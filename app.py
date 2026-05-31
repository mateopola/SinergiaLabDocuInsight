"""
DocuInsight - Plataforma de inteligencia documental (Streamlit).

Continuacion visual de la landing publicada en docs/ (GitHub Pages).
Estructura de app con tabs: Dashboard / Procesar / Casos.
Procesa un documento a la vez y acumula historial en la sesion.

Para modo dev (datos mock): abrir http://localhost:8501/?dev=1
    o exportar DOCUINSIGHT_MOCK=1 antes de levantar.
"""

from __future__ import annotations

import base64
import json
import os
import textwrap
from datetime import datetime
from pathlib import Path

# Estabilizar threading en CPU Windows: torch (GLiNER) + paddle pelean por
# threads y el segundo en cargar puede dar inestabilidad. Forzar single
# thread antes de cualquier import pesado.
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

# protobuf 7.x (traido por otras libs) rompe los _pb2 de PaddlePaddle 2.6
# ("Descriptors cannot be created directly"). Forzar la implementacion pura
# Python de protobuf evita el conflicto. DEBE setearse antes de importar
# cualquier cosa que cargue protobuf (transformers/gliner/paddle).
os.environ.setdefault("PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION", "python")

# SSL: configuramos el bundle de `certifi` para descargas legitimas (HuggingFace
# y otros). Pero PaddleOCR descarga sus modelos de `paddleocr.bj.bcebos.com`
# (Baidu Cloud) que usa CAs que certifi no incluye. Como fallback para dev local
# (server corriendo en localhost), deshabilitamos la verificacion SSL global.
#
# IMPORTANTE: para deploy en produccion, descargar manualmente los modelos de
# PaddleOCR a ~/.paddleocr/whl/{det,rec,cls}/ y quitar este monkey-patch.
try:
    import certifi as _certifi
    os.environ.setdefault("SSL_CERT_FILE", _certifi.where())
    os.environ.setdefault("REQUESTS_CA_BUNDLE", _certifi.where())
    os.environ.setdefault("CURL_CA_BUNDLE", _certifi.where())
except ImportError:
    pass

import ssl as _ssl
_ssl._create_default_https_context = _ssl._create_unverified_context

# Silenciar warnings de urllib3 sobre unverified HTTPS (espera, los queremos
# acallar solo para la descarga inicial de Paddle; el resto del trafico SSL
# del proceso tambien queda sin verificar pero es server local).
import urllib3 as _urllib3
_urllib3.disable_warnings(_urllib3.exceptions.InsecureRequestWarning)


def _h(html: str) -> str:
    """
    Sanitiza HTML multilinea para st.markdown(unsafe_allow_html=True).

    Streamlit usa CommonMark, que interpreta lineas con 4+ espacios al
    inicio como bloque de codigo y muestra el HTML como texto literal.
    Esta funcion quita indentacion comun y trim para evitar el bug.
    """
    return textwrap.dedent(html).strip()

import pandas as pd
import plotly.express as px
import streamlit as st
from PIL import Image

from export import build_excel
from pipeline import get_pipeline
from schemas import (
    DOC_TYPE_LABELS,
    EXPECTED_ENTITIES,
    DocType,
    DocumentResult,
    humanize_entity_label,
)

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

LOGO_PATH = Path(__file__).parent / "assets" / "logo.png"
CLASSIFIER_METRICS = Path(__file__).parent / "models" / "classifier" / "metrics.json"

LANDING_URL = "https://mateopola.github.io/SinergiaLabDocuInsight/"

# Paleta de marca (sincronizada con docs/index.html)
PRIMARY = "#0C74C8"
PRIMARY_DARK = "#0858A0"
PRIMARY_LIGHT = "#E0F0FB"
ACCENT = "#FE6B23"
ACCENT_LIGHT = "#FFE4D6"
CREAM = "#FFF4F4"
DARK = "#41444B"
INK = "#0F172A"
SUCCESS = "#10B981"
WARN = "#F59E0B"
DANGER = "#DC2626"


@st.cache_data
def _logo_b64() -> str:
    return base64.b64encode(LOGO_PATH.read_bytes()).decode("ascii")


@st.cache_data
def _platform_metrics() -> dict:
    """Metricas verdaderas del modelo (no inventadas) para el strip de capacidades."""
    try:
        data = json.loads(CLASSIFIER_METRICS.read_text())
        return {
            "accuracy": data.get("test_accuracy", 0),
            "n_train": data.get("n_train", 0),
        }
    except Exception:
        return {"accuracy": 0, "n_train": 0}


@st.cache_resource(show_spinner="Cargando modelos por primera vez (puede tardar 30-60s)…")
def _cached_pipeline(use_mock_flag: bool):
    """Pipeline cacheado para que los modelos solo se carguen una vez por sesion."""
    return get_pipeline(use_mock=use_mock_flag)


def _render_doc_preview(file_bytes: bytes, filename: str) -> None:
    """Renderiza la primera pagina del PDF o la imagen completa."""
    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    try:
        if ext in ("png", "jpg", "jpeg"):
            st.image(file_bytes, use_container_width=True)
        elif ext == "pdf":
            import fitz  # PyMuPDF
            doc = fitz.open(stream=file_bytes, filetype="pdf")
            if len(doc) > 0:
                page = doc[0]
                pix = page.get_pixmap(dpi=110)
                st.image(pix.tobytes("png"), use_container_width=True)
                if len(doc) > 1:
                    st.caption(f"Pagina 1 de {len(doc)}")
            doc.close()
        else:
            st.info("Formato sin preview disponible.")
    except Exception as e:
        st.warning(f"No se pudo renderizar el preview: {type(e).__name__}: {e}")


# ---------------------------------------------------------------------------
# Sistema de iconos (Lucide-style, SVG inline)
# ---------------------------------------------------------------------------

