import streamlit as st
import pandas as pd
import plotly.express as px
import unicodedata
import io
from calendar import monthrange

st.set_page_config(page_title="Flujo de Caja Comparativo", layout="wide")
st.title("📊 Dashboard Comparativo - Flujo Real vs Proyectado")

# ----------------- FUNCIONES -----------------
@st.cache_data
def normalizar(texto):
    if pd.isnull(texto):
        return ""
    texto = str(texto).upper().strip()
    texto = unicodedata.normalize("NFD", texto).encode("ascii", "ignore").decode("utf-8")
    return texto

def clasificar(texto, abono):
    texto = normalizar(texto)

    if abono > 0:
        if any(p in texto for p in ["FACTURA", "COBRAR", "FLUJO", "TRASPASO DE", "APP-TRASPASO", "PAGO", "DEPOSITO", "DEP.CHEQ", "DEPOSITO EN EFECTIVO"]):
            return "1.01.05.01-FACTURAS POR COBRAR NACIONAL- FLUJO"
        elif "LINEA DE CREDITO" in texto:
            return "LINEA DE CREDITO"
        else:
            return "NO CLASIFICADO"
    else:
        if "PAGO: PROVEEDORES" in texto:
            return "2.01.07.01-PROVEEDORES NACIONALES FIJOS"
        elif "PROVISION: PROVEEDORES" in texto:
            return "2.01.07.01-PROVEEDORES NACIONALES EXISTENCIAS"
        elif "PROVEEDORES" in texto:
            return "PROVEEDORES NACIONALES"
        elif "SUELDOS" in texto or "REMUNERACION" in texto:
            return "REMUNERACIONES POR PAGAR"
        elif any(p in texto for p in ["SERVIPAG", "AGUA", "DISTRIBUIDORA", "TRASPASO A"]):
            return "PROVEEDORES NACIONALES"
        elif "HONORARIOS" in texto:
            return "HONORARIOS"
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
            return "2.01.07.01-PROVEEDORES ARRDO  OFICINA , ESTACIONAMIENTO ,KAME"
        elif "PAGO INSTITUCIONES PREVISIONALES" in texto:
            return "IMPOSICIONES"
        elif "Traspaso De: Reciclajes Ecologicos De Chile Limitada" in texto:
            return "FINANCIAMIENTO EXTERNO"
        else:
            return "NO CLASIFICADO"

@st.cache_data
def cargar_real(path):
    df = pd.read_excel(path)
    df.columns = df.columns.str.strip().str.upper()

    if "DESCRIPCIÓN" in df.columns:
        df.rename(columns={"DESCRIPCIÓN": "DESCRIPCION"}, inplace=True)

    df["DESCRIPCION"] = df["DESCRIPCION"].astype(str)
    df["FECHA"] = pd.to_datetime(df["FECHA"], dayfirst=True, errors='coerce')
    df["CLASIFICACION"] = df.apply(lambda row: clasificar(row["DESCRIPCION"], row["ABONOS (CLP)"]), axis=1)
    df["MES"] = df["FECHA"].dt.to_period("M").dt.to_timestamp()

    st.write("Meses detectados en flujo real:")
    st.write(df["MES"].dropna().unique())

    st.write("Cantidad de movimientos por MES en flujo real:")
    st.write(df["MES"].value_counts().sort_index())

    return df

@st.cache_data
def cargar_proyeccion(path):
    df = pd.read_excel(path)
    df.dropna(subset=["CLASIFICACION"], inplace=True)
    df = df.melt(id_vars="CLASIFICACION", var_name="FECHA", value_name="MONTO")
    df["FECHA"] = pd.to_datetime(df["FECHA"], errors="coerce")
    df["MES"] = df["FECHA"].dt.to_period("M").dt.to_timestamp()
    df["CLASIFICACION"] = df["CLASIFICACION"].astype(str).apply(normalizar)
    return df

