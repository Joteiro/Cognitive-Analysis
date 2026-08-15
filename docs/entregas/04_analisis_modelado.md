# Entrega 4 — Diseño del análisis y estrategia de modelado

**Proyecto:** Nutri-Score de Contenidos (repositorio `Cognitive Analysis`)
**Autor:** Juan Taraciuk
**Fecha:** agosto de 2026

> **Nota de incrementalidad.** Esta entrega no sustituye ninguna anterior. Introduce dos
> elementos nuevos respecto de la Entrega 3 y corrige un hallazgo sobre una etiqueta ya
> existente; ambos cambios están señalados explícitamente en §4.4 y §8.6.

---

## 1. Problema que se busca resolver

### 1.1. Qué ocurre actualmente y por qué es un problema

Consumimos varias horas diarias de video sin ninguna información sobre qué nos aporta.
El envase de un alimento declara proteínas, azúcares y calorías; un video de YouTube
declara duración, vistas y "me gusta" — tres cifras que describen la **popularidad del
canal**, no la **composición del contenido**.

Las entregas anteriores construyeron la respuesta a esa carencia: un panel de ocho
descriptores verificables por video (densidad de cifras, ritmo, riqueza léxica,
atribución de fuentes, trazabilidad, correspondencia entre promesa y contenido, carga
promocional, conectores), calculados sobre la transcripción y expresados como percentiles
respecto de un corpus público de referencia de 410 videos muestreado por estratos.

**El problema que queda abierto, y que esta entrega aborda, es que nadie ha demostrado
que esos ocho descriptores tengan relación con nada que le ocurra al espectador.** Son una
descripción honesta de la composición del contenido, igual que una etiqueta nutricional.
Pero una etiqueta nutricional sirve porque existe evidencia externa de que las grasas
saturadas hacen algo en el organismo. Aquí esa evidencia no existe todavía: el proyecto
mide composición y no ha medido nunca efecto.

Esa carencia no es cosmética. En la revisión de la Entrega 2 se señaló que el riesgo
principal del proyecto es **definir "valor cognitivo" de forma circular**: si el criterio
de valor sale de una rúbrica escrita por el propio autor, o de la opinión de un modelo de
lenguaje, el sistema se limita a confirmar sus propias premisas. Por ese motivo se
eliminó del proyecto la letra A–E agregada: transmitía autoridad sobre una base subjetiva.

### 1.2. Quién usa el resultado y para qué decisión

| Usuario | Decisión que toma | Qué necesita saber |
|---|---|---|
| Espectador | Si empieza el video, y cuánto tiempo le dedica | Si un contenido con este perfil de descriptores le suele quedar o se le evapora |
| Espectador (retrospectivo) | Cómo reequilibra su dieta de consumo | Cuánto de lo que consumió retuvo, por formato y por periodo |
| Creador de contenido | Qué rasgos editoriales refuerza | Qué descriptores se asocian con que su audiencia recuerde el contenido |

### 1.3. Qué resultado concreto haría útil al proyecto

Un enunciado verificable de la forma:

> «De los ocho descriptores del panel, *estos* predicen la retención medida a x días
> **mejor de lo que la predice la simple duración del video**, con esta magnitud y este
> intervalo de confianza.»

La cláusula en negrita es la que da sentido a todo el trabajo. El primer scorer del
proyecto (v1.0) tenía una correlación de **0,73 con el logaritmo de la duración**: la
mitad de su varianza era duración disfrazada de calidad. Todo el rediseño posterior
consistió en construir descriptores que *no* fueran un cronómetro encubierto (hoy ninguno
supera un |r| de 0,35 con log(duración)). Si ahora resultara que la retención se predice
igual de bien con un cronómetro, el panel no aportaría nada por encima de mirar cuántos
minutos dura el video, y habría que decirlo.

---

## 2. Análisis de datos planteado y utilidad esperada

### 2.1. Preguntas que se quieren responder

