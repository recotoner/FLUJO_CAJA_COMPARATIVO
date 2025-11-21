# 📊 Instrucciones para Configuración desde Excel

## Estructura del Archivo Excel

El sistema soporta dos formatos de Excel para configurar clasificadores:

### Formato 1: Hojas Separadas (Recomendado)

Crea un archivo Excel con **dos hojas**:

1. **Hoja "ABONOS"**: Para clasificaciones de ingresos (transacciones con ABONOS > 0)
2. **Hoja "CARGOS"**: Para clasificaciones de egresos (transacciones con ABONOS ≤ 0)

#### Columnas Requeridas:

| Columna | Descripción | Ejemplo |
|---------|-------------|---------|
| **Nombre** | Nombre de la clasificación | `PROVEEDORES NACIONALES` |
| **Palabras Clave** | Palabras a buscar (separadas por `\|`) | `PROVEEDORES\|SERVIPAG\|AGUA` |
| **Tipo Coincidencia** | `contiene_cualquiera` o `contiene_exacto` | `contiene_cualquiera` |
| **Excluir** | Excepciones (opcional, separadas por `\|`) | `TRASPASO DE: JORGE` |

### Formato 2: Hoja Única con Columna "Tipo"

Si prefieres una sola hoja, agrega una columna **"Tipo"** con valores:
- `ABONO` para ingresos
- `CARGO` para egresos

## Ejemplo de Estructura

### Hoja ABONOS:
```
| Nombre                                          | Palabras Clave                                    | Tipo Coincidencia    | Excluir |
|------------------------------------------------|---------------------------------------------------|----------------------|---------|
| 1.01.05.01 - Facturas por cobrar Nacional     | FACTURA\|COBRAR\|FLUJO\|PAGO\|DEPOSITO            | contiene_cualquiera  |         |
| PRESTAMO RECIBIDO DE SOCIO                     | TRASPASO DE: JORGE ALBERTO VICUNA GREENE          | contiene_exacto       |         |
```

### Hoja CARGOS:
```
| Nombre                    | Palabras Clave              | Tipo Coincidencia    | Excluir |
|---------------------------|-----------------------------|----------------------|---------|
| PROVEEDORES NACIONALES    | PROVEEDORES\|SERVIPAG\|AGUA  | contiene_cualquiera |         |
| REMUNERACIONES POR PAGAR  | SUELDOS\|REMUNERACION        | contiene_cualquiera  |         |
| IMPUESTOS                 | PAGO EN SII                  | contiene_exacto      |         |
```

## Separadores de Palabras Clave

Puedes usar cualquiera de estos separadores:
- `|` (pipe) - **Recomendado**
- `;` (punto y coma)
- `,` (coma)

Ejemplo: `FACTURA|COBRAR|FLUJO` o `FACTURA;COBRAR;FLUJO` o `FACTURA,COBRAR,FLUJO`

## Tipos de Coincidencia

### `contiene_cualquiera`
- Coincide si **al menos una** palabra clave está presente en el texto
- Ejemplo: Si palabras clave son `SUELDOS|REMUNERACION`, coincide con textos que contengan "SUELDOS" **o** "REMUNERACION"

### `contiene_exacto`
- Coincide solo si **todas** las palabras clave están presentes
- Ejemplo: Si palabras clave son `PAGO EN SII`, solo coincide con textos que contengan exactamente "PAGO EN SII"

## Campo Excluir (Opcional)

Permite excluir ciertos patrones antes de aplicar la regla.

Ejemplo:
- **Palabras Clave**: `TRASPASO DE`
- **Excluir**: `TRASPASO DE: JORGE ALBERTO VICUNA GREENE|TRASPASO DE:RECICLAJES`

Esto significa: "Coincide con 'TRASPASO DE' pero NO si también contiene alguna de las exclusiones"

## Orden de Evaluación

⚠️ **IMPORTANTE**: Las reglas se evalúan en el orden que aparecen en el Excel (de arriba hacia abajo). 
La **primera coincidencia** es la que se aplica.

**Recomendación**: Coloca las reglas más específicas primero y las más generales al final.

## Nombre del Archivo

Para que el sistema detecte tu archivo, usa el formato:
- `clasificadores_[nombre_cliente].xlsx`
- Ejemplo: `clasificadores_cliente_a.xlsx`

Colócalo en:
- Directorio `configs/` (recomendado)
- O en el directorio raíz del proyecto

## Template de Ejemplo

Puedes usar el archivo `clasificadores_template.xlsx` como base y modificarlo según tus necesidades.


