"""
Datos quemados (seed) + lógica de métricas de negocio para el dashboard.

Objetivo: que el dashboard "cockpit ejecutivo" tenga SIEMPRE una base rica de
documentos ya procesados (aunque la sesión esté vacía), para demos y video. Lo
que el usuario procesa en vivo se suma encima de este seed.

Cada documento es un `DocumentResult` real (mismos campos que produce el pipeline)
con confianza por campo, latencia y una fecha de procesamiento (`_processed_at`,
atributo dinámico) repartida en los últimos 30 días para alimentar las series de
tiempo. Algunos docs traen 1-2 campos de baja confianza a propósito: alimentan la
cola de revisión HITL.

Los campos por tipología coinciden con el esquema del modelo v2 (GLiNER2 unificado
de las compañeras, ver pipeline_utils/ner_gliner2.py) para que el seed sea
consistente con lo que se extrae en vivo.
"""
from __future__ import annotations

import random
from datetime import datetime, timedelta

from schemas import DocType, DocumentResult, Entity

# ---------------------------------------------------------------------------
# Parámetros de negocio (base "Colombia típico", confirmada con el usuario)
# ---------------------------------------------------------------------------
MANUAL_MIN_PER_DOC = 8.0       # minutos que toma capturar un doc a mano
REVIEW_MIN_PER_DOC = 2.0       # minutos de revisión humana cuando un doc cae en la cola HITL
COST_PER_HOUR_COP = 12_000     # costo cargado de un operador de data-entry (COP/hora)
MANUAL_ERROR_RATE = 0.04       # 4% de error en captura manual
AUTO_ERROR_RATE = 0.008        # 0.8% de error con extracción asistida + HITL
REVIEW_THRESHOLD = 0.80        # debajo de esta confianza, un campo necesita revisión humana

# ---------------------------------------------------------------------------
# Pools de valores realistas (Colombia)
# ---------------------------------------------------------------------------
_EMPRESAS = [
    "SOLUCIONES ANDINAS SAS", "COMERCIALIZADORA EL DORADO SAS",
    "INVERSIONES MONTERREY SAS", "TECNOLOGIA GLOBAL COLOMBIA SAS",
    "AGROPECUARIA LA SABANA SAS", "CONSTRUCCIONES VALLE VERDE SAS",
    "LOGISTICA EXPRESS BOGOTA SAS", "DISTRIBUIDORA CARIBE SAS",
    "MANUFACTURAS DEL NORTE SAS", "SERVICIOS INTEGRALES OMEGA SAS",
    "ALIMENTOS FRESCOS DE COLOMBIA SAS", "TEXTILES MEDELLIN SA",
    "GRUPO EMPRESARIAL ZENITH SAS", "FERRETERIA INDUSTRIAL EL TORNILLO SAS",
    "TRANSPORTES RAPIDOS DEL SUR SAS", "EDITORIAL LETRAS DORADAS SAS",
    "SOSTENIBILIDAD LEGAL SAS", "CONSULTORES FINANCIEROS APEX SAS",
]
_PERSONAS = [
    "Juan Carlos Pérez Gómez", "María Fernanda Rodríguez Díaz",
    "Andrés Felipe Martínez López", "Laura Sofía Ramírez Torres",
    "Carlos Eduardo Gómez Sánchez", "Ana María Castro Vargas",
    "Diego Alejandro Moreno Ruiz", "Valentina Herrera Jiménez",
    "Santiago Restrepo Ospina", "Camila Andrea Rojas Mejía",
    "Felipe Augusto Salazar Cano", "Daniela Quintero Patiño",
    "Sebastián Cárdenas Ríos", "Paula Andrea Vélez Henao",
]
_CIUDADES = [
    "BOGOTÁ D.C.", "MEDELLÍN", "CALI", "BARRANQUILLA", "CARTAGENA",
    "BUCARAMANGA", "PEREIRA", "MANIZALES", "CÚCUTA", "IBAGUÉ",
]
_ACTIVIDADES = [
    "Comercio al por mayor de equipos de cómputo",
    "Construcción de edificios residenciales",
    "Cultivo de productos agrícolas",
    "Transporte de carga por carretera",
    "Fabricación de productos textiles",
    "Actividades de consultoría de gestión",
    "Comercio al por menor de alimentos",
    "Elaboración de productos de panadería",
]
_ASEGURADORAS = ["SURA", "Seguros Bolívar", "Allianz", "MAPFRE", "Liberty Seguros"]
_MESES = ["ENE", "FEB", "MAR", "ABR", "MAY", "JUN", "JUL", "AGO", "SEP", "OCT", "NOV", "DIC"]
_MESES_LARGO = ["ENERO", "FEBRERO", "MARZO", "ABRIL", "MAYO", "JUNIO",
                "JULIO", "AGOSTO", "SEPTIEMBRE", "OCTUBRE", "NOVIEMBRE", "DICIEMBRE"]
