# Piloto de quiz de retencion -- informe

Generado 2026-08-18 14:49 UTC · modelo `gemini-2.5-flash` · 2.1 min de ejecucion · version `quiz-0.7`

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
| Preguntas generadas | 6 | 100 % |
| Con cita verificable (existe) | 6 | 100 % |
| Cuya cita justifica la respuesta | 6 | 100 % |
| Llegaron al control de trivialidad | 6 | 100 % |
| Contestables sin ver el video | 5 | 83 % de las evaluadas |
| **Sobreviven** | **1** | **17 %** |

Preguntas utiles por video: 1.0 de 6 generadas.

### Motivos de descarte

| motivo | n |
|---|---:|
| contestable_sin_ver_el_video | 5 |

### Tipo de pregunta

| tipo | generadas | sobreviven |
|---|---:|---:|
| dato | 3 | 0 |
| relacion | 2 | 1 |
| argumento | 1 | 0 |

## 3. Ejemplos

**SOBREVIVE** — _ASÍ CONTROLA SÁNCHEZ LOS MEDIOS mientras sus escándalos de corrupción se acumulan - @SoloFonseca_

> ¿Qué consecuencia tuvo el cambio en la ley que permitió que la dirección de Televisión Española se eligiera por mayoría simple?

0. Pedro Sánchez ya no tiene que pactar con la oposición para elegir a la dirección ✔
1. La velocidad de aprobación contrastó con la ayuda a la Comunidad Valenciana
2. RTVE se convirtió en un órgano de propaganda del gobierno
3. La oposición no estuvo presente en la votación

Cita (literal): «Sin embargo, en esta votación se cambió por la mayoría simple. Es decir, que ahora Pedro Sánchez ya no tiene que pactar con la oposición, puede hacerlo con los partidos de su coalición de gobierno.»
Control sin video: eligio 2 (seguridad alta) → fallo, sobrevive

**DESCARTADA** — _ASÍ CONTROLA SÁNCHEZ LOS MEDIOS mientras sus escándalos de corrupción se acumulan - @SoloFonseca_

> ¿Quiénes fueron los pioneros en la política de la televisión pública, según el video?

0. Los países europeos
1. Los nazis ✔
2. España
3. Estados Unidos

Cita (literal): «La televisión pública apareció en la década de los años 30. Y venga, a ver si adivináis quiénes fueron los pioneros en esta política. Los nazis.»
Control sin video: eligio 1 (seguridad media) → ACERTO, descartada
Descarte: `contestable_sin_ver_el_video`

**DESCARTADA** — _ASÍ CONTROLA SÁNCHEZ LOS MEDIOS mientras sus escándalos de corrupción se acumulan - @SoloFonseca_

> ¿Cuál fue el presupuesto de Televisión Española en el año 2025, según el video?

0. 1220 millones de euros ✔
1. 840 millones de euros
2. 5000 millones de dólares
3. 2500 millones de dólares

Cita (literal): «Pero es que en el año 2025 el presupuesto de Televisión Española alcanzó los 1220 millones de euros.»
Control sin video: eligio 0 (seguridad media) → ACERTO, descartada
Descarte: `contestable_sin_ver_el_video`

**DESCARTADA** — _ASÍ CONTROLA SÁNCHEZ LOS MEDIOS mientras sus escándalos de corrupción se acumulan - @SoloFonseca_

> ¿Cuál fue la razón principal por la que los gobiernos europeos decidieron crear monopolios estatales de televisión en sus inicios?

0. No eran rentables en la economía privada
1. La idea de tener medios estatales les sonaba un poco nazi
2. Había muy pocas frecuencias para emitir imagen en vivo ✔
3. Para evitar la anarquía de televisiones libres

Cita (literal): «Además, en aquella época solamente se podía emitir imagen en vivo por muy pocas frecuencias. Por tanto, los gobiernos decidieron que lo mejor era crear monopolios estatales...»
Control sin video: eligio 2 (seguridad alta) → ACERTO, descartada
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