# Configuraciones de Clasificadores por Cliente

Este directorio contiene las configuraciones de clasificadores para diferentes clientes.

## Estructura de Archivos

Cada cliente debe tener su propio archivo JSON con el siguiente formato de nombre:
- `clasificadores_[nombre_cliente].json`

Ejemplos:
- `clasificadores_cliente_a.json`
- `clasificadores_empresa_xyz.json`
- `clasificadores_sucursal_norte.json`

## Ubicación de Archivos

El sistema busca configuraciones en dos lugares:

1. **Directorio `configs/`** (recomendado): Para organizar configuraciones por cliente
   - Ejemplo: `configs/clasificadores_cliente_a.json`

2. **Directorio raíz**: Para configuraciones generales o por defecto
   - Ejemplo: `clasificadores.json` (configuración por defecto)
   - Ejemplo: `clasificadores_empresa.json`

## Estructura del JSON

Cada archivo debe seguir esta estructura:

```json
{
  "clasificadores": {
    "abonos": [
      {
        "nombre": "NOMBRE DE LA CLASIFICACION",
        "palabras_clave": ["PALABRA1", "PALABRA2"],
        "tipo": "contiene_cualquiera",
        "excluir": ["EXCEPCION"]  // Opcional
      }
    ],
    "cargos": [
      {
        "nombre": "NOMBRE DE LA CLASIFICACION",
        "palabras_clave": ["PALABRA1", "PALABRA2"],
        "tipo": "contiene_cualquiera"
      }
    ]
  },
  "clasificacion_default": "NO CLASIFICADO"
}
```

## Tipos de Coincidencia

- **`contiene_cualquiera`**: Coincide si al menos una palabra clave está presente
- **`contiene_exacto`**: Coincide solo si todas las palabras clave están presentes

## Uso en la Aplicación

1. Coloca tu archivo JSON en el directorio `configs/` o en la raíz
2. Inicia la aplicación Streamlit
3. En la barra lateral, selecciona el cliente/configuración deseada
4. La aplicación cargará automáticamente las reglas de clasificación correspondientes


