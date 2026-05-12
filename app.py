"""
DocuInsight — Aplicación Streamlit.
SinergIA Lab · MVP de clasificación documental + extracción de entidades.

Correr con:
    streamlit run app.py
"""

from __future__ import annotations

import base64
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st
from PIL import Image

LOGO_PATH = Path(__file__).parent / "assets" / "logo.png"

from export import build_excel
from pipeline import get_pipeline
from schemas import (
    DOC_TYPE_LABELS,
    DocType,
    DocumentResult,
    humanize_entity_label,
)


@st.cache_data
def _logo_b64() -> str:
    """Devuelve el logo en base64 para embeberlo en HTML inline."""
    return base64.b64encode(LOGO_PATH.read_bytes()).decode("ascii")


DOC_TYPE_ICONS = {
    DocType.CEDULA: "🪪",
    DocType.CAMARA_COMERCIO: "🏢",
    DocType.RUT: "🧾",
    DocType.POLIZA: "🛡️",
    DocType.DESCONOCIDO: "❓",
}

DOC_TYPE_DESCRIPTIONS = {
    DocType.CEDULA: "Identificación personal: nombres, apellidos, número, fechas.",
    DocType.CAMARA_COMERCIO: "Información societaria: razón social, NIT, representante.",
    DocType.RUT: "Registro tributario: NIT, CIIU, responsabilidades.",
    DocType.POLIZA: "Pólizas de seguros: aseguradora, tomador, vigencias, prima.",
}


def _confidence_badge(value: float) -> str:
    """Devuelve un badge HTML coloreado segun el umbral de confianza."""
    pct = f"{value:.0%}"
    if value >= 0.85:
        bg, fg = "#DCFCE7", "#166534"   # verde
    elif value >= 0.60:
        bg, fg = "#FEF3C7", "#92400E"   # naranja-ambar
    else:
        bg, fg = "#FEE2E2", "#991B1B"   # rojo
    return (
        f'<span style="background:{bg};color:{fg};padding:2px 10px;'
        f'border-radius:10px;font-weight:600;font-size:0.85em;'
        f'display:inline-block;min-width:48px;text-align:center;">{pct}</span>'
    )


# ============================================================================
# CONFIGURACIÓN GENERAL
# ============================================================================

st.set_page_config(
    page_title="DocuInsight · SinergIA Lab",
    page_icon=Image.open(LOGO_PATH),
    layout="wide",
    initial_sidebar_state="expanded",
)

# Paleta exacta extraida del logo SinergIA Lab
PRIMARY = "#0C74C8"        # azul de las figuras
PRIMARY_DARK = "#0858A0"   # azul mas oscuro para profundidad
ACCENT = "#FE6B23"         # naranja de la figura derecha y "IA"
DARK_TEXT = "#41444B"      # gris del wordmark "Sinerg" y "LAB"
LIGHT_BG = "#FFF4F4"       # crema del fondo del logo

