# DocuInsight

**Synergia Lab** · MVP de clasificación documental + extracción de entidades.

Interfaz Streamlit para procesamiento por lote de cuatro tipos documentales:
**Cédula de Ciudadanía**, **Cámara de Comercio**, **RUT** y **Pólizas**.

---

## Arquitectura

La aplicación está separada en dos capas independientes para que la UI pueda desarrollarse sin esperar a los modelos:

```
┌─────────────────────────────────────────────────────┐
│  Interfaz (Streamlit)                               │
│   - Carga por lote, progreso, resultados, Excel     │
└──────────────────┬──────────────────────────────────┘
                   │  contrato: DocumentPipeline
                   ▼
┌─────────────────────────────────────────────────────┐
│  Pipeline                                           │
│   - MockPipeline (mock_models.py)  ◄── modo dev     │
│   - RealPipeline (real_models.py)  ◄── modelos reales│
└─────────────────────────────────────────────────────┘
```

El toggle **"Usar modelos mock"** en la sidebar alterna entre las dos implementaciones sin cambiar código.

---

## Estructura de archivos

| Archivo | Responsabilidad |
| --- | --- |
| `app.py` | Aplicación Streamlit principal |
| `schemas.py` | **Contrato de datos** (compartir con el equipo) |
| `pipeline.py` | Protocolo y factory del pipeline |
| `mock_models.py` | Pipeline simulado para desarrollo de UI |
| `real_models.py` | Placeholder para integración con modelos reales |
| `export.py` | Generación de Excel multi-hoja |
| `requirements.txt` | Dependencias |

---

## Cómo correr

```bash
# 1. Crear entorno virtual (recomendado)
python -m venv .venv
source .venv/bin/activate    # en Windows: .venv\Scripts\activate

# 2. Instalar dependencias
pip install -r requirements.txt

# 3. Levantar la app
streamlit run app.py
```

Abre automáticamente en `http://localhost:8501`.

---

## Contrato para el equipo de modelos

Cualquier implementación del pipeline real debe cumplir el `Protocol` definido en `pipeline.py`:

```python
class DocumentPipeline(Protocol):
    def process(self, file_bytes: bytes, filename: str) -> DocumentResult: ...
```

Donde `DocumentResult` (ver `schemas.py`) contiene:

- `filename: str`
- `doc_type: DocType` — uno de `cedula | camara_comercio | rut | poliza | desconocido`
- `doc_type_confidence: float` — 0 a 1
- `extracted_text: str` — texto OCR / texto del PDF
- `entities: list[Entity]` — lista de entidades extraídas
- `processing_time_ms: int`
- `error: Optional[str]` — None si todo ok

### Entidades esperadas por tipo

Ver `EXPECTED_ENTITIES` en `schemas.py`. Resumen:

- **Cédula:** nombres, apellidos, número, fechas y lugares de nacimiento/expedición, sexo.
- **Cámara de Comercio:** razón social, NIT, matrícula, representante legal, domicilio, objeto social, capital, vigencia.
- **RUT:** NIT, razón social, dirección, ciudad, CIIU, responsabilidades, fecha de generación.
- **Póliza:** aseguradora, tomador, asegurado, beneficiario, número, ramo, vigencias, valor asegurado, prima, amparos.

### Integración

1. El equipo de modelos implementa `RealPipeline` en `real_models.py`.
2. En la sidebar, desactivar **"Usar modelos mock"**.
3. Listo — la UI no necesita cambios.

---

## Roadmap MVP (2 semanas)

**Semana 1** — UI + mock + export Excel (esta entrega).
**Semana 2** — Integración con pipeline real, ajustes visuales, validaciones.

---

## Stack candidato (en evaluación por el equipo de modelos)

- **OCR:** PaddleOCR | EasyOCR
- **Clasificación:** Regresión logística | BETO | LightGBM
- **NER:** GLiNER 2 | spaCy | otro
