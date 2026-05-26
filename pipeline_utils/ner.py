"""
NER por tipologia, usando GLiNER fine-tuned (4 modelos, uno por tipologia).

Modelos entrenados en SinergiaLabProyecto/notebooks/24_ner_gliner_finetune_colab.ipynb
(fine-tune de urchade/gliner_multi-v2.1 sobre 497 documentos validados manualmente).
Macro-F1 entity-level exact-match sobre OCR Paddle:

    CC  ->  GLiNER FT  macro-F1 0.670  (vs spaCy+Paddle 0.515)
    CED ->  GLiNER FT  macro-F1 0.871  (vs spaCy+Paddle 0.323)
    POL ->  GLiNER FT  macro-F1 0.303  (vs spaCy+Paddle 0.065)
    RUT ->  GLiNER FT  macro-F1 0.378  (vs spaCy+Paddle 0.119)

Ver reports/nb24_gliner_finetune_resumen.md del repo SinergiaLabProyecto.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from .label_mapping import GLINER_LABELS_BY_DOCTYPE, to_ui_label


@dataclass(frozen=True)
class ExtractedEntity:
    ui_label: str      # label que entiende la UI (p.ej. 'nit')
    value: str         # texto extraido del documento
    confidence: float  # 0..1 (score del span devuelto por GLiNER)


# Threshold optimo por tipologia. Calibrado segun el analisis precision/recall
# del nb24: CC y CED tienen buen balance en 0.5, POL y RUT sobre-predicen
# fuerte y se benefician de un threshold mas alto.
DEFAULT_THRESHOLDS: dict[str, float] = {
    "camara_comercio": 0.50,
    "cedula":          0.50,
    "poliza":          0.70,
    "rut":             0.70,
}


class GLiNERExtractor:
    """Extractor NER usando GLiNER fine-tuned (uno por tipologia).

    Lazy-loads el modelo en disco; thread-unsafe pero el pipeline de
    DocuInsight es single-threaded por request.
    """

    def __init__(self, model_dir: Path, doctype: str, threshold: float):
        from gliner import GLiNER
        if not model_dir.exists():
            raise FileNotFoundError(
                f"No se encontro el modelo GLiNER en {model_dir}. "
                "Bajalo desde Google Drive (ver README en streamlit_app o "
                "el plan de integracion)."
            )
        self.model = GLiNER.from_pretrained(str(model_dir), local_files_only=True)
        self.doctype = doctype
        self.threshold = threshold
        self.labels = GLINER_LABELS_BY_DOCTYPE[doctype]

    def extract(self, text: str, doctype: str) -> list[ExtractedEntity]:
        # Nota: `doctype` se pasa por consistencia con la firma anterior
        # (CRFExtractor / SpacyExtractor), pero deberia coincidir con
        # self.doctype porque cada extractor esta dedicado a una tipologia.
        if doctype != self.doctype:
            # Defense in depth: si el dispatcher se confunde, no rompemos
            # silenciosamente -- avisamos.
            raise ValueError(
                f"GLiNERExtractor para '{self.doctype}' recibio doctype='{doctype}'"
            )
        if not text or not text.strip():
            return []

        raw = self.model.predict_entities(text, self.labels, threshold=self.threshold)

        # Mapear a ExtractedEntity. Si el mismo (label, value) aparece varias
        # veces, nos quedamos con el de mayor score (es informativo para la UI;
        # los duplicados solo agregan ruido visual).
        best_by_key: dict[tuple[str, str], ExtractedEntity] = {}
        for p in raw:
            ui_lab = to_ui_label(self.doctype, p["label"])
            if ui_lab is None:
                continue
            value = p["text"]
            key = (ui_lab, value)
            conf = float(p["score"])
            prev = best_by_key.get(key)
            if prev is None or conf > prev.confidence:
                best_by_key[key] = ExtractedEntity(
                    ui_label=ui_lab,
                    value=value,
                    confidence=conf,
                )
        return list(best_by_key.values())


class NERDispatcher:
    """
    Carga los 4 extractores GLiNER (uno por tipologia) y enruta segun doctype.

    Layout esperado en disco:
        models/ner/gliner/cc/
        models/ner/gliner/ced/
        models/ner/gliner/pol/
        models/ner/gliner/rut/
    """

    def __init__(
        self,
        models_dir: Path,
        thresholds: dict[str, float] | None = None,
    ):
        thresholds = thresholds or DEFAULT_THRESHOLDS
        gliner_dir = models_dir / "ner" / "gliner"
        self.extractors: dict[str, GLiNERExtractor] = {
            "camara_comercio": GLiNERExtractor(
                gliner_dir / "cc",  "camara_comercio", thresholds["camara_comercio"]
            ),
            "cedula":          GLiNERExtractor(
                gliner_dir / "ced", "cedula", thresholds["cedula"]
            ),
            "poliza":          GLiNERExtractor(
                gliner_dir / "pol", "poliza", thresholds["poliza"]
            ),
            "rut":             GLiNERExtractor(
                gliner_dir / "rut", "rut", thresholds["rut"]
            ),
        }

    def extract(self, text: str, doctype: str) -> list[ExtractedEntity]:
        extractor = self.extractors.get(doctype)
        if extractor is None:
            return []
        return extractor.extract(text, doctype)
