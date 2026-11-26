# Lecciones

Lo aprendido al buscar jurisprudencia y litigar tutelas y memoriales en casos reales entre 2023 y 2026, sobre todo ante juzgados y el Tribunal Superior de Cali. Sin nombres ni datos de las personas. Es una guía de trabajo, no asesoría jurídica: cada regla debe confirmarse en la sentencia completa y en su versión vigente.

## 1. Los buscadores

- **Corte Constitucional (`buscador_new`).** Una frase entre comillas por consulta. Si no hay resultados, la respuesta no es JSON: tratarla como cero resultados. La Corte cambia la página más o menos una vez al año; si deja de responder, revisar primero la dirección del servicio.
- **Copia local de `ccc` y `cccLLM`.** Llega hasta abril de 2024. Lo posterior (por ejemplo, las unificaciones de 2025 y 2026) hay que buscarlo en línea. El *indegree* (cuántas veces la citan) separa bien las sentencias hito de las que solo repiten la regla.
- **Corte Suprema (GraphQL).** Responden los tipos `Tutelas` y `Laboral`; los demás devuelven error. El texto completo sale de `getContentSearch` con la sala que corresponda (`Tutelas` o `Laboral`). El PDF oficial no tiene enlace directo por sentencia: se descarga con una petición `POST` a `downloadFile` usando la ruta (`onlinePath`) que trae el resultado.
- **Publicaciones Procesales.** Busca en el texto completo de cientos de miles de documentos de todo el país. Varias frases entre comillas funcionan como "y". Con cuatro procesos en paralelo el portal respondió 403 durante horas: usar uno solo, tres segundos entre páginas y pocas descargas a la vez. Solo trae lo que cada despacho decide publicar.
- **Consulta Nacional de Procesos.** El JSON público da las actuaciones de cada radicado. Sirve para vigilar un proceso propio y para ver cómo resuelve un despacho (la anotación de la sentencia suele decir AMPARA, NIEGA o IMPROCEDENTE).
- **Modelos de lenguaje locales.** Sirven para clasificar y resumir, pero confunden lo que pide el accionante con lo que ordena el juez y atribuyen al juez frases de la demanda. Nunca citar sin leer el fallo.

## 2. Citar para que el juez confíe

- Cero afirmaciones sin prueba. Leer completo lo que se cita, verificar cada cita palabra por palabra (`verificar_citas.py`) y abrir cada enlace el día del envío. Un error que descubra la contraparte, como atribuirle una cita que no hizo o ubicar una norma en un acto que no la contiene, tumba la credibilidad de todo el escrito.
- Citas en APA: de 40 palabras o más, en bloque, sin comillas y con (p. X). Nunca recortar con "…" para cambiar el sentido.
- En el texto: número de la sentencia, fecha completa y magistrado ponente, tomado de la sentencia y nunca supuesto. Decir cuál sala (Sala Tercera de Decisión Laboral, Sala de Casación Laboral, Sala Plena) y cuál corte, nunca solo "la Sala" o "la Corte".
- Notas al pie abreviadas: sentencia, fecha, página, ponente, sala y enlace. Para normas: número, fecha, artículo, Diario Oficial y enlace.
- Sin pantallazos, salvo la parte pertinente de la respuesta de la entidad tomada del original.
- No decirle al juez qué fallar. Mostrarle la línea de los jueces superiores y pedirle una salida concreta.
- Escribir en primera persona y en orden: lo que se pide, los hechos, la jurisprudencia en orden cronológico (mostrando cómo cambió la regla) y las solicitudes numeradas. Los jueces leen poco: síntesis primero.
- Usar los verbos procesales exactos (ordenó, ofició, requirió, confirmó). No afirmar pagos ni resultados que no consten. Sin cifras de dinero en los memoriales; días y periodos sí. A terceros se les cita por radicado, sin nombres.

## 3. Derecho de petición y cumplimiento de fallos

