import streamlit as st
import pandas as pd
import plotly.express as px
import unicodedata
import io
import traceback
import tempfile
from calendar import monthrange
from pathlib import Path
from datetime import datetime

# Importar sistema de autenticación y base de datos
from auth.login import require_login, get_current_user, show_user_info
from database.crud import (
    obtener_clasificadores, obtener_transacciones, obtener_archivos,
    guardar_archivo_proyeccion, obtener_archivos_proyeccion, obtener_archivo_proyeccion,
    registrar_archivo, guardar_transacciones
)
from database.models import TipoTransaccion

# Importar funciones necesarias SIN ejecutar código de Streamlit del otro archivo
# Copiamos las funciones directamente aquí para evitar conflictos
import json

def normalizar(texto):
    """Normaliza el texto eliminando acentos, convirtiendo a mayúsculas y normalizando espacios."""
    if pd.isnull(texto):
        return ""
    texto = str(texto).upper().strip()
    # Quitar acentos
    texto = unicodedata.normalize("NFD", texto).encode("ascii", "ignore").decode("utf-8")
    # Normalizar espacios: quitar espacios múltiples, espacios alrededor de guiones
    import re
    texto = re.sub(r'\s+', ' ', texto)  # Reemplazar múltiples espacios con uno solo
    texto = re.sub(r'\s*-\s*', '-', texto)  # Quitar espacios alrededor de guiones
    texto = re.sub(r'\s*:\s*', ':', texto)  # Quitar espacios alrededor de dos puntos
    texto = texto.strip()  # Quitar espacios al inicio y final
    return texto

def convertir_clasificadores_bd_a_dict(clasificadores_bd):
    """Convierte clasificadores de la BD al formato que espera clasificar_mejorado."""
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
        
        if clf.tipo == TipoTransaccion.ABONO:
            config["clasificadores"]["abonos"].append(clasificador_dict)
        else:
            config["clasificadores"]["cargos"].append(clasificador_dict)
    
    return config

def evaluar_clasificador(texto, clasificador, debug=False):
    """Evalúa si un texto coincide con un clasificador según su tipo."""
    tipo = clasificador.get("tipo", "contiene_cualquiera")
    palabras_clave = clasificador.get("palabras_clave", [])
    excluir = clasificador.get("excluir", [])
    
    # Si no hay palabras clave, no puede coincidir
    if not palabras_clave or len(palabras_clave) == 0:
        if debug:
            print(f"  [DEBUG] No hay palabras clave en clasificador")
        return False
    
    # Normalizar palabras clave y exclusiones para comparación
    palabras_clave_norm = [normalizar(str(palabra)) for palabra in palabras_clave if palabra and str(palabra).strip()]
    excluir_norm = [normalizar(str(exclusion)) for exclusion in excluir] if excluir else []
    
    # Si después de normalizar no quedan palabras clave, no puede coincidir
    if not palabras_clave_norm or len(palabras_clave_norm) == 0:
        if debug:
            print(f"  [DEBUG] No quedaron palabras clave después de normalizar")
        return False
    
    # Verificar exclusiones primero (después de normalizar)
    if excluir_norm:
        for exclusion in excluir_norm:
            if exclusion in texto:
                if debug:
                    print(f"  [DEBUG] Excluido por: '{exclusion}'")
                return False
    
    # Comparar texto normalizado con palabras clave normalizadas
    if tipo == "contiene_exacto":
        # Para contiene_exacto, TODAS las palabras deben estar presentes
        todas_presentes = all(palabra in texto for palabra in palabras_clave_norm)
        if debug:
            print(f"  [DEBUG] Tipo: contiene_exacto")
            print(f"  [DEBUG] Texto: '{texto[:100]}...'")
            print(f"  [DEBUG] Palabras clave normalizadas: {palabras_clave_norm}")
            for palabra in palabras_clave_norm:
                presente = palabra in texto
                print(f"  [DEBUG]   '{palabra}' {'✓' if presente else '✗'} en texto")
            print(f"  [DEBUG] Resultado: {todas_presentes}")
        return todas_presentes
    elif tipo == "contiene_cualquiera":
        # Para contiene_cualquiera, al menos UNA palabra debe estar presente
        alguna_presente = any(palabra in texto for palabra in palabras_clave_norm)
        if debug:
            print(f"  [DEBUG] Tipo: contiene_cualquiera")
            print(f"  [DEBUG] Texto: '{texto[:100]}...'")
            print(f"  [DEBUG] Palabras clave normalizadas: {palabras_clave_norm}")
            for palabra in palabras_clave_norm:
                presente = palabra in texto
                print(f"  [DEBUG]   '{palabra}' {'✓' if presente else '✗'} en texto")
            print(f"  [DEBUG] Resultado: {alguna_presente}")
        return alguna_presente
    else:
        if debug:
            print(f"  [DEBUG] Tipo desconocido: {tipo}")
        return False

def clasificar_mejorado(texto, abono, config_clasificadores, cargo=0):
    """Clasifica una transacción según el texto y los montos de abono y cargo."""
    if config_clasificadores is None:
            return "NO CLASIFICADO"

    texto = normalizar(texto)
    clasificadores = config_clasificadores.get("clasificadores", {})
    clasificacion_default = config_clasificadores.get("clasificacion_default", "NO CLASIFICADO")
    
    # Determinar si es un abono o un cargo basándose en ambos valores
    # Si hay abono > 0, es un abono (ingreso)
    # Si hay cargo > 0 y abono = 0, es un cargo (egreso)
    # Si ambos son 0 o ambos > 0, usar abono como criterio principal
    es_abono = abono > 0 and cargo == 0
    es_cargo = cargo > 0 and abono == 0
    
    # Si es claramente un cargo, buscar en clasificadores de cargos
    if es_cargo:
        lista_clasificadores = clasificadores.get("cargos", [])
    # Si es claramente un abono, buscar en clasificadores de abonos
    elif es_abono:
        lista_clasificadores = clasificadores.get("abonos", [])
    # Si ambos están presentes o ambos son 0, usar abono como criterio (comportamiento anterior)
    else:
        lista_clasificadores = clasificadores.get("abonos", []) if abono > 0 else clasificadores.get("cargos", [])
    
    for clasificador in lista_clasificadores:
        if evaluar_clasificador(texto, clasificador, debug=False):
            return clasificador.get("nombre", clasificacion_default)
    
    return clasificacion_default

def cargar_datos_desde_bd(archivo_id, usuario_id):
    """Carga datos desde la base de datos usando el archivo_id."""
    try:
        transacciones_bd = obtener_transacciones(
            usuario_id=usuario_id,
            fecha_desde=None,
            fecha_hasta=None,
            archivo_id=archivo_id
        )
        
        if transacciones_bd is None or len(transacciones_bd) == 0:
            return None
        
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
        
        if "FECHA" in df.columns:
            df["FECHA"] = pd.to_datetime(df["FECHA"], errors='coerce')
        
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
        
        # Validación crítica: Verificar que ABONOS y CARGOS no sean iguales
        if "ABONOS (CLP)" in df.columns and "CARGOS (CLP)" in df.columns:
            total_abonos = df["ABONOS (CLP)"].sum()
            total_cargos = df["CARGOS (CLP)"].sum()
            filas_abonos = len(df[df["ABONOS (CLP)"] > 0])
            filas_cargos = len(df[df["CARGOS (CLP)"] > 0])
            
            # Mostrar diagnóstico en sidebar solo en modo debug
            if MODO_DEBUG:
                st.sidebar.markdown("---")
                st.sidebar.markdown("### 🔍 Datos desde BD")
                debug_info(f"💰 Total ABONOS: ${total_abonos:,.0f}")
                debug_info(f"💸 Total CARGOS: ${total_cargos:,.0f}")
                debug_info(f"📊 Filas con ABONOS > 0: {filas_abonos}")
                debug_info(f"📊 Filas con CARGOS > 0: {filas_cargos}")
            
            # Verificar si ambas columnas tienen exactamente los mismos valores
            if df["ABONOS (CLP)"].equals(df["CARGOS (CLP)"]):
                st.error("❌ ERROR CRÍTICO: Los datos cargados desde la BD tienen ABONOS y CARGOS con los mismos valores.")
                st.warning("⚠️ **PROBLEMA:** La cartola se guardó incorrectamente en la base de datos.")
                st.info("💡 **CAUSA:** Cuando se guardó la cartola, se usó la misma columna para ABONOS y CARGOS.")
                st.info("📋 **SOLUCIÓN:**")
                st.info("   1. Elimina esta cartola de la base de datos")
                st.info("   2. Verifica que tu archivo Excel tenga columnas SEPARADAS:")
                st.info("      - Columna 'Abonos (CLP)' o 'ABONOS' para ingresos")
                st.info("      - Columna 'Cargos (CLP)' o 'CARGOS' para egresos")
                st.info("   3. Vuelve a cargar la cartola desde el archivo Excel corregido")
                st.info("   4. Guarda la cartola nuevamente")
                with st.expander("🔍 Ver datos cargados desde BD"):
                    st.write("Primeras 10 filas:")
                    st.dataframe(df[["FECHA", "DESCRIPCION", "ABONOS (CLP)", "CARGOS (CLP)", "CLASIFICACION"]].head(10))
                    st.write(f"Total ABONOS: ${total_abonos:,.0f}")
                    st.write(f"Total CARGOS: ${total_cargos:,.0f}")
                    st.write(f"Filas con ABONOS > 0: {filas_abonos}")
                    st.write(f"Filas con CARGOS > 0: {filas_cargos}")
                st.stop()
            
            # Advertencia si los totales son iguales (muy sospechoso)
            if abs(total_abonos - total_cargos) < 1 and total_abonos > 0:
                st.error("❌ ERROR: Los totales de ABONOS y CARGOS son iguales. Esto NO es posible.")
                st.warning("⚠️ **PROBLEMA:** Los datos en la base de datos están incorrectos.")
                st.info("💡 **CAUSA:** La cartola se guardó incorrectamente. Se usó la misma columna para ambos.")
                st.info("📋 **SOLUCIÓN:**")
                st.info("   1. Elimina esta cartola de la base de datos")
                st.info("   2. Verifica que tu archivo Excel tenga columnas SEPARADAS")
                st.info("   3. Vuelve a cargar y guardar la cartola desde el archivo corregido")
                with st.expander("🔍 Ver detalles del problema"):
                    st.write(f"Total ABONOS: ${total_abonos:,.0f}")
                    st.write(f"Total CARGOS: ${total_cargos:,.0f}")
                    st.write(f"Filas con ABONOS > 0: {filas_abonos}")
                    st.write(f"Filas con CARGOS > 0: {filas_cargos}")
                    st.write("Muestra de datos (primeras 10 filas):")
                    st.dataframe(df[["FECHA", "DESCRIPCION", "ABONOS (CLP)", "CARGOS (CLP)", "CLASIFICACION"]].head(10))
                st.stop()
        
        if df.empty or len(df) == 0:
            return None
        
        return df
    except Exception as e:
        st.error(f"❌ Error al cargar datos desde BD: {e}")
        return None

