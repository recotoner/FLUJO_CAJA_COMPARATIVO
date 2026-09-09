"""
Parser y carga de Excel libro de sueldos / remuneraciones (v3.0).
Persistencia: proyeccion_cargas (tipo remuneraciones) + proyeccion_remuneraciones.
"""
from __future__ import annotations

import io
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, BinaryIO, Dict, List, Mapping, Optional, Sequence, Tuple, Union

import pandas as pd

from database import crud_proyeccion as crud_p
from modulo_carga_erp import leer_excel_facturas, normalizar_nombres_columnas


def _norm_text(s: str) -> str:
    t = unicodedata.normalize("NFKD", str(s).strip().lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = re.sub(r"\s+", " ", t)
    return t


_ALIAS_EMPLEADO = (
    "nombre trabajador",
    "nombre del trabajador",
    "nombre",
    "empleado",
    "trabajador",
    "funcionario",
    "nombre empleado",
    "apellidos y nombres",
    "nombres",
    "apellidos",
    "apellido paterno",
    "apellido materno",
    "nombre completo",
    "nombre y apellido",
    "razon social",
    "denominacion",
    "personal",
    "colaborador",
    "ficha",
    "sujeto",
)

# Columnas de aportes a cargo del empleador (se suman en monto_aporte_empleador).
# No usar alias cortos ambiguos (p. ej. «sis» ⊂ «inasist»).
_ALIAS_APORTE_EMPLEADOR = (
    "aporte empl a cta indiv",
    "aporte empl. a cta. indiv.",
    "aporte empleador a cta indiv",
    "aporte empleador cuenta individual",
    "aporte trab pesado",
    "aporte trab. pesado",
    "s.c. empleador",
    "sc empleador",
    "s c empleador",
    "seguro cesantia empleador",
    "aporte mutual",
    "s.i.s.",
    "s.i.s",
    "comp. exp. vida",
    "comp exp vida",
    "cot. rentabilidad protegida",
    "cot rentabilidad protegida",
    "aporte sustit",
    "aporte sustit.",
    "cot. expecta. vida sue. empre.",
    "cot expecta vida sue empre",
    "rent. protegida sue. empre.",
    "rent protegida sue empre",
)


_EXCLUIR_APORTE_EMPLEADOR = (
    "inasist",
    "atraso",
    "gratif",
    "bono",
    "semana corrida",
    "horas extra",
    "colacion",
    "moviliz",
    "prestamo",
    "anticipo",
    "sobregiro",
    "voluntaria",
    "ahorro",
    "apv",
    "afil",
    "alcance",
    "haberes",
    "imponible",
    "sueldo",
    "nombre",
    "cargo",
    "dias trabaj",
)

_ALIAS_RUT = (
    "rut",
    "rut empleado",
    "rut trabajador",
    "run",
    "run empleado",
    "identificacion",
    "identificación",
    "id tributario",
)

_ALIAS_LIQUIDO = (
    "alcance liquido",
    "alcance líquido",
    "liquido",
    "líquido",
    "liquido a pago",
    "líquido a pago",
    "liquido a percibir",
    "pago liquido",
    "sueldo liquido",
    "liquido a pagar",
    "a pago",
    "líquido del mes",
    "total liquido",
    "haber liquido",
    "haber líquido",
    "liquido haber",
    "remuneracion liquida",
    "remuneración líquida",
    "a percibir",
    "pago efectivo",
    "total a pagar",
    "líquido del periodo",
    "liquido del periodo",
    "monto liquido",
)

_ALIAS_BRUTO = (
    "bruto",
    "total haber",
    "haberes",
    "devengado",
    "total devengo",
    "total remuneraciones",
    "remuneracion total",
    "remuneración total",
    "total haberes",
    "devengos",
)

MAPEO_REM_PRESETS: Dict[str, Dict[str, Sequence[str]]] = {
    "dag": {
        "empleado": ("nombre trabajador", "nombre del trabajador", "trabajador", "nombre"),
        "rut_empleado": ("rut", "rut trabajador", "rut empleado"),
        "monto_liquido": ("alcance liquido", "alcance líquido", "liquido a pago", "liquido"),
        "monto_bruto": ("total haberes", "haberes", "total haber", "bruto"),
        "monto_imponible": ("total imponibles", "imponible", "total imponible", "renta imponible"),
        "monto_afp": ("cotiza. a.f.p.", "cotiza afp", "cotizacion afp", "afp"),
        "monto_salud_adicional": ("adic. isapre", "adicional isapre", "adicional salud", "adic isapre"),
        "monto_cesantia": ("seg. desempleo", "seguro desempleo", "seguro cesantia", "cesantia"),
        "monto_salud": ("cotiza. salud", "cotiza salud", "cotizacion salud", "salud"),
        "monto_impuesto_unico": (
            "imp. a la renta",
            "impuesto a la renta",
            "impuesto unico",
            "impuesto único",
            "imp. unico",
        ),
        "monto_aporte_empleador": _ALIAS_APORTE_EMPLEADOR,
        "mes_aplicacion": ("mes", "periodo", "mes remuneracion"),
        "dia_pago": ("dia pago", "día pago"),
    },
    "planilla_cl": {
        "empleado": _ALIAS_EMPLEADO,
        "rut_empleado": _ALIAS_RUT,
        "monto_liquido": _ALIAS_LIQUIDO,
        "monto_bruto": _ALIAS_BRUTO,
        "monto_imponible": ("imponible", "base imponible", "total imponible", "renta imponible", "total imponibles"),
        "monto_afp": (
            "afp",
            "cot afp",
            "cotizacion afp",
            "cotización afp",
            "cotiza. a.f.p.",
            "cotiza afp",
            "cotizacion obligatoria",
            "prevision",
            "previsión",
            "descuento afp",
        ),
        # Antes que «salud» base para no asignar la columna «adicional salud» solo a salud.
        "monto_salud_adicional": (
            "adicional salud",
            "adicional de salud",
            "salud adicional",
            "adic. isapre",
            "adic isapre",
            "cot adicional salud",
            "cotización adicional salud",
            "cotizacion adicional salud",
            "cotizacion salud adicional",
            "adicional isapre",
            "adicional fonasa",
            "adicional salud obligatoria",
            "adicional obligatorio salud",
        ),
        "monto_cesantia": (
            "seguro cesantia",
            "seguro cesantía",
            "seg. desempleo",
            "seguro desempleo",
            "s. cesantia",
            "s. cesantía",
            "seguro de cesantia",
            "cot cesantia",
            "cotización cesantia",
            "cotizacion cesantia",
            "cotizacion seguro cesantia",
            "cesantia",
            "cesantía",
        ),
        "monto_salud": (
            "salud",
            "fonasa",
            "isapre",
            "cot salud",
            "cotiza. salud",
            "cotiza salud",
            "cotizacion salud",
            "cotización de salud",
            "c. salud",
        ),
        "monto_impuesto_unico": (
            "imp. a la renta",
            "impuesto a la renta",
            "impuesto unico",
            "impuesto único",
            "impuesto ui",
            "imp. unico",
            "imp. único",
            "iu",
            "i.u",
            "impuesto segunda categoria",
            "impuesto segunda categoría",
            "impuesto 2da",
            "impuesto 2da categoria",
            "retencion impuesto unico",
        ),
        "monto_aporte_empleador": _ALIAS_APORTE_EMPLEADOR,
        "mes_aplicacion": (
            "mes",
            "periodo",
            "mes remuneracion",
            "mes remuneración",
            "periodo liquidacion",
            "mes año",
            "fecha periodo",
        ),
        "dia_pago": ("dia pago", "día pago", "dia de pago", "dia pago sueldo"),
    },
    "generico": {
        "empleado": _ALIAS_EMPLEADO,
        "rut_empleado": _ALIAS_RUT,
        "monto_liquido": _ALIAS_LIQUIDO,
        "monto_bruto": _ALIAS_BRUTO,
        "monto_imponible": ("imponible", "base imponible", "total imponibles"),
        "monto_afp": ("afp", "cotizacion obligatoria", "prevision", "cot afp", "cotiza afp"),
        "monto_salud_adicional": ("adicional salud", "adicional de salud", "cot adicional salud", "adic isapre"),
        "monto_cesantia": ("seguro cesantia", "seguro cesantía", "cesantia", "seg desempleo"),
        "monto_salud": ("salud", "fonasa", "isapre", "cot salud", "cotizacion salud", "cotiza salud"),
        "monto_impuesto_unico": ("impuesto unico", "impuesto único", "impuesto ui", "imp. unico", "imp a la renta", "iu"),
        "monto_aporte_empleador": _ALIAS_APORTE_EMPLEADOR,
        "mes_aplicacion": ("mes", "periodo", "mes año", "fecha periodo"),
        "dia_pago": ("dia pago", "día pago"),
    },
}


def _desambiguar_nombres_columnas_duplicados(columnas: Sequence[str]) -> List[str]:
    """Tras normalizar, evita nombres repetidos («afp», «afp») que rompen row.get en pandas."""
    seen: Dict[str, int] = {}
    out: List[str] = []
    for c in columnas:
        if c not in seen:
            seen[c] = 0
            out.append(c)
        else:
            seen[c] += 1
            out.append(f"{c}__{seen[c]}")
    return out


def preparar_df_remuneraciones_columnas(df: pd.DataFrame) -> pd.DataFrame:
    """Normaliza encabezados y renombra columnas duplicadas; mismo orden que usa el mapeo."""
    out = normalizar_nombres_columnas(df)
    out.columns = _desambiguar_nombres_columnas_duplicados(list(out.columns))
    return out


def _mejor_columna_para_logico(
    ncols: Sequence[str],
    variants: Sequence[str],
    logical: str,
    used_cols: set[str],
) -> Optional[str]:
    """
    Elige la columna que mejor encaja con el concepto lógico.
    Prioridad: nombre exacto (ej. «afp») > token contenido en encabezado (ej. «cot afp») > nc ⊂ nv.
    Así no se queda una «cot …» vacía ignorando la columna literal AFP/SALUD del libro.
    """
    mejor_nc: Optional[str] = None
    mejor_clave: Optional[Tuple[int, int, str]] = None
    for nc in ncols:
        if not nc or nc in used_cols:
            continue
        if logical == "monto_salud" and "adicional" in nc:
            continue
        # Evitar que «empleado» capture «empleador» / «s.c. empleador».
        if logical == "empleado" and "empleador" in nc:
            continue
        if logical == "empleado" and re.search(r"\bs\.?\s*c\.?\b", nc):
            continue
        clave_nc: Optional[Tuple[int, int]] = None
        for v in variants:
            nv = _norm_text(v)
            if not nv:
                continue
            # Evitar match parcial empleado ⊂ empleador.
            if logical == "empleado" and nv == "empleado" and "empleador" in nc:
                continue
            if nc == nv or nv in nc:
                # rank 0 exacto; 1 substring nv in nc (encabezado más largo)
                r = 0 if nc == nv else 1
                # Preferir encabezados más específicos para trabajador/líquido.
                if logical == "empleado" and "nombre" in nc:
                    r = -1 if nc == nv or nv in nc else r
                if logical == "monto_liquido" and "alcance" in nc:
                    r = -1
                tup = (r, len(nc))
            elif nc in nv:
                if logical == "monto_salud_adicional" and len(nc) < len(nv):
                    continue
                tup = (2, len(nc))
            else:
                continue
            clave_nc = tup if clave_nc is None or tup < clave_nc else clave_nc
        if clave_nc is not None:
            r, ln = clave_nc
            cand = (r, ln, nc)
            if mejor_clave is None or cand < mejor_clave:
                mejor_clave = (r, ln, nc)
                mejor_nc = nc
    return mejor_nc


def _alias_encaja_columna(nc: str, nv: str) -> bool:
    """Match de alias vs encabezado; evita falsos positivos de substrings cortos."""
    if not nv:
        return False
    if nc == nv:
        return True
    # «s.i.s.» / SIS: solo token propio, nunca «sis» dentro de «inasist».
    if nv.replace(".", "") == "sis":
        return bool(re.search(r"(^|[^a-z0-9])s\.?i\.?s\.?([^a-z0-9]|$)", nc))
    if len(nv) <= 3:
        return bool(re.search(rf"(^|[^a-z0-9]){re.escape(nv)}([^a-z0-9]|$)", nc))
    if nv in nc:
        return True
    # nc ⊂ nv solo si el encabezado es razonablemente específico.
    if len(nc) >= 8 and nc in nv:
        return True
    return False


def _columnas_para_aporte_empleador(ncols: Sequence[str], used_cols: set[str]) -> List[str]:
    """Devuelve todas las columnas de aportes del empleador (multi-columna)."""
    out: List[str] = []
    for nc in ncols:
        if not nc or nc in used_cols:
            continue
        # No tomar cotizaciones del trabajador ni descuentos/haberes ajenos.
        if any(
            x in nc
            for x in (
                "cotiza. a.f.p",
                "cotiza afp",
                "cotiza. salud",
                "cotiza salud",
                "adic. isapre",
                "seg. desempleo",
                "seguro desempleo",
            )
        ):
            continue
        if any(x in nc for x in _EXCLUIR_APORTE_EMPLEADOR):
            continue
        if "imp" in nc and "renta" in nc:
            continue
        # «Trabajo pesado» del trabajador ≠ «Aporte Trab. Pesado» del empleador.
        if "trabajo pesado" in nc and "aporte" not in nc:
            continue
        matched = False
        for v in _ALIAS_APORTE_EMPLEADOR:
            if _alias_encaja_columna(nc, _norm_text(v)):
                matched = True
                break
        # Heurística DAG: columnas con «empleador», «mutual», SIS, «aporte empl».
        if not matched:
            if "empleador" in nc or "mutual" in nc or "aporte empl" in nc:
                matched = True
            if re.search(r"(^|[^a-z0-9])s\.?i\.?s\.?([^a-z0-9]|$)", nc):
                matched = True
            if "aporte sustit" in nc or "comp. exp" in nc or "comp exp" in nc:
                matched = True
            if "rentabilidad protegida" in nc or "sue. empre" in nc or "sue empre" in nc:
                matched = True
        if matched:
            out.append(nc)
    return out


_MESES_ES = {
    "enero": 1,
    "febrero": 2,
    "marzo": 3,
    "abril": 4,
    "mayo": 5,
    "junio": 6,
    "julio": 7,
    "agosto": 8,
    "septiembre": 9,
    "setiembre": 9,
    "octubre": 10,
    "noviembre": 11,
    "diciembre": 12,
}


def detectar_periodo_libro_remuneraciones(fuente_bytes: bytes, *, hoja: Union[int, str, None] = 0) -> Optional[date]:
    """
    Busca en las primeras filas del Excel un texto tipo «Julio de 2026».
    Retorna el primer día del mes detectado, o None.
    """
    try:
        df_raw = pd.read_excel(
            io.BytesIO(fuente_bytes),
            sheet_name=hoja if hoja is not None else 0,
            header=None,
            nrows=8,
            engine="openpyxl",
        )
    except Exception:
        return None
    patron = re.compile(
        r"\b(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|setiembre|octubre|noviembre|diciembre)"
        r"\s*(?:de\s*)?(20\d{2}|\d{2})\b",
        re.IGNORECASE,
    )
    for _, row in df_raw.iterrows():
        for val in row.tolist():
            if val is None or (isinstance(val, float) and pd.isna(val)):
                continue
            txt = str(val).strip()
            if not txt or txt.lower().startswith("unnamed"):
                continue
            m = patron.search(_norm_text(txt))
            if not m:
                # También probar sin normalizar acentos removidos sobre el texto original lower.
                m = patron.search(txt.lower())
            if not m:
                continue
            mes_nom = _norm_text(m.group(1))
            anio_raw = m.group(2)
            mes = _MESES_ES.get(mes_nom)
            if not mes:
                continue
            anio = int(anio_raw)
            if anio < 100:
                anio += 2000
            return date(anio, mes, 1)
    return None


def _es_fila_total_o_invalida(empleado: str, rut: Optional[str]) -> bool:
    """Excluye TOTAL/SUBTOTAL y filas sin trabajador/RUT usable."""
    emp_n = _norm_text(empleado or "")
    if not emp_n:
        return True
    if any(tok in emp_n for tok in ("total", "subtotal", "totales", "suma", "resumen")):
        return True
    rut_s = (rut or "").strip()
    if not rut_s:
        return True
    # RUT chileno mínimo: dígitos + guión opcional + DV.
    if not re.search(r"\d{6,}-?[\dkK]", rut_s):
        return True
    return False


def detectar_mapeo_remuneraciones(
    columnas: Sequence[str],
    preset: Optional[str] = None,
) -> Dict[str, str]:
    ncols = [_norm_text(c) for c in columnas]
    preset_key = (preset or "generico").lower()
    aliases = MAPEO_REM_PRESETS.get(preset_key) or MAPEO_REM_PRESETS["generico"]
    mapping: Dict[str, str] = {}
    used_cols: set[str] = set()

    for logical, variants in aliases.items():
        if logical in mapping:
            continue
        if logical == "monto_aporte_empleador":
            cols_ap = _columnas_para_aporte_empleador(ncols, used_cols)
            if cols_ap:
                mapping["monto_aporte_empleador"] = cols_ap[0]
                mapping["__aporte_empleador_cols__"] = "||".join(cols_ap)
                used_cols.update(cols_ap)
            continue
        nc = _mejor_columna_para_logico(ncols, variants, logical, used_cols)
        if nc:
            mapping[logical] = nc
            used_cols.add(nc)

    if "empleado" not in mapping:
        for nc in ncols:
            if nc in used_cols:
                continue
            if "empleador" in nc:
                continue
            if "nombre" in nc and "empresa" not in nc:
                mapping["empleado"] = nc
                used_cols.add(nc)
                break

    if "empleado" not in mapping:
        for nc in ncols:
            if nc in used_cols:
                continue
            if "empleador" in nc:
                continue
            if any(
                h in nc
                for h in (
                    "apellido",
                    "nombres",
                    "personal",
                    "colaborador",
                    "funcionario",
                    "trabajador",
                )
            ) and "empresa" not in nc:
                mapping["empleado"] = nc
                used_cols.add(nc)
                break

    if "empleado" not in mapping and "rut_empleado" in mapping:
        mapping["empleado"] = mapping["rut_empleado"]

    return mapping


def _remuneraciones_fuente_a_bytes(fuente: Union[str, Path, bytes, BinaryIO]) -> bytes:
    if isinstance(fuente, bytes):
        return fuente
    if isinstance(fuente, (str, Path)):
        return Path(fuente).read_bytes()
    chunk = fuente.read()
    if not isinstance(chunk, bytes):
        return bytes(chunk)
    return chunk


def _remuneraciones_headers_look_reasonable(df_raw: pd.DataFrame) -> bool:
    good = 0
    for c in df_raw.columns:
        t = _norm_text(str(c))
        if not t or t.startswith("unnamed"):
            continue
        if re.fullmatch(r"\d+", t):
            continue
        good += 1
    return good >= 2 and df_raw.shape[1] >= 2


def _score_mapeo_remuneraciones(mapeo: Mapping[str, str]) -> int:
    """
    Elige la fila de encabezado del Excel. Debe privilegiar la fila donde existan
    cotizaciones (AFP, salud, etc.); si no, a veces se tomaba una fila «buena» solo por
    empleado+líquido y las columnas AFP/SALUD quedaban sin mapear.
    """
    s = 0
    if "empleado" in mapeo:
        s += 100
    if "monto_liquido" in mapeo:
        s += 80
    elif "monto_bruto" in mapeo:
        s += 55
    if "rut_empleado" in mapeo:
        s += 12
    if "mes_aplicacion" in mapeo:
        s += 8
    if "monto_afp" in mapeo:
        s += 40
    if "monto_salud" in mapeo:
        s += 40
    if "monto_salud_adicional" in mapeo:
        s += 15
    if "monto_cesantia" in mapeo:
        s += 15
    if "monto_impuesto_unico" in mapeo:
        s += 10
    if "monto_aporte_empleador" in mapeo or "__aporte_empleador_cols__" in mapeo:
        s += 25
    # Preferir encabezados DAG reales.
    emp_col = (mapeo.get("empleado") or "")
    if "nombre trabajador" in emp_col or emp_col == "nombre trabajador":
        s += 50
    if "empleador" in emp_col:
        s -= 80
    liq_col = (mapeo.get("monto_liquido") or "")
    if "alcance" in liq_col:
        s += 40
    return s


def encontrar_mejor_encabezado_remuneraciones(
    fuente_bytes: bytes,
    *,
    preset: Optional[str] = None,
    hoja: Union[int, str, None] = 0,
    max_fila: int = 15,
) -> tuple[int, pd.DataFrame, Dict[str, str]]:
    """
    Muchos Excel traen título o filas vacías antes del encabezado real.
    Prueba header=0..max_fila y elige el mapeo con mejor puntuación.
    """
    best_fh: Optional[int] = None
    best_df: Optional[pd.DataFrame] = None
    best_mapeo: Dict[str, str] = {}
    best_key: Tuple[int, int] = (-1, -1)

    for fh in range(max(1, max_fila)):
        try:
            df_raw = pd.read_excel(
                io.BytesIO(fuente_bytes),
                sheet_name=hoja if hoja is not None else 0,
                header=fh,
                engine="openpyxl",
            )
        except Exception:
            continue
        if df_raw is None or df_raw.shape[1] < 2:
            continue
        if not _remuneraciones_headers_look_reasonable(df_raw):
            continue
        df = preparar_df_remuneraciones_columnas(df_raw)
        cols = list(df.columns)
        mapeo = detectar_mapeo_remuneraciones(cols, preset=preset)
        sc = _score_mapeo_remuneraciones(mapeo)
        key = (sc, fh)
        if key > best_key:
            best_key = key
            best_fh = fh
            best_df = df
            best_mapeo = mapeo

    if best_df is None or best_fh is None:
        raise ValueError(
            "No se encontró una fila de encabezados útil en las primeras filas del Excel. "
            "Revise que la primera hoja tenga columnas con nombres (no solo «Unnamed»)."
        )
    return best_fh, best_df, best_mapeo


def _to_date(val: Any) -> Optional[date]:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    if isinstance(val, date) and not isinstance(val, pd.Timestamp):
        return val
    ts = pd.to_datetime(val, errors="coerce", dayfirst=True)
    if pd.isna(ts):
        return None
    return ts.date()


def _to_decimal(val: Any) -> Optional[Decimal]:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    if isinstance(val, Decimal):
        return val
    s = str(val).strip()
    if not s:
        return None
    s = s.replace(".", "").replace(",", ".") if "," in s and "." in s else s.replace(",", ".")
    try:
        return Decimal(s)
    except InvalidOperation:
        try:
            return Decimal(str(float(val)))
        except (ValueError, TypeError, InvalidOperation):
            return None


def _mes_aplicacion_desde_valor(val: Any, *, primer_dia_mes: bool) -> Optional[date]:
    d = _to_date(val)
    if not d:
        return None
    if primer_dia_mes:
        return date(d.year, d.month, 1)
    return d


def dataframe_a_registros_remuneracion(
    df: pd.DataFrame,
    mapeo: Mapping[str, str],
    *,
    mes_aplicacion_default: Optional[date],
    primer_dia_mes: bool = True,
    dia_pago_default: Optional[int] = None,
) -> tuple[List[Dict[str, Any]], List[str]]:
    """
    Dicts listos para crud_p.crear_proyeccion_remuneraciones_bulk (sin carga_id ni user_id).
    Requiere por fila: empleado y (monto_liquido o monto_bruto) y mes (columna o default).
    """
    advertencias: List[str] = []
    if "empleado" not in mapeo:
        cols_m = list(df.columns)[:45]
        raise ValueError(
            "No se detectó columna de empleado/nombre (ni RUT reconocible como respaldo). "
            "Revise encabezados, que la fila de títulos sea detectable o pruebe otro export del ERP. "
            f"Mapeo automático: {list(mapeo.keys())}. Columnas en el archivo (normalizadas): {cols_m}"
        )
    col_liq = mapeo.get("monto_liquido")
    col_bruto = mapeo.get("monto_bruto")
    if col_liq is None and col_bruto is None:
        raise ValueError(
            "Se requiere columna de líquido o de bruto/haberes en el mapeo. "
            f"Mapeo actual: {list(mapeo.keys())}. "
            f"Columnas (normalizadas): {list(df.columns)[:45]}"
        )
    if mes_aplicacion_default is None and "mes_aplicacion" not in mapeo:
        raise ValueError(
            "Indique la columna de mes/periodo en el Excel o pase mes_aplicacion_default (primer día del mes)."
        )

    col_emp = mapeo["empleado"]
    col_rut = mapeo.get("rut_empleado")
    col_imp = mapeo.get("monto_imponible")
    col_afp = mapeo.get("monto_afp")
    col_salud = mapeo.get("monto_salud")
    col_salud_adic = mapeo.get("monto_salud_adicional")
    col_ces = mapeo.get("monto_cesantia")
    col_iu = mapeo.get("monto_impuesto_unico")
    col_mes = mapeo.get("mes_aplicacion")
    col_dia = mapeo.get("dia_pago")
    cols_aporte_emp = [
        c for c in str(mapeo.get("__aporte_empleador_cols__") or "").split("||") if c
    ]
    if not cols_aporte_emp and mapeo.get("monto_aporte_empleador"):
        cols_aporte_emp = [mapeo["monto_aporte_empleador"]]

    out: List[Dict[str, Any]] = []

    for idx, row in df.iterrows():
        emp = row.get(col_emp)
        if emp is None or (isinstance(emp, float) and pd.isna(emp)):
            advertencias.append(f"Fila {idx}: sin nombre de empleado, omitida.")
            continue
        empleado = str(emp).strip()[:200]
        rut_val: Optional[str] = None
        if col_rut:
            r = row.get(col_rut)
            if r is not None and not (isinstance(r, float) and pd.isna(r)):
                rut_val = str(r).strip()[:20]
        if _es_fila_total_o_invalida(empleado, rut_val):
            advertencias.append(
                f"Fila {idx}: excluida (TOTAL/SUBTOTAL o sin trabajador/RUT válido)."
            )
            continue

        limpio = _to_decimal(row.get(col_liq)) if col_liq else None
        bruto = _to_decimal(row.get(col_bruto)) if col_bruto else None
        if limpio is None and bruto is not None:
            limpio = bruto
            advertencias.append(f"Fila {idx}: se usó monto bruto como líquido (revisar).")
        if limpio is None:
            advertencias.append(f"Fila {idx}: sin líquido ni bruto válido, omitida.")
            continue

        mes_app: Optional[date] = None
        if col_mes:
            mes_app = _mes_aplicacion_desde_valor(row.get(col_mes), primer_dia_mes=primer_dia_mes)
        if mes_app is None and mes_aplicacion_default is not None:
            mes_app = mes_aplicacion_default
        if mes_app is None:
            advertencias.append(f"Fila {idx}: sin mes de aplicación, omitida.")
            continue

        reg: Dict[str, Any] = {
            "empleado": empleado,
            "mes_aplicacion": mes_app,
            "monto_liquido": limpio,
        }
        if rut_val:
            reg["rut_empleado"] = rut_val
        if bruto is not None and col_bruto:
            reg["monto_bruto"] = bruto
        if col_imp:
            imp = _to_decimal(row.get(col_imp))
            if imp is not None:
                reg["monto_imponible"] = imp
        if col_afp:
            afp = _to_decimal(row.get(col_afp))
            if afp is not None:
                reg["monto_afp"] = afp
        if col_salud:
            s = _to_decimal(row.get(col_salud))
            if s is not None:
                reg["monto_salud"] = s
        if col_salud_adic:
            sa = _to_decimal(row.get(col_salud_adic))
            if sa is not None:
                reg["monto_salud_adicional"] = sa
        if col_ces:
            ce = _to_decimal(row.get(col_ces))
            if ce is not None:
                reg["monto_cesantia"] = ce
        if col_iu:
            iu = _to_decimal(row.get(col_iu))
            if iu is not None:
                reg["monto_impuesto_unico"] = iu
        aporte_emp = Decimal(0)
        tiene_aporte = False
        for c_ap in cols_aporte_emp:
            val_ap = _to_decimal(row.get(c_ap))
            if val_ap is None:
                continue
            aporte_emp += val_ap
            tiene_aporte = True
        if tiene_aporte:
            reg["monto_aporte_empleador"] = aporte_emp
        dia: Optional[int] = None
        if col_dia:
            dval = row.get(col_dia)
            if dval is not None and not (isinstance(dval, float) and pd.isna(dval)):
                try:
                    dia = int(float(str(dval).replace(",", ".")))
                except ValueError:
                    pass
        if dia is None and dia_pago_default is not None:
            dia = dia_pago_default
        if dia is not None:
            reg["dia_pago"] = dia

        out.append(reg)

    return out, advertencias


@dataclass
class ResultadoCargaRemuneraciones:
    carga_id: int
    filas_guardadas: int
    filas_leidas: int
    filas_validas: int
    mapeo_columnas: Dict[str, str] = field(default_factory=dict)
    advertencias: List[str] = field(default_factory=list)
    mes_aplicacion_usado: Optional[date] = None
    periodo_detectado_encabezado: Optional[date] = None


def inspeccionar_excel_remuneraciones(
    fuente: Union[str, Path, bytes],
    *,
    preset: Optional[str] = None,
    hoja: Union[int, str, None] = 0,
    fila_header: int = 0,
    auto_fila_header: bool = True,
    max_fila_header: int = 15,
) -> Dict[str, Any]:
    fh_usada = fila_header
    raw = _remuneraciones_fuente_a_bytes(fuente)
    periodo_hdr = detectar_periodo_libro_remuneraciones(raw, hoja=hoja)
    if auto_fila_header:
        fh_usada, df, mapeo = encontrar_mejor_encabezado_remuneraciones(
            raw, preset=preset or "dag", hoja=hoja, max_fila=max_fila_header
        )
        cols = list(df.columns)
        preset_final = _elegir_preset_remuneraciones(cols, preset)
        if preset_final != (preset or "dag").lower():
            fh_usada, df, mapeo = encontrar_mejor_encabezado_remuneraciones(
                raw, preset=preset_final, hoja=hoja, max_fila=max_fila_header
            )
            cols = list(df.columns)
    else:
        df_raw = leer_excel_facturas(fuente, hoja=hoja, fila_header=fila_header)
        df = preparar_df_remuneraciones_columnas(df_raw)
        cols = list(df.columns)
        mapeo = detectar_mapeo_remuneraciones(cols, preset=_elegir_preset_remuneraciones(cols, preset))
    necesita_mes = "mes_aplicacion" not in mapeo and periodo_hdr is None
    faltantes: List[str] = []
    if "empleado" not in mapeo:
        faltantes.append("empleado")
    if "monto_liquido" not in mapeo and "monto_bruto" not in mapeo:
        faltantes.append("monto_liquido o monto_bruto")
    if necesita_mes:
        faltantes.append("mes_aplicacion (o usar mes_aplicacion_default al cargar)")
    return {
        "columnas": cols,
        "mapeo": {k: v for k, v in mapeo.items() if not k.startswith("__")},
        "requiere_mes_default": necesita_mes,
        "periodo_detectado": periodo_hdr,
        "mapeo_ok": "empleado" in mapeo and ("monto_liquido" in mapeo or "monto_bruto" in mapeo),
        "faltantes": faltantes,
        "muestra_filas": min(5, len(df)),
        "fila_header": fh_usada,
    }


def _elegir_preset_remuneraciones(columnas: Sequence[str], preset: Optional[str]) -> str:
    if preset:
        return preset.lower()
    ncols = [_norm_text(c) for c in columnas]
    if any("alcance liquido" in c or c == "alcance liquido" for c in ncols):
        return "dag"
    if any("nombre trabajador" in c for c in ncols):
        return "dag"
    if any("cotiza. a.f.p" in c or "cotiza afp" in c for c in ncols):
        return "dag"
    return "planilla_cl"


def cargar_excel_remuneraciones(
    user_id: int,
    fuente: Union[str, Path, bytes, BinaryIO],
    nombre_archivo: str,
    *,
    preset_columnas: Optional[str] = None,
    mes_aplicacion_default: Optional[date] = None,
    primer_dia_mes: bool = True,
    dia_pago_default: Optional[int] = None,
    hoja: Union[int, str, None] = 0,
    fila_header: int = 0,
    auto_fila_header: bool = True,
    max_fila_header: int = 15,
    origen: str = "upload_excel",
) -> ResultadoCargaRemuneraciones:
    raw = _remuneraciones_fuente_a_bytes(fuente)
    periodo_hdr = detectar_periodo_libro_remuneraciones(raw, hoja=hoja)

    if auto_fila_header:
        _fh, df, mapeo_probe = encontrar_mejor_encabezado_remuneraciones(
            raw,
            preset=preset_columnas or "dag",
            hoja=hoja,
            max_fila=max_fila_header,
        )
        preset_final = _elegir_preset_remuneraciones(list(df.columns), preset_columnas)
        if preset_final != (preset_columnas or "dag").lower():
            _fh, df, mapeo = encontrar_mejor_encabezado_remuneraciones(
                raw,
                preset=preset_final,
                hoja=hoja,
                max_fila=max_fila_header,
            )
        else:
            mapeo = mapeo_probe
    else:
        df_raw = leer_excel_facturas(fuente, hoja=hoja, fila_header=fila_header)
        df = preparar_df_remuneraciones_columnas(df_raw)
        preset_final = _elegir_preset_remuneraciones(list(df.columns), preset_columnas)
        mapeo = detectar_mapeo_remuneraciones(list(df.columns), preset=preset_final)

    # Período: encabezado del libro tiene prioridad; fallback manual solo si no se detecta.
    mes_usado = periodo_hdr
    if mes_usado is None and mes_aplicacion_default is not None:
        mes_usado = mes_aplicacion_default
    if mes_usado is not None and primer_dia_mes:
        mes_usado = date(mes_usado.year, mes_usado.month, 1)

    registros, adv = dataframe_a_registros_remuneracion(
        df,
        mapeo,
        mes_aplicacion_default=mes_usado,
        primer_dia_mes=primer_dia_mes,
        dia_pago_default=dia_pago_default,
    )
    if periodo_hdr is not None:
        adv = [
            f"Período detectado desde encabezado del libro: {periodo_hdr.strftime('%Y-%m')}."
        ] + list(adv)
    elif mes_aplicacion_default is not None:
        adv = [
            "No se detectó período en el encabezado; se usó el mes manual de fallback."
        ] + list(adv)

    carga = crud_p.crear_proyeccion_carga(
        user_id,
        "remuneraciones",
        nombre_archivo=nombre_archivo,
        origen=origen,
        total_registros=len(registros),
    )

    bulk: List[Dict[str, Any]] = []
    for r in registros:
        row = dict(r)
        row["carga_id"] = carga.id
        row["user_id"] = user_id
        bulk.append(row)

    n = crud_p.crear_proyeccion_remuneraciones_bulk(bulk) if bulk else 0

    return ResultadoCargaRemuneraciones(
        carga_id=carga.id,
        filas_guardadas=n,
        filas_leidas=len(df),
        filas_validas=len(registros),
        mapeo_columnas={k: v for k, v in mapeo.items() if not k.startswith("__")},
        advertencias=adv,
        mes_aplicacion_usado=mes_usado,
        periodo_detectado_encabezado=periodo_hdr,
    )
