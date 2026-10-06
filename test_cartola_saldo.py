# -*- coding: utf-8 -*-
"""Tests mínimos: saldo de cierre según orientación estructural de la cartola."""
from __future__ import annotations

import unittest
from datetime import date

import pandas as pd

from cartola_saldo import (
    detectar_orientacion_cartola,
    saldo_cierre_desde_dataframe,
)


class TestCartolaSaldoCierre(unittest.TestCase):
    def test_cartola_ascendente_toma_ultimo_saldo_del_ultimo_dia(self):
        df = pd.DataFrame(
            {
                "FECHA": pd.to_datetime(
                    ["2026-09-29", "2026-09-29", "2026-09-30", "2026-09-30", "2026-09-30"]
                ),
                "ABONOS (CLP)": [1000, 0, 5000, 0, 2000],
                "CARGOS (CLP)": [0, 500, 0, 1000, 0],
                "SALDO (CLP)": [10000, 9500, 14500, 13500, 15500],
            }
        )
        orient = detectar_orientacion_cartola(
            list(df["FECHA"]),
            list(range(len(df))),
            saldos=list(df["SALDO (CLP)"]),
            abonos=list(df["ABONOS (CLP)"]),
            cargos=list(df["CARGOS (CLP)"]),
        )
        self.assertEqual(orient, "asc")
        saldo, fecha, o2 = saldo_cierre_desde_dataframe(df)
        self.assertEqual(o2, "asc")
        self.assertEqual(saldo, 15500.0)
        self.assertEqual(pd.Timestamp(fecha).date(), date(2026, 9, 30))

    def test_cartola_descendente_toma_primer_saldo_del_ultimo_dia(self):
        # Archivo reciente → antiguo: primera fila del 30/09 es el cierre.
        df = pd.DataFrame(
            {
                "FECHA": pd.to_datetime(
                    ["2026-09-30", "2026-09-30", "2026-09-30", "2026-09-29", "2026-09-29"]
                ),
                "ABONOS (CLP)": [2000, 0, 5000, 0, 1000],
                "CARGOS (CLP)": [0, 1000, 0, 500, 0],
                "SALDO (CLP)": [15500, 13500, 14500, 9500, 10000],
            }
        )
        orient = detectar_orientacion_cartola(
            list(df["FECHA"]),
            list(range(len(df))),
            saldos=list(df["SALDO (CLP)"]),
            abonos=list(df["ABONOS (CLP)"]),
            cargos=list(df["CARGOS (CLP)"]),
        )
        self.assertEqual(orient, "desc")
        saldo, fecha, o2 = saldo_cierre_desde_dataframe(df)
        self.assertEqual(o2, "desc")
        self.assertEqual(saldo, 15500.0)
        self.assertEqual(pd.Timestamp(fecha).date(), date(2026, 9, 30))

    def test_caso_real_septiembre_2026_cierre_25873919_no_intermedio_18311711(self):
        # Cartola cronológica ascendente: el 30/09 abre/intermedio en 18.311.711
        # y cierra en 25.873.919 (última fila original del día).
        df = pd.DataFrame(
            {
                "FECHA": pd.to_datetime(
                    [
                        "2026-09-28",
                        "2026-09-29",
                        "2026-09-30",
                        "2026-09-30",
                        "2026-09-30",
                        "2026-09-30",
                    ]
                ),
                "ABONOS (CLP)": [0, 100000, 500000, 0, 8000000, 0],
                "CARGOS (CLP)": [200000, 0, 0, 300000, 0, 137792],
                "SALDO (CLP)": [
                    17_000_000,
                    17_100_000,
                    18_311_711,  # intermedio / primera posición del 30/09 (incorrecto como cierre)
                    18_011_711,
                    26_011_711,
                    25_873_919,  # cierre real
                ],
            }
        )
        saldo, fecha, orient = saldo_cierre_desde_dataframe(df)
        self.assertEqual(orient, "asc")
        self.assertEqual(pd.Timestamp(fecha).date(), date(2026, 9, 30))
        self.assertEqual(saldo, 25_873_919.0)
        self.assertNotEqual(saldo, 18_311_711.0)


if __name__ == "__main__":
    unittest.main()
