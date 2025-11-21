"""
Script para inicializar la base de datos.
Solo necesitas ejecutar esto UNA VEZ al inicio.

Ejecutar desde el directorio raíz del proyecto:
    python database/init_db.py
"""
import sys
from pathlib import Path

# Agregar el directorio raíz al path
BASE_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BASE_DIR))

from database.connection import init_db, engine
from database.models import Base

if __name__ == "__main__":
    print("Creando base de datos...")
    init_db()
    print("Base de datos lista!")
    print("\nAhora puedes usar el sistema normalmente.")
    print("La base de datos esta en: database/flujo_caja.db")

