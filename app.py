import hashlib
import io
import os
import pandas as pd
import plotly.express as px
import streamlit as st
from PIL import Image

# 1. Configuración de la página
st.set_page_config(
    page_title="Portal Digital de Recaudo - Citi Summa",
    page_icon="💼",
    layout="wide",
    initial_sidebar_state="expanded",
)


# --- FORMATOS FINANCIEROS Y NUMÉRICOS ---
def formato_pesos(val):
    if pd.isna(val) or val is None:
        return "$0"
    try:
        return f"${float(val):,.0f}".replace(",", ".")
    except (ValueError, TypeError):
        return "$0"


def formato_numero(val):
    if pd.isna(val) or val is None:
        return "0"
    try:
        return f"{int(val):,.0f}".replace(",", ".")
    except (ValueError, TypeError):
        return "0"


# 2. Estilos CSS Personalizados
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
    }
    [data-testid="stMetricLabel"] { color: #475569; font-size: 0.9rem; font-weight: 800; text-transform: uppercase; }
    [data-testid="stMetricValue"] { color: #0f172a; font-size: 1.7rem !important; font-weight: 900; }
    [data-testid="stSidebar"] { background-color: #0f172a; }
    [data-testid="stSidebar"] h1, [data-testid="stSidebar"] span, [data-testid="stSidebar"] p { color: #f8fafc !important; }
    </style>
""",
    unsafe_allow_html=True,
)

# 3. GESTIÓN DEL LOGO PERSISTENTE Y ESTILIZADO EN SIDEBAR
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


# --- DEFINICIÓN DE MESES POR DEFECTO Y ESPECÍFICOS ---
MESES_ESTANDAR = [
    ("MARZO 2023", 217450011, 53),
    ("ABRIL 2023", 252750319, 62),
    ("MAYO 2023", 199530664, 60),
    ("AGOSTO 2023", 330411006, 73),
    ("SEPTIEMBRE 2023", 214162693, 50),
    ("OCTUBRE 2023", 172146722, 40),
    ("NOVIEMBRE 2023", 156811901, 37),
]

MESES_ESPECIFICOS = {
    "Popular 3tc Citi 2022": [("NOVIEMBRE 2022", 217450011, 53)],
    "Popular 3tc Citi 2023": [("FEBRERO 2023", 252750319, 62)],
    "Popular 2026": [("ENERO 2026", 330411006, 73)],
    "Popular 2tc 2023": [
        ("SEPTIEMBRE 2023", 214162693, 50),
        ("NOVIEMBRE 2023", 156811901, 37),
        ("DICIEMBRE 2023", 180000000, 42),
    ],
    "Popular 2tc 2024": [
        ("ENERO 2024", 220000000, 55),
        ("FEBRERO 2024", 230000000, 58),
        ("MARZO 2024", 240000000, 60),
        ("ABRIL 2024", 210000000, 52),
        ("DICIEMBRE 2024", 250000000, 65),
    ],
    "Av Villas 2023": [
        ("ENERO 2023", 190000000, 48),
        ("MARZO 2023", 210000000, 50),
        ("JUNIO 2023", 205000000, 51),
        ("DICIEMBRE 2023", 230000000, 58),
    ],
    "Av Villas 2024": [
        ("ENERO 2024", 215000000, 53),
        ("FEBRERO 2024", 225000000, 56),
        ("MARZO 2024", 235000000, 59),
        ("DICIEMBRE 2024", 260000000, 64),
    ],
    "FICH": [("NOVIEMBRE 2021", 199530664, 60)],
    "Coovitel Propia": [("SEPTIEMBRE 2022", 214162693, 50)],
    "Coovitel Propia 2": [("ABRIL 2023", 172146722, 40)],
    "Popular 1": [("DICIEMBRE 2021", 156811901, 37)],
    "Popular 2": [("OCTUBRE 2022", 200000000, 45)],
}

TODAS_LAS_CARTERAS = [
    "Popular 3tc Citi 2022",
    "Popular 3tc Citi 2023",
    "Popular 2026",
    "Popular 2tc 2023",
    "Popular 2tc 2024",
    "Av Villas 2023",
    "Av Villas 2024",
    "FICH",
    "Coovitel Propia",
    "Coovitel Propia 2",
    "Popular 1",
    "Popular 2",
    "Popular 2tc 2025",
]

DIRECTORES = ["ADRIANA", "CARLOS", "JEIMMY", "ERIKA", "MIGUEL"]


def inicializar_base_datos():
    datos = []
    for director in DIRECTORES:
        for cartera in TODAS_LAS_CARTERAS:
            meses_a_usar = MESES_ESPECIFICOS.get(cartera, MESES_ESTANDAR)
            for mes, cap, cli in meses_a_usar:
                datos.append({
                    "CARTERA": cartera.strip(),
                    "DIRECTOR": director.strip().upper(),
                    "MES": mes.strip().upper(),
                    "CAPITAL": float(cap),
                    "# CLIENTES": int(cli),
                    "RECAUDO": 0.0,
                    "PROYECCION": 0.0,
                    "% EFECTIVIDAD": 0.0,
                    "ESTIMADO CIERRE": 0.0,
                })
    return pd.DataFrame(datos)


if "base_meses_db" not in st.session_state:
    st.session_state.base_meses_db = inicializar_base_datos()

if "backup_db" not in st.session_state:
    st.session_state.backup_db = None


# --- AUTENTICACIÓN Y BASE DE USUARIOS ---
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

# --- PANTALLA DE LOGIN ---
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

        if st.button("Iniciar Sesión", type="primary", use_container_width=True):
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

# --- MENÚ LATERAL ---
mostrar_logo_sidebar()
st.sidebar.title(f"👤 {st.session_state.nombre}")
st.sidebar.caption(f"Rol: **{st.session_state.rol.upper()}**")
st.sidebar.markdown("---")

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

# ==========================================
# VISTA 1: PRESIDENCIA
# ==========================================
if st.session_state.rol == "presidencia":
    st.title("🏛️ Panel de Control Presidencial")
    st.caption(
        "Vista ejecutiva de alto nivel, participaciones de mercado y tendencias globales"
    )

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
    p_tab1, p_tab2, p_tab3, p_tab4 = st.tabs([
        "🏆 Participación por Director",
        "📊 Recaudo por Cartera",
        "📈 Análisis por Cartera y Mes",
        "📅 Consolidado Mes x Mes",
    ])

    with p_tab1:
        st.subheader("🥇 Rendimiento y Participación por Director")
        df_dir = df_all.groupby("DIRECTOR", as_index=False).agg(
            {"CAPITAL": "sum", "RECAUDO": "sum", "PROYECCION": "sum"}
        )
        df_dir["DIRECTOR_BOLD"] = df_dir["DIRECTOR"].apply(lambda x: f"<b>{x}</b>")

        col_rank_g1, col_rank_g2 = st.columns([1, 1])
        with col_rank_g1:
            fig_pie_dir = px.pie(
                df_dir,
                names="DIRECTOR_BOLD",
                values="RECAUDO",
                hole=0.45,
                title="<b>% Participación de Recaudo por Director</b>",
                color_discrete_sequence=PALETA_VIVA,
            )
            fig_pie_dir.update_traces(
                textposition="inside",
                textinfo="percent+label",
                textfont=dict(size=14, color="white", family="Arial Black"),
                marker=dict(line=dict(color="#ffffff", width=2)),
            )
            st.plotly_chart(fig_pie_dir, use_container_width=True)

        with col_rank_g2:
            fig_rank_bar = px.bar(
                df_dir,
                x="RECAUDO",
                y="DIRECTOR_BOLD",
                orientation="h",
                text_auto=".2s",
                title="<b>Monto Total Recaudado ($) por Director</b>",
                color="DIRECTOR_BOLD",
                color_discrete_sequence=PALETA_VIVA,
            )
            fig_rank_bar.update_layout(
                yaxis={
                    "categoryorder": "total ascending",
                    "tickfont": dict(size=13, color="black"),
                },
                showlegend=False,
            )
            st.plotly_chart(fig_rank_bar, use_container_width=True)

    with p_tab2:
        st.subheader("📊 Recaudo General por Cartera")
        df_cart_tot = df_all.groupby("CARTERA", as_index=False).agg(
            {"RECAUDO": "sum"}
        )
        df_cart_tot["CARTERA_BOLD"] = df_cart_tot["CARTERA"].apply(
            lambda x: f"<b>{x}</b>"
        )
        fig_cart_bar = px.bar(
            df_cart_tot,
            x="CARTERA_BOLD",
            y="RECAUDO",
            color="CARTERA_BOLD",
            text_auto=".2s",
            title="<b>Recaudo Total ($) por Cada Cartera</b>",
            color_discrete_sequence=px.colors.qualitative.Vivid,
        )
        fig_cart_bar.update_layout(
            showlegend=False,
            xaxis=dict(tickangle=-45, tickfont=dict(size=13, color="black")),
        )
        st.plotly_chart(fig_cart_bar, use_container_width=True)

    with p_tab3:
        st.subheader("📈 Comportamiento Mensual por Cartera Específica")
        carteras_disp = df_all["CARTERA"].unique().tolist()
        if carteras_disp:
            cartera_pres = st.selectbox(
                "Seleccione una Cartera para Analizar:",
                carteras_disp,
                key="pres_cart_select",
            )
            df_sub_cart = (
                df_all[df_all["CARTERA"] == cartera_pres]
                .groupby("MES", as_index=False)
                .agg({"RECAUDO": "sum", "PROYECCION": "sum", "CAPITAL": "sum"})
            )
            df_sub_cart["MES_BOLD"] = df_sub_cart["MES"].apply(lambda x: f"<b>{x}</b>")

            fig_sub_cart = px.bar(
                df_sub_cart,
                x="MES_BOLD",
                y=["RECAUDO", "PROYECCION"],
                barmode="group",
                title=(
                    f"<b>Comportamiento Mensual de Recaudo vs Proyección - {cartera_pres}</b>"
                ),
                color_discrete_map={"RECAUDO": "#2563eb", "PROYECCION": "#f59e0b"},
                labels={"value": "Monto ($)", "variable": "Tipo"},
            )
            st.plotly_chart(fig_sub_cart, use_container_width=True)

    with p_tab4:
        st.subheader("📅 Consolidado General Mes por Mes")
        df_mes_tot = df_all.groupby("MES", as_index=False).agg(
            {"CAPITAL": "sum", "RECAUDO": "sum", "PROYECCION": "sum"}
        )
        df_mes_tot["MES_BOLD"] = df_mes_tot["MES"].apply(lambda x: f"<b>{x}</b>")
        fig_mes = px.bar(
            df_mes_tot,
            x="MES_BOLD",
            y=["RECAUDO", "PROYECCION"],
            barmode="group",
            title="<b>Evolución de Recaudo vs Proyección Mes x Mes</b>",
            color_discrete_map={"RECAUDO": "#2563eb", "PROYECCION": "#f59e0b"},
        )
        st.plotly_chart(fig_mes, use_container_width=True)

# ==========================================
# VISTA 2: DIRECTOR (NORMALIZACIÓN Y GUARDADO FIABLE)
# ==========================================
elif st.session_state.rol == "director":
    st.title(f"✍️ Gestión de Recaudos por Mes - {st.session_state.nombre}")

    director_actual = st.session_state.nombre.strip().upper()
    df_full = st.session_state.base_meses_db

    # Normalización del campo DIRECTOR para comparación insensible a diferencias de formato
    df_full["DIRECTOR_NORMALIZADO"] = (
        df_full["DIRECTOR"]
        .astype(str)
        .apply(lambda x: x.split("(")[0].strip().upper() if pd.notna(x) else "")
    )

    df_director = df_full[df_full["DIRECTOR_NORMALIZADO"] == director_actual]
    carteras_director = df_director["CARTERA"].dropna().unique().tolist()

    if not carteras_director:
        st.warning(
            f"⚠️ No hay carteras asociadas al usuario **{director_actual}** en la base actual."
        )
        st.info(
            "Si el Gerente cargó un archivo Excel, asegúrese de que el nombre del Director coincida exactamente."
        )
    else:
        tab1, tab2 = st.tabs(["📅 Captura por Cartera y Mes", "📋 Resumen Completo"])

        with tab1:
            cartera_sel = st.selectbox(
                "Seleccione la Cartera a Gestionar:", carteras_director
            )

            mask_cartera = (
                df_full["DIRECTOR_NORMALIZADO"] == director_actual
            ) & (df_full["CARTERA"] == cartera_sel)
            df_sub = df_full[mask_cartera].copy()

            c1, c2, c3 = st.columns(3)
            c1.metric("Capital Asignado", formato_pesos(df_sub["CAPITAL"].sum()))
            c2.metric("Clientes Totales", formato_numero(df_sub["# CLIENTES"].sum()))
            c3.metric("Recaudo Acumulado", formato_pesos(df_sub["RECAUDO"].sum()))

            st.markdown("---")
            st.subheader(f"Desglose Mensual: **{cartera_sel}**")

            df_editado = st.data_editor(
                df_sub[["MES", "CAPITAL", "# CLIENTES", "RECAUDO", "PROYECCION"]],
                disabled=["MES", "CAPITAL", "# CLIENTES"],
                use_container_width=True,
                key=f"editor_{director_actual}_{cartera_sel}",
                column_config={
                    "MES": st.column_config.TextColumn("Mes / Periodo"),
                    "CAPITAL": st.column_config.NumberColumn("Capital ($)", format="$ %,d"),
                    "# CLIENTES": st.column_config.NumberColumn("# Clientes", format="%,d"),
                    "RECAUDO": st.column_config.NumberColumn("Recaudo Actual ($)", format="$ %,d", min_value=0.0),
                    "PROYECCION": st.column_config.NumberColumn("Proyección ($)", format="$ %,d", min_value=0.0),
                },
                hide_index=True,
            )

            if st.button("💾 Guardar Recaudos de la Cartera", type="primary", use_container_width=True):
                filas_modificadas = 0

                # Procesa los cambios fila por fila
                for idx, row in df_editado.iterrows():
                    mes_val = str(row["MES"]).strip().upper()
                    rec = float(row["RECAUDO"]) if pd.notna(row["RECAUDO"]) else 0.0
                    proy = float(row["PROYECCION"]) if pd.notna(row["PROYECCION"]) else 0.0

                    mask_global = (
                        (st.session_state.base_meses_db["DIRECTOR"].astype(str).str.split("(").str[0].str.strip().str.upper() == director_actual) &
                        (st.session_state.base_meses_db["CARTERA"].astype(str).str.strip() == cartera_sel.strip()) &
                        (st.session_state.base_meses_db["MES"].astype(str).str.strip().str.upper() == mes_val)
                    )

                    if mask_global.any():
                        cap_val = st.session_state.base_meses_db.loc[mask_global, "CAPITAL"].values[0]

                        st.session_state.base_meses_db.loc[mask_global, "RECAUDO"] = rec
                        st.session_state.base_meses_db.loc[mask_global, "PROYECCION"] = proy
                        st.session_state.base_meses_db.loc[mask_global, "% EFECTIVIDAD"] = ((rec / cap_val * 100) if cap_val > 0 else 0.0)
                        st.session_state.base_meses_db.loc[mask_global, "ESTIMADO CIERRE"] = rec + proy
                        filas_modificadas += 1

                if filas_modificadas > 0:
                    st.success(f"✅ ¡Se guardaron correctamente {filas_modificadas} registros para {cartera_sel}!")
                    st.rerun()
                else:
                    st.error("⚠️ No se encontraron coincidencias exactas para actualizar la base de datos.")

        with tab2:
            st.subheader("📋 Historial de Recaudo Completo")
            mis_datos = df_director.drop(columns=["DIRECTOR_NORMALIZADO"], errors="ignore").copy()
            for col in ["CAPITAL", "RECAUDO", "PROYECCION", "ESTIMADO CIERRE"]:
                if col in mis_datos.columns:
                    mis_datos[col] = mis_datos[col].apply(formato_pesos)
            if "# CLIENTES" in mis_datos.columns:
                mis_datos["# CLIENTES"] = mis_datos["# CLIENTES"].apply(formato_numero)
            st.dataframe(mis_datos, use_container_width=True)

# ==========================================
# VISTA 3: GERENTE GENERAL (CARGUE, CONFIGURACIÓN Y DASHBOARD)
# ==========================================
elif st.session_state.rol == "admin":
    st.title("📊 Panel Consolidado Gerencial")
    df_all = st.session_state.base_meses_db

    t1, t2, t3, t4 = st.tabs([
        "📈 Dashboard Consolidado",
        "📅 Consolidado Mes x Mes",
        "📋 Base General",
        "⚙️ Configuración / Admin",
    ])

    with t1:
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Capital Total", formato_pesos(df_all["CAPITAL"].sum()))
        m2.metric("Total Recaudado", formato_pesos(df_all["RECAUDO"].sum()))
        m3.metric("Total Proyección", formato_pesos(df_all["PROYECCION"].sum()))
        m4.metric("Total Clientes", formato_numero(df_all["# CLIENTES"].sum()))

        st.markdown("---")
        col_g1, col_g2 = st.columns(2)

        with col_g1:
            st.subheader("📊 Recaudo por Cartera")
            df_cart = df_all.groupby("CARTERA", as_index=False)["RECAUDO"].sum()
            df_cart["CARTERA_BOLD"] = df_cart["CARTERA"].apply(lambda x: f"<b>{x}</b>")
            fig1 = px.bar(
                df_cart,
                x="CARTERA_BOLD",
                y="RECAUDO",
                color="CARTERA_BOLD",
                text_auto=".2s",
                color_discrete_sequence=px.colors.qualitative.Dark24,
            )
            fig1.update_layout(
                showlegend=False,
                xaxis=dict(tickangle=-45, tickfont=dict(size=12, color="black")),
            )
            st.plotly_chart(fig1, use_container_width=True)

        with col_g2:
            st.subheader("🥧 Participación % por Director")
            df_dir_g = df_all.groupby("DIRECTOR", as_index=False)["RECAUDO"].sum()
            df_dir_g["DIRECTOR_BOLD"] = df_dir_g["DIRECTOR"].apply(lambda x: f"<b>{x}</b>")
            fig2 = px.pie(
                df_dir_g,
                names="DIRECTOR_BOLD",
                values="RECAUDO",
                hole=0.4,
                color_discrete_sequence=PALETA_VIVA,
            )
            fig2.update_traces(
                textposition="inside",
                textinfo="percent+label",
                textfont=dict(size=13, color="white", family="Arial Black"),
            )
            st.plotly_chart(fig2, use_container_width=True)

        st.markdown("---")
        st.subheader("📈 Detalle Mensual de Recaudo por Cartera")
        carteras_admin_disp = df_all["CARTERA"].unique().tolist()
        if carteras_admin_disp:
            cartera_admin_sel = st.selectbox(
                "Filtrar Comportamiento Mensual por Cartera:",
                carteras_admin_disp,
                key="admin_cart_select",
            )

            df_cart_mes_admin = (
                df_all[df_all["CARTERA"] == cartera_admin_sel]
                .groupby("MES", as_index=False)
                .agg({"RECAUDO": "sum", "PROYECCION": "sum"})
            )
            df_cart_mes_admin["MES_BOLD"] = df_cart_mes_admin["MES"].apply(lambda x: f"<b>{x}</b>")

            fig_admin_cart = px.bar(
                df_cart_mes_admin,
                x="MES_BOLD",
                y=["RECAUDO", "PROYECCION"],
                barmode="group",
                title=f"<b>Evolución Mensual: {cartera_admin_sel}</b>",
                color_discrete_map={"RECAUDO": "#059669", "PROYECCION": "#3b82f6"},
                labels={"value": "Monto ($)", "variable": "Estado"},
            )
            st.plotly_chart(fig_admin_cart, use_container_width=True)

    with t2:
        st.subheader("📅 Consolidado Mes x Mes de Toda la Operación")
        df_mes_ger = df_all.groupby("MES", as_index=False).agg(
            {"CAPITAL": "sum", "RECAUDO": "sum", "PROYECCION": "sum"}
        )
        df_mes_ger["MES_BOLD"] = df_mes_ger["MES"].apply(lambda x: f"<b>{x}</b>")
        fig_mes_g = px.bar(
            df_mes_ger,
            x="MES_BOLD",
            y=["RECAUDO", "PROYECCION"],
            barmode="group",
            title="<b>Consolidado de Recaudo vs Proyección Mensual ($)</b>",
            color_discrete_map={"RECAUDO": "#059669", "PROYECCION": "#3b82f6"},
        )
        st.plotly_chart(fig_mes_g, use_container_width=True)

    with t3:
        st.subheader("📋 Base General Desglosada")
        df_mostrar_admin = df_all.copy()
        for col in ["CAPITAL", "RECAUDO", "PROYECCION", "ESTIMADO CIERRE"]:
            if col in df_mostrar_admin.columns:
                df_mostrar_admin[col] = df_mostrar_admin[col].apply(formato_pesos)
        if "# CLIENTES" in df_mostrar_admin.columns:
            df_mostrar_admin["# CLIENTES"] = df_mostrar_admin["# CLIENTES"].apply(formato_numero)
        st.dataframe(df_mostrar_admin, use_container_width=True)

    with t4:
        st.subheader("⚙️ Panel Administrativo del Gerente General")

        # --- MENSAJE PERSISTENTE DE ÉXITO TRAS RECARGAR ---
        if "mensaje_exito_carga" in st.session_state:
            st.success(st.session_state.mensaje_exito_carga)
            del st.session_state["mensaje_exito_carga"]

        st.markdown("### 📥 Cargue Masivo de Estructura Base (Excel / CSV)")
        st.caption("Suba el archivo con la estructura fija de carteras, directores, meses, capitales y número de clientes.")

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
            df_plantilla = pd.DataFrame([
                {
                    "DIRECTOR": "ADRIANA",
                    "CARTERA": "Popular 2tc 2024",
                    "MES": "ENERO 2024",
                    "CAPITAL": 220000000,
                    "# CLIENTES": 55,
                },
                {
                    "DIRECTOR": "ADRIANA",
                    "CARTERA": "Popular 2tc 2024",
                    "MES": "FEBRERO 2024",
                    "CAPITAL": 230000000,
                    "# CLIENTES": 58,
                },
                {
                    "DIRECTOR": "CARLOS",
                    "CARTERA": "Av Villas 2024",
                    "MES": "DICIEMBRE 2024",
                    "CAPITAL": 260000000,
                    "# CLIENTES": 64,
                },
            ])
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
                df_plantilla.to_excel(writer, index=False, sheet_name="EstructuraBase")

            st.download_button(
                label="📄 Descargar Plantilla de Ejemplo",
                data=buffer.getvalue(),
                file_name="Plantilla_Estructura_Base.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )

        if uploaded_base is not None:
            st.info(f"📁 Archivo detectado: **{uploaded_base.name}**")

            if st.button("🚀 Cargar y Procesar Base de Datos", type="primary", use_container_width=True):
                try:
                    # Garantizar lectura limpia desde el inicio
                    uploaded_base.seek(0)

                    if uploaded_base.name.endswith(".csv"):
                        df_cargado = pd.read_csv(uploaded_base)
                    else:
                        df_cargado = pd.read_excel(uploaded_base, engine="openpyxl")

                    df_cargado.columns = [str(c).strip().upper() for c in df_cargado.columns]

                    columnas_requeridas = {"DIRECTOR", "CARTERA", "MES", "CAPITAL", "# CLIENTES"}
                    columnas_actuales = set(df_cargado.columns)

                    if not columnas_requeridas.issubset(columnas_actuales):
                        faltantes = columnas_requeridas - columnas_actuales
                        st.error(f"❌ **Error en la estructura del archivo.** Faltan las columnas: `{faltantes}`")
                    else:
                        st.session_state.backup_db = st.session_state.base_meses_db.copy()

                        df_cargado["DIRECTOR"] = df_cargado["DIRECTOR"].astype(str).str.strip().str.upper()
                        df_cargado["CARTERA"] = df_cargado["CARTERA"].astype(str).str.strip()
                        df_cargado["MES"] = df_cargado["MES"].astype(str).str.strip().str.upper()

                        df_cargado["CAPITAL"] = pd.to_numeric(df_cargado["CAPITAL"], errors="coerce").fillna(0.0)
                        df_cargado["# CLIENTES"] = pd.to_numeric(df_cargado["# CLIENTES"], errors="coerce").fillna(0).astype(int)

                        df_cargado["RECAUDO"] = (
                            pd.to_numeric(df_cargado["RECAUDO"], errors="coerce").fillna(0.0)
                            if "RECAUDO" in df_cargado.columns
                            else 0.0
                        )
                        df_cargado["PROYECCION"] = (
                            pd.to_numeric(df_cargado["PROYECCION"], errors="coerce").fillna(0.0)
                            if "PROYECCION" in df_cargado.columns
                            else 0.0
                        )

                        df_cargado["% EFECTIVIDAD"] = (
                            (df_cargado["RECAUDO"] / df_cargado["CAPITAL"] * 100)
                            .fillna(0.0)
                            .replace([float("inf"), -float("inf")], 0.0)
                        )
                        df_cargado["ESTIMADO CIERRE"] = df_cargado["RECAUDO"] + df_cargado["PROYECCION"]

                        # --- LIMPIEZA AUTOMÁTICA DE CACHÉ DE TABLAS EDITABLES ---
                        keys_a_eliminar = [k for k in st.session_state.keys() if k.startswith("editor_")]
                        for k in keys_a_eliminar:
                            del st.session_state[k]

                        # Almacenar mensaje y base en session_state antes de recargar la vista
                        st.session_state.base_meses_db = df_cargado
                        st.session_state.mensaje_exito_carga = (
                            f"🎉 ¡Base de datos cargada con éxito! Se procesaron {len(df_cargado)} registros."
                        )
                        st.rerun()

                except Exception as e:
                    st.error(f"❌ Error procesando el archivo: `{str(e)}`")

        st.markdown("---")
        col_adm1, col_adm2 = st.columns(2)

        # MÓDULO 1: CAMBIO DE CONTRASEÑAS PERSISTENTE EN SESSION_STATE
        with col_adm1:
            st.markdown("### 🔑 Modificación de Contraseñas")
            usuario_a_modificar = st.selectbox(
                "Seleccione el usuario:",
                options=list(st.session_state.usuarios_db.keys()),
                format_func=lambda x: f"{st.session_state.usuarios_db[x]['nombre']} ({x})",
            )

            nueva_clave = st.text_input("Nueva contraseña:", type="password", key="new_pass_input")
            confirmar_clave = st.text_input("Confirmar nueva contraseña:", type="password", key="confirm_pass_input")

            if st.button("🔄 Actualizar Contraseña", type="primary"):
                if not nueva_clave:
                    st.error("Por favor ingrese una contraseña válida.")
                elif nueva_clave != confirmar_clave:
                    st.error("Las contraseñas no coinciden.")
                else:
                    st.session_state.usuarios_db[usuario_a_modificar]["hash"] = hacer_hash(nueva_clave)
                    st.success(f"¡Contraseña actualizada correctamente para **{st.session_state.usuarios_db[usuario_a_modificar]['nombre']}**!")

        # MÓDULO 2: LOGO Y REINICIO CON RESPALDO
        with col_adm2:
            st.markdown("### 🖼️ Actualizar Logo Corporativo")
            uploaded_logo = st.file_uploader("Cargar nuevo logo", type=["png", "jpg", "jpeg"])
            if uploaded_logo is not None:
                img = Image.open(uploaded_logo)
                img.save(LOGO_PATH)
                st.success("¡Logo actualizado exitosamente!")
                st.rerun()

            st.markdown("---")
            st.markdown("### ⚠️ Reinicio de Base de Datos")
            if "confirmar_reinicio" not in st.session_state:
                st.session_state.confirmar_reinicio = False

            if not st.session_state.confirmar_reinicio:
                if st.button("🔴 Reiniciar Base de Datos", type="primary"):
                    st.session_state.confirmar_reinicio = True
                    st.rerun()
            else:
                st.warning("⚠️ ¿Está seguro de reiniciar la base de datos?")
                col_alert1, col_alert2 = st.columns(2)

                with col_alert1:
                    if st.button("✅ SÍ, REINICIAR", use_container_width=True):
                        st.session_state.backup_db = st.session_state.base_meses_db.copy()
                        
                        # Limpiar caché de editores también al reiniciar
                        keys_a_eliminar = [k for k in st.session_state.keys() if k.startswith("editor_")]
                        for k in keys_a_eliminar:
                            del st.session_state[k]

                        st.session_state.base_meses_db = inicializar_base_datos()
                        st.session_state.confirmar_reinicio = False
                        st.rerun()

                with col_alert2:
                    if st.button("❌ CANCELAR", use_container_width=True):
                        st.session_state.confirmar_reinicio = False
                        st.rerun()
