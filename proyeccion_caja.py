"""
Motor y UI Streamlit del Tab «Proyección de caja» (v3.0).
Snapshots versionados, líneas con tipo_confianza y cargas CxC/CxP/remuneraciones.
"""
from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

import pandas as pd
import streamlit as st

try:
    from database import crud_proyeccion as crud_p
except Exception:
    # Fallback para despliegues donde crud_proyeccion.py quedó en raíz del proyecto.
    import crud_proyeccion as crud_p
from database.connection import get_db
from database.crud import (
    obtener_archivos,
    obtener_rango_fechas_transacciones,
    obtener_transacciones,
)
from database.models import (
    ArchivoCargado,
    ProyeccionFactura,
    ProyeccionImportacion,
    ProyeccionLinea,
    ProyeccionSnapshot,
    Transaccion,
    Usuario,
)
from modulo_carga_erp import cargar_excel_cxc_cxp
from modulo_remuneraciones import cargar_excel_remuneraciones

UMBRAL_CONFIANZA_BAJA = 0.40

COLOR_CONF = {
    "real": "#2ca02c",
    "estimado": "#ffbf00",
    "manual": "#1f77b4",
}

CONCEPTOS_ORDEN = [
    "📥 CxC — Pago Clientes",
    "📤 Proveedores Nacionales",
    "📤 Proveedores Extranjeros",
    "📤 Remuneraciones",
    "📤 Imposiciones AFP/Salud",
    "📤 Impuesto único nómina",
    "📤 Créditos bancarios",
    "📤 Honorarios líquidos",
    "📤 Retenciones 2da categoría",
    "📤 IVA Neto",
    "📤 PPM",
    "📤 F29 total a pagar — código 91",
    "📤 Gastos Aduana/Flete",
    "📤 IVA Importación",
    "📤 Categoría personalizada (cliente)",
    "🏦 Saldo Cartola",
    "💰 Posición Neta Acum.",
]

# En snapshots nuevos estas categorías no generan egresos (van dentro del F29 c.91).
# Los registros históricos en BD / snapshots viejos no se borran.
CODIGOS_EXCLUIDOS_POR_F29 = frozenset({"IVA", "PPM", "RETENCION", "IU_NOMINA"})

# Comparativo: un solo concepto de caja típico como ingreso (resto = egresos / salidas).
CONCEPTOS_INGRESO_COMPARATIVO = frozenset({"📥 CxC — Pago Clientes"})


def _dec(x: Any) -> Decimal:
    if x is None:
        return Decimal(0)
    if isinstance(x, Decimal):
        return x
    return Decimal(str(x))


def _next_month_year_month(y: int, m: int) -> Tuple[int, int]:
    if m == 12:
        return y + 1, 1
    return y, m + 1


def _prev_month(y: int, m: int) -> Tuple[int, int]:
    if m == 1:
        return y - 1, 12
    return y, m - 1


def _fecha_con_dia(y: int, m: int, dia: int) -> date:
    last = calendar.monthrange(y, m)[1]
    return date(y, m, min(max(1, dia), last))


def _primer_dia_mes_siguiente(fecha: date) -> date:
    """Primer día del mes calendario siguiente a `fecha` (útil para retenciones SII vs honorario mes previo)."""
    y, m = _next_month_year_month(fecha.year, fecha.month)
    return date(y, m, 1)


def _fecha_pago_f29_desde_periodo(mes_periodo: date, dia_pago_impuestos: int) -> date:
    """
    Pago F29 código 91: mes calendario siguiente al período tributario + día SII.
    Controla diciembre → enero del año siguiente.
    """
    y, m = _next_month_year_month(mes_periodo.year, mes_periodo.month)
    return _fecha_con_dia(y, m, int(dia_pago_impuestos))


def _iter_months_in_range(inicio: date, fin: date) -> Iterable[Tuple[int, int]]:
    y, m = inicio.year, inicio.month
    while date(y, m, 1) <= fin:
        yield y, m
        if m == 12:
            y, m = y + 1, 1
        else:
            m += 1


def _mapa_categorias_codigo_a_id() -> Dict[str, int]:
    """
    Un codigo por fila. Si en BD hay duplicados del mismo `codigo` (p. ej. re-seeds),
    se usa el **menor id** para comportamiento estable (evita que el último Arbitrario pise el id correcto).
    """
    out: Dict[str, int] = {}
    filas = sorted(
        crud_p.listar_categorias_financieras(),
        key=lambda c: (c.id or 0),
    )
    for c in filas:
        cod = (c.codigo or "").strip()
        if not cod:
            continue
        if cod not in out:
            out[cod] = c.id
    return out


def _ultima_carga_id(user_id: int, tipo: str) -> Optional[int]:
    L = crud_p.listar_proyeccion_cargas(user_id, tipo=tipo, limite=1)
    return L[0].id if L else None


def _facturas_ultimas_cargas(user_id: int) -> List[ProyeccionFactura]:
    """
    Devuelve facturas de la última carga de CxC y de la última carga de CxP.
    Evita sumar histórico completo cuando existen múltiples cargas.
    """
    out: List[ProyeccionFactura] = []
    cxc_id = _ultima_carga_id(user_id, "cxc")
    cxp_id = _ultima_carga_id(user_id, "cxp")
    if cxc_id:
        out.extend(crud_p.listar_proyeccion_facturas_por_carga(cxc_id))
    if cxp_id:
        out.extend(crud_p.listar_proyeccion_facturas_por_carga(cxp_id))
    return out


def _rango_facturas_cargadas(user_id: int) -> Tuple[Optional[date], Optional[date]]:
    """Rango min/max por fecha de vencimiento usando solo últimas cargas CxC/CxP."""
    facts = _facturas_ultimas_cargas(user_id)
    if not facts:
        return None, None
    fechas = [f.fecha_vencimiento for f in facts if f.fecha_vencimiento is not None]
    if not fechas:
        return None, None
    return min(fechas), max(fechas)


def _monto_factura(f: ProyeccionFactura) -> Decimal:
    return _dec(f.saldo) if f.saldo is not None else _dec(f.monto_total)


def _neto_para_iva(f: ProyeccionFactura) -> Decimal:
    """Neto contable: monto_neto si viene; si no, monto_total / 1.19 (factura con IVA incluido)."""
    if f.monto_neto is not None:
        return _dec(f.monto_neto)
    mt = _dec(f.monto_total)
    if mt > 0:
        return mt / Decimal("1.19")
    return Decimal(0)


def _fecha_iva_importacion_desde_eta(eta: date) -> date:
    """Día 12 del mes siguiente al mes de la ETA (real o estimada)."""
    ny, nm = _next_month_year_month(eta.year, eta.month)
    return _fecha_con_dia(ny, nm, 12)


def _fecha_dia_en_mes_siguiente_mes_ref(mes_ref: date, dia: int) -> date:
    """
    Devuelve `dia` del mes calendario **siguiente** al mes de `mes_ref` (primer día del mes de nómina).
    Uso típico: cotizaciones previsionales de la nómina de marzo → pago día X de abril.
    """
    y, m = _next_month_year_month(mes_ref.year, mes_ref.month)
    return _fecha_con_dia(y, m, dia)


def _fecha_pago_si_dia_paso_en_mes_actual(
    mes_aplicacion: date,
    dia_pay: int,
    periodo_inicio: date,
) -> date:
    """
    Fecha de pago en el mes de mes_aplicación; si ese día ya pasó respecto del día de corte
    y seguimos en el mismo mes calendario que periodo_inicio, se mueve al mismo día del mes siguiente.
    """
    y, m = mes_aplicacion.year, mes_aplicacion.month
    candidate = _fecha_con_dia(y, m, dia_pay)
    if (
        y == periodo_inicio.year
        and m == periodo_inicio.month
        and periodo_inicio > candidate
    ):
        y2, m2 = _next_month_year_month(y, m)
        candidate = _fecha_con_dia(y2, m2, dia_pay)
    return candidate


def _importacion_activa(imp: ProyeccionImportacion) -> bool:
    stt = (imp.estado or "").strip().lower()
    return stt not in ("cerrada", "cerrado", "anulada", "cancelada", "completada")


def _suma_neto_facturas_mes(facturas: List[ProyeccionFactura], tipo: str, y: int, m: int) -> Decimal:
    """Suma monto_neto (o total/1.19) de facturas con vencimiento en (y, m)."""
    s = Decimal(0)
    for f in facturas:
        if f.tipo != tipo:
            continue
        fv = f.fecha_vencimiento
        if fv and fv.year == y and fv.month == m:
            s += _neto_para_iva(f)
    return s


def _fraccion_flujo_estimado_manual_lineas(lineas: List[ProyeccionLinea]) -> float:
    num = Decimal(0)
    den = Decimal(0)
    for ln in lineas:
        a = abs(_dec(ln.monto))
        if a == 0:
            continue
        den += a
        tc = (ln.tipo_confianza or "real").strip().lower()
        if tc in ("estimado", "manual"):
            num += a
    if den == 0:
        return 0.0
    return float(num / den)


def _obtener_saldo_cartola_real(user_id: int, archivo_id: Optional[int] = None) -> Decimal:
    """
    Saldo al cierre según estructura de la cartola (orientación asc/desc del extracto).
    Sin columna saldo, equivale al neto del extracto.
    """
    try:
        trans = obtener_transacciones(user_id=user_id, archivo_id=archivo_id)
    except Exception:
        return Decimal(0)
    if not trans and archivo_id is not None:
        # Fallback defensivo: si la cartola seleccionada no trae movimientos en esta vista,
        # usar movimientos del usuario para no forzar saldo 0.
        try:
            trans = obtener_transacciones(user_id=user_id, archivo_id=None)
        except Exception:
            return Decimal(0)
    if not trans and archivo_id is not None:
        # Fallback extra: resolver por archivo_id directo, por si el user_id de sesión difiere.
        try:
            db = next(get_db())
            trans = (
                db.query(Transaccion)
                .filter(Transaccion.archivo_id == int(archivo_id))
                .order_by(Transaccion.id.asc())
                .all()
            )
            db.close()
        except Exception:
            return Decimal(0)
    if not trans:
        # Último fallback: usar la última cartola con movimientos en BD para evitar mostrar 0.
        # Esto cubre casos donde la sesión no trae user_id/archivo_id consistentes.
        try:
            db = next(get_db())
            ult = (
                db.query(Transaccion.archivo_id)
                .filter(Transaccion.archivo_id.isnot(None))
                .order_by(Transaccion.id.desc())
                .first()
            )
            if ult and ult[0] is not None:
                trans = (
                    db.query(Transaccion)
                    .filter(Transaccion.archivo_id == int(ult[0]))
                    .order_by(Transaccion.id.asc())
                    .all()
                )
            db.close()
        except Exception:
            return Decimal(0)

    def _dec_loose(x: Any) -> Decimal:
        if x is None:
            return Decimal(0)
        if isinstance(x, Decimal):
            return x
        if isinstance(x, (int, float)):
            return Decimal(str(x))
        s = str(x).strip().replace("$", "").replace(" ", "")
        if not s:
            return Decimal(0)
        # Normaliza formatos como 1.234.567,89 o 1,234,567.89
        if "," in s and "." in s:
            if s.rfind(",") > s.rfind("."):
                s = s.replace(".", "").replace(",", ".")
            else:
                s = s.replace(",", "")
        elif "," in s:
            s = s.replace(",", ".")
        try:
            return Decimal(s)
        except Exception:
            return Decimal(0)

    from cartola_saldo import saldo_cierre_desde_movimientos

    trans_list = list(trans)
    # Orden de archivo ~ id de inserción ascendente al cargar la cartola.
    trans_list.sort(key=lambda t: int(getattr(t, "id", None) or 0))
    movs = []
    neto = Decimal(0)
    for idx, t in enumerate(trans_list):
        ab = _dec_loose(getattr(t, "abono", None))
        cg = _dec_loose(getattr(t, "cargo", None))
        neto += ab - cg
        movs.append(
            {
                "fecha": getattr(t, "fecha", None),
                "saldo": getattr(t, "saldo", None),
                "abono": ab,
                "cargo": cg,
                "ord": int(getattr(t, "id", None) or idx),
            }
        )
    saldo_cierre, _ = saldo_cierre_desde_movimientos(movs)
    if saldo_cierre is not None:
        return saldo_cierre
    return neto

def _resolver_archivo_tab1_activo(user_id: int) -> Optional[int]:
    """
    Intenta resolver la cartola activa de Tab 1 desde sesión.
    Si no existe, usa la última cartola del usuario para evitar saldo 0 por falta de contexto.
    """
    for key in ("archivo_id_cargado_bd", "archivo_id_cargado", "archivo_id_tab1"):
        raw = st.session_state.get(key)
        if raw is None:
            continue
        try:
            rid = int(raw)
        except Exception:
            continue
        if rid > 0:
            return rid

    # Fallback por nombre de archivo cargado en Tab 1.
    nombre_bd = st.session_state.get("archivo_cargado_bd")
    if nombre_bd:
        try:
            db = next(get_db())
            row = (
                db.query(ArchivoCargado.id)
                .filter(ArchivoCargado.nombre_archivo == str(nombre_bd))
                .order_by(ArchivoCargado.id.desc())
                .first()
            )
            db.close()
            if row and row[0]:
                return int(row[0])
        except Exception:
            pass

    try:
        archivos = obtener_archivos(user_id) or []
    except Exception:
        return None
    if not archivos:
        return None
    # Preferir la cartola más reciente disponible.
    archivos_ordenados = sorted(
        archivos,
        key=lambda a: (
            getattr(a, "fecha_carga", None) or date.min,
            getattr(a, "id", 0),
        ),
        reverse=True,
    )
    return getattr(archivos_ordenados[0], "id", None)


def _slot_iva_ppm_ocupado(slots: set[Tuple[date, int]], fecha: date, categoria_id: int) -> bool:
    return (fecha, categoria_id) in slots


def _ocupar_slot_iva_ppm(slots: set[Tuple[date, int]], fecha: date, categoria_id: int) -> None:
    slots.add((fecha, categoria_id))


@dataclass
class LineaEspecificacion:
    fecha_impacto: date
    categoria_id: int
    descripcion: str
    monto: Decimal
    tipo_confianza: str
    origen: str
    referencia_id: Optional[int] = None


