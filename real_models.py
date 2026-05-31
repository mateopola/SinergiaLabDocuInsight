"""
Pipeline real de DocuInsight.

Orquesta:
  1. OCR (PyMuPDF para digitales, PaddleOCR para escaneados)
  2. Clasificacion (C-1 TF-IDF + Regresion Logistica, Fase 3.0)
  3. NER por tipologia (GLiNER fine-tuned, 4 modelos -- Fase 3.1, nb24)

La carga de modelos ocurre 1 sola vez en __init__ (cacheada por Streamlit
a traves del singleton del pipeline).
"""
from __future__ import annotations

import time
from pathlib import Path

from schemas import DocType, DocumentResult, Entity
from pipeline_utils.classifier import DocumentClassifier
from pipeline_utils.ner import NERDispatcher
from pipeline_utils.ocr import extract_text

# Mapeo del string que devuelve el clasificador al enum DocType de DocuInsight
_DOCTYPE_FROM_STR = {
    "cedula":          DocType.CEDULA,
    "camara_comercio": DocType.CAMARA_COMERCIO,
    "rut":             DocType.RUT,
    "poliza":          DocType.POLIZA,
    "desconocido":     DocType.DESCONOCIDO,
}

# Umbral debajo del cual el clasificador "no esta seguro" -> DESCONOCIDO
MIN_CLASSIFIER_CONFIDENCE = 0.50


class RealPipeline:
    """Implementacion productiva del DocumentPipeline Protocol."""

    def __init__(self) -> None:
        models_dir = Path(__file__).parent / "models"
        if not models_dir.exists():
            raise FileNotFoundError(
                f"No se encontro el directorio de modelos: {models_dir}. "
                "Asegurate de haber copiado los modelos desde SinergiaLabProyecto."
            )
        self.classifier = DocumentClassifier(models_dir / "classifier")
        self.ner = NERDispatcher(models_dir)

    def process(self, file_bytes: bytes, filename: str) -> DocumentResult:
        start = time.time()
        try:
            # 1. OCR / extraccion de texto (PyMuPDF si digital, PaddleOCR si no)
            text, engine = extract_text(file_bytes, filename)
            if not text or not text.strip():
                return DocumentResult(
                    filename=filename,
                    doc_type=DocType.DESCONOCIDO,
                    doc_type_confidence=0.0,
                    extracted_text="",
                    error="No se pudo extraer texto del documento.",
                    processing_time_ms=int((time.time() - start) * 1000),
                )

            # 2. Clasificacion
            doctype_str, doctype_conf = self.classifier.predict(text)
            if doctype_conf < MIN_CLASSIFIER_CONFIDENCE:
                doctype_str = "desconocido"
            doc_type = _DOCTYPE_FROM_STR.get(doctype_str, DocType.DESCONOCIDO)

            # 2.5. Re-OCR forzado para RUT digital.
            # El formulario DIAN tiene el NIT/CIIU en cajas individuales por
            # digito; PyMuPDF las extrae como tokens sueltos ("0 2", "1 8")
            # que rompen al modelo NER. PaddleOCR lee en orden visual y produce
            # la distribucion de tokens que vio el training de los 4 GLiNER.
            # ~30-60s extra por RUT digital, pero el output es usable.
            if doc_type == DocType.RUT and engine == "pymupdf":
                text, engine = extract_text(file_bytes, filename, force_ocr=True)

            # 3. NER (solo si la clase es conocida)
            entities: list[Entity] = []
            if doc_type != DocType.DESCONOCIDO:
                extracted = self.ner.extract(text, doctype_str)
                entities = [
                    Entity(label=e.ui_label, value=e.value, confidence=e.confidence)
                    for e in extracted
                ]

            return DocumentResult(
                filename=filename,
                doc_type=doc_type,
                doc_type_confidence=doctype_conf,
                extracted_text=text,
                entities=entities,
                processing_time_ms=int((time.time() - start) * 1000),
            )
        except Exception as exc:
            return DocumentResult(
                filename=filename,
                doc_type=DocType.DESCONOCIDO,
                doc_type_confidence=0.0,
                extracted_text="",
                error=f"{type(exc).__name__}: {exc}",
                processing_time_ms=int((time.time() - start) * 1000),
            )