# CSS personalizado
st.markdown(
    f"""
    <style>
        /* Reducir padding superior para que header y sidebar-brand arranquen al tope */
        [data-testid="stHeader"] {{
            background: transparent;
            height: 0;
        }}
        .block-container {{
            padding-top: 1.5rem !important;
            padding-bottom: 3rem !important;
        }}
        section[data-testid="stSidebar"] > div:first-child {{
            padding-top: 0 !important;
        }}
        section[data-testid="stSidebar"] {{
            background-color: {LIGHT_BG};
        }}

        /* Bloque de marca en el tope del sidebar */
        .sidebar-brand {{
            background: linear-gradient(135deg, {PRIMARY} 0%, {PRIMARY_DARK} 100%);
            margin: 0 -1rem 1.25rem -1rem;
            padding: 2.25rem 1rem 1.25rem 1rem;
            text-align: center;
            box-shadow: 0 4px 14px rgba(12, 116, 200, 0.18);
        }}
        .sidebar-brand img {{
            height: 68px;
            width: 68px;
            background: white;
            padding: 6px;
            border-radius: 0.6rem;
            display: block;
            margin: 0 auto 0.65rem auto;
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.18);
        }}
        .sidebar-brand .brand-name {{
            color: white;
            font-weight: 700;
            font-size: 1.1rem;
            letter-spacing: 0.02em;
            margin: 0;
        }}
        .sidebar-brand .brand-sub {{
            color: rgba(255, 255, 255, 0.85);
            font-size: 0.7rem;
            text-transform: uppercase;
            letter-spacing: 0.2em;
            margin: 0.3rem 0 0 0;
        }}

        /* Header principal — sin logo (ya está en sidebar), alineado con sidebar-brand */
        .main-header {{
            background: linear-gradient(135deg, {PRIMARY} 0%, {PRIMARY_DARK} 100%);
            color: white;
            padding: 2rem 2rem 1.5rem 2rem;
            border-radius: 0.6rem;
            margin: 0 0 1.5rem 0;
            box-shadow: 0 4px 14px rgba(12, 116, 200, 0.18);
        }}
        .main-header h1 {{
            color: white !important;
            margin: 0;
            font-weight: 700;
            font-size: 1.9rem;
            line-height: 1.1;
        }}
        .main-header p {{
            color: rgba(255, 255, 255, 0.92);
            margin: 0.4rem 0 0 0;
            font-size: 1rem;
        }}

        .stButton > button[kind="primary"] {{
            background-color: {PRIMARY};
            color: white;
            border: none;
            font-weight: 500;
        }}
        .stButton > button[kind="primary"]:hover {{
            background-color: {ACCENT};
            color: white;
            border: none;
        }}
        .stTabs [data-baseweb="tab-list"] button[aria-selected="true"] {{
            color: {PRIMARY};
            font-weight: 600;
        }}
        .doctype-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 1rem;
            margin: 1.5rem 0;
        }}
        .doctype-card {{
            background: white;
            border: 1px solid #E5E7EB;
            border-left: 4px solid {PRIMARY};
            border-radius: 0.5rem;
            padding: 1rem 1.25rem;
            transition: transform 0.15s ease, box-shadow 0.15s ease;
        }}
        .doctype-card:hover {{
            transform: translateY(-2px);
            box-shadow: 0 6px 16px rgba(12, 116, 200, 0.12);
        }}
        .doctype-card .icon {{
            font-size: 1.75rem;
            margin-bottom: 0.4rem;
        }}
        .doctype-card .title {{
            color: {PRIMARY};
            font-weight: 600;
            font-size: 1rem;
            margin: 0 0 0.25rem 0;
        }}
        .doctype-card .desc {{
            color: #6B7280;
            font-size: 0.85rem;
            margin: 0;
            line-height: 1.4;
        }}
        .metric-card {{
            background: white;
            border: 1px solid #E5E7EB;
            border-left: 4px solid {PRIMARY};
            border-radius: 0.5rem;
            padding: 1rem 1.25rem;
            height: 100%;
        }}
        .metric-card .metric-label {{
            color: #6B7280;
            font-size: 0.8rem;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            margin-bottom: 0.3rem;
            display: flex;
            align-items: center;
            gap: 0.4rem;
        }}
        .metric-card .metric-value {{
            color: {DARK_TEXT};
            font-size: 2rem;
            font-weight: 700;
            line-height: 1;
        }}
        .metric-card .metric-sub {{
            color: #9CA3AF;
            font-size: 0.75rem;
            margin-top: 0.25rem;
        }}
        .metric-card.accent {{
            border-left-color: {ACCENT};
        }}
        .empty-state {{
            text-align: center;
            padding: 2rem 1rem;
            color: #6B7280;
        }}
        .empty-state .big-icon {{
            font-size: 3rem;
            opacity: 0.4;
            margin-bottom: 0.5rem;
        }}
    </style>
    """,
    unsafe_allow_html=True,
)


# ============================================================================
# ESTADO DE SESIÓN
# ============================================================================

if "results" not in st.session_state:
    st.session_state.results: list[DocumentResult] = []
if "processed_at" not in st.session_state:
    st.session_state.processed_at = None


# ============================================================================
# SIDEBAR
# ============================================================================

