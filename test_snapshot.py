"""
Prueba simple del motor de snapshots.

Uso:
    python test_snapshot.py
    python test_snapshot.py 3
"""
from __future__ import annotations

import sys
from collections import defaultdict
from decimal import Decimal

from database.connection import get_db
from database.models import Usuario
from database import crud_proyeccion as crud_p
from proyeccion_caja import generar_snapshot


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


def main() -> None:
    arg_user_id = sys.argv[1] if len(sys.argv) > 1 else None
    user_id = _resolver_user_id(arg_user_id)

    print(f"Usuario seleccionado: {user_id}")
    snapshot = generar_snapshot(
        user_id=user_id,
        periodo_dias=30,
        etiqueta="test_snapshot_30d",
        notas="Prueba automatizada simple",
    )

    lineas = crud_p.listar_proyeccion_lineas_snapshot(snapshot.id)
    print(f"Snapshot creado: id={snapshot.id}, version={snapshot.version}")
    print(f"Total líneas creadas: {len(lineas)}")

    resumen_por_categoria: dict[str, Decimal] = defaultdict(lambda: Decimal(0))
    for ln in lineas:
        cat = crud_p.obtener_categoria_por_id(ln.categoria_id)
        nombre = cat.nombre if cat else f"categoria_{ln.categoria_id}"
        resumen_por_categoria[nombre] += Decimal(str(ln.monto))

    print("\nResumen por categoría:")
    if not resumen_por_categoria:
        print("- (sin líneas)")
    else:
        for nombre, total in sorted(resumen_por_categoria.items(), key=lambda x: x[0].lower()):
            print(f"- {nombre}: {total:,.2f}")


if __name__ == "__main__":
    main()
