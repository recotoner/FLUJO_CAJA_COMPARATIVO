"""
Script para inicializar la base de datos en Render/PostgreSQL.
Ejecutar una vez después del despliegue.
"""
from database.connection import init_db
import os
import sys

if __name__ == "__main__":
    # Verificar que DATABASE_URL esté configurada
    if not os.getenv("DATABASE_URL"):
        print("❌ ERROR: DATABASE_URL no está configurada")
        print("💡 Asegúrate de configurar la variable de entorno DATABASE_URL en Render")
        sys.exit(1)
    
    print("="*60)
    print("  INICIALIZANDO BASE DE DATOS")
    print("="*60)
    print(f"\n📊 Tipo de BD: PostgreSQL (Producción)")
    print(f"🔗 URL: {os.getenv('DATABASE_URL')[:50]}...")
    print("\n⏳ Creando tablas...")
    
    try:
        init_db()
        print("\n" + "="*60)
        print("✅ BASE DE DATOS INICIALIZADA CORRECTAMENTE")
        print("="*60)
        print("\n📋 Tablas creadas:")
        print("   - usuarios")
        print("   - clasificadores")
        print("   - transacciones")
        print("   - archivos_cargados")
        print("   - mapeo_columnas")
        print("   - alertas")
        print("\n💡 Próximo paso: Crear un usuario administrador con:")
        print("   python crear_cliente.py")
        print("="*60 + "\n")
    except Exception as e:
        print(f"\n❌ ERROR al inicializar la base de datos: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

