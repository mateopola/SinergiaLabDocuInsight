# DocuInsight - App Streamlit con modelos GLiNER + PaddleOCR
#
# Imagen self-contained: bakea los modelos en la imagen para evitar dependencia
# de storage externo. Tamano final ~5.5 GB (4.4 GB GLiNER + ~1 GB deps).
#
# Build local (requiere los modelos en models/ner/gliner/ y los Paddle models
# en ~/.paddleocr/whl/ — ver deploy/README.md):
#     docker build -t docuinsight:latest .
#
# Run local:
#     docker run -p 8501:8501 docuinsight:latest

FROM python:3.12-slim

# Dependencias del sistema requeridas por:
#   - PyMuPDF (libxml2, libxslt) — para parsear PDFs
#   - PaddleOCR / OpenCV (libgl1, libglib2.0) — para render de imagenes
#   - libgomp1 — OpenMP que usan torch y paddle
RUN apt-get update && apt-get install -y --no-install-recommends \
    libxml2 \
    libxslt1.1 \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    curl \
    ca-certificates \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Instalar dependencias Python primero (capa cacheable)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copiar el codigo de la app
COPY app.py pipeline.py real_models.py schemas.py export.py ./
COPY pipeline_utils/ ./pipeline_utils/
COPY assets/ ./assets/
COPY .streamlit/ ./.streamlit/

# Copiar modelos: classifier (~13 MB) y GLiNER 4 tipologias (~4.4 GB total).
# El .dockerignore preserva models/ pero excluye otros directorios pesados.
COPY models/ ./models/

# Pre-cachear modelos PaddleOCR para no depender de descarga en runtime.
# Si la carpeta local ~/.paddleocr/whl/ existe se copia, sino se intenta bajar
# durante el build (con curl -k para skip SSL).
COPY paddle_cache/ /root/.paddleocr/

# Threading: forzar single-thread para que torch (GLiNER) y paddle no peleen
ENV OMP_NUM_THREADS=1 \
    MKL_NUM_THREADS=1 \
    OPENBLAS_NUM_THREADS=1 \
    TOKENIZERS_PARALLELISM=false \
    PYTHONUNBUFFERED=1

EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=10s --start-period=180s --retries=3 \
    CMD curl -fsS http://localhost:8501/_stcore/health || exit 1

# Streamlit en modo headless escuchando en 0.0.0.0 (no localhost) para que
# Azure App Service / Container Apps lo expongan correctamente.
CMD ["streamlit", "run", "app.py", \
     "--server.port=8501", \
     "--server.address=0.0.0.0", \
     "--server.headless=true", \
     "--server.fileWatcherType=none", \
     "--browser.gatherUsageStats=false"]