# ----------------- CARGA -----------------
df_real = cargar_real("cartola_junio_2025.xlsx")
df_proj = cargar_proyeccion("flujo_proyectado.xlsx")

# ----------------- VALIDACIÓN DE CLASIFICACIÓN -----------------
st.subheader("🧪 Validación de Clasificación en Flujo Real")

fecha_limite = st.date_input("Fecha límite para validar", value=df_real["FECHA"].max())
df_validacion = df_real[df_real["FECHA"] <= pd.to_datetime(fecha_limite)]

total = len(df_validacion)
no_clasificados = df_validacion[df_validacion["CLASIFICACION"] == "NO CLASIFICADO"]
n_no = len(no_clasificados)
n_ok = total - n_no

st.markdown(f"""
- ✅ Clasificados: **{n_ok}**
- ❌ No Clasificados: **{n_no}**
- 📊 Total evaluado: **{total}**
- 🎯 Porcentaje clasificado: **{(n_ok/total*100):.2f}%**
""")

if n_no > 0:
    st.warning("Movimientos no clasificados detectados:")
    st.dataframe(no_clasificados[["FECHA", "DESCRIPCION", "ABONOS (CLP)", "CARGOS (CLP)"]], use_container_width=True)



# ----------------- RESUMEN REAL -----------------
df_resumen_real = df_real.groupby(["CLASIFICACION", "MES"])[["CARGOS (CLP)", "ABONOS (CLP)"]].sum().reset_index()
df_resumen_real["REAL_NETO"] = abs(df_resumen_real["ABONOS (CLP)"] - df_resumen_real["CARGOS (CLP)"])

# ----------------- UNIFICACIÓN -----------------
df_merge = pd.merge(df_proj, df_resumen_real, how="left", on=["CLASIFICACION", "MES"]).copy()
df_merge["REAL_NETO"] = df_merge["REAL_NETO"].fillna(0)
df_merge["DIFERENCIA"] = df_merge["REAL_NETO"] - df_merge["MONTO"]

# ----------------- FILTROS -----------------
st.sidebar.header("Filtros")
clasificaciones = sorted(df_merge["CLASIFICACION"].unique())
seleccionadas = st.sidebar.multiselect("Clasificaciones", clasificaciones, default=clasificaciones)
min_date = df_merge["MES"].min()
max_date = df_merge["MES"].max()
fecha_inicio, fecha_fin = st.sidebar.date_input("Rango de fechas", [min_date, max_date])

df_vista = df_merge[
    (df_merge["CLASIFICACION"].isin(seleccionadas)) &
    (df_merge["MES"] >= pd.to_datetime(fecha_inicio)) &
    (df_merge["MES"] <= pd.to_datetime(fecha_fin))
]

# ----------------- TABLA -----------------
st.subheader("🔍 Comparación Detallada")
st.dataframe(df_vista[["CLASIFICACION", "MES", "MONTO", "REAL_NETO", "DIFERENCIA"]], use_container_width=True)

# ----------------- GRÁFICO -----------------
st.subheader("📊 Comparativo Proyectado vs Real")
fig = px.bar(df_vista, x="MES", y=["MONTO", "REAL_NETO"], color_discrete_sequence=["#1f77b4", "#ff7f0e"],
             barmode="group", facet_col="CLASIFICACION", facet_col_wrap=2, height=600)
fig.update_layout(showlegend=True)
st.plotly_chart(fig, use_container_width=True)

# ----------------- RESUMEN POR CLASIFICACIÓN -----------------
st.subheader("📘 Resumen Total por Clasificación")
df_resumen_clasif = df_vista.groupby("CLASIFICACION")[["MONTO", "REAL_NETO", "DIFERENCIA"]].sum().reset_index()
df_resumen_clasif = df_resumen_clasif.sort_values("MONTO", ascending=False)
st.dataframe(df_resumen_clasif, use_container_width=True)

