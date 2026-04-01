"""
Parser y carga de Excel CxC / CxP exportados desde ERP (v3.0).
Sin APIs externas: sube archivo → normaliza → persiste en proyeccion_cargas + proyeccion_facturas.
"""
from __future__ import annotations

import io
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, BinaryIO, Dict, List, Mapping, Optional, Sequence, Union

import pandas as pd

from database import crud_proyeccion as crud_p

# Claves lógicas internas → posibles títulos de columna en Excel (minusc_norm)
# Extensible: añadir sinónimos por ERP.
MAPEO_PRESETS: Dict[str, Dict[str, Sequence[str]]] = {
    "kame": {
        "fecha_vencimiento": ("fecha vencimiento", "fecha vto", "vencimiento"),
        "fecha_emision": ("fecha emision", "fecha emisión", "emision", "emisión"),
        "saldo": ("saldo", "saldo pendiente", "por cobrar", "por pagar"),
        "razon_social": ("razon social", "razón social", "cliente", "proveedor", "nombre"),
        "monto_total": ("total doc", "monto total", "total", "total documento"),
        "rut_contraparte": ("rut", "rut cliente", "rut proveedor", "rut contraparte"),
        "folio": ("folio", "nro", "numero", "número", "n documento"),
        "monto_neto": ("neto", "monto neto"),
        "monto_iva": ("iva", "monto iva"),
        "condicion_venta": ("condicion", "condición", "condicion venta"),
        "estado": ("estado", "situacion", "situación"),
    },
    "defontana": {
        "fecha_vencimiento": ("fecha vto", "fecha vencimiento", "vencimiento"),
        "fecha_emision": ("fecha emision", "fecha emisión"),
        "saldo": ("monto pendiente", "saldo", "pendiente"),
        "razon_social": ("cliente / proveedor", "cliente", "proveedor", "razon social", "razón social"),
        "monto_total": ("monto total", "total", "total doc"),
        "rut_contraparte": ("rut", "rut contraparte"),
        "folio": ("folio", "factura", "nro"),
        "monto_neto": ("neto",),
        "monto_iva": ("iva",),
        "condicion_venta": ("condicion venta",),
        "estado": ("estado",),
    },
    "bsale": {
        "fecha_vencimiento": ("fecha vencimiento", "fecha vto", "vencimiento"),
        "fecha_emision": ("fecha emision", "fecha emisión"),
        "saldo": ("saldo",),
        "razon_social": ("razon social", "razón social"),
        "monto_total": ("monto total", "total"),
        "rut_contraparte": ("rut",),
        "folio": ("folio",),
        "monto_neto": ("neto",),
        "monto_iva": ("iva",),
        "condicion_venta": (),
        "estado": ("estado",),
    },
    "generico": {
        "fecha_vencimiento": ("fecha vencimiento", "fecha vto", "vencimiento", "fecha_vencimiento", "fec venc"),
        "fecha_emision": ("fecha emision", "fecha emisión", "fecha emision", "fecha_emision"),
        "saldo": ("saldo", "monto pendiente", "pendiente", "saldo documento"),
        "razon_social": (
            "razon social",
            "razón social",
            "cliente",
            "proveedor",
            "cliente / proveedor",
            "nombre",
            "nombre fantasia",
        ),
        "monto_total": ("monto total", "total doc", "total", "total documento", "monto_total"),
        "rut_contraparte": ("rut", "rut contraparte"),
        "folio": ("folio", "nro", "numero", "número"),
        "monto_neto": ("neto", "monto neto"),
        "monto_iva": ("iva", "monto iva"),
        "condicion_venta": ("condicion venta", "condición venta"),
        "estado": ("estado",),
    },
}


