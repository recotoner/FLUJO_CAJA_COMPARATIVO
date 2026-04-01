"""
CRUD para tablas del módulo de proyección de caja (Tab 2).
"""
from __future__ import annotations

import calendar
from datetime import date
from decimal import Decimal
from typing import Any, Dict, List, Optional, Sequence, Union

from sqlalchemy import desc, func
from sqlalchemy.exc import OperationalError

from database.connection import get_db, engine
from database.models import (
    CategoriaFinanciera,
    Clasificador,
    ProyeccionCarga,
    ProyeccionCreditoBancario,
    ProyeccionEgresoParametrico,
    ProyeccionFactura,
    ProyeccionImportacion,
    ProyeccionLinea,
    ProyeccionMapeoCategoria,
    ProyeccionParametrosUsuario,
    ProyeccionRemuneracion,
    ProyeccionSnapshot,
    Transaccion,
)

Number = Union[int, float, Decimal, None]


def _ensure_mapeo_categorias_table() -> None:
    """
    Garantiza existencia de la tabla de mapeo en entornos con BD ya creada.
    Evita romper la app cuando se agrega esta tabla en una iteración posterior.
    """
    ProyeccionMapeoCategoria.__table__.create(bind=engine, checkfirst=True)


def _ensure_creditos_bancarios_table() -> None:
    """Garantiza existencia de tabla de créditos bancarios en BD existentes."""
    ProyeccionCreditoBancario.__table__.create(bind=engine, checkfirst=True)


def _ensure_proyeccion_remuneraciones_columns() -> None:
    """Columnas nuevas en libro de remuneraciones (BD ya existente)."""
    ddl = [
        "ALTER TABLE proyeccion_remuneraciones ADD COLUMN monto_impuesto_unico DECIMAL(15, 0)",
        "ALTER TABLE proyeccion_remuneraciones ADD COLUMN monto_salud_adicional DECIMAL(15, 0)",
        "ALTER TABLE proyeccion_remuneraciones ADD COLUMN monto_cesantia DECIMAL(15, 0)",
    ]
    with engine.begin() as conn:
        for q in ddl:
            try:
                conn.exec_driver_sql(q)
            except Exception:
                pass


def _ensure_parametros_usuario_columns() -> None:
    """
    Asegura columnas nuevas de parámetros en BD existente (SQLite/Postgres).
    """
    ddl = [
        "ALTER TABLE proyeccion_parametros_usuario ADD COLUMN venta_global_esperada_mes DECIMAL(15, 0)",
        "ALTER TABLE proyeccion_parametros_usuario ADD COLUMN porcentaje_ventas_contado DECIMAL(5, 4)",
        "ALTER TABLE proyeccion_parametros_usuario ADD COLUMN compra_global_esperada_mes DECIMAL(15, 0)",
        "ALTER TABLE proyeccion_parametros_usuario ADD COLUMN porcentaje_compras_contado DECIMAL(5, 4)",
        "ALTER TABLE proyeccion_parametros_usuario ADD COLUMN porcentaje_morosidad_cxc DECIMAL(5, 4)",
        "ALTER TABLE proyeccion_parametros_usuario ADD COLUMN porcentaje_recuperabilidad_morosos DECIMAL(5, 4)",
    ]
    with engine.begin() as conn:
        for q in ddl:
            try:
                conn.exec_driver_sql(q)
            except Exception:
                # Columna ya existe u otro motor no requiere alter.
                pass


# --- Seed maestro categorías (diseño v2 / v3) ---
SEED_CATEGORIAS_FINANCIERAS: List[Dict[str, Any]] = [
    {"codigo": "CLIENTES", "nombre": "Pago de Clientes", "tipo": "ingreso", "orden_display": 10},
    {"codigo": "PROV_NACIONAL", "nombre": "Proveedores Nacionales", "tipo": "egreso", "orden_display": 20},
    {"codigo": "PROV_EXTRANJERO", "nombre": "Proveedores Extranjeros", "tipo": "egreso", "orden_display": 30},
    {"codigo": "REMUNERACIONES", "nombre": "Remuneraciones", "tipo": "egreso", "orden_display": 40},
    {"codigo": "IMPOSICIONES", "nombre": "Imposiciones", "tipo": "egreso", "orden_display": 50},
    {
        "codigo": "IU_NOMINA",
        "nombre": "Impuesto único nómina",
        "tipo": "egreso",
        "orden_display": 55,
    },
    {"codigo": "HONORARIOS", "nombre": "Honorarios", "tipo": "egreso", "orden_display": 60},
    {"codigo": "CREDITO_BANCARIO", "nombre": "Créditos bancarios", "tipo": "egreso", "orden_display": 65},
    {"codigo": "IVA", "nombre": "IVA Neto", "tipo": "egreso", "orden_display": 70},
    {"codigo": "IVA_IMPORTACION", "nombre": "IVA Importación", "tipo": "egreso", "orden_display": 80},
    {"codigo": "PPM", "nombre": "PPM", "tipo": "egreso", "orden_display": 90},
    {"codigo": "RETENCION", "nombre": "Retenciones", "tipo": "egreso", "orden_display": 100},
    {"codigo": "GASTOS_IMPORTACION", "nombre": "Gastos de Importación", "tipo": "egreso", "orden_display": 110},
    {"codigo": "IMPUESTOS", "nombre": "Impuestos SII", "tipo": "egreso", "orden_display": 120},
    {"codigo": "MULTAS_TGR", "nombre": "Multas / TGR", "tipo": "egreso", "orden_display": 130},
    {"codigo": "TRASPASO", "nombre": "Traspaso Interno", "tipo": "ambos", "orden_display": 140},
    {"codigo": "ASESORIA", "nombre": "Asesoría Estratégica", "tipo": "egreso", "orden_display": 150},
]


