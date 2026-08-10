# Entrega 3 — Diseño del modelo de datos y capa gold

> **Autor:** Juan Taraciuk
> **Proyecto:** Cognitive Analysis — *Nutri-Score de Contenidos*
> **Entregas previas:** [`01_ideas_producto.md`](01_ideas_producto.md) · [`02_datos_necesarios.md`](02_datos_necesarios.md)

---

## 1. Resumen de la idea y datos del proyecto

**Problema.** Consumimos cada día una enorme cantidad de contenido digital —sobre todo video— sin ninguna señal que indique cuánto valor real aporta antes de invertir el tiempo. En alimentación existe la etiqueta nutricional; en contenido no hay nada equivalente. La analogía que guía el proyecto es exactamente esa: igual que quien quiere ganar músculo mira las proteínas y quien quiere adelgazar mira las calorías, quien quiere consumir de forma más consciente debería poder mirar un indicador simple del "valor cognitivo" de un video antes de darle play.

**Solución.** Calcular automáticamente un *Nutri-Score cognitivo* (letra A–E y valor 0–100) para cada video de YouTube. Una extensión de Chrome detecta el video que se está viendo y lo envía a un backend (FastAPI, desplegado en Render) que lo enriquece y lo puntúa. La puntuación hoy la produce un **motor por reglas** transparente (diez señales ponderadas sobre título, duración, transcripción, categoría, engagement y descripción); ese motor es además la base para etiquetar datos y, más adelante, entrenar un **modelo supervisado**. El MVP ya está operativo end-to-end (extensión + backend + PostgreSQL en Supabase, con ~85 videos capturados).

**Fuentes de datos y qué aporta cada una.** El proyecto combina tres orígenes, ya descritos en la Entrega 2:

- **YouTube Data API v3** (`videos.list`, `part=snippet,statistics`) — metadatos y estadísticas del video: descripción, `tags`, categoría, visualizaciones, "me gusta" y comentarios. Es una foto del momento.
- **Supadata API** — la transcripción del video (subtítulos nativos, con *fallback* a Whisper). Resuelve el bloqueo de YouTube a las IPs de datacenter de Render. Es la materia prima del análisis de lenguaje.
- **Extensión propia (first-party)** — el evento de consumo: qué video se vio y cuándo. Es lo que, acumulado, permite reconstruir la "dieta cognitiva" del usuario.

A esto se suma una cuarta pieza que **no viene de ninguna fuente externa sino que se genera dentro del sistema**: el resultado del scorer (features + puntuación), que es lo que finalmente alimenta el análisis y el modelo.

---

## 2. Tecnología o formato de almacenamiento elegido

**Elección: base de datos relacional PostgreSQL (Supabase), con uso de columnas `JSONB` para las partes semiestructuradas.** No se opta por CSV/Excel/Parquet como almacenamiento primario, y la justificación es concreta para este proyecto:

- **La ingesta es transaccional y continua, no un volcado.** Los datos no llegan como un fichero que se procesa una vez, sino como un goteo de eventos: cada vez que abro un video, la extensión hace un `POST` y el backend escribe una fila. Una base relacional con escritura concurrente y restricciones es el encaje natural; un CSV se corrompería con escrituras simultáneas y no ofrece integridad.
- **Necesito deduplicar de forma fiable.** Un mismo video puede verse muchas veces, pero debe existir **un solo** registro de contenido. Esto se garantiza con una restricción `UNIQUE(external_id)` a nivel de motor —algo que un fichero plano no puede imponer— y que ya está implementada (`content_items.external_id UNIQUE`).
- **Guardo historial de puntuaciones versionadas.** Cada corrida del scorer se guarda como una fila nueva etiquetada con `scorer_version`, lo que permite re-puntuar el catálogo con una versión mejorada del algoritmo y comparar. Ese patrón append-only con relación 1:N encaja en un modelo relacional, no en una hoja de cálculo.
- **Los datos son mixtos: estructurados + semiestructurados.** Los metadatos (duración, categoría, contadores) son tabulares, pero hay tres piezas que no lo son: el *payload* crudo de la extensión, la lista de `tags`, y el *breakdown* de señales del scorer. PostgreSQL permite tener lo estructurado en columnas tipadas y lo semiestructurado en `JSONB` en la **misma** tabla, sin forzar un esquema rígido ni fragmentar en varios ficheros. Es justamente la combinación que pide un dato heterogéneo como éste.
- **El volumen lo permite sin complejidad extra.** El objetivo del curso es del orden de **cientos a pocos miles de videos** (~500–1.500) más decenas/cientos de eventos de consumo. Es un volumen pequeño; no justifica un data warehouse ni Parquet particionado. Postgres lo maneja de sobra y ya está desplegado y funcionando, lo que además evita añadir infraestructura por gusto (criterio explícito de la entrega: no usar tecnología más compleja "porque sí").

