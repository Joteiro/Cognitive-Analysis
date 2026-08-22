# Piloto de quiz de retencion -- informe

Generado 2026-08-17 10:01 UTC · modelo `openai/gpt-oss-120b` · 3.4 min de ejecucion · version `quiz-0.6`

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
| Cuya cita justifica la respuesta | 12 | 67 % |
| Llegaron al control de trivialidad | 12 | 67 % |
| Contestables sin ver el video | 9 | 75 % de las evaluadas |
| **Sobreviven** | **3** | **17 %** |

Preguntas utiles por video: 1.0 de 6 generadas.

### Motivos de descarte

| motivo | n |
|---|---:|
| contestable_sin_ver_el_video | 9 |
| cita_no_justifica | 6 |

### Tipo de pregunta

| tipo | generadas | sobreviven |
|---|---:|---:|
| dato | 8 | 2 |
| argumento | 5 | 0 |
| relacion | 4 | 1 |
| definicion | 1 | 0 |

## 3. Ejemplos

**SOBREVIVE** — _ASÍ CONTROLA SÁNCHEZ LOS MEDIOS mientras sus escándalos de corrupción se acumulan - @SoloFonseca_

> Según el vídeo, ¿cuántos pagos a medios realizó el gobierno que reveló El Confidencial?

0. 8,3 millones
1. 6900 ✔
2. 40 años
3. 500 millones

Cita (literal): «Por primera vez el confidencial accede a más de 6900 pagos a medios realizados desde Moncloa.»
Control sin video: eligio 0 (seguridad media) → fallo, sobrevive

**SOBREVIVE** — _TRUMP DESTRUYE LA IMAGEN DE EEUU y el turismo le está pasando factura - @SoloFonseca_

> Según el video, ¿por qué la llegada de turistas aéreos a EE. UU. descendió un 7,5% en enero de 2026?

0. Problemas de seguridad en los aeropuertos
1. Tensión global por la guerra comercial ✔
2. Restricciones sanitarias por el COVID‑19
3. Aumento de los precios de los vuelos

Cita (parcial_12_de_29): «El descenso se debe a la tensión global por la guerra comercial. ... en enero del presente año la llegada de turistas aéreos ... se registró un descenso de 7.5%»
Control sin video: eligio 3 (seguridad media) → fallo, sobrevive

**SOBREVIVE** — _TRUMP DESTRUYE LA IMAGEN DE EEUU y el turismo le está pasando factura - @SoloFonseca_

> ¿Qué evento cultural se promociona para el 3‑5 de julio de 2026 en Cartagena, España?

0. Feria Internacional de Turismo
1. Concierto de Badanny
2. Festival de Jazz de Murcia
3. Rock Imperium ✔

Cita (parcial_13_de_23): «Venga, tío, deja de pelártela... Empieza este viernes 3 de julio y termina el domingo 5 de julio... Rock Imperium en Cartagena, España»
Control sin video: eligio 0 (seguridad media) → fallo, sobrevive

**DESCARTADA** — _ASÍ CONTROLA SÁNCHEZ LOS MEDIOS mientras sus escándalos de corrupción se acumulan - @SoloFonseca_

> ¿Por qué el autor afirma que Pedro Sánchez ha convertido a RTVE en su propia televisión?

0. Porque aumenta la publicidad institucional en medios privados
1. Porque controla el presupuesto y la dirección de la cadena ✔
2. Porque reduce el número de canales públicos
3. Porque elimina la competencia desleal en el sector

Cita (literal): «Pedro Sánchez ha convertido a Radio Televisión Española en su propia televisión. Durante su gobierno, el presupuesto anual de la televisión pública ha duplicado el coste de la película más cara de la historia.»
Descarte: `cita_no_justifica`

**DESCARTADA** — _ASÍ CONTROLA SÁNCHEZ LOS MEDIOS mientras sus escándalos de corrupción se acumulan - @SoloFonseca_

> ¿Qué se entiende por "publicidad institucional" según el vídeo?

0. Anuncios de instituciones educativas en televisión
1. Dinero público que el gobierno destina a medios afines ✔
2. Campañas de concienciación sobre salud pública
3. Publicidad de empresas privadas en espacios públicos

Cita (literal): «Un gasto en publicidad que es totalmente opaco y que favorece a los medios de comunicación afines.»
Descarte: `cita_no_justifica`

**DESCARTADA** — _ASÍ CONTROLA SÁNCHEZ LOS MEDIOS mientras sus escándalos de corrupción se acumulan - @SoloFonseca_

> ¿Cómo evita el gobierno la transparencia al repartir la publicidad institucional?

0. Distribuyendo el dinero directamente entre los medios más grandes
1. Publicando los criterios de reparto en el Boletín Oficial del Estado
2. Utilizando una plataforma digital de acceso público
3. Contratando a una empresa externa que envía una lista de candidatos ✔

Cita (literal): «Una táctica que suele utilizar el gobierno es contratar a una empresa externa que se encargue del reparto. Así queda aún más opaco.»
Descarte: `cita_no_justifica`

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