def _dec(v: Number) -> Optional[Decimal]:
    if v is None:
        return None
    if isinstance(v, Decimal):
        return v
    return Decimal(str(v))


def _sumar_un_mes_mismo_dia(fecha: date) -> date:
    """Mueve al mes siguiente preservando día (acotado al último día del mes)."""
    if fecha.month == 12:
        y, m = fecha.year + 1, 1
    else:
        y, m = fecha.year, fecha.month + 1
    last = calendar.monthrange(y, m)[1]
    return date(y, m, min(fecha.day, last))


def seed_categorias_financieras() -> int:
    """
    Inserta categorías maestras si no existen (idempotente por codigo).
    Si existe pero está inactiva (p. ej. en BD servidor tras pruebas), la reactiva.
    Retorna cantidad de filas insertadas o reactivadas.
    """
    db = next(get_db())
    inserted = 0
    reactivated = 0
    try:
        for row in SEED_CATEGORIAS_FINANCIERAS:
            ex = db.query(CategoriaFinanciera).filter(CategoriaFinanciera.codigo == row["codigo"]).first()
            if ex:
                if ex.activo is not True:
                    ex.activo = True
                    reactivated += 1
                continue
            db.add(
                CategoriaFinanciera(
                    codigo=row["codigo"],
                    nombre=row["nombre"],
                    tipo=row["tipo"],
                    aplica_tab1=True,
                    aplica_tab2=True,
                    orden_display=row.get("orden_display"),
                    activo=True,
                )
            )
            inserted += 1
        db.commit()
        return inserted + reactivated
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


# --- Categorías financieras ---
def listar_categorias_financieras(solo_activas: bool = True) -> List[CategoriaFinanciera]:
    db = next(get_db())
    try:
        q = db.query(CategoriaFinanciera).order_by(CategoriaFinanciera.orden_display, CategoriaFinanciera.id)
        if solo_activas:
            q = q.filter(CategoriaFinanciera.activo.is_(True))
        return q.all()
    finally:
        db.close()


def obtener_categoria_por_id(categoria_id: int) -> Optional[CategoriaFinanciera]:
    db = next(get_db())
    try:
        return db.query(CategoriaFinanciera).filter(CategoriaFinanciera.id == categoria_id).first()
    finally:
        db.close()


def obtener_categoria_por_codigo(codigo: str) -> Optional[CategoriaFinanciera]:
    db = next(get_db())
    try:
        q = db.query(CategoriaFinanciera).filter(CategoriaFinanciera.codigo == codigo)
        row = q.filter(CategoriaFinanciera.activo.is_(True)).order_by(CategoriaFinanciera.id).first()
        if row:
            return row
        return q.order_by(CategoriaFinanciera.id).first()
    finally:
        db.close()


def crear_categoria_financiera(
    codigo: str,
    nombre: str,
    tipo: str,
    *,
    aplica_tab1: bool = True,
    aplica_tab2: bool = True,
    orden_display: Optional[int] = None,
    activo: bool = True,
) -> CategoriaFinanciera:
    db = next(get_db())
    try:
        c = CategoriaFinanciera(
            codigo=codigo,
            nombre=nombre,
            tipo=tipo,
            aplica_tab1=aplica_tab1,
            aplica_tab2=aplica_tab2,
            orden_display=orden_display,
            activo=activo,
        )
        db.add(c)
        db.commit()
        db.refresh(c)
        return c
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def actualizar_categoria_financiera(categoria_id: int, **campos) -> Optional[CategoriaFinanciera]:
    db = next(get_db())
    try:
        c = db.query(CategoriaFinanciera).filter(CategoriaFinanciera.id == categoria_id).first()
        if not c:
            return None
        for k, v in campos.items():
            if hasattr(c, k):
                setattr(c, k, v)
        db.commit()
        db.refresh(c)
        return c
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def desactivar_categoria_financiera(categoria_id: int) -> bool:
    db = next(get_db())
    try:
        c = db.query(CategoriaFinanciera).filter(CategoriaFinanciera.id == categoria_id).first()
        if not c:
            return False
        c.activo = False
        db.commit()
        return True
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


