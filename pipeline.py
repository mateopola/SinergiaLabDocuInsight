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
    Factory. En desarrollo usar mock; en producción (v2 Space) usar el real.

    Degradación elegante: si se pide el pipeline real pero el backend NER
    (gliner2) no está instalado en el entorno —p.ej. en una máquina local sin
    la dependencia pesada—, en vez de romper recién al llegar al NER se cae a
    modo demostración (MockPipeline) y se marca con `_demo_fallback` para que
    la UI muestre un aviso. En el Space v2 gliner2 SÍ está instalado, así que
    ahí se usa el pipeline real sin cambios.
    """
    if use_mock:
        from mock_models import MockPipeline
        return MockPipeline()

    import importlib.util

    def _demo(reason: str):
        from mock_models import MockPipeline
        p = MockPipeline()
        p._demo_fallback = reason
        return p

    if importlib.util.find_spec("gliner2") is None:
        return _demo("El modelo real (gliner2) no está instalado en este entorno.")
    try:
        from real_models import RealPipeline
        return RealPipeline()
    except Exception as exc:  # carga de modelos/clasificador falló
        return _demo(f"No se pudo cargar el pipeline real: {type(exc).__name__}.")
