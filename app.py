import hashlib
import io
import os
import pandas as pd
import requests
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from PIL import Image

# ============================================================
# 1. CONFIGURACIÓN DE LA PÁGINA
# ============================================================
st.set_page_config(
    page_title="Portal Digital de Recaudo - Citi Summa",
    page_icon="💼",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ============================================================
# 2. FORMATOS FINANCIEROS Y NUMÉRICOS
# ============================================================
def formato_pesos(val):
    if pd.isna(val) or val is None:
        return "$0"
    try:
        return f"${float(val):,.0f}".replace(",", ".")
    except (ValueError, TypeError):
        return "$0"



MESES_CALENDARIO = {
    "ENERO": 1, "FEBRERO": 2, "MARZO": 3, "ABRIL": 4,
    "MAYO": 5, "JUNIO": 6, "JULIO": 7, "AGOSTO": 8,
    "SEPTIEMBRE": 9, "OCTUBRE": 10, "NOVIEMBRE": 11,
    "DICIEMBRE": 12,
}

def preparar_periodo(df):
    """Extrae mes y año desde valores como 'ENERO 2024' y ordena cronológicamente."""
    out = df.copy()
    out["MES_ORIGINAL"] = out["MES"].astype(str).str.strip().str.upper()
    out["AÑO"] = pd.to_numeric(
        out["MES_ORIGINAL"].str.extract(r"(20\d{2})")[0],
        errors="coerce",
    )
    out["MES_NOMBRE"] = (
        out["MES_ORIGINAL"]
        .str.replace(r"\s*20\d{2}", "", regex=True)
        .str.strip()
    )
    out["MES_ORDEN"] = out["MES_NOMBRE"].map(MESES_CALENDARIO).fillna(99)
    return out

def formato_pesos_cop(val):
    """Formato ejecutivo en pesos colombianos, conservando el valor completo."""
    if pd.isna(val) or val is None:
        return "$ 0 COP"
    try:
        return f"$ {float(val):,.0f} COP".replace(",", ".")
    except (ValueError, TypeError):
        return "$ 0 COP"

def formato_numero(val):
    if pd.isna(val) or val is None:
        return "0"
    try:
        return f"{int(val):,.0f}".replace(",", ".")
    except (ValueError, TypeError):
        return "0"


# ============================================================
# 2.0 SANEAMIENTO DE TIPOS ANTES DE MOSTRAR TABLAS
# ============================================================
def preparar_para_mostrar(df, columnas_texto=None, columnas_entero=None, columnas_decimal=None):
    """
    Sanea un dataframe antes de entregarlo a st.dataframe / st.data_editor.

    Streamlit convierte los dataframes a formato Arrow (pyarrow) para
    poder renderizarlos. Si una columna tiene tipos mezclados (por
    ejemplo texto y número juntos, o valores nulos con formatos
    distintos), esa conversión falla con errores como:
    "ValueError ... convert_pandas_df_to_arrow_bytes".

    Esta función fuerza tipos de datos consistentes por columna para
    evitar ese error, sin importar de dónde venga el dataframe
    (Supabase, un Excel cargado, o la base de respaldo local).
    """
    if df is None or df.empty:
        return df

    out = df.copy()
    out = out.loc[:, ~out.columns.duplicated()]
    out = out.reset_index(drop=True)

    columnas_texto = columnas_texto or [
        c for c in ["ID", "CARTERA", "DIRECTOR", "MES"] if c in out.columns
    ]
    columnas_entero = columnas_entero or [
        c for c in ["# CLIENTES"] if c in out.columns
    ]
    columnas_decimal = columnas_decimal or [
        c for c in ["CAPITAL", "RECAUDO", "PROYECCION", "% EFECTIVIDAD", "ESTIMADO CIERRE"]
        if c in out.columns
    ]

    for col in columnas_texto:
        if col == "ID":
            # El ID se conserva numérico (permite nulos) para que los
            # botones de guardado sigan funcionando correctamente.
            out[col] = pd.to_numeric(out[col], errors="coerce")
        else:
            out[col] = out[col].where(out[col].notna(), "").astype(str)

    for col in columnas_entero:
        out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0).astype("int64")

    for col in columnas_decimal:
        out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0.0).astype("float64")

    return out


# ============================================================
# 2.1 RESUMEN CONSOLIDADO (SUMATORIA TOTAL POR CARTERA)
# ============================================================
def resumen_por_cartera(df):
    """
    Agrupa el dataframe recibido por CARTERA y calcula la sumatoria
    total de CAPITAL, # CLIENTES, RECAUDO y PROYECCION, junto con el
    % de EFECTIVIDAD y el ESTIMADO CIERRE consolidados. Agrega al
    final una fila con el TOTAL GENERAL de todas las carteras.
    """
    columnas_salida = [
        "CARTERA", "CAPITAL", "# CLIENTES", "RECAUDO",
        "PROYECCION", "% EFECTIVIDAD", "ESTIMADO CIERRE",
    ]

    if df is None or df.empty or "CARTERA" not in df.columns:
        return pd.DataFrame(columns=columnas_salida)

    resumen = (
        df.groupby("CARTERA", as_index=False)
        .agg({
            "CAPITAL": "sum",
            "# CLIENTES": "sum",
            "RECAUDO": "sum",
            "PROYECCION": "sum",
        })
    )

    resumen["% EFECTIVIDAD"] = (
        (resumen["RECAUDO"] / resumen["CAPITAL"] * 100)
        .where(resumen["CAPITAL"] > 0, 0)
    )
    resumen["ESTIMADO CIERRE"] = resumen["RECAUDO"] + resumen["PROYECCION"]

    resumen = resumen.sort_values(
        "CAPITAL", ascending=False
    ).reset_index(drop=True)

    cap_sum = resumen["CAPITAL"].sum()
    rec_sum = resumen["RECAUDO"].sum()

    fila_total = pd.DataFrame([{
        "CARTERA": "🔷 TOTAL GENERAL",
        "CAPITAL": cap_sum,
        "# CLIENTES": resumen["# CLIENTES"].sum(),
        "RECAUDO": rec_sum,
        "PROYECCION": resumen["PROYECCION"].sum(),
        "% EFECTIVIDAD": (rec_sum / cap_sum * 100) if cap_sum > 0 else 0.0,
        "ESTIMADO CIERRE": resumen["ESTIMADO CIERRE"].sum(),
    }])

    return pd.concat([resumen, fila_total], ignore_index=True)[columnas_salida]


def mostrar_resumen_cartera(df, titulo="📦 Sumatoria Total de la Cartera (por Cartera)"):
    """Renderiza la tabla de sumatoria total separada por cartera."""
    st.markdown(f"#### {titulo}")

    resumen = resumen_por_cartera(df)

    if resumen.empty:
        st.info("No hay información de carteras disponible para consolidar.")
        return

    resumen = preparar_para_mostrar(
        resumen,
        columnas_texto=["CARTERA"],
        columnas_entero=["# CLIENTES"],
        columnas_decimal=["CAPITAL", "RECAUDO", "PROYECCION", "% EFECTIVIDAD", "ESTIMADO CIERRE"],
    )

    st.dataframe(
        resumen,
        use_container_width=True,
        hide_index=True,
        column_config={
            "CARTERA": st.column_config.TextColumn(
                "Cartera", width="medium"
            ),
            "CAPITAL": st.column_config.NumberColumn(
                "Capital Total ($)", format="$ %,d", width="large"
            ),
            "# CLIENTES": st.column_config.NumberColumn(
                "# Clientes", format="%,d", width="small"
            ),
            "RECAUDO": st.column_config.NumberColumn(
                "Recaudo Total ($)", format="$ %,d", width="large"
            ),
            "PROYECCION": st.column_config.NumberColumn(
                "Proyección Total ($)", format="$ %,d", width="large"
            ),
            "% EFECTIVIDAD": st.column_config.NumberColumn(
                "% Efectividad", format="%.2f %%", width="small"
            ),
            "ESTIMADO CIERRE": st.column_config.NumberColumn(
                "Estimado Cierre ($)", format="$ %,d", width="large"
            ),
        },
    )