# --- Proyección cargas ---
def crear_proyeccion_carga(
    user_id: int,
    tipo: str,
    nombre_archivo: Optional[str] = None,
    origen: str = "upload_excel",
    total_registros: Optional[int] = None,
    notas: Optional[str] = None,
) -> ProyeccionCarga:
    db = next(get_db())
    try:
        c = ProyeccionCarga(
            user_id=user_id,
            tipo=tipo,
            nombre_archivo=nombre_archivo,
            origen=origen,
            total_registros=total_registros,
            notas=notas,
        )
        db.add(c)
        db.commit()
        db.refresh(c)
        return c
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def obtener_proyeccion_carga(carga_id: int) -> Optional[ProyeccionCarga]:
    db = next(get_db())
    try:
        return db.query(ProyeccionCarga).filter(ProyeccionCarga.id == carga_id).first()
    finally:
        db.close()


def listar_proyeccion_cargas(
    user_id: int,
    tipo: Optional[str] = None,
    limite: int = 50,
) -> List[ProyeccionCarga]:
    db = next(get_db())
    try:
        q = db.query(ProyeccionCarga).filter(ProyeccionCarga.user_id == user_id)
        if tipo:
            q = q.filter(ProyeccionCarga.tipo == tipo)
        return q.order_by(desc(ProyeccionCarga.fecha_carga)).limit(limite).all()
    finally:
        db.close()


def actualizar_proyeccion_carga(carga_id: int, **campos) -> Optional[ProyeccionCarga]:
    db = next(get_db())
    try:
        c = db.query(ProyeccionCarga).filter(ProyeccionCarga.id == carga_id).first()
        if not c:
            return None
        for k, v in campos.items():
            if hasattr(c, k) and v is not None:
                setattr(c, k, v)
        db.commit()
        db.refresh(c)
        return c
    finally:
        db.close()


def eliminar_proyeccion_carga(carga_id: int) -> bool:
    """Elimina facturas/remuneraciones ligadas y luego la cabecera de carga."""
    db = next(get_db())
    try:
        c = db.query(ProyeccionCarga).filter(ProyeccionCarga.id == carga_id).first()
        if not c:
            return False
        db.query(ProyeccionFactura).filter(ProyeccionFactura.carga_id == carga_id).delete()
        db.query(ProyeccionRemuneracion).filter(ProyeccionRemuneracion.carga_id == carga_id).delete()
        db.delete(c)
        db.commit()
        return True
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


# --- Proyección facturas ---
def crear_proyeccion_factura(
    carga_id: int,
    user_id: int,
    tipo: str,
    fecha_vencimiento: date,
    *,
    rut_contraparte: Optional[str] = None,
    razon_social: Optional[str] = None,
    folio: Optional[str] = None,
    monto_neto: Number = None,
    monto_iva: Number = None,
    monto_total: Number = None,
    saldo: Number = None,
    fecha_emision: Optional[date] = None,
    condicion_venta: Optional[str] = None,
    estado: Optional[str] = None,
    tipo_confianza: str = "real",
) -> ProyeccionFactura:
    db = next(get_db())
    try:
        f = ProyeccionFactura(
            carga_id=carga_id,
            user_id=user_id,
            tipo=tipo,
            rut_contraparte=rut_contraparte,
            razon_social=razon_social,
            folio=folio,
            monto_neto=_dec(monto_neto),
            monto_iva=_dec(monto_iva),
            monto_total=_dec(monto_total),
            saldo=_dec(saldo),
            fecha_emision=fecha_emision,
            fecha_vencimiento=fecha_vencimiento,
            condicion_venta=condicion_venta,
            estado=estado,
            tipo_confianza=tipo_confianza,
        )
        db.add(f)
        db.commit()
        db.refresh(f)
        return f
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def crear_proyeccion_facturas_bulk(registros: Sequence[Dict[str, Any]]) -> int:
    """Inserta muchas facturas en una sesión. Cada dict debe incluir las claves requeridas del modelo."""
    if not registros:
        return 0
    db = next(get_db())
    try:
        objs = []
        for r in registros:
            copy = dict(r)
            for key in ("monto_neto", "monto_iva", "monto_total", "saldo"):
                if key in copy:
                    copy[key] = _dec(copy[key])
            objs.append(ProyeccionFactura(**copy))
        db.add_all(objs)
        db.commit()
        return len(objs)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def listar_proyeccion_facturas_por_carga(carga_id: int) -> List[ProyeccionFactura]:
    db = next(get_db())
    try:
        return (
            db.query(ProyeccionFactura)
            .filter(ProyeccionFactura.carga_id == carga_id)
            .order_by(ProyeccionFactura.fecha_vencimiento)
            .all()
        )
    finally:
        db.close()


def listar_proyeccion_facturas_usuario(
    user_id: int,
    tipo: Optional[str] = None,
    desde: Optional[date] = None,
    hasta: Optional[date] = None,
) -> List[ProyeccionFactura]:
    db = next(get_db())
    try:
        q = db.query(ProyeccionFactura).filter(ProyeccionFactura.user_id == user_id)
        if tipo:
            q = q.filter(ProyeccionFactura.tipo == tipo)
        if desde:
            q = q.filter(ProyeccionFactura.fecha_vencimiento >= desde)
        if hasta:
            q = q.filter(ProyeccionFactura.fecha_vencimiento <= hasta)
        return q.order_by(ProyeccionFactura.fecha_vencimiento).all()
    finally:
        db.close()


def obtener_proyeccion_factura(factura_id: int) -> Optional[ProyeccionFactura]:
    db = next(get_db())
    try:
        return db.query(ProyeccionFactura).filter(ProyeccionFactura.id == factura_id).first()
    finally:
        db.close()


