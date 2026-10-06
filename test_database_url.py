# -*- coding: utf-8 -*-
"""Tests: normalización de DATABASE_URL hacia postgresql+psycopg2."""
from __future__ import annotations

import unittest

from database.connection import normalize_database_url


class TestNormalizeDatabaseUrl(unittest.TestCase):
    def test_postgres_scheme_uses_psycopg2(self):
        url = "postgres://user:pass@host:5432/dbname"
        self.assertEqual(
            normalize_database_url(url),
            "postgresql+psycopg2://user:pass@host:5432/dbname",
        )

    def test_postgresql_scheme_uses_psycopg2(self):
        url = "postgresql://user:pass@host:5432/dbname"
        self.assertEqual(
            normalize_database_url(url),
            "postgresql+psycopg2://user:pass@host:5432/dbname",
        )

    def test_explicit_driver_and_sqlite_unchanged(self):
        self.assertEqual(
            normalize_database_url("postgresql+psycopg2://u:p@h/db"),
            "postgresql+psycopg2://u:p@h/db",
        )
        self.assertEqual(
            normalize_database_url("postgresql+asyncpg://u:p@h/db"),
            "postgresql+asyncpg://u:p@h/db",
        )
        self.assertEqual(
            normalize_database_url("sqlite:///tmp/app.db"),
            "sqlite:///tmp/app.db",
        )


if __name__ == "__main__":
    unittest.main()