| # | Pregunta | Momento | Estado |
|---|---|---|---|
| P1 | ¿Los descriptores están confundidos con la duración? | Antes del modelado | **Respondida** |
| P2 | ¿Los cortes de la escala deben ser globales o por formato? | Antes | **Respondida** |
| P3 | ¿Cómo es la dieta de consumo real y qué sesgos tiene? | Antes | **Respondida** |
| P4 | ¿El instrumento de medición (el quiz) produce preguntas válidas? | Antes | **Respondida (piloto)** |
| P5 | ¿La retención varía más entre videos o entre personas? | Antes del modelado | Pendiente de datos |
| P6 | ¿Qué descriptores se asocian con mayor retención, y con qué signo? | Modelado | Pendiente de datos |
| P7 | ¿Cómo decae la retención con los días transcurridos? | Durante | Pendiente de datos |
| P8 | ¿El modelo falla de forma distinta según formato o duración? | Después | Pendiente de datos |

### 2.2. Análisis ya ejecutados (con resultado)

**P1 — Confusión con la duración.** Para cada indicador candidato se calculó su
correlación con log(duración) sobre datos propios antes de aceptarlo en el panel. El
procedimiento descartó indicadores con evidencia, no por intuición:

- `hapax_ratio`: r = **−0,82**. Duración disfrazada. Fuera.
- `preguntas_1000w`: r = 0,70, y además depende del transcriptor automático. Fuera.
- Enlaces externos normalizados por minuto: r = −0,68; **en valor absoluto baja a −0,05**.
  De ahí una regla general del proyecto: se normaliza por minuto lo que ocurre *durante*
  el video, y queda en absoluto lo que existe *alrededor* (descripción, etiquetas).
- `marcadores_estructura` con ordinales sueltos: los resúmenes de fútbol encabezaban el
  ranking ("el segundo gol", "primer tiempo"). Depurado sigue en r = −0,50. Fuera.

Los ocho supervivientes tienen todos |r| ≤ 0,35 con log(duración) y una correlación mutua
máxima de 0,53.

**P2 — Ámbito de la escala.** Se resolvió con una **prueba de permutación** (2.000
remezclas de las etiquetas de formato). Los cortes por formato siempre se ven distintos;
la pregunta es si se ven *más* distintos que al remezclar al azar. El estadístico se
adapta al tipo de descriptor: rango del percentil 33 para los continuos, y rango de la
tasa de presencia para los que tienen más de un tercio del corpus en cero exacto (ahí el
tercil no existe y el p33 vale 0 en todos los grupos).

**P3 — Dieta de consumo.** 81 minutos diarios de media, mediana de un día de frescura,
45 de 94 videos vistos en ráfaga (menos de 30 minutos desde el anterior), 64 % de los
minutos en contenido perecedero, e índice HHI de concentración de canal 0,216 con un
único canal al 41 %. El hallazgo metodológico relevante: **cambiar el denominador cambia
la conclusión**. Por número de videos domina Deporte (37 %); por minutos consumidos domina
Entretenimiento (46,6 %). Es exactamente la diferencia entre "por porción" y "por 100 g"
de un envase, y obliga a que el dashboard declare siempre cuál está usando.

**P4 — Validez del instrumento.** Ver §2.3.

### 2.3. Análisis del instrumento de medición (piloto ya ejecutado)

Antes de poder usar la retención como variable objetivo hay que demostrar que se puede
medir. Se construyó un generador de preguntas a partir de las transcripciones y se probó
sobre una muestra de 5 videos repartidos por todo el rango de duración. Cada pregunta pasa
**tres controles automáticos e independientes**:

1. **Anclaje** — la cita textual que el modelo dice haber extraído debe existir realmente
   en la transcripción. Filtra invención.
2. **Suficiencia** — esa cita debe *contener* la respuesta, no sugerirla. Anclar no es
   justificar.
3. **Trivialidad** — el mismo modelo intenta contestar **sin la transcripción**, viendo
   sólo lo que vería alguien que pasó por el título en su historial. Si acierta, la
   pregunta no medía retención y se descarta. **Es el grupo de control del instrumento.**

