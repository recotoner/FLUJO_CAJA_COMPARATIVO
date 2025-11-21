# 🗄️ Opciones de Base de Datos para el Sistema

## Comparación de Opciones

| Característica | SQLite | MySQL/MariaDB | PostgreSQL |
|---------------|--------|---------------|------------|
| **Instalación** | ✅ Incluido en Python | ⚠️ Requiere servidor | ⚠️ Requiere servidor |
| **Configuración** | ✅ Cero configuración | ⚠️ Requiere setup | ⚠️ Requiere setup |
| **Escalabilidad** | ⚠️ Hasta ~100 usuarios | ✅ Muy escalable | ✅ Muy escalable |
| **Backup** | ✅ Copiar archivo | ⚠️ Requiere mysqldump | ⚠️ Requiere pg_dump |
| **Costo** | ✅ Gratis | ✅ Gratis | ✅ Gratis |
| **Complejidad** | ✅ Muy simple | ⚠️ Media | ⚠️ Media-Alta |
| **Ideal para** | Desarrollo, MVP, pequeña/mediana escala | Producción, alta escala | Producción, datos complejos |

---

## 🎯 Recomendación: SQLite para Empezar

### ¿Por qué SQLite?

1. **Cero configuración**: Solo instalar Python (ya lo tienes)
2. **Archivo único**: `flujo_caja.db` - fácil de respaldar
3. **Perfecto para MVP**: Validar el producto antes de escalar
4. **Migración fácil**: Se puede migrar a MySQL después sin cambiar código (usando SQLAlchemy)

### Estructura con SQLite

```
api_cluster/
├── flujo_caja_app.py
├── database/
│   ├── flujo_caja.db          # Archivo SQLite (se crea automáticamente)
│   ├── models.py              # Modelos SQLAlchemy
│   └── init_db.py             # Script para crear tablas
└── ...
```

### Código de Ejemplo (SQLite)

```python
# database/connection.py
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import os

# SQLite - Archivo local
DATABASE_URL = "sqlite:///database/flujo_caja.db"

engine = create_engine(DATABASE_URL, echo=True)
SessionLocal = sessionmaker(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

---

## 📦 Dependencias Necesarias

### Para SQLite:
```txt
# requirements.txt (agregar)
sqlalchemy>=2.0.0
streamlit-authenticator>=0.2.3
bcrypt>=4.0.0
```

### Para MySQL (si decides usarlo después):
```txt
# requirements.txt (agregar)
sqlalchemy>=2.0.0
pymysql>=1.1.0
# o
mysql-connector-python>=8.0.0
```

---

## 🔄 Migración Futura (SQLite → MySQL)

Si después necesitas MySQL, el cambio es mínimo con SQLAlchemy:

```python
# Solo cambiar la URL de conexión
# De:
DATABASE_URL = "sqlite:///database/flujo_caja.db"

# A:
DATABASE_URL = "mysql+pymysql://usuario:password@localhost/flujo_caja"
```

El resto del código **NO cambia** porque SQLAlchemy abstrae la base de datos.

---

## 🚀 Plan de Implementación

### Fase 1: SQLite (Recomendado)
1. Instalar SQLAlchemy
2. Crear modelos
3. Crear tablas
4. Implementar CRUD
5. **Ventaja**: Funciona inmediatamente, sin servidor

### Fase 2: Migración a MySQL (Opcional, si es necesario)
1. Instalar MySQL
2. Crear base de datos
3. Cambiar URL de conexión
4. Migrar datos (script simple)
5. **Ventaja**: Escalabilidad

---

## 💡 Mi Recomendación Final

**Empezar con SQLite porque:**
- ✅ Funciona de inmediato
- ✅ No requiere configuración
- ✅ Fácil de respaldar (copiar archivo)
- ✅ Perfecto para validar el producto
- ✅ Migración a MySQL es trivial después

**Considerar MySQL si:**
- Tienes más de 50-100 usuarios simultáneos
- Necesitas características avanzadas
- Ya tienes infraestructura MySQL

¿Con cuál quieres empezar?