ICON_PATHS: dict[str, str] = {
    # Navigation / actions
    "arrow-right": '<path d="M5 12h14"/><path d="m12 5 7 7-7 7"/>',
    "arrow-down": '<path d="M12 5v14"/><path d="m19 12-7 7-7-7"/>',
    "arrow-up-right": '<path d="M7 7h10v10"/><path d="M7 17 17 7"/>',
    "rotate-cw": '<path d="M21 12a9 9 0 1 1-9-9c2.52 0 4.93 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/>',
    "trash": '<path d="M3 6h18"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6"/><path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>',
    "external-link": '<path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" x2="21" y1="14" y2="3"/>',
    "chevron-left": '<path d="m15 18-6-6 6-6"/>',
    # Charts / dashboard
    "bar-chart": '<line x1="12" x2="12" y1="20" y2="10"/><line x1="18" x2="18" y1="20" y2="4"/><line x1="6" x2="6" y1="20" y2="16"/>',
    "activity": '<polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>',
    "trending-up": '<polyline points="22 7 13.5 15.5 8.5 10.5 2 17"/><polyline points="16 7 22 7 22 13"/>',
    "gauge": '<path d="m12 14 4-4"/><path d="M3.34 19a10 10 0 1 1 17.32 0"/>',
    "pie-chart": '<path d="M21.21 15.89A10 10 0 1 1 8 2.83"/><path d="M22 12A10 10 0 0 0 12 2v10z"/>',
    "layers": '<path d="m12.83 2.18 8.07 4.04a2 2 0 0 1 0 3.58l-8.07 4.04a2 2 0 0 1-1.66 0L3.1 9.8a2 2 0 0 1 0-3.58L11.17 2.18a2 2 0 0 1 1.66 0Z"/><path d="m6.08 9.5-3.04 1.52a2 2 0 0 0 0 3.58l8.07 4.04a2 2 0 0 0 1.66 0l8.07-4.04a2 2 0 0 0 0-3.58L17.8 9.5"/>',
    # Process / power
    "zap": '<polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>',
    "cpu": '<rect x="4" y="4" width="16" height="16" rx="2"/><rect x="9" y="9" width="6" height="6"/><path d="M15 2v2"/><path d="M15 20v2"/><path d="M2 15h2"/><path d="M2 9h2"/><path d="M20 15h2"/><path d="M20 9h2"/><path d="M9 2v2"/><path d="M9 20v2"/>',
    "scan": '<path d="M3 7V5a2 2 0 0 1 2-2h2"/><path d="M17 3h2a2 2 0 0 1 2 2v2"/><path d="M21 17v2a2 2 0 0 1-2 2h-2"/><path d="M7 21H5a2 2 0 0 1-2-2v-2"/><line x1="7" x2="17" y1="12" y2="12"/>',
    "sparkles": '<path d="m12 3-1.912 5.813a2 2 0 0 1-1.265 1.265L3 12l5.823 1.922a2 2 0 0 1 1.265 1.265L12 21l1.912-5.813a2 2 0 0 1 1.265-1.265L21 12l-5.823-1.922a2 2 0 0 1-1.265-1.265L12 3Z"/>',
    "upload": '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" x2="12" y1="3" y2="15"/>',
    "download": '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" x2="12" y1="15" y2="3"/>',
    # Files / data
    "file": '<path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z"/><polyline points="14 2 14 8 20 8"/>',
    "file-text": '<path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><line x1="10" y1="9" x2="8" y2="9"/>',
    "folder": '<path d="M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.93a2 2 0 0 1-1.66-.9l-.82-1.23A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z"/>',
    "database": '<ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M3 5v14a9 3 0 0 0 18 0V5"/><path d="M3 12a9 3 0 0 0 18 0"/>',
    "inbox": '<polyline points="22 12 16 12 14 15 10 15 8 12 2 12"/><path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z"/>',
    # Document types
    "credit-card": '<rect width="20" height="14" x="2" y="5" rx="2"/><line x1="2" x2="22" y1="10" y2="10"/>',
    "building": '<rect width="16" height="20" x="4" y="2" rx="2" ry="2"/><path d="M9 22v-4h6v4"/><path d="M8 6h.01"/><path d="M16 6h.01"/><path d="M12 6h.01"/><path d="M12 10h.01"/><path d="M12 14h.01"/><path d="M16 10h.01"/><path d="M16 14h.01"/><path d="M8 10h.01"/><path d="M8 14h.01"/>',
    "receipt": '<path d="M4 2v20l2-1 2 1 2-1 2 1 2-1 2 1 2-1 2 1V2l-2 1-2-1-2 1-2-1-2 1-2-1-2 1Z"/><path d="M16 8h-6a2 2 0 1 0 0 4h4a2 2 0 1 1 0 4H8"/><path d="M12 17.5v-11"/>',
    "shield-check": '<path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"/><path d="m9 12 2 2 4-4"/>',
    "help-circle": '<circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/><path d="M12 17h.01"/>',
    # Status
    "check-circle": '<path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/>',
    "check": '<polyline points="20 6 9 17 4 12"/>',
    "x-circle": '<circle cx="12" cy="12" r="10"/><line x1="15" x2="9" y1="9" y2="15"/><line x1="9" x2="15" y1="9" y2="15"/>',
    "alert-circle": '<circle cx="12" cy="12" r="10"/><line x1="12" x2="12" y1="8" y2="12"/><line x1="12" x2="12.01" y1="16" y2="16"/>',
    "info": '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/>',
    "clock": '<circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>',
    "tag": '<path d="M12.586 2.586A2 2 0 0 0 11.172 2H4a2 2 0 0 0-2 2v7.172a2 2 0 0 0 .586 1.414l8.704 8.704a2.426 2.426 0 0 0 3.42 0l6.58-6.58a2.426 2.426 0 0 0 0-3.42z"/><circle cx="7.5" cy="7.5" r="1.5"/>',
    "target": '<circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="2"/>',
    "search": '<circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>',
    "circle-dot": '<circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="2" fill="currentColor"/>',
    "shield-alert": '<path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"/><path d="M12 8v4"/><path d="M12 16h.01"/>',
    "globe": '<circle cx="12" cy="12" r="10"/><line x1="2" x2="22" y1="12" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/>',
    "infinity": '<path d="M12 12c-2-2.67-4-4-6-4a4 4 0 1 0 0 8c2 0 4-1.33 6-4Zm0 0c2 2.67 4 4 6 4a4 4 0 0 0 0-8c-2 0-4 1.33-6 4Z"/>',
    "users": '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>',
}


def icon(name: str, size: int = 18, color: str = "currentColor",
         stroke: float = 2.0, klass: str = "") -> str:
    paths = ICON_PATHS.get(name, ICON_PATHS["help-circle"])
    cls_attr = f' class="{klass}"' if klass else ""
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" '
        f'viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="{stroke}" '
        f'stroke-linecap="round" stroke-linejoin="round"{cls_attr} '
        f'style="display:inline-block;vertical-align:middle;flex-shrink:0;">'
        f'{paths}</svg>'
    )


DOC_TYPE_ICON_NAME = {
    DocType.CEDULA: "credit-card",
    DocType.CAMARA_COMERCIO: "building",
    DocType.RUT: "receipt",
    DocType.POLIZA: "shield-check",
    DocType.DESCONOCIDO: "help-circle",
}

DOC_TYPES_ORDER = [
    DocType.CEDULA,
    DocType.CAMARA_COMERCIO,
    DocType.RUT,
    DocType.POLIZA,
]


def _confidence_badge(value: float) -> str:
    pct = f"{value:.0%}"
    if value >= 0.85:
        bg, fg = "#DCFCE7", "#166534"
    elif value >= 0.60:
        bg, fg = "#FEF3C7", "#92400E"
    else:
        bg, fg = "#FEE2E2", "#991B1B"
    return (
        f'<span style="background:{bg};color:{fg};padding:3px 10px;'
        f'border-radius:8px;font-weight:600;font-size:0.82em;'
        f'display:inline-block;min-width:48px;text-align:center;'
        f'font-family:\'Space Grotesk\',sans-serif;">{pct}</span>'
    )


def _conf_colors(value: float) -> tuple[str, str]:
    if value >= 0.85:
        return "#DCFCE7", "#166534"
    if value >= 0.60:
        return "#FEF3C7", "#92400E"
    return "#FEE2E2", "#991B1B"


# ---------------------------------------------------------------------------
# Page config + lectura de query params (modo dev)
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="DocuInsight · Plataforma de inteligencia documental · SinergIA Lab",
    page_icon=Image.open(LOGO_PATH),
    layout="wide",
    initial_sidebar_state="collapsed",
)

use_mock = (
    st.query_params.get("dev") == "1"
    or os.environ.get("DOCUINSIGHT_MOCK") == "1"
)

PM = _platform_metrics()
TOTAL_FIELDS = sum(len(v) for v in EXPECTED_ENTITIES.values())


# ---------------------------------------------------------------------------
# CSS global (sistema de diseno enterprise unificado con la landing)
# ---------------------------------------------------------------------------

