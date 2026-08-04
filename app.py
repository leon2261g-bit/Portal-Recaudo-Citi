import hashlib
import io
import os
from datetime import datetime
import pandas as pd
import requests
import plotly.express as px
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
# 2. FORMATOS FINANCIEROS Y CALENDARIO
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

def formato_numero(val):
    if pd.isna(val) or val is None:
        return "0"
    try:
        return f"{int(val):,.0f}".replace(",", ".")
    except (ValueError, TypeError):
        return "0"

# ============================================================
# 2.0 SANEAMIENTO DE TIPOS DE DATOS
# ============================================================
def preparar_para_mostrar(df, columnas_texto=None, columnas_entero=None, columnas_decimal=None):
    if df is None or df.empty:
        return df

    out = df.copy()
    out = out.loc[:, ~out.columns.duplicated()]
    out = out.reset_index(drop=True)

    columnas_texto = columnas_texto or [
        c for c in ["ID", "CARTERA", "DIRECTOR", "MES", "FECHA_CIERRE", "MES_CIERRE"] if c in out.columns
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
            out[col] = pd.to_numeric(out[col], errors="coerce")
        else:
            out[col] = out[col].where(out[col].notna(), "").astype(str)

    for col in columnas_entero:
        out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0).astype("int64")

    for col in columnas_decimal:
        out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0.0).astype("float64")

    return out

# ============================================================
# 2.1 RESUMEN CONSOLIDADO POR CARTERA
# ============================================================
def resumen_por_cartera(df):
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

    resumen = resumen.sort_values("CAPITAL", ascending=False).reset_index(drop=True)

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
            "CARTERA": st.column_config.TextColumn("Cartera", width="medium"),
            "CAPITAL": st.column_config.NumberColumn("Capital Total ($)", format="$ %,d", width="large"),
            "# CLIENTES": st.column_config.NumberColumn("# Clientes", format="%,d", width="small"),
            "RECAUDO": st.column_config.NumberColumn("Recaudo Total ($)", format="$ %,d", width="large"),
            "PROYECCION": st.column_config.NumberColumn("Proyección Total ($)", format="$ %,d", width="large"),
            "% EFECTIVIDAD": st.column_config.NumberColumn("% Efectividad", format="%.2f %%", width="small"),
            "ESTIMADO CIERRE": st.column_config.NumberColumn("Estimado Cierre ($)", format="$ %,d", width="large"),
        },
    )