# ============================================================
# 3. ESTILOS CSS PERSONALIZADOS
# ============================================================
st.markdown(
    """
    <style>
    .main { background-color: #f8fafc; }
    h1 { color: #0f172a; font-family: 'Segoe UI', Roboto, sans-serif; font-weight: 800; }
    h2, h3 { color: #1e293b; font-weight: 700; }

    [data-testid="stMetric"] {
        background: linear-gradient(135deg, #ffffff 0%, #f1f5f9 100%);
        border: 1px solid #cbd5e1;
        border-radius: 16px;
        padding: 20px;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.08);
        border-top: 4px solid #2563eb;
        overflow: visible !important;
    }

    [data-testid="stMetricLabel"] {
        color: #475569;
        font-size: 0.9rem;
        font-weight: 800;
        text-transform: uppercase;
    }

    [data-testid="stMetricValue"] {
        color: #0f172a;
        font-weight: 900;
        white-space: normal !important;
        overflow: visible !important;
        text-overflow: clip !important;
        word-break: break-word;
        line-height: 1.2;
    }

    [data-testid="stMetricValue"] > div {
        font-size: clamp(1.0rem, 1.7vw, 1.6rem) !important;
        white-space: normal !important;
        overflow: visible !important;
        text-overflow: clip !important;
        word-break: break-word;
    }

    [data-testid="stSidebar"] { background-color: #0f172a; }

    [data-testid="stSidebar"] h1,
    [data-testid="stSidebar"] span,
    [data-testid="stSidebar"] p {
        color: #f8fafc !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ============================================================
# 4. GESTIÓN DEL LOGO
# ============================================================
LOGO_PATH = "logo_empresa.png"


def cargar_logo():
    if os.path.exists(LOGO_PATH):
        try:
            return Image.open(LOGO_PATH)
        except Exception:
            return None
    return None


def mostrar_logo_sidebar():
    logo = cargar_logo()

    if logo is not None:
        _, col_logo, _ = st.sidebar.columns([1, 4, 1])
        with col_logo:
            st.image(logo, use_container_width=True)
    else:
        st.sidebar.markdown("### 🏢 **Citi Summa**\n*Servicios Legales*")

    st.sidebar.markdown("---")


# ============================================================
# 5. BASE INICIAL DESDE LA TABLA REAL DE CARTERA
# ============================================================
# La base inicial se construye con la información proporcionada
# en el archivo "actualización cartera.xlsx".
#
# Columnas de origen:
# DIRECTOR | CARTERA | MES | CAPITAL | # CLIENTES
#
# Los campos operativos RECAUDO, PROYECCION, % EFECTIVIDAD y
# ESTIMADO CIERRE comienzan en cero.
# ============================================================

DATOS_INICIALES_CARTERA = [{'CARTERA': 'Popular 3tc Citi 2022', 'DIRECTOR': 'ADRIANA', 'MES': 'NOVIEMBRE 2022', 'CAPITAL': 283011316.0, '# CLIENTES': 64, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Popular 3tc Citi 2022', 'DIRECTOR': 'CARLOS', 'MES': 'NOVIEMBRE 2022', 'CAPITAL': 0.0, '# CLIENTES': 0, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Popular 3tc Citi 2022', 'DIRECTOR': 'JEIMMY', 'MES': 'NOVIEMBRE 2022', 'CAPITAL': 542955485.0, '# CLIENTES': 132, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Popular 3tc Citi 2022', 'DIRECTOR': 'ERIKA', 'MES': 'NOVIEMBRE 2022', 'CAPITAL': 353845265.0, '# CLIENTES': 85, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Popular 3tc Citi 2022', 'DIRECTOR': 'MIGUEL', 'MES': 'NOVIEMBRE 2022', 'CAPITAL': 308957270.0, '# CLIENTES': 73, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Popular 3tc Citi 2023', 'DIRECTOR': 'ADRIANA', 'MES': 'FEBRERO 2023', 'CAPITAL': 363775986.0, '# CLIENTES': 86, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Popular 3tc Citi 2023', 'DIRECTOR': 'CARLOS', 'MES': 'FEBRERO 2023', 'CAPITAL': 16116359.0, '# CLIENTES': 4, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Popular 3tc Citi 2023', 'DIRECTOR': 'JEIMMY', 'MES': 'FEBRERO 2023', 'CAPITAL': 628826406.0, '# CLIENTES': 145, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Popular 3tc Citi 2023', 'DIRECTOR': 'ERIKA', 'MES': 'FEBRERO 2023', 'CAPITAL': 307198091.0, '# CLIENTES': 70, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Popular 3tc Citi 2023', 'DIRECTOR': 'MIGUEL', 'MES': 'FEBRERO 2023', 'CAPITAL': 317064819.0, '# CLIENTES': 74, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Popular 2026', 'DIRECTOR': 'ADRIANA', 'MES': 'ENERO 2026', 'CAPITAL': 3598011715.0, '# CLIENTES': 85, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Popular 2026', 'DIRECTOR': 'CARLOS', 'MES': 'ENERO 2026', 'CAPITAL': 7259787281.659, '# CLIENTES': 173, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Popular 2026', 'DIRECTOR': 'JEIMMY', 'MES': 'ENERO 2026', 'CAPITAL': 7479973316.0, '# CLIENTES': 173, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Popular 2026', 'DIRECTOR': 'ERIKA', 'MES': 'ENERO 2026', 'CAPITAL': 0.0, '# CLIENTES': 0, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Popular 2026', 'DIRECTOR': 'MIGUEL', 'MES': 'ENERO 2026', 'CAPITAL': 10896210066.994997, '# CLIENTES': 259, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Popular 2tc 2023', 'DIRECTOR': 'ADRIANA', 'MES': 'MARZO 2023', 'CAPITAL': 217450011.0, '# CLIENTES': 53, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Popular 2tc 2023', 'DIRECTOR': 'ADRIANA', 'MES': 'ABRIL 2023', 'CAPITAL': 252750319.0, '# CLIENTES': 62, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Popular 2tc 2023', 'DIRECTOR': 'ADRIANA', 'MES': 'MAYO 2023', 'CAPITAL': 199530664.0, '# CLIENTES': 60, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Popular 2tc 2023', 'DIRECTOR': 'ADRIANA', 'MES': 'AGOSTO 2023', 'CAPITAL': 330411006.0, '# CLIENTES': 73, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Popular 2tc 2023', 'DIRECTOR': 'ADRIANA', 'MES': 'SEPTIEMBRE 2023', 'CAPITAL': 214162693.0, '# CLIENTES': 50, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Popular 2tc 2023', 'DIRECTOR': 'ADRIANA', 'MES': 'OCTUBRE 2023', 'CAPITAL': 172146722.0, '# CLIENTES': 40, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Popular 2tc 2023', 'DIRECTOR': 'ADRIANA', 'MES': 'NOVIEMBRE 2023', 'CAPITAL': 156811901.0, '# CLIENTES': 37, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Popular 2tc 2023', 'DIRECTOR': 'CARLOS', 'MES': 'MARZO 2023', 'CAPITAL': 136917130.0, '# CLIENTES': 23, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Popular 2tc 2023', 'DIRECTOR': 'CARLOS', 'MES': 'ABRIL 2023', 'CAPITAL': 92269779.0, '# CLIENTES': 16, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Popular 2tc 2023', 'DIRECTOR': 'CARLOS', 'MES': 'MAYO 2023', 'CAPITAL': 121778876.0, '# CLIENTES': 30, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Popular 2tc 2023', 'DIRECTOR': 'CARLOS', 'MES': 'AGOSTO 2023', 'CAPITAL': 100080622.0, '# CLIENTES': 18, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Popular 2tc 2023', 'DIRECTOR': 'CARLOS', 'MES': 'SEPTIEMBRE 2023', 'CAPITAL': 64017762.0, '# CLIENTES': 17, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Popular 2tc 2023', 'DIRECTOR': 'CARLOS', 'MES': 'OCTUBRE 2023', 'CAPITAL': 32716977.0, '# CLIENTES': 10, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Popular 2tc 2023', 'DIRECTOR': 'CARLOS', 'MES': 'NOVIEMBRE 2023', 'CAPITAL': 84333875.0, '# CLIENTES': 9, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Popular 2tc 2023', 'DIRECTOR': 'JEIMMY', 'MES': 'MARZO 2023', 'CAPITAL': 208883758.0, '# CLIENTES': 37, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Popular 2tc 2023', 'DIRECTOR': 'JEIMMY', 'MES': 'ABRIL 2023', 'CAPITAL': 314328703.0, '# CLIENTES': 61, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Popular 2tc 2023', 'DIRECTOR': 'JEIMMY', 'MES': 'MAYO 2023', 'CAPITAL': 324075901.0, '# CLIENTES': 80, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Popular 2tc 2023', 'DIRECTOR': 'JEIMMY', 'MES': 'AGOSTO 2023', 'CAPITAL': 361175283.0, '# CLIENTES': 84, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Popular 2tc 2023', 'DIRECTOR': 'JEIMMY', 'MES': 'SEPTIEMBRE 2023', 'CAPITAL': 118548516.0, '# CLIENTES': 36, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Popular 2tc 2023', 'DIRECTOR': 'JEIMMY', 'MES': 'OCTUBRE 2023', 'CAPITAL': 125300433.0, '# CLIENTES': 22, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Popular 2tc 2023', 'DIRECTOR': 'JEIMMY', 'MES': 'NOVIEMBRE 2023', 'CAPITAL': 144760249.0, '# CLIENTES': 38, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Popular 2tc 2023', 'DIRECTOR': 'ERIKA', 'MES': 'MARZO 2023', 'CAPITAL': 158069634.0, '# CLIENTES': 27, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Popular 2tc 2023', 'DIRECTOR': 'ERIKA', 'MES': 'ABRIL 2023', 'CAPITAL': 168676090.0, '# CLIENTES': 37, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Popular 2tc 2023', 'DIRECTOR': 'ERIKA', 'MES': 'MAYO 2023', 'CAPITAL': 171496851.0, '# CLIENTES': 38, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Popular 2tc 2023', 'DIRECTOR': 'ERIKA', 'MES': 'AGOSTO 2023', 'CAPITAL': 173054368.0, '# CLIENTES': 41, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Popular 2tc 2023', 'DIRECTOR': 'ERIKA', 'MES': 'SEPTIEMBRE 2023', 'CAPITAL': 185321197.0, '# CLIENTES': 38, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Popular 2tc 2023', 'DIRECTOR': 'ERIKA', 'MES': 'OCTUBRE 2023', 'CAPITAL': 76231049.0, '# CLIENTES': 15, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Popular 2tc 2023', 'DIRECTOR': 'ERIKA', 'MES': 'NOVIEMBRE 2023', 'CAPITAL': 63478223.0, '# CLIENTES': 16, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Popular 2tc 2023', 'DIRECTOR': 'MIGUEL', 'MES': 'MARZO 2023', 'CAPITAL': 366474313.0, '# CLIENTES': 62, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Popular 2tc 2023', 'DIRECTOR': 'MIGUEL', 'MES': 'ABRIL 2023', 'CAPITAL': 391300211.0, '# CLIENTES': 81, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Popular 2tc 2023', 'DIRECTOR': 'MIGUEL', 'MES': 'MAYO 2023', 'CAPITAL': 442850207.0, '# CLIENTES': 82, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Popular 2tc 2023', 'DIRECTOR': 'MIGUEL', 'MES': 'AGOSTO 2023', 'CAPITAL': 418012165.0, '# CLIENTES': 84, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Popular 2tc 2023', 'DIRECTOR': 'MIGUEL', 'MES': 'SEPTIEMBRE 2023', 'CAPITAL': 349068958.0, '# CLIENTES': 76, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Popular 2tc 2023', 'DIRECTOR': 'MIGUEL', 'MES': 'OCTUBRE 2023', 'CAPITAL': 147610188.0, '# CLIENTES': 40, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Popular 2tc 2023', 'DIRECTOR': 'MIGUEL', 'MES': 'NOVIEMBRE 2023', 'CAPITAL': 148133591.0, '# CLIENTES': 30, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Popular 2tc 2024', 'DIRECTOR': 'ADRIANA', 'MES': 'AGOSTO 2024', 'CAPITAL': 148513093.0, '# CLIENTES': 29, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Popular 2tc 2024', 'DIRECTOR': 'ADRIANA', 'MES': 'NOVIEMBRE 2024', 'CAPITAL': 125989825.0, '# CLIENTES': 34, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Popular 2tc 2024', 'DIRECTOR': 'ADRIANA', 'MES': 'DICIEMBRE 2024', 'CAPITAL': 453590983.0, '# CLIENTES': 108, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Popular 2tc 2025', 'DIRECTOR': 'ADRIANA', 'MES': 'ENERO 2025', 'CAPITAL': 211644080.0, '# CLIENTES': 44, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Popular 2tc 2025', 'DIRECTOR': 'ADRIANA', 'MES': 'FEBRERO 2025', 'CAPITAL': 470409122.0, '# CLIENTES': 66, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Popular 2tc 2025', 'DIRECTOR': 'ADRIANA', 'MES': 'ABRIL 2025', 'CAPITAL': 758385662.0, '# CLIENTES': 135, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Popular 2tc 2024', 'DIRECTOR': 'CARLOS', 'MES': 'AGOSTO 2024', 'CAPITAL': 71639878.0, '# CLIENTES': 12, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Popular 2tc 2024', 'DIRECTOR': 'CARLOS', 'MES': 'NOVIEMBRE 2024', 'CAPITAL': 56044961.0, '# CLIENTES': 16, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Popular 2tc 2024', 'DIRECTOR': 'CARLOS', 'MES': 'DICIEMBRE 2024', 'CAPITAL': 64948542.0, '# CLIENTES': 21, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Popular 2tc 2025', 'DIRECTOR': 'CARLOS', 'MES': 'ENERO 2025', 'CAPITAL': 91417010.0, '# CLIENTES': 19, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Popular 2tc 2025', 'DIRECTOR': 'CARLOS', 'MES': 'FEBRERO 2025', 'CAPITAL': 152192100.0, '# CLIENTES': 25, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Popular 2tc 2025', 'DIRECTOR': 'CARLOS', 'MES': 'ABRIL 2025', 'CAPITAL': 162914652.0, '# CLIENTES': 34, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Popular 2tc 2024', 'DIRECTOR': 'JEIMMY', 'MES': 'AGOSTO 2024', 'CAPITAL': 104294765.0, '# CLIENTES': 34, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Popular 2tc 2024', 'DIRECTOR': 'JEIMMY', 'MES': 'NOVIEMBRE 2024', 'CAPITAL': 56528799.0, '# CLIENTES': 24, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Popular 2tc 2024', 'DIRECTOR': 'JEIMMY', 'MES': 'DICIEMBRE 2024', 'CAPITAL': 398214954.0, '# CLIENTES': 111, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Popular 2tc 2025', 'DIRECTOR': 'JEIMMY', 'MES': 'ENERO 2025', 'CAPITAL': 160391400.0, '# CLIENTES': 42, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Popular 2tc 2025', 'DIRECTOR': 'JEIMMY', 'MES': 'FEBRERO 2025', 'CAPITAL': 340286333.0, '# CLIENTES': 64, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Popular 2tc 2025', 'DIRECTOR': 'JEIMMY', 'MES': 'ABRIL 2025', 'CAPITAL': 562281175.0, '# CLIENTES': 83, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Popular 2tc 2024', 'DIRECTOR': 'ERIKA', 'MES': 'AGOSTO 2024', 'CAPITAL': 115422703.0, '# CLIENTES': 25, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Popular 2tc 2024', 'DIRECTOR': 'ERIKA', 'MES': 'NOVIEMBRE 2024', 'CAPITAL': 63620189.0, '# CLIENTES': 18, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Popular 2tc 2024', 'DIRECTOR': 'ERIKA', 'MES': 'DICIEMBRE 2024', 'CAPITAL': 208670107.0, '# CLIENTES': 46, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Popular 2tc 2025', 'DIRECTOR': 'ERIKA', 'MES': 'ENERO 2025', 'CAPITAL': 121091826.0, '# CLIENTES': 23, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Popular 2tc 2025', 'DIRECTOR': 'ERIKA', 'MES': 'FEBRERO 2025', 'CAPITAL': 234092129.0, '# CLIENTES': 36, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Popular 2tc 2025', 'DIRECTOR': 'ERIKA', 'MES': 'ABRIL 2025', 'CAPITAL': 396642657.0, '# CLIENTES': 63, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Popular 2tc 2024', 'DIRECTOR': 'MIGUEL', 'MES': 'AGOSTO 2024', 'CAPITAL': 135321515.0, '# CLIENTES': 37, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Popular 2tc 2024', 'DIRECTOR': 'MIGUEL', 'MES': 'NOVIEMBRE 2024', 'CAPITAL': 190346413.0, '# CLIENTES': 32, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Popular 2tc 2024', 'DIRECTOR': 'MIGUEL', 'MES': 'DICIEMBRE 2024', 'CAPITAL': 567330140.0, '# CLIENTES': 147, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Popular 2tc 2025', 'DIRECTOR': 'MIGUEL', 'MES': 'ENERO 2025', 'CAPITAL': 153480414.0, '# CLIENTES': 33, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Popular 2tc 2025', 'DIRECTOR': 'MIGUEL', 'MES': 'FEBRERO 2025', 'CAPITAL': 414815978.0, '# CLIENTES': 66, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Popular 2tc 2025', 'DIRECTOR': 'MIGUEL', 'MES': 'ABRIL 2025', 'CAPITAL': 919678690.0, '# CLIENTES': 152, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Av Villas 2023', 'DIRECTOR': 'ADRIANA', 'MES': 'MAYO 2023', 'CAPITAL': 141407500.0, '# CLIENTES': 26, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Av Villas 2023', 'DIRECTOR': 'ADRIANA', 'MES': 'JUNIO 2023', 'CAPITAL': 134172386.0, '# CLIENTES': 23, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Av Villas 2023', 'DIRECTOR': 'ADRIANA', 'MES': 'JULIO 2023', 'CAPITAL': 201262077.0, '# CLIENTES': 22, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Av Villas 2023', 'DIRECTOR': 'ADRIANA', 'MES': 'AGOSTO 2023', 'CAPITAL': 68927008.0, '# CLIENTES': 8, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Av Villas 2023', 'DIRECTOR': 'ADRIANA', 'MES': 'SEPTIEMBRE 2023', 'CAPITAL': 108898560.0, '# CLIENTES': 10, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Av Villas 2023', 'DIRECTOR': 'ADRIANA', 'MES': 'OCTUBRE 2023', 'CAPITAL': 42076495.0, '# CLIENTES': 5, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Av Villas 2023', 'DIRECTOR': 'ADRIANA', 'MES': 'NOVIEMBRE 2023', 'CAPITAL': 5497318.0, '# CLIENTES': 3, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Av Villas 2023', 'DIRECTOR': 'ADRIANA', 'MES': 'DICIEMBRE 2023', 'CAPITAL': 147550166.0, '# CLIENTES': 13, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Av Villas 2023', 'DIRECTOR': 'CARLOS', 'MES': 'MAYO 2023', 'CAPITAL': 217388736.0, '# CLIENTES': 31, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Av Villas 2023', 'DIRECTOR': 'CARLOS', 'MES': 'JUNIO 2023', 'CAPITAL': 205585999.0, '# CLIENTES': 28, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Av Villas 2023', 'DIRECTOR': 'CARLOS', 'MES': 'JULIO 2023', 'CAPITAL': 230760809.0, '# CLIENTES': 20, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Av Villas 2023', 'DIRECTOR': 'CARLOS', 'MES': 'AGOSTO 2023', 'CAPITAL': 82183618.0, '# CLIENTES': 12, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Av Villas 2023', 'DIRECTOR': 'CARLOS', 'MES': 'SEPTIEMBRE 2023', 'CAPITAL': 42103360.0, '# CLIENTES': 9, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Av Villas 2023', 'DIRECTOR': 'CARLOS', 'MES': 'OCTUBRE 2023', 'CAPITAL': 27248323.0, '# CLIENTES': 5, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Av Villas 2023', 'DIRECTOR': 'CARLOS', 'MES': 'NOVIEMBRE 2023', 'CAPITAL': 74528605.0, '# CLIENTES': 10, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Av Villas 2023', 'DIRECTOR': 'CARLOS', 'MES': 'DICIEMBRE 2023', 'CAPITAL': 75593625.0, '# CLIENTES': 9, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Av Villas 2023', 'DIRECTOR': 'JEIMMY', 'MES': 'MAYO 2023', 'CAPITAL': 251225056.0, '# CLIENTES': 35, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Av Villas 2023', 'DIRECTOR': 'JEIMMY', 'MES': 'JUNIO 2023', 'CAPITAL': 188718871.0, '# CLIENTES': 30, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Av Villas 2023', 'DIRECTOR': 'JEIMMY', 'MES': 'JULIO 2023', 'CAPITAL': 67690772.0, '# CLIENTES': 9, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Av Villas 2023', 'DIRECTOR': 'JEIMMY', 'MES': 'AGOSTO 2023', 'CAPITAL': 87128538.0, '# CLIENTES': 13, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Av Villas 2023', 'DIRECTOR': 'JEIMMY', 'MES': 'SEPTIEMBRE 2023', 'CAPITAL': 33099999.0, '# CLIENTES': 7, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Av Villas 2023', 'DIRECTOR': 'JEIMMY', 'MES': 'OCTUBRE 2023', 'CAPITAL': 70306705.0, '# CLIENTES': 7, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Av Villas 2023', 'DIRECTOR': 'JEIMMY', 'MES': 'NOVIEMBRE 2023', 'CAPITAL': 17414553.0, '# CLIENTES': 6, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Av Villas 2023', 'DIRECTOR': 'JEIMMY', 'MES': 'DICIEMBRE 2023', 'CAPITAL': 143013722.0, '# CLIENTES': 12, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Av Villas 2023', 'DIRECTOR': 'MIGUEL', 'MES': 'MAYO 2023', 'CAPITAL': 455585882.0, '# CLIENTES': 45, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Av Villas 2023', 'DIRECTOR': 'MIGUEL', 'MES': 'JUNIO 2023', 'CAPITAL': 198079720.0, '# CLIENTES': 40, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Av Villas 2023', 'DIRECTOR': 'MIGUEL', 'MES': 'JULIO 2023', 'CAPITAL': 297714675.0, '# CLIENTES': 23, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Av Villas 2023', 'DIRECTOR': 'MIGUEL', 'MES': 'AGOSTO 2023', 'CAPITAL': 148462785.0, '# CLIENTES': 16, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Av Villas 2023', 'DIRECTOR': 'MIGUEL', 'MES': 'SEPTIEMBRE 2023', 'CAPITAL': 107119724.0, '# CLIENTES': 11, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Av Villas 2023', 'DIRECTOR': 'MIGUEL', 'MES': 'OCTUBRE 2023', 'CAPITAL': 55189226.0, '# CLIENTES': 4, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Av Villas 2023', 'DIRECTOR': 'MIGUEL', 'MES': 'NOVIEMBRE 2023', 'CAPITAL': 31687946.0, '# CLIENTES': 8, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Av Villas 2023', 'DIRECTOR': 'MIGUEL', 'MES': 'DICIEMBRE 2023', 'CAPITAL': 58923965.0, '# CLIENTES': 14, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Av Villas 2024', 'DIRECTOR': 'ADRIANA', 'MES': 'ENERO 2024', 'CAPITAL': 147926349.0, '# CLIENTES': 9, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Av Villas 2024', 'DIRECTOR': 'ADRIANA', 'MES': 'FEBRERO 2024', 'CAPITAL': 85215893.0, '# CLIENTES': 12, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Av Villas 2024', 'DIRECTOR': 'ADRIANA', 'MES': 'MARZO 2024', 'CAPITAL': 133658303.0, '# CLIENTES': 10, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Av Villas 2024', 'DIRECTOR': 'ADRIANA', 'MES': 'ABRIL 2024', 'CAPITAL': 141942785.0, '# CLIENTES': 8, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Av Villas 2024', 'DIRECTOR': 'ADRIANA', 'MES': 'MAYO 2024', 'CAPITAL': 123371678.0, '# CLIENTES': 9, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Av Villas 2024', 'DIRECTOR': 'ADRIANA', 'MES': 'JUNIO 2024', 'CAPITAL': 40518214.0, '# CLIENTES': 6, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Av Villas 2024', 'DIRECTOR': 'ADRIANA', 'MES': 'JULIO 2024', 'CAPITAL': 105561311.0, '# CLIENTES': 6, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Av Villas 2024', 'DIRECTOR': 'ADRIANA', 'MES': 'AGOSTO 2024', 'CAPITAL': 88247918.0, '# CLIENTES': 8, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Av Villas 2024', 'DIRECTOR': 'CARLOS', 'MES': 'ENERO 2024', 'CAPITAL': 64628932.0, '# CLIENTES': 14, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Av Villas 2024', 'DIRECTOR': 'CARLOS', 'MES': 'FEBRERO 2024', 'CAPITAL': 65250440.0, '# CLIENTES': 9, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Av Villas 2024', 'DIRECTOR': 'CARLOS', 'MES': 'MARZO 2024', 'CAPITAL': 54002588.0, '# CLIENTES': 8, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Av Villas 2024', 'DIRECTOR': 'CARLOS', 'MES': 'ABRIL 2024', 'CAPITAL': 76207201.0, '# CLIENTES': 9, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Av Villas 2024', 'DIRECTOR': 'CARLOS', 'MES': 'MAYO 2024', 'CAPITAL': 108337915.0, '# CLIENTES': 11, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Av Villas 2024', 'DIRECTOR': 'CARLOS', 'MES': 'JUNIO 2024', 'CAPITAL': 209457854.0, '# CLIENTES': 21, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Av Villas 2024', 'DIRECTOR': 'CARLOS', 'MES': 'JULIO 2024', 'CAPITAL': 40103766.0, '# CLIENTES': 4, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Av Villas 2024', 'DIRECTOR': 'CARLOS', 'MES': 'AGOSTO 2024', 'CAPITAL': 101884220.0, '# CLIENTES': 7, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Av Villas 2024', 'DIRECTOR': 'JEIMMY', 'MES': 'ENERO 2024', 'CAPITAL': 82690884.0, '# CLIENTES': 8, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Av Villas 2024', 'DIRECTOR': 'JEIMMY', 'MES': 'FEBRERO 2024', 'CAPITAL': 40989588.0, '# CLIENTES': 6, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Av Villas 2024', 'DIRECTOR': 'JEIMMY', 'MES': 'MARZO 2024', 'CAPITAL': 39524789.0, '# CLIENTES': 6, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Av Villas 2024', 'DIRECTOR': 'JEIMMY', 'MES': 'ABRIL 2024', 'CAPITAL': 37125082.0, '# CLIENTES': 5, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Av Villas 2024', 'DIRECTOR': 'JEIMMY', 'MES': 'MAYO 2024', 'CAPITAL': 55033607.0, '# CLIENTES': 6, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Av Villas 2024', 'DIRECTOR': 'JEIMMY', 'MES': 'JUNIO 2024', 'CAPITAL': 33532585.0, '# CLIENTES': 8, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Av Villas 2024', 'DIRECTOR': 'JEIMMY', 'MES': 'JULIO 2024', 'CAPITAL': 47277197.0, '# CLIENTES': 7, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Av Villas 2024', 'DIRECTOR': 'JEIMMY', 'MES': 'AGOSTO 2024', 'CAPITAL': 20261708.0, '# CLIENTES': 7, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Av Villas 2024', 'DIRECTOR': 'MIGUEL', 'MES': 'ENERO 2024', 'CAPITAL': 169812351.0, '# CLIENTES': 17, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Av Villas 2024', 'DIRECTOR': 'MIGUEL', 'MES': 'FEBRERO 2024', 'CAPITAL': 207169782.0, '# CLIENTES': 16, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Av Villas 2024', 'DIRECTOR': 'MIGUEL', 'MES': 'MARZO 2024', 'CAPITAL': 18670928.0, '# CLIENTES': 4, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Av Villas 2024', 'DIRECTOR': 'MIGUEL', 'MES': 'ABRIL 2024', 'CAPITAL': 210282220.0, '# CLIENTES': 14, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Av Villas 2024', 'DIRECTOR': 'MIGUEL', 'MES': 'MAYO 2024', 'CAPITAL': 101782378.0, '# CLIENTES': 13, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Av Villas 2024', 'DIRECTOR': 'MIGUEL', 'MES': 'JUNIO 2024', 'CAPITAL': 119458579.0, '# CLIENTES': 13, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Av Villas 2024', 'DIRECTOR': 'MIGUEL', 'MES': 'JULIO 2024', 'CAPITAL': 89055563.0, '# CLIENTES': 8, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Av Villas 2024', 'DIRECTOR': 'MIGUEL', 'MES': 'AGOSTO 2024', 'CAPITAL': 65474540.0, '# CLIENTES': 15, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'FICH', 'DIRECTOR': 'ADRIANA', 'MES': 'NOVIEMBRE 2021', 'CAPITAL': 4087595610.0, '# CLIENTES': 305, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'FICH', 'DIRECTOR': 'CARLOS', 'MES': 'NOVIEMBRE 2021', 'CAPITAL': 4095378850.0, '# CLIENTES': 304, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'FICH', 'DIRECTOR': 'JEIMMY', 'MES': 'NOVIEMBRE 2021', 'CAPITAL': 4106110386.0, '# CLIENTES': 305, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'FICH', 'DIRECTOR': 'ERIKA', 'MES': 'NOVIEMBRE 2021', 'CAPITAL': 4093999544.0, '# CLIENTES': 304, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'FICH', 'DIRECTOR': 'MIGUEL', 'MES': 'NOVIEMBRE 2021', 'CAPITAL': 4094056079.0, '# CLIENTES': 304, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Coovitel Propia', 'DIRECTOR': 'ADRIANA', 'MES': 'SEPTIEMBRE 2022', 'CAPITAL': 903286535.0, '# CLIENTES': 152, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Coovitel Propia', 'DIRECTOR': 'CARLOS', 'MES': 'SEPTIEMBRE 2022', 'CAPITAL': 905752041.0, '# CLIENTES': 152, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Coovitel Propia', 'DIRECTOR': 'JEIMMY', 'MES': 'SEPTIEMBRE 2022', 'CAPITAL': 906808933.0, '# CLIENTES': 153, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Coovitel Propia', 'DIRECTOR': 'ERIKA', 'MES': 'SEPTIEMBRE 2022', 'CAPITAL': 877168053.0, '# CLIENTES': 152, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Coovitel Propia', 'DIRECTOR': 'MIGUEL', 'MES': 'SEPTIEMBRE 2022', 'CAPITAL': 1049527961.0, '# CLIENTES': 152, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Coovitel Propia 2', 'DIRECTOR': 'MIGUEL', 'MES': 'ABRIL 2023', 'CAPITAL': 0.0, '# CLIENTES': 0, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Coovitel Propia 2', 'DIRECTOR': 'CARLOS', 'MES': 'ABRIL 2023', 'CAPITAL': 0.0, '# CLIENTES': 0, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Popular 1', 'DIRECTOR': 'ADRIANA', 'MES': 'DICIEMBRE 2021', 'CAPITAL': 15283080585.0, '# CLIENTES': 1345, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Popular 1', 'DIRECTOR': 'CARLOS', 'MES': 'DICIEMBRE 2021', 'CAPITAL': 2844968739.0, '# CLIENTES': 744, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Popular 1', 'DIRECTOR': 'JEIMMY', 'MES': 'DICIEMBRE 2021', 'CAPITAL': 22525612904.0, '# CLIENTES': 2764, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Popular 1', 'DIRECTOR': 'ERIKA', 'MES': 'DICIEMBRE 2021', 'CAPITAL': 3800321160.0, '# CLIENTES': 965, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Popular 1', 'DIRECTOR': 'MIGUEL', 'MES': 'DICIEMBRE 2021', 'CAPITAL': 2943871809.0, '# CLIENTES': 725, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Popular 2', 'DIRECTOR': 'ADRIANA', 'MES': 'OCTUBRE 2022', 'CAPITAL': 15127927307.0, '# CLIENTES': 2177, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Popular 2', 'DIRECTOR': 'CARLOS', 'MES': 'OCTUBRE 2022', 'CAPITAL': 15270093716.0, '# CLIENTES': 2093, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Popular 2', 'DIRECTOR': 'JEIMMY', 'MES': 'OCTUBRE 2022', 'CAPITAL': 27475983116.0, '# CLIENTES': 1580, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Popular 2', 'DIRECTOR': 'ERIKA', 'MES': 'OCTUBRE 2022', 'CAPITAL': 10334335995.0, '# CLIENTES': 852, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Popular 2', 'DIRECTOR': 'MIGUEL', 'MES': 'OCTUBRE 2022', 'CAPITAL': 12559138445.0, '# CLIENTES': 1401, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}]


def inicializar_base_datos():
    """
    Inicializa la base operativa usando la tabla real de cartera.

    La combinación de Director + Cartera + Mes + Capital + Clientes
    ya no se genera mediante listas fijas ni valores inventados.
    """
    datos = [registro.copy() for registro in DATOS_INICIALES_CARTERA]

    return pd.DataFrame(datos)[
        [
            "CARTERA",
            "DIRECTOR",
            "MES",
            "CAPITAL",
            "# CLIENTES",
            "RECAUDO",
            "PROYECCION",
            "% EFECTIVIDAD",
            "ESTIMADO CIERRE",
        ]
    ]


# ============================================================
# 5B. CONEXIÓN Y SINCRONIZACIÓN CON SUPABASE
# ============================================================
def obtener_secret(nombre):
    try:
        return st.secrets[nombre]
    except Exception:
        return os.getenv(nombre)

SUPABASE_URL = obtener_secret("SUPABASE_URL")
SUPABASE_KEY = obtener_secret("SUPABASE_KEY")
SUPABASE_TABLE = "base_meses_db"

if not SUPABASE_URL or not SUPABASE_KEY:
    st.error(
        "❌ No se encontraron las credenciales de Supabase. "
        "Configura SUPABASE_URL y SUPABASE_KEY en Streamlit Cloud → Settings → Secrets."
    )
    st.stop()

SUPABASE_URL = str(SUPABASE_URL).rstrip("/")
SUPABASE_HEADERS = {
    "apikey": str(SUPABASE_KEY),
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
}



# Columnas internas estandarizadas de la aplicación.
# La tabla real de Supabase usa nombres en minúscula; la aplicación
# trabaja internamente con estos nombres visibles.
COLUMNAS_APP = [
    "ID",
    "CARTERA",
    "DIRECTOR",
    "MES",
    "CAPITAL",
    "# CLIENTES",
    "RECAUDO",
    "PROYECCION",
    "% EFECTIVIDAD",
    "ESTIMADO CIERRE",
]

def supabase_request(method, endpoint, **kwargs):
    url = f"{SUPABASE_URL}/rest/v1/{endpoint}"
    headers = dict(SUPABASE_HEADERS)
    headers.update(kwargs.pop("headers", {}))
    response = requests.request(method, url, headers=headers, timeout=30, **kwargs)
    if not response.ok:
        raise RuntimeError(
            f"Supabase HTTP {response.status_code}: {response.text[:1000]}"
        )
    if not response.text:
        return []
    try:
        return response.json()
    except Exception:
        return []


def dataframe_desde_supabase():
    """Fuente oficial de datos: tabla base_meses_db en Supabase."""
    registros = supabase_request(
        "GET",
        f"{SUPABASE_TABLE}?select=*&order=id.asc",
    )
    if not registros:
        return pd.DataFrame(columns=["ID", *COLUMNAS_APP])

    df = pd.DataFrame(registros).rename(columns={
        "id": "ID",
        "cartera": "CARTERA",
        "director": "DIRECTOR",
        "mes": "MES",
        "capital": "CAPITAL",
        "num_clientes": "# CLIENTES",
        "recaudo": "RECAUDO",
        "proyeccion": "PROYECCION",
        "efectividad": "% EFECTIVIDAD",
        "estimado_cierre": "ESTIMADO CIERRE",
    })

    for col in ["CARTERA", "DIRECTOR", "MES"]:
        if col not in df.columns:
            df[col] = ""
        df[col] = df[col].astype(str).str.strip()

    df["DIRECTOR"] = df["DIRECTOR"].str.upper()
    df["MES"] = df["MES"].str.upper()

    for col in ["CAPITAL", "RECAUDO", "PROYECCION", "% EFECTIVIDAD", "ESTIMADO CIERRE"]:
        if col not in df.columns:
            df[col] = 0.0
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)

    if "# CLIENTES" not in df.columns:
        df["# CLIENTES"] = 0
    df["# CLIENTES"] = pd.to_numeric(df["# CLIENTES"], errors="coerce").fillna(0).astype(int)

    # Mantener los valores derivados consistentes con el recaudo actual.
    df["% EFECTIVIDAD"] = (
        (df["RECAUDO"] / df["CAPITAL"] * 100)
        .where(df["CAPITAL"] > 0, 0)
        .fillna(0)
    )
    df["ESTIMADO CIERRE"] = df["RECAUDO"] + df["PROYECCION"]

    return df[["ID", *COLUMNAS_APP]].copy()


def actualizar_sesion_desde_supabase():
    df = dataframe_desde_supabase()
    st.session_state.base_meses_db = df
    return df


def actualizar_registro_supabase(registro_id, recaudo, proyeccion, capital):
    efectividad = (recaudo / capital * 100) if capital > 0 else 0.0
    estimado_cierre = recaudo + proyeccion
    payload = {
        "recaudo": float(recaudo),
        "proyeccion": float(proyeccion),
        "efectividad": float(efectividad),
        "estimado_cierre": float(estimado_cierre),
    }
    supabase_request(
        "PATCH",
        f"{SUPABASE_TABLE}?id=eq.{int(registro_id)}",
        json=payload,
        headers={"Prefer": "return=minimal"},
    )


def eliminar_todos_registros_supabase():
    supabase_request(
        "DELETE",
        f"{SUPABASE_TABLE}?id=not.is.null",
        headers={"Prefer": "return=minimal"},
    )



# ============================================================
# 6. INICIALIZACIÓN DEL ESTADO DE SESIÓN
# ============================================================
if "base_meses_db" not in st.session_state:
    try:
        df_supabase = dataframe_desde_supabase()
        if not df_supabase.empty:
            st.session_state.base_meses_db = df_supabase
        else:
            # Solo se usa como respaldo si Supabase está vacío.
            st.session_state.base_meses_db = inicializar_base_datos()
    except Exception as e:
        st.error(f"❌ Error cargando la base desde Supabase: {e}")
        st.stop()

if "backup_db" not in st.session_state:
    st.session_state.backup_db = None


# ============================================================
# 7. AUTENTICACIÓN Y BASE DE USUARIOS
# ============================================================
def hacer_hash(password):
    return hashlib.sha256(str.encode(password)).hexdigest()


if "usuarios_db" not in st.session_state:
    st.session_state.usuarios_db = {
        "presidencia": {
            "hash": hacer_hash("presidencia2026"),
            "nombre": "Presidencia Ejecutiva",
            "rol": "presidencia",
        },
        "gerente": {
            "hash": hacer_hash("gerencia2026"),
            "nombre": "Gerente General",
            "rol": "admin",
        },
        "adriana": {
            "hash": hacer_hash("adriana123"),
            "nombre": "ADRIANA",
            "rol": "director",
        },
        "carlos": {
            "hash": hacer_hash("carlos123"),
            "nombre": "CARLOS",
            "rol": "director",
        },
        "jeimmy": {
            "hash": hacer_hash("jeimmy123"),
            "nombre": "JEIMMY",
            "rol": "director",
        },
        "erika": {
            "hash": hacer_hash("erika123"),
            "nombre": "ERIKA",
            "rol": "director",
        },
        "miguel": {
            "hash": hacer_hash("miguel123"),
            "nombre": "MIGUEL",
            "rol": "director",
        },
    }


if "autenticado" not in st.session_state:
    st.session_state.autenticado = False


# ============================================================
# 8. PANTALLA DE LOGIN
# ============================================================
if not st.session_state.autenticado:
    _, col_c2, _ = st.columns([1, 2, 1])

    with col_c2:
        st.write("")
        st.write("")

        logo_login = cargar_logo()

        if logo_login is not None:
            st.image(logo_login, use_container_width=True)
        else:
            st.title("🏛️ CITI SUMMA")
            st.caption("SERVICIOS LEGALES")

        st.markdown("### 🔐 Portal Digital de Recaudo")
        st.caption("Ingrese sus credenciales de acceso:")

        user_input = st.text_input("Usuario:").strip().lower()
        pass_input = st.text_input("Contraseña:", type="password")

        if st.button(
            "Iniciar Sesión",
            type="primary",
            use_container_width=True,
        ):
            usuarios = st.session_state.usuarios_db

            if (
                user_input in usuarios
                and usuarios[user_input]["hash"] == hacer_hash(pass_input)
            ):
                st.session_state.autenticado = True
                st.session_state.usuario = user_input
                st.session_state.rol = usuarios[user_input]["rol"]
                st.session_state.nombre = usuarios[user_input]["nombre"]
                st.rerun()
            else:
                st.error("Usuario o contraseña incorrectos")

    st.stop()


# ============================================================
# 9. MENÚ LATERAL
# ============================================================
mostrar_logo_sidebar()

st.sidebar.title(f"👤 {st.session_state.nombre}")
st.sidebar.caption(f"Rol: **{st.session_state.rol.upper()}**")
st.sidebar.markdown("---")

if st.sidebar.button("🔄 Actualizar datos desde Supabase", use_container_width=True):
    try:
        actualizar_sesion_desde_supabase()
        for key in list(st.session_state.keys()):
            if str(key).startswith("editor_"):
                del st.session_state[key]
        st.success("✅ Datos actualizados desde Supabase.")
        st.rerun()
    except Exception as e:
        st.error(f"❌ Error actualizando datos: {e}")

if st.sidebar.button("🚪 Cerrar Sesión", use_container_width=True):
    st.session_state.autenticado = False
    st.rerun()


PALETA_VIVA = [
    "#2563EB",
    "#7C3AED",
    "#DB2777",
    "#EA580C",
    "#059669",
    "#0284C7",
    "#D97706",
    "#DC2626",
    "#4F46E5",
    "#0D9488",
]

PALETA_CARTERAS_BASE = (
    px.colors.qualitative.Dark24 + px.colors.qualitative.Vivid
)


# ============================================================
# 6.1 PALETA DE COLOR CONSISTENTE (DIRECTOR / CARTERA)
# ============================================================
def construir_paleta(valores, paleta_base=None):
    """
    Asigna un color fijo a cada valor único (ordenado alfabéticamente),
    para que un mismo director o cartera use siempre el mismo color
    sin importar el gráfico o la pestaña donde aparezca.
    """
    paleta_base = paleta_base or PALETA_VIVA
    valores_unicos = sorted(
        {str(v).strip() for v in valores if pd.notna(v) and str(v).strip()}
    )
    return {
        v: paleta_base[i % len(paleta_base)]
        for i, v in enumerate(valores_unicos)
    }


def paleta_bold(mapa):
    """Convierte un mapa de colores a las claves '<b>valor</b>' usadas
    en los gráficos que resaltan la etiqueta en negrilla."""
    return {f"<b>{k}</b>": v for k, v in mapa.items()}


# ============================================================
# 6.2 SERIE MENSUAL CRONOLÓGICA (para tendencias)
# ============================================================
def preparar_serie_mensual(df):
    """Agrupa CAPITAL/RECAUDO/PROYECCION por mes real (año + mes),
    ordenados cronológicamente (no solo por nombre de mes)."""
    if df is None or df.empty:
        return pd.DataFrame(
            columns=["CLAVE_ORDEN", "ETIQUETA_MES", "CAPITAL", "RECAUDO", "PROYECCION"]
        )

    dfp = preparar_periodo(df)
    dfp = dfp.dropna(subset=["AÑO"])
    if dfp.empty:
        return pd.DataFrame(
            columns=["CLAVE_ORDEN", "ETIQUETA_MES", "CAPITAL", "RECAUDO", "PROYECCION"]
        )

    dfp["CLAVE_ORDEN"] = dfp["AÑO"].astype(int) * 100 + dfp["MES_ORDEN"].astype(int)
    dfp["ETIQUETA_MES"] = (
        dfp["MES_NOMBRE"].str.title() + " " + dfp["AÑO"].astype(int).astype(str)
    )

    serie = (
        dfp.groupby(["CLAVE_ORDEN", "ETIQUETA_MES"], as_index=False)
        .agg({"CAPITAL": "sum", "RECAUDO": "sum", "PROYECCION": "sum"})
        .sort_values("CLAVE_ORDEN")
        .reset_index(drop=True)
    )
    return serie


def grafico_tendencia_mensual(df, meses_atras=6, titulo="📉 Tendencia — Últimos Meses"):
    """Mini gráfico de línea/área con la tendencia reciente de
    Recaudo vs Proyección, a modo de 'sparkline' ampliado."""
    serie = preparar_serie_mensual(df)

    st.markdown(f"##### {titulo}")

    if serie.empty:
        st.info("No hay suficiente historial mensual para mostrar la tendencia.")
        return

    serie = serie.tail(meses_atras)

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=serie["ETIQUETA_MES"], y=serie["RECAUDO"],
        mode="lines+markers", name="Recaudo",
        line=dict(color="#2563eb", width=3),
        marker=dict(size=6),
        fill="tozeroy", fillcolor="rgba(37,99,235,0.10)",
    ))
    fig.add_trace(go.Scatter(
        x=serie["ETIQUETA_MES"], y=serie["PROYECCION"],
        mode="lines+markers", name="Proyección",
        line=dict(color="#f59e0b", width=3, dash="dot"),
        marker=dict(size=6),
    ))
    fig.update_layout(
        height=220,
        margin=dict(l=10, r=10, t=10, b=10),
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.05, xanchor="left", x=0),
        yaxis_tickformat=",.0f",
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        hovermode="x unified",
    )
    fig.update_traces(hovertemplate="%{fullData.name}: $ %{y:,.0f} COP<extra></extra>")
    st.plotly_chart(fig, use_container_width=True)


# ============================================================
# 6.3 FILTROS GLOBALES (AÑO / CARTERA) — PERSISTENTES POR VISTA
# ============================================================
def aplicar_filtros_globales(df, key_prefix):
    """Muestra un filtro de Año y Cartera que aplica a toda la vista
    (todas las pestañas), en vez de que cada gráfico tenga el suyo."""
    df_periodo = preparar_periodo(df)
    anios = sorted(
        [int(x) for x in df_periodo["AÑO"].dropna().unique()]
    )
    carteras = sorted(df["CARTERA"].dropna().unique().tolist())

    col_f1, col_f2 = st.columns([1, 2])

    with col_f1:
        anio_sel = st.selectbox(
            "📅 Año",
            ["Todos"] + anios,
            key=f"{key_prefix}_anio_global",
        )

    with col_f2:
        cartera_sel = st.multiselect(
            "📦 Cartera(s) — vacío = todas",
            carteras,
            default=[],
            key=f"{key_prefix}_cartera_global",
        )

    df_filtrado = df.copy()

    if anio_sel != "Todos":
        df_periodo_f = preparar_periodo(df_filtrado)
        indices_validos = df_periodo_f[
            df_periodo_f["AÑO"] == int(anio_sel)
        ].index
        df_filtrado = df_filtrado.loc[indices_validos]

    if cartera_sel:
        df_filtrado = df_filtrado[df_filtrado["CARTERA"].isin(cartera_sel)]

    return df_filtrado


# ============================================================
# 6.4 PANEL DE ALERTAS (SOLO GERENCIA)
# ============================================================
def panel_alertas_gerencia(df, umbral_efectividad=30.0):
    """Resalta, sin tener que buscarlo en la tabla, qué carteras están
    en riesgo (baja efectividad) y qué directores no han registrado
    recaudo en el mes más reciente."""
    st.markdown("#### 🚨 Alertas de Gestión")

    if df is None or df.empty:
        st.info("No hay datos suficientes para calcular alertas.")
        return

    resumen_cart = resumen_por_cartera(df)
    resumen_cart = resumen_cart[
        resumen_cart["CARTERA"] != "🔷 TOTAL GENERAL"
    ]
    criticas = resumen_cart[
        (resumen_cart["CAPITAL"] > 0)
        & (resumen_cart["% EFECTIVIDAD"] < umbral_efectividad)
    ].sort_values("% EFECTIVIDAD")

    df_periodo = preparar_periodo(df).dropna(subset=["AÑO"])
    directores_sin_recaudo = pd.DataFrame(columns=["DIRECTOR", "RECAUDO"])
    if not df_periodo.empty:
        df_periodo["CLAVE_ORDEN"] = (
            df_periodo["AÑO"].astype(int) * 100
            + df_periodo["MES_ORDEN"].astype(int)
        )
        mes_max = df_periodo["CLAVE_ORDEN"].max()
        df_mes_actual = df_periodo[df_periodo["CLAVE_ORDEN"] == mes_max]
        directores_agg = (
            df_mes_actual.groupby("DIRECTOR", as_index=False)["RECAUDO"]
            .sum()
        )
        directores_sin_recaudo = directores_agg[
            directores_agg["RECAUDO"] <= 0
        ]

    col_a1, col_a2 = st.columns(2)

    with col_a1:
        if criticas.empty:
            st.success(
                f"✅ Ninguna cartera está por debajo del {umbral_efectividad:.0f}% de efectividad."
            )
        else:
            st.error(
                f"⚠️ {len(criticas)} cartera(s) con efectividad menor al "
                f"{umbral_efectividad:.0f}%:"
            )
            for _, row in criticas.iterrows():
                st.markdown(
                    f"- **{row['CARTERA']}** — {row['% EFECTIVIDAD']:.1f}% de efectividad "
                    f"(Capital {formato_pesos(row['CAPITAL'])})"
                )

    with col_a2:
        if directores_sin_recaudo.empty:
            st.success(
                "✅ Todos los directores registran recaudo en el mes más reciente."
            )
        else:
            st.warning(
                f"⚠️ {len(directores_sin_recaudo)} director(es) sin recaudo "
                "registrado en el mes más reciente:"
            )
            for _, row in directores_sin_recaudo.iterrows():
                st.markdown(f"- **{row['DIRECTOR']}**")


# ============================================================
# 6.5 COMPARATIVO CAPITAL vs RECAUDO vs PROYECCIÓN POR CARTERA
# ============================================================
def grafico_comparativo_capital_cartera(df, titulo="💠 Capital vs. Recaudo vs. Proyección por Cartera"):
    """Barras horizontales apiladas por cartera: cuánto se ha
    recaudado, cuánto está proyectado y cuánto capital falta por
    gestionar, todo en una sola barra por cartera."""
    st.markdown(f"#### {titulo}")

    resumen = resumen_por_cartera(df)
    resumen = resumen[resumen["CARTERA"] != "🔷 TOTAL GENERAL"].copy()

    if resumen.empty:
        st.info("No hay información de carteras disponible.")
        return

    resumen["RESTANTE"] = (
        resumen["CAPITAL"] - resumen["RECAUDO"] - resumen["PROYECCION"]
    ).clip(lower=0)
    resumen = resumen.sort_values("CAPITAL", ascending=True)

    fig = go.Figure()
    fig.add_trace(go.Bar(
        y=resumen["CARTERA"], x=resumen["RECAUDO"],
        name="Recaudado", orientation="h",
        marker_color="#059669",
        hovertemplate="Recaudado: $ %{x:,.0f} COP<extra></extra>",
    ))
    fig.add_trace(go.Bar(
        y=resumen["CARTERA"], x=resumen["PROYECCION"],
        name="Proyectado", orientation="h",
        marker_color="#f59e0b",
        hovertemplate="Proyectado: $ %{x:,.0f} COP<extra></extra>",
    ))
    fig.add_trace(go.Bar(
        y=resumen["CARTERA"], x=resumen["RESTANTE"],
        name="Falta por gestionar", orientation="h",
        marker_color="#e2e8f0",
        hovertemplate="Falta por gestionar: $ %{x:,.0f} COP<extra></extra>",
    ))
    fig.update_layout(
        barmode="stack",
        height=max(320, 42 * len(resumen)),
        xaxis_title="Capital (COP)",
        yaxis_title="",
        xaxis_tickformat=",.0f",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        margin=dict(l=20, r=20, t=20, b=20),
    )
    st.plotly_chart(fig, use_container_width=True)


# ============================================================
# VISTA 1: PRESIDENCIA
# ============================================================
if st.session_state.rol == "presidencia":

    try:
        actualizar_sesion_desde_supabase()
    except Exception as e:
        st.error(f"❌ No fue posible actualizar la información: {e}")

    st.title("🏛️ Panel de Control Presidencial")
    st.caption(
        "Vista ejecutiva de alto nivel, participaciones de mercado y tendencias globales"
    )

    df_all_original = st.session_state.base_meses_db.copy()

    # Paletas fijas por director/cartera calculadas sobre el universo
    # completo de datos, para que el color no cambie al filtrar.
    paleta_directores = paleta_bold(
        construir_paleta(df_all_original["DIRECTOR"])
    )
    paleta_carteras = paleta_bold(
        construir_paleta(df_all_original["CARTERA"], PALETA_CARTERAS_BASE)
    )

    st.markdown("##### 🔎 Filtros (aplican a todo el panel)")
    df_all = aplicar_filtros_globales(df_all_original, key_prefix="pres")

    cap_tot = df_all["CAPITAL"].sum()
    rec_tot = df_all["RECAUDO"].sum()
    proy_tot = df_all["PROYECCION"].sum()

    efect_global = (
        rec_tot / cap_tot * 100
        if cap_tot > 0
        else 0.0
    )

    m1, m2, m3, m4 = st.columns(4)

    m1.metric("Capital Global", formato_pesos(cap_tot))
    m2.metric("Recaudo Total", formato_pesos(rec_tot))
    m3.metric("Proyección Total", formato_pesos(proy_tot))
    m4.metric("% Efectividad Global", f"{efect_global:.2f}%")

    st.markdown("---")

    p_tab1, p_tab2, p_tab3, p_tab4 = st.tabs(
        [
            "🏆 Participación por Director",
            "📊 Recaudo por Cartera",
            "📈 Análisis por Cartera y Mes",
            "📅 Consolidado Mes x Mes",
        ]
    )

    with p_tab1:
        st.subheader("🏆 Ranking de Recaudo por Director")

        df_dir = (
            df_all.groupby("DIRECTOR", as_index=False)["RECAUDO"]
            .sum()
            .sort_values("RECAUDO", ascending=False)
            .reset_index(drop=True)
        )
        df_dir["RANKING"] = range(1, len(df_dir) + 1)
        df_dir["DIRECTOR_BOLD"] = df_dir["DIRECTOR"].apply(
            lambda x: f"<b>{x}</b>"
        )

        col_p1, col_p2 = st.columns([1.3, 1])

        with col_p1:
            fig_rank_bar = px.bar(
                df_dir.sort_values("RECAUDO", ascending=True),
                x="RECAUDO",
                y="DIRECTOR_BOLD",
                orientation="h",
                text="RECAUDO",
                title="<b>Ranking de Recaudo por Director</b>",
                color="DIRECTOR_BOLD",
                color_discrete_map=paleta_directores,
            )
            fig_rank_bar.update_traces(
                texttemplate="$ %{x:,.0f} COP",
                textposition="outside",
                textfont=dict(size=13, family="Arial Black", color="#0f172a"),
                cliponaxis=False,
                hovertemplate="%{y}<br>$ %{x:,.0f} COP<extra></extra>",
            )
            fig_rank_bar.update_layout(
                showlegend=False,
                xaxis_title="Recaudo (COP)",
                yaxis_title="",
                xaxis_tickformat=",.0f",
                margin=dict(l=20, r=160, t=60, b=20),
            )
            st.plotly_chart(fig_rank_bar, use_container_width=True)

        with col_p2:
            st.markdown("###### 🥧 Participación % por Director")

            fig_part_pres = px.pie(
                df_dir,
                names="DIRECTOR_BOLD",
                values="RECAUDO",
                hole=0.4,
                color="DIRECTOR_BOLD",
                color_discrete_map=paleta_directores,
            )
            fig_part_pres.update_traces(
                textposition="inside",
                textinfo="percent+label",
                textfont=dict(
                    size=12,
                    color="white",
                    family="Arial Black",
                ),
            )
            fig_part_pres.update_layout(
                showlegend=False,
                margin=dict(l=10, r=10, t=30, b=10),
            )
            st.plotly_chart(fig_part_pres, use_container_width=True)

    with p_tab2:
        st.subheader("📊 Peso de Capital y Efectividad por Cartera")
        st.caption(
            "El tamaño de cada bloque representa el Capital de la cartera; "
            "el color representa su % de Efectividad (verde = buena, rojo = crítica)."
        )

        df_treemap = resumen_por_cartera(df_all)
        df_treemap = df_treemap[
            df_treemap["CARTERA"] != "🔷 TOTAL GENERAL"
        ]

        if df_treemap.empty:
            st.info("No hay carteras disponibles con los filtros actuales.")
        else:
            fig_treemap = px.treemap(
                df_treemap,
                path=[px.Constant("Todas las Carteras"), "CARTERA"],
                values="CAPITAL",
                color="% EFECTIVIDAD",
                color_continuous_scale="RdYlGn",
                range_color=[0, 100],
            )
            fig_treemap.update_traces(
                texttemplate=(
                    "<b>%{label}</b><br>$ %{value:,.0f} COP"
                    "<br>%{color:.1f}% efectividad"
                ),
                textfont=dict(size=13, family="Arial Black"),
            )
            fig_treemap.update_layout(
                margin=dict(l=10, r=10, t=20, b=10),
                coloraxis_colorbar=dict(title="% Efectividad"),
            )
            st.plotly_chart(fig_treemap, use_container_width=True)

        st.markdown("---")

        mostrar_resumen_cartera(
            df_all,
            titulo="📦 Sumatoria Total de la Cartera (por Cartera)",
        )

    with p_tab3:
        st.subheader("📈 Comportamiento Mensual por Cartera Específica")

        carteras_disp = df_all["CARTERA"].dropna().unique().tolist()

        if carteras_disp:
            cartera_pres = st.selectbox(
                "Seleccione una Cartera para Analizar:",
                carteras_disp,
                key="pres_cart_select",
            )

            df_sub_cart = (
                df_all[df_all["CARTERA"] == cartera_pres]
                .groupby("MES", as_index=False)
                .agg(
                    {
                        "RECAUDO": "sum",
                        "PROYECCION": "sum",
                        "CAPITAL": "sum",
                    }
                )
            )

            df_sub_cart["MES_BOLD"] = df_sub_cart["MES"].apply(
                lambda x: f"<b>{x}</b>"
            )

            fig_sub_cart = px.bar(
                df_sub_cart,
                x="MES_BOLD",
                y=["RECAUDO", "PROYECCION"],
                barmode="group",
                title=(
                    f"<b>Comportamiento Mensual de Recaudo vs "
                    f"Proyección - {cartera_pres}</b>"
                ),
                color_discrete_map={
                    "RECAUDO": "#2563eb",
                    "PROYECCION": "#f59e0b",
                },
                labels={
                    "value": "Monto ($)",
                    "variable": "Tipo",
                },
            )

            st.plotly_chart(
                fig_sub_cart,
                use_container_width=True,
            )

    with p_tab4:
        st.subheader("📅 Consolidado General Mes por Mes")

        df_periodo = preparar_periodo(df_all)
        anios = sorted(
            [int(x) for x in df_periodo["AÑO"].dropna().unique()]
        )
        opciones_anio = ["Todos"] + anios
        anio_sel = st.selectbox(
            "Seleccione el año:",
            opciones_anio,
            key="pres_anio_mes",
        )

        df_filtrado = df_periodo.copy()
        if anio_sel != "Todos":
            df_filtrado = df_filtrado[df_filtrado["AÑO"] == int(anio_sel)]

        df_mes_tot = (
            df_filtrado.groupby(["MES_ORDEN", "MES_NOMBRE"], as_index=False)
            .agg({"CAPITAL": "sum", "RECAUDO": "sum", "PROYECCION": "sum"})
            .sort_values("MES_ORDEN")
        )

        fig_mes = go.Figure()
        fig_mes.add_trace(go.Scatter(
            x=df_mes_tot["MES_NOMBRE"], y=df_mes_tot["CAPITAL"],
            mode="lines", name="Capital (referencia)",
            line=dict(color="#94a3b8", width=2, dash="dash"),
            hovertemplate="Capital: $ %{y:,.0f} COP<extra></extra>",
        ))
        fig_mes.add_trace(go.Scatter(
            x=df_mes_tot["MES_NOMBRE"], y=df_mes_tot["RECAUDO"],
            mode="lines+markers", name="Recaudo",
            line=dict(color="#2563eb", width=3),
            marker=dict(size=7),
            fill="tozeroy", fillcolor="rgba(37,99,235,0.10)",
            hovertemplate="Recaudo: $ %{y:,.0f} COP<extra></extra>",
        ))
        fig_mes.add_trace(go.Scatter(
            x=df_mes_tot["MES_NOMBRE"], y=df_mes_tot["PROYECCION"],
            mode="lines+markers", name="Proyección",
            line=dict(color="#f59e0b", width=3, dash="dot"),
            marker=dict(size=7),
            hovertemplate="Proyección: $ %{y:,.0f} COP<extra></extra>",
        ))
        fig_mes.update_layout(
            title="<b>Evolución de Recaudo vs Proyección Mes a Mes</b>",
            xaxis_title="Mes",
            yaxis_title="Valor (COP)",
            xaxis=dict(
                categoryorder="array",
                categoryarray=list(MESES_CALENDARIO.keys()),
                tickangle=0,
            ),
            yaxis_tickformat=",.0f",
            hovermode="x unified",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        )
        st.plotly_chart(fig_mes, use_container_width=True)


# ============================================================
# VISTA 2: DIRECTOR
# ============================================================
elif st.session_state.rol == "director":

    st.title(
        f"✍️ Gestión de Recaudos por Mes - "
        f"{st.session_state.nombre}"
    )

    director_actual = st.session_state.nombre.strip().upper()

    df_full = st.session_state.base_meses_db.copy()

    df_full["DIRECTOR_NORMALIZADO"] = (
        df_full["DIRECTOR"]
        .astype(str)
        .apply(
            lambda x: (
                x.split("(")[0].strip().upper()
                if pd.notna(x)
                else ""
            )
        )
    )

    df_full["CARTERA_NORMALIZADA"] = (
        df_full["CARTERA"]
        .astype(str)
        .str.strip()
    )

    df_director = df_full[
        df_full["DIRECTOR_NORMALIZADO"] == director_actual
    ]

    carteras_director = (
        df_director["CARTERA_NORMALIZADA"]
        .dropna()
        .unique()
        .tolist()
    )

    if not carteras_director:
        st.warning(
            f"⚠️ No hay carteras asociadas al usuario "
            f"**{director_actual}** en la base actual."
        )

    else:
        tab1, tab2, tab3 = st.tabs(
            [
                "📅 Captura por Cartera y Mes",
                "📋 Resumen Completo",
                "📦 Base General por Cartera",
            ]
        )

        with tab1:

            cartera_sel = st.selectbox(
                "Seleccione la Cartera a Gestionar:",
                carteras_director,
            )

            mask_cartera = (
                (df_full["DIRECTOR_NORMALIZADO"] == director_actual)
                & (
                    df_full["CARTERA_NORMALIZADA"]
                    == cartera_sel
                )
            )

            df_sub = df_full[mask_cartera].copy()
            df_sub_editor = preparar_para_mostrar(df_sub)

            c1, c2, c3 = st.columns(3)

            c1.metric(
                "Capital Asignado",
                formato_pesos(df_sub["CAPITAL"].sum()),
            )

            c2.metric(
                "Clientes Totales",
                formato_numero(df_sub["# CLIENTES"].sum()),
            )

            c3.metric(
                "Recaudo Acumulado",
                formato_pesos(df_sub["RECAUDO"].sum()),
            )

            st.markdown("---")

            st.subheader(
                f"Desglose Mensual: **{cartera_sel}**"
            )

            df_editado = st.data_editor(
                df_sub_editor[
                    [
                        "ID",
                        "MES",
                        "CAPITAL",
                        "# CLIENTES",
                        "RECAUDO",
                        "PROYECCION",
                    ]
                ],
                disabled=[
                    "ID",
                    "MES",
                    "CAPITAL",
                    "# CLIENTES",
                ],
                use_container_width=True,
                key=f"editor_{director_actual}_{cartera_sel}",
                column_config={
                    "MES": st.column_config.TextColumn(
                        "Mes / Periodo",
                        width="medium",
                    ),
                    "CAPITAL": st.column_config.NumberColumn(
                        "Capital ($)",
                        format="$ %,d",
                        width="large",
                    ),
                    "# CLIENTES": st.column_config.NumberColumn(
                        "# Clientes",
                        format="%,d",
                        width="small",
                    ),
                    "RECAUDO": st.column_config.NumberColumn(
                        "Recaudo Actual ($)",
                        format="$ %,d",
                        min_value=0.0,
                        width="large",
                    ),
                    "PROYECCION": st.column_config.NumberColumn(
                        "Proyección ($)",
                        format="$ %,d",
                        min_value=0.0,
                        width="large",
                    ),
                },
                hide_index=True,
            )

            if st.button(
                "💾 Guardar Recaudos de la Cartera",
                type="primary",
                use_container_width=True,
            ):

                filas_modificadas = 0
                errores = []

                try:
                    for _, row in df_editado.iterrows():
                        registro_id = row.get("ID")
                        if pd.isna(registro_id):
                            errores.append(f"Registro sin ID: {row['MES']}")
                            continue

                        rec = float(row["RECAUDO"]) if pd.notna(row["RECAUDO"]) else 0.0
                        proy = float(row["PROYECCION"]) if pd.notna(row["PROYECCION"]) else 0.0
                        cap_val = float(row["CAPITAL"]) if pd.notna(row["CAPITAL"]) else 0.0

                        actualizar_registro_supabase(
                            registro_id, rec, proy, cap_val
                        )
                        filas_modificadas += 1

                    if filas_modificadas > 0:
                        actualizar_sesion_desde_supabase()
                        for key in list(st.session_state.keys()):
                            if str(key).startswith("editor_"):
                                del st.session_state[key]
                        st.success(
                            f"✅ ¡Se guardaron correctamente {filas_modificadas} registros para {cartera_sel}!"
                        )
                        if errores:
                            st.warning("⚠️ Algunos registros no se actualizaron: " + ", ".join(errores))
                        st.rerun()
                    else:
                        st.error("⚠️ No se actualizaron registros.")

                except Exception as e:
                    st.error(f"❌ Error guardando los cambios en Supabase: {e}")

        with tab2:

            st.subheader(
                "📋 Historial de Recaudo Completo"
            )

            mis_datos = df_director.drop(
                columns=[
                    "DIRECTOR_NORMALIZADO",
                    "CARTERA_NORMALIZADA",
                ],
                errors="ignore",
            ).copy()

            mis_datos = preparar_para_mostrar(mis_datos)

            st.dataframe(
                mis_datos,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "CAPITAL": st.column_config.NumberColumn(
                        "Capital ($)", format="$ %,d", width="large"
                    ),
                    "# CLIENTES": st.column_config.NumberColumn(
                        "# Clientes", format="%,d", width="small"
                    ),
                    "RECAUDO": st.column_config.NumberColumn(
                        "Recaudo ($)", format="$ %,d", width="large"
                    ),
                    "PROYECCION": st.column_config.NumberColumn(
                        "Proyección ($)", format="$ %,d", width="large"
                    ),
                    "% EFECTIVIDAD": st.column_config.NumberColumn(
                        "% Efectividad", format="%.2f %%", width="small"
                    ),
                    "ESTIMADO CIERRE": st.column_config.NumberColumn(
                        "Estimado Cierre ($)", format="$ %,d", width="large"
                    ),
                },
            )

        with tab3:

            st.subheader(
                f"📦 Base General por Cartera - {st.session_state.nombre}"
            )
            st.caption(
                "Sumatoria total de capital, recaudo y proyección, "
                "separada por cada cartera a su cargo."
            )

            mostrar_resumen_cartera(
                df_director,
                titulo="📦 Sumatoria Total por Cartera",
            )


# ============================================================
# VISTA 3: GERENTE GENERAL
# ============================================================
elif st.session_state.rol == "admin":

    try:
        actualizar_sesion_desde_supabase()
    except Exception as e:
        st.error(f"❌ No fue posible actualizar la información: {e}")

    st.title("📊 Panel Consolidado Gerencial")

    df_all = st.session_state.base_meses_db

    paleta_directores_g = paleta_bold(construir_paleta(df_all["DIRECTOR"]))
    paleta_carteras_g = paleta_bold(
        construir_paleta(df_all["CARTERA"], PALETA_CARTERAS_BASE)
    )

    t1, t2, t3, t4 = st.tabs(
        [
            "📈 Dashboard Consolidado",
            "📅 Consolidado Mes x Mes",
            "📋 Base General",
            "⚙️ Configuración / Admin",
        ]
    )

    with t1:

        st.markdown("##### 🔎 Filtros (aplican a este dashboard)")
        df_all_t1 = aplicar_filtros_globales(df_all, key_prefix="ger")

        m1, m2, m3, m4 = st.columns(4)

        m1.metric(
            "Capital Total",
            formato_pesos(df_all_t1["CAPITAL"].sum()),
        )

        m2.metric(
            "Total Recaudado",
            formato_pesos(df_all_t1["RECAUDO"].sum()),
        )

        m3.metric(
            "Total Proyección",
            formato_pesos(df_all_t1["PROYECCION"].sum()),
        )

        m4.metric(
            "Total Clientes",
            formato_numero(df_all_t1["# CLIENTES"].sum()),
        )

        st.markdown("---")

        panel_alertas_gerencia(df_all_t1, umbral_efectividad=30.0)

        st.markdown("---")

        # Primera línea: recaudo por cartera a todo el ancho.
        st.subheader("📊 Recaudo Total por Cartera")

        df_cart = (
            df_all_t1.groupby("CARTERA", as_index=False)["RECAUDO"]
            .sum()
            .sort_values("RECAUDO", ascending=True)
        )
        df_cart["CARTERA_BOLD"] = df_cart["CARTERA"].apply(
            lambda x: f"<b>{x}</b>"
        )

        fig1 = px.bar(
            df_cart,
            x="RECAUDO",
            y="CARTERA_BOLD",
            orientation="h",
            text="RECAUDO",
            color="CARTERA_BOLD",
            color_discrete_map=paleta_carteras_g,
        )
        fig1.update_traces(
            texttemplate="$ %{x:,.0f} COP",
            textposition="outside",
            textfont=dict(size=13, family="Arial Black", color="#0f172a"),
            cliponaxis=False,
            hovertemplate="%{y}<br>$ %{x:,.0f} COP<extra></extra>",
        )
        fig1.update_layout(
            showlegend=False,
            xaxis_title="Recaudo (COP)",
            yaxis_title="",
            xaxis_tickformat=",.0f",
            margin=dict(l=20, r=170, t=30, b=20),
        )
        st.plotly_chart(fig1, use_container_width=True)

        # Segunda línea: ranking y participación.
        col_g1, col_g2 = st.columns([1, 1])

        with col_g1:
            st.subheader("🏆 Ranking de Recaudo por Director")
            df_dir_g = (
                df_all_t1.groupby("DIRECTOR", as_index=False)["RECAUDO"]
                .sum()
                .sort_values("RECAUDO", ascending=True)
            )
            df_dir_g["DIRECTOR_BOLD"] = df_dir_g["DIRECTOR"].apply(
                lambda x: f"<b>{x}</b>"
            )
            fig_rank_g = px.bar(
                df_dir_g,
                x="RECAUDO",
                y="DIRECTOR_BOLD",
                orientation="h",
                text="RECAUDO",
                color="DIRECTOR_BOLD",
                color_discrete_map=paleta_directores_g,
            )
            fig_rank_g.update_traces(
                texttemplate="$ %{x:,.0f} COP",
                textposition="outside",
                textfont=dict(size=12, family="Arial Black", color="#0f172a"),
                cliponaxis=False,
                hovertemplate="%{y}<br>$ %{x:,.0f} COP<extra></extra>",
            )
            fig_rank_g.update_layout(
                showlegend=False,
                xaxis_title="Recaudo (COP)",
                yaxis_title="",
                xaxis_tickformat=",.0f",
                margin=dict(l=20, r=150, t=30, b=20),
            )
            st.plotly_chart(fig_rank_g, use_container_width=True)

        with col_g2:
            st.subheader("🥧 Participación % por Director")

            df_dir_g_pie = df_all_t1.groupby(
                "DIRECTOR", as_index=False
            )["RECAUDO"].sum()
            df_dir_g_pie["DIRECTOR_BOLD"] = df_dir_g_pie[
                "DIRECTOR"
            ].apply(lambda x: f"<b>{x}</b>")

            fig2 = px.pie(
                df_dir_g_pie,
                names="DIRECTOR_BOLD",
                values="RECAUDO",
                hole=0.4,
                color="DIRECTOR_BOLD",
                color_discrete_map=paleta_directores_g,
            )
            fig2.update_traces(
                textposition="inside",
                textinfo="percent+label",
                textfont=dict(
                    size=13,
                    color="white",
                    family="Arial Black",
                ),
            )
            st.plotly_chart(fig2, use_container_width=True)

        st.markdown("---")

        grafico_comparativo_capital_cartera(df_all_t1)

        st.markdown("---")

        st.subheader(
            "📈 Detalle Mensual de Recaudo por Cartera"
        )

        carteras_admin_disp = (
            df_all_t1["CARTERA"]
            .dropna()
            .unique()
            .tolist()
        )

        if carteras_admin_disp:

            cartera_admin_sel = st.selectbox(
                "Filtrar Comportamiento Mensual por Cartera:",
                carteras_admin_disp,
                key="admin_cart_select",
            )

            df_cart_mes_admin = (
                df_all_t1[
                    df_all_t1["CARTERA"]
                    == cartera_admin_sel
                ]
                .groupby(
                    "MES",
                    as_index=False,
                )
                .agg(
                    {
                        "RECAUDO": "sum",
                        "PROYECCION": "sum",
                    }
                )
            )

            df_cart_mes_admin["MES_BOLD"] = (
                df_cart_mes_admin["MES"].apply(
                    lambda x: f"<b>{x}</b>"
                )
            )

            fig_admin_cart = px.bar(
                df_cart_mes_admin,
                x="MES_BOLD",
                y=["RECAUDO", "PROYECCION"],
                barmode="group",
                title=(
                    f"<b>Evolución Mensual: "
                    f"{cartera_admin_sel}</b>"
                ),
                color_discrete_map={
                    "RECAUDO": "#059669",
                    "PROYECCION": "#3b82f6",
                },
                labels={
                    "value": "Monto ($)",
                    "variable": "Estado",
                },
            )

            st.plotly_chart(
                fig_admin_cart,
                use_container_width=True,
            )

    with t2:

        st.subheader(
            "📅 Consolidado Mes x Mes de Toda la Operación"
        )

        df_periodo_ger = preparar_periodo(df_all)
        anios_ger = sorted(
            [int(x) for x in df_periodo_ger["AÑO"].dropna().unique()]
        )
        anio_ger = st.selectbox(
            "Seleccione el año:",
            ["Todos"] + anios_ger,
            key="admin_anio_mes",
        )

        df_mes_filtrado = df_periodo_ger.copy()
        if anio_ger != "Todos":
            df_mes_filtrado = df_mes_filtrado[
                df_mes_filtrado["AÑO"] == int(anio_ger)
            ]

        df_mes_ger = (
            df_mes_filtrado
            .groupby(["MES_ORDEN", "MES_NOMBRE"], as_index=False)
            .agg({
                "CAPITAL": "sum",
                "RECAUDO": "sum",
                "PROYECCION": "sum",
            })
            .sort_values("MES_ORDEN")
        )

        fig_mes_g = px.bar(
            df_mes_ger,
            x="MES_NOMBRE",
            y=["RECAUDO", "PROYECCION"],
            barmode="group",
            category_orders={
                "MES_NOMBRE": list(MESES_CALENDARIO.keys())
            },
            title=(
                "<b>Consolidado de Recaudo vs "
                "Proyección Mensual</b>"
            ),
            color_discrete_map={
                "RECAUDO": "#059669",
                "PROYECCION": "#3b82f6",
            },
        )
        fig_mes_g.update_layout(
            xaxis_title="Mes",
            yaxis_title="Valor (COP)",
            yaxis_tickformat=",.0f",
            hovermode="x unified",
        )
        fig_mes_g.update_traces(
            hovertemplate="%{fullData.name}: $ %{y:,.0f} COP<extra></extra>"
        )
        st.plotly_chart(fig_mes_g, use_container_width=True)

    with t3:

        st.subheader("📋 Base General")

        mostrar_resumen_cartera(
            df_all,
            titulo="📦 Sumatoria Total de la Cartera (por Cartera)",
        )

        st.markdown("---")

        st.subheader("📋 Base General Desglosada")

        df_mostrar_admin = df_all.copy()
        df_mostrar_admin = preparar_para_mostrar(df_mostrar_admin)

        st.dataframe(
            df_mostrar_admin,
            use_container_width=True,
            hide_index=True,
            column_config={
                "CAPITAL": st.column_config.NumberColumn(
                    "Capital ($)", format="$ %,d", width="large"
                ),
                "# CLIENTES": st.column_config.NumberColumn(
                    "# Clientes", format="%,d", width="small"
                ),
                "RECAUDO": st.column_config.NumberColumn(
                    "Recaudo ($)", format="$ %,d", width="large"
                ),
                "PROYECCION": st.column_config.NumberColumn(
                    "Proyección ($)", format="$ %,d", width="large"
                ),
                "% EFECTIVIDAD": st.column_config.NumberColumn(
                    "% Efectividad", format="%.2f %%", width="small"
                ),
                "ESTIMADO CIERRE": st.column_config.NumberColumn(
                    "Estimado Cierre ($)", format="$ %,d", width="large"
                ),
            },
        )

    with t4:

        st.subheader(
            "⚙️ Panel Administrativo del Gerente General"
        )

        if "mensaje_exito_carga" in st.session_state:
            st.success(
                st.session_state.mensaje_exito_carga
            )
            del st.session_state["mensaje_exito_carga"]

        st.markdown(
            "### 📥 Cargue Masivo de Estructura Base "
            "(Excel / CSV)"
        )

        st.caption(
            "Suba el archivo con la estructura fija de "
            "carteras, directores, meses, capitales y "
            "número de clientes."
        )

        col_up1, col_up2 = st.columns([2, 1])

        with col_up1:

            uploaded_base = st.file_uploader(
                "Seleccione el archivo Excel (.xlsx) o CSV (.csv)",
                type=["xlsx", "csv"],
                key="cargador_excel_principal",
            )

        with col_up2:

            st.write("")
            st.write("")

            df_plantilla = pd.DataFrame(
                [
                    {
                        "DIRECTOR": "ADRIANA",
                        "CARTERA": "Popular 2tc 2024",
                        "MES": "ENERO 2024",
                        "CAPITAL": 220000000,
                        "# CLIENTES": 55,
                    },
                    {
                        "DIRECTOR": "ERIKA",
                        "CARTERA": "Popular 2tc 2025",
                        "MES": "ENERO 2025",
                        "CAPITAL": 225000000,
                        "# CLIENTES": 56,
                    },
                ]
            )

            buffer = io.BytesIO()

            with pd.ExcelWriter(
                buffer,
                engine="openpyxl",
            ) as writer:
                df_plantilla.to_excel(
                    writer,
                    index=False,
                    sheet_name="EstructuraBase",
                )

            st.download_button(
                label="📄 Descargar Plantilla de Ejemplo",
                data=buffer.getvalue(),
                file_name="Plantilla_Estructura_Base.xlsx",
                mime=(
                    "application/vnd.openxmlformats-officedocument."
                    "spreadsheetml.sheet"
                ),
                use_container_width=True,
            )

        if uploaded_base is not None:

            st.info(
                f"📁 Archivo detectado: "
                f"**{uploaded_base.name}**"
            )

            if st.button(
                "🚀 Cargar y Procesar Base de Datos",
                type="primary",
                use_container_width=True,
            ):

                try:

                    uploaded_base.seek(0)

                    if uploaded_base.name.endswith(".csv"):
                        df_cargado = pd.read_csv(
                            uploaded_base
                        )
                    else:
                        df_cargado = pd.read_excel(
                            uploaded_base,
                            engine="openpyxl",
                        )

                    df_cargado.columns = [
                        str(c).strip().upper()
                        for c in df_cargado.columns
                    ]

                    columnas_requeridas = {
                        "DIRECTOR",
                        "CARTERA",
                        "MES",
                        "CAPITAL",
                        "# CLIENTES",
                    }

                    columnas_actuales = set(
                        df_cargado.columns
                    )

                    if not columnas_requeridas.issubset(
                        columnas_actuales
                    ):

                        faltantes = (
                            columnas_requeridas
                            - columnas_actuales
                        )

                        st.error(
                            "❌ **Error en la estructura del "
                            f"archivo.** Faltan las columnas: "
                            f"`{faltantes}`"
                        )

                    else:

                        st.session_state.backup_db = (
                            st.session_state.base_meses_db.copy()
                        )

                        df_cargado["DIRECTOR"] = (
                            df_cargado["DIRECTOR"]
                            .astype(str)
                            .str.strip()
                            .str.upper()
                        )

                        df_cargado["CARTERA"] = (
                            df_cargado["CARTERA"]
                            .astype(str)
                            .str.strip()
                        )

                        df_cargado["MES"] = (
                            df_cargado["MES"]
                            .astype(str)
                            .str.strip()
                            .str.upper()
                        )

                        df_cargado["CAPITAL"] = (
                            pd.to_numeric(
                                df_cargado["CAPITAL"],
                                errors="coerce",
                            )
                            .fillna(0.0)
                        )

                        df_cargado["# CLIENTES"] = (
                            pd.to_numeric(
                                df_cargado["# CLIENTES"],
                                errors="coerce",
                            )
                            .fillna(0)
                            .astype(int)
                        )

                        df_cargado["RECAUDO"] = (
                            pd.to_numeric(
                                df_cargado["RECAUDO"],
                                errors="coerce",
                            ).fillna(0.0)
                            if "RECAUDO"
                            in df_cargado.columns
                            else 0.0
                        )

                        df_cargado["PROYECCION"] = (
                            pd.to_numeric(
                                df_cargado["PROYECCION"],
                                errors="coerce",
                            ).fillna(0.0)
                            if "PROYECCION"
                            in df_cargado.columns
                            else 0.0
                        )

                        df_cargado[
                            "% EFECTIVIDAD"
                        ] = (
                            (
                                df_cargado["RECAUDO"]
                                / df_cargado["CAPITAL"]
                                * 100
                            )
                            .fillna(0.0)
                            .replace(
                                [
                                    float("inf"),
                                    -float("inf"),
                                ],
                                0.0,
                            )
                        )

                        df_cargado[
                            "ESTIMADO CIERRE"
                        ] = (
                            df_cargado["RECAUDO"]
                            + df_cargado["PROYECCION"]
                        )

                        keys_a_eliminar = [
                            k
                            for k in st.session_state.keys()
                            if k.startswith("editor_")
                        ]

                        for k in keys_a_eliminar:
                            del st.session_state[k]

                        st.session_state.base_meses_db = (
                            df_cargado
                        )

                        st.session_state.mensaje_exito_carga = (
                            "🎉 ¡Base de datos cargada con éxito! "
                            f"Se procesaron {len(df_cargado)} registros."
                        )

                        st.rerun()

                except Exception as e:
                    st.error(
                        f"❌ Error procesando el archivo: `{str(e)}`"
                    )

        st.markdown("---")

        col_adm1, col_adm2 = st.columns(2)

        with col_adm1:

            st.markdown(
                "### 🔑 Modificación de Contraseñas"
            )

            usuario_a_modificar = st.selectbox(
                "Seleccione el usuario:",
                options=list(
                    st.session_state.usuarios_db.keys()
                ),
                format_func=lambda x: (
                    f"{st.session_state.usuarios_db[x]['nombre']} "
                    f"({x})"
                ),
            )

            nueva_clave = st.text_input(
                "Nueva contraseña:",
                type="password",
                key="new_pass_input",
            )

            confirmar_clave = st.text_input(
                "Confirmar nueva contraseña:",
                type="password",
                key="confirm_pass_input",
            )

            if st.button(
                "🔄 Actualizar Contraseña",
                type="primary",
            ):

                if not nueva_clave:
                    st.error(
                        "Por favor ingrese una contraseña válida."
                    )

                elif nueva_clave != confirmar_clave:
                    st.error(
                        "Las contraseñas no coinciden."
                    )

                else:

                    st.session_state.usuarios_db[
                        usuario_a_modificar
                    ]["hash"] = hacer_hash(
                        nueva_clave
                    )

                    st.success(
                        "¡Contraseña actualizada correctamente "
                        f"para **{st.session_state.usuarios_db[usuario_a_modificar]['nombre']}**!"
                    )

        with col_adm2:

            st.markdown(
                "### 🖼️ Actualizar Logo Corporativo"
            )

            uploaded_logo = st.file_uploader(
                "Cargar nuevo logo",
                type=["png", "jpg", "jpeg"],
            )

            if uploaded_logo is not None:

                img = Image.open(uploaded_logo)
                img.save(LOGO_PATH)

                st.success(
                    "¡Logo actualizado exitosamente!"
                )

                st.rerun()

        st.markdown("---")

        st.markdown(
            "### ⚠️ Reinicio de Base de Datos"
        )

        if "confirmar_reinicio" not in st.session_state:
            st.session_state.confirmar_reinicio = False

        if not st.session_state.confirmar_reinicio:

            if st.button(
                "🔴 Reiniciar Base de Datos",
                type="primary",
            ):
                st.session_state.confirmar_reinicio = True
                st.rerun()

        else:

            st.warning(
                "⚠️ ¿Está seguro de reiniciar la base de datos "
                "a sus valores predeterminados?"
            )

            col_alert1, col_alert2 = st.columns(2)

            with col_alert1:

                if st.button(
                    "✅ Sí, reiniciar",
                    type="primary",
                    use_container_width=True,
                ):

                    st.session_state.base_meses_db = (
                        inicializar_base_datos()
                    )

                    st.session_state.confirmar_reinicio = False
                    st.rerun()

            with col_alert2:

                if st.button(
                    "❌ Cancelar",
                    use_container_width=True,
                ):

                    st.session_state.confirmar_reinicio = False
                    st.rerun()
