import streamlit as st
import pandas as pd
import plotly.express as px
import unicodedata
import io

# ---------- CONFIGURACIÓN DE PÁGINA ----------
st.set_page_config(page_title="Flujo de Caja Inteligente", layout="wide")
st.title("📊 Dashboard Flujo de Caja - Clasificación Inteligente")

# ---------- FUNCIONES ----------
@st.cache_data
def normalizar(texto):
    if pd.isnull(texto):
        return ""
    texto = str(texto).upper().strip()
    texto = unicodedata.normalize("NFD", texto).encode("ascii", "ignore").decode("utf-8")
    return texto

def clasificar_mejorado(texto, abono):
    texto = normalizar(texto)

    if abono > 0:
        if any(palabra in texto for palabra in ["FACTURA", "COBRAR", "FLUJO", "APP-TRASPASO", "PAGO", "DEPOSITO", "DEP.CHEQ", "DEPOSITO EN EFECTIVO"]):
            return "1.01.05.01 - Facturas por cobrar Nacional- FLUJO"
        elif "LINEA DE CREDITO" in texto:
            return "LINEA DE CREDITO"
        elif "RECICLAJES ECOLOGICOS DE CHILE LIMITADA" in texto:
            return "FINANCIAMIENTO EXTERNO"
        elif "TRASPASO DE" in texto:
            return "1.01.05.01 - Facturas por cobrar Nacional- FLUJO"
        else:
            return "NO CLASIFICADO"
    else:
        if "PROVEEDORES" in texto:
            return "PROVEEDORES NACIONALES"
        elif "SUELDOS" in texto or "REMUNERACION" in texto:
            return "REMUNERACIONES POR PAGAR"
        elif any(p in texto for p in ["SERVIPAG", "AGUA", "DISTRIBUIDORA", "TRASPASO A"]):
            return "PROVEEDORES NACIONALES"
        elif "HONORARIOS" in texto:
            return "HONORARIOS POR PAGAR"
        elif "INSTITUTO" in texto or "COLEGIO" in texto:
            return "GASTOS EDUCACION"
        elif "CONSTRUCCION" in texto or "SEPCO" in texto:
            return "FACTURAS POR COBRAR NACIONAL"
        elif "LINEA" in texto:
            return "LINEA DE CREDITO"
        elif "EFECTIVO" in texto:
            return "DEPOSITO EFECTIVO"
        elif "VIRTUALPOS" in texto:
            return "SERVICIOS TRANSBANK"
        elif "BRUSSELS" in texto:
            return "SERVICIOS EXTERNOS"
        elif "COMISION" in texto or "SEGURO" in texto:
            return "GASTOS Y COMISIONES BANCARIAS ( BANCO CHILE - SECURITY )"
        elif "PAGO EN SII" in texto:
            return "IMPUESTOS"
        elif "PAGO DE CREDITOS M/N" in texto:
            return "CREDITO BANCO DE CHILE"
        elif "PAGO AUTOMATICO TARJETA DE CREDITO" in texto:
            return "PAGO TARJETA DE CREDITO"
        elif any(p in texto for p in ["INVERSIONES ISLA KENT SPA", "INMOBILIARIA MONJITAS SA", "MALSCH Y COMPANIA S.A."]):
            return "2.01.07.01-Proveedores Arrdo  Oficina , estacionamiento"
        elif "PAGO INSTITUCIONES PREVISIONALES" in texto:
            return "IMPOSICIONES"
        elif "TRASPASO DE:RECICLAJES ECOLOGICOS DE CHILE LIMITADA" in texto:
            return "FINANCIAMIENTO EXTERNO"
        else:
            return "NO CLASIFICADO"

@st.cache_data
def cargar_datos(path):
    df = pd.read_excel(path)
    df.columns = df.columns.str.strip().str.upper()

    if "DESCRIPCIÓN" in df.columns:
        df.rename(columns={"DESCRIPCIÓN": "DESCRIPCION"}, inplace=True)

    df["DESCRIPCION"] = df["DESCRIPCION"].astype(str)
    df["COMENTARIO"] = df["DESCRIPCION"].apply(normalizar)
    df["FECHA"] = pd.to_datetime(df["FECHA"], dayfirst=True, errors='coerce')

    df["CLASIFICACION"] = df.apply(lambda row: clasificar_mejorado(row["COMENTARIO"], row["ABONOS (CLP)"]), axis=1)
    df = df.loc[:, ~df.columns.str.contains("^UNNAMED")]
    return df