| Métrica | Versión 1 | Versión 2 | Lectura |
|---|---:|---:|---|
| Preguntas generadas | 20 | 30 | |
| Cita inventada | 15 % | 7 % | El control de anclaje se justifica solo |
| Cita que no justifica la respuesta | (no medido) | 21 % | 1 de cada 5 "ancladas" no servía |
| Contestables sin ver el video | 47 % | 41 % | Referencia de azar: 25 % |
| **Preguntas útiles por video** | **1,8** | **2,6** | Mínimo operativo fijado: 2 |

El diagnóstico de la versión 1 fue que el 47 % de trivialidad **no venía de fuga por el
título** (sólo 1 de 20 respuestas aparecía en él) sino del **diseño de los distractores**:
cuando la opción correcta es la que "suena mejor" de las cuatro, el conocimiento general
basta. La corrección aplicada en la versión 2 fue exigir que los distractores sean
**elementos que sí aparecen en la transcripción pero no contestan esa pregunta**, de modo
que las cuatro opciones sean igual de plausibles para quien no vio el video.

Un dato relevante para interpretar la variable objetivo: de las 30 preguntas de la versión
2, **19 son de tipo "dato"** y sólo 2 de "relación". El instrumento mide sobre todo
**recuerdo factual**, no comprensión profunda. La variable se llamará "retención" y no
"aprendizaje" por esa razón.

### 2.4. Análisis previstos sobre la variable objetivo

- **Distribución de la proporción de aciertos**: efectos techo y suelo, proporción de
  quizzes con 0 y con 100 % de aciertos, para decidir entre regresión binomial y
  binarización.
- **Descomposición de la varianza (P5)**: modelo nulo con efectos aleatorios por video y
  por persona, para saber cuánta de la variabilidad es atribuible al contenido y cuánta a
  quién lo vio. Si casi toda es de la persona, ningún descriptor del video va a predecir
  nada y conviene saberlo antes de modelar.
- **Curva de olvido (P7)**: retención frente a días transcurridos. Hipótesis de decaimiento
  logarítmico; determina también cuál es el retardo óptimo del quiz en el producto.
- **Relación descriptor–retención (P6)**: dispersión y correlación de Spearman de cada uno
  de los ocho, con la duración señalada en el gráfico como control visual.
- **Balance y cobertura**: número de observaciones por formato y por estrato de duración,
  con un piso explícito de n por celda para no informar medias de dos videos.

### 2.5. Qué se incorpora al MVP

- En el **panel de la extensión**: una línea comparativa del tipo «videos con este perfil
  se recuerdan por encima / por debajo de la media», con su intervalo y el n en que se
  basa. Nunca una letra ni un semáforo.
- En el **dashboard de dieta**, ya construido: dos vistas nuevas — retención por formato y
  curva de olvido — junto a los indicadores existentes de minutos, frescura y concentración
  de canal.

---

## 3. Tipo de modelos que se van a plantear

### 3.1. Tipo de tarea

**Regresión sobre una proporción acotada.** La variable objetivo es «k aciertos sobre n
preguntas», no un continuo libre. Esto tiene dos consecuencias que descartan el reflejo de
tirar un OLS:

1. Un modelo lineal ordinario puede predecir valores fuera de [0, 1], que no significan nada.
2. Un OLS trata igual un 2 de 3 que un 20 de 30, cuando el segundo es muchísimo más
   informativo. Un modelo binomial pondera por el número de preguntas de forma natural.

Por eso la familia elegida es un **GLM binomial con enlace logit** (equivalentemente,
regresión beta si se trabaja con la proporción directamente). Es, en el fondo, una
regresión logística sobre "aciertos frente a fallos".

### 3.2. Alternativas a comparar

