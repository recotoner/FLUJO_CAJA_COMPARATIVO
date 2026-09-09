"""
UI Streamlit: parámetros fiscales por usuario para proyección de caja (v3.0).
Persistencia en proyeccion_parametros_usuario.

Usar desde el Tab de proyección: ``render_modulo_parametros_usuario(usuario)``,
con ``usuario`` = retorno de ``auth.login.get_current_user()`` (modelo Usuario).
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

import pandas as pd
import streamlit as st

from database import crud_proyeccion as crud_p

if TYPE_CHECKING:
    from database.models import Usuario


def _fraccion_desde_porcentaje(pct: float) -> Decimal:
    return Decimal(str(round(pct / 100.0, 8)))


def _dec(x) -> Decimal:
    if x is None:
        return Decimal(0)
    if isinstance(x, Decimal):
        return x
    return Decimal(str(x))


def render_modulo_parametros_usuario(usuario: Optional["Usuario"]) -> None:
    """
    Formulario de tasas y días de pago. Si ``usuario`` es None, no hace nada útil (sesión cerrada).
    """
    if usuario is None:
        st.warning("Debe iniciar sesión para configurar parámetros.")
        return

    user_id = usuario.id
    p = crud_p.obtener_o_crear_proyeccion_parametros_usuario(user_id)
    crud_p.seed_categorias_financieras()

    st.markdown(
        """
        <style>
        .param-box {
            border: 1px solid #CFE6D8;
            background: #F7FCF9;
            border-radius: 12px;
            padding: 10px 12px;
            margin-bottom: 10px;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.subheader("Parámetros fiscales y fechas de pago")
    st.caption(
        "Estos valores alimentan el motor de proyección (honorarios, fechas SII y F29 código 91). "
        "El total a pagar del F29 (código 91) se ingresa manualmente por período tributario; "
        "el egreso de caja se proyecta el mes siguiente en el día de pago de impuestos."
    )

    ret_pct = float(p.tasa_retencion_honorarios) * 100 if p.tasa_retencion_honorarios is not None else 10.75
    contado_pct = float(p.porcentaje_ventas_contado) * 100 if p.porcentaje_ventas_contado is not None else 0.0
    mora_pct = float(p.porcentaje_morosidad_cxc) * 100 if p.porcentaje_morosidad_cxc is not None else 0.0
    recup_mora_pct = (
        float(p.porcentaje_recuperabilidad_morosos) * 100
        if getattr(p, "porcentaje_recuperabilidad_morosos", None) is not None
        else 0.0
    )
    venta_mes = float(p.venta_global_esperada_mes) if p.venta_global_esperada_mes is not None else 0.0
    compra_mes = (
        float(p.compra_global_esperada_mes)
        if getattr(p, "compra_global_esperada_mes", None) is not None
        else 0.0
    )
    compra_contado_pct = (
        float(p.porcentaje_compras_contado) * 100
        if getattr(p, "porcentaje_compras_contado", None) is not None
        else 0.0
    )
    dia_imp_actual = int(p.dia_pago_impuestos or 12)

    st.markdown('<div class="param-box">', unsafe_allow_html=True)
    with st.form("form_param_proyeccion"):
        tasa_ret_input = st.number_input(
            "Retención honorarios (%)",
            min_value=0.0,
            max_value=30.0,
            value=ret_pct,
            step=0.01,
            format="%.4f",
            help="Referencia histórica; las retenciones 2da categoría ya no se proyectan como egreso separado "
            "(van dentro del F29 código 91).",
        )
        st.caption("Se conserva el parámetro; el pago tributario consolidado es el F29 código 91.")

        st.markdown("**Supuestos opcionales comerciales (cliente)**")
        c6, c7, c8 = st.columns(3)
        with c6:
            venta_global_mes_input = st.number_input(
                "Venta total esperada del mes",
                min_value=0.0,
                value=venta_mes,
                step=1000.0,
                format="%.0f",
                help="Monto total esperado del mes (contado + crédito). Si queda en 0, no se aplica este supuesto.",
            )
            st.caption("Estimación total de ventas del mes (contado + crédito).")
        with c7:
            porcentaje_contado_input = st.number_input(
                "% ventas contado",
                min_value=0.0,
                max_value=100.0,
                value=contado_pct,
                step=0.1,
                format="%.2f",
                help="Porción de la venta global que se cobra en el mismo mes (contado).",
            )
            st.caption("Parte de la venta mensual que se cobra inmediatamente.")
        with c8:
            porcentaje_morosidad_input = st.number_input(
                "% morosidad Facturas por Cobrar",
                min_value=0.0,
                max_value=100.0,
                value=mora_pct,
                step=0.1,
                format="%.2f",
                help="Porcentaje estimado de facturas por cobrar que vencen pero no se cobran efectivamente.",
            )
            st.caption("Estimación de facturas que podrían no cobrarse a tiempo.")
        c9, c10, c11 = st.columns(3)
        with c9:
            compra_global_mes_input = st.number_input(
                "Compras esperadas del mes",
                min_value=0.0,
                value=compra_mes,
                step=1000.0,
                format="%.0f",
                help="Monto total esperado de compras del mes (contado + crédito).",
            )
            st.caption("Estimación total de compras del mes.")
        with c10:
            porcentaje_compra_contado_input = st.number_input(
                "% compras contado",
                min_value=0.0,
                max_value=100.0,
                value=compra_contado_pct,
                step=0.1,
                format="%.2f",
                help="Porción de las compras esperadas que se paga al contado dentro del mes.",
            )
            st.caption("Parte de las compras mensuales pagadas inmediatamente.")
        with c11:
            porcentaje_recup_morosos_input = st.number_input(
                "% recuperabilidad morosos",
                min_value=0.0,
                max_value=100.0,
                value=recup_mora_pct,
                step=0.1,
                format="%.2f",
                help="Porción esperada de recuperación sobre CxC vencidos a la fecha de análisis.",
            )
            st.caption("Cobro estimado de clientes morosos (base: CxC vencidos).")

        c3, c4, c5 = st.columns(3)
        with c3:
            dia_imp = st.number_input(
                "Día pago impuestos (IVA / tareas SII)",
                min_value=1,
                max_value=31,
                value=dia_imp_actual,
                help="Día del mes siguiente al período tributario en que se proyecta el F29 código 91 (p. ej. 12).",
            )
            st.caption("También fija el día de caja del F29 (mes siguiente al período).")
        with c4:
            dia_rem = st.number_input(
                "Día pago remuneraciones",
                min_value=1,
                max_value=31,
                value=int(p.dia_pago_remuneraciones or 30),
            )
            st.caption("Día habitual de pago de sueldos.")
        with c5:
            dia_impos = st.number_input(
                "Día pago imposiciones (AFP / salud)",
                min_value=1,
                max_value=31,
                value=int(p.dia_pago_imposiciones or 10),
                help="Día del mes para proyectar el egreso de cotizaciones; configurable aquí y guardado por usuario. "
                "Tras cambiarlo, regenerá la proyección.",
            )
            st.caption("Usado junto con el mes del libro de remuneraciones para fechar la fila «Imposiciones».")

        enviar = st.form_submit_button("Guardar parámetros", type="primary")
    st.markdown("</div>", unsafe_allow_html=True)

    if enviar:
        # Conserva tasa_ppm existente (columna en BD); ya no se edita en la UI.
        crud_p.actualizar_proyeccion_parametros_usuario(
            user_id,
            tasa_ppm=p.tasa_ppm,
            tasa_retencion_honorarios=_fraccion_desde_porcentaje(tasa_ret_input),
            venta_global_esperada_mes=Decimal(str(venta_global_mes_input)) if venta_global_mes_input > 0 else None,
            porcentaje_ventas_contado=_fraccion_desde_porcentaje(porcentaje_contado_input)
            if porcentaje_contado_input > 0
            else None,
            compra_global_esperada_mes=Decimal(str(compra_global_mes_input)) if compra_global_mes_input > 0 else None,
            porcentaje_compras_contado=_fraccion_desde_porcentaje(porcentaje_compra_contado_input)
            if porcentaje_compra_contado_input > 0
            else None,
            porcentaje_morosidad_cxc=_fraccion_desde_porcentaje(porcentaje_morosidad_input)
            if porcentaje_morosidad_input > 0
            else None,
            porcentaje_recuperabilidad_morosos=_fraccion_desde_porcentaje(porcentaje_recup_morosos_input)
            if porcentaje_recup_morosos_input > 0
            else None,
            dia_pago_impuestos=int(dia_imp),
            dia_pago_remuneraciones=int(dia_rem),
            dia_pago_imposiciones=int(dia_impos),
        )
        st.success("Parámetros guardados correctamente.")
        st.rerun()

    st.markdown("**F29 total a pagar — código 91**")
    st.caption(
        f"Ingresa el monto del código 91 por período tributario. "
        f"El egreso de caja se proyecta el **mes siguiente** el día **{dia_imp_actual}** "
        f"(parámetro «Día pago impuestos»). Ejemplo: período 2026-08 → pago ~2026-09-{dia_imp_actual:02d}."
    )

    cat_f29 = crud_p.obtener_categoria_por_codigo("F29_91")
    if not cat_f29:
        st.error("No se encontró la categoría F29_91. Use «Sincronizar categorías maestras» o regenere la proyección.")
        return

    with st.form("form_f29_codigo_91"):
        f1, f2 = st.columns(2)
        with f1:
            periodo_f29 = st.date_input(
                "Período tributario",
                value=date.today().replace(day=1),
                help="Mes del período F29 (se usa año-mes; el día se normaliza al 1).",
                key="dt_f29_periodo",
            )
        with f2:
            monto_f29 = st.number_input(
                "Monto F29 código 91",
                min_value=0.0,
                step=1000.0,
                value=0.0,
                format="%.0f",
                key="num_f29_monto",
            )
        guardar_f29 = st.form_submit_button("Guardar F29 código 91", type="primary")

    if guardar_f29:
        if monto_f29 <= 0:
            st.warning("Ingrese un monto F29 código 91 mayor que 0.")
        else:
            mes_periodo = date(periodo_f29.year, periodo_f29.month, 1)
            if crud_p.existe_egreso_f29_periodo(user_id, mes_periodo):
                st.error(
                    f"Ya existe un F29 código 91 para el período {mes_periodo.year}-{mes_periodo.month:02d}. "
                    "Elimínelo antes de ingresar otro monto para el mismo período."
                )
            else:
                crud_p.crear_proyeccion_egreso_parametrico(
                    user_id=user_id,
                    categoria_id=cat_f29.id,
                    descripcion=f"F29 total a pagar — código 91 ({mes_periodo.year}-{mes_periodo.month:02d})",
                    monto_estimado=monto_f29,
                    dia_pago=dia_imp_actual,
                    mes_aplicacion=mes_periodo,
                    es_recurrente=False,
                )
                st.success(
                    f"F29 guardado: período {mes_periodo.year}-{mes_periodo.month:02d} · "
                    f"${monto_f29:,.0f} · pago proyectado mes siguiente día {dia_imp_actual}."
                )
                st.rerun()

    rows_f29 = crud_p.listar_proyeccion_egresos_por_codigo(user_id, "F29_91")
    if rows_f29:
        tabla = []
        for e in rows_f29:
            ma = e.mes_aplicacion
            per = f"{ma.year}-{ma.month:02d}" if ma else "—"
            if ma:
                if ma.month == 12:
                    py, pm = ma.year + 1, 1
                else:
                    py, pm = ma.year, ma.month + 1
                pago = f"{py}-{pm:02d}-{int(e.dia_pago or dia_imp_actual):02d}"
            else:
                pago = "—"
            tabla.append(
                {
                    "id": e.id,
                    "período_tributario": per,
                    "monto_código_91": float(_dec(e.monto_estimado)),
                    "pago_proyectado": pago,
                    "descripción": e.descripcion or "",
                }
            )
        st.dataframe(pd.DataFrame(tabla), use_container_width=True, hide_index=True)

        by_id = {int(r["id"]): r for r in tabla}
        oid_pick = sorted(by_id.keys(), reverse=True)

        def _fmt_f29(oid: int) -> str:
            if oid == 0:
                return "— Ninguno —"
            r = by_id[oid]
            return (
                f"Id {oid} · período {r['período_tributario']} · "
                f"${r['monto_código_91']:,.0f} · pago {r['pago_proyectado']}"
            )

        sel_del = st.selectbox(
            "Eliminar registro F29 código 91",
            options=[0] + oid_pick,
            format_func=_fmt_f29,
            key=f"sel_elim_f29_{user_id}",
        )
        if st.button(
            "Eliminar F29 seleccionado",
            key=f"btn_elim_f29_{user_id}",
            disabled=sel_del == 0,
        ):
            if crud_p.eliminar_proyeccion_egreso_parametrico(sel_del, user_id):
                st.success(f"F29 id {sel_del} eliminado.")
                st.rerun()
            else:
                st.error("No se eliminó (registro inexistente o no es suyo).")
    else:
        st.info("Aún no hay montos F29 código 91. Agrega al menos el período del horizonte de proyección.")
