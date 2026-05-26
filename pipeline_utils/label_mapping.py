"""
Mapea labels internos (CC_NIT, CED_NOMBRE, etc.) a los labels que espera la UI
de DocuInsight (definidos en schemas.EXPECTED_ENTITIES).

VERSION 2 (2026-05-24) — actualizado para los 4 modelos GLiNER fine-tuned
(notebook 24 del repo SinergiaLabProyecto). El set de labels canonicos por
tipologia es exactamente el del fine-tune; cualquier label fuera de este
mapping es ignorado por la UI.
"""
from __future__ import annotations

# {(doctype_docuinsight, label_interno_modelo) -> label_docuinsight}
_LABEL_MAP: dict[tuple[str, str], str] = {
    # ---- Cedula (8 campos) ----
    ("cedula", "CED_NOMBRE"):            "nombres",
    ("cedula", "CED_APELLIDO"):          "apellidos",
    ("cedula", "CED_NUMERO"):            "numero_cedula",
    ("cedula", "CED_LUGAR_EXPEDICION"):  "lugar_expedicion",
    ("cedula", "CED_FECHA_EXPEDICION"):  "fecha_expedicion",
    ("cedula", "CED_FECHA_NACIMIENTO"):  "fecha_nacimiento",
    ("cedula", "CED_LUGAR_NACIMIENTO"):  "lugar_nacimiento",
    ("cedula", "CED_SEXO"):              "sexo",

    # ---- Camara de Comercio (5 campos) ----
    ("camara_comercio", "CC_RAZON_SOCIAL"):       "razon_social",
    ("camara_comercio", "CC_NIT"):                "nit",
    ("camara_comercio", "CC_NUM_MATRICULA"):      "numero_matricula",
    ("camara_comercio", "CC_FECHA_CONSTITUCION"): "fecha_constitucion",
    ("camara_comercio", "CC_DOMICILIO"):          "domicilio",

    # ---- RUT (8 campos) ----
    ("rut", "RUT_NIT"):                 "nit",
    ("rut", "RUT_RAZON_SOCIAL"):        "razon_social",
    ("rut", "RUT_DIRECCION_PPAL"):      "direccion",
    ("rut", "RUT_CIUDAD"):              "ciudad",
    ("rut", "RUT_DEPARTAMENTO"):        "departamento",
    ("rut", "RUT_RESPONSABILIDADES"):   "responsabilidades",
    ("rut", "RUT_FECHA_GENERACION"):    "fecha_generacion",
    ("rut", "RUT_REGIMEN"):             "regimen",

    # ---- Poliza (7 campos) ----
    ("poliza", "POL_NUM_POLIZA"):        "numero_poliza",
    ("poliza", "POL_TOMADOR"):           "tomador",
    ("poliza", "POL_PRIMA"):             "prima",
    ("poliza", "POL_ASEGURADORA"):       "aseguradora",
    ("poliza", "POL_VIGENCIA_DESDE"):    "vigencia_desde",
    ("poliza", "POL_VIGENCIA_HASTA"):    "vigencia_hasta",
    # POL_ENTIDAD_ASEGURADA: el modelo lo extrae pero el schema v2 lo elimino
    # por solaparse con tomador. Si en el futuro se quiere mostrar, mapear aqui.
}


# Lista de labels canonicos que se le piden a GLiNER en inferencia, por tipologia.
# Es el conjunto sobre el que se fine-tuneo el modelo, NO los UI labels.
GLINER_LABELS_BY_DOCTYPE: dict[str, list[str]] = {
    "camara_comercio": [
        "CC_NIT", "CC_RAZON_SOCIAL", "CC_NUM_MATRICULA",
        "CC_FECHA_CONSTITUCION", "CC_DOMICILIO",
    ],
    "cedula": [
        "CED_NUMERO", "CED_NOMBRE", "CED_APELLIDO",
        "CED_FECHA_NACIMIENTO", "CED_LUGAR_NACIMIENTO",
        "CED_FECHA_EXPEDICION", "CED_LUGAR_EXPEDICION", "CED_SEXO",
    ],
    "poliza": [
        "POL_NUM_POLIZA", "POL_TOMADOR", "POL_ASEGURADORA",
        "POL_PRIMA", "POL_VIGENCIA_DESDE", "POL_VIGENCIA_HASTA",
        "POL_ENTIDAD_ASEGURADA",
    ],
    "rut": [
        "RUT_NIT", "RUT_RAZON_SOCIAL", "RUT_DIRECCION_PPAL",
        "RUT_CIUDAD", "RUT_DEPARTAMENTO", "RUT_RESPONSABILIDADES",
        "RUT_FECHA_GENERACION", "RUT_REGIMEN",
    ],
}


def to_ui_label(doctype: str, internal_label: str) -> str | None:
    """Devuelve el label de DocuInsight o None si no aplica."""
    return _LABEL_MAP.get((doctype, internal_label))