| Alternativa | Tipo | Por qué se plantea | Limitación principal |
|---|---|---|---|
| **Baseline 0** | Media global de retención | Referencia mínima obligatoria: cualquier modelo debe superarla | Ignora todo; trivial de batir |
| **Baseline 1 — el que importa** | GLM binomial con **log(duración)** como único predictor | Todo el proyecto nace de descubrir que el score v1 era duración disfrazada (r = 0,73). Si el panel no le gana a un cronómetro, no aporta nada | Es un baseline deliberadamente difícil: la duración es un predictor real de la fatiga y del olvido |
| **Candidato 1** | GLM binomial con los 8 descriptores (en percentil) + controles | Interpretable: cada coeficiente tiene signo y magnitud legibles, que es lo que el proyecto necesita comunicar al usuario. Admite regularización (elastic net) para el n pequeño | No captura interacciones ni no linealidades |
| **Candidato 2** | Gradient boosting sobre los mismos predictores | Comprueba si una mayor flexibilidad mejora de verdad, o si la relación es esencialmente lineal | Con decenas de filas y 8+ predictores, sobreajuste casi garantizado; sólo es admisible con validación por grupos y comparación honesta contra el GLM |

Se descartan explícitamente las redes neuronales y cualquier enfoque que requiera miles de
observaciones: el volumen realista del estudio es de decenas de filas (§8.2). También se
descarta usar el texto de la transcripción como entrada directa (embeddings o bolsa de
palabras): metería miles de dimensiones frente a decenas de filas, y además rompería la
interpretabilidad que es el núcleo del producto.

---

## 4. Datos de entrada del análisis y los modelos

### 4.1. Capa gold existente

`content_features` — tabla materializada en PostgreSQL, **una fila por video**, clave
`content_item_id`. Es la capa gold definida en la Entrega 3. Contiene los 8 descriptores en
valor bruto y en percentil respecto del corpus de referencia, el gate de aptitud, las 9
etiquetas deterministas y el bloque `panel` en JSONB.

### 4.2. Entradas del modelo

| Entrada | Descripción | Granularidad / tipo | Uso |
|---|---|---|---|
| `gold_retencion` | Dataset de modelado (§4.4) | Una fila por (persona, video) | Fuente principal |
| `ritmo_ppm_pct` … `cobertura_titulo_pct` | Los 8 descriptores en **percentil** del corpus de referencia | Numérica 0–100 | Features principales |
| `log_duracion` | Logaritmo de la duración en segundos | Numérica | **Baseline 1** y control |
| `dias_transcurridos` | Días entre el visionado y el quiz | Numérica | Control (curva de olvido) |
| `formato` | Estrato temático del video | Categórica (4 niveles), one-hot | Control y análisis por segmento |
| `n_preguntas` | Preguntas supervivientes del quiz | Entera | Peso del binomial |
| `transcripcion_recortada` | Si la transcripción se muestreó por exceder 3.000 palabras | Booleana | Control de calidad del instrumento |
| `persona_id` | Identificador seudonimizado del respondiente | Categórica | Efecto aleatorio / variable de agrupación |

**Se usan los descriptores en percentil y no en bruto** porque las unidades son
heterogéneas (palabras/minuto frente a un índice 0–1) y porque el percentil es lo que el
producto ya muestra al usuario: modelar sobre lo mismo que se comunica evita una brecha
entre lo que se valida y lo que se enseña.

### 4.3. Variables excluidas y motivo

| Variable | Motivo de exclusión |
|---|---|
| `view_count`, `like_count`, `comment_count` | Miden el canal y el algoritmo de recomendación, no el contenido. Decisión tomada en la Entrega 2. Único uso admisible: control negativo |
| Texto crudo de la transcripción | Miles de dimensiones frente a decenas de filas; destruye la interpretabilidad. Se usa sólo para *generar* el quiz |
| `score_letter`, `score_numeric` (scorer v1.0) | Retirados del proyecto: transmitían autoridad sobre base subjetiva y estaban confundidos con la duración |
| Historial de visionado de terceros | Dato personal sensible: se minimiza, se consiente y se permite borrado |
| Cualquier métrica posterior a la respuesta | Riesgo de fuga (§8.3) |

### 4.4. Estructuras nuevas respecto de la Entrega 3

> **Cambio declarado.** La Entrega 3 definió una única tabla gold (`content_features`),
> suficiente para un sistema descriptivo. Medir retención obliga a añadir tres estructuras,
> porque aparece una entidad nueva —la persona— que antes no existía en el modelo de datos.

