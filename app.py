import hashlib
import io
import os
import pandas as pd
import plotly.express as px
import requests
import streamlit as st
from PIL import Image

# ============================================================
# 1. CONFIGURACIÓN
# ============================================================
st.set_page_config(
    page_title="Portal Digital de Recaudo - Citi Summa",
    page_icon="💼",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ============================================================
# 2. SUPABASE
# ============================================================
def obtener_secret(nombre):
    try:
        return st.secrets[nombre]
    except Exception:
        return os.getenv(nombre)

SUPABASE_URL = obtener_secret("SUPABASE_URL")
SUPABASE_KEY = obtener_secret("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    st.error(
        "❌ No se encontraron las credenciales de Supabase. "
        "Configura SUPABASE_URL y SUPABASE_KEY en Streamlit Cloud → Settings → Secrets."
    )
    st.stop()

SUPABASE_URL = str(SUPABASE_URL).rstrip("/")
SUPABASE_TABLE = "base_meses_db"

SUPABASE_HEADERS = {
    "apikey": str(SUPABASE_KEY),
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
}

def supabase_request(method, endpoint, **kwargs):
    """Realiza una petición REST a Supabase con manejo básico de errores."""
    url = f"{SUPABASE_URL}/rest/v1/{endpoint}"
    headers = dict(SUPABASE_HEADERS)
    headers.update(kwargs.pop("headers", {}))
    response = requests.request(
        method,
        url,
        headers=headers,
        timeout=30,
        **kwargs,
    )
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

# ============================================================
# 3. FORMATOS
# ============================================================
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

# ============================================================
# 4. ESTILOS
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
    }
    [data-testid="stMetricLabel"] {
        color: #475569;
        font-size: 0.9rem;
        font-weight: 800;
        text-transform: uppercase;
    }
    [data-testid="stMetricValue"] {
    color: #0f172a;
    font-size: 1.25rem !important;
    font-weight: 900;
    white-space: nowrap;
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
# 5. LOGO
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
# 6. SUPABASE ↔ DATAFRAME
# ============================================================
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

def dataframe_desde_supabase():
    """Carga SIEMPRE la versión actual de la tabla base_meses_db."""
    registros = supabase_request(
        "GET",
        f"{SUPABASE_TABLE}?select=*&order=id.asc",
    )

    if not registros:
        return pd.DataFrame(columns=COLUMNAS_APP)

    df = pd.DataFrame(registros)

    renombrar = {
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
    }
    df = df.rename(columns=renombrar)

    for col in ["CARTERA", "DIRECTOR", "MES"]:
        if col not in df.columns:
            df[col] = ""
        df[col] = df[col].astype(str).str.strip()

    df["DIRECTOR"] = df["DIRECTOR"].str.upper()
    df["MES"] = df["MES"].str.upper()

    for col in ["CAPITAL", "RECAUDO", "PROYECCION", "ESTIMADO CIERRE", "% EFECTIVIDAD"]:
        if col not in df.columns:
            df[col] = 0.0
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)

    if "# CLIENTES" not in df.columns:
        df["# CLIENTES"] = 0
    df["# CLIENTES"] = pd.to_numeric(
        df["# CLIENTES"], errors="coerce"
    ).fillna(0).astype(int)

    if "ID" not in df.columns:
        df["ID"] = None

    # Recalcular únicamente los campos derivados para mantener consistencia.
    df["% EFECTIVIDAD"] = (
        (df["RECAUDO"] / df["CAPITAL"] * 100)
        .where(df["CAPITAL"] > 0, 0)
        .fillna(0)
    )
    df["ESTIMADO CIERRE"] = df["RECAUDO"] + df["PROYECCION"]

    return df[COLUMNAS_APP].copy()

def actualizar_sesion_desde_supabase():
    """Fuente oficial: Supabase. Reemplaza la copia local de la sesión."""
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

def upsert_dataframe_supabase(df):
    """Carga o actualiza la estructura base usando cartera+director+mes."""
    registros = []

    for _, row in df.iterrows():
        registros.append({
            "cartera": str(row["CARTERA"]).strip(),
            "director": str(row["DIRECTOR"]).strip().upper(),
            "mes": str(row["MES"]).strip().upper(),
            "capital": float(row["CAPITAL"]),
            "num_clientes": int(row["# CLIENTES"]),
            "recaudo": float(row.get("RECAUDO", 0.0)),
            "proyeccion": float(row.get("PROYECCION", 0.0)),
            "efectividad": float(row.get("% EFECTIVIDAD", 0.0)),
            "estimado_cierre": float(row.get("ESTIMADO CIERRE", 0.0)),
        })

    if not registros:
        return

    # La restricción UNIQUE (cartera, director, mes) permite el upsert.
    supabase_request(
        "POST",
        SUPABASE_TABLE,
        json=registros,
        headers={
            "Prefer": "resolution=merge-duplicates,return=minimal"
        },
    )

