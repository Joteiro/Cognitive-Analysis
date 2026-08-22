# Piloto de quiz de retencion -- informe

Generado 2026-08-15 11:34 UTC · modelo `llama-3.3-70b-versatile` · 2.7 min de ejecucion · version `quiz-piloto-0.1`

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
| Preguntas generadas | 20 | 100 % |
| Con cita verificable | 17 | 85 % |
| Llegaron al control de trivialidad | 17 | 85 % |
| Contestables sin ver el video | 8 | 47 % de las evaluadas |
| **Sobreviven** | **9** | **45 %** |

Preguntas utiles por video: 1.8 de 4 generadas.

### Motivos de descarte

| motivo | n |
|---|---:|
| contestable_sin_ver_el_video | 8 |
| cita_no_verificable | 3 |

## 3. Ejemplos

**SOBREVIVE** — _REBORD Y LA VERDAD SOBRE BLENDER - MOVISTAR ARENA HAGOVERO EL 19 DE OCTUBRE_

> ¿Qué es lo que se ha habilitado para que las personas puedan contribuir al sistema Agob?

0. Un fondo de desempleo
1. Una cuenta de PayPal ✔
2. Un sistema de donaciones
3. Una cuenta de Kickstarter

Cita (literal): «Hemos habilitado la posibilidad de pagar desde el exterior por PayPal»
Control sin video: eligio 2 (seguridad baja) → fallo, sobrevive

**SOBREVIVE** — _TRUMP SE RETIRA DE IRÁN pero Israel quiere seguir luchando - @SoloFonseca_

> ¿Cuál es el cuarto punto que Irán quiere cumplir según el acuerdo?

0. Terminar con su plan nuclear
1. Terminar con los misiles balísticos
2. Reabrir el estrecho de Ormud ✔
3. Terminar con el régimen de los ayatolas

Cita (parcial_28_de_34): «la cuarta condición de Irán para terminar esta guerra es el fin del conflicto en todos los frentes, incluyendo a todos los grupos de resistencia en la región, y reabrir el estrecho de Ormud»
Control sin video: eligio 0 (seguridad baja) → fallo, sobrevive

**SOBREVIVE** — _TRUMP SE RETIRA DE IRÁN pero Israel quiere seguir luchando - @SoloFonseca_

> ¿Cuál es el precio actual del barril de petróleo?

0. $80 ✔
1. $67
2. $70
3. $60

Cita (literal): «el barril de petróleo ya está por debajo de los $80»
Control sin video: eligio 1 (seguridad baja) → fallo, sobrevive

**DESCARTADA** — _REBORD Y LA VERDAD SOBRE BLENDER - MOVISTAR ARENA HAGOVERO EL 19 DE OCTUBRE_

> ¿Cuántas personas están viendo la transmisión clandestina?

0. Más de 40,000 ✔
1. Más de 30,000
2. Más de 60,000
3. Más de 50,000

Cita (literal): «somos más de 40,000 personas mirando esta transmisión clandestina»
Control sin video: eligio 0 (seguridad baja) → ACERTO, descartada
Descarte: `contestable_sin_ver_el_video`

**DESCARTADA** — _REBORD Y LA VERDAD SOBRE BLENDER - MOVISTAR ARENA HAGOVERO EL 19 DE OCTUBRE_

> ¿En qué plataforma se transmitirán los mensajes oficiales los lunes?

0. Kick
1. YouTube ✔
2. Twitch
3. Instagram

Cita (literal): «los días lunes a las 21 horas yo hago una transmisión formal como venimos haciendo hace ya muchos años»
Control sin video: eligio 1 (seguridad media) → ACERTO, descartada
Descarte: `contestable_sin_ver_el_video`

**DESCARTADA** — _REBORD Y LA VERDAD SOBRE BLENDER - MOVISTAR ARENA HAGOVERO EL 19 DE OCTUBRE_

> ¿Dónde se realizará la despedida a la altura de la historia del movimiento agobero?

0. Teatro Colón
1. Estadio de River
2. Plaza de Mayo
3. Movistar Arena ✔

Cita (literal): «Hay una fecha oficial del Movistar Arena»
Control sin video: eligio 3 (seguridad alta) → ACERTO, descartada
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