_NOMBRES = ["MATEO ANDRÉS", "VALENTINA", "SANTIAGO JOSÉ", "ISABELLA", "SAMUEL DAVID",
            "MARIANA", "NICOLÁS", "SOFÍA ALEJANDRA", "MARTÍN", "GABRIELA"]
_APELLIDOS = ["POLANCO RODRÍGUEZ", "GÓMEZ SÁNCHEZ", "MARTÍNEZ LÓPEZ", "RAMÍREZ TORRES",
              "CASTRO VARGAS", "MORENO RUIZ", "HERRERA JIMÉNEZ", "RESTREPO OSPINA"]

# Volumen del piloto (30 días). ~50 docs/día -> números de ahorro creíbles e
# impactantes para el dashboard, y una curva de volumen rica.
PILOT_DOCS = 1500

# Distribución del corpus real: Cámara y Póliza dominan, luego RUT, pocas Cédulas.
_TYPE_WEIGHTS = [
    (DocType.CAMARA_COMERCIO, 0.37),
    (DocType.POLIZA, 0.31),
    (DocType.RUT, 0.20),
    (DocType.CEDULA, 0.12),
]
_TYPES = [t for t, _ in _TYPE_WEIGHTS]
_WEIGHTS = [w for _, w in _TYPE_WEIGHTS]


def _rng_conf(rng: random.Random, lo: float = 0.86, hi: float = 0.99) -> float:
    return round(rng.uniform(lo, hi), 4)


def _nit(rng: random.Random) -> str:
    base = rng.randint(800_000_000, 901_999_999)
    dv = rng.randint(0, 9)
    s = f"{base:,}".replace(",", ".")
    return f"{s}-{dv}"


# Rango de confianza base por tipología (refleja dificultad real del OCR/NER):
# la cédula impresa es la más limpia; el RUT digital DIAN (cajas por dígito) es
# el más ruidoso. Diferencia los datos para que "Confianza por tipo" cuente algo.
_CONF_RANGE = {
    DocType.CEDULA: (0.90, 0.99),
    DocType.CAMARA_COMERCIO: (0.87, 0.98),
    DocType.POLIZA: (0.84, 0.96),
    DocType.RUT: (0.80, 0.94),
}


