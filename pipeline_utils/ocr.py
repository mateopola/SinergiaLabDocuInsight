"""
OCR dispatcher.

Si el archivo es un PDF con texto extraible (digital) -> PyMuPDF, rapido.
Si es imagen o PDF escaneado -> PaddleOCR, mas lento pero robusto.

Devuelve el texto del documento completo (concatenando paginas con \\n\\n).
Para PDFs largos limita a las primeras 10 paginas (mismo limite usado en el
training set de los modelos NER GLiNER, que se entrenaron sobre output
PaddleOCR -- ver PADDLE_OCR_EVALUATION.md del repo SinergiaLabProyecto).

VERSION 2 (2026-05-24): migrado de EasyOCR a PaddleOCR por dos razones:
  1. Match con la distribucion de tokens del training (GLiNER aprendio sobre
     output Paddle, no Easy).
  2. EasyOCR usa onnxruntime que entra en conflicto con torch (GLiNER) y
     produce segfault al cargar ambos en CPU Windows.
"""
from __future__ import annotations

import io
import re
from typing import Optional

# Limite de paginas alineado con el dataset de entrenamiento
MAX_PAGES = 10
# Umbral de chars por pagina debajo del cual se considera "no extraible"
MIN_CHARS_PER_PAGE = 20


def extract_text(file_bytes: bytes, filename: str, force_ocr: bool = False) -> tuple[str, str]:
    """
    Extrae texto del archivo. Devuelve (texto, motor_usado).

    motor_usado: 'pymupdf' | 'paddleocr'.

    force_ocr: si True, salta PyMuPDF y va directo a PaddleOCR. Util para
    re-procesar PDFs digitales cuyo orden de tokens de PyMuPDF rompe los
    modelos NER (caso tipico: formulario DIAN del RUT con cajas individuales
    por digito). Los modelos GLiNER fueron entrenados sobre texto PaddleOCR
    (orden de lectura visual); forzar OCR los pone en la distribucion del
    train.
    """
    lower = filename.lower()
    is_pdf = lower.endswith(".pdf")
    is_image = lower.endswith((".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp"))

    if is_pdf:
        if not force_ocr:
            text, _ = _try_pymupdf(file_bytes)
            if text and _looks_extractable(text):
                return _normalizar_texto(text), "pymupdf"
        # PDF escaneado, sin texto, o re-procesamiento forzado
        ocr_text = _ocr_pdf_with_paddle(file_bytes)
        return _normalizar_texto(ocr_text), "paddleocr"

    if is_image:
        return _normalizar_texto(_ocr_image_bytes_with_paddle(file_bytes)), "paddleocr"

    raise ValueError(f"Formato no soportado: {filename}")


# Compat alias: real_models.py viejo todavia pasa force_easyocr=True. Aceptamos
# ambos nombres para no romper. Nuevo codigo debe usar force_ocr.
def extract_text_compat(file_bytes: bytes, filename: str, **kw) -> tuple[str, str]:
    if "force_easyocr" in kw and "force_ocr" not in kw:
        kw["force_ocr"] = kw.pop("force_easyocr")
    return extract_text(file_bytes, filename, **kw)


# ---------------------------------------------------------------------------
# PyMuPDF
# ---------------------------------------------------------------------------

def _try_pymupdf(file_bytes: bytes) -> tuple[Optional[str], str]:
    """
    Extrae con PyMuPDF usando `get_text('blocks')` y reordena por coordenadas
    (top->bottom, left->right). El default `get_text()` puede entregar texto
    en el orden interno del PDF -- no en el orden de lectura visual -- y eso
    causa mismatch con lo que vieron los modelos NER.
    """
    import fitz  # PyMuPDF
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    pages = []
    try:
        for i, page in enumerate(doc):
            if i >= MAX_PAGES:
                break
            page_text = _page_text_in_reading_order(page)
            if len(page_text.strip()) < MIN_CHARS_PER_PAGE:
                continue
            pages.append(page_text)
        text = "\n\n".join(pages)
    finally:
        doc.close()
    return text, "pymupdf"


def _page_text_in_reading_order(page) -> str:
    blocks = page.get_text("blocks")
    text_blocks = [b for b in blocks if b[6] == 0 and b[4].strip()]
    text_blocks.sort(key=lambda b: (round(b[1] / 5), b[0]))
    return "\n".join(b[4].rstrip() for b in text_blocks)


def _looks_extractable(text: str) -> bool:
    return len(text.strip()) >= MIN_CHARS_PER_PAGE


# ---------------------------------------------------------------------------
# PaddleOCR
# ---------------------------------------------------------------------------

# Cache del lector Paddle (carga es lenta: descarga modelos la primera vez,
# ~30-60s; despues ~0.5s por imagen en CPU).
_paddle_ocr = None


def _get_paddle_ocr():
    global _paddle_ocr
    if _paddle_ocr is None:
        # Suprimir logs ruidosos de Paddle al inicializar
        import logging
        logging.getLogger("ppocr").setLevel(logging.ERROR)
        from paddleocr import PaddleOCR
        _paddle_ocr = PaddleOCR(
            use_angle_cls=True,
            lang="es",
            show_log=False,
            use_gpu=False,
        )
    return _paddle_ocr


def _paddle_result_to_text(result) -> str:
    """
    Convierte el output de PaddleOCR.ocr() a texto.

    PaddleOCR 2.8 devuelve una lista por imagen. Cada item es:
        [bbox, (text, confidence)]
    o None si no detecto nada. El bbox ya esta ordenado top->bottom,
    left->right por Paddle.
    """
    if not result:
        return ""
    # Para una sola imagen result = [page_lines]; page_lines puede ser None
    lines = result[0] if isinstance(result, list) and len(result) > 0 else result
    if not lines:
        return ""
    return "\n".join(
        line[1][0]
        for line in lines
        if line and len(line) >= 2 and line[1] and len(line[1]) >= 1
    )


def _ocr_image_bytes_with_paddle(img_bytes: bytes) -> str:
    ocr = _get_paddle_ocr()
    import numpy as np
    from PIL import Image
    img = Image.open(io.BytesIO(img_bytes))
    # Paddle espera BGR (estilo OpenCV)
    arr = np.array(img.convert("RGB"))[:, :, ::-1]
    result = ocr.ocr(arr, cls=True)
    return _paddle_result_to_text(result)


def _ocr_pdf_with_paddle(pdf_bytes: bytes) -> str:
    """Renderiza cada pagina del PDF a imagen y la pasa por PaddleOCR.
    Filtra paginas en blanco para no confundir clasificador/NER."""
    import fitz
    ocr = _get_paddle_ocr()
    import numpy as np
    from PIL import Image

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    pages_text = []
    try:
        for i, page in enumerate(doc):
            if i >= MAX_PAGES:
                break
            # render a 200 DPI (consistente con el preprocessing del training)
            pix = page.get_pixmap(dpi=200)
            img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            arr = np.array(img)[:, :, ::-1]  # RGB -> BGR
            result = ocr.ocr(arr, cls=True)
            page_text = _paddle_result_to_text(result)
            if len(page_text.strip()) < MIN_CHARS_PER_PAGE:
                continue  # skip blank/cover pages
            pages_text.append(page_text)
    finally:
        doc.close()
    if not pages_text:
        raise RuntimeError(
            "PaddleOCR no pudo extraer texto de ninguna pagina. "
            "El PDF puede estar danado o totalmente en blanco."
        )
    return "\n\n".join(pages_text)


# ---------------------------------------------------------------------------
# Normalizacion del texto OCR
# ---------------------------------------------------------------------------
# Alinea el texto de inferencia con el dataset de training de los modelos
# (clasificador C-1 y los 4 GLiNER fueron entrenados sobre texto normalizado
# con estas mismas reglas).
#
# Reglas:
#   - Bloque de digitos individuales consecutivos -> unir (NIT/cedula)
#   - Indices de fila DIAN secuenciales (1,2,3,...) -> eliminar
#   - Numeros cortos sueltos en contexto de tabla -> descartar
#   - Digitos separados por espacios en la misma linea -> unir
#   - Espacios multiples -> uno; espacios antes de puntuacion -> limpios
#   - Mas de 2 saltos -> 1 linea en blanco
# ---------------------------------------------------------------------------

def _normalizar_texto(texto: str) -> str:
    if not texto:
        return texto

    lineas = texto.splitlines()
    resultado: list[str] = []
    i = 0
    while i < len(lineas):
        linea = lineas[i].strip()

        # Bloque de digitos individuales consecutivos
        if re.match(r"^\d$", linea):
            bloque = [linea]
            j = i + 1
            while j < len(lineas) and re.match(r"^\d$", lineas[j].strip()):
                bloque.append(lineas[j].strip())
                j += 1
            if len(bloque) >= 4:
                nums = [int(d) for d in bloque]
                es_secuencial = all(nums[k + 1] == nums[k] + 1 for k in range(len(nums) - 1))
                if es_secuencial:
                    i = j   # indices de fila DIAN -> descartar
                    continue
                resultado.append("".join(bloque))   # NIT/cedula -> unir
                i = j
                continue

        # Numero corto suelto en contexto de tabla -> descartar
        if re.match(r"^\d{1,2}$", linea):
            num = int(linea)
            if 1 <= num <= 99:
                prev = resultado[-1].strip() if resultado else ""
                sig = lineas[i + 1].strip() if i + 1 < len(lineas) else ""
                if (re.match(r"^\d{1,2}$", prev) or re.match(r"^\d{1,2}$", sig) or
                        re.match(r"^\d{1,3}\.", prev) or re.match(r"^\d{1,3}\.", sig)):
                    i += 1
                    continue

        # Digitos separados por espacios en la misma linea -> unir
        linea = re.sub(
            r"(?<!\w)(\d[\d \.\-]{4,})(?!\w)",
            lambda m: re.sub(r"\s+", "", m.group()),
            linea,
        )
        linea = re.sub(r" {2,}", " ", linea)
        linea = re.sub(r" ([,;:\.\)\]])", r"\1", linea)
        linea = linea.strip()

        if linea:
            resultado.append(linea)
        elif resultado and resultado[-1] != "":
            resultado.append("")
        i += 1

    out = "\n".join(resultado)
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out.strip()
