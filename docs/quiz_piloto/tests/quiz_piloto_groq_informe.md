# Piloto de quiz de retencion -- informe

Generado 2026-08-18 14:54 UTC · modelo `openai/gpt-oss-120b` · 2.0 min de ejecucion · version `quiz-0.7`

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
| Videos que fallaron por completo | 3 | 100 % |
| Preguntas generadas | 0 | 100 % |
| Con cita verificable (existe) | 0 | n/d |
| Cuya cita justifica la respuesta | 0 | n/d |
| Llegaron al control de trivialidad | 0 | n/d |
| Contestables sin ver el video | 0 | n/d de las evaluadas |
| **Sobreviven** | **0** | **n/d** |

Preguntas utiles por video: 0.0 de 10 generadas.

### Motivos de descarte

| motivo | n |
|---|---:|

### Tipo de pregunta

| tipo | generadas | sobreviven |
|---|---:|---:|

## 3. Ejemplos

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