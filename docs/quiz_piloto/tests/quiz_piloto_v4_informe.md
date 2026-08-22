# Piloto de quiz de retencion -- informe

Generado 2026-08-17 14:18 UTC · modelo `openai/gpt-oss-120b` · 4.5 min de ejecucion · version `quiz-0.7`

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
| Videos que fallaron por completo | 1 | 33 % |
| Preguntas generadas | 12 | 100 % |
| Con cita verificable (existe) | 12 | 100 % |
| Cuya cita justifica la respuesta | 12 | 100 % |
| Llegaron al control de trivialidad | 12 | 100 % |
| Contestables sin ver el video | 9 | 75 % de las evaluadas |
| **Sobreviven** | **3** | **25 %** |

Preguntas utiles por video: 1.0 de 6 generadas.

### Motivos de descarte

| motivo | n |
|---|---:|
| contestable_sin_ver_el_video | 9 |

### Tipo de pregunta

| tipo | generadas | sobreviven |
|---|---:|---:|
| dato | 5 | 0 |
| argumento | 3 | 2 |
| relacion | 2 | 0 |
| definicion | 2 | 1 |

## 3. Ejemplos

**SOBREVIVE** — _ASÍ CONTROLA SÁNCHEZ LOS MEDIOS mientras sus escándalos de corrupción se acumulan - @SoloFonseca_

> Según el hablante, ¿por qué el gobierno prefiere dar dinero a ciertos medios?

0. para evitar dar explicaciones
1. porque le son más afines ✔
2. para controlar la versión
3. para elegir su dirección en pandemia

Cita (literal): «Y como ya os podéis imaginar, el gobierno prefiere darle el dinero a los medios que le son más afines.»
Control sin video: eligio 2 (seguridad media) → fallo, sobrevive

**SOBREVIVE** — _ASÍ CONTROLA SÁNCHEZ LOS MEDIOS mientras sus escándalos de corrupción se acumulan - @SoloFonseca_

> ¿Qué tipo de vídeos se describen como “Only FS” en el programa?

0. una opinión que quiero soltar del momento
1. una noticia que acaba de pasar
2. vídeos normales
3. vídeos con mayor latencia, vídeos perennes ✔

Cita (literal): «Los vídeos como este que acabáis de ver están pensados para ser vídeos con mayor latencia, vídeos perennes que se llama.»
Control sin video: eligio 0 (seguridad media) → fallo, sobrevive

**SOBREVIVE** — _ASÍ CONTROLA SÁNCHEZ LOS MEDIOS mientras sus escándalos de corrupción se acumulan - @SoloFonseca_

> Según el presentador, ¿por qué la distribución de publicidad institucional no es pública?

0. para duplicar el presupuesto
1. para controlar la versión
2. para elegir su dirección en pandemia
3. porque no se está contratando a los medios directamente ✔

Cita (literal): «De esta forma, esta distribución no es pública porque no se está contratando a los medios directamente y así es como el gobierno se evita tener que dar explicaciones.»
Control sin video: eligio 1 (seguridad media) → fallo, sobrevive

**DESCARTADA** — _ASÍ CONTROLA SÁNCHEZ LOS MEDIOS mientras sus escándalos de corrupción se acumulan - @SoloFonseca_

> ¿Cuántos pagos a medios accedió por primera vez El Confidencial según el video?

0. 40 años
1. más de 6900 pagos ✔
2. cerca de 500 millones de euros
3. 8,3 millones de euros

Cita (literal): «Por primera vez el confidencial accede a más de 6900 pagos a medios realizados desde Moncloa.»
Control sin video: eligio 1 (seguridad media) → ACERTO, descartada
Descarte: `contestable_sin_ver_el_video`

**DESCARTADA** — _ASÍ CONTROLA SÁNCHEZ LOS MEDIOS mientras sus escándalos de corrupción se acumulan - @SoloFonseca_

> ¿Hasta cuánto dinero recibió la Cadena SER según la información mostrada?

0. más de 6900 pagos
1. 8,3 millones de euros ✔
2. 40 años
3. cerca de 500 millones de euros

Cita (literal): «la izquierdista Cadena SER ha recibido hasta 8,3 millones de euros, más del doble que la conservadora COPE.»
Control sin video: eligio 1 (seguridad media) → ACERTO, descartada
Descarte: `contestable_sin_ver_el_video`

**DESCARTADA** — _ASÍ CONTROLA SÁNCHEZ LOS MEDIOS mientras sus escándalos de corrupción se acumulan - @SoloFonseca_

> ¿Qué ocurre cuando un medio “se desmarca” según el relato?

0. se le pone publicidad institucional
1. se le cambia el titular
2. se duplica el presupuesto
3. empieza el festival, menos foco, menos voz o directamente a callar ✔

Cita (literal): «Y si alguno se desmarca, empieza el festival, menos foco, menos voz o directamente a callar.»
Control sin video: eligio 3 (seguridad media) → ACERTO, descartada
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