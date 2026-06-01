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

import gc
import os
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from .label_mapping import GLINER_LABELS_BY_DOCTYPE, to_ui_label

# En PCs con poca RAM (<= 8 GB) cargar los 4 modelos GLiNER (~4.4 GB) causa
# swapping y freezes. Con SINGLE_MODEL_RAM=1 (default) el dispatcher mantiene
# UN solo modelo cargado a la vez: al cambiar de tipologia descarga el anterior.
# Techo de RAM ~1.1 GB constante, a cambio de recargar (~30-60s) al alternar
# tipologias. Para servidores con RAM holgada, exportar SINGLE_MODEL_RAM=0.
SINGLE_MODEL_RAM = os.environ.get("SINGLE_MODEL_RAM", "1") == "1"


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

    Carga LAZY: el modelo (~1.1 GB) se carga del disco la PRIMERA vez que se
    llama a extract(), no en __init__. Asi el dispatcher puede instanciar los 4
    extractores sin gastar ~4.4 GB de RAM ni ~4 min de arranque -- solo se
    cargan los modelos de las tipologias que realmente se procesan.

    Thread-unsafe, pero el pipeline de DocuInsight es single-threaded por request.
    """

    def __init__(self, model_dir: Path, doctype: str, threshold: float):
        # Validacion barata (fail-fast) sin cargar pesos.
        if not model_dir.exists():
            raise FileNotFoundError(
                f"No se encontro el modelo GLiNER en {model_dir}. "
                "Bajalo desde Google Drive (ver deploy/README o el plan de "
                "integracion)."
            )
        self.model_dir = model_dir
        self.doctype = doctype
        self.threshold = threshold
        self.labels = GLINER_LABELS_BY_DOCTYPE[doctype]
        self.model = None  # se carga lazy en _ensure_loaded()

    def _ensure_loaded(self):
        """Carga el modelo en la primera invocacion (idempotente)."""
        if self.model is None:
            from gliner import GLiNER
            self.model = GLiNER.from_pretrained(
                str(self.model_dir), local_files_only=True
            )
        return self.model

    def unload(self):
        """Libera el modelo de RAM. Se vuelve a cargar en el proximo extract()."""
        if self.model is not None:
            self.model = None
            gc.collect()

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

        model = self._ensure_loaded()
        raw = model.predict_entities(text, self.labels, threshold=self.threshold)

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
    Instancia los 4 extractores GLiNER (uno por tipologia) y enruta segun
    doctype. Los modelos NO se cargan aca: cada GLiNERExtractor es lazy y
    carga su modelo (~1.1 GB) la primera vez que recibe un documento de su
    tipologia. En la practica un usuario que sube solo cedulas nunca paga el
    costo de cargar los modelos de RUT/CC/POL.

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
        single_model_ram: bool | None = None,
    ):
        # IMPORTANTE (Windows): cargar las DLLs de torch ANTES de que cualquier
        # OCR cargue paddle. Si paddle se importa primero, el import de torch
        # falla con "shm.dll WinError 127". El pipeline construye el
        # NERDispatcher antes del primer process()/OCR, asi que importar torch
        # aca fija el orden correcto. NO carga los modelos GLiNER (eso sigue
        # siendo lazy) -- solo trae las librerias nativas.
        import torch  # noqa: F401

        thresholds = thresholds or DEFAULT_THRESHOLDS
        # Si no se pasa explicito, usar la config global (env SINGLE_MODEL_RAM).
        self.single_model_ram = (
            SINGLE_MODEL_RAM if single_model_ram is None else single_model_ram
        )
        self._last_doctype: str | None = None
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
        # Modo low-RAM: al cambiar de tipologia, descargar el modelo previo
        # para que nunca haya mas de uno residente en memoria.
        if (self.single_model_ram and self._last_doctype is not None
                and self._last_doctype != doctype):
            prev = self.extractors.get(self._last_doctype)
            if prev is not None:
                prev.unload()
        self._last_doctype = doctype
        return extractor.extract(text, doctype)