# ----------------- RESUMEN POR MES -----------------
st.subheader("📅 Totales por Mes")
df_resumen_mes = df_vista.groupby("MES")[["MONTO", "REAL_NETO", "DIFERENCIA"]].sum().reset_index()
st.dataframe(df_resumen_mes, use_container_width=True)

# ----------------- SEMÁFORO CLÁSICO -----------------
st.subheader("🚦 Evaluación Mensual (Semáforo)")
def evaluar_semáforo(fila):
    if fila["MONTO"] == 0:
        return "🔘 Sin Proyección"
    pct = fila["DIFERENCIA"] / fila["MONTO"]
    if pct >= -0.05:
        return "🟢 OK"
    elif pct >= -0.15:
        return "🟡 Atención"
    else:
        return "🔴 Crítico"

df_resumen_mes["EVALUACION"] = df_resumen_mes.apply(evaluar_semáforo, axis=1)
st.dataframe(df_resumen_mes, use_container_width=True)

# ----------------- SEMÁFORO AJUSTADO -----------------
st.subheader("📆 Evaluación Ajustada por Avance del Mes")

fecha_max = df_real["FECHA"].max()
def calcular_proporcion(mes):
    if pd.isnull(mes) or mes > fecha_max:
        return 0
    dias_totales = monthrange(mes.year, mes.month)[1]
    dias_ejecutados = min((fecha_max - pd.Timestamp(mes)).days + 1, dias_totales)
    return dias_ejecutados / dias_totales

df_resumen_mes["AVANCE"] = df_resumen_mes["MES"].apply(calcular_proporcion)
df_resumen_mes["MONTO_AJUSTADO"] = df_resumen_mes["MONTO"] * df_resumen_mes["AVANCE"]
df_resumen_mes["DIFERENCIA_AJUSTADA"] = df_resumen_mes["REAL_NETO"] - df_resumen_mes["MONTO_AJUSTADO"]

def evaluar_ajustado(fila):
    if fila["MONTO_AJUSTADO"] == 0:
        return "🔘 Sin Avance"
    pct = fila["DIFERENCIA_AJUSTADA"] / fila["MONTO_AJUSTADO"]
    if pct >= -0.05:
        return "🟢 OK"
    elif pct >= -0.15:
        return "🟡 Atención"
    else:
        return "🔴 Crítico"

df_resumen_mes["EVALUACION_AJUSTADA"] = df_resumen_mes.apply(evaluar_ajustado, axis=1)
st.dataframe(df_resumen_mes[["MES", "MONTO", "MONTO_AJUSTADO", "REAL_NETO", "DIFERENCIA_AJUSTADA", "EVALUACION_AJUSTADA"]], use_container_width=True)

# ----------------- GRÁFICO DE LÍNEA -----------------
st.subheader("📈 Evolución Mensual - Proyectado vs Real")
fig_mes = px.line(df_resumen_mes, x="MES", y=["MONTO", "REAL_NETO"], markers=True)
fig_mes.update_layout(title="Totales mensuales", xaxis_title="Mes", yaxis_title="Monto")
st.plotly_chart(fig_mes, use_container_width=True)

# ----------------- DIFERENCIA -----------------
st.subheader("📌 Diferencia Acumulada")
df_resumen = df_vista.groupby("CLASIFICACION")["DIFERENCIA"].sum().reset_index()
st.dataframe(df_resumen, use_container_width=True)

# ----------------- DESCARGA -----------------
st.subheader("⬇️ Descargar Comparativo")
output = io.BytesIO()
df_vista.to_excel(output, index=False, engine='openpyxl')
st.download_button("Descargar Excel comparativo", output.getvalue(), file_name="comparativo_flujo.xlsx")
st.markdown("---")
st.subheader("🔁 Otras herramientas disponibles")
if st.button("🔗 Ir a versión con más detalle financiero"):
    st.markdown("[Haz clic aquí para abrir ➡️](https://flujocaja-vuzuh5stlggh4pppmua5qz.streamlit.app/)", unsafe_allow_html=True)