**Sobre la capa gold en concreto.** La capa gold **no se exporta a ficheros**: se materializa como **vistas SQL dentro de la misma base PostgreSQL** (ver §4). Las fases posteriores —EDA en un notebook, entrenamiento del modelo, dashboard— la consumen leyendo directamente esas vistas por SQL (por ejemplo con `pandas.read_sql`). Así el "contrato de datos" vive en un único lugar, siempre consistente con las tablas de origen, sin copias desincronizadas ni un paso de exportación que mantener.

---

## 3. Estructura de capas de datos

El proyecto ya está organizado según una **arquitectura medallion de tres capas**, implementada como tres tablas en PostgreSQL (migración `001_three_layer_schema.sql`, aplicada el 2026-07-16). El mapeo con la nomenclatura `raw / processed / gold` de la guía es directo:

| Capa (guía) | Equivalente medallion | Materialización real | Contenido |
|---|---|---|---|
| **Raw** | Bronze | Tabla `raw_events` | Ingesta cruda e inmutable. Guarda el `POST` verbatim de la extensión en una columna `JSONB`, append-only. Nunca se modifica: es la fuente de verdad para auditoría y para poder reprocesar. |
| **Processed** | Silver | Tabla `content_items` | Un registro limpio y enriquecido por video único (dedup por `external_id`). Metadatos tipados de la extensión + YouTube API + transcripción. Es el "video" ya normalizado. |
| **Intermedia / serving** | — | Tabla `content_scores` | Historial de puntuaciones: una fila por cada corrida del scorer sobre un `content_item`, etiquetada con `scorer_version`. Contiene la letra, el valor 0–100 y el *breakdown* de señales en `JSONB`. Alimenta la capa gold pero no es la gold en sí. |
| **Gold** | Gold | **Vistas SQL** (`gold_video_features`, `gold_consumption_events`, `gold_cognitive_diet`) | Datasets finales, limpios y con el contrato estable que consumen EDA, modelo y dashboard. Se construyen sobre las tres tablas anteriores. |

Es decir, el flujo es:

```
raw_events        →  content_items      →  content_scores    →  vistas gold_*
(payload crudo)      (video limpio)         (features+score)     (datasets de consumo final)
   bronze                silver                serving               gold
```

**Matiz respecto a la migración.** El archivo de migración etiqueta hoy a `content_scores` como "gold". Para esta entrega refino esa definición: `content_scores` es una capa **de servicio / intermedia** (el output operativo del scorer que consume la extensión en tiempo real), mientras que la **gold analítica** —la que sirve de contrato para las fases de Data Science— son las **vistas derivadas** que aplanan y combinan las tres tablas en datasets listos para modelar y visualizar. Esta separación es coherente con la definición de la guía: la gold es "el conjunto de datos limpios, definidos y preparados que se utilizarán en análisis, modelado, visualización".

---

## 4. Definición de la capa gold

La capa gold se compone de **tres vistas** en PostgreSQL, cada una con un consumidor claro. Las dos primeras son el núcleo de la entrega; la tercera es una agregación de conveniencia para el dashboard.

### 4.1. Tabla resumen

