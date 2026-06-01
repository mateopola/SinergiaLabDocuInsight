# Launcher local de DocuInsight (Windows / PowerShell).
#
# Por que este script y no `streamlit run app.py` directo:
#   Streamlit importa protobuf ANTES de ejecutar app.py, asi que setear la
#   variable dentro de app.py llega tarde. paddlepaddle 2.6 en Windows tiene
#   _pb2 que rompen con protobuf >= 4 ("Descriptors cannot be created
#   directly"). Forzar la implementacion pura-Python de protobuf EN EL ENTORNO
#   (antes de arrancar Python) evita el conflicto.
#
# Uso:
#   .\run.ps1
#
# Si PowerShell bloquea el script:
#   powershell -ExecutionPolicy Bypass -File .\run.ps1

$env:PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION = "python"

# Estabilidad torch + paddle en CPU: forzar single-thread.
$env:OMP_NUM_THREADS = "1"
$env:MKL_NUM_THREADS = "1"
$env:OPENBLAS_NUM_THREADS = "1"
$env:TOKENIZERS_PARALLELISM = "false"

# Modo low-RAM: mantener 1 solo modelo GLiNER en memoria (PCs <= 8 GB).
# Exportar "0" si corres en un servidor con RAM holgada.
if (-not $env:SINGLE_MODEL_RAM) { $env:SINGLE_MODEL_RAM = "1" }

Write-Host "Iniciando DocuInsight..." -ForegroundColor Cyan
Write-Host "  protobuf  : pure-python (compat PaddleOCR)" -ForegroundColor DarkGray
Write-Host "  low-RAM   : SINGLE_MODEL_RAM=$($env:SINGLE_MODEL_RAM)" -ForegroundColor DarkGray
Write-Host "  URL       : http://localhost:8501" -ForegroundColor Green

streamlit run app.py --server.port=8501 --browser.gatherUsageStats=false
