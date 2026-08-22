# Piloto de quiz de retencion -- informe

Generado 2026-08-18 16:12 UTC · modelo `gemini-2.5-flash` · 2.7 min de ejecucion · version `quiz-0.8`

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
| Videos procesados | 1 | |
| Videos que fallaron por completo | 0 | 0 % |
| Preguntas generadas | 8 | 100 % |
| Con cita verificable (existe) | 8 | 100 % |
| Cuya cita justifica la respuesta | 8 | 100 % |
| Llegaron al control de trivialidad | 8 | 100 % |
| Contestables sin ver el video | 8 | 100 % de las evaluadas |
| **Sobreviven** | **0** | **0 %** |

Preguntas utiles por video: 0.0 de 8 generadas.

### Motivos de descarte

| motivo | n |
|---|---:|
| contestable_sin_ver_el_video | 8 |

### Tipo de pregunta

| tipo | generadas | sobreviven |
|---|---:|---:|
| dato | 4 | 0 |
| relacion | 2 | 0 |
| argumento | 2 | 0 |

## 3. Ejemplos

**DESCARTADA** — _ASÍ CONTROLA SÁNCHEZ LOS MEDIOS mientras sus escándalos de corrupción se acumulan - @SoloFonseca_

> Según el narrador, ¿cuál fue el presupuesto de Radio Televisión Española en el año 2025, después de la llegada de Pedro Sánchez al poder?

0. 840 millones de euros
1. 1220 millones de euros ✔
2. 11 millones de euros
3. 250 millones de euros

Cita (literal): «Pero es que en el año 2025 el presupuesto de Televisión Española alcanzó los 1220 millones de euros. Es decir, que desde que llegó Pedro Sánchez al poder, el presupuesto de Televisión Española ha aumentado un 25%.»
Control sin video: eligio 1 (seguridad baja) → ACERTO, descartada
Descarte: `contestable_sin_ver_el_video`

**DESCARTADA** — _ASÍ CONTROLA SÁNCHEZ LOS MEDIOS mientras sus escándalos de corrupción se acumulan - @SoloFonseca_

> ¿Cuáles fueron las dos razones principales por las que los países europeos, a diferencia de Estados Unidos, optaron por crear televisiones públicas en sus inicios?

0. La influencia de los nazis y el deseo de competir con Estados Unidos.
1. La doctrina económica keynesiana y la escasez de frecuencias de emisión. ✔
2. El modelo de la BBC y la alta rentabilidad del sector.
3. La necesidad de ofrecer programas educativos y la falta de interés privado.

Cita (parcial_21_de_36): «Pues la excusa que encontraron fue la tecnología. No olvidéis que aquellos años eran la era de oro del keinesenismo económico... Además, en aquella época solamente se podía emitir imagen en vivo por muy pocas frecuencias.»
Control sin video: eligio 1 (seguridad media) → ACERTO, descartada
Descarte: `contestable_sin_ver_el_video`

**DESCARTADA** — _ASÍ CONTROLA SÁNCHEZ LOS MEDIOS mientras sus escándalos de corrupción se acumulan - @SoloFonseca_

> ¿Quiénes fueron los pioneros en la política de la televisión pública, según lo mencionado en la transcripción?

0. Los países europeos
1. Los nazis ✔
2. Estados Unidos
3. España bajo Franco

Cita (literal): «La televisión pública apareció en la década de los años 30. Y venga, a ver si adivináis quiénes fueron los pioneros en esta política. Los nazis.»
Control sin video: eligio 1 (seguridad media) → ACERTO, descartada
Descarte: `contestable_sin_ver_el_video`

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