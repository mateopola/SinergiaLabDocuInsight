"""
Placeholder para la implementación real del pipeline.

Este archivo es responsabilidad del equipo de modelos. Debe implementar
la clase RealPipeline cumpliendo el Protocol DocumentPipeline definido
en pipeline.py.

Stack candidato (en evaluación):
  - OCR:           PaddleOCR  |  EasyOCR
  - Clasificación: Regresión logística  |  BETO  |  LightGBM
  - NER:           GLiNER 2  |  spaCy  |  otro

Contrato:
  - Entrada:  bytes del archivo + nombre del archivo
  - Salida:   DocumentResult (ver schemas.py)
  - Entidades esperadas por tipo: EXPECTED_ENTITIES en schemas.py

Notas para integración:
  1. Detectar si el PDF tiene texto extraíble (PyMuPDF) antes de aplicar OCR.
  2. Si es imagen escaneada o PDF sin texto → OCR.
  3. Texto limpio → clasificador → tipo documental + confianza.
  4. Texto + tipo documental → extractor de entidades (NER guiado por tipo).
  5. Construir DocumentResult y retornarlo.
"""

from __future__ import annotations

from schemas import DocumentResult


class RealPipeline:
    def __init__(self) -> None:
        # TODO (equipo de modelos):
        #   self.ocr = ...
        #   self.classifier = ...
        #   self.ner = ...
        raise NotImplementedError(
            "El pipeline real aún no está integrado. "
            "Mantén el toggle 'Usar modelos mock' activado en la sidebar."
        )

    def process(self, file_bytes: bytes, filename: str) -> DocumentResult:
        # TODO (equipo de modelos):
        #   1. Detectar formato y extraer texto (OCR si aplica)
        #   2. Clasificar tipo documental
        #   3. Extraer entidades según el tipo
        #   4. Retornar DocumentResult
        raise NotImplementedError