def _norm_text(s: str) -> str:
    t = unicodedata.normalize("NFKD", str(s).strip().lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = re.sub(r"\s+", " ", t)
    return t


def normalizar_nombres_columnas(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out.columns = [_norm_text(c) for c in out.columns]
    return out


def _columnas_df_normalizadas(df: pd.DataFrame) -> List[str]:
    return [_norm_text(c) for c in df.columns]


def detectar_mapeo_columnas(
    columnas: Sequence[str],
    preset: Optional[str] = None,
) -> Dict[str, str]:
    """
    Devuelve mapa {clave_logica: nombre_columna_en_df_normalizado}.
    Usa el preset indicado o 'generico'.
    """
    ncols = [_norm_text(c) for c in columnas]
    preset_key = (preset or "generico").lower()
    aliases = MAPEO_PRESETS.get(preset_key) or MAPEO_PRESETS["generico"]
    mapping: Dict[str, str] = {}
    used_cols: set[str] = set()

    for logical, variants in aliases.items():
        if logical in mapping:
            continue
        for v in variants:
            nv = _norm_text(v)
            for nc in ncols:
                if nc in used_cols:
                    continue
                if nc == nv or nv in nc or nc in nv:
                    mapping[logical] = nc
                    used_cols.add(nc)
                    break
            if logical in mapping:
                break

    # fecha_vencimiento obligatoria: intentar sinónimos extra
    if "fecha_vencimiento" not in mapping:
        for nc in ncols:
            if nc in used_cols:
                continue
            if "venc" in nc or "vto" in nc:
                mapping["fecha_vencimiento"] = nc
                used_cols.add(nc)
                break

    return mapping


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


def dataframe_a_registros_factura(
    df: pd.DataFrame,
    mapeo: Mapping[str, str],
    *,
    tipo_factura: str,
    tipo_confianza: str = "real",
) -> tuple[List[Dict[str, Any]], List[str]]:
    """
    Convierte filas del DataFrame en dicts listos para crud_p.crear_proyeccion_facturas_bulk
    (incluye tipo, tipo_confianza, fechas y montos; sin carga_id ni user_id).
    """
    advertencias: List[str] = []
    req = ["fecha_vencimiento", "razon_social", "monto_total", "saldo"]
    faltan = [k for k in req if k not in mapeo]
    if faltan:
        raise ValueError(f"Faltan columnas requeridas en el mapeo: {faltan}. Mapeo actual: {list(mapeo.keys())}")

    out: List[Dict[str, Any]] = []
    col_vcto = mapeo["fecha_vencimiento"]
    col_razon = mapeo["razon_social"]
    col_total = mapeo["monto_total"]
    col_saldo = mapeo["saldo"]
    col_emision = mapeo.get("fecha_emision")
    col_rut = mapeo.get("rut_contraparte")
    col_folio = mapeo.get("folio")
    col_neto = mapeo.get("monto_neto")
    col_iva = mapeo.get("monto_iva")
    col_cond = mapeo.get("condicion_venta")
    col_estado = mapeo.get("estado")

    for idx, row in df.iterrows():
        fev = _to_date(row.get(col_vcto))
        if not fev:
            advertencias.append(f"Fila {idx}: sin fecha_vencimiento válida, omitida.")
            continue
        razon = row.get(col_razon)
        if razon is None or (isinstance(razon, float) and pd.isna(razon)):
            advertencias.append(f"Fila {idx}: sin razón social, omitida.")
            continue
        razon_s = str(razon).strip()[:200]
        m_total = _to_decimal(row.get(col_total))
        saldo = _to_decimal(row.get(col_saldo))
        if saldo is None and m_total is not None:
            saldo = m_total
        if saldo is None:
            advertencias.append(f"Fila {idx}: sin saldo ni total válido, omitida.")
            continue

        reg: Dict[str, Any] = {
            "tipo": tipo_factura,
            "razon_social": razon_s,
            "fecha_vencimiento": fev,
            "monto_total": m_total,
            "saldo": saldo,
            "tipo_confianza": tipo_confianza,
        }
        if col_emision:
            fei = _to_date(row.get(col_emision))
            if fei:
                reg["fecha_emision"] = fei
        if col_rut:
            rut = row.get(col_rut)
            if rut is not None and not (isinstance(rut, float) and pd.isna(rut)):
                reg["rut_contraparte"] = str(rut).strip()[:20]
        if col_folio:
            folio = row.get(col_folio)
            if folio is not None and not (isinstance(folio, float) and pd.isna(folio)):
                reg["folio"] = str(folio).strip()[:50]
        if col_neto:
            neto = _to_decimal(row.get(col_neto))
            if neto is not None:
                reg["monto_neto"] = neto
        if col_iva:
            iva = _to_decimal(row.get(col_iva))
            if iva is not None:
                reg["monto_iva"] = iva
        if col_cond:
            cv = row.get(col_cond)
            if cv is not None and not (isinstance(cv, float) and pd.isna(cv)):
                reg["condicion_venta"] = str(cv).strip()[:50]
        if col_estado:
            es = row.get(col_estado)
            if es is not None and not (isinstance(es, float) and pd.isna(es)):
                reg["estado"] = str(es).strip()[:50]

        out.append(reg)

    return out, advertencias


def leer_excel_facturas(
    fuente: Union[str, Path, bytes, BinaryIO],
    *,
    hoja: Union[int, str, None] = 0,
    fila_header: int = 0,
) -> pd.DataFrame:
    """Lee la primera hoja (o la indicada); fila_header índice 0-based para el encabezado."""
    if isinstance(fuente, (str, Path)):
        return pd.read_excel(fuente, sheet_name=hoja if hoja is not None else 0, header=fila_header, engine="openpyxl")
    if isinstance(fuente, bytes):
        return pd.read_excel(
            io.BytesIO(fuente), sheet_name=hoja if hoja is not None else 0, header=fila_header, engine="openpyxl"
        )
    return pd.read_excel(fuente, sheet_name=hoja if hoja is not None else 0, header=fila_header, engine="openpyxl")


@dataclass
class ResultadoCargaErp:
    carga_id: int
    facturas_guardadas: int
    filas_leidas: int
    filas_validas: int
    mapeo_columnas: Dict[str, str] = field(default_factory=dict)
    advertencias: List[str] = field(default_factory=list)


def cargar_excel_cxc_cxp(
    user_id: int,
    fuente: Union[str, Path, bytes, BinaryIO],
    nombre_archivo: str,
    *,
    es_cxc: bool,
    preset_columnas: Optional[str] = None,
    hoja: Union[int, str, None] = 0,
    fila_header: int = 0,
    tipo_confianza: str = "real",
    origen: str = "upload_excel",
) -> ResultadoCargaErp:
    """
    Flujo completo: lee Excel, detecta columnas, crea proyeccion_carga y bulk de proyeccion_facturas.

    es_cxc=True → tipo carga 'cxc' y facturas 'por_cobrar'.
    es_cxc=False → tipo carga 'cxp' y facturas 'por_pagar'.
    """
    df_raw = leer_excel_facturas(fuente, hoja=hoja, fila_header=fila_header)
    df = normalizar_nombres_columnas(df_raw)
    cols = _columnas_df_normalizadas(df)
    mapeo = detectar_mapeo_columnas(cols, preset=preset_columnas)

    tipo_carga = "cxc" if es_cxc else "cxp"
    tipo_factura = "por_cobrar" if es_cxc else "por_pagar"

    registros, adv = dataframe_a_registros_factura(df, mapeo, tipo_factura=tipo_factura, tipo_confianza=tipo_confianza)

    carga = crud_p.crear_proyeccion_carga(
        user_id,
        tipo_carga,
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

    n = crud_p.crear_proyeccion_facturas_bulk(bulk) if bulk else 0

    return ResultadoCargaErp(
        carga_id=carga.id,
        facturas_guardadas=n,
        filas_leidas=len(df),
        filas_validas=len(registros),
        mapeo_columnas=dict(mapeo),
        advertencias=adv,
    )


def inspeccionar_excel_erp(
    fuente: Union[str, Path, bytes],
    *,
    preset: Optional[str] = None,
    hoja: Union[int, str, None] = 0,
    fila_header: int = 0,
) -> Dict[str, Any]:
    """Devuelve columnas normalizadas y mapeo detectado sin escribir en BD (útil para UI)."""
    df_raw = leer_excel_facturas(fuente, hoja=hoja, fila_header=fila_header)
    df = normalizar_nombres_columnas(df_raw)
    cols = list(df.columns)
    mapeo = detectar_mapeo_columnas(cols, preset=preset)
    faltantes = [k for k in ("fecha_vencimiento", "razon_social", "monto_total", "saldo") if k not in mapeo]
    return {
        "columnas": cols,
        "mapeo": mapeo,
        "mapeo_ok": len(faltantes) == 0,
        "faltantes": faltantes,
        "muestra_filas": min(5, len(df)),
    }
