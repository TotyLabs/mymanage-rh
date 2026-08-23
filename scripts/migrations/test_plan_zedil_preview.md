# Plan de pruebas — preview de migración ZEDIL

## Objetivo

Validar que el preview de migración sea seguro, idempotente y conservador sin modificar la base de datos.

## Casos de prueba

1. Ejecución inicial
   - Ejecutar el script sin cambios.
   - Verificar que genera el JSON en [scripts/migrations/preview_zedil_bulk_import.json](scripts/migrations/preview_zedil_bulk_import.json).
   - Confirmar que no se crean empleados, usuarios ni firmas.

2. Duplicados por DNI
   - Simular una fila con DNI ya existente en ZEDIL.
   - Verificar que la acción planificada sea existing_keep o existing_noop, no creación.

3. Duplicados por email
   - Simular un registro con un email ya usado por otro usuario del mismo org.
   - Verificar que el script marque el conflicto y evite una creación no controlada.

4. Firmas ambiguas
   - Simular nombres de persona con coincidencias múltiples.
   - Verificar que el estado sea FIRMA_AMBIGUA y no se asigne firma automáticamente.

5. Firmas faltantes
   - Simular un nombre sin coincidencia de firma.
   - Verificar que el estado sea FIRMA_FALTANTE y no se invente una asignación.

6. Idempotencia
   - Ejecutar dos veces el script con el mismo Excel.
   - Verificar que el resumen sea estable y que no haya cambios en la base.

7. Rollback
   - Si más adelante se habilita una ejecución real, probar un lote parcial con un fallo.
   - Verificar que el lote completo no deje cambios parciales.

## Criterios de aceptación

- El script no escribe en base de datos.
- El reporte produce un resumen estable.
- Los conflictos se anotan en el JSON y en el markdown.
- La estrategia de firma es conservadora y evita falsos positivos.