st.markdown(
    f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=Space+Grotesk:wght@500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap');

:root {{
    --brand-blue: {PRIMARY};
    --brand-blue-dark: {PRIMARY_DARK};
    --brand-blue-light: {PRIMARY_LIGHT};
    --brand-orange: {ACCENT};
    --brand-orange-light: {ACCENT_LIGHT};
    --brand-cream: {CREAM};
    --brand-dark: {DARK};
    --brand-ink: {INK};
    --success: {SUCCESS};
    --warn: {WARN};
    --danger: {DANGER};
    --shadow-xs: 0 1px 2px rgba(15, 23, 42, 0.04);
    --shadow-sm: 0 4px 12px -2px rgba(12, 116, 200, 0.08);
    --shadow-md: 0 12px 28px -8px rgba(12, 116, 200, 0.18);
    --shadow-lg: 0 24px 48px -12px rgba(12, 116, 200, 0.22);
    --shadow-glow: 0 0 0 1px rgba(12, 116, 200, 0.08), 0 8px 24px -8px rgba(12, 116, 200, 0.25);
}}

/* --- Esconder chrome Streamlit --- */
[data-testid="stSidebar"], [data-testid="collapsedControl"],
[data-testid="stToolbar"], [data-testid="stDecoration"],
[data-testid="stHeader"], footer {{
    display: none !important;
}}

/* --- Fondo: crema con mesh sutil --- */
.stApp {{
    background-color: {CREAM};
    background-image:
        radial-gradient(at 8% 12%, hsla(208, 88%, 60%, 0.16) 0px, transparent 50%),
        radial-gradient(at 92% 18%, hsla(19, 99%, 56%, 0.13) 0px, transparent 50%),
        radial-gradient(at 50% 95%, hsla(208, 88%, 60%, 0.08) 0px, transparent 55%);
    background-attachment: fixed;
}}

/* --- Tipografia --- */
html, body, [class*="css"], .stMarkdown, p, span, div, li {{
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    color: {DARK};
}}
h1, h2, h3, h4, .display, .stMarkdown h1, .stMarkdown h2, .stMarkdown h3 {{
    font-family: 'Space Grotesk', sans-serif !important;
    color: {INK};
    letter-spacing: -0.02em;
}}
.mono {{ font-family: 'JetBrains Mono', monospace; }}

.block-container {{
    padding-top: 0 !important;
    padding-bottom: 5rem !important;
    max-width: 1480px !important;
}}

/* ============================================================
   NAVBAR — strip + main bar
   ============================================================ */
.brand-strip {{
    position: fixed; top: 0; left: 0; right: 0;
    height: 3px; z-index: 1000;
    background: linear-gradient(90deg, {PRIMARY} 0%, {ACCENT} 100%);
}}
.navbar {{
    position: sticky; top: 3px; z-index: 100;
    background: rgba(255, 244, 244, 0.92);
    backdrop-filter: blur(24px) saturate(180%);
    -webkit-backdrop-filter: blur(24px) saturate(180%);
    border-bottom: 1px solid rgba(15, 23, 42, 0.06);
    padding: 0.85rem 2rem;
    margin: 0 -3rem 1.5rem -3rem;
}}
.navbar-inner {{
    max-width: 1480px; margin: 0 auto;
    display: flex; align-items: center; justify-content: space-between; gap: 1rem;
}}
.navbar-brand {{
    display: flex; align-items: center; gap: 0.85rem;
    text-decoration: none !important;
    transition: opacity 0.2s ease;
}}
.navbar-brand:hover {{ opacity: 0.85; }}
.navbar-brand img {{
    width: 40px; height: 40px; border-radius: 9px;
    background: white; padding: 5px;
    box-shadow: var(--shadow-sm);
    object-fit: contain;
}}
.navbar-brand .brand-name {{
    font-family: 'Space Grotesk', sans-serif;
    font-weight: 700; color: {INK};
    font-size: 0.95rem; line-height: 1.15;
}}
.navbar-brand .brand-sub {{
    color: {PRIMARY}; font-weight: 600; font-size: 0.66rem;
    text-transform: uppercase; letter-spacing: 0.14em; margin-top: 2px;
}}
.navbar-center {{
    display: flex; align-items: center; gap: 1.5rem;
    color: rgba(65, 68, 75, 0.55);
    font-size: 0.78rem;
    font-family: 'JetBrains Mono', monospace;
}}
.navbar-center .stat-item {{
    display: flex; align-items: center; gap: 0.4rem;
}}
.navbar-center .stat-item strong {{
    color: {INK}; font-weight: 600;
}}
.navbar-actions {{ display: flex; align-items: center; gap: 0.5rem; }}
.navbar-status {{
    display: inline-flex; align-items: center; gap: 0.45rem;
    padding: 0.35rem 0.85rem; border-radius: 999px;
    background: rgba(16, 185, 129, 0.08);
    border: 1px solid rgba(16, 185, 129, 0.2);
    color: #047857; font-size: 0.7rem; font-weight: 700;
    text-transform: uppercase; letter-spacing: 0.1em;
}}
.navbar-status .dot {{
    width: 6px; height: 6px; border-radius: 50%; background: {SUCCESS};
    animation: pulse-green 1.8s ease-in-out infinite;
}}
@keyframes pulse-green {{
    0%, 100% {{ box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.35); }}
    50% {{ box-shadow: 0 0 0 6px rgba(16, 185, 129, 0); }}
}}
.navbar-back {{
    display: inline-flex; align-items: center; gap: 0.4rem;
    color: rgba(65, 68, 75, 0.7); text-decoration: none !important;
    font-size: 0.85rem; font-weight: 500;
    padding: 0.5rem 1rem; border-radius: 10px;
    transition: all 0.2s ease;
}}
.navbar-back:hover {{
    color: {PRIMARY}; background: rgba(12, 116, 200, 0.06);
}}

/* ============================================================
   APP HEADER
   ============================================================ */
.app-header {{
    padding: 1rem 0 1.75rem 0;
    margin: 0 0 1.25rem 0;
    border-bottom: 1px solid rgba(15, 23, 42, 0.06);
}}
.app-header .accent-bar {{
    width: 40px; height: 2px;
    background: {PRIMARY};
    margin-bottom: 1rem;
}}
.app-header h1 {{
    font-family: 'Space Grotesk', sans-serif !important;
    font-size: clamp(1.85rem, 3vw, 2.4rem) !important;
    font-weight: 700 !important;
    color: {INK} !important;
    margin: 0 0 0.45rem 0 !important;
    line-height: 1.1; letter-spacing: -0.025em;
}}
.app-header h1 .gradient-text {{
    background: linear-gradient(135deg, {PRIMARY} 0%, {ACCENT} 100%);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
    background-clip: text;
}}
.app-header p {{
    color: rgba(65, 68, 75, 0.7);
    font-size: 1rem; margin: 0; max-width: 720px;
}}

/* Capability strip */
.capability-strip {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    gap: 1px;
    background: rgba(15, 23, 42, 0.06);
    border: 1px solid rgba(15, 23, 42, 0.06);
    border-radius: 14px;
    margin: 1.25rem 0 0 0;
    overflow: hidden;
}}
.capability-strip .cap-item {{
    background: rgba(255, 255, 255, 0.65);
    backdrop-filter: blur(12px);
    padding: 0.95rem 1.15rem;
    display: flex; align-items: center; gap: 0.85rem;
}}
.cap-item .ic {{
    width: 38px; height: 38px;
    border-radius: 10px;
    background: {PRIMARY_LIGHT};
    color: {PRIMARY};
    display: flex; align-items: center; justify-content: center;
    flex-shrink: 0;
}}
.cap-item .body {{ flex: 1; min-width: 0; }}
.cap-item .value {{
    font-family: 'Space Grotesk', sans-serif;
    font-size: 1.15rem; font-weight: 700;
    color: {INK}; line-height: 1.1;
}}
.cap-item .label {{
    font-size: 0.7rem; color: rgba(65, 68, 75, 0.6);
    text-transform: uppercase; letter-spacing: 0.06em;
    margin-top: 0.15rem; font-weight: 600;
}}

/* ============================================================
   TABBAR CUSTOM (con iconos SVG)
   ============================================================ */
.tabbar {{
    display: inline-flex;
    gap: 4px;
    background: rgba(255, 255, 255, 0.85);
    backdrop-filter: blur(20px) saturate(180%);
    -webkit-backdrop-filter: blur(20px) saturate(180%);
    border: 1px solid rgba(15, 23, 42, 0.06);
    border-radius: 13px;
    padding: 5px;
    margin: 0.5rem 0 1.75rem 0;
    box-shadow: var(--shadow-xs);
}}
.tab-link {{
    display: inline-flex; align-items: center; gap: 0.55rem;
    padding: 0.6rem 1.3rem;
    border-radius: 9px;
    font-family: 'Space Grotesk', sans-serif;
    font-weight: 600;
    font-size: 0.92rem;
    color: rgba(65, 68, 75, 0.7);
    text-decoration: none !important;
    transition: all 0.2s ease;
    line-height: 1;
}}
.tab-link:hover {{
    color: {PRIMARY};
    background: rgba(12, 116, 200, 0.05);
}}
.tab-link.active {{
    background: {INK};
    color: white;
    box-shadow: 0 2px 6px -2px rgba(15, 23, 42, 0.3);
}}
.tab-link.active:hover {{
    color: white;
    background: {INK};
}}

/* ============================================================
   CARDS — universal panel
   ============================================================ */
.panel {{
    background: rgba(255, 255, 255, 0.78);
    backdrop-filter: blur(16px);
    -webkit-backdrop-filter: blur(16px);
    border: 1px solid rgba(15, 23, 42, 0.06);
    border-radius: 16px;
    box-shadow: var(--shadow-sm);
}}
.panel-header {{
    padding: 1.1rem 1.5rem;
    border-bottom: 1px solid rgba(15, 23, 42, 0.05);
    display: flex; align-items: center; justify-content: space-between; gap: 1rem;
}}
.panel-header h3 {{
    font-family: 'Space Grotesk', sans-serif !important;
    font-size: 0.95rem !important;
    font-weight: 700 !important;
    color: {INK} !important;
    margin: 0 !important;
    display: flex; align-items: center; gap: 0.55rem;
    text-transform: uppercase;
    letter-spacing: 0.06em;
}}
.panel-header h3 .ic-wrap {{
    color: {PRIMARY};
}}
.panel-header .meta {{
    color: rgba(65, 68, 75, 0.55);
    font-size: 0.78rem;
    font-family: 'JetBrains Mono', monospace;
}}
.panel-body {{ padding: 1.25rem 1.5rem; }}

