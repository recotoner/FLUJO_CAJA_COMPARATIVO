# Estructura del Archivo Excel de Proyección

## Formato Requerido

El archivo Excel de proyección debe tener la siguiente estructura **EXACTA**:

### Columnas Requeridas (en este orden):

1. **CLASIFICACION** (primera columna)
   - Nombre exacto: `CLASIFICACION` (puede tener espacios antes/después, pero debe contener la palabra "CLASIFICACION")
   - Contiene el nombre de la clasificación (ej: "Ventas", "Gastos Operacionales", etc.)

2. **TIPO DE MOVIMIENTO** (segunda columna)
   - Nombre exacto: `TIPO DE MOVIMIENTO` (puede tener espacios antes/después)
   - Valores permitidos: **EXACTAMENTE** `INGRESO` o `EGRESO` (en mayúsculas, sin espacios adicionales)

3. **Columnas de Fecha** (resto de columnas)
   - **Formato de nombre de columna**: `mmm-yy` (mes abreviado en español + año de 2 dígitos)
   - Ejemplos válidos:
     - `ene-25` (enero 2025)
     - `feb-25` (febrero 2025)
     - `mar-25` (marzo 2025)
     - `abr-25` (abril 2025)
     - `may-25` (mayo 2025)
     - `jun-25` (junio 2025)
     - `jul-25` (julio 2025)
     - `ago-25` (agosto 2025)
     - `sep-25` o `sept-25` (septiembre 2025)
     - `oct-25` (octubre 2025)
     - `nov-25` (noviembre 2025)
     - `dic-25` (diciembre 2025)

### Estructura de la Tabla:

```
| CLASIFICACION          | TIPO DE MOVIMIENTO | jul-25 | ago-25 | sep-25 | oct-25 | nov-25 | dic-25 |
|------------------------|-------------------|--------|--------|--------|--------|--------|--------|
| Ventas                 | INGRESO           | 100000 | 120000 | 110000 | 130000 | 125000 | 140000 |
| Servicios              | INGRESO           | 50000  | 55000  | 60000  | 65000  | 70000  | 75000  |
| Gastos Operacionales   | EGRESO            | 80000  | 85000  | 90000  | 95000  | 100000 | 105000 |
| Gastos Administrativos | EGRESO            | 30000  | 32000  | 35000  | 38000  | 40000  | 42000  |
```

### Reglas Importantes:

1. **Nombres de columnas de fecha**:
   - ✅ CORRECTO: `jul-25`, `ago-25`, `nov-25`
   - ❌ INCORRECTO: `Jul-25`, `JUL-25`, `julio-25`, `07-25`, `2025-07`, `jul/25`

2. **Valores en TIPO DE MOVIMIENTO**:
   - ✅ CORRECTO: `INGRESO`, `EGRESO`
   - ❌ INCORRECTO: `Ingreso`, `ingreso`, `INGRESOS`, `EGRESOS`, `Abono`, `Cargo`

3. **Valores numéricos**:
   - Los montos deben ser números (pueden tener decimales)
   - Las celdas vacías se interpretan como 0

4. **Primera fila**:
   - La primera fila debe contener los encabezados de columna
   - NO debe haber filas de metadatos antes de los encabezados

### Ejemplo de Archivo Correcto:

```
CLASIFICACION          | TIPO DE MOVIMIENTO | jul-25 | ago-25 | sep-25 | oct-25 | nov-25 | dic-25
Ventas                 | INGRESO           | 100000 | 120000 | 110000 | 130000 | 125000 | 140000
Servicios              | INGRESO           | 50000  | 55000  | 60000  | 65000  | 70000  | 75000
Gastos Operacionales   | EGRESO            | 80000  | 85000  | 90000  | 95000  | 100000 | 105000
Gastos Administrativos | EGRESO            | 30000  | 32000  | 35000  | 38000  | 40000  | 42000
```

### Abreviaciones de Meses Válidas:

- `ene` o `jan` → Enero
- `feb` → Febrero
- `mar` → Marzo
- `abr` o `apr` → Abril
- `may` → Mayo
- `jun` → Junio
- `jul` → Julio
- `ago` o `aug` → Agosto
- `sep` o `sept` → Septiembre
- `oct` → Octubre
- `nov` → Noviembre
- `dic` o `dec` → Diciembre

### Año:

- Formato: 2 dígitos (ej: `25` = 2025, `24` = 2024)
- El código asume años 20XX automáticamente

## Solución de Problemas

Si el filtro no funciona:

1. **Verifica los nombres de las columnas de fecha**:
   - Deben estar en minúsculas
   - Formato: `mes-año` (ej: `nov-25`)
   - Sin espacios antes o después del guión

2. **Verifica los valores de TIPO DE MOVIMIENTO**:
   - Deben ser exactamente `INGRESO` o `EGRESO`
   - Sin espacios adicionales
   - En mayúsculas

3. **Revisa el sidebar de debug**:
   - Busca el mensaje "🔍 Fechas originales"
   - Verifica que las fechas se muestren correctamente
   - Si aparecen como `nan` o valores extraños, el formato de las columnas es incorrecto








