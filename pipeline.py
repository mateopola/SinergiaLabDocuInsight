"""
Orquestación del pipeline.

Define el contrato (Protocol) que cualquier implementación real del pipeline
debe cumplir, y proporciona una factory que elige entre el pipeline mock
(para desarrollo de UI) y el real (cuando esté listo).
"""

from __future__ import annotations

from typing import Protocol

from schemas import DocumentResult


class DocumentPipeline(Protocol):
    """
    Contrato que toda implementación de pipeline debe cumplir.

    Recibe los bytes crudos de un archivo (PDF, PNG, JPG) y su nombre,
    y retorna un DocumentResult con tipo documental + entidades extraídas.

    La implementación es libre de hacer internamente:
      - Detección de formato (PDF nativo vs imagen escaneada)
      - OCR cuando sea necesario
      - Clasificación
      - NER
    """

    def process(self, file_bytes: bytes, filename: str) -> DocumentResult:
        ...


def get_pipeline(use_mock: bool = True) -> DocumentPipeline:
    """
    Factory. En desarrollo usar mock; cuando los modelos reales estén
    integrados, pasar use_mock=False.
    """
    if use_mock:
        from mock_models import MockPipeline
        return MockPipeline()
    else:
        from real_models import RealPipeline
        return RealPipeline()