# ============================================================
# 3. ESTILOS CSS PERSONALIZADOS (RESPONSIVO MÓVIL Y WEB)
# ============================================================
st.markdown(
    """
    <style>
    .main { background-color: #f8fafc; }
    h1 { color: #0f172a; font-family: 'Segoe UI', Roboto, sans-serif; font-weight: 800; }
    h2, h3 { color: #1e293b; font-weight: 700; }

    /* Tarjetas KPI Metricas */
    [data-testid="stMetric"] {
        background: linear-gradient(135deg, #ffffff 0%, #f1f5f9 100%);
        border: 1px solid #cbd5e1;
        border-radius: 16px;
        padding: 16px;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.08);
        border-top: 4px solid #2563eb;
        overflow: visible !important;
    }

    [data-testid="stMetricLabel"] {
        color: #475569;
        font-size: 0.85rem;
        font-weight: 800;
        text-transform: uppercase;
    }

    [data-testid="stMetricValue"] > div {
        font-size: clamp(1.1rem, 1.8vw, 1.6rem) !important;
        font-weight: 900;
        color: #0f172a;
        word-break: break-word;
    }

    [data-testid="stSidebar"] { background-color: #0f172a; }
    [data-testid="stSidebar"] h1, [data-testid="stSidebar"] span, [data-testid="stSidebar"] p {
        color: #f8fafc !important;
    }

    /* Ajustes específicos para móviles */
    @media (max-width: 768px) {
        .main .block-container {
            padding-left: 0.8rem !important;
            padding-right: 0.8rem !important;
            padding-top: 1rem !important;
        }
        [data-testid="stMetric"] {
            padding: 10px !important;
            margin-bottom: 8px;
        }
        [data-testid="stMetricValue"] > div {
            font-size: 1.2rem !important;
        }
        /* Scrolleo horizontal automático en tablas móviles */
        [data-testid="stTable"], [data-testid="stDataFrame"], [data-testid="stDataEditor"] {
            overflow-x: auto !important;
        }
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
# 5. BASE INICIAL Y CONFIGURACIÓN SUPABASE
# ============================================================
DATOS_INICIALES_CARTERA = [{'CARTERA': 'Popular 3tc Citi 2022', 'DIRECTOR': 'ADRIANA', 'MES': 'NOVIEMBRE 2022', 'CAPITAL': 283011316.0, '# CLIENTES': 64, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Popular 3tc Citi 2022', 'DIRECTOR': 'CARLOS', 'MES': 'NOVIEMBRE 2022', 'CAPITAL': 0.0, '# CLIENTES': 0, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Popular 3tc Citi 2022', 'DIRECTOR': 'JEIMMY', 'MES': 'NOVIEMBRE 2022', 'CAPITAL': 542955485.0, '# CLIENTES': 132, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Popular 3tc Citi 2022', 'DIRECTOR': 'ERIKA', 'MES': 'NOVIEMBRE 2022', 'CAPITAL': 353845265.0, '# CLIENTES': 85, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Popular 3tc Citi 2022', 'DIRECTOR': 'MIGUEL', 'MES': 'NOVIEMBRE 2022', 'CAPITAL': 308957270.0, '# CLIENTES': 73, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Popular 3tc Citi 2023', 'DIRECTOR': 'ADRIANA', 'MES': 'FEBRERO 2023', 'CAPITAL': 363775986.0, '# CLIENTES': 86, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Popular 3tc Citi 2023', 'DIRECTOR': 'CARLOS', 'MES': 'FEBRERO 2023', 'CAPITAL': 16116359.0, '# CLIENTES': 4, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Popular 3tc Citi 2023', 'DIRECTOR': 'JEIMMY', 'MES': 'FEBRERO 2023', 'CAPITAL': 628826406.0, '# CLIENTES': 145, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Popular 3tc Citi 2023', 'DIRECTOR': 'ERIKA', 'MES': 'FEBRERO 2023', 'CAPITAL': 307198091.0, '# CLIENTES': 70, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Popular 3tc Citi 2023', 'DIRECTOR': 'MIGUEL', 'MES': 'FEBRERO 2023', 'CAPITAL': 317064819.0, '# CLIENTES': 74, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Popular 2026', 'DIRECTOR': 'ADRIANA', 'MES': 'ENERO 2026', 'CAPITAL': 3598011715.0, '# CLIENTES': 85, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Popular 2026', 'DIRECTOR': 'CARLOS', 'MES': 'ENERO 2026', 'CAPITAL': 7259787281.659, '# CLIENTES': 173, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Popular 2026', 'DIRECTOR': 'JEIMMY', 'MES': 'ENERO 2026', 'CAPITAL': 7479973316.0, '# CLIENTES': 173, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Popular 2026', 'DIRECTOR': 'ERIKA', 'MES': 'ENERO 2026', 'CAPITAL': 0.0, '# CLIENTES': 0, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Popular 2026', 'DIRECTOR': 'MIGUEL', 'MES': 'ENERO 2026', 'CAPITAL': 10896210066.994997, '# CLIENTES': 259, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}]

def inicializar_base_datos():
    datos = [registro.copy() for registro in DATOS_INICIALES_CARTERA]
    return pd.DataFrame(datos)[
        ["CARTERA", "DIRECTOR", "MES", "CAPITAL", "# CLIENTES", "RECAUDO", "PROYECCION", "% EFECTIVIDAD", "ESTIMADO CIERRE"]
    ]

def obtener_secret(nombre):
    try:
        return st.secrets[nombre]
    except Exception:
        return os.getenv(nombre)

SUPABASE_URL = obtener_secret("SUPABASE_URL")
SUPABASE_KEY = obtener_secret("SUPABASE_KEY")
SUPABASE_TABLE = "base_meses_db"
SUPABASE_TABLE_HIST = "historico_meses_db"

if not SUPABASE_URL or not SUPABASE_KEY:
    st.error("❌ No se encontraron las credenciales de Supabase en Secrets.")
    st.stop()

SUPABASE_URL = str(SUPABASE_URL).rstrip("/")
SUPABASE_HEADERS = {
    "apikey": str(SUPABASE_KEY),
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
}

COLUMNAS_APP = ["ID", "CARTERA", "DIRECTOR", "MES", "CAPITAL", "# CLIENTES", "RECAUDO", "PROYECCION", "% EFECTIVIDAD", "ESTIMADO CIERRE"]

def supabase_request(method, endpoint, **kwargs):
    url = f"{SUPABASE_URL}/rest/v1/{endpoint}"
    headers = dict(SUPABASE_HEADERS)
    headers.update(kwargs.pop("headers", {}))
    response = requests.request(method, url, headers=headers, timeout=30, **kwargs)
    if not response.ok:
        raise RuntimeError(f"Supabase HTTP {response.status_code}: {response.text[:1000]}")
    if not response.text:
        return []
    try:
        return response.json()
    except Exception:
        return []

def dataframe_desde_supabase():
    registros = supabase_request("GET", f"{SUPABASE_TABLE}?select=*&order=id.asc")
    if not registros:
        return pd.DataFrame(columns=["ID", *COLUMNAS_APP])

    df = pd.DataFrame(registros).rename(columns={
        "id": "ID", "cartera": "CARTERA", "director": "DIRECTOR", "mes": "MES",
        "capital": "CAPITAL", "num_clientes": "# CLIENTES", "recaudo": "RECAUDO",
        "proyeccion": "PROYECCION", "efectividad": "% EFECTIVIDAD", "estimado_cierre": "ESTIMADO CIERRE",
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

    df["% EFECTIVIDAD"] = ((df["RECAUDO"] / df["CAPITAL"] * 100).where(df["CAPITAL"] > 0, 0).fillna(0))
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
    supabase_request("PATCH", f"{SUPABASE_TABLE}?id=eq.{int(registro_id)}", json=payload, headers={"Prefer": "return=minimal"})

# ============================================================
# 5B. FUNCIONES PARA MANEJO DE HISTÓRICO Y CIERRE MENSUAL
# ============================================================
def cargar_historico_supabase():
    try:
        registros = supabase_request("GET", f"{SUPABASE_TABLE_HIST}?select=*&order=id.desc")
        if not registros:
            return pd.DataFrame()
        df = pd.DataFrame(registros).rename(columns={
            "id": "ID", "cartera": "CARTERA", "director": "DIRECTOR", "mes": "MES",
            "capital": "CAPITAL", "num_clientes": "# CLIENTES", "recaudo": "RECAUDO",
            "proyeccion": "PROYECCION", "efectividad": "% EFECTIVIDAD", "estimado_cierre": "ESTIMADO CIERRE",
            "fecha_cierre": "FECHA_CIERRE", "mes_cierre": "MES_CIERRE"
        })
        return df
    except Exception:
        if "historico_db_local" in st.session_state:
            return st.session_state.historico_db_local
        return pd.DataFrame()

def guardar_cierre_mensual():
    df_actual = st.session_state.base_meses_db.copy()
    fecha_hoy = datetime.now().strftime("%Y-%m-%d %H:%M")
    mes_cierre = datetime.now().strftime("%B %Y").upper()

    registros_cierre = []
    for _, r in df_actual.iterrows():
        registros_cierre.append({
            "cartera": str(r["CARTERA"]),
            "director": str(r["DIRECTOR"]),
            "mes": str(r["MES"]),
            "capital": float(r["CAPITAL"]),
            "num_clientes": int(r["# CLIENTES"]),
            "recaudo": float(r["RECAUDO"]),
            "proyeccion": float(r["PROYECCION"]),
            "efectividad": float(r["% EFECTIVIDAD"]),
            "estimado_cierre": float(r["ESTIMADO CIERRE"]),
            "fecha_cierre": fecha_hoy,
            "mes_cierre": mes_cierre,
        })

    try:
        supabase_request("POST", SUPABASE_TABLE_HIST, json=registros_cierre, headers={"Prefer": "return=minimal"})
    except Exception as e:
        df_actual["FECHA_CIERRE"] = fecha_hoy
        df_actual["MES_CIERRE"] = mes_cierre
        if "historico_db_local" not in st.session_state or st.session_state.historico_db_local is None:
            st.session_state.historico_db_local = df_actual
        else:
            st.session_state.historico_db_local = pd.concat([st.session_state.historico_db_local, df_actual], ignore_index=True)

# ============================================================
# 6. INICIALIZACIÓN DE SESIÓN Y AUTENTICACIÓN
# ============================================================
if "base_meses_db" not in st.session_state:
    try:
        df_supabase = dataframe_desde_supabase()
        if not df_supabase.empty:
            st.session_state.base_meses_db = df_supabase
        else:
            st.session_state.base_meses_db = inicializar_base_datos()
    except Exception as e:
        st.error(f"❌ Error cargando la base desde Supabase: {e}")
        st.stop()

def hacer_hash(password):
    return hashlib.sha256(str.encode(password)).hexdigest()

if "usuarios_db" not in st.session_state:
    st.session_state.usuarios_db = {
        "presidencia": {"hash": hacer_hash("presidencia2026"), "nombre": "Presidencia Ejecutiva", "rol": "presidencia"},
        "gerente": {"hash": hacer_hash("gerencia2026"), "nombre": "Gerente General", "rol": "admin"},
        "adriana": {"hash": hacer_hash("adriana123"), "nombre": "ADRIANA", "rol": "director"},
        "carlos": {"hash": hacer_hash("carlos123"), "nombre": "CARLOS", "rol": "director"},
        "jeimmy": {"hash": hacer_hash("jeimmy123"), "nombre": "JEIMMY", "rol": "director"},
        "erika": {"hash": hacer_hash("erika123"), "nombre": "ERIKA", "rol": "director"},
        "miguel": {"hash": hacer_hash("miguel123"), "nombre": "MIGUEL", "rol": "director"},
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
        logo_login = cargar_logo()
        if logo_login is not None:
            st.image(logo_login, use_container_width=True)
        else:
            st.title("🏛️ CITI SUMMA")
            st.caption("SERVICIOS LEGALES")

        st.markdown("### 🔐 Portal Digital de Recaudo")
        user_input = st.text_input("Usuario:").strip().lower()
        pass_input = st.text_input("Contraseña:", type="password")

        if st.button("Iniciar Sesión", type="primary", use_container_width=True):
            usuarios = st.session_state.usuarios_db
            if user_input in usuarios and usuarios[user_input]["hash"] == hacer_hash(pass_input):
                st.session_state.autenticado = True
                st.session_state.usuario = user_input
                st.session_state.rol = usuarios[user_input]["rol"]
                st.session_state.nombre = usuarios[user_input]["nombre"]
                st.rerun()
            else:
                st.error("Usuario o contraseña incorrectos")
    st.stop()

# ============================================================
# 9. MENÚ LATERAL Y NAVEGACIÓN
# ============================================================
mostrar_logo_sidebar()
st.sidebar.title(f"👤 {st.session_state.nombre}")
st.sidebar.caption(f"Rol: **{st.session_state.rol.upper()}**")
st.sidebar.markdown("---")

if st.sidebar.button("🔄 Actualizar datos", use_container_width=True):
    try:
        actualizar_sesion_desde_supabase()
        st.success("✅ Datos actualizados.")
        st.rerun()
    except Exception as e:
        st.error(f"❌ Error: {e}")

if st.sidebar.button("🚪 Cerrar Sesión", use_container_width=True):
    st.session_state.autenticado = False
    st.rerun()

PALETA_VIVA = ["#2563EB", "#7C3AED", "#DB2777", "#EA580C", "#059669", "#0284C7", "#D97706", "#DC2626"]

# ============================================================
# COMPONENTE REUTILIZABLE: TABLA DE HISTÓRICOS
# ============================================================
def renderizar_pestaña_historico():
    st.subheader("📜 Histórico de Cierres Mensuales")
    df_hist = cargar_historico_supabase()

    if df_hist.empty:
        st.info("ℹ️ Aún no se han ejecutado cierres mensuales en la plataforma.")
        return

    df_hist = preparar_para_mostrar(df_hist)

    fechas_disponibles = ["Todas"] + sorted(df_hist["FECHA_CIERRE"].dropna().unique().tolist(), reverse=True)
    col_f1, col_f2 = st.columns([2, 1])
    with col_f1:
        fecha_sel = st.selectbox("Filtrar por Cierre (Fecha / Hora):", fechas_disponibles)

    df_filtrado_hist = df_hist.copy()
    if fecha_sel != "Todas":
        df_filtrado_hist = df_filtrado_hist[df_filtrado_hist["FECHA_CIERRE"] == fecha_sel]

    st.dataframe(
        df_filtrado_hist,
        use_container_width=True,
        hide_index=True,
        column_config={
            "FECHA_CIERRE": st.column_config.TextColumn("Fecha Cierre", width="medium"),
            "CARTERA": st.column_config.TextColumn("Cartera", width="medium"),
            "DIRECTOR": st.column_config.TextColumn("Director", width="small"),
            "CAPITAL": st.column_config.NumberColumn("Capital ($)", format="$ %,d"),
            "RECAUDO": st.column_config.NumberColumn("Recaudo ($)", format="$ %,d"),
            "PROYECCION": st.column_config.NumberColumn("Proyección ($)", format="$ %,d"),
            "% EFECTIVIDAD": st.column_config.NumberColumn("% Efectividad", format="%.2f %%"),
        },
    )

    # Generar Excel con Pestañas para descarga
    buffer_excel = io.BytesIO()
    with pd.ExcelWriter(buffer_excel, engine="openpyxl") as writer:
        df_filtrado_hist.to_excel(writer, index=False, sheet_name="Detalle_Historico")
        resumen_hist = resumen_por_cartera(df_filtrado_hist)
        resumen_hist.to_excel(writer, index=False, sheet_name="Resumen_Por_Cartera")

    st.download_button(
        label="📥 Descargar Reporte Histórico en Excel",
        data=buffer_excel.getvalue(),
        file_name=f"Historico_Recaudo_CitiSumma_{datetime.now().strftime('%Y%m%d')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="primary",
        use_container_width=True,
    )

# ============================================================
# VISTA 1: PRESIDENCIA
# ============================================================
if st.session_state.rol == "presidencia":
    st.title("🏛️ Panel de Control Presidencial")
    df_all = st.session_state.base_meses_db.copy()

    cap_tot = df_all["CAPITAL"].sum()
    rec_tot = df_all["RECAUDO"].sum()
    proy_tot = df_all["PROYECCION"].sum()
    efect_global = (rec_tot / cap_tot * 100) if cap_tot > 0 else 0.0

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Capital Global", formato_pesos(cap_tot))
    m2.metric("Recaudo Total", formato_pesos(rec_tot))
    m3.metric("Proyección Total", formato_pesos(proy_tot))
    m4.metric("% Efectividad Global", f"{efect_global:.2f}%")

    st.markdown("---")
    p_tab1, p_tab2, p_tab3, p_tab4, p_tab5 = st.tabs([
        "🏆 Ranking Director", "📊 Recaudo Cartera", "📈 Comportamiento Mensual", "📅 Consolidado Mes x Mes", "📜 Histórico Cierres"
    ])

    with p_tab1:
        df_dir = df_all.groupby("DIRECTOR", as_index=False)["RECAUDO"].sum().sort_values("RECAUDO", ascending=True)
        fig_rank = px.bar(df_dir, x="RECAUDO", y="DIRECTOR", orientation="h", text_auto=".2s", title="<b>Ranking Recaudo por Director</b>")
        fig_rank.update_layout(autosize=True, margin=dict(l=10, r=10, t=40, b=10))
        st.plotly_chart(fig_rank, use_container_width=True)

    with p_tab2:
        df_cart = df_all.groupby("CARTERA", as_index=False)["RECAUDO"].sum().sort_values("RECAUDO", ascending=True)
        fig_cart = px.bar(df_cart, x="RECAUDO", y="CARTERA", orientation="h", text_auto=".2s", title="<b>Recaudo por Cartera</b>")
        fig_cart.update_layout(autosize=True, margin=dict(l=10, r=10, t=40, b=10))
        st.plotly_chart(fig_cart, use_container_width=True)
        mostrar_resumen_cartera(df_all)

    with p_tab3:
        carteras_disp = df_all["CARTERA"].dropna().unique().tolist()
        if carteras_disp:
            cartera_pres = st.selectbox("Seleccione Cartera:", carteras_disp)
            df_sub = df_all[df_all["CARTERA"] == cartera_pres].groupby("MES", as_index=False).agg({"RECAUDO": "sum", "PROYECCION": "sum"})
            fig_sub = px.bar(df_sub, x="MES", y=["RECAUDO", "PROYECCION"], barmode="group", title=f"<b>Evolución: {cartera_pres}</b>")
            fig_sub.update_layout(autosize=True, margin=dict(l=10, r=10, t=40, b=10))
            st.plotly_chart(fig_sub, use_container_width=True)

    with p_tab4:
        df_periodo = preparar_periodo(df_all)
        df_mes_tot = df_periodo.groupby(["MES_ORDEN", "MES_NOMBRE"], as_index=False).agg({"RECAUDO": "sum", "PROYECCION": "sum"}).sort_values("MES_ORDEN")
        fig_mes = px.bar(df_mes_tot, x="MES_NOMBRE", y=["RECAUDO", "PROYECCION"], barmode="group", title="<b>Evolución Mensual Operativa</b>")
        fig_mes.update_layout(autosize=True, margin=dict(l=10, r=10, t=40, b=10))
        st.plotly_chart(fig_mes, use_container_width=True)

    with p_tab5:
        renderizar_pestaña_historico()

# ============================================================
# VISTA 2: DIRECTOR
# ============================================================
elif st.session_state.rol == "director":
    st.title(f"✍️ Gestión de Recaudos - {st.session_state.nombre}")
    director_actual = st.session_state.nombre.strip().upper()
    df_full = st.session_state.base_meses_db.copy()

    df_full["DIRECTOR_NORMALIZADO"] = df_full["DIRECTOR"].astype(str).apply(lambda x: x.split("(")[0].strip().upper() if pd.notna(x) else "")
    df_director = df_full[df_full["DIRECTOR_NORMALIZADO"] == director_actual]
    carteras_director = df_director["CARTERA"].astype(str).str.strip().dropna().unique().tolist()

    if not carteras_director:
        st.warning(f"⚠️ No hay carteras asociadas al usuario **{director_actual}**.")
    else:
        tab1, tab2, tab3 = st.tabs(["📅 Captura Recaudo", "📋 Historial", "📜 Cierres Históricos"])

        with tab1:
            cartera_sel = st.selectbox("Seleccione Cartera:", carteras_director)
            mask_cartera = (df_full["DIRECTOR_NORMALIZADO"] == director_actual) & (df_full["CARTERA"].astype(str).str.strip() == cartera_sel)
            df_sub = df_full[mask_cartera].copy()
            df_sub_editor = preparar_para_mostrar(df_sub)

            c1, c2, c3 = st.columns(3)
            c1.metric("Capital Asignado", formato_pesos(df_sub["CAPITAL"].sum()))
            c2.metric("Clientes Totales", formato_numero(df_sub["# CLIENTES"].sum()))
            c3.metric("Recaudo Acumulado", formato_pesos(df_sub["RECAUDO"].sum()))

            st.markdown("---")
            df_editado = st.data_editor(
                df_sub_editor[["ID", "MES", "CAPITAL", "# CLIENTES", "RECAUDO", "PROYECCION"]],
                disabled=["ID", "MES", "CAPITAL", "# CLIENTES"],
                use_container_width=True,
                key=f"editor_{director_actual}_{cartera_sel}",
                hide_index=True,
            )

            if st.button("💾 Guardar Recaudos", type="primary", use_container_width=True):
                for _, row in df_editado.iterrows():
                    actualizar_registro_supabase(row["ID"], row["RECAUDO"], row["PROYECCION"], row["CAPITAL"])
                actualizar_sesion_desde_supabase()
                st.success("✅ ¡Recaudos guardados con éxito!")
                st.rerun()

        with tab2:
            st.dataframe(preparar_para_mostrar(df_director), use_container_width=True, hide_index=True)

        with tab3:
            renderizar_pestaña_historico()

# ============================================================
# VISTA 3: GERENTE GENERAL
# ============================================================
elif st.session_state.rol == "admin":
    st.title("📊 Panel Consolidado Gerencial")
    df_all = st.session_state.base_meses_db

    t1, t2, t3, t4, t5 = st.tabs([
        "📈 Dashboard Consolidado", "📅 Consolidado Mes x Mes", "📋 Base General", "📜 Histórico", "⚙️ Configuración / Admin"
    ])

    with t1:
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Capital Total", formato_pesos(df_all["CAPITAL"].sum()))
        m2.metric("Total Recaudado", formato_pesos(df_all["RECAUDO"].sum()))
        m3.metric("Total Proyección", formato_pesos(df_all["PROYECCION"].sum()))
        m4.metric("Total Clientes", formato_numero(df_all["# CLIENTES"].sum()))

        st.markdown("---")
        df_cart = df_all.groupby("CARTERA", as_index=False)["RECAUDO"].sum().sort_values("RECAUDO", ascending=True)
        fig1 = px.bar(df_cart, x="RECAUDO", y="CARTERA", orientation="h", text_auto=".2s", title="<b>Recaudo Total por Cartera</b>")
        fig1.update_layout(autosize=True, margin=dict(l=10, r=10, t=40, b=10))
        st.plotly_chart(fig1, use_container_width=True)

    with t2:
        df_periodo_ger = preparar_periodo(df_all)
        df_mes_ger = df_periodo_ger.groupby(["MES_ORDEN", "MES_NOMBRE"], as_index=False).agg({"RECAUDO": "sum", "PROYECCION": "sum"}).sort_values("MES_ORDEN")
        fig_mes_g = px.bar(df_mes_ger, x="MES_NOMBRE", y=["RECAUDO", "PROYECCION"], barmode="group", title="<b>Consolidado Mensual</b>")
        fig_mes_g.update_layout(autosize=True, margin=dict(l=10, r=10, t=40, b=10))
        st.plotly_chart(fig_mes_g, use_container_width=True)

    with t3:
        mostrar_resumen_cartera(df_all)
        st.markdown("---")
        st.dataframe(preparar_para_mostrar(df_all), use_container_width=True, hide_index=True)

    with t4:
        renderizar_pestaña_historico()

    with t5:
        st.subheader("⚙️ Panel de Control y Cierre Mensual")

        # MÓDULO DE CIERRE MENSUAL
        st.markdown("### 🔒 Ejecutar Cierre Operativo Mensual")
        st.caption("Guarda una instantánea histórica permanente de las cifras actuales para consulta y descarga futura.")
        if st.button("🔒 Ejecutar Cierre Mensual de Cifras", type="primary", use_container_width=True):
            guardar_cierre_mensual()
            st.success("🎉 ¡Cierre mensual ejecutado correctamente! Los datos se guardaron en la pestaña Histórico.")
            st.rerun()

        st.markdown("---")
        st.markdown("### 🔑 Modificación de Contraseñas")
        usuario_a_modificar = st.selectbox("Seleccione el usuario:", options=list(st.session_state.usuarios_db.keys()))
        nueva_clave = st.text_input("Nueva contraseña:", type="password")
        if st.button("🔄 Actualizar Contraseña", type="primary"):
            if nueva_clave:
                st.session_state.usuarios_db[usuario_a_modificar]["hash"] = hacer_hash(nueva_clave)
                st.success("¡Contraseña actualizada correctamente!")