- Una tutela por derecho de petición obliga a la entidad a decidir, no a pagar. Si se quiere el pago por tutela, hay que pedirlo desde el escrito inicial y justificar la procedencia: sujeto de especial protección, mínimo vital, ineficacia del proceso ordinario.
- Es común que la administradora responda al fallo con una resolución que no resuelve lo pedido y pida declarar hecho superado. El hecho superado exige satisfacción integral y voluntaria durante el trámite; una resolución expedida para cumplir el fallo no lo configura.
- Exigir certificados "actualizados, no superiores a tres meses, con firma y sello" no está en la ley (CPACA, art. 9, num. 5). Si la demora de la entidad hace "vencer" el certificado, argumentar el círculo imposible y pedir que lo solicite directamente a la EPS (T-523 de 2020; Decreto Ley 019 de 2012, art. 9).
- Una entidad no puede negar prestaciones con requisitos de sus circulares internas que la ley no prevé (T-314 de 2022).
- La entidad que alega haber respondido debe aportar copia íntegra de la respuesta, sus anexos y la constancia de envío. Un enlace que el juez no puede abrir no acredita nada (T-044 de 2019).
- El silencio de la entidad frente a un punto concreto se toma como presunción de certeza. La inmediatez se satisface si la vulneración persiste. Pedir un remedio con plazo y turno concretos, no una orden genérica de "responder" (sobre cargas desproporcionadas, T-377 de 2022).
- En el incidente de desacato casi nunca hay sanción en firme: los jueces cierran cuando llega cualquier respuesta. Hay que mostrar con hechos y folios por qué la respuesta no cumple. Cuando el juez archiva por cumplimiento, quedan los recursos contra el acto administrativo y la jurisdicción ordinaria laboral.
- Las notificaciones por correo físico (citación y luego aviso) corren desde que alguien recibe en la dirección registrada. Verificar quién recibió y cuándo, porque desde ahí cuentan los diez días del recurso.

## 4. Pensiones

- **Documentos descargados de internet.** Línea de la Sala de Casación Laboral desde SL5170-2019 hasta SL013-2024: los documentos obtenidos en línea son auténticos por su fecha, hora y emblemas, aunque no tengan firma; si hay duda, se pide a quien los produjo. En contra: T-157 de 2019, que avaló exigir certificado firmado.
- **Retroactivo de la pensión de invalidez.** La regla SL5170-2021 (las mesadas empiezan cuando expira la última incapacidad) tiene una excepción armonizada por la misma Sala: SL4299-2022 y SL2223-2023. Si entre la estructuración y la última incapacidad el afiliado no cotizó ni tuvo otro ingreso, se paga desde la estructuración descontando solo las incapacidades pagadas. Las salas laborales del Tribunal de Cali no aplican todas la misma regla: revisar la del ponente antes de impugnar (`red_citas.py --que-citan SL4299-2022` ayuda).
- **Retroactivo en tutela.** La SU-140 de 2026 dispuso que la pensión de invalidez se causa desde la estructuración y que la ineficiencia administrativa no puede reducir el derecho. Antes, la SU-556 de 2019 enviaba el retroactivo al juez ordinario en los casos de condición más beneficiosa.
- **Indexación.** La Sala de Casación Laboral la trata como pago completo de la obligación, no como un aumento de la condena (SL359-2021). Pedir lo conservador: retroactivo desde la estructuración, descontando solo lo pagado, indexado, sin intereses y sin renunciar a ellos.
- **Historia laboral.** La carga de probar que la historia laboral es exacta recae en la administradora (SU-405 de 2021). Pero con una sola copia simple cuestionada y sin otros indicios, la Corte niega (T-274 de 2022). Hay que acumular indicios: archivos del ISS (microfichas, tarjetas de reseña), el expediente de liquidación de la empresa, testigos y documentos personales. Un caso frecuente son las semanas que no aparecen porque la persona tuvo varios números de afiliación al ISS.