def actualizar_proyeccion_factura(factura_id: int, **campos) -> Optional[ProyeccionFactura]:
    db = next(get_db())
    try:
        f = db.query(ProyeccionFactura).filter(ProyeccionFactura.id == factura_id).first()
        if not f:
            return None
        for k, v in campos.items():
            if not hasattr(f, k):
                continue
            if k in ("monto_neto", "monto_iva", "monto_total", "saldo"):
                v = _dec(v)
            setattr(f, k, v)
        db.commit()
        db.refresh(f)
        return f
    finally:
        db.close()


def eliminar_facturas_por_carga(carga_id: int) -> int:
    db = next(get_db())
    try:
        n = db.query(ProyeccionFactura).filter(ProyeccionFactura.carga_id == carga_id).delete()
        db.commit()
        return n
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def eliminar_proyeccion_factura(factura_id: int) -> bool:
    db = next(get_db())
    try:
        f = db.query(ProyeccionFactura).filter(ProyeccionFactura.id == factura_id).first()
        if not f:
            return False
        db.delete(f)
        db.commit()
        return True
    finally:
        db.close()


# --- Remuneraciones ---
def crear_proyeccion_remuneracion(
    carga_id: int,
    user_id: int,
    mes_aplicacion: date,
    *,
    empleado: Optional[str] = None,
    rut_empleado: Optional[str] = None,
    monto_bruto: Number = None,
    monto_liquido: Number = None,
    monto_imponible: Number = None,
    monto_afp: Number = None,
    monto_salud: Number = None,
    monto_salud_adicional: Number = None,
    monto_cesantia: Number = None,
    monto_impuesto_unico: Number = None,
    dia_pago: Optional[int] = None,
) -> ProyeccionRemuneracion:
    _ensure_proyeccion_remuneraciones_columns()
    db = next(get_db())
    try:
        r = ProyeccionRemuneracion(
            carga_id=carga_id,
            user_id=user_id,
            empleado=empleado,
            rut_empleado=rut_empleado,
            mes_aplicacion=mes_aplicacion,
            monto_bruto=_dec(monto_bruto),
            monto_liquido=_dec(monto_liquido),
            monto_imponible=_dec(monto_imponible),
            monto_afp=_dec(monto_afp),
            monto_salud=_dec(monto_salud),
            monto_salud_adicional=_dec(monto_salud_adicional),
            monto_cesantia=_dec(monto_cesantia),
            monto_impuesto_unico=_dec(monto_impuesto_unico),
            dia_pago=dia_pago,
        )
        db.add(r)
        db.commit()
        db.refresh(r)
        return r
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def crear_proyeccion_remuneraciones_bulk(registros: Sequence[Dict[str, Any]]) -> int:
    if not registros:
        return 0
    _ensure_proyeccion_remuneraciones_columns()
    db = next(get_db())
    try:
        objs = []
        for r in registros:
            copy = dict(r)
            for key in (
                "monto_bruto",
                "monto_liquido",
                "monto_imponible",
                "monto_afp",
                "monto_salud",
                "monto_salud_adicional",
                "monto_cesantia",
                "monto_impuesto_unico",
            ):
                if key in copy:
                    copy[key] = _dec(copy[key])
            objs.append(ProyeccionRemuneracion(**copy))
        db.add_all(objs)
        db.commit()
        return len(objs)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def listar_proyeccion_remuneraciones_carga(carga_id: int) -> List[ProyeccionRemuneracion]:
    _ensure_proyeccion_remuneraciones_columns()
    db = next(get_db())
    try:
        return db.query(ProyeccionRemuneracion).filter(ProyeccionRemuneracion.carga_id == carga_id).all()
    finally:
        db.close()


def listar_proyeccion_remuneraciones_usuario(user_id: int) -> List[ProyeccionRemuneracion]:
    db = next(get_db())
    try:
        return (
            db.query(ProyeccionRemuneracion)
            .filter(ProyeccionRemuneracion.user_id == user_id)
            .order_by(desc(ProyeccionRemuneracion.mes_aplicacion))
            .all()
        )
    finally:
        db.close()


def obtener_proyeccion_remuneracion(rem_id: int) -> Optional[ProyeccionRemuneracion]:
    db = next(get_db())
    try:
        return db.query(ProyeccionRemuneracion).filter(ProyeccionRemuneracion.id == rem_id).first()
    finally:
        db.close()


def actualizar_proyeccion_remuneracion(rem_id: int, **campos) -> Optional[ProyeccionRemuneracion]:
    db = next(get_db())
    try:
        r = db.query(ProyeccionRemuneracion).filter(ProyeccionRemuneracion.id == rem_id).first()
        if not r:
            return None
        for k, v in campos.items():
            if not hasattr(r, k):
                continue
            if k.startswith("monto_"):
                v = _dec(v)
            setattr(r, k, v)
        db.commit()
        db.refresh(r)
        return r
    finally:
        db.close()


def eliminar_remuneraciones_por_carga(carga_id: int) -> int:
    db = next(get_db())
    try:
        n = db.query(ProyeccionRemuneracion).filter(ProyeccionRemuneracion.carga_id == carga_id).delete()
        db.commit()
        return n
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