def _construir_lineas_snapshot(
    user_id: int,
    periodo_inicio: date,
    periodo_fin: date,
    cats: Mapping[str, int],
    slots_iva_ppm: set[Tuple[date, int]],
) -> Tuple[List[LineaEspecificacion], List[str]]:
    lineas: List[LineaEspecificacion] = []
    avisos: List[str] = []

    cxc_id = _ultima_carga_id(user_id, "cxc")
    cxp_id = _ultima_carga_id(user_id, "cxp")
    rem_id = _ultima_carga_id(user_id, "remuneraciones")

    facturas_cxc: List[ProyeccionFactura] = (
        crud_p.listar_proyeccion_facturas_por_carga(cxc_id) if cxc_id else []
    )
    facturas_cxp: List[ProyeccionFactura] = (
        crud_p.listar_proyeccion_facturas_por_carga(cxp_id) if cxp_id else []
    )
    params = crud_p.obtener_proyeccion_parametros_usuario(user_id)
    def _pct_0_1(v: Decimal) -> Decimal:
        if v < 0:
            return Decimal(0)
        if v > 1:
            return Decimal(1)
        return v

    mora_cxc = (
        _dec(params.porcentaje_morosidad_cxc)
        if params and params.porcentaje_morosidad_cxc is not None
        else Decimal(0)
    )
    mora_cxc = _pct_0_1(mora_cxc)

    for f in facturas_cxc:
        if f.tipo != "por_cobrar":
            continue
        mto = _monto_factura(f)
        if mto == 0:
            continue
        fi = f.fecha_vencimiento
        if fi < periodo_inicio or fi > periodo_fin:
            continue
        tc = (f.tipo_confianza or "real").strip().lower()
        lineas.append(
            LineaEspecificacion(
                fi,
                cats["CLIENTES"],
                f"Factura por Cobrar {f.folio or ''} {f.razon_social or ''}".strip()[:200],
                mto,
                tc,
                "upload_excel",
                f.id,
            )
        )
        if mora_cxc > 0:
            ajuste = -(mto * mora_cxc)
            if ajuste != 0:
                lineas.append(
                    LineaEspecificacion(
                        fi,
                        cats["CLIENTES"],
                        (
                            f"Ajuste morosidad Facturas por Cobrar ({float(mora_cxc * Decimal(100)):.1f}%) "
                            f"{f.folio or ''} {f.razon_social or ''}"
                        ).strip()[:200],
                        ajuste,
                        "estimado",
                        "parametrico",
                        f.id,
                    )
                )

    for f in facturas_cxp:
        if f.tipo != "por_pagar":
            continue
        mto = _monto_factura(f)
        if mto == 0:
            continue
        fi = f.fecha_vencimiento
        if fi < periodo_inicio or fi > periodo_fin:
            continue
        tc = (f.tipo_confianza or "real").strip().lower()
        lineas.append(
            LineaEspecificacion(
                fi,
                cats["PROV_NACIONAL"],
                f"Factura por Pagar {f.folio or ''} {f.razon_social or ''}".strip()[:200],
                -abs(mto),
                tc,
                "upload_excel",
                f.id,
            )
        )

    if rem_id:
        par_rem = crud_p.obtener_o_crear_proyeccion_parametros_usuario(user_id)
        dia_rem_raw = par_rem.dia_pago_remuneraciones
        dia_imp_raw = par_rem.dia_pago_imposiciones
        dia_rem_def = int(dia_rem_raw) if dia_rem_raw is not None else 30
        dia_imp_def = int(dia_imp_raw) if dia_imp_raw is not None else 10
        # Última carga vigente: el mes del libro es trazabilidad (base estimada), no la
        # única fecha de proyección. Se replica 1 línea de líquido y 1 de imposiciones
        # por cada mes del horizonte. Impuesto único no genera egreso ni se suma a F29.
        from collections import defaultdict

        por_periodo: Dict[Tuple[int, int], List[Any]] = defaultdict(list)
        for r in crud_p.listar_proyeccion_remuneraciones_carga(rem_id):
            if not r.mes_aplicacion:
                continue
            por_periodo[(r.mes_aplicacion.year, r.mes_aplicacion.month)].append(r)

        if por_periodo:
            src_y, src_m = max(por_periodo.keys())
            rows_base = por_periodo[(src_y, src_m)]
            dias_pago_filas = [int(r.dia_pago) for r in rows_base if r.dia_pago]
            dia_r = dias_pago_filas[0] if dias_pago_filas else dia_rem_def

            total_liq = Decimal(0)
            total_cot_trab = Decimal(0)
            total_aporte_emp = Decimal(0)
            for r in rows_base:
                total_liq += _dec(r.monto_liquido)
                total_cot_trab += (
                    _dec(r.monto_afp)
                    + _dec(r.monto_salud)
                    + _dec(getattr(r, "monto_salud_adicional", None))
                    + _dec(getattr(r, "monto_cesantia", None))
                )
                total_aporte_emp += _dec(getattr(r, "monto_aporte_empleador", None))
            total_impos = total_cot_trab + total_aporte_emp
            fuente = f"{src_y}-{src_m:02d}"
            avisos.append(
                f"Remuneraciones/imposiciones: período fuente {fuente} de la última carga "
                f"se usa como base estimada para cada mes del horizonte."
            )

            for y, m in _iter_months_in_range(periodo_inicio, periodo_fin):
                fr = _fecha_con_dia(y, m, dia_r)
                fi = _fecha_con_dia(y, m, dia_imp_def)

                if total_liq and periodo_inicio <= fr <= periodo_fin:
                    lineas.append(
                        LineaEspecificacion(
                            fr,
                            cats["REMUNERACIONES"],
                            f"Remuneraciones líquidas {y}-{m:02d} (base est. {fuente})",
                            -abs(total_liq),
                            "estimado",
                            "remuneraciones",
                            None,
                        )
                    )

                if total_impos and periodo_inicio <= fi <= periodo_fin:
                    lineas.append(
                        LineaEspecificacion(
                            fi,
                            cats["IMPOSICIONES"],
                            f"Imposiciones AFP/Salud {y}-{m:02d} (base est. {fuente})",
                            -abs(total_impos),
                            "estimado",
                            "remuneraciones",
                            None,
                        )
                    )

    egresos = crud_p.listar_proyeccion_egresos_parametricos(user_id)
    id_a_codigo: Dict[int, str] = {}
    for c in crud_p.listar_categorias_financieras():
        id_a_codigo[c.id] = c.codigo

    dia_imp = int(params.dia_pago_impuestos) if params and params.dia_pago_impuestos is not None else 12
    f29_periodos_cubiertos: set[Tuple[int, int]] = set()

    for e in egresos:
        cod = id_a_codigo.get(e.categoria_id, "")
        if cod in CODIGOS_EXCLUIDOS_POR_F29:
            # Históricos IVA/PPM/RETENCION (e IU vía otra vía) no entran a snapshots nuevos.
            continue

        m_est = _dec(e.monto_estimado)
        if m_est == 0:
            continue
        dia_e = e.dia_pago or 12

        # F29_91: mes_aplicacion = período tributario; pago = mes siguiente + dia_pago_impuestos.
        if cod == "F29_91":
            if e.es_recurrente:
                continue
            if not e.mes_aplicacion:
                continue
            ma = e.mes_aplicacion
            fd = _fecha_pago_f29_desde_periodo(ma, dia_imp)
            f29_periodos_cubiertos.add((ma.year, ma.month))
            if periodo_inicio <= fd <= periodo_fin:
                lineas.append(
                    LineaEspecificacion(
                        fd,
                        e.categoria_id,
                        "F29 total a pagar — código 91",
                        -abs(m_est),
                        "manual",
                        "parametrico",
                        e.id,
                    )
                )
            continue

        if e.es_recurrente:
            for y, m in _iter_months_in_range(periodo_inicio, periodo_fin):
                fd = _fecha_con_dia(y, m, dia_e)
                if periodo_inicio <= fd <= periodo_fin:
                    lineas.append(
                        LineaEspecificacion(
                            fd,
                            e.categoria_id,
                            (e.descripcion or f"Egreso param. {cod}")[:200],
                            -abs(m_est),
                            "estimado",
                            "parametrico",
                            e.id,
                        )
                    )
        else:
            if e.mes_aplicacion:
                ma = e.mes_aplicacion
                fd = _fecha_con_dia(ma.year, ma.month, dia_e)
                if periodo_inicio <= fd <= periodo_fin:
                    lineas.append(
                        LineaEspecificacion(
                            fd,
                            e.categoria_id,
                            (e.descripcion or f"Egreso param. {cod}")[:200],
                            -abs(m_est),
                            "estimado",
                            "parametrico",
                            e.id,
                        )
                    )

    # Créditos/pasivos bancarios parametrizados por usuario.
    cid_credito = cats.get("CREDITO_BANCARIO")
    if cid_credito:
        for cr in crud_p.listar_proyeccion_creditos_bancarios(user_id, solo_activos=True):
            cuota = _dec(cr.monto_cuota)
            cuotas = int(cr.cuotas_pendientes or 0)
            if cuota <= 0 or cuotas <= 0:
                continue
            base = cr.fecha_proximo_pago
            if not base:
                continue
            dref = int(base.day)
            y, m = base.year, base.month
            for _ in range(cuotas):
                fd = _fecha_con_dia(y, m, dref)
                if periodo_inicio <= fd <= periodo_fin:
                    lineas.append(
                        LineaEspecificacion(
                            fd,
                            cid_credito,
                            f"Cuota crédito: {(cr.descripcion or '').strip() or 'Crédito bancario'}".strip()[:200],
                            -abs(cuota),
                            "manual",
                            "credito_bancario",
                            cr.id,
                        )
                    )
                y, m = _next_month_year_month(y, m)

    for imp in crud_p.listar_proyeccion_importaciones(user_id):
        if not _importacion_activa(imp):
            continue
        if imp.monto_cif_clp and imp.fecha_pago_proveedor:
            fp = imp.fecha_pago_proveedor
            if periodo_inicio <= fp <= periodo_fin:
                lineas.append(
                    LineaEspecificacion(
                        fp,
                        cats["PROV_EXTRANJERO"],
                        f"Pago prov. extr. {imp.invoice_numero or imp.id}",
                        -abs(_dec(imp.monto_cif_clp)),
                        "manual",
                        "importacion",
                        imp.id,
                    )
                )
        eta = imp.eta_real or imp.eta_estimada
        if imp.gastos_aduana_estimados and eta:
            g = _dec(imp.gastos_aduana_estimados)
            if g:
                if periodo_inicio <= eta <= periodo_fin:
                    lineas.append(
                        LineaEspecificacion(
                            eta,
                            cats["GASTOS_IMPORTACION"],
                            f"Aduana/flete imp. {imp.invoice_numero or imp.id}",
                            -abs(g),
                            "estimado",
                            "importacion",
                            imp.id,
                        )
                    )
        if imp.iva_diferido_estimado:
            iva_m = _dec(imp.iva_diferido_estimado)
            if iva_m:
                f_iva = imp.fecha_impacto_iva
                if f_iva is None and eta:
                    f_iva = _fecha_iva_importacion_desde_eta(eta)
                if f_iva and periodo_inicio <= f_iva <= periodo_fin:
                    lineas.append(
                        LineaEspecificacion(
                            f_iva,
                            cats["IVA_IMPORTACION"],
                            f"IVA diferido imp. {imp.invoice_numero or imp.id}",
                            -abs(iva_m),
                            "estimado",
                            "importacion",
                            imp.id,
                        )
                    )

    # Ventas contado esperadas del mes (supuesto manual cliente).
    venta_global = (
        _dec(params.venta_global_esperada_mes)
        if params and params.venta_global_esperada_mes is not None
        else Decimal(0)
    )
    pct_contado = (
        _dec(params.porcentaje_ventas_contado)
        if params and params.porcentaje_ventas_contado is not None
        else Decimal(0)
    )
    pct_contado = _pct_0_1(pct_contado)
    if venta_global > 0 and pct_contado > 0:
        ingresos_contado = venta_global * pct_contado
        # Distribuye contado en TODO el horizonte futuro visible de la proyección
        # (no solo en el primer mes del snapshot).
        inicio_contado = max(periodo_inicio, date.today())
        fd = inicio_contado
        while fd <= periodo_fin:
            dias_mes_fd = calendar.monthrange(fd.year, fd.month)[1]
            monto_diario = ingresos_contado / Decimal(dias_mes_fd)
            lineas.append(
                LineaEspecificacion(
                    fd,
                    cats["CLIENTES"],
                    "Ventas contado esperadas (supuesto cliente)",
                    monto_diario,
                    "manual",
                    "parametrico",
                    None,
                )
            )
            fd = fd + timedelta(days=1)

    # Compras contado esperadas del mes (supuesto manual cliente).
    compra_global = (
        _dec(getattr(params, "compra_global_esperada_mes", None))
        if params and getattr(params, "compra_global_esperada_mes", None) is not None
        else Decimal(0)
    )
    pct_compra_contado = (
        _dec(getattr(params, "porcentaje_compras_contado", None))
        if params and getattr(params, "porcentaje_compras_contado", None) is not None
        else Decimal(0)
    )
    pct_compra_contado = _pct_0_1(pct_compra_contado)
    if compra_global > 0 and pct_compra_contado > 0:
        egresos_contado = compra_global * pct_compra_contado
        inicio_compra = max(periodo_inicio, date.today())
        fd = inicio_compra
        while fd <= periodo_fin:
            dias_mes_fd = calendar.monthrange(fd.year, fd.month)[1]
            monto_diario = egresos_contado / Decimal(dias_mes_fd)
            lineas.append(
                LineaEspecificacion(
                    fd,
                    cats["PROV_NACIONAL"],
                    "Compras contado esperadas (supuesto cliente)",
                    -abs(monto_diario),
                    "manual",
                    "parametrico",
                    None,
                )
            )
            fd = fd + timedelta(days=1)

    # Recuperación de clientes morosos (sobre CxC vencidos a fecha de análisis).
    pct_recup_morosos = (
        _dec(getattr(params, "porcentaje_recuperabilidad_morosos", None))
        if params and getattr(params, "porcentaje_recuperabilidad_morosos", None) is not None
        else Decimal(0)
    )
    pct_recup_morosos = _pct_0_1(pct_recup_morosos)
    if pct_recup_morosos > 0:
        fecha_analisis = date.today()
        base_morosos = Decimal(0)
        for f in facturas_cxc:
            if f.tipo != "por_cobrar" or not f.fecha_vencimiento:
                continue
            if f.fecha_vencimiento < fecha_analisis:
                mto = _monto_factura(f)
                if mto > 0:
                    base_morosos += mto
        recup_morosos = base_morosos * pct_recup_morosos
        if recup_morosos > 0:
            inicio_recup = max(periodo_inicio, fecha_analisis)
            fd = inicio_recup
            while fd <= periodo_fin:
                dias_mes_fd = calendar.monthrange(fd.year, fd.month)[1]
                monto_diario = recup_morosos / Decimal(dias_mes_fd)
                lineas.append(
                    LineaEspecificacion(
                        fd,
                        cats["CLIENTES"],
                        "Recuperación CxC morosos (supuesto cliente)",
                        monto_diario,
                        "manual",
                        "parametrico",
                        None,
                    )
                )
                fd = fd + timedelta(days=1)

    # Advertencias F29: solo pagos futuros (>= hoy) dentro del horizonte del snapshot.
    # No alertar períodos históricos; consolidar faltantes en un solo aviso.
    hoy = date.today()
    f29_faltantes: List[Tuple[Tuple[int, int], date]] = []
    for y, m in _iter_months_in_range(periodo_inicio, periodo_fin):
        fd = _fecha_con_dia(y, m, dia_imp)
        if fd < hoy:
            continue
        if fd < periodo_inicio or fd > periodo_fin:
            continue
        py, pm = _prev_month(y, m)
        if (py, pm) not in f29_periodos_cubiertos:
            f29_faltantes.append(((py, pm), fd))

    if f29_faltantes:
        periodos_txt = ", ".join(f"{py}-{pm:02d}" for (py, pm), _ in f29_faltantes)
        avisos.append(
            f"Falta F29 código 91 para período(s) tributario(s) {periodos_txt} "
            f"(pago futuro dentro del horizonte). No se estima automáticamente."
        )

    return lineas, avisos


def generar_snapshot(
    user_id: int,
    periodo_dias: int,
    etiqueta: Optional[str] = None,
    notas: Optional[str] = None,
) -> Tuple[ProyeccionSnapshot, List[str]]:
    """
    Lee últimas cargas CxC, CxP y remuneraciones; importaciones activas; egresos paramétricos;
    F29 código 91 manual (período tributario → pago mes siguiente + dia_pago_impuestos).
    No genera egresos separados de IVA, PPM, RETENCION ni IU_NOMINA (van en F29 c.91).
    IVA importaciones: si no hay ``fecha_impacto_iva``, se usa día 12 del mes **siguiente** a la ETA.
    Retorna ``(snapshot, avisos)``; avisos incluye períodos F29 faltantes en el horizonte.
    """
    if periodo_dias not in (30, 60, 90):
        periodo_dias = min(max(30, periodo_dias), 90)

    # PostgreSQL / deploy nuevo: asegura categorías (p. ej. CREDITO_BANCARIO activo).
    crud_p.seed_categorias_financieras()

    fecha_proyeccion = date.today()
    # Para que "Vencidos/Por vencer/Todos" sea consistente con Excel, el snapshot
    # debe incluir también los vencidos más antiguos que existan en la ultima carga.
    facts_latest = _facturas_ultimas_cargas(user_id)
    venc_min = None
    for f in facts_latest:
        if f.fecha_vencimiento is not None:
            venc_min = f.fecha_vencimiento if venc_min is None else min(venc_min, f.fecha_vencimiento)
    periodo_inicio = venc_min if (venc_min is not None and venc_min < fecha_proyeccion) else fecha_proyeccion
    periodo_fin = fecha_proyeccion + timedelta(days=periodo_dias)

    cats = _mapa_categorias_codigo_a_id()
    for req in (
        "CLIENTES",
        "PROV_NACIONAL",
        "PROV_EXTRANJERO",
        "REMUNERACIONES",
        "IMPOSICIONES",
        "IVA",
        "IVA_IMPORTACION",
        "PPM",
        "GASTOS_IMPORTACION",
    ):
        if req not in cats:
            raise ValueError(
                f"Falta categoría financiera '{req}'. Ejecute seed_categorias_financieras o revise la BD."
            )

    creditos_activos = crud_p.listar_proyeccion_creditos_bancarios(user_id, solo_activos=True)
    if creditos_activos and cats.get("CREDITO_BANCARIO") is None:
        raise ValueError(
            "Hay créditos bancarios activos en tu cuenta pero falta la categoría financiera "
            "`CREDITO_BANCARIO` (debe existir y estar activa). "
            "En servidor: ejecute `seed_categorias_financieras` / init_db y evite códigos duplicados en `categorias_financieras`."
        )

    slots_iva_ppm: set[Tuple[date, int]] = set()
    especs, avisos = _construir_lineas_snapshot(user_id, periodo_inicio, periodo_fin, cats, slots_iva_ppm)

    snap = crud_p.crear_proyeccion_snapshot(
        user_id,
        fecha_proyeccion,
        periodo_inicio,
        periodo_fin,
        etiqueta=etiqueta,
        notas=notas,
    )

    bulk: List[Dict[str, Any]] = []
    for e in especs:
        bulk.append(
            {
                "snapshot_id": snap.id,
                "fecha_impacto": e.fecha_impacto,
                "categoria_id": e.categoria_id,
                "descripcion": e.descripcion,
                "monto": e.monto,
                "tipo_confianza": e.tipo_confianza,
                "origen": e.origen,
                "referencia_id": e.referencia_id,
            }
        )
    if bulk:
        crud_p.crear_proyeccion_lineas_bulk(bulk)

    return crud_p.obtener_proyeccion_snapshot(snap.id), avisos


