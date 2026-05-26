"""
Contrato de datos de DocuInsight.

Este archivo define las estructuras que viajan entre el pipeline de modelos
y la interfaz. Es el contrato que comparten todos los miembros del equipo.

Si necesitas agregar un nuevo tipo documental o una nueva entidad, hazlo aquí.

VERSIÓN 2 (2026-05-17): set de entidades ampliado a 27 campos según la
decisión documentada en PADDLE_OCR_EVALUATION.md del repo SinergiaLabProyecto.
Combina extracción NER (15 campos) + regex extractors (12 campos) sobre OCR
generado por PaddleOCR.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class DocType(str, Enum):
    CEDULA = "cedula"
    CAMARA_COMERCIO = "camara_comercio"
    RUT = "rut"
    POLIZA = "poliza"
    DESCONOCIDO = "desconocido"


DOC_TYPE_LABELS: dict[DocType, str] = {
    DocType.CEDULA: "Cédula de Ciudadanía",
    DocType.CAMARA_COMERCIO: "Cámara de Comercio",
    DocType.RUT: "RUT",
    DocType.POLIZA: "Póliza",
    DocType.DESCONOCIDO: "Desconocido",
}


@dataclass
class Entity:
    """Una entidad nombrada extraída de un documento."""
    label: str          # nombre técnico, p.ej. "numero_cedula"
    value: str          # valor extraído
    confidence: float = 1.0   # 0..1
    source: str = "ner"       # 'ner' | 'regex' — útil para debugging/UI


@dataclass
class DocumentResult:
    """Resultado del procesamiento de un único documento."""
    filename: str
    doc_type: DocType
    doc_type_confidence: float   # 0..1
    extracted_text: str          # texto OCR / texto extraído del PDF
    entities: list[Entity] = field(default_factory=list)
    processing_time_ms: int = 0
    error: Optional[str] = None

    @property
    def doc_type_label(self) -> str:
        return DOC_TYPE_LABELS[self.doc_type]


# ---------------------------------------------------------------------------
# Entidades esperadas por tipo documental (set v2 — 27 campos).
# Origen: NER (modelo aprendido) o regex (anchor léxico). Ver
# PADDLE_OCR_EVALUATION.md para la justificación de cada campo.
# ---------------------------------------------------------------------------

EXPECTED_ENTITIES: dict[DocType, list[str]] = {
    DocType.CEDULA: [
        # NER (5)
        "nombres",
        "apellidos",
        "numero_cedula",
        "lugar_expedicion",
        "fecha_expedicion",
        # regex con cobertura parcial 52-65% (3)
        "fecha_nacimiento",
        "lugar_nacimiento",
        "sexo",
    ],
    DocType.CAMARA_COMERCIO: [
        # NER (4)
        "razon_social",
        "nit",
        "numero_matricula",
        "fecha_constitucion",
        # regex (1)
        "domicilio",
    ],
    DocType.RUT: [
        # NER (3) — actividad_economica_ciiu eliminado por bajo valor de negocio
        "nit",
        "razon_social",
        "direccion",
        # regex (5)
        "ciudad",
        "departamento",
        "responsabilidades",
        "fecha_generacion",
        "regimen",
    ],
    DocType.POLIZA: [
        # NER (3) — asegurado eliminado por solaparse con tomador
        "numero_poliza",
        "tomador",
        "prima",
        # regex (3)
        "aseguradora",
        "vigencia_desde",
        "vigencia_hasta",
    ],
}


def humanize_entity_label(label: str) -> str:
    """Convierte 'numero_cedula' → 'Número de cédula' (display)."""
    mapping = {
        # Cédula
        "nombres":              "Nombres",
        "apellidos":            "Apellidos",
        "numero_cedula":        "Número de cédula",
        "lugar_expedicion":     "Lugar de expedición",
        "fecha_expedicion":     "Fecha de expedición",
        "fecha_nacimiento":     "Fecha de nacimiento",
        "lugar_nacimiento":     "Lugar de nacimiento",
        "sexo":                 "Sexo",
        # Cámara de Comercio
        "razon_social":         "Razón social",
        "nit":                  "NIT",
        "numero_matricula":     "Número de matrícula",
        "fecha_constitucion":   "Fecha de constitución",
        "domicilio":            "Domicilio",
        # RUT
        "direccion":            "Dirección principal",
        "ciudad":               "Ciudad",
        "departamento":         "Departamento",
        "responsabilidades":    "Responsabilidades tributarias",
        "fecha_generacion":     "Fecha de generación",
        "regimen":              "Régimen",
        # Póliza
        "numero_poliza":        "Número de póliza",
        "tomador":              "Tomador",
        "prima":                "Prima",
        "aseguradora":          "Aseguradora",
        "vigencia_desde":       "Vigencia desde",
        "vigencia_hasta":       "Vigencia hasta",
    }
    return mapping.get(label, label.replace("_", " ").capitalize())
