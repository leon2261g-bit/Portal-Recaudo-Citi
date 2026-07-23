import streamlit as st
import pandas as pd
import hashlib
from PIL import Image
import os
import plotly.express as px

# 1. Configuración de la página
st.set_page_config(
    page_title="Portal Digital de Recaudo",
    page_icon="💼",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- FORMATOS FINANCIEROS Y NUMÉRICOS ---
def formato_pesos(val):
    if pd.isna(val) or val is None:
        return "$ 0"
    return f"$ {val:,.0f}".replace(",", ".")

def formato_numero(val):
    if pd.isna(val) or val is None:
        return "0"
    return f"{val:,.0f}".replace(",", ".")

# 2. Estilos CSS Personalizados
st.markdown("""
    <style>
    .main { background-color: #f8fafc; }
    h1 { color: #0f172a; font-family: 'Segoe UI', Roboto, sans-serif; font-weight: 800; }
    h2, h3 { color: #1e293b; font-weight: 600; }
    [data-testid="stMetric"] {
        background: linear-gradient(135deg, #ffffff 0%, #f1f5f9 100%);
        border: 1px solid #e2e8f0;
        border-radius: 16px;
        padding: 20px;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);
        border-top: 4px solid #2563eb;
    }
    [data-testid="stMetricLabel"] { color: #64748b; font-size: 0.85rem; font-weight: 700; text-transform: uppercase; }
    [data-testid="stMetricValue"] { color: #0f172a; font-size: 1.6rem !important; font-weight: 800; }
    [data-testid="stSidebar"] { background-color: #0f172a; }
    [data-testid="stSidebar"] h1, [data-testid="stSidebar"] span, [data-testid="stSidebar"] p { color: #f8fafc !important; }
    </style>
""", unsafe_allow_html=True)

# 3. GESTIÓN DEL LOGO PERSISTENTE
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
        st.sidebar.image(logo, use_container_width=True)
    else:
        st.sidebar.markdown("### 🏢 **Portal de Recaudo**")
    st.sidebar.markdown("---")

# --- BASE DE DATOS INICIAL ---
DATOS_EXCEL = [
    {"CARTERA": "POPULAR 2TC CITI 2023", "DIRECTOR": "ADRIANA", "MES": "MARZO 2023", "CAPITAL": 217450011, "# CLIENTES": 53},
    {"CARTERA": "POPULAR 2TC CITI 2023", "DIRECTOR": "ADRIANA", "MES": "ABRIL 2023", "CAPITAL": 252750319, "# CLIENTES": 62},
    {"CARTERA": "POPULAR 2TC CITI 2023", "DIRECTOR": "ADRIANA", "MES": "MAYO 2023", "CAPITAL": 199530664, "# CLIENTES": 60},
    {"CARTERA": "POPULAR 2TC CITI 2023", "DIRECTOR": "ADRIANA", "MES": "AGOSTO 2023", "CAPITAL": 330411006, "# CLIENTES": 73},
    {"CARTERA": "POPULAR 2TC CITI 2023", "DIRECTOR": "ADRIANA", "MES": "SEPTIEMBRE 2023", "CAPITAL": 214162693, "# CLIENTES": 50},
    {"CARTERA": "POPULAR 2TC CITI 2023", "DIRECTOR": "ADRIANA", "MES": "OCTUBRE 2023", "CAPITAL": 172146722, "# CLIENTES": 40},
    {"CARTERA": "POPULAR 2TC CITI 2023", "DIRECTOR": "ADRIANA", "MES": "NOVIEMBRE 2023", "CAPITAL": 156811901, "# CLIENTES": 37},
    
    {"CARTERA": "POPULAR 2026", "DIRECTOR": "ADRIANA", "MES": "GENERAL", "CAPITAL": 3598011715, "# CLIENTES": 85},
    {"CARTERA": "POPULAR 2026", "DIRECTOR": "CARLOS", "MES": "GENERAL", "CAPITAL": 7259787281, "# CLIENTES": 173},
    {"CARTERA": "POPULAR 2026", "DIRECTOR": "JEIMMY", "MES": "GENERAL", "CAPITAL": 7479973316, "# CLIENTES": 173},
    {"CARTERA": "POPULAR 2026", "DIRECTOR": "ERIKA", "MES": "GENERAL", "CAPITAL": 0, "# CLIENTES": 0},
    {"CARTERA": "POPULAR 2026", "DIRECTOR": "MIGUEL", "MES": "GENERAL", "CAPITAL": 10896210066, "# CLIENTES": 259},
]

if 'base_meses_db' not in st.session_state:
    df_init = pd.DataFrame(DATOS_EXCEL)
    df_init['RECAUDO'] = 0.0
    df_init['PROYECCION'] = 0.0
    df_init['% EFECTIVIDAD'] = 0.0
    df_init['ESTIMADO CIERRE'] = 0.0
    st.session_state.base_meses_db = df_init

# --- AUTENTICACIÓN Y ROLES ---
def hacer_hash(password):
    return hashlib.sha256(str.encode(password)).hexdigest()

USUARIOS = {
    "presidencia": {"hash": hacer_hash("presidencia2026"), "nombre": "Presidencia Ejecutiva", "rol": "presidencia"},
    "gerente":     {"hash": hacer_hash("gerencia2026"),    "nombre": "Gerente General",       "rol": "admin"},
    "adriana":     {"hash": hacer_hash("adriana123"),       "nombre": "ADRIANA",               "rol": "director"},
    "carlos":      {"hash": hacer_hash("carlos123"),        "nombre": "CARLOS",                "rol": "director"},
    "jeimmy":      {"hash": hacer_hash("jeimmy123"),        "nombre": "JEIMMY",                "rol": "director"},
    "erika":       {"hash": hacer_hash("erika123"),         "nombre": "ERIKA",                 "rol": "director"},
    "miguel":      {"hash": hacer_hash("miguel123"),        "nombre": "MIGUEL",                "rol": "director"}
}

if 'autenticado' not in st.session_state:
    st.session_state.autenticado = False

# --- PANTALLA DE LOGIN ---
if not st.session_state.autenticado:
    _, col_c2, _ = st.columns([1, 2, 1])
    with col_c2:
        st.write("")
        st.write("")
        logo_login = cargar_logo()
        if logo_login is not None:
            st.image(logo_login, width=220)
        
        st.title("🔐 Portal Digital de Recaudo")
        st.caption("Ingrese sus credenciales de acceso:")
        
        user_input = st.text_input("Usuario:").strip().lower()
        pass_input = st.text_input("Contraseña:", type="password")
        
        if st.button("Iniciar Sesión", type="primary", use_container_width=True):
            if user_input in USUARIOS and USUARIOS[user_input]["hash"] == hacer_hash(pass_input):
                st.session_state.autenticado = True
                st.session_state.usuario = user_input
                st.session_state.rol = USUARIOS[user_input]["rol"]
                st.session_state.nombre = USUARIOS[user_input]["nombre"]
                st.rerun()
            else:
                st.error("Usuario o contraseña incorrectos")
    st.stop()

# --- MENÚ LATERAL COMÚN ---
mostrar_logo_sidebar()
st.sidebar.title(f"👤 {st.session_state.nombre}")
st.sidebar.caption(f"Rol: **{st.session_state.rol.upper()}**")
st.sidebar.markdown("---")

# Exclusivo de Gerente General: Carga y Administración del Logo
if st.session_state.rol == "admin":
    with st.sidebar.expander("⚙️ Exclusivo Gerente: Configurar Logo"):
        uploaded_logo = st.file_uploader("Actualizar logo corporativo", type=["png", "jpg", "jpeg"])
        if uploaded_logo is not None:
            img = Image.open(uploaded_logo)
            img.save(LOGO_PATH)
            st.success("¡Logo guardado de forma permanente!")
            st.rerun()
    st.sidebar.markdown("---")

if st.sidebar.button("🚪 Cerrar Sesión", use_container_width=True):
    st.session_state.autenticado = False
    st.rerun()

# ==========================================
# VISTA 1: PRESIDENCIA (Estratégica & Rankings)
# ==========================================
if st.session_state.rol == "presidencia":
    st.title("🏛️ Panel de Control Presidencial")
    st.caption("Vista ejecutiva de alto nivel, ranking de rendimiento y tendencias por cartera")
    
    df_all = st.session_state.base_meses_db.copy()
    
    # Métricas Globales
    cap_tot = df_all['CAPITAL'].sum()
    rec_tot = df_all['RECAUDO'].sum()
    proy_tot = df_all['PROYECCION'].sum()
    efect_global = (rec_tot / cap_tot * 100) if cap_tot > 0 else 0.0
    
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Capital Global", formato_pesos(cap_tot))
    m2.metric("Recaudo Total", formato_pesos(rec_tot))
    m3.metric("Proyección Total", formato_pesos(proy_tot))
    m4.metric("% Efectividad Global", f"{efect_global:.2f}%")
    
    st.markdown("---")
    
    p_tab1, p_tab2 = st.tabs(["🏆 Ranking por Director", "📈 Recaudo por Cartera y Mes"])
    
    with p_tab1:
        st.subheader("🥇 Ranking de Gestión por Director")
        
        # Agrupación por Director
        df_dir = df_all.groupby('DIRECTOR', as_index=False).agg({
            'CAPITAL': 'sum',
            'RECAUDO': 'sum',
            'PROYECCION': 'sum',
            '# CLIENTES': 'sum'
        })
        
        df_dir['% EFECTIVIDAD'] = df_dir.apply(
            lambda r: (r['RECAUDO'] / r['CAPITAL'] * 100) if r['CAPITAL'] > 0 else 0.0, axis=1
        )
        
        # Ordenar para Ranking
        df_dir = df_dir.sort_values(by='RECAUDO', ascending=False).reset_index(drop=True)
        
        medallas = ["🥇 1°", "🥈 2°", "🥉 3°"] + [f"  {i+1}°" for i in range(3, len(df_dir))]
        df_dir['POSICIÓN'] = medallas[:len(df_dir)]
        
        col_rank_t, col_rank_g = st.columns([1.1, 1])
        
        with col_rank_t:
            df_rank_print = df_dir[['POSICIÓN', 'DIRECTOR', 'RECAUDO', 'CAPITAL', '% EFECTIVIDAD']].copy()
            df_rank_print['RECAUDO'] = df_rank_print['RECAUDO'].apply(formato_pesos)
            df_rank_print['CAPITAL'] = df_rank_print['CAPITAL'].apply(formato_pesos)
            df_rank_print['% EFECTIVIDAD'] = df_rank_print['% EFECTIVIDAD'].apply(lambda x: f"{x:.2f}%")
            
            st.dataframe(df_rank_print, use_container_width=True, hide_index=True)
            
        with col_rank_g:
            fig_rank = px.bar(
                df_dir,
                x='RECAUDO',
                y='DIRECTOR',
                orientation='h',
                text_auto='.2s',
                title="Líderes de Recaudo ($)",
                color='RECAUDO',
                color_continuous_scale='Blues'
            )
            fig_rank.update_layout(yaxis={'categoryorder': 'total ascending'}, showlegend=False)
            st.plotly_chart(fig_rank, use_container_width=True)

    with p_tab2:
        st.subheader("📊 Comportamiento de Recaudo por Cartera y Mes")
        
        df_cart_mes = df_all.groupby(['CARTERA', 'MES'], as_index=False).agg({
            'RECAUDO': 'sum',
            'PROYECCION': 'sum',
            'CAPITAL': 'sum'
        })
        
        col_f1, col_f2 = st.columns(2)
        with col_f1:
            carteras_disponibles = ["TODAS"] + list(df_cart_mes['CARTERA'].unique())
            cartera_filtro = st.selectbox("Filtrar por Cartera:", carteras_disponibles)
        
        if cartera_filtro != "TODAS":
            df_chart_data = df_cart_mes[df_cart_mes['CARTERA'] == cartera_filtro]
        else:
            df_chart_data = df_cart_mes
            
        fig_cart_mes = px.bar(
            df_chart_data,
            x='MES',
            y='RECAUDO',
            color='CARTERA',
            barmode='group',
            title=f"Recaudo Histórico y Proyectado por Mes ({cartera_filtro})",
            labels={'RECAUDO': 'Recaudo ($)', 'MES': 'Periodo / Mes'},
            color_discrete_sequence=px.colors.qualitative.Pastel
        )
        st.plotly_chart(fig_cart_mes, use_container_width=True)
        
        st.caption("Detalle Completo por Cartera y Mes:")
        df_cm_print = df_chart_data.copy()
        df_cm_print['RECAUDO'] = df_cm_print['RECAUDO'].apply(formato_pesos)
        df_cm_print['PROYECCION'] = df_cm_print['PROYECCION'].apply(formato_pesos)
        df_cm_print['CAPITAL'] = df_cm_print['CAPITAL'].apply(formato_pesos)
        st.dataframe(df_cm_print, use_container_width=True, hide_index=True)

# ==========================================
# VISTA 2: DIRECTOR
# ==========================================
elif st.session_state.rol == "director":
    st.title(f"✍️ Gestión de Recaudos por Mes - {st.session_state.nombre}")
    
    director_actual = st.session_state.nombre
    df_full = st.session_state.base_meses_db
    
    carteras_director = df_full[df_full['DIRECTOR'] == director_actual]['CARTERA'].unique().tolist()
    
    tab1, tab2 = st.tabs(["📅 Captura por Cartera y Mes", "📋 Resumen Completo"])
    
    with tab1:
        cartera_sel = st.selectbox("Seleccione la Cartera a Gestionar:", carteras_director)
        
        filtro_meses = (df_full['DIRECTOR'] == director_actual) & (df_full['CARTERA'] == cartera_sel)
        df_sub = df_full[filtro_meses].copy()
        
        tot_cap = df_sub['CAPITAL'].sum()
        tot_cli = df_sub['# CLIENTES'].sum()
        tot_rec = df_sub['RECAUDO'].sum()
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Capital Asignado", formato_pesos(tot_cap))
        c2.metric("Clientes Totales", formato_numero(tot_cli))
        c3.metric("Recaudo Acumulado", formato_pesos(tot_rec))
        
        st.markdown("---")
        st.subheader(f"Desglose Mensual: **{cartera_sel}**")
        st.caption("Ingresa los valores de **Recaudo** y **Proyección** en las celdas de la tabla:")
        
        df_editado = st.data_editor(
            df_sub[['MES', 'CAPITAL', '# CLIENTES', 'RECAUDO', 'PROYECCION']],
            disabled=['MES', 'CAPITAL', '# CLIENTES'],
            use_container_width=True,
            column_config={
                "MES": st.column_config.TextColumn("Mes / Periodo"),
                "CAPITAL": st.column_config.NumberColumn("Capital ($)", format="$ %,d"),
                "# CLIENTES": st.column_config.NumberColumn("# Clientes", format="%,d"),
                "RECAUDO": st.column_config.NumberColumn("Recaudo Actual ($)", format="$ %,d", min_value=0),
                "PROYECCION": st.column_config.NumberColumn("Proyección ($)", format="$ %,d", min_value=0)
            },
            hide_index=True
        )
        
        if st.button("💾 Guardar Recaudos de la Cartera", type="primary", use_container_width=True):
            for idx, row in df_editado.iterrows():
                mes_val = row['MES']
                rec = float(row['RECAUDO'])
                proy = float(row['PROYECCION'])
                cap = float(row['CAPITAL'])
                
                efect = (rec / cap * 100) if cap > 0 else 0.0
                est_cierre = rec + proy
                
                cond = (df_full['DIRECTOR'] == director_actual) & (df_full['CARTERA'] == cartera_sel) & (df_full['MES'] == mes_val)
                st.session_state.base_meses_db.loc[cond, 'RECAUDO'] = rec
                st.session_state.base_meses_db.loc[cond, 'PROYECCION'] = proy
                st.session_state.base_meses_db.loc[cond, '% EFECTIVIDAD'] = efect
                st.session_state.base_meses_db.loc[cond, 'ESTIMADO CIERRE'] = est_cierre
                
            st.success(f"¡Valores de {cartera_sel} guardados con éxito!")
            st.rerun()

    with tab2:
        st.subheader("📋 Historial de Recaudo Completo")
        mis_datos = st.session_state.base_meses_db[st.session_state.base_meses_db['DIRECTOR'] == director_actual].copy()
        
        df_mostrar = mis_datos.copy()
        for col in ['CAPITAL', 'RECAUDO', 'PROYECCION', 'ESTIMADO CIERRE']:
            df_mostrar[col] = df_mostrar[col].apply(formato_pesos)
        df_mostrar['# CLIENTES'] = df_mostrar['# CLIENTES'].apply(formato_numero)
        df_mostrar['% EFECTIVIDAD'] = df_mostrar['% EFECTIVIDAD'].apply(lambda x: f"{x:.2f}%".replace(".", ","))
        
        st.dataframe(df_mostrar, use_container_width=True)

# ==========================================
# VISTA 3: GERENTE GENERAL
# ==========================================
elif st.session_state.rol == "admin":
    st.title("📊 Panel Consolidado Gerencial")
    
    df_all = st.session_state.base_meses_db
    
    t1, t2 = st.tabs(["📈 Dashboard Consolidado", "📋 Vista Detallada por Mes"])
    
    with t1:
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Capital Total", formato_pesos(df_all['CAPITAL'].sum()))
        m2.metric("Total Recaudado", formato_pesos(df_all['RECAUDO'].sum()))
        m3.metric("Total Proyección", formato_pesos(df_all['PROYECCION'].sum()))
        m4.metric("Total Clientes", formato_numero(df_all['# CLIENTES'].sum()))
        
        st.markdown("---")
        
        col_g1, col_g2 = st.columns(2)
        with col_g1:
            st.subheader("📊 Recaudo por Cartera")
            df_cart = df_all.groupby('CARTERA', as_index=False)['RECAUDO'].sum()
            fig1 = px.bar(
                df_cart, 
                x='CARTERA', 
                y='RECAUDO', 
                color='CARTERA', 
                color_discrete_sequence=px.colors.qualitative.Bold,
                labels={'RECAUDO': 'Monto Recaudado ($)', 'CARTERA': 'Cartera'}
            )
            fig1.update_layout(showlegend=False)
            st.plotly_chart(fig1, use_container_width=True)
            
        with col_g2:
            st.subheader("👥 Recaudo por Director")
            df_dir = df_all.groupby('DIRECTOR', as_index=False)['RECAUDO'].sum()
            fig2 = px.pie(
                df_dir, 
                names='DIRECTOR', 
                values='RECAUDO', 
                hole=0.4,
                color_discrete_sequence=px.colors.qualitative.Set2
            )
            fig2.update_traces(textinfo='percent+label')
            st.plotly_chart(fig2, use_container_width=True)

    with t2:
        st.subheader("📋 Base General Desglosada")
        
        df_mostrar_admin = df_all.copy()
        for col in ['CAPITAL', 'RECAUDO', 'PROYECCION', 'ESTIMADO CIERRE']:
            df_mostrar_admin[col] = df_mostrar_admin[col].apply(formato_pesos)
        df_mostrar_admin['# CLIENTES'] = df_mostrar_admin['# CLIENTES'].apply(formato_numero)
        df_mostrar_admin['% EFECTIVIDAD'] = df_mostrar_admin['% EFECTIVIDAD'].apply(lambda x: f"{x:.2f}%".replace(".", ","))
        
        st.dataframe(df_mostrar_admin, use_container_width=True)