def _agregacion_diaria_waterfall(
    lineas: List[ProyeccionLinea],
) -> Tuple[List[date], List[float], List[str]]:
    from collections import defaultdict

    por_dia_monto: Dict[date, Decimal] = defaultdict(lambda: Decimal(0))
    por_dia_peso_conf: Dict[date, Dict[str, Decimal]] = defaultdict(lambda: defaultdict(lambda: Decimal(0)))

    for ln in lineas:
        d = ln.fecha_impacto
        m = _dec(ln.monto)
        por_dia_monto[d] += m
        tc = (ln.tipo_confianza or "real").strip().lower()
        if tc not in COLOR_CONF:
            tc = "estimado"
        por_dia_peso_conf[d][tc] += abs(m)

    fechas = sorted(por_dia_monto.keys())
    montos = [float(por_dia_monto[d]) for d in fechas]
    dominantes: List[str] = []
    for d in fechas:
        confs = por_dia_peso_conf[d]
        dom = max(confs.items(), key=lambda x: x[1])[0] if confs else "real"
        dominantes.append(dom)
    return fechas, montos, dominantes


def _fig_waterfall(fechas: List[date], montos: List[float], dominantes: List[str]):
    import plotly.graph_objects as go

    labels = [fd.isoformat() for fd in fechas]
    fig = go.Figure(
        go.Waterfall(
            name="Flujo",
            orientation="v",
            measure=["relative"] * len(montos),
            x=labels,
            y=montos,
            text=[f"{v:,.0f}" for v in montos],
            connector={"line": {"color": "rgb(100,100,100)"}},
            increasing={"marker": {"color": "#2ca02c"}},
            decreasing={"marker": {"color": "#d62728"}},
            totals={"marker": {"color": "#9467bd"}},
        )
    )
    fig.update_layout(
        title="Flujo proyectado día a día (color ≈ confianza dominante ese día)",
        xaxis_title="Fecha",
        yaxis_title="Monto",
        height=480,
        legend_title_text="Referencia colores",
    )
    fig.add_annotation(
        x=0,
        y=-0.12,
        xref="paper",
        yref="paper",
        showarrow=False,
        text="Verde=real · Amarillo=estimado · Azul=manual (por peso del monto absoluto del día)",
        font=dict(size=11),
    )
    return fig


def _text_column_streamlit(label: str, *, width: str = "large", pinned: bool = False) -> Any:
    """TextColumn con columna fija (Excel-style) si la versión de Streamlit lo permite."""
    from streamlit import column_config as cc

    if pinned:
        try:
            return cc.TextColumn(str(label), width=width, pinned=True)
        except TypeError:
            pass
    return cc.TextColumn(str(label), width=width)


def _dataframe_proyeccion(
    df: pd.DataFrame,
    *,
    money_cols: Optional[List[str]] = None,
    pct_cols: Optional[List[str]] = None,
    date_cols: Optional[List[str]] = None,
    text_wide_cols: Optional[List[str]] = None,
    pinned_text_cols: Optional[List[str]] = None,
    column_config: Optional[Mapping[str, Any]] = None,
    **kwargs: Any,
) -> None:
    """`st.dataframe` con formato numérico/fecha cuando Streamlit lo soporta."""
    import streamlit as st

    money_cols = list(money_cols or [])
    pct_cols = list(pct_cols or [])
    date_cols = list(date_cols or [])
    text_wide_cols = list(text_wide_cols or [])
    pinned_set = set(pinned_text_cols or [])
    cfg: Dict[str, Any] = dict(column_config or {})
    try:
        from streamlit import column_config as cc

        for c in df.columns:
            if c in cfg:
                continue
            if c in money_cols:
                cfg[c] = cc.NumberColumn(str(c), format="$%d")
            elif c in pct_cols:
                cfg[c] = cc.NumberColumn(str(c), format="%.1f %%")
            elif c in date_cols:
                cfg[c] = cc.DateColumn(str(c), format="DD/MM/YYYY")
            elif c in text_wide_cols:
                cfg[c] = _text_column_streamlit(str(c), width="large", pinned=c in pinned_set)
        if cfg:
            kwargs["column_config"] = cfg
    except Exception:
        pass
    st.dataframe(df, **kwargs)