# --- Snapshots ---
def siguiente_version_snapshot(user_id: int) -> int:
    db = next(get_db())
    try:
        m = db.query(func.max(ProyeccionSnapshot.version)).filter(ProyeccionSnapshot.user_id == user_id).scalar()
        return (m or 0) + 1
    finally:
        db.close()


def crear_proyeccion_snapshot(
    user_id: int,
    fecha_proyeccion: date,
    periodo_inicio: date,
    periodo_fin: date,
    *,
    version: Optional[int] = None,
    etiqueta: Optional[str] = None,
    notas: Optional[str] = None,
) -> ProyeccionSnapshot:
    db = next(get_db())
    try:
        if version is None:
            version = (
                db.query(func.max(ProyeccionSnapshot.version)).filter(ProyeccionSnapshot.user_id == user_id).scalar()
                or 0
            ) + 1
        s = ProyeccionSnapshot(
            user_id=user_id,
            fecha_proyeccion=fecha_proyeccion,
            periodo_inicio=periodo_inicio,
            periodo_fin=periodo_fin,
            version=version,
            etiqueta=etiqueta,
            notas=notas,
        )
        db.add(s)
        db.commit()
        db.refresh(s)
        return s
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def obtener_proyeccion_snapshot(snapshot_id: int) -> Optional[ProyeccionSnapshot]:
    db = next(get_db())
    try:
        return db.query(ProyeccionSnapshot).filter(ProyeccionSnapshot.id == snapshot_id).first()
    finally:
        db.close()


def listar_proyeccion_snapshots(user_id: int, limite: int = 100) -> List[ProyeccionSnapshot]:
    db = next(get_db())
    try:
        return (
            db.query(ProyeccionSnapshot)
            .filter(ProyeccionSnapshot.user_id == user_id)
            .order_by(desc(ProyeccionSnapshot.version), desc(ProyeccionSnapshot.created_at))
            .limit(limite)
            .all()
        )
    finally:
        db.close()


def actualizar_proyeccion_snapshot(snapshot_id: int, **campos) -> Optional[ProyeccionSnapshot]:
    db = next(get_db())
    try:
        s = db.query(ProyeccionSnapshot).filter(ProyeccionSnapshot.id == snapshot_id).first()
        if not s:
            return None
        for k, v in campos.items():
            if hasattr(s, k) and v is not None:
                setattr(s, k, v)
        db.commit()
        db.refresh(s)
        return s
    finally:
        db.close()


def eliminar_proyeccion_snapshot(snapshot_id: int) -> bool:
    db = next(get_db())
    try:
        s = db.query(ProyeccionSnapshot).filter(ProyeccionSnapshot.id == snapshot_id).first()
        if not s:
            return False
        db.delete(s)
        db.commit()
        return True
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


# --- Líneas de snapshot ---
def crear_proyeccion_linea(
    snapshot_id: int,
    fecha_impacto: date,
    categoria_id: int,
    monto: Number,
    *,
    descripcion: Optional[str] = None,
    tipo_confianza: Optional[str] = None,
    origen: Optional[str] = None,
    referencia_id: Optional[int] = None,
) -> ProyeccionLinea:
    db = next(get_db())
    try:
        ln = ProyeccionLinea(
            snapshot_id=snapshot_id,
            fecha_impacto=fecha_impacto,
            categoria_id=categoria_id,
            descripcion=descripcion,
            monto=_dec(monto),
            tipo_confianza=tipo_confianza,
            origen=origen,
            referencia_id=referencia_id,
        )
        db.add(ln)
        db.commit()
        db.refresh(ln)
        return ln
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def crear_proyeccion_lineas_bulk(registros: Sequence[Dict[str, Any]]) -> int:
    if not registros:
        return 0
    db = next(get_db())
    try:
        objs = []
        for r in registros:
            copy = dict(r)
            copy["monto"] = _dec(copy.get("monto"))
            objs.append(ProyeccionLinea(**copy))
        db.add_all(objs)
        db.commit()
        return len(objs)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def listar_proyeccion_lineas_snapshot(snapshot_id: int) -> List[ProyeccionLinea]:
    db = next(get_db())
    try:
        return (
            db.query(ProyeccionLinea)
            .filter(ProyeccionLinea.snapshot_id == snapshot_id)
            .order_by(ProyeccionLinea.fecha_impacto)
            .all()
        )
    finally:
        db.close()


def obtener_proyeccion_linea(linea_id: int) -> Optional[ProyeccionLinea]:
    db = next(get_db())
    try:
        return db.query(ProyeccionLinea).filter(ProyeccionLinea.id == linea_id).first()
    finally:
        db.close()


def actualizar_proyeccion_linea(linea_id: int, **campos) -> Optional[ProyeccionLinea]:
    db = next(get_db())
    try:
        ln = db.query(ProyeccionLinea).filter(ProyeccionLinea.id == linea_id).first()
        if not ln:
            return None
        for k, v in campos.items():
            if not hasattr(ln, k):
                continue
            if k == "monto":
                v = _dec(v)
            setattr(ln, k, v)
        db.commit()
        db.refresh(ln)
        return ln
    finally:
        db.close()