/* --- KPI cards --- */
.kpi-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 1rem;
    margin-bottom: 1.5rem;
}}
.kpi {{
    background: rgba(255, 255, 255, 0.85);
    backdrop-filter: blur(16px);
    border: 1px solid rgba(15, 23, 42, 0.06);
    border-radius: 14px;
    padding: 1.15rem 1.35rem;
    position: relative;
    transition: all 0.25s ease;
    overflow: hidden;
}}
.kpi:hover {{
    transform: translateY(-2px);
    box-shadow: var(--shadow-md);
    border-color: rgba(12, 116, 200, 0.18);
}}
.kpi::before {{
    content: ''; position: absolute; top: 0; left: 0; right: 0; height: 2px;
    background: {PRIMARY};
    opacity: 0; transition: opacity 0.25s ease;
}}
.kpi:hover::before {{ opacity: 1; }}
.kpi-head {{
    display: flex; align-items: center; gap: 0.5rem;
    color: rgba(65, 68, 75, 0.6);
    font-size: 0.7rem; font-weight: 700;
    text-transform: uppercase; letter-spacing: 0.07em;
    margin-bottom: 0.65rem;
}}
.kpi-head .ic {{ color: {PRIMARY}; }}
.kpi-head.accent .ic {{ color: {ACCENT}; }}
.kpi-value {{
    font-family: 'Space Grotesk', sans-serif;
    color: {INK}; font-size: 2rem; font-weight: 700;
    line-height: 1; letter-spacing: -0.025em;
}}
.kpi-unit {{
    font-size: 0.85rem; color: rgba(65, 68, 75, 0.55);
    font-weight: 500; margin-left: 0.25rem;
}}
.kpi-sub {{
    color: rgba(65, 68, 75, 0.55);
    font-size: 0.76rem; margin-top: 0.45rem;
    font-family: 'JetBrains Mono', monospace;
}}
.kpi-sub.success {{ color: #047857; }}
.kpi-sub.warn {{ color: #B45309; }}
.kpi-sub.danger {{ color: #B91C1C; }}

/* --- Doc type cards --- */
.doctype-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
    gap: 1rem;
}}
.doctype {{
    background: rgba(255, 255, 255, 0.85);
    backdrop-filter: blur(16px);
    border: 1px solid rgba(15, 23, 42, 0.06);
    border-radius: 14px;
    padding: 1.1rem 1.3rem;
    transition: all 0.25s ease;
    position: relative; overflow: hidden;
}}
.doctype:hover {{
    transform: translateY(-3px);
    box-shadow: var(--shadow-md);
    border-color: rgba(12, 116, 200, 0.2);
}}
.doctype.active::after {{
    content: ''; position: absolute;
    top: 0; left: 0; right: 0; height: 3px;
    background: {PRIMARY};
}}
.doctype-icon {{
    width: 44px; height: 44px;
    border-radius: 11px;
    background: rgba(12, 116, 200, 0.07);
    color: {PRIMARY};
    display: flex; align-items: center; justify-content: center;
    margin-bottom: 0.85rem;
}}
.doctype.active .doctype-icon {{
    background: {PRIMARY};
    color: white;
}}
.doctype .dt-label {{
    font-family: 'Space Grotesk', sans-serif;
    color: {INK}; font-weight: 700; font-size: 0.95rem;
    margin-bottom: 0.2rem;
}}
.doctype .dt-meta {{
    color: rgba(65, 68, 75, 0.55);
    font-size: 0.78rem;
    font-family: 'JetBrains Mono', monospace;
}}
.doctype .dt-count {{
    position: absolute; top: 1.1rem; right: 1.3rem;
    font-family: 'Space Grotesk', sans-serif;
    font-size: 1.5rem; font-weight: 700;
    color: {INK};
    line-height: 1;
}}
.doctype .dt-count-label {{
    position: absolute; top: 2.6rem; right: 1.3rem;
    font-size: 0.62rem; color: rgba(65, 68, 75, 0.5);
    text-transform: uppercase; letter-spacing: 0.08em;
    font-weight: 600;
}}

/* ============================================================
   UPLOADER
   ============================================================ */
.upload-shell {{ max-width: 820px; margin: 0.5rem auto 0 auto; }}
.upload-card-header {{
    background: rgba(255, 255, 255, 0.85);
    backdrop-filter: blur(28px) saturate(180%);
    -webkit-backdrop-filter: blur(28px) saturate(180%);
    border: 1px solid rgba(15, 23, 42, 0.06);
    border-bottom: none;
    border-radius: 16px 16px 0 0;
    padding: 1.4rem 1.75rem 0.65rem 1.75rem;
}}
.upload-card-header h2 {{
    font-family: 'Space Grotesk', sans-serif !important;
    font-size: 1.05rem !important;
    font-weight: 700 !important;
    color: {INK} !important;
    margin: 0 0 0.3rem 0 !important;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    display: flex; align-items: center; gap: 0.5rem;
}}
.upload-card-header h2 .ic {{ color: {PRIMARY}; }}
.upload-card-header p {{
    color: rgba(65, 68, 75, 0.65);
    font-size: 0.88rem; margin: 0;
}}

[data-testid="stFileUploader"] {{ max-width: 820px; margin: 0 auto; }}
[data-testid="stFileUploader"] > div:first-child {{
    background: rgba(255, 255, 255, 0.85);
    backdrop-filter: blur(28px) saturate(180%);
    -webkit-backdrop-filter: blur(28px) saturate(180%);
    border: 1px solid rgba(15, 23, 42, 0.06);
    border-top: none;
    border-radius: 0 0 16px 16px;
    padding: 0.5rem 1.75rem 1.75rem 1.75rem;
    box-shadow: var(--shadow-md);
}}
[data-testid="stFileUploader"] section {{
    background: rgba(12, 116, 200, 0.025) !important;
    border: 2px dashed rgba(12, 116, 200, 0.28) !important;
    border-radius: 12px !important;
    padding: 2.25rem 1rem !important;
    transition: all 0.2s ease !important;
}}
[data-testid="stFileUploader"] section:hover {{
    border-color: {ACCENT} !important;
    background: rgba(254, 107, 35, 0.04) !important;
}}
[data-testid="stFileUploader"] section small,
[data-testid="stFileUploader"] section span {{
    color: rgba(65, 68, 75, 0.7) !important;
}}
[data-testid="stFileUploader"] button {{
    background: white !important;
    color: {PRIMARY} !important;
    border: 1px solid rgba(12, 116, 200, 0.25) !important;
    border-radius: 9px !important;
    font-weight: 600 !important;
}}
[data-testid="stFileUploader"] button:hover {{
    background: rgba(12, 116, 200, 0.05) !important;
    border-color: {PRIMARY} !important;
}}
.uploader-aux {{ max-width: 820px; margin: 0.85rem auto 0 auto; }}
.file-chip {{
    padding: 0.85rem 1.1rem;
    background: rgba(255, 255, 255, 0.85);
    backdrop-filter: blur(16px);
    border: 1px solid rgba(15, 23, 42, 0.06);
    border-radius: 12px;
    display: flex; align-items: center; gap: 0.7rem;
}}
.file-chip .ic {{ color: {PRIMARY}; }}
.file-chip .name {{ font-weight: 600; color: {INK}; flex: 1; min-width: 0;
                    word-break: break-all; font-size: 0.92rem; }}
.file-chip .size {{
    color: rgba(65, 68, 75, 0.55);
    font-family: 'JetBrains Mono', monospace; font-size: 0.78rem;
    flex-shrink: 0;
}}

/* ============================================================
   BUTTONS
   ============================================================ */
.stButton > button[kind="primary"], .stDownloadButton > button {{
    background: {INK} !important;
    color: white !important;
    border: none !important;
    border-radius: 10px !important;
    padding: 0.7rem 1.4rem !important;
    font-family: 'Inter', sans-serif !important;
    font-weight: 600 !important;
    box-shadow: 0 1px 2px rgba(15, 23, 42, 0.1) !important;
    transition: all 0.15s ease !important;
}}
.stButton > button[kind="primary"]:hover, .stDownloadButton > button:hover {{
    background: #1E293B !important;
    box-shadow: 0 4px 12px -2px rgba(15, 23, 42, 0.2) !important;
    color: white !important;
}}
.stButton > button[kind="secondary"] {{
    background: white !important;
    color: {PRIMARY} !important;
    border: 1.5px solid rgba(12, 116, 200, 0.2) !important;
    border-radius: 11px !important;
    padding: 0.6rem 1.2rem !important;
    font-weight: 600 !important;
}}
.stButton > button[kind="secondary"]:hover {{
    border-color: {PRIMARY} !important;
    background: rgba(12, 116, 200, 0.05) !important;
    color: {PRIMARY} !important;
}}
[data-testid="stPopoverButton"] {{
    background: white !important;
    color: {PRIMARY} !important;
    border: 1.5px solid rgba(12, 116, 200, 0.2) !important;
    border-radius: 11px !important;
    padding: 0.6rem 1.2rem !important;
    font-weight: 600 !important;
}}
[data-testid="stPopoverButton"]:hover {{
    border-color: {PRIMARY} !important;
    background: rgba(12, 116, 200, 0.05) !important;
}}

/* Progress / status */
[data-testid="stProgress"] > div > div > div > div {{
    background: linear-gradient(90deg, {PRIMARY}, {ACCENT}) !important;
}}
[data-testid="stStatusWidget"], [data-testid="stStatus"] {{
    background: rgba(255, 255, 255, 0.85) !important;
    border: 1px solid rgba(15, 23, 42, 0.06) !important;
    border-radius: 12px !important;
}}

/* ============================================================
   RESULT
   ============================================================ */
.result-shell {{
    max-width: 1180px; margin: 2.5rem auto 0 auto; padding: 0 0.25rem;
}}
.result-hero {{
    background: rgba(255, 255, 255, 0.92);
    backdrop-filter: blur(24px) saturate(180%);
    -webkit-backdrop-filter: blur(24px) saturate(180%);
    border: 1px solid rgba(15, 23, 42, 0.06);
    border-radius: 16px;
    padding: 1.65rem 2rem;
    margin-bottom: 1.5rem;
    box-shadow: var(--shadow-sm);
    display: flex; align-items: center; gap: 1.5rem; flex-wrap: wrap;
    position: relative; overflow: hidden;
}}
.result-hero::before {{
    content: ''; position: absolute; top: 0; left: 0; bottom: 0; width: 3px;
    background: {PRIMARY};
}}
.result-hero .r-icon {{
    width: 60px; height: 60px;
    border-radius: 13px;
    background: {PRIMARY_LIGHT};
    color: {PRIMARY};
    display: flex; align-items: center; justify-content: center;
    flex-shrink: 0;
}}
.result-hero .r-body {{ flex: 1; min-width: 240px; }}
.result-hero .r-label {{
    color: rgba(65, 68, 75, 0.55); font-size: 0.68rem;
    text-transform: uppercase; letter-spacing: 0.1em;
    margin-bottom: 0.3rem; font-weight: 700;
}}
.result-hero .r-doctype {{
    font-family: 'Space Grotesk', sans-serif;
    color: {INK}; font-size: 1.65rem; font-weight: 700;
    line-height: 1.1; margin-bottom: 0.4rem; letter-spacing: -0.02em;
}}
.result-hero .r-filename {{
    color: rgba(65, 68, 75, 0.6); font-size: 0.85rem;
    word-break: break-all;
    font-family: 'JetBrains Mono', monospace;
}}
.result-hero .r-conf {{ text-align: right; flex-shrink: 0; }}
.result-hero .r-conf-pill {{
    padding: 10px 18px; border-radius: 12px;
    font-weight: 700; font-size: 1.25rem;
    display: inline-block;
    font-family: 'Space Grotesk', sans-serif;
    letter-spacing: -0.01em;
}}
.result-hero .r-conf-label {{
    color: rgba(65, 68, 75, 0.5); font-size: 0.68rem;
    text-transform: uppercase; letter-spacing: 0.08em;
    margin-top: 0.4rem; font-weight: 700;
}}

/* ============================================================
   ENTITIES TABLE
   ============================================================ */
.section-title {{
    font-family: 'Space Grotesk', sans-serif;
    color: {INK}; font-size: 0.85rem; font-weight: 700;
    margin: 1.75rem 0 0.85rem 0;
    display: flex; align-items: center; gap: 0.55rem;
    text-transform: uppercase; letter-spacing: 0.08em;
}}
.section-title .ic {{ color: {PRIMARY}; }}
.section-title .count {{
    margin-left: auto;
    color: rgba(65, 68, 75, 0.5); font-size: 0.78rem;
    font-family: 'JetBrains Mono', monospace;
    text-transform: none; letter-spacing: 0;
    font-weight: 500;
}}

.entities-table {{
    width: 100%; border-collapse: collapse;
    background: rgba(255, 255, 255, 0.85);
    backdrop-filter: blur(16px);
    -webkit-backdrop-filter: blur(16px);
    border: 1px solid rgba(15, 23, 42, 0.06);
    border-radius: 14px; overflow: hidden;
    box-shadow: var(--shadow-sm);
}}
.entities-table thead {{ background: rgba(255, 244, 244, 0.85); }}
.entities-table th {{
    padding: 12px 18px; text-align: left;
    color: {INK}; font-family: 'Space Grotesk', sans-serif;
    font-size: 0.68rem; text-transform: uppercase;
    letter-spacing: 0.1em; font-weight: 700;
}}
.entities-table th.center {{ text-align: center; width: 100px; }}
.entities-table td {{
    padding: 13px 18px;
    border-bottom: 1px solid rgba(229, 231, 235, 0.4);
    font-size: 0.92rem;
}}
.entities-table tr:last-child td {{ border-bottom: none; }}
.entities-table td.label-col {{
    color: rgba(65, 68, 75, 0.6);
    font-size: 0.83em;
    font-family: 'JetBrains Mono', monospace;
    text-transform: uppercase;
    letter-spacing: 0.04em;
}}
.entities-table td.value-col {{
    font-weight: 500; color: {INK}; word-break: break-word;
}}
.entities-table td.conf-col {{ text-align: center; }}
.entities-table tr:hover td {{ background: rgba(255, 244, 244, 0.5); }}

/* ============================================================
   CASES (history rows)
   ============================================================ */
.cases-list {{ display: flex; flex-direction: column; gap: 0.5rem; }}
.case-row {{
    background: rgba(255, 255, 255, 0.85);
    backdrop-filter: blur(16px);
    border: 1px solid rgba(15, 23, 42, 0.06);
    border-radius: 12px;
    padding: 0.95rem 1.15rem;
    display: flex; align-items: center; gap: 1rem;
    transition: all 0.2s ease;
}}
.case-row:hover {{
    transform: translateY(-1px);
    box-shadow: var(--shadow-sm);
    border-color: rgba(12, 116, 200, 0.18);
}}
.case-row .c-icon {{
    width: 36px; height: 36px; border-radius: 9px;
    background: linear-gradient(135deg, rgba(12, 116, 200, 0.1) 0%, rgba(254, 107, 35, 0.1) 100%);
    color: {PRIMARY};
    display: flex; align-items: center; justify-content: center;
    flex-shrink: 0;
}}
.case-row .c-icon.err {{
    background: rgba(220, 38, 38, 0.08);
    color: {DANGER};
}}
.case-row .c-body {{ flex: 1; min-width: 0; }}
.case-row .c-name {{
    color: {INK}; font-weight: 600; font-size: 0.9rem;
    word-break: break-all; line-height: 1.2;
}}
.case-row .c-meta {{
    color: rgba(65, 68, 75, 0.6); font-size: 0.76rem;
    margin-top: 0.2rem;
    font-family: 'JetBrains Mono', monospace;
    display: flex; gap: 0.85rem; flex-wrap: wrap; align-items: center;
}}
.case-row .c-meta .sep {{ color: rgba(65, 68, 75, 0.25); }}
.case-row .c-entities-count {{
    color: {INK}; font-weight: 700; font-size: 1.1rem;
    font-family: 'Space Grotesk', sans-serif;
    flex-shrink: 0; min-width: 36px; text-align: right;
}}
.case-row .c-entities-label {{
    color: rgba(65, 68, 75, 0.5); font-size: 0.62rem;
    font-weight: 600; text-transform: uppercase;
    letter-spacing: 0.07em; text-align: right;
    margin-top: -0.05rem;
}}
.case-row .c-pill {{
    padding: 5px 11px; border-radius: 8px;
    font-weight: 700; font-size: 0.82rem;
    font-family: 'Space Grotesk', sans-serif;
    flex-shrink: 0; min-width: 56px; text-align: center;
}}

/* ============================================================
   EMPTY STATES
   ============================================================ */
.empty-state {{
    text-align: center; padding: 4rem 2rem;
    background: rgba(255, 255, 255, 0.5);
    backdrop-filter: blur(16px);
    border: 1px dashed rgba(12, 116, 200, 0.2);
    border-radius: 16px; margin: 1rem 0;
}}
.empty-state .ic-wrap {{
    width: 60px; height: 60px; border-radius: 16px;
    background: linear-gradient(135deg, rgba(12, 116, 200, 0.08), rgba(254, 107, 35, 0.08));
    color: {PRIMARY};
    display: inline-flex; align-items: center; justify-content: center;
    margin-bottom: 1rem;
}}
.empty-state h3 {{
    color: {INK} !important;
    font-size: 1.1rem !important;
    margin: 0 0 0.4rem 0 !important;
    font-weight: 700 !important;
}}
.empty-state p {{
    color: rgba(65, 68, 75, 0.6); font-size: 0.92rem;
    margin: 0 auto; max-width: 440px;
}}

/* Error state */
.result-error {{
    max-width: 720px; margin: 1.5rem auto 0 auto;
    background: rgba(255, 255, 255, 0.92);
    border: 1px solid rgba(220, 38, 38, 0.25);
    border-left: 4px solid {DANGER};
    border-radius: 14px;
    padding: 1.4rem 1.75rem;
    box-shadow: var(--shadow-sm);
}}
.result-error h3 {{
    color: #991B1B !important;
    font-family: 'Space Grotesk', sans-serif;
    margin: 0 0 0.5rem 0 !important;
    display: flex; align-items: center; gap: 0.5rem;
}}
.result-error p {{
    color: rgba(65, 68, 75, 0.8); margin: 0;
    font-family: 'JetBrains Mono', monospace; font-size: 0.85rem;
}}

/* ============================================================
   DEV badge
   ============================================================ */
.dev-badge {{
    position: fixed; bottom: 1rem; right: 1rem; z-index: 1000;
    background: {INK}; color: white;
    padding: 5px 12px; border-radius: 8px;
    font-size: 0.66rem; font-weight: 700;
    letter-spacing: 0.1em; opacity: 0.8;
    text-transform: uppercase;
    font-family: 'JetBrains Mono', monospace;
}}

/* ============================================================
   RESPONSIVE
   ============================================================ */
@media (max-width: 900px) {{
    .navbar-center {{ display: none; }}
}}
@media (max-width: 768px) {{
    .navbar {{ padding: 0.7rem 1rem; margin: 0 -1rem 1rem -1rem; }}
    .navbar-brand img {{ width: 36px; height: 36px; }}
    .navbar-back span {{ display: none; }}
    .navbar-status {{ display: none; }}
    .result-hero {{ flex-direction: column; text-align: left; gap: 1rem; }}
    .result-hero .r-conf {{ text-align: left; }}
}}
</style>
""",
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------------
# Estado
# ---------------------------------------------------------------------------

if "history" not in st.session_state:
    st.session_state.history: list[DocumentResult] = []
if "last_result" not in st.session_state:
    st.session_state.last_result: DocumentResult | None = None


# ---------------------------------------------------------------------------
# Brand strip + Navbar
# ---------------------------------------------------------------------------

n_processed = len(st.session_state.history)
n_total_entities = sum(len(r.entities) for r in st.session_state.history if not r.error)

st.markdown(_h(f"""
<div class="brand-strip"></div>
<nav class="navbar">
<div class="navbar-inner">
<a class="navbar-brand" href="{LANDING_URL}" target="_self">
<img src="data:image/png;base64,{_logo_b64()}" alt="SinergIA Lab"/>
<div>
<div class="brand-name">SinergIA Lab</div>
<div class="brand-sub">DocuInsight</div>
</div>
</a>
<div class="navbar-center">
<span class="stat-item">{icon("layers", 14, PRIMARY)} <span><strong>4</strong> tipologías</span></span>
<span class="stat-item">{icon("tag", 14, PRIMARY)} <span><strong>{TOTAL_FIELDS}</strong> campos</span></span>
<span class="stat-item">{icon("target", 14, PRIMARY)} <span><strong>{PM['accuracy']:.0%}</strong> accuracy</span></span>
</div>
<div class="navbar-actions">
<span class="navbar-status"><span class="dot"></span>Plataforma operativa</span>
<a class="navbar-back" href="{LANDING_URL}" target="_self">{icon("chevron-left", 14, "currentColor")} <span>Sitio web</span></a>
</div>
</div>
</nav>
"""), unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# App header con capability strip
# ---------------------------------------------------------------------------

_header_html = (
    '<div class="app-header">'
    '<div class="accent-bar"></div>'
    '<h1>Centro de <span class="gradient-text">inteligencia documental</span></h1>'
    '<p>Procesamiento masivo de documentos con clasificación automática, OCR híbrido '
    'y extracción de entidades estructuradas para operaciones enterprise.</p>'
    '<div class="capability-strip">'
        f'<div class="cap-item"><div class="ic">{icon("layers", 18, PRIMARY)}</div>'
            '<div class="body"><div class="value">4 tipologías</div>'
            '<div class="label">Cédula · CC · RUT · Póliza</div></div></div>'
        f'<div class="cap-item"><div class="ic">{icon("tag", 18, PRIMARY)}</div>'
            f'<div class="body"><div class="value">{TOTAL_FIELDS} campos</div>'
            '<div class="label">Extracción NER + regex</div></div></div>'
        f'<div class="cap-item"><div class="ic">{icon("target", 18, PRIMARY)}</div>'
            f'<div class="body"><div class="value">{PM["accuracy"]:.1%}</div>'
            '<div class="label">Accuracy en clasificación</div></div></div>'
        f'<div class="cap-item"><div class="ic">{icon("cpu", 18, PRIMARY)}</div>'
            '<div class="body"><div class="value">OCR híbrido</div>'
            '<div class="label">PyMuPDF + EasyOCR</div></div></div>'
        f'<div class="cap-item"><div class="ic">{icon("infinity", 18, PRIMARY)}</div>'
            '<div class="body"><div class="value">Escalable</div>'
            '<div class="label">Miles de documentos</div></div></div>'
    '</div>'
    '</div>'
)
st.markdown(_header_html, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Helpers de render
# ---------------------------------------------------------------------------

def _entities_table_html(result: DocumentResult) -> str:
    rows = "".join(
        f'<tr>'
        f'<td class="label-col">{humanize_entity_label(e.label)}</td>'
        f'<td class="value-col">{e.value}</td>'
        f'<td class="conf-col">{_confidence_badge(e.confidence)}</td>'
        f'</tr>'
        for e in result.entities
    )
    return (
        '<table class="entities-table">'
        '<thead><tr>'
        '<th>Campo</th><th>Valor</th><th class="center">Confianza</th>'
        '</tr></thead>'
        f'<tbody>{rows}</tbody>'
        '</table>'
    )


def _render_result(result: DocumentResult) -> None:
    if result.error:
        st.markdown(_h(f"""
<div class="result-error">
<h3>{icon("x-circle", 20, "#991B1B")} No se pudo procesar el documento</h3>
<p><strong>Archivo:</strong> {result.filename}</p>
<p style="margin-top:0.5rem;"><strong>Detalle:</strong> {result.error}</p>
</div>
"""), unsafe_allow_html=True)
        return

    dt_icon = icon(DOC_TYPE_ICON_NAME[result.doc_type], 28, PRIMARY)
    conf = result.doc_type_confidence
    conf_bg, conf_fg = _conf_colors(conf)

    st.markdown(_h(f"""
<div class="result-shell">
<div class="result-hero">
<div class="r-icon">{dt_icon}</div>
<div class="r-body">
<div class="r-label">Tipo documental detectado</div>
<div class="r-doctype">{DOC_TYPE_LABELS[result.doc_type]}</div>
<div class="r-filename">{result.filename}</div>
</div>
<div class="r-conf">
<div class="r-conf-pill" style="background:{conf_bg};color:{conf_fg};">{conf:.1%}</div>
<div class="r-conf-label">Confianza</div>
</div>
</div>
</div>
"""), unsafe_allow_html=True)

    high_conf = sum(1 for e in result.entities if e.confidence >= 0.85)
    expected = len(EXPECTED_ENTITIES.get(result.doc_type, []))
    coverage = (len(result.entities) / expected * 100) if expected else 0

    # Layout 2 columnas: preview a la izquierda, datos a la derecha
    file_bytes = getattr(result, "_file_bytes", None)

    col_preview, col_data = st.columns([1, 1.1], gap="large")

    with col_preview:
        st.markdown(
            f'<div class="section-title">{icon("file", 14, PRIMARY, klass="ic")} Documento</div>',
            unsafe_allow_html=True,
        )
        if file_bytes:
            st.markdown(
                '<div style="background:white;border:1px solid rgba(15,23,42,0.06);'
                'border-radius:14px;padding:0.75rem;box-shadow:var(--shadow-sm);">',
                unsafe_allow_html=True,
            )
            _render_doc_preview(file_bytes, result.filename)
            st.markdown('</div>', unsafe_allow_html=True)
        else:
            st.info("Preview no disponible para este caso (sesion anterior).")

    with col_data:
        st.markdown(
            f'<div class="section-title">{icon("activity", 14, PRIMARY, klass="ic")} Metricas del procesamiento</div>',
            unsafe_allow_html=True,
        )
        k1, k2 = st.columns(2)
        k1.markdown(_h(f"""
<div class="kpi">
<div class="kpi-head">{icon("tag", 14, PRIMARY, klass="ic")} Entidades</div>
<div class="kpi-value">{len(result.entities)}<span class="kpi-unit">/ {expected}</span></div>
<div class="kpi-sub">{coverage:.0f}% del esquema</div>
</div>
"""), unsafe_allow_html=True)
        k2.markdown(_h(f"""
<div class="kpi">
<div class="kpi-head">{icon("check-circle", 14, PRIMARY, klass="ic")} Alta confianza</div>
<div class="kpi-value">{high_conf}<span class="kpi-unit">/ {len(result.entities)}</span></div>
<div class="kpi-sub success">campos validados</div>
</div>
"""), unsafe_allow_html=True)
        k3, k4 = st.columns(2)
        k3.markdown(_h(f"""
<div class="kpi">
<div class="kpi-head">{icon("clock", 14, PRIMARY, klass="ic")} Latencia</div>
<div class="kpi-value">{result.processing_time_ms}<span class="kpi-unit">ms</span></div>
<div class="kpi-sub">end-to-end</div>
</div>
"""), unsafe_allow_html=True)
        k4.markdown(_h(f"""
<div class="kpi">
<div class="kpi-head">{icon("file-text", 14, PRIMARY, klass="ic")} Texto OCR</div>
<div class="kpi-value">{len(result.extracted_text):,}<span class="kpi-unit">chars</span></div>
<div class="kpi-sub">tokens extraidos</div>
</div>
"""), unsafe_allow_html=True)

    # Tabla de entidades full-width abajo de las dos columnas
    st.markdown(
        f'<div class="section-title">{icon("database", 14, PRIMARY, klass="ic")} Metadatos extraidos '
        f'<span class="count">{len(result.entities)} campos</span></div>',
        unsafe_allow_html=True,
    )

    if result.entities:
        st.markdown(_entities_table_html(result), unsafe_allow_html=True)
    else:
        st.info("No se extrajeron entidades de este documento.")

    st.markdown('<div style="height:1.25rem;"></div>', unsafe_allow_html=True)
    col_ocr, col_dl = st.columns([1.5, 1])
    with col_ocr:
        with st.popover("Ver texto OCR completo", use_container_width=True):
            st.text(result.extracted_text or "(sin texto)")
    with col_dl:
        st.download_button(
            "Descargar Excel",
            data=build_excel([result]),
            file_name=(
                f"docuinsight_{Path(result.filename).stem}_"
                f"{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
            ),
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
            key=f"dl_{result.filename}_{result.processing_time_ms}",
        )


# ---------------------------------------------------------------------------
# Tabs (texto plano, sin emoji)
# ---------------------------------------------------------------------------

active_tab = st.query_params.get("tab", "dashboard")


def _tab_link(label: str, icon_name: str, key: str) -> str:
    is_active = key == active_tab
    cls = " active" if is_active else ""
    color = "white" if is_active else "currentColor"
    extras = []
    if use_mock:
        extras.append("dev=1")
    extras.append(f"tab={key}")
    href = "?" + "&amp;".join(extras)
    return (
        f'<a href="{href}" class="tab-link{cls}" target="_self">'
        f'{icon(icon_name, 16, color)}<span>{label}</span>'
        f'</a>'
    )


st.markdown(
    '<div class="tabbar">'
    + _tab_link("Dashboard", "bar-chart", "dashboard")
    + _tab_link("Procesar", "scan", "procesar")
    + _tab_link("Casos", "folder", "casos")
    + '</div>',
    unsafe_allow_html=True,
)


# ============================================================================
# TAB: DASHBOARD
# ============================================================================

if active_tab == "dashboard":
    history = st.session_state.history
    ok = [r for r in history if not r.error]
    n_total = len(history)
    n_ok = len(ok)
    n_err = n_total - n_ok

    avg_time = (sum(r.processing_time_ms for r in ok) / n_ok) if n_ok else 0
    avg_conf = (sum(r.doc_type_confidence for r in ok) / n_ok) if n_ok else 0
    total_entities = sum(len(r.entities) for r in ok)

    # KPIs principales
    c1, c2, c3, c4 = st.columns(4)
    err_html = f' &middot; <span style="color:#B91C1C;">{n_err} con error</span>' if n_err else ''
    c1.markdown(_h(f"""
<div class="kpi">
<div class="kpi-head">{icon("inbox", 14, PRIMARY, klass="ic")} Documentos procesados</div>
<div class="kpi-value">{n_total}</div>
<div class="kpi-sub"><span style="color:#047857;">{n_ok} ok</span>{err_html}</div>
</div>
"""), unsafe_allow_html=True)
    c2.markdown(_h(f"""
<div class="kpi">
<div class="kpi-head accent">{icon("database", 14, ACCENT, klass="ic")} Entidades extraídas</div>
<div class="kpi-value">{total_entities:,}</div>
<div class="kpi-sub">total acumulado en sesión</div>
</div>
"""), unsafe_allow_html=True)
    c3.markdown(_h(f"""
<div class="kpi">
<div class="kpi-head">{icon("clock", 14, PRIMARY, klass="ic")} Latencia promedio</div>
<div class="kpi-value">{int(avg_time):,}<span class="kpi-unit">ms</span></div>
<div class="kpi-sub">por documento</div>
</div>
"""), unsafe_allow_html=True)
    c4.markdown(_h(f"""
<div class="kpi">
<div class="kpi-head">{icon("target", 14, PRIMARY, klass="ic")} Confianza media</div>
<div class="kpi-value">{avg_conf:.1%}</div>
<div class="kpi-sub">clasificación correcta</div>
</div>
"""), unsafe_allow_html=True)

    if not history:
        st.markdown(_h(f"""
<div class="empty-state" style="margin-top:1.5rem;">
<div class="ic-wrap">{icon("activity", 28, PRIMARY)}</div>
<h3>Aún no hay actividad en esta sesión</h3>
<p>El dashboard se llena automáticamente a medida que procesás documentos. Empezá en la pestaña <strong>Procesar</strong>.</p>
</div>
"""), unsafe_allow_html=True)
    elif ok:
        # Charts
        col_pie, col_hist = st.columns([1, 1])
        with col_pie:
            st.markdown(
                f'<div class="panel"><div class="panel-header">'
                f'<h3><span class="ic-wrap">{icon("pie-chart", 14, PRIMARY)}</span> Distribución por tipo</h3>'
                f'<span class="meta">{n_ok} documentos</span>'
                f'</div><div class="panel-body">',
                unsafe_allow_html=True,
            )
            dist = {DOC_TYPE_LABELS[dt]: sum(1 for r in ok if r.doc_type == dt)
                    for dt in DOC_TYPES_ORDER}
            dist = {k: v for k, v in dist.items() if v > 0}
            if dist:
                fig = px.pie(
                    names=list(dist.keys()),
                    values=list(dist.values()),
                    color_discrete_sequence=[PRIMARY, ACCENT, PRIMARY_DARK, "#82A5C9"],
                    hole=0.6,
                )
                fig.update_traces(
                    textposition="outside",
                    textinfo="label+percent",
                    marker=dict(line=dict(color="white", width=3)),
                    textfont=dict(family="Inter, sans-serif", size=12, color=INK),
                )
                fig.update_layout(
                    height=300,
                    margin=dict(t=10, b=10, l=10, r=10),
                    showlegend=False,
                    font=dict(family="Inter, sans-serif", color=DARK, size=12),
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(0,0,0,0)",
                )
                st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
            st.markdown('</div></div>', unsafe_allow_html=True)

        with col_hist:
            st.markdown(
                f'<div class="panel"><div class="panel-header">'
                f'<h3><span class="ic-wrap">{icon("bar-chart", 14, PRIMARY)}</span> Distribución de confianza</h3>'
                f'<span class="meta">{n_ok} muestras</span>'
                f'</div><div class="panel-body">',
                unsafe_allow_html=True,
            )
            confs = [r.doc_type_confidence for r in ok]
            fig2 = px.histogram(
                x=confs, nbins=10, range_x=[0, 1],
                color_discrete_sequence=[PRIMARY],
            )
            fig2.update_traces(marker_line_color="white", marker_line_width=2)
            fig2.update_layout(
                height=300,
                margin=dict(t=10, b=40, l=40, r=10),
                xaxis_title=None, yaxis_title=None,
                bargap=0.08,
                font=dict(family="Inter, sans-serif", color=DARK, size=12),
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                xaxis=dict(tickformat=".0%", showgrid=False,
                           tickfont=dict(family="JetBrains Mono, monospace", size=11)),
                yaxis=dict(gridcolor="rgba(15,23,42,0.05)",
                           tickfont=dict(family="JetBrains Mono, monospace", size=11)),
            )
            st.plotly_chart(fig2, use_container_width=True, config={"displayModeBar": False})
            st.markdown('</div></div>', unsafe_allow_html=True)

        # Tipos en sesión
        st.markdown(
            f'<div class="section-title">{icon("layers", 14, PRIMARY, klass="ic")} '
            f'Tipos documentales en esta sesión</div>',
            unsafe_allow_html=True,
        )
        cards_html = '<div class="doctype-grid">'
        for dt in DOC_TYPES_ORDER:
            count = sum(1 for r in ok if r.doc_type == dt)
            pct = (count / n_ok * 100) if n_ok else 0
            active_cls = " active" if count > 0 else ""
            ic = icon(DOC_TYPE_ICON_NAME[dt], 22)
            cards_html += (
                f'<div class="doctype{active_cls}">'
                f'<div class="doctype-icon">{ic}</div>'
                f'<div class="dt-label">{DOC_TYPE_LABELS[dt]}</div>'
                f'<div class="dt-meta">{pct:.0f}% de la sesión</div>'
                f'<div class="dt-count">{count}</div>'
                f'<div class="dt-count-label">docs</div>'
                f'</div>'
            )
        cards_html += '</div>'
        st.markdown(cards_html, unsafe_allow_html=True)


# ============================================================================
# TAB: PROCESAR
# ============================================================================

elif active_tab == "procesar":
    st.markdown(_h(f"""
<div class="upload-shell">
<div class="upload-card-header">
<h2>{icon("upload", 16, PRIMARY, klass="ic")} Ingestar documento</h2>
<p>PDF, PNG o JPG · OCR + clasificación + extracción en tiempo real</p>
</div>
</div>
"""), unsafe_allow_html=True)

    uploaded = st.file_uploader(
        "Arrastrá el archivo o hacé clic para seleccionar",
        type=["pdf", "png", "jpg", "jpeg"],
        accept_multiple_files=False,
        label_visibility="collapsed",
        key="single_uploader",
    )

    if uploaded:
        st.markdown(_h(f"""
<div class="uploader-aux">
<div class="file-chip">
<span class="ic">{icon("file", 18, PRIMARY)}</span>
<span class="name">{uploaded.name}</span>
<span class="size">{uploaded.size / 1024:.1f} KB</span>
</div>
</div>
"""), unsafe_allow_html=True)

        _, btn_col, _ = st.columns([1, 2, 1])
        with btn_col:
            process = st.button(
                "Procesar documento  →",
                type="primary",
                use_container_width=True,
                key="process_btn",
            )

        if process:
            file_bytes = uploaded.getvalue()
            pipeline = _cached_pipeline(use_mock)
            with st.status("Procesando documento…", expanded=True) as status:
                st.write("Extrayendo texto (OCR)…")
                try:
                    result = pipeline.process(file_bytes, uploaded.name)
                    if result.error:
                        status.update(label=result.error, state="error")
                    else:
                        st.write(
                            f"Clasificado como **{DOC_TYPE_LABELS[result.doc_type]}** "
                            f"({result.doc_type_confidence:.1%} confianza)"
                        )
                        st.write(f"{len(result.entities)} entidades extraidas")
                        status.update(label="Procesamiento completo", state="complete")
                except Exception as e:
                    result = DocumentResult(
                        filename=uploaded.name,
                        doc_type=DocType.DESCONOCIDO,
                        doc_type_confidence=0.0,
                        extracted_text="",
                        error=f"Error en pipeline: {type(e).__name__}: {e}",
                    )
                    status.update(label=f"Error: {e}", state="error")

            # Adjuntamos los bytes al result para que el preview funcione despues
            # (en sesion actual y al volver desde la tab Casos)
            result._file_bytes = file_bytes
            st.session_state.last_result = result
            st.session_state.history.append(result)

    if st.session_state.last_result is not None:
        _render_result(st.session_state.last_result)
    elif not uploaded:
        st.markdown(_h(f"""
<div class="empty-state" style="margin-top:1.5rem;">
<div class="ic-wrap">{icon("scan", 28, PRIMARY)}</div>
<h3>Listo para procesar</h3>
<p>Soltá un documento arriba y vas a ver acá el tipo detectado, las entidades extraídas y el JSON estructurado en menos de 3 segundos.</p>
</div>
"""), unsafe_allow_html=True)


# ============================================================================
# TAB: CASOS
# ============================================================================

elif active_tab == "casos":
    history = st.session_state.history

    if not history:
        st.markdown(_h(f"""
<div class="empty-state">
<div class="ic-wrap">{icon("folder", 28, PRIMARY)}</div>
<h3>No hay casos registrados</h3>
<p>Cada documento procesado queda registrado acá durante la sesión. Una vez integrado a la base de datos persistirán entre sesiones.</p>
</div>
"""), unsafe_allow_html=True)
    else:
        # Toolbar
        col_filter, col_dl, col_clear = st.columns([2, 1, 1])
        with col_filter:
            options = ["Todos los tipos"] + [DOC_TYPE_LABELS[dt] for dt in DOC_TYPES_ORDER]
            errors_exist = any(r.error for r in history)
            if errors_exist:
                options.append("Solo errores")
            filter_choice = st.selectbox(
                "Filtrar", options=options, index=0, label_visibility="collapsed"
            )
        with col_dl:
            ok_history = [r for r in history if not r.error]
            st.download_button(
                "Exportar sesión",
                data=build_excel(ok_history) if ok_history else b"",
                file_name=f"docuinsight_sesion_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
                disabled=not ok_history,
                key="dl_session",
            )
        with col_clear:
            if st.button("Limpiar sesión", type="secondary",
                         use_container_width=True, key="clear_session"):
                st.session_state.history = []
                st.session_state.last_result = None
                st.rerun()

        # Filtro
        if filter_choice == "Todos los tipos":
            filtered = history
        elif filter_choice == "Solo errores":
            filtered = [r for r in history if r.error]
        else:
            filtered = [r for r in history if DOC_TYPE_LABELS.get(r.doc_type) == filter_choice]

        st.markdown(
            f'<div style="color:rgba(65,68,75,0.55);font-size:0.8rem;'
            f'font-family:\'JetBrains Mono\',monospace;margin:1rem 0 0.75rem 0;">'
            f'{len(filtered)} de {len(history)} casos</div>',
            unsafe_allow_html=True,
        )

        # Render rows
        for idx, result in enumerate(filtered):
            if result.error:
                ic = icon("alert-circle", 18, DANGER)
                ic_cls = " err"
                meta_html = (
                    f'<span>{result.error[:80]}{"..." if len(result.error) > 80 else ""}</span>'
                )
                pill_html = (
                    f'<div class="c-pill" style="background:#FEE2E2;color:#991B1B;">'
                    f'Error</div>'
                )
                ent_count_html = ''
            else:
                ic = icon(DOC_TYPE_ICON_NAME[result.doc_type], 18)
                ic_cls = ""
                conf_bg, conf_fg = _conf_colors(result.doc_type_confidence)
                meta_html = (
                    f'<span>{DOC_TYPE_LABELS[result.doc_type]}</span>'
                    f'<span class="sep">·</span>'
                    f'<span>{result.processing_time_ms} ms</span>'
                )
                pill_html = (
                    f'<div class="c-pill" style="background:{conf_bg};color:{conf_fg};">'
                    f'{result.doc_type_confidence:.0%}</div>'
                )
                ent_count_html = (
                    f'<div>'
                    f'<div class="c-entities-count">{len(result.entities)}</div>'
                    f'<div class="c-entities-label">campos</div>'
                    f'</div>'
                )

            # Row visual (full HTML control)
            st.markdown(_h(f"""
<div class="case-row">
<div class="c-icon{ic_cls}">{ic}</div>
<div class="c-body">
<div class="c-name">{result.filename}</div>
<div class="c-meta">{meta_html}</div>
</div>
{ent_count_html}
{pill_html}
</div>
"""), unsafe_allow_html=True)

            # Detalle expandible (separado del row visual de arriba — Streamlit limitation)
            with st.expander("Ver detalle", expanded=False):
                if result.error:
                    st.error(f"Error: {result.error}")
                else:
                    case_bytes = getattr(result, "_file_bytes", None)
                    if case_bytes:
                        prev_col, data_col = st.columns([1, 1.2], gap="medium")
                        with prev_col:
                            st.markdown(
                                '<div style="background:white;border:1px solid rgba(15,23,42,0.06);'
                                'border-radius:12px;padding:0.6rem;">',
                                unsafe_allow_html=True,
                            )
                            _render_doc_preview(case_bytes, result.filename)
                            st.markdown('</div>', unsafe_allow_html=True)
                        with data_col:
                            st.markdown(_entities_table_html(result), unsafe_allow_html=True)
                    else:
                        st.markdown(_entities_table_html(result), unsafe_allow_html=True)
                    st.markdown('<div style="height:0.75rem;"></div>', unsafe_allow_html=True)
                    col_a, col_b = st.columns([1.5, 1])
                    with col_a:
                        with st.popover("Ver texto OCR", use_container_width=True):
                            st.text(result.extracted_text or "(sin texto)")
                    with col_b:
                        st.download_button(
                            "Excel",
                            data=build_excel([result]),
                            file_name=(
                                f"docuinsight_{Path(result.filename).stem}_"
                                f"{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
                            ),
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            use_container_width=True,
                            key=f"dl_case_{idx}",
                        )


# ---------------------------------------------------------------------------
# Dev badge
# ---------------------------------------------------------------------------

if use_mock:
    st.markdown(
        '<div class="dev-badge">DEV · MOCK</div>',
        unsafe_allow_html=True,
    )
