"""
Script interactivo para crear nuevos clientes/usuarios en el sistema.
Ejecutar: python crear_cliente.py
"""
from database.crud import crear_usuario, obtener_usuario_por_email
import getpass
import sys
import os

# Configurar encoding para Windows
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

def validar_email(email):
    """Valida que el email tenga un formato básico correcto"""
    if '@' not in email or '.' not in email.split('@')[1]:
        return False
    return True

def crear_nuevo_cliente():
    """Función interactiva para crear un nuevo cliente"""
    print("\n" + "="*60)
    print("  CREAR NUEVO CLIENTE - Sistema Flujo de Caja")
    print("="*60 + "\n")
    
    # Solicitar email
    while True:
        email = input("Email del cliente: ").strip()
        if not email:
            print("❌ El email no puede estar vacío. Intenta de nuevo.\n")
            continue
        
        if not validar_email(email):
            print("❌ El formato del email no es válido. Intenta de nuevo.\n")
            continue
        
        # Verificar si el email ya existe
        usuario_existente = obtener_usuario_por_email(email)
        if usuario_existente:
            print(f"❌ El email {email} ya está registrado.")
            respuesta = input("¿Deseas continuar con otro email? (s/n): ").strip().lower()
            if respuesta != 's':
                print("Operación cancelada.")
                return None
            continue
        
        break
    
        # Solicitar nombre de empresa
    while True:
        nombre_empresa = input("Nombre de la empresa: ").strip()
        if not nombre_empresa:
            print("❌ El nombre de la empresa no puede estar vacío. Intenta de nuevo.\n")
            continue
        break
    
    # Solicitar contraseña
    while True:
        password = getpass.getpass("Contrasena: ")
        if len(password) < 6:
            print("❌ La contraseña debe tener al menos 6 caracteres. Intenta de nuevo.\n")
            continue
        
        password_confirm = getpass.getpass("Confirmar contrasena: ")
        if password != password_confirm:
            print("❌ Las contraseñas no coinciden. Intenta de nuevo.\n")
            continue
        break
    
    # Solicitar plan (opcional)
    print("\nPlanes disponibles:")
    print("  1. básico (por defecto)")
    print("  2. premium")
    print("  3. empresarial")
    plan_input = input("Selecciona el plan (1-3, Enter para básico): ").strip()
    
    planes = {
        '1': 'basico',
        '2': 'premium',
        '3': 'empresarial'
    }
    plan = planes.get(plan_input, 'basico')
    
    # Confirmar creación
    print("\n" + "-"*60)
    print("Resumen del cliente a crear:")
    print(f"   Email: {email}")
    print(f"   Empresa: {nombre_empresa}")
    print(f"   Plan: {plan}")
    print("-"*60)
    
    confirmar = input("\n¿Confirmar creación? (s/n): ").strip().lower()
    if confirmar != 's':
        print("❌ Operación cancelada.")
        return None
    
    # Crear usuario
    try:
        print("\n⏳ Creando cliente...")
        usuario = crear_usuario(
            email=email,
            password=password,
            nombre_empresa=nombre_empresa,
            plan=plan
        )
        
        print("\n" + "="*60)
        print("CLIENTE CREADO EXITOSAMENTE!")
        print("="*60)
        print(f"\nInformacion del cliente:")
        print(f"   ID: {usuario.id}")
        print(f"   Email: {usuario.email}")
        print(f"   Empresa: {usuario.nombre_empresa}")
        print(f"   Plan: {usuario.plan}")
        print(f"   Fecha de registro: {usuario.fecha_registro}")
        print(f"   Estado: {'Activo' if usuario.activo else 'Inactivo'}")
        print("\n" + "="*60)
        print("Credenciales de acceso:")
        print(f"   Email: {email}")
        print(f"   Contraseña: [la que ingresaste]")
        print("="*60 + "\n")
        
        return usuario
        
    except ValueError as e:
        print(f"\n❌ Error: {e}")
        return None
    except Exception as e:
        print(f"\n❌ Error inesperado: {e}")
        import traceback
        traceback.print_exc()
        return None

def listar_clientes():
    """Lista todos los clientes existentes"""
    from database.connection import get_db
    from database.models import Usuario
    
    db = next(get_db())
    try:
        clientes = db.query(Usuario).all()
        if not clientes:
            print("\nNo hay clientes registrados en el sistema.\n")
            return
        
        print("\n" + "="*80)
        print("  CLIENTES REGISTRADOS")
        print("="*80)
        print(f"{'ID':<5} {'Email':<30} {'Empresa':<25} {'Plan':<15} {'Estado':<10}")
        print("-"*80)
        
        for cliente in clientes:
            estado = "Activo" if cliente.activo else "Inactivo"
            print(f"{cliente.id:<5} {cliente.email:<30} {cliente.nombre_empresa:<25} {cliente.plan:<15} {estado}")
        
        print("="*80 + "\n")
    finally:
        db.close()

if __name__ == "__main__":
    print("\n" + "="*60)
    print("  GESTION DE CLIENTES - Sistema Flujo de Caja")
    print("="*60)
    
    while True:
        print("\nOpciones disponibles:")
        print("  1. Crear nuevo cliente")
        print("  2. Listar clientes existentes")
        print("  3. Salir")
        
        opcion = input("\nSelecciona una opción (1-3): ").strip()
        
        if opcion == '1':
            crear_nuevo_cliente()
        elif opcion == '2':
            listar_clientes()
        elif opcion == '3':
            print("\nHasta luego!\n")
            sys.exit(0)
        else:
            print("❌ Opción no válida. Por favor selecciona 1, 2 o 3.")