| Dataset gold | Granularidad | Campos clave | Uso posterior |
|---|---|---|---|
| `gold_video_features` | Una fila por **video único** | `content_item_id`, `external_id`, features `f_*`, `score_numeric`, `score_letter`, `label_manual` | EDA + **modelo predictivo** |
| `gold_consumption_events` | Una fila por **visualización** (usuario × video × instante) | `event_id`, `user_pseudo_id`, `content_item_id`, `watched_at`, `score_letter` | **Dashboard** de dieta cognitiva |
| `gold_cognitive_diet` | Una fila por **usuario × semana** | `user_pseudo_id`, `week`, distribución A–E, minutos por franja de valor | Dashboard (agregado) |

### 4.2. `gold_video_features` — dataset de modelado

**Descripción funcional.** Una fila por video con su vector de características ya extraído más la variable objetivo. Es el dataset de entrenamiento/evaluación del modelo supervisado y la base del EDA. Se construye aplanando el `content_scores.score_details` (JSONB) más reciente de cada `content_item` y uniéndolo con los metadatos de `content_items`.

**Granularidad.** Un registro por `content_item` (video único). Se toma **solo la puntuación más reciente por video** para una `scorer_version` fija (`DISTINCT ON (content_item_id) ... ORDER BY scored_at DESC`), de modo que el historial de re-scoring no duplique filas.

**Número aproximado de registros.** Hoy ~85; objetivo del curso ~500–1.500.

**Clave primaria.** `content_item_id` (o `external_id` como clave natural de YouTube).

**Campos principales.**

| Campo | Tipo | Descripción |
|---|---|---|
| `content_item_id` | `bigint` (PK) | Identificador interno del video. |
| `external_id` | `varchar` | ID nativo de YouTube. Clave natural. |
| `title` | `text` | Título del video. |
| `channel` | `text` | Canal. |
| `category_id` | `varchar` | ID de categoría de YouTube. |
| `category_name` | `varchar` | Nombre legible de categoría (`Education`, `Comedy`, …). |
| `duration_seconds` | `integer` | Duración en segundos. |
| `duration_bucket` | `varchar` (derivado) | `short` / `very_short` / `medium` / `long` / `very_long`. |
| `has_transcript` | `boolean` (derivado) | `true` si había transcripción utilizable (≥50 palabras). **Flag imprescindible** para no confundir señal real con imputación. |
| `f_title` | `float` | Señal de título (0–1): penaliza mayúsculas, exclamaciones y palabras emocionales/clickbait. |
| `f_duration` | `float` | Señal de duración (0–1). |
| `f_lexical_richness` | `float` | Riqueza léxica: ratio de palabras únicas (0–1). |
| `f_data_density` | `float` | Densidad de cifras por 100 palabras (0–1). |
| `f_source_presence` | `float` | Presencia de referencias a fuentes/evidencia (0–1). |
| `f_readability` | `float` | Legibilidad (Flesch) en rango óptimo (0–1). |
| `f_repetition` | `float` | Ratio de bigramas únicos, poca repetición → mejor (0–1). |
| `f_category` | `float` | Categoría como proxy de valor educativo (0–1). |
| `f_engagement` | `float` | Combinación de ratios like/view y comment/view (0–1). |
| `f_description` | `float` | Calidad de la descripción: longitud, links y fuentes (0–1). |
| `like_ratio` | `float` (derivado) | `like_count / view_count`. |
| `comment_ratio` | `float` (derivado) | `comment_count / view_count`. |
| `flesch_score` | `float` (derivado) | Índice Flesch crudo. |
| `scorer_version` | `varchar` | Versión del algoritmo que generó estas features. |
| **`score_numeric`** | `float` | **Target actual (weak label):** puntuación 0–100 del scorer por reglas. |
| **`score_letter`** | `char(1)` | **Target actual (weak label):** clase A–E. |
| **`label_manual`** | `float` / `char(1)` *(nullable)* | **Target de referencia (ground truth):** etiqueta manual de "valor cognitivo" según rúbrica. Hoy vacío; se construye en la fase de etiquetado. |
| `watched_at` | `timestamptz` | Cuándo se vio por primera vez. |
| `scored_at` | `timestamptz` | Cuándo se calculó la puntuación. |

**Variables objetivo / columnas relevantes.** El objetivo del modelo es `score_numeric` (regresión) o `score_letter` (clasificación). Distinción clave del proyecto: hoy el único target disponible es el **weak label** del propio scorer por reglas, y el `label_manual` (ground truth) es la columna que aún hay que poblar y que definirá la calidad real del modelo. Las diez columnas `f_*` son las variables predictoras.

