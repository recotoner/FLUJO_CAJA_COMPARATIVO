"""
Modelos de base de datos.
Estos son como "plantillas" para guardar datos.
No necesitas entender SQL - solo saber que existen estas "cajas" para guardar información.
"""
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Date, Text, DECIMAL, ForeignKey, Enum, LargeBinary
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from .connection import Base
import enum

# ============================================
# TABLA DE USUARIOS
# ============================================
class Usuario(Base):
    """Información de cada cliente/usuario del sistema"""
    __tablename__ = "usuarios"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    nombre_empresa = Column(String(255), nullable=False)
    activo = Column(Boolean, default=True)
    fecha_registro = Column(DateTime, server_default=func.now())
    plan = Column(String(50), default="basico")  # 'basico', 'premium', etc.
    
    # Relaciones (esto conecta con otras tablas)
    clasificadores = relationship("Clasificador", back_populates="usuario")
    archivos = relationship("ArchivoCargado", back_populates="usuario")
    transacciones = relationship("Transaccion", back_populates="usuario")
    mapeos = relationship("MapeoColumnas", back_populates="usuario")
    alertas = relationship("Alerta", back_populates="usuario")

# ============================================
# TABLA DE CLASIFICADORES
# ============================================
class TipoTransaccion(enum.Enum):
    ABONO = "abono"
    CARGO = "cargo"

