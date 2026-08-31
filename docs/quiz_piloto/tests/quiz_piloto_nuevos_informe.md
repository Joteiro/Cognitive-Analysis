# Piloto de quiz de retencion -- informe

Generado 2026-08-30 19:49 UTC · modelo `gemini-2.5-flash` · 38.5 min de ejecucion · version `quiz-1.2`

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
| Videos que fallaron por completo | 2 | 7 % |
| Preguntas generadas | 163 | 100 % |
| Con cita verificable (existe) | 162 | 99 % |
| Cuya cita justifica la respuesta | 143 | 88 % |
| **Utilizables** (pasan los tres filtros) | **0** | **0 %** |

Preguntas utilizables por video: 0.0 de 6 generadas.

### Linea de base (sin ver el video)

| | n | |
|---|---:|---:|
| Items con linea de base medida | 0 | |
| La linea de base acerto | 0 | n/d |
| **Subconjunto dificil** (la linea de base fallo) | **0** | n/d |

Referencia: con cuatro opciones el azar acierta el 25 %. Una linea de base muy por
encima indica que el tema es de conocimiento publico, no que la pregunta este mal.

**Como calcular la retencion con esto, de dos formas complementarias:**

1. *Sobre el subconjunto dificil*: proporcion de aciertos de la persona entre los
   0 items que la linea de base fallo. Interpretacion directa, n mas chico.
2. *Sobre todos los items, descontando la base*: `(acierto_persona - acierto_base) /
   (1 - acierto_base)`, la correccion clasica por adivinacion. Usa todo el material,
   al precio de asumir que la linea de base del modelo aproxima la de la persona.

Informar las dos y compararlas es en si mismo un resultado: si divergen mucho, la
linea de base del modelo no representa bien a la persona.

### Motivos de descarte

| motivo | n |
|---|---:|
| control_fallo | 133 |
| cita_no_justifica | 19 |
| opciones_desbalanceadas | 10 |
| cita_no_verificable | 1 |

### Tipo de pregunta

| tipo | generadas | sobreviven |
|---|---:|---:|
| dato | 61 | 0 |
| argumento | 39 | 0 |
| relacion | 39 | 0 |
| definicion | 23 | 0 |
| descripcion | 1 | 0 |

## 3. Ejemplos

**DESCARTADA** — _EL DÍA DESPUÉS DE LA HUMILLACIÓN DE BOCA | #ParenLaMano Completo - 29/05 | VORTERIX_

> ¿Qué tipo de crisis tiene Boca, según la descripción de uno de los oradores?

0. Una crisis deportiva, con malos resultados en los últimos años.
1. Una crisis de identidad, que se arrastra desde hace una década. ✔
2. Una crisis institucional, por la falta de liderazgo en la dirigencia.
3. Una crisis económica, por la mala gestión de sus recursos.

Cita (literal): «River tiene una crisis deportiva y Boca tiene una crisis de identidad, boludo. Boca tiene una crisis de identidad hace 10 años.»
Descarte: `control_fallo: HTTP 403 (no se reintenta): {"error":{"message":"Access denied. Please check your network settings."}}`

**DESCARTADA** — _EL DÍA DESPUÉS DE LA HUMILLACIÓN DE BOCA | #ParenLaMano Completo - 29/05 | VORTERIX_

> ¿Según el orador, cuándo comenzó la crisis de identidad de Boca?

0. El 9 de diciembre, con la derrota en la final.
1. La noche de Independiente del Valle. ✔
2. Con la salida de Carlos Bianchi como director técnico.
3. Hace 10 años, con la llegada de una nueva dirigencia.

Cita (literal): «Empezó la noche de Independiente del Val, son años que vengo diciéndolo. La noche de Independiente del Valle a Boca le tiraron un tiro.»
Descarte: `control_fallo: HTTP 403 (no se reintenta): {"error":{"message":"Access denied. Please check your network settings."}}`

**DESCARTADA** — _EL DÍA DESPUÉS DE LA HUMILLACIÓN DE BOCA | #ParenLaMano Completo - 29/05 | VORTERIX_

> ¿Cuál es la principal crítica hacia la gestión de Riquelme, según los panelistas?

0. No logra generar una oposición política fuerte al macrismo dentro del club.
1. Se equivoca reiteradamente al elegir jugadores que no funcionan en el equipo. ✔
2. No se comunica adecuadamente con la prensa ni con los hinchas.
3. No asume la responsabilidad por las decisiones de los directores técnicos.

Cita (literal): «Él desde que llegó se vive equivocando reiteradamente reiteradas veces en lo mismo. Relme con todo cariño no le pega, no le pega a los jugadores.»
Descarte: `control_fallo: HTTP 403 (no se reintenta): {"error":{"message":"Access denied. Please check your network settings."}}`

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