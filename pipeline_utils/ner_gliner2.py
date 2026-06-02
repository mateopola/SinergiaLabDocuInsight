"""
NER backend ALTERNATIVO: GLiNER2 unificado (modelo de las companeras).

Modelo: Yeraldyn/gliner2-large-sineria-v8 (fine-tune LoRA sobre
fastino/gliner2-large-v1, base microsoft/deberta-v3-large). A diferencia del
backend v1 (4 modelos GLiNER especializados), aca UN solo modelo maneja las 4
tipologias; se le pasa el esquema de etiquetas correspondiente segun la clase
detectada por el clasificador.

API gliner2:
    from gliner2 import GLiNER2
    m = GLiNER2.from_pretrained(repo)
    m.extract_entities(texto, [labels]) -> {'entities': {label: [valores]}}

NOTA: el esquema de etiquetas de abajo es APROXIMADO, reconstruido desde las
tablas de ejemplos del documento Ciclo 4 (no se dispone del notebook original
de Yeraldyn). Si se obtiene el esquema exacto, basta actualizar SCHEMA_BY_DOCTYPE.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

# Repo del modelo de las companeras en HF Hub.
GLINER2_HUB_REPO = os.environ.get("GLINER2_HUB_REPO", "Yeraldyn/gliner2-large-sineria-v8")


@dataclass(frozen=True)
class ExtractedEntity:
    ui_label: str
    value: str
    confidence: float  # gliner2 no devuelve score por entidad -> 1.0


# Esquema por tipologia: {label_descriptivo_para_gliner2: ui_label_de_la_app}
# El label descriptivo es el prompt EXACTO que recibe el modelo (schema-driven).
# Estos son los labels OFICIALES con los que Yeraldyn entreno el modelo
# (confirmados por ella) -> rinde igual que en el documento Ciclo 4.
SCHEMA_BY_DOCTYPE: dict[str, dict[str, str]] = {
    "cedula": {
        "primer y segundo nombre propio del titular sin apellidos":               "nombres",
        "primer y segundo apellido del titular de la cedula sin nombres propios": "apellidos",
        "numero de cedula de ciudadania compuesto solo por digitos":              "numero_cedula",
        "municipio colombiano donde fue expedida la cedula de ciudadania":        "lugar_expedicion",
        "mes abreviado y ano de cuatro digitos en que fue expedida la cedula":    "fecha_expedicion",
    },
    "camara_comercio": {
        "razon social de la empresa":                                             "razon_social",
        "numero NIT de nueve digitos de la empresa sin digito verificador DV":    "nit",
        "numero de matricula mercantil asignado por camara de comercio":          "numero_matricula",
        "fecha de constitucion de la empresa ante notaria o escritura publica":   "fecha_constitucion",
        "nombre completo de la persona nombrada como representante legal":         "representante_legal",
    },
    "rut": {
        "numero NIT de nueve digitos de la empresa sin digito verificador DV":    "nit",
        "razon social de la empresa":                                             "razon_social",
        "calle carrera o avenida con numero y ciudad de la sede principal de la empresa": "direccion",
        "descripcion de la actividad economica principal de la empresa":          "actividad_economica",
    },
    "poliza": {
        "empresa o entidad asegurada en la poliza de seguro":                     "asegurado",
        "nombre o razon social del tomador del seguro":                           "tomador",
        "cifra en pesos colombianos de la prima neta pagada por la poliza de seguro": "prima",
        "numero de poliza de seguro emitido por la aseguradora":                  "numero_poliza",
    },
}


class GLiNER2Extractor:
    """Wrapper del modelo GLiNER2 unificado. Carga lazy."""

    def __init__(self, repo: str = GLINER2_HUB_REPO):
        self.repo = repo
        self.model = None

    def _ensure_loaded(self):
        if self.model is None:
            # gliner2[local] trae torch/transformers. Import diferido para no
            # pagar el costo si nunca se usa.
            from gliner2 import GLiNER2
            self.model = GLiNER2.from_pretrained(self.repo)
        return self.model

    def extract(self, text: str, doctype: str) -> list[ExtractedEntity]:
        schema = SCHEMA_BY_DOCTYPE.get(doctype)
        if not schema or not text or not text.strip():
            return []
        model = self._ensure_loaded()
        labels = list(schema.keys())
        # include_confidence=True -> el modelo devuelve el score real por entidad,
        # no un 1.0 fijo. Formato: {'entities': {label: [{'text':..,'confidence':..}]}}
        try:
            raw = model.extract_entities(text, labels, include_confidence=True)
            con_score = True
        except TypeError:
            # version de gliner2 sin el parametro -> fallback sin score
            raw = model.extract_entities(text, labels)
            con_score = False
        ents = (raw or {}).get("entities", {})
        out: list[ExtractedEntity] = []
        seen: set[tuple[str, str]] = set()
        for desc_label, ui_label in schema.items():
            for item in ents.get(desc_label, []) or []:
                # Con include_confidence: item = {'text':.., 'confidence':..}.
                # Sin el: item = str. Soportamos ambos por robustez.
                if isinstance(item, dict):
                    value = (item.get("text") or "").strip()
                    conf = float(item.get("confidence", 1.0))
                else:
                    value = (item or "").strip()
                    conf = 1.0
                if not value:
                    continue
                key = (ui_label, value)
                if key in seen:
                    continue
                seen.add(key)
                out.append(ExtractedEntity(ui_label=ui_label, value=value, confidence=conf))
        return out


class NERDispatcher:
    """Interfaz identica a la del backend v1, pero un solo modelo unificado.

    Se mantiene el nombre NERDispatcher para que real_models.py funcione sin
    cambios (solo cambia el import).
    """

    def __init__(self, models_dir=None, **kwargs):
        # Cargar torch ANTES que paddle (mismo motivo que en el backend v1:
        # en Windows el segundo en cargar pierde la DLL). gliner2[local] usa torch.
        import torch  # noqa: F401
        self.extractor = GLiNER2Extractor()

    def extract(self, text: str, doctype: str) -> list[ExtractedEntity]:
        return self.extractor.extract(text, doctype)