# ---------- CONFIGURACIÓN DE PÁGINA ----------
st.set_page_config(
    page_title="Flujo de Caja Comparativo",
    page_icon="📊",
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
    
    /* Tablas mejoradas */
    .dataframe {
        border-radius: 8px;
        overflow: hidden;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    
    /* Alertas mejoradas */
    .stAlert {
        border-radius: 8px;
        border-left: 4px solid;
    }
</style>
""", unsafe_allow_html=True)

# ---------- VERIFICAR LOGIN ----------
if not require_login():
    st.stop()  # Si no está logueado, mostrar login y detener

# Obtener usuario actual
usuario_actual = get_current_user()
if not usuario_actual:
    st.error("❌ Error: No se pudo obtener información del usuario.")
    st.stop()

# Mostrar información del usuario en sidebar
show_user_info()

# ==================== TÍTULO PRINCIPAL - COMPARATIVO ====================
st.markdown("# 📊 DASHBOARD COMPARATIVO")
st.markdown("## Flujo Real vs Proyectado")
st.markdown("---")

# Mensaje informativo destacado y visible
st.success("✅ **APLICACIÓN COMPARATIVA ACTIVA** - Esta app compara datos REALES vs PROYECTADOS")
st.warning("⚠️ **IMPORTANTE**: Si no ves comparaciones, verifica que hayas cargado un archivo de proyección en el sidebar")

# Verificar que estamos en el archivo correcto
st.sidebar.markdown("---")
st.sidebar.markdown("### ℹ️ Información")
st.sidebar.info("📊 **Aplicación Comparativa**\n\nEsta app compara datos reales con proyecciones.")

# Modo debug (oculto por defecto, solo para desarrolladores)
MODO_DEBUG = st.sidebar.checkbox("🔧 Modo Debug (solo desarrolladores)", value=False, key="modo_debug_comparativo")

# ----------------- FUNCIONES -----------------
def debug_info(message, *args, **kwargs):
    """Muestra información de debug solo si el modo debug está activado"""
    if MODO_DEBUG:
        st.sidebar.info(message, *args, **kwargs)

def debug_warning(message, *args, **kwargs):
    """Muestra advertencia de debug solo si el modo debug está activado"""
    if MODO_DEBUG:
        st.sidebar.warning(message, *args, **kwargs)

def debug_expander(label, *args, **kwargs):
    """Crea un expander de debug solo si el modo debug está activado"""
    if MODO_DEBUG:
        return st.sidebar.expander(label, *args, **kwargs)
    else:
        # Retornar un objeto dummy que no hace nada
        class DummyExpander:
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass
            def __call__(self, *args, **kwargs):
                pass
        return DummyExpander()
@st.cache_data
def analizar_estructura_excel(archivo):
    """
    Analiza la estructura del archivo Excel y muestra información detallada.
    Útil para debug y para adaptar el código a diferentes formatos.
    """
    try:
        # Guardar archivo temporalmente
        with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as tmp_file:
            tmp_path = tmp_file.name
            tmp_file.write(archivo.read())
            archivo.seek(0)  # Resetear el archivo para que pueda leerse de nuevo
        
        # Leer el archivo
        df = pd.read_excel(tmp_path, header=0)
        
        # Información de estructura
        info = {
            "num_filas": len(df),
            "num_columnas": len(df.columns),
            "nombres_columnas": [str(col) for col in df.columns.tolist()],
            "primeras_filas": df.head(10).to_dict('records'),
            "tipos_datos": df.dtypes.to_dict()
        }
        
        # Limpiar archivo temporal
        Path(tmp_path).unlink(missing_ok=True)
        
        return info
    except Exception as e:
        return {"error": str(e)}

def cargar_proyeccion_desde_archivo(archivo):
    """
    Carga archivo de proyección desde un archivo subido.
    
    Args:
        archivo: Archivo subido (BytesIO o similar)
    
    Returns:
        pd.DataFrame: DataFrame con los datos de proyección
    """
    try:
        # Determinar extensión del archivo
        nombre_archivo = archivo.name if hasattr(archivo, 'name') else 'archivo.xlsx'
        extension = Path(nombre_archivo).suffix.lower()
        
        # Guardar archivo temporalmente con la extensión correcta
        with tempfile.NamedTemporaryFile(delete=False, suffix=extension) as tmp_file:
            # Asegurarse de que el archivo esté al inicio
            if hasattr(archivo, 'seek'):
                archivo.seek(0)
            tmp_file.write(archivo.read())
            tmp_path = tmp_file.name
        
        # Leer Excel (pandas maneja .xls y .xlsx automáticamente)
        # IMPORTANTE: Si las columnas son fechas, pandas puede leerlas como datetime
        # Por eso NO usamos parse_dates aquí, sino que las manejamos después
        df = pd.read_excel(tmp_path, engine=None)  # engine=None permite que pandas elija automáticamente
        
        # Verificar que el archivo tenga datos
        if df.empty:
            st.warning("⚠️ El archivo Excel está vacío.")
            Path(tmp_path).unlink(missing_ok=True)
            return None
        
        # Normalizar nombres de columnas (convertir a string primero si hay números)
        # IMPORTANTE: Si pandas leyó columnas como datetime, convertirlas a string con formato estándar
        nuevas_columnas = []
        for col in df.columns:
            # Si la columna es datetime (pandas puede leer fechas como datetime en los headers)
            if isinstance(col, (pd.Timestamp, datetime)):
                # Convertir a string con formato YYYY-MM-DD HH:MM:SS
                nueva_col = col.strftime('%Y-%m-%d %H:%M:%S')
            else:
                # Convertir a string y limpiar
                nueva_col = str(col).strip()
            nuevas_columnas.append(nueva_col)
        
        df.columns = nuevas_columnas
        
        # Debug: mostrar TODAS las columnas encontradas
        if MODO_DEBUG:
            columnas_str = [str(col) for col in df.columns.tolist()]
            debug_info(f"📋 TODAS las columnas en archivo ({len(columnas_str)}):")
            with debug_expander("🔍 Ver todas las columnas"):
                for i, col in enumerate(columnas_str):
                    st.text(f"  {i+1}. '{col}' (longitud: {len(col)})")
        
        # Buscar columna CLASIFICACION (primera columna o la que contenga "CLASIFICACION")
        col_clasificacion = None
        for col in df.columns:
            if "CLASIFICACION" in str(col).upper():
                col_clasificacion = col
                break
        
        if col_clasificacion is None:
            # Si no se encuentra, usar la primera columna
            col_clasificacion = df.columns[0]
        
        debug_info(f"📌 Columna de clasificación detectada: '{col_clasificacion}'")
        
        # Renombrar a CLASIFICACION
        if col_clasificacion != "CLASIFICACION":
            df.rename(columns={col_clasificacion: "CLASIFICACION"}, inplace=True)
        
        # Buscar columna TIPO DE MOVIMIENTO
        col_tipo = None
        for col in df.columns:
            col_upper = str(col).upper().strip()
            if "TIPO" in col_upper and "MOVIMIENTO" in col_upper:
                col_tipo = col
                break
        
        if col_tipo is None:
            st.error("❌ No se encontró la columna 'TIPO DE MOVIMIENTO' en el archivo.")
            st.info("💡 El archivo debe tener una columna 'TIPO DE MOVIMIENTO' con valores 'INGRESO' o 'EGRESO'.")
            Path(tmp_path).unlink(missing_ok=True)
            return None
        
        debug_info(f"📌 Columna TIPO DE MOVIMIENTO detectada: '{col_tipo}'")
        
        # Renombrar a TIPO
        df.rename(columns={col_tipo: "TIPO"}, inplace=True)
        
        # Eliminar filas sin clasificación o sin tipo
        df.dropna(subset=["CLASIFICACION", "TIPO"], inplace=True)
        
        if df.empty:
            st.warning("⚠️ No se encontraron filas con clasificación y tipo válidos.")
            Path(tmp_path).unlink(missing_ok=True)
            return None
        
        # Normalizar valores de TIPO (mayúsculas, sin espacios)
        df["TIPO"] = df["TIPO"].astype(str).str.strip().str.upper()
        
        # Validar que los valores de TIPO sean INGRESO o EGRESO
        valores_tipo_validos = df["TIPO"].isin(["INGRESO", "EGRESO"])
        if not valores_tipo_validos.all():
            valores_invalidos = df[~valores_tipo_validos]["TIPO"].unique()
            st.warning(f"⚠️ Se encontraron valores inválidos en TIPO DE MOVIMIENTO: {valores_invalidos}")
            st.info("💡 Los valores deben ser exactamente 'INGRESO' o 'EGRESO'.")
            # Filtrar solo los válidos
            df = df[valores_tipo_validos].copy()
        
        if df.empty:
            st.warning("⚠️ No quedaron filas con tipos válidos (INGRESO/EGRESO).")
            Path(tmp_path).unlink(missing_ok=True)
            return None
        
        # Normalizar clasificaciones
        df["CLASIFICACION_ORIGINAL"] = df["CLASIFICACION"].copy()
        df["CLASIFICACION_NORM"] = df["CLASIFICACION"].astype(str).apply(normalizar)
        df["CLASIFICACION"] = df["CLASIFICACION_NORM"]
        
        # Debug: mostrar resumen
        debug_info(f"📊 Clasificaciones detectadas: {len(df[df['TIPO']=='INGRESO'])} ingresos, {len(df[df['TIPO']=='EGRESO'])} egresos")
        
        # Hacer melt - todas las columnas excepto CLASIFICACION, CLASIFICACION_ORIGINAL, CLASIFICACION_NORM, TIPO son fechas
        columnas_fecha = [col for col in df.columns if col not in ["CLASIFICACION", "CLASIFICACION_ORIGINAL", "CLASIFICACION_NORM", "TIPO"]]
        
        if not columnas_fecha:
            st.warning("⚠️ No se encontraron columnas de fecha en el archivo.")
            Path(tmp_path).unlink(missing_ok=True)
            return None
        
        debug_info(f"📅 Columnas de fecha detectadas: {len(columnas_fecha)}")
        
        # Debug: mostrar las columnas de fecha detectadas
        if MODO_DEBUG:
            with debug_expander("🔍 Ver columnas de fecha detectadas"):
                for i, col in enumerate(columnas_fecha[:20]):  # Mostrar primeras 20
                    st.text(f"  {i+1}. '{col}'")
                if len(columnas_fecha) > 20:
                    st.text(f"  ... y {len(columnas_fecha) - 20} más")
        
        # Hacer melt manteniendo TIPO y CLASIFICACION_ORIGINAL
        id_vars = ["CLASIFICACION", "CLASIFICACION_ORIGINAL", "CLASIFICACION_NORM", "TIPO"]
        df = df.melt(id_vars=id_vars, value_vars=columnas_fecha, var_name="FECHA", value_name="MONTO")
        
        # Debug: mostrar valores únicos de FECHA después del melt (primeros 20)
        if MODO_DEBUG:
            fechas_unicas_melt = df["FECHA"].unique()[:20]
            debug_info(f"🔍 Valores de FECHA después del melt (primeros 20):")
            with debug_expander("🔍 Ver valores de FECHA"):
                for fecha in fechas_unicas_melt:
                    st.text(f"  '{fecha}' (tipo: {type(fecha).__name__})")
        
        debug_info(f"📊 Registros después de melt: {len(df)}")
        
        # Convertir MONTO a numérico
        df["MONTO"] = pd.to_numeric(df["MONTO"], errors='coerce').fillna(0)
        
        # Debug: mostrar información sobre MONTO antes de filtrar
        total_monto_antes = df["MONTO"].sum()
        registros_con_monto = len(df[df["MONTO"] != 0])
        debug_info(f"💰 Total MONTO antes de filtrar: ${total_monto_antes:,.0f} ({registros_con_monto} registros con monto > 0)")
        
        # Convertir fechas - manejar múltiples formatos
        def convertir_fecha_custom(fecha_str):
            """Convierte fechas en múltiples formatos a datetime"""
            if pd.isna(fecha_str):
                return None
            
            # Si ya es un Timestamp o datetime, normalizarlo al primer día del mes
            if isinstance(fecha_str, (pd.Timestamp, datetime)):
                return pd.Timestamp(year=fecha_str.year, month=fecha_str.month, day=1)
            
            # Convertir a string y limpiar
            fecha_original = str(fecha_str).strip()
            fecha_str_lower = fecha_original.lower()
            
            # PRIMERO: Intentar parsear formato datetime completo '2025-07-01 00:00:00' o '2025-07-01'
            # Este es el formato que está usando el archivo del usuario
            try:
                # Intentar parsear como datetime ISO (YYYY-MM-DD HH:MM:SS o YYYY-MM-DD)
                resultado = pd.to_datetime(fecha_original, errors='coerce', format='%Y-%m-%d %H:%M:%S')
                if pd.isna(resultado):
                    resultado = pd.to_datetime(fecha_original, errors='coerce', format='%Y-%m-%d')
                if pd.notna(resultado):
                    # Normalizar al primer día del mes
                    return pd.Timestamp(year=resultado.year, month=resultado.month, day=1)
            except:
                pass
            
            # SEGUNDO: Intentar con pd.to_datetime genérico (maneja muchos formatos)
            try:
                resultado = pd.to_datetime(fecha_original, errors='coerce', dayfirst=False)
                if pd.notna(resultado):
                    return pd.Timestamp(year=resultado.year, month=resultado.month, day=1)
            except:
                pass
            
            # TERCERO: Mapeo de meses en español (para formatos como 'jul-25')
            meses_es = {
                'ene': 1, 'jan': 1, 'enero': 1, 'january': 1, '01': 1, '1': 1,
                'feb': 2, 'febrero': 2, 'february': 2, '02': 2, '2': 2,
                'mar': 3, 'marzo': 3, 'march': 3, '03': 3, '3': 3,
                'abr': 4, 'apr': 4, 'abril': 4, 'april': 4, '04': 4, '4': 4,
                'may': 5, 'mayo': 5, '05': 5, '5': 5,
                'jun': 6, 'june': 6, 'junio': 6, '06': 6, '6': 6,
                'jul': 7, 'july': 7, 'julio': 7, '07': 7, '7': 7,
                'ago': 8, 'aug': 8, 'agosto': 8, 'august': 8, '08': 8, '8': 8,
                'sep': 9, 'sept': 9, 'septiembre': 9, 'september': 9, '09': 9, '9': 9,
                'oct': 10, 'octubre': 10, 'october': 10, '10': 10,
                'nov': 11, 'noviembre': 11, 'november': 11, '11': 11,
                'dic': 12, 'dec': 12, 'diciembre': 12, 'december': 12, '12': 12
            }
            
            # Intentar formato "jul-25", "jul-2025", "jul/25", "jul 25"
            separadores = ['-', '/', ' ', '_', '.']
            for sep in separadores:
                if sep in fecha_str_lower:
                    partes = fecha_str_lower.split(sep)
                    if len(partes) >= 2:
                        mes_str = partes[0].strip()
                        año_str = partes[1].strip()
                        
                        # Intentar con el mapeo de meses
                        if mes_str in meses_es:
                            mes = meses_es[mes_str]
                            try:
                                # Si el año tiene 2 dígitos, asumir 20XX
                                if len(año_str) == 2:
                                    año = 2000 + int(año_str)
                                else:
                                    año = int(año_str)
                                
                                # Retornar primer día del mes
                                return pd.Timestamp(year=año, month=mes, day=1)
                            except (ValueError, TypeError):
                                continue
            
            # CUARTO: Intentar formato "2025-07", "2025/07", "07/2025", "07-2025"
            for sep in separadores:
                if sep in fecha_str_lower:
                    partes = fecha_str_lower.split(sep)
                    if len(partes) == 2:
                        try:
                            # Intentar año-mes
                            if len(partes[0]) == 4:  # año primero
                                año = int(partes[0])
                                mes = int(partes[1])
                                if 1 <= mes <= 12:
                                    return pd.Timestamp(year=año, month=mes, day=1)
                            # Intentar mes-año
                            elif len(partes[1]) == 4:  # año segundo
                                mes = int(partes[0])
                                año = int(partes[1])
                                if 1 <= mes <= 12:
                                    return pd.Timestamp(year=año, month=mes, day=1)
                        except (ValueError, TypeError):
                            continue
            
            # Si nada funciona, retornar None
            return None
        
        # Guardar valores originales de FECHA antes de convertir
        fechas_originales = df["FECHA"].copy()
        
        # Debug: mostrar algunas fechas originales antes de convertir
        fechas_unicas_originales = fechas_originales.unique()[:10]
        debug_info(f"🔍 Fechas originales (primeras 10): {[str(f) for f in fechas_unicas_originales]}")
        
        # Aplicar conversión de fechas personalizada
        df["FECHA"] = df["FECHA"].apply(convertir_fecha_custom)
        
        # Debug: mostrar algunas fechas después de convertir_fecha_custom
        fechas_despues_custom = df["FECHA"].unique()[:10]
        debug_info(f"🔍 Fechas después convertir_fecha_custom (primeras 10): {[str(f) for f in fechas_despues_custom]}")
        
        # Asegurar que FECHA sea datetime - convertir toda la columna
        df["FECHA"] = pd.to_datetime(df["FECHA"], errors='coerce')
        
        # Si aún hay fechas nulas, intentar conversión estándar con los valores originales
        # IMPORTANTE: El Excel usa formato DD/MM/YYYY, así que usamos dayfirst=True
        if df["FECHA"].isna().any():
            mask_nulas = df["FECHA"].isna()
            # Usar los valores originales (antes de convertir_fecha_custom) para reintentar
            valores_originales_str = fechas_originales.loc[mask_nulas].astype(str)
            # Intentar primero con dayfirst=True (DD/MM/YYYY)
            df.loc[mask_nulas, "FECHA"] = pd.to_datetime(valores_originales_str, errors='coerce', dayfirst=True, format='%d/%m/%Y')
        
        # Si aún hay nulas, intentar sin formato específico pero con dayfirst=True
        if df["FECHA"].isna().any():
            mask_nulas = df["FECHA"].isna()
            valores_originales_str = fechas_originales.loc[mask_nulas].astype(str)
            df.loc[mask_nulas, "FECHA"] = pd.to_datetime(valores_originales_str, errors='coerce', dayfirst=True)
        
        # Verificar que FECHA sea datetime antes de usar .dt
        if not pd.api.types.is_datetime64_any_dtype(df["FECHA"]):
            # Si aún no es datetime, intentar una última conversión forzada
            df["FECHA"] = pd.to_datetime(df["FECHA"], errors='coerce')
        
        # Calcular MES solo si FECHA es datetime
        if pd.api.types.is_datetime64_any_dtype(df["FECHA"]):
            df["MES"] = df["FECHA"].dt.to_period("M").dt.to_timestamp()
            # Debug: mostrar algunas fechas y MES después de calcular
            if MODO_DEBUG and len(df) > 0:
                muestra_fechas_mes = df[["FECHA", "MES"]].head(5)
                debug_info(f"✅ Fechas convertidas correctamente. Muestra:")
                with debug_expander("🔍 Ver muestra FECHA -> MES"):
                    st.dataframe(muestra_fechas_mes)
        else:
            # Si no se pudo convertir, crear MES basado en el string original
            st.warning("⚠️ Algunas fechas no se pudieron convertir a datetime. Intentando extraer mes del formato original...")
            # Debug: mostrar qué fechas no se pudieron convertir
            fechas_nulas = fechas_originales[df["FECHA"].isna()].unique()[:10]
            debug_warning(f"❌ Fechas que no se pudieron convertir: {[str(f) for f in fechas_nulas]}")
            # Intentar extraer mes del formato original como último recurso
            df["MES"] = None
        
        # La clasificación ya está normalizada y asignada a CLASIFICACION arriba
        
        # Debug: información antes de filtrar
        registros_antes_filtro = len(df)
        registros_sin_fecha = len(df[df["FECHA"].isna()])
        registros_con_monto_cero = len(df[df["MONTO"] == 0])
        debug_info(f"📊 Antes de filtrar: {registros_antes_filtro} registros ({registros_sin_fecha} sin fecha, {registros_con_monto_cero} con monto=0)")
        
        # Eliminar filas sin fecha válida o sin monto
        df = df[df["FECHA"].notna()].copy()
        df = df[df["MONTO"] != 0].copy()  # Solo mantener filas con monto diferente de cero
        
        # Debug: información después de filtrar
        registros_despues_filtro = len(df)
        debug_info(f"📊 Después de filtrar: {registros_despues_filtro} registros")
        
        if registros_despues_filtro > 0:
            debug_info(f"💰 Total MONTO después de filtrar: ${df['MONTO'].sum():,.0f}")
            debug_info(f"📅 Rango fechas: {df['FECHA'].min()} a {df['FECHA'].max()}")
            debug_info(f"📊 Tipos: {len(df[df['TIPO']=='INGRESO'])} ingresos, {len(df[df['TIPO']=='EGRESO'])} egresos")
            
            # Debug CRÍTICO: mostrar muestras de fechas y MES
            if "MES" in df.columns:
                meses_unicos = sorted(df["MES"].dt.to_period("M").unique().astype(str).tolist())
                debug_info(f"📅 MES únicos en proyección: {meses_unicos[:20]}")
                
                # Mostrar ejemplos de conversión de fechas
                if MODO_DEBUG:
                    muestra = df[["FECHA", "MES", "MONTO"]].head(10)
                    with debug_expander("🔍 Muestra de fechas convertidas (primeras 10 filas)"):
                        st.dataframe(muestra)
        
        # Verificar que el DataFrame no esté vacío
        if df.empty:
            st.warning("⚠️ El archivo de proyección no contiene datos válidos después del procesamiento.")
            st.info("💡 Verifica que el archivo tenga:")
            st.info("   - Una columna 'CLASIFICACION' o similar")
            st.info("   - Columnas con fechas como encabezados")
            st.info("   - Valores numéricos en las celdas de fechas")
            Path(tmp_path).unlink(missing_ok=True)
            return None
        
        # Limpiar archivo temporal
        Path(tmp_path).unlink(missing_ok=True)
        
        return df
    except Exception as e:
        st.error(f"❌ Error al cargar archivo de proyección: {e}")
        with st.expander("🔍 Ver detalles del error"):
            st.code(traceback.format_exc())
        return None

def preparar_dataframe_real(df):
    """
    Prepara el DataFrame real agregando columnas necesarias.
    
    Args:
        df: DataFrame con datos reales
    
    Returns:
        pd.DataFrame: DataFrame preparado con columna MES
    """
    if df is None or df.empty:
        return None
    
    # Asegurar que existe la columna MES
    if "FECHA" in df.columns:
        df["FECHA"] = pd.to_datetime(df["FECHA"], errors='coerce')
        df["MES"] = df["FECHA"].dt.to_period("M").dt.to_timestamp()
    else:
        st.error("❌ El DataFrame no contiene la columna FECHA")
        return None
    
    return df

def encontrar_fila_encabezados(path):
    """
    Encuentra la fila que contiene los encabezados de las columnas.
    Lee el archivo línea por línea buscando la fila con los encabezados.
    
    Returns:
        int: Número de fila (0-indexed) donde están los encabezados, o 0 si no se encuentra
    """
    palabras_clave = ['FECHA', 'DESCRIPCION', 'ABONOS', 'CARGOS', 'SALDO', 'CANAL', 'SUCURSAL', 'DOCTO', 'DOCUMENTO', 'GLOSA', 'DETALLE', 'FECHA OPERACION']
    
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

def identificar_tipo_clasificacion(clasificacion_norm, config_clasificadores):
    """
    Identifica si una clasificación es INGRESO (ABONO) o EGRESO (CARGO)
    basándose en los clasificadores del usuario.
    
    Args:
        clasificacion_norm: Clasificación normalizada
        config_clasificadores: Configuración de clasificadores
    
    Returns:
        str: "INGRESO" o "EGRESO" o None si no se puede determinar
    """
    if config_clasificadores is None:
        return None
    
    clasificadores = config_clasificadores.get("clasificadores", {})
    
    # Buscar en clasificadores de abonos (ingresos)
    for clf in clasificadores.get("abonos", []):
        nombre_clf = normalizar(clf.get("nombre", ""))
        if nombre_clf == clasificacion_norm:
            return "INGRESO"
    
    # Buscar en clasificadores de cargos (egresos)
    for clf in clasificadores.get("cargos", []):
        nombre_clf = normalizar(clf.get("nombre", ""))
        if nombre_clf == clasificacion_norm:
            return "EGRESO"
    
    return None

# ----------------- CARGA DE DATOS -----------------
st.sidebar.markdown("---")
st.sidebar.markdown("### 📁 Carga de Datos")

# Cargar datos reales - Opción 1: Desde BD o Opción 2: Archivo nuevo
try:
    archivos_disponibles = obtener_archivos(usuario_actual.id)
    
    # Opción para cargar nueva cartola o usar guardada
    if archivos_disponibles:
        opciones_cartolas = {
            f"{archivo.nombre_archivo} - {archivo.fecha_carga.strftime('%Y-%m-%d')}": archivo.id
            for archivo in archivos_disponibles
        }
        opciones_cartolas["➕ Cargar nueva cartola"] = None
        
        cartola_seleccionada_nombre = st.sidebar.selectbox(
            "Seleccionar cartola guardada o cargar nueva",
            options=list(opciones_cartolas.keys()),
            key="cartola_comparativo_seleccionada"
        )
        
        cartola_id_seleccionado = opciones_cartolas[cartola_seleccionada_nombre]
        
        if cartola_id_seleccionado is not None:
            # Cargar desde BD
            archivo_id_seleccionado = cartola_id_seleccionado
            with st.spinner("🔄 Cargando datos desde la base de datos..."):
                df_real = cargar_datos_desde_bd(archivo_id_seleccionado, usuario_actual.id)
        else:
            # Cargar nuevo archivo
            archivo_cartola_nuevo = st.sidebar.file_uploader(
                "Cargar nueva cartola (Excel)",
                type=['xlsx', 'xls'],
                key="archivo_cartola_nuevo_comparativo"
            )
            
            if archivo_cartola_nuevo is None:
                st.warning("⚠️ Por favor, carga una cartola para continuar.")
                st.stop()
            
            # Procesar archivo nuevo de forma simplificada
            with st.spinner("🔄 Procesando cartola..."):
                import tempfile
                import os
                
                # Guardar archivo temporalmente
                with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as tmp_file:
                    tmp_file.write(archivo_cartola_nuevo.read())
                    tmp_path = tmp_file.name
                
                try:
                    # Buscar la fila de encabezados primero
                    fila_encabezados = encontrar_fila_encabezados(tmp_path)
                    
                    # Leer el archivo usando la fila encontrada como encabezados
                    if fila_encabezados > 0:
                        df_real = pd.read_excel(tmp_path, header=fila_encabezados)
                        debug_info(f"💡 Encabezados detectados en la fila {fila_encabezados + 1}")
                    else:
                        # Intentar leer sin especificar header
                        df_real = pd.read_excel(tmp_path, header=0)
                    
                    # Normalizar nombres de columnas (convertir a string primero si hay números)
                    df_real.columns = [str(col).strip().upper() for col in df_real.columns]
                    
                    # Si las columnas son UNNAMED, intentar leer de nuevo buscando mejor
                    if any('UNNAMED' in str(col) for col in df_real.columns):
                        debug_warning("⚠️ Detectadas columnas sin nombre. Buscando encabezados de forma más agresiva...")
                        # Intentar leer sin header y buscar manualmente
                        df_temp = pd.read_excel(tmp_path, header=None, nrows=30)
                        
                        # Buscar fila con encabezados
                        encontrado = False
                        for idx in range(len(df_temp)):
                            row = df_temp.iloc[idx]
                            valores = [str(val).upper().strip() for val in row.values if pd.notna(val) and str(val).strip() != '']
                            
                            # Verificar si esta fila tiene las palabras clave (normalizar para comparar)
                            valores_norm = [normalizar(str(v)) for v in valores]
                            tiene_fecha = any('FECHA' in v for v in valores_norm)
                            tiene_descripcion = any('DESCRIPCION' in v or 'GLOSA' in v or 'DETALLE' in v for v in valores_norm)
                            tiene_abonos = any('ABONO' in v or 'CREDITO' in v for v in valores_norm)
                            tiene_cargos = any('CARGO' in v or 'DEBITO' in v for v in valores_norm)
                            
                            if (tiene_fecha or tiene_descripcion) and (tiene_abonos or tiene_cargos):
                                # Esta es la fila de encabezados
                                df_real = pd.read_excel(tmp_path, header=idx)
                                df_real.columns = [str(col).strip().upper() for col in df_real.columns]
                                debug_info(f"✅ Encabezados encontrados en la fila {idx + 1}")
                                encontrado = True
                                break
                        
                        if not encontrado:
                            debug_warning("⚠️ No se pudieron detectar los encabezados automáticamente")
                    
                    # Limpiar filas vacías al inicio y final
                    df_real = df_real.dropna(how='all').reset_index(drop=True)
                    
                    # Buscar columnas necesarias (flexible y más completo)
                    col_fecha = None
                    col_desc = None
                    col_abono = None
                    col_cargo = None
                    
                    # Mostrar columnas disponibles para debug (convertir a string para evitar errores con floats)
                    columnas_str = [str(col) for col in df_real.columns.tolist()[:10]]
                    debug_info(f"📋 Columnas encontradas: {', '.join(columnas_str)}")
                    
                    for col in df_real.columns:
                        col_upper = str(col).upper().strip()
                        # Buscar fecha con más variantes
                        if col_fecha is None:
                            if any(palabra in col_upper for palabra in ["FECHA", "DATE", "FECHA OPERACION", "FECHA MOVIMIENTO", "FECHA TRANSACCION", "FECHA VALOR", "FECHA OPER", "FECHA VAL"]):
                                col_fecha = col
                            # Si no se encuentra por nombre, intentar detectar por contenido
                            elif col_fecha is None and len(df_real) > 0:
                                # Intentar convertir la primera fila para ver si es fecha
                                try:
                                    primera_fila = df_real[col].iloc[0]
                                    if pd.notna(primera_fila):
                                        # Intentar convertir a fecha
                                        test_date = pd.to_datetime(primera_fila, errors='coerce', dayfirst=True)
                                        if pd.notna(test_date):
                                            col_fecha = col
                                except:
                                    pass
                        # Buscar descripción - normalizar el nombre de la columna para comparar
                        if col_desc is None:
                            # Normalizar el nombre de la columna para comparar (sin acentos)
                            col_normalizada = normalizar(str(col))
                            if any(palabra in col_normalizada for palabra in ["DESCRIPCION", "DETALLE", "GLOSA", "CONCEPTO", "MOTIVO", "DESCRIPCION MOVIMIENTO", "GLOSA MOVIMIENTO"]):
                                col_desc = col
                        # Buscar abonos - PRIORIZAR palabras específicas de ABONOS
                        if col_abono is None:
                            # Priorizar palabras específicas de abonos (evitar palabras ambiguas)
                            if any(palabra in col_upper for palabra in ["ABONOS (CLP)", "ABONO (CLP)", "ABONOS", "ABONO"]):
                                col_abono = col
                            elif any(palabra in col_upper for palabra in ["DEPOSITO", "DEPOSITOS", "CREDITO", "CREDITOS"]) and "CARGO" not in col_upper and "DEBITO" not in col_upper:
                                col_abono = col
                            # Solo usar INGRESO si no contiene palabras de cargos
                            elif "INGRESO" in col_upper and "EGRESO" not in col_upper and "CARGO" not in col_upper:
                                col_abono = col
                        
                        # Buscar cargos - PRIORIZAR palabras específicas de CARGOS
                        if col_cargo is None:
                            # Priorizar palabras específicas de cargos (evitar palabras ambiguas)
                            if any(palabra in col_upper for palabra in ["CARGOS (CLP)", "CARGO (CLP)", "CARGOS", "CARGO"]):
                                col_cargo = col
                            elif any(palabra in col_upper for palabra in ["DEBITO", "DÉBITO", "DEBITOS"]) and "ABONO" not in col_upper and "CREDITO" not in col_upper:
                                col_cargo = col
                            # Solo usar EGRESO si no contiene palabras de abonos
                            elif "EGRESO" in col_upper and "INGRESO" not in col_upper and "ABONO" not in col_upper:
                                col_cargo = col
                    
                    # Debug: Mostrar qué columnas se detectaron (solo en modo debug)
                    if MODO_DEBUG:
                        st.sidebar.markdown("---")
                        st.sidebar.markdown("### 🔍 Detección de Columnas")
                        if col_abono:
                            debug_info(f"✅ ABONOS detectado: '{col_abono}'")
                            # Mostrar muestra de valores
                            if col_abono in df_real.columns:
                                muestra_abonos = df_real[col_abono].head(5).tolist()
                                with debug_expander(f"   Muestra ABONOS"):
                                    st.write(muestra_abonos)
                        else:
                            debug_warning("⚠️ No se detectó columna de ABONOS")
                        
                        if col_cargo:
                            debug_info(f"✅ CARGOS detectado: '{col_cargo}'")
                            # Mostrar muestra de valores
                            if col_cargo in df_real.columns:
                                muestra_cargos = df_real[col_cargo].head(5).tolist()
                                with debug_expander(f"   Muestra CARGOS"):
                                    st.write(muestra_cargos)
                        else:
                            debug_warning("⚠️ No se detectó columna de CARGOS")
                        
                        # CRÍTICO: Mostrar información de la columna de descripción
                        if col_desc:
                            debug_info(f"✅ DESCRIPCION detectado: '{col_desc}'")
                            # Mostrar muestra de valores ANTES de renombrar
                            if col_desc in df_real.columns:
                                muestra_desc = df_real[col_desc].head(5).tolist()
                                valores_no_vacios = df_real[col_desc].notna().sum()
                                valores_vacios = df_real[col_desc].isna().sum()
                                with debug_expander(f"   Muestra DESCRIPCION"):
                                    st.write(f"Muestra (primeras 5): {muestra_desc}")
                                    st.write(f"Valores no vacíos: {valores_no_vacios} | Vacíos: {valores_vacios}")
                                if valores_no_vacios == 0:
                                    debug_warning("❌ PROBLEMA: La columna de descripción está completamente vacía!")
                        else:
                            debug_warning("❌ No se detectó columna de DESCRIPCION")
                            debug_warning("⚠️ Se creará una columna vacía. Las transacciones no se podrán clasificar.")
                    
                    # IMPORTANTE: Verificar que ABONOS y CARGOS no sean la misma columna
                    if col_abono and col_cargo and col_abono == col_cargo:
                        st.error("❌ ERROR: Se detectó que ABONOS y CARGOS apuntan a la misma columna.")
                        st.info("💡 Esto indica un problema en la detección de columnas del archivo Excel.")
                        with st.expander("🔍 Ver todas las columnas del archivo"):
                            st.write("Columnas encontradas:", df_real.columns.tolist())
                            st.write("Primeras 5 filas del archivo:")
                            st.dataframe(df_real.head(5))
                        st.stop()
                    else:
                        # Renombrar columnas normalmente
                        if col_abono:
                            # Guardar valores antes de renombrar para debug
                            valores_abonos_antes = df_real[col_abono].sum() if col_abono in df_real.columns else 0
                            df_real.rename(columns={col_abono: "ABONOS (CLP)"}, inplace=True)
                            if MODO_DEBUG:
                                debug_info(f"💰 Total ABONOS antes de procesar: ${valores_abonos_antes:,.0f}")
                        
                        if col_cargo:
                            # Guardar valores antes de renombrar para debug
                            valores_cargos_antes = df_real[col_cargo].sum() if col_cargo in df_real.columns else 0
                            df_real.rename(columns={col_cargo: "CARGOS (CLP)"}, inplace=True)
                            if MODO_DEBUG:
                                debug_info(f"💸 Total CARGOS antes de procesar: ${valores_cargos_antes:,.0f}")
                    
                    # Renombrar otras columnas
                    if col_fecha:
                        df_real.rename(columns={col_fecha: "FECHA"}, inplace=True)
                    if col_desc:
                        df_real.rename(columns={col_desc: "DESCRIPCION"}, inplace=True)
                    
                    # Asegurar columnas necesarias
                    if "FECHA" not in df_real.columns:
                        st.error("❌ No se encontró columna de fecha en el archivo.")
                        with st.expander("🔍 Ver columnas disponibles"):
                            st.write("Columnas encontradas:", df_real.columns.tolist())
                            st.write("Primeras filas del archivo:")
                            st.dataframe(df_real.head())
                        st.stop()
                    
                    # Asegurar DESCRIPCION existe antes de cualquier acceso
                    # Solo mostrar error si realmente no se detectó col_desc Y no existe DESCRIPCION
                    if "DESCRIPCION" not in df_real.columns:
                        # Si col_desc era None, entonces realmente no se detectó
                        if col_desc is None:
                            df_real["DESCRIPCION"] = ""
                            if MODO_DEBUG:
                                debug_warning("❌ PROBLEMA CRÍTICO: No se encontró columna de descripción. Se creó vacía.")
                            st.error("❌ ERROR: No se pudo detectar la columna de descripción en el archivo Excel.")
                            st.warning("⚠️ Sin descripciones, las transacciones NO se podrán clasificar automáticamente.")
                            with st.expander("🔍 Ver todas las columnas del archivo para identificar la descripción"):
                                st.write("**Columnas encontradas:**")
                                st.write(df_real.columns.tolist())
                                st.write("**Primeras 5 filas del archivo:**")
                                st.dataframe(df_real.head(5))
                        else:
                            # Si col_desc se detectó pero DESCRIPCION no existe, hubo un problema al renombrar
                            if MODO_DEBUG:
                                debug_warning("⚠️ Se detectó la columna pero no se pudo renombrar. Intentando crear DESCRIPCION...")
                            # Intentar copiar desde la columna original si aún existe
                            if col_desc in df_real.columns:
                                df_real["DESCRIPCION"] = df_real[col_desc].copy()
                                if MODO_DEBUG:
                                    debug_info("✅ Columna DESCRIPCION creada desde la columna original.")
                            else:
                                df_real["DESCRIPCION"] = ""
                                st.sidebar.error("❌ No se pudo crear DESCRIPCION. La columna original ya no existe.")
                    else:
                        # Verificar que DESCRIPCION tiene valores después de renombrar
                        valores_desc = df_real["DESCRIPCION"].notna().sum()
                        valores_vacios_desc = df_real["DESCRIPCION"].isna().sum()
                        if valores_desc == 0:
                            st.sidebar.error("❌ PROBLEMA: La columna DESCRIPCION está completamente vacía después de renombrar!")
                            st.error("❌ ERROR: La columna de descripción está vacía. Verifica el archivo Excel.")
                            with st.expander("🔍 Ver datos del archivo"):
                                st.write("**Primeras 10 filas:**")
                                st.dataframe(df_real[["FECHA", "DESCRIPCION", "ABONOS (CLP)", "CARGOS (CLP)"]].head(10) if all(col in df_real.columns for col in ["FECHA", "DESCRIPCION", "ABONOS (CLP)", "CARGOS (CLP)"]) else df_real.head(10))
                        else:
                            st.sidebar.success(f"✅ DESCRIPCION tiene {valores_desc} valores no vacíos (de {len(df_real)} filas)")
                            # Mostrar muestra después de renombrar
                            muestra_desc_final = df_real["DESCRIPCION"].head(3).tolist()
                            st.sidebar.write(f"   Muestra final: {muestra_desc_final}")
                    
                    # Convertir fechas - intentar múltiples formatos
                    try:
                        df_real["FECHA"] = pd.to_datetime(df_real["FECHA"], errors='coerce', dayfirst=True)
                        # Si falla, intentar sin dayfirst
                        if df_real["FECHA"].isna().all():
                            df_real["FECHA"] = pd.to_datetime(df_real["FECHA"], errors='coerce', dayfirst=False)
                    except:
                        df_real["FECHA"] = pd.to_datetime(df_real["FECHA"], errors='coerce')
                    
                    # Calcular MES antes de continuar (necesario para validaciones)
                    df_real["MES"] = df_real["FECHA"].dt.to_period("M").dt.to_timestamp()
                    
                    # Asegurar columnas de montos
                    if "ABONOS (CLP)" not in df_real.columns:
                        df_real["ABONOS (CLP)"] = 0
                        st.warning("⚠️ No se encontró columna de ABONOS. Se creó con valores en 0.")
                    else:
                        # Convertir a numérico y mostrar debug
                        df_real["ABONOS (CLP)"] = pd.to_numeric(df_real["ABONOS (CLP)"], errors='coerce').fillna(0)
                        total_abonos_despues = df_real["ABONOS (CLP)"].sum()
                        filas_abonos = len(df_real[df_real["ABONOS (CLP)"] > 0])
                        st.sidebar.info(f"💰 ABONOS después de convertir: ${total_abonos_despues:,.0f} ({filas_abonos} filas)")
                    
                    if "CARGOS (CLP)" not in df_real.columns:
                        df_real["CARGOS (CLP)"] = 0
                        st.warning("⚠️ No se encontró columna de CARGOS. Se creó con valores en 0.")
                    else:
                        # Convertir a numérico y mostrar debug
                        df_real["CARGOS (CLP)"] = pd.to_numeric(df_real["CARGOS (CLP)"], errors='coerce').fillna(0)
                        total_cargos_despues = df_real["CARGOS (CLP)"].sum()
                        filas_cargos = len(df_real[df_real["CARGOS (CLP)"] > 0])
                        st.sidebar.info(f"💸 CARGOS después de convertir: ${total_cargos_despues:,.0f} ({filas_cargos} filas)")
                    
                    # Validación final: Verificar que ambas columnas existen y tienen datos diferentes
                    total_abonos = df_real["ABONOS (CLP)"].sum()
                    total_cargos = df_real["CARGOS (CLP)"].sum()
                    
                    # Debug: Mostrar muestra de datos (solo si todas las columnas existen)
                    if all(col in df_real.columns for col in ["FECHA", "DESCRIPCION", "ABONOS (CLP)", "CARGOS (CLP)"]):
                        st.sidebar.markdown("---")
                        st.sidebar.markdown("### 📊 Muestra de Datos")
                        muestra_df = df_real[["FECHA", "DESCRIPCION", "ABONOS (CLP)", "CARGOS (CLP)"]].head(3)
                        with st.sidebar.expander("🔍 Ver primeras 3 filas"):
                            st.dataframe(muestra_df)
                    
                    if abs(total_abonos - total_cargos) < 1 and total_abonos > 0:
                        st.error("❌ ERROR: Los totales de ABONOS y CARGOS son iguales. Esto indica un problema en la lectura del archivo.")
                        st.info("💡 Tu archivo Excel debe tener columnas SEPARADAS para ABONOS y CARGOS.")
                        st.info("📋 Columnas esperadas en el Excel:")
                        st.info("   - Una columna llamada 'ABONOS', 'DEPOSITOS', 'CREDITOS' o similar para ingresos")
                        st.info("   - Una columna llamada 'CARGOS', 'DEBITOS', 'EGRESOS' o similar para gastos")
                        with st.expander("🔍 Ver columnas detectadas y datos"):
                            st.write("Columnas encontradas:", df_real.columns.tolist())
                            st.write("Primeras 10 filas:")
                            # Solo mostrar columnas que existen
                            cols_mostrar = [col for col in ["FECHA", "DESCRIPCION", "ABONOS (CLP)", "CARGOS (CLP)"] if col in df_real.columns]
                            if cols_mostrar:
                                st.dataframe(df_real[cols_mostrar].head(10))
                            else:
                                st.dataframe(df_real.head(10))
                            st.write(f"Total ABONOS: ${total_abonos:,.0f}")
                            st.write(f"Total CARGOS: ${total_cargos:,.0f}")
                            st.write(f"Filas con ABONOS > 0: {len(df_real[df_real['ABONOS (CLP)'] > 0])}")
                            st.write(f"Filas con CARGOS > 0: {len(df_real[df_real['CARGOS (CLP)'] > 0])}")
                        st.stop()
                    
                    # Clasificar usando clasificadores
                    clasificadores_bd = obtener_clasificadores(usuario_actual.id)
                    config_clasificadores = None
                    
                    # Mostrar información sobre clasificadores
                    st.sidebar.markdown("---")
                    st.sidebar.markdown("### 🏷️ Clasificadores Cargados")
                    
                    if clasificadores_bd and len(clasificadores_bd) > 0:
                        config_clasificadores = convertir_clasificadores_bd_a_dict(clasificadores_bd)
                        clasif_abonos = len(config_clasificadores.get("clasificadores", {}).get("abonos", []))
                        clasif_cargos = len(config_clasificadores.get("clasificadores", {}).get("cargos", []))
                        st.sidebar.success(f"✅ {len(clasificadores_bd)} clasificadores encontrados")
                        st.sidebar.info(f"📊 ABONOS: {clasif_abonos} | CARGOS: {clasif_cargos}")
                        
                        # Mostrar información detallada de clasificadores (siempre visible)
                        with st.sidebar.expander("🔍 Ver clasificadores cargados", expanded=False):
                            if clasif_abonos > 0:
                                st.write("**📊 CLASIFICADORES ABONOS:**")
                                for idx, clf in enumerate(config_clasificadores.get("clasificadores", {}).get("abonos", []), 1):
                                    palabras = clf.get("palabras_clave", [])
                                    palabras_str = ", ".join(palabras) if palabras else "(sin palabras clave)"
                                    tipo_coinc = clf.get("tipo", "contiene_cualquiera")
                                    st.write(f"{idx}. **{clf.get('nombre', 'N/A')}**")
                                    st.write(f"   Palabras: `{palabras_str}`")
                                    st.write(f"   Tipo: `{tipo_coinc}`")
                                    if clf.get("excluir"):
                                        excluir_str = ", ".join(clf.get("excluir", []))
                                        st.write(f"   Excluir: `{excluir_str}`")
                                    st.write("---")
                            else:
                                st.warning("⚠️ No hay clasificadores de ABONOS configurados")
                            
                            if clasif_cargos > 0:
                                st.write("**📊 CLASIFICADORES CARGOS:**")
                                for idx, clf in enumerate(config_clasificadores.get("clasificadores", {}).get("cargos", []), 1):
                                    palabras = clf.get("palabras_clave", [])
                                    palabras_str = ", ".join(palabras) if palabras else "(sin palabras clave)"
                                    tipo_coinc = clf.get("tipo", "contiene_cualquiera")
                                    st.write(f"{idx}. **{clf.get('nombre', 'N/A')}**")
                                    st.write(f"   Palabras: `{palabras_str}`")
                                    st.write(f"   Tipo: `{tipo_coinc}`")
                                    if clf.get("excluir"):
                                        excluir_str = ", ".join(clf.get("excluir", []))
                                        st.write(f"   Excluir: `{excluir_str}`")
                                    st.write("---")
                            else:
                                st.warning("⚠️ No hay clasificadores de CARGOS configurados")
                    else:
                        st.sidebar.error("❌ No se encontraron clasificadores en la base de datos")
                        st.sidebar.warning("⚠️ Todas las transacciones quedarán como 'NO CLASIFICADO'")
                        st.sidebar.info("💡 Configura clasificadores en la aplicación principal de Flujo de Caja")
                    
                    # Aplicar clasificación
                    if config_clasificadores:
                        df_real["CLASIFICACION"] = df_real.apply(
                            lambda row: clasificar_mejorado(
                                str(row.get("DESCRIPCION", "")),
                                float(row.get("ABONOS (CLP)", 0)),
                                config_clasificadores,
                                cargo=float(row.get("CARGOS (CLP)", 0))
                            ),
                            axis=1
                        )
                        
                        # Mostrar estadísticas de clasificación (siempre visible)
                        total_clasificados = len(df_real[df_real["CLASIFICACION"] != "NO CLASIFICADO"])
                        total_no_clasificados = len(df_real[df_real["CLASIFICACION"] == "NO CLASIFICADO"])
                        
                        st.sidebar.markdown("---")
                        st.sidebar.markdown("### 📊 Resultado de Clasificación")
                        st.sidebar.info(f"✅ Clasificados: {total_clasificados}")
                        st.sidebar.warning(f"⚠️ Sin clasificar: {total_no_clasificados}")
                        
                        # Mostrar ejemplos de transacciones no clasificadas (siempre visible)
                        if total_no_clasificados > 0:
                            ejemplos = df_real[df_real["CLASIFICACION"] == "NO CLASIFICADO"].head(5)
                            with st.sidebar.expander("🔍 Ver ejemplos NO CLASIFICADOS", expanded=False):
                                st.write(f"**Mostrando {len(ejemplos)} de {total_no_clasificados} transacciones sin clasificar:**")
                                for idx, (_, row) in enumerate(ejemplos.iterrows(), 1):
                                    desc = str(row.get("DESCRIPCION", ""))
                                    desc_norm = normalizar(desc)
                                    abono = float(row.get("ABONOS (CLP)", 0))
                                    cargo = float(row.get("CARGOS (CLP)", 0))
                                    tipo_trans = "ABONO" if abono > 0 else "CARGO" if cargo > 0 else "AMBOS/NINGUNO"
                                    
                                    st.write(f"**{idx}. {tipo_trans}**")
                                    st.write(f"   Original: `{desc[:80]}{'...' if len(desc) > 80 else ''}`")
                                    st.write(f"   Normalizada: `{desc_norm[:80]}{'...' if len(desc_norm) > 80 else ''}`")
                                    st.write(f"   Monto: Abono=${abono:,.0f} | Cargo=${cargo:,.0f}")
                                    
                                    # Analizar por qué no coincidió con los clasificadores
                                    if tipo_trans == "ABONO" and clasif_abonos > 0:
                                        st.write(f"   🔍 **Análisis de clasificadores ABONOS:**")
                                        clasificadores_aplicables = config_clasificadores.get("clasificadores", {}).get("abonos", [])
                                        for clf_idx, clf in enumerate(clasificadores_aplicables, 1):
                                            palabras_clave = clf.get("palabras_clave", [])
                                            palabras_norm = [normalizar(str(p)) for p in palabras_clave if p]
                                            tipo_coinc = clf.get("tipo", "contiene_cualquiera")
                                            
                                            # Evaluar si debería coincidir
                                            if tipo_coinc == "contiene_exacto":
                                                todas_presentes = all(palabra in desc_norm for palabra in palabras_norm)
                                                st.write(f"      {clf_idx}. **{clf.get('nombre', 'N/A')}** ({tipo_coinc})")
                                                for palabra in palabras_norm:
                                                    presente = palabra in desc_norm
                                                    icono = "✓" if presente else "✗"
                                                    st.write(f"         {icono} `{palabra}`")
                                                st.write(f"         Resultado: {'✓ COINCIDIRÍA' if todas_presentes else '✗ No coincide (faltan palabras)'}")
                                            else:  # contiene_cualquiera
                                                alguna_presente = any(palabra in desc_norm for palabra in palabras_norm)
                                                st.write(f"      {clf_idx}. **{clf.get('nombre', 'N/A')}** ({tipo_coinc})")
                                                for palabra in palabras_norm:
                                                    presente = palabra in desc_norm
                                                    icono = "✓" if presente else "✗"
                                                    st.write(f"         {icono} `{palabra}`")
                                                st.write(f"         Resultado: {'✓ COINCIDIRÍA' if alguna_presente else '✗ No coincide (ninguna palabra encontrada)'}")
                                            
                                            # Verificar exclusiones
                                            if clf.get("excluir"):
                                                excluir_norm = [normalizar(str(e)) for e in clf.get("excluir", [])]
                                                for exclusion in excluir_norm:
                                                    if exclusion in desc_norm:
                                                        st.write(f"         ⚠️ EXCLUIDO por: `{exclusion}`")
                                            
                                            st.write("")
                                    
                                    elif tipo_trans == "CARGO" and clasif_cargos > 0:
                                        st.write(f"   🔍 **Análisis de clasificadores CARGOS:**")
                                        clasificadores_aplicables = config_clasificadores.get("clasificadores", {}).get("cargos", [])
                                        for clf_idx, clf in enumerate(clasificadores_aplicables, 1):
                                            palabras_clave = clf.get("palabras_clave", [])
                                            palabras_norm = [normalizar(str(p)) for p in palabras_clave if p]
                                            tipo_coinc = clf.get("tipo", "contiene_cualquiera")
                                            
                                            # Evaluar si debería coincidir
                                            if tipo_coinc == "contiene_exacto":
                                                todas_presentes = all(palabra in desc_norm for palabra in palabras_norm)
                                                st.write(f"      {clf_idx}. **{clf.get('nombre', 'N/A')}** ({tipo_coinc})")
                                                for palabra in palabras_norm:
                                                    presente = palabra in desc_norm
                                                    icono = "✓" if presente else "✗"
                                                    st.write(f"         {icono} `{palabra}`")
                                                st.write(f"         Resultado: {'✓ COINCIDIRÍA' if todas_presentes else '✗ No coincide (faltan palabras)'}")
                                            else:  # contiene_cualquiera
                                                alguna_presente = any(palabra in desc_norm for palabra in palabras_norm)
                                                st.write(f"      {clf_idx}. **{clf.get('nombre', 'N/A')}** ({tipo_coinc})")
                                                for palabra in palabras_norm:
                                                    presente = palabra in desc_norm
                                                    icono = "✓" if presente else "✗"
                                                    st.write(f"         {icono} `{palabra}`")
                                                st.write(f"         Resultado: {'✓ COINCIDIRÍA' if alguna_presente else '✗ No coincide (ninguna palabra encontrada)'}")
                                            
                                            # Verificar exclusiones
                                            if clf.get("excluir"):
                                                excluir_norm = [normalizar(str(e)) for e in clf.get("excluir", [])]
                                                for exclusion in excluir_norm:
                                                    if exclusion in desc_norm:
                                                        st.write(f"         ⚠️ EXCLUIDO por: `{exclusion}`")
                                            
                                            st.write("")
                                    
                                    st.write("---")
                    else:
                        df_real["CLASIFICACION"] = "NO CLASIFICADO"
                    
                    # Eliminar filas sin fecha válida
                    df_real = df_real[df_real["FECHA"].notna()].copy()
                    
                    if df_real.empty:
                        st.error("❌ No se pudieron procesar datos válidos del archivo.")
                        st.stop()
                    
                except Exception as e:
                    st.error(f"❌ Error al procesar cartola: {e}")
                    with st.expander("🔍 Ver detalles del error"):
                        st.code(traceback.format_exc())
                    st.stop()
                finally:
                    # Limpiar archivo temporal
                    if os.path.exists(tmp_path):
                        os.unlink(tmp_path)
    else:
        # No hay archivos guardados, solo permitir cargar nuevo
        st.sidebar.info("💡 No hay cartolas guardadas. Carga una nueva cartola.")
        archivo_cartola_nuevo = st.sidebar.file_uploader(
            "Cargar cartola (Excel)",
            type=['xlsx', 'xls'],
            key="archivo_cartola_nuevo_comparativo"
        )
        
        if archivo_cartola_nuevo is None:
            st.warning("⚠️ Por favor, carga una cartola para continuar.")
            st.stop()
        
        # Procesar archivo nuevo (usar la misma lógica que arriba)
        with st.spinner("🔄 Procesando cartola..."):
            import tempfile
            import os
            
            # Guardar archivo temporalmente
            with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as tmp_file:
                tmp_file.write(archivo_cartola_nuevo.read())
                tmp_path = tmp_file.name
            
            try:
                # Buscar la fila de encabezados primero
                fila_encabezados = encontrar_fila_encabezados(tmp_path)
                
                # Leer el archivo usando la fila encontrada como encabezados
                if fila_encabezados > 0:
                    df_real = pd.read_excel(tmp_path, header=fila_encabezados)
                    st.sidebar.info(f"💡 Encabezados detectados en la fila {fila_encabezados + 1}")
                else:
                    # Intentar leer sin especificar header
                    df_real = pd.read_excel(tmp_path, header=0)
                
                # Normalizar nombres de columnas (convertir a string primero si hay números)
                df_real.columns = [str(col).strip().upper() for col in df_real.columns]
                
                # Si las columnas son UNNAMED, intentar leer de nuevo buscando mejor
                if any('UNNAMED' in str(col) for col in df_real.columns):
                    debug_warning("⚠️ Detectadas columnas sin nombre. Buscando encabezados de forma más agresiva...")
                    # Intentar leer sin header y buscar manualmente
                    df_temp = pd.read_excel(tmp_path, header=None, nrows=30)
                    
                    # Buscar fila con encabezados
                    encontrado = False
                    for idx in range(len(df_temp)):
                        row = df_temp.iloc[idx]
                        valores = [str(val).upper().strip() for val in row.values if pd.notna(val) and str(val).strip() != '']
                        
                        # Verificar si esta fila tiene las palabras clave
                        tiene_fecha = any('FECHA' in v for v in valores)
                        # Normalizar valores para comparar (quitar acentos)
                        valores_norm = [normalizar(str(v)) for v in valores]
                        tiene_descripcion = any('DESCRIPCION' in v or 'GLOSA' in v or 'DETALLE' in v for v in valores_norm)
                        tiene_abonos = any('ABONO' in v or 'CREDITO' in v for v in valores_norm)
                        tiene_cargos = any('CARGO' in v or 'DEBITO' in v for v in valores_norm)
                        
                        if (tiene_fecha or tiene_descripcion) and (tiene_abonos or tiene_cargos):
                            # Esta es la fila de encabezados
                            df_real = pd.read_excel(tmp_path, header=idx)
                            df_real.columns = [str(col).strip().upper() for col in df_real.columns]
                            st.sidebar.success(f"✅ Encabezados encontrados en la fila {idx + 1}")
                            encontrado = True
                            break
                    
                    if not encontrado:
                        debug_warning("⚠️ No se pudieron detectar los encabezados automáticamente")
                
                # Limpiar filas vacías al inicio y final
                df_real = df_real.dropna(how='all').reset_index(drop=True)
                
                # Buscar columnas necesarias (flexible y más completo)
                col_fecha = None
                col_desc = None
                col_abono = None
                col_cargo = None
                
                # Mostrar columnas disponibles para debug (convertir a string para evitar errores con floats)
                columnas_str = [str(col) for col in df_real.columns.tolist()[:10]]
                st.sidebar.info(f"📋 Columnas encontradas: {', '.join(columnas_str)}")
                
                for col in df_real.columns:
                    col_upper = col.upper().strip()
                    # Buscar fecha con más variantes
                    if col_fecha is None:
                        if any(palabra in col_upper for palabra in ["FECHA", "DATE", "FECHA OPERACION", "FECHA MOVIMIENTO", "FECHA TRANSACCION", "FECHA VALOR", "FECHA OPER", "FECHA VAL"]):
                            col_fecha = col
                        # Si no se encuentra por nombre, intentar detectar por contenido
                        elif col_fecha is None and len(df_real) > 0:
                            # Intentar convertir la primera fila para ver si es fecha
                            try:
                                primera_fila = df_real[col].iloc[0]
                                if pd.notna(primera_fila):
                                    # Intentar convertir a fecha
                                    test_date = pd.to_datetime(primera_fila, errors='coerce', dayfirst=True)
                                    if pd.notna(test_date):
                                        col_fecha = col
                            except:
                                pass
                    # Buscar descripción - normalizar el nombre de la columna para comparar
                    if col_desc is None:
                        # Normalizar el nombre de la columna para comparar (sin acentos)
                        col_normalizada = normalizar(str(col))
                        if any(palabra in col_normalizada for palabra in ["DESCRIPCION", "DETALLE", "GLOSA", "CONCEPTO", "MOTIVO", "DESCRIPCION MOVIMIENTO", "GLOSA MOVIMIENTO"]):
                            col_desc = col
                    # Buscar abonos - PRIORIZAR palabras específicas de ABONOS
                    if col_abono is None:
                        # Priorizar palabras específicas de abonos (evitar palabras ambiguas)
                        if any(palabra in col_upper for palabra in ["ABONOS (CLP)", "ABONO (CLP)", "ABONOS", "ABONO"]):
                            col_abono = col
                        elif any(palabra in col_upper for palabra in ["DEPOSITO", "DEPOSITOS", "CREDITO", "CREDITOS"]) and "CARGO" not in col_upper and "DEBITO" not in col_upper:
                            col_abono = col
                        # Solo usar INGRESO si no contiene palabras de cargos
                        elif "INGRESO" in col_upper and "EGRESO" not in col_upper and "CARGO" not in col_upper:
                            col_abono = col
                    
                    # Buscar cargos - PRIORIZAR palabras específicas de CARGOS
                    if col_cargo is None:
                        # Priorizar palabras específicas de cargos (evitar palabras ambiguas)
                        if any(palabra in col_upper for palabra in ["CARGOS (CLP)", "CARGO (CLP)", "CARGOS", "CARGO"]):
                            col_cargo = col
                        elif any(palabra in col_upper for palabra in ["DEBITO", "DÉBITO", "DEBITOS"]) and "ABONO" not in col_upper and "CREDITO" not in col_upper:
                            col_cargo = col
                        # Solo usar EGRESO si no contiene palabras de abonos
                        elif "EGRESO" in col_upper and "INGRESO" not in col_upper and "ABONO" not in col_upper:
                            col_cargo = col
                
                # Renombrar otras columnas primero
                if col_fecha:
                    df_real.rename(columns={col_fecha: "FECHA"}, inplace=True)
                if col_desc:
                    df_real.rename(columns={col_desc: "DESCRIPCION"}, inplace=True)
                
                # Debug: Mostrar qué columnas se detectaron
                st.sidebar.markdown("---")
                st.sidebar.markdown("### 🔍 Detección de Columnas")
                if col_abono:
                    st.sidebar.success(f"✅ ABONOS detectado: '{col_abono}'")
                    # Mostrar muestra de valores
                    if col_abono in df_real.columns:
                        try:
                            muestra_abonos = df_real[col_abono].head(5).tolist()
                            total_abonos_antes = pd.to_numeric(df_real[col_abono], errors='coerce').fillna(0).sum()
                            st.sidebar.write(f"   Total antes: ${total_abonos_antes:,.0f}")
                        except:
                            pass
                else:
                    st.sidebar.warning("⚠️ No se detectó columna de ABONOS")
                
                if col_cargo:
                    st.sidebar.success(f"✅ CARGOS detectado: '{col_cargo}'")
                    # Mostrar muestra de valores
                    if col_cargo in df_real.columns:
                        try:
                            muestra_cargos = df_real[col_cargo].head(5).tolist()
                            total_cargos_antes = pd.to_numeric(df_real[col_cargo], errors='coerce').fillna(0).sum()
                            st.sidebar.write(f"   Total antes: ${total_cargos_antes:,.0f}")
                        except:
                            pass
                else:
                    st.sidebar.warning("⚠️ No se detectó columna de CARGOS")
                
                # CRÍTICO: Mostrar información de la columna de descripción
                if col_desc:
                    st.sidebar.success(f"✅ DESCRIPCION detectado: '{col_desc}'")
                    # Mostrar muestra de valores ANTES de renombrar
                    if col_desc in df_real.columns:
                        muestra_desc = df_real[col_desc].head(5).tolist()
                        valores_no_vacios = df_real[col_desc].notna().sum()
                        valores_vacios = df_real[col_desc].isna().sum()
                        st.sidebar.write(f"   Muestra (primeras 5): {muestra_desc}")
                        st.sidebar.write(f"   Valores no vacíos: {valores_no_vacios} | Vacíos: {valores_vacios}")
                        if valores_no_vacios == 0:
                            st.sidebar.error("❌ PROBLEMA: La columna de descripción está completamente vacía!")
                else:
                    st.sidebar.error("❌ No se detectó columna de DESCRIPCION")
                    st.sidebar.warning("⚠️ Se creará una columna vacía. Las transacciones no se podrán clasificar.")
                
                # IMPORTANTE: Verificar que ABONOS y CARGOS no sean la misma columna
                if col_abono and col_cargo and col_abono == col_cargo:
                    st.error("❌ ERROR: Se detectó que ABONOS y CARGOS apuntan a la misma columna.")
                    st.info("💡 Esto indica un problema en la detección de columnas del archivo Excel.")
                    with st.expander("🔍 Ver todas las columnas del archivo"):
                        st.write("Columnas encontradas:", df_real.columns.tolist())
                        st.write("Primeras 5 filas del archivo:")
                        st.dataframe(df_real.head(5))
                    st.stop()
                else:
                    # Columnas separadas, renombrar normalmente
                    if col_abono:
                        # Guardar valores antes de renombrar para debug
                        valores_abonos_antes = pd.to_numeric(df_real[col_abono], errors='coerce').fillna(0).sum() if col_abono in df_real.columns else 0
                        df_real.rename(columns={col_abono: "ABONOS (CLP)"}, inplace=True)
                        st.sidebar.info(f"💰 Total ABONOS detectado: ${valores_abonos_antes:,.0f}")
                    
                    if col_cargo:
                        # Guardar valores antes de renombrar para debug
                        valores_cargos_antes = pd.to_numeric(df_real[col_cargo], errors='coerce').fillna(0).sum() if col_cargo in df_real.columns else 0
                        df_real.rename(columns={col_cargo: "CARGOS (CLP)"}, inplace=True)
                        st.sidebar.info(f"💸 Total CARGOS detectado: ${valores_cargos_antes:,.0f}")
                
                # Asegurar columnas necesarias
                if "FECHA" not in df_real.columns:
                    st.error("❌ No se encontró columna de fecha en el archivo.")
                    with st.expander("🔍 Ver columnas disponibles"):
                        st.write("Columnas encontradas:", df_real.columns.tolist())
                        st.write("Primeras filas del archivo:")
                        st.dataframe(df_real.head())
                    st.stop()
                
                # Asegurar DESCRIPCION existe antes de cualquier acceso
                # Solo mostrar error si realmente no se detectó col_desc Y no existe DESCRIPCION
                if "DESCRIPCION" not in df_real.columns:
                    # Si col_desc era None, entonces realmente no se detectó
                    if col_desc is None:
                        df_real["DESCRIPCION"] = ""
                        st.sidebar.error("❌ PROBLEMA CRÍTICO: No se encontró columna de descripción. Se creó vacía.")
                        st.error("❌ ERROR: No se pudo detectar la columna de descripción en el archivo Excel.")
                        st.warning("⚠️ Sin descripciones, las transacciones NO se podrán clasificar automáticamente.")
                        with st.expander("🔍 Ver todas las columnas del archivo para identificar la descripción"):
                            st.write("**Columnas encontradas:**")
                            st.write(df_real.columns.tolist())
                            st.write("**Primeras 5 filas del archivo:**")
                            st.dataframe(df_real.head(5))
                    else:
                        # Si col_desc se detectó pero DESCRIPCION no existe, hubo un problema al renombrar
                        st.sidebar.warning("⚠️ Se detectó la columna pero no se pudo renombrar. Intentando crear DESCRIPCION...")
                        # Intentar copiar desde la columna original si aún existe
                        if col_desc in df_real.columns:
                            df_real["DESCRIPCION"] = df_real[col_desc].copy()
                            st.sidebar.success("✅ Columna DESCRIPCION creada desde la columna original.")
                        else:
                            df_real["DESCRIPCION"] = ""
                            st.sidebar.error("❌ No se pudo crear DESCRIPCION. La columna original ya no existe.")
                else:
                    # Verificar que DESCRIPCION tiene valores después de renombrar
                    valores_desc = df_real["DESCRIPCION"].notna().sum()
                    valores_vacios_desc = df_real["DESCRIPCION"].isna().sum()
                    if valores_desc == 0:
                        st.sidebar.error("❌ PROBLEMA: La columna DESCRIPCION está completamente vacía después de renombrar!")
                        st.error("❌ ERROR: La columna de descripción está vacía. Verifica el archivo Excel.")
                        with st.expander("🔍 Ver datos del archivo"):
                            st.write("**Primeras 10 filas:**")
                            st.dataframe(df_real[["FECHA", "DESCRIPCION", "ABONOS (CLP)", "CARGOS (CLP)"]].head(10) if all(col in df_real.columns for col in ["FECHA", "DESCRIPCION", "ABONOS (CLP)", "CARGOS (CLP)"]) else df_real.head(10))
                    else:
                        st.sidebar.success(f"✅ DESCRIPCION tiene {valores_desc} valores no vacíos (de {len(df_real)} filas)")
                        # Mostrar muestra después de renombrar
                        muestra_desc_final = df_real["DESCRIPCION"].head(3).tolist()
                        st.sidebar.write(f"   Muestra final: {muestra_desc_final}")
                
                # Convertir fechas - intentar múltiples formatos
                try:
                    df_real["FECHA"] = pd.to_datetime(df_real["FECHA"], errors='coerce', dayfirst=True)
                    # Si falla, intentar sin dayfirst
                    if df_real["FECHA"].isna().all():
                        df_real["FECHA"] = pd.to_datetime(df_real["FECHA"], errors='coerce', dayfirst=False)
                except:
                    df_real["FECHA"] = pd.to_datetime(df_real["FECHA"], errors='coerce')
                
                # Calcular MES antes de continuar (necesario para validaciones)
                if pd.api.types.is_datetime64_any_dtype(df_real["FECHA"]):
                    df_real["MES"] = df_real["FECHA"].dt.to_period("M").dt.to_timestamp()
                
                # Asegurar columnas de montos y validar que no sean iguales
                if "ABONOS (CLP)" not in df_real.columns:
                    df_real["ABONOS (CLP)"] = 0
                else:
                    df_real["ABONOS (CLP)"] = pd.to_numeric(df_real["ABONOS (CLP)"], errors='coerce').fillna(0)
                
                if "CARGOS (CLP)" not in df_real.columns:
                    df_real["CARGOS (CLP)"] = 0
                else:
                    df_real["CARGOS (CLP)"] = pd.to_numeric(df_real["CARGOS (CLP)"], errors='coerce').fillna(0)
                
                # Validación crítica: Verificar que ABONOS y CARGOS no sean la misma columna
                if "ABONOS (CLP)" in df_real.columns and "CARGOS (CLP)" in df_real.columns:
                    # Verificar si ambas columnas tienen exactamente los mismos valores
                    if df_real["ABONOS (CLP)"].equals(df_real["CARGOS (CLP)"]):
                        st.error("❌ ERROR CRÍTICO: Las columnas ABONOS y CARGOS tienen los mismos valores. Esto indica un problema en la detección de columnas del archivo Excel.")
                        st.info("💡 Verifica que tu archivo Excel tenga columnas separadas para ABONOS y CARGOS, o que use valores positivos para abonos y negativos para cargos.")
                        with st.expander("🔍 Ver datos del archivo"):
                            st.write("Primeras 10 filas:")
                            # Solo mostrar columnas que existen
                            cols_mostrar = [col for col in ["FECHA", "DESCRIPCION", "ABONOS (CLP)", "CARGOS (CLP)"] if col in df_real.columns]
                            if cols_mostrar:
                                st.dataframe(df_real[cols_mostrar].head(10))
                            else:
                                st.dataframe(df_real.head(10))
                            st.write(f"Total ABONOS: ${df_real['ABONOS (CLP)'].sum():,.0f}")
                            st.write(f"Total CARGOS: ${df_real['CARGOS (CLP)'].sum():,.0f}")
                        st.stop()
                
                # Clasificar usando clasificadores
                clasificadores_bd = obtener_clasificadores(usuario_actual.id)
                config_clasificadores = None
                
                # Mostrar información sobre clasificadores
                st.sidebar.markdown("---")
                st.sidebar.markdown("### 🏷️ Clasificadores Cargados")
                
                if clasificadores_bd and len(clasificadores_bd) > 0:
                    config_clasificadores = convertir_clasificadores_bd_a_dict(clasificadores_bd)
                    clasif_abonos = len(config_clasificadores.get("clasificadores", {}).get("abonos", []))
                    clasif_cargos = len(config_clasificadores.get("clasificadores", {}).get("cargos", []))
                    st.sidebar.success(f"✅ {len(clasificadores_bd)} clasificadores encontrados")
                    st.sidebar.info(f"📊 ABONOS: {clasif_abonos} | CARGOS: {clasif_cargos}")
                    
                    # Mostrar información detallada de clasificadores (siempre visible)
                    with st.sidebar.expander("🔍 Ver clasificadores cargados", expanded=False):
                        if clasif_abonos > 0:
                            st.write("**📊 CLASIFICADORES ABONOS:**")
                            for idx, clf in enumerate(config_clasificadores.get("clasificadores", {}).get("abonos", []), 1):
                                palabras = clf.get("palabras_clave", [])
                                palabras_str = ", ".join(palabras) if palabras else "(sin palabras clave)"
                                tipo_coinc = clf.get("tipo", "contiene_cualquiera")
                                st.write(f"{idx}. **{clf.get('nombre', 'N/A')}**")
                                st.write(f"   Palabras: `{palabras_str}`")
                                st.write(f"   Tipo: `{tipo_coinc}`")
                                if clf.get("excluir"):
                                    excluir_str = ", ".join(clf.get("excluir", []))
                                    st.write(f"   Excluir: `{excluir_str}`")
                                st.write("---")
                        else:
                            st.warning("⚠️ No hay clasificadores de ABONOS configurados")
                        
                        if clasif_cargos > 0:
                            st.write("**📊 CLASIFICADORES CARGOS:**")
                            for idx, clf in enumerate(config_clasificadores.get("clasificadores", {}).get("cargos", []), 1):
                                palabras = clf.get("palabras_clave", [])
                                palabras_str = ", ".join(palabras) if palabras else "(sin palabras clave)"
                                tipo_coinc = clf.get("tipo", "contiene_cualquiera")
                                st.write(f"{idx}. **{clf.get('nombre', 'N/A')}**")
                                st.write(f"   Palabras: `{palabras_str}`")
                                st.write(f"   Tipo: `{tipo_coinc}`")
                                if clf.get("excluir"):
                                    excluir_str = ", ".join(clf.get("excluir", []))
                                    st.write(f"   Excluir: `{excluir_str}`")
                                st.write("---")
                        else:
                            st.warning("⚠️ No hay clasificadores de CARGOS configurados")
                else:
                    st.sidebar.error("❌ No se encontraron clasificadores en la base de datos")
                    st.sidebar.warning("⚠️ Todas las transacciones quedarán como 'NO CLASIFICADO'")
                    st.sidebar.info("💡 Configura clasificadores en la aplicación principal de Flujo de Caja")
                
                # Aplicar clasificación
                if config_clasificadores:
                    df_real["CLASIFICACION"] = df_real.apply(
                        lambda row: clasificar_mejorado(
                            str(row.get("DESCRIPCION", "")),
                            float(row.get("ABONOS (CLP)", 0)),
                            config_clasificadores,
                            cargo=float(row.get("CARGOS (CLP)", 0))
                        ),
                        axis=1
                    )
                    
                    # Mostrar estadísticas de clasificación (siempre visible)
                    total_clasificados = len(df_real[df_real["CLASIFICACION"] != "NO CLASIFICADO"])
                    total_no_clasificados = len(df_real[df_real["CLASIFICACION"] == "NO CLASIFICADO"])
                    
                    st.sidebar.markdown("---")
                    st.sidebar.markdown("### 📊 Resultado de Clasificación")
                    st.sidebar.info(f"✅ Clasificados: {total_clasificados}")
                    st.sidebar.warning(f"⚠️ Sin clasificar: {total_no_clasificados}")
                    
                    # Mostrar ejemplos de transacciones no clasificadas con análisis detallado
                    if total_no_clasificados > 0:
                        ejemplos = df_real[df_real["CLASIFICACION"] == "NO CLASIFICADO"].head(5)
                        with st.sidebar.expander("🔍 Ver ejemplos NO CLASIFICADOS", expanded=False):
                            st.write(f"**Mostrando {len(ejemplos)} de {total_no_clasificados} transacciones sin clasificar:**")
                            for idx, (_, row) in enumerate(ejemplos.iterrows(), 1):
                                desc = str(row.get("DESCRIPCION", ""))
                                desc_norm = normalizar(desc)
                                abono = float(row.get("ABONOS (CLP)", 0))
                                cargo = float(row.get("CARGOS (CLP)", 0))
                                tipo_trans = "ABONO" if abono > 0 else "CARGO" if cargo > 0 else "AMBOS/NINGUNO"
                                
                                st.write(f"**{idx}. {tipo_trans}**")
                                st.write(f"   Original: `{desc[:80]}{'...' if len(desc) > 80 else ''}`")
                                st.write(f"   Normalizada: `{desc_norm[:80]}{'...' if len(desc_norm) > 80 else ''}`")
                                st.write(f"   Monto: Abono=${abono:,.0f} | Cargo=${cargo:,.0f}")
                                
                                # Analizar por qué no coincidió con los clasificadores
                                if tipo_trans == "ABONO" and clasif_abonos > 0:
                                    st.write(f"   🔍 **Análisis de clasificadores ABONOS:**")
                                    clasificadores_aplicables = config_clasificadores.get("clasificadores", {}).get("abonos", [])
                                    for clf_idx, clf in enumerate(clasificadores_aplicables, 1):
                                        palabras_clave = clf.get("palabras_clave", [])
                                        palabras_norm = [normalizar(str(p)) for p in palabras_clave if p]
                                        tipo_coinc = clf.get("tipo", "contiene_cualquiera")
                                        
                                        # Evaluar si debería coincidir
                                        if tipo_coinc == "contiene_exacto":
                                            todas_presentes = all(palabra in desc_norm for palabra in palabras_norm)
                                            st.write(f"      {clf_idx}. **{clf.get('nombre', 'N/A')}** ({tipo_coinc})")
                                            for palabra in palabras_norm:
                                                presente = palabra in desc_norm
                                                icono = "✓" if presente else "✗"
                                                st.write(f"         {icono} `{palabra}`")
                                            st.write(f"         Resultado: {'✓ COINCIDIRÍA' if todas_presentes else '✗ No coincide (faltan palabras)'}")
                                        else:  # contiene_cualquiera
                                            alguna_presente = any(palabra in desc_norm for palabra in palabras_norm)
                                            st.write(f"      {clf_idx}. **{clf.get('nombre', 'N/A')}** ({tipo_coinc})")
                                            for palabra in palabras_norm:
                                                presente = palabra in desc_norm
                                                icono = "✓" if presente else "✗"
                                                st.write(f"         {icono} `{palabra}`")
                                            st.write(f"         Resultado: {'✓ COINCIDIRÍA' if alguna_presente else '✗ No coincide (ninguna palabra encontrada)'}")
                                        
                                        # Verificar exclusiones
                                        if clf.get("excluir"):
                                            excluir_norm = [normalizar(str(e)) for e in clf.get("excluir", [])]
                                            for exclusion in excluir_norm:
                                                if exclusion in desc_norm:
                                                    st.write(f"         ⚠️ EXCLUIDO por: `{exclusion}`")
                                        
                                        st.write("")
                                
                                elif tipo_trans == "CARGO" and clasif_cargos > 0:
                                    st.write(f"   🔍 **Análisis de clasificadores CARGOS:**")
                                    clasificadores_aplicables = config_clasificadores.get("clasificadores", {}).get("cargos", [])
                                    for clf_idx, clf in enumerate(clasificadores_aplicables, 1):
                                        palabras_clave = clf.get("palabras_clave", [])
                                        palabras_norm = [normalizar(str(p)) for p in palabras_clave if p]
                                        tipo_coinc = clf.get("tipo", "contiene_cualquiera")
                                        
                                        # Evaluar si debería coincidir
                                        if tipo_coinc == "contiene_exacto":
                                            todas_presentes = all(palabra in desc_norm for palabra in palabras_norm)
                                            st.write(f"      {clf_idx}. **{clf.get('nombre', 'N/A')}** ({tipo_coinc})")
                                            for palabra in palabras_norm:
                                                presente = palabra in desc_norm
                                                icono = "✓" if presente else "✗"
                                                st.write(f"         {icono} `{palabra}`")
                                            st.write(f"         Resultado: {'✓ COINCIDIRÍA' if todas_presentes else '✗ No coincide (faltan palabras)'}")
                                        else:  # contiene_cualquiera
                                            alguna_presente = any(palabra in desc_norm for palabra in palabras_norm)
                                            st.write(f"      {clf_idx}. **{clf.get('nombre', 'N/A')}** ({tipo_coinc})")
                                            for palabra in palabras_norm:
                                                presente = palabra in desc_norm
                                                icono = "✓" if presente else "✗"
                                                st.write(f"         {icono} `{palabra}`")
                                            st.write(f"         Resultado: {'✓ COINCIDIRÍA' if alguna_presente else '✗ No coincide (ninguna palabra encontrada)'}")
                                        
                                        # Verificar exclusiones
                                        if clf.get("excluir"):
                                            excluir_norm = [normalizar(str(e)) for e in clf.get("excluir", [])]
                                            for exclusion in excluir_norm:
                                                if exclusion in desc_norm:
                                                    st.write(f"         ⚠️ EXCLUIDO por: `{exclusion}`")
                                        
                                        st.write("")
                                
                                st.write("---")
                else:
                    df_real["CLASIFICACION"] = "NO CLASIFICADO"
                
                # Eliminar filas sin fecha válida
                df_real = df_real[df_real["FECHA"].notna()].copy()
                
                if df_real.empty:
                    st.error("❌ No se pudieron procesar datos válidos del archivo.")
                    st.stop()
                
            except Exception as e:
                st.error(f"❌ Error al procesar cartola: {e}")
                with st.expander("🔍 Ver detalles del error"):
                    st.code(traceback.format_exc())
                st.stop()
            finally:
                # Limpiar archivo temporal
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
    
    if df_real is None or df_real.empty:
        st.error("❌ No se pudieron cargar los datos. El archivo seleccionado puede estar vacío.")
        st.stop()
    
    # Preparar DataFrame
    df_real = preparar_dataframe_real(df_real)
    
    if df_real is None:
        st.error("❌ Error al preparar los datos reales.")
        st.stop()
    
    # Mostrar resumen de datos cargados (solo información esencial)
    st.sidebar.markdown("---")
    st.sidebar.markdown("### 📊 Resumen de Datos")
    st.sidebar.success(f"✅ {len(df_real)} transacciones cargadas")
    if "ABONOS (CLP)" in df_real.columns:
        total_abonos = df_real["ABONOS (CLP)"].sum()
        st.sidebar.info(f"💰 Total ABONOS: ${total_abonos:,.0f}")
    if "CARGOS (CLP)" in df_real.columns:
        total_cargos = df_real["CARGOS (CLP)"].sum()
        st.sidebar.info(f"💸 Total CARGOS: ${total_cargos:,.0f}")
    if "FECHA" in df_real.columns:
        fecha_min = df_real["FECHA"].min()
        fecha_max = df_real["FECHA"].max()
        st.sidebar.info(f"📅 Rango fechas: {fecha_min.date() if hasattr(fecha_min, 'date') else fecha_min} a {fecha_max.date() if hasattr(fecha_max, 'date') else fecha_max}")
    
    # Opción para guardar cartola nueva en la base de datos
    # Verificar si es una cartola nueva (no cargada desde BD)
    cartola_guardada = st.session_state.get('cartola_guardada_comparativo', False)
    if not cartola_guardada and 'archivo_cartola_nuevo_comparativo' in st.session_state and st.session_state.archivo_cartola_nuevo_comparativo is not None:
        st.sidebar.markdown("---")
        st.sidebar.markdown("### 💾 Guardar Cartola")
        nombre_cartola = st.sidebar.text_input(
            "Nombre para guardar esta cartola",
            value=st.session_state.archivo_cartola_nuevo_comparativo.name if hasattr(st.session_state.archivo_cartola_nuevo_comparativo, 'name') else "cartola_importada.xlsx",
            key="nombre_cartola_guardar_comparativo"
        )
        
        if st.sidebar.button("💾 Guardar Cartola en Base de Datos", use_container_width=True):
            try:
                with st.spinner("💾 Guardando cartola..."):
                    # Registrar archivo
                    archivo_registrado = registrar_archivo(
                        usuario_id=usuario_actual.id,
                        nombre_archivo=nombre_cartola,
                        total_registros=len(df_real)
                    )
                    
                    # Validar antes de guardar que ABONOS y CARGOS no sean iguales
                    if "ABONOS (CLP)" in df_real.columns and "CARGOS (CLP)" in df_real.columns:
                        if df_real["ABONOS (CLP)"].equals(df_real["CARGOS (CLP)"]):
                            st.error("❌ ERROR: No se puede guardar la cartola porque ABONOS y CARGOS tienen los mismos valores.")
                            st.info("💡 Verifica que tu archivo Excel tenga columnas separadas para ABONOS y CARGOS.")
                            st.stop()
                    
                    # Preparar transacciones para guardar
                    transacciones_para_guardar = []
                    for _, row in df_real.iterrows():
                        abono_val = float(row["ABONOS (CLP)"]) if pd.notna(row["ABONOS (CLP)"]) else 0
                        cargo_val = float(row["CARGOS (CLP)"]) if "CARGOS (CLP)" in row and pd.notna(row["CARGOS (CLP)"]) else 0
                        
                        transacciones_para_guardar.append({
                            "fecha": row["FECHA"] if pd.notna(row["FECHA"]) else datetime.now(),
                            "descripcion": str(row.get("DESCRIPCION", "")) if pd.notna(row.get("DESCRIPCION", "")) else "",
                            "abono": abono_val,
                            "cargo": cargo_val,
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
                    
                    st.session_state.cartola_guardada_comparativo = True
                    st.session_state.archivo_cartola_id_comparativo = archivo_registrado.id
                    st.sidebar.success(f"✅ {total_guardadas} transacciones guardadas correctamente")
                    st.rerun()
            except Exception as e:
                st.sidebar.error(f"❌ Error al guardar: {e}")
                with st.sidebar.expander("🔍 Ver detalles del error"):
                    st.code(traceback.format_exc())
    
    # Cargar clasificadores desde BD para re-clasificar si es necesario
    clasificadores_bd = obtener_clasificadores(usuario_actual.id)
    config_clasificadores = None
    if clasificadores_bd:
        config_clasificadores = convertir_clasificadores_bd_a_dict(clasificadores_bd)
        
        # Mostrar información sobre clasificadores
        clasif_abonos = len(config_clasificadores.get("clasificadores", {}).get("abonos", []))
        clasif_cargos = len(config_clasificadores.get("clasificadores", {}).get("cargos", []))
        st.sidebar.markdown("---")
        st.sidebar.markdown("### 🏷️ Clasificadores")
        st.sidebar.write(f"📊 Clasificadores ABONOS: {clasif_abonos}")
        st.sidebar.write(f"📊 Clasificadores CARGOS: {clasif_cargos}")
        
        if clasif_cargos == 0:
            st.sidebar.warning("⚠️ No hay clasificadores de CARGOS configurados. Los egresos quedarán como 'NO CLASIFICADO'.")
        
        # Re-clasificar si es necesario (solo si hay transacciones sin clasificar)
        if "CLASIFICACION" in df_real.columns:
            sin_clasificar = df_real[df_real["CLASIFICACION"].isin(["NO CLASIFICADO", None, ""])]
            if len(sin_clasificar) > 0:
                st.sidebar.info(f"🔄 Re-clasificando {len(sin_clasificar)} transacciones sin clasificar...")
                for idx in sin_clasificar.index:
                    desc = df_real.loc[idx, "DESCRIPCION"]
                    abono = df_real.loc[idx, "ABONOS (CLP)"]
                    cargo = df_real.loc[idx, "CARGOS (CLP)"] if "CARGOS (CLP)" in df_real.columns else 0
                    df_real.loc[idx, "CLASIFICACION"] = clasificar_mejorado(desc, abono, config_clasificadores, cargo=cargo)
    else:
        st.sidebar.markdown("---")
        st.sidebar.markdown("### 🏷️ Clasificadores")
        st.sidebar.warning("⚠️ No hay clasificadores configurados. Todas las transacciones quedarán como 'NO CLASIFICADO'.")
        st.sidebar.info("💡 Configura clasificadores en la aplicación principal para clasificar automáticamente las transacciones.")
    
    st.sidebar.success(f"✅ Datos cargados: {len(df_real)} transacciones")
    
except Exception as e:
    st.error(f"❌ Error al cargar datos desde la base de datos: {e}")
    with st.expander("🔍 Ver detalles del error"):
        st.code(traceback.format_exc())
    st.stop()

# Cargar archivo de proyección
st.sidebar.markdown("---")
st.sidebar.markdown("### 📊 Archivo de Proyección")

# Opción 1: Cargar proyección guardada
try:
    proyecciones_guardadas = obtener_archivos_proyeccion(usuario_actual.id)
    
    if proyecciones_guardadas:
        opciones_proyecciones = {
            f"{proy.nombre_archivo} - {proy.fecha_carga.strftime('%Y-%m-%d')}": proy.id
            for proy in proyecciones_guardadas
        }
        opciones_proyecciones["➕ Cargar nuevo archivo"] = None
        
        proyeccion_seleccionada_nombre = st.sidebar.selectbox(
            "Seleccionar proyección guardada o cargar nueva",
            options=list(opciones_proyecciones.keys()),
            key="proyeccion_seleccionada_comparativo"
        )
        
        proyeccion_id_seleccionado = opciones_proyecciones[proyeccion_seleccionada_nombre]
        
        if proyeccion_id_seleccionado is not None:
            # Cargar desde BD
            archivo_proy_bd = obtener_archivo_proyeccion(proyeccion_id_seleccionado, usuario_actual.id)
            if archivo_proy_bd:
                # Crear BytesIO desde el contenido y asegurar que esté en el inicio
                archivo_proyeccion = io.BytesIO(archivo_proy_bd.contenido)
                archivo_proyeccion.name = archivo_proy_bd.nombre_archivo
                # Marcar que viene de BD para no intentar guardarlo de nuevo
                st.session_state['proyeccion_cargada_desde_bd'] = True
            else:
                st.sidebar.error("❌ No se pudo cargar la proyección seleccionada.")
                st.stop()
        else:
            st.session_state['proyeccion_cargada_desde_bd'] = False
            # Cargar nuevo archivo
            archivo_proyeccion = st.sidebar.file_uploader(
                "Cargar archivo de proyección (Excel)",
                type=['xlsx', 'xls'],
                key="archivo_proyeccion_comparativo"
            )
    else:
        # No hay proyecciones guardadas, solo permitir cargar nuevo
        archivo_proyeccion = st.sidebar.file_uploader(
            "Cargar archivo de proyección (Excel)",
            type=['xlsx', 'xls'],
            key="archivo_proyeccion_comparativo"
        )
        proyeccion_id_seleccionado = None
        
except Exception as e:
    st.sidebar.warning(f"⚠️ Error al cargar proyecciones guardadas: {e}")
    archivo_proyeccion = st.sidebar.file_uploader(
        "Cargar archivo de proyección (Excel)",
        type=['xlsx', 'xls'],
        key="archivo_proyeccion_comparativo"
    )
    proyeccion_id_seleccionado = None

if archivo_proyeccion is None:
    st.warning("⚠️ Por favor, carga un archivo de proyección para continuar.")
    st.info("💡 El archivo debe tener una columna 'CLASIFICACION' y columnas con fechas como encabezados.")
    
    # Opción para analizar estructura de archivo de ejemplo (solo en modo debug)
    if MODO_DEBUG:
        st.markdown("---")
        st.markdown("### 🔍 Analizar Estructura de Archivo (Modo Debug)")
        archivo_analisis = st.file_uploader(
            "Sube un archivo Excel para analizar su estructura",
            type=['xlsx', 'xls'],
            key="archivo_analisis_estructura"
        )
        
        if archivo_analisis is not None:
            with st.spinner("Analizando estructura del archivo..."):
                info = analizar_estructura_excel(archivo_analisis)
                
                if "error" in info:
                    st.error(f"❌ Error al analizar: {info['error']}")
                else:
                    st.success("✅ Archivo analizado correctamente")
                    st.markdown("### 📋 Información de Estructura")
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        st.metric("Filas", info["num_filas"])
                    with col2:
                        st.metric("Columnas", info["num_columnas"])
                    
                    st.markdown("#### 📝 Nombres de Columnas")
                    for i, col in enumerate(info["nombres_columnas"], 1):
                        st.text(f"{i}. '{col}'")
                    
                    st.markdown("#### 📊 Primeras Filas (muestra)")
                    st.dataframe(pd.DataFrame(info["primeras_filas"]).head(10))
                    
                    st.markdown("#### 🔍 Tipos de Datos")
                    tipos_df = pd.DataFrame(list(info["tipos_datos"].items()), columns=["Columna", "Tipo"])
                    st.dataframe(tipos_df)
    st.stop()

try:
    with st.spinner("🔄 Procesando archivo de proyección..."):
        df_proj = cargar_proyeccion_desde_archivo(archivo_proyeccion)
    
    if df_proj is None:
        st.error("❌ No se pudo cargar el archivo de proyección. Verifica el formato.")
        st.info("💡 Revisa los mensajes de error arriba para más detalles.")
        st.stop()
    
    if df_proj.empty:
        st.error("❌ El archivo de proyección está vacío o no contiene datos válidos.")
        st.info("💡 Verifica que el archivo tenga datos en las celdas correspondientes.")
        st.stop()
    
    st.sidebar.success(f"✅ Proyección cargada: {len(df_proj)} registros")
    
    # Botón para guardar proyección (solo si es un archivo nuevo, no uno guardado)
    proyeccion_desde_bd = st.session_state.get('proyeccion_cargada_desde_bd', False)
    if not proyeccion_desde_bd and proyeccion_id_seleccionado is None and hasattr(archivo_proyeccion, 'read'):
        st.sidebar.markdown("---")
        nombre_proyeccion = st.sidebar.text_input(
            "Nombre para guardar esta proyección",
            value=archivo_proyeccion.name if hasattr(archivo_proyeccion, 'name') else "proyeccion.xlsx",
            key="nombre_proyeccion_guardar"
        )
        descripcion_proyeccion = st.sidebar.text_area(
            "Descripción (opcional)",
            key="descripcion_proyeccion_guardar",
            height=68
        )
        
        if st.sidebar.button("💾 Guardar Proyección", use_container_width=True):
            try:
                # Leer el contenido del archivo
                if hasattr(archivo_proyeccion, 'seek'):
                    archivo_proyeccion.seek(0)  # Volver al inicio del archivo
                contenido_bytes = archivo_proyeccion.read()
                
                # Guardar en BD
                archivo_guardado = guardar_archivo_proyeccion(
                    usuario_id=usuario_actual.id,
                    nombre_archivo=nombre_proyeccion,
                    contenido=contenido_bytes,
                    descripcion=descripcion_proyeccion if descripcion_proyeccion else None
                )
                
                st.sidebar.success(f"✅ Proyección guardada: {archivo_guardado.nombre_archivo}")
                st.rerun()  # Recargar para mostrar la nueva proyección en el selector
            except Exception as e:
                st.sidebar.error(f"❌ Error al guardar proyección: {e}")
                with st.sidebar.expander("🔍 Ver detalles del error"):
                    st.code(traceback.format_exc())
    
except Exception as e:
    st.error(f"❌ Error al procesar archivo de proyección: {e}")
    with st.expander("🔍 Ver detalles del error"):
        st.code(traceback.format_exc())
    st.stop()

# ----------------- VALIDACIONES FINALES -----------------
# Verificar que tenemos datos válidos antes de continuar
if df_real is None or df_real.empty:
    st.error("❌ No hay datos reales disponibles.")
    st.stop()

if df_proj is None or df_proj.empty:
    st.error("❌ No hay datos de proyección disponibles.")
    st.stop()

# Verificar que hay fechas válidas
if df_real["FECHA"].isna().all():
    st.error("❌ No se encontraron fechas válidas en los datos reales.")
    st.stop()

# ==================== PRIMERO: PREPARAR COMPARACIÓN ====================
# Mover la preparación del merge ANTES de mostrar datos individuales
# para que las comparaciones sean lo primero que se vea

# ----------------- RESUMEN REAL -----------------
try:
    # Verificar que existen las columnas necesarias
    columnas_requeridas = ["CLASIFICACION", "MES", "CARGOS (CLP)", "ABONOS (CLP)"]
    columnas_faltantes = [col for col in columnas_requeridas if col not in df_real.columns]
    
    if columnas_faltantes:
        st.error(f"❌ Faltan columnas requeridas en los datos reales: {', '.join(columnas_faltantes)}")
        st.stop()
    
    # Normalizar clasificaciones en df_real antes de agrupar
    if "CLASIFICACION" in df_real.columns:
        df_real["CLASIFICACION_NORM"] = df_real["CLASIFICACION"].astype(str).apply(normalizar)
    else:
        st.error("❌ No se encontró la columna CLASIFICACION en los datos reales.")
        st.stop()
    
    # Validación crítica: Verificar que ABONOS y CARGOS no sean la misma columna
    if "ABONOS (CLP)" in df_real.columns and "CARGOS (CLP)" in df_real.columns:
        total_abonos_raw = df_real["ABONOS (CLP)"].sum()
        total_cargos_raw = df_real["CARGOS (CLP)"].sum()
        filas_con_abonos = len(df_real[df_real["ABONOS (CLP)"] > 0])
        filas_con_cargos = len(df_real[df_real["CARGOS (CLP)"] > 0])
        
        # Mostrar diagnóstico en sidebar
        st.sidebar.markdown("---")
        st.sidebar.markdown("### 🔍 Diagnóstico de Datos")
        st.sidebar.write(f"💰 Total ABONOS: ${total_abonos_raw:,.0f}")
        st.sidebar.write(f"💸 Total CARGOS: ${total_cargos_raw:,.0f}")
        st.sidebar.write(f"📊 Filas con ABONOS > 0: {filas_con_abonos}")
        st.sidebar.write(f"📊 Filas con CARGOS > 0: {filas_con_cargos}")
        
        debug_info(f"🔍 Validación: Total ABONOS raw: ${total_abonos_raw:,.0f}, Total CARGOS raw: ${total_cargos_raw:,.0f}")
        
        # Verificar si ambas columnas tienen exactamente los mismos valores
        if df_real["ABONOS (CLP)"].equals(df_real["CARGOS (CLP)"]):
            st.error("❌ ERROR CRÍTICO: Las columnas ABONOS y CARGOS tienen los mismos valores.")
            st.warning("⚠️ **PROBLEMA:** Los datos en la base de datos están incorrectos.")
            st.info("💡 **CAUSA:** El archivo Excel original tenía una sola columna de montos o las columnas fueron mal detectadas.")
            st.info("📋 **SOLUCIÓN:**")
            st.info("   1. Verifica que tu archivo Excel tenga columnas SEPARADAS para ABONOS y CARGOS")
            st.info("   2. Vuelve a cargar la cartola desde el archivo Excel corregido")
            st.info("   3. Elimina la cartola incorrecta de la base de datos y guárdala nuevamente")
            with st.expander("🔍 Ver datos cargados"):
                st.write("Primeras 10 filas:")
                st.dataframe(df_real[["FECHA", "DESCRIPCION", "ABONOS (CLP)", "CARGOS (CLP)", "CLASIFICACION"]].head(10))
                st.write(f"Total ABONOS: ${total_abonos_raw:,.0f}")
                st.write(f"Total CARGOS: ${total_cargos_raw:,.0f}")
                st.write(f"Filas con ABONOS > 0: {filas_con_abonos}")
                st.write(f"Filas con CARGOS > 0: {filas_con_cargos}")
            st.stop()
        
        # Advertencia si los totales son iguales (muy sospechoso)
        if abs(total_abonos_raw - total_cargos_raw) < 1 and total_abonos_raw > 0:
            st.error("❌ ERROR: Los totales de ABONOS y CARGOS son iguales. Esto NO es posible.")
            st.warning("⚠️ **PROBLEMA:** Los datos están incorrectos. Los ingresos y egresos no pueden ser iguales.")
            st.info("💡 **CAUSA PROBABLE:** El archivo Excel tiene una sola columna de montos o las columnas están mal detectadas.")
            st.info("📋 **SOLUCIÓN:**")
            st.info("   1. Verifica que tu archivo Excel tenga columnas SEPARADAS:")
            st.info("      - Una columna para ABONOS (ingresos): 'ABONOS', 'DEPOSITOS', 'CREDITOS'")
            st.info("      - Una columna para CARGOS (egresos): 'CARGOS', 'DEBITOS', 'EGRESOS'")
            st.info("   2. Si tu archivo tiene una sola columna, sepárala manualmente en Excel")
            st.info("   3. Vuelve a cargar la cartola desde el archivo corregido")
            with st.expander("🔍 Ver detalles del problema"):
                st.write(f"Total ABONOS: ${total_abonos_raw:,.0f}")
                st.write(f"Total CARGOS: ${total_cargos_raw:,.0f}")
                st.write(f"Filas con ABONOS > 0: {filas_con_abonos}")
                st.write(f"Filas con CARGOS > 0: {filas_con_cargos}")
                st.write("Muestra de datos originales (primeras 10 filas):")
                st.dataframe(df_real[["FECHA", "DESCRIPCION", "ABONOS (CLP)", "CARGOS (CLP)", "CLASIFICACION"]].head(10))
            st.stop()
    
    # Separar datos reales en INGRESOS (ABONOS) y EGRESOS (CARGOS)
    # Filtrar solo filas con ABONOS > 0 para ingresos
    df_real_con_abonos = df_real[df_real["ABONOS (CLP)"] > 0].copy()
    df_resumen_real_ingresos = df_real_con_abonos.groupby(["CLASIFICACION_NORM", "MES"])["ABONOS (CLP)"].sum().reset_index()
    df_resumen_real_ingresos.rename(columns={"CLASIFICACION_NORM": "CLASIFICACION", "ABONOS (CLP)": "REAL_INGRESOS"}, inplace=True)
    
    # Filtrar solo filas con CARGOS > 0 para egresos
    df_real_con_cargos = df_real[df_real["CARGOS (CLP)"] > 0].copy()
    df_resumen_real_egresos = df_real_con_cargos.groupby(["CLASIFICACION_NORM", "MES"])["CARGOS (CLP)"].sum().reset_index()
    df_resumen_real_egresos.rename(columns={"CLASIFICACION_NORM": "CLASIFICACION", "CARGOS (CLP)": "REAL_EGRESOS"}, inplace=True)
    
    # Debug: Verificar resúmenes
    debug_info(f"💰 Registros ingresos reales: {len(df_resumen_real_ingresos)}")
    if len(df_resumen_real_ingresos) > 0:
        total_real_ingresos = df_resumen_real_ingresos['REAL_INGRESOS'].sum()
        debug_info(f"💰 Total REAL_INGRESOS: ${total_real_ingresos:,.0f}")
    debug_info(f"💸 Registros egresos reales: {len(df_resumen_real_egresos)}")
    if len(df_resumen_real_egresos) > 0:
        total_real_egresos = df_resumen_real_egresos['REAL_EGRESOS'].sum()
        debug_info(f"💸 Total REAL_EGRESOS: ${total_real_egresos:,.0f}")
        
        # Validación CRÍTICA: Los ingresos y egresos NO deben ser iguales
        if len(df_resumen_real_ingresos) > 0 and abs(total_real_ingresos - total_real_egresos) < 1:
            st.error("❌ ERROR CRÍTICO: Los totales de ingresos y egresos reales son iguales. Esto NO es posible.")
            st.warning("⚠️ **PROBLEMA:** Los datos en la base de datos están incorrectos.")
            st.info("💡 **CAUSA:** El archivo Excel original tenía una sola columna de montos o las columnas fueron mal detectadas.")
            st.info("📋 **SOLUCIÓN:**")
            st.info("   1. Verifica que tu archivo Excel tenga columnas SEPARADAS:")
            st.info("      - Una columna para ABONOS (ingresos): 'ABONOS', 'DEPOSITOS', 'CREDITOS'")
            st.info("      - Una columna para CARGOS (egresos): 'CARGOS', 'DEBITOS', 'EGRESOS'")
            st.info("   2. Si tu archivo tiene una sola columna de montos, sepárala manualmente en Excel")
            st.info("   3. Vuelve a cargar la cartola desde el archivo corregido")
            st.info("   4. Elimina la cartola incorrecta de la base de datos y guárdala nuevamente")
            with st.expander("🔍 Ver detalles del problema"):
                st.write(f"Total REAL_INGRESOS: ${total_real_ingresos:,.0f}")
                st.write(f"Total REAL_EGRESOS: ${total_real_egresos:,.0f}")
                st.write(f"Filas con ABONOS > 0: {len(df_real_con_abonos)}")
                st.write(f"Filas con CARGOS > 0: {len(df_real_con_cargos)}")
                st.write("Muestra de datos con ABONOS:")
                if len(df_real_con_abonos) > 0:
                    st.dataframe(df_real_con_abonos[["FECHA", "DESCRIPCION", "ABONOS (CLP)", "CLASIFICACION"]].head(5))
                else:
                    st.write("No hay datos con ABONOS > 0")
                st.write("Muestra de datos con CARGOS:")
                if len(df_real_con_cargos) > 0:
                    st.dataframe(df_real_con_cargos[["FECHA", "DESCRIPCION", "CARGOS (CLP)", "CLASIFICACION"]].head(5))
                else:
                    st.write("No hay datos con CARGOS > 0")
                st.write("Muestra de datos originales (primeras 10 filas):")
                st.dataframe(df_real[["FECHA", "DESCRIPCION", "ABONOS (CLP)", "CARGOS (CLP)", "CLASIFICACION"]].head(10))
            st.stop()
    
    # Asegurar que las clasificaciones en df_proj también estén normalizadas
    if "CLASIFICACION" in df_proj.columns:
        df_proj["CLASIFICACION"] = df_proj["CLASIFICACION"].astype(str).apply(normalizar)
    
    # Identificar tipo (INGRESO/EGRESO) de cada clasificación en la proyección
    # Si ya viene con TIPO del archivo (detectado automáticamente), usarlo
    # Si no, intentar identificarlo usando clasificadores o inferencia
    if "TIPO" not in df_proj.columns or df_proj["TIPO"].isna().all():
        if config_clasificadores:
            df_proj["TIPO"] = df_proj["CLASIFICACION"].apply(
                lambda x: identificar_tipo_clasificacion(x, config_clasificadores)
            )
        else:
            # Si no hay clasificadores, intentar inferir por el nombre
            df_proj["TIPO"] = df_proj["CLASIFICACION"].apply(
                lambda x: "INGRESO" if any(palabra in x.lower() for palabra in ["cobrar", "factura", "ingreso", "venta"]) 
                else ("EGRESO" if any(palabra in x.lower() for palabra in ["proveedor", "pago", "gasto", "egreso", "cargo"]) 
                else None)
            )
    else:
        # Si ya tiene TIPO, verificar que esté completo
        if df_proj["TIPO"].isna().any():
            # Completar los que faltan usando clasificadores
            mask_sin_tipo = df_proj["TIPO"].isna()
            if config_clasificadores:
                df_proj.loc[mask_sin_tipo, "TIPO"] = df_proj.loc[mask_sin_tipo, "CLASIFICACION"].apply(
                    lambda x: identificar_tipo_clasificacion(x, config_clasificadores)
                )
    
    # Separar proyección en ingresos y egresos
    df_proj_ingresos = df_proj[df_proj["TIPO"] == "INGRESO"].copy()
    df_proj_egresos = df_proj[df_proj["TIPO"] == "EGRESO"].copy()
    
    # Si hay clasificaciones sin tipo identificado, mostrar advertencia solo en modo debug
    sin_tipo = df_proj[df_proj["TIPO"].isna()]
    if len(sin_tipo) > 0:
        if MODO_DEBUG:
            debug_warning(f"⚠️ {len(sin_tipo)} clasificaciones en proyección sin tipo identificado (INGRESO/EGRESO)")
            debug_info("💡 Estas clasificaciones no se incluirán en la comparación. Verifica tus clasificadores.")
            # Mostrar las clasificaciones sin tipo para debug
            with debug_expander("🔍 Ver clasificaciones sin tipo"):
                st.write(sorted(sin_tipo["CLASIFICACION"].unique()))
    
    # Mostrar información de debug
    if MODO_DEBUG:
        st.sidebar.markdown("---")
        st.sidebar.markdown("### 🔍 Información de Datos")
        debug_info(f"📊 Clasificaciones en Real: {df_resumen_real_ingresos['CLASIFICACION'].nunique()}")
        debug_info(f"📊 Clasificaciones en Proyección: {df_proj['CLASIFICACION'].nunique()}")
        debug_info(f"💰 Ingresos proyectados: {len(df_proj_ingresos)} registros")
        if len(df_proj_ingresos) > 0:
            debug_info(f"💰 Total MONTO ingresos: ${df_proj_ingresos['MONTO'].sum():,.0f}")
        debug_info(f"💸 Egresos proyectados: {len(df_proj_egresos)} registros")
        if len(df_proj_egresos) > 0:
            debug_info(f"💸 Total MONTO egresos: ${df_proj_egresos['MONTO'].sum():,.0f}")
    
    # Debug: Verificar clasificaciones antes del merge
    clasif_proj_ing = set(df_proj_ingresos["CLASIFICACION"].unique()) if len(df_proj_ingresos) > 0 else set()
    clasif_real_ing = set(df_resumen_real_ingresos["CLASIFICACION"].unique()) if len(df_resumen_real_ingresos) > 0 else set()
    coincidencias_clasif_ing = clasif_proj_ing & clasif_real_ing
    debug_info(f"🔍 Clasificaciones proyección ingresos: {len(clasif_proj_ing)}")
    debug_info(f"🔍 Clasificaciones reales ingresos: {len(clasif_real_ing)}")
    debug_info(f"🔍 Coincidencias clasificaciones ingresos: {len(coincidencias_clasif_ing)}")
    
    if len(coincidencias_clasif_ing) == 0 and len(clasif_proj_ing) > 0 and len(clasif_real_ing) > 0:
        debug_warning("⚠️ No hay coincidencias de clasificaciones en ingresos")
        if MODO_DEBUG:
            with debug_expander("🔍 Ver clasificaciones proyección ingresos"):
                st.write(sorted(list(clasif_proj_ing))[:10])
            with debug_expander("🔍 Ver clasificaciones reales ingresos"):
                st.write(sorted(list(clasif_real_ing))[:10])
    
    # ----------------- UNIFICACIÓN - INGRESOS -----------------
    # Usar outer join para mantener todos los registros (tanto proyectados como reales)
    df_merge_ingresos = pd.merge(
        df_proj_ingresos[["CLASIFICACION", "MES", "MONTO"]], 
        df_resumen_real_ingresos, 
        how="outer",  # Outer para mantener todos los registros
        on=["CLASIFICACION", "MES"]
    ).copy()
    df_merge_ingresos["REAL_INGRESOS"] = df_merge_ingresos["REAL_INGRESOS"].fillna(0)
    df_merge_ingresos["MONTO"] = df_merge_ingresos["MONTO"].fillna(0)
    df_merge_ingresos["DIFERENCIA"] = df_merge_ingresos["REAL_INGRESOS"] - df_merge_ingresos["MONTO"]
    df_merge_ingresos["TIPO"] = "INGRESO"
    
    # Debug: Verificar merge de ingresos
    debug_info(f"🔗 Merge ingresos: {len(df_merge_ingresos)} registros")
    if len(df_merge_ingresos) > 0:
        debug_info(f"🔗 Total MONTO merge: ${df_merge_ingresos['MONTO'].sum():,.0f}")
        debug_info(f"🔗 Total REAL_INGRESOS merge: ${df_merge_ingresos['REAL_INGRESOS'].sum():,.0f}")
        # Mostrar meses disponibles en el merge
        if "MES" in df_merge_ingresos.columns:
            # Asegurar que MES esté normalizado
            if not pd.api.types.is_datetime64_any_dtype(df_merge_ingresos["MES"]):
                df_merge_ingresos["MES"] = pd.to_datetime(df_merge_ingresos["MES"])
            df_merge_ingresos["MES"] = pd.to_datetime(df_merge_ingresos["MES"]).dt.to_period("M").dt.to_timestamp()
            meses_ingresos = sorted(df_merge_ingresos["MES"].dt.to_period("M").unique().astype(str).tolist())
            debug_info(f"📅 Meses ingresos en merge: {meses_ingresos}")
        
        # Debug: verificar cuántos registros tienen MONTO > 0
        registros_con_monto = len(df_merge_ingresos[df_merge_ingresos["MONTO"] > 0])
        debug_info(f"💰 Registros con MONTO > 0: {registros_con_monto} de {len(df_merge_ingresos)}")
    
    # Debug: Verificar que MONTO no sea cero
    if len(df_merge_ingresos) > 0 and df_merge_ingresos["MONTO"].sum() == 0:
        debug_warning("⚠️ PROBLEMA: Los ingresos proyectados suman 0")
        if MODO_DEBUG:
            with debug_expander("🔍 Debug ingresos"):
                st.write("df_proj_ingresos:")
                st.write(df_proj_ingresos.head(10))
                st.write("df_merge_ingresos:")
                st.write(df_merge_ingresos.head(10))
    
    # Debug: Verificar clasificaciones antes del merge
    clasif_proj_eg = set(df_proj_egresos["CLASIFICACION"].unique()) if len(df_proj_egresos) > 0 else set()
    clasif_real_eg = set(df_resumen_real_egresos["CLASIFICACION"].unique()) if len(df_resumen_real_egresos) > 0 else set()
    coincidencias_clasif_eg = clasif_proj_eg & clasif_real_eg
    debug_info(f"🔍 Clasificaciones proyección egresos: {len(clasif_proj_eg)}")
    debug_info(f"🔍 Clasificaciones reales egresos: {len(clasif_real_eg)}")
    debug_info(f"🔍 Coincidencias clasificaciones egresos: {len(coincidencias_clasif_eg)}")
    
    if len(coincidencias_clasif_eg) == 0 and len(clasif_proj_eg) > 0 and len(clasif_real_eg) > 0:
        debug_warning("⚠️ No hay coincidencias de clasificaciones en egresos")
        if MODO_DEBUG:
            with debug_expander("🔍 Ver clasificaciones proyección egresos"):
                st.write(sorted(list(clasif_proj_eg))[:10])
            with debug_expander("🔍 Ver clasificaciones reales egresos"):
                st.write(sorted(list(clasif_real_eg))[:10])
    
    # ----------------- UNIFICACIÓN - EGRESOS -----------------
    # Asegurar que MES esté normalizado en ambos dataframes antes del merge
    if "MES" in df_proj_egresos.columns:
        if not pd.api.types.is_datetime64_any_dtype(df_proj_egresos["MES"]):
            df_proj_egresos["MES"] = pd.to_datetime(df_proj_egresos["MES"])
        df_proj_egresos["MES"] = pd.to_datetime(df_proj_egresos["MES"]).dt.to_period("M").dt.to_timestamp()
    
    if "MES" in df_resumen_real_egresos.columns:
        if not pd.api.types.is_datetime64_any_dtype(df_resumen_real_egresos["MES"]):
            df_resumen_real_egresos["MES"] = pd.to_datetime(df_resumen_real_egresos["MES"])
        df_resumen_real_egresos["MES"] = pd.to_datetime(df_resumen_real_egresos["MES"]).dt.to_period("M").dt.to_timestamp()
    
    # Debug: mostrar meses antes del merge
    if len(df_proj_egresos) > 0 and "MES" in df_proj_egresos.columns:
        meses_proj_eg = sorted(df_proj_egresos["MES"].dt.to_period("M").unique().astype(str).tolist())
        debug_info(f"📅 Meses PROYECCIÓN egresos antes merge: {meses_proj_eg[:10]}")
    if len(df_resumen_real_egresos) > 0 and "MES" in df_resumen_real_egresos.columns:
        meses_real_eg = sorted(df_resumen_real_egresos["MES"].dt.to_period("M").unique().astype(str).tolist())
        debug_info(f"📅 Meses REAL egresos antes merge: {meses_real_eg[:10]}")
    
    # Usar outer join para mantener todos los registros (tanto proyectados como reales)
    df_merge_egresos = pd.merge(
        df_proj_egresos[["CLASIFICACION", "MES", "MONTO"]], 
        df_resumen_real_egresos, 
        how="outer",  # Outer para mantener todos los registros
        on=["CLASIFICACION", "MES"]
    ).copy()
    df_merge_egresos["REAL_EGRESOS"] = df_merge_egresos["REAL_EGRESOS"].fillna(0)
    df_merge_egresos["MONTO"] = df_merge_egresos["MONTO"].fillna(0)
    df_merge_egresos["DIFERENCIA"] = df_merge_egresos["REAL_EGRESOS"] - df_merge_egresos["MONTO"]
    df_merge_egresos["TIPO"] = "EGRESO"
    
    # Debug: Verificar merge de egresos
    debug_info(f"🔗 Merge egresos: {len(df_merge_egresos)} registros")
    if len(df_merge_egresos) > 0:
        debug_info(f"🔗 Total MONTO merge: ${df_merge_egresos['MONTO'].sum():,.0f}")
        debug_info(f"🔗 Total REAL_EGRESOS merge: ${df_merge_egresos['REAL_EGRESOS'].sum():,.0f}")
        # Mostrar meses disponibles en el merge
        if "MES" in df_merge_egresos.columns:
            # Asegurar que MES esté normalizado
            if not pd.api.types.is_datetime64_any_dtype(df_merge_egresos["MES"]):
                df_merge_egresos["MES"] = pd.to_datetime(df_merge_egresos["MES"])
            df_merge_egresos["MES"] = pd.to_datetime(df_merge_egresos["MES"]).dt.to_period("M").dt.to_timestamp()
            meses_egresos = sorted(df_merge_egresos["MES"].dt.to_period("M").unique().astype(str).tolist())
            debug_info(f"📅 Meses egresos en merge: {meses_egresos}")
        
        # Debug: verificar cuántos registros tienen MONTO > 0
        registros_con_monto = len(df_merge_egresos[df_merge_egresos["MONTO"] > 0])
        debug_info(f"💰 Registros con MONTO > 0: {registros_con_monto} de {len(df_merge_egresos)}")
    
    # Debug: Verificar que MONTO no sea cero
    if len(df_merge_egresos) > 0 and df_merge_egresos["MONTO"].sum() == 0:
        debug_warning("⚠️ PROBLEMA: Los egresos proyectados suman 0")
        if MODO_DEBUG:
            with debug_expander("🔍 Debug egresos"):
                st.write("df_proj_egresos:")
                st.write(df_proj_egresos.head(10))
                st.write("df_merge_egresos:")
                st.write(df_merge_egresos.head(10))
    
    # Combinar ambos para tener un df_merge completo (para compatibilidad con código existente)
    df_merge = pd.concat([df_merge_ingresos, df_merge_egresos], ignore_index=True)
    
    if df_merge.empty:
        st.warning("⚠️ No hay coincidencias entre los datos reales y la proyección.")
        st.info("💡 Verifica que las clasificaciones coincidan entre ambos archivos.")
        
        # Mostrar clasificaciones disponibles para debug
        with st.expander("🔍 Ver clasificaciones disponibles"):
            col1, col2 = st.columns(2)
            with col1:
                st.write("**Clasificaciones en Real:**")
                st.write(sorted(df_resumen_real_ingresos["CLASIFICACION"].unique()))
            with col2:
                st.write("**Clasificaciones en Proyección:**")
                st.write(sorted(df_proj["CLASIFICACION"].unique()))
        st.stop()
    
    # Mostrar estadísticas del merge
    coincidencias_ingresos = len(df_merge_ingresos[(df_merge_ingresos["REAL_INGRESOS"] > 0) & (df_merge_ingresos["MONTO"] > 0)])
    coincidencias_egresos = len(df_merge_egresos[(df_merge_egresos["REAL_EGRESOS"] > 0) & (df_merge_egresos["MONTO"] > 0)])
    debug_info(f"✅ Coincidencias Ingresos: {coincidencias_ingresos}, Egresos: {coincidencias_egresos}")
        
except Exception as e:
    st.error(f"❌ Error al procesar resumen y unificación: {e}")
    with st.expander("🔍 Ver detalles del error"):
        st.code(traceback.format_exc())
    st.stop()

# ----------------- FILTROS -----------------
st.markdown("---")
st.markdown("## 🔍 Filtros de Análisis")
st.markdown("### Selecciona el rango de fechas y clasificaciones a analizar")

col_filtro1, col_filtro2 = st.columns(2)

try:
    # Obtener fechas mínimas y máximas de los datos reales (más preciso que MES)
    if "FECHA" in df_real.columns and not df_real["FECHA"].isna().all():
        fecha_min_real = df_real["FECHA"].min()
        fecha_max_real = df_real["FECHA"].max()
    else:
        # Fallback a MES si no hay FECHA
        fecha_min_real = df_merge["MES"].min() if "MES" in df_merge.columns else None
        fecha_max_real = df_merge["MES"].max() if "MES" in df_merge.columns else None
    
    # Obtener fechas de la proyección
    if "FECHA" in df_proj.columns and not df_proj["FECHA"].isna().all():
        fecha_min_proj = df_proj["FECHA"].min()
        fecha_max_proj = df_proj["FECHA"].max()
    else:
        fecha_min_proj = df_merge["MES"].min() if "MES" in df_merge.columns else None
        fecha_max_proj = df_merge["MES"].max() if "MES" in df_merge.columns else None
    
    # Determinar rango global
    if fecha_min_real is not None and fecha_min_proj is not None:
        fecha_min_global = min(fecha_min_real, fecha_min_proj)
        fecha_max_global = max(fecha_max_real, fecha_max_proj)
    elif fecha_min_real is not None:
        fecha_min_global = fecha_min_real
        fecha_max_global = fecha_max_real
    elif fecha_min_proj is not None:
        fecha_min_global = fecha_min_proj
        fecha_max_global = fecha_max_proj
    else:
        fecha_min_global = None
        fecha_max_global = None
    
    with col_filtro1:
        if fecha_min_global is not None and fecha_max_global is not None:
            # Convertir a date si es datetime
            if hasattr(fecha_min_global, 'date'):
                fecha_min_date = fecha_min_global.date()
            elif isinstance(fecha_min_global, pd.Timestamp):
                fecha_min_date = fecha_min_global.date()
            else:
                fecha_min_date = fecha_min_global
            
            if hasattr(fecha_max_global, 'date'):
                fecha_max_date = fecha_max_global.date()
            elif isinstance(fecha_max_global, pd.Timestamp):
                fecha_max_date = fecha_max_global.date()
            else:
                fecha_max_date = fecha_max_global
            
            fechas_seleccionadas = st.date_input(
                "📅 Rango de Fechas",
                value=[fecha_min_date, fecha_max_date],
                min_value=fecha_min_date,
                max_value=fecha_max_date,
                key="filtro_fechas_comparativo"
            )
            
            # st.date_input devuelve una tupla cuando value es una lista
            if isinstance(fechas_seleccionadas, (list, tuple)) and len(fechas_seleccionadas) == 2:
                fecha_inicio, fecha_fin = fechas_seleccionadas[0], fechas_seleccionadas[1]
            else:
                fecha_inicio, fecha_fin = None, None
        else:
            st.error("❌ No se pudieron determinar las fechas para el filtro.")
            fecha_inicio, fecha_fin = None, None
    
    with col_filtro2:
        clasificaciones = sorted(df_merge["CLASIFICACION"].unique()) if "CLASIFICACION" in df_merge.columns else []
        if not clasificaciones:
            st.warning("⚠️ No hay clasificaciones disponibles.")
            seleccionadas = []
        else:
            seleccionadas = st.multiselect(
                "🏷️ Clasificaciones",
                clasificaciones,
                default=clasificaciones,
                key="filtro_clasificaciones_comparativo"
            )

except Exception as e:
    st.error(f"❌ Error en filtros: {e}")
    with st.expander("🔍 Ver detalles del error"):
        st.code(traceback.format_exc())
    seleccionadas = []
    fecha_inicio, fecha_fin = None, None

# Aplicar filtros
try:
    # Aplicar filtros a ingresos y egresos por separado
    df_vista_ingresos = df_merge_ingresos.copy()
    df_vista_egresos = df_merge_egresos.copy()
    
    # Debug: mostrar meses disponibles ANTES del filtro
    if "MES" in df_vista_ingresos.columns and len(df_vista_ingresos) > 0:
        # Asegurar que MES esté normalizado
        if not pd.api.types.is_datetime64_any_dtype(df_vista_ingresos["MES"]):
            df_vista_ingresos["MES"] = pd.to_datetime(df_vista_ingresos["MES"])
        df_vista_ingresos["MES"] = pd.to_datetime(df_vista_ingresos["MES"]).dt.to_period("M").dt.to_timestamp()
        meses_antes_ing = sorted(df_vista_ingresos["MES"].dt.to_period("M").unique().astype(str).tolist())
        debug_info(f"📅 Meses ingresos ANTES filtro: {meses_antes_ing}")
        debug_info(f"💰 Total MONTO ingresos ANTES filtro: ${df_vista_ingresos['MONTO'].sum():,.0f}")
    if "MES" in df_vista_egresos.columns and len(df_vista_egresos) > 0:
        # Asegurar que MES esté normalizado
        if not pd.api.types.is_datetime64_any_dtype(df_vista_egresos["MES"]):
            df_vista_egresos["MES"] = pd.to_datetime(df_vista_egresos["MES"])
        df_vista_egresos["MES"] = pd.to_datetime(df_vista_egresos["MES"]).dt.to_period("M").dt.to_timestamp()
        meses_antes_eg = sorted(df_vista_egresos["MES"].dt.to_period("M").unique().astype(str).tolist())
        debug_info(f"📅 Meses egresos ANTES filtro: {meses_antes_eg}")
        debug_info(f"💰 Total MONTO egresos ANTES filtro: ${df_vista_egresos['MONTO'].sum():,.0f}")
    
    # Filtrar por fechas (usar MES para la comparación, que es lo que se agrupa)
    if fecha_inicio and fecha_fin:
        fecha_inicio_val = pd.to_datetime(fecha_inicio)
        fecha_fin_val = pd.to_datetime(fecha_fin)
        
        # Debug: mostrar fechas seleccionadas por el usuario
        debug_info(f"🔍 Fechas seleccionadas: {fecha_inicio_val.strftime('%Y-%m-%d')} a {fecha_fin_val.strftime('%Y-%m-%d')}")
        
        # Normalizar fechas de filtro al primer día del mes para comparar con MES
        fecha_inicio_mes = pd.Timestamp(year=fecha_inicio_val.year, month=fecha_inicio_val.month, day=1)
        # Para fecha_fin, necesitamos incluir todo el mes, así que usamos el último día del mes
        # Pero como MES es el primer día del mes, comparamos con el primer día del mes siguiente menos 1 día
        # O mejor: comparamos con el primer día del mes de fecha_fin (inclusive)
        fecha_fin_mes = pd.Timestamp(year=fecha_fin_val.year, month=fecha_fin_val.month, day=1)
        
        debug_info(f"🔍 Filtro normalizado: desde {fecha_inicio_mes.strftime('%Y-%m-%d')} hasta {fecha_fin_mes.strftime('%Y-%m-%d')}")
        
        # Filtrar por MES (la comparación se hace por mes)
        # MES es el primer día del mes, así que comparamos si está dentro del rango de meses
        if "MES" in df_vista_ingresos.columns:
            # Asegurar que MES esté normalizado al primer día del mes
            if not pd.api.types.is_datetime64_any_dtype(df_vista_ingresos["MES"]):
                df_vista_ingresos["MES"] = pd.to_datetime(df_vista_ingresos["MES"])
            
            # Normalizar MES al primer día del mes para comparar
            df_vista_ingresos["MES"] = pd.to_datetime(df_vista_ingresos["MES"]).dt.to_period("M").dt.to_timestamp()
            
            # Filtrar: MES debe estar entre fecha_inicio_mes y fecha_fin_mes (inclusive)
            # Debug: mostrar algunos valores de MES antes del filtro para comparar
            if len(df_vista_ingresos) > 0:
                muestra_mes_antes = df_vista_ingresos["MES"].head(5).tolist()
                debug_info(f"🔍 Muestra MES antes filtro: {[str(m) for m in muestra_mes_antes]}")
            
            mask = (df_vista_ingresos["MES"] >= fecha_inicio_mes) & (df_vista_ingresos["MES"] <= fecha_fin_mes)
            df_vista_ingresos = df_vista_ingresos[mask].copy()
            
            # Debug: mostrar información del filtro
            debug_info(f"🔍 Filtro ingresos: {fecha_inicio_mes.strftime('%Y-%m-%d')} <= MES <= {fecha_fin_mes.strftime('%Y-%m-%d')}")
            debug_info(f"📊 Registros ingresos después de filtro: {len(df_vista_ingresos)}")
            if len(df_vista_ingresos) > 0:
                meses_encontrados = sorted(df_vista_ingresos['MES'].dt.to_period('M').unique().astype(str).tolist())
                debug_info(f"📅 MES ingresos encontrados: {meses_encontrados}")
                debug_info(f"💰 Total MONTO ingresos filtrado: ${df_vista_ingresos['MONTO'].sum():,.0f}")
            else:
                # Si no hay registros después del filtro, mostrar qué meses había antes
                debug_warning(f"⚠️ No se encontraron registros de ingresos para {fecha_inicio_mes.strftime('%Y-%m')}")
                if "MES" in df_merge_ingresos.columns:
                    # Asegurar que MES esté normalizado en df_merge_ingresos
                    if not pd.api.types.is_datetime64_any_dtype(df_merge_ingresos["MES"]):
                        df_merge_ingresos["MES"] = pd.to_datetime(df_merge_ingresos["MES"])
                    df_merge_ingresos["MES"] = pd.to_datetime(df_merge_ingresos["MES"]).dt.to_period("M").dt.to_timestamp()
                    meses_disponibles = sorted(df_merge_ingresos["MES"].dt.to_period("M").unique().astype(str).tolist())
                    debug_info(f"📅 Meses disponibles en merge: {meses_disponibles}")
                    # Mostrar algunos valores de MES para comparar
                    muestra_mes_merge = df_merge_ingresos["MES"].head(5).tolist()
                    debug_info(f"🔍 Muestra MES en merge: {[str(m) for m in muestra_mes_merge]}")
        
        if "MES" in df_vista_egresos.columns:
            # Asegurar que MES esté normalizado al primer día del mes
            if not pd.api.types.is_datetime64_any_dtype(df_vista_egresos["MES"]):
                df_vista_egresos["MES"] = pd.to_datetime(df_vista_egresos["MES"])
            
            # Normalizar MES al primer día del mes para comparar
            df_vista_egresos["MES"] = pd.to_datetime(df_vista_egresos["MES"]).dt.to_period("M").dt.to_timestamp()
            
            # Filtrar: MES debe estar entre fecha_inicio_mes y fecha_fin_mes (inclusive)
            # Debug: mostrar algunos valores de MES antes del filtro para comparar
            if len(df_vista_egresos) > 0:
                muestra_mes_antes = df_vista_egresos["MES"].head(5).tolist()
                debug_info(f"🔍 Muestra MES egresos antes filtro: {[str(m) for m in muestra_mes_antes]}")
            
            mask = (df_vista_egresos["MES"] >= fecha_inicio_mes) & (df_vista_egresos["MES"] <= fecha_fin_mes)
            df_vista_egresos = df_vista_egresos[mask].copy()
            
            # Debug: mostrar información del filtro
            debug_info(f"🔍 Filtro egresos: {fecha_inicio_mes.strftime('%Y-%m-%d')} <= MES <= {fecha_fin_mes.strftime('%Y-%m-%d')}")
            debug_info(f"📊 Registros egresos después de filtro: {len(df_vista_egresos)}")
            if len(df_vista_egresos) > 0:
                meses_encontrados = sorted(df_vista_egresos['MES'].dt.to_period('M').unique().astype(str).tolist())
                debug_info(f"📅 MES egresos encontrados: {meses_encontrados}")
                debug_info(f"💰 Total MONTO egresos filtrado: ${df_vista_egresos['MONTO'].sum():,.0f}")
            else:
                # Si no hay registros después del filtro, mostrar qué meses había antes
                debug_warning(f"⚠️ No se encontraron registros de egresos para {fecha_inicio_mes.strftime('%Y-%m')}")
                if "MES" in df_merge_egresos.columns:
                    # Asegurar que MES esté normalizado en df_merge_egresos
                    if not pd.api.types.is_datetime64_any_dtype(df_merge_egresos["MES"]):
                        df_merge_egresos["MES"] = pd.to_datetime(df_merge_egresos["MES"])
                    df_merge_egresos["MES"] = pd.to_datetime(df_merge_egresos["MES"]).dt.to_period("M").dt.to_timestamp()
                    meses_disponibles = sorted(df_merge_egresos["MES"].dt.to_period("M").unique().astype(str).tolist())
                    debug_info(f"📅 Meses disponibles en merge: {meses_disponibles}")
                    # Mostrar algunos valores de MES para comparar
                    muestra_mes_merge = df_merge_egresos["MES"].head(5).tolist()
                    debug_info(f"🔍 Muestra MES egresos en merge: {[str(m) for m in muestra_mes_merge]}")
    
    # Filtrar por clasificaciones
    if seleccionadas:
        df_vista_ingresos = df_vista_ingresos[df_vista_ingresos["CLASIFICACION"].isin(seleccionadas)]
        df_vista_egresos = df_vista_egresos[df_vista_egresos["CLASIFICACION"].isin(seleccionadas)]
    
    # Combinar para df_vista (para compatibilidad)
    df_vista = pd.concat([df_vista_ingresos, df_vista_egresos], ignore_index=True)
    
    # Mostrar información sobre el filtro aplicado
    if fecha_inicio and fecha_fin:
        st.info(f"📅 **Filtro activo**: Desde {fecha_inicio} hasta {fecha_fin}")
    if seleccionadas and len(seleccionadas) < len(clasificaciones) if 'clasificaciones' in locals() else False:
        st.info(f"🏷️ **Clasificaciones seleccionadas**: {len(seleccionadas)} de {len(clasificaciones)}")
    
    if df_vista.empty:
        st.warning("⚠️ No hay datos que coincidan con los filtros seleccionados.")
        st.info("💡 Intenta ajustar el rango de fechas o las clasificaciones.")
        df_vista_ingresos = df_merge_ingresos.copy()
        df_vista_egresos = df_merge_egresos.copy()
        df_vista = df_merge.copy()  # Mostrar todos los datos como fallback
        
except Exception as e:
    st.error(f"❌ Error al aplicar filtros: {e}")
    with st.expander("🔍 Ver detalles del error"):
        st.code(traceback.format_exc())
    df_vista_ingresos = df_merge_ingresos.copy()
    df_vista_egresos = df_merge_egresos.copy()
    df_vista = df_merge.copy()  # Usar todos los datos como fallback

# ==================== SECCIÓN COMPARATIVA - PRINCIPAL ====================
# ESTA ES LA PARTE PRINCIPAL DE LA APLICACIÓN COMPARATIVA
# Mostrar las comparaciones INMEDIATAMENTE después de preparar los datos

# Estilos CSS personalizados para mejorar la presentación
st.markdown("""
    <style>
    /* Header principal mejorado */
    .main-header {
        font-size: 2.5rem;
        font-weight: 700;
        background: linear-gradient(135deg, #2d5016 0%, #4a7c2a 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
        text-align: center;
        margin-bottom: 1.5rem;
        padding-bottom: 1rem;
        border-bottom: 3px solid #2d5016;
        text-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    
    /* Secciones con mejor diseño */
    .section-header {
        font-size: 1.5rem;
        font-weight: 600;
        color: #2c3e50;
        margin-top: 2rem;
        margin-bottom: 1.5rem;
        padding: 1rem 1.5rem;
        background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
        border-left: 5px solid #2d5016;
        border-radius: 8px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
    }
    
    /* Métricas mejoradas */
    [data-testid="stMetricContainer"] {
        background: linear-gradient(135deg, #ffffff 0%, #f8f9fa 100%);
        padding: 1.25rem;
        border-radius: 12px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        border: 1px solid #e0e0e0;
        transition: all 0.3s ease;
    }
    
    [data-testid="stMetricContainer"]:hover {
        transform: translateY(-2px);
        box-shadow: 0 6px 12px rgba(0,0,0,0.15);
    }
    
    [data-testid="stMetricLabel"] {
        font-size: 0.95rem;
        font-weight: 600;
        color: #495057;
        letter-spacing: 0.5px;
    }
    
    [data-testid="stMetricValue"] {
        font-size: 1.8rem;
        font-weight: 700;
        color: #212529;
    }
    
    [data-testid="stMetricDelta"] {
        font-weight: 600;
    }
    
    /* Badges de estado mejorados */
    .status-badge {
        padding: 0.75rem 1.25rem;
        border-radius: 25px;
        font-weight: 600;
        font-size: 0.9rem;
        display: inline-block;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    
    .status-success {
        background: linear-gradient(135deg, #28a745 0%, #20c997 100%);
        color: white;
    }
    
    .status-warning {
        background: linear-gradient(135deg, #ffc107 0%, #fd7e14 100%);
        color: #212529;
    }
    
    /* Tablas con colores condicionales */
    .dataframe {
        border-radius: 8px;
        overflow: hidden;
        box-shadow: 0 2px 8px rgba(0,0,0,0.1);
    }
    
    .dataframe thead {
        background: linear-gradient(135deg, #2d5016 0%, #4a7c2a 100%);
        color: white;
    }
    
    .dataframe thead th {
        font-weight: 600;
        padding: 1rem;
    }
    
    .dataframe tbody tr {
        transition: background-color 0.2s ease;
    }
    
    .dataframe tbody tr:hover {
        background-color: #f8f9fa;
    }
    
    /* Mejoras en separadores */
    hr {
        border: none;
        height: 2px;
        background: linear-gradient(90deg, transparent, #2d5016, transparent);
        margin: 2rem 0;
    }
    
    /* Mejoras en títulos de sección */
    h3 {
        color: #2c3e50;
        font-weight: 600;
        margin-top: 1.5rem;
        margin-bottom: 1rem;
        padding-bottom: 0.5rem;
        border-bottom: 2px solid #e9ecef;
    }
    
    /* Alertas mejoradas */
    .stAlert {
        border-radius: 8px;
        border-left: 4px solid;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    
    /* Mejoras en el contenedor principal */
    .main .block-container {
        padding-top: 2rem;
        padding-bottom: 2rem;
        max-width: 1200px;
    }
    
    /* Mejoras en el sidebar */
    .css-1d391kg {
        background: linear-gradient(180deg, #f8f9fa 0%, #ffffff 100%);
    }
    
    /* Botones mejorados */
    .stButton > button {
        border-radius: 8px;
        font-weight: 500;
        transition: all 0.3s ease;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    
    .stButton > button:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 8px rgba(0,0,0,0.2);
    }
    
    /* Mejoras en los gráficos */
    .js-plotly-plot {
        border-radius: 8px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.1);
    }
    </style>
""", unsafe_allow_html=True)

st.markdown("---")
st.markdown('<h1 class="main-header">📊 Comparación Proyectado vs Real</h1>', unsafe_allow_html=True)

# Debug: Verificar estado de las variables
st.sidebar.markdown("---")
# Estado de datos (solo en modo debug)
if MODO_DEBUG:
    with debug_expander("🔍 Estado de Datos"):
        st.write(f"df_merge existe: {'df_merge' in locals()}")
        st.write(f"df_vista existe: {'df_vista' in locals()}")
        if 'df_merge' in locals():
            st.write(f"df_merge tamaño: {len(df_merge)}")
            if not df_merge.empty:
                st.write(f"Columnas df_merge: {list(df_merge.columns)}")
        if 'df_vista' in locals():
            st.write(f"df_vista tamaño: {len(df_vista)}")

# Verificar que tenemos df_vista antes de continuar
if 'df_vista' not in locals() or df_vista.empty:
    st.error("❌ Error: No se pudo preparar la vista comparativa.")
    if 'df_merge' in locals() and not df_merge.empty:
        st.info("💡 df_merge tiene datos, pero df_vista está vacío. Revisa los filtros.")
        with st.expander("🔍 Ver datos de df_merge"):
            st.dataframe(df_merge.head(10))
    else:
        st.info("💡 Verifica que las clasificaciones en el archivo de proyección coincidan con las de los datos reales.")
    st.stop()

# Mostrar métricas principales de comparación - SEPARADAS POR INGRESOS Y EGRESOS
st.markdown('<div class="section-header">💰 Resumen Comparativo General</div>', unsafe_allow_html=True)

# INGRESOS
st.markdown("### 💵 Ingresos")
try:
    if 'df_vista_ingresos' in locals() and not df_vista_ingresos.empty:
        total_proyectado_ing = df_vista_ingresos["MONTO"].sum() if "MONTO" in df_vista_ingresos.columns else 0
        total_real_ing = df_vista_ingresos["REAL_INGRESOS"].sum() if "REAL_INGRESOS" in df_vista_ingresos.columns else 0
        diferencia_ing = df_vista_ingresos["DIFERENCIA"].sum() if "DIFERENCIA" in df_vista_ingresos.columns else 0
        porcentaje_dif_ing = (diferencia_ing / total_proyectado_ing) * 100 if total_proyectado_ing > 0 else 0
        
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            delta_ing = f"{porcentaje_dif_ing:+.2f}%" if total_proyectado_ing > 0 else None
            st.metric("Ingresos Proyectados", f"${total_proyectado_ing:,.0f}", delta=delta_ing)
        with col2:
            st.metric("Ingresos Reales", f"${total_real_ing:,.0f}")
        with col3:
            color_delta = "normal" if diferencia_ing >= 0 else "inverse"
            st.metric("Diferencia", f"${diferencia_ing:,.0f}", delta=f"{porcentaje_dif_ing:+.2f}%")
        with col4:
            if diferencia_ing >= 0:
                st.markdown(
                    f'<div class="status-badge status-success">'
                    f'✅ Supera proyección en {abs(porcentaje_dif_ing):.2f}%'
                    f'</div>',
                    unsafe_allow_html=True
                )
            else:
                st.markdown(
                    f'<div class="status-badge status-warning">'
                    f'⚠️ Por debajo de proyección en {abs(porcentaje_dif_ing):.2f}%'
                    f'</div>',
                    unsafe_allow_html=True
                )
    else:
        st.info("ℹ️ No hay datos de ingresos para mostrar comparación.")
except Exception as e:
    st.error(f"❌ Error al calcular métricas de ingresos: {e}")

st.markdown("---")

# EGRESOS
st.markdown("### 💸 Egresos")
try:
    if 'df_vista_egresos' in locals() and not df_vista_egresos.empty:
        total_proyectado_eg = df_vista_egresos["MONTO"].sum() if "MONTO" in df_vista_egresos.columns else 0
        total_real_eg = df_vista_egresos["REAL_EGRESOS"].sum() if "REAL_EGRESOS" in df_vista_egresos.columns else 0
        diferencia_eg = df_vista_egresos["DIFERENCIA"].sum() if "DIFERENCIA" in df_vista_egresos.columns else 0
        porcentaje_dif_eg = (diferencia_eg / total_proyectado_eg) * 100 if total_proyectado_eg > 0 else 0
        
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            delta_eg = f"{porcentaje_dif_eg:+.2f}%" if total_proyectado_eg > 0 else None
            st.metric("Egresos Proyectados", f"${total_proyectado_eg:,.0f}", delta=delta_eg)
        with col2:
            st.metric("Egresos Reales", f"${total_real_eg:,.0f}")
        with col3:
            st.metric("Diferencia", f"${diferencia_eg:,.0f}", delta=f"{porcentaje_dif_eg:+.2f}%")
        with col4:
            if diferencia_eg <= 0:
                st.markdown(
                    f'<div class="status-badge status-success">'
                    f'✅ Por debajo de proyección en {abs(porcentaje_dif_eg):.2f}%'
                    f'</div>',
                    unsafe_allow_html=True
                )
            else:
                st.markdown(
                    f'<div class="status-badge status-warning">'
                    f'⚠️ Supera proyección en {abs(porcentaje_dif_eg):.2f}%'
                    f'</div>',
                    unsafe_allow_html=True
                )
    else:
        st.info("ℹ️ No hay datos de egresos para mostrar comparación.")
except Exception as e:
    st.error(f"❌ Error al calcular métricas de egresos: {e}")

# ----------------- TABLA COMPARATIVA DETALLADA - INGRESOS -----------------
st.markdown("---")
st.markdown('<div class="section-header">📋 Comparación Detallada: Ingresos</div>', unsafe_allow_html=True)

if 'df_vista_ingresos' in locals() and not df_vista_ingresos.empty:
    columnas_ingresos = ["CLASIFICACION", "MES", "MONTO", "REAL_INGRESOS", "DIFERENCIA"]
    columnas_faltantes_ing = [col for col in columnas_ingresos if col not in df_vista_ingresos.columns]
    
    if columnas_faltantes_ing:
        st.warning(f"⚠️ Faltan columnas: {', '.join(columnas_faltantes_ing)}")
    else:
        # Formatear la tabla para mejor presentación con colores condicionales
        df_display_ing = df_vista_ingresos[columnas_ingresos].copy()
        
        # Formatear valores monetarios
        df_display_ing["MONTO"] = df_display_ing["MONTO"].apply(lambda x: f"${x:,.0f}" if pd.notna(x) else "$0")
        df_display_ing["REAL_INGRESOS"] = df_display_ing["REAL_INGRESOS"].apply(lambda x: f"${x:,.0f}" if pd.notna(x) else "$0")
        
        # Formatear fechas
        df_display_ing["MES"] = df_display_ing["MES"].dt.strftime("%Y-%m") if pd.api.types.is_datetime64_any_dtype(df_vista_ingresos["MES"]) else df_display_ing["MES"]
        
        # Crear columna de diferencia formateada con colores
        def formatear_diferencia(valor):
            if pd.isna(valor):
                return "$0"
            valor_num = float(valor)
            if valor_num >= 0:
                return f"${valor_num:,.0f}"
            else:
                return f"${valor_num:,.0f}"
        
        df_display_ing["DIFERENCIA"] = df_display_ing["DIFERENCIA"].apply(formatear_diferencia)
        
        # Aplicar estilos condicionales
        def highlight_difference(val):
            if isinstance(val, str) and val.startswith("$"):
                try:
                    num_val = float(val.replace("$", "").replace(",", ""))
                    if num_val > 0:
                        return 'background-color: #d4edda; color: #155724; font-weight: 600;'
                    elif num_val < 0:
                        return 'background-color: #f8d7da; color: #721c24; font-weight: 600;'
                except:
                    pass
            return ''
        
        # Aplicar estilos solo a la columna DIFERENCIA
        styled_df = df_display_ing.style.applymap(
            highlight_difference,
            subset=['DIFERENCIA']
        ).set_properties(**{
            'text-align': 'left'
        }).set_table_styles([
            {'selector': 'thead th', 'props': [('background-color', '#2d5016'), ('color', 'white'), ('font-weight', '600'), ('padding', '1rem')]},
            {'selector': 'tbody tr:hover', 'props': [('background-color', '#f8f9fa')]},
        ])
        
        st.dataframe(
            styled_df,
            use_container_width=True,
            hide_index=True
        )
else:
    st.info("ℹ️ No hay datos de ingresos para mostrar.")

# ----------------- TABLA COMPARATIVA DETALLADA - EGRESOS -----------------
st.markdown("---")
st.markdown('<div class="section-header">📋 Comparación Detallada: Egresos</div>', unsafe_allow_html=True)

if 'df_vista_egresos' in locals() and not df_vista_egresos.empty:
    columnas_egresos = ["CLASIFICACION", "MES", "MONTO", "REAL_EGRESOS", "DIFERENCIA"]
    columnas_faltantes_eg = [col for col in columnas_egresos if col not in df_vista_egresos.columns]
    
    if columnas_faltantes_eg:
        st.warning(f"⚠️ Faltan columnas: {', '.join(columnas_faltantes_eg)}")
    else:
        # Formatear la tabla para mejor presentación con colores condicionales
        df_display_eg = df_vista_egresos[columnas_egresos].copy()
        
        # Formatear valores monetarios
        df_display_eg["MONTO"] = df_display_eg["MONTO"].apply(lambda x: f"${x:,.0f}" if pd.notna(x) else "$0")
        df_display_eg["REAL_EGRESOS"] = df_display_eg["REAL_EGRESOS"].apply(lambda x: f"${x:,.0f}" if pd.notna(x) else "$0")
        
        # Formatear fechas
        df_display_eg["MES"] = df_display_eg["MES"].dt.strftime("%Y-%m") if pd.api.types.is_datetime64_any_dtype(df_vista_egresos["MES"]) else df_display_eg["MES"]
        
        # Crear columna de diferencia formateada con colores
        def formatear_diferencia(valor):
            if pd.isna(valor):
                return "$0"
            valor_num = float(valor)
            if valor_num >= 0:
                return f"${valor_num:,.0f}"
            else:
                return f"${valor_num:,.0f}"
        
        df_display_eg["DIFERENCIA"] = df_display_eg["DIFERENCIA"].apply(formatear_diferencia)
        
        # Aplicar estilos condicionales (para egresos, negativo es bueno, positivo es malo)
        def highlight_difference_egresos(val):
            if isinstance(val, str) and val.startswith("$"):
                try:
                    num_val = float(val.replace("$", "").replace(",", ""))
                    if num_val < 0:  # Negativo es bueno (gastamos menos)
                        return 'background-color: #d4edda; color: #155724; font-weight: 600;'
                    elif num_val > 0:  # Positivo es malo (gastamos más)
                        return 'background-color: #f8d7da; color: #721c24; font-weight: 600;'
                except:
                    pass
            return ''
        
        # Aplicar estilos solo a la columna DIFERENCIA
        styled_df = df_display_eg.style.applymap(
            highlight_difference_egresos,
            subset=['DIFERENCIA']
        ).set_properties(**{
            'text-align': 'left'
        }).set_table_styles([
            {'selector': 'thead th', 'props': [('background-color', '#2d5016'), ('color', 'white'), ('font-weight', '600'), ('padding', '1rem')]},
            {'selector': 'tbody tr:hover', 'props': [('background-color', '#f8f9fa')]},
        ])
        
        st.dataframe(
            styled_df,
            use_container_width=True,
            hide_index=True
        )
else:
    st.info("ℹ️ No hay datos de egresos para mostrar.")

# ----------------- GRÁFICO COMPARATIVO - INGRESOS -----------------
st.markdown("---")
st.markdown('<div class="section-header">📊 Análisis Visual: Ingresos</div>', unsafe_allow_html=True)

try:
    if 'df_vista_ingresos' in locals() and not df_vista_ingresos.empty and "MONTO" in df_vista_ingresos.columns and "REAL_INGRESOS" in df_vista_ingresos.columns:
        fig_ing = px.bar(
            df_vista_ingresos, 
            x="MES", 
            y=["MONTO", "REAL_INGRESOS"], 
            color_discrete_sequence=["#2d5016", "#4a7c2a"],
            barmode="group", 
            facet_col="CLASIFICACION", 
            facet_col_wrap=2, 
            height=600,
            labels={"MONTO": "Proyectado", "REAL_INGRESOS": "Real", "MES": "Mes", "value": "Monto (CLP)"}
        )
        fig_ing.update_layout(
            showlegend=True,
            title={
                "text": "Comparación Ingresos: Proyectado vs Real por Clasificación",
                "x": 0.5,
                "xanchor": "center",
                "font": {"size": 18, "color": "#2c3e50"}
            },
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            font=dict(family="Arial, sans-serif", size=12, color="#2c3e50"),
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.02,
                xanchor="right",
                x=1
            )
        )
        fig_ing.update_xaxes(showgrid=True, gridwidth=1, gridcolor="rgba(0,0,0,0.1)")
        fig_ing.update_yaxes(showgrid=True, gridwidth=1, gridcolor="rgba(0,0,0,0.1)")
        st.plotly_chart(fig_ing, use_container_width=True)
    else:
        st.info("ℹ️ No hay datos de ingresos para generar el gráfico.")
except Exception as e:
    st.error(f"❌ Error al generar gráfico de ingresos: {e}")
    with st.expander("🔍 Ver detalles del error"):
        st.code(traceback.format_exc())

# ----------------- GRÁFICO COMPARATIVO - EGRESOS -----------------
st.markdown("---")
st.markdown('<div class="section-header">📊 Análisis Visual: Egresos</div>', unsafe_allow_html=True)

try:
    if 'df_vista_egresos' in locals() and not df_vista_egresos.empty and "MONTO" in df_vista_egresos.columns and "REAL_EGRESOS" in df_vista_egresos.columns:
        fig_eg = px.bar(
            df_vista_egresos, 
            x="MES", 
            y=["MONTO", "REAL_EGRESOS"], 
            color_discrete_sequence=["#e74c3c", "#c0392b"],
            barmode="group", 
            facet_col="CLASIFICACION", 
            facet_col_wrap=2, 
            height=600,
            labels={"MONTO": "Proyectado", "REAL_EGRESOS": "Real", "MES": "Mes", "value": "Monto (CLP)"}
        )
        fig_eg.update_layout(
            showlegend=True,
            title={
                "text": "Comparación Egresos: Proyectado vs Real por Clasificación",
                "x": 0.5,
                "xanchor": "center",
                "font": {"size": 18, "color": "#2c3e50"}
            },
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            font=dict(family="Arial, sans-serif", size=12, color="#2c3e50"),
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.02,
                xanchor="right",
                x=1
            )
        )
        fig_eg.update_xaxes(showgrid=True, gridwidth=1, gridcolor="rgba(0,0,0,0.1)")
        fig_eg.update_yaxes(showgrid=True, gridwidth=1, gridcolor="rgba(0,0,0,0.1)")
        st.plotly_chart(fig_eg, use_container_width=True)
    else:
        st.info("ℹ️ No hay datos de egresos para generar el gráfico.")
except Exception as e:
    st.error(f"❌ Error al generar gráfico de egresos: {e}")
    with st.expander("🔍 Ver detalles del error"):
        st.code(traceback.format_exc())

# ----------------- RESUMEN POR CLASIFICACIÓN - INGRESOS -----------------
st.markdown("---")
st.subheader("📘 Resumen por Clasificación: INGRESOS")
if 'df_vista_ingresos' in locals() and not df_vista_ingresos.empty:
    df_resumen_clasif_ing = df_vista_ingresos.groupby("CLASIFICACION")[["MONTO", "REAL_INGRESOS", "DIFERENCIA"]].sum().reset_index()
    df_resumen_clasif_ing = df_resumen_clasif_ing.sort_values("MONTO", ascending=False)
    st.dataframe(df_resumen_clasif_ing, use_container_width=True)
else:
    st.info("ℹ️ No hay datos de ingresos para mostrar resumen.")

# ----------------- RESUMEN POR CLASIFICACIÓN - EGRESOS -----------------
st.subheader("📘 Resumen por Clasificación: EGRESOS")
if 'df_vista_egresos' in locals() and not df_vista_egresos.empty:
    df_resumen_clasif_eg = df_vista_egresos.groupby("CLASIFICACION")[["MONTO", "REAL_EGRESOS", "DIFERENCIA"]].sum().reset_index()
    df_resumen_clasif_eg = df_resumen_clasif_eg.sort_values("MONTO", ascending=False)
    st.dataframe(df_resumen_clasif_eg, use_container_width=True)
else:
    st.info("ℹ️ No hay datos de egresos para mostrar resumen.")

# ----------------- RESUMEN POR MES - INGRESOS -----------------
st.markdown("---")
st.subheader("📅 Totales por Mes: INGRESOS")
if 'df_vista_ingresos' in locals() and not df_vista_ingresos.empty:
    df_resumen_mes_ing = df_vista_ingresos.groupby("MES")[["MONTO", "REAL_INGRESOS", "DIFERENCIA"]].sum().reset_index()
    st.dataframe(df_resumen_mes_ing, use_container_width=True)
else:
    st.info("ℹ️ No hay datos de ingresos para mostrar resumen mensual.")

# ----------------- RESUMEN POR MES - EGRESOS -----------------
st.subheader("📅 Totales por Mes: EGRESOS")
if 'df_vista_egresos' in locals() and not df_vista_egresos.empty:
    df_resumen_mes_eg = df_vista_egresos.groupby("MES")[["MONTO", "REAL_EGRESOS", "DIFERENCIA"]].sum().reset_index()
    st.dataframe(df_resumen_mes_eg, use_container_width=True)
else:
    st.info("ℹ️ No hay datos de egresos para mostrar resumen mensual.")

# Nota: Las secciones de semáforo se pueden agregar más adelante si se requiere
# Por ahora, las comparaciones separadas de ingresos y egresos están completas

# ----------------- GRÁFICO DE LÍNEA - COMBINADO -----------------
st.markdown("---")
st.subheader("📈 Evolución Mensual - Proyectado vs Real (Combinado)")

try:
    # Combinar ingresos y egresos para gráfico general
    if 'df_resumen_mes_ing' in locals() and 'df_resumen_mes_eg' in locals():
        # Crear DataFrame combinado
        df_resumen_mes_ing_copy = df_resumen_mes_ing.copy()
        df_resumen_mes_ing_copy["TIPO"] = "INGRESOS"
        df_resumen_mes_ing_copy.rename(columns={"REAL_INGRESOS": "REAL"}, inplace=True)
        
        df_resumen_mes_eg_copy = df_resumen_mes_eg.copy()
        df_resumen_mes_eg_copy["TIPO"] = "EGRESOS"
        df_resumen_mes_eg_copy.rename(columns={"REAL_EGRESOS": "REAL"}, inplace=True)
        
        # Unificar columnas
        df_resumen_mes_ing_copy = df_resumen_mes_ing_copy[["MES", "MONTO", "REAL", "TIPO"]]
        df_resumen_mes_eg_copy = df_resumen_mes_eg_copy[["MES", "MONTO", "REAL", "TIPO"]]
        
        df_resumen_mes_combinado = pd.concat([df_resumen_mes_ing_copy, df_resumen_mes_eg_copy], ignore_index=True)
        
        if not df_resumen_mes_combinado.empty:
            fig_mes = px.line(df_resumen_mes_combinado, x="MES", y=["MONTO", "REAL"], 
                            color="TIPO", markers=True)
            fig_mes.update_layout(title="Totales mensuales - Ingresos y Egresos", 
                                xaxis_title="Mes", yaxis_title="Monto")
            st.plotly_chart(fig_mes, use_container_width=True)
        else:
            st.info("ℹ️ No hay datos para generar el gráfico combinado.")
    else:
        st.info("ℹ️ No hay datos suficientes para generar el gráfico combinado.")
except Exception as e:
    st.error(f"❌ Error al generar gráfico combinado: {e}")
    with st.expander("🔍 Ver detalles del error"):
        st.code(traceback.format_exc())

# ----------------- DIFERENCIA ACUMULADA -----------------
st.markdown("---")
st.subheader("📌 Diferencia Acumulada por Clasificación")

# Diferencia de ingresos
if 'df_vista_ingresos' in locals() and not df_vista_ingresos.empty:
    st.markdown("### 💵 Ingresos")
    df_resumen_ing = df_vista_ingresos.groupby("CLASIFICACION")["DIFERENCIA"].sum().reset_index()
    df_resumen_ing = df_resumen_ing.sort_values("DIFERENCIA", ascending=False)
    st.dataframe(df_resumen_ing, use_container_width=True)

# Diferencia de egresos
if 'df_vista_egresos' in locals() and not df_vista_egresos.empty:
    st.markdown("### 💸 Egresos")
    df_resumen_eg = df_vista_egresos.groupby("CLASIFICACION")["DIFERENCIA"].sum().reset_index()
    df_resumen_eg = df_resumen_eg.sort_values("DIFERENCIA", ascending=False)
    st.dataframe(df_resumen_eg, use_container_width=True)

# ----------------- DESCARGA -----------------
st.subheader("⬇️ Descargar Comparativo")
output = io.BytesIO()
df_vista.to_excel(output, index=False, engine='openpyxl')
st.download_button("Descargar Excel comparativo", output.getvalue(), file_name="comparativo_flujo.xlsx")

# ----------------- LINK FINAL -----------------
st.markdown("---")
st.markdown('<div class="section-header">🔗 Otras herramientas disponibles</div>', unsafe_allow_html=True)
if st.button("🔙 Ir a versión con más detalle financiero", use_container_width=True):
    st.markdown("[Haz clic aquí para abrir ➡️](https://flujocaja-vuzuh5stlggh4pppmua5qz.streamlit.app/)", unsafe_allow_html=True)

# ----------------- FOOTER PROFESIONAL -----------------
st.markdown("---")
st.markdown("""
    <div style="
        background: linear-gradient(135deg, #2d5016 0%, #4a7c2a 100%);
        color: white;
        padding: 2rem;
        border-radius: 10px;
        margin-top: 3rem;
        text-align: center;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    ">
        <h3 style="color: white; margin-bottom: 1rem;">📊 Flujo de Caja Comparativo</h3>
        <p style="margin-bottom: 0.5rem; opacity: 0.9;">
            Sistema de análisis comparativo de flujo de caja proyectado vs real
        </p>
        <p style="margin-bottom: 0; font-size: 0.9rem; opacity: 0.8;">
            © 2025 - Desarrollado para gestión financiera empresarial
        </p>
    </div>
""", unsafe_allow_html=True)
