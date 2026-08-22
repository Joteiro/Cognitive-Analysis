# Piloto de quiz de retencion -- informe

Generado 2026-08-19 16:39 UTC · modelo `gemini-2.5-flash` · 8.0 min de ejecucion · version `quiz-1.2`

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
| Videos procesados | 30 | |
| Videos que fallaron por completo | 0 | 0 % |
| Preguntas generadas | 180 | 100 % |
| Con cita verificable (existe) | 179 | 99 % |
| Cuya cita justifica la respuesta | 172 | 96 % |
| **Utilizables** (pasan los tres filtros) | **158** | **88 %** |

Preguntas utilizables por video: 5.3 de 6 generadas.

### Linea de base (sin ver el video)

| | n | |
|---|---:|---:|
| Items con linea de base medida | 158 | |
| La linea de base acerto | 98 | 62 % |
| **Subconjunto dificil** (la linea de base fallo) | **60** | 38 % |

Referencia: con cuatro opciones el azar acierta el 25 %. Una linea de base muy por
encima indica que el tema es de conocimiento publico, no que la pregunta este mal.

**Como calcular la retencion con esto, de dos formas complementarias:**

1. *Sobre el subconjunto dificil*: proporcion de aciertos de la persona entre los
   60 items que la linea de base fallo. Interpretacion directa, n mas chico.
2. *Sobre todos los items, descontando la base*: `(acierto_persona - acierto_base) /
   (1 - acierto_base)`, la correccion clasica por adivinacion. Usa todo el material,
   al precio de asumir que la linea de base del modelo aproxima la de la persona.

Informar las dos y compararlas es en si mismo un resultado: si divergen mucho, la
linea de base del modelo no representa bien a la persona.

### Motivos de descarte

| motivo | n |
|---|---:|
| opciones_desbalanceadas | 13 |
| cita_no_justifica | 7 |
| control_fallo | 1 |
| opciones_duplicadas | 1 |

### Tipo de pregunta

| tipo | generadas | sobreviven |
|---|---:|---:|
| relacion | 55 | 52 |
| dato | 50 | 32 |
| argumento | 47 | 47 |
| definicion | 26 | 25 |
| opinion | 1 | 1 |
| comprension | 1 | 1 |

## 3. Ejemplos

**SOBREVIVE** — _ASÍ CONTROLA SÁNCHEZ LOS MEDIOS mientras sus escándalos de corrupción se acumulan - @SoloFonseca_

> Según el narrador, ¿qué medida específica tomó Pedro Sánchez para asegurar el control sobre la dirección de Radio Televisión Española?

0. Duplicó el presupuesto anual de la televisión pública para aumentar su influencia.
1. Aprobó una ley para cambiar el órgano de gobierno de RTVE durante una tragedia. ✔
2. Contrató a David Broncano para un programa de máxima audiencia en la televisión pública.
3. Incrementó la plantilla de RTVE con más de 500 personas leales a su gobierno.

Cita (parcial_11_de_21): «el gobierno aprovechó la tragedia para aprobar una única ley... una ley para cambiar el órgano de gobierno de Televisión Española.»
Control sin video: eligio 1 (seguridad alta) → ACERTO, descartada

**SOBREVIVE** — _ASÍ CONTROLA SÁNCHEZ LOS MEDIOS mientras sus escándalos de corrupción se acumulan - @SoloFonseca_

> Según el narrador, ¿cuál fue la principal justificación que encontraron los países europeos para crear monopolios estatales de televisión?

0. La necesidad de una fuente de información pura sin corrupción capitalista.
1. La tecnología y la doctrina del keynesianismo económico. ✔
2. El deseo de promover la cultura nacional y la educación cívica.
3. La competencia desleal de las cadenas privadas estadounidenses.

Cita (literal): «la excusa que encontraron fue la tecnología. No olvidéis que aquellos años eran la era de oro del keinesenismo económico.»
Control sin video: eligio 2 (seguridad media) → fallo, sobrevive

**SOBREVIVE** — _ASÍ CONTROLA SÁNCHEZ LOS MEDIOS mientras sus escándalos de corrupción se acumulan - @SoloFonseca_

> Según el narrador, ¿en qué porcentaje aumentó el presupuesto de Televisión Española desde que Pedro Sánchez asumió el poder?

0. Un 10%.
1. Un 50%.
2. Se duplicó.
3. Un 25%. ✔

Cita (literal): «desde que llegó Pedro Sánchez al poder, el presupuesto de Televisión Española ha aumentado un 25%.»
Control sin video: eligio 2 (seguridad media) → fallo, sobrevive

**DESCARTADA** — _ASÍ CONTROLA SÁNCHEZ LOS MEDIOS mientras sus escándalos de corrupción se acumulan - @SoloFonseca_

> Según el narrador, ¿quiénes fueron los pioneros en la política de televisión pública durante la década de los años 30?

0. Los países europeos.
1. Los nazis. ✔
2. Las empresas privadas de Estados Unidos.
3. El gobierno de España.

Cita (literal): «La televisión pública apareció en la década de los años 30. Y venga, a ver si adivináis quiénes fueron los pioneros en esta política. Los nazis.»
Descarte: `opciones_desbalanceadas`

**DESCARTADA** — _A TRUMP SE LE ACABA EL TIEMPO estas son las SALIDAS que TIENE - @SoloFonseca_

> En la metáfora del póker utilizada por el narrador para explicar el conflicto en el estrecho de Ormuz, ¿qué representan "las ciegas"?

0. Los aliados de la Casa Blanca en la región.
1. Las bases militares estadounidenses en Oriente Medio.
2. Las fichas obligatorias que se ponen al principio de cada ronda.
3. Los buques mercantes que transitan por el estrecho. ✔

Cita (literal): «Las ciegas en el póker son las fichas obligatorias que se tienen que poner al principio de cada ronda antes de ver las cartas. En este caso, las ciegas son los buges marcantes.»
Descarte: `cita_no_justifica`

**DESCARTADA** — _A TRUMP SE LE ACABA EL TIEMPO estas son las SALIDAS que TIENE - @SoloFonseca_

> ¿Cómo describe oficialmente Irán los pagos exigidos por el tránsito de buques en el estrecho de Ormuz, según su portavoz de exteriores citado en el video?

0. "servicios de navegación" y "medidas de protección medioambiental del estrecho" ✔
1. "un sistema de caseta de peaje" y "una herramienta de diplomacia"
2. "un acuerdo de 14 puntos" y "un trazado pactado"
3. "un ranking político" y "un favor que se cobra"

Cita (literal): «Según su portavoz de exteriores son, atentos, servicios de navegación y lo mejor de todo, medidas de protección medioambiental del estrecho.»
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