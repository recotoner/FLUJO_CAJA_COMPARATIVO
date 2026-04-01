import io
import json
import re
from typing import Dict, Optional, Tuple, Any

import math
import pandas as pd
import requests
import streamlit as st


st.set_page_config(
    page_title="Analizador Financiero Empresarial",
    page_icon="📊",
    layout="wide",
)

# ---------- CSS: tonos verdes, diseño refinado ----------
st.markdown("""
<style>
    /* Tipografía corporativa */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

    :root {
        --verde-oscuro: #2d5016;
        --verde-principal: #3a6b1a;
        --verde-medio: #5a8a2a;
        --verde-claro: #c8e0a0;
        --verde-palo: #f0f7e6;
        --verde-fondo: #f0f7e6;
        --verde-fondo-card: #f8fbf2;
        --texto-principal: #1a1a1a;
    }
    
    html, body, [class^="css"]  {
        font-family: 'Inter', system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        color: var(--texto-principal);
    }

    .main .block-container {
        padding-top: 1.9rem;
        padding-bottom: 3rem;
        max-width: 1100px;
        background: linear-gradient(180deg, #ffffff 0%, var(--verde-palo) 100%);
        border-radius: 16px;
        padding-left: 2rem !important;
        padding-right: 2rem !important;
        box-shadow: 0 8px 24px rgba(0, 0, 0, 0.04);
    }
    
    /* Tipografía */
    h1 {
        color: var(--verde-oscuro);
        border-bottom: 3px solid var(--verde-medio);
        padding-bottom: 0.5rem;
        margin-bottom: 1rem;
        font-weight: 700;
        letter-spacing: -0.02em;
    }
    h2 {
        color: var(--verde-oscuro);
        margin-top: 1.25rem;
        margin-bottom: 0.75rem;
        font-weight: 700;
        font-size: 1.35rem;
    }
    h3 {
        color: #3a6b1a;
        margin-top: 1rem;
        margin-bottom: 0.5rem;
        font-weight: 600;
        font-size: 1.15rem;
    }
    h4 {
        color: var(--verde-medio);
        margin-top: 1rem;
        margin-bottom: 0.6rem;
        font-weight: 600;
        font-size: 1rem;
        padding: 0.4rem 0 0.35rem 0;
        border-bottom: 2px solid var(--verde-claro);
        display: inline-block;
    }
    
    /* Banner de cabecera */
    .analizador-banner {
        background: linear-gradient(135deg, #2d5016 0%, #3a6b1a 40%, #5a8a2a 100%);
        color: #ffffff;
        padding: 2rem 2.25rem;
        border-radius: 18px;
        margin-bottom: 1.9rem;
        box-shadow: 0 10px 30px rgba(14, 46, 11, 0.45);
        border-bottom: 4px solid rgba(240, 247, 230, 0.9);
        position: relative;
        overflow: hidden;
    }
    .analizador-banner::before {
        content: "";
        position: absolute;
        top: -20%;
        right: -15%;
        width: 45%;
        height: 160%;
        background: radial-gradient(circle at top, rgba(255,255,255,0.18), transparent 55%);
        opacity: 0.7;
        pointer-events: none;
    }
    .analizador-banner h2 {
        color: #ffffff !important;
        margin: 0;
        font-size: 1.7rem;
        border: none;
        font-weight: 700;
        letter-spacing: -0.02em;
    }
    .analizador-banner p {
        margin: 0.6rem 0 0 0;
        opacity: 0.96;
        font-size: 0.96rem;
        line-height: 1.6;
        max-width: 78%;
    }
    
    /* Tarjetas de sección */
    .section-card {
        background: linear-gradient(180deg, #ffffff 0%, var(--verde-fondo-card) 100%);
        border: 1px solid var(--verde-claro);
        border-radius: 12px;
        padding: 1.35rem 1.6rem;
        margin: 1rem 0;
        box-shadow: 0 2px 12px rgba(0, 0, 0, 0.07);
        transition: box-shadow 0.25s ease, transform 0.2s ease;
    }
    .section-card:hover {
        box-shadow: 0 4px 16px rgba(0, 0, 0, 0.09);
        transform: translateY(-1px);
    }
    .section-card .section-title {
        color: var(--verde-oscuro);
        font-weight: 700;
        margin-bottom: 0.75rem;
    }
    
    /* Barra de acciones (botones) */
    .action-bar {
        background: #f8fbeF;
        border-radius: 12px;
        padding: 0.9rem 1.2rem;
        margin: 1.25rem 0 0.75rem 0;
        box-shadow: 0 2px 10px rgba(0, 0, 0, 0.05);
        border-left: 6px solid var(--verde-oscuro);
        border-top: 1px solid rgba(200, 224, 160, 0.8);
        border-right: 1px solid rgba(200, 224, 160, 0.6);
        border-bottom: 1px solid rgba(200, 224, 160, 0.6);
        display: flex;
        align-items: center;
        gap: 0.6rem;
    }
    .action-bar p {
        margin: 0;
        font-size: 0.95rem;
        font-weight: 600;
        color: var(--verde-oscuro);
    }
    
    /* Botones */
    .stButton > button {
        border-radius: 10px;
        font-weight: 500;
        transition: all 0.25s ease;
        border: none !important;
    }
    .stButton > button:hover {
        transform: translateY(-1px);
        box-shadow: 0 6px 16px rgba(0, 0, 0, 0.16);
    }
    /* Botón primario: Obtener análisis (segunda columna de la barra) */
    .stButton:nth-of-type(2) > button[kind="primary"] {
        background: linear-gradient(135deg, #3a6b1a 0%, #5a8a2a 100%) !important;
        color: #ffffff !important;
        font-weight: 600 !important;
        box-shadow: 0 3px 10px rgba(28, 70, 16, 0.35);
        padding: 0.55rem 1.4rem;
    }
    .stButton:nth-of-type(2) > button[kind="primary"]:hover {
        background: linear-gradient(135deg, #2d5016 0%, #3a6b1a 100%) !important;
    }
    /* Botón secundario: Calcular KPIs (primera columna) */
    .stButton:nth-of-type(1) > button[kind="primary"] {
        background: #ffffff !important;
        color: var(--verde-oscuro) !important;
        border: 1.5px solid var(--verde-oscuro) !important;
        box-shadow: 0 2px 6px rgba(0, 0, 0, 0.04);
    }
    .stButton:nth-of-type(1) > button[kind="primary"]:hover {
        background: #f5faef !important;
    }
    
    /* Métricas: números centrados */
    [data-testid="stMetricContainer"] {
        background: linear-gradient(145deg, #ffffff 0%, var(--verde-palo) 100%);
        padding: 1.1rem 1rem;
        border-radius: 12px;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
        transition: transform 0.25s ease, box-shadow 0.25s ease;
        border: 1px solid rgba(200, 224, 160, 0.9);
        text-align: center;
    }
    [data-testid="stMetricContainer"]:hover {
        transform: translateY(-3px);
        box-shadow: 0 6px 18px rgba(0, 0, 0, 0.15);
    }
    [data-testid="stMetricLabel"] {
        font-weight: 600;
        color: var(--verde-oscuro);
        font-size: 0.9rem;
        text-align: center;
    }
    [data-testid="stMetricValue"] {
        font-size: 1.6rem;
        font-weight: 700;
        color: var(--verde-oscuro);
        text-align: center;
    }
    
    /* Inputs numéricos */
    [data-testid="stNumberInput"] {
        border-radius: 10px;
        margin-bottom: 0.75rem;
    }
    .stNumberInput input {
        border-radius: 8px !important;
        border: 1.5px solid var(--verde-claro) !important;
        background-color: #ffffff !important;
        padding: 0.4rem 0.5rem !important;
    }
    .stNumberInput input:focus {
        border-color: var(--verde-oscuro) !important;
        box-shadow: 0 0 0 2px rgba(45, 80, 22, 0.25) !important;
        outline: none !important;
    }
    /* Botones + / - de los number_input */
    [data-testid="stNumberInput"] button {
        border-radius: 6px !important;
        background-color: #3a6b1a !important;
        color: #ffffff !important;
        border: none !important;
    }
    [data-testid="stNumberInput"] button:hover {
        background-color: #2d5016 !important;
    }
    
    /* Checkbox */
    .stCheckbox {
        padding: 0.5rem 0;
    }
    .stCheckbox > label {
        font-weight: 500;
        color: #5a8a2a;
        background: #e8f5d0;
        padding: 0.25rem 0.7rem;
        border-radius: 999px;
        font-size: 0.9rem;
        font-style: italic;
    }
    
    /* Divisor */
    .divider-verde {
        height: 2px;
        background: linear-gradient(90deg, transparent 0%, var(--verde-claro) 20%, var(--verde-claro) 80%, transparent 100%);
        margin: 1.6rem 0;
        border-radius: 1px;
    }
    
    /* Expander y JSON */
    .streamlit-expanderHeader {
        font-weight: 600;
        color: var(--verde-oscuro);
    }
    [data-testid="stExpander"] {
        border: 1px solid var(--verde-claro);
        border-radius: 12px;
        background: var(--verde-fondo-card);
    }
    
    /* Alertas */
    [data-testid="stAlert"] {
        border-radius: 10px;
        border-left: 4px solid var(--verde-medio);
    }
    
    /* Badge periodo en KPIs */
    .kpi-period-badge {
        display: inline-block;
        background: linear-gradient(135deg, var(--verde-medio), var(--verde-oscuro));
        color: #ffffff;
        padding: 0.35rem 0.9rem;
        border-radius: 20px;
        font-size: 0.9rem;
        font-weight: 600;
        margin-bottom: 0.75rem;
        box-shadow: 0 2px 6px rgba(0, 0, 0, 0.2);
    }
</style>
""", unsafe_allow_html=True)

