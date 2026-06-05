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

import os
import time
from pathlib import Path

# protobuf 7.x rompe los _pb2 de PaddlePaddle 2.6. Forzar impl pura Python
# antes de que cualquier import (gliner/transformers/paddle) cargue protobuf.
# Cubre el path standalone (importar RealPipeline sin pasar por app.py).
os.environ.setdefault("PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION", "python")

from schemas import DocType, DocumentResult, Entity
from pipeline_utils.classifier import DocumentClassifier
from pipeline_utils.ner_gliner2 import NERDispatcher  # variante v2: modelo unificado de las companeras
from pipeline_utils.ocr import extract_text
from pipeline_utils.postproc import clean_entities

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

    # ------------------------------------------------------------------
    # Fases expuestas individualmente para que la UI muestre el avance en
    # tiempo real (1/3 OCR -> 2/3 Clasificacion -> 3/3 NER). process() las
    # orquesta en un solo llamado para callers que no necesitan el paso-a-paso.
    # ------------------------------------------------------------------

    def run_ocr(self, file_bytes: bytes, filename: str, force_ocr: bool = False):
        """Fase 1 — extrae texto. Devuelve (texto, motor)."""
        return extract_text(file_bytes, filename, force_ocr=force_ocr)

    def run_classify(self, text: str):
        """Fase 2 — clasifica la tipologia. Devuelve (doctype_str, conf, DocType)."""
        doctype_str, conf = self.classifier.predict(text)
        if conf < MIN_CLASSIFIER_CONFIDENCE:
            doctype_str = "desconocido"
        doc_type = _DOCTYPE_FROM_STR.get(doctype_str, DocType.DESCONOCIDO)
        return doctype_str, conf, doc_type

    def needs_rut_reocr(self, doc_type, engine) -> bool:
        """True si es un RUT digital leido por PyMuPDF (requiere re-OCR Paddle)."""
        return doc_type == DocType.RUT and engine == "pymupdf"

    def run_ner(self, text: str, doctype_str: str) -> list[Entity]:
        """Fase 3 — extrae entidades + limpia ruido OCR. Devuelve list[Entity]."""
        if doctype_str == "desconocido":
            return []
        extracted = self.ner.extract(text, doctype_str)
        extracted = clean_entities(extracted)
        return [
            Entity(label=e.ui_label, value=e.value, confidence=e.confidence)
            for e in extracted
        ]

    def process(self, file_bytes: bytes, filename: str) -> DocumentResult:
        start = time.time()
        try:
            # 1. OCR
            text, engine = self.run_ocr(file_bytes, filename)
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
            doctype_str, doctype_conf, doc_type = self.run_classify(text)

            # 2.5. Re-OCR forzado para RUT digital (cajas DIAN por digito).
            if self.needs_rut_reocr(doc_type, engine):
                text, engine = self.run_ocr(file_bytes, filename, force_ocr=True)

            # 3. NER
            entities = self.run_ner(text, doctype_str)

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
