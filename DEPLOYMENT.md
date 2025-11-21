# 🚀 Guía de Despliegue en Render

## Configuración para PostgreSQL en Render

### Paso 1: Crear Base de Datos PostgreSQL en Render

1. Ve a tu dashboard de Render
2. Click en "New +" → "PostgreSQL"
3. Configura:
   - **Name**: `flujo-caja-db`
   - **Database**: `flujo_caja`
   - **User**: `flujo_caja_user`
   - **Plan**: Free (o el que prefieras)
4. Click en "Create Database"
5. **IMPORTANTE**: Copia la **Internal Database URL** (algo como: `postgresql://user:password@host:port/dbname`)

### Paso 2: Crear Servicio Web en Render

1. En Render, click en "New +" → "Web Service"
2. Conecta tu repositorio de GitHub
3. Configura:
   - **Name**: `flujo-caja-app`
   - **Environment**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `streamlit run flujo_caja_app.py --server.port $PORT --server.address 0.0.0.0`

### Paso 3: Configurar Variables de Entorno

En la sección "Environment" del servicio web, agrega:

- **Key**: `DATABASE_URL`
- **Value**: Pega la **Internal Database URL** que copiaste en el Paso 1

### Paso 4: Inicializar la Base de Datos

Una vez desplegado, necesitas crear las tablas. Tienes dos opciones:

#### Opción A: Script de inicialización automática

El código ya incluye `init_db()` que se ejecutará automáticamente la primera vez.

#### Opción B: Script manual (recomendado para producción)

Crea un script `init_db_render.py`:

```python
from database.connection import init_db
import os

if __name__ == "__main__":
    if not os.getenv("DATABASE_URL"):
        print("❌ DATABASE_URL no está configurada")
        exit(1)
    
    print("Inicializando base de datos...")
    init_db()
    print("✅ Base de datos inicializada correctamente")
```

Y ejecútalo una vez en Render usando el shell:
```bash
python init_db_render.py
```

### Paso 5: Crear Usuario Administrador

Después de inicializar la BD, crea tu primer usuario:

```bash
python crear_cliente.py
```

## 🔧 Configuración Local vs Producción

### Desarrollo Local (SQLite)
- No necesitas configurar nada
- La BD se crea automáticamente en `database/flujo_caja.db`

### Producción (PostgreSQL)
- Configura la variable de entorno `DATABASE_URL`
- El sistema detectará automáticamente PostgreSQL y usará esa conexión

## 📝 Notas Importantes

1. **Migración de Datos**: Si tienes datos en SQLite local y quieres migrarlos a PostgreSQL, necesitarás un script de migración.

2. **Backups**: Configura backups automáticos en Render para tu base de datos PostgreSQL.

3. **Seguridad**: 
   - Nunca commitees la `DATABASE_URL` en el código
   - Usa variables de entorno siempre
   - La Internal Database URL de Render solo es accesible desde otros servicios de Render

4. **Escalabilidad**: PostgreSQL en Render puede escalar según tu plan.

## 🐛 Troubleshooting

### Error: "No module named 'psycopg2'"
- Asegúrate de que `psycopg2-binary` esté en `requirements.txt`

### Error: "Connection refused"
- Verifica que `DATABASE_URL` esté configurada correctamente
- Asegúrate de usar la **Internal Database URL** (no la External)

### Error: "Table does not exist"
- Ejecuta `init_db()` para crear las tablas
- Verifica que la conexión a PostgreSQL funcione

## ✅ Checklist de Despliegue

- [ ] Base de datos PostgreSQL creada en Render
- [ ] Variable de entorno `DATABASE_URL` configurada
- [ ] `requirements.txt` incluye `psycopg2-binary`
- [ ] Tablas creadas en PostgreSQL (ejecutar `init_db()`)
- [ ] Usuario administrador creado
- [ ] Aplicación desplegada y funcionando
- [ ] Backups configurados

