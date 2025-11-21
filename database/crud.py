"""
Funciones simples para usar la base de datos.
No necesitas saber SQL - solo llamar estas funciones.
"""
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from database.models import (
    Usuario, Clasificador, Transaccion, ArchivoCargado, 
    MapeoColumnas, Alerta, TipoTransaccion
)
from database.connection import get_db
import bcrypt
import json
from datetime import datetime
from typing import Optional, List

# ============================================
# FUNCIONES DE USUARIOS
# ============================================

def crear_usuario(email: str, password: str, nombre_empresa: str, plan: str = "basico") -> Usuario:
    """
    Crea un nuevo usuario.
    
    Ejemplo:
        usuario = crear_usuario("cliente@ejemplo.com", "password123", "Empresa XYZ")
    """
    db = next(get_db())
    try:
        # Verificar si el usuario ya existe
        if db.query(Usuario).filter(Usuario.email == email).first():
            raise ValueError(f"El email {email} ya está registrado")
        
        # Hashear password
        password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        
        # Crear usuario
        usuario = Usuario(
            email=email,
            password_hash=password_hash,
            nombre_empresa=nombre_empresa,
            plan=plan
        )
        db.add(usuario)
        db.commit()
        db.refresh(usuario)
        return usuario
    finally:
        db.close()

def verificar_password(email: str, password: str) -> Optional[Usuario]:
    """
    Verifica si el email y password son correctos.
    Retorna el usuario si es correcto, None si no.
    
    Ejemplo:
        usuario = verificar_password("cliente@ejemplo.com", "password123")
        if usuario:
            print("Login exitoso")
    """
    db = next(get_db())
    try:
        usuario = db.query(Usuario).filter(Usuario.email == email).first()
        if usuario and bcrypt.checkpw(password.encode('utf-8'), usuario.password_hash.encode('utf-8')):
            return usuario
        return None
    finally:
        db.close()

def obtener_usuario(usuario_id: int) -> Optional[Usuario]:
    """Obtiene un usuario por su ID."""
    db = next(get_db())
    try:
        return db.query(Usuario).filter(Usuario.id == usuario_id).first()
    finally:
        db.close()

def obtener_usuario_por_email(email: str) -> Optional[Usuario]:
    """Obtiene un usuario por su email."""
    db = next(get_db())
    try:
        return db.query(Usuario).filter(Usuario.email == email).first()
    finally:
        db.close()

# ============================================
# FUNCIONES DE CLASIFICADORES
# ============================================

def crear_clasificador(
    usuario_id: int,
    nombre: str,
    tipo: str,  # "abono" o "cargo"
    palabras_clave: List[str],
    tipo_coincidencia: str = "contiene_cualquiera",
    excluir: Optional[List[str]] = None,
    orden: int = 0
) -> Clasificador:
    """
    Crea un clasificador para un usuario.
    
    Ejemplo:
        clasificador = crear_clasificador(
            usuario_id=1,
            nombre="PROVEEDORES NACIONALES",
            tipo="cargo",
            palabras_clave=["PROVEEDORES", "SERVIPAG", "AGUA"],
            tipo_coincidencia="contiene_cualquiera"
        )
    """
    db = next(get_db())
    try:
        tipo_enum = TipoTransaccion.ABONO if tipo.lower() == "abono" else TipoTransaccion.CARGO
        
        clasificador = Clasificador(
            usuario_id=usuario_id,
            nombre=nombre,
            tipo=tipo_enum,
            palabras_clave=json.dumps(palabras_clave),
            tipo_coincidencia=tipo_coincidencia,
            excluir=json.dumps(excluir) if excluir else None,
            orden=orden
        )
        db.add(clasificador)
        db.commit()
        db.refresh(clasificador)
        return clasificador
    finally:
        db.close()

def obtener_clasificadores(usuario_id: int, tipo: Optional[str] = None) -> List[Clasificador]:
    """
    Obtiene todos los clasificadores de un usuario.
    
    Ejemplo:
        clasificadores = obtener_clasificadores(usuario_id=1, tipo="cargo")
    """
    db = next(get_db())
    try:
        query = db.query(Clasificador).filter(
            and_(
                Clasificador.usuario_id == usuario_id,
                Clasificador.activo == True
            )
        )
        
        if tipo:
            tipo_enum = TipoTransaccion.ABONO if tipo.lower() == "abono" else TipoTransaccion.CARGO
            query = query.filter(Clasificador.tipo == tipo_enum)
        
        return query.order_by(Clasificador.orden).all()
    finally:
        db.close()

