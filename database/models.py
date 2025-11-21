"""
Modelos de base de datos.
Estos son como "plantillas" para guardar datos.
No necesitas entender SQL - solo saber que existen estas "cajas" para guardar información.
"""
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, DECIMAL, ForeignKey, Enum
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


