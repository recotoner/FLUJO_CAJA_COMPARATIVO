"""
UI Streamlit: parámetros fiscales por usuario para proyección de caja (v3.0).
Persistencia en proyeccion_parametros_usuario.

Usar desde el Tab de proyección: ``render_modulo_parametros_usuario(usuario)``,
con ``usuario`` = retorno de ``auth.login.get_current_user()`` (modelo Usuario).
"""
from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Optional

import streamlit as st

from database import crud_proyeccion as crud_p

if TYPE_CHECKING:
    from database.models import Usuario


def _fraccion_desde_porcentaje(pct: float) -> Decimal:
    return Decimal(str(round(pct / 100.0, 8)))


def render_modulo_parametros_usuario(usuario: Optional["Usuario"]) -> None:
    """
    Formulario de tasas y días de pago. Si ``usuario`` es None, no hace nada útil (sesión cerrada).
    """
    if usuario is None:
        st.warning("Debe iniciar sesión para configurar parámetros.")
        return

    user_id = usuario.id
    p = crud_p.obtener_o_crear_proyeccion_parametros_usuario(user_id)

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
        "Estos valores alimentan el motor de proyección (IVA, PPM, honorarios). "
        "La tasa PPM es obligatoria para proyectar Pagos Provisionales Mensuales."
    )

    ppm_pct = float(p.tasa_ppm) * 100 if p.tasa_ppm is not None else 0.0
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

    st.markdown('<div class="param-box">', unsafe_allow_html=True)
    with st.form("form_param_proyeccion"):
        c1, c2 = st.columns(2)
        with c1:
            tasa_ppm_input = st.number_input(
                "Tasa PPM (%)",
                min_value=0.0,
                max_value=100.0,
                value=ppm_pct,
                step=0.01,
                format="%.4f",
                help="Porcentaje mensual del Pago Provisional Mensual. Obligatorio para incluir PPM en la proyección.",
            )
            st.caption("Porcentaje que pagas mensualmente al SII sobre tus ventas.")
        with c2:
            tasa_ret_input = st.number_input(
                "Retención honorarios (%)",
                min_value=0.0,
                max_value=30.0,
                value=ret_pct,
                step=0.01,
                format="%.4f",
                help="Retención por honorarios aplicable cuando corresponda (típico 10,75 %).",
            )
            st.caption("Retención aplicada a pagos por boletas de honorarios.")

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
                value=int(p.dia_pago_impuestos or 12),
                help="Día del mes en que se modela el pago (p. ej. 12).",
            )
            st.caption("Día en que normalmente pagas impuestos del mes.")
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

    if not enviar:
        if p.tasa_ppm is None or float(p.tasa_ppm) <= 0:
            st.warning(
                "⚠️ Tasa PPM no configurada o en cero: la proyección no debería avanzar en modo completo hasta definirla."
            )
        return

    if tasa_ppm_input <= 0:
        st.error("Indique una tasa PPM mayor que 0 (obligatoria para el cálculo de PPM).")
        return

    crud_p.actualizar_proyeccion_parametros_usuario(
        user_id,
        tasa_ppm=_fraccion_desde_porcentaje(tasa_ppm_input),
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