**Uso posterior.** EDA (distribución de scores, correlaciones entre señales, cobertura por categoría) y entrenamiento/validación del modelo supervisado.

### 4.3. `gold_consumption_events` — dataset del dashboard

**Descripción funcional.** Una fila por evento de visualización, para reconstruir la "dieta cognitiva" en el tiempo. Se construye desde `raw_events` (cada evento de consumo) uniendo con `content_items` y con la puntuación vigente del video.

> **Estado: diseño previsto (parcialmente futuro).** Hoy `raw_events` guarda el `payload` de la extensión con `tracked_at`, pero **sin identificador de usuario** (el MVP opera sobre mi propio consumo). Este dataset define el campo `user_pseudo_id` como parte del diseño objetivo; mientras haya un solo usuario, toma un valor constante (`self`). Cuando la extensión incorpore un id seudónimo por usuario (con consentimiento, ver privacidad en Entrega 2), el dataset queda completo sin cambios de esquema.

**Granularidad.** Un registro por `(user_pseudo_id, external_id, watched_at)` — cada vez que se ve un video. A diferencia de `gold_video_features`, aquí **sí** hay varias filas por video (una por visualización).

**Número aproximado de registros.** Decenas a cientos por usuario; crece con el uso.

**Clave primaria.** `event_id` (derivado de `raw_events.id`).

**Campos principales.**

| Campo | Tipo | Descripción |
|---|---|---|
| `event_id` | `bigint` (PK) | Identificador del evento (= `raw_events.id`). |
| `user_pseudo_id` | `varchar` | Identificador seudónimo del usuario. Hoy `self`. |
| `content_item_id` | `bigint` (FK) | Video visto → `content_items.id`. |
| `external_id` | `varchar` | ID de YouTube del video. |
| `watched_at` | `timestamptz` | Instante de la visualización (normalizado a UTC). |
| `watched_date` | `date` (derivado) | Fecha, para agregación diaria/semanal. |
| `category_name` | `varchar` | Categoría del video (desde `content_items`). |
| `duration_seconds` | `integer` | Duración del video. |
| `score_letter` | `char(1)` | Letra vigente del video. |
| `score_numeric` | `float` | Valor 0–100 vigente del video. |

**Uso posterior.** Dashboard personal de dieta cognitiva: distribución de scores A–E consumidos, mezcla por categoría, evolución semanal, tiempo dedicado a contenido de alto vs. bajo valor.

### 4.4. `gold_cognitive_diet` — agregado del dashboard *(conveniencia)*

**Descripción funcional.** Agregación de `gold_consumption_events` por usuario y semana, para alimentar directamente los gráficos del dashboard sin recalcular en el cliente. **Granularidad:** una fila por `(user_pseudo_id, week)`. **Campos:** conteo de videos por letra (`n_A`…`n_E`), minutos totales, minutos en contenido de alto valor (A/B) vs. bajo (D/E), score medio, categoría dominante. **Uso:** dashboard (series temporales y KPIs). Es opcional: si se prefiere, el dashboard agrega al vuelo sobre `gold_consumption_events`.

---

## 5. Relaciones entre datos

El proyecto **sí** usa varias tablas relacionadas; no es un dataset único. Las entidades y sus relaciones:

**Tablas/datasets existentes.**

- `raw_events` (eventos crudos de consumo)
- `content_items` (videos únicos)
- `content_scores` (puntuaciones, historial)
- vistas gold: `gold_video_features`, `gold_consumption_events`, `gold_cognitive_diet`

**Claves y cardinalidades.**

```
content_items.id  1 ──── N  content_scores.content_item_id     (FK real, ON DELETE CASCADE)
content_items.external_id  1 ──── N  raw_events (por external_id dentro del payload; enlace lógico, sin FK)
content_items.id  1 ──── 1  gold_video_features                (una fila por video)
content_items.id  1 ──── N  gold_consumption_events            (una fila por visualización)
```