# URL del webhook de análisis financiero (n8n - producción)
N8N_WEBHOOK_URL = "https://henry0101.app.n8n.cloud/webhook/4fb41b28-0bc4-430a-9dcc-6c054a21fbb1"


def _normalizar_texto(texto: Any) -> str:
    if texto is None:
        return ""
    return str(texto).strip().lower()


def _crear_mapa_desde_excel(df: pd.DataFrame) -> Dict[str, float]:
    """
    Convierte un DataFrame de estados financieros en un mapa {nombre_cuenta_normalizado: valor}.
    Asume una columna de descripción y una de monto. Intenta detectarlas de forma flexible.
    """
    if df is None or df.empty:
        return {}

    df = df.copy()
    df.columns = [str(c).strip().lower() for c in df.columns]

    # Detectar columna de descripción mediante encabezados
    col_desc = None
    for patron in ["cuenta", "concepto", "descripcion", "descripción", "nombre", "detalle", "glosa"]:
        for c in df.columns:
            if patron in c:
                col_desc = c
                break
        if col_desc:
            break

    # Detectar columna de monto mediante encabezados
    col_monto = None
    for patron in ["monto", "importe", "saldo", "valor", "total"]:
        for c in df.columns:
            if patron in c:
                col_monto = c
                break
        if col_monto:
            break

    mapa: Dict[str, float] = {}

    # Caso 1: tenemos columnas identificadas por nombre
    if col_desc is not None and col_monto is not None:
        for _, row in df.iterrows():
            nombre = _normalizar_texto(row[col_desc])
            if not nombre:
                continue
            try:
                valor = float(row[col_monto])
            except (TypeError, ValueError):
                continue
            nombre_simple = re.sub(r"\s+", " ", nombre)
            mapa[nombre_simple] = valor

        # Si ya obtuvimos algo, devolverlo
        if mapa:
            return mapa

    # Caso 2 (fallback): estructura como las que mostraste,
    # sin encabezados claros. Recorremos fila por fila buscando
    # la primera celda de texto (descripción) y la primera numérica (monto).
    for _, row in df.iterrows():
        nombre_celda = None
        valor_celda = None

        for cell in row:
            if nombre_celda is None and isinstance(cell, str) and cell.strip():
                nombre_celda = cell
            if valor_celda is None and isinstance(cell, (int, float)):
                valor_celda = cell

        if nombre_celda is None or valor_celda is None:
            continue

        nombre = _normalizar_texto(nombre_celda)
        if not nombre:
            continue

        try:
            valor = float(valor_celda)
        except (TypeError, ValueError):
            continue

        nombre_simple = re.sub(r"\s+", " ", nombre)
        mapa[nombre_simple] = valor

    return mapa