def eliminar_todos_registros_supabase():
    # Elimina todos los registros existentes.
    supabase_request(
        "DELETE",
        f"{SUPABASE_TABLE}?id=not.is.null",
        headers={"Prefer": "return=minimal"},
    )

# ============================================================
# 7. CARGA INICIAL DESDE SUPABASE
# ============================================================
if "base_meses_db" not in st.session_state:
    try:
        st.session_state.base_meses_db = dataframe_desde_supabase()
    except Exception as e:
        st.error(f"❌ Error cargando la base desde Supabase: {e}")
        st.stop()

if "backup_db" not in st.session_state:
    st.session_state.backup_db = None

# ============================================================
# 8. AUTENTICACIÓN
# ============================================================
def hacer_hash(password):
    return hashlib.sha256(str(password).encode()).hexdigest()

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
# 9. LOGIN
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
                # Cargar datos actuales inmediatamente después del login.
                actualizar_sesion_desde_supabase()
                st.rerun()
            else:
                st.error("Usuario o contraseña incorrectos")
    st.stop()

# ============================================================
# 10. MENÚ LATERAL
# ============================================================
mostrar_logo_sidebar()
st.sidebar.title(f"👤 {st.session_state.nombre}")
st.sidebar.caption(f"Rol: **{st.session_state.rol.upper()}**")
st.sidebar.markdown("---")

if st.sidebar.button("🔄 Actualizar datos desde Supabase", use_container_width=True):
    try:
        actualizar_sesion_desde_supabase()
        # Limpiar editores para que no conserven valores viejos.
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
    "#2563EB", "#7C3AED", "#DB2777", "#EA580C", "#059669",
    "#0284C7", "#D97706", "#DC2626", "#4F46E5", "#0D9488",
]

# ============================================================
# 11. PRESIDENCIA
# ============================================================
if st.session_state.rol == "presidencia":
    # Siempre refrescar al abrir el panel para evitar copias obsoletas.
    try:
        actualizar_sesion_desde_supabase()
    except Exception as e:
        st.error(f"❌ No fue posible actualizar la información: {e}")

    st.title("🏛️ Panel de Control Presidencial")
    st.caption(
        "Vista ejecutiva de alto nivel, participaciones de mercado y tendencias globales"
    )

    df_all = st.session_state.base_meses_db.copy()

    if df_all.empty:
        st.warning("⚠️ No hay registros en Supabase.")
        st.stop()

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
        df_dir["DIRECTOR_BOLD"] = df_dir["DIRECTOR"].apply(
            lambda x: f"<b>{x}</b>"
        )

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
                labels={"value": "Monto ($)", "variable": "Tipo"},
            )
            st.plotly_chart(fig_sub_cart, use_container_width=True)

    with p_tab4:
        st.subheader("📅 Consolidado General Mes por Mes")
        df_mes_tot = df_all.groupby("MES", as_index=False).agg(
            {
                "CAPITAL": "sum",
                "RECAUDO": "sum",
                "PROYECCION": "sum",
            }
        )
        df_mes_tot["MES_BOLD"] = df_mes_tot["MES"].apply(
            lambda x: f"<b>{x}</b>"
        )
        fig_mes = px.bar(
            df_mes_tot,
            x="MES_BOLD",
            y=["RECAUDO", "PROYECCION"],
            barmode="group",
            title="<b>Evolución de Recaudo vs Proyección Mes x Mes</b>",
            color_discrete_map={
                "RECAUDO": "#2563eb",
                "PROYECCION": "#f59e0b",
            },
        )
        st.plotly_chart(fig_mes, use_container_width=True)

