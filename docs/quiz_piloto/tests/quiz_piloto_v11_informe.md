# Piloto de quiz de retencion -- informe

Generado 2026-08-19 15:04 UTC · modelo `gemini-2.5-flash` · 4.0 min de ejecucion · version `quiz-1.1`

## 1. Que se midio

Cada pregunta pasa **tres filtros de descarte** y despues se le mide una **linea
de base**. Los filtros: **anclaje** (la cita existe de verdad en la transcripcion:
control de invencion), **suficiencia** (la cita respalda la respuesta, con umbral
distinto segun el tipo de pregunta) y **equilibrio** (que la correcta no se delate
por su forma: unidad, magnitud o longitud).

La **linea de base** no descarta. Un modelo distinto del que genero las preguntas
intenta contestarlas sin la transcripcion, viendo solo lo que veria alguien que paso
por el titulo. Su acierto es el suelo contra el que hay que leer la retencion humana.

Por que no se descarta lo adivinable: sobre temas de conocimiento publico ninguna
pregunta bien construida es del todo inadivinable, porque si los cuatro distractores
son plausibles y del mismo tipo, lo unico que discrimina es cual es verdad en el
mundo -- y eso el modelo lo sabe. **No hace falta que cada item sea inadivinable:
hace falta conocer la tasa de acierto sin exposicion y descontarla.**

## 2. Numeros

| | n | sobre el total |
|---|---:|---:|
| Videos procesados | 3 | |
| Videos que fallaron por completo | 1 | 33 % |
| Preguntas generadas | 12 | 100 % |
| Con cita verificable (existe) | 12 | 100 % |
| Cuya cita justifica la respuesta | 11 | 92 % |
| **Utilizables** (pasan los tres filtros) | **11** | **92 %** |

Preguntas utilizables por video: 3.7 de 6 generadas.

### Linea de base (sin ver el video)

| | n | |
|---|---:|---:|
| Items con linea de base medida | 11 | |
| La linea de base acerto | 6 | 55 % |
| **Subconjunto dificil** (la linea de base fallo) | **5** | 45 % |

Referencia: con cuatro opciones el azar acierta el 25 %. Una linea de base muy por
encima indica que el tema es de conocimiento publico, no que la pregunta este mal.

**Como calcular la retencion con esto, de dos formas complementarias:**

1. *Sobre el subconjunto dificil*: proporcion de aciertos de la persona entre los
   5 items que la linea de base fallo. Interpretacion directa, n mas chico.
2. *Sobre todos los items, descontando la base*: `(acierto_persona - acierto_base) /
   (1 - acierto_base)`, la correccion clasica por adivinacion. Usa todo el material,
   al precio de asumir que la linea de base del modelo aproxima la de la persona.

Informar las dos y compararlas es en si mismo un resultado: si divergen mucho, la
linea de base del modelo no representa bien a la persona.

### Motivos de descarte

| motivo | n |
|---|---:|
| cita_no_justifica | 1 |

### Tipo de pregunta

| tipo | generadas | sobreviven |
|---|---:|---:|
| argumento | 4 | 4 |
| dato | 3 | 2 |
| relacion | 3 | 3 |
| definicion | 2 | 2 |

## 3. Ejemplos

**SOBREVIVE** — _ASÍ CONTROLA SÁNCHEZ LOS MEDIOS mientras sus escándalos de corrupción se acumulan - @SoloFonseca_

> Según el narrador, ¿cuánto ha aumentado el presupuesto de Radio Televisión Española desde que Pedro Sánchez llegó al poder?

0. Un 50%
1. Un 25% ✔
2. Un 15%
3. Un 100%

Cita (literal): «El presupuesto total de Radio Televisión Española para 2022 supera los 11 millones de euros. Pero es que en el año 2025 el presupuesto de Televisión Española alcanzó los 1220 millones de euros. Es decir, que desde que llegó Pedro Sánchez al poder, el presupuesto de Televisión Española ha aumentado un 25%.»
Control sin video: eligio 0 (seguridad media) → fallo, sobrevive

**SOBREVIVE** — _ASÍ CONTROLA SÁNCHEZ LOS MEDIOS mientras sus escándalos de corrupción se acumulan - @SoloFonseca_

> ¿Qué doctrina económica se menciona en el video como la justificación para que los países europeos fundaran empresas públicas de televisión?

0. El liberalismo de mercado.
1. El keynesianismo económico. ✔
2. El capitalismo privado.
3. La creación de monopolios estatales.

Cita (literal): «No olvidéis que aquellos años eran la era de oro del keinesenismo económico, una doctrina que promulga que hay unos sectores estratégicos que normalmente no son rentables en la economía privada y que por tanto el Estado tiene que invertir en ellos.»
Control sin video: eligio 1 (seguridad media) → ACERTO, descartada

**SOBREVIVE** — _ASÍ CONTROLA SÁNCHEZ LOS MEDIOS mientras sus escándalos de corrupción se acumulan - @SoloFonseca_

> Según el video, ¿cuál fue la primera consecuencia que sufrió Pedro J. Ramírez por destapar el escándalo de Los GAL cuando dirigía el diario 16?

0. Le tendieron una trampa para grabarlo en una situación comprometida.
1. El gobierno presionó para que lo despidieran de su periódico. ✔
2. Fue galardonado con un premio por su valentía periodística.
3. Se le ofreció un puesto de alto nivel en la administración pública.

Cita (literal): «Sin embargo, ¿qué creéis que le hicieron a Pedro J Ramírez? ¿Le dieron un puliter? ¿Le dieron una medalla? Pues no. El gobierno presionó para que lo echaran de su propio periódico.»
Control sin video: eligio 1 (seguridad media) → ACERTO, descartada

**DESCARTADA** — _RUBENS: RICO, EXCÉNTRICO, FAMOSO Y MUCHO MÁS..._

> Según la introducción del video, ¿qué característica peculiar se menciona sobre la forma en que Rubens pintaba a los santos?

0. Como figuras atléticas recién salidas del gimnasio. ✔
1. De manera idealizada, sin imperfecciones físicas.
2. Con un estilo sombrío y melancólico.
3. Con expresiones de profunda devoción religiosa.

Cita (literal): «Pintaba los santos como si acabasen de salir del gimnasio. Adoraba la celulitis y la pintaba maravillosamente bien.»
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