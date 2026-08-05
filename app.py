import hashlib
import io
import os
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
    if df is None or df.empty:
        return df

    out = df.copy()
    out = out.loc[:, ~out.columns.duplicated()]
    out = out.reset_index(drop=True)

    columnas_texto = columnas_texto or [
        c for c in ["ID", "CARTERA", "DIRECTOR", "MES", "FECHA_CIERRE", "PERIODO_CIERRE"] if c in out.columns
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
# 2.1 RESUMEN CONSOLIDADO (SUMATORIA TOTAL POR CARTERA)
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
# 3. ESTILOS CSS PERSONALIZADOS (RESPONSIVE MOVIL & WEB)
# ============================================================
st.markdown(
    """
    <style>
    .main { background-color: #f8fafc; padding: 0.5rem; }
    h1 { color: #0f172a; font-family: 'Segoe UI', Roboto, sans-serif; font-weight: 800; font-size: clamp(1.4rem, 2.5vw, 2.2rem); }
    h2, h3 { color: #1e293b; font-weight: 700; font-size: clamp(1.1rem, 2vw, 1.6rem); }

    [data-testid="stMetric"] {
        background: linear-gradient(135deg, #ffffff 0%, #f1f5f9 100%);
        border: 1px solid #cbd5e1;
        border-radius: 12px;
        padding: 12px;
        box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
        border-top: 4px solid #2563eb;
        margin-bottom: 8px;
    }

    [data-testid="stMetricLabel"] {
        color: #475569;
        font-size: 0.8rem;
        font-weight: 800;
        text-transform: uppercase;
    }

    [data-testid="stMetricValue"] {
        color: #0f172a;
        font-weight: 900;
        line-height: 1.2;
    }

    [data-testid="stMetricValue"] > div {
        font-size: clamp(1.0rem, 2vw, 1.5rem) !important;
        word-break: break-word;
    }

    [data-testid="stSidebar"] { background-color: #0f172a; }
    [data-testid="stSidebar"] h1, [data-testid="stSidebar"] span, [data-testid="stSidebar"] p {
        color: #f8fafc !important;
    }
    
    /* Adaptabilidad de tablas en móvil */
    .stDataFrame { width: 100% !important; overflow-x: auto !important; }
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
# 5. BASE INICIAL Y CONEXIÓN SUPABASE
# ============================================================
DATOS_INICIALES_CARTERA = [{'CARTERA': 'Popular 3tc Citi 2022', 'DIRECTOR': 'ADRIANA', 'MES': 'NOVIEMBRE 2022', 'CAPITAL': 283011316.0, '# CLIENTES': 64, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Popular 3tc Citi 2022', 'DIRECTOR': 'CARLOS', 'MES': 'NOVIEMBRE 2022', 'CAPITAL': 0.0, '# CLIENTES': 0, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Popular 3tc Citi 2022', 'DIRECTOR': 'JEIMMY', 'MES': 'NOVIEMBRE 2022', 'CAPITAL': 542955485.0, '# CLIENTES': 132, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Popular 3tc Citi 2022', 'DIRECTOR': 'ERIKA', 'MES': 'NOVIEMBRE 2022', 'CAPITAL': 353845265.0, '# CLIENTES': 85, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}, {'CARTERA': 'Popular 3tc Citi 2022', 'DIRECTOR': 'MIGUEL', 'MES': 'NOVIEMBRE 2022', 'CAPITAL': 308957270.0, '# CLIENTES': 73, 'RECAUDO': 0.0, 'PROYECCION': 0.0, '% EFECTIVIDAD': 0.0, 'ESTIMADO CIERRE': 0.0}]

def inicializar_base_datos():
    datos = [registro.copy() for registro in DATOS_INICIALES_CARTERA]
    return pd.DataFrame(datos)[["CARTERA", "DIRECTOR", "MES", "CAPITAL", "# CLIENTES", "RECAUDO", "PROYECCION", "% EFECTIVIDAD", "ESTIMADO CIERRE"]]

def obtener_secret(nombre):
    try:
        return st.secrets[nombre]
    except Exception:
        return os.getenv(nombre)

SUPABASE_URL = obtener_secret("SUPABASE_URL")
SUPABASE_KEY = obtener_secret("SUPABASE_KEY")
SUPABASE_TABLE = "base_meses_db"
SUPABASE_HISTORICO_TABLE = "historico_cierres_db"

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
        "proyeccion": "PROYECCION", "efectividad": "% EFECTIVIDAD", "estimado_cierre": "ESTIMADO CIERRE"
    })

    for col in ["CARTERA", "DIRECTOR", "MES"]:
        df[col] = df[col].astype(str).str.strip() if col in df.columns else ""

    df["DIRECTOR"] = df["DIRECTOR"].str.upper()
    df["MES"] = df["MES"].str.upper()

    for col in ["CAPITAL", "RECAUDO", "PROYECCION", "% EFECTIVIDAD", "ESTIMADO CIERRE"]:
        df[col] = pd.to_numeric(df.get(col, 0.0), errors="coerce").fillna(0.0)

    df["# CLIENTES"] = pd.to_numeric(df.get("# CLIENTES", 0), errors="coerce").fillna(0).astype(int)
    df["% EFECTIVIDAD"] = ((df["RECAUDO"] / df["CAPITAL"] * 100).where(df["CAPITAL"] > 0, 0)).fillna(0)
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

def reiniciar_recaudo_proyeccion_supabase():
    payload = {"recaudo": 0.0, "proyeccion": 0.0, "efectividad": 0.0, "estimado_cierre": 0.0}
    supabase_request("PATCH", f"{SUPABASE_TABLE}?id=gt.0", json=payload, headers={"Prefer": "return=minimal"})

def guardar_cierre_historico_supabase(nombre_periodo):
    df_actual = dataframe_desde_supabase()
    if df_actual.empty:
        return False
    
    fecha_cierre = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
    registros_historico = []
    
    for _, r in df_actual.iterrows():
        registros_historico.append({
            "periodo_cierre": str(nombre_periodo),
            "fecha_cierre": fecha_cierre,
            "cartera": str(r["CARTERA"]),
            "director": str(r["DIRECTOR"]),
            "mes": str(r["MES"]),
            "capital": float(r["CAPITAL"]),
            "num_clientes": int(r["# CLIENTES"]),
            "recaudo": float(r["RECAUDO"]),
            "proyeccion": float(r["PROYECCION"]),
            "efectividad": float(r["% EFECTIVIDAD"]),
            "estimado_cierre": float(r["ESTIMADO CIERRE"])
        })
    
    supabase_request("POST", f"{SUPABASE_HISTORICO_TABLE}", json=registros_historico, headers={"Prefer": "return=minimal"})
    return True

def obtener_historico_supabase():
    registros = supabase_request("GET", f"{SUPABASE_HISTORICO_TABLE}?select=*&order=fecha_cierre.desc")
    if not registros:
        return pd.DataFrame()
    df = pd.DataFrame(registros).rename(columns={
        "id": "ID", "periodo_cierre": "PERIODO_CIERRE", "fecha_cierre": "FECHA_CIERRE",
        "cartera": "CARTERA", "director": "DIRECTOR", "mes": "MES",
        "capital": "CAPITAL", "num_clientes": "# CLIENTES", "recaudo": "RECAUDO",
        "proyeccion": "PROYECCION", "efectividad": "% EFECTIVIDAD", "estimado_cierre": "ESTIMADO CIERRE"
    })
    return df

# ============================================================
# 6. INICIALIZACIÓN Y AUTENTICACIÓN
# ============================================================
if "base_meses_db" not in st.session_state:
    try:
        df_supabase = dataframe_desde_supabase()
        st.session_state.base_meses_db = df_supabase if not df_supabase.empty else inicializar_base_datos()
    except Exception as e:
        st.error(f"❌ Error cargando base: {e}")
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

# LOGIN
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

# MENÚ LATERAL
mostrar_logo_sidebar()
st.sidebar.title(f"👤 {st.session_state.nombre}")
st.sidebar.caption(f"Rol: **{st.session_state.rol.upper()}**")
st.sidebar.markdown("---")

if st.sidebar.button("🔄 Actualizar datos desde Supabase", use_container_width=True):
    actualizar_sesion_desde_supabase()
    st.success("✅ Datos sincronizados.")
    st.rerun()

if st.sidebar.button("🚪 Cerrar Sesión", use_container_width=True):
    st.session_state.autenticado = False
    st.rerun()

PALETA_VIVA = ["#2563EB", "#7C3AED", "#DB2777", "#EA580C", "#059669", "#0284C7", "#D97706", "#DC2626", "#4F46E5", "#0D9488"]

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
    p_tab1, p_tab2, p_tab3, p_tab4 = st.tabs(["🏆 Ranking Director", "📊 Recaudo Cartera", "📈 Análisis Mensual", "📅 Consolidado Mes x Mes"])

    with p_tab1:
        st.subheader("🏆 Ranking de Recaudo por Director")
        df_dir = df_all.groupby("DIRECTOR", as_index=False)["RECAUDO"].sum().sort_values("RECAUDO", ascending=True)
        fig_rank_bar = px.bar(df_dir, x="RECAUDO", y="DIRECTOR", orientation="h", text="RECAUDO", color="DIRECTOR", color_discrete_sequence=PALETA_VIVA)
        fig_rank_bar.update_traces(texttemplate="$ %{x:,.0f} COP", textposition="outside", cliponaxis=False)
        fig_rank_bar.update_layout(autosize=True, showlegend=False, xaxis_title="Recaudo (COP)", yaxis_title="", margin=dict(l=10, r=110, t=30, b=30))
        st.plotly_chart(fig_rank_bar, use_container_width=True)

    with p_tab2:
        st.subheader("📊 Recaudo General por Cartera")
        df_cart_tot = df_all.groupby("CARTERA", as_index=False)["RECAUDO"].sum().sort_values("RECAUDO", ascending=True)
        fig_cart_bar = px.bar(df_cart_tot, x="RECAUDO", y="CARTERA", orientation="h", text="RECAUDO", color="CARTERA", color_discrete_sequence=px.colors.qualitative.Vivid)
        fig_cart_bar.update_traces(texttemplate="$ %{x:,.0f} COP", textposition="outside", cliponaxis=False)
        fig_cart_bar.update_layout(autosize=True, showlegend=False, xaxis_title="Recaudo (COP)", yaxis_title="", margin=dict(l=10, r=110, t=30, b=30))
        st.plotly_chart(fig_cart_bar, use_container_width=True)
        st.markdown("---")
        mostrar_resumen_cartera(df_all)

    with p_tab3:
        st.subheader("📈 Comportamiento Mensual por Cartera")
        carteras_disp = df_all["CARTERA"].dropna().unique().tolist()
        if carteras_disp:
            cartera_pres = st.selectbox("Seleccione Cartera:", carteras_disp)
            df_sub_cart = df_all[df_all["CARTERA"] == cartera_pres].groupby("MES", as_index=False).agg({"RECAUDO": "sum", "PROYECCION": "sum"})
            fig_sub_cart = px.bar(df_sub_cart, x="MES", y=["RECAUDO", "PROYECCION"], barmode="group", color_discrete_map={"RECAUDO": "#2563eb", "PROYECCION": "#f59e0b"})
            fig_sub_cart.update_layout(autosize=True, legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1), margin=dict(l=10, r=10, t=30, b=30))
            st.plotly_chart(fig_sub_cart, use_container_width=True)

    with p_tab4:
        st.subheader("📅 Consolidado General Mes por Mes")
        df_periodo = preparar_periodo(df_all)
        df_mes_tot = df_periodo.groupby(["MES_ORDEN", "MES_NOMBRE"], as_index=False).agg({"RECAUDO": "sum", "PROYECCION": "sum"}).sort_values("MES_ORDEN")
        fig_mes = px.bar(df_mes_tot, x="MES_NOMBRE", y=["RECAUDO", "PROYECCION"], barmode="group", color_discrete_map={"RECAUDO": "#2563eb", "PROYECCION": "#f59e0b"})
        fig_mes.update_layout(autosize=True, legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1), margin=dict(l=10, r=10, t=30, b=30))
        st.plotly_chart(fig_mes, use_container_width=True)

# ============================================================
# VISTA 2: DIRECTOR
# ============================================================
elif st.session_state.rol == "director":
    st.title(f"✍️ Gestión de Recaudos - {st.session_state.nombre}")
    director_actual = st.session_state.nombre.strip().upper()
    df_full = st.session_state.base_meses_db.copy()
    df_full["DIRECTOR_NORMALIZADO"] = df_full["DIRECTOR"].astype(str).apply(lambda x: x.split("(")[0].strip().upper() if pd.notna(x) else "")
    df_director = df_full[df_full["DIRECTOR_NORMALIZADO"] == director_actual]

    carteras_director = df_director["CARTERA"].dropna().unique().tolist()

    if not carteras_director:
        st.warning(f"⚠️ No hay carteras asociadas a **{director_actual}**.")
    else:
        tab1, tab2, tab3 = st.tabs(["📅 Captura por Cartera", "📋 Resumen Completo", "📦 Base General por Cartera"])

        with tab1:
            cartera_sel = st.selectbox("Seleccione Cartera:", carteras_director)
            df_sub = df_director[df_director["CARTERA"] == cartera_sel].copy()
            df_sub_editor = preparar_para_mostrar(df_sub)

            c1, c2, c3 = st.columns(3)
            c1.metric("Capital Asignado", formato_pesos(df_sub["CAPITAL"].sum()))
            c2.metric("Clientes Totales", formato_numero(df_sub["# CLIENTES"].sum()))
            c3.metric("Recaudo Acumulado", formato_pesos(df_sub["RECAUDO"].sum()))

            st.markdown("---")
            st.subheader(f"Desglose Mensual: **{cartera_sel}**")

            df_editado = st.data_editor(
                df_sub_editor[["ID", "MES", "CAPITAL", "# CLIENTES", "RECAUDO", "PROYECCION"]],
                disabled=["ID", "MES", "CAPITAL", "# CLIENTES"],
                use_container_width=True,
                key=f"editor_{director_actual}_{cartera_sel}",
                column_config={
                    "MES": st.column_config.TextColumn("Mes", width="medium"),
                    "CAPITAL": st.column_config.NumberColumn("Capital ($)", format="$ %,d", width="large"),
                    "# CLIENTES": st.column_config.NumberColumn("# Clientes", format="%,d", width="small"),
                    "RECAUDO": st.column_config.NumberColumn("Recaudo ($)", format="$ %,d", min_value=0.0, width="large"),
                    "PROYECCION": st.column_config.NumberColumn("Proyección ($)", format="$ %,d", min_value=0.0, width="large"),
                },
                hide_index=True,
            )

            if st.button("💾 Guardar Recaudos", type="primary", use_container_width=True):
                try:
                    for _, row in df_editado.iterrows():
                        actualizar_registro_supabase(row["ID"], row["RECAUDO"], row["PROYECCION"], row["CAPITAL"])
                    actualizar_sesion_desde_supabase()
                    st.success("✅ Cambios guardados en Supabase.")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Error al guardar: {e}")

        with tab2:
            st.subheader("📋 Historial Completo")
            st.dataframe(preparar_para_mostrar(df_director), use_container_width=True, hide_index=True)

        with tab3:
            mostrar_resumen_cartera(df_director, titulo="📦 Sumatoria Total por Cartera")

# ============================================================
# VISTA 3: GERENTE GENERAL (ADMIN)
# ============================================================
elif st.session_state.rol == "admin":
    st.title("📊 Panel Consolidado Gerencial")
    df_all = st.session_state.base_meses_db

    t1, t2, t3, t4, t5 = st.tabs([
        "📈 Dashboard Consolidado",
        "📅 Consolidado Mes x Mes",
        "📋 Base General",
        "📚 Histórico Cierres",
        "⚙️ Gestión y Cierre de Mes"
    ])

    with t1:
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Capital Total", formato_pesos(df_all["CAPITAL"].sum()))
        m2.metric("Total Recaudado", formato_pesos(df_all["RECAUDO"].sum()))
        m3.metric("Proyección Total", formato_pesos(df_all["PROYECCION"].sum()))
        efect = (df_all["RECAUDO"].sum() / df_all["CAPITAL"].sum() * 100) if df_all["CAPITAL"].sum() > 0 else 0
        m4.metric("% Efectividad Global", f"{efect:.2f}%")

        st.markdown("---")
        fig_ger = px.bar(df_all.groupby("DIRECTOR", as_index=False)["RECAUDO"].sum(), x="DIRECTOR", y="RECAUDO", color="DIRECTOR", title="<b>Recaudo por Director</b>", color_discrete_sequence=PALETA_VIVA)
        fig_ger.update_layout(autosize=True, margin=dict(l=10, r=10, t=30, b=30))
        st.plotly_chart(fig_ger, use_container_width=True)

    with t2:
        st.subheader("📅 Evolución Mes a Mes")
        df_periodo = preparar_periodo(df_all)
        df_mes_tot = df_periodo.groupby(["MES_ORDEN", "MES_NOMBRE"], as_index=False).agg({"RECAUDO": "sum", "PROYECCION": "sum"}).sort_values("MES_ORDEN")
        fig_mes_ger = px.bar(df_mes_tot, x="MES_NOMBRE", y=["RECAUDO", "PROYECCION"], barmode="group", color_discrete_map={"RECAUDO": "#2563eb", "PROYECCION": "#f59e0b"})
        fig_mes_ger.update_layout(autosize=True, legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1), margin=dict(l=10, r=10, t=30, b=30))
        st.plotly_chart(fig_mes_ger, use_container_width=True)

    with t3:
        st.subheader("📋 Base General Operativa")
        st.dataframe(preparar_para_mostrar(df_all), use_container_width=True, hide_index=True)

    with t4:
        st.subheader("📚 Consulta e Histórico de Cierres Mensuales")
        try:
            df_hist = obtener_historico_supabase()
            if df_hist.empty:
                st.info("No hay cierres mensuales registrados hasta la fecha.")
            else:
                periodos = df_hist["PERIODO_CIERRE"].unique().tolist()
                periodo_sel = st.selectbox("Filtrar por Periodo de Cierre:", ["Todos"] + periodos)
                
                df_hist_filtrado = df_hist if periodo_sel == "Todos" else df_hist[df_hist["PERIODO_CIERRE"] == periodo_sel]
                df_hist_mostrar = preparar_para_mostrar(df_hist_filtrado)
                
                st.dataframe(df_hist_mostrar, use_container_width=True, hide_index=True)
                
                # BOTÓN DE DESCARGA EXCEL
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine="openpyxl") as writer:
                    df_hist_filtrado.to_excel(writer, index=False, sheet_name="Historico")
                excel_data = output.getvalue()

                st.download_button(
                    label="📥 Descargar Histórico a Excel",
                    data=excel_data,
                    file_name=f"Historico_Cierres_{periodo_sel}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )
        except Exception as e:
            st.error(f"❌ Error al consultar el histórico: {e}")

    with t5:
        st.subheader("⚙️ Panel de Acciones Gerenciales")
        st.warning("⚠️ Las siguientes acciones afectarán la base global de datos.")

        col_cierre, col_reset = st.columns(2)

        with col_cierre:
            st.markdown("### 🔒 Cierre Mensual")
            st.caption("Guarda una fotografía de la información actual en la pestaña Histórico.")
            nombre_periodo_input = st.text_input("Nombre del periodo de cierre (Ej. ENERO 2026):", value=pd.Timestamp.now().strftime("%B %Y").upper())
            
            if st.button("🔒 Realizar Cierre de Mes", type="primary", use_container_width=True):
                if not nombre_periodo_input.strip():
                    st.error("Por favor ingrese un nombre de periodo válido.")
                else:
                    try:
                        exito = guardar_cierre_historico_supabase(nombre_periodo_input.strip().upper())
                        if exito:
                            st.success(f"✅ ¡Cierre de {nombre_periodo_input} registrado en la pestaña 'Histórico' correctamente!")
                            st.rerun()
                        else:
                            st.error("No hay registros para guardar en el cierre.")
                    except Exception as e:
                        st.error(f"❌ Error guardando el cierre: {e}")

        with col_reset:
            st.markdown("### 🔄 Reinicio Operativo")
            st.caption("Limpia los campos de Recaudo y Proyección dejándolos en $0 COP para iniciar un nuevo periodo.")
            
            if st.button("🔄 Reiniciar Recaudo y Proyección", type="secondary", use_container_width=True):
                try:
                    reiniciar_recaudo_proyeccion_supabase()
                    actualizar_sesion_desde_supabase()
                    st.success("✅ Recaudo y Proyección reiniciados a $0 COP con éxito.")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Error al reiniciar datos: {e}")