def eliminar_clasificador(clasificador_id: int, usuario_id: int) -> bool:
    """Elimina (desactiva) un clasificador."""
    db = next(get_db())
    try:
        clasificador = db.query(Clasificador).filter(
            and_(
                Clasificador.id == clasificador_id,
                Clasificador.usuario_id == usuario_id
            )
        ).first()
        
        if clasificador:
            clasificador.activo = False
            db.commit()
            return True
        return False
    finally:
        db.close()

# ============================================
# FUNCIONES DE TRANSACCIONES
# ============================================

def guardar_transacciones(transacciones: List[dict], usuario_id: int, archivo_id: Optional[int] = None) -> int:
    """
    Guarda múltiples transacciones en la base de datos.
    
    Ejemplo:
        transacciones = [
            {
                "fecha": datetime(2025, 11, 20),
                "descripcion": "PAGO A PROVEEDOR",
                "abono": 0,
                "cargo": 100000,
                "saldo": 500000,
                "clasificacion": "PROVEEDORES NACIONALES",
                "comentario": "PAGO A PROVEEDOR"
            },
            ...
        ]
        total = guardar_transacciones(transacciones, usuario_id=1, archivo_id=1)
    """
    db = next(get_db())
    try:
        count = 0
        for trans in transacciones:
            transaccion = Transaccion(
                usuario_id=usuario_id,
                archivo_id=archivo_id,
                fecha=trans.get("fecha"),
                descripcion=trans.get("descripcion"),
                abono=trans.get("abono", 0),
                cargo=trans.get("cargo", 0),
                saldo=trans.get("saldo"),
                clasificacion=trans.get("clasificacion"),
                comentario=trans.get("comentario")
            )
            db.add(transaccion)
            count += 1
        
        db.commit()
        return count
    finally:
        db.close()

def obtener_transacciones(
    usuario_id: int,
    fecha_desde: Optional[datetime] = None,
    fecha_hasta: Optional[datetime] = None,
    clasificacion: Optional[str] = None,
    archivo_id: Optional[int] = None
) -> List[Transaccion]:
    """
    Obtiene transacciones de un usuario con filtros opcionales.
    
    Ejemplo:
        transacciones = obtener_transacciones(
            usuario_id=1,
            fecha_desde=datetime(2025, 11, 1),
            fecha_hasta=datetime(2025, 11, 30),
            clasificacion="PROVEEDORES NACIONALES",
            archivo_id=5  # Opcional: filtrar por archivo específico
        )
    """
    db = next(get_db())
    try:
        query = db.query(Transaccion).filter(Transaccion.usuario_id == usuario_id)
        
        if archivo_id:
            query = query.filter(Transaccion.archivo_id == archivo_id)
        if fecha_desde:
            query = query.filter(Transaccion.fecha >= fecha_desde)
        if fecha_hasta:
            query = query.filter(Transaccion.fecha <= fecha_hasta)
        if clasificacion:
            query = query.filter(Transaccion.clasificacion == clasificacion)
        
        # Si se especifica archivo_id, ordenar por ID (orden de inserción original de la cartola)
        # Si no, ordenar por fecha ascendente (más antigua primero, más reciente al final)
        if archivo_id:
            # Ordenar por ID para mantener el orden original de la cartola
            return query.order_by(Transaccion.id.asc()).all()
        else:
            # Ordenar por fecha ascendente (más antigua primero)
            return query.order_by(Transaccion.fecha.asc()).all()
    finally:
        db.close()

def obtener_transacciones_sin_clasificar(usuario_id: int) -> List[Transaccion]:
    """Obtiene transacciones que no tienen clasificación o están como 'NO CLASIFICADO'."""
    db = next(get_db())
    try:
        return db.query(Transaccion).filter(
            and_(
                Transaccion.usuario_id == usuario_id,
                or_(
                    Transaccion.clasificacion == None,
                    Transaccion.clasificacion == "NO CLASIFICADO"
                )
            )
        ).all()
    finally:
        db.close()

# ============================================
# FUNCIONES DE ARCHIVOS
# ============================================

