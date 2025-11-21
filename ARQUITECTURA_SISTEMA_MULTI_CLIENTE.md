# 🏗️ Arquitectura Sistema Multi-Cliente - Flujo de Caja

## ✅ Factibilidad: TOTALMENTE FACTIBLE

El código actual tiene una base excelente que se puede extender. Aquí está el plan:

---

## 📊 Estado Actual (Lo que ya tienes)

✅ Sistema de clasificadores parametrizable (JSON/Excel)  
✅ Detección automática de cliente  
✅ Carga y procesamiento de Excel  
✅ Clasificación inteligente de transacciones  
✅ Dashboard con visualizaciones  
⚠️ **NO hay base de datos** - Se creará desde cero  

---

## 🎯 Funcionalidades a Agregar

### 1. **Sistema de Autenticación y Usuarios**
- Login por cliente
- Sesiones seguras
- Roles y permisos

### 2. **Gestión de Archivos**
- Subida de cartolas bancarias
- Almacenamiento por cliente
- Historial de cargas

### 3. **Mapeo de Columnas Configurable**
- Cada banco tiene formato diferente
- Cliente configura qué columna es qué
- Guardar mapeo por cliente/banco

### 4. **Editor de Clasificadores en la App**
- Interfaz visual para crear/editar clasificadores
- Sin necesidad de editar JSON/Excel manualmente
- Guardar en base de datos

### 5. **Sistema de Alertas**
- Detectar movimientos sin clasificar
- Notificaciones visuales
- Reportes de clasificación incompleta

### 6. **Persistencia de Datos**
- Guardar transacciones en BD
- Historial completo
- Consultas y reportes históricos

---

## 🏛️ Arquitectura Propuesta

### **Opciones de Base de Datos**

Tienes 3 opciones, desde la más simple hasta la más robusta:

#### **Opción 1: SQLite (Recomendada para empezar)** ⭐
- ✅ **Ventajas**: 
  - No requiere servidor
  - Archivo único, fácil de respaldar
  - Perfecto para desarrollo y producción pequeña/mediana
  - Cero configuración
- ❌ **Desventajas**: 
  - Menos eficiente con muchos usuarios simultáneos
  - No soporta algunas características avanzadas

#### **Opción 2: MySQL/MariaDB**
- ✅ **Ventajas**: 
  - Muy robusto y escalable
  - Soporta muchos usuarios simultáneos
  - Estándar en la industria
- ❌ **Desventajas**: 
  - Requiere servidor/configuración
  - Más complejo de mantener

#### **Opción 3: PostgreSQL**
- ✅ **Ventajas**: 
  - Muy robusto
  - Open source
  - Excelente para datos complejos
- ❌ **Desventajas**: 
  - Requiere servidor/configuración
  - Curva de aprendizaje más alta

**Recomendación**: Empezar con **SQLite** y migrar a MySQL después si es necesario.

---

### **Base de Datos (SQLite/MySQL)**

```sql
-- Tabla de Usuarios/Clientes
CREATE TABLE usuarios (
    id INT PRIMARY KEY AUTO_INCREMENT,
    email VARCHAR(255) UNIQUE,
    password_hash VARCHAR(255),
    nombre_empresa VARCHAR(255),
    activo BOOLEAN DEFAULT TRUE,
    fecha_registro DATETIME,
    plan VARCHAR(50) -- 'basico', 'premium', etc.
);

-- Tabla de Configuraciones de Clasificadores
CREATE TABLE clasificadores (
    id INT PRIMARY KEY AUTO_INCREMENT,
    usuario_id INT,
    nombre VARCHAR(255),
    tipo ENUM('abono', 'cargo'),
    palabras_clave TEXT, -- JSON array
    tipo_coincidencia VARCHAR(50),
    excluir TEXT, -- JSON array (opcional)
    activo BOOLEAN DEFAULT TRUE,
    orden INT, -- Orden de evaluación
    FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
);

-- Tabla de Mapeo de Columnas (por banco)
CREATE TABLE mapeo_columnas (
    id INT PRIMARY KEY AUTO_INCREMENT,
    usuario_id INT,
    banco VARCHAR(100),
    columna_fecha VARCHAR(100),
    columna_descripcion VARCHAR(100),
    columna_abono VARCHAR(100),
    columna_cargo VARCHAR(100),
    columna_saldo VARCHAR(100),
    activo BOOLEAN DEFAULT TRUE,
    FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
);

-- Tabla de Archivos Cargados
CREATE TABLE archivos_cargados (
    id INT PRIMARY KEY AUTO_INCREMENT,
    usuario_id INT,
    nombre_archivo VARCHAR(255),
    fecha_carga DATETIME,
    banco VARCHAR(100),
    total_registros INT,
    estado VARCHAR(50), -- 'procesado', 'error', 'pendiente'
    FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
);

-- Tabla de Transacciones
CREATE TABLE transacciones (
    id INT PRIMARY KEY AUTO_INCREMENT,
    usuario_id INT,
    archivo_id INT,
    fecha DATE,
    descripcion TEXT,
    abono DECIMAL(15,2),
    cargo DECIMAL(15,2),
    saldo DECIMAL(15,2),
    clasificacion VARCHAR(255),
    comentario TEXT,
    fecha_registro DATETIME,
    FOREIGN KEY (usuario_id) REFERENCES usuarios(id),
    FOREIGN KEY (archivo_id) REFERENCES archivos_cargados(id),
    INDEX idx_usuario_fecha (usuario_id, fecha),
    INDEX idx_clasificacion (clasificacion)
);

-- Tabla de Alertas
CREATE TABLE alertas (
    id INT PRIMARY KEY AUTO_INCREMENT,
    usuario_id INT,
    tipo VARCHAR(50), -- 'sin_clasificar', 'error_mapeo', etc.
    mensaje TEXT,
    fecha DATETIME,
    leida BOOLEAN DEFAULT FALSE,
    FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
);
```