def _entities_for(dt: DocType, rng: random.Random) -> list[Entity]:
    """Construye los campos del tipo `dt` con valores y confianza realistas.

    Mismos ui_labels que extrae el modelo v2 (ner_gliner2.SCHEMA_BY_DOCTYPE).
    """
    _lo, _hi = _CONF_RANGE[dt]

    def E(label, value, lo=None, hi=None):
        return Entity(label=label, value=value,
                      confidence=_rng_conf(rng, lo if lo is not None else _lo,
                                           hi if hi is not None else _hi))

    if dt == DocType.CAMARA_COMERCIO:
        return [
            E("razon_social", rng.choice(_EMPRESAS)),
            E("nit", _nit(rng)),
            E("numero_matricula", f"0{rng.randint(2_000_000, 2_999_999)}"),
            E("fecha_constitucion",
              f"{rng.randint(1, 28)} DE {rng.choice(_MESES_LARGO)} DE {rng.randint(2005, 2021)}"),
            E("representante_legal", rng.choice(_PERSONAS)),
        ]
    if dt == DocType.POLIZA:
        prima = rng.randint(8, 480) * 100_000
        return [
            E("numero_poliza", f"{rng.choice('ABCDP')}{rng.choice('ABCDP')}-{rng.randint(10_000, 99_999):05d}"),
            E("tomador", rng.choice(_EMPRESAS + _PERSONAS)),
            E("prima", "$ " + f"{prima:,}".replace(",", ".")),
            E("asegurado", rng.choice(_EMPRESAS)),
        ]
    if dt == DocType.RUT:
        return [
            E("nit", _nit(rng)),
            E("razon_social", rng.choice(_EMPRESAS)),
            E("direccion", f"Calle {rng.randint(1, 170)} # {rng.randint(1, 99)}-{rng.randint(1, 99)}, "
                           f"{rng.choice(_CIUDADES).title()}"),
            E("actividad_economica", rng.choice(_ACTIVIDADES)),
        ]
    # Cédula
    return [
        E("nombres", rng.choice(_NOMBRES)),
        E("apellidos", rng.choice(_APELLIDOS)),
        E("numero_cedula", f"{rng.randint(900_000_000, 1_099_999_999):,}".replace(",", ".")),
        E("lugar_expedicion", rng.choice(_CIUDADES)),
        E("fecha_expedicion", f"{rng.randint(1, 28)} {rng.choice(_MESES)} {rng.randint(2008, 2020)}"),
    ]


_LATENCY = {
    DocType.CAMARA_COMERCIO: (2800, 6200),
    DocType.RUT: (2400, 5200),
    DocType.POLIZA: (2200, 4800),
    DocType.CEDULA: (1500, 3000),
}
_EXT = {DocType.CAMARA_COMERCIO: "pdf", DocType.RUT: "pdf",
        DocType.POLIZA: "pdf", DocType.CEDULA: "jpg"}
_PREFIX = {DocType.CAMARA_COMERCIO: "CertCamaraComercio",
           DocType.RUT: "RUT_DIAN", DocType.POLIZA: "Poliza",
           DocType.CEDULA: "Cedula"}


def build_seed_history(now: datetime | None = None, seed: int = 7,
                       n: int = PILOT_DOCS) -> list[DocumentResult]:
    """Devuelve `n` DocumentResult ya procesados (piloto de 30 días), deterministas.

    Cada uno con `_processed_at` (datetime) y `_seed=True` como atributos
    dinámicos. ~1 de cada 7 trae algún campo bajo el umbral HITL.
    """
    rng = random.Random(seed)
    now = now or datetime.now()
    docs = rng.choices(_TYPES, weights=_WEIGHTS, k=n)

    results: list[DocumentResult] = []
    for i, dt in enumerate(docs):
        ents = _entities_for(dt, rng)

        # ~14% de los docs: bajar 1-2 campos a zona de revisión (0.55-0.79).
        needs_review = rng.random() < 0.14
        if needs_review:
            k = rng.randint(1, min(2, len(ents)))
            for idx in rng.sample(range(len(ents)), k):
                ents[idx] = Entity(label=ents[idx].label, value=ents[idx].value,
                                   confidence=round(rng.uniform(0.55, 0.79), 4))

        # Confianza de clasificación: alta salvo en algunos de los "review".
        doc_conf = round(rng.uniform(0.72, 0.84), 4) if needs_review and rng.random() < 0.5 \
            else round(rng.uniform(0.86, 0.99), 4)

        lo, hi = _LATENCY[dt]
        latency = rng.randint(lo, hi)

        # Fecha en los últimos 30 días, con leve sesgo a fechas recientes
        # (para que la curva de volumen muestre tendencia ascendente).
        day_offset = int(abs(rng.gauss(0, 11))) % 30
        ts = now - timedelta(days=day_offset,
                             hours=rng.randint(8, 18), minutes=rng.randint(0, 59))

        r = DocumentResult(
            filename=f"{_PREFIX[dt]}_{1000 + i}.{_EXT[dt]}",
            doc_type=dt,
            doc_type_confidence=doc_conf,
            extracted_text="",  # el seed no necesita el texto OCR completo
            entities=ents,
            processing_time_ms=latency,
        )
        setattr(r, "_processed_at", ts)
        setattr(r, "_seed", True)
        results.append(r)

    # Orden cronológico (más antiguo primero) para las series de tiempo.
    results.sort(key=lambda x: getattr(x, "_processed_at"))
    return results