def registrar_archivo(
    usuario_id: int,
    nombre_archivo: str,
    banco: Optional[str] = None,
    total_registros: int = 0
) -> ArchivoCargado:
    """
    Registra un archivo cargado.
    
    Ejemplo:
        archivo = registrar_archivo(
            usuario_id=1,
            nombre_archivo="cartola_noviembre_2025.xlsx",
            banco="Banco de Chile",
            total_registros=150
        )
    """
    db = next(get_db())
    try:
        archivo = ArchivoCargado(
            usuario_id=usuario_id,
            nombre_archivo=nombre_archivo,
            banco=banco,
            total_registros=total_registros,
            estado="procesado"
        )
        db.add(archivo)
        db.commit()
        db.refresh(archivo)
        return archivo
    finally:
        db.close()

def obtener_archivos(usuario_id: int) -> List[ArchivoCargado]:
    """Obtiene todos los archivos cargados por un usuario."""
    db = next(get_db())
    try:
        return db.query(ArchivoCargado).filter(
            ArchivoCargado.usuario_id == usuario_id
        ).order_by(ArchivoCargado.fecha_carga.desc()).all()
    finally:
        db.close()

# ============================================
# FUNCIONES DE MAPEO DE COLUMNAS
# ============================================

def guardar_mapeo_columnas(
    usuario_id: int,
    banco: str,
    columna_fecha: str,
    columna_descripcion: str,
    columna_abono: str,
    columna_cargo: Optional[str] = None,
    columna_saldo: Optional[str] = None
) -> MapeoColumnas:
    """
    Guarda la configuración de mapeo de columnas para un banco.
    
    Ejemplo:
        mapeo = guardar_mapeo_columnas(
            usuario_id=1,
            banco="Banco de Chile",
            columna_fecha="FECHA",
            columna_descripcion="DESCRIPCION",
            columna_abono="ABONOS (CLP)",
            columna_cargo="CARGOS (CLP)",
            columna_saldo="SALDO (CLP)"
        )
    """
    db = next(get_db())
    try:
        # Desactivar mapeos anteriores del mismo banco
        db.query(MapeoColumnas).filter(
            and_(
                MapeoColumnas.usuario_id == usuario_id,
                MapeoColumnas.banco == banco
            )
        ).update({"activo": False})
        
        mapeo = MapeoColumnas(
            usuario_id=usuario_id,
            banco=banco,
            columna_fecha=columna_fecha,
            columna_descripcion=columna_descripcion,
            columna_abono=columna_abono,
            columna_cargo=columna_cargo,
            columna_saldo=columna_saldo
        )
        db.add(mapeo)
        db.commit()
        db.refresh(mapeo)
        return mapeo
    finally:
        db.close()

def obtener_mapeo_columnas(usuario_id: int, banco: Optional[str] = None) -> Optional[MapeoColumnas]:
    """Obtiene el mapeo de columnas activo para un usuario y banco."""
    db = next(get_db())
    try:
        query = db.query(MapeoColumnas).filter(
            and_(
                MapeoColumnas.usuario_id == usuario_id,
                MapeoColumnas.activo == True
            )
        )
        
        if banco:
            query = query.filter(MapeoColumnas.banco == banco)
        
        return query.first()
    finally:
        db.close()

# ============================================
# FUNCIONES DE ALERTAS
# ============================================

def crear_alerta(usuario_id: int, tipo: str, mensaje: str) -> Alerta:
    """
    Crea una alerta para un usuario.
    
    Ejemplo:
        alerta = crear_alerta(
            usuario_id=1,
            tipo="sin_clasificar",
            mensaje="Hay 15 transacciones sin clasificar"
        )
    """
    db = next(get_db())
    try:
        alerta = Alerta(
            usuario_id=usuario_id,
            tipo=tipo,
            mensaje=mensaje
        )
        db.add(alerta)
        db.commit()
        db.refresh(alerta)
        return alerta
    finally:
        db.close()

def obtener_alertas(usuario_id: int, no_leidas: bool = True) -> List[Alerta]:
    """Obtiene alertas de un usuario."""
    db = next(get_db())
    try:
        query = db.query(Alerta).filter(Alerta.usuario_id == usuario_id)
        
        if no_leidas:
            query = query.filter(Alerta.leida == False)
        
        return query.order_by(Alerta.fecha.desc()).all()
    finally:
        db.close()

def marcar_alerta_leida(alerta_id: int, usuario_id: int) -> bool:
    """Marca una alerta como leída."""
    db = next(get_db())
    try:
        alerta = db.query(Alerta).filter(
            and_(
                Alerta.id == alerta_id,
                Alerta.usuario_id == usuario_id
            )
        ).first()
        
        if alerta:
            alerta.leida = True
            db.commit()
            return True
        return False
    finally:
        db.close()

