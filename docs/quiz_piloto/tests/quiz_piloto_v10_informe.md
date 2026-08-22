# Piloto de quiz de retencion -- informe

Generado 2026-08-19 14:13 UTC · modelo `gemini-2.5-flash` · 4.0 min de ejecucion · version `quiz-1.0`

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
| Llegaron al control de trivialidad | 13 | 72 % |
| Contestables sin ver el video | 10 | 77 % de las evaluadas |
| **Sobreviven** | **3** | **17 %** |

Preguntas utiles por video: 1.0 de 6 generadas.

### Motivos de descarte

| motivo | n |
|---|---:|
| contestable_sin_ver_el_video | 10 |
| opciones_desbalanceadas | 4 |
| cita_no_justifica | 1 |

### Tipo de pregunta

| tipo | generadas | sobreviven |
|---|---:|---:|
| relacion | 6 | 1 |
| dato | 4 | 1 |
| definicion | 4 | 1 |
| argumento | 3 | 0 |
| comprension | 1 | 0 |

## 3. Ejemplos

**SOBREVIVE** — _ASÍ CONTROLA SÁNCHEZ LOS MEDIOS mientras sus escándalos de corrupción se acumulan - @SoloFonseca_

> ¿Cómo se describe el proceso de reparto de la publicidad institucional por parte del gobierno en España?

0. Es un proceso totalmente opaco, sin criterios de reparto ni límites conocidos. ✔
1. Se basa en criterios públicos y límites claros para evitar favoritismos entre los medios.
2. Prioriza a los medios con mayor audiencia para maximizar el impacto de los anuncios.
3. Está regulado por una empresa externa que garantiza la transparencia en los pagos.

Cita (literal): «el reparto de publicidad institucional en España es un proceso totalmente opaco. Quiero decir, no se conocen los criterios de reparto ni sus límites»
Control sin video: eligio 1 (seguridad alta) → fallo, sobrevive

**SOBREVIVE** — _TRUMP DESTRUYE LA IMAGEN DE EEUU y el turismo le está pasando factura - @SoloFonseca_

> ¿Qué nueva norma ha propuesto la administración estadounidense para obligar a los visitantes de decenas de países a entregar cierta información antes de entrar al país?

0. Presentar un expediente criminal detallado.
1. Proporcionar un historial de viajes de los últimos 10 años.
2. Demostrar solvencia económica para cubrir toda la estancia.
3. Entregar 5 años de actividad en redes sociales. ✔

Cita (literal): «ha propuesto una nueva norma para obligar a los visitantes de decenas de países a entregar atentos 5 años de actividad en redes sociales.»
Control sin video: eligio 2 (seguridad media) → fallo, sobrevive

**SOBREVIVE** — _RUBENS: RICO, EXCÉNTRICO, FAMOSO Y MUCHO MÁS..._

> ¿Cuál de los siguientes cambios realizó Rubens al copiar el cuadro de Adán y Eva de Tiziano?

0. Añadió un loro rojo en la esquina superior izquierda del cuadro. ✔
1. Eliminó por completo las hojas que cubrían los genitales de Adán y Eva.
2. Hizo las figuras de Adán y Eva más rígidas y estáticas.
3. Utilizó colores más apagados y menos vibrantes que el original.

Cita (parcial_10_de_17): «Pero es que también en una esquina en la esquina superior izquierda, él añade un loro rojo.»
Control sin video: eligio 1 (seguridad media) → fallo, sobrevive

**DESCARTADA** — _ASÍ CONTROLA SÁNCHEZ LOS MEDIOS mientras sus escándalos de corrupción se acumulan - @SoloFonseca_

> ¿Qué acciones tomó Pedro Sánchez para consolidar su control sobre Radio Televisión Española, según el narrador?

0. Privatizó la dirección y duplicó el coste de la película más cara.
1. Aumentó el presupuesto anual y redujo la plantilla de forma drástica.
2. Modificó el organigrama para incluir a la oposición y redujo el presupuesto.
3. Cambió la ley para poder elegir a su dirección y disparó la plantilla con gente leal. ✔

Cita (literal): «cambió la ley para poder elegir a su dirección en mitad de la pandemia. Además, ha disparado la plantilla con gente muy leal.»
Control sin video: eligio 3 (seguridad media) → ACERTO, descartada
Descarte: `contestable_sin_ver_el_video`

**DESCARTADA** — _ASÍ CONTROLA SÁNCHEZ LOS MEDIOS mientras sus escándalos de corrupción se acumulan - @SoloFonseca_

> ¿Qué grupo fue identificado como pionero en la política de televisión pública en la década de los años 30?

0. Los estadounidenses.
1. Los países europeos en general.
2. El Reino Unido y la BBC.
3. Los nazis. ✔

Cita (literal): «La televisión pública apareció en la década de los años 30. Y venga, a ver si adivináis quiénes fueron los pioneros en esta política. Los nazis.»
Descarte: `opciones_desbalanceadas`

**DESCARTADA** — _ASÍ CONTROLA SÁNCHEZ LOS MEDIOS mientras sus escándalos de corrupción se acumulan - @SoloFonseca_

> ¿Cuál fue la principal justificación económica que los países europeos encontraron para crear empresas públicas de televisión?

0. La doctrina keynesiana que indicaba la necesidad de inversión estatal en sectores estratégicos no rentables para privados. ✔
1. La escasez de frecuencias para emitir imagen en vivo, lo que requería monopolios estatales.
2. El deseo de imitar el modelo de éxito de Estados Unidos en la creación de medios privados.
3. La necesidad de controlar la información para evitar la anarquía y la libertad de expresión.

Cita (literal): «una doctrina que promulga que hay unos sectores estratégicos que normalmente no son rentables en la economía privada y que por tanto el Estado tiene que invertir en ellos.»
Control sin video: eligio 0 (seguridad alta) → ACERTO, descartada
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