def _buscar_valor(mapa: Dict[str, float], patrones: list[str]) -> Optional[float]:
    """
    Busca el primer valor cuyo nombre de cuenta contenga alguno de los patrones.
    """
    for patron in patrones:
        for nombre, valor in mapa.items():
            if patron in nombre:
                return valor
    return None


def extraer_datos_financieros(
    df_balance: Optional[pd.DataFrame],
    df_estado_resultados: Optional[pd.DataFrame],
) -> Dict[str, Optional[float]]:
    """
    Extrae las variables financieras clave desde los DataFrames.
    """
    mapa_balance = _crear_mapa_desde_excel(df_balance) if df_balance is not None else {}
    mapa_er = _crear_mapa_desde_excel(df_estado_resultados) if df_estado_resultados is not None else {}

    datos: Dict[str, Optional[float]] = {
        "ventas": _buscar_valor(
            mapa_er,
            [
                "total ingresos de explotación",
                "ingresos de explotación",
                "ventas",
                "ingresos operacionales",
                "ingresos por ventas",
                "ingresos de actividades ordinarias",
            ],
        ),
        "costo_ventas": _buscar_valor(
            mapa_er,
            [
                "total costos de explotación",
                "costos de explotación",
                "costo de ventas",
                "costo de los bienes vendidos",
                "costo de explotacion",
                "costo de explotación",
            ],
        ),
        "gastos_operacion": _buscar_valor(
            mapa_er,
            [
                "gastos de administración y ventas",
                "gastos de administración",
                "gastos de administracion",
                "gastos de venta",
                "gastos operacionales",
            ],
        ),
        "utilidad_neta": _buscar_valor(
            mapa_er,
            ["utilidad neta", "resultado del ejercicio", "ganancia (perdida) neta", "ganancia (pérdida) neta"],
        ),
        "activo_corriente": _buscar_valor(
            mapa_balance,
            [
                "activo corriente",
                "activos corrientes",
                "activo $",  # formato balance ejemplo
            ],
        ),
        "pasivo_corriente": _buscar_valor(
            mapa_balance,
            [
                "pasivo corriente",
                "pasivos corrientes",
                "pasivo $",  # formato balance ejemplo
            ],
        ),
        "inventario": _buscar_valor(
            mapa_balance,
            ["inventario", "existencias"],
        ),
    }

    # Datos adicionales útiles para KPIs
    datos["patrimonio"] = _buscar_valor(
        mapa_balance,
        ["patrimonio neto", "patrimonio", "capital contable"],
    )
    datos["deuda_total"] = _buscar_valor(
        mapa_balance,
        ["pasivo total", "total pasivo", "pasivos totales"],
    )

    return datos


def _safe_div(num: Optional[float], den: Optional[float]) -> Optional[float]:
    if num is None or den in (None, 0):
        return None
    try:
        return num / den
    except ZeroDivisionError:
        return None


def calcular_kpis(datos: Dict[str, Optional[float]]) -> Dict[str, Optional[float]]:
    ventas = datos.get("ventas")
    costo_ventas = datos.get("costo_ventas")
    gastos_operacion = datos.get("gastos_operacion")
    utilidad_neta = datos.get("utilidad_neta")
    activo_corriente = datos.get("activo_corriente")
    pasivo_corriente = datos.get("pasivo_corriente")
    inventario = datos.get("inventario")
    patrimonio = datos.get("patrimonio")
    deuda_total = datos.get("deuda_total")

    margen_bruto = None
    if ventas is not None and costo_ventas is not None:
        margen_bruto = _safe_div(ventas - costo_ventas, ventas)

    margen_operativo = None
    if ventas is not None and costo_ventas is not None and gastos_operacion is not None:
        utilidad_operativa = ventas - costo_ventas - gastos_operacion
        margen_operativo = _safe_div(utilidad_operativa, ventas)

    margen_neto = None
    if ventas is not None and utilidad_neta is not None:
        margen_neto = _safe_div(utilidad_neta, ventas)

    razon_corriente = _safe_div(activo_corriente, pasivo_corriente)
    capital_trabajo = None
    if activo_corriente is not None and pasivo_corriente is not None:
        capital_trabajo = activo_corriente - pasivo_corriente

    deuda_patrimonio = _safe_div(deuda_total, patrimonio)

    rotacion_inventario = None
    if costo_ventas is not None and inventario is not None:
        # Aproximación usando inventario final
        rotacion_inventario = _safe_div(costo_ventas, inventario)

    return {
        "margen_bruto": margen_bruto,
        "margen_operativo": margen_operativo,
        "margen_neto": margen_neto,
        "razon_corriente": razon_corriente,
        "capital_trabajo": capital_trabajo,
        "deuda_patrimonio": deuda_patrimonio,
        "rotacion_inventario": rotacion_inventario,
    }


