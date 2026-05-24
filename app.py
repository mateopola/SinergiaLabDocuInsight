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
import os
from datetime import datetime
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st
from PIL import Image

from export import build_excel
from pipeline import get_pipeline
from schemas import (
    DOC_TYPE_LABELS,
    DocType,
    DocumentResult,
    humanize_entity_label,
)

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

LOGO_PATH = Path(__file__).parent / "assets" / "logo.png"

# URL publica de la landing (GitHub Pages, sirviendo desde docs/).
LANDING_URL = "https://mateopola.github.io/SinergiaLabDocuInsight/"

# Paleta exacta de la landing (docs/index.html)
PRIMARY = "#0C74C8"
PRIMARY_DARK = "#0858A0"
PRIMARY_LIGHT = "#E0F0FB"
ACCENT = "#FE6B23"
ACCENT_LIGHT = "#FFE4D6"
CREAM = "#FFF4F4"
DARK = "#41444B"
INK = "#0F172A"

DOC_TYPE_ICONS = {
    DocType.CEDULA: "🪪",
    DocType.CAMARA_COMERCIO: "🏢",
    DocType.RUT: "🧾",
    DocType.POLIZA: "🛡️",
    DocType.DESCONOCIDO: "❓",
}

DOC_TYPES_ORDER = [
    DocType.CEDULA,
    DocType.CAMARA_COMERCIO,
    DocType.RUT,
    DocType.POLIZA,
]


@st.cache_data
def _logo_b64() -> str:
    return base64.b64encode(LOGO_PATH.read_bytes()).decode("ascii")


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
        f'display:inline-block;min-width:48px;text-align:center;">{pct}</span>'
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


# ---------------------------------------------------------------------------
# CSS global (replica el sistema de diseno de docs/)
# ---------------------------------------------------------------------------

st.markdown(
    f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=Space+Grotesk:wght@500;600;700&display=swap');

:root {{
    --brand-blue: {PRIMARY};
    --brand-blue-dark: {PRIMARY_DARK};
    --brand-blue-light: {PRIMARY_LIGHT};
    --brand-orange: {ACCENT};
    --brand-orange-light: {ACCENT_LIGHT};
    --brand-cream: {CREAM};
    --brand-dark: {DARK};
    --brand-ink: {INK};
    --shadow-soft: 0 20px 40px -10px rgba(12,116,200,0.18);
    --shadow-medium: 0 8px 20px -8px rgba(12,116,200,0.35);
    --shadow-strong: 0 25px 50px -12px rgba(12,116,200,0.25);
}}

/* --- Esconder chrome de Streamlit --- */
[data-testid="stSidebar"], [data-testid="collapsedControl"],
[data-testid="stToolbar"], [data-testid="stDecoration"],
[data-testid="stHeader"], footer {{
    display: none !important;
}}

/* --- Fondo global: crema + mesh gradients --- */
.stApp {{
    background-color: {CREAM};
    background-image:
        radial-gradient(at 12% 18%, hsla(208, 88%, 60%, 0.18) 0px, transparent 50%),
        radial-gradient(at 87% 22%, hsla(19, 99%, 56%, 0.15) 0px, transparent 50%),
        radial-gradient(at 52% 91%, hsla(208, 88%, 60%, 0.10) 0px, transparent 50%),
        radial-gradient(at 92% 80%, hsla(19, 99%, 56%, 0.08) 0px, transparent 50%);
    background-attachment: fixed;
}}

/* --- Tipografia base --- */
html, body, [class*="css"], .stMarkdown, p, span, div {{
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    color: {DARK};
}}
h1, h2, h3, .display, .stMarkdown h1, .stMarkdown h2, .stMarkdown h3 {{
    font-family: 'Space Grotesk', sans-serif !important;
    color: {INK};
    letter-spacing: -0.02em;
}}

.block-container {{
    padding-top: 0 !important;
    padding-bottom: 5rem !important;
    max-width: 1400px !important;
}}

/* --- Top brand strip --- */
.brand-strip {{
    position: fixed; top: 0; left: 0; right: 0;
    height: 4px; z-index: 1000;
    background: linear-gradient(90deg, {PRIMARY} 0%, {ACCENT} 100%);
}}

/* --- Navbar --- */
.navbar {{
    position: sticky;
    top: 4px;
    z-index: 100;
    background: rgba(255, 244, 244, 0.85);
    backdrop-filter: blur(20px) saturate(180%);
    -webkit-backdrop-filter: blur(20px) saturate(180%);
    border-bottom: 1px solid rgba(15, 23, 42, 0.06);
    padding: 0.9rem 2rem;
    margin: 0 -3rem 1.25rem -3rem;
}}
.navbar-inner {{
    max-width: 1400px; margin: 0 auto;
    display: flex; align-items: center; justify-content: space-between;
    gap: 1rem;
}}
.navbar-brand {{
    display: flex; align-items: center; gap: 0.85rem;
    text-decoration: none !important;
}}
.navbar-brand:hover {{ transform: translateY(-1px); }}
.navbar-brand img {{
    width: 42px; height: 42px; border-radius: 10px;
    background: white; padding: 5px;
    box-shadow: 0 2px 8px rgba(15, 23, 42, 0.08);
    object-fit: contain;
}}
.navbar-brand .brand-name {{
    font-family: 'Space Grotesk', sans-serif;
    font-weight: 700; color: {INK};
    font-size: 0.98rem; line-height: 1.15;
}}
.navbar-brand .brand-sub {{
    color: {PRIMARY}; font-weight: 600; font-size: 0.68rem;
    text-transform: uppercase; letter-spacing: 0.14em; margin-top: 3px;
}}
.navbar-actions {{ display: flex; align-items: center; gap: 0.6rem; }}
.navbar-back {{
    color: {DARK}; text-decoration: none !important;
    font-size: 0.875rem; font-weight: 500;
    padding: 0.55rem 1.1rem; border-radius: 10px;
    transition: all 0.2s ease;
}}
.navbar-back:hover {{
    color: {PRIMARY}; background: rgba(12, 116, 200, 0.06);
}}
.navbar-status {{
    display: inline-flex; align-items: center; gap: 0.45rem;
    padding: 0.35rem 0.85rem; border-radius: 999px;
    background: rgba(220, 252, 231, 0.6);
    border: 1px solid rgba(22, 101, 52, 0.18);
    color: #166534; font-size: 0.72rem; font-weight: 700;
    text-transform: uppercase; letter-spacing: 0.1em;
}}
.navbar-status .dot {{
    width: 7px; height: 7px; border-radius: 50%; background: #10B981;
    animation: pulse-green 1.6s ease-in-out infinite;
}}
@keyframes pulse-green {{
    0%, 100% {{ box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.4); }}
    50% {{ box-shadow: 0 0 0 6px rgba(16, 185, 129, 0); }}
}}

