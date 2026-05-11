"""
DocuInsight — Aplicación Streamlit.
Synergia Lab · MVP de clasificación documental + extracción de entidades.

Correr con:
    streamlit run app.py
"""

from __future__ import annotations

import time
from datetime import datetime

import pandas as pd
import streamlit as st

from export import build_excel
from pipeline import get_pipeline
from schemas import (
    DOC_TYPE_LABELS,
    DocType,
    DocumentResult,
    humanize_entity_label,
)


# ============================================================================
# CONFIGURACIÓN GENERAL
# ============================================================================

st.set_page_config(
    page_title="DocuInsight · Synergia Lab",
    page_icon="📄",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Paleta de marca
PRIMARY = "#1E3A5F"
ACCENT = "#4FB3BF"
LIGHT_BG = "#F5F8FA"

# CSS personalizado
st.markdown(
    f"""
    <style>
        .main-header {{
            background: linear-gradient(135deg, {PRIMARY} 0%, {ACCENT} 100%);
            color: white;
            padding: 1.75rem 2rem;
            border-radius: 0.75rem;
            margin-bottom: 1.5rem;
            box-shadow: 0 2px 8px rgba(30, 58, 95, 0.15);
        }}
        .main-header h1 {{
            color: white !important;
            margin: 0;
            font-weight: 600;
            font-size: 2rem;
        }}
        .main-header p {{
            color: rgba(255, 255, 255, 0.92);
            margin: 0.25rem 0 0 0;
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
        section[data-testid="stSidebar"] {{
            background-color: {LIGHT_BG};
        }}
        .stTabs [data-baseweb="tab-list"] button[aria-selected="true"] {{
            color: {PRIMARY};
            font-weight: 600;
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

    st.markdown(
        "<div style='text-align:center; color:#888; font-size:0.8rem; margin-top:2rem;'>"
        "DocuInsight v0.1<br>Synergia Lab"
        "</div>",
        unsafe_allow_html=True,
    )


# ============================================================================
# HEADER
# ============================================================================

st.markdown(
    """
    <div class="main-header">
        <h1>📄 DocuInsight</h1>
        <p>Clasificación inteligente y extracción de entidades documentales · Synergia Lab</p>
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
        cols = st.columns(5)
        with cols[0]:
            st.metric("Total procesados", len(results))
        for i, dt in enumerate([DocType.CEDULA, DocType.CAMARA_COMERCIO, DocType.RUT, DocType.POLIZA]):
            count = sum(1 for r in results if r.doc_type == dt)
            with cols[i + 1]:
                st.metric(DOC_TYPE_LABELS[dt], count)

        errors = [r for r in results if r.error]
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
            icon = "❌" if result.error else "📄"
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
                    df = pd.DataFrame(
                        [
                            {
                                "Entidad": humanize_entity_label(e.label),
                                "Valor": e.value,
                                "Confianza": f"{e.confidence:.0%}",
                            }
                            for e in result.entities
                        ]
                    )
                    st.dataframe(df, use_container_width=True, hide_index=True)
                else:
                    st.info("No se extrajeron entidades de este documento.")

                with st.popover("Ver texto extraído (OCR)"):
                    st.text(result.extracted_text or "(sin texto)")

                st.caption(f"Tiempo de procesamiento: {result.processing_time_ms} ms")