# ---------- CARGA DIRECTA DE ARCHIVO ----------
archivo = "cartola_junio_2025.xlsx"
try:
    df = cargar_datos(archivo)

    # ---------- BARRA LATERAL DE FILTROS ----------
    st.sidebar.header("Filtros")
    fecha_min = df["FECHA"].min()
    fecha_max = df["FECHA"].max()
    rango = st.sidebar.date_input("🗓️ Rango de fechas", [fecha_min, fecha_max])

    if len(rango) == 2:
        df = df[(df["FECHA"] >= pd.to_datetime(rango[0])) & (df["FECHA"] <= pd.to_datetime(rango[1]))]
        st.caption(f"📃 Mostrando movimientos desde {rango[0].strftime('%d-%m-%Y')} hasta {rango[1].strftime('%d-%m-%Y')}")

    clasificaciones = sorted(df["CLASIFICACION"].unique())
    seleccion = st.sidebar.multiselect("🏷️ Clasificaciones", clasificaciones, default=clasificaciones)

    df_filtrado = df[df["CLASIFICACION"].isin(seleccion)]

    # ---------- METRICAS PRINCIPALES ----------
    total_abonos = df_filtrado['ABONOS (CLP)'].sum()
    total_cargos = df_filtrado['CARGOS (CLP)'].sum()
    flujo_neto = total_abonos - total_cargos

    col1, col2, col3 = st.columns(3)
    col1.metric("💸 Total Abonos", f"${total_abonos:,.0f}")
    col2.metric("💰 Total Cargos", f"${total_cargos:,.0f}")
    col3.metric("📈 Flujo Neto", f"${flujo_neto:,.0f}", delta_color="inverse")

    # ---------- CÁLCULO DE SALDO FINAL ----------
    st.sidebar.subheader("💼 Ajustes de caja")
    saldo_inicial = st.sidebar.number_input("Saldo inicial del periodo", value=0, key="saldo_inicial_input")
    saldo_calculado = saldo_inicial + total_abonos - total_cargos

    df_ordenado = df_filtrado.sort_values(by="FECHA")
    fila_ultimo_saldo = df_ordenado[df_ordenado["SALDO (CLP)"].notna()].iloc[-1:]

    if not fila_ultimo_saldo.empty:
        saldo_cartola = fila_ultimo_saldo["SALDO (CLP)"].values[0]
        fecha_saldo_cartola = fila_ultimo_saldo["FECHA"].values[0]
        diferencia = saldo_calculado - saldo_cartola
    else:
        saldo_cartola = None
        diferencia = None

    col4, col5 = st.columns(2)
    col4.metric("📌 Saldo Final Calculado", f"${saldo_calculado:,.0f}")
    if saldo_cartola is not None:
        col5.metric("🏦 Saldo según cartola", f"${saldo_cartola:,.0f}", delta=f"${diferencia:,.0f}")
        st.caption(f"💡 Saldo cartola al {pd.to_datetime(fecha_saldo_cartola).strftime('%d-%m-%Y')}")
    else:
        col5.warning("No se pudo leer saldo final de cartola.")

    # ---------- TABLA DETALLE ----------
    st.subheader("🔍 Detalle de transacciones clasificadas")
    st.dataframe(df_filtrado, use_container_width=True)

    # ---------- GRÁFICOS ----------
    resumen_torta = df_filtrado.groupby("CLASIFICACION")[["ABONOS (CLP)", "CARGOS (CLP)"]].sum().reset_index()
    if not resumen_torta.empty:
        st.subheader("📊 Distribución de abonos por clasificación")
        fig_torta = px.pie(resumen_torta, names="CLASIFICACION", values="ABONOS (CLP)", title="Abonos por categoría")
        st.plotly_chart(fig_torta, use_container_width=True)

    resumen_cargos = resumen_torta[resumen_torta["CARGOS (CLP)"] > 0]
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
    st.error(f"No se pudo cargar el archivo: {e}")