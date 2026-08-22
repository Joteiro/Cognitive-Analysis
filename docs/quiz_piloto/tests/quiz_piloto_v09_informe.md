# Piloto de quiz de retencion -- informe

Generado 2026-08-19 12:47 UTC · modelo `gemini-2.5-flash` · 4.0 min de ejecucion · version `quiz-0.9`

## 1. Que se midio

Cada pregunta pasa dos filtros independientes. El de **anclaje** comprueba que la
cita que el modelo dice haber sacado de la transcripcion exista de verdad ahi: es
el control de invencion. El de **trivialidad** hace que el mismo modelo conteste la
pregunta sin la transcripcion, viendo solo titulo, canal y opciones; si acierta, la
pregunta no medía retencion y se descarta. Con cuatro opciones, el azar acierta el
25 %, asi que una tasa de trivialidad cercana a esa cifra indica preguntas que de
verdad exigen haber visto el video.

## 2. Numeros

| | n | sobre el total |
|---|---:|---:|
| Videos procesados | 3 | |
| Videos que fallaron por completo | 0 | 0 % |
| Preguntas generadas | 18 | 100 % |
| Con cita verificable (existe) | 18 | 100 % |
| Cuya cita justifica la respuesta | 17 | 94 % |
| Llegaron al control de trivialidad | 15 | 83 % |
| Contestables sin ver el video | 10 | 67 % de las evaluadas |
| **Sobreviven** | **5** | **28 %** |

Preguntas utiles por video: 1.7 de 6 generadas.

### Motivos de descarte

| motivo | n |
|---|---:|
| contestable_sin_ver_el_video | 10 |
| opciones_desbalanceadas | 2 |
| cita_no_justifica | 1 |

### Tipo de pregunta

| tipo | generadas | sobreviven |
|---|---:|---:|
| dato | 7 | 3 |
| relacion | 6 | 1 |
| argumento | 4 | 1 |
| definicion | 1 | 0 |

## 3. Ejemplos

**SOBREVIVE** — _ASÍ CONTROLA SÁNCHEZ LOS MEDIOS mientras sus escándalos de corrupción se acumulan - @SoloFonseca_

> Según el narrador, ¿cuánto aumentó el presupuesto de Radio Televisión Española desde la llegada de Pedro Sánchez al poder hasta 2025?

0. Un 50%
1. Un 25% ✔
2. Un 125%
3. Un 100%

Cita (literal): «En el año 2025 el presupuesto de Televisión Española alcanzó los 1220 millones de euros. Es decir, que desde que llegó Pedro Sánchez al poder, el presupuesto de Televisión Española ha aumentado un 25%.»
Control sin video: eligio 3 (seguridad media) → fallo, sobrevive

**SOBREVIVE** — _ASÍ CONTROLA SÁNCHEZ LOS MEDIOS mientras sus escándalos de corrupción se acumulan - @SoloFonseca_

> ¿Cuánto costó a los españoles la contratación de David Broncano en Televisión Española para el programa "La Revuelta"?

0. 14 millones de euros ✔
1. 40 millones de euros
2. 60 millones de euros
3. 8,3 millones de euros

Cita (literal): «Pedro Sánchez se quiso vengar del hormiguero contratando a David Broncano en la televisión española y esta vengancita costó a los españoles 14 millones de euros.»
Control sin video: eligio 3 (seguridad media) → fallo, sobrevive

**SOBREVIVE** — _TRUMP DESTRUYE LA IMAGEN DE EEUU y el turismo le está pasando factura - @SoloFonseca_

> ¿Qué grave consecuencia se menciona tras el desmantelamiento de USAID y el corte de ayuda humanitaria en la República Democrática del Congo?

0. La retención de un futbolista por 7 horas en el aeropuerto de Chicago.
1. La detención de un niño de 5 años en operaciones de inmigración.
2. Un aumento del 10% en la violencia en las zonas de África que recibían ayuda.
3. Un brote de ébola que se convirtió en el tercer peor de toda la historia. ✔

Cita (literal): «USAID financiaba el 70% de la ayuda humanitaria en la República Democrática del Congo. Así que cuando la cortaron, nadie detectó a tiempo un brote de ébola que se convirtió en el tercer peor de toda la historia.»
Control sin video: eligio 2 (seguridad media) → fallo, sobrevive

**DESCARTADA** — _ASÍ CONTROLA SÁNCHEZ LOS MEDIOS mientras sus escándalos de corrupción se acumulan - @SoloFonseca_

> ¿Qué grupo fue pionero en la política de la televisión pública en la década de los años 30?

0. Los nazis ✔
1. Los países europeos
2. El gobierno español
3. Estados Unidos

Cita (literal): «La televisión pública apareció en la década de los años 30. Y venga, a ver si adivináis quiénes fueron los pioneros en esta política. Los nazis.»
Descarte: `opciones_desbalanceadas`

**DESCARTADA** — _ASÍ CONTROLA SÁNCHEZ LOS MEDIOS mientras sus escándalos de corrupción se acumulan - @SoloFonseca_

> ¿Cuál fue la principal justificación económica para la creación de empresas públicas de telefonía, ferrocarril y televisión en Europa durante la era dorada del keynesianismo?

0. La escasez de frecuencias para la emisión de imagen en vivo.
1. La necesidad de controlar la libertad de expresión en los medios.
2. La doctrina que considera estratégicos los sectores no rentables para la economía privada. ✔
3. La intención de formar, informar y entretener a los ciudadanos de forma neutral.

Cita (literal): «aquellos años eran la era de oro del keinesenismo económico, una doctrina que promulga que hay unos sectores estratégicos que normalmente no son rentables en la economía privada y que por tanto el Estado tiene que invertir en ellos.»
Control sin video: eligio 2 (seguridad alta) → ACERTO, descartada
Descarte: `contestable_sin_ver_el_video`

**DESCARTADA** — _ASÍ CONTROLA SÁNCHEZ LOS MEDIOS mientras sus escándalos de corrupción se acumulan - @SoloFonseca_

> ¿Cuál fue la razón principal por la que el gobierno de Mariano Rajoy consiguió que Pedro J. Ramírez fuera despedido de El Mundo, el periódico que él mismo había fundado?

0. Por criticar duramente al gobierno y destapar casos de corrupción como Gürtel. ✔
1. Por la difusión de un vídeo personal comprometedor.
2. Por negarse a cambiar titulares a petición del gobierno.
3. Por destapar el escándalo de Losgal en el diario 16.

Cita (parcial_27_de_43): «Fue su periódico, El Mundo, el que destapó buena parte del caso Gürtel y de los famosos papeles de las cuentas en B del caso Máas. [...] El gobierno consiguió que echaran al director de su propio periódico, el que él mismo había fundado.»
Descarte: `opciones_desbalanceadas`

## 4. Como leer esto

Lo que decide si la funcionalidad sigue adelante no es el numero de preguntas
generadas sino el de **supervivientes por video**. Con menos de dos por video no
hay quiz posible: no alcanza para distinguir a quien retuvo de quien no.

Una tasa de trivialidad muy por encima del 25 % significa que el generador esta
haciendo preguntas de cultura general disfrazadas, y hay que endurecer el prompt.
Muy por debajo del 25 % tambien es sospechoso: sugiere distractores tan raros que
el control los descarta por absurdos, y entonces la pregunta tampoco discrimina.

Las preguntas de este piloto **no estan revisadas por una persona**. Antes de
usarlas para medir nada hay que leerlas: el control automatico filtra invencion y
trivialidad, no ambiguedad ni preguntas mal planteadas.