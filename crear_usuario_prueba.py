"""
Script para crear un usuario de prueba.
Ejecutar: python crear_usuario_prueba.py
"""
from database.crud import crear_usuario

if __name__ == "__main__":
    print("Creando usuario de prueba...")
    
    try:
        usuario = crear_usuario(
            email="demo@ejemplo.com",
            password="demo123",
            nombre_empresa="Empresa Demo",
            plan="basico"
        )
        print(f"Usuario creado exitosamente!")
        print(f"Email: {usuario.email}")
        print(f"Nombre: {usuario.nombre_empresa}")
        print(f"ID: {usuario.id}")
        print("\nPuedes iniciar sesión con:")
        print("  Email: demo@ejemplo.com")
        print("  Password: demo123")
    except ValueError as e:
        print(f"Error: {e}")
        print("El usuario ya existe. Puedes usar:")
        print("  Email: demo@ejemplo.com")
        print("  Password: demo123")









