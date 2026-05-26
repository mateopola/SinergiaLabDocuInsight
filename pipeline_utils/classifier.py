"""
Wrapper del clasificador C-1 TF-IDF + Regresion Logistica.

Entrenado en SinergiaLabProyecto Fase 3.0 (accuracy test 1.0 / macro-F1 1.0).
Mapea texto del documento a una de las 4 clases canonicas: Cedula, RUT,
Poliza, CamaraComercio.
"""
from __future__ import annotations

from pathlib import Path

import joblib

# Mapeo de la etiqueta interna del clasificador a la enum DocType de DocuInsight
# Las etiquetas internas son las que vieron los splits del training (Fase 3.0).
_CLASS_TO_DOCTYPE = {
    "Cedula":         "cedula",
    "CamaraComercio": "camara_comercio",
    "RUT":            "rut",
    "Poliza":         "poliza",
}


class DocumentClassifier:
    """Clasifica un documento en (doctype_str, confidence)."""

    def __init__(self, models_dir: Path):
        self.vectorizer = joblib.load(models_dir / "vectorizer.joblib")
        self.classifier = joblib.load(models_dir / "classifier.joblib")
        # Las clases del modelo (sin enum, son las strings que se entrenaron)
        self.classes_ = list(self.classifier.classes_)

    def predict(self, text: str) -> tuple[str, float]:
        """
        Devuelve (doctype, confidence).

        doctype: una de ('cedula', 'camara_comercio', 'rut', 'poliza').
        confidence: probabilidad maxima del clasificador (0..1).

        Si el texto está vacio o el clasificador no esta seguro,
        el caller decide si reportar 'desconocido'.
        """
        if not text or not text.strip():
            return "desconocido", 0.0
        X = self.vectorizer.transform([text])
        proba = self.classifier.predict_proba(X)[0]
        best_idx = int(proba.argmax())
        label = self.classes_[best_idx]
        confidence = float(proba[best_idx])
        doctype = _CLASS_TO_DOCTYPE.get(label, "desconocido")
        return doctype, confidence
