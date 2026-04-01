"""
Script para crear un archivo Excel de ejemplo con la estructura correcta
para el archivo de proyección de flujo de caja.
"""

import pandas as pd
from datetime import datetime

# Crear datos de ejemplo
datos = {
    'CLASIFICACION': [
        'Ventas',
        'Servicios',
        'Gastos Operacionales',
        'Gastos Administrativos',
        'Gastos de Personal',
        'Otros Ingresos'
    ],
    'TIPO DE MOVIMIENTO': [
        'INGRESO',
        'INGRESO',
        'EGRESO',
        'EGRESO',
        'EGRESO',
        'INGRESO'
    ],
    # Columnas de fecha en formato mmm-yy (minúsculas)
    'jul-25': [100000, 50000, 80000, 30000, 200000, 10000],
    'ago-25': [120000, 55000, 85000, 32000, 200000, 12000],
    'sep-25': [110000, 60000, 90000, 35000, 200000, 15000],
    'oct-25': [130000, 65000, 95000, 38000, 200000, 18000],
    'nov-25': [125000, 70000, 100000, 40000, 200000, 20000],
    'dic-25': [140000, 75000, 105000, 42000, 200000, 22000],
    'ene-26': [150000, 80000, 110000, 45000, 200000, 25000],
    'feb-26': [160000, 85000, 115000, 48000, 200000, 28000],
}

# Crear DataFrame
df = pd.DataFrame(datos)

# Guardar como Excel
nombre_archivo = 'ejemplo_proyeccion.xlsx'
df.to_excel(nombre_archivo, index=False, engine='openpyxl')

print(f"✅ Archivo creado: {nombre_archivo}")
print("\n📋 Estructura del archivo:")
print(df.to_string())
print("\n📌 IMPORTANTE:")
print("   - Los nombres de las columnas de fecha deben estar en minúsculas")
print("   - Formato: mmm-yy (ej: nov-25, dic-25)")
print("   - Los valores de TIPO DE MOVIMIENTO deben ser exactamente: INGRESO o EGRESO")