class Clasificador(Base):
    """Reglas de clasificación que cada usuario configura"""
    __tablename__ = "clasificadores"
    
    id = Column(Integer, primary_key=True, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    nombre = Column(String(255), nullable=False)
    tipo = Column(Enum(TipoTransaccion), nullable=False)
    palabras_clave = Column(Text)  # JSON array como texto
    tipo_coincidencia = Column(String(50), default="contiene_cualquiera")
    excluir = Column(Text, nullable=True)  # JSON array como texto (opcional)
    activo = Column(Boolean, default=True)
    orden = Column(Integer, default=0)  # Orden de evaluación
    
    # Relación
    usuario = relationship("Usuario", back_populates="clasificadores")

# ============================================
# TABLA DE MAPEO DE COLUMNAS
# ============================================
class MapeoColumnas(Base):
    """Configuración de cómo mapear columnas del Excel según el banco"""
    __tablename__ = "mapeo_columnas"
    
    id = Column(Integer, primary_key=True, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    banco = Column(String(100), nullable=False)
    columna_fecha = Column(String(100))
    columna_descripcion = Column(String(100))
    columna_abono = Column(String(100))
    columna_cargo = Column(String(100))
    columna_saldo = Column(String(100))
    activo = Column(Boolean, default=True)
    
    # Relación
    usuario = relationship("Usuario", back_populates="mapeos")

# ============================================
# TABLA DE ARCHIVOS CARGADOS
# ============================================
class ArchivoCargado(Base):
    """Registro de cada archivo que el usuario sube"""
    __tablename__ = "archivos_cargados"
    
    id = Column(Integer, primary_key=True, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    nombre_archivo = Column(String(255), nullable=False)
    fecha_carga = Column(DateTime, server_default=func.now())
    banco = Column(String(100))
    total_registros = Column(Integer, default=0)
    estado = Column(String(50), default="procesado")  # 'procesado', 'error', 'pendiente'
    
    # Relaciones
    usuario = relationship("Usuario", back_populates="archivos")
    transacciones = relationship("Transaccion", back_populates="archivo")

# ============================================
# TABLA DE TRANSACCIONES
# ============================================
class Transaccion(Base):
    """Cada movimiento bancario guardado"""
    __tablename__ = "transacciones"
    
    id = Column(Integer, primary_key=True, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    archivo_id = Column(Integer, ForeignKey("archivos_cargados.id"), nullable=True)
    fecha = Column(DateTime, nullable=False, index=True)
    descripcion = Column(Text)
    abono = Column(DECIMAL(15, 2), default=0)
    cargo = Column(DECIMAL(15, 2), default=0)
    saldo = Column(DECIMAL(15, 2), nullable=True)
    clasificacion = Column(String(255), index=True)
    comentario = Column(Text)  # Descripción normalizada
    fecha_registro = Column(DateTime, server_default=func.now())
    
    # Relaciones
    usuario = relationship("Usuario", back_populates="transacciones")
    archivo = relationship("ArchivoCargado", back_populates="transacciones")

# ============================================
# TABLA DE ALERTAS
# ============================================
class Alerta(Base):
    """Alertas y notificaciones para el usuario"""
    __tablename__ = "alertas"
    
    id = Column(Integer, primary_key=True, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    tipo = Column(String(50), nullable=False)  # 'sin_clasificar', 'error_mapeo', etc.
    mensaje = Column(Text, nullable=False)
    fecha = Column(DateTime, server_default=func.now())
    leida = Column(Boolean, default=False)
    
    # Relación
    usuario = relationship("Usuario", back_populates="alertas")

# ============================================
# TABLA DE ARCHIVOS DE PROYECCIÓN
# ============================================
class ArchivoProyeccion(Base):
    """Archivos de proyección guardados por el usuario"""
    __tablename__ = "archivos_proyeccion"
    
    id = Column(Integer, primary_key=True, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    nombre_archivo = Column(String(255), nullable=False)
    fecha_carga = Column(DateTime, server_default=func.now())
    contenido = Column(LargeBinary, nullable=False)  # Contenido del archivo Excel como bytes
    descripcion = Column(Text, nullable=True)  # Descripción opcional del usuario
    
    # Relación
    usuario = relationship("Usuario")


# ============================================
# PROYECCIÓN DE CAJA (Tab 2) — v3.0
# ============================================


class CategoriaFinanciera(Base):
    """Maestro de categorías para líneas de proyección (convive con Tab 1 por convención de nombres)."""

    __tablename__ = "categorias_financieras"

    id = Column(Integer, primary_key=True, index=True)
    codigo = Column(String(50), unique=True, nullable=False, index=True)
    nombre = Column(String(100), nullable=False)
    tipo = Column(String(20), nullable=False)  # ingreso / egreso / ambos
    aplica_tab1 = Column(Boolean, default=True)
    aplica_tab2 = Column(Boolean, default=True)
    orden_display = Column(Integer, nullable=True)
    activo = Column(Boolean, default=True)

    lineas = relationship("ProyeccionLinea", back_populates="categoria")
    egresos_parametricos = relationship("ProyeccionEgresoParametrico", back_populates="categoria")


class ProyeccionCarga(Base):
    """Historial de cada upload Excel (CxC, CxP o remuneraciones)."""

    __tablename__ = "proyeccion_cargas"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False, index=True)
    tipo = Column(String(20), nullable=False)  # cxc / cxp / remuneraciones
    nombre_archivo = Column(String(200), nullable=True)
    fecha_carga = Column(DateTime, server_default=func.now())
    origen = Column(String(50), default="upload_excel")
    total_registros = Column(Integer, nullable=True)
    notas = Column(Text, nullable=True)

    usuario = relationship("Usuario", foreign_keys=[user_id])
    facturas = relationship("ProyeccionFactura", back_populates="carga")
    remuneraciones = relationship("ProyeccionRemuneracion", back_populates="carga")


class ProyeccionFactura(Base):
    """CxC / CxP normalizadas desde Excel (v3 reemplaza facturas_erp sueltas con carga_id)."""

    __tablename__ = "proyeccion_facturas"

    id = Column(Integer, primary_key=True, index=True)
    carga_id = Column(Integer, ForeignKey("proyeccion_cargas.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False, index=True)
    tipo = Column(String(20), nullable=False)  # por_cobrar / por_pagar
    rut_contraparte = Column(String(20), nullable=True)
    razon_social = Column(String(200), nullable=True)
    folio = Column(String(50), nullable=True)
    monto_neto = Column(DECIMAL(15, 0), nullable=True)
    monto_iva = Column(DECIMAL(15, 0), nullable=True)
    monto_total = Column(DECIMAL(15, 0), nullable=True)
    saldo = Column(DECIMAL(15, 0), nullable=True)
    fecha_emision = Column(Date, nullable=True)
    fecha_vencimiento = Column(Date, nullable=False, index=True)
    condicion_venta = Column(String(50), nullable=True)
    estado = Column(String(50), nullable=True)
    tipo_confianza = Column(String(20), default="real")
    created_at = Column(DateTime, server_default=func.now())

    carga = relationship("ProyeccionCarga", back_populates="facturas")
    usuario = relationship("Usuario", foreign_keys=[user_id])


class ProyeccionRemuneracion(Base):
    """Libro de sueldos persistido."""

    __tablename__ = "proyeccion_remuneraciones"

    id = Column(Integer, primary_key=True, index=True)
    carga_id = Column(Integer, ForeignKey("proyeccion_cargas.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False, index=True)
    empleado = Column(String(200), nullable=True)
    rut_empleado = Column(String(20), nullable=True)
    mes_aplicacion = Column(Date, nullable=False, index=True)
    monto_bruto = Column(DECIMAL(15, 0), nullable=True)
    monto_liquido = Column(DECIMAL(15, 0), nullable=True)
    monto_imponible = Column(DECIMAL(15, 0), nullable=True)
    monto_afp = Column(DECIMAL(15, 0), nullable=True)
    monto_salud = Column(DECIMAL(15, 0), nullable=True)
    monto_salud_adicional = Column(DECIMAL(15, 0), nullable=True)
    monto_cesantia = Column(DECIMAL(15, 0), nullable=True)
    monto_impuesto_unico = Column(DECIMAL(15, 0), nullable=True)
    dia_pago = Column(Integer, nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    carga = relationship("ProyeccionCarga", back_populates="remuneraciones")
    usuario = relationship("Usuario", foreign_keys=[user_id])


class ProyeccionSnapshot(Base):
    """Cabecera de una proyección versionada."""

    __tablename__ = "proyeccion_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False, index=True)
    fecha_proyeccion = Column(Date, nullable=False)
    periodo_inicio = Column(Date, nullable=False)
    periodo_fin = Column(Date, nullable=False)
    version = Column(Integer, nullable=False)
    etiqueta = Column(String(100), nullable=True)
    notas = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    usuario = relationship("Usuario", foreign_keys=[user_id])
    lineas = relationship(
        "ProyeccionLinea",
        back_populates="snapshot",
        cascade="all, delete-orphan",
    )


class ProyeccionLinea(Base):
    """Detalle de una proyección con tipo_confianza."""

    __tablename__ = "proyeccion_lineas"

    id = Column(Integer, primary_key=True, index=True)
    snapshot_id = Column(Integer, ForeignKey("proyeccion_snapshots.id"), nullable=False, index=True)
    fecha_impacto = Column(Date, nullable=False, index=True)
    categoria_id = Column(Integer, ForeignKey("categorias_financieras.id"), nullable=False, index=True)
    descripcion = Column(String(200), nullable=True)
    monto = Column(DECIMAL(15, 0), nullable=False)
    tipo_confianza = Column(String(20), nullable=True)
    origen = Column(String(50), nullable=True)
    referencia_id = Column(Integer, nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    snapshot = relationship("ProyeccionSnapshot", back_populates="lineas")
    categoria = relationship("CategoriaFinanciera", back_populates="lineas")


class ProyeccionImportacion(Base):
    """Importaciones manuales (formulario)."""

    __tablename__ = "proyeccion_importaciones"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False, index=True)
    proveedor_extranjero = Column(String(200), nullable=True)
    invoice_numero = Column(String(100), nullable=True)
    monto_cif_usd = Column(DECIMAL(15, 2), nullable=True)
    tipo_cambio_estimado = Column(DECIMAL(10, 2), nullable=True)
    monto_cif_clp = Column(DECIMAL(15, 0), nullable=True)
    eta_estimada = Column(Date, nullable=True)
    eta_real = Column(Date, nullable=True)
    gastos_aduana_estimados = Column(DECIMAL(15, 0), nullable=True)
    iva_diferido_estimado = Column(DECIMAL(15, 0), nullable=True)
    fecha_pago_proveedor = Column(Date, nullable=True)
    fecha_impacto_iva = Column(Date, nullable=True)
    estado = Column(String(50), nullable=True)
    notas = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    usuario = relationship("Usuario", foreign_keys=[user_id])


class ProyeccionEgresoParametrico(Base):
    """Egresos periódicos paramétricos."""

    __tablename__ = "proyeccion_egresos_parametricos"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False, index=True)
    categoria_id = Column(Integer, ForeignKey("categorias_financieras.id"), nullable=False, index=True)
    descripcion = Column(String(200), nullable=True)
    monto_estimado = Column(DECIMAL(15, 0), nullable=True)
    dia_pago = Column(Integer, nullable=True)
    mes_aplicacion = Column(Date, nullable=True)
    es_recurrente = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())

    usuario = relationship("Usuario", foreign_keys=[user_id])
    categoria = relationship("CategoriaFinanciera", back_populates="egresos_parametricos")


class ProyeccionCreditoBancario(Base):
    """Pasivos financieros configurables por usuario."""

    __tablename__ = "proyeccion_creditos_bancarios"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False, index=True)
    descripcion = Column(String(200), nullable=False)
    monto_credito = Column(DECIMAL(15, 0), nullable=True)
    saldo_pendiente = Column(DECIMAL(15, 0), nullable=True)
    fecha_proximo_pago = Column(Date, nullable=False)
    monto_cuota = Column(DECIMAL(15, 0), nullable=False)
    cuotas_pendientes = Column(Integer, nullable=False, default=1)
    activo = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    usuario = relationship("Usuario", foreign_keys=[user_id])


class ProyeccionParametrosUsuario(Base):
    """Parámetros fiscales y días de pago por usuario (una fila por usuario)."""

    __tablename__ = "proyeccion_parametros_usuario"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("usuarios.id"), unique=True, nullable=False, index=True)
    tasa_ppm = Column(DECIMAL(5, 4), nullable=True)
    tasa_retencion_honorarios = Column(DECIMAL(5, 4), default=0.1075)
    venta_global_esperada_mes = Column(DECIMAL(15, 0), nullable=True)
    porcentaje_ventas_contado = Column(DECIMAL(5, 4), nullable=True)
    compra_global_esperada_mes = Column(DECIMAL(15, 0), nullable=True)
    porcentaje_compras_contado = Column(DECIMAL(5, 4), nullable=True)
    porcentaje_morosidad_cxc = Column(DECIMAL(5, 4), nullable=True)
    porcentaje_recuperabilidad_morosos = Column(DECIMAL(5, 4), nullable=True)
    dia_pago_impuestos = Column(Integer, default=12)
    dia_pago_remuneraciones = Column(Integer, default=30)
    dia_pago_imposiciones = Column(Integer, default=10)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    usuario = relationship("Usuario", foreign_keys=[user_id])


class ProyeccionMapeoCategoria(Base):
    """Mapeo por usuario entre concepto de proyección y categoría ejecutada de Tab 1."""

    __tablename__ = "proyeccion_mapeo_categorias"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False, index=True)
    concepto_proyeccion = Column(String(120), nullable=False, index=True)
    categoria_tab1 = Column(String(255), nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    usuario = relationship("Usuario", foreign_keys=[user_id])