| Tabla | Granularidad | Contenido |
|---|---|---|
| `quiz_preguntas` | Una fila por pregunta generada | Enunciado, 4 opciones, índice correcto, cita, tipo, y el resultado de los **tres controles** (anclada, justificada, trivial) con su motivo. Se conservan también las descartadas: son el registro de validez del instrumento |
| `quiz_respuestas` | Una fila por (persona, pregunta, intento) | Opción elegida, acierto, marca de tiempo, días transcurridos desde el visionado |
| `gold_retencion` | Una fila por (persona, video) | Vista de modelado: une `content_features` con la agregación de `quiz_respuestas` |

Se conserva el principio de la Entrega 3, «traer una vez, iterar mil»: las preguntas se
generan en el momento de la ingesta y se guardan, de modo que el diseño del análisis pueda
cambiar sin volver a llamar a ningún servicio externo.

### 4.5. Disponibilidad temporal

Los ocho descriptores se calculan a partir de la transcripción y los metadatos en el
momento en que el video se registra, es decir, **antes** de que exista ninguna respuesta.
`dias_transcurridos` se conoce en el instante de lanzar el quiz. **La única información
posterior a la predicción es la respuesta misma, que es la variable objetivo.** No hay
ninguna variable de entrada que sólo esté disponible después del hecho que se quiere
predecir.

---

## 5. Datos de salida y forma de consumo

| Campo de salida | Descripción | Tipo | Uso posterior |
|---|---|---|---|
| `content_item_id`, `persona_id` | Unidad analizada | integer / string | Trazabilidad y unión |
| `retencion_estimada` | Proporción esperada de aciertos | float 0–1 | Panel y dashboard |
| `intervalo_inf`, `intervalo_sup` | Intervalo de predicción | float | Obligatorio: sin él la cifra finge precisión que no tiene |
| `n_base` | Observaciones en que se apoya la estimación | integer | Se muestra siempre junto al valor |
| `descriptores_dominantes` | Los 2–3 descriptores de mayor contribución, con signo | texto | Explicación al usuario |
| `modelo_version`, `fecha_ejecucion` | Versión y momento | string / datetime | Reproducibilidad |

**Granularidad de salida:** (persona, video) para el uso individual; agregada por formato y
por semana para el dashboard.

**Formato:** tabla en PostgreSQL, consumida por la API FastAPI existente, y renderizada en
el panel de la extensión de Chrome y en el dashboard HTML ya construido.

**Cómo la usa el usuario:** el panel pasa de decir «este video tiene densidad informativa
alta» a poder añadir «y los videos con este perfil tienden a recordarse por encima de la
media». La decisión que habilita es de asignación de tiempo.

**Qué hay que mostrar obligatoriamente junto al resultado:** el intervalo, el n, y una
advertencia de que es una tendencia poblacional y no una promesa individual. El proyecto ya
tomó la decisión de no volver a mostrar una letra ni un semáforo.

---

## 6. Estrategia para diseñar y seleccionar el modelo

### 6.1. Preparación del dataset

1. Partir de `content_features` filtrando `apto = true` (el gate de la capa 0: transcripción
   completa y metadatos presentes).
2. Excluir los videos que el verificador de formato marcó como «posible clasificación
   diferente» con confianza alta (§8.6).
3. Unir con `quiz_respuestas` agregadas por (persona, video).
4. Exigir **n ≥ 3 preguntas supervivientes** por quiz. Con 2 preguntas la proporción sólo
   puede valer 0, 0,5 o 1, y el ruido se come cualquier señal.

### 6.2. Definición de la variable objetivo

```
retencion(persona, video) = aciertos / n_preguntas
```

sobre las preguntas que **superaron los tres controles** del instrumento. Las preguntas
descartadas no entran en el denominador: si entraran, una pregunta trivial acertada por
conocimiento general inflaría la retención sin que la persona recordara nada.

### 6.3. Preprocesamiento

- Los percentiles ya están en escala común: no requieren escalado adicional para el GLM
  (sí centrado para interpretar el intercepto).