- **`content_items` 1:N `content_scores`.** Un video tiene muchas puntuaciones (una por corrida/versión del scorer). Es una FK real con borrado en cascada. La gold toma **la más reciente** por video.
- **`content_items` 1:N `raw_events`.** Un mismo video puede generar varios eventos de consumo (se vio varias veces). El enlace es lógico, por el `external_id` que viaja dentro del `payload` JSONB del evento, no una FK física —porque `raw_events` es deliberadamente inmutable y agnóstico al esquema.
- **`gold_video_features` 1:1 `content_items`.** Aplana metadatos + features + target por video.
- **`gold_consumption_events` N:1 `content_items`.** Cada evento apunta a un video; un video aparece en muchos eventos.

**Joins, agregaciones y cruces necesarios.**

- `gold_video_features` = `content_items` ⋈ (último `content_scores` por `content_item_id`), con aplanado del JSON `score_details`.
- `gold_consumption_events` = `raw_events` ⋈ `content_items` (por `external_id`) ⋈ (último `content_scores`).
- `gold_cognitive_diet` = agregación `GROUP BY user_pseudo_id, week` sobre la vista anterior.

**Problemas al combinar fuentes.** El cruce delicado es el de **`raw_events` con `content_items`**: la clave (`external_id`) vive dentro de un `JSONB` en el evento y como columna en el video, así que hay que extraerla y castearla, y tolerar eventos antiguos cuyo payload tenga otro nombre de campo. El segundo punto frágil es el **aplanado de `content_scores.score_details`**: es un JSON cuya forma puede cambiar entre versiones del scorer (si se renombra o añade una señal), lo que rompería la vista `gold_video_features` si no se fija la `scorer_version` y se versiona también la vista.

---

## 6. Diccionario de datos inicial

Campos principales que consumen el modelo y el dashboard (no se documentan todas las columnas internas):

| Campo | Descripción | Tipo de dato | Fuente | Obligatorio | Observaciones |
|---|---|---|---|---|---|
| `external_id` | ID nativo del video en YouTube | `varchar(100)` | Extensión / YouTube | Sí | Clave natural; `UNIQUE`. |
| `title` | Título del video | `text` | Extensión / YouTube | Sí | Materia prima de la señal de clickbait. |
| `channel` | Canal que publica | `text` | Extensión / YouTube | No | Puede venir vacío. |
| `duration_seconds` | Duración en segundos | `integer` | Extensión | No | `<60s` = short; base de `duration_bucket`. |
| `category_id` | ID de categoría YouTube | `varchar(10)` | YouTube API | No | Vacío → señal de categoría cae a neutro 0.5. |
| `category_name` | Nombre de categoría | `varchar(50)` | YouTube API | No | `Other` si el id no está mapeado. |
| `view_count` | Nº de visualizaciones | `bigint` | YouTube API | No | Snapshot del momento; preferir sobre el scraping de la extensión. |
| `like_count` | Nº de "me gusta" | `integer` | YouTube API | No | Puede estar deshabilitado; dislikes ya no existen. |
| `comment_count` | Nº de comentarios | `integer` | YouTube API | No | Proxy de reflexión generada. |
| `transcript` | Transcripción completa | `text` | Supadata | No | Irregular: no todos los videos la tienen → degrada NLP. |
| `watched_at` | Instante de visualización | `timestamptz` | Extensión | Sí (consumo) | Normalizar a UTC (`YYYY-MM-DDThh:mm:ssZ`). |
| `f_data_density` … `f_description` | Vector de 10 señales del scorer | `float` (0–1) | Generado (scorer) | Sí (modelo) | Ver §4.2; extraídas de `score_details`. |
| `has_transcript` | ¿Había transcripción utilizable? | `boolean` | Generado | Sí (modelo) | Distingue señal real de imputación neutra. |
| `score_numeric` | Puntuación 0–100 (weak label) | `float` | Generado (scorer) | Sí (modelo) | Target actual. |
| `score_letter` | Clase A–E (weak label) | `char(1)` | Generado (scorer) | Sí (modelo) | Umbrales: A≥80, B≥60, C≥40, D≥20, E<20. |
| `label_manual` | Etiqueta manual de valor cognitivo | `float`/`char(1)` | Etiquetado manual | No (aún) | **Ground truth pendiente**; define la calidad del modelo. |
| `scorer_version` | Versión del algoritmo | `varchar(20)` | Generado | Sí | Permite comparar/reproducir. |
| `user_pseudo_id` | Usuario seudónimo | `varchar` | Extensión (previsto) | Sí (consumo) | Hoy `self`; sin datos identificativos. |