# ---------------------------------------------------------------------------
# Lógica de métricas de negocio (consumida por el dashboard)
# ---------------------------------------------------------------------------

def field_confidences(result: DocumentResult) -> list[float]:
    return [e.confidence for e in result.entities]


def needs_review(result: DocumentResult, threshold: float = REVIEW_THRESHOLD) -> bool:
    """True si el documento debe pasar por un revisor humano (cola HITL)."""
    if result.error:
        return True
    if not result.entities:
        return True
    if result.doc_type_confidence < threshold:
        return True
    return any(e.confidence < threshold for e in result.entities)


def low_fields(result: DocumentResult, threshold: float = REVIEW_THRESHOLD) -> list[Entity]:
    """Campos del documento por debajo del umbral (los que el revisor mira)."""
    return [e for e in result.entities if e.confidence < threshold]


def compute_business_metrics(history: list[DocumentResult],
                             threshold: float = REVIEW_THRESHOLD) -> dict:
    """KPIs de negocio para la banda hero del dashboard."""
    ok = [r for r in history if not r.error]
    n_ok = len(ok)
    if not n_ok:
        return {
            "n_ok": 0, "ahorro_cop": 0, "horas_ahorradas": 0.0,
            "tasa_automatizacion": 0.0, "precision": 0.0,
            "n_review": 0, "n_auto": 0, "reduccion_error_pct": 0.0,
        }

    saved_min = 0.0
    n_review = 0
    all_confs: list[float] = []
    for r in ok:
        rev = needs_review(r, threshold)
        n_review += 1 if rev else 0
        auto_min = r.processing_time_ms / 60_000.0 + (REVIEW_MIN_PER_DOC if rev else 0.0)
        saved_min += max(MANUAL_MIN_PER_DOC - auto_min, 0.0)
        all_confs.extend(e.confidence for e in r.entities)

    horas = saved_min / 60.0
    precision = sum(all_confs) / len(all_confs) if all_confs else 0.0
    reduccion = (1.0 - AUTO_ERROR_RATE / MANUAL_ERROR_RATE) if MANUAL_ERROR_RATE else 0.0

    return {
        "n_ok": n_ok,
        "ahorro_cop": int(horas * COST_PER_HOUR_COP),
        "horas_ahorradas": horas,
        "tasa_automatizacion": (n_ok - n_review) / n_ok,
        "precision": precision,
        "n_review": n_review,
        "n_auto": n_ok - n_review,
        "reduccion_error_pct": reduccion,
    }


def confidence_by_type(history: list[DocumentResult]) -> dict[DocType, float]:
    """Confianza media de campo por tipología (para el gráfico de barras)."""
    out: dict[DocType, float] = {}
    for dt in (DocType.CAMARA_COMERCIO, DocType.RUT, DocType.CEDULA, DocType.POLIZA):
        confs = [e.confidence for r in history if not r.error and r.doc_type == dt
                 for e in r.entities]
        if confs:
            out[dt] = sum(confs) / len(confs)
    return out


def volume_by_day(history: list[DocumentResult]) -> list[tuple]:
    """[(date, count)] ordenado, sobre los docs con `_processed_at`."""
    from collections import Counter
    c: Counter = Counter()
    for r in history:
        ts = getattr(r, "_processed_at", None)
        if ts is not None:
            c[ts.date()] += 1
    return sorted(c.items())