---

## 🔄 Flujo de Usuario Propuesto

### **1. Registro/Login**
```
Usuario → Login → Dashboard (solo sus datos)
```

### **2. Primera Configuración (One-Time Setup)**

**Paso 1: Configurar Mapeo de Columnas**
- Sube un archivo de ejemplo de su banco
- Sistema detecta columnas automáticamente
- Usuario confirma/ajusta el mapeo
- Guarda configuración: "Banco X → Columnas Y"

**Paso 2: Configurar Clasificadores**
- Interfaz visual para crear reglas
- O importar desde Excel/JSON
- Guarda en BD

### **3. Uso Normal**

**Cargar Cartola:**
1. Usuario sube archivo Excel
2. Sistema detecta banco (o usuario selecciona)
3. Aplica mapeo de columnas guardado
4. Procesa y clasifica automáticamente
5. Muestra alertas si hay movimientos sin clasificar
6. Guarda en BD

**Dashboard:**
- Muestra solo datos del usuario logueado
- Filtros por fecha, clasificación
- Alertas de movimientos sin clasificar

---

## 🛠️ Implementación Técnica

### **Stack Tecnológico**

**Backend:**
- Python (Streamlit) - Ya lo tienes ✅
- Base de datos: **SQLite** (recomendado) o MySQL
- **SQLAlchemy** (ORM) - Funciona con SQLite y MySQL
- O **sqlite3** (built-in Python) si usas SQLite

**Autenticación:**
- `streamlit-authenticator` (librería)
- O implementación custom con session_state

**Almacenamiento:**
- Archivos: Directorio por usuario o S3/Cloud Storage
- Datos: MySQL

### **Estructura de Código Propuesta**

```
flujo_caja_app/
├── app.py                    # App principal Streamlit
├── auth/
│   ├── login.py              # Módulo de autenticación
│   └── session_manager.py    # Gestión de sesiones
├── database/
│   ├── models.py             # Modelos SQLAlchemy
│   ├── connection.py         # Conexión BD
│   └── queries.py             # Queries comunes
├── upload/
│   ├── file_handler.py       # Manejo de archivos
│   └── column_mapper.py      # Mapeo de columnas
├── classifiers/
│   ├── editor.py             # Editor visual de clasificadores
│   └── manager.py            # Gestión de clasificadores
├── alerts/
│   └── alert_manager.py      # Sistema de alertas
└── utils/
    ├── excel_processor.py    # Procesamiento Excel
    └── normalizer.py         # Normalización (ya existe)
```

---

## 📝 Plan de Implementación (Fases)

### **Fase 1: Autenticación y Base de Datos** (1-2 semanas)
- [ ] Crear tablas en MySQL
- [ ] Implementar login/logout
- [ ] Sistema de sesiones
- [ ] Aislar datos por usuario

### **Fase 2: Subida de Archivos** (1 semana)
- [ ] Componente de subida
- [ ] Almacenamiento por usuario
- [ ] Validación de formato

### **Fase 3: Mapeo de Columnas** (1-2 semanas)
- [ ] Detección automática de columnas
- [ ] Interfaz de configuración
- [ ] Guardar mapeos por banco/cliente

### **Fase 4: Editor de Clasificadores** (1-2 semanas)
- [ ] Interfaz visual
- [ ] CRUD de clasificadores
- [ ] Importar/Exportar

### **Fase 5: Sistema de Alertas** (1 semana)
- [ ] Detección de movimientos sin clasificar
- [ ] Notificaciones visuales
- [ ] Reportes

### **Fase 6: Persistencia y Dashboard** (1-2 semanas)
- [ ] Guardar transacciones en BD
- [ ] Consultas históricas
- [ ] Mejoras al dashboard

---

## 💡 Ventajas de esta Arquitectura

✅ **Escalable**: Fácil agregar nuevos clientes  
✅ **Seguro**: Datos aislados por usuario  
✅ **Flexible**: Cada cliente configura su banco  
✅ **Mantenible**: Código modular  
✅ **Reutiliza código actual**: 70% del código existente se puede mantener  

---

## 🔧 Modificaciones al Código Actual

### **Lo que se REUTILIZA:**
- ✅ Función `normalizar()`
- ✅ Función `clasificar_mejorado()`
- ✅ Función `evaluar_clasificador()`
- ✅ Lógica de procesamiento Excel
- ✅ Dashboard y visualizaciones

### **Lo que se MODIFICA:**
- 🔄 Carga de datos: De archivo local → BD
- 🔄 Clasificadores: De JSON/Excel → BD
- 🔄 Detección cliente: De nombre archivo → Login

### **Lo que se AGREGA:**
- ➕ Sistema de autenticación
- ➕ Mapeo de columnas
- ➕ Editor de clasificadores
- ➕ Sistema de alertas
- ➕ Gestión de archivos

---

## 🚀 ¿Quieres que empecemos?

Puedo ayudarte a implementar esto paso a paso. Sugerencia:

1. **Empezar con Fase 1** (Autenticación + BD)
2. **Migrar código actual** para usar BD
3. **Agregar funcionalidades** una por una

¿Te parece bien este enfoque?