def eliminar_lineas_snapshot(snapshot_id: int) -> int:
    db = next(get_db())
    try:
        n = db.query(ProyeccionLinea).filter(ProyeccionLinea.snapshot_id == snapshot_id).delete()
        db.commit()
        return n
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


# --- Importaciones ---
def crear_proyeccion_importacion(user_id: int, **campos) -> ProyeccionImportacion:
    db = next(get_db())
    try:
        cols = set(ProyeccionImportacion.__mapper__.column_attrs.keys()) - {"id", "created_at"}
        kwargs = {k: v for k, v in campos.items() if k in cols}
        for k in ("monto_cif_usd", "tipo_cambio_estimado", "monto_cif_clp", "gastos_aduana_estimados", "iva_diferido_estimado"):
            if k in kwargs and kwargs[k] is not None:
                kwargs[k] = _dec(kwargs[k])
        imp = ProyeccionImportacion(user_id=user_id, **kwargs)
        db.add(imp)
        db.commit()
        db.refresh(imp)
        return imp
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def listar_proyeccion_importaciones(user_id: int) -> List[ProyeccionImportacion]:
    db = next(get_db())
    try:
        return (
            db.query(ProyeccionImportacion)
            .filter(ProyeccionImportacion.user_id == user_id)
            .order_by(desc(ProyeccionImportacion.created_at))
            .all()
        )
    finally:
        db.close()


def obtener_proyeccion_importacion(importacion_id: int) -> Optional[ProyeccionImportacion]:
    db = next(get_db())
    try:
        return db.query(ProyeccionImportacion).filter(ProyeccionImportacion.id == importacion_id).first()
    finally:
        db.close()


def actualizar_proyeccion_importacion(importacion_id: int, **campos) -> Optional[ProyeccionImportacion]:
    db = next(get_db())
    try:
        imp = db.query(ProyeccionImportacion).filter(ProyeccionImportacion.id == importacion_id).first()
        if not imp:
            return None
        for k, v in campos.items():
            if not hasattr(imp, k):
                continue
            if k in (
                "monto_cif_usd",
                "tipo_cambio_estimado",
                "monto_cif_clp",
                "gastos_aduana_estimados",
                "iva_diferido_estimado",
            ):
                v = _dec(v)
            setattr(imp, k, v)
        db.commit()
        db.refresh(imp)
        return imp
    finally:
        db.close()


def eliminar_proyeccion_importacion(importacion_id: int) -> bool:
    db = next(get_db())
    try:
        imp = db.query(ProyeccionImportacion).filter(ProyeccionImportacion.id == importacion_id).first()
        if not imp:
            return False
        db.delete(imp)
        db.commit()
        return True
    finally:
        db.close()


# --- Egresos paramétricos ---
def crear_proyeccion_egreso_parametrico(
    user_id: int,
    categoria_id: int,
    *,
    descripcion: Optional[str] = None,
    monto_estimado: Number = None,
    dia_pago: Optional[int] = None,
    mes_aplicacion: Optional[date] = None,
    es_recurrente: bool = True,
) -> ProyeccionEgresoParametrico:
    db = next(get_db())
    try:
        e = ProyeccionEgresoParametrico(
            user_id=user_id,
            categoria_id=categoria_id,
            descripcion=descripcion,
            monto_estimado=_dec(monto_estimado),
            dia_pago=dia_pago,
            mes_aplicacion=mes_aplicacion,
            es_recurrente=es_recurrente,
        )
        db.add(e)
        db.commit()
        db.refresh(e)
        return e
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def listar_proyeccion_egresos_parametricos(user_id: int) -> List[ProyeccionEgresoParametrico]:
    db = next(get_db())
    try:
        return db.query(ProyeccionEgresoParametrico).filter(ProyeccionEgresoParametrico.user_id == user_id).all()
    finally:
        db.close()


def obtener_proyeccion_egreso_parametrico(egreso_id: int) -> Optional[ProyeccionEgresoParametrico]:
    db = next(get_db())
    try:
        return db.query(ProyeccionEgresoParametrico).filter(ProyeccionEgresoParametrico.id == egreso_id).first()
    finally:
        db.close()


def actualizar_proyeccion_egreso_parametrico(egreso_id: int, **campos) -> Optional[ProyeccionEgresoParametrico]:
    db = next(get_db())
    try:
        e = db.query(ProyeccionEgresoParametrico).filter(ProyeccionEgresoParametrico.id == egreso_id).first()
        if not e:
            return None
        for k, v in campos.items():
            if not hasattr(e, k):
                continue
            if k == "monto_estimado":
                v = _dec(v)
            setattr(e, k, v)
        db.commit()
        db.refresh(e)
        return e
    finally:
        db.close()


def eliminar_proyeccion_egreso_parametrico(egreso_id: int, user_id: Optional[int] = None) -> bool:
    db = next(get_db())
    try:
        q = db.query(ProyeccionEgresoParametrico).filter(ProyeccionEgresoParametrico.id == egreso_id)
        if user_id is not None:
            q = q.filter(ProyeccionEgresoParametrico.user_id == user_id)
        e = q.first()
        if not e:
            return False
        db.delete(e)
        db.commit()
        return True
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


