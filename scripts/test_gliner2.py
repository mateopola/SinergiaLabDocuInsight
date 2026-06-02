"""Prueba rapida del backend GLiNER2 (modelo de las companeras).
Requiere: pip install "gliner2[local]"

Uso: python scripts/test_gliner2.py
"""
import os, sys
os.environ.setdefault("PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION", "python")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline_utils.ner_gliner2 import GLiNER2Extractor, SCHEMA_BY_DOCTYPE

# Textos de muestra (OCR-like) por tipologia
SAMPLES = {
    "cedula": "REPUBLICA DE COLOMBIA CEDULA DE CIUDADANIA NUMERO 1.020.818.311 "
              "POLANCO RODRIGUEZ APELLIDOS MATEO NOMBRES FECHA Y LUGAR DE EXPEDICION "
              "29-AGO-2014 BOGOTA D.C",
    "camara_comercio": "CAMARA DE COMERCIO Razon social: COMERCIALIZADORA ANDINA SAS "
              "NIT 900.123.456-7 Matricula No. 02529040 Representante legal Juan Perez Gomez",
}

ext = GLiNER2Extractor()
print(f"Modelo: {ext.repo}")
for tip, text in SAMPLES.items():
    print(f"\n=== {tip} ===")
    print(f"labels: {list(SCHEMA_BY_DOCTYPE[tip].keys())}")
    ents = ext.extract(text, tip)
    if not ents:
        print("  (no extrajo nada)")
    for e in ents:
        print(f"  {e.ui_label:20s} = {e.value!r}")
