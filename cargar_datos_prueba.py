"""
Carga de datos de prueba CxC/CxP desde Excel usando modulo_carga_erp.

Uso:
    python cargar_datos_prueba.py ruta_cxc.xlsx ruta_cxp.xlsx
    python cargar_datos_prueba.py ruta_cxc.xlsx ruta_cxp.xlsx 17

Notas:
- Usa DATABASE_URL desde variable de entorno si está definida.
- Si no se entrega user_id, usa el primer usuario activo.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from database.connection import get_db
from database.models import Usuario
from modulo_carga_erp import cargar_excel_cxc_cxp


def _resolver_user_id(arg_user_id: str | None) -> int:
    if arg_user_id:
        return int(arg_user_id)

    db = next(get_db())
    try:
        user = (
            db.query(Usuario)
            .filter(Usuario.activo.is_(True))
            .order_by(Usuario.id.asc())
            .first()
        )
        if not user:
            raise RuntimeError("No hay usuarios activos en la base de datos.")
        return int(user.id)
    finally:
        db.close()


def _validar_archivo(path_str: str) -> Path:
    p = Path(path_str)
    if not p.exists():
        raise FileNotFoundError(f"No existe el archivo: {p}")
    if p.suffix.lower() not in (".xlsx", ".xls"):
        raise ValueError(f"Archivo no soportado ({p.suffix}): {p}")
    return p


def _imprimir_resultado(nombre: str, res) -> None:
    print(f"\n[{nombre}]")
    print(f"- carga_id: {res.carga_id}")
    print(f"- total registros cargados: {res.facturas_guardadas}")
    if res.advertencias:
        print("- advertencias:")
        for w in res.advertencias[:100]:
            print(f"  * {w}")
        if len(res.advertencias) > 100:
            print(f"  * ... ({len(res.advertencias) - 100} advertencias más)")
    else:
        print("- advertencias: ninguna")


def main() -> None:
    if len(sys.argv) < 3:
        print("Uso: python cargar_datos_prueba.py ruta_cxc.xlsx ruta_cxp.xlsx [user_id]")
        sys.exit(1)

    ruta_cxc = _validar_archivo(sys.argv[1])
    ruta_cxp = _validar_archivo(sys.argv[2])
    user_id = _resolver_user_id(sys.argv[3] if len(sys.argv) > 3 else None)

    db_url = os.getenv("DATABASE_URL")
    if db_url:
        print("DATABASE_URL detectada: se usará PostgreSQL (según connection.py).")
    else:
        print("DATABASE_URL no detectada: se usará SQLite local (según connection.py).")

    print(f"user_id seleccionado: {user_id}")
    print(f"archivo CxC: {ruta_cxc}")
    print(f"archivo CxP: {ruta_cxp}")

    res_cxc = cargar_excel_cxc_cxp(
        user_id=user_id,
        fuente=str(ruta_cxc),
        nombre_archivo=ruta_cxc.name,
        es_cxc=True,
        preset_columnas="kame",
    )

    res_cxp = cargar_excel_cxc_cxp(
        user_id=user_id,
        fuente=str(ruta_cxp),
        nombre_archivo=ruta_cxp.name,
        es_cxc=False,
        preset_columnas="kame",
    )

    _imprimir_resultado("CxC", res_cxc)
    _imprimir_resultado("CxP", res_cxp)


if __name__ == "__main__":
    main()