---

## 7. Problemas de calidad esperados

Aterrizados al caso concreto, no genéricos:

- **Valores nulos que en realidad son imputaciones.** Cuando falta la transcripción, el scorer **no** deja las señales de NLP vacías: las rellena con un valor neutro `0.5` (`lexical_richness`, `data_density`, `source_presence`, `readability`, `repetition`). Ese `0.5` no es una observación real y contaminaría el modelo si se trata como tal. Es el problema de calidad número uno del dataset. Mitigación: el flag `has_transcript`.
- **Nulos reales en metadatos.** `category_id` puede venir vacío (`""`) → la señal de categoría cae a 0.5; `description` vacía → 0.2; `like_count`/`comment_count` pueden ser 0 o ausentes (YouTube ocultó los dislikes y algunos creadores deshabilitan los likes).
- **Duplicados.** Dos niveles. (a) Un video visto N veces genera N `raw_events` —correcto, son eventos distintos— pero **un solo** `content_item` (garantizado por `UNIQUE(external_id)`). (b) Re-puntuar genera **varias** filas en `content_scores`; si la vista gold no toma solo la más reciente por video, se duplican las features. Por eso `gold_video_features` usa `DISTINCT ON (content_item_id)`.
- **Inconsistencia de categorías.** `category_name` está denormalizado como texto; los ids no mapeados caen en `Other`; YouTube puede cambiar la categoría asignada a un video.
- **Fechas mal formateadas / desfasadas.** `watched_at` llega como string desde la extensión y puede traer zona horaria distinta → normalizar a UTC. Además `stats_fetched_at` (cuándo se leyó la API) ≠ `watched_at` (cuándo se vio): las estadísticas son un snapshot que puede quedar desactualizado respecto al momento del consumo.
- **Unidades / doble fuente de la misma métrica.** Las visualizaciones existen dos veces: `view_count_raw` (string tipo "1,2 M" que la extensión scrapea del DOM) y `view_count` (entero de la API). Se debe **preferir siempre el entero de la API** y descartar el string.
- **Cambios de definición entre fuentes.** Métricas de engagement de la extensión (scraping del DOM) vs. YouTube API: la API es la fuente de verdad. Los dislikes ya no están disponibles públicamente.
- **Datos desactualizados.** `view_count`, `like_count` y `comment_count` cambian con el tiempo y no se refrescan: son foto del primer enriquecimiento.
- **Falta de histórico.** El consumo por usuario recién empieza a acumularse; para el dashboard hace falta que pasen semanas. Hoy hay ~85 videos frente al objetivo de 500–1.500.
- **Sesgos de cobertura.** El catálogo refleja **mi** consumo (auto-datos): sesgo hacia mis intereses, idioma (es/en) y quizá sobre-representación de categorías educativas. El dataset no es una muestra representativa de YouTube.
- **Outliers.** Videos virales con `view_count` enorme distorsionan los ratios de engagement; los *shorts* (<60s) reciben `format=short` y quedan penalizados por diseño; transcripciones muy largas en videos de horas.
- **Problemas al cruzar fuentes.** (i) `external_id` como clave entre `raw_events` (dentro del JSON) y `content_items` (columna); (ii) el esquema de `score_details` puede variar entre versiones del scorer y romper el aplanado a features.
- **Campos relevantes no disponibles.** El más importante: `label_manual` (el ground truth de valor cognitivo) todavía no existe y hay que construirlo. También faltan señales deseables mencionadas en la Entrega 2 (dislikes, señales de audio, texto de comentarios).

---

## 8. Decisiones de limpieza y transformación previstas

Hipótesis iniciales (pueden ajustarse en fases posteriores):