/* --- App header (mini hero, no full screen) --- */
.app-header {{
    padding: 1rem 0 1.5rem 0;
    margin: 0 0 1.5rem 0;
    border-bottom: 1px solid rgba(15, 23, 42, 0.06);
    display: flex; justify-content: space-between; align-items: center;
    gap: 1rem; flex-wrap: wrap;
}}
.app-header .left {{ flex: 1; min-width: 280px; }}
.app-header h1 {{
    font-family: 'Space Grotesk', sans-serif !important;
    font-size: 1.85rem !important;
    font-weight: 700 !important;
    color: {INK} !important;
    margin: 0 0 0.35rem 0 !important;
    line-height: 1.1;
    letter-spacing: -0.02em;
}}
.app-header h1 .gradient-text {{
    background: linear-gradient(135deg, {PRIMARY} 0%, {ACCENT} 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
}}
.app-header p {{
    color: rgba(65, 68, 75, 0.7);
    font-size: 0.95rem; margin: 0;
}}
.app-header .accent-bar {{
    width: 56px; height: 4px;
    background: linear-gradient(90deg, {PRIMARY}, {ACCENT});
    border-radius: 2px; margin-bottom: 0.7rem;
}}

/* --- Tabs custom (look de app) --- */
.stTabs [data-baseweb="tab-list"] {{
    gap: 4px;
    background: rgba(255, 255, 255, 0.75);
    backdrop-filter: blur(20px) saturate(180%);
    -webkit-backdrop-filter: blur(20px) saturate(180%);
    border: 1px solid rgba(255, 255, 255, 0.6);
    border-radius: 14px;
    padding: 5px;
    margin-bottom: 1.5rem !important;
    box-shadow: var(--shadow-soft);
}}
.stTabs [data-baseweb="tab"] {{
    padding: 0.6rem 1.25rem !important;
    border-radius: 10px !important;
    font-family: 'Space Grotesk', sans-serif !important;
    font-weight: 600 !important;
    font-size: 0.93rem !important;
    color: rgba(65, 68, 75, 0.65) !important;
    background: transparent !important;
    border: none !important;
    transition: all 0.2s ease !important;
}}
.stTabs [data-baseweb="tab"]:hover {{
    color: {PRIMARY} !important;
    background: rgba(12, 116, 200, 0.04) !important;
}}
.stTabs [aria-selected="true"] {{
    background: linear-gradient(90deg, {PRIMARY} 0%, {ACCENT} 100%) !important;
    color: white !important;
    box-shadow: 0 4px 12px -4px rgba(12, 116, 200, 0.4) !important;
}}
.stTabs [data-baseweb="tab-highlight"] {{ display: none !important; }}
.stTabs [data-baseweb="tab-border"] {{ display: none !important; }}

/* --- Uploader card --- */
.upload-shell {{
    max-width: 760px;
    margin: 0.5rem auto 0 auto;
}}
.upload-card-header {{
    background: rgba(255, 255, 255, 0.75);
    backdrop-filter: blur(28px) saturate(180%);
    -webkit-backdrop-filter: blur(28px) saturate(180%);
    border: 1px solid rgba(255, 255, 255, 0.5);
    border-bottom: none;
    border-radius: 16px 16px 0 0;
    padding: 1.5rem 1.75rem 0.4rem 1.75rem;
}}
.upload-card-header h2 {{
    font-family: 'Space Grotesk', sans-serif !important;
    font-size: 1.15rem !important;
    font-weight: 700 !important;
    color: {INK} !important;
    margin: 0 0 0.3rem 0 !important;
}}
.upload-card-header p {{
    color: rgba(65, 68, 75, 0.6);
    font-size: 0.88rem; margin: 0;
}}

/* --- File uploader override --- */
[data-testid="stFileUploader"] {{
    max-width: 760px; margin: 0 auto;
}}
[data-testid="stFileUploader"] > div:first-child {{
    background: rgba(255, 255, 255, 0.75);
    backdrop-filter: blur(28px) saturate(180%);
    -webkit-backdrop-filter: blur(28px) saturate(180%);
    border: 1px solid rgba(255, 255, 255, 0.5);
    border-top: none;
    border-radius: 0 0 16px 16px;
    padding: 0.4rem 1.75rem 1.75rem 1.75rem;
    box-shadow: var(--shadow-strong);
}}
[data-testid="stFileUploader"] section {{
    background: rgba(12, 116, 200, 0.03) !important;
    border: 2px dashed rgba(12, 116, 200, 0.3) !important;
    border-radius: 12px !important;
    padding: 2rem 1rem !important;
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
    border-radius: 8px !important;
    font-weight: 600 !important;
}}
[data-testid="stFileUploader"] button:hover {{
    background: rgba(12, 116, 200, 0.05) !important;
    border-color: {PRIMARY} !important;
}}

.uploader-aux {{ max-width: 760px; margin: 0.85rem auto 0 auto; }}
.file-chip {{
    padding: 0.85rem 1.1rem;
    background: rgba(255, 255, 255, 0.7);
    backdrop-filter: blur(16px);
    border: 1px solid rgba(12, 116, 200, 0.12);
    border-radius: 12px;
    color: {DARK}; font-size: 0.92rem;
    display: flex; align-items: center; gap: 0.6rem;
}}
.file-chip .name {{ font-weight: 600; color: {INK}; }}
.file-chip .size {{ color: rgba(65, 68, 75, 0.6); }}

/* --- Botones --- */
.stButton > button[kind="primary"], .stDownloadButton > button {{
    background: linear-gradient(90deg, {PRIMARY} 0%, {ACCENT} 100%) !important;
    color: white !important;
    border: none !important;
    border-radius: 12px !important;
    padding: 0.75rem 1.4rem !important;
    font-family: 'Inter', sans-serif !important;
    font-weight: 600 !important;
    box-shadow: var(--shadow-medium) !important;
    transition: all 0.2s ease !important;
}}
.stButton > button[kind="primary"]:hover, .stDownloadButton > button:hover {{
    transform: translateY(-1px) !important;
    box-shadow: var(--shadow-strong) !important;
    color: white !important;
}}
.stButton > button[kind="secondary"] {{
    background: white !important;
    color: {PRIMARY} !important;
    border: 1.5px solid rgba(12, 116, 200, 0.22) !important;
    border-radius: 12px !important;
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
    border: 1.5px solid rgba(12, 116, 200, 0.22) !important;
    border-radius: 12px !important;
    padding: 0.6rem 1.2rem !important;
    font-weight: 600 !important;
}}
[data-testid="stPopoverButton"]:hover {{
    border-color: {PRIMARY} !important;
    background: rgba(12, 116, 200, 0.05) !important;
}}

/* --- Result section --- */
.result-shell {{
    max-width: 1080px; margin: 2.5rem auto 0 auto; padding: 0 0.5rem;
}}
.result-hero {{
    background: rgba(255, 255, 255, 0.85);
    backdrop-filter: blur(20px) saturate(180%);
    -webkit-backdrop-filter: blur(20px) saturate(180%);
    border: 1px solid rgba(255, 255, 255, 0.6);
    border-left: 5px solid {PRIMARY};
    border-radius: 16px;
    padding: 1.65rem 1.85rem;
    margin-bottom: 1.5rem;
    box-shadow: var(--shadow-soft);
    display: flex; align-items: center; gap: 1.5rem; flex-wrap: wrap;
}}
.result-hero .r-icon {{ font-size: 3.25rem; line-height: 1; flex-shrink: 0; }}
.result-hero .r-body {{ flex: 1; min-width: 240px; }}
.result-hero .r-label {{
    color: rgba(65, 68, 75, 0.6); font-size: 0.7rem;
    text-transform: uppercase; letter-spacing: 0.1em;
    margin-bottom: 0.35rem; font-weight: 700;
}}
.result-hero .r-doctype {{
    font-family: 'Space Grotesk', sans-serif;
    color: {INK}; font-size: 1.6rem; font-weight: 700;
    line-height: 1.1; margin-bottom: 0.4rem;
}}
.result-hero .r-filename {{
    color: rgba(65, 68, 75, 0.6); font-size: 0.85rem; word-break: break-all;
}}
.result-hero .r-conf {{ text-align: right; flex-shrink: 0; }}
.result-hero .r-conf-pill {{
    padding: 9px 16px; border-radius: 12px;
    font-weight: 700; font-size: 1.2rem;
    display: inline-block;
    font-family: 'Space Grotesk', sans-serif;
}}
.result-hero .r-conf-label {{
    color: rgba(65, 68, 75, 0.5); font-size: 0.68rem;
    text-transform: uppercase; letter-spacing: 0.08em;
    margin-top: 0.35rem; font-weight: 600;
}}

/* --- Metric cards --- */
.metric-card {{
    background: rgba(255, 255, 255, 0.7);
    backdrop-filter: blur(16px);
    -webkit-backdrop-filter: blur(16px);
    border: 1px solid rgba(255, 255, 255, 0.6);
    border-left: 4px solid {PRIMARY};
    border-radius: 16px;
    padding: 1.2rem 1.4rem;
    box-shadow: var(--shadow-soft);
    transition: all 0.25s ease;
    height: 100%;
}}
.metric-card:hover {{
    transform: translateY(-3px);
    box-shadow: var(--shadow-strong);
}}
.metric-card.accent {{ border-left-color: {ACCENT}; }}
.metric-card.neutral {{ border-left-color: rgba(15, 23, 42, 0.25); }}
.metric-card .m-label {{
    color: rgba(65, 68, 75, 0.6); font-size: 0.7rem;
    text-transform: uppercase; letter-spacing: 0.08em;
    margin-bottom: 0.55rem; font-weight: 600;
    display: flex; align-items: center; gap: 0.4rem;
}}
.metric-card .m-value {{
    font-family: 'Space Grotesk', sans-serif;
    color: {INK}; font-size: 1.9rem; font-weight: 700; line-height: 1;
}}
.metric-card .m-sub {{
    color: rgba(65, 68, 75, 0.55); font-size: 0.76rem; margin-top: 0.35rem;
}}

/* --- Chart card --- */
.chart-card {{
    background: rgba(255, 255, 255, 0.7);
    backdrop-filter: blur(16px);
    -webkit-backdrop-filter: blur(16px);
    border: 1px solid rgba(255, 255, 255, 0.6);
    border-radius: 16px;
    padding: 1.25rem 1.5rem;
    box-shadow: var(--shadow-soft);
    margin-bottom: 1rem;
}}
.chart-title {{
    font-family: 'Space Grotesk', sans-serif;
    color: {INK}; font-size: 1.05rem; font-weight: 700;
    margin: 0 0 0.5rem 0;
}}

/* --- Section titles --- */
.section-title {{
    font-family: 'Space Grotesk', sans-serif;
    color: {INK}; font-size: 1.15rem; font-weight: 700;
    margin: 1.75rem 0 1rem 0;
    display: flex; align-items: center; gap: 0.55rem;
}}

/* --- Entities table --- */
.entities-table {{
    width: 100%; border-collapse: collapse;
    background: rgba(255, 255, 255, 0.75);
    backdrop-filter: blur(16px);
    -webkit-backdrop-filter: blur(16px);
    border: 1px solid rgba(255, 255, 255, 0.6);
    border-radius: 14px; overflow: hidden;
    box-shadow: var(--shadow-soft);
}}
.entities-table thead {{ background: rgba(255, 244, 244, 0.85); }}
.entities-table th {{
    padding: 12px 16px; text-align: left;
    color: {INK}; font-family: 'Space Grotesk', sans-serif;
    font-size: 0.7rem; text-transform: uppercase;
    letter-spacing: 0.09em; font-weight: 700;
}}
.entities-table th.center {{ text-align: center; width: 110px; }}
.entities-table td {{
    padding: 12px 16px;
    border-bottom: 1px solid rgba(229, 231, 235, 0.5);
    font-size: 0.92rem;
}}
.entities-table tr:last-child td {{ border-bottom: none; }}
.entities-table td.label-col {{
    color: rgba(65, 68, 75, 0.7); font-size: 0.85em;
}}
.entities-table td.value-col {{
    font-weight: 500; color: {INK}; word-break: break-word;
}}
.entities-table td.conf-col {{ text-align: center; }}
.entities-table tr:hover td {{ background: rgba(255, 244, 244, 0.4); }}

/* --- Cases (history) rows --- */
.case-row {{
    background: rgba(255, 255, 255, 0.7);
    backdrop-filter: blur(16px);
    border: 1px solid rgba(255, 255, 255, 0.6);
    border-radius: 12px;
    padding: 0.9rem 1.1rem;
    margin-bottom: 0.6rem;
    display: flex; align-items: center; gap: 1rem;
    transition: all 0.2s ease;
}}
.case-row:hover {{
    transform: translateY(-1px);
    box-shadow: var(--shadow-soft);
}}
.case-row .c-icon {{ font-size: 1.5rem; line-height: 1; }}
.case-row .c-body {{ flex: 1; min-width: 0; }}
.case-row .c-name {{
    color: {INK}; font-weight: 600; font-size: 0.9rem;
    word-break: break-all; line-height: 1.2;
}}
.case-row .c-meta {{
    color: rgba(65, 68, 75, 0.6); font-size: 0.78rem;
    margin-top: 0.2rem;
}}
.case-row .c-entities {{
    color: {PRIMARY}; font-weight: 700; font-size: 0.95rem;
    font-family: 'Space Grotesk', sans-serif;
}}
.case-row .c-entities .label {{
    color: rgba(65, 68, 75, 0.5); font-size: 0.7rem;
    font-weight: 600; text-transform: uppercase;
    letter-spacing: 0.07em; display: block; margin-bottom: 0.1rem;
}}

/* --- Empty states --- */
.empty-state {{
    text-align: center; padding: 4rem 2rem;
    background: rgba(255, 255, 255, 0.5);
    backdrop-filter: blur(16px);
    border: 1px dashed rgba(12, 116, 200, 0.2);
    border-radius: 16px;
    margin: 1rem 0;
}}
.empty-state .e-icon {{
    font-size: 3rem; opacity: 0.4; margin-bottom: 0.5rem;
}}
.empty-state h3 {{
    color: {INK} !important;
    font-size: 1.15rem !important;
    margin: 0 0 0.4rem 0 !important;
    font-weight: 700 !important;
}}
.empty-state p {{
    color: rgba(65, 68, 75, 0.6); font-size: 0.92rem;
    margin: 0; max-width: 440px; margin: 0 auto;
}}

/* --- Error state --- */
.result-error {{
    max-width: 720px; margin: 1.5rem auto 0 auto;
    background: rgba(255, 255, 255, 0.85);
    border: 1px solid #FECACA;
    border-left: 5px solid #DC2626;
    border-radius: 16px;
    padding: 1.5rem 1.75rem;
    box-shadow: var(--shadow-soft);
}}
.result-error h3 {{
    color: #991B1B !important;
    font-family: 'Space Grotesk', sans-serif;
    margin: 0 0 0.5rem 0 !important;
}}
.result-error p {{ color: rgba(65, 68, 75, 0.8); margin: 0; }}

/* --- Progress bar --- */
[data-testid="stProgress"] > div > div > div > div {{
    background: linear-gradient(90deg, {PRIMARY}, {ACCENT}) !important;
}}
[data-testid="stStatusWidget"], [data-testid="stStatus"] {{
    background: rgba(255, 255, 255, 0.7) !important;
    border: 1px solid rgba(12, 116, 200, 0.12) !important;
    border-radius: 12px !important;
}}

/* --- Dev badge --- */
.dev-badge {{
    position: fixed; bottom: 1rem; right: 1rem; z-index: 1000;
    background: {INK}; color: white;
    padding: 5px 12px; border-radius: 8px;
    font-size: 0.7rem; font-weight: 700;
    letter-spacing: 0.08em; opacity: 0.75;
    text-transform: uppercase;
    font-family: 'Space Grotesk', sans-serif;
}}

/* --- Responsive --- */
@media (max-width: 768px) {{
    .navbar {{ padding: 0.7rem 1rem; margin: 0 -1rem 1rem -1rem; }}
    .navbar-brand img {{ width: 36px; height: 36px; }}
    .navbar-back {{ font-size: 0.78rem; padding: 0.45rem 0.8rem; }}
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

st.markdown(
    f"""
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
            <div class="navbar-actions">
                <span class="navbar-status">
                    <span class="dot"></span>
                    {n_processed} {"documento" if n_processed == 1 else "documentos"} en sesión
                </span>
                <a class="navbar-back" href="{LANDING_URL}" target="_self">← Volver al sitio</a>
            </div>
        </div>
    </nav>
    """,
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------------
# App header
# ---------------------------------------------------------------------------

st.markdown(
    """
    <div class="app-header">
        <div class="left">
            <div class="accent-bar"></div>
            <h1>Centro de <span class="gradient-text">inteligencia documental</span></h1>
            <p>Clasificación automática, extracción de entidades y trazabilidad de cada documento procesado en la sesión.</p>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)


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
        '<th>Entidad</th><th>Valor</th><th class="center">Confianza</th>'
        '</tr></thead>'
        f'<tbody>{rows}</tbody>'
        '</table>'
    )


def _render_result(result: DocumentResult) -> None:
    if result.error:
        st.markdown(
            f"""
            <div class="result-error">
                <h3>❌ No se pudo procesar el documento</h3>
                <p><strong>Archivo:</strong> {result.filename}</p>
                <p style="margin-top:0.5rem;"><strong>Error:</strong> {result.error}</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    icon = DOC_TYPE_ICONS.get(result.doc_type, "📄")
    conf = result.doc_type_confidence
    conf_bg, conf_fg = _conf_colors(conf)

    st.markdown(
        f"""
        <div class="result-shell">
            <div class="result-hero">
                <div class="r-icon">{icon}</div>
                <div class="r-body">
                    <div class="r-label">Tipo documental detectado</div>
                    <div class="r-doctype">{DOC_TYPE_LABELS[result.doc_type]}</div>
                    <div class="r-filename">📄 {result.filename}</div>
                </div>
                <div class="r-conf">
                    <div class="r-conf-pill" style="background:{conf_bg};color:{conf_fg};">
                        {conf:.0%}
                    </div>
                    <div class="r-conf-label">Confianza</div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    high_conf = sum(1 for e in result.entities if e.confidence >= 0.85)
    c1, c2, c3 = st.columns(3)
    c1.markdown(
        f'<div class="metric-card">'
        f'<div class="m-label">🏷️ Entidades extraídas</div>'
        f'<div class="m-value">{len(result.entities)}</div>'
        f'<div class="m-sub">campos identificados</div></div>',
        unsafe_allow_html=True,
    )
    c2.markdown(
        f'<div class="metric-card">'
        f'<div class="m-label">⏱️ Tiempo</div>'
        f'<div class="m-value">{result.processing_time_ms} ms</div>'
        f'<div class="m-sub">OCR + clasificación + NER</div></div>',
        unsafe_allow_html=True,
    )
    c3.markdown(
        f'<div class="metric-card accent">'
        f'<div class="m-label">✅ Alta confianza</div>'
        f'<div class="m-value">{high_conf}</div>'
        f'<div class="m-sub">de {len(result.entities)} entidades</div></div>',
        unsafe_allow_html=True,
    )

    st.markdown(
        '<div class="section-title">📋 Entidades extraídas</div>',
        unsafe_allow_html=True,
    )

    if result.entities:
        st.markdown(_entities_table_html(result), unsafe_allow_html=True)
    else:
        st.info("ℹ️ No se extrajeron entidades de este documento.")

    st.markdown('<div style="height:1.5rem;"></div>', unsafe_allow_html=True)
    col_ocr, col_dl = st.columns([1.5, 1])
    with col_ocr:
        with st.popover("📝 Ver texto extraído (OCR)", use_container_width=True):
            st.text(result.extracted_text or "(sin texto)")
    with col_dl:
        st.download_button(
            "📥 Descargar Excel",
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
# Tabs
# ---------------------------------------------------------------------------

tab_dashboard, tab_process, tab_cases = st.tabs([
    "📊 Dashboard",
    "🚀 Procesar",
    "📁 Casos",
])


# ============================================================================
# TAB: DASHBOARD
# ============================================================================

with tab_dashboard:
    history = st.session_state.history
    ok = [r for r in history if not r.error]
    n_total = len(history)
    n_ok = len(ok)
    n_err = n_total - n_ok

    # Métricas top
    avg_time = (sum(r.processing_time_ms for r in ok) / n_ok) if n_ok else 0
    avg_conf = (sum(r.doc_type_confidence for r in ok) / n_ok) if n_ok else 0
    total_entities = sum(len(r.entities) for r in ok)

    c1, c2, c3, c4 = st.columns(4)
    c1.markdown(
        f'<div class="metric-card">'
        f'<div class="m-label">📄 Documentos procesados</div>'
        f'<div class="m-value">{n_total}</div>'
        f'<div class="m-sub">{n_ok} ok · {n_err} con error</div></div>',
        unsafe_allow_html=True,
    )
    c2.markdown(
        f'<div class="metric-card accent">'
        f'<div class="m-label">🏷️ Entidades extraídas</div>'
        f'<div class="m-value">{total_entities}</div>'
        f'<div class="m-sub">total acumulado</div></div>',
        unsafe_allow_html=True,
    )
    c3.markdown(
        f'<div class="metric-card">'
        f'<div class="m-label">⏱️ Tiempo promedio</div>'
        f'<div class="m-value">{int(avg_time)} ms</div>'
        f'<div class="m-sub">por documento</div></div>',
        unsafe_allow_html=True,
    )
    c4.markdown(
        f'<div class="metric-card neutral">'
        f'<div class="m-label">🎯 Confianza promedio</div>'
        f'<div class="m-value">{avg_conf:.0%}</div>'
        f'<div class="m-sub">clasificación</div></div>',
        unsafe_allow_html=True,
    )

    if not history:
        st.markdown(
            """
            <div class="empty-state" style="margin-top:2rem;">
                <div class="e-icon">📊</div>
                <h3>El dashboard se va a llenar a medida que proceses documentos</h3>
                <p>Andá a la pestaña <strong>🚀 Procesar</strong> para cargar el primero.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
    elif ok:
        st.markdown('<div style="height:1rem;"></div>', unsafe_allow_html=True)
        col_pie, col_hist = st.columns([1, 1])

        # Pie chart: distribución por tipo
        with col_pie:
            dist = {DOC_TYPE_LABELS[dt]: sum(1 for r in ok if r.doc_type == dt)
                    for dt in DOC_TYPES_ORDER}
            dist = {k: v for k, v in dist.items() if v > 0}
            if dist:
                fig = px.pie(
                    names=list(dist.keys()),
                    values=list(dist.values()),
                    color_discrete_sequence=[PRIMARY, ACCENT, PRIMARY_DARK, "#82A5C9"],
                    hole=0.55,
                )
                fig.update_traces(
                    textposition="outside",
                    textinfo="label+percent",
                    marker=dict(line=dict(color="white", width=2)),
                )
                fig.update_layout(
                    height=320,
                    margin=dict(t=20, b=20, l=20, r=20),
                    showlegend=False,
                    font=dict(family="Inter, sans-serif", color=DARK, size=12),
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(0,0,0,0)",
                )
                st.markdown('<div class="chart-card">'
                            '<div class="chart-title">Distribución por tipo documental</div>',
                            unsafe_allow_html=True)
                st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
                st.markdown('</div>', unsafe_allow_html=True)

        # Histograma de confianza
        with col_hist:
            confs = [r.doc_type_confidence for r in ok]
            fig2 = px.histogram(
                x=confs, nbins=10, range_x=[0, 1],
                color_discrete_sequence=[PRIMARY],
            )
            fig2.update_traces(marker_line_color="white", marker_line_width=1)
            fig2.update_layout(
                height=320,
                margin=dict(t=20, b=40, l=40, r=20),
                xaxis_title="Confianza",
                yaxis_title="Documentos",
                bargap=0.08,
                font=dict(family="Inter, sans-serif", color=DARK, size=12),
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                xaxis=dict(tickformat=".0%", showgrid=False),
                yaxis=dict(gridcolor="rgba(15,23,42,0.06)"),
            )
            st.markdown('<div class="chart-card">'
                        '<div class="chart-title">Confianza de clasificación</div>',
                        unsafe_allow_html=True)
            st.plotly_chart(fig2, use_container_width=True, config={"displayModeBar": False})
            st.markdown('</div>', unsafe_allow_html=True)

        # Tipos soportados con conteo
        st.markdown(
            '<div class="section-title">🗂️ Tipos documentales en esta sesión</div>',
            unsafe_allow_html=True,
        )
        type_cols = st.columns(4)
        for col, dt in zip(type_cols, DOC_TYPES_ORDER):
            count = sum(1 for r in ok if r.doc_type == dt)
            pct = (count / n_ok * 100) if n_ok else 0
            accent_cls = " accent" if count > 0 else " neutral"
            col.markdown(
                f'<div class="metric-card{accent_cls}">'
                f'<div class="m-label">{DOC_TYPE_ICONS[dt]} {DOC_TYPE_LABELS[dt]}</div>'
                f'<div class="m-value">{count}</div>'
                f'<div class="m-sub">{pct:.0f}% de la sesión</div></div>',
                unsafe_allow_html=True,
            )


# ============================================================================
# TAB: PROCESAR
# ============================================================================

with tab_process:
    st.markdown(
        """
        <div class="upload-shell">
            <div class="upload-card-header">
                <h2>Subí tu documento</h2>
                <p>Formatos aceptados: PDF, PNG, JPG · Procesamiento instantáneo</p>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    uploaded = st.file_uploader(
        "Arrastrá el archivo o hacé clic para seleccionar",
        type=["pdf", "png", "jpg", "jpeg"],
        accept_multiple_files=False,
        label_visibility="collapsed",
        key="single_uploader",
    )

    if uploaded:
        st.markdown(
            f"""
            <div class="uploader-aux">
                <div class="file-chip">
                    📄 <span class="name">{uploaded.name}</span>
                    <span class="size">· {uploaded.size / 1024:.1f} KB</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        _, btn_col, _ = st.columns([1, 2, 1])
        with btn_col:
            process = st.button(
                "🚀 Procesar documento",
                type="primary",
                use_container_width=True,
                key="process_btn",
            )

        if process:
            pipeline = get_pipeline(use_mock=use_mock)
            with st.status("Procesando documento...", expanded=True) as status:
                st.write("📄 Extrayendo texto del documento (OCR)...")
                try:
                    file_bytes = uploaded.getvalue()
                    result = pipeline.process(file_bytes, uploaded.name)
                    if result.error:
                        status.update(label=f"✗ {result.error}", state="error")
                    else:
                        st.write(
                            f"🏷️ Clasificado como **{DOC_TYPE_LABELS[result.doc_type]}** "
                            f"({result.doc_type_confidence:.0%} confianza)"
                        )
                        st.write(f"🔎 {len(result.entities)} entidades extraídas")
                        status.update(label="✓ Procesamiento completo", state="complete")
                except Exception as e:
                    result = DocumentResult(
                        filename=uploaded.name,
                        doc_type=DocType.DESCONOCIDO,
                        doc_type_confidence=0.0,
                        extracted_text="",
                        error=f"Error en pipeline: {type(e).__name__}: {e}",
                    )
                    status.update(label=f"✗ Error: {e}", state="error")

            st.session_state.last_result = result
            st.session_state.history.append(result)

    # Resultado del último procesamiento (si existe)
    if st.session_state.last_result is not None:
        _render_result(st.session_state.last_result)
    elif not uploaded:
        st.markdown(
            """
            <div class="empty-state" style="margin-top:1.5rem;">
                <div class="e-icon">📥</div>
                <h3>Sin documentos procesados aún</h3>
                <p>Soltá un archivo arriba y vas a ver acá el tipo detectado y las entidades extraídas.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )


# ============================================================================
# TAB: CASOS (historial)
# ============================================================================

with tab_cases:
    history = st.session_state.history

    if not history:
        st.markdown(
            """
            <div class="empty-state">
                <div class="e-icon">📁</div>
                <h3>No hay casos procesados todavía</h3>
                <p>Cada documento que proceses queda guardado acá durante la sesión. Andá a <strong>🚀 Procesar</strong> para empezar.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        # Acciones de la sesión
        col_filter, col_dl, col_clear = st.columns([2, 1, 1])
        with col_filter:
            options = ["Todos"] + [DOC_TYPE_LABELS[dt] for dt in DOC_TYPES_ORDER]
            errors_exist = any(r.error for r in history)
            if errors_exist:
                options.append("Solo errores")
            filter_choice = st.selectbox(
                "Filtrar", options=options, index=0, label_visibility="collapsed"
            )
        with col_dl:
            ok_history = [r for r in history if not r.error]
            st.download_button(
                "📥 Exportar Excel",
                data=build_excel(ok_history) if ok_history else b"",
                file_name=f"docuinsight_sesion_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
                disabled=not ok_history,
                key="dl_session",
            )
        with col_clear:
            if st.button("🗑️ Limpiar sesión", type="secondary",
                         use_container_width=True, key="clear_session"):
                st.session_state.history = []
                st.session_state.last_result = None
                st.rerun()

        # Filtro
        if filter_choice == "Todos":
            filtered = history
        elif filter_choice == "Solo errores":
            filtered = [r for r in history if r.error]
        else:
            filtered = [r for r in history if DOC_TYPE_LABELS.get(r.doc_type) == filter_choice]

        st.caption(f"Mostrando {len(filtered)} de {len(history)} casos")

        # Lista de casos
        for idx, result in enumerate(filtered):
            if result.error:
                icon = "❌"
                meta = f"Error · {result.error[:60]}..."
            else:
                icon = DOC_TYPE_ICONS.get(result.doc_type, "📄")
                meta = (
                    f"{DOC_TYPE_LABELS[result.doc_type]} · "
                    f"{result.doc_type_confidence:.0%} conf. · "
                    f"{result.processing_time_ms} ms"
                )

            header = f"{icon}  **{result.filename}**  ·  {meta}"
            with st.expander(header, expanded=False):
                if result.error:
                    st.error(f"**Error:** {result.error}")
                else:
                    # Mini-card con tipo + confianza
                    conf_bg, conf_fg = _conf_colors(result.doc_type_confidence)
                    st.markdown(
                        f"""
                        <div style="display:flex;gap:1rem;align-items:center;
                                    padding:0.75rem 1rem;background:rgba(255,255,255,0.6);
                                    border-radius:10px;margin-bottom:1rem;">
                            <span style="font-size:1.75rem;">{icon}</span>
                            <div style="flex:1;">
                                <div style="font-family:'Space Grotesk',sans-serif;
                                            font-weight:700;color:{INK};font-size:1.05rem;">
                                    {DOC_TYPE_LABELS[result.doc_type]}
                                </div>
                                <div style="color:rgba(65,68,75,0.6);font-size:0.8rem;margin-top:0.15rem;">
                                    {len(result.entities)} entidades · {result.processing_time_ms} ms
                                </div>
                            </div>
                            <div style="background:{conf_bg};color:{conf_fg};
                                        padding:6px 14px;border-radius:10px;
                                        font-weight:700;font-size:0.95rem;
                                        font-family:'Space Grotesk',sans-serif;">
                                {result.doc_type_confidence:.0%}
                            </div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
                    if result.entities:
                        st.markdown(_entities_table_html(result), unsafe_allow_html=True)
                    else:
                        st.info("No se extrajeron entidades de este documento.")

                    st.markdown('<div style="height:0.75rem;"></div>', unsafe_allow_html=True)
                    col_ocr2, col_dl2 = st.columns([1.5, 1])
                    with col_ocr2:
                        with st.popover("📝 Ver texto extraído (OCR)",
                                        use_container_width=True):
                            st.text(result.extracted_text or "(sin texto)")
                    with col_dl2:
                        st.download_button(
                            "📥 Excel",
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
        '<div class="dev-badge">⚙ DEV · MOCK MODE</div>',
        unsafe_allow_html=True,
    )
