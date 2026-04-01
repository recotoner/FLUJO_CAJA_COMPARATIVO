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
    "planilla_cl": {
        "empleado": _ALIAS_EMPLEADO,
        "rut_empleado": _ALIAS_RUT,
        "monto_liquido": _ALIAS_LIQUIDO,
        "monto_bruto": _ALIAS_BRUTO,
        "monto_imponible": ("imponible", "base imponible", "total imponible", "renta imponible"),
        "monto_afp": (
            "afp",
            "cot afp",
            "cotizacion afp",
            "cotización afp",
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
            "cotizacion salud",
            "cotización de salud",
            "c. salud",
        ),
        "monto_impuesto_unico": (
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
        "monto_imponible": ("imponible", "base imponible"),
        "monto_afp": ("afp", "cotizacion obligatoria", "prevision", "cot afp"),
        "monto_salud_adicional": ("adicional salud", "adicional de salud", "cot adicional salud"),
        "monto_cesantia": ("seguro cesantia", "seguro cesantía", "cesantia"),
        "monto_salud": ("salud", "fonasa", "isapre", "cot salud", "cotizacion salud"),
        "monto_impuesto_unico": ("impuesto unico", "impuesto único", "impuesto ui", "imp. unico", "iu"),
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
        clave_nc: Optional[Tuple[int, int]] = None
        for v in variants:
            nv = _norm_text(v)
            if not nv:
                continue
            if nc == nv or nv in nc:
                # rank 0 exacto; 1 substring nv in nc (encabezado más largo)
                r = 0 if nc == nv else 1
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
        nc = _mejor_columna_para_logico(ncols, variants, logical, used_cols)
        if nc:
            mapping[logical] = nc
            used_cols.add(nc)

    if "empleado" not in mapping:
        for nc in ncols:
            if nc in used_cols:
                continue
            if "nombre" in nc and "empresa" not in nc:
                mapping["empleado"] = nc
                used_cols.add(nc)
                break

    if "empleado" not in mapping:
        for nc in ncols:
            if nc in used_cols:
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

    out: List[Dict[str, Any]] = []

    for idx, row in df.iterrows():
        emp = row.get(col_emp)
        if emp is None or (isinstance(emp, float) and pd.isna(emp)):
            advertencias.append(f"Fila {idx}: sin nombre de empleado, omitida.")
            continue
        empleado = str(emp).strip()[:200]

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
        if col_rut:
            r = row.get(col_rut)
            if r is not None and not (isinstance(r, float) and pd.isna(r)):
                reg["rut_empleado"] = str(r).strip()[:20]
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
    if auto_fila_header:
        raw = _remuneraciones_fuente_a_bytes(fuente)
        fh_usada, df, mapeo = encontrar_mejor_encabezado_remuneraciones(
            raw, preset=preset, hoja=hoja, max_fila=max_fila_header
        )
        cols = list(df.columns)
    else:
        df_raw = leer_excel_facturas(fuente, hoja=hoja, fila_header=fila_header)
        df = preparar_df_remuneraciones_columnas(df_raw)
        cols = list(df.columns)
        mapeo = detectar_mapeo_remuneraciones(cols, preset=preset)
    necesita_mes = "mes_aplicacion" not in mapeo
    faltantes: List[str] = []
    if "empleado" not in mapeo:
        faltantes.append("empleado")
    if "monto_liquido" not in mapeo and "monto_bruto" not in mapeo:
        faltantes.append("monto_liquido o monto_bruto")
    if necesita_mes:
        faltantes.append("mes_aplicacion (o usar mes_aplicacion_default al cargar)")
    return {
        "columnas": cols,
        "mapeo": mapeo,
        "requiere_mes_default": necesita_mes,
        "mapeo_ok": "empleado" in mapeo and ("monto_liquido" in mapeo or "monto_bruto" in mapeo),
        "faltantes": faltantes,
        "muestra_filas": min(5, len(df)),
    }


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
    if auto_fila_header:
        raw = _remuneraciones_fuente_a_bytes(fuente)
        _fh, df, mapeo = encontrar_mejor_encabezado_remuneraciones(
            raw,
            preset=preset_columnas,
            hoja=hoja,
            max_fila=max_fila_header,
        )
    else:
        df_raw = leer_excel_facturas(fuente, hoja=hoja, fila_header=fila_header)
        df = preparar_df_remuneraciones_columnas(df_raw)
        mapeo = detectar_mapeo_remuneraciones(list(df.columns), preset=preset_columnas)

    if mes_aplicacion_default is not None and primer_dia_mes:
        mes_aplicacion_default = date(mes_aplicacion_default.year, mes_aplicacion_default.month, 1)

    registros, adv = dataframe_a_registros_remuneracion(
        df,
        mapeo,
        mes_aplicacion_default=mes_aplicacion_default,
        primer_dia_mes=primer_dia_mes,
        dia_pago_default=dia_pago_default,
    )

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
        mapeo_columnas=dict(mapeo),
        advertencias=adv,
    )