- **Valores nulos.** Regla central: **distinguir "ausente" de "neutro".** En el dataset de modelado se expondrán las señales tal como las calcula el scorer **junto al flag `has_transcript`** (y, si se decide, `is_stats_reliable` cuando `view_count < 100`), de modo que el EDA/modelo pueda tratar el `0.5` imputado de forma diferenciada (p. ej. excluir esos videos, o dar la información al modelo como variable extra). No se rellenan huecos con medias ciegas.
- **Duplicados.** Videos: la unicidad ya está garantizada por `UNIQUE(external_id)`. Scores: `gold_video_features` toma **una sola** puntuación por video (`DISTINCT ON (content_item_id) ORDER BY scored_at DESC`) fijando `scorer_version`. Eventos de consumo: **no** se deduplican (cada visualización es un dato legítimo).
- **Normalización.** Fechas → `timestamptz` en UTC. Categoría → mantener `category_id` + `category_name` canónico. `tags` (`JSONB`) → lista de strings en minúsculas. Visualizaciones → usar el entero de la API y descartar `view_count_raw`.
- **Variables derivadas.** `has_transcript`, `duration_bucket`, `like_ratio`, `comment_ratio`, `is_educational` (categoría ∈ {27, 28}), y el aplanado de las diez `f_*` desde `score_details`. Target: `score_numeric`/`score_letter` (weak label del scorer) y, cuando exista, `label_manual` (ground truth).
- **Agregaciones.** Para el dashboard, agregación por `usuario × semana`: distribución A–E, minutos en alto vs. bajo valor, mezcla por categoría y evolución temporal (vista `gold_cognitive_diet`).
- **Datos que se descartan.** `view_count_raw` (redundante e inconsistente); registros de prueba; opcionalmente los *shorts* del dataset de modelado si distorsionan (o mantenerlos con flag). Nunca se descartan `raw_events` (auditoría).
- **Criterio de registro válido.** Para la capa processed: `external_id` y `title` no nulos. Para el modelo: además tener al menos una puntuación; y preferentemente `has_transcript = true` (o, si se incluyen sin transcript, marcarlos para no mezclar imputaciones con observaciones).

---

## 9. Riesgos del modelo de datos

**¿Qué parte está más clara?** Las capas raw → processed → serving. Ya existen, funcionan y contienen ~85 videos reales; el pipeline de ingesta, enriquecimiento (YouTube API + Supadata) y puntuación está operativo. `gold_video_features` es en gran medida un **aplanado directo de datos que ya se están guardando**, no algo por inventar.

**¿Qué genera más incertidumbre?** El **target real del modelo**. Hoy el único objetivo disponible es el propio score por reglas (weak label): si se entrena así sin más, el modelo aprenderá a **imitar las reglas**, no a predecir "valor cognitivo". La incertidumbre está en construir `label_manual` con una rúbrica defendible y consistente. La segunda fuente de incertidumbre es la **estabilidad del esquema `score_details`** entre versiones del scorer, del que depende la vista de features.

**¿Qué fuente o tabla puede dar más problemas?** Dos: (i) `content_scores.score_details`, por ser JSON semiestructurado que cambia de forma entre versiones y sostiene el aplanado a features; y (ii) la dependencia de **Supadata** para la transcripción, que es un tercero de pago y deja huecos (`has_transcript = false`) que degradan medio dataset de señales de NLP.

**¿Qué ocurriría si no se puede construir la gold como está definida?** El sistema sigue siendo entregable. *Fallback* inmediato: usar `content_scores` tal cual (letra + valor) como gold mínima, sin el vector de features aplanado; o exportar las tres tablas a CSV y hacer el aplanado en pandas dentro del notebook, fuera de la vista SQL. En ambos casos se pierde elegancia pero no capacidad de análisis.

**¿Qué alternativa hay para simplificar el modelo si fuera necesario?** Colapsar a **una sola tabla gold ancha a nivel de video** (features + target) y posponer el dataset de consumo/dashboard a una fase posterior —el dataset de modelado es el crítico—. Y, en el límite, mantener el **scorer por reglas como producto final** (calibrado y validado contra la muestra etiquetada manualmente) sin modelo supervisado, ruta ya contemplada en la Entrega 2 que reduce el riesgo global del proyecto.
