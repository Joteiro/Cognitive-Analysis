# Piloto de quiz de retencion -- informe

Generado 2026-08-31 12:03 UTC · modelo `gemini-2.5-flash` · 8.9 min de ejecucion · version `quiz-1.2`

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
| Videos procesados | 7 | |
| Videos que fallaron por completo | 2 | 29 % |
| Preguntas generadas | 30 | 100 % |
| Con cita verificable (existe) | 30 | 100 % |
| Cuya cita justifica la respuesta | 22 | 73 % |
| **Utilizables** (pasan los tres filtros) | **19** | **63 %** |

Preguntas utilizables por video: 2.7 de 6 generadas.

### Linea de base (sin ver el video)

| | n | |
|---|---:|---:|
| Items con linea de base medida | 19 | |
| La linea de base acerto | 10 | 53 % |
| **Subconjunto dificil** (la linea de base fallo) | **9** | 47 % |

Referencia: con cuatro opciones el azar acierta el 25 %. Una linea de base muy por
encima indica que el tema es de conocimiento publico, no que la pregunta este mal.

**Como calcular la retencion con esto, de dos formas complementarias:**

1. *Sobre el subconjunto dificil*: proporcion de aciertos de la persona entre los
   9 items que la linea de base fallo. Interpretacion directa, n mas chico.
2. *Sobre todos los items, descontando la base*: `(acierto_persona - acierto_base) /
   (1 - acierto_base)`, la correccion clasica por adivinacion. Usa todo el material,
   al precio de asumir que la linea de base del modelo aproxima la de la persona.

Informar las dos y compararlas es en si mismo un resultado: si divergen mucho, la
linea de base del modelo no representa bien a la persona.

### Motivos de descarte

| motivo | n |
|---|---:|
| cita_no_justifica | 8 |
| opciones_desbalanceadas | 3 |

### Tipo de pregunta

| tipo | generadas | sobreviven |
|---|---:|---:|
| argumento | 12 | 7 |
| relacion | 8 | 6 |
| dato | 6 | 3 |
| definicion | 4 | 3 |

## 3. Ejemplos

**SOBREVIVE** — _¿Qué pasa si un NIÑO nunca escucha HABLAR a nadie? | La Ratonera 06_

> Según el podcast, ¿qué relación se establece entre ser bilingüe y la inteligencia?

0. Te hace más inteligente, lo cual es un claro ejemplo de la capacidad de definir la inteligencia en la ciencia.
1. No te hace más inteligente, pero se observan cambios cerebrales como mayor neuroplasticidad y rapidez en el cambio de tareas. ✔
2. No te hace más inteligente, y los cambios cerebrales observados no son significativos para el aprendizaje.
3. Te hace más inteligente, como lo demuestra la capacidad de aprender idiomas de forma más rápida y eficiente.

Cita (literal): «ser bilingüe no te hace necesariamente más inteligente, porque inteligente es algo que no sabemos definir del todo bien en ciencia, pero que es verdad que el cerebro eh se pueden observar cambios en gente bilingüe como que tienes más neuroplasticidad, que cambias más rápido de tarea a otra, etcétera»
Control sin video: eligio 1 (seguridad media) → ACERTO, descartada

**SOBREVIVE** — _¿Qué pasa si un NIÑO nunca escucha HABLAR a nadie? | La Ratonera 06_

> En la lengua Tariano del Amazonas, ¿para qué sirve el sufijo que se añade a una frase como "Cecilia regañó al perro"?

0. Para indicar si el hablante está de parte de Cecilia o del perro en el conflicto.
1. Para indicar cómo el hablante obtuvo esa información, si la vio, la escuchó o se la contaron. ✔
2. Para señalar si la acción ocurrió en el pasado reciente o en un pasado más lejano.
3. Para marcar el nivel de agresividad de la bronca, usando una escala del 2 al 16.

Cita (literal): «Si tú en Tariano dices, "Cecilia regañó al perro", tienes que añadirle un sufijo. ¿Para qué sirve ese sufijo? Ah, para indicar cómo sabes esa información. Si lo has visto tú, si lo has escuchado, si te lo han contado.»
Control sin video: eligio 1 (seguridad media) → ACERTO, descartada

**SOBREVIVE** — _¿Qué pasa si un NIÑO nunca escucha HABLAR a nadie? | La Ratonera 06_

> Según la explicación del podcast, ¿por qué las aplicaciones para aprender idiomas solo permiten avanzar hasta cierto punto?

0. Porque se centran solo en la repetición espaciada, lo que limita la comprensión profunda del idioma.
1. Porque el aprendizaje inicial es muy rápido, pero luego se estanca y se necesitan más recursos para seguir progresando. ✔
2. Porque no logran replicar la inmersión lingüística completa, que es esencial para el dominio avanzado.
3. Porque están diseñadas para enseñar solo las 1000 palabras básicas, dejando de lado la gramática compleja.

Cita (literal): «Porque el aprendizaje funciona de forma que tú aprendes mucho y muy rápido al principio, pero enseguida te estancas con lo que necesitas más cosas para aprender ese idioma.»
Control sin video: eligio 2 (seguridad media) → fallo, sobrevive

**DESCARTADA** — _¿Por qué Queremos Volver a la Luna?_

> Según el video, ¿qué aspecto de la superficie lunar la hace valiosa para entender la formación y evolución de planetas rocosos como la Tierra?

0. Su superficie, que ha permanecido casi inalterada por miles de millones de años. ✔
1. La presencia de agua líquida en grandes cantidades.
2. Su atmósfera densa que protege los registros geológicos.
3. Su intensa actividad geológica reciente.

Cita (literal): «Es decir, que algunas de sus partes apenas habrán cambiado desde que nació la Luna. Estudiarlas podrían ayudarnos a entender cómo se formaron y evolucionaron los planetas rocosos.»
Descarte: `cita_no_justifica`

**DESCARTADA** — _Intro to Geology: Crash Course Geology #1_

> Según la tradición oral Havasupai, ¿qué fenómeno geológico se describe en relación con el Gran Cañón?

0. Terremotos que formaron sus paredes.
1. Volcanes que crearon sus capas de roca.
2. Glaciares que lo erosionaron a lo largo del tiempo.
3. Un río que talló el Gran Cañón. ✔

Cita (literal): «Havasupai oral tradition describes a river carving the Grand Canyon—which it did.»
Descarte: `cita_no_justifica`

**DESCARTADA** — _Intro to Geology: Crash Course Geology #1_

> ¿Cuál fue la principal diferencia en el enfoque de los primeros geólogos occidentales en comparación con las culturas indígenas, según el video?

0. Los occidentales se basaron en la observación directa, mientras que los indígenas usaron la tradición oral.
1. Los occidentales exploraron fenómenos sin considerar sus interrelaciones, a diferencia de la visión indígena. ✔
2. Los occidentales se enfocaron en la clasificación de rocas, mientras que los indígenas estudiaron los movimientos de la Tierra.
3. Los occidentales priorizaron la explotación de recursos, mientras que los indígenas valoraban la preservación.

Cita (literal): «Rather than recognize the interconnectedness of different aspects of geology, early Western geologists largely explored questions about the earth without considering the relationships between those phenomena.»
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