- No hay imputación de nulos: el gate de aptitud excluye los casos incompletos aguas arriba,
  que es preferible a inventar valores. Es la corrección de un error del scorer v1, donde
  84 de 90 puntuaciones tenían cinco señales imputadas a 0,5, es decir, el 52 % del peso.
- `formato` en one-hot; `dias_transcurridos` centrado.

### 6.4. Criterios de comparación y regla de decisión

| Criterio | Peso en la decisión |
|---|---|
| Mejora sobre el **Baseline 1 (duración)** | Condición necesaria: sin esto no se selecciona nada |
| Estabilidad entre pliegues | Alto: una métrica media buena con varianza enorme entre folds no es un modelo |
| Interpretabilidad | Alto: el producto necesita explicar *por qué* |
| Coste y complejidad | Bajo, el volumen es pequeño |

**Regla de decisión final.** Se aplica el criterio del *error estándar*: entre los modelos
cuyo error esté dentro de una desviación estándar del mejor, se elige **el más simple**. En
caso de empate entre el GLM y el gradient boosting, gana el GLM por interpretable. Y ningún
modelo se selecciona si no supera al Baseline 1 con su intervalo de confianza sin cruzar el
cero.

---

## 7. Estrategia de validación y evaluación

### 7.1. Separación de los datos

**Validación cruzada por grupos (GroupKFold), agrupando por video.** No aleatoria por
pregunta, y el motivo es una fuga de manual: dos preguntas del mismo video comparten
contenido, transcripción y descriptores. Si una cae en entrenamiento y otra en prueba, el
modelo ya vio el material y la métrica sale inflada.

Cuando haya más de un respondiente se añade una segunda validación **agrupada por persona**,
para responder a una pregunta distinta: ¿el modelo generaliza a alguien cuyo nivel base de
memoria no ha visto nunca? Son dos preguntas diferentes y ambas importan.

Si un mismo video llegara a evaluarse en dos momentos, la separación adicional es
**temporal**, para no predecir el pasado con el futuro.

### 7.2. Métricas

| Elemento | Decisión prevista | Justificación |
|---|---|---|
| Separación | GroupKFold por video; anidado por persona cuando n lo permita | Evita la fuga por contenido compartido y reproduce el uso real |
| Métrica principal | **MAE sobre la proporción** | Directamente interpretable: «se equivoca en 0,15 de proporción de aciertos» |
| Métrica secundaria | **Spearman** entre retención predicha y observada | Para el producto importa más el **orden** de los videos que el valor exacto |
| Baseline | GLM con log(duración) | Mide la mejora que aporta el panel sobre un cronómetro |
| Criterio de aceptación | Mejorar el MAE del Baseline 1 en **≥ 10 % relativo**, con intervalo bootstrap sobre los pliegues que no cruce el cero | Fija de antemano qué cuenta como éxito, para no decidirlo mirando el resultado |

### 7.3. Análisis de errores

Residuos desagregados por formato, por estrato de duración, por días transcurridos y por la
bandera `transcripcion_recortada` — esta última porque los videos largos se muestrean a
3.000 palabras y conviene saber si el modelo falla justo ahí. Se revisarán además los casos
extremos: retenciones de 0 y de 1, que suelen indicar un quiz mal generado antes que una
memoria excepcional.

### 7.4. Qué pasa si ningún modelo alcanza el umbral

**Sería un resultado publicable, no un fracaso.** Significaría que los rasgos textuales
medibles de un video no explican la retención por encima de su duración, lo cual es
información útil y honesta sobre los límites de este tipo de instrumentos. Se reportaría
como tal, y el proyecto se entregaría con su capa descriptiva —que ya está construida y
validada— como resultado principal.

---

## 8. Riesgos y alternativas

### 8.1. ¿La variable objetivo está disponible y representa el fenómeno?

**Disponible: no todavía.** Éste es el riesgo principal y el más honesto de declarar. El
**instrumento** está construido y medido (2,6 preguntas útiles por video, tres controles
automáticos, tasas de invención y trivialidad cuantificadas), pero **no existe ninguna
respuesta humana registrada**. Falta el trabajo de campo.

