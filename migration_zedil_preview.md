# Preview de migración masiva — ZEDIL S.A.

## Resumen ejecutivo

- Archivo analizado: [fichaempleadozed123.xls](fichaempleadozed123.xls)
- Organización detectada: ZEDIL S.A.
- ID interno de organización: 9270b7bb-b720-486f-8e2f-953c462b87ca
- Modo: preview-only, sin escritura en base de datos
- Cambios ejecutados: 0

## Datos del Excel

- Total de filas válidas detectadas por el parser del proyecto: 134
- Total esperado de empleados para la migración: 134

## Estado actual de la base para ZEDIL S.A.

- Empleados existentes en la organización: 134
- Usuarios existentes en la organización: 0
- Estado actual de los empleados: pre_registered (134)
- Estado actual de los usuarios: no asociados aún

## Plan de acción propuesto (sin ejecución)

1. Resolver y validar la organización ZEDIL S.A.
2. Leer y validar el Excel con el parser de legajos del proyecto.
3. Detectar conflictos y duplicados sin modificar la base.
4. Para cada empleado existente en ZEDIL, planificar la creación de un usuario de acceso cuando aún no exista.
5. Crear la cuenta de forma administrativa, respetando el hashing bcrypt del sistema.
6. Marcar la cuenta como verificada por medios administrativos, siguiendo los campos reales del sistema.
7. Permitir la transición automática de pre_registered a active mediante el flujo del registro correcto.
8. Asignar firma solo cuando exista un match válido y explícito.

## Organización y contexto real del proyecto

### Modelos y flujos inspeccionados

- [models/tables.py](models/tables.py): define las tablas users, employees, organizations, user_signatures, company_signers.
- [models/enums.py](models/enums.py): define EmployeeStatus.pre_registered, EmployeeStatus.active, UserStatus.pending_verification, UserStatus.active.
- [api/auth.py](api/auth.py): el registro de empleado actual actualiza employees.status a active y crea users con password_hash + user_status pending_verification.
- [api/employees.py](api/employees.py): el endpoint de bulk import crea empleados con status pre_registered o pending_verification y es idempotente por DNI.
- [payroll_core.py](payroll_core.py): usa bcrypt para hash_password/verify_password y protege logs con masking de PII.
- [services/legajo/form_parser.py](services/legajo/form_parser.py): parser real que detecta bloques por empleado y extrae nombres, DNI, legajo, email y otros campos desde el archivo .xls.
- [services/legajo/normalizer.py](services/legajo/normalizer.py): normaliza columnas y valores del Excel.
- [services/legajo/validator.py](services/legajo/validator.py): valida DNI, CUIL y emails.
- [api/signatures.py](api/signatures.py): persiste firmas en user_signatures con signature_path y signature_hash.

## Previsualización de resultados

### Resumen esperado

- Total Excel: 134
- Aptos para migrar: 134
- Bloqueados: 0
- Empleados a crear: 0
- Empleados existentes: 134
- Usuarios a crear: 134
- Usuarios existentes: 0
- Firmas a asignar: aproximadamente 21 coincidencias exactas/normalizadas detectadas en el directorio de firmas
- Firmas faltantes: el resto
- Firmas ambiguas: 0 en la comparación conservadora aplicada
- Firmas huérfanas: por determinar con la comparación exacta/normalizada
- Cambios ejecutados: 0

## Firmas detectadas

- Directorio inspeccionado: [storage/signatures/FIRMAS ZEDIL S.A./source](storage/signatures/FIRMAS%20ZEDIL%20S.A./source)
- Archivos de firma detectados: 53
- Coincidencias exactas/normalizadas detectadas contra el Excel: 21
- Casos sin firma: el resto
- Estrategia: no asignar firma si el match no es claro; mantener la migración de usuarios/empleados aunque falte firma.

## Riesgos y advertencias

- El archivo presenta bloques de forma con nombres incompletos o vacíos para algunas filas; el parser identifica 134 registros válidos pero algunos bloques pueden ser ambiguos por el formato del Excel.
- El email aparece como campo opcional y algunos registros podrían no tenerlo o tenerlo inválido.
- El sistema usa un unique constraint en users por (email, organization_id), por lo que la previsualización debe tratar duplicados por email con cuidado.
- La migración no debe crear usuarios si el empleado no quedó asociado previamente como pre_registered a ZEDIL S.A.

## Estrategia de verificación y credenciales

- Se utilizará la lógica existente de bcrypt en [payroll_core.py](payroll_core.py).
- No se imprimirán contraseñas ni hashes en reporte ni logs.
- La estrategia compatible con el flujo actual es crear una cuenta administrativa con contraseña temporal segura y obligación de cambio, o bien una cuenta verificada administrativamente sin exponerla directamente.
- La verificación real del sistema se representa por los campos user_status/is_verified en users y el estado del empleado en employees, siguiendo el mismo patrón del flujo de registro de [api/auth.py](api/auth.py).

## Estrategia de rollback

- Mantener todo el proceso en una sola transacción o en lotes transaccionales recuperables.
- Si falla una fila o el lote completo, hacer rollback del lote y dejar el reporte visible.
- No ejecutar la migración real en esta etapa.

## Confirmación explícita

- No se ejecutó ninguna inserción, actualización, borrado ni cambio de archivo en esta etapa.
