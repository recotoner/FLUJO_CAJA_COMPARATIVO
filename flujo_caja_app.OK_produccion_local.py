import streamlit as st
import pandas as pd
import plotly.express as px
import unicodedata
import io
import json
import os
import re
import hashlib
import tempfile
from pathlib import Path
from datetime import datetime

# Importar sistema de autenticación y base de datos
from auth.login import require_login, show_user_info, get_current_user
from database.crud import (
    obtener_clasificadores, obtener_transacciones, guardar_transacciones,
    registrar_archivo, crear_alerta, obtener_alertas, obtener_mapeo_columnas,
    obtener_archivos
)
from database.models import TipoTransaccion

# ---------- CONFIGURACIÓN DE PÁGINA ----------
st.set_page_config(
    page_title="Flujo de Caja Inteligente",
    page_icon="💼",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ---------- CSS PERSONALIZADO ----------
st.markdown("""
<style>
    /* Estilos generales */
    .main .block-container {
        padding-top: 2rem;
        padding-bottom: 2rem;
    }
    
    /* Título principal mejorado */
    h1 {
        color: #1f77b4;
        border-bottom: 3px solid #1f77b4;
        padding-bottom: 0.5rem;
        margin-bottom: 1.5rem;
    }
    
    /* Subtítulos */
    h2 {
        color: #2c3e50;
        margin-top: 1.5rem;
        margin-bottom: 1rem;
    }
    
    h3 {
        color: #34495e;
        margin-top: 1rem;
    }
    
    /* Métricas mejoradas */
    [data-testid="stMetricValue"] {
        font-size: 2rem;
        font-weight: bold;
    }
    
    /* Sidebar mejorado */
    .css-1d391kg {
        padding-top: 2rem;
    }
    
    /* Botones mejorados */
    .stButton > button {
        border-radius: 8px;
        font-weight: 500;
        transition: all 0.3s ease;
        border: none !important;
    }
    
    .stButton > button:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 8px rgba(0,0,0,0.2);
    }
    
    /* Botón de guardar destacado */
    .stButton > button[kind="primary"] {
        background: linear-gradient(135deg, #2d5016 0%, #4a7c2a 100%) !important;
        color: white !important;
        font-weight: 600 !important;
    }
    
    .stButton > button[kind="primary"]:hover {
        background: linear-gradient(135deg, #1f3a0f 0%, #2d5016 100%) !important;
    }
    
    /* Botones secundarios */
    .stButton > button[kind="secondary"] {
        background-color: #6c757d !important;
        color: white !important;
    }
    
    .stButton > button[kind="secondary"]:hover {
        background-color: #5a6268 !important;
    }
    
    /* Tarjetas de información */
    .info-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        padding: 1.5rem;
        border-radius: 10px;
        margin: 1rem 0;
    }
    
    /* Tablas mejoradas */
    .dataframe {
        border-radius: 8px;
        overflow: hidden;
    }
    
    /* Alertas mejoradas */
    .stAlert {
        border-radius: 8px;
        border-left: 4px solid;
    }
    
    /* Banner de bienvenido */
    .welcome-banner {
        background: linear-gradient(135deg, #2d5016 0%, #4a7c2a 100%);
        color: white;
        padding: 1rem 1.5rem;
        border-radius: 10px;
        margin-bottom: 1.5rem;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        display: flex;
        align-items: center;
        justify-content: space-between;
    }
    
    .welcome-banner h3 {
        color: white !important;
        margin: 0;
        font-size: 1.3rem;
    }
    
    /* Métricas con gradiente */
    [data-testid="stMetricContainer"] {
        background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
        padding: 1rem;
        border-radius: 10px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        transition: transform 0.3s ease;
    }
    
    [data-testid="stMetricContainer"]:hover {
        transform: translateY(-3px);
        box-shadow: 0 4px 8px rgba(0,0,0,0.15);
    }
    
    /* Mejoras en las tarjetas de métricas */
    [data-testid="stMetricLabel"] {
        font-size: 0.9rem;
        font-weight: 600;
        color: #2c3e50;
    }
    
    /* Sidebar con mejor diseño */
    .css-1d391kg {
        background: linear-gradient(180deg, #f8f9fa 0%, #ffffff 100%);
    }
    
    /* Mejoras en los expanders */
    .streamlit-expanderHeader {
        font-weight: 600;
        color: #2c3e50;
    }
    
    /* Mejoras en las tablas */
    .dataframe {
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    
    /* Mejoras en los selectboxes */
    .stSelectbox > div > div {
        border-radius: 6px;
    }
    
    /* Mejoras en los file uploaders */
    .uploadedFile {
        border-radius: 6px;
        padding: 0.5rem;
    }
</style>
""", unsafe_allow_html=True)

# ---------- VERIFICAR LOGIN ----------
if not require_login():
    st.stop()  # Si no está logueado, mostrar login y detener

# ---------- HEADER MEJORADO ----------
usuario_actual = get_current_user()

# Banner de bienvenido persistente
if usuario_actual:
    # Mostrar banner de bienvenido si no se ha mostrado en esta sesión o si es la primera vez
    if 'bienvenido_mostrado' not in st.session_state:
        st.session_state.bienvenido_mostrado = True
    
    # Mostrar banner de bienvenido
    st.markdown(
        f"""
        <div class="welcome-banner">
            <div>
                <h3>👋 ¡Bienvenido, {usuario_actual.nombre_empresa}!</h3>
                <p style="margin: 0.5rem 0 0 0; opacity: 0.9;">Gestiona tu flujo de caja de manera inteligente</p>
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

col_header1, col_header2 = st.columns([3, 1])
with col_header1:
    st.markdown("## 💼 Dashboard Flujo de Caja")
    st.markdown("### Clasificación Inteligente de Transacciones")
with col_header2:
    st.markdown("<br>", unsafe_allow_html=True)
    if usuario_actual:
        st.markdown(
            f"""
            <div style="text-align: right; padding: 0.5rem; background-color: #f0f2f6; border-radius: 8px;">
                <strong>👤 {usuario_actual.nombre_empresa}</strong>
            </div>
            """,
            unsafe_allow_html=True
        )

st.markdown("---")

# ---------- CONFIGURACIÓN ----------
DIRECTORIO_CONFIGS = "configs"  # Directorio donde se guardan las configuraciones por cliente
CONFIG_CLASIFICADORES = "clasificadores.json"  # Configuración por defecto

# Inicializar session state para recordar selecciones
if 'cliente_seleccionado' not in st.session_state:
    st.session_state.cliente_seleccionado = None
if 'archivo_actual' not in st.session_state:
    st.session_state.archivo_actual = None
if 'archivo_cargado_bd' not in st.session_state:
    st.session_state.archivo_cargado_bd = None
if 'archivo_id_cargado_bd' not in st.session_state:
    st.session_state.archivo_id_cargado_bd = None

# ---------- FUNCIONES DE UTILIDAD ----------

def normalizar(texto):
    """Normaliza el texto eliminando acentos y convirtiendo a mayúsculas."""
    if pd.isnull(texto):
        return ""
    texto = str(texto).upper().strip()
    texto = unicodedata.normalize("NFD", texto).encode("ascii", "ignore").decode("utf-8")
    return texto

def listar_configuraciones():
    """Lista todos los archivos de configuración disponibles (JSON y Excel)."""
    configs = []
    directorio_base = Path(__file__).parent
    
    # Buscar en el directorio de configs
    dir_configs = directorio_base / DIRECTORIO_CONFIGS
    if dir_configs.exists():
        # Buscar JSON
        configs.extend(dir_configs.glob("*.json"))
        # Buscar Excel
        configs.extend(dir_configs.glob("*.xlsx"))
    
    # Buscar en el directorio raíz
    configs.extend(directorio_base.glob("clasificadores*.json"))
    configs.extend(directorio_base.glob("clasificadores*.xlsx"))
    
    # Eliminar duplicados y ordenar
    configs = sorted(set(configs), key=lambda x: x.name)
    return configs

def extraer_nombre_cliente_desde_archivo(nombre_archivo):
    """
    Extrae el nombre del cliente desde el nombre del archivo de datos.
    
    Ejemplos:
    - cartola_cliente_a_junio_2025.xlsx -> cliente_a
    - datos_empresa_xyz.xlsx -> empresa_xyz
    - cliente_b_cartola.xlsx -> cliente_b
    
    Args:
        nombre_archivo: Nombre del archivo (con o sin ruta)
    
    Returns:
        str: Nombre del cliente extraído o None
    """
    nombre_sin_ruta = Path(nombre_archivo).stem.lower()
    
    # Patrones comunes para detectar nombre de cliente
    patrones = [
        r'cliente[_\s]+([a-z0-9_]+)',
        r'empresa[_\s]+([a-z0-9_]+)',
        r'([a-z0-9_]+)[_\s]+cartola',
        r'([a-z0-9_]+)[_\s]+datos',
        r'cartola[_\s]+([a-z0-9_]+)',
    ]
    
    for patron in patrones:
        match = re.search(patron, nombre_sin_ruta)
        if match:
            return match.group(1)
    
    return None

def detectar_configuracion_por_cliente(nombre_cliente, configs_disponibles):
    """
    Intenta encontrar la configuración que coincide con el nombre del cliente.
    
    Args:
        nombre_cliente: Nombre del cliente a buscar
        configs_disponibles: Lista de rutas de archivos de configuración
    
    Returns:
        Path: Ruta de la configuración encontrada o None
    """
    if not nombre_cliente:
        return None
    
    nombre_cliente_clean = nombre_cliente.lower().replace(" ", "_")
    
    for config_path in configs_disponibles:
        nombre_config = config_path.stem.lower()
        
        # Buscar coincidencias
        if nombre_cliente_clean in nombre_config or nombre_config.replace("clasificadores_", "") == nombre_cliente_clean:
            return config_path
    
    return None

def crear_mapa_cliente_config(configs_disponibles):
    """
    Crea un diccionario que mapea nombres de clientes a configuraciones.
    
    Returns:
        dict: {nombre_cliente: ruta_config}
    """
    mapa = {}
    for config_path in configs_disponibles:
        nombre = config_path.stem.replace("clasificadores_", "").replace("_", " ").title()
        if nombre != "Clasificadores":
            mapa[nombre.lower()] = config_path
    return mapa

def cargar_clasificadores_desde_excel(ruta_excel):
    """
    Carga la configuración de clasificadores desde un archivo Excel.
    
    Estructura esperada del Excel:
    - Hoja "ABONOS" o columna "Tipo" con valor "ABONO"
    - Hoja "CARGOS" o columna "Tipo" con valor "CARGO"
    - Columnas: Nombre, Palabras Clave, Tipo Coincidencia, Excluir (opcional)
    
    Args:
        ruta_excel: Ruta del archivo Excel
    
    Returns:
        dict: Configuración cargada o None si hay error
    """
    try:
        # Leer todas las hojas disponibles
        excel_file = pd.ExcelFile(ruta_excel)
        hojas = excel_file.sheet_names
        
        config = {
            "clasificadores": {
                "abonos": [],
                "cargos": []
            },
            "clasificacion_default": "NO CLASIFICADO"
        }
        
        # Intentar leer desde hojas separadas
        if "ABONOS" in hojas:
            df_abonos = pd.read_excel(ruta_excel, sheet_name="ABONOS")
            config["clasificadores"]["abonos"] = _procesar_dataframe_clasificadores(df_abonos)
        
        if "CARGOS" in hojas:
            df_cargos = pd.read_excel(ruta_excel, sheet_name="CARGOS")
            config["clasificadores"]["cargos"] = _procesar_dataframe_clasificadores(df_cargos)
        
        # Si no hay hojas separadas, intentar leer desde una sola hoja con columna "Tipo"
        if "ABONOS" not in hojas and "CARGOS" not in hojas:
            # Leer la primera hoja
            df = pd.read_excel(ruta_excel, sheet_name=hojas[0])
            df.columns = df.columns.str.strip().str.upper()
            
            # Verificar si tiene columna "TIPO"
            if "TIPO" in df.columns:
                df_abonos = df[df["TIPO"].str.upper().str.strip() == "ABONO"].copy()
                df_cargos = df[df["TIPO"].str.upper().str.strip() == "CARGO"].copy()
                
                config["clasificadores"]["abonos"] = _procesar_dataframe_clasificadores(df_abonos)
                config["clasificadores"]["cargos"] = _procesar_dataframe_clasificadores(df_cargos)
            else:
                # Si no hay columna TIPO, asumir que todo son cargos (comportamiento por defecto)
                config["clasificadores"]["cargos"] = _procesar_dataframe_clasificadores(df)
        
        return config
    except Exception as e:
        st.error(f"❌ Error al leer el archivo Excel {ruta_excel}: {e}")
        return None

def _procesar_dataframe_clasificadores(df):
    """Convierte un DataFrame en lista de clasificadores."""
    clasificadores = []
    
    if df.empty:
        return clasificadores
    
    # Normalizar nombres de columnas
    df.columns = df.columns.str.strip().str.upper()
    
    # Mapear nombres de columnas posibles
    col_nombre = None
    col_palabras = None
    col_tipo = None
    col_excluir = None
    
    for col in df.columns:
        col_upper = col.upper()
        if "NOMBRE" in col_upper or "CLASIFICACION" in col_upper:
            col_nombre = col
        elif "PALABRA" in col_upper or "CLAVE" in col_upper:
            col_palabras = col
        elif "TIPO" in col_upper and "COINCIDENCIA" in col_upper:
            col_tipo = col
        elif "EXCLUIR" in col_upper:
            col_excluir = col
    
    if col_nombre is None or col_palabras is None:
        return clasificadores
    
    for _, row in df.iterrows():
        nombre = str(row[col_nombre]).strip() if pd.notna(row[col_nombre]) else ""
        if not nombre or nombre == "nan":
            continue
        
        # Procesar palabras clave (pueden estar separadas por |, , o ;)
        palabras_str = str(row[col_palabras]) if pd.notna(row[col_palabras]) else ""
        palabras_clave = []
        if palabras_str and palabras_str != "nan":
            # Separar por diferentes delimitadores
            for delimiter in ["|", ";", ","]:
                if delimiter in palabras_str:
                    palabras_clave = [p.strip() for p in palabras_str.split(delimiter) if p.strip()]
                    break
            if not palabras_clave:
                palabras_clave = [palabras_str.strip()]
        
        # Tipo de coincidencia
        tipo_coincidencia = "contiene_cualquiera"  # Por defecto
        if col_tipo and pd.notna(row[col_tipo]):
            tipo_val = str(row[col_tipo]).strip().upper()
            if "EXACTO" in tipo_val or "EXACT" in tipo_val:
                tipo_coincidencia = "contiene_exacto"
        
        # Exclusiones
        excluir = []
        if col_excluir and pd.notna(row[col_excluir]):
            excluir_str = str(row[col_excluir])
            if excluir_str and excluir_str != "nan":
                for delimiter in ["|", ";", ","]:
                    if delimiter in excluir_str:
                        excluir = [e.strip() for e in excluir_str.split(delimiter) if e.strip()]
                        break
                if not excluir:
                    excluir = [excluir_str.strip()]
        
        clasificador = {
            "nombre": nombre,
            "palabras_clave": palabras_clave,
            "tipo": tipo_coincidencia
        }
        
        if excluir:
            clasificador["excluir"] = excluir
        
        clasificadores.append(clasificador)
    
    return clasificadores

def cargar_clasificadores(ruta_config=None):
    """
    Carga la configuración de clasificadores desde un archivo JSON o Excel.
    
    Args:
        ruta_config: Ruta del archivo. Si es None, usa la configuración por defecto.
    
    Returns:
        dict: Configuración cargada o None si hay error
    """
    if ruta_config is None:
        ruta_config = CONFIG_CLASIFICADORES
    
    try:
        # Si es una ruta relativa, buscar en el directorio base
        if not Path(ruta_config).is_absolute():
            ruta_completa = Path(__file__).parent / ruta_config
        else:
            ruta_completa = Path(ruta_config)
        
        if not ruta_completa.exists():
            return None
        
        # Determinar tipo de archivo por extensión
        if ruta_completa.suffix.lower() == '.xlsx':
            config = cargar_clasificadores_desde_excel(ruta_completa)
        else:
            # Asumir JSON
            with open(ruta_completa, 'r', encoding='utf-8') as f:
                config = json.load(f)
        
        # Validar estructura básica
        if config and "clasificadores" not in config:
            st.warning(f"⚠️ El archivo {ruta_config} no tiene la estructura correcta.")
            return None
            
        return config
    except json.JSONDecodeError as e:
        st.error(f"❌ Error al leer el archivo JSON {ruta_config}: {e}")
        return None
    except Exception as e:
        st.error(f"❌ Error inesperado al cargar clasificadores: {e}")
        return None

def evaluar_clasificador(texto, clasificador):
    """Evalúa si un texto coincide con un clasificador según su tipo."""
    tipo = clasificador.get("tipo", "contiene_cualquiera")
    palabras_clave = clasificador.get("palabras_clave", [])
    excluir = clasificador.get("excluir", [])
    
    # Verificar exclusiones primero
    if excluir:
        if any(exclusion in texto for exclusion in excluir):
            return False
    
    if tipo == "contiene_exacto":
        # Todas las palabras deben estar presentes
        return all(palabra in texto for palabra in palabras_clave)
    elif tipo == "contiene_cualquiera":
        # Al menos una palabra debe estar presente
        return any(palabra in texto for palabra in palabras_clave)
    else:
        return False

def convertir_clasificadores_bd_a_dict(clasificadores_bd):
    """
    Convierte clasificadores de la BD al formato que espera clasificar_mejorado.
    
    Args:
        clasificadores_bd: Lista de objetos Clasificador de la BD
    
    Returns:
        dict: Formato compatible con config_clasificadores
    """
    config = {
        "clasificadores": {
            "abonos": [],
            "cargos": []
        },
        "clasificacion_default": "NO CLASIFICADO"
    }
    
    for clf in clasificadores_bd:
        clasificador_dict = {
            "nombre": clf.nombre,
            "palabras_clave": json.loads(clf.palabras_clave) if clf.palabras_clave else [],
            "tipo": clf.tipo_coincidencia
        }
        
        if clf.excluir:
            clasificador_dict["excluir"] = json.loads(clf.excluir)
        
        # Agregar a la lista correspondiente
        if clf.tipo == TipoTransaccion.ABONO:
            config["clasificadores"]["abonos"].append(clasificador_dict)
        else:
            config["clasificadores"]["cargos"].append(clasificador_dict)
    
    return config


def fusionar_configs_clasificadores(config_base, config_usuario):
    """
    Fusiona config base + config usuario (BD) sin perder reglas existentes.
    Prioriza las reglas del usuario evaluándolas primero.
    """
    def _lista(cfg, key):
        if not cfg:
            return []
        return cfg.get("clasificadores", {}).get(key, []) or []

    def _firma(regla):
        nombre = str(regla.get("nombre", "")).strip()
        tipo = str(regla.get("tipo", "contiene_cualquiera")).strip()
        palabras = tuple(sorted(str(p).strip() for p in (regla.get("palabras_clave", []) or []) if str(p).strip()))
        excluir = tuple(sorted(str(p).strip() for p in (regla.get("excluir", []) or []) if str(p).strip()))
        return (nombre, tipo, palabras, excluir)

    fusion = {
        "clasificadores": {"abonos": [], "cargos": []},
        "clasificacion_default": "NO CLASIFICADO"
    }
    if config_base and config_base.get("clasificacion_default"):
        fusion["clasificacion_default"] = config_base.get("clasificacion_default")
    if config_usuario and config_usuario.get("clasificacion_default"):
        fusion["clasificacion_default"] = config_usuario.get("clasificacion_default")

    for lista_key in ["abonos", "cargos"]:
        seen = set()
        # Usuario primero (prioridad), luego base
        for regla in (_lista(config_usuario, lista_key) + _lista(config_base, lista_key)):
            if not isinstance(regla, dict):
                continue
            sig = _firma(regla)
            if sig in seen:
                continue
            seen.add(sig)
            fusion["clasificadores"][lista_key].append(regla)

    return fusion

def clasificar_mejorado(texto, abono, config_clasificadores):
    """
    Clasifica una transacción según el texto y el monto de abono.
    
    Args:
        texto: Texto normalizado de la transacción
        abono: Monto de abono (positivo para ingresos, negativo o cero para egresos)
        config_clasificadores: Diccionario con la configuración de clasificadores
    
    Returns:
        str: Nombre de la clasificación o "NO CLASIFICADO"
    """
    if config_clasificadores is None:
            return "NO CLASIFICADO"

    texto = normalizar(texto)
    clasificadores = config_clasificadores.get("clasificadores", {})
    clasificacion_default = config_clasificadores.get("clasificacion_default", "NO CLASIFICADO")
    
    # Seleccionar lista de clasificadores según tipo de transacción
    lista_clasificadores = clasificadores.get("abonos", []) if abono > 0 else clasificadores.get("cargos", [])
    
    # Evaluar cada clasificador en orden
    for clasificador in lista_clasificadores:
        if evaluar_clasificador(texto, clasificador):
            return clasificador.get("nombre", clasificacion_default)
    
    return clasificacion_default


def cargar_datos_desde_bd(archivo_id, usuario_id):
    """
    Carga datos desde la base de datos usando el archivo_id.
    Este enfoque evita problemas de serialización con DataFrames grandes en session_state.
    
    Args:
        archivo_id: ID del archivo en la base de datos
        usuario_id: ID del usuario
    
    Returns:
        pd.DataFrame: DataFrame con los datos cargados o None si hay error
    """
    try:
        # Obtener transacciones del archivo específico
        transacciones_bd = obtener_transacciones(
            usuario_id=usuario_id,
            fecha_desde=None,
            fecha_hasta=None,
            archivo_id=archivo_id
        )
        
        if transacciones_bd is None or len(transacciones_bd) == 0:
            return None
        
        # Convertir a DataFrame
        datos = []
        for trans in transacciones_bd:
            datos.append({
                "FECHA": trans.fecha,
                "DESCRIPCION": trans.descripcion or "",
                "ABONOS (CLP)": float(trans.abono) if trans.abono else 0,
                "CARGOS (CLP)": float(trans.cargo) if trans.cargo else 0,
                "SALDO (CLP)": float(trans.saldo) if trans.saldo else None,
                "CLASIFICACION": trans.clasificacion or "NO CLASIFICADO",
                "COMENTARIO": trans.comentario or ""
            })
        
        if len(datos) == 0:
            return None
        
        df = pd.DataFrame(datos)
        
        if df is None or df.empty:
            return None
        
        # Asegurar que las columnas necesarias estén presentes
        if "FECHA" in df.columns:
            # Guardar el número de filas antes de convertir fechas
            filas_antes = len(df)
            df["FECHA"] = pd.to_datetime(df["FECHA"], errors='coerce')
            # Verificar si se perdieron filas después de convertir fechas
            filas_despues = len(df)
            if filas_despues != filas_antes:
                st.sidebar.warning(f"⚠️ Se perdieron {filas_antes - filas_despues} filas al convertir fechas")
        else:
            st.sidebar.warning(f"⚠️ No se encontró la columna FECHA en el DataFrame")
        
        if "DESCRIPCION" not in df.columns:
            df["DESCRIPCION"] = ""
        if "ABONOS (CLP)" not in df.columns:
            df["ABONOS (CLP)"] = 0
        if "CARGOS (CLP)" not in df.columns:
            df["CARGOS (CLP)"] = 0
        if "CLASIFICACION" not in df.columns:
            df["CLASIFICACION"] = "NO CLASIFICADO"
        if "COMENTARIO" not in df.columns:
            df["COMENTARIO"] = df["DESCRIPCION"].apply(normalizar) if "DESCRIPCION" in df.columns else ""
        
        # Verificación final
        if df.empty or len(df) == 0:
            return None
        
        return df
    except Exception as e:
        st.error(f"❌ Error al cargar datos desde BD: {e}")
        return None

def encontrar_fila_encabezados(path):
    """
    Encuentra la fila que contiene los encabezados de las columnas.
    Lee el archivo línea por línea buscando la fila con los encabezados.
    
    Returns:
        int: Número de fila (0-indexed) donde están los encabezados, o 0 si no se encuentra
    """
    palabras_clave = [
        'FECHA', 'DESCRIPCION',
        'ABONOS', 'INGRESOS', 'ENTRADAS', 'CREDITO', 'ABONO',
        'DEPOSITOS', 'DEPOSITO', 'DEPOSIT',
        'CARGOS', 'EGRESOS', 'SALIDAS', 'DEBITO',
        'SALDO',
        'CANAL', 'SUCURSAL', 'DOCTO', 'DOCUMENTO', 'GLOSA', 'DETALLE', 'FECHA OPERACION'
    ]
    
    try:
        # Leer las primeras 20 filas para buscar encabezados
        df_temp = pd.read_excel(path, header=None, nrows=20)
        
        for idx in range(len(df_temp)):
            row = df_temp.iloc[idx]
            # Convertir toda la fila a string y buscar palabras clave
            fila_str = ' '.join([str(val).upper() for val in row.values if pd.notna(val) and str(val).strip() != ''])
            
            # Contar cuántas palabras clave aparecen en esta fila
            coincidencias = sum(1 for palabra in palabras_clave if palabra in fila_str)
            
            # Si encontramos al menos 2 palabras clave, probablemente es la fila de encabezados
            if coincidencias >= 2:
                return idx
        
        return 0
    except:
        return 0

def cargar_datos(path, config_clasificadores):
    """
    Carga y procesa los datos del archivo Excel.
    Detecta automáticamente dónde empiezan los datos reales, saltando encabezados.
    
    Args:
        path: Ruta del archivo Excel
        config_clasificadores: Configuración de clasificadores
    
    Returns:
        pd.DataFrame: DataFrame procesado con clasificaciones
    """
    try:
        # Acumular mensajes de debug para mostrarlos en un expander
        mensajes_debug = []
        
        # Buscar la fila de encabezados primero
        fila_encabezados = encontrar_fila_encabezados(path)
        
        # Leer el archivo usando la fila encontrada como encabezados
        if fila_encabezados > 0:
            df = pd.read_excel(path, header=fila_encabezados)
            mensajes_debug.append(("info", f"💡 Se detectaron encabezados en la fila {fila_encabezados + 1}"))
        else:
            # Intentar leer sin especificar header
            df = pd.read_excel(path, header=0)
        
        # Limpiar nombres de columnas
        df.columns = df.columns.str.strip().str.upper()
        
        # Si las columnas son UNNAMED, intentar leer de nuevo buscando mejor
        if any('UNNAMED' in str(col) for col in df.columns):
            mensajes_debug.append(("warning", "⚠️ Detectadas columnas sin nombre. Buscando encabezados de forma más agresiva..."))
            # Intentar leer sin header y buscar manualmente
            df_temp = pd.read_excel(path, header=None, nrows=30)
            
            # Buscar fila con encabezados
            encontrado = False
            for idx in range(len(df_temp)):
                row = df_temp.iloc[idx]
                valores = [str(val).upper().strip() for val in row.values if pd.notna(val) and str(val).strip() != '']
                fila_str = ' '.join(valores)
                
                # Verificar si esta fila tiene las palabras clave
                tiene_fecha = any('FECHA' in v for v in valores)
                tiene_descripcion = any('DESCRIPCION' in v or 'GLOSA' in v or 'DETALLE' in v for v in valores)
                tiene_abonos = any('ABONO' in v or 'CREDITO' in v for v in valores)
                tiene_cargos = any('CARGO' in v or 'DEBITO' in v for v in valores)
                
                if (tiene_fecha or tiene_descripcion) and (tiene_abonos or tiene_cargos):
                    # Esta es la fila de encabezados
                    df = pd.read_excel(path, header=idx)
                    df.columns = df.columns.str.strip().str.upper()
                    mensajes_debug.append(("success", f"✅ Encabezados encontrados en la fila {idx + 1}"))
                    encontrado = True
                    break
            
            if not encontrado:
                mensajes_debug.append(("warning", "⚠️ No se pudieron detectar los encabezados automáticamente"))
                # Guardar df_temp para mostrarlo en el expander si es necesario
                if 'df_temp' in locals():
                    mensajes_debug.append(("dataframe", df_temp.head(10)))
        
        # Mostrar mensajes de debug en un expander (colapsado por defecto)
        if mensajes_debug:
            with st.expander("🔧 Información de carga de datos", expanded=False):
                for tipo, mensaje in mensajes_debug:
                    if tipo == "info":
                        st.info(mensaje)
                    elif tipo == "warning":
                        st.warning(mensaje)
                    elif tipo == "success":
                        st.success(mensaje)
                    elif tipo == "dataframe":
                        st.write("Primeras 10 filas del archivo:")
                        st.dataframe(mensaje)
        
        # Limpiar filas vacías al inicio y final
        df = df.dropna(how='all').reset_index(drop=True)
        

        # Normalizar nombres de columnas
        if "DESCRIPCIÓN" in df.columns:
            df.rename(columns={"DESCRIPCIÓN": "DESCRIPCION"}, inplace=True)
        
        # Buscar columnas similares (flexibilidad en nombres)
        mapeo_columnas = {}
        columnas_upper = [col.upper() for col in df.columns]
        
        # Buscar FECHA
        if "FECHA" not in df.columns:
            for col in df.columns:
                if "FECHA" in col.upper() or "DATE" in col.upper():
                    mapeo_columnas[col] = "FECHA"
                    break
        
        # Buscar DESCRIPCION
        if "DESCRIPCION" not in df.columns:
            for col in df.columns:
                if "DESCRIPCION" in col.upper() or "DESCRIP" in col.upper() or "DETALLE" in col.upper() or "GLOSA" in col.upper():
                    mapeo_columnas[col] = "DESCRIPCION"
                    break
        
        # Buscar ABONOS
        if "ABONOS (CLP)" not in df.columns:
            for col in df.columns:
                col_upper = str(col).upper()
                if "ABONO" in col.upper() and "CLP" in col.upper():
                    mapeo_columnas[col] = "ABONOS (CLP)"
                    break
                elif (
                    ("ABONO" in col_upper)
                    or ("DEPOSITO" in col_upper)
                    or ("DEPOSITOS" in col_upper)
                    or ("INGRESO" in col_upper)
                    or ("ENTRADA" in col_upper)
                    or ("CREDITO" in col_upper)
                ):
                    # Evitar columnas que claramente representan egresos/cargos.
                    if any(k in col_upper for k in ["DEBITO", "EGRESO", "EGRESOS", "CARGO", "CARGOS", "SALIDA", "SALIDAS"]):
                        continue
                    mapeo_columnas[col] = "ABONOS (CLP)"
                    break
        
        # Buscar CARGOS (muchos bancos cambian encabezados: CARGOS/DEBITO/EGRESOS)
        if "CARGOS (CLP)" not in df.columns:
            for col in df.columns:
                col_upper = col.upper()
                # Incluye variantes con y sin "(CLP)"
                if ("CARGO" in col_upper or "DEBITO" in col_upper or "DÉBITO" in col_upper) and "CLP" in col_upper:
                    mapeo_columnas[col] = "CARGOS (CLP)"
                    break
                if ("CARGOS" in col_upper or "EGRESO" in col_upper or "EGRESOS" in col_upper) and ("CLP" in col_upper or True):
                    mapeo_columnas[col] = "CARGOS (CLP)"
                    break
                if ("DEBITO" in col_upper or "DÉBITO" in col_upper) and ("CLP" in col_upper):
                    mapeo_columnas[col] = "CARGOS (CLP)"
                    break

        # Aplicar mapeo
        if mapeo_columnas:
            df.rename(columns=mapeo_columnas, inplace=True)

        # Validar columnas requeridas
        columnas_requeridas = ["DESCRIPCION", "FECHA", "ABONOS (CLP)"]
        columnas_faltantes = [col for col in columnas_requeridas if col not in df.columns]
        
        if columnas_faltantes:
            # Aviso amigable para el cliente: formato no corresponde a "Cartola Histórica"
            st.warning(
                "⚠️ Este archivo no parece tener el formato esperado (Cartola Histórica). "
                "Vuelve a descargar/subir la 'Cartola Histórica' del banco (no 'Movimientos del mes')."
            )
            st.info(f"💡 Columnas encontradas en el archivo: {', '.join(df.columns.tolist()[:15])}")
            st.caption(f"Detalles técnicos (faltan columnas mínimas): {', '.join(columnas_faltantes)}")
            
            # Mostrar primeras filas para ayudar a entender la estructura
            with st.expander("🔍 Ver primeras filas del archivo (para depuración)"):
                st.dataframe(df.head(10))
            
            st.info("💡 Si tu archivo tiene un formato diferente, puedes configurar el mapeo de columnas en la sección de configuración.")
            
            return None

        # Procesar datos
        df["DESCRIPCION"] = df["DESCRIPCION"].astype(str)
        df["COMENTARIO"] = df["DESCRIPCION"].apply(normalizar)
        df["FECHA"] = pd.to_datetime(df["FECHA"], dayfirst=True, errors='coerce')

        # Si no se pudo identificar CARGOS, crearla para que métricas/gráficos no fallen
        if "CARGOS (CLP)" not in df.columns:
            df["CARGOS (CLP)"] = 0

        # Clasificar transacciones
        df["CLASIFICACION"] = df.apply(
            lambda row: clasificar_mejorado(row["COMENTARIO"], row["ABONOS (CLP)"], config_clasificadores), 
            axis=1
        )
        
        # Eliminar columnas sin nombre
        df = df.loc[:, ~df.columns.str.contains("^UNNAMED")]
        return df
    except Exception as e:
        st.error(f"❌ Error al procesar el archivo: {e}")
        return None

# ---------- MOSTRAR INFORMACIÓN DEL USUARIO ----------
show_user_info()

# ---------- ALERTAS ----------
usuario_actual = get_current_user()
if usuario_actual:
    alertas = obtener_alertas(usuario_actual.id, no_leidas=True)
    if alertas:
        st.sidebar.markdown("---")
        st.sidebar.markdown("### ⚠️ Alertas")
        for alerta in alertas[:5]:  # Mostrar máximo 5
            with st.sidebar.container():
                st.warning(f"**{alerta.tipo}**: {alerta.mensaje}")
                if st.button(f"✓ Marcar como leída", key=f"alert_{alerta.id}", use_container_width=True):
                    from database.crud import marcar_alerta_leida
                    marcar_alerta_leida(alerta.id, usuario_actual.id)
                    st.rerun()

# ---------- CARGA DE CONFIGURACIÓN Y DATOS ----------
st.sidebar.markdown("---")
st.sidebar.markdown("### 📁 Carga de Datos")

# Cargar clasificadores desde BD
usuario_actual = get_current_user()
config_clasificadores = None

if usuario_actual:
    # Cargar base por defecto (si existe)
    config_base_default = None
    configs_disponibles = listar_configuraciones()
    if configs_disponibles:
        config_base_default = cargar_clasificadores(CONFIG_CLASIFICADORES)

    # Cargar clasificadores del usuario desde BD
    clasificadores_bd = obtener_clasificadores(usuario_actual.id)
    if clasificadores_bd:
        config_bd_usuario = convertir_clasificadores_bd_a_dict(clasificadores_bd)
        # IMPORTANTE: fusionar BD + base para no perder reglas históricas.
        config_clasificadores = fusionar_configs_clasificadores(config_base_default, config_bd_usuario)
        st.sidebar.markdown(
            f'<div style="background-color: #d4edda; color: #155724; padding: 0.75rem; border-radius: 6px; margin: 0.5rem 0;">'
            f'✅ <strong>{len(clasificadores_bd)} clasificadores</strong> cargados desde BD'
            f'</div>',
            unsafe_allow_html=True
        )
    else:
        # Si no tiene clasificadores en BD, intentar cargar desde archivos (compatibilidad)
        st.sidebar.info("💡 No tienes clasificadores configurados. Usando configuración por defecto.")
        config_clasificadores = config_base_default
else:
    st.sidebar.warning("⚠️ No se pudo obtener información del usuario")

# Mantener el clasificador activo en session_state para permitir edición en UI
if config_clasificadores is not None:
    # Importante: conservar el clasificador editado en sesión entre reruns (ej: download button).
    # Solo reinicializar cuando no exista o cuando cambie de usuario.
    usuario_cfg_ss = st.session_state.get("config_clasificadores_usuario_id")
    if (
        "config_clasificadores" not in st.session_state
        or st.session_state.get("config_clasificadores") is None
        or usuario_cfg_ss != (usuario_actual.id if usuario_actual else None)
    ):
        st.session_state.config_clasificadores = config_clasificadores
        st.session_state.config_clasificadores_usuario_id = usuario_actual.id if usuario_actual else None

    # Usar siempre el config vigente de sesión para clasificar en esta ejecución.
    config_clasificadores = st.session_state.config_clasificadores

# ---------- OPCIÓN 1: CARGAR DESDE BASE DE DATOS ----------
if usuario_actual:
    st.sidebar.markdown("---")
    st.sidebar.markdown("### 💾 Cartolas Guardadas")
    archivos_guardados = obtener_archivos(usuario_actual.id)
    
    if archivos_guardados:
        nombres_archivos = [f"{arch.nombre_archivo} ({arch.fecha_carga.strftime('%d-%m-%Y')})" for arch in archivos_guardados[:10]]
        archivo_seleccionado_bd = st.sidebar.selectbox(
            "📂 Cargar desde Base de Datos",
            options=["-- Seleccionar --"] + nombres_archivos,
            help="Selecciona una cartola guardada anteriormente"
        )
        
        if archivo_seleccionado_bd and archivo_seleccionado_bd != "-- Seleccionar --":
            # Encontrar el archivo seleccionado
            idx_seleccionado = nombres_archivos.index(archivo_seleccionado_bd)
            archivo_seleccionado = archivos_guardados[idx_seleccionado]
            
            # Cargar transacciones desde BD
            if st.sidebar.button("📥 Cargar Transacciones", use_container_width=True, key=f"cargar_bd_{archivo_seleccionado.id}"):
                # Usar la función centralizada para cargar datos
                df_cargado = cargar_datos_desde_bd(archivo_seleccionado.id, usuario_actual.id)
                
                if df_cargado is not None and not df_cargado.empty and len(df_cargado) > 0:
                    # Guardar solo el archivo_id en session_state (enfoque más confiable)
                    # No guardamos el DataFrame completo para evitar problemas de serialización
                    st.session_state.archivo_id_cargado_bd = archivo_seleccionado.id
                    st.session_state.archivo_cargado_bd = archivo_seleccionado.nombre_archivo
                    
                    # Limpiar cualquier DataFrame previo
                    if 'df_cargado_bd' in st.session_state:
                        del st.session_state.df_cargado_bd
                    
                    # Limpiar bandera de archivo nuevo (ya que viene de BD)
                    if 'archivo_nuevo_procesado' in st.session_state:
                        del st.session_state.archivo_nuevo_procesado
                    if 'nombre_archivo_nuevo' in st.session_state:
                        del st.session_state.nombre_archivo_nuevo
                    
                    # Mostrar mensaje de éxito y hacer rerun
                    st.sidebar.success(f"✅ {len(df_cargado)} transacciones cargadas desde BD")
                    st.rerun()
                else:
                    st.sidebar.error(f"❌ No se pudieron cargar las transacciones para el archivo '{archivo_seleccionado.nombre_archivo}'")
                    st.sidebar.info("💡 Verifica que el archivo haya sido guardado correctamente con transacciones en la base de datos.")
    else:
        st.sidebar.info("💡 No hay cartolas guardadas. Sube una cartola y guárdala en BD.")

# ---------- OPCIÓN 2: SUBIR ARCHIVO EXCEL ----------
st.sidebar.markdown("---")
st.sidebar.markdown("### 📤 Subir Nueva Cartola")
archivo_subido = st.sidebar.file_uploader(
    "Selecciona archivo Excel",
    type=['xlsx', 'xls'],
    help="Sube tu archivo de cartola bancaria en formato Excel"
)

archivo = None
df = None

# PRIORIDAD 1: Si se sube un archivo nuevo, tiene máxima prioridad
# Limpiar cualquier referencia a BD antes de procesar el archivo nuevo
if archivo_subido:
        # Limpiar datos de BD PRIMERO, antes de procesar el archivo nuevo
        if 'archivo_id_cargado_bd' in st.session_state:
            st.session_state.archivo_id_cargado_bd = None
            st.session_state.archivo_cargado_bd = None
        # Limpiar cualquier referencia antigua a df_cargado_bd
        if 'df_cargado_bd' in st.session_state:
            del st.session_state.df_cargado_bd
        
        # Guardar archivo temporalmente
        with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as tmp_file:
            tmp_file.write(archivo_subido.getvalue())
            archivo = tmp_file.name
        
        # Marcar que se procesó un archivo nuevo (para mostrar el botón de guardar)
        st.session_state.archivo_nuevo_procesado = True
        st.session_state.nombre_archivo_nuevo = archivo_subido.name
        st.sidebar.success(f"✅ Archivo cargado: {archivo_subido.name}")

# PRIORIDAD 2: Si no hay archivo subido ni archivo local, verificar si hay un archivo_id guardado
# Si hay archivo_id, cargar los datos desde BD
if df is None and 'archivo_id_cargado_bd' in st.session_state and st.session_state.archivo_id_cargado_bd is not None:
    if usuario_actual:
        # Cargar datos desde BD usando el archivo_id
        archivo_id = st.session_state.archivo_id_cargado_bd
        df_bd = cargar_datos_desde_bd(archivo_id, usuario_actual.id)
        
        if df_bd is not None and not df_bd.empty and len(df_bd) > 0:
            df = df_bd
            # Limpiar bandera de archivo nuevo (ya que viene de BD)
            if 'archivo_nuevo_procesado' in st.session_state:
                del st.session_state.archivo_nuevo_procesado
            if 'nombre_archivo_nuevo' in st.session_state:
                del st.session_state.nombre_archivo_nuevo
            st.sidebar.success(f"✅ Cargado desde BD: {st.session_state.get('archivo_cargado_bd', 'N/A')} ({len(df)} registros)")
        else:
            # No se pudieron cargar los datos
            st.sidebar.error(f"❌ No se pudieron cargar los datos. Verifica que el archivo tenga transacciones guardadas en la base de datos.")
    else:
        st.sidebar.error("❌ No se pudo obtener información del usuario")

if df is None:
    st.sidebar.info("💡 Sube un archivo Excel o carga una cartola guardada desde la base de datos")

# ---------- IMPORTAR CLASIFICADORES DESDE ARCHIVO ----------
st.sidebar.markdown("---")
st.sidebar.subheader("⚙️ Configuración de Clasificadores")

# Opción para importar clasificadores desde archivo
archivo_clasificadores = st.sidebar.file_uploader(
    "📥 Importar Clasificadores",
    type=['xlsx', 'json'],
    help="Sube un archivo Excel o JSON con tus clasificadores para importarlos a tu cuenta"
)

if archivo_clasificadores and usuario_actual:
    if st.sidebar.button("💾 Importar Clasificadores", use_container_width=True):
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=f'.{archivo_clasificadores.name.split(".")[-1]}') as tmp_file:
                tmp_file.write(archivo_clasificadores.getvalue())
                tmp_path = tmp_file.name
            
            # Cargar clasificadores desde archivo
            if tmp_path.endswith('.xlsx'):
                config_temp = cargar_clasificadores_desde_excel(tmp_path)
            else:
                config_temp = cargar_clasificadores(tmp_path)
            
            if config_temp and config_temp.get("clasificadores"):
                # Importar a BD
                from database.crud import crear_clasificador, eliminar_clasificador
                importados = 0
                reemplazados = 0

                # Reemplazo completo: desactivar clasificadores activos actuales del usuario
                # para que el nuevo archivo importado sea la fuente principal.
                clasificadores_actuales = obtener_clasificadores(usuario_actual.id)
                for clf in clasificadores_actuales:
                    if eliminar_clasificador(clf.id, usuario_actual.id):
                        reemplazados += 1
                
                # Importar abonos
                for clf in config_temp["clasificadores"].get("abonos", []):
                    crear_clasificador(
                        usuario_id=usuario_actual.id,
                        nombre=clf["nombre"],
                        tipo="abono",
                        palabras_clave=clf.get("palabras_clave", []),
                        tipo_coincidencia=clf.get("tipo", "contiene_cualquiera"),
                        excluir=clf.get("excluir"),
                        orden=importados
                    )
                    importados += 1
                
                # Importar cargos
                for clf in config_temp["clasificadores"].get("cargos", []):
                    crear_clasificador(
                        usuario_id=usuario_actual.id,
                        nombre=clf["nombre"],
                        tipo="cargo",
                        palabras_clave=clf.get("palabras_clave", []),
                        tipo_coincidencia=clf.get("tipo", "contiene_cualquiera"),
                        excluir=clf.get("excluir"),
                        orden=importados
                    )
                    importados += 1
                
                st.sidebar.success(f"✅ {importados} clasificadores importados (reemplazados anteriores: {reemplazados})")
                # Reset para que el próximo rerun recargue desde BD
                if "config_clasificadores" in st.session_state:
                    del st.session_state.config_clasificadores
                if "config_clasificadores_usuario_id" in st.session_state:
                    del st.session_state.config_clasificadores_usuario_id
                st.session_state.reclasificar_en_vista = True
                st.rerun()
            else:
                st.sidebar.error("❌ El archivo no tiene el formato correcto")
            
            # Limpiar archivo temporal
            os.unlink(tmp_path)
        except Exception as e:
            st.sidebar.error(f"❌ Error al importar: {e}")

# Detectar si el archivo cambió
archivo_cambio = archivo != st.session_state.archivo_actual
if archivo_cambio:
    st.session_state.archivo_actual = archivo

if config_clasificadores is not None and usuario_actual:
    # Si hay un archivo subido, procesarlo (tiene prioridad sobre datos de BD)
    # Esto asegura que si el usuario sube un archivo nuevo, se procese ese archivo
    if archivo_subido and archivo:
        # Procesar el archivo subido (tiene prioridad)
        try:
            df = cargar_datos(archivo, config_clasificadores)
        except Exception as e:
            st.error(f"❌ Error al procesar el archivo: {e}")
            st.exception(e)
            df = None
    elif df is not None and not df.empty:
        # Los datos ya están cargados (desde BD)
        # Continuar con el procesamiento de datos
        pass
    
    # Verificar si tenemos datos o mostrar mensaje
    if df is None or df.empty:
        if not archivo:
            st.info("👆 Por favor, sube un archivo Excel o carga una cartola guardada desde la base de datos para comenzar.")
            st.stop()
    
    # Procesar datos si están disponibles
    if df is not None and not df.empty:
        try:
            # Si el DataFrame viene de BD, ya tiene CLASIFICACION
            # Si viene de archivo, necesita procesarse
            viene_de_bd_en_vista = (
                'archivo_id_cargado_bd' in st.session_state
                and st.session_state.archivo_id_cargado_bd is not None
                and not archivo_subido
            )
            force_reclasificar = (
                st.session_state.get("config_clasificadores_editado", False)
                or st.session_state.get("reclasificar_en_vista", False)
                or viene_de_bd_en_vista
            )
            if force_reclasificar or "CLASIFICACION" not in df.columns:
                # Procesar datos si no están clasificados
                if "DESCRIPCION" in df.columns:
                    df["DESCRIPCION"] = df["DESCRIPCION"].astype(str)
                    df["COMENTARIO"] = df["DESCRIPCION"].apply(normalizar)
                if "FECHA" in df.columns:
                    df["FECHA"] = pd.to_datetime(df["FECHA"], dayfirst=True, errors='coerce')
                
                # Clasificar transacciones
                if "COMENTARIO" in df.columns and "ABONOS (CLP)" in df.columns:
                    df["CLASIFICACION"] = df.apply(
                        lambda row: clasificar_mejorado(row["COMENTARIO"], row["ABONOS (CLP)"], config_clasificadores), 
                        axis=1
                    )
                
                # Consumir el flag: ya estamos usando el clasificador actualizado
                if force_reclasificar:
                    st.session_state.config_clasificadores_editado = False
            
            # Guardar transacciones en BD (solo si no vienen de BD)
            # Verificar si los datos actuales vienen de BD usando el archivo_id
            viene_de_bd_guardar = ('archivo_id_cargado_bd' in st.session_state and 
                                  st.session_state.archivo_id_cargado_bd is not None)
            
            # Mostrar el botón de guardar si:
            # 1. Se procesó un archivo nuevo (archivo_nuevo_procesado = True)
            # 2. O si no viene de BD (archivo nuevo que aún no se ha guardado)
            archivo_nuevo = st.session_state.get('archivo_nuevo_procesado', False)
            if archivo_nuevo or not viene_de_bd_guardar:
                if st.sidebar.button("💾 Guardar en Base de Datos", use_container_width=True):
                    try:
                        # Registrar archivo
                        nombre_archivo = st.session_state.get('nombre_archivo_nuevo', 'cartola_importada.xlsx')
                        archivo_registrado = registrar_archivo(
                            usuario_id=usuario_actual.id,
                            nombre_archivo=nombre_archivo,
                            total_registros=len(df)
                        )
                        
                        # Preparar transacciones para guardar
                        transacciones_para_guardar = []
                        for _, row in df.iterrows():
                            transacciones_para_guardar.append({
                                "fecha": row["FECHA"] if pd.notna(row["FECHA"]) else datetime.now(),
                                "descripcion": str(row["DESCRIPCION"]) if pd.notna(row["DESCRIPCION"]) else "",
                                "abono": float(row["ABONOS (CLP)"]) if pd.notna(row["ABONOS (CLP)"]) else 0,
                                "cargo": float(row["CARGOS (CLP)"]) if "CARGOS (CLP)" in row and pd.notna(row["CARGOS (CLP)"]) else 0,
                                "saldo": float(row["SALDO (CLP)"]) if "SALDO (CLP)" in row and pd.notna(row["SALDO (CLP)"]) else None,
                                "clasificacion": str(row["CLASIFICACION"]) if pd.notna(row["CLASIFICACION"]) else "NO CLASIFICADO",
                                "comentario": str(row["COMENTARIO"]) if "COMENTARIO" in row and pd.notna(row["COMENTARIO"]) else ""
                            })
                        
                        # Guardar transacciones
                        total_guardadas = guardar_transacciones(
                            transacciones_para_guardar,
                            usuario_id=usuario_actual.id,
                            archivo_id=archivo_registrado.id
                        )
                        
                        # Actualizar session_state con el archivo guardado
                        st.session_state.archivo_id_cargado_bd = archivo_registrado.id
                        st.session_state.archivo_cargado_bd = archivo_registrado.nombre_archivo
                        # Limpiar la bandera de archivo nuevo
                        if 'archivo_nuevo_procesado' in st.session_state:
                            del st.session_state.archivo_nuevo_procesado
                        if 'nombre_archivo_nuevo' in st.session_state:
                            del st.session_state.nombre_archivo_nuevo
                        
                        st.sidebar.success(f"✅ {total_guardadas} transacciones guardadas")
                        st.rerun()
                    except Exception as e:
                        st.sidebar.error(f"❌ Error al guardar: {e}")
            
            # Verificar transacciones sin clasificar EN EL DATASET ACTUAL (no en BD)
            # Esto se ejecuta siempre, independientemente de si viene de BD o no
            if "CLASIFICACION" in df.columns:
                if "mensaje_reclasificacion" in st.session_state:
                    tipo_msg, texto_msg = st.session_state.pop("mensaje_reclasificacion")
                    if tipo_msg == "warning":
                        st.warning(texto_msg)
                    else:
                        st.success(texto_msg)

                sin_clasificar_actual = df[df["CLASIFICACION"].isin([None, "NO CLASIFICADO", ""])]
                if len(sin_clasificar_actual) > 0:
                    st.warning(f"⚠️ Hay {len(sin_clasificar_actual)} transacciones sin clasificar en este dataset")
                    config_activo = st.session_state.get("config_clasificadores", config_clasificadores)
                    if not config_activo:
                        st.error("❌ No se encontró la configuración de clasificadores activa.")
                    else:
                        # Opciones del dropdown:
                        # - Prioridad: categorías desde el config activo
                        # - Respaldo: también incluimos categorías desde el config cargado desde BD (por si el session_state quedó incompleto)
                        def _nombres_categorias(cfg):
                            if not cfg:
                                return []
                            abonos_n = [
                                c.get("nombre")
                                for c in cfg.get("clasificadores", {}).get("abonos", [])
                                if isinstance(c, dict) and c.get("nombre")
                            ]
                            cargos_n = [
                                c.get("nombre")
                                for c in cfg.get("clasificadores", {}).get("cargos", [])
                                if isinstance(c, dict) and c.get("nombre")
                            ]
                            return abonos_n + cargos_n

                        categorias_existentes = sorted(
                            set(_nombres_categorias(config_activo) + _nombres_categorias(config_clasificadores))
                        )
                        # Respaldo final: si por algún motivo los configs no traen nombres,
                        # levantar categorías activas directamente desde la BD del usuario.
                        categorias_db = []
                        if usuario_actual:
                            try:
                                clasificadores_db_fallback = obtener_clasificadores(usuario_actual.id)
                                categorias_db = sorted(
                                    set(
                                        clf.nombre.strip()
                                        for clf in clasificadores_db_fallback
                                        if getattr(clf, "nombre", None) and str(clf.nombre).strip()
                                    )
                                )
                            except Exception:
                                categorias_db = []

                        # Unión final con BD como fuente de verdad (evita quedar vacío si el config en memoria no trae nombres)
                        categorias_existentes = sorted(set(categorias_existentes + categorias_db))

                        # Respaldo adicional: categorías presentes en el dataset actual.
                        # Esto garantiza que el dropdown tenga opciones incluso si falla la carga de config/BD.
                        try:
                            categorias_df = sorted(
                                set(
                                    str(c).strip()
                                    for c in df["CLASIFICACION"].dropna().unique().tolist()
                                    if str(c).strip() and str(c).strip() != "NO CLASIFICADO"
                                )
                            )
                        except Exception:
                            categorias_df = []

                        categorias_existentes = sorted(set(categorias_existentes + categorias_df))
                        opciones_categoria = ["-- Seleccionar --"] + categorias_existentes

                        sin_clasificar_ui = sin_clasificar_actual.copy()
                        sin_clasificar_ui["CATEGORIA"] = "-- Seleccionar --"
                        sin_clasificar_ui["NUEVA_CATEGORIA"] = ""

                        columnas_ui = []
                        if "FECHA" in sin_clasificar_ui.columns:
                            columnas_ui.append("FECHA")
                        if "DESCRIPCION" in sin_clasificar_ui.columns:
                            columnas_ui.append("DESCRIPCION")
                        if "ABONOS (CLP)" in sin_clasificar_ui.columns:
                            columnas_ui.append("ABONOS (CLP)")
                        if "CARGOS (CLP)" in sin_clasificar_ui.columns:
                            columnas_ui.append("CARGOS (CLP)")

                        columnas_ui += ["CATEGORIA", "NUEVA_CATEGORIA"]

                        with st.expander("🧩 Gestionar NO CLASIFICADO (editar en pantalla)"):
                            st.caption("Selecciona una categoría existente o escribe una nueva. Luego se actualiza el JSON en memoria y se reclasifica la cartola.")
                            muestra_ejemplo = categorias_existentes[:5]
                            st.caption(f"Categorías disponibles: {len(categorias_existentes)} (ej: {', '.join(muestra_ejemplo) if muestra_ejemplo else 'N/A'})")
                            opciones_categoria_filtradas = ["-- Seleccionar --"] + categorias_existentes
                            
                            # UI robusta: evitamos st.data_editor con SelectboxColumn (en algunos despliegues
                            # no respeta options y queda vacío). En su lugar, usamos selectbox por fila.
                            max_filas_ui = 50
                            df_ui = sin_clasificar_ui.copy()
                            if len(df_ui) > max_filas_ui:
                                st.warning(f"Mostrando solo las primeras {max_filas_ui} filas para edición. Reduce el rango o vuelve a probar.")
                                df_ui = df_ui.head(max_filas_ui)

                            indices_ui = df_ui.index.tolist()
                            st.dataframe(
                                df_ui[columnas_ui].drop(columns=["CATEGORIA", "NUEVA_CATEGORIA"], errors="ignore"),
                                use_container_width=True
                            )

                            categoria_masiva = st.selectbox(
                                "Aplicar misma categoría a todas las filas visibles (opcional)",
                                options=opciones_categoria_filtradas,
                                index=0,
                                key="categoria_masiva_no_clasif"
                            )
                            if categoria_masiva and categoria_masiva != "-- Seleccionar --":
                                st.info(f"Se aplicará '{categoria_masiva}' a todas las filas visibles, salvo que escribas una categoría nueva en una fila específica.")

                            st.markdown("**Asignación por fila**")
                            for idx in indices_ui:
                                r = df_ui.loc[idx]
                                row_cols = st.columns([2, 6, 6])
                                with row_cols[0]:
                                    st.write(str(r.get("FECHA", ""))[:16])
                                with row_cols[1]:
                                    st.write(str(r.get("DESCRIPCION", ""))[:70])
                                with row_cols[2]:
                                    st.selectbox(
                                        "Categoría",
                                        options=opciones_categoria_filtradas,
                                        index=0,
                                        key=f"categoria_no_clasif_{idx}"
                                    )
                                    st.text_input(
                                        "Nueva (opcional)",
                                        value="",
                                        key=f"nueva_categoria_no_clasif_{idx}",
                                        placeholder="Ej: PROVEEDORES NACIONALES"
                                    )

                            if st.button("✅ Aplicar cambios y reclasificar", use_container_width=True):
                                # Copia profunda para no mutar directamente el objeto usado por Streamlit
                                config_nuevo = json.loads(json.dumps(config_activo))

                                def _get_lista_objetivo(row_):
                                    abono_val = float(row_.get("ABONOS (CLP)", 0) or 0)
                                    return "abonos" if abono_val > 0 else "cargos"

                                actualizados = 0
                                errores = 0
                                reglas_aprendidas = []

                                # Índice de reglas por (lista_objetivo, nombre, tipo) para evitar duplicados en memoria
                                indice_reglas = set()
                                for lista_base in ["abonos", "cargos"]:
                                    for regla in config_nuevo.get("clasificadores", {}).get(lista_base, []):
                                        nombre_r = str(regla.get("nombre", "")).strip()
                                        tipo_r = str(regla.get("tipo", "contiene_cualquiera")).strip()
                                        if nombre_r:
                                            indice_reglas.add((lista_base, nombre_r, tipo_r))

                                for idx in indices_ui:
                                    r = df_ui.loc[idx]
                                    cat_sel = str(st.session_state.get(f"categoria_no_clasif_{idx}", "")).strip()
                                    if (not cat_sel or cat_sel == "-- Seleccionar --") and categoria_masiva and categoria_masiva != "-- Seleccionar --":
                                        cat_sel = categoria_masiva
                                    cat_nueva = str(st.session_state.get(f"nueva_categoria_no_clasif_{idx}", "")).strip()
                                    nombre_categoria = cat_nueva if cat_nueva else cat_sel

                                    if not nombre_categoria or nombre_categoria == "-- Seleccionar --" or nombre_categoria == "NO CLASIFICADO":
                                        errores += 1
                                        continue

                                    # "Detalle Movimiento" en esta app corresponde a "DESCRIPCION".
                                    detalle = r.get("DESCRIPCION", "") if hasattr(r, "get") else ""
                                    detalle_norm = normalizar(detalle)
                                    if not detalle_norm:
                                        errores += 1
                                        continue

                                    lista_objetivo = _get_lista_objetivo(r)
                                    config_nuevo["clasificadores"].setdefault(lista_objetivo, [])
                                    reglas = config_nuevo["clasificadores"][lista_objetivo]

                                    # Regla de aprendizaje SIEMPRE como contiene_cualquiera para evitar conflictos
                                    # con reglas existentes de tipo contiene_exacto.
                                    key_regla_aprendida = (lista_objetivo, nombre_categoria, "contiene_cualquiera")
                                    regla_aprendida = None
                                    if key_regla_aprendida in indice_reglas:
                                        regla_aprendida = next(
                                            (
                                                x for x in reglas
                                                if x.get("nombre") == nombre_categoria and x.get("tipo", "contiene_cualquiera") == "contiene_cualquiera"
                                            ),
                                            None
                                        )

                                    if regla_aprendida is None:
                                        reglas.append({
                                            "nombre": nombre_categoria,
                                            "palabras_clave": [detalle_norm],
                                            "tipo": "contiene_cualquiera"
                                        })
                                        indice_reglas.add(key_regla_aprendida)
                                    else:
                                        palabras = regla_aprendida.get("palabras_clave", [])
                                        if detalle_norm not in palabras:
                                            palabras.append(detalle_norm)
                                            regla_aprendida["palabras_clave"] = palabras

                                    reglas_aprendidas.append((lista_objetivo, nombre_categoria, detalle_norm))

                                    actualizados += 1

                                st.session_state.config_clasificadores = config_nuevo
                                # Flag para forzar reclasificación en el siguiente render (especialmente si df viene de BD)
                                st.session_state.config_clasificadores_editado = True
                                # Mantener reclasificación activa en esta vista para que un rerun
                                # (ej: descargar JSON) no vuelva a mostrar CLASIFICACION antigua desde BD.
                                st.session_state.reclasificar_en_vista = True
                                # Reclasificar toda la cartola en pantalla
                                df["CLASIFICACION"] = df.apply(
                                    lambda row: clasificar_mejorado(
                                        row.get("COMENTARIO", ""),
                                        float(row.get("ABONOS (CLP)", 0) or 0),
                                        st.session_state.config_clasificadores
                                    ),
                                    axis=1
                                )
                                # Mantener el flag para el siguiente rerun:
                                # cuando el dataset viene desde BD, se recarga con CLASIFICACION antigua
                                # y necesita forzar reclasificación una vez más en el siguiente ciclo.
                                st.session_state.config_clasificadores_editado = True

                                # Persistencia mínima en BD (opción A): guardar reglas aprendidas como clasificadores
                                # para que estén disponibles al reingresar.
                                persistidas_bd = 0
                                if usuario_actual and reglas_aprendidas:
                                    try:
                                        from database.crud import crear_clasificador, obtener_clasificadores
                                        existentes_bd = obtener_clasificadores(usuario_actual.id)
                                        firmas_bd = set()
                                        for clf in existentes_bd:
                                            try:
                                                tipo_txt = "abonos" if str(getattr(clf, "tipo", "")).lower().endswith("abono") else "cargos"
                                                nombre_txt = str(getattr(clf, "nombre", "")).strip()
                                                palabras_txt = json.loads(getattr(clf, "palabras_clave", "[]") or "[]")
                                                for p in palabras_txt:
                                                    firmas_bd.add((tipo_txt, nombre_txt, normalizar(p)))
                                            except Exception:
                                                continue

                                        for lista_obj, nombre_cat, kw in reglas_aprendidas:
                                            firma = (lista_obj, nombre_cat, kw)
                                            if firma in firmas_bd:
                                                continue
                                            crear_clasificador(
                                                usuario_id=usuario_actual.id,
                                                nombre=nombre_cat,
                                                tipo="abono" if lista_obj == "abonos" else "cargo",
                                                palabras_clave=[kw],
                                                tipo_coincidencia="contiene_cualquiera",
                                                excluir=None,
                                                orden=9999
                                            )
                                            firmas_bd.add(firma)
                                            persistidas_bd += 1
                                    except Exception:
                                        pass

                                restantes = len(df[df["CLASIFICACION"].isin([None, "NO CLASIFICADO", ""])])
                                if errores > 0:
                                    mensaje = f"Se aplicaron cambios con observaciones. Restantes sin clasificar: {restantes}."
                                    st.session_state.mensaje_reclasificacion = ("warning", mensaje)
                                else:
                                    mensaje = f"✅ Cambios aplicados correctamente. Restantes sin clasificar: {restantes}."
                                    st.session_state.mensaje_reclasificacion = ("success", mensaje)
                                st.rerun()

                        # Descarga siempre disponible (aun si aún no aplicaste cambios)
                        json_actualizado = json.dumps(st.session_state.config_clasificadores, ensure_ascii=False, indent=2)
                        st.download_button(
                            "⬇️ Descargar clasificador actualizado (JSON)",
                            data=json_actualizado,
                            file_name="clasificadores_actualizado.json",
                            mime="application/json",
                            use_container_width=True
                        )
                else:
                    st.success("✅ Todas las transacciones están clasificadas")
                    if st.session_state.get("config_clasificadores") is not None:
                        json_actualizado = json.dumps(
                            st.session_state.config_clasificadores,
                            ensure_ascii=False,
                            indent=2
                        )
                        st.download_button(
                            "⬇️ Descargar clasificador actualizado (JSON)",
                            data=json_actualizado,
                            file_name="clasificadores_actualizado.json",
                            mime="application/json",
                            use_container_width=True
                        )

            # ---------- BARRA LATERAL DE FILTROS ----------
            st.sidebar.markdown("---")
            st.sidebar.markdown("### 🔍 Filtros")
            
            # Verificar que la columna FECHA existe y tiene datos válidos
            if "FECHA" not in df.columns:
                st.error("❌ Error: No se encontró la columna FECHA en los datos")
                st.stop()
            
            # Asegurar que las fechas estén en formato datetime
            if df["FECHA"].dtype != 'datetime64[ns]':
                try:
                    df["FECHA"] = pd.to_datetime(df["FECHA"], errors='coerce')
                except Exception as e:
                    st.error(f"❌ Error al convertir fechas: {e}")
                    st.stop()
            
            # Verificar que hay fechas válidas
            fechas_validas = df["FECHA"].notna()
            if fechas_validas.sum() == 0:
                st.error("❌ Error: No hay fechas válidas en los datos")
                st.stop()
            
            # Filtrar solo filas con fechas válidas
            df = df[fechas_validas].copy()
            
            try:
                fecha_min = df["FECHA"].min()
                fecha_max = df["FECHA"].max()
                
                # Convertir a date para el date_input
                if pd.isna(fecha_min) or pd.isna(fecha_max):
                    st.error("❌ Error: No se pudieron obtener las fechas mínima y máxima")
                    st.stop()
                
                fecha_min_date = fecha_min.date() if hasattr(fecha_min, 'date') else fecha_min
                fecha_max_date = fecha_max.date() if hasattr(fecha_max, 'date') else fecha_max
                
                rango = st.sidebar.date_input("🗓️ Rango de fechas", [fecha_min_date, fecha_max_date])
            except Exception as e:
                st.error(f"❌ Error al procesar fechas: {e}")
                import traceback
                st.error(f"Traceback: {traceback.format_exc()}")
                st.stop()

            if len(rango) == 2:
                df = df[(df["FECHA"] >= pd.to_datetime(rango[0])) & (df["FECHA"] <= pd.to_datetime(rango[1]))]
                st.caption(f"📃 Mostrando movimientos desde {rango[0].strftime('%d-%m-%Y')} hasta {rango[1].strftime('%d-%m-%Y')}")

            clasificaciones = sorted(df["CLASIFICACION"].unique())
            seleccion = st.sidebar.multiselect("🏷️ Clasificaciones", clasificaciones, default=clasificaciones)

            df_filtrado = df[df["CLASIFICACION"].isin(seleccion)]

            # ---------- METRICAS PRINCIPALES ----------
            total_abonos = df_filtrado['ABONOS (CLP)'].sum()
            total_cargos = df_filtrado['CARGOS (CLP)'].sum() if 'CARGOS (CLP)' in df_filtrado.columns else 0
            flujo_neto = total_abonos - total_cargos

            # Métricas con diseño mejorado
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.markdown(
                    f"""
                    <div style="background: linear-gradient(135deg, #28a745 0%, #20c997 100%); 
                                color: white; 
                                padding: 1.5rem; 
                                border-radius: 10px; 
                                text-align: center;
                                box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
                        <h3 style="color: white; margin: 0 0 0.5rem 0; font-size: 0.9rem; opacity: 0.9;">💸 Total Abonos</h3>
                        <h2 style="color: white; margin: 0; font-size: 2rem; font-weight: bold;">${total_abonos:,.0f}</h2>
                    </div>
                    """,
                    unsafe_allow_html=True
                )
            
            with col2:
                st.markdown(
                    f"""
                    <div style="background: linear-gradient(135deg, #dc3545 0%, #fd7e14 100%); 
                                color: white; 
                                padding: 1.5rem; 
                                border-radius: 10px; 
                                text-align: center;
                                box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
                        <h3 style="color: white; margin: 0 0 0.5rem 0; font-size: 0.9rem; opacity: 0.9;">💰 Total Cargos</h3>
                        <h2 style="color: white; margin: 0; font-size: 2rem; font-weight: bold;">${total_cargos:,.0f}</h2>
                    </div>
                    """,
                    unsafe_allow_html=True
                )
            
            with col3:
                color_neto = "#28a745" if flujo_neto >= 0 else "#dc3545"
                st.markdown(
                    f"""
                    <div style="background: linear-gradient(135deg, {color_neto} 0%, #6c757d 100%); 
                                color: white; 
                                padding: 1.5rem; 
                                border-radius: 10px; 
                                text-align: center;
                                box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
                        <h3 style="color: white; margin: 0 0 0.5rem 0; font-size: 0.9rem; opacity: 0.9;">📈 Flujo Neto</h3>
                        <h2 style="color: white; margin: 0; font-size: 2rem; font-weight: bold;">${flujo_neto:,.0f}</h2>
                    </div>
                    """,
                    unsafe_allow_html=True
                )
            
            st.markdown("<br>", unsafe_allow_html=True)

            # ---------- CÁLCULO DE SALDO FINAL ----------
            st.sidebar.markdown("---")
            st.sidebar.markdown("### 💼 Ajustes de caja")
            saldo_inicial = st.sidebar.number_input("Saldo inicial del periodo", value=0, key="saldo_inicial_input")
            saldo_calculado = saldo_inicial + total_abonos - total_cargos

            # Tomar el saldo de la cartola
            # IMPORTANTE: El saldo final es el ÚLTIMO saldo en el DataFrame (final del día)
            # Esto funciona tanto si hay una sola fecha como múltiples fechas
            saldo_cartola = None
            diferencia = None
            fecha_saldo_cartola = None
            
            if "SALDO (CLP)" in df.columns and "FECHA" in df.columns:
                # Filtrar solo filas con saldo no nulo
                filas_con_saldo = df[df["SALDO (CLP)"].notna()].copy()
                if not filas_con_saldo.empty:
                    # Asegurar que FECHA esté en formato datetime
                    if not pd.api.types.is_datetime64_any_dtype(filas_con_saldo["FECHA"]):
                        filas_con_saldo["FECHA"] = pd.to_datetime(filas_con_saldo["FECHA"], errors='coerce')

                    # Candidato 1: último saldo por orden original en el DataFrame
                    fila_saldo_index = filas_con_saldo.iloc[-1:]
                    saldo_index = float(fila_saldo_index["SALDO (CLP)"].values[0])
                    fecha_index = fila_saldo_index["FECHA"].values[0]
                    
                    # Verificar si todas las fechas son iguales
                    fechas_unicas = filas_con_saldo["FECHA"].nunique()
                    
                    if fechas_unicas == 1:
                        # Si todas las fechas son iguales, tomar el ÚLTIMO saldo no nulo del DataFrame
                        # (corresponde al final del día, última transacción)
                        # Usar el índice original para mantener el orden de la cartola
                        fila_saldo = filas_con_saldo.iloc[-1:]
                    else:
                        # Si hay múltiples fechas, ordenar por fecha ascendente y tomar la última (más reciente)
                        filas_con_saldo = filas_con_saldo.sort_values(by="FECHA", ascending=True, na_position='last')
                        fila_saldo = filas_con_saldo.iloc[-1:]
                    
                    saldo_fecha = float(fila_saldo["SALDO (CLP)"].values[0])
                    fecha_saldo_fecha = fila_saldo["FECHA"].values[0]
                    diferencia_fecha = saldo_calculado - saldo_fecha
                    diferencia_index = saldo_calculado - saldo_index

                    # Elegir el candidato cuyo saldo quede más cerca del saldo calculado
                    if abs(diferencia_fecha) <= abs(diferencia_index):
                        saldo_cartola = saldo_fecha
                        fecha_saldo_cartola = fecha_saldo_fecha
                        diferencia = diferencia_fecha
                    else:
                        saldo_cartola = saldo_index
                        fecha_saldo_cartola = fecha_index
                        diferencia = diferencia_index

            col4, col5 = st.columns(2)
            col4.metric("📌 Saldo Final Calculado", f"${saldo_calculado:,.0f}")
            if saldo_cartola is not None:
                col5.metric("🏦 Saldo según cartola", f"${saldo_cartola:,.0f}", delta=f"${diferencia:,.0f}")
                st.caption(f"💡 Saldo cartola al {pd.to_datetime(fecha_saldo_cartola).strftime('%d-%m-%Y')}")
            else:
                # Fallback: si el Excel/BD no trae SALDO (CLP), mostramos el saldo calculado para no dejar vacío.
                # Indica que no se pudo leer el saldo directamente desde la cartola.
                saldo_cartola = saldo_calculado
                diferencia = 0
                if "FECHA" in df.columns and not df["FECHA"].empty:
                    try:
                        fecha_saldo_cartola = df["FECHA"].max()
                    except:
                        fecha_saldo_cartola = None
                col5.metric("🏦 Saldo según cartola", f"${saldo_cartola:,.0f}", delta=f"${diferencia:,.0f}")
                st.caption("💡 No se pudo leer el saldo final directamente desde la cartola; se mostró el saldo calculado.")

            # ---------- TABLA DETALLE ----------
            st.subheader("🔍 Detalle de transacciones clasificadas")
            st.dataframe(df_filtrado, use_container_width=True)

            # ---------- GRÁFICOS ----------
            resumen_torta = df_filtrado.groupby("CLASIFICACION")[["ABONOS (CLP)", "CARGOS (CLP)"]].sum().reset_index()
            if not resumen_torta.empty:
                st.subheader("📊 Distribución de abonos por clasificación")
                fig_torta = px.pie(resumen_torta, names="CLASIFICACION", values="ABONOS (CLP)", title="Abonos por categoría")
                st.plotly_chart(fig_torta, use_container_width=True)

                resumen_cargos = resumen_torta[resumen_torta["CARGOS (CLP)"] > 0] if 'CARGOS (CLP)' in resumen_torta.columns else pd.DataFrame()
                if not resumen_cargos.empty:
                    st.subheader("📊 Distribución de cargos por clasificación")
                    fig_cargos = px.pie(resumen_cargos, names="CLASIFICACION", values="CARGOS (CLP)", title="Cargos por categoría")
                    st.plotly_chart(fig_cargos, use_container_width=True)
                else:
                    st.info("No hay cargos para graficar en el rango y clasificaciones seleccionadas.")

                st.subheader("📊 Comparativa de abonos y cargos por clasificación")
                fig_barra = px.bar(resumen_torta, x="CLASIFICACION", y=["ABONOS (CLP)", "CARGOS (CLP)"], barmode="group", title="Ingresos vs Egresos por categoría")
                st.plotly_chart(fig_barra, use_container_width=True)

            # ---------- DESCARGA ----------
            st.subheader("⬇️ Descargar Excel clasificado")
            output = io.BytesIO()
            df_filtrado.to_excel(output, index=False, engine='openpyxl')
            st.download_button("Descargar archivo clasificado", output.getvalue(), file_name="cartola_clasificada.xlsx")
        except Exception as e:
            # Capturar cualquier error en el procesamiento y mostrarlo
            st.error(f"❌ Error durante el procesamiento de datos: {e}")
            import traceback
            with st.expander("🔍 Ver detalles del error"):
                st.code(traceback.format_exc())
            st.warning("⚠️ No se pudieron mostrar los datos debido a un error en el procesamiento.")
    else:
            # Si llegamos aquí, significa que df está vacío o None
            st.warning("⚠️ No se pudieron cargar los datos o el archivo está vacío.")
else:
    st.error("❌ No se puede continuar sin la configuración de clasificadores.")