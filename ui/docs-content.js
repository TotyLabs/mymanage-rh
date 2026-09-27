/**
 * Public legal documents rendered by the documentation page.
 * Keep this HTML aligned with docs/legal/TOS.md and docs/legal/PRIVACY.md.
 */
const renderSections = (sections) => sections.map(([id, title, body]) => `
  <section aria-labelledby="${id}">
    <h2 id="${id}">${title}</h2>
    ${body}
  </section>
`).join('');

export const docsContent = {
  tos: {
    id: 'tos',
    title: 'Términos y Condiciones de MyManageRH',
    version: '1.0',
    lastUpdated: '2026-09-27',
    effectiveDate: '[COMPLETAR: fecha de entrada en vigencia]',
    category: 'Legal',
    html: `
      ${renderSections([
        ['tos-01-introduccion', '1. Introducción y aceptación', `
          <p>Estos Términos y Condiciones (los <strong>Términos</strong>) regulan el acceso y uso de MyManageRH. El Servicio está dirigido principalmente a organizaciones que administran información laboral y a las personas que esas organizaciones autorizan a utilizarlo.</p>
          <p>La persona que acepta en nombre de una organización declara tener facultades suficientes para obligarla. La aceptación puede realizarse mediante un mecanismo electrónico de la Plataforma; la fecha, versión y evento de aceptación podrán quedar registrados. Cada Usuario también debe respetar las reglas de uso que le sean aplicables. El uso de un documento o una firma no implica, por sí solo, que el Usuario acepte obligaciones laborales distintas de las expresamente informadas.</p>
          <p>Los Términos se complementan, según corresponda, con la orden comercial, el contrato SaaS, el acuerdo de tratamiento de datos (DPA) y la <a href="/privacy">Política de Privacidad de MyManageRH</a>. Si existe una contradicción, prevalecerá el documento específico firmado para la contratación respecto de su objeto, salvo normas imperativas. Las modificaciones se rigen por la sección 29.</p>
          <p>Quien no tenga capacidad legal para aceptar estos Términos no debe crear una Cuenta ni aceptar en nombre de otra persona u organización sin autorización.</p>
        `],
        ['tos-02-identificacion', '2. Identificación de MyManageRH', `
          <p>MyManageRH es el proveedor y nombre bajo el que se ofrece el Servicio. Los datos de la persona jurídica que lo opera deben completarse antes de publicar:</p>
          <ul>
            <li><strong>Titular y operador legal:</strong> [COMPLETAR: razón social y tipo societario responsable de MyManageRH].</li>
            <li><strong>CUIT:</strong> [COMPLETAR: CUIT].</li>
            <li><strong>Domicilio legal:</strong> [COMPLETAR: domicilio constituido].</li>
            <li><strong>Contacto general y soporte:</strong> [COMPLETAR: correo o formulario operativo].</li>
            <li><strong>Contacto legal:</strong> [COMPLETAR: canal para notificaciones legales].</li>
          </ul>
        `],
        ['tos-03-definiciones', '3. Definiciones', `
          <ul>
            <li><strong>MyManageRH o Proveedor:</strong> el titular u operador identificado en la sección 2.</li>
            <li><strong>Plataforma:</strong> las aplicaciones web, API y componentes que permiten acceder al Servicio.</li>
            <li><strong>Servicio:</strong> las funciones de gestión de Recursos Humanos y documentos habilitadas para el Cliente.</li>
            <li><strong>Cliente:</strong> la persona jurídica u organización que contrata o habilita el uso de MyManageRH.</li>
            <li><strong>Organización:</strong> el espacio de trabajo y los datos administrados por un Cliente dentro de la Plataforma.</li>
            <li><strong>Administrador:</strong> Usuario al que el Cliente asigna facultades de configuración y administración de una Organización.</li>
            <li><strong>Usuario:</strong> toda persona autorizada por el Cliente para acceder a la Plataforma, incluidos administradores y trabajadores.</li>
            <li><strong>Trabajador o Empleado:</strong> persona cuyos datos laborales son administrados por el Cliente mediante el Servicio; puede o no tener una Cuenta.</li>
            <li><strong>Cuenta:</strong> credenciales y datos que habilitan el acceso de un Usuario.</li>
            <li><strong>Datos del Cliente:</strong> datos, archivos, instrucciones y contenidos que el Cliente o sus Usuarios cargan, generan o administran mediante el Servicio.</li>
            <li><strong>Documento:</strong> archivo o registro laboral, incluidos recibos, legajos y documentos que se carguen o generen.</li>
            <li><strong>Legajo:</strong> conjunto de datos y documentos que el Cliente asocia a un Trabajador.</li>
            <li><strong>Recibo:</strong> documento relativo a remuneraciones u otros conceptos laborales que el Cliente carga o genera.</li>
            <li><strong>Firma electrónica y Firma digital:</strong> tienen los significados y alcances explicados en la sección 12.</li>
            <li><strong>Credenciales:</strong> contraseña, token, código OTP u otro medio de autenticación.</li>
            <li><strong>OTP:</strong> código temporal de un solo uso para verificar una acción o acceso.</li>
            <li><strong>Suscripción o Plan:</strong> alcance comercial contratado por el Cliente, si corresponde.</li>
          </ul>
        `],
        ['tos-04-servicio', '4. Descripción del Servicio', `
          <p>MyManageRH es una plataforma SaaS que puede ofrecer administración de organizaciones, Usuarios y Empleados; legajos; carga, generación, almacenamiento, consulta y descarga de documentos; recibos; flujos de firma electrónica; OTP; notificaciones; roles y permisos; registros de actividad; gestión documental; importación y exportación; integraciones; y modelos o plantillas laborales.</p>
          <p>Las funciones disponibles dependen del Plan, la configuración, las integraciones habilitadas y el contrato del Cliente. MyManageRH no liquida salarios ni determina condiciones laborales salvo que una función específica se ofrezca expresamente por contrato. El Cliente debe verificar el alcance antes de utilizar una función para una obligación laboral.</p>
        `],
        ['tos-05-cuentas', '5. Registro y Cuentas', `
          <p>El Cliente y sus Usuarios deben proporcionar información correcta y mantenerla actualizada. El Cliente determina quién puede crear Cuentas y debe solicitar la baja o revocación de accesos que ya no correspondan.</p>
          <p>Cada Usuario debe proteger sus Credenciales, no compartir contraseñas ni OTP y utilizar los mecanismos de recuperación solo para su propia Cuenta. Un OTP es personal, temporal y no debe reenviarse ni incluirse en documentos o comunicaciones públicas.</p>
          <p>El Cliente y el Usuario deben avisar al canal de soporte indicado en la sección 33 ante una pérdida de Credenciales, sospecha de acceso no autorizado o error de identidad. MyManageRH podrá solicitar verificaciones razonables antes de recuperar una Cuenta. El Cliente es responsable de las instrucciones de alta, baja y recuperación que emita a través de sus Administradores.</p>
        `],
        ['tos-06-organizaciones', '6. Organizaciones, Administradores y permisos', `
          <p>Quien crea o configura una Organización declara estar autorizado para actuar por el Cliente. El Cliente designa Administradores, define roles y permisos, revisa periódicamente esos permisos y mantiene actualizado el listado de personas autorizadas.</p>
          <p>Los Administradores actúan bajo responsabilidad del Cliente. El Cliente debe retirar sus permisos cuando cambien sus funciones o termine su relación con la Organización. MyManageRH podrá pedir confirmación de autoridad cuando sea razonable para proteger la Organización o a sus Usuarios.</p>
        `],
        ['tos-07-obligaciones-cliente', '7. Obligaciones del Cliente', `
          <p>El Cliente debe contar con una base jurídica válida y las autorizaciones necesarias para cargar, consultar y tratar los Datos del Cliente; informar a Trabajadores y otros titulares cuando corresponda; asegurar que la información sea pertinente, correcta y actualizada; y cumplir sus obligaciones laborales, previsionales, fiscales y de protección de datos.</p>
          <p>También debe revisar recibos, documentos, modelos, destinatarios y flujos antes de publicarlos o pedir una firma; administrar accesos; validar la identidad del firmante según su proceso; conservar originales y respaldos que la normativa requiera; usar el Servicio legítimamente; y notificar incidentes o instrucciones que puedan afectar la seguridad o derechos de terceros.</p>
          <p>El Servicio no traslada a MyManageRH la calidad de empleador ni las obligaciones que corresponden al Cliente.</p>
        `],
        ['tos-08-obligaciones-usuarios', '8. Obligaciones de los Usuarios', `
          <p>Los Usuarios deben utilizar la Plataforma únicamente para fines autorizados, proteger sus Credenciales y comprobar el Documento y la acción antes de confirmar una firma o envío. No deben suplantar a otra persona, facilitar un OTP a terceros ni utilizar una Cuenta ajena.</p>
          <p>Todo Usuario debe reportar accesos, solicitudes de firma, documentos o notificaciones que no reconozca. El uso de una Cuenta no sustituye las políticas internas ni las instrucciones válidas del Cliente.</p>
        `],
        ['tos-09-usos-prohibidos', '9. Usos prohibidos', `
          <p>No se permite acceder o intentar acceder a una Organización, Cuenta, Documento, API o sistema sin autorización; evadir controles; interferir con registros; alterar fraudulentamente documentos o evidencia; introducir malware; realizar ataques o sondeos no autorizados; degradar el Servicio; abusar de API o extraer datos mediante scraping no autorizado; cargar información ilegal, engañosa, excesiva o no autorizada; falsificar identidad, firma o consentimiento; revender o sublicenciar el Servicio; ni utilizar MyManageRH para vulnerar derechos de terceros.</p>
          <p>La ingeniería inversa, descompilación o elusión de medidas técnicas queda prohibida salvo en la medida en que una norma imperativa no permita restringirla.</p>
        `],
        ['tos-10-datos-cliente', '10. Datos y contenido del Cliente', `
          <p>Los Datos del Cliente no pasan a ser propiedad de MyManageRH. El Cliente conserva los derechos que tenga sobre esos datos y es responsable de su origen, exactitud, legalidad, base de tratamiento y contenido.</p>
          <p>El Cliente concede a MyManageRH únicamente la autorización limitada, no exclusiva y vigente durante la prestación del Servicio para alojar, reproducir, transmitir, organizar y procesar los Datos del Cliente en la medida técnica necesaria para operar las funciones contratadas, cumplir instrucciones documentadas y proteger el Servicio. Esta autorización no habilita usos publicitarios, venta de datos ni entrenamiento de modelos con Datos del Cliente.</p>
          <p>El Cliente puede solicitar acceso, corrección, exportación o eliminación mediante las funciones disponibles o el canal de soporte. Formato, alcance y plazo de exportación: [COMPLETAR: procedimiento de exportación]. La eliminación puede estar sujeta a obligaciones legales, instrucciones, litigios y copias de respaldo según la Política de Privacidad y el DPA.</p>
        `],
        ['tos-11-documentos', '11. Documentos y gestión documental', `
          <p>El Cliente es responsable del contenido, versión, destinatarios, período, legibilidad y exactitud de los Documentos. Debe revisarlos antes de cargarlos, generarlos, distribuirlos o pedir una firma.</p>
          <p>La Plataforma puede conservar archivos, metadatos, versiones, estados, hashes u otros registros para operar la gestión documental y la trazabilidad. Estas funciones no garantizan por sí solas la exactitud jurídica del Documento, que no haya sido modificado fuera de MyManageRH ni su admisibilidad en un caso concreto. El Cliente debe mantener los originales o copias que sus obligaciones requieran.</p>
        `],
        ['tos-12-firmas', '12. Firma electrónica y firma digital', `
          <p>Una <strong>firma electrónica</strong> es un conjunto de datos electrónicos asociado a un documento o acto que permite identificar o expresar la voluntad de una persona, pero que no reúne necesariamente los requisitos legales de una firma digital. Conforme a la Ley 25.506, su valor y prueba se analizan según el caso y la normativa aplicable.</p>
          <p>Una <strong>firma digital</strong> tiene el alcance legal previsto por la Ley 25.506 y requiere que se cumplan sus condiciones, incluidos los elementos criptográficos y certificados correspondientes. No toda imagen de firma, aceptación en pantalla, OTP, casilla de verificación o registro de autenticación constituye una firma digital.</p>
          <p>MyManageRH puede registrar autenticación, OTP, confirmación de acciones, identidad declarada o verificada, fecha y hora, Documento, hash, dirección IP, agente de usuario u otros eventos técnicos cuando la función y configuración los generen. Esos elementos pueden aportar evidencia de un flujo de firma electrónica, pero no garantizan identidad real, intención, validez laboral o calificación jurídica del acto.</p>
          <p>Solo debe describirse un Documento como firmado digitalmente cuando el mecanismo concreto satisfaga la Ley 25.506 y ello pueda verificarse en el Documento. La disponibilidad de certificados, firmas visuales o funciones criptográficas no implica que todos los documentos utilicen firma digital. El Cliente determina el mecanismo adecuado, informa a los firmantes y revisa el resultado.</p>
        `],
        ['tos-13-evidencia', '13. Registros y evidencia electrónica', `
          <p>Para operar el Servicio, MyManageRH puede generar registros de autenticación, actividad, cambios documentales, solicitudes de firma, verificaciones, timestamps, hashes, direcciones IP y datos técnicos del navegador o dispositivo, según la función utilizada.</p>
          <p>Los registros sirven para seguridad, soporte, auditoría y reconstrucción técnica de eventos. Su exactitud, integridad, disponibilidad, plazo de conservación y valor probatorio dependen del sistema, la configuración, las fuentes de tiempo, las medidas aplicadas y la legislación. No se garantiza que un registro pruebe por sí solo todos los elementos jurídicos de una relación laboral o de una firma.</p>
        `],
        ['tos-14-planes', '14. Planes y suscripciones', `
          <p>El Plan y la orden comercial determinan alcance, límites de uso, cantidad de Usuarios o Empleados, almacenamiento, funciones, integraciones y soporte. Estos Términos no fijan precios ni límites generales. La disponibilidad de una función puede variar según el Plan o la configuración.</p>
          <p>Las modificaciones de Plan, ampliaciones o reducciones se rigen por la orden comercial y deben solicitarlas Administradores autorizados. No se alterarán retroactivamente condiciones devengadas salvo acuerdo o norma aplicable.</p>
        `],
        ['tos-15-precios', '15. Precios, facturación e impuestos', `
          <p>Precio, moneda, periodicidad, impuestos, vencimiento, medios de pago, mora, ajustes y eventuales reintegros se informarán en la propuesta, orden comercial o contrato aceptado por el Cliente. No hay un precio único establecido en estos Términos.</p>
          <p>Los cambios de precio deben notificarse según el contrato y la normativa aplicable. Las consecuencias de una falta de pago, incluidos intereses, suspensión o terminación, serán las expresamente pactadas y no podrán desconocer derechos inderogables.</p>
        `],
        ['tos-16-promociones', '16. Pruebas gratuitas y promociones', `
          <p>No se establecen aquí pruebas gratuitas ni promociones generales. Si se ofrece una prueba o promoción, sus condiciones, duración, alcance, requisitos de conversión a un Plan pago y forma de cancelación deberán informarse antes de su aceptación. [COMPLETAR: confirmar si existen ofertas vigentes y dónde se publican sus condiciones].</p>
        `],
        ['tos-17-disponibilidad', '17. Disponibilidad y mantenimiento', `
          <p>MyManageRH adoptará esfuerzos razonables para operar el Servicio, pero no promete disponibilidad ininterrumpida ni un porcentaje de disponibilidad, salvo que un SLA escrito y firmado establezca expresamente ese compromiso.</p>
          <p>Puede haber mantenimiento, actualizaciones, incidentes, interrupciones de conectividad o fallas de proveedores externos. Cuando resulte razonable, MyManageRH procurará informar mantenimientos que afecten materialmente el acceso. Nada limita obligaciones inderogables.</p>
        `],
        ['tos-18-soporte', '18. Soporte', `
          <p>El soporte se presta por los canales y dentro del alcance indicados en el Plan o contrato. No se prometen horarios ni tiempos de respuesta generales en estos Términos.</p>
          <ul><li><strong>Canal:</strong> [COMPLETAR: correo, formulario o portal operativo].</li><li><strong>Horario y tiempos comprometidos, si existen:</strong> [COMPLETAR: según Plan o SLA firmado].</li></ul>
          <p>El Cliente debe aportar información suficiente para diagnosticar una consulta y evitar incluir datos personales innecesarios.</p>
        `],
        ['tos-19-seguridad', '19. Seguridad', `
          <p>MyManageRH aplica medidas técnicas y organizativas razonables y acordes al Servicio para reducir riesgos de acceso no autorizado, pérdida, alteración o divulgación de información. Según la función y configuración, pueden existir autenticación, roles, aislamiento por Organización, registros de actividad, protección de comunicaciones y controles de integridad.</p>
          <p>Ninguna medida elimina todos los riesgos. El Cliente y los Usuarios también deben proteger Credenciales, dispositivos, permisos y canales de comunicación. Los detalles operativos sensibles no se publican en estos Términos.</p>
        `],
        ['tos-20-propiedad-intelectual', '20. Propiedad intelectual', `
          <p>MyManageRH o sus licenciantes conservan los derechos sobre software, código, interfaces, diseño, marca, documentación y demás componentes propios. El Cliente recibe un derecho limitado, revocable y no transferible de acceso durante la vigencia del Servicio y conforme al Plan contratado.</p>
          <p>Los componentes de terceros se rigen además por sus propias licencias. El Cliente conserva los derechos que tenga sobre los Datos del Cliente conforme a la sección 10. El uso no transfiere propiedad intelectual.</p>
        `],
        ['tos-21-terceros', '21. Integraciones y servicios de terceros', `
          <p>El Servicio puede conectarse con proveedores o sistemas externos para infraestructura, correo, SMS, almacenamiento, autenticación u otras funciones. La integración efectiva depende de la configuración y el Plan; los proveedores pueden tener términos y políticas propios.</p>
          <p>MyManageRH no controla los sistemas de terceros ni garantiza su disponibilidad. El uso de una integración no amplía las finalidades de tratamiento descritas en la Política de Privacidad. Inventario vigente: [COMPLETAR: URL o anexo de proveedores, finalidades y ubicaciones].</p>
        `],
        ['tos-22-confidencialidad', '22. Confidencialidad', `
          <p>Cada parte debe proteger la información no pública recibida de la otra y utilizarla solo para la relación contractual. No es confidencial la información pública sin incumplimiento, previamente conocida de forma legítima, recibida de un tercero autorizado o cuya divulgación exija la ley.</p>
          <p>Quien reciba una solicitud legal de divulgación procurará informar a la otra parte cuando la ley lo permita y limitar la entrega a lo requerido. Los Datos Personales también se rigen por la Política de Privacidad y, cuando corresponda, el DPA.</p>
        `],
        ['tos-23-privacidad', '23. Privacidad y datos personales', `
          <p>El tratamiento de datos personales se describe en la <a href="/privacy">Política de Privacidad de MyManageRH</a>. Para datos laborales que MyManageRH procesa siguiendo instrucciones del Cliente, las partes deben documentar sus roles y obligaciones en el DPA aplicable. Esta sección no reemplaza esos documentos.</p>
        `],
        ['tos-24-suspension', '24. Suspensión', `
          <p>MyManageRH podrá limitar o suspender temporalmente una Cuenta, función u Organización cuando sea razonablemente necesario para responder a una orden legal, riesgo de seguridad, acceso no autorizado, uso ilícito, incumplimiento material o falta de pago cuando esté pactada.</p>
          <p>Cuando sea legal y operativamente posible, MyManageRH avisará al Cliente, explicará el motivo y permitirá corregir la situación. La suspensión será proporcional al riesgo y no eliminará derechos de exportación o acceso que correspondan por ley o contrato.</p>
        `],
        ['tos-25-terminacion', '25. Terminación', `
          <p>El Cliente puede terminar el Servicio conforme a su contrato u orden comercial. MyManageRH puede terminarlo por incumplimiento material no subsanado, imposibilidad legal de continuar o los supuestos expresamente pactados, con aviso y oportunidad de subsanar cuando corresponda.</p>
          <p>Al terminar, se deshabilitarán los accesos según el proceso aplicable. El Cliente debe solicitar y descargar la exportación durante el período acordado: [COMPLETAR: período y procedimiento]. Luego, los datos se devolverán o eliminarán conforme al contrato, DPA, obligaciones legales y Política de Privacidad; no se fija aquí un plazo no definido.</p>
          <p>Las cláusulas que por su naturaleza deban subsistir, como propiedad intelectual, confidencialidad, pagos devengados, responsabilidad y obligaciones legales, continuarán vigentes.</p>
        `],
        ['tos-26-limitaciones', '26. Exclusiones y limitaciones', `
          <p>MyManageRH es una herramienta tecnológica. No constituye por sí sola asesoramiento jurídico, laboral, contable, impositivo ni de liquidación de haberes. El Cliente debe obtener asesoramiento profesional y decidir cómo cumplir sus obligaciones.</p>
          <p>MyManageRH no garantiza que un Documento sea correcto, que una firma tenga una calificación jurídica determinada ni que el Servicio satisfaga automáticamente las obligaciones del Cliente. Las limitaciones de responsabilidad, si se pactan, deberán ser claras, razonables y compatibles con normas imperativas; no excluyen responsabilidad que legalmente no pueda excluirse.</p>
        `],
        ['tos-27-indemnidad', '27. Indemnidad', `
          <p>Cada parte responderá por sus propios incumplimientos y actos. El Cliente mantendrá indemne a MyManageRH frente a reclamos de terceros que deriven directamente de Datos del Cliente ilícitos o cargados sin autorización, uso no autorizado por el Cliente o instrucciones contrarias a la ley, salvo en la medida en que el reclamo sea causado por un incumplimiento de MyManageRH.</p>
          <p>La parte que solicite indemnidad notificará el reclamo sin demora razonable, permitirá una defensa adecuada y no aceptará acuerdos que impongan obligaciones a la otra parte sin su consentimiento. Esta cláusula no elimina derechos de titulares ni responsabilidades no renunciables.</p>
        `],
        ['tos-28-cambios-servicio', '28. Cambios en el Servicio', `
          <p>MyManageRH puede corregir, actualizar o modificar funciones por razones técnicas, de seguridad, legales o de producto. Si un cambio elimina materialmente una función contratada, se aplicará el procedimiento y los derechos previstos en el contrato o Plan. No se garantiza que una función experimental o de tercero permanezca disponible.</p>
        `],
        ['tos-29-cambios-terminos', '29. Modificaciones de los Términos', `
          <p>MyManageRH identificará cada versión y fecha. Los cambios se comunicarán mediante la Plataforma, correo u otro canal razonable. Los cambios materiales se informarán antes de su vigencia y se solicitará nueva aceptación cuando la ley, el contrato o la naturaleza del cambio lo requieran.</p>
          <p>La falta de aceptación de una modificación que requiera consentimiento puede impedir el uso de las funciones afectadas; el Cliente podrá terminar el Servicio según su contrato. La versión vigente estará disponible en <a href="/terms">/terms</a>.</p>
        `],
        ['tos-30-comunicaciones', '30. Comunicaciones', `
          <p>Las comunicaciones operativas podrán cursarse dentro de la Plataforma, al correo asociado a la Cuenta o a los contactos que el Cliente registre. El Cliente debe mantener esos canales actualizados y revisar avisos relevantes.</p>
          <p>Las notificaciones legales se enviarán a los domicilios y canales constituidos en el contrato o, si no existen, a [COMPLETAR: canal y domicilio válidos]. Los mensajes automáticos no reemplazan una notificación formal cuando la ley exija otro medio.</p>
        `],
        ['tos-31-ley-jurisdiccion', '31. Ley aplicable y jurisdicción', `
          <p>Estos Términos se interpretan conforme a las leyes de la República Argentina, sin perjuicio de normas imperativas y derechos que no puedan renunciarse. <strong>Jurisdicción y tribunales competentes:</strong> [COMPLETAR: sede y jurisdicción territorial aplicable].</p>
        `],
        ['tos-32-disposiciones', '32. Disposiciones generales', `
          <p>Estos Términos, junto con los documentos comerciales y de tratamiento de datos aplicables, conforman el acuerdo sobre el uso del Servicio y reemplazan entendimientos previos sobre el mismo objeto. Si una cláusula resulta inválida, las restantes continúan vigentes y aquella se interpretará de forma compatible con la ley.</p>
          <p>La falta de ejercicio de un derecho no implica renuncia. Ninguna parte puede ceder el contrato sin la autorización requerida, salvo reorganización societaria permitida por ley y con aviso razonable. La relación es de prestación de servicios; no crea sociedad, mandato, relación laboral ni representación. En caso de contradicción, se aplicará el orden de prevalencia definido en la sección 1 y en el contrato firmado.</p>
        `],
        ['tos-33-contacto', '33. Contacto', `
          <ul>
            <li><strong>Soporte:</strong> [COMPLETAR: canal operativo].</li>
            <li><strong>Consultas legales:</strong> [COMPLETAR: contacto legal].</li>
            <li><strong>Privacidad:</strong> privacy@mymanagerh.com.</li>
            <li><strong>Identidad legal, CUIT y domicilio:</strong> ver los campos pendientes de la sección 2.</li>
          </ul>
        `]
      ])}
    `
  },
  privacy: {
    id: 'privacy',
    title: 'Política de Privacidad de MyManageRH',
    version: '1.0',
    lastUpdated: '2026-09-27',
    effectiveDate: '[COMPLETAR: fecha de entrada en vigencia]',
    category: 'Legal',
    html: `
      ${renderSections([
        ['privacy-01-introduccion', '1. Introducción', `
          <p>Esta Política explica qué datos personales puede tratar MyManageRH, para qué, con quién se comparten y cómo pueden ejercerse los derechos de sus titulares. Se aplica al sitio y al Servicio SaaS de Recursos Humanos, incluidos administración de organizaciones, empleados, legajos, recibos, documentos, autenticación, firmas, notificaciones e integraciones habilitadas.</p>
          <p>Debe leerse junto con los Términos y Condiciones de MyManageRH y, cuando corresponda, con el contrato y el DPA del Cliente. La información concreta depende de las funciones utilizadas y de los datos que el Cliente decida cargar.</p>
        `],
        ['privacy-02-identidad', '2. Identidad del responsable', `
          <p>MyManageRH es el nombre bajo el que se ofrece el Servicio. La persona jurídica que actúa como responsable en los tratamientos propios de MyManageRH debe identificarse antes de publicar:</p>
          <ul>
            <li><strong>Razón social y tipo societario:</strong> [COMPLETAR: entidad legal responsable de MyManageRH].</li>
            <li><strong>CUIT:</strong> [COMPLETAR: CUIT].</li>
            <li><strong>Domicilio:</strong> [COMPLETAR: domicilio legal].</li>
            <li><strong>Contacto general:</strong> [COMPLETAR: canal operativo].</li>
            <li><strong>Contacto de privacidad:</strong> privacy@mymanagerh.com [CONFIRMAR: casilla operativa y responsable].</li>
          </ul>
        `],
        ['privacy-03-roles', '3. Roles respecto del tratamiento', `
          <p>El rol se determina por finalidad y actividad, no solo por el nombre de las partes. Cuando un Cliente utiliza MyManageRH para administrar información laboral de sus Trabajadores, normalmente decide para qué incorpora los datos, qué información carga, quién accede y qué acciones se realizan. En esos tratamientos, el Cliente actúa como responsable y MyManageRH procesa datos siguiendo instrucciones documentadas para prestar y proteger el Servicio, en el rol que corresponda conforme a la Ley 25.326, el contrato y el DPA.</p>
          <p>MyManageRH puede determinar finalidades propias limitadas para administrar Cuentas de contacto del Cliente, contratar y facturar el Servicio, atender consultas dirigidas directamente a MyManageRH, proteger sus sistemas y cumplir obligaciones legales. En esos casos debe identificarse el rol aplicable según la actividad concreta.</p>
          <p>El empleador conserva sus obligaciones respecto de datos laborales, información a los Trabajadores, base jurídica y decisiones de Recursos Humanos. MyManageRH no se convierte por ello en empleador ni asume automáticamente obligaciones laborales del Cliente.</p>
        `],
        ['privacy-04-personas', '4. Personas alcanzadas', `
          <p>La Política puede alcanzar a representantes y contactos de Clientes; Administradores y otros Usuarios; Trabajadores cuyos datos incorpora el Cliente; visitantes del sitio; personas que solicitan soporte; y firmantes o destinatarios de Documentos. Una persona puede estar alcanzada aunque no tenga una Cuenta, por ejemplo cuando su empleador carga sus datos o un recibo.</p>
        `],
        ['privacy-05-datos', '5. Datos personales tratados', `
          <p>MyManageRH trata los datos que se incorporan o generan al usar las funciones habilitadas. No todas las categorías se tratan en todos los Clientes.</p>
          <h3 id="privacy-05-1-identificacion">5.1 Identificación</h3><p>Nombre, apellido, DNI, CUIL/CUIT, fecha de nacimiento, número de legajo u otros identificadores que el Cliente cargue o que sean necesarios para asociar un registro.</p>
          <h3 id="privacy-05-2-contacto">5.2 Contacto</h3><p>Correo electrónico, teléfono, domicilio y canales de contacto del Usuario o Trabajador, cuando se proporcionen.</p>
          <h3 id="privacy-05-3-laboral">5.3 Información laboral</h3><p>Organización, puesto, sector, categoría, fechas de ingreso o egreso, estado, datos administrativos, sindicales u otros campos del legajo que el Cliente decida gestionar.</p>
          <h3 id="privacy-05-4-economicos">5.4 Datos económicos y remunerativos</h3><p>Recibos, remuneraciones, conceptos de liquidación, comprobantes de pago y, si el Cliente los carga, datos bancarios como banco, tipo de cuenta, CBU o alias.</p>
          <h3 id="privacy-05-5-legajo">5.5 Información del legajo</h3><p>Archivos y documentación laboral que el Cliente incorpora, incluidos certificados o documentos de identidad si decide cargarlos. El Cliente debe limitar la carga a lo necesario y permitido.</p>
          <h3 id="privacy-05-6-documentos">5.6 Documentos y firmas</h3><p>Contenido y metadatos de Documentos; versiones y estados; solicitudes de firma; imagen de firma si se utiliza; confirmaciones; OTP o datos asociados a su validación; hashes, fecha y hora, e información técnica vinculada al evento cuando la función la registre.</p>
          <h3 id="privacy-05-7-cuenta">5.7 Cuenta</h3><p>Nombre de Usuario, correo, identificador de Cuenta, Organización, rol, permisos, estado y preferencias necesarias para operar la Cuenta.</p>
          <h3 id="privacy-05-8-seguridad">5.8 Autenticación y seguridad</h3><p>Datos asociados a inicios de sesión, sesiones, recuperación de Cuenta, OTP, intentos fallidos, cambios de permisos, alertas y otros eventos de seguridad. Las Credenciales no deben exponerse en los registros de soporte.</p>
          <h3 id="privacy-05-9-tecnicos">5.9 Datos técnicos</h3><p>Dirección IP, fecha y hora, agente de usuario, tipo de navegador, sistema operativo, dispositivo, identificadores de sesión, eventos y registros de actividad, cuando se generen en el uso del Servicio.</p>
          <h3 id="privacy-05-10-soporte">5.10 Soporte</h3><p>Contenido de consultas, comunicaciones, archivos enviados voluntariamente y datos necesarios para responder y mantener un historial de soporte.</p>
          <h3 id="privacy-05-11-facturacion">5.11 Facturación</h3><p>Datos identificatorios y de contacto de representantes, datos fiscales y registros de facturación o pago necesarios para administrar la relación comercial. El alcance y medios de pago deben definirse en la contratación.</p>
          <h3 id="privacy-05-12-sensibles">5.12 Datos sensibles</h3><p>MyManageRH no solicita de manera general datos sensibles para crear una Cuenta. Sin embargo, un Cliente podría incorporar datos sensibles, por ejemplo información sobre afiliación sindical o salud. Antes de hacerlo, debe evaluar necesidad, proporcionalidad, base jurídica, deber de información y medidas reforzadas.</p>
          <p>MyManageRH tratará esos datos únicamente en la medida necesaria para prestar la función instruida y conforme al contrato y la ley. El Cliente debe evitar cargar categorías sensibles que no sean necesarias o que no esté legalmente habilitado a tratar.</p>
        `],
        ['privacy-06-fuentes', '6. Fuentes de los datos', `
          <p>Los datos pueden provenir del titular que crea o utiliza una Cuenta; del Cliente, sus Administradores u otros Usuarios autorizados; de importaciones; de Documentos cargados o generados; de interacciones con soporte; de integraciones habilitadas; y de eventos técnicos generados al usar el Servicio.</p>
          <p>Cuando el Cliente obtiene datos de un Trabajador o los incorpora desde otra fuente, debe contar con una fuente legítima y cumplir el deber de información aplicable.</p>
        `],
        ['privacy-07-finalidades', '7. Finalidades', `
          <p>Los datos pueden tratarse, según corresponda, para administrar Organizaciones, Cuentas, roles y permisos; prestar las funciones contratadas; importar, asociar, organizar, consultar, corregir, exportar o eliminar información por instrucción del Cliente; gestionar firmas electrónicas, autenticación y OTP; registrar estados y evidencia; enviar notificaciones; atender soporte; facturar; proteger la Plataforma y prevenir fraude o accesos no autorizados; mantener y diagnosticar el Servicio; y cumplir obligaciones legales o responder requerimientos válidos.</p>
          <p>MyManageRH no utiliza los Datos del Cliente para fines incompatibles con el Servicio ni para publicidad basada en perfiles laborales.</p>
        `],
        ['privacy-08-bases', '8. Fundamento del tratamiento', `
          <p>El Cliente determina y documenta la base jurídica aplicable a los datos laborales que administra. Según el caso, puede incluir una obligación legal, una relación contractual, una instrucción válida u otra base reconocida por la Ley 25.326. El consentimiento se utiliza cuando resulta exigible o adecuado, pero no se presume como fundamento universal del tratamiento laboral.</p>
          <p>Para datos que MyManageRH trata con finalidades propias, la base depende de la actividad: gestión de la relación contractual, obligaciones legales, solicitud de la persona, medidas razonables de seguridad u otra base jurídicamente admisible. Matriz por actividad: [COMPLETAR: bases jurídicas aprobadas].</p>
        `],
        ['privacy-09-organizaciones', '9. Información aportada por organizaciones', `
          <p>El Cliente instruye qué datos se cargan, quién los consulta, para qué función se usan y cuándo se corrigen o eliminan. Debe contar con facultades para impartir esas instrucciones. Los Trabajadores deben dirigir inicialmente al empleador las solicitudes relativas a información que este controla.</p>
          <p>MyManageRH podrá asistir técnicamente al Cliente o derivarle una solicitud para que responda. El Cliente debe corregir instrucciones o datos inexactos y notificar los cambios necesarios. La terminación del Servicio no elimina automáticamente obligaciones de conservación del empleador.</p>
        `],
        ['privacy-10-destinatarios', '10. Destinatarios y cesiones', `
          <p>Los datos pueden ser accesibles para el Cliente y los Usuarios que autorice dentro de la Organización, según sus roles; para MyManageRH y el personal autorizado que necesite acceso para operar, mantener, dar soporte o proteger el Servicio; y para proveedores que actúen por cuenta de MyManageRH bajo instrucciones y obligaciones apropiadas.</p>
          <p>También pueden comunicarse a autoridades ante un requerimiento válido u obligación legal, o a terceros cuando el titular o Cliente lo instruya legítimamente. MyManageRH no vende datos personales ni los comparte con anunciantes para fines publicitarios propios.</p>
        `],
        ['privacy-11-proveedores', '11. Proveedores y subencargados', `
          <p>Para prestar el Servicio pueden utilizarse proveedores de infraestructura, correo, SMS, gestión de claves y entrega de tipografías. Entre las integraciones configurables identificadas se encuentran servicios compatibles con SMTP, Amazon SES, Gmail, Twilio, AWS KMS y Google Cloud KMS; la prestación efectiva depende de la configuración y el proveedor contratado. El sitio carga tipografías desde Google Fonts.</p>
          <p>Antes de publicar debe completarse el inventario efectivo de proveedores, funciones, países, datos a los que acceden, subencargados y mecanismos de actualización: <strong>[COMPLETAR: lista vigente de proveedores y subencargados]</strong>. Los proveedores con acceso a datos deberán estar sujetos a obligaciones compatibles de confidencialidad, seguridad y uso limitado.</p>
        `],
        ['privacy-12-transferencias', '12. Transferencias internacionales', `
          <p>Un proveedor de correo, infraestructura, tipografías, almacenamiento o gestión de claves puede procesar datos fuera de Argentina. La ubicación efectiva depende de los proveedores y configuraciones vigentes; los países y mecanismos jurídicos aplicables deben informarse con precisión.</p>
          <p>Antes de publicar debe completarse: <strong>[COMPLETAR: países o regiones de procesamiento, proveedores involucrados y mecanismo de transferencia/salvaguardas aplicable]</strong>. Cuando exista una transferencia internacional, se aplicarán las condiciones y salvaguardas exigidas por la normativa argentina. No se presume que todos los países tengan un nivel adecuado de protección.</p>
        `],
        ['privacy-13-retencion', '13. Conservación y eliminación', `
          <p>Los datos se conservan durante el tiempo necesario para la finalidad aplicable, la prestación del Servicio, las instrucciones del Cliente, la defensa de reclamos y las obligaciones legales. No se fija aquí un plazo numérico que no haya sido definido y validado.</p>
          <ul>
            <li><strong>Cuentas y administración:</strong> [DEFINIR PLAZO DE RETENCIÓN].</li>
            <li><strong>Recibos, legajos y documentos:</strong> [DEFINIR PLAZO Y RESPONSABILIDAD DEL CLIENTE].</li>
            <li><strong>Registros de auditoría y seguridad:</strong> [DEFINIR PLAZO DE RETENCIÓN].</li>
            <li><strong>Copias de respaldo y eliminación definitiva:</strong> [DEFINIR CICLO Y PLAZO DE ELIMINACIÓN].</li>
            <li><strong>Soporte y facturación:</strong> [DEFINIR PLAZO DE RETENCIÓN].</li>
          </ul>
          <p>Al terminar el Servicio, la información se exportará, devolverá, eliminará o conservará conforme al contrato y al DPA. Puede mantenerse durante el plazo necesario para cumplir obligaciones legales o atender reclamos; las copias de respaldo se eliminarán según un ciclo documentado.</p>
        `],
        ['privacy-14-seguridad', '14. Seguridad', `
          <p>MyManageRH adopta medidas técnicas y organizativas razonables para proteger los datos frente a acceso, pérdida, alteración o divulgación no autorizados. Según la función y configuración, pueden incluir autenticación, controles de roles y Organización, gestión de sesiones, registros de actividad, protección de comunicaciones y controles de integridad documental.</p>
          <p>El nivel de protección depende también del Cliente, sus permisos, dispositivos, canales, Credenciales y configuración. Ningún sistema puede garantizar seguridad absoluta. Las medidas efectivamente aplicadas deben documentarse en el DPA o anexo de seguridad: [COMPLETAR: referencia al anexo actualizado].</p>
        `],
        ['privacy-15-incidentes', '15. Incidentes de seguridad', `
          <p>MyManageRH mantendrá un proceso para detectar, analizar, contener y mitigar incidentes que afecten datos personales bajo su control o procesamiento. Cuando un incidente afecte Datos del Cliente, MyManageRH lo comunicará al Cliente sin demora indebida y conforme al contrato, al DPA y a la normativa, incluyendo información razonablemente disponible para evaluar el impacto.</p>
          <p>El Cliente, como responsable de datos laborales cuando corresponda, decidirá y ejecutará las notificaciones a titulares y autoridades que la ley exija. Las partes cooperarán razonablemente. No se promete un plazo fijo de 72 horas que no esté acordado y validado.</p>
        `],
        ['privacy-16-derechos', '16. Derechos de los titulares', `
          <p>La Ley 25.326 reconoce, según corresponda, derechos de acceso, rectificación, actualización y supresión de datos personales, además de los recursos previstos por la normativa. Su ejercicio puede estar sujeto a excepciones, identidad verificada y plazos legales.</p>
          <p>Cuando el Cliente decide el tratamiento laboral, el titular debe dirigirse al empleador para solicitar acceso, corrección o supresión. MyManageRH asistirá al Cliente cuando actúe como proveedor técnico. Para tratamientos en los que MyManageRH determine directamente la finalidad, el titular puede contactarse mediante la sección 17.</p>
        `],
        ['privacy-17-ejercer-derechos', '17. Cómo ejercer derechos', `
          <p>La persona puede escribir a <a href="mailto:privacy@mymanagerh.com">privacy@mymanagerh.com</a> indicando su nombre, medio de respuesta, derecho que desea ejercer y la información necesaria para localizar los datos. MyManageRH podrá pedir información razonable para verificar identidad y evitar entregar o modificar datos de otra persona.</p>
          <p>Si los datos corresponden a una Organización Cliente, MyManageRH podrá derivar la solicitud al Cliente e informarlo al titular cuando sea apropiado. Canal y procedimiento: [CONFIRMAR: responsable de privacidad y proceso operativo].</p>
        `],
        ['privacy-18-autoridad', '18. Autoridad de control', `
          <p>En Argentina, la <strong>Agencia de Acceso a la Información Pública (AAIP)</strong> es la autoridad de control en materia de protección de datos personales. Las personas pueden consultar información y canales oficiales en <a href="https://www.argentina.gob.ar/aaip" rel="noreferrer">argentina.gob.ar/aaip</a>, sin perjuicio de los derechos y procedimientos previstos por la normativa.</p>
        `],
        ['privacy-19-cookies', '19. Cookies y tecnologías similares', `
          <p>La Plataforma utiliza mecanismos necesarios para autenticación, seguridad y funcionamiento de sesiones, incluidos cookies de sesión y almacenamiento local del navegador según el flujo utilizado. Si la persona activa “Recordar mis datos”, el navegador puede conservar su nombre o correo para autocompletar; esa opción no está destinada a guardar contraseñas.</p>
          <p>El sitio público carga tipografías desde Google Fonts; el navegador se conecta con Google y puede transmitir datos técnicos de conexión, como dirección IP y datos del navegador. Inventario de cookies, proveedores, ubicaciones y preferencias: [COMPLETAR: inventario y mecanismo de preferencias].</p>
          <p>Al momento de esta versión no se identificaron herramientas de publicidad o analítica de terceros en el sitio. [CONFIRMAR esta condición en producción]. Si se incorporan tecnologías de medición o publicidad, esta Política deberá actualizarse antes de activarlas y se solicitará consentimiento cuando la ley lo requiera.</p>
        `],
        ['privacy-20-menores', '20. Menores de edad', `
          <p>MyManageRH está dirigido principalmente a organizaciones. La edad no se utiliza aquí para excluir automáticamente a toda persona trabajadora menor de 18 años: un Cliente podría tener que administrar información de un Trabajador menor conforme a la legislación laboral y de protección de datos aplicable.</p>
          <p>El Cliente debe verificar la legalidad del vínculo, las autorizaciones o intervenciones de representantes que correspondan y la necesidad de cada dato. MyManageRH no presta por esta Política consentimiento para una relación laboral ni sustituye controles legales del empleador.</p>
        `],
        ['privacy-21-automatizacion', '21. Automatización e inteligencia artificial', `
          <p>El Servicio puede utilizar automatizaciones para importar archivos, extraer campos mediante OCR, asociar recibos y organizar documentos. Esas funciones pueden cometer errores y el Cliente debe revisar los resultados antes de utilizarlos para una decisión o comunicación laboral.</p>
          <p>MyManageRH no adopta actualmente decisiones automatizadas sobre contratación, despido, evaluación o condiciones laborales de una persona. Si se incorporara una función que produjera decisiones de ese tipo o efectos jurídicos significativos, se informarán su finalidad, datos, lógica general, intervención humana y mecanismos de revisión conforme a la ley.</p>
        `],
        ['privacy-22-agregados', '22. Datos anonimizados o agregados', `
          <p>El sistema genera métricas operativas para observar el funcionamiento del Servicio. El uso de métricas agregadas fuera de la prestación al Cliente y el método para impedir la reidentificación deben confirmarse: [COMPLETAR: alcance, anonimización y finalidades autorizadas]. No se presentarán datos como anónimos si una persona puede ser razonablemente identificada.</p>
        `],
        ['privacy-23-servicios-externos', '23. Servicios y enlaces externos', `
          <p>La Plataforma puede incluir enlaces, integraciones o recursos de terceros. Al utilizarlos, la persona puede interactuar directamente con ese tercero, que aplicará sus propios términos y políticas. Esta Política cubre el tratamiento realizado por MyManageRH; no describe prácticas de terceros que actúen como responsables independientes.</p>
          <p>Las funciones externas no deben habilitarse sin evaluar qué datos reciben, dónde los procesan y qué información corresponde comunicar al Cliente y a los titulares.</p>
        `],
        ['privacy-24-modificaciones', '24. Modificaciones de la Política', `
          <p>Cada versión indicará su fecha de actualización y entrada en vigencia. Los cambios se publicarán en <a href="/privacy">/privacy</a> y podrán comunicarse por la Plataforma o por correo. Los cambios materiales se informarán antes de su vigencia y se solicitará nueva aceptación cuando la ley lo exija.</p>
          <p>El uso continuado del Servicio no reemplaza una aceptación expresa cuando sea necesaria. Archivo de versiones anteriores: [COMPLETAR: mecanismo de consulta].</p>
        `],
        ['privacy-25-contacto', '25. Contacto', `
          <ul>
            <li><strong>Privacidad y derechos de titulares:</strong> <a href="mailto:privacy@mymanagerh.com">privacy@mymanagerh.com</a> [CONFIRMAR: canal operativo].</li>
            <li><strong>Soporte del Servicio:</strong> [COMPLETAR: correo, formulario o portal].</li>
            <li><strong>Titular legal, CUIT y domicilio:</strong> [COMPLETAR: datos de la sección 2].</li>
          </ul>
        `]
      ])}
    `
  }
};