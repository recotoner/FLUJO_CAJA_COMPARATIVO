# -*- coding: utf-8 -*-
"""
Saldo de cierre de cartola según estructura del extracto (sin usar saldo calculado).

Orientación:
- asc: archivo antiguo → reciente → cierre = última fila original de la última fecha
- desc: archivo reciente → antiguo → cierre = primera fila original de la última fecha
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, List, Mapping, Optional, Sequence, Tuple

import pandas as pd

Orientacion = str  # "asc" | "desc"


def _to_float(v: Any) -> Optional[float]:
    if v is None:
        return None
    if isinstance(v, float) and pd.isna(v):
        return None
    n = pd.to_numeric(v, errors="coerce")
    if pd.isna(n):
        return None
    return float(n)


def _fecha_val(v: Any):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    if isinstance(v, datetime):
        return v
    if isinstance(v, date) and not isinstance(v, datetime):
        return datetime.combine(v, datetime.min.time())
    ts = pd.to_datetime(v, errors="coerce")
    if pd.isna(ts):
        return None
    return ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts


def detectar_orientacion_cartola(
    fechas: Sequence[Any],
    orden_original: Sequence[int],
    *,
    saldos: Optional[Sequence[Any]] = None,
    abonos: Optional[Sequence[Any]] = None,
    cargos: Optional[Sequence[Any]] = None,
) -> Orientacion:
    """
    Detecta si el archivo está en orden cronológico ascendente (asc) o descendente (desc)
    según la estructura (fechas y, si hace falta, cadena de saldos).
    """
    rows = []
    for i, (f, o) in enumerate(zip(fechas, orden_original)):
        fv = _fecha_val(f)
        if fv is None:
            continue
        rows.append(
            {
                "fecha": fv,
                "ord": int(o),
                "saldo": _to_float(saldos[i]) if saldos is not None else None,
                "abono": _to_float(abonos[i]) if abonos is not None else 0.0,
                "cargo": _to_float(cargos[i]) if cargos is not None else 0.0,
            }
        )
    if len(rows) < 2:
        return "asc"

    rows.sort(key=lambda r: r["ord"])
    f0 = rows[0]["fecha"]
    f1 = rows[-1]["fecha"]
    if f0 < f1:
        return "asc"
    if f0 > f1:
        return "desc"

    # Misma fecha global (o primer/último iguales): inferir por cadena de saldos.
    return _orientacion_por_cadena_saldo(rows)


def _orientacion_por_cadena_saldo(rows_file_order: List[dict]) -> Orientacion:
    """
    Si el saldo de cada fila es el saldo *después* del movimiento:
    - en orden asc (tiempo): s[i+1] ≈ s[i] + abono[i+1] - cargo[i+1]
    - en orden desc (tiempo invertido en archivo): s[i+1] ≈ s[i] - abono[i] + cargo[i]
    """
    score_asc = 0
    score_desc = 0
    for i in range(len(rows_file_order) - 1):
        a = rows_file_order[i]
        b = rows_file_order[i + 1]
        sa, sb = a["saldo"], b["saldo"]
        if sa is None or sb is None:
            continue
        ab_b = b["abono"] or 0.0
        cg_b = b["cargo"] or 0.0
        ab_a = a["abono"] or 0.0
        cg_a = a["cargo"] or 0.0
        if abs((sa + ab_b - cg_b) - sb) <= 1.0:
            score_asc += 1
        if abs((sa - ab_a + cg_a) - sb) <= 1.0:
            score_desc += 1
    if score_desc > score_asc:
        return "desc"
    return "asc"


def saldo_cierre_desde_dataframe(
    df: pd.DataFrame,
    *,
    col_fecha: str = "FECHA",
    col_saldo: str = "SALDO (CLP)",
    col_abono: str = "ABONOS (CLP)",
    col_cargo: str = "CARGOS (CLP)",
) -> Tuple[Optional[float], Optional[Any], Optional[Orientacion]]:
    """
    Retorna (saldo_cierre, fecha_cierre, orientacion).
    Si no hay saldos reales en el extracto, (None, None, orientacion_o_None).
    """
    if df is None or df.empty or col_fecha not in df.columns or col_saldo not in df.columns:
        return None, None, None

    dfc = df.copy()
    dfc = dfc.reset_index(drop=True)
    dfc["_ord_orig"] = dfc.index.astype(int)
    dfc[col_fecha] = pd.to_datetime(dfc[col_fecha], errors="coerce")
    dfc = dfc[dfc[col_fecha].notna()]
    if dfc.empty:
        return None, None, None

    saldos_num = pd.to_numeric(dfc[col_saldo], errors="coerce")
    if not bool(saldos_num.notna().any()):
        return None, None, None

    ab_series = (
        pd.to_numeric(dfc[col_abono], errors="coerce")
        if col_abono in dfc.columns
        else pd.Series([0.0] * len(dfc))
    )
    cg_series = (
        pd.to_numeric(dfc[col_cargo], errors="coerce")
        if col_cargo in dfc.columns
        else pd.Series([0.0] * len(dfc))
    )

    orient = detectar_orientacion_cartola(
        list(dfc[col_fecha]),
        list(dfc["_ord_orig"]),
        saldos=list(saldos_num),
        abonos=list(ab_series),
        cargos=list(cg_series),
    )

    ultima_fecha = dfc[col_fecha].max()
    dia = dfc[dfc[col_fecha] == ultima_fecha].copy()
    dia["_saldo_num"] = pd.to_numeric(dia[col_saldo], errors="coerce")
    dia_con_saldo = dia[dia["_saldo_num"].notna()].sort_values("_ord_orig", ascending=True)
    if dia_con_saldo.empty:
        # Sin saldo explícito en el último día: propagar en orden cronológico real.
        return _saldo_por_propagacion(dfc, saldos_num, ab_series, cg_series, orient, col_fecha)

    if orient == "asc":
        fila = dia_con_saldo.iloc[-1]
    else:
        fila = dia_con_saldo.iloc[0]
    return float(fila["_saldo_num"]), fila[col_fecha], orient


def _saldo_por_propagacion(
    dfc: pd.DataFrame,
    saldos_num: pd.Series,
    ab_series: pd.Series,
    cg_series: pd.Series,
    orient: Orientacion,
    col_fecha: str,
) -> Tuple[Optional[float], Optional[Any], Orientacion]:
    dfc = dfc.copy()
    dfc["_saldo_num"] = saldos_num.values
    dfc["_ab"] = ab_series.fillna(0.0).values
    dfc["_cg"] = cg_series.fillna(0.0).values
    # Orden cronológico real: tiempo ascendente.
    if orient == "asc":
        ordered = dfc.sort_values(["_ord_orig"], ascending=True)
    else:
        ordered = dfc.sort_values(["_ord_orig"], ascending=False)
    running = None
    last_fecha = None
    for _, row in ordered.iterrows():
        last_fecha = row[col_fecha]
        s = row["_saldo_num"]
        ab = float(row["_ab"] or 0.0)
        cg = float(row["_cg"] or 0.0)
        if pd.notna(s):
            running = float(s)
        elif running is not None:
            running = running + ab - cg
        else:
            running = ab - cg
    return running, last_fecha, orient


def saldo_cierre_desde_movimientos(
    movimientos: Sequence[Mapping[str, Any]],
) -> Tuple[Optional[Decimal], Optional[date]]:
    """
    Misma lógica para registros tipo Transaccion.
    Cada mapping: fecha, saldo, abono/abonos, cargo/cargos, ord (opcional; si falta usa índice).
    """
    if not movimientos:
        return None, None
    rows = []
    for i, m in enumerate(movimientos):
        rows.append(
            {
                "FECHA": m.get("fecha"),
                "SALDO (CLP)": m.get("saldo"),
                "ABONOS (CLP)": m.get("abono", m.get("abonos")),
                "CARGOS (CLP)": m.get("cargo", m.get("cargos")),
                "_ord_given": m.get("ord", i),
            }
        )
    df = pd.DataFrame(rows)
    # Preservar orden original dado
    df = df.sort_values("_ord_given", ascending=True).reset_index(drop=True)
    saldo, fecha, _ = saldo_cierre_desde_dataframe(df)
    if saldo is None:
        return None, None
    if fecha is None:
        return Decimal(str(saldo)), None
    if hasattr(fecha, "date"):
        return Decimal(str(int(round(saldo)))), fecha.date()
    return Decimal(str(int(round(saldo)))), fecha
