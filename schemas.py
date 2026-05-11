"""
Contrato de datos de DocuInsight.

Este archivo define las estructuras que viajan entre el pipeline de modelos
y la interfaz. Es el contrato que comparten todos los miembros del equipo.

Si necesitas agregar un nuevo tipo documental o una nueva entidad, hazlo aquí.
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
# Entidades esperadas por tipo documental.
# Si los compañeros amplían o reducen lo que extraen, actualizar esto.
# ---------------------------------------------------------------------------

EXPECTED_ENTITIES: dict[DocType, list[str]] = {
    DocType.CEDULA: [
        "nombres",
        "apellidos",
        "numero_cedula",
        "fecha_nacimiento",
        "lugar_nacimiento",
        "fecha_expedicion",
        "lugar_expedicion",
        "sexo",
    ],
    DocType.CAMARA_COMERCIO: [
        "razon_social",
        "nit",
        "numero_matricula",
        "fecha_matricula",
        "representante_legal",
        "cedula_representante",
        "domicilio",
        "objeto_social",
        "capital",
        "estado_sociedad",
        "vigencia",
    ],
    DocType.RUT: [
        "nit",
        "razon_social",
        "direccion",
        "ciudad",
        "actividad_economica_ciiu",
        "responsabilidades",
        "fecha_generacion",
    ],
    DocType.POLIZA: [
        "aseguradora",
        "tomador",
        "asegurado",
        "beneficiario",
        "numero_poliza",
        "ramo",
        "vigencia_desde",
        "vigencia_hasta",
        "valor_asegurado",
        "prima",
        "amparos",
    ],
}


def humanize_entity_label(label: str) -> str:
    """Convierte 'numero_cedula' → 'Número de cédula' (display)."""
    mapping = {
        "nombres": "Nombres",
        "apellidos": "Apellidos",
        "numero_cedula": "Número de cédula",
        "fecha_nacimiento": "Fecha de nacimiento",
        "lugar_nacimiento": "Lugar de nacimiento",
        "fecha_expedicion": "Fecha de expedición",
        "lugar_expedicion": "Lugar de expedición",
        "sexo": "Sexo",
        "razon_social": "Razón social",
        "nit": "NIT",
        "numero_matricula": "Número de matrícula",
        "fecha_matricula": "Fecha de matrícula",
        "representante_legal": "Representante legal",
        "cedula_representante": "Cédula del representante",
        "domicilio": "Domicilio",
        "objeto_social": "Objeto social",
        "capital": "Capital",
        "estado_sociedad": "Estado de la sociedad",
        "vigencia": "Vigencia",
        "direccion": "Dirección",
        "ciudad": "Ciudad",
        "actividad_economica_ciiu": "Actividad económica (CIIU)",
        "responsabilidades": "Responsabilidades tributarias",
        "fecha_generacion": "Fecha de generación",
        "aseguradora": "Aseguradora",
        "tomador": "Tomador",
        "asegurado": "Asegurado",
        "beneficiario": "Beneficiario",
        "numero_poliza": "Número de póliza",
        "ramo": "Ramo",
        "vigencia_desde": "Vigencia desde",
        "vigencia_hasta": "Vigencia hasta",
        "valor_asegurado": "Valor asegurado",
        "prima": "Prima",
        "amparos": "Amparos",
    }
    return mapping.get(label, label.replace("_", " ").capitalize())