def render_proyeccion(usuario: Optional[Usuario]) -> None:
    """
    UI Tab 2: parámetros, cargas, generación de snapshot, selector, KPIs, waterfall, detalle.
    """
    import streamlit as st
    from modulo_parametros import render_modulo_parametros_usuario

    st.markdown(
        """
        <style>
        :root {
            --proy-primary: #0e5a8a;
            --proy-secondary: #1d8f6e;
            --proy-bg-soft: #f7faf9;
            --proy-border: #d4e5dd;
            --proy-text-strong: #123729;
            --proy-text-soft: #5b6f66;
        }
        html, body, [class*="css"] {
            font-size: 14px;
        }
        .proy-hero {
            background: linear-gradient(135deg, var(--proy-primary) 0%, var(--proy-secondary) 100%);
            color: white;
            border-radius: 16px;
            padding: 18px 20px;
            margin: 2px 0 10px 0;
            box-shadow: 0 10px 26px rgba(0,0,0,0.12);
        }
        .proy-hero-title {
            font-size: 1.62rem;
            font-weight: 800;
            line-height: 1.1;
            margin-bottom: 4px;
        }
        .proy-hero-sub {
            font-size: 0.93rem;
            opacity: 0.96;
        }
        .proy-banner {
            border: 1px solid var(--proy-border);
            border-radius: 12px;
            padding: 10px 12px;
            background: var(--proy-bg-soft);
            margin: 4px 0 12px 0;
            font-size: 0.90rem;
        }
        .proy-section-title {
            font-weight: 700;
            color: var(--proy-text-strong);
            margin-top: 12px;
            margin-bottom: 4px;
            letter-spacing: 0.1px;
        }
        .proy-section-sub {
            margin-top: 0;
            margin-bottom: 8px;
            color: var(--proy-text-soft);
            font-size: 0.84rem;
        }
        .proy-kpi-card {
            border-radius: 14px;
            padding: 12px 12px;
            color: white;
            box-shadow: 0 5px 14px rgba(0,0,0,0.10);
            min-height: 92px;
        }
        .proy-kpi-label {
            font-size: 0.78rem;
            opacity: 0.92;
            margin-bottom: 5px;
            font-weight: 600;
        }
        .proy-kpi-value {
            font-size: 1.58rem;
            line-height: 1.1;
            font-weight: 800;
            letter-spacing: 0.2px;
        }
        .proy-kpi-ing { background: linear-gradient(135deg, #0EA35A, #16C172); }
        .proy-kpi-egr { background: linear-gradient(135deg, #B6382E, #DF5A4E); }
        .proy-kpi-net { background: linear-gradient(135deg, #2E4C97, #4D6CD9); }
        .proy-kpi-risk { background: linear-gradient(135deg, #6A5A1A, #9B8326); }
        .proy-upload-card {
            border: 1px solid var(--proy-border);
            border-radius: 14px;
            padding: 12px 14px 16px 14px;
            background: linear-gradient(180deg, #fbfdfc 0%, #f4faf7 100%);
            box-shadow: 0 2px 10px rgba(14, 90, 74, 0.06);
            margin-bottom: 6px;
        }
        .proy-upload-title {
            font-weight: 700;
            font-size: 0.94rem;
            color: var(--proy-text-strong);
            margin: 0 0 10px 0;
            line-height: 1.25;
        }
        .proy-data-summary-card {
            border: 1px solid var(--proy-border);
            border-radius: 14px;
            padding: 10px 12px 12px 12px;
            background: linear-gradient(180deg, #f8fbff 0%, #f2f8ff 100%);
            box-shadow: 0 2px 10px rgba(24, 78, 145, 0.08);
            margin: 6px 0 10px 0;
        }
        .proy-data-summary-title {
            font-weight: 800;
            font-size: 0.95rem;
            color: #184e91;
            margin: 0 0 8px 0;
        }
        .proy-filter-card {
            border: 1px solid #d8e8f7;
            border-radius: 14px;
            padding: 10px 12px 10px 12px;
            background: linear-gradient(180deg, #fcfeff 0%, #f5faff 100%);
            box-shadow: 0 2px 8px rgba(24, 78, 145, 0.06);
            margin: 8px 0 10px 0;
        }
        .proy-filter-title {
            font-weight: 800;
            font-size: 0.95rem;
            color: #184e91;
            margin: 0 0 6px 0;
        }
        .proy-proj-card {
            border: 2px solid #1c6dd0;
            border-radius: 14px;
            padding: 12px 14px 12px 14px;
            background: linear-gradient(180deg, #eef6ff 0%, #e2f0ff 100%);
            box-shadow: 0 4px 12px rgba(28, 109, 208, 0.18);
            margin: 12px 0 14px 0;
        }
        .proy-proj-title {
            font-weight: 900;
            font-size: 1.22rem;
            color: #0f4ea3;
            margin: 0;
            text-transform: uppercase;
            text-align: center;
            letter-spacing: 0.6px;
        }
        div[data-testid="stDataFrame"] {
            border: 1px solid var(--proy-border);
            border-radius: 12px;
            overflow: hidden;
            box-shadow: 0 1px 8px rgba(0,0,0,0.04);
        }
        div[data-testid="stDataFrame"] [role="columnheader"] {
            background: #eef5f2 !important;
            font-weight: 700 !important;
        }
        div[data-testid="stExpander"] {
            border: 1px solid var(--proy-border);
            border-radius: 12px;
            background: #fbfdfc;
        }
        div[data-testid="stExpander"] summary p {
            font-weight: 700;
            color: var(--proy-text-strong);
        }
        .stButton > button {
            border-radius: 9px;
            border: 1px solid #c6d8cf;
            font-weight: 600;
        }
        .proy-cta-wrap .stButton > button {
            min-height: 54px;
            font-size: 1.12rem;
            font-weight: 800;
            letter-spacing: 0.2px;
            border-radius: 12px;
            box-shadow: 0 6px 14px rgba(24, 78, 145, 0.24);
        }
        .proy-cta-wrap .stButton > button[kind="primary"] {
            background: linear-gradient(135deg, #1e7f3f 0%, #33a95b 100%) !important;
            border: none !important;
        }
        .proy-cta-wrap .stButton > button[kind="primary"]:hover {
            transform: translateY(-1px);
            box-shadow: 0 8px 18px rgba(24, 78, 145, 0.30);
        }
        .stTextInput input, .stNumberInput input, .stDateInput input, .stTextArea textarea, .stSelectbox div[data-baseweb="select"] > div {
            border-radius: 9px !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        """
        <div class="proy-hero">
          <div class="proy-hero-title">Proyección de Caja</div>
          <div class="proy-hero-sub">Vista ejecutiva para anticipar flujo, riesgo y brechas contra ejecución real.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if usuario is None:
        st.warning("Inicie sesión para usar la proyección.")
        return

    user_id = usuario.id
    _seed_ss = f"proy_cat_seed_v2_{user_id}"
    if not st.session_state.get(_seed_ss):
        try:
            crud_p.seed_categorias_financieras()
        except Exception:
            pass
        st.session_state[_seed_ss] = True
    modo_presentacion = st.toggle(
        "Modo presentación gerencial (vista más limpia)",
        value=False,
        help="Reduce ruido visual y centra la pantalla en indicadores y tablas ejecutivas.",
    )
    if modo_presentacion:
        st.caption("Vista gerencial activa: foco en KPIs, matriz por fecha y comparativo.")

    with st.expander("Diagnóstico: créditos y retenciones (si no aparecen en la proyección)", expanded=False):
        st.caption(
            "Comprueba que exista la categoría **CREDITO_BANCARIO**, que los registros estén en BD "
            "y que la fecha de impacto caiga dentro de la ventana del próximo snapshot."
        )
        if st.button("Sincronizar categorías maestras ahora", key=f"btn_seed_cat_{user_id}"):
            try:
                nch = crud_p.seed_categorias_financieras()
                st.success(f"Categorías sincronizadas (cambios: {nch}). Genere la proyección de nuevo.")
            except Exception as ex:
                st.error(str(ex))
        cats_d = _mapa_categorias_codigo_a_id()
        cb_id = cats_d.get("CREDITO_BANCARIO")
        if cb_id:
            st.markdown(f"- **CREDITO_BANCARIO** en mapa: `id {cb_id}`")
        else:
            st.error(
                "❌ No hay categoría **CREDITO_BANCARIO** activa: las cuotas de crédito **no** se agregan al snapshot. "
                "Pulse «Sincronizar categorías maestras» arriba."
            )
        cat_hon = crud_p.obtener_categoria_por_codigo("HONORARIOS")
        cat_ret = crud_p.obtener_categoria_por_codigo("RETENCION")
        st.markdown(
            f"- **HONORARIOS** → `id {cat_hon.id if cat_hon else '—'}` · "
            f"**RETENCION** → `id {cat_ret.id if cat_ret else '—'}`"
        )
        if not cat_hon or not cat_ret:
            st.warning("Faltan categorías HONORARIOS o RETENCION. Use «Sincronizar categorías maestras».")
        creds = crud_p.listar_proyeccion_creditos_bancarios(user_id, solo_activos=True)
        st.markdown(f"- Créditos bancarios **activos** en BD: **{len(creds)}**")
        for c in creds[:8]:
            st.caption(
                f"  · id {c.id} · próximo **{c.fecha_proximo_pago}** · cuota ${_dec(c.monto_cuota):,.0f} · "
                f"pend. **{c.cuotas_pendientes}**"
            )
        eggs = crud_p.listar_proyeccion_egresos_parametricos(user_id)
        id_h = cat_hon.id if cat_hon else None
        id_r = cat_ret.id if cat_ret else None
        hr_rows = [e for e in eggs if id_h is not None and id_r is not None and e.categoria_id in (id_h, id_r)]
        st.markdown(f"- Egresos paramétricos honorarios/retención: **{len(hr_rows)}** filas")
        for e in hr_rows[-10:]:
            cx = crud_p.obtener_categoria_por_id(e.categoria_id)
            cod = (cx.codigo if cx else "?")
            st.caption(
                f"  · id {e.id} **{cod}** · ${float(_dec(e.monto_estimado) or 0):,.0f} · "
                f"día pago {e.dia_pago} · mes_aplicación **{e.mes_aplicacion}**"
            )
        _fp = date.today()
        _facts = _facturas_ultimas_cargas(user_id)
        _vmin = None
        for _f in _facts:
            if _f.fecha_vencimiento is not None:
                _vmin = _f.fecha_vencimiento if _vmin is None else min(_vmin, _f.fecha_vencimiento)
        _p0 = _vmin if (_vmin is not None and _vmin < _fp) else _fp
        _p1 = _fp + timedelta(days=30)
        st.info(
            f"Ventana **aproximada** al generar con **30 días** hoy: **`{_p0}`** → **`{_p1}`**. "
            f"Fuera de ese tramo no hay líneas en el snapshot (use 60/90 días o corrija fechas)."
        )

    with st.expander("Parámetros fiscales y días de pago", expanded=False):
        render_modulo_parametros_usuario(usuario)

    with st.expander("Configuración de comparativo", expanded=False):
        categorias_tab1 = crud_p.listar_categorias_tab1_usuario(user_id)
        mapeo_actual = crud_p.obtener_mapeo_conceptos_tab1_dict(user_id)
        if not categorias_tab1:
            st.info(
                "Aún no hay categorías históricas detectadas en Tab 1 para este usuario. "
                "El mapeo quedará disponible cuando existan transacciones clasificadas."
            )
        else:
            st.caption(
                "Este mapeo permitirá comparar proyectado vs ejecutado por concepto, "
                "aunque el cliente use nombres personalizados en Tab 1."
            )
            opciones = ["-- Sin mapeo --"] + categorias_tab1
            seleccion_local: Dict[str, str] = {}
            for concepto in CONCEPTOS_ORDEN:
                if concepto in ("🏦 Saldo Cartola", "💰 Posición Neta Acum."):
                    continue
                actual = mapeo_actual.get(concepto, "-- Sin mapeo --")
                idx = opciones.index(actual) if actual in opciones else 0
                seleccion_local[concepto] = st.selectbox(
                    f"{concepto}",
                    options=opciones,
                    index=idx,
                    key=f"map_{concepto}",
                )

            _map_inv: Dict[str, List[str]] = {}
            for _concepto, _categoria in seleccion_local.items():
                if _categoria and _categoria != "-- Sin mapeo --":
                    _map_inv.setdefault(_categoria, []).append(_concepto)
            _dups_cfg = {k: v for k, v in _map_inv.items() if len(v) > 1}
            if _dups_cfg:
                st.warning(
                    "Hay categorías Tab 1 asignadas a más de un concepto. "
                    "Esto puede duplicar el ejecutado en el comparativo: "
                    + " | ".join([f"{cat} → {', '.join(concs)}" for cat, concs in _dups_cfg.items()])
                )

            if st.button("Guardar mapeo conceptos Tab 1", key="btn_guardar_mapeo_tab1"):
                if _dups_cfg:
                    st.error(
                        "No se guardó el mapeo porque hay categorías Tab 1 repetidas en varios conceptos. "
                        "Deja cada categoría en un solo concepto y vuelve a guardar."
                    )
                else:
                    for concepto, categoria in seleccion_local.items():
                        if categoria == "-- Sin mapeo --":
                            crud_p.eliminar_mapeo_concepto_tab1(user_id, concepto)
                        else:
                            crud_p.upsert_mapeo_concepto_tab1(user_id, concepto, categoria)
                    st.success("Mapeo guardado.")

    with st.expander("Importaciones y pagos al exterior", expanded=False):
        st.caption(
            "Este formulario alimenta las líneas de Proveedores Extranjeros, Gastos Aduana/Flete e IVA Importación."
        )
        with st.form("form_importaciones"):
            i1, i2 = st.columns(2)
            with i1:
                proveedor_extranjero = st.text_input("Proveedor extranjero")
                invoice_numero = st.text_input("Invoice número")
                estado_importacion = st.selectbox(
                    "Estado",
                    options=["activa", "en_transito", "cerrada", "anulada"],
                    index=0,
                )
                notas_importacion = st.text_area("Notas", placeholder="Observaciones de la importación")
            with i2:
                monto_cif_clp = st.number_input("Monto CIF CLP", min_value=0.0, step=1000.0, value=0.0)
                gastos_aduana_estimados = st.number_input("Gastos aduana/flete estimados", min_value=0.0, step=1000.0, value=0.0)
                iva_diferido_estimado = st.number_input("IVA importación estimado", min_value=0.0, step=1000.0, value=0.0)

            f1, f2, f3, f4 = st.columns(4)
            with f1:
                usar_fecha_pago = st.checkbox("Definir fecha pago proveedor", value=False, key="chk_fecha_pago_imp")
                fecha_pago_proveedor = st.date_input("Fecha pago proveedor extranjero", value=date.today(), key="dt_fecha_pago_imp")
            with f2:
                usar_eta_est = st.checkbox("Definir ETA estimada", value=False, key="chk_eta_est_imp")
                eta_estimada = st.date_input("ETA estimada", value=date.today(), key="dt_eta_est_imp")
            with f3:
                usar_eta_real = st.checkbox("Definir ETA real", value=False, key="chk_eta_real_imp")
                eta_real = st.date_input("ETA real", value=date.today(), key="dt_eta_real_imp")
            with f4:
                usar_fecha_iva = st.checkbox("Definir fecha impacto IVA", value=False, key="chk_fecha_iva_imp")
                fecha_impacto_iva = st.date_input("Fecha impacto IVA (Tesorería)", value=date.today(), key="dt_fecha_iva_imp")

            guardar_imp = st.form_submit_button("Guardar importación", type="primary")

        if guardar_imp:
            try:
                crud_p.crear_proyeccion_importacion(
                    user_id=user_id,
                    proveedor_extranjero=proveedor_extranjero or None,
                    invoice_numero=invoice_numero or None,
                    monto_cif_clp=monto_cif_clp if monto_cif_clp > 0 else None,
                    gastos_aduana_estimados=gastos_aduana_estimados if gastos_aduana_estimados > 0 else None,
                    iva_diferido_estimado=iva_diferido_estimado if iva_diferido_estimado > 0 else None,
                    fecha_pago_proveedor=fecha_pago_proveedor if usar_fecha_pago else None,
                    eta_estimada=eta_estimada if usar_eta_est else None,
                    eta_real=eta_real if usar_eta_real else None,
                    fecha_impacto_iva=fecha_impacto_iva if usar_fecha_iva else None,
                    estado=estado_importacion,
                    notas=notas_importacion or None,
                )
                st.success("Importación guardada correctamente.")
                st.rerun()
            except Exception as ex:
                st.error(f"No se pudo guardar importación: {ex}")

        imps = crud_p.listar_proyeccion_importaciones(user_id)
        if imps:
            rows_imp = []
            for imp in imps[:30]:
                rows_imp.append(
                    {
                        "id": imp.id,
                        "estado": imp.estado,
                        "invoice": imp.invoice_numero,
                        "proveedor_extranjero": imp.proveedor_extranjero,
                        "monto_cif_clp": float(_dec(imp.monto_cif_clp)),
                        "fecha_pago_proveedor": imp.fecha_pago_proveedor,
                        "eta_estimada": imp.eta_estimada,
                        "eta_real": imp.eta_real,
                        "fecha_impacto_iva_tesoreria": imp.fecha_impacto_iva,
                    }
                )
            _dataframe_proyeccion(
                pd.DataFrame(rows_imp),
                money_cols=["monto_cif_clp"],
                date_cols=[
                    "fecha_pago_proveedor",
                    "eta_estimada",
                    "eta_real",
                    "fecha_impacto_iva_tesoreria",
                ],
                use_container_width=True,
                hide_index=True,
            )

            st.markdown("**Gestión de importaciones guardadas**")
            imp_opts = {f"ID {imp.id} · {imp.invoice_numero or 's/invoice'} · {imp.estado or 'sin estado'}": imp for imp in imps}
            sel_key = st.selectbox("Seleccionar importación", options=list(imp_opts.keys()), key="sel_imp_edit")
            imp_sel = imp_opts[sel_key]

            cedit1, cedit2, cedit3 = st.columns(3)
            with cedit1:
                if st.button("Marcar cerrada", key="btn_imp_cerrar"):
                    crud_p.actualizar_proyeccion_importacion(imp_sel.id, estado="cerrada")
                    st.success(f"Importación {imp_sel.id} marcada como cerrada.")
                    st.rerun()
            with cedit2:
                if st.button("Marcar anulada", key="btn_imp_anular"):
                    crud_p.actualizar_proyeccion_importacion(imp_sel.id, estado="anulada")
                    st.success(f"Importación {imp_sel.id} marcada como anulada.")
                    st.rerun()
            with cedit3:
                if st.button("Eliminar importación", key="btn_imp_eliminar", type="secondary"):
                    crud_p.eliminar_proyeccion_importacion(imp_sel.id)
                    st.success(f"Importación {imp_sel.id} eliminada.")
                    st.rerun()

            with st.expander("Editar importación seleccionada", expanded=False):
                with st.form("form_editar_importacion"):
                    e1, e2 = st.columns(2)
                    with e1:
                        proveedor_edit = st.text_input("Proveedor extranjero", value=imp_sel.proveedor_extranjero or "")
                        invoice_edit = st.text_input("Invoice número", value=imp_sel.invoice_numero or "")
                        estado_edit = st.selectbox(
                            "Estado",
                            options=["activa", "en_transito", "cerrada", "anulada"],
                            index=["activa", "en_transito", "cerrada", "anulada"].index((imp_sel.estado or "activa")) if (imp_sel.estado or "activa") in ["activa", "en_transito", "cerrada", "anulada"] else 0,
                            key="estado_edit_importacion",
                        )
                        notas_edit = st.text_area("Notas", value=imp_sel.notas or "")
                    with e2:
                        monto_cif_edit = st.number_input("Monto CIF CLP", min_value=0.0, step=1000.0, value=float(_dec(imp_sel.monto_cif_clp)))
                        gastos_edit = st.number_input("Gastos aduana/flete estimados", min_value=0.0, step=1000.0, value=float(_dec(imp_sel.gastos_aduana_estimados)))
                        iva_edit = st.number_input("IVA importación estimado", min_value=0.0, step=1000.0, value=float(_dec(imp_sel.iva_diferido_estimado)))

                    fe1, fe2, fe3, fe4 = st.columns(4)
                    with fe1:
                        usar_fp = st.checkbox("Definir fecha pago proveedor", value=imp_sel.fecha_pago_proveedor is not None, key="chk_fp_edit")
                        fp_edit = st.date_input("Fecha pago proveedor", value=imp_sel.fecha_pago_proveedor or date.today(), key="dt_fp_edit")
                    with fe2:
                        usar_eta_est = st.checkbox("Definir ETA estimada", value=imp_sel.eta_estimada is not None, key="chk_eta_est_edit")
                        eta_est_edit = st.date_input("ETA estimada", value=imp_sel.eta_estimada or date.today(), key="dt_eta_est_edit")
                    with fe3:
                        usar_eta_real_e = st.checkbox("Definir ETA real", value=imp_sel.eta_real is not None, key="chk_eta_real_edit")
                        eta_real_edit = st.date_input("ETA real", value=imp_sel.eta_real or date.today(), key="dt_eta_real_edit")
                    with fe4:
                        usar_fiva = st.checkbox("Definir fecha impacto IVA", value=imp_sel.fecha_impacto_iva is not None, key="chk_fiva_edit")
                        fiva_edit = st.date_input("Fecha impacto IVA (Tesorería)", value=imp_sel.fecha_impacto_iva or date.today(), key="dt_fiva_edit")

                    guardar_edit = st.form_submit_button("Guardar cambios importación", type="primary")

                if guardar_edit:
                    crud_p.actualizar_proyeccion_importacion(
                        imp_sel.id,
                        proveedor_extranjero=proveedor_edit or None,
                        invoice_numero=invoice_edit or None,
                        estado=estado_edit,
                        notas=notas_edit or None,
                        monto_cif_clp=monto_cif_edit if monto_cif_edit > 0 else None,
                        gastos_aduana_estimados=gastos_edit if gastos_edit > 0 else None,
                        iva_diferido_estimado=iva_edit if iva_edit > 0 else None,
                        fecha_pago_proveedor=fp_edit if usar_fp else None,
                        eta_estimada=eta_est_edit if usar_eta_est else None,
                        eta_real=eta_real_edit if usar_eta_real_e else None,
                        fecha_impacto_iva=fiva_edit if usar_fiva else None,
                    )
                    st.success(f"Importación {imp_sel.id} actualizada.")
                    st.rerun()

    with st.expander("Honorarios líquidos", expanded=False):
        st.caption(
            "Registra pagos de **honorarios líquidos** (`📤 Honorarios líquidos`). "
            "Las retenciones de 2da categoría **ya no se proyectan como egreso separado**: "
            "deben incluirse en el **F29 código 91** (parámetros fiscales). "
            "El impuesto único de nómina tampoco se proyecta aparte (va en el mismo F29)."
        )
        cat_h = crud_p.obtener_categoria_por_codigo("HONORARIOS")
        if not cat_h:
            st.error("No se encontró la categoría HONORARIOS en `categorias_financieras`.")
        else:
            with st.form("form_honorarios_retenciones"):
                desc_h = st.text_input("Descripción honorario", value="Honorarios profesionales")
                monto_h = st.number_input("Monto honorario líquido", min_value=0.0, step=1000.0, value=0.0)
                fecha_h = st.date_input(
                    "Mes del honorario (referencia)",
                    value=date.today(),
                    key="dt_honorario_pago",
                    help="Define el **mes** del período. El pago del líquido puede ser fin de mes o el día exacto (opción abajo).",
                )
                honorario_fin_mes = st.checkbox(
                    "Honorario líquido: pago el último día del mes",
                    value=True,
                    key="chk_hr_hon_fin_mes",
                    help="Proyecta el egreso de honorarios el **último día calendario** del mes de la referencia (p. ej. marzo → 31).",
                )
                guardar_hr = st.form_submit_button("Guardar honorario líquido", type="primary")

                if guardar_hr:
                    if monto_h <= 0:
                        st.warning("Ingrese un monto de honorario mayor que 0.")
                    else:
                        mes_app = date(fecha_h.year, fecha_h.month, 1)
                        if honorario_fin_mes:
                            dia_hon = calendar.monthrange(fecha_h.year, fecha_h.month)[1]
                        else:
                            dia_hon = fecha_h.day
                        crud_p.crear_proyeccion_egreso_parametrico(
                            user_id=user_id,
                            categoria_id=cat_h.id,
                            descripcion=desc_h or "Honorarios líquidos",
                            monto_estimado=monto_h,
                            dia_pago=dia_hon,
                            mes_aplicacion=mes_app,
                            es_recurrente=False,
                        )
                        st.success(
                            f"Honorario líquido guardado (día {dia_hon}, mes {mes_app.year}-{mes_app.month:02d}). "
                            "La retención tributaria debe ir en F29 código 91."
                        )
                        st.rerun()

            # Vista de últimos registros de honorarios (líquidos). Históricos RETENCION se listan
            # solo para consulta/eliminación manual; no entran a snapshots nuevos.
            cat_r = crud_p.obtener_categoria_por_codigo("RETENCION")
            eg = crud_p.listar_proyeccion_egresos_parametricos(user_id)
            target_ids = {cat_h.id}
            if cat_r:
                target_ids.add(cat_r.id)
            rows_hr = []
            for e in eg:
                if e.categoria_id not in target_ids:
                    continue
                c = crud_p.obtener_categoria_por_id(e.categoria_id)
                rows_hr.append(
                    {
                        "id": e.id,
                        "categoría": c.nombre if c else e.categoria_id,
                        "descripción": e.descripcion,
                        "monto": float(_dec(e.monto_estimado)),
                        "día_pago": e.dia_pago,
                        "mes_aplicación": e.mes_aplicacion,
                        "recurrente": e.es_recurrente,
                    }
                )
            if rows_hr:
                df_hr = pd.DataFrame(rows_hr).sort_values(
                    ["mes_aplicación", "día_pago"], ascending=[False, False]
                )
                _dataframe_proyeccion(
                    df_hr,
                    money_cols=["monto"],
                    use_container_width=True,
                    hide_index=True,
                )
                st.caption(
                    "Solo los honorarios líquidos se proyectan. Filas RETENCION históricas "
                    "permanecen en BD pero se excluyen de nuevas proyecciones (usar F29 c.91)."
                )
                by_hr_id: Dict[int, Dict[str, Any]] = {int(r["id"]): r for r in rows_hr}
                oid_pick = sorted(by_hr_id.keys(), reverse=True)

                def _fmt_hr_elim(oid: int) -> str:
                    if oid == 0:
                        return "— Ninguno —"
                    r = by_hr_id[oid]
                    return (
                        f"Id {oid} · {r['categoría']} · ${r['monto']:,.0f} · "
                        f"día {r['día_pago']} · {r['mes_aplicación']}"
                    )

                sel_hr_del = st.selectbox(
                    "Eliminar egreso paramétrico",
                    options=[0] + oid_pick,
                    format_func=_fmt_hr_elim,
                    key=f"sel_elim_hr_eg_{user_id}",
                )
                if st.button(
                    "Eliminar seleccionado",
                    key=f"btn_elim_hr_eg_{user_id}",
                    disabled=sel_hr_del == 0,
                ):
                    try:
                        if crud_p.eliminar_proyeccion_egreso_parametrico(sel_hr_del, user_id):
                            st.success(f"Egreso paramétrico {sel_hr_del} eliminado.")
                            st.rerun()
                        else:
                            st.error("No se eliminó (registro inexistente o no es suyo).")
                    except Exception as ex:
                        st.error(f"No se pudo eliminar: {ex}")

    with st.expander("Pasivos / Créditos bancarios", expanded=False):
        st.caption(
            "Registra créditos para proyectar cuotas mensuales automáticas en "
            "`📤 Créditos bancarios` dentro del flujo. Se proyectan automáticamente "
            "hasta completar las cuotas pendientes."
        )
        with st.form("form_creditos_bancarios"):
            cb1, cb2, cb3 = st.columns(3)
            with cb1:
                desc_cr = st.text_input("Nombre del crédito", value="Crédito bancario")
                monto_credito = st.number_input("Monto crédito (referencial)", min_value=0.0, step=100000.0, value=0.0)
            with cb2:
                saldo_pend = st.number_input("Saldo pendiente", min_value=0.0, step=100000.0, value=0.0)
                monto_cuota = st.number_input("Monto cuota", min_value=0.0, step=10000.0, value=0.0)
            with cb3:
                fecha_prox = st.date_input("Fecha próximo pago", value=date.today(), key="dt_credito_prox")
                cuotas_pend = st.number_input("N° cuotas pendientes", min_value=1, step=1, value=1)
            guardar_cr = st.form_submit_button("Guardar crédito", type="primary")
            if guardar_cr:
                if monto_cuota <= 0:
                    st.warning("Ingrese un monto de cuota mayor a 0.")
                else:
                    crud_p.crear_proyeccion_credito_bancario(
                        user_id=user_id,
                        descripcion=desc_cr or "Crédito bancario",
                        monto_credito=monto_credito if monto_credito > 0 else None,
                        saldo_pendiente=saldo_pend if saldo_pend > 0 else None,
                        fecha_proximo_pago=fecha_prox,
                        monto_cuota=monto_cuota,
                        cuotas_pendientes=int(cuotas_pend),
                        activo=True,
                    )
                    st.success("Crédito guardado.")
                    st.rerun()

        cred = crud_p.listar_proyeccion_creditos_bancarios(user_id, solo_activos=False)
        if cred:
            rows_cr = [
                {
                    "id": c.id,
                    "descripción": c.descripcion,
                    "monto_crédito": float(_dec(c.monto_credito)),
                    "saldo_pendiente": float(_dec(c.saldo_pendiente)),
                    "próximo_pago": c.fecha_proximo_pago,
                    "monto_cuota": float(_dec(c.monto_cuota)),
                    "cuotas_pendientes": int(c.cuotas_pendientes or 0),
                    "activo": bool(c.activo),
                }
                for c in cred
            ]
            df_cr = pd.DataFrame(rows_cr).sort_values(["activo", "próximo_pago"], ascending=[False, True])
            _dataframe_proyeccion(
                df_cr,
                money_cols=["monto_crédito", "saldo_pendiente", "monto_cuota"],
                date_cols=["próximo_pago"],
                use_container_width=True,
                hide_index=True,
            )
            by_id_cr: Dict[int, Dict[str, Any]] = {int(r["id"]): r for r in rows_cr}
            pick_cr = sorted(by_id_cr.keys(), reverse=True)

            def _fmt_cr(oid: int) -> str:
                if oid == 0:
                    return "— Ninguno —"
                r = by_id_cr[oid]
                return (
                    f"Id {oid} · {r['descripción']} · cuota ${r['monto_cuota']:,.0f} · "
                    f"{r['cuotas_pendientes']} cuotas · próximo {r['próximo_pago']}"
                )

            sel_cr_del = st.selectbox(
                "Eliminar crédito",
                options=[0] + pick_cr,
                format_func=_fmt_cr,
                key=f"sel_elim_credito_{user_id}",
            )
            if st.button(
                "Eliminar crédito seleccionado",
                key=f"btn_elim_credito_{user_id}",
                disabled=sel_cr_del == 0,
            ):
                try:
                    if crud_p.eliminar_proyeccion_credito_bancario(sel_cr_del, user_id):
                        st.success(f"Crédito {sel_cr_del} eliminado.")
                        st.rerun()
                    else:
                        st.error("No se eliminó (registro inexistente o no es suyo).")
                except Exception as ex:
                    st.error(f"No se pudo eliminar: {ex}")

            activos = [r for r in rows_cr if bool(r.get("activo")) and int(r.get("cuotas_pendientes") or 0) > 0]
            if activos:
                by_id_act: Dict[int, Dict[str, Any]] = {int(r["id"]): r for r in activos}
                act_ids = sorted(by_id_act.keys(), reverse=True)

                def _fmt_cr_pago(oid: int) -> str:
                    if oid == 0:
                        return "— Ninguno —"
                    r = by_id_act[oid]
                    return (
                        f"Id {oid} · {r['descripción']} · cuota ${r['monto_cuota']:,.0f} · "
                        f"pendientes {r['cuotas_pendientes']} · próximo {r['próximo_pago']}"
                    )

                sel_cr_pago = st.selectbox(
                    "Marcar cuota pagada (crédito activo)",
                    options=[0] + act_ids,
                    format_func=_fmt_cr_pago,
                    key=f"sel_pago_credito_{user_id}",
                )
                if st.button(
                    "Registrar pago de 1 cuota",
                    key=f"btn_pago_credito_{user_id}",
                    disabled=sel_cr_pago == 0,
                ):
                    try:
                        upd = crud_p.registrar_pago_cuota_credito_bancario(sel_cr_pago, user_id)
                        if not upd:
                            st.error("No se encontró el crédito seleccionado.")
                        else:
                            st.success(
                                f"Cuota registrada. Pendientes: {int(upd.cuotas_pendientes or 0)} · "
                                f"próximo pago: {upd.fecha_proximo_pago} · activo: {bool(upd.activo)}"
                            )
                            st.rerun()
                    except Exception as ex:
                        st.error(f"No se pudo registrar el pago: {ex}")

    st.subheader("Carga de datos")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown(
            '<div class="proy-upload-card">'
            '<p class="proy-upload-title">📥 Subir Facturas por Cobrar (desde tu ERP)</p>',
            unsafe_allow_html=True,
        )
        up_cxc = st.file_uploader(
            "Facturas por Cobrar (ERP)",
            type=["xlsx", "xls"],
            key="up_cxc",
            label_visibility="collapsed",
        )
        if up_cxc and st.button("Procesar Facturas por Cobrar", key="btn_cxc"):
            try:
                data = up_cxc.getvalue()
                r = cargar_excel_cxc_cxp(
                    user_id, data, up_cxc.name, es_cxc=True,
                )
                st.success(f"Cargadas {r.facturas_guardadas} facturas (carga #{r.carga_id}).")
                if r.advertencias:
                    with st.expander("Advertencias parser"):
                        for a in r.advertencias[:50]:
                            st.caption(a)
            except Exception as ex:
                st.error(str(ex))
        st.markdown("</div>", unsafe_allow_html=True)
    with c2:
        st.markdown(
            '<div class="proy-upload-card">'
            '<p class="proy-upload-title">📤 Subir Facturas por Pagar (desde tu ERP)</p>',
            unsafe_allow_html=True,
        )
        up_cxp = st.file_uploader(
            "Facturas por Pagar (ERP)",
            type=["xlsx", "xls"],
            key="up_cxp",
            label_visibility="collapsed",
        )
        if up_cxp and st.button("Procesar Facturas por Pagar", key="btn_cxp"):
            try:
                data = up_cxp.getvalue()
                r = cargar_excel_cxc_cxp(
                    user_id, data, up_cxp.name, es_cxc=False,
                )
                st.success(f"Cargadas {r.facturas_guardadas} facturas (carga #{r.carga_id}).")
                if r.advertencias:
                    with st.expander("Advertencias parser"):
                        for a in r.advertencias[:50]:
                            st.caption(a)
            except Exception as ex:
                st.error(str(ex))
        st.markdown("</div>", unsafe_allow_html=True)
    with c3:
        st.markdown(
            '<div class="proy-upload-card">'
            '<p class="proy-upload-title">👥 Subir Libro de Remuneraciones</p>',
            unsafe_allow_html=True,
        )
        up_rem = st.file_uploader(
            "Libro de remuneraciones",
            type=["xlsx", "xls"],
            key="up_rem",
            label_visibility="collapsed",
        )
        mes_def = st.date_input(
            "Mes aplicación (fallback si el Excel no trae periodo)",
            value=date.today().replace(day=1),
            key="mes_rem",
            help="Solo se usa si el libro no trae el período en el encabezado (p. ej. «Julio de 2026»).",
        )
        if up_rem and st.button("Procesar remuneraciones", key="btn_rem"):
            try:
                data = up_rem.getvalue()
                r = cargar_excel_remuneraciones(
                    user_id,
                    data,
                    up_rem.name,
                    mes_aplicacion_default=mes_def,
                    preset_columnas="dag",
                )
                st.success(
                    f"Guardadas {r.filas_guardadas} filas válidas (carga #{r.carga_id})"
                    + (
                        f" · período {r.mes_aplicacion_usado.strftime('%Y-%m')}"
                        if r.mes_aplicacion_usado
                        else ""
                    )
                    + "."
                )
                if r.advertencias:
                    with st.expander("Advertencias parser"):
                        for a in r.advertencias[:50]:
                            st.caption(a)
            except Exception as ex:
                st.error(str(ex))
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown(
        '<div class="proy-data-summary-card"><div class="proy-data-summary-title">Resumen datos cargados (última carga CxC/CxP)</div>',
        unsafe_allow_html=True,
    )
    fact_cargadas = _facturas_ultimas_cargas(user_id)
    cxc_carg = sum(_monto_factura(f) for f in fact_cargadas if f.tipo == "por_cobrar")
    cxp_carg = sum(_monto_factura(f) for f in fact_cargadas if f.tipo == "por_pagar")
    # Algunos ERP (p. ej. KAMA) traen CxP con saldo negativo; restar ese total hace cxc - (-cxp) y
    # infla el "Saldo Cobrar - Pagar". Aquí se usa magnitud en pagar y neto = cobrar − pagar.
    cxp_mag = abs(cxp_carg)
    saldo_cob_menos_pag = cxc_carg - cxp_mag
    r1, r2, r3, r4 = st.columns(4)
    r1.metric("Facturas por Cobrar", f"${cxc_carg:,.0f}")
    r2.metric("Facturas por Pagar", f"${cxp_mag:,.0f}")
    r3.metric("Saldo Cobrar - Pagar", f"${saldo_cob_menos_pag:,.0f}")
    r4.metric("Registros facturas", f"{len(fact_cargadas):,}")
    st.caption("Este resumen usa solo la última carga de CxC y CxP para mantener una base limpia antes de proyectar.")
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown('<div class="proy-section-title">📋 Consultar documentos pendientes (Facturas por Cobrar y Facturas por Pagar)</div>', unsafe_allow_html=True)
    st.caption(
        "Consulta operativa independiente de la proyección: revisa vencidos, por vencer o todo en base a la última carga."
    )
    fecha_consulta = date.today()
    estado_det = st.radio(
        "Estado pendientes",
        options=["Todos", "Por vencer", "Vencidos"],
        horizontal=True,
        index=1,
        key=f"estado_detalle_carga_{user_id}",
    )

    def _aplica_estado_det(fecha_evento: date) -> bool:
        if estado_det == "Todos":
            return True
        if estado_det == "Por vencer":
            return fecha_evento >= fecha_consulta
        return fecha_evento < fecha_consulta

    fact_det = [f for f in fact_cargadas if f.fecha_vencimiento and _aplica_estado_det(f.fecha_vencimiento)]
    if fact_det:
        tipo_opts_det = []
        cxc_n = sum(1 for f in fact_det if f.tipo == "por_cobrar")
        cxp_n = sum(1 for f in fact_det if f.tipo == "por_pagar")
        if cxc_n:
            tipo_opts_det.append("Facturas por Cobrar")
        if cxp_n:
            tipo_opts_det.append("Facturas por Pagar")
        d1, d2, d3 = st.columns([1, 1, 1])
        with d1:
            tipo_det = st.selectbox(
                "Tipo de documento",
                options=tipo_opts_det,
                key=f"detalle_tipo_carga_{user_id}",
            )
        tipo_fact_sel = "por_cobrar" if "Cobrar" in tipo_det else "por_pagar"
        fact_tipo = [f for f in fact_det if f.tipo == tipo_fact_sel]
        fechas_tipo = sorted({f.fecha_vencimiento for f in fact_tipo if f.fecha_vencimiento})
        if fechas_tipo:
            min_tipo = min(fechas_tipo)
            max_tipo = max(fechas_tipo)
        else:
            min_tipo = fecha_consulta
            max_tipo = fecha_consulta
        with d2:
            fecha_desde_det = st.date_input(
                "Vencimiento desde",
                value=min_tipo,
                min_value=min_tipo,
                max_value=max_tipo,
                key=f"detalle_desde_carga_{user_id}",
            )
        with d3:
            fecha_hasta_det = st.date_input(
                "Vencimiento hasta",
                value=max_tipo,
                min_value=min_tipo,
                max_value=max_tipo,
                key=f"detalle_hasta_carga_{user_id}",
            )
        if fecha_desde_det > fecha_hasta_det:
            st.warning("Rango inválido: 'Vencimiento desde' es mayor que 'Vencimiento hasta'.")
            fact_sel = []
        else:
            fact_sel = [
                f for f in fact_tipo
                if f.fecha_vencimiento and fecha_desde_det <= f.fecha_vencimiento <= fecha_hasta_det
            ]
        if fact_sel:
            total_sel = sum(_monto_factura(f) for f in fact_sel)
            st.markdown(
                f"**{tipo_det}** | **Vencimiento:** {fecha_desde_det} → {fecha_hasta_det} | "
                f"**Documentos:** {len(fact_sel):,} | **Total:** ${float(total_sel):,.0f}"
            )
            det_rows = []
            for f in fact_sel:
                det_rows.append(
                    {
                        "razon social": f.razon_social or "",
                        "folio": f.folio or "",
                        "fecha emision": f.fecha_emision,
                        "fecha vencimiento": f.fecha_vencimiento,
                        "condicion venta": f.condicion_venta or "",
                        "total doc": float(_dec(f.monto_total)),
                        "saldo": float(_monto_factura(f)),
                    }
                )
            df_det_pend = pd.DataFrame(det_rows).sort_values(
                ["fecha vencimiento", "razon social", "folio"],
                ascending=[True, True, True],
            )
            _dataframe_proyeccion(
                df_det_pend,
                money_cols=["total doc", "saldo"],
                date_cols=["fecha emision", "fecha vencimiento"],
                text_wide_cols=["razon social", "condicion venta"],
                pinned_text_cols=["razon social"],
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.caption("No hay documentos para el tipo/estado/rango de vencimiento seleccionados.")
    else:
        st.caption("No hay documentos en la última carga para el estado seleccionado.")
    st.markdown('<div class="proy-proj-card"><div class="proy-proj-title">🚀 Sección Proyección</div></div>', unsafe_allow_html=True)
    st.subheader("Generar proyección")
    st.caption("Paso 1: define horizonte y crea/actualiza tu proyección.")
    psel = st.radio("Horizonte", options=[30, 60, 90], format_func=lambda d: f"{d} días", horizontal=True)
    etiqueta = st.text_input("Etiqueta (opcional)", placeholder="Ej. Escenario base marzo")
    notas = st.text_area("Notas (opcional)", placeholder="Supuestos del escenario")
    _, col_btn, _ = st.columns([1, 2.2, 1])
    with col_btn:
        st.markdown('<div class="proy-cta-wrap">', unsafe_allow_html=True)
        generar_click = st.button(
            "Generar proyección",
            type="primary",
            use_container_width=True,
            key="btn_generar_proyeccion_principal",
        )
        st.markdown("</div>", unsafe_allow_html=True)
    if generar_click:
        try:
            snap, avisos_f29 = generar_snapshot(user_id, psel, etiqueta=etiqueta or None, notas=notas or None)
            st.session_state["ultimo_snapshot_proy"] = snap.id
            st.session_state["avisos_f29_ultimos"] = list(avisos_f29 or [])
            st.session_state["msg_ok_proyeccion"] = (
                f"Proyección guardada v{snap.version} creada (id {snap.id})."
            )
            st.rerun()
        except Exception as ex:
            st.error(str(ex))

    msg_ok = st.session_state.pop("msg_ok_proyeccion", None)
    if msg_ok:
        st.success(msg_ok)
    for aviso in st.session_state.pop("avisos_f29_ultimos", []) or []:
        st.warning(aviso)

    snaps = crud_p.listar_proyeccion_snapshots(user_id, limite=80)
    if not snaps:
        st.info("No hay proyecciones guardadas. Genere una después de cargar Facturas por Cobrar/Pagar o datos mínimos.")
        return

    opts = {f"v{s.version} · {(s.etiqueta or 'sin etiqueta')[:40]} · {s.fecha_proyeccion} (id {s.id})": s.id for s in snaps}
    default_key = st.session_state.get("ultimo_snapshot_proy")
    default_idx = 0
    if default_key:
        for i, sid in enumerate(opts.values()):
            if sid == default_key:
                default_idx = i
                break
    with st.expander("Filtros de visualización de proyección", expanded=False):
        st.caption("Paso 2: selecciona proyección activa y define el período visible.")
        choice = st.selectbox("Proyección activa", options=list(opts.keys()), index=default_idx)
        sid = opts[choice]
        snap = crud_p.obtener_proyeccion_snapshot(sid)
        lineas = crud_p.listar_proyeccion_lineas_snapshot(sid) if snap else []

        if not snap:
            st.warning("No se pudo cargar la proyección seleccionada.")
            return

        st.markdown(
            f"""
            <div class="proy-banner">
            <b>Proyección activa:</b> v{snap.version} · {(snap.etiqueta or "sin etiqueta")} ·
            <b>Ventana del snapshot</b> (lo que se calculó al generar): {snap.periodo_inicio} → {snap.periodo_fin}.
            Facturas y remuneraciones con fechas fuera de ese tramo no quedan en la proyección guardada (hay que volver a generar con más días o ampliando datos).
            </div>
            """,
            unsafe_allow_html=True,
        )

        # ---- Filtro de período para visualización ----
        lineas_escenario = list(lineas)
        lineas_filtradas = list(lineas_escenario)
        # Filtros de visualización: por defecto simples para no sobrecargar la interfaz.
        fmin_snap = snap.periodo_inicio
        fmax_snap = snap.periodo_fin
        fmin_datos, fmax_datos = _rango_facturas_cargadas(user_id)
        fecha_analisis = date.today()
        st.caption(
            f"La proyección muestra solo flujo **futuro** (impactos desde **{fecha_analisis}** en adelante)."
        )

        def _aplica_estado(fecha_evento: date) -> bool:
            return fecha_evento >= fecha_analisis

        fact_ult = _facturas_ultimas_cargas(user_id)
        cxp_vencido_no_pagado = sum(
            _monto_factura(f)
            for f in fact_ult
            if f.tipo == "por_pagar"
            and f.fecha_vencimiento is not None
            and f.fecha_vencimiento < fecha_analisis
            and _monto_factura(f) > 0
        )
        incluir_arrastre_cxp = bool(st.session_state.get(f"toggle_arrastre_cxp_user_{user_id}", False))
        if incluir_arrastre_cxp and cxp_vencido_no_pagado > 0:
            cat_prov_nac = crud_p.obtener_categoria_por_codigo("PROV_NACIONAL")
            if cat_prov_nac:
                lineas_escenario.append(
                    SimpleNamespace(
                        id=-10_000_000 - sid,
                        fecha_impacto=fecha_analisis,
                        categoria_id=cat_prov_nac.id,
                        descripcion="Arrastre inicial CXP vencidos no pagados",
                        monto=-abs(cxp_vencido_no_pagado),
                        tipo_confianza="manual",
                        origen="parametrico",
                    )
                )
                lineas_filtradas = list(lineas_escenario)

        fuente_rango = "Proyección guardada"
        with st.expander("Opciones avanzadas de rango", expanded=False):
            fuente_rango = st.radio(
                "Fuente del rango",
                options=["Proyección guardada", "Datos cargados (Facturas por Cobrar/Pagar)"],
                index=0,
                horizontal=True,
                key=f"fuente_rango_snapshot_{sid}",
            )
            st.caption("Solo cambia fechas sugeridas para el rango personalizado; no recalcula la proyección.")
        # Límites del calenario: unión snapshot + facturas (créditos/IVA pueden ir más allá del último vencimiento CxC/CxP).
        fmin_bound = fmin_snap
        fmax_bound = fmax_snap
        if fmin_datos:
            fmin_bound = min(fmin_bound, fmin_datos)
        if fmax_datos:
            fmax_bound = max(fmax_bound, fmax_datos)

        st.caption("Filtro principal: define el período visible de la proyección activa.")
        if fuente_rango == "Datos cargados (Facturas por Cobrar/Pagar)" and fmin_datos and fmax_datos:
            fmin_default = fmin_datos
            fmax_default = fmax_datos
        else:
            if fuente_rango == "Datos cargados (Facturas por Cobrar/Pagar)" and (not fmin_datos or not fmax_datos):
                st.info("No hay facturas cargadas para usar rango de datos; se usa rango de la proyección guardada.")
            fmin_default = fmin_snap
            fmax_default = fmax_snap

        modo_vista = st.radio(
            "Ver período",
            options=["Horizonte proyección guardada", "Rango personalizado"],
            horizontal=True,
            key=f"modo_periodo_snapshot_{sid}",
        )
        if modo_vista == "Rango personalizado":
            cfd, cfh = st.columns(2)
            with cfd:
                fecha_desde = st.date_input(
                    "Desde",
                    value=fmin_default,
                    min_value=fmin_bound,
                    max_value=fmax_bound,
                    key=f"fecha_desde_snapshot_{sid}",
                )
            with cfh:
                fecha_hasta = st.date_input(
                    "Hasta",
                    value=fmax_default,
                    min_value=fmin_bound,
                    max_value=fmax_bound,
                    key=f"fecha_hasta_snapshot_{sid}",
                )
            fecha_desde_sel = fecha_desde
            fecha_hasta_sel = fecha_hasta
            if fecha_desde > fecha_hasta:
                st.warning("El rango es inválido: 'Desde' es mayor que 'Hasta'.")
                lineas_filtradas = []
            else:
                lineas_filtradas = [
                    l for l in lineas_escenario if fecha_desde <= l.fecha_impacto <= fecha_hasta and _aplica_estado(l.fecha_impacto)
                ]
                st.caption(
                    f"Mostrando {len(lineas_filtradas)} líneas entre {fecha_desde} y {fecha_hasta} "
                    f"(proyección guardada: {fmin_snap} a {fmax_snap}; calendario permitido: {fmin_bound} a {fmax_bound}; modo: futuro)."
                )
        else:
            fecha_desde_sel = fmin_snap
            fecha_hasta_sel = fmax_snap
            st.caption(
                f"Mostrando horizonte completo de la proyección guardada: {fmin_snap} a {fmax_snap} "
                f"(solo impactos desde {fecha_analisis})."
            )
            lineas_filtradas = [
                l
                for l in lineas_escenario
                if fmin_snap <= l.fecha_impacto <= fmax_snap and _aplica_estado(l.fecha_impacto)
            ]
        # Proyección y visualización trabajan solo con eventos futuros (desde hoy).
    incluir_arrastre_cxp_ui = st.toggle(
        "Incluir arrastre de CXP vencidos no pagados (día 1)",
        value=bool(st.session_state.get(f"toggle_arrastre_cxp_user_{user_id}", False)),
        key=f"toggle_arrastre_cxp_user_{user_id}",
        help="Si está activo, agrega al flujo proyectado un egreso inicial con CXP vencidos de la última carga.",
    )
    st.caption(f"CXP vencidos no pagados detectados: **${cxp_vencido_no_pagado:,.0f}**.")
    if incluir_arrastre_cxp_ui and cxp_vencido_no_pagado > 0:
        st.success(
            f"✅ Escenario ajustado: arrastre inicial de CXP vencidos activo por **${cxp_vencido_no_pagado:,.0f}**."
        )

    # Saldo inicial desde la misma cartola activa en Tab 1 (si existe), con fallback robusto.
    archivo_id_tab1 = _resolver_archivo_tab1_activo(user_id)

    # Detecta supuestos realmente presentes en el snapshot visible (no solo parámetros actuales).
    aplica_mora = any(
        "ajuste morosidad facturas por cobrar" in ((l.descripcion or "").strip().lower())
        for l in lineas
    )
    aplica_contado = any(
        "ventas contado esperadas" in ((l.descripcion or "").strip().lower())
        for l in lineas
    )
    aplica_recup_morosos = any(
        "recuperación cxc morosos" in ((l.descripcion or "").strip().lower())
        or "recuperacion cxc morosos" in ((l.descripcion or "").strip().lower())
        for l in lineas
    )
    aplica_compra_contado = any(
        "compras contado esperadas" in ((l.descripcion or "").strip().lower())
        for l in lineas
    )
    if aplica_mora or aplica_contado or aplica_recup_morosos or aplica_compra_contado:
        mensajes = []
        if aplica_mora:
            mensajes.append("morosidad en Facturas por Cobrar")
        if aplica_contado:
            mensajes.append("ventas contado esperadas")
        if aplica_recup_morosos:
            mensajes.append("recuperación de CxC morosos")
        if aplica_compra_contado:
            mensajes.append("compras contado esperadas")
        st.warning(
            "La proyección actual incluye supuestos del cliente: "
            + ", ".join(mensajes)
            + "."
        )

    pct_riesgo = _fraccion_flujo_estimado_manual_lineas(lineas_filtradas)
    if pct_riesgo > UMBRAL_CONFIANZA_BAJA:
        st.warning(
            f"Más del {UMBRAL_CONFIANZA_BAJA:.0%} del flujo (por monto absoluto) es **estimado o manual** "
            f"({pct_riesgo:.1%}). Interpretar la proyección con precaución."
        )

    total_ing = sum(_dec(l.monto) for l in lineas_filtradas if _dec(l.monto) > 0)
    total_egr = sum(_dec(l.monto) for l in lineas_filtradas if _dec(l.monto) < 0)
    # KPI de cobros alineado con la fila CxC de la matriz (mismo universo que usa el detalle).
    total_cxc_proy = Decimal(0)
    total_contado_proy = Decimal(0)
    total_recup_morosos_proy = Decimal(0)
    total_compra_contado_proy = Decimal(0)
    neg_clientes_en_flujo = Decimal(0)  # reducciones CxC (p. ej. mora) ya neteadas en el KPI verde
    _cat_cache_cxc: Dict[int, str] = {}
    for _l in lineas_filtradas:
        _m = _dec(_l.monto)
        _cid = int(_l.categoria_id)
        if _cid not in _cat_cache_cxc:
            _c = crud_p.obtener_categoria_por_id(_cid)
            _cat_cache_cxc[_cid] = ((_c.codigo if _c else "") or "").strip().upper()
        if _cat_cache_cxc[_cid] == "CLIENTES":
            total_cxc_proy += _m
            if _m < 0:
                neg_clientes_en_flujo += _m
            _desc_l = ((_l.descripcion or "").strip().lower())
            if "ventas contado esperadas" in _desc_l:
                total_contado_proy += _m
            if "recuperación cxc morosos" in _desc_l or "recuperacion cxc morosos" in _desc_l:
                total_recup_morosos_proy += _m
        if _cat_cache_cxc[_cid] == "PROV_NACIONAL":
            _desc_l = ((_l.descripcion or "").strip().lower())
            if "compras contado esperadas" in _desc_l:
                total_compra_contado_proy += _m
    total_cxc_credito_neto = total_cxc_proy - total_contado_proy - total_recup_morosos_proy
    # Egresos mostrados: sin filas negativas CLIENTES (van ya dentro del neto "Cobros CxC").
    total_egr_kpi = total_egr - neg_clientes_en_flujo
    flujo_total_todas_lineas = total_ing + total_egr
    # Saldo neto del bloque KPI = exactamente verde + roja (criterio usuario).
    saldo_neto_periodo = total_cxc_proy + total_egr_kpi
    colm1, colm2, colm3, colm4 = st.columns(4)
    with colm1:
        st.markdown(
            f"""
            <div class="proy-kpi-card proy-kpi-ing">
              <div class="proy-kpi-label">Cobros CxC proyectados</div>
              <div class="proy-kpi-value">${total_cxc_proy:,.0f}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    st.caption(
        f"Desglose cobros CxC: crédito neto **${total_cxc_credito_neto:,.0f}** + "
        f"ventas contado proyectadas **${total_contado_proy:,.0f}** + "
        f"recuperación morosos **${total_recup_morosos_proy:,.0f}** = **${total_cxc_proy:,.0f}**."
    )
    with colm2:
        st.markdown(
            f"""
            <div class="proy-kpi-card proy-kpi-egr">
              <div class="proy-kpi-label">Egresos (otras categorías)</div>
              <div class="proy-kpi-value">${total_egr_kpi:,.0f}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    if neg_clientes_en_flujo != 0:
        st.caption(
            f"Reducciones ya incluidas en *Cobros CxC* (p. ej. morosidad): **${neg_clientes_en_flujo:,.0f}**. "
            f"No se repiten en egresos. **Saldo neto período = Cobros CxC + Egresos (otras categorías)**."
        )
    if total_compra_contado_proy != 0:
        st.caption(
            f"Desglose egresos: compras contado proyectadas **${total_compra_contado_proy:,.0f}** (incluidas en egresos totales)."
        )
    with colm3:
        st.markdown(
            f"""
            <div class="proy-kpi-card proy-kpi-net">
              <div class="proy-kpi-label">Saldo neto período</div>
              <div class="proy-kpi-value">${saldo_neto_periodo:,.0f}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with colm4:
        st.markdown(
            f"""
            <div class="proy-kpi-card proy-kpi-risk">
              <div class="proy-kpi-label">Ponderación estimado+manual</div>
              <div class="proy-kpi-value">{pct_riesgo:.1%}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    _fuera_bloque_kpi = flujo_total_todas_lineas - saldo_neto_periodo
    if abs(_fuera_bloque_kpi) > Decimal("500"):
        st.caption(
            f"En el mismo período, el detalle suma **${flujo_total_todas_lineas:,.0f}** en todas las líneas; "
            f"la diferencia **${_fuera_bloque_kpi:,.0f}** son netos en categorías no cubiertas por estas dos tarjetas (p. ej. IVA)."
        )
    # Saldo inicial/arrastre visible desde Tab 1 para lectura de caja real.
    # Prioridad: saldo ya calculado en Tab 1 (misma sesión) para consistencia exacta.
    saldo_ss = st.session_state.get("saldo_tab1_actual")
    if saldo_ss is not None:
        try:
            saldo_cartola_real = float(saldo_ss)
        except Exception:
            saldo_cartola_real = float(_obtener_saldo_cartola_real(user_id, archivo_id_tab1))
    else:
        saldo_cartola_real = float(_obtener_saldo_cartola_real(user_id, archivo_id_tab1))
    s1, s2 = st.columns(2)
    s1.metric("Saldo inicial caja (Tab 1)", f"${saldo_cartola_real:,.0f}")
    s2.metric("Saldo final proyectado (inicial + flujo neto)", f"${(saldo_cartola_real + float(saldo_neto_periodo)):,.0f}")

    # ---- Exportación Excel / PDF (solo lectura del snapshot visible; no regenera) ----
    from modulo_exportacion_proyeccion import (
        ContextoExportacionProyeccion,
        FacturaExportacion,
        LineaExportacion,
        ParametrosExportacion,
        concepto_desde_codigo,
        exportar_excel_y_pdf,
    )

    _origen_alias_exp = {
        "upload_excel": "Carga Excel",
        "parametrico": "Cálculo automático",
    }
    _id_nom_exp: Dict[int, str] = {}
    _id_cod_exp: Dict[int, str] = {}
    for _cid in {int(l.categoria_id) for l in lineas_filtradas}:
        _c = crud_p.obtener_categoria_por_id(_cid)
        if _c:
            _id_nom_exp[_cid] = _c.nombre or ""
            _id_cod_exp[_cid] = (_c.codigo or "").strip().upper()

    _lineas_exp: List[Any] = []
    _periodo_rem_fuente: Optional[str] = None
    for _l in lineas_filtradas:
        _cod = _id_cod_exp.get(int(_l.categoria_id), "")
        _nom = _id_nom_exp.get(int(_l.categoria_id), str(_l.categoria_id))
        _concepto = concepto_desde_codigo(_cod, _nom)
        _desc = (_l.descripcion or "").strip()
        if "base est." in _desc.lower():
            import re as _re_exp

            _m_rem = _re_exp.search(r"base est\.\s*(\d{4}-\d{2})", _desc, flags=_re_exp.IGNORECASE)
            if _m_rem:
                _periodo_rem_fuente = _m_rem.group(1)
        _lineas_exp.append(
            LineaExportacion(
                fecha=_l.fecha_impacto,
                concepto=_concepto,
                categoria=_nom,
                descripcion=_desc,
                monto=_dec(_l.monto),
                confianza=(_l.tipo_confianza or "").strip() or "—",
                origen=_origen_alias_exp.get(
                    (_l.origen or "").strip().lower(), (_l.origen or "—")
                ),
            )
        )

    _params_u = crud_p.obtener_proyeccion_parametros_usuario(user_id)
    _params_exp = ParametrosExportacion(
        tasa_ppm=_dec(_params_u.tasa_ppm) if _params_u and _params_u.tasa_ppm is not None else None,
        tasa_retencion_honorarios=(
            _dec(_params_u.tasa_retencion_honorarios)
            if _params_u and _params_u.tasa_retencion_honorarios is not None
            else None
        ),
        dia_pago_impuestos=int(_params_u.dia_pago_impuestos) if _params_u and _params_u.dia_pago_impuestos is not None else None,
        dia_pago_remuneraciones=(
            int(_params_u.dia_pago_remuneraciones)
            if _params_u and _params_u.dia_pago_remuneraciones is not None
            else None
        ),
        dia_pago_imposiciones=(
            int(_params_u.dia_pago_imposiciones)
            if _params_u and _params_u.dia_pago_imposiciones is not None
            else None
        ),
        venta_global_esperada_mes=(
            _dec(_params_u.venta_global_esperada_mes)
            if _params_u and _params_u.venta_global_esperada_mes is not None
            else None
        ),
        porcentaje_ventas_contado=(
            _dec(_params_u.porcentaje_ventas_contado)
            if _params_u and _params_u.porcentaje_ventas_contado is not None
            else None
        ),
        compra_global_esperada_mes=(
            _dec(_params_u.compra_global_esperada_mes)
            if _params_u and _params_u.compra_global_esperada_mes is not None
            else None
        ),
        porcentaje_compras_contado=(
            _dec(_params_u.porcentaje_compras_contado)
            if _params_u and _params_u.porcentaje_compras_contado is not None
            else None
        ),
        porcentaje_morosidad_cxc=(
            _dec(_params_u.porcentaje_morosidad_cxc)
            if _params_u and _params_u.porcentaje_morosidad_cxc is not None
            else None
        ),
        porcentaje_recuperabilidad_morosos=(
            _dec(_params_u.porcentaje_recuperabilidad_morosos)
            if _params_u and _params_u.porcentaje_recuperabilidad_morosos is not None
            else None
        ),
        periodo_fuente_remuneraciones=_periodo_rem_fuente,
    )

    _facts_exp: List[Any] = []
    for _f in _facturas_ultimas_cargas(user_id):
        _facts_exp.append(
            FacturaExportacion(
                tipo=(_f.tipo or "").strip().lower(),
                fecha_vencimiento=_f.fecha_vencimiento,
                razon_social=(_f.razon_social or "")[:200],
                folio=(_f.folio or "")[:50],
                monto=_monto_factura(_f),
                saldo=_dec(_f.saldo) if _f.saldo is not None else _monto_factura(_f),
                estado=(_f.estado or "")[:50],
                tipo_confianza=(_f.tipo_confianza or "real"),
            )
        )

    _advs_exp: List[str] = []
    if aplica_mora or aplica_contado or aplica_recup_morosos or aplica_compra_contado:
        _msgs = []
        if aplica_mora:
            _msgs.append("morosidad en Facturas por Cobrar")
        if aplica_contado:
            _msgs.append("ventas contado esperadas")
        if aplica_recup_morosos:
            _msgs.append("recuperación de CxC morosos")
        if aplica_compra_contado:
            _msgs.append("compras contado esperadas")
        _advs_exp.append("Supuestos del cliente activos: " + ", ".join(_msgs) + ".")
    if pct_riesgo > UMBRAL_CONFIANZA_BAJA:
        _advs_exp.append(
            f"Más del {UMBRAL_CONFIANZA_BAJA:.0%} del flujo es estimado o manual ({pct_riesgo:.1%})."
        )
    if incluir_arrastre_cxp_ui and cxp_vencido_no_pagado > 0:
        _advs_exp.append(
            f"Arrastre inicial CXP vencidos incluido: ${cxp_vencido_no_pagado:,.0f}."
        )
    if _periodo_rem_fuente:
        _advs_exp.append(
            f"Remuneraciones/imposiciones: período fuente {_periodo_rem_fuente} "
            f"de la última carga se usa como base estimada para cada mes del horizonte."
        )

    _empresa_exp = (getattr(usuario, "nombre_empresa", None) or "Empresa").strip() or "Empresa"
    # Rango exportado = filtros visibles de la UI (solo futuro), no el inicio histórico del snapshot.
    _rango_export_inicio = max(fecha_desde_sel, fecha_analisis)
    _rango_export_fin = fecha_hasta_sel
    if _rango_export_inicio > _rango_export_fin:
        _rango_export_inicio = _rango_export_fin
    _ctx_export = ContextoExportacionProyeccion(
        user_id=int(user_id),
        snapshot_user_id=int(getattr(snap, "user_id", user_id)),
        empresa=_empresa_exp,
        fecha_emision=date.today(),
        snapshot_id=int(snap.id),
        version=int(snap.version),
        etiqueta=(snap.etiqueta or "")[:100],
        notas=(snap.notas or "")[:2000],
        periodo_inicio=_rango_export_inicio,
        periodo_fin=_rango_export_fin,
        saldo_inicial=_dec(saldo_cartola_real),
        cobros_cxc=_dec(total_cxc_proy),
        egresos=_dec(total_egr_kpi),
        flujo_neto=_dec(saldo_neto_periodo),
        saldo_final=_dec(saldo_cartola_real) + _dec(saldo_neto_periodo),
        pct_estimado_manual=float(pct_riesgo),
        advertencias=_advs_exp,
        lineas=_lineas_exp,
        facturas=_facts_exp,
        parametros=_params_exp,
    )

    st.markdown('<div class="proy-section-title">Exportar proyección</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="proy-section-sub">Descarga el escenario visible (mismo usuario y snapshot). No recalcula ni guarda una nueva proyección.</div>',
        unsafe_allow_html=True,
    )
    _can_export = bool(snap and snap.id and int(getattr(snap, "user_id", user_id)) == int(user_id))
    _bx1, _bx2 = st.columns(2)
    if _can_export:
        try:
            _xlsx_bytes, _pdf_bytes, _n_xlsx, _n_pdf = exportar_excel_y_pdf(_ctx_export)
        except Exception as _ex_exp:
            _xlsx_bytes = _pdf_bytes = None
            st.error(f"No se pudo generar la exportación: {_ex_exp}")
        else:
            with _bx1:
                st.download_button(
                    "📊 Descargar Excel",
                    data=_xlsx_bytes,
                    file_name=_n_xlsx,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key=f"dl_xlsx_proy_{sid}_{user_id}",
                    type="primary",
                    use_container_width=True,
                )
            with _bx2:
                st.download_button(
                    "📄 Descargar PDF",
                    data=_pdf_bytes,
                    file_name=_n_pdf,
                    mime="application/pdf",
                    key=f"dl_pdf_proy_{sid}_{user_id}",
                    type="primary",
                    use_container_width=True,
                )
    else:
        st.info("Seleccione una proyección válida de su cuenta para habilitar la descarga.")

    if lineas_filtradas:
        fechas, montos, doms = _agregacion_diaria_waterfall(lineas_filtradas)
        if fechas:
            with st.expander("Evolución diaria del flujo (visual opcional)", expanded=False):
                vista_graf = st.radio(
                    "Tipo de gráfico",
                    options=["Neto diario (barras)", "Acumulado (línea)", "Waterfall detallado"],
                    horizontal=True,
                    key=f"graf_tipo_snapshot_{sid}",
                )
                _serie = pd.DataFrame({"fecha": pd.to_datetime(fechas), "neto_dia": montos}).sort_values("fecha")
                if vista_graf == "Neto diario (barras)":
                    st.bar_chart(_serie.set_index("fecha")["neto_dia"], use_container_width=True)
                elif vista_graf == "Acumulado (línea)":
                    _serie["acumulado"] = _serie["neto_dia"].cumsum() + float(_obtener_saldo_cartola_real(user_id, archivo_id_tab1))
                    st.line_chart(_serie.set_index("fecha")["acumulado"], use_container_width=True)
                else:
                    st.plotly_chart(_fig_waterfall(fechas, montos, doms), use_container_width=True)

        cats_ids = {l.categoria_id for l in lineas_filtradas}
        id_nombre: Dict[int, str] = {}
        id_codigo: Dict[int, str] = {}
        for cid in cats_ids:
            c = crud_p.obtener_categoria_por_id(cid)
            if c:
                id_nombre[cid] = c.nombre
                id_codigo[cid] = c.codigo

        def _concepto_desde_linea(categoria_codigo: str, categoria_nombre: str) -> str:
            cod = (categoria_codigo or "").strip().upper()
            if cod == "CLIENTES":
                return "📥 CxC — Pago Clientes"
            if cod == "PROV_NACIONAL":
                return "📤 Proveedores Nacionales"
            if cod == "PROV_EXTRANJERO":
                return "📤 Proveedores Extranjeros"
            if cod == "REMUNERACIONES":
                return "📤 Remuneraciones"
            if cod == "IMPOSICIONES":
                return "📤 Imposiciones AFP/Salud"
            if cod == "IU_NOMINA":
                return "📤 Impuesto único nómina"
            if cod == "CREDITO_BANCARIO":
                return "📤 Créditos bancarios"
            if cod == "HONORARIOS":
                return "📤 Honorarios líquidos"
            if cod == "RETENCION":
                return "📤 Retenciones 2da categoría"
            if cod == "IVA":
                return "📤 IVA Neto"
            if cod == "PPM":
                return "📤 PPM"
            if cod == "F29_91":
                return "📤 F29 total a pagar — código 91"
            if cod == "GASTOS_IMPORTACION":
                return "📤 Gastos Aduana/Flete"
            if cod == "IVA_IMPORTACION":
                return "📤 IVA Importación"
            if cod:
                return "📤 Categoría personalizada (cliente)"
            if "cliente" in (categoria_nombre or "").lower():
                return "📥 CxC — Pago Clientes"
            return "📤 Categoría personalizada (cliente)"

        rows = []
        concepto_alias = {
            "📥 CxC — Pago Clientes": "📥 Facturas por Cobrar — Clientes",
            "📤 Proveedores Nacionales": "📤 Facturas por Pagar — Proveedores Nacionales",
            "📤 Proveedores Extranjeros": "📤 Facturas por Pagar — Proveedores Extranjeros",
        }
        origen_alias = {
            "upload_excel": "Carga Excel",
            "parametrico": "Cálculo automático",
        }
        for l in sorted(lineas_filtradas, key=lambda x: (x.fecha_impacto, x.id)):
            codigo = id_codigo.get(l.categoria_id, "")
            nombre = id_nombre.get(l.categoria_id, str(l.categoria_id))
            concepto_raw = _concepto_desde_linea(codigo, nombre)
            rows.append(
                {
                    "fecha": l.fecha_impacto,
                    "concepto": concepto_raw,
                    "concepto_ui": concepto_alias.get(concepto_raw, concepto_raw),
                    "categoría": nombre,
                    "descripción": l.descripcion,
                    "monto": float(_dec(l.monto)),
                    "confianza": l.tipo_confianza,
                    "origen": origen_alias.get((l.origen or "").strip().lower(), l.origen),
                }
            )
        df_det = pd.DataFrame(rows)
        mapeo_tab1 = crud_p.obtener_mapeo_conceptos_tab1_dict(user_id)
        df_det["categoría_tab1_mapeada"] = df_det["concepto"].map(mapeo_tab1).fillna("")

        with st.expander("Detalle extendido de facturas por vencer (opcional)", expanded=False):
            st.markdown('<div class="proy-section-title">Facturas por vencer (ordenado por tipo)</div>', unsafe_allow_html=True)
            st.markdown(
                '<div class="proy-section-sub">Ingreso (cobros) a la izquierda y egreso (pagos) a la derecha para lectura rápida.</div>',
                unsafe_allow_html=True,
            )
            cxc_df = df_det[df_det["concepto"] == "📥 CxC — Pago Clientes"].copy()
            cxp_df = df_det[
                df_det["concepto"].isin(["📤 Proveedores Nacionales", "📤 Proveedores Extranjeros"])
            ].copy()
            cxc_df["concepto"] = cxc_df["concepto_ui"]
            cxp_df["concepto"] = cxp_df["concepto_ui"]
            b1, b2 = st.columns(2)
            with b1:
                st.markdown("**📥 Facturas por Cobrar (cobros)**")
                _dataframe_proyeccion(
                    cxc_df.sort_values(["fecha", "monto"], ascending=[True, False]),
                    money_cols=["monto"],
                    date_cols=["fecha"],
                    text_wide_cols=["concepto", "descripción", "categoría"],
                    pinned_text_cols=["concepto"],
                    use_container_width=True,
                    hide_index=True,
                )
            with b2:
                st.markdown("**📤 Facturas por Pagar (pagos)**")
                _dataframe_proyeccion(
                    cxp_df.sort_values(["fecha", "monto"], ascending=[True, True]),
                    money_cols=["monto"],
                    date_cols=["fecha"],
                    text_wide_cols=["concepto", "descripción", "categoría"],
                    pinned_text_cols=["concepto"],
                    use_container_width=True,
                    hide_index=True,
                )

        # Matriz concepto x fecha para lectura ejecutiva.
        df_m = df_det.copy()
        df_m["fecha"] = pd.to_datetime(df_m["fecha"]).dt.strftime("%Y-%m-%d")
        pivot = (
            df_m.groupby(["concepto", "fecha"], as_index=False)["monto"]
            .sum()
            .pivot(index="concepto", columns="fecha", values="monto")
            .fillna(0.0)
        )
        # Conectar saldo cartola real de Tab 1.
        if "🏦 Saldo Cartola" not in pivot.index:
            pivot.loc["🏦 Saldo Cartola"] = 0.0
        if len(pivot.columns) > 0:
            primera_col = list(pivot.columns)[0]
            pivot.loc["🏦 Saldo Cartola", :] = 0.0
            pivot.loc["🏦 Saldo Cartola", primera_col] = saldo_cartola_real

        for concepto in CONCEPTOS_ORDEN:
            if concepto not in pivot.index:
                pivot.loc[concepto] = 0.0
        pivot = pivot.loc[CONCEPTOS_ORDEN]
        # Posición neta acumulada por fecha = saldo inicial + acumulado de flujo operativo diario.
        _rows_excluir_total_dia = {"🏦 Saldo Cartola", "💰 Posición Neta Acum."}
        _base_oper = pivot.drop(index=list(_rows_excluir_total_dia), errors="ignore")
        if len(_base_oper.columns) > 0:
            _acum = float(saldo_cartola_real)
            for _col in list(_base_oper.columns):
                _acum += float(_base_oper[_col].sum())
                pivot.loc["💰 Posición Neta Acum.", _col] = _acum
        # Total por día (neto operativo): suma columnas por fecha excluyendo saldo inicial y acumulado.
        pivot_total_dia = pivot.drop(index=list(_rows_excluir_total_dia), errors="ignore").sum(axis=0)
        pivot = pivot.rename(index=concepto_alias)
        pivot["TOTAL"] = pivot.sum(axis=1)
        # Evita que TOTAL de saldo/posición sea suma de columnas; usar significado financiero.
        if "🏦 Saldo Cartola" in pivot.index:
            pivot.loc["🏦 Saldo Cartola", "TOTAL"] = float(saldo_cartola_real)
        if "💰 Posición Neta Acum." in pivot.index and len(pivot.columns) > 1:
            _ult_col = list(pivot.columns[:-1])[-1]
            pivot.loc["💰 Posición Neta Acum.", "TOTAL"] = float(pivot.loc["💰 Posición Neta Acum.", _ult_col])
        # Agrega fila resumen al final para lectura ejecutiva del total por día.
        fila_total_dia = pivot_total_dia.to_dict()
        fila_total_dia["TOTAL"] = float(pivot_total_dia.sum())
        pivot.loc["🧮 Total por día"] = fila_total_dia
        st.caption("Tablero principal: primero revisa esta matriz y luego baja al detalle rapido CxC/CxP.")
        st.markdown('<div class="proy-section-title">Concepto / Por vencer fechas</div>', unsafe_allow_html=True)
        st.markdown(
            '<div class="proy-section-sub">La fila <b>🧮 Total por día</b> resume el neto operativo diario del período visible.</div>',
            unsafe_allow_html=True,
        )
        pivot_show = pivot.reset_index()
        _pc0 = pivot_show.columns[0]
        pivot_show = pivot_show.rename(columns={_pc0: "Concepto"})
        pivot_cfg: Dict[str, Any] = {}
        try:
            from streamlit import column_config as cc

            pivot_cfg["Concepto"] = _text_column_streamlit("Concepto", width="large", pinned=True)
            for _col in pivot_show.columns[1:]:
                pivot_cfg[str(_col)] = cc.NumberColumn(str(_col), format="$%d")
        except Exception:
            pivot_cfg = {}
        _dataframe_proyeccion(
            pivot_show,
            column_config=pivot_cfg or None,
            use_container_width=True,
            hide_index=True,
        )
        with st.expander("Analisis avanzado", expanded=False):
            vista_adv = st.radio(
                "Vista análisis avanzado",
                options=["Resumen ejecutivo", "Detalle técnico"],
                horizontal=True,
                key=f"vista_analisis_adv_{sid}",
            )
            show_tecnico = vista_adv == "Detalle técnico"
            # ---- Comparación proyectado vs ejecutado (punto 3) ----
            st.subheader("Comparativo proyectado vs ejecutado (por concepto)")
            if show_tecnico:
                st.caption(
                    "El **ejecutado** viene de Tab 1 (cartola → `transacciones`). "
                    "Este bloque usa un **solo rango de fechas** para ambos lados: "
                    "**desde** la primera fecha con movimiento en la cartola que elijas (o la más antigua si elegís «Todas las cartolas») "
                    "y **hasta hoy**, para comparar lo que **ya debió** impactar según el snapshot con lo que **ya movió** el banco."
                )
                st.caption(
                    "El **proyectado** del comparativo usa la misma lógica de arriba: solo impactos con fecha desde hoy "
                    "y dentro del rango seleccionado. El rango amplio de la vista (matrices/KPIs) puede ser distinto."
                )
            else:
                st.caption("Resumen simple: compara proyectado vs ejecutado en la misma ventana de fechas.")

            archivos_cartola = obtener_archivos(user_id)
            if not archivos_cartola:
                st.warning(
                    "No se encontraron cartolas cargadas en Tab 1 para este usuario. "
                    "Carga una cartola en Tab 1 y vuelve aquí."
                )
                archivos_cartola = []

            cartola_opts: Dict[str, Optional[int]] = {"Todas las cartolas (Tab 1)": None}
            for a in archivos_cartola:
                cartola_opts[f"#{a.id} · {a.nombre_archivo} · {getattr(a, 'fecha_carga', '')}"] = a.id

            cartola_choice = st.selectbox(
                "Cartola (Tab 1) a usar como Ejecutado",
                options=list(cartola_opts.keys()),
                index=0,
                key=f"cartola_ejecutado_sel_{sid}",
            )
            archivo_id_sel = cartola_opts[cartola_choice]

            import datetime as _dt

            fecha_min_cart, _fecha_max_cart = obtener_rango_fechas_transacciones(user_id, archivo_id_sel)
            comp_hasta = date.today()
            comparativo_sin_datos = False
            if fecha_min_cart is None:
                st.warning(
                    "No hay movimientos en Tab 1 para la cartola seleccionada (o no hay datos cargados). "
                    "El comparativo necesita al menos un movimiento con fecha para fijar el inicio del período."
                )
                comparativo_sin_datos = True
                comp_desde = comp_hasta
            else:
                comp_desde = fecha_min_cart
                if comp_desde > comp_hasta:
                    st.warning(
                        "La primera fecha de la cartola es posterior a hoy; revisá fechas del archivo o del sistema. "
                        "Se usa un único día como ventana."
                    )
                    comp_hasta = comp_desde

            _etiq_cart = (
                "todas las cartolas cargadas"
                if archivo_id_sel is None
                else f"cartola #{archivo_id_sel}"
            )
            st.info(
                f"**Ventana del comparativo:** `{comp_desde}` → `{comp_hasta}` · "
                f"Inicio = primer movimiento en {_etiq_cart}; fin = **hoy** (mismo rango en proyectado y ejecutado)."
            )

            if not comparativo_sin_datos:
                if comp_hasta < snap.periodo_inicio or comp_desde > snap.periodo_fin:
                    if show_tecnico:
                        st.warning(
                            f"La ventana del comparativo (**{comp_desde} → {comp_hasta}**) **no se cruza** con la ventana del snapshot "
                            f"**{snap.periodo_inicio} → {snap.periodo_fin}**. "
                            "El **proyectado** del comparativo quedará ~0 en casi todo; el **ejecutado** sigue reflejando la cartola."
                        )
                elif comp_desde < snap.periodo_inicio or comp_hasta > snap.periodo_fin:
                    if show_tecnico:
                        st.info(
                            "Parte del comparativo queda **fuera** de la ventana del snapshot. "
                            "Solo cuentan para el proyectado las líneas del snapshot con fecha de impacto en la intersección."
                        )

            trans = []
            neto_por_categoria: Dict[str, Decimal] = {}
            proyectado_por_concepto: Dict[str, float] = {}
            if not comparativo_sin_datos:
                trans = obtener_transacciones(
                    usuario_id=user_id,
                    fecha_desde=_dt.datetime.combine(comp_desde, _dt.time.min),
                    fecha_hasta=_dt.datetime.combine(comp_hasta, _dt.time.max),
                    archivo_id=archivo_id_sel,
                )

                for t in trans:
                    cat = (getattr(t, "clasificacion", None) or "").strip()
                    if not cat:
                        continue
                    net = _dec(getattr(t, "abono", None)) - _dec(getattr(t, "cargo", None))
                    neto_por_categoria[cat] = neto_por_categoria.get(cat, Decimal(0)) + net

                lineas_comp = [
                    l
                    for l in lineas_escenario
                    if comp_desde <= l.fecha_impacto <= comp_hasta and _aplica_estado(l.fecha_impacto)
                ]
                cats_comp = {l.categoria_id for l in lineas_comp}
                for cid in cats_comp:
                    if cid not in id_nombre:
                        c = crud_p.obtener_categoria_por_id(cid)
                        if c:
                            id_nombre[cid] = c.nombre
                            id_codigo[cid] = c.codigo
                for l in lineas_comp:
                    codigo = id_codigo.get(l.categoria_id, "")
                    nombre = id_nombre.get(l.categoria_id, str(l.categoria_id))
                    concepto_raw = _concepto_desde_linea(codigo, nombre)
                    prev = Decimal(str(proyectado_por_concepto.get(concepto_raw, 0)))
                    proyectado_por_concepto[concepto_raw] = float(prev + _dec(l.monto))

            filas_comp = []
            conceptos_validos: List[str] = [
                c
                for c in CONCEPTOS_ORDEN
                if c not in ("🏦 Saldo Cartola", "💰 Posición Neta Acum.")
            ]
            for concepto in conceptos_validos:
                categoria_tab1 = (mapeo_tab1 or {}).get(concepto, "").strip()
                if not categoria_tab1:
                    continue
                p = _dec(proyectado_por_concepto.get(concepto, 0))
                e = neto_por_categoria.get(categoria_tab1, Decimal(0))
                diff = p - e
                diff_pct = (diff / e * 100) if e != 0 else None
                filas_comp.append(
                    {
                        "concepto": concepto,
                        "categoria_tab1": categoria_tab1,
                        "proyectado": float(p),
                        "ejecutado": float(e),
                        "diferencia": float(diff),
                        "%diferencia": (None if diff_pct is None else float(diff_pct)),
                    }
                )

            # Evita duplicar ejecutado cuando una categoría Tab 1 está mapeada a múltiples conceptos.
            _conceptos_por_cat: Dict[str, List[str]] = {}
            for _concepto in conceptos_validos:
                _cat = (mapeo_tab1 or {}).get(_concepto, "").strip()
                if _cat:
                    _conceptos_por_cat.setdefault(_cat, []).append(_concepto)
            _dups_comp = {k: v for k, v in _conceptos_por_cat.items() if len(v) > 1}
            if _dups_comp:
                if show_tecnico:
                    st.warning(
                        "Mapeo duplicado detectado en comparativo. "
                        "Para no inflar ejecutado, la categoría se aplica solo al primer concepto en orden: "
                        + " | ".join([f"{cat} → {', '.join(concs)}" for cat, concs in _dups_comp.items()])
                    )
                _seen_cat: set[str] = set()
                for _fila in filas_comp:
                    _cat = (_fila.get("categoria_tab1") or "").strip()
                    if not _cat:
                        continue
                    if _cat in _seen_cat:
                        _fila["ejecutado"] = 0.0
                        _fila["diferencia"] = float(_fila["proyectado"])
                        _fila["%diferencia"] = None
                    else:
                        _seen_cat.add(_cat)

            categorias_con_mapeo = {
                (mapeo_tab1 or {}).get(c, "").strip()
                for c in conceptos_validos
                if (mapeo_tab1 or {}).get(c, "").strip()
            }
            for cat, net in neto_por_categoria.items():
                if cat in categorias_con_mapeo:
                    continue
                net_f = float(net)
                diff = -net_f
                diff_pct = (diff / net_f * 100) if net_f != 0 else None
                filas_comp.append(
                    {
                        "concepto": f"(Tab 1 — sin mapeo) {cat}",
                        "categoria_tab1": cat,
                        "proyectado": 0.0,
                        "ejecutado": net_f,
                        "diferencia": float(diff),
                        "%diferencia": (None if diff_pct is None else float(diff_pct)),
                    }
                )

            if comparativo_sin_datos:
                pass
            elif not filas_comp:
                st.info(
                    "Completa el mapeo `conceptos proyección ↔ categorías ejecutadas (Tab 1)` "
                    "para ver el comparativo por concepto."
                )
            else:
                df_comp = pd.DataFrame(filas_comp)
                order_idx = {c: i for i, c in enumerate(CONCEPTOS_ORDEN)}

                def _orden_concepto_comparativo(x: Any) -> int:
                    if x in order_idx:
                        return order_idx[x]
                    if str(x).startswith("(Tab 1"):
                        return 5000
                    return 8000

                df_comp["_ord"] = df_comp["concepto"].map(_orden_concepto_comparativo)
                df_comp["_ing"] = df_comp.apply(
                    lambda r: (
                        r["concepto"] in CONCEPTOS_INGRESO_COMPARATIVO
                        or (
                            str(r["concepto"]).startswith("(Tab 1")
                            and float(r["ejecutado"]) > 0
                        )
                    ),
                    axis=1,
                )
                df_ing = df_comp[df_comp["_ing"]].sort_values("_ord").drop(columns=["_ing", "_ord"])
                df_egr = df_comp[~df_comp["_ing"]].sort_values("_ord").drop(columns=["_ing", "_ord"])
                df_ing = df_ing.copy()
                df_egr = df_egr.copy()
                df_ing["concepto"] = df_ing["concepto"].map(concepto_alias).fillna(df_ing["concepto"])
                df_egr["concepto"] = df_egr["concepto"].map(concepto_alias).fillna(df_egr["concepto"])

                cols_base = ["concepto", "proyectado", "ejecutado", "diferencia", "%diferencia"]
                cols_full = ["concepto", "categoria_tab1", "proyectado", "ejecutado", "diferencia", "%diferencia"]
                _cols_show = cols_full if (show_tecnico and not modo_presentacion) else cols_base
                _text_wide = ["concepto"] if (not show_tecnico or modo_presentacion) else ["concepto", "categoria_tab1"]

                st.caption(
                    "**Ingresos:** cobros a clientes (CxC) y, en Tab 1 sin mapeo, categorías con neto **> 0**. "
                    "**Egresos:** el resto (incluye Tab 1 sin mapeo con neto ≤ 0)."
                )
                st.markdown("**Ingresos (proyectado vs ejecutado)**")
                if df_ing.empty:
                    st.caption("Sin ítems de ingreso en este período.")
                else:
                    _dataframe_proyeccion(
                        df_ing[_cols_show],
                        money_cols=["proyectado", "ejecutado", "diferencia"],
                        pct_cols=["%diferencia"],
                        text_wide_cols=_text_wide,
                        pinned_text_cols=["concepto"],
                        use_container_width=True,
                        hide_index=True,
                    )
                st.markdown("**Egresos (proyectado vs ejecutado)**")
                if df_egr.empty:
                    st.caption("Sin ítems de egreso en este período.")
                else:
                    _dataframe_proyeccion(
                        df_egr[_cols_show],
                        money_cols=["proyectado", "ejecutado", "diferencia"],
                        pct_cols=["%diferencia"],
                        text_wide_cols=_text_wide,
                        pinned_text_cols=["concepto"],
                        use_container_width=True,
                        hide_index=True,
                    )
                if show_tecnico:
                    st.caption(
                        "Definición (este cuadro): **Ejecutado** = Abonos − Cargos en Tab 1 con fecha entre "
                        f"**{comp_desde}** y **{comp_hasta}** (misma cartola que elegiste arriba). "
                        "**Proyectado** = suma de líneas del snapshot "
                        f"**v{snap.version}** con **fecha de impacto futura** en ese mismo rango. "
                        "Ventana guardada del snapshot: "
                        f"**{snap.periodo_inicio} → {snap.periodo_fin}**."
                    )

            if show_tecnico:
                st.markdown("---")
                st.markdown("**Posicion neta y detalle completo**")
                # Posición neta acumulada por fecha.
                neto_dia = (
                    df_m.groupby("fecha", as_index=False)["monto"]
                    .sum()
                    .sort_values("fecha")
                )
                neto_dia["posicion_neta_acum"] = neto_dia["monto"].cumsum() + saldo_cartola_real
                st.markdown('<div class="proy-section-title">💰 Posición Neta Acumulada (por fecha)</div>', unsafe_allow_html=True)
                _dataframe_proyeccion(
                    neto_dia.rename(columns={"monto": "flujo_neto_dia"}),
                    money_cols=["flujo_neto_dia", "posicion_neta_acum"],
                    use_container_width=True,
                    hide_index=True,
                )

                if not modo_presentacion:
                    st.markdown('<div class="proy-section-title">Detalle completo por línea</div>', unsafe_allow_html=True)
                    df_det_show = df_det.copy()
                    df_det_show["concepto"] = df_det_show["concepto_ui"]
                    _dataframe_proyeccion(
                        df_det_show.drop(columns=["concepto_ui"]),
                        money_cols=["monto"],
                        date_cols=["fecha"],
                        text_wide_cols=["descripción", "categoría", "concepto", "categoría_tab1_mapeada"],
                        pinned_text_cols=["concepto"],
                        use_container_width=True,
                        hide_index=True,
                    )
    else:
        st.caption("No hay líneas para el período seleccionado.")
