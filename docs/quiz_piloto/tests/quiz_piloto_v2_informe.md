# Piloto de quiz de retencion -- informe

Generado 2026-08-15 17:43 UTC · modelo `llama-3.3-70b-versatile` · 3.5 min de ejecucion · version `quiz-piloto-0.1`

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
| Videos procesados | 5 | |
| Videos que fallaron por completo | 0 | 0 % |
| Preguntas generadas | 30 | 100 % |
| Con cita verificable (existe) | 28 | 93 % |
| Cuya cita justifica la respuesta | 22 | 73 % |
| Llegaron al control de trivialidad | 22 | 73 % |
| Contestables sin ver el video | 9 | 41 % de las evaluadas |
| **Sobreviven** | **13** | **43 %** |

Preguntas utiles por video: 2.6 de 6 generadas.

### Motivos de descarte

| motivo | n |
|---|---:|
| contestable_sin_ver_el_video | 9 |
| cita_no_justifica | 6 |
| cita_no_verificable | 2 |

### Tipo de pregunta

| tipo | generadas | sobreviven |
|---|---:|---:|
| dato | 19 | 8 |
| argumento | 8 | 3 |
| relacion | 2 | 2 |
| definicion | 1 | 0 |

## 3. Ejemplos

**SOBREVIVE** — _REBORD Y LA VERDAD SOBRE BLENDER - MOVISTAR ARENA HAGOVERO EL 19 DE OCTUBRE_

> ¿Qué plataforma de transmisión va a utilizar Tomás Rebord además de YouTube?

0. Kick ✔
1. Twitch
2. Instagram Live
3. Facebook Live

Cita (parcial_8_de_13): «Voy a inaugurar otro canal. Este otro canal será en la plataforma Kick»
Control sin video: eligio 1 (seguridad alta) → fallo, sobrevive

**SOBREVIVE** — _REBORD Y LA VERDAD SOBRE BLENDER - MOVISTAR ARENA HAGOVERO EL 19 DE OCTUBRE_

> ¿Qué día y hora va a realizar Tomás Rebord transmisiones oficiales?

0. Los lunes a las 21 horas ✔
1. Los lunes a las 20 horas
2. Los martes a las 20 horas
3. Los martes a las 21 horas

Cita (literal): «los días lunes a las 21 horas yo hago una transmisión formal»
Control sin video: eligio 3 (seguridad baja) → fallo, sobrevive

**SOBREVIVE** — _REBORD Y LA VERDAD SOBRE BLENDER - MOVISTAR ARENA HAGOVERO EL 19 DE OCTUBRE_

> ¿Por qué Tomás Rebord considera que el movimiento agobero ha entrado en la clandestinidad?

0. Por un atentado ✔
1. Por una amenaza externa
2. Por una pérdida de apoyo popular
3. Por una decisión política

Cita (literal): «nos comimos un atentado, ground cero, el ground cero del agoberismo»
Control sin video: eligio 2 (seguridad baja) → fallo, sobrevive

**DESCARTADA** — _REBORD Y LA VERDAD SOBRE BLENDER - MOVISTAR ARENA HAGOVERO EL 19 DE OCTUBRE_

> ¿Cuántas personas están mirando la transmisión clandestina según Tomás Rebord?

0. Más de 40.000 personas ✔
1. Más de 30.000 personas
2. Más de 60.000 personas
3. Más de 50.000 personas

Cita (literal): «somos más de 40,000 personas mirando esta transmisión clandestina»
Control sin video: eligio 0 (seguridad baja) → ACERTO, descartada
Descarte: `contestable_sin_ver_el_video`

**DESCARTADA** — _REBORD Y LA VERDAD SOBRE BLENDER - MOVISTAR ARENA HAGOVERO EL 19 DE OCTUBRE_

> ¿Qué va a hacer Tomás Rebord con el sistema Agob?

0. Va a utilizarlo para hacer donaciones a organizaciones benéficas
1. Va a utilizarlo para promocionar su canal de YouTube
2. Va a utilizarlo para crear un nuevo partido político
3. Va a utilizarlo para generar un fondo de desempleo ✔

Cita (literal): «el sistema Agob lo que ha permitido hasta ahora es básicamente generar un fondo de desempleboard»
Descarte: `cita_no_justifica`

**DESCARTADA** — _REBORD Y LA VERDAD SOBRE BLENDER - MOVISTAR ARENA HAGOVERO EL 19 DE OCTUBRE_

> ¿Qué tipo de contenido va a ofrecer Tomás Rebord en la plataforma Kick?

0. Contenido espontáneo y fresco ✔
1. Análisis políticos y sociales
2. Entrevistas con personalidades públicas
3. Transmisiones formales y planificadas

Cita (literal): «va a ser espontáneo, fresco y divertido»
Control sin video: eligio 0 (seguridad media) → ACERTO, descartada
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