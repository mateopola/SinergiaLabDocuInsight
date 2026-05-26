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
                return text, "pymupdf"
        # PDF escaneado, sin texto, o re-procesamiento forzado
        ocr_text = _ocr_pdf_with_paddle(file_bytes)
        return ocr_text, "paddleocr"

    if is_image:
        return _ocr_image_bytes_with_paddle(file_bytes), "paddleocr"

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
