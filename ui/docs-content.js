/**
 * Embedded Document Content
 * Pre-rendered HTML for authorized documents.
 * Hardened: No raw markdown or fetch calls.
 */

export const docsContent = {
  'tos': {
    id: 'tos',
    title: 'Términos y Condiciones',
    lastUpdated: '2026-04-27',
    category: 'Legal',
    html: `
      <h1>Términos y Condiciones - MyManageRH</h1>
      
      <h2>1. Partes</h2>
      <p>Estos Términos regulan el uso de MyManageRH, servicio SaaS B2B operado por MyManageRH, por parte de la organización cliente, sus administradores, representantes autorizados y empleados usuarios.</p>
      
      <h2>2. Objeto del servicio</h2>
      <p>MyManageRH permite gestionar empleados, cargar recibos de sueldo, solicitar y registrar firmas digitales o electrónicas, conservar evidencia técnica y consultar auditoría asociada a recibos y documentos laborales.</p>
      <p>El servicio no realiza liquidación salarial salvo que se contrate y documente un módulo específico. El cliente conserva responsabilidad por exactitud de datos laborales, salariales y personales ingresados.</p>
      
      <h2>3. Uso permitido</h2>
      <p>El cliente podrá usar el servicio para:</p>
      <ul>
        <li>Administrar organizaciones, empleados y usuarios autorizados.</li>
        <li>Cargar recibos y documentos laborales.</li>
        <li>Gestionar firmas del empleador y empleado.</li>
        <li>Consultar historial, evidencia y estados.</li>
        <li>Integrar sistemas externos mediante API o webhooks aprobados.</li>
      </ul>
      
      <h2>4. Uso prohibido</h2>
      <p>Queda prohibido:</p>
      <ul>
        <li>Cargar datos falsos, ilícitos o no autorizados.</li>
        <li>Intentar acceder a datos de otra organización.</li>
        <li>Compartir credenciales o tokens.</li>
        <li>Manipular recibos firmados fuera del sistema.</li>
        <li>Interferir con auditoría, logs o evidencia.</li>
        <li>Subir malware, archivos maliciosos o contenido no relacionado con payroll.</li>
        <li>Usar el servicio en violación de las leyes de la República Argentina.</li>
      </ul>
      
      <h2>5. Obligaciones del usuario y del cliente</h2>
      <p>El cliente debe:</p>
      <ul>
        <li>Mantener datos correctos de empleados and recibos.</li>
        <li>Administrar altas, bajas y permisos de usuarios.</li>
        <li>Validar identidad de empleados según su política interna.</li>
        <li>Obtener consentimientos o bases legales requeridas.</li>
        <li>Definir retención y finalidad del tratamiento.</li>
        <li>Notificar a MyManageRH incidentes o usos no autorizados.</li>
      </ul>
      
      <h2>6. Responsabilidad por datos ingresados</h2>
      <p>MyManageRH procesa datos según instrucciones del cliente en el marco del servicio contratado. El cliente es responsable por la calidad, legalidad, autorización y exactitud de los datos ingresados, incluyendo DNI, CUIL, salario, email, legajo y recibos.</p>
      
      <h2>7. Firma digital y evidencia</h2>
      <p>MyManageRH genera evidencia técnica asociada a firmas, como timestamps, IP, user-agent, hashes, eventos, sellos QR y metadata criptográfica cuando aplica.</p>
      <p>La validez legal de una firma o evidencia depende de la legislación de la República Argentina (Ley 25.506 de Firma Digital y Ley 25.326 de Protección de Datos Personales), contrato aplicable, consentimiento, configuración del sistema y políticas del cliente. MyManageRH no afirma validez legal absoluta sin revisión profesional.</p>
      
      <h2>8. Disponibilidad</h2>
      <p>MyManageRH procurará mantener una disponibilidad mensual objetivo del 99,5 %, salvo interrupciones derivadas de mantenimiento programado, fuerza mayor, fallas de proveedores externos, incidentes de infraestructura, requerimientos legales o circunstancias fuera de su control razonable. La disponibilidad podrá variar según el plan contratado o acuerdos de nivel de servicio (SLA) específicos, cuando existan.</p>
      
      <h2>9. Pagos</h2>
      <p>Si aplica, los pagos, impuestos, moneda, facturación, mora y reajustes se regirán por la orden comercial o contrato SaaS correspondiente.</p>
      
      <h2>10. Propiedad intelectual</h2>
      <p>MyManageRH conserva titularidad sobre software, documentación, know-how, arquitectura, marca y materiales propios de MyManageRH, salvo acuerdo escrito en contrario.</p>
      <p>El cliente conserva titularidad sobre sus datos, recibos, logos, documentos y contenido cargado.</p>
      
      <h2>11. Confidencialidad</h2>
      <p>Las partes deberán proteger información confidencial, incluyendo datos de empleados, recibos, arquitectura, credenciales, documentación no pública y términos comerciales.</p>
      
      <h2>12. Suspensión del servicio</h2>
      <p>MyManageRH podrá suspender total o parcialmente el acceso cuando exista riesgo de seguridad, uso no autorizado, incumplimiento material, falta de pago si aplica, requerimiento legal o afectación a otros clientes.</p>
      
      <h2>13. Limitación de responsabilidad</h2>
      <p>La responsabilidad de MyManageRH se limitará a lo establecido en el contrato aplicable y en la legislación vigente de la República Argentina. MyManageRH no garantiza la disponibilidad ininterrumpida del servicio, la ausencia absoluta de errores ni la validez jurídica de firmas o documentos fuera de las condiciones previstas por la normativa aplicable. Asimismo, MyManageRH no será responsable por datos incorrectos, incompletos o ilícitos cargados por el cliente, configuraciones realizadas por éste o decisiones laborales adoptadas utilizando la información procesada por la plataforma.</p>
      
      <h2>14. Terminación</h2>
      <p>La terminación, exportación, retención y eliminación de datos se regirán por contrato, DPA y políticas de retención: Recibos y evidencia de firma (5 a 10 años según normativa laboral), Logs de auditoría (mínimo 1 año).</p>
      
      <h2>15. Jurisdicción</h2>
      <p>Jurisdicción y ley aplicable: Ciudad Autónoma de Buenos Aires, República Argentina.</p>
    `
  },
  'privacy': {
    id: 'privacy',
    title: 'Política de Privacidad',
    lastUpdated: '2026-04-27',
    category: 'Legal',
    html: `
      <h1>Política de Privacidad - MyManageRH</h1>
      
      <h2>1. Responsable y servicio</h2>
      <p>MyManageRH es un SaaS B2B operado por MyManageRH para gestión de recibos de sueldo, firma digital, evidencia y auditoría. En la mayoría de los escenarios B2B, la organización cliente determina finalidades y medios esenciales del tratamiento, y MyManageRH procesa datos siguiendo instrucciones del cliente.</p>
      <p>Definiciones finales sujetas a las leyes de la República Argentina (Ley 25.326) y al DPA aplicable.</p>
      
      <h2>2. Datos recolectados</h2>
      <p>El sistema puede tratar:</p>
      <ul>
        <li>Nombre y apellido.</li>
        <li>DNI, CUIL/CUIT.</li>
        <li>Email, Teléfono, Dirección.</li>
        <li>Datos de legajo, Datos bancarios (CBU).</li>
        <li>Recibos de sueldo y salarios.</li>
        <li>Firmas visuales y Evidencia de firma.</li>
        <li>IP, user-agent, timestamps y actividad.</li>
        <li>Credenciales hasheadas y sesiones hasheadas.</li>
      </ul>
      
      <h2>3. Finalidad del tratamiento</h2>
      <p>Los datos se tratan para:</p>
      <ul>
        <li>Administrar empleados y usuarios.</li>
        <li>Cargar, asociar, firmar y consultar recibos.</li>
        <li>Verificar identidad en flujos de firma.</li>
        <li>Generar evidencia técnica y auditoría.</li>
        <li>Enviar emails, OTP o notificaciones.</li>
        <li>Operar webhooks e integraciones.</li>
        <li>Prevenir fraude, abuso y accesos no autorizados.</li>
      </ul>
      
      <h2>4. Base legal</h2>
      <p>Base legal: cumplimiento de obligaciones legales laborales, ejecución de contrato de trabajo y consentimiento del titular cuando corresponda.</p>
      
      <h2>5. Protección de datos</h2>
      <h3>Seguridad de acceso</h3>
      <ul>
        <li>Autenticación y autorización basada en roles.</li>
        <li>Sesiones y tokens almacenados de forma segura.</li>
        <li>Scoping por organización.</li>
      </ul>
      <h3>Seguridad de la información</h3>
      <ul>
        <li>Hashes SHA-256 para integridad documental.</li>
        <li>Redacción de datos personales sensibles en logs cuando corresponda.</li>
        <li>TLS 1.2 o superior para comunicaciones en producción.</li>
        <li>Cifrado de datos en reposo mediante servicios compatibles con AWS KMS cuando corresponda.</li>
      </ul>
      
      <h2>6. Acceso restringido</h2>
      <p>El acceso a datos queda restringido a usuarios autorizados por organización, personal operativo autorizado de MyManageRH y subprocesadores necesarios para prestar el servicio.</p>
      
      <h2>7. Retención</h2>
      <p>Retención: Recibos y evidencia (5-10 años), Logs (1 año).</p>
      
      <h2>8. Derechos ARCO</h2>
      <p>Conforme a la Ley N.º 25.326, los titulares de los datos podrán ejercer los derechos de acceso, rectificación, actualización y supresión cuando corresponda. Cuando la organización cliente actúe como responsable del tratamiento, MyManageRH remitirá la solicitud al cliente para su correspondiente gestión. Las consultas relacionadas con privacidad podrán enviarse a privacy@mymanagerh.com.</p>
      
      <h2>9. Subprocesadores</h2>
      <p>Subprocesadores: Amazon Web Services (Infra), Twilio (SMS), Google/SMTP (Email).</p>
      
      <h2>10. Transferencias internacionales</h2>
      <p>Transferencias internacionales: AWS (Regiones US-East o similares), protegidas por cláusulas contractuales estándar y medidas técnicas de cifrado (KMS).</p>
      
      <h2>11. Cookies y tecnologías similares</h2>
      <p>MyManageRH utiliza cookies y tecnologías similares necesarias para el funcionamiento del servicio, autenticación de usuarios, mantenimiento de sesiones y mejora de la experiencia de uso. En caso de incorporarse cookies analíticas o publicitarias, se informará oportunamente mediante la política correspondiente.</p>
      
      <h2>12. Incidentes</h2>
      <p>Ante incidentes, MyManageRH activará su procedimiento interno, preservará evidencia y comunicará al cliente (< 72 horas).</p>
      
      <h2>13. Contacto</h2>
      <p>Contacto de privacidad: privacy@mymanagerh.com</p>
    `
  }
};