def llamar_agente_n8n(webhook_url: str, payload: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    try:
        resp = requests.post(webhook_url, json=payload, timeout=60)
        resp.raise_for_status()
        try:
            return resp.json(), None
        except ValueError:
            # Respuesta no JSON: devolver texto plano para depuración
            return {"raw_text": resp.text}, None
    except requests.RequestException as e:
        return None, str(e)


def _extraer_salud_financiera(data: Optional[Dict[str, Any]]) -> Optional[str]:
    """
    Extrae el valor de salud financiera desde la respuesta del agente.
    Acepta varios nombres de clave (snake_case, camelCase) y estructuras anidadas.
    """
    if not data or not isinstance(data, dict):
        return None
    for key in ("salud_financiera", "saludFinanciera", "salud financiera"):
        val = data.get(key)
        if val is not None and str(val).strip():
            if isinstance(val, dict):
                for sub in ("valor", "nivel", "estado", "descripcion", "texto"):
                    if sub in val and val[sub] is not None:
                        return str(val[sub]).strip()
                return str(val).strip()
            return str(val).strip()
    for nest in ("resumen", "analisis", "resultado", "summary"):
        sub = data.get(nest)
        if isinstance(sub, dict):
            for key in ("salud_financiera", "saludFinanciera"):
                val = sub.get(key)
                if val is not None and str(val).strip():
                    return str(val).strip()
    return None


def _normalizar_respuesta_agente(data: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Convierte la respuesta del agente (a veces { "output": "string con JSON" })
    en un diccionario con salud_financiera, diagnostico, recomendaciones.
    """
    if not data:
        return {}
    if isinstance(data.get("raw_text"), str):
        data = {"output": data["raw_text"]}
    # Si ya viene el objeto esperado en la raíz
    if "salud_financiera" in data or "diagnostico" in data or "recomendaciones" in data:
        return data
    # Si viene envuelto en "output" (string)
    output = data.get("output")
    if not isinstance(output, str):
        return data
    s = output.strip()
    # Quitar prefijos típicos (json, markdown)
    for prefix in ("json", "```json", "```"):
        if s.lower().startswith(prefix):
            s = s[len(prefix) :].strip()
    if s.endswith("```"):
        s = s[:-3].strip()
    # Intentar parsear como JSON
    try:
        parsed = json.loads(s)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass
    # Buscar un bloque {...} en el texto
    start = s.find("{")
    if start >= 0:
        depth = 0
        end = -1
        for i in range(start, len(s)):
            if s[i] == "{":
                depth += 1
            elif s[i] == "}":
                depth -= 1
                if depth == 0:
                    end = i
                    break
        if end > start:
            try:
                parsed = json.loads(s[start : end + 1])
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                pass
    return data


def _formatear_porcentaje(valor: Optional[float]) -> str:
    if valor is None:
        return "N/D"
    return f"{valor * 100:,.0f}%"


def _formatear_numero(valor: Optional[float]) -> str:
    if valor is None:
        return "N/D"
    return f"{valor:,.0f}"


def _formatear_porcentaje_kpi(valor: Optional[float]) -> str:
    """Porcentaje con 2 decimales para KPIs."""
    if valor is None:
        return "N/D"
    return f"{valor * 100:,.2f}%"


def _formatear_numero_kpi(valor: Optional[float]) -> str:
    """Número con 2 decimales para KPIs."""
    if valor is None:
        return "N/D"
    return f"{valor:,.2f}"


def generar_reporte_html(
    datos_periodos: Dict[str, Dict[str, Optional[float]]],
    kpis_periodos: Dict[str, Dict[str, Optional[float]]],
    analisis_agente: Optional[Dict[str, Any]],
) -> str:
    LABELS_DATOS = {
        "ventas": "Ventas / Ingresos de explotación",
        "costo_ventas": "Costo de ventas",
        "gastos_operacion": "Gastos de operación",
        "utilidad_neta": "Utilidad neta",
        "activo_corriente": "Activo corriente",
        "pasivo_corriente": "Pasivo corriente",
        "inventario": "Inventario / Existencias",
        "patrimonio": "Patrimonio",
        "deuda_total": "Deuda total / Pasivo total",
    }

    LABELS_KPIS = {
        "margen_bruto": "Margen bruto",
        "margen_operativo": "Margen operativo",
        "margen_neto": "Margen neto",
        "razon_corriente": "Razón corriente",
        "capital_trabajo": "Capital de trabajo",
        "deuda_patrimonio": "Deuda / Patrimonio",
        "rotacion_inventario": "Rotación de inventario",
    }

    html = """
    <html>
    <head>
        <meta charset="utf-8" />
        <title>Informe Analizador Financiero Empresarial</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 24px; background: #fafafa; max-width: 900px; margin-left: auto; margin-right: auto; }
            h1 { color: #2d5016; border-bottom: 3px solid #4a7c2a; padding-bottom: 0.5rem; }
            h2 { color: #2d5016; margin-top: 1.5rem; }
            h3 { color: #3d6b1e; margin-top: 1rem; }
            table { border-collapse: collapse; width: 100%; margin-bottom: 24px; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 4px rgba(0,0,0,0.08); }
            th, td { border: 1px solid #c8e6c9; padding: 10px; }
            th { background: linear-gradient(135deg, #2d5016 0%, #4a7c2a 100%); color: white; text-align: left; }
            td { text-align: center; }
            tr:nth-child(even) { background-color: #e8f5e9; }
            tr:nth-child(odd) { background-color: #f1f8e9; }
            .bloque-analisis { background: linear-gradient(135deg, #e8f5e9 0%, #c8e6c9 100%); padding: 1.25rem 1.5rem; border-radius: 8px; margin: 1rem 0; border-left: 4px solid #4a7c2a; max-width: 100%; }
            .bloque-analisis p, .bloque-analisis li, .texto-informe { text-align: justify; line-height: 1.6; }
            .bloque-analisis ul { margin: 0.5rem 0; padding-left: 1.5rem; }
            .bloque-analisis .salud-financiera { font-weight: 600; color: #1f3a0f; margin-bottom: 1rem; }
            .texto-informe p { margin: 0.75rem 0; }
        </style>
    </head>
    <body>
        <h1>Informe Analizador Financiero Empresarial</h1>
    """

    for nombre_periodo, datos in datos_periodos.items():
        html += f"<h2>{nombre_periodo} - Datos financieros clave</h2>"
        html += "<table><tbody>"
        for clave, valor in datos.items():
            label = LABELS_DATOS.get(clave, clave)
            html += f"<tr><th>{label}</th><td>{_formatear_numero(valor)}</td></tr>"
        html += "</tbody></table>"

        kpis = kpis_periodos.get(nombre_periodo, {})
        html += f"<h3>{nombre_periodo} - KPIs financieros</h3>"
        html += "<table><tbody>"
        # Orden fijo para incluir siempre todos los KPIs (incl. deuda_patrimonio y rotacion_inventario)
        orden_kpis = (
            "margen_bruto", "margen_operativo", "margen_neto",
            "razon_corriente", "capital_trabajo", "deuda_patrimonio", "rotacion_inventario"
        )
        for clave in orden_kpis:
            valor = kpis.get(clave)
            label = LABELS_KPIS.get(clave, clave)
            if "margen" in clave:
                texto = _formatear_porcentaje_kpi(valor)
            elif clave in ("razon_corriente", "deuda_patrimonio", "rotacion_inventario"):
                # Ratios: se muestran como número decimal (ej. 2.48)
                texto = _formatear_numero_kpi(valor)
            else:
                texto = _formatear_numero_kpi(valor)
            html += f"<tr><th>{label}</th><td>{texto}</td></tr>"
        html += "</tbody></table>"

    if analisis_agente:
        html += '<div class="bloque-analisis"><h2>Análisis del agente de IA</h2>'
        salud = _extraer_salud_financiera(analisis_agente)
        if salud:
            salud_safe = salud.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
            html += f'<p class="salud-financiera"><strong>Salud financiera:</strong> {salud_safe}</p>'

        def markdown_a_html(texto: str) -> str:
            lineas = texto.split("\n")
            html_partes = []
            en_lista = False

            for linea in lineas:
                linea = linea.strip()
                if not linea:
                    if en_lista:
                        html_partes.append("</ul>")
                        en_lista = False
                    html_partes.append("<br>")
                    continue

                if linea.startswith("### "):
                    html_partes.append(f"<h4>{linea[4:]}</h4>")
                elif linea.startswith("## "):
                    html_partes.append(f"<h3>{linea[3:]}</h3>")
                elif re.match(r"^[-•*]\s+", linea) or re.match(r"^\s*[-•*]\s+", linea):
                    if not en_lista:
                        html_partes.append("<ul>")
                        en_lista = True
                    contenido = re.sub(r"^[\s\-•*]+", "", linea)
                    contenido = re.sub(r"\*\*(.*?)\*\*", lambda m: f"<strong>{m.group(1)}</strong>", contenido)
                    html_partes.append(f"<li>{contenido}</li>")
                elif re.match(r"^\d+[\.\)]\s+", linea):
                    if en_lista:
                        html_partes.append("</ul>")
                        en_lista = False
                    contenido = re.sub(r"^\d+[\.\)]\s+", "", linea)
                    contenido = re.sub(r"\*\*(.*?)\*\*", lambda m: f"<strong>{m.group(1)}</strong>", contenido)
                    html_partes.append(f"<p>{contenido}</p>")
                else:
                    if en_lista:
                        html_partes.append("</ul>")
                        en_lista = False
                    linea_fmt = re.sub(r"\*\*(.*?)\*\*", lambda m: f"<strong>{m.group(1)}</strong>", linea)
                    html_partes.append(f"<p>{linea_fmt}</p>")

            if en_lista:
                html_partes.append("</ul>")

            return "\n".join(html_partes)

        informe = analisis_agente.get("informe")
        if isinstance(informe, str) and informe.strip():
            texto_html = markdown_a_html(informe.strip())
            html += "<h3>Diagnóstico</h3><div class=\"texto-informe\">" + texto_html + "</div>"
        else:
            diagnostico = analisis_agente.get("diagnostico") or analisis_agente.get("informe_ejecutivo") or analisis_agente.get("resumen")
            if isinstance(diagnostico, str) and diagnostico.strip():
                html += "<h3>Diagnóstico</h3><div class=\"texto-informe\">"
                for par in diagnostico.strip().split("\n\n"):
                    par = par.strip().replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                    if par:
                        html += f"<p>{par}</p>"
                html += "</div>"
            elif isinstance(diagnostico, list) and diagnostico:
                # Si es una sola cadena larga (informe ejecutivo), mostrar como párrafos justificados
                if len(diagnostico) == 1 and isinstance(diagnostico[0], str) and (len(diagnostico[0]) > 200 or "\n\n" in diagnostico[0]):
                    texto = diagnostico[0].strip()
                    html += "<h3>Diagnóstico</h3><div class=\"texto-informe\">"
                    for par in texto.split("\n\n"):
                        par = par.strip().replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                        if par:
                            html += f"<p>{par}</p>"
                    html += "</div>"
                else:
                    html += "<h3>Diagnóstico</h3><ul>"
                    for item in diagnostico:
                        item_safe = str(item).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                        html += f"<li>{item_safe}</li>"
                    html += "</ul>"

        recomendaciones = analisis_agente.get("recomendaciones") or []
        if isinstance(recomendaciones, list) and recomendaciones:
            html += "<h3>Recomendaciones</h3><ul>"
            for item in recomendaciones:
                item_safe = str(item).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                html += f"<li>{item_safe}</li>"
            html += "</ul>"
        html += "</div>"

    html += "</body></html>"
    return html


def procesar_periodo(
    balance_file,
    er_file,
) -> Tuple[Optional[Dict[str, Optional[float]]], Optional[Dict[str, Optional[float]]], Optional[str]]:
    if balance_file is None or er_file is None:
        return None, None, "Debes subir Balance y Estado de Resultados para este periodo."
    try:
        df_balance = pd.read_excel(balance_file)
        df_er = pd.read_excel(er_file)
    except Exception as e:
        return None, None, f"Error al leer los archivos Excel: {e}"

    datos = extraer_datos_financieros(df_balance, df_er)
    kpis = calcular_kpis(datos)
    return datos, kpis, None


def main() -> None:
    # Banner de cabecera (tonos verdes, profesional)
    st.markdown(
        """
        <div class="analizador-banner">
            <h2>📊 Analizador Financiero Empresarial</h2>
            <p>Ingresa los datos del Estado de Resultados y Balance General para calcular KPIs clave y obtener un diagnóstico automatizado con apoyo de IA.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        """
        <div class="section-card" style="padding: 0.9rem 1.2rem; margin-bottom: 1.25rem; display: flex; align-items: center; gap: 0.75rem;">
            <span style="font-size: 1.4rem;">💡</span>
            <div>
                <p style="margin: 0; font-size: 0.95rem; color: #2d5016; font-weight: 600;">¿Primera vez?</p>
                <p style="margin: 0.2rem 0 0 0; font-size: 0.88rem; color: #5a6b52;">Activa la opción inferior para rellenar con datos de ejemplo y probar la calculadora.</p>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    usar_ejemplo = st.checkbox(
        "Rellenar con datos de ejemplo",
        value=False,
        help="Usa un conjunto de datos de muestra para probar la calculadora y el análisis.",
    )

    datos_p1_inicial = {
        "ventas": 120_000_000.0 if usar_ejemplo else 0.0,
        "costo_ventas": 70_000_000.0 if usar_ejemplo else 0.0,
        "gastos_operacion": 25_000_000.0 if usar_ejemplo else 0.0,
        "utilidad_neta": 15_000_000.0 if usar_ejemplo else 0.0,
        "activo_corriente": 40_000_000.0 if usar_ejemplo else 0.0,
        "pasivo_corriente": 20_000_000.0 if usar_ejemplo else 0.0,
        "inventario": 8_000_000.0 if usar_ejemplo else 0.0,
        "patrimonio": 35_000_000.0 if usar_ejemplo else 0.0,
        "deuda_total": 10_000_000.0 if usar_ejemplo else 0.0,
    }

    datos_periodos: Dict[str, Dict[str, Optional[float]]] = {}
    kpis_periodos: Dict[str, Dict[str, Optional[float]]] = {}

    st.markdown(
        """
        <div class="section-card" style="margin-bottom: 0.5rem;">
            <p class="section-title" style="margin: 0 0 0.25rem 0; font-size: 1.2rem;">📋 Ingreso de datos financieros (Periodo 1)</p>
            <p style="margin: 0; color: #5a6b52; font-size: 0.9rem;">Completa los valores del último periodo anual. Los primeros campos corresponden al Estado de Resultados y los siguientes al Balance General.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        """
        <div style="
            background: linear-gradient(90deg, rgba(74,124,42,0.08) 0%, transparent 100%);
            border-left: 4px solid #4a7c2a;
            padding: 0.5rem 0.85rem;
            border-radius: 0 8px 8px 0;
            margin: 1rem 0 0.5rem 0;
        ">
            <span style="font-weight: 600; color: #2d5016; font-size: 0.95rem;">Estado de Resultados</span>
        </div>
        """,
        unsafe_allow_html=True,
    )
    col_a, col_b = st.columns(2)

    with col_a:
        ventas_val = st.number_input(
            "Ventas / Ingresos de explotación (ER)",
            value=int(datos_p1_inicial["ventas"]),
            step=1_000_000,
            min_value=None,
            format="%d",
            help="Puede ser negativo en casos excepcionales.",
        )
        costo_ventas_val = st.number_input(
            "Costo de ventas / Costos de explotación (ER)",
            value=int(datos_p1_inicial["costo_ventas"]),
            step=1_000_000,
            min_value=None,
            format="%d",
        )
    with col_b:
        gastos_ope_val = st.number_input(
            "Gastos de operación (adm. y ventas) (ER)",
            value=int(datos_p1_inicial["gastos_operacion"]),
            step=500_000,
            min_value=None,
            format="%d",
        )
        utilidad_neta_val = st.number_input(
            "Utilidad neta / Resultado del ejercicio (ER)",
            value=int(datos_p1_inicial["utilidad_neta"]),
            step=500_000,
            min_value=None,
            format="%d",
            help="Use valor negativo si hay pérdida.",
        )

    st.markdown(
        """
        <div style="
            background: linear-gradient(90deg, rgba(74,124,42,0.08) 0%, transparent 100%);
            border-left: 4px solid #4a7c2a;
            padding: 0.5rem 0.85rem;
            border-radius: 0 8px 8px 0;
            margin: 1.25rem 0 0.5rem 0;
        ">
            <span style="font-weight: 600; color: #2d5016; font-size: 0.95rem;">Balance General</span>
        </div>
        """,
        unsafe_allow_html=True,
    )
    col_b1, col_b2, col_b3 = st.columns(3)

    with col_b1:
        activo_corriente_val = st.number_input(
            "Activo corriente (Balance)",
            value=int(datos_p1_inicial["activo_corriente"]),
            step=1_000_000,
            min_value=None,
            format="%d",
        )
    with col_b2:
        pasivo_corriente_val = st.number_input(
            "Pasivo corriente (Balance)",
            value=int(datos_p1_inicial["pasivo_corriente"]),
            step=1_000_000,
            min_value=None,
            format="%d",
        )
    with col_b3:
        inventario_val = st.number_input(
            "Inventario / Existencias (Balance)",
            value=int(datos_p1_inicial["inventario"]),
            step=500_000,
            min_value=None,
            format="%d",
        )
        patrimonio_val = st.number_input(
            "Patrimonio (Balance)",
            value=int(datos_p1_inicial["patrimonio"]),
            step=1_000_000,
            min_value=None,
            format="%d",
        )
        deuda_total_val = st.number_input(
            "Deuda total / Pasivo total (Balance)",
            value=int(datos_p1_inicial["deuda_total"]),
            step=1_000_000,
            min_value=None,
            format="%d",
        )

    datos_p1 = {
        "ventas": ventas_val,
        "costo_ventas": costo_ventas_val,
        "gastos_operacion": gastos_ope_val,
        "utilidad_neta": utilidad_neta_val,
        "activo_corriente": activo_corriente_val,
        "pasivo_corriente": pasivo_corriente_val,
        "inventario": inventario_val,
        "patrimonio": patrimonio_val,
        "deuda_total": deuda_total_val,
    }

    st.markdown("<div class=\"divider-verde\"></div>", unsafe_allow_html=True)

    st.markdown(
        """
        <div class="action-bar">
            <p style="margin: 0; font-size: 0.95rem; font-weight: 600; color: #2d5016;">⚡ Elige una acción</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    col_btn1, col_btn2, col_btn3 = st.columns([1, 1, 2])
    with col_btn1:
        calcular = st.button("📊 Calcular KPIs", type="primary")
    with col_btn2:
        obtener_analisis = st.button("🤖 Obtener análisis financiero", type="primary")

    # Validar: todos los campos deben estar definidos (se permiten negativos y cero)
    errores = [k for k, v in datos_p1.items() if v is None]
    if (calcular or obtener_analisis) and errores:
        st.error(f"Por favor completa todos los campos. Pendientes: {', '.join(errores)}")
        return

    if not (calcular or obtener_analisis):
        # Aún no se ha solicitado ninguna acción
        return

    # Cálculo de KPIs a partir de los datos ingresados
    kpis_p1 = calcular_kpis(datos_p1)

    datos_periodos["Periodo 1"] = datos_p1
    kpis_periodos["Periodo 1"] = kpis_p1

    # Construir payload exactamente en el formato esperado por el agente.
    datos_principales = datos_periodos.get("Periodo 1", {})
    kpis_principales = kpis_periodos.get("Periodo 1", {})

    def _num(o: Optional[float]) -> float:
        """Convierte None o NaN en 0.0 para asegurar valores numéricos válidos en el JSON."""
        if o is None:
            return 0.0
        try:
            v = float(o)
        except (TypeError, ValueError):
            return 0.0
        if math.isnan(v) or math.isinf(v):
            return 0.0
        return v

    payload = {
        "ventas": _num(datos_principales.get("ventas")),
        "costo_ventas": _num(datos_principales.get("costo_ventas")),
        "gastos_operacion": _num(datos_principales.get("gastos_operacion")),
        "utilidad_neta": _num(datos_principales.get("utilidad_neta")),
        "activo_corriente": _num(datos_principales.get("activo_corriente")),
        "pasivo_corriente": _num(datos_principales.get("pasivo_corriente")),
        "inventario": _num(datos_principales.get("inventario")),
        "patrimonio": _num(datos_principales.get("patrimonio")),
        "deuda_total": _num(datos_principales.get("deuda_total")),
        "kpis": {
            "margen_bruto": _num(kpis_principales.get("margen_bruto")),
            "margen_operativo": _num(kpis_principales.get("margen_operativo")),
            "margen_neto": _num(kpis_principales.get("margen_neto")),
            "razon_corriente": _num(kpis_principales.get("razon_corriente")),
            "capital_trabajo": _num(kpis_principales.get("capital_trabajo")),
            "deuda_patrimonio": _num(kpis_principales.get("deuda_patrimonio")),
            "rotacion_inventario": _num(kpis_principales.get("rotacion_inventario")),
        },
    }

    st.markdown(
        """
        <div class="section-card" style="margin-bottom: 0.5rem;">
            <p class="section-title" style="margin: 0; font-size: 1.2rem;">📈 KPIs calculados</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    for nombre_periodo, kpis in kpis_periodos.items():
        st.markdown(f"<span class=\"kpi-period-badge\">{nombre_periodo}</span>", unsafe_allow_html=True)
        col_a, col_b, col_c = st.columns(3)
        with col_a:
            st.metric("Margen bruto", _formatear_porcentaje_kpi(kpis.get("margen_bruto")))
            st.metric("Margen operativo", _formatear_porcentaje_kpi(kpis.get("margen_operativo")))
        with col_b:
            st.metric("Margen neto", _formatear_porcentaje_kpi(kpis.get("margen_neto")))
            st.metric("Razón corriente", _formatear_numero_kpi(kpis.get("razon_corriente")))
        with col_c:
            st.metric("Capital de trabajo", _formatear_numero_kpi(kpis.get("capital_trabajo")))
            st.metric("Deuda / Patrimonio", _formatear_numero_kpi(kpis.get("deuda_patrimonio")))
        st.metric("Rotación de inventario", _formatear_numero_kpi(kpis.get("rotacion_inventario")))

    analisis_agente = None

    if obtener_analisis:
        st.markdown("<div class=\"divider-verde\"></div>", unsafe_allow_html=True)
        st.markdown(
            """
            <div class="section-card" style="margin-bottom: 0.5rem;">
                <p class="section-title" style="margin: 0; font-size: 1.2rem;">🤖 Solicitando análisis financiero automático</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        analisis_agente, error_webhook = llamar_agente_n8n(N8N_WEBHOOK_URL, payload)
        if error_webhook:
            st.error(f"Error al llamar al servicio de análisis: {error_webhook}")
            analisis_agente = None
        else:
            st.success("Análisis recibido correctamente desde el servicio externo.")
            # Normalizar: a veces n8n devuelve { "output": "texto con JSON" }
            analisis_agente = _normalizar_respuesta_agente(analisis_agente)

    if analisis_agente:
        st.markdown("<div class=\"divider-verde\"></div>", unsafe_allow_html=True)
        st.markdown(
            """
            <div class="section-card" style="margin-bottom: 0.5rem;">
                <p class="section-title" style="margin: 0; font-size: 1.2rem;">✅ Resultado del agente de IA</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # Mostrar resumen estructurado si vienen las claves esperadas
        salud = _extraer_salud_financiera(analisis_agente)
        if salud:
            salud_safe = str(salud).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            st.markdown(
                f"""
                <div style="
                    background: linear-gradient(135deg, #e8f5e9 0%, #c8e6c9 100%);
                    border-left: 4px solid #4a7c2a;
                    padding: 0.75rem 1rem;
                    border-radius: 8px;
                    margin-bottom: 1rem;
                ">
                    <strong style="color: #2d5016;">Salud financiera:</strong> <span style="color: #1f3a0f;">{salud_safe}</span>
                </div>
                """,
                unsafe_allow_html=True,
            )

        informe = analisis_agente.get("informe")
        if isinstance(informe, str) and informe.strip():
            st.markdown("**Diagnóstico**")
            st.markdown(informe)

        def _esc(s: str) -> str:
            return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

        recomendaciones = analisis_agente.get("recomendaciones") or []
        if isinstance(recomendaciones, list) and recomendaciones:
            items_html = "".join(f"<li style='margin: 0.35rem 0;'>{_esc(item)}</li>" for item in recomendaciones)
            st.markdown(
                f"""
                <div style="
                    background: linear-gradient(180deg, #f8fbf8 0%, #e8f5e9 100%);
                    border: 1px solid #c8e6c9;
                    border-radius: 10px;
                    padding: 1rem 1.25rem;
                    margin-bottom: 1rem;
                ">
                    <p style="margin: 0 0 0.5rem 0; font-weight: 600; color: #2d5016;">💡 Recomendaciones</p>
                    <ul style="margin: 0.5rem 0 0 0; padding-left: 1.25rem;">{items_html}</ul>
                </div>
                """,
                unsafe_allow_html=True,
            )

        # Siempre mostrar la respuesta completa para depuración
        with st.expander("Ver respuesta completa del servicio de análisis", expanded=False):
            st.json(analisis_agente)

    # Informe descargable (solo HTML, con ayuda para guardar como PDF)
    st.markdown("<div class=\"divider-verde\"></div>", unsafe_allow_html=True)
    st.markdown(
        """
        <div class="section-card" style="margin-bottom: 0.5rem;">
            <p class="section-title" style="margin: 0; font-size: 1.2rem;">📥 Informe descargable</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    reporte_html = generar_reporte_html(datos_periodos, kpis_periodos, analisis_agente)
    st.markdown(
        """
        <div style="
            background: linear-gradient(135deg, #1f3a0f 0%, #2d5016 40%, #4a7c2a 100%);
            color: white;
            padding: 1.4rem 1.75rem;
            border-radius: 14px;
            margin-bottom: 1.25rem;
            box-shadow: 0 6px 20px rgba(45, 80, 22, 0.3);
            border-left: 6px solid #a5d6a7;
        ">
            <p style="margin: 0 0 0.5rem 0; font-size: 1.05rem; font-weight: 600;">
                📥 Descargar informe
            </p>
            <p style="margin: 0; font-size: 0.9rem; line-height: 1.6; opacity: 0.95;">
                Descarga el informe en formato HTML. Si necesitas un PDF, ábrelo en el navegador y usa
                <strong> Archivo → Imprimir → Guardar como PDF</strong> para generarlo con el mismo diseño.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.download_button(
        "Descargar informe (HTML)",
        data=reporte_html,
        file_name="informe_analizador_financiero.html",
        mime="text/html",
        key="dl_html",
    )


if __name__ == "__main__":
    main()

