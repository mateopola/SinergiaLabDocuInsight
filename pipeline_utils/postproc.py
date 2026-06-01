"""
Post-procesamiento de entidades extraidas por GLiNER.

El modelo marca bien el span, pero el OCR a veces pega la etiqueta del campo
o texto colindante al valor (ej. "NUMERO1.020.818.311", "29-AGO-2014BOGOTA").
Este modulo limpia esos artefactos con reglas por tipo de campo.

Principio: CONSERVADOR. Si una regla no matchea con claridad, se devuelve el
valor original (solo .strip()). Nunca se vacia un campo -- preferimos mostrar
el valor crudo antes que perder el dato.
"""
from __future__ import annotations

import re
from dataclasses import replace

# Meses validos del calendario en cedulas/documentos colombianos (3 letras).
_MESES = {"ENE", "FEB", "MAR", "ABR", "MAY", "JUN",
          "JUL", "AGO", "SEP", "OCT", "NOV", "DIC"}

# Palabras-etiqueta que el OCR suele pegar al inicio de un valor.
_PREFIJOS_LABEL = re.compile(
    r"^\s*(NUMERO|NUMRO|NUM|NIT|MATRICULA|MATRICULAS|No\.?|N°|NRO\.?)\s*[:\-]?\s*",
    re.IGNORECASE,
)


def _strip_label_prefix(value: str) -> str:
    return _PREFIJOS_LABEL.sub("", value).strip()


def _normalizar_mes(mes: str) -> str:
    """Corrige errores OCR comunes en la abreviatura del mes (0->O, 1->I)."""
    fix = mes.upper().replace("0", "O").replace("1", "I").replace("5", "S")
    return fix if fix in _MESES else mes.upper()


# ---------------------------------------------------------------------------
# Cleaners por campo
# ---------------------------------------------------------------------------

def _clean_numero_cedula(value: str) -> str:
    v = _strip_label_prefix(value)
    # Numero de cedula: 6-10 digitos, usualmente con puntos de miles.
    m = re.search(r"\d{1,3}(?:\.\d{3})+|\d{6,11}", v)
    return m.group(0) if m else v


def _clean_nit(value: str) -> str:
    v = _strip_label_prefix(value)
    # NIT: 6-12 digitos (con puntos opcionales) + digito de verificacion opcional.
    m = re.search(r"\d{1,3}(?:\.\d{3})+(?:-\d)?|\d{6,12}(?:-\d)?", v)
    return m.group(0) if m else v


def _clean_matricula(value: str) -> str:
    v = _strip_label_prefix(value)
    m = re.search(r"\d{4,}", v)
    return m.group(0) if m else v


def _clean_fecha_dmy(value: str) -> str:
    """Fechas tipo cedula: DD-MMM-AAAA (ej. 29-AGO-2014). Recorta lo pegado
    despues del anio y normaliza el mes."""
    v = value.strip()
    m = re.search(r"(\d{1,2})[\-\s]([A-Z0-9]{3})[\-\s](\d{4})", v, re.IGNORECASE)
    if not m:
        return v
    dia, mes, anio = m.group(1), _normalizar_mes(m.group(2)), m.group(3)
    return f"{int(dia):02d}-{mes}-{anio}"


# Mapeo ui_label -> funcion de limpieza. Los campos no listados solo se .strip().
_CLEANERS = {
    "numero_cedula":    _clean_numero_cedula,
    "nit":              _clean_nit,
    "numero_matricula": _clean_matricula,
    "fecha_nacimiento": _clean_fecha_dmy,
    "fecha_expedicion": _clean_fecha_dmy,
}


def clean_value(ui_label: str, value: str) -> str:
    """Limpia un valor segun su tipo de campo. Conservador: si la regla no
    aplica, devuelve el valor con strip."""
    if not value:
        return value
    cleaner = _CLEANERS.get(ui_label)
    try:
        return cleaner(value) if cleaner else value.strip()
    except Exception:
        # Ante cualquier error de regex inesperado, no perdemos el dato.
        return value.strip()


def clean_entities(entities):
    """Aplica clean_value a una lista de ExtractedEntity (devuelve lista nueva).

    Acepta cualquier objeto con atributos .ui_label y .value que soporte
    dataclasses.replace (ExtractedEntity es frozen dataclass).
    """
    out = []
    for e in entities:
        nuevo = clean_value(e.ui_label, e.value)
        out.append(replace(e, value=nuevo) if nuevo != e.value else e)
    return out