# ============================================================
# 12. DIRECTOR
# ============================================================
elif st.session_state.rol == "director":
    st.title(
        f"✍️ Gestión de Recaudos por Mes - {st.session_state.nombre}"
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
        df_full["CARTERA"].astype(str).str.strip()
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
        tab1, tab2 = st.tabs(
            ["📅 Captura por Cartera y Mes", "📋 Resumen Completo"]
        )

        with tab1:
            cartera_sel = st.selectbox(
                "Seleccione la Cartera a Gestionar:",
                carteras_director,
            )

            mask_cartera = (
                (df_full["DIRECTOR_NORMALIZADO"] == director_actual)
                & (df_full["CARTERA_NORMALIZADA"] == cartera_sel)
            )
            df_sub = df_full[mask_cartera].copy()

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
            st.subheader(f"Desglose Mensual: **{cartera_sel}**")

            df_editado = st.data_editor(
                df_sub[
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
                    "ID": st.column_config.NumberColumn(
                        "ID", disabled=True
                    ),
                    "MES": st.column_config.TextColumn(
                        "Mes / Periodo"
                    ),
                    "CAPITAL": st.column_config.NumberColumn(
                        "Capital ($)",
                        format="$ %,d",
                    ),
                    "# CLIENTES": st.column_config.NumberColumn(
                        "# Clientes",
                        format="%,d",
                    ),
                    "RECAUDO": st.column_config.NumberColumn(
                        "Recaudo Actual ($)",
                        format="$ %,d",
                        min_value=0.0,
                    ),
                    "PROYECCION": st.column_config.NumberColumn(
                        "Proyección ($)",
                        format="$ %,d",
                        min_value=0.0,
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
                        registro_id = row["ID"]

                        if pd.isna(registro_id):
                            errores.append(
                                f"Registro sin ID: {row['MES']}"
                            )
                            continue

                        rec = (
                            float(row["RECAUDO"])
                            if pd.notna(row["RECAUDO"])
                            else 0.0
                        )
                        proy = (
                            float(row["PROYECCION"])
                            if pd.notna(row["PROYECCION"])
                            else 0.0
                        )
                        capital = float(row["CAPITAL"])

                        actualizar_registro_supabase(
                            registro_id,
                            rec,
                            proy,
                            capital,
                        )
                        filas_modificadas += 1

                    if filas_modificadas > 0:
                        # La sesión se refresca desde la fuente oficial.
                        actualizar_sesion_desde_supabase()

                        # Obligar al editor a reconstruirse con datos reales.
                        for key in list(st.session_state.keys()):
                            if str(key).startswith("editor_"):
                                del st.session_state[key]

                        st.success(
                            f"✅ ¡Se guardaron correctamente "
                            f"{filas_modificadas} registros para "
                            f"{cartera_sel}!"
                        )
                        if errores:
                            st.warning(
                                "⚠️ Algunos registros no se actualizaron: "
                                + ", ".join(errores)
                            )
                        st.rerun()
                    else:
                        st.error(
                            "⚠️ No se actualizaron registros."
                        )

                except Exception as e:
                    st.error(
                        f"❌ Error guardando los cambios en Supabase: {e}"
                    )

        with tab2:
            st.subheader("📋 Historial de Recaudo Completo")
            mis_datos = df_director.drop(
                columns=[
                    "DIRECTOR_NORMALIZADO",
                    "CARTERA_NORMALIZADA",
                ],
                errors="ignore",
            ).copy()

            for col in [
                "CAPITAL",
                "RECAUDO",
                "PROYECCION",
                "ESTIMADO CIERRE",
            ]:
                if col in mis_datos.columns:
                    mis_datos[col] = mis_datos[col].apply(
                        formato_pesos
                    )

            if "# CLIENTES" in mis_datos.columns:
                mis_datos["# CLIENTES"] = mis_datos[
                    "# CLIENTES"
                ].apply(formato_numero)

            st.dataframe(mis_datos, use_container_width=True)

# ============================================================
# 13. GERENCIA
# ============================================================
elif st.session_state.rol == "admin":
    # Refresco automático al cargar el panel.
    try:
        actualizar_sesion_desde_supabase()
    except Exception as e:
        st.error(f"❌ No fue posible actualizar la información: {e}")

    st.title("📊 Panel Consolidado Gerencial")

    df_all = st.session_state.base_meses_db.copy()

    if df_all.empty:
        st.warning("⚠️ No hay registros en Supabase.")
        st.stop()

    t1, t2, t3, t4 = st.tabs(
        [
            "📈 Dashboard Consolidado",
            "📅 Consolidado Mes x Mes",
            "📋 Base General",
            "⚙️ Configuración / Admin",
        ]
    )

    with t1:
        m1, m2, m3, m4 = st.columns(4)
        m1.metric(
            "Capital Total",
            formato_pesos(df_all["CAPITAL"].sum()),
        )
        m2.metric(
            "Total Recaudado",
            formato_pesos(df_all["RECAUDO"].sum()),
        )
        m3.metric(
            "Total Proyección",
            formato_pesos(df_all["PROYECCION"].sum()),
        )
        m4.metric(
            "Total Clientes",
            formato_numero(df_all["# CLIENTES"].sum()),
        )

        st.markdown("---")

        col_g1, col_g2 = st.columns(2)

        with col_g1:
            st.subheader("📊 Recaudo por Cartera")
            df_cart = df_all.groupby(
                "CARTERA", as_index=False
            )["RECAUDO"].sum()
            df_cart["CARTERA_BOLD"] = df_cart["CARTERA"].apply(
                lambda x: f"<b>{x}</b>"
            )

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
                xaxis=dict(
                    tickangle=-45,
                    tickfont=dict(size=12, color="black"),
                ),
            )
            st.plotly_chart(fig1, use_container_width=True)

        with col_g2:
            st.subheader("🥧 Participación % por Director")
            df_dir_g = df_all.groupby(
                "DIRECTOR", as_index=False
            )["RECAUDO"].sum()
            df_dir_g["DIRECTOR_BOLD"] = df_dir_g[
                "DIRECTOR"
            ].apply(lambda x: f"<b>{x}</b>")

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
                textfont=dict(
                    size=13,
                    color="white",
                    family="Arial Black",
                ),
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
                .agg(
                    {
                        "RECAUDO": "sum",
                        "PROYECCION": "sum",
                    }
                )
            )

            df_cart_mes_admin["MES_BOLD"] = df_cart_mes_admin[
                "MES"
            ].apply(lambda x: f"<b>{x}</b>")

            fig_admin_cart = px.bar(
                df_cart_mes_admin,
                x="MES_BOLD",
                y=["RECAUDO", "PROYECCION"],
                barmode="group",
                title=f"<b>Evolución Mensual: {cartera_admin_sel}</b>",
                color_discrete_map={
                    "RECAUDO": "#059669",
                    "PROYECCION": "#3b82f6",
                },
                labels={"value": "Monto ($)", "variable": "Estado"},
            )
            st.plotly_chart(
                fig_admin_cart,
                use_container_width=True,
            )

    with t2:
        st.subheader("📅 Consolidado Mes x Mes de Toda la Operación")

        df_mes_ger = df_all.groupby("MES", as_index=False).agg(
            {
                "CAPITAL": "sum",
                "RECAUDO": "sum",
                "PROYECCION": "sum",
            }
        )
        df_mes_ger["MES_BOLD"] = df_mes_ger["MES"].apply(
            lambda x: f"<b>{x}</b>"
        )

        fig_mes_g = px.bar(
            df_mes_ger,
            x="MES_BOLD",
            y=["RECAUDO", "PROYECCION"],
            barmode="group",
            title="<b>Consolidado de Recaudo vs Proyección Mensual ($)</b>",
            color_discrete_map={
                "RECAUDO": "#059669",
                "PROYECCION": "#3b82f6",
            },
        )
        st.plotly_chart(fig_mes_g, use_container_width=True)

    with t3:
        st.subheader("📋 Base General Desglosada")

        df_mostrar_admin = df_all.copy()

        for col in [
            "CAPITAL",
            "RECAUDO",
            "PROYECCION",
            "ESTIMADO CIERRE",
        ]:
            if col in df_mostrar_admin.columns:
                df_mostrar_admin[col] = df_mostrar_admin[
                    col
                ].apply(formato_pesos)

        if "# CLIENTES" in df_mostrar_admin.columns:
            df_mostrar_admin["# CLIENTES"] = df_mostrar_admin[
                "# CLIENTES"
            ].apply(formato_numero)

        st.dataframe(
            df_mostrar_admin,
            use_container_width=True,
        )

    with t4:
        st.subheader("⚙️ Panel Administrativo del Gerente General")

        if "mensaje_exito_carga" in st.session_state:
            st.success(st.session_state.mensaje_exito_carga)
            del st.session_state["mensaje_exito_carga"]

        st.markdown("### 📥 Cargue Masivo de Estructura Base (Excel / CSV)")
        st.caption(
            "Suba el archivo con la estructura fija de carteras, "
            "directores, meses, capitales y número de clientes."
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
            st.info(f"📁 Archivo detectado: **{uploaded_base.name}**")

            if st.button(
                "🚀 Cargar y Procesar Base de Datos",
                type="primary",
                use_container_width=True,
            ):
                try:
                    uploaded_base.seek(0)

                    if uploaded_base.name.lower().endswith(".csv"):
                        df_cargado = pd.read_csv(uploaded_base)
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

                    columnas_actuales = set(df_cargado.columns)

                    if not columnas_requeridas.issubset(
                        columnas_actuales
                    ):
                        faltantes = (
                            columnas_requeridas - columnas_actuales
                        )
                        st.error(
                            "❌ **Error en la estructura del archivo.** "
                            f"Faltan las columnas: `{faltantes}`"
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
                        df_cargado["CAPITAL"] = pd.to_numeric(
                            df_cargado["CAPITAL"],
                            errors="coerce",
                        ).fillna(0.0)

                        df_cargado["# CLIENTES"] = pd.to_numeric(
                            df_cargado["# CLIENTES"],
                            errors="coerce",
                        ).fillna(0).astype(int)

                        df_cargado["RECAUDO"] = (
                            pd.to_numeric(
                                df_cargado["RECAUDO"],
                                errors="coerce",
                            ).fillna(0.0)
                            if "RECAUDO" in df_cargado.columns
                            else 0.0
                        )

                        df_cargado["PROYECCION"] = (
                            pd.to_numeric(
                                df_cargado["PROYECCION"],
                                errors="coerce",
                            ).fillna(0.0)
                            if "PROYECCION" in df_cargado.columns
                            else 0.0
                        )

                        df_cargado["% EFECTIVIDAD"] = (
                            (
                                df_cargado["RECAUDO"]
                                / df_cargado["CAPITAL"]
                                * 100
                            )
                            .fillna(0.0)
                            .replace(
                                [float("inf"), -float("inf")],
                                0.0,
                            )
                        )

                        df_cargado["ESTIMADO CIERRE"] = (
                            df_cargado["RECAUDO"]
                            + df_cargado["PROYECCION"]
                        )

                        # Upsert en Supabase.
                        upsert_dataframe_supabase(df_cargado)

                        # Cargar de nuevo para obtener los IDs reales
                        # y la versión definitiva de Supabase.
                        actualizar_sesion_desde_supabase()

                        for key in list(st.session_state.keys()):
                            if str(key).startswith("editor_"):
                                del st.session_state[key]

                        st.session_state.mensaje_exito_carga = (
                            "🎉 ¡Base de datos cargada y sincronizada "
                            f"con éxito! Se procesaron "
                            f"{len(df_cargado)} registros."
                        )
                        st.rerun()

                except Exception as e:
                    st.error(
                        f"❌ Error procesando el archivo: `{str(e)}`"
                    )

        st.markdown("---")
        col_adm1, col_adm2 = st.columns(2)

        with col_adm1:
            st.markdown("### 🔑 Modificación de Contraseñas")

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
                    st.error("Las contraseñas no coinciden.")
                else:
                    st.session_state.usuarios_db[
                        usuario_a_modificar
                    ]["hash"] = hacer_hash(nueva_clave)

                    st.success(
                        "¡Contraseña actualizada correctamente para "
                        f"**{st.session_state.usuarios_db[usuario_a_modificar]['nombre']}**!"
                    )

        with col_adm2:
            st.markdown("### 🖼️ Actualizar Logo Corporativo")

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
        st.markdown("### ⚠️ Reinicio de Base de Datos")

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
                "⚠️ ¿Está seguro de reiniciar la base de datos? "
                "Esta acción eliminará los registros actuales de Supabase."
            )

            col_alert1, col_alert2 = st.columns(2)

            with col_alert1:
                if st.button(
                    "✅ Sí, reiniciar",
                    type="primary",
                    use_container_width=True,
                ):
                    try:
                        eliminar_todos_registros_supabase()
                        st.session_state.base_meses_db = pd.DataFrame(
                            columns=COLUMNAS_APP
                        )
                        st.session_state.confirmar_reinicio = False

                        for key in list(st.session_state.keys()):
                            if str(key).startswith("editor_"):
                                del st.session_state[key]

                        st.success(
                            "✅ Base de datos de Supabase reiniciada."
                        )
                        st.rerun()

                    except Exception as e:
                        st.error(
                            f"❌ Error reiniciando Supabase: {e}"
                        )

            with col_alert2:
                if st.button(
                    "❌ Cancelar",
                    use_container_width=True,
                ):
                    st.session_state.confirmar_reinicio = False
                    st.rerun()