# --- Créditos bancarios ---
def crear_proyeccion_credito_bancario(
    user_id: int,
    *,
    descripcion: str,
    monto_credito: Number = None,
    saldo_pendiente: Number = None,
    fecha_proximo_pago: date,
    monto_cuota: Number,
    cuotas_pendientes: int,
    activo: bool = True,
) -> ProyeccionCreditoBancario:
    _ensure_creditos_bancarios_table()
    db = next(get_db())
    try:
        c = ProyeccionCreditoBancario(
            user_id=user_id,
            descripcion=(descripcion or "").strip()[:200] or "Crédito bancario",
            monto_credito=_dec(monto_credito),
            saldo_pendiente=_dec(saldo_pendiente),
            fecha_proximo_pago=fecha_proximo_pago,
            monto_cuota=_dec(monto_cuota),
            cuotas_pendientes=max(0, int(cuotas_pendientes or 0)),
            activo=bool(activo),
        )
        db.add(c)
        db.commit()
        db.refresh(c)
        return c
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def listar_proyeccion_creditos_bancarios(
    user_id: int, *, solo_activos: bool = True
) -> List[ProyeccionCreditoBancario]:
    _ensure_creditos_bancarios_table()
    db = next(get_db())
    try:
        q = db.query(ProyeccionCreditoBancario).filter(ProyeccionCreditoBancario.user_id == user_id)
        if solo_activos:
            q = q.filter(ProyeccionCreditoBancario.activo.is_(True))
        return q.order_by(
            ProyeccionCreditoBancario.fecha_proximo_pago.asc(),
            ProyeccionCreditoBancario.id.desc(),
        ).all()
    finally:
        db.close()


def actualizar_proyeccion_credito_bancario(
    credito_id: int, user_id: int, **campos
) -> Optional[ProyeccionCreditoBancario]:
    _ensure_creditos_bancarios_table()
    db = next(get_db())
    try:
        c = (
            db.query(ProyeccionCreditoBancario)
            .filter(ProyeccionCreditoBancario.id == credito_id, ProyeccionCreditoBancario.user_id == user_id)
            .first()
        )
        if not c:
            return None
        for k, v in campos.items():
            if not hasattr(c, k):
                continue
            if k in ("monto_credito", "saldo_pendiente", "monto_cuota"):
                v = _dec(v)
            if k == "cuotas_pendientes":
                v = max(0, int(v or 0))
            setattr(c, k, v)
        db.commit()
        db.refresh(c)
        return c
    finally:
        db.close()


def eliminar_proyeccion_credito_bancario(credito_id: int, user_id: int) -> bool:
    _ensure_creditos_bancarios_table()
    db = next(get_db())
    try:
        c = (
            db.query(ProyeccionCreditoBancario)
            .filter(ProyeccionCreditoBancario.id == credito_id, ProyeccionCreditoBancario.user_id == user_id)
            .first()
        )
        if not c:
            return False
        db.delete(c)
        db.commit()
        return True
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def registrar_pago_cuota_credito_bancario(credito_id: int, user_id: int) -> Optional[ProyeccionCreditoBancario]:
    """
    Marca una cuota como pagada:
    - reduce cuotas_pendientes en 1,
    - descuenta saldo_pendiente por monto_cuota (si existe),
    - mueve fecha_proximo_pago al mes siguiente,
    - desactiva el crédito cuando llega a 0 cuotas.
    """
    _ensure_creditos_bancarios_table()
    db = next(get_db())
    try:
        c = (
            db.query(ProyeccionCreditoBancario)
            .filter(ProyeccionCreditoBancario.id == credito_id, ProyeccionCreditoBancario.user_id == user_id)
            .first()
        )
        if not c:
            return None
        cuotas = int(c.cuotas_pendientes or 0)
        if cuotas <= 0:
            c.cuotas_pendientes = 0
            c.activo = False
            db.commit()
            db.refresh(c)
            return c

        c.cuotas_pendientes = max(0, cuotas - 1)
        if c.saldo_pendiente is not None and c.monto_cuota is not None:
            c.saldo_pendiente = max(Decimal("0"), _dec(c.saldo_pendiente) - _dec(c.monto_cuota))

        if c.cuotas_pendientes > 0 and c.fecha_proximo_pago is not None:
            c.fecha_proximo_pago = _sumar_un_mes_mismo_dia(c.fecha_proximo_pago)
            c.activo = True
        else:
            c.activo = False

        db.commit()
        db.refresh(c)
        return c
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


# --- Parámetros usuario ---
def obtener_proyeccion_parametros_usuario(user_id: int) -> Optional[ProyeccionParametrosUsuario]:
    _ensure_parametros_usuario_columns()
    db = next(get_db())
    try:
        return db.query(ProyeccionParametrosUsuario).filter(ProyeccionParametrosUsuario.user_id == user_id).first()
    finally:
        db.close()