**¿Representa el fenómeno?** Parcialmente, y está medido: 19 de las 30 preguntas del piloto
son de recuerdo factual. La variable mide **retención de datos**, no comprensión ni cambio
de conducta. Nombrarla con precisión es parte de la mitigación.

### 8.2. Volumen y calidad

El escenario realista es de 37 videos informativos y un puñado de respondientes. Aunque se
recluten 5 personas con 10 videos cada una, son ~50 filas frente a 8 predictores más
controles: **el gradient boosting sobreajustará con casi total seguridad**. Mitigaciones
previstas, en este orden:

1. Modelar a nivel de **pregunta** en lugar de video, con efectos aleatorios por video y por
   persona: multiplica las observaciones por ~2,6 sin inventar datos.
2. Regularización (elastic net) sobre el GLM.
3. Si aun así no alcanza, reducir el panel a los 3–4 descriptores con mayor asociación
   univariada y declarar esa selección como exploratoria.

### 8.3. Fuga de información

Riesgo **bajo por diseño**: todas las variables de entrada existen antes del quiz (§4.5). El
riesgo real no está en las variables sino en la **partición**, y por eso la validación es por
grupos y no aleatoria (§7.1).

### 8.4. Sesgos de cobertura y desbalance

- El historial personal está concentrado: HHI de canal 0,216, con un solo canal al 41 %.
  Un modelo entrenado ahí aprende ese canal, no el fenómeno.
- Los descriptores del panel se calibraron contra un corpus público estratificado de 410
  videos precisamente para no heredar ese sesgo, pero la **variable objetivo sí lo heredará**
  mientras los respondientes vean el historial de una sola persona.
- El desbalance de la propia variable (efectos techo o suelo) se medirá en la EDA antes de
  fijar la familia del modelo.

### 8.5. Sesgo del evaluador

El primer respondiente es el autor del proyecto, que conoce los videos, el instrumento y las
hipótesis. Mitigación: reclutar respondientes externos, y **fijar por escrito el análisis
antes de ver los datos** — este mismo documento cumple esa función.

### 8.6. Hallazgo sobre la etiqueta de formato

> **Corrección declarada respecto de entregas anteriores.** La etiqueta `formato`
> (informativo / práctico / entretenimiento / deporte) se deriva **únicamente del
> `category_id` que el canal se autodeclara en YouTube**: no consulta el título, la duración,
> los capítulos ni la transcripción. Es una etiqueta **del canal, no del video**. El caso que
> lo destapó: una entrevista de 129 minutos clasificada como "informativo" porque el canal se
> declara "News & Politics".

Como `formato` se usa como estrato en la escala de referencia y como control en el modelo, el
error se propaga. Mitigación implementada: un verificador que contrasta la etiqueta de la
regla con la que un modelo observa en una muestra de la transcripción, **sin corregirla
nunca** —la etiqueta oficial sigue siendo la determinista— y que reporta el acuerdo bruto y
el **kappa de Cohen**. Kappa y no porcentaje de acuerdo, porque con una categoría dominante
dos clasificadores que la eligieran siempre acordarían el 90 % sin saber nada.

Si el kappa resulta bajo, la conclusión no es que el modelo tenga razón: es que la etiqueta
derivada de la categoría de YouTube y el contenido observable **miden cosas distintas**, y
eso hay que declararlo en todo resultado partido por formato.

### 8.7. Qué genera más incertidumbre

Conseguir n. Todo el diseño estadístico es correcto y ejecutable; lo que no está garantizado
es reunir suficientes pares (persona, video) con quizzes completados dentro del plazo.

### 8.8. Alternativa si el modelado no puede validarse con rigor

Se entrega el proyecto como **sistema descriptivo validado**, que ya existe y ya está medido:
corpus público de 410 videos muestreado por estratos, ocho descriptores con su confusión con
la duración acotada y documentada, escala percentílica cuyo ámbito se decidió por prueba de
permutación, panel funcionando en la extensión y dashboard de dieta. El quiz pasa entonces a
ser **trabajo futuro con el instrumento ya construido y su validez ya cuantificada**, que es
una posición mucho más sólida que proponerlo como idea.