with st.sidebar:
    st.markdown(
        f"""
        <div class="sidebar-brand">
            <img src="data:image/png;base64,{_logo_b64()}" alt="SinergIA Lab"/>
            <div class="brand-name">SinergIA Lab</div>
            <div class="brand-sub">DocuInsight v0.1</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("### ⚙️ Configuración")
    use_mock = st.toggle(
        "Usar modelos mock",
        value=True,
        help=(
            "Activado: usa el pipeline simulado para desarrollo de UI. "
            "Desactivar cuando el pipeline real esté integrado."
        ),
    )

    st.divider()

    st.markdown("### 📋 Tipos documentales")
    for dt in [DocType.CEDULA, DocType.CAMARA_COMERCIO, DocType.RUT, DocType.POLIZA]:
        st.markdown(f"- {DOC_TYPE_LABELS[dt]}")

    st.divider()

    if st.session_state.results:
        if st.button("🗑️ Limpiar resultados", use_container_width=True):
            st.session_state.results = []
            st.session_state.processed_at = None
            st.rerun()


# ============================================================================
# HEADER
# ============================================================================

st.markdown(
    """
    <div class="main-header">
        <h1>DocuInsight</h1>
        <p>Clasificación inteligente y extracción de entidades documentales</p>
    </div>
    """,
    unsafe_allow_html=True,
)


# ============================================================================
# TABS
# ============================================================================

tab_upload, tab_results = st.tabs(["📥 Cargar y procesar", "📊 Resultados"])


# ---------------------------------------------------------------------------
# TAB: CARGAR Y PROCESAR
# ---------------------------------------------------------------------------

with tab_upload:
    st.subheader("Cargar lote de documentos")
    st.markdown(
        "Selecciona uno o varios documentos en formato **PDF, PNG o JPG**. "
        "DocuInsight detecta automáticamente el tipo documental y extrae las entidades clave."
    )

    uploaded = st.file_uploader(
        "Arrastra los archivos aquí o haz clic para seleccionar",
        type=["pdf", "png", "jpg", "jpeg"],
        accept_multiple_files=True,
        label_visibility="collapsed",
    )

    if not uploaded:
        st.markdown("##### Tipos documentales soportados")
        cards_html = '<div class="doctype-grid">'
        for dt in [DocType.CEDULA, DocType.CAMARA_COMERCIO, DocType.RUT, DocType.POLIZA]:
            cards_html += (
                f'<div class="doctype-card">'
                f'<div class="icon">{DOC_TYPE_ICONS[dt]}</div>'
                f'<p class="title">{DOC_TYPE_LABELS[dt]}</p>'
                f'<p class="desc">{DOC_TYPE_DESCRIPTIONS[dt]}</p>'
                f'</div>'
            )
        cards_html += '</div>'
        st.markdown(cards_html, unsafe_allow_html=True)

    if uploaded:
        st.success(f"✅ {len(uploaded)} archivo(s) cargado(s) y listo(s) para procesar")

        with st.expander("Ver lista de archivos cargados", expanded=False):
            for f in uploaded:
                st.text(f"• {f.name}  ({f.size / 1024:.1f} KB)")

        col1, col2, col3 = st.columns([1, 1, 3])
        with col1:
            process = st.button("🚀 Procesar lote", type="primary", use_container_width=True)

        if process:
            pipeline = get_pipeline(use_mock=use_mock)

            progress = st.progress(0.0, text="Iniciando procesamiento...")
            log_area = st.empty()
            log_lines: list[str] = []

            results: list[DocumentResult] = []
            n = len(uploaded)

            for i, file in enumerate(uploaded):
                progress.progress(
                    (i + 1) / n,
                    text=f"Procesando {i + 1}/{n}: {file.name}",
                )

                try:
                    file_bytes = file.getvalue()
                    result = pipeline.process(file_bytes, file.name)
                except Exception as e:
                    result = DocumentResult(
                        filename=file.name,
                        doc_type=DocType.DESCONOCIDO,
                        doc_type_confidence=0.0,
                        extracted_text="",
                        error=f"Error en pipeline: {e}",
                    )

                results.append(result)

                # Log incremental
                if result.error:
                    log_lines.append(f"❌ **{file.name}** → {result.error}")
                else:
                    log_lines.append(
                        f"✅ **{file.name}** → {DOC_TYPE_LABELS[result.doc_type]} "
                        f"({result.doc_type_confidence:.0%} confianza · "
                        f"{len(result.entities)} entidades)"
                    )
                log_area.markdown("\n\n".join(log_lines[-10:]))  # últimas 10 líneas
                time.sleep(0.03)

            st.session_state.results = results
            st.session_state.processed_at = datetime.now()

            progress.empty()
            st.success(
                f"🎉 Procesamiento completado: {n} documento(s). "
                "Ve a la pestaña **Resultados** para ver el detalle."
            )


# ---------------------------------------------------------------------------
# TAB: RESULTADOS
# ---------------------------------------------------------------------------

with tab_results:
    if not st.session_state.results:
        st.info("ℹ️ Aún no hay resultados. Carga y procesa documentos en la pestaña anterior.")
    else:
        results = st.session_state.results

        # ---------- Resumen ----------
        st.subheader("Resumen")

        errors = [r for r in results if r.error]
        n_total = len(results)
        n_ok = n_total - len(errors)

        cols = st.columns(5)
        cards = [
            (
                "📊", "Total procesados", n_total,
                f"{n_ok} ok · {len(errors)} con error",
                False,
            ),
        ]
        for dt in [DocType.CEDULA, DocType.CAMARA_COMERCIO, DocType.RUT, DocType.POLIZA]:
            count = sum(1 for r in results if r.doc_type == dt)
            pct = (count / n_total * 100) if n_total else 0
            cards.append((
                DOC_TYPE_ICONS[dt],
                DOC_TYPE_LABELS[dt],
                count,
                f"{pct:.0f}% del lote",
                count > 0,
            ))

        for col, (icon, label, value, sub, is_accent) in zip(cols, cards):
            accent_cls = " accent" if is_accent else ""
            col.markdown(
                f'<div class="metric-card{accent_cls}">'
                f'<div class="metric-label">{icon} {label}</div>'
                f'<div class="metric-value">{value}</div>'
                f'<div class="metric-sub">{sub}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )
        if errors:
            st.warning(f"⚠️ {len(errors)} documento(s) con errores. Ver pestaña de errores abajo.")

        if st.session_state.processed_at:
            st.caption(
                f"Último procesamiento: {st.session_state.processed_at.strftime('%Y-%m-%d %H:%M:%S')}"
            )

        st.divider()

        # ---------- Descarga ----------
        col1, col2 = st.columns([1, 4])
        with col1:
            excel_bytes = build_excel(results)
            st.download_button(
                label="📥 Descargar Excel",
                data=excel_bytes,
                file_name=f"docuinsight_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                type="primary",
                use_container_width=True,
            )

        st.divider()

        # ---------- Analytics ----------
        ok_results = [r for r in results if not r.error]
        if ok_results:
            st.subheader("Analytics del lote")

            col_pie, col_hist = st.columns([1, 1])

            with col_pie:
                dist_data = {
                    DOC_TYPE_LABELS[dt]: sum(1 for r in ok_results if r.doc_type == dt)
                    for dt in [DocType.CEDULA, DocType.CAMARA_COMERCIO, DocType.RUT, DocType.POLIZA]
                }
                dist_data = {k: v for k, v in dist_data.items() if v > 0}
                if dist_data:
                    fig_pie = px.pie(
                        names=list(dist_data.keys()),
                        values=list(dist_data.values()),
                        title="Distribución por tipo documental",
                        color_discrete_sequence=[PRIMARY, ACCENT, "#82A5C9", "#41444B"],
                        hole=0.45,
                    )
                    fig_pie.update_traces(textposition="inside", textinfo="percent+label")
                    fig_pie.update_layout(
                        showlegend=True,
                        height=320,
                        margin=dict(t=50, b=20, l=20, r=20),
                        font=dict(family="sans-serif", color=DARK_TEXT),
                    )
                    st.plotly_chart(fig_pie, use_container_width=True)

            with col_hist:
                confidences = [r.doc_type_confidence for r in ok_results]
                fig_hist = px.histogram(
                    x=confidences,
                    nbins=10,
                    title="Distribución de confianza de clasificación",
                    color_discrete_sequence=[PRIMARY],
                    range_x=[0, 1],
                )
                fig_hist.update_layout(
                    xaxis_title="Confianza",
                    yaxis_title="Documentos",
                    height=320,
                    bargap=0.05,
                    margin=dict(t=50, b=40, l=40, r=20),
                    font=dict(family="sans-serif", color=DARK_TEXT),
                )
                fig_hist.update_xaxes(tickformat=".0%")
                st.plotly_chart(fig_hist, use_container_width=True)

            # Tiempos de procesamiento
            times = [r.processing_time_ms for r in ok_results if r.processing_time_ms]
            if times:
                total_s = sum(times) / 1000
                avg_ms = sum(times) / len(times)
                low_conf = sum(1 for r in ok_results if r.doc_type_confidence < 0.85)
                t_col1, t_col2, t_col3 = st.columns(3)
                t_col1.markdown(
                    f'<div class="metric-card">'
                    f'<div class="metric-label">⏱️ Tiempo total</div>'
                    f'<div class="metric-value">{total_s:.1f}s</div>'
                    f'<div class="metric-sub">procesando {len(times)} documento(s)</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
                t_col2.markdown(
                    f'<div class="metric-card">'
                    f'<div class="metric-label">⚡ Promedio por documento</div>'
                    f'<div class="metric-value">{avg_ms:.0f}ms</div>'
                    f'<div class="metric-sub">latencia media</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
                t_col3.markdown(
                    f'<div class="metric-card accent">'
                    f'<div class="metric-label">🔍 Requieren revisión</div>'
                    f'<div class="metric-value">{low_conf}</div>'
                    f'<div class="metric-sub">confianza < 85%</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

            st.divider()

        # ---------- Filtro ----------
        st.subheader("Detalle por documento")

        col1, col2 = st.columns([1, 3])
        with col1:
            options = ["Todos"] + [
                DOC_TYPE_LABELS[dt]
                for dt in [DocType.CEDULA, DocType.CAMARA_COMERCIO, DocType.RUT, DocType.POLIZA]
            ]
            if errors:
                options.append("Solo errores")

            filter_choice = st.selectbox("Filtrar por", options=options, index=0)

        if filter_choice == "Todos":
            filtered = results
        elif filter_choice == "Solo errores":
            filtered = errors
        else:
            filtered = [r for r in results if DOC_TYPE_LABELS[r.doc_type] == filter_choice]

        st.caption(f"Mostrando {len(filtered)} de {len(results)} documento(s)")

        # ---------- Detalle ----------
        for result in filtered:
            if result.error:
                icon = "❌"
            else:
                icon = DOC_TYPE_ICONS.get(result.doc_type, "📄")
            header = (
                f"{icon}  **{result.filename}**  ·  "
                f"{DOC_TYPE_LABELS[result.doc_type]}"
            )
            if not result.error:
                header += f"  ·  {result.doc_type_confidence:.0%} confianza"

            with st.expander(header):
                if result.error:
                    st.error(f"**Error:** {result.error}")
                    continue

                if result.entities:
                    rows_html = "".join(
                        f"<tr>"
                        f"<td style='padding:8px 12px;border-bottom:1px solid #F3F4F6;color:#6B7280;font-size:0.85em;'>"
                        f"{humanize_entity_label(e.label)}</td>"
                        f"<td style='padding:8px 12px;border-bottom:1px solid #F3F4F6;font-weight:500;'>"
                        f"{e.value}</td>"
                        f"<td style='padding:8px 12px;border-bottom:1px solid #F3F4F6;text-align:center;'>"
                        f"{_confidence_badge(e.confidence)}</td>"
                        f"</tr>"
                        for e in result.entities
                    )
                    st.markdown(
                        f'<table style="width:100%;border-collapse:collapse;'
                        f'background:white;border:1px solid #E5E7EB;border-radius:6px;'
                        f'overflow:hidden;">'
                        f'<thead><tr style="background:{LIGHT_BG};">'
                        f'<th style="padding:10px 12px;text-align:left;color:{DARK_TEXT};'
                        f'font-size:0.8em;text-transform:uppercase;letter-spacing:0.05em;">Entidad</th>'
                        f'<th style="padding:10px 12px;text-align:left;color:{DARK_TEXT};'
                        f'font-size:0.8em;text-transform:uppercase;letter-spacing:0.05em;">Valor</th>'
                        f'<th style="padding:10px 12px;text-align:center;color:{DARK_TEXT};'
                        f'font-size:0.8em;text-transform:uppercase;letter-spacing:0.05em;width:90px;">Confianza</th>'
                        f'</tr></thead><tbody>{rows_html}</tbody></table>',
                        unsafe_allow_html=True,
                    )
                else:
                    st.info("No se extrajeron entidades de este documento.")

                st.markdown("")
                with st.popover("Ver texto extraído (OCR)"):
                    st.text(result.extracted_text or "(sin texto)")

                st.caption(f"⏱️ Tiempo de procesamiento: {result.processing_time_ms} ms")