def obtener_o_crear_proyeccion_parametros_usuario(user_id: int) -> ProyeccionParametrosUsuario:
    _ensure_parametros_usuario_columns()
    db = next(get_db())
    try:
        p = db.query(ProyeccionParametrosUsuario).filter(ProyeccionParametrosUsuario.user_id == user_id).first()
        if p:
            return p
        p = ProyeccionParametrosUsuario(user_id=user_id)
        db.add(p)
        db.commit()
        db.refresh(p)
        return p
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def actualizar_proyeccion_parametros_usuario(user_id: int, **campos) -> ProyeccionParametrosUsuario:
    _ensure_parametros_usuario_columns()
    db = next(get_db())
    try:
        p = db.query(ProyeccionParametrosUsuario).filter(ProyeccionParametrosUsuario.user_id == user_id).first()
        if not p:
            p = ProyeccionParametrosUsuario(user_id=user_id)
            db.add(p)
        for k, v in campos.items():
            if hasattr(p, k) and v is not None:
                if k in (
                    "tasa_ppm",
                    "tasa_retencion_honorarios",
                    "venta_global_esperada_mes",
                    "porcentaje_ventas_contado",
                    "compra_global_esperada_mes",
                    "porcentaje_compras_contado",
                    "porcentaje_morosidad_cxc",
                    "porcentaje_recuperabilidad_morosos",
                ):
                    v = _dec(v)
                setattr(p, k, v)
        db.commit()
        db.refresh(p)
        return p
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def eliminar_proyeccion_parametros_usuario(user_id: int) -> bool:
    db = next(get_db())
    try:
        p = db.query(ProyeccionParametrosUsuario).filter(ProyeccionParametrosUsuario.user_id == user_id).first()
        if not p:
            return False
        db.delete(p)
        db.commit()
        return True
    finally:
        db.close()


# --- Mapeo conceptos proyección -> categorías ejecutadas Tab 1 ---
def listar_categorias_tab1_usuario(user_id: int) -> List[str]:
    """
    Categorías de Tab 1 disponibles para mapeo.

    Incluye:
    - categorías realmente usadas (distinct transacciones.clasificacion)
    - categorías definidas en clasificadores activos (catálogo), aunque aún no tengan movimiento
    """
    db = next(get_db())
    try:
        rows_tx = (
            db.query(Transaccion.clasificacion)
            .filter(Transaccion.usuario_id == user_id, Transaccion.clasificacion.isnot(None))
            .distinct()
            .all()
        )
        rows_cls = (
            db.query(Clasificador.nombre)
            .filter(Clasificador.usuario_id == user_id, Clasificador.activo == True)
            .distinct()
            .all()
        )
        out = sorted(
            {
                str(r[0]).strip()
                for r in (list(rows_tx) + list(rows_cls))
                if r and r[0] is not None and str(r[0]).strip()
            }
        )
        return out
    finally:
        db.close()


def listar_mapeo_conceptos_tab1(user_id: int) -> List[ProyeccionMapeoCategoria]:
    _ensure_mapeo_categorias_table()
    db = next(get_db())
    try:
        try:
            return (
                db.query(ProyeccionMapeoCategoria)
                .filter(ProyeccionMapeoCategoria.user_id == user_id)
                .order_by(ProyeccionMapeoCategoria.concepto_proyeccion.asc())
                .all()
            )
        except OperationalError:
            # Último resguardo si el motor no alcanzó a crear tabla antes del query.
            db.rollback()
            _ensure_mapeo_categorias_table()
            return (
                db.query(ProyeccionMapeoCategoria)
                .filter(ProyeccionMapeoCategoria.user_id == user_id)
                .order_by(ProyeccionMapeoCategoria.concepto_proyeccion.asc())
                .all()
            )
    finally:
        db.close()


def obtener_mapeo_conceptos_tab1_dict(user_id: int) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for m in listar_mapeo_conceptos_tab1(user_id):
        out[m.concepto_proyeccion] = m.categoria_tab1
    return out


def upsert_mapeo_concepto_tab1(user_id: int, concepto_proyeccion: str, categoria_tab1: str) -> ProyeccionMapeoCategoria:
    _ensure_mapeo_categorias_table()
    db = next(get_db())
    try:
        m = (
            db.query(ProyeccionMapeoCategoria)
            .filter(
                ProyeccionMapeoCategoria.user_id == user_id,
                ProyeccionMapeoCategoria.concepto_proyeccion == concepto_proyeccion,
            )
            .first()
        )
        if m:
            m.categoria_tab1 = categoria_tab1
        else:
            m = ProyeccionMapeoCategoria(
                user_id=user_id,
                concepto_proyeccion=concepto_proyeccion,
                categoria_tab1=categoria_tab1,
            )
            db.add(m)
        db.commit()
        db.refresh(m)
        return m
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def eliminar_mapeo_concepto_tab1(user_id: int, concepto_proyeccion: str) -> bool:
    _ensure_mapeo_categorias_table()
    db = next(get_db())
    try:
        m = (
            db.query(ProyeccionMapeoCategoria)
            .filter(
                ProyeccionMapeoCategoria.user_id == user_id,
                ProyeccionMapeoCategoria.concepto_proyeccion == concepto_proyeccion,
            )
            .first()
        )
        if not m:
            return False
        db.delete(m)
        db.commit()
        return True
    finally:
        db.close()
