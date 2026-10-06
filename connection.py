"""
Conexión a la base de datos.
Soporta PostgreSQL (producción) y SQLite (desarrollo local).
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
import os
from pathlib import Path


def normalize_database_url(url: str) -> str:
    """
    Fuerza el driver psycopg2 en URLs PostgreSQL sin driver explícito.

    SQLAlchemy 2.1+ usa psycopg (v3) por defecto para postgresql://; este proyecto
    declara psycopg2-binary. No altera sqlite ni URLs que ya traen +driver.
    """
    if not url:
        return url
    if url.startswith("postgres://"):
        return "postgresql+psycopg2://" + url[len("postgres://") :]
    if url.startswith("postgresql://"):
        return "postgresql+psycopg2://" + url[len("postgresql://") :]
    return url


# Crear directorio si no existe
BASE_DIR = Path(__file__).parent.parent
DB_DIR = BASE_DIR / "database"
DB_DIR.mkdir(exist_ok=True)

# Determinar qué base de datos usar
# Prioridad: Variable de entorno DATABASE_URL > PostgreSQL local > SQLite
DATABASE_URL = os.getenv("DATABASE_URL")

if DATABASE_URL:
    # PostgreSQL en producción (Render, Heroku, etc.)
    DATABASE_URL = normalize_database_url(DATABASE_URL)

    # Configuración para PostgreSQL
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,  # Verificar conexiones antes de usarlas
        pool_recycle=300,     # Reciclar conexiones cada 5 minutos
        echo=False
    )
    # print("Conectado a PostgreSQL (produccion)")
else:
    # SQLite para desarrollo local
    DATABASE_FILE = DB_DIR / "flujo_caja.db"
    DATABASE_URL = f"sqlite:///{DATABASE_FILE}"

    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False},  # Necesario para SQLite con Streamlit
        echo=False
    )
    # print("Conectado a SQLite (desarrollo local)")

# Crear sesión
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base para los modelos
Base = declarative_base()

def get_db():
    """
    Obtiene una sesión de base de datos.
    Úsalo así:

    db = next(get_db())
    # hacer operaciones
    db.close()
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db():
    """
    Crea todas las tablas en la base de datos.
    Solo necesitas llamar esto UNA VEZ al inicio.
    """
    import database.models  # noqa: F401 — registra modelos en Base.metadata
    Base.metadata.create_all(bind=engine)
    from database.crud_proyeccion import _ensure_proyeccion_remuneraciones_columns

    _ensure_proyeccion_remuneraciones_columns()
    if os.getenv("DATABASE_URL"):
        print("Tablas creadas en PostgreSQL")
    else:
        print(f"Tablas creadas en SQLite: {DATABASE_FILE}")

