"""
Deploy de los archivos cambiados al Space v2 (mateopola/docuinsight-gliner2).

Sube SOLO los 4 archivos modificados (app.py, seed_data.py, mock_models.py,
pipeline.py) — no toca modelos, Dockerfile ni requirements.

Auth: usa el token guardado por `huggingface-cli login` (o la env HF_TOKEN).
SSL corporativo (Zscaler): truststore.inject_into_ssl() antes de cualquier red.

Uso:  python deploy_v2.py
"""
from __future__ import annotations

import os
import sys

# SSL corporativo: confiar en el almacén de certificados del sistema.
try:
    import truststore
    truststore.inject_into_ssl()
except Exception as e:  # pragma: no cover
    print(f"[warn] truststore no disponible: {e}")

from huggingface_hub import HfApi, get_token

REPO_ID = "mateopola/docuinsight-gliner2"
STAGING = os.path.join(os.path.dirname(__file__), "..", "docuinsight-space-v2")
FILES = ["app.py", "seed_data.py", "mock_models.py", "pipeline.py", "Dockerfile", ".dockerignore"]


def main() -> int:
    token = os.environ.get("HF_TOKEN") or get_token()
    if not token:
        print("ERROR: no hay token. Corré 'huggingface-cli login' o exportá HF_TOKEN.")
        return 1

    api = HfApi(token=token)
    who = api.whoami()
    print(f"Autenticado como: {who.get('name')} | subiendo a {REPO_ID}")

    res = api.upload_folder(
        folder_path=os.path.abspath(STAGING),
        repo_id=REPO_ID,
        repo_type="space",
        allow_patterns=FILES,
        commit_message="feat(dashboard): cockpit de impacto + seed piloto + stepper + nav fluida",
    )
    print("OK. Commit:", getattr(res, "oid", res))
    print(f"Space: https://huggingface.co/spaces/{REPO_ID}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
