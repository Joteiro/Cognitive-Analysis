# Entrega 3 — Diseño del modelo de datos y capa gold

> **Autor:** Juan Taraciuk
> **Proyecto:** Cognitive Analysis — *Nutri-Score de Contenidos*
> **Entregas previas:** [`01_ideas_producto.md`](01_ideas_producto.md) · [`02_datos_necesarios.md`](02_datos_necesarios.md)
> **Actualizado:** agosto 2026 · escala `mm-2026-08-v1` · features `panel-1.0`

> **Nota sobre la evolución del proyecto.** Este documento refleja el diseño de datos **vigente**, que cambió de forma sustancial respecto de lo descrito en la Entrega 2. Aquel documento planteaba un *Nutri-Score cognitivo* agregado (letra A–E y valor 0–100) producido por un scorer por reglas, con vistas a un modelo supervisado. Ese enfoque se jubiló por una razón que vale la pena registrar: la puntuación única correlacionaba 0,73 con el logaritmo de la duración —es decir, medía en buena parte "cuán largo es el video" disfrazado de "cuán valioso es"— y, sobre todo, **agregar y poner una letra es emitir un juicio** que el sistema no debería arrogarse. La Entrega 2 se conserva intacta como registro histórico de esa etapa; lo que sigue describe el modelo que la reemplazó.

---

## 1. Resumen de la idea y datos del proyecto

**Problema.** Consumimos cada día una enorme cantidad de contenido digital —sobre todo video— sin ninguna señal que indique qué nos aporta antes de invertir el tiempo. En alimentación existe la etiqueta nutricional; en contenido no hay nada equivalente. La analogía sigue guiando el proyecto: igual que quien quiere ganar músculo mira las proteínas y quien quiere adelgazar mira las calorías, quien quiere consumir de forma más consciente debería poder mirar **una etiqueta con varios indicadores** antes de darle play —y decidir por sí mismo, según su objetivo.

**Solución (rediseñada).** En lugar de una nota única, el sistema calcula un **panel de 8 descriptores** medibles de cada video de YouTube y ubica cada uno como **percentil dentro de un corpus público de referencia** ("este video tiene más cifras por minuto que el 68 % de los videos comparables"). Deliberadamente **no hay letra, no hay puntuación agregada y no hay pesos**: cada descriptor se muestra por separado y la valoración la pone el usuario. Es el cambio conceptual central respecto de la Entrega 2 —de un *score que juzga* a un *panel que describe*—. Siguiendo la misma lógica, se descartaron las **métricas de audiencia** (visualizaciones, likes, comentarios): miden al canal y al algoritmo de recomendación, no al contenido en sí.

Una extensión de Chrome detecta el video en pantalla, un backend FastAPI (desplegado en Render) lo enriquece y lo puntúa contra la escala, y el resultado se muestra en el navegador. El MVP está operativo end-to-end con base PostgreSQL en Supabase.

**Fuentes de datos y qué aporta cada una.**

- **YouTube Data API v3** (`videos.list`, `part=snippet,statistics,contentDetails`) — metadatos: título, canal, descripción, `tags`, categoría, duración e idioma declarado. (Las estadísticas de audiencia se recogen pero ya **no** alimentan la medición.)
- **Transcripción del video** — la materia prima del análisis lingüístico. Se obtiene por dos caminos calibrados como equivalentes: `youtube_transcript_api` + `yt-dlp` en un worker **local** (IP residencial, usado para construir el corpus de referencia y para el enriquecimiento por lotes) y **Supadata** en producción (modo `native`, nunca Whisper, para los videos que el usuario abre en vivo). La procedencia de cada transcripción se guarda como dato (`transcript_source`, `transcript_is_generated`, `transcript_lang`), porque cambia qué señales son calculables. La equivalencia de ambas fuentes se verificó de forma pareada sobre 7 videos (correlaciones de 0,996 a 1,000; ningún video cambia de tramo).
- **Extensión propia (first-party)** — el evento de consumo (qué video se vio y cuándo). Es lo que, acumulado, forma el **historial** personal que alimenta el dashboard de "dieta cognitiva".
- **Corpus de referencia** — una fuente nueva, generada por **muestreo estratificado** de videos públicos de YouTube (no es consumo del usuario). Es la población contra la que se calculan los percentiles, y se materializa en el artefacto versionado `escala_referencia.json`.

A esto se suma la pieza que el sistema **genera** y que es el corazón de la entrega: la tabla `content_features`, la "etiqueta nutricional" calculada de cada video.

---

## 2. Tecnología o formato de almacenamiento elegido

**Elección: base de datos relacional PostgreSQL (Supabase) con columnas `JSONB`, complementada por un fichero JSON versionado para la escala de referencia.** Es una **combinación de formatos**, y cada pieza está donde le corresponde:

- **PostgreSQL para todo lo operativo, intermedio y la capa gold.** La ingesta es transaccional y continua (cada video abierto es un `POST` que escribe una fila), necesita deduplicación fiable a nivel de motor (`UNIQUE(external_id)`), funciona además como **cola de trabajo** con reintentos (columnas `attempts`, `next_attempt_at`, `enrichment_status`), y mezcla datos tabulares con semiestructurados (el `payload` crudo, los `tags`, los `transcript_segments`, el `panel` calculado) que `JSONB` resuelve en la misma tabla sin fragmentar en ficheros. El volumen —cientos a pocos miles de videos— es pequeño y no justifica un data warehouse ni Parquet; Postgres ya está desplegado y funcionando, lo que evita añadir tecnología "porque sí".
- **Un fichero JSON (`escala_referencia.json`) para la escala de referencia.** La escala es un objeto pequeño, **inmutable y versionado** (`frame_version = "mm-2026-08-v1"`): 101 percentiles por descriptor más los parámetros del método. Tiene que (a) viajar con el deploy para que el panel en vivo y el estudio del TFM midan contra exactamente la misma población, y (b) quedar congelada bajo control de versiones, porque *percentiles de escalas distintas no son comparables*. Para ese rol —un artefacto de solo-lectura, portable y auditable— un fichero versionado es mejor medio que una tabla.

**Matiz respecto de la Entrega 3 anterior.** En una versión previa de esta entrega la capa gold se planteó como *vistas SQL*. El diseño real evolucionó a una **tabla materializada** (`content_features`, ver §4) y no una vista, por dos motivos concretos del código: el sistema necesita **memoria** de lo que midió —para poder afirmar en la memoria del TFM "así se distribuyó mi historial", algo imposible si el panel se recalcula y se olvida en cada request— y necesita **cachear** un cálculo caro (importar pandas/numpy en el arranque en frío de Render cuesta 10–20 s). Cada cálculo del panel hace `upsert` en `content_features` (una fila por video, se pisa al recalcular).

---

## 3. Estructura de capas de datos

El proyecto usa una **arquitectura medallion de tres capas** sobre PostgreSQL, más el fichero de escala como artefacto de referencia. El mapeo con la nomenclatura `raw / processed / gold` de la guía:

| Capa (guía) | Materialización real | Contenido |
|---|---|---|
| **Raw** (bronze) | Tabla `raw_events` | Ingesta cruda e inmutable: el `POST` verbatim de la extensión en `JSONB`, append-only. Fuente de verdad y semilla de la cola de enriquecimiento. |
| **Processed** (silver) | Tabla `content_items` (44 columnas) | Un registro limpio y enriquecido por video único (dedup por `external_id`). Metadatos + transcripción con su procedencia + estado de la cola de enriquecimiento + separación de corpus (ver abajo). |
| **Gold** | **Tabla `content_features`** | La "etiqueta nutricional": una fila por video con los 8 descriptores crudos, su percentil en la escala, el gate de aptitud y las etiquetas. Es el contrato de datos que consumen el dashboard, el análisis del TFM y la extensión. |
| *Artefacto de referencia* | Fichero `escala_referencia.json` | La escala (101 percentiles por descriptor, por formato cuando corresponde) contra la que `content_features` ubica cada valor. Versionado por `frame_version`. |
| *Retirada* | Tabla `content_scores` | Historial del viejo score A–E. **Sin filas nuevas desde 2026-08-13**; se conserva como evidencia de la etapa anterior. |

**Dos subpoblaciones dentro de `content_items`.** La columna `corpus` separa `historial` (lo que mira el usuario; tiene `watched_at`) de `referencia` (videos muestreados para construir la escala). **Nunca se mezclan al calcular percentiles**: medir el historial contra sí mismo sería circular. El historial personal de partida (94 videos, 41 % de un solo canal, casi todo *News & Politics* en español) es justamente lo que **no** puede servir de escala —"es un espejo del consumo de una persona, no una referencia"— y por eso existe el corpus separado.

**Flujo:**

```
raw_events   →   content_items          →   content_features
(payload)        (video limpio + cola        (panel: 8 descriptores
  bronze          + procedencia + corpus)     + percentiles + gate)
                        silver                        gold
                           │                            ▲
                           │  subconjunto corpus=referencia
                           ▼                            │
                   muestreo estratificado  →  escala_referencia.json
                                              (artefacto de referencia)
```

---

## 4. Definición de la capa gold

La capa gold es **un único dataset: la tabla `content_features`**. Aguas arriba hay un modelo relacional pequeño que la alimenta (§5), pero lo que consumen las fases posteriores —dashboard, análisis, extensión— es esta sola tabla. No hay una segunda tabla gold de "consumo": el dashboard reconstruye la dieta cognitiva uniendo `content_features` con el `watched_at` de `content_items` (filtrando `corpus = 'historial'`) y **agregando al vuelo**, sin materializar un dataset aparte.

### 4.1. Tabla resumen

| Dataset gold | Granularidad | Campos clave | Uso posterior |
|---|---|---|---|
| `content_features` | Una fila por **video** (`content_item_id` único; se pisa al recalcular) | `content_item_id`, `apto`, los 8 `*_pct` (percentiles), `formato`, `frame_version` | **Dashboard** (dieta cognitiva) · **EDA / memoria TFM** · **extensión** (endpoint `/panel`) |

### 4.2. `content_features` — especificación

**Descripción funcional.** La etiqueta nutricional de cada video: sus 8 descriptores en valor crudo, la posición de cada uno como percentil en la escala de referencia, si el video es **medible** (gate `apto`) y por qué no lo es cuando no lo es, más un conjunto de etiquetas categóricas auditables. Se calcula con `nutriscore_features.py` —el **mismo** módulo con el que se construyó la escala, para que el panel en vivo y el estudio no midan cosas distintas— y se persiste por `upsert`.

**Granularidad.** Una fila por video (`UNIQUE (content_item_id)`), correspondiente al último cálculo. Está versionada por `features_version` (hoy `panel-1.0`) y `frame_version` (la escala usada).

**Número aproximado de registros.** Del orden de **varios cientos** hoy (historial ≈94 + corpus de referencia ≈410), y crece con cada video nuevo que se abre. Se guardan también las filas de videos **no aptos**: que un video no se pueda medir es un dato, no un vacío —el hallazgo de que los formatos difieren más en *si se pueden medir* que en *cómo puntúan* se sostiene sobre esas filas.

**Clave primaria / identificador.** `content_item_id` (FK a `content_items.id`, `ON DELETE CASCADE`, con índice único → funciona como identificador natural de la fila).

**Campos principales.**

| Campo | Tipo | Descripción |
|---|---|---|
| `content_item_id` | `bigint` (FK, único) | Video al que corresponde el panel. |
| `features_version` | `varchar` | Versión del calculador (`panel-1.0`). |
| `frame_version` | `varchar` | Versión de la escala usada (`mm-2026-08-v1`). Los percentiles solo son comparables dentro de la misma. |
| `formato` | `varchar` | Macroformato del video (`informativo` / `practico_personal` / `entretenimiento` / `deporte_gaming`). Necesario para leer los descriptores `por_formato`. |
| `apto` | `boolean` | Gate: si el video es medible. `true` / `false` / (fila ausente → "procesando"). |
| `cobertura_transcripcion` | `real` | Palabras reales ÷ esperadas (`duración_min × 150`). Base del gate. |
| `motivo_no_apto` | `varchar` | Por qué no es medible (p. ej. `cobertura_de_habla_insuficiente`). |
| `n_words` | `integer` | Palabras de la transcripción. |
| `duration_seconds` | `integer` | Duración del video. |
| `lang` | `varchar` | Idioma del texto medido (`es` / `en`), derivado de la transcripción. |
| `transcript_source` | `varchar` | `youtube_manual` / `youtube_auto` / `supadata` / `extension`. |
| `has_description`, `has_tags` | `boolean` | Disponibilidad de descripción y tags. |
| `ritmo_ppm` … `cobertura_titulo` | `real` | Los **8 descriptores** en valor crudo (ver tabla 4.3). |
| `ritmo_ppm_pct` … `cobertura_titulo_pct` | `real` | El **percentil 0–100** de cada descriptor en la escala. **Son las columnas que se muestran y se analizan.** |
| `panel` | `jsonb` | El panel completo tal como lo devuelve el endpoint (por descriptor: valor, unidad, ámbito, estado, percentil). |
| `etiquetas` | `jsonb` | Etiquetas categóricas `et_*` (porción de duración, formato editorial, trazabilidad, caducidad, calidad del dato, etc.). |
| `computed_at` | `timestamptz` | Cuándo se calculó. |

**Variables relevantes y ausencia de variable objetivo.** Aquí está el cambio de fondo respecto de la Entrega 2: **no hay variable objetivo (`target`)**, porque el proyecto ya no es un problema de predicción sino de **descripción**. Las columnas centrales para el análisis son los **ocho percentiles `*_pct`** (lo que se muestra al usuario y se agrega en el dashboard), el gate **`apto`** (variable clave del estudio: qué proporción de cada formato es medible) y **`formato`** (dimensión de estratificación). No hay letra, no hay score agregado, no hay etiqueta a aprender.

**Uso posterior.** (a) La **extensión**, que lee el panel en tiempo real vía `GET /panel/{video_id}`; (b) el **dashboard** de dieta cognitiva, que agrega el historial en el tiempo (distribución de percentiles, mezcla de formatos, evolución); (c) el **análisis / EDA de la memoria del TFM** (cómo se distribuyó el consumo, qué formatos caen fuera del gate).

### 4.3. Los 8 descriptores

Todos se calculan sobre la transcripción o la descripción, **normalizados** (por 100 o 1000 palabras, por minuto, o en ventana fija) para no medir duración disfrazada. Ninguno depende de que la transcripción tenga puntuación. Cada uno es de tipo **continuo** (se ubica por su percentil en el corpus) o de **presencia** (primero "tiene / no tiene", y si tiene, su percentil entre los que tienen), y de ámbito **global** o **por formato** (decidido por una prueba estadística, §8).

| Descriptor | Qué mide | Cálculo / unidad | Tipo · Ámbito |
|---|---|---|---|
| `ritmo_ppm` | Velocidad del habla | palabras ÷ minutos · *palabras/min* | continuo · global |
| `cifras_100w` | Densidad de cantidades verificables | (dígitos + números escritos) por 100 palabras · *cifras/100w* | continuo · por formato |
| `atribucion_1000w` | Marcas de fuente/atribución ("según", "un estudio", "según…") | léxico por 1000 palabras · *marcas/1000w* | presencia · por formato |
| `mattr_200` | Diversidad léxica insensible a la longitud | *Moving-Average Type-Token Ratio*, ventana fija de 200 tokens, paso 50 · *0–1* | continuo · global |
| `conectores_1000w` | Conectores lógicos entre ideas ("porque", "sin embargo", "por lo tanto") | léxico por 1000 palabras · *marcas/1000w* | continuo · global |
| `enlaces_externos` | URLs en la descripción que no son redes propias | conteo **absoluto** (no se normaliza: la descripción es un artefacto fijo, no un flujo) · *enlaces* | presencia · por formato |
| `promocional_1000w` | "Azúcares añadidos": llamadas a la acción + patrocinio | léxico (CTA + patrocinio) por 1000 palabras · *marcas/1000w* | presencia · por formato |
| `cobertura_titulo` | Correspondencia promesa↔contenido | fracción de palabras clave del título (>3 letras, sin stopwords) presentes en la transcripción · *0–1* | continuo · por formato |

### 4.4. El gate de aptitud (capa 0)

Antes de medir, `capa0_validez` decide si el video es **apto** para el panel. `apto = true` requiere las tres condiciones: **hay transcripción** (`n_words > 0`), la transcripción está **completa** (`cobertura_transcripcion` entre 0,45 y 1,6 respecto de las palabras esperadas a 150 wpm) y **hay metadatos** (`category_id` no nulo). Si falla, el video se marca `apto = false` con su `motivo_no_apto` (típicamente `cobertura_de_habla_insuficiente`: música, gameplay sin comentario, tomas sin voz) y **nunca** se rellena con un cero ni una letra: se responde "Sin datos suficientes". La distinción entre "todavía procesando" (fila inexistente o sin transcripción reciente) y "no se va a poder medir" (gate en `false`) es explícita, para no dejar la etiqueta girando indefinidamente.

---

## 5. Relaciones entre datos

El proyecto **sí** tiene un modelo relacional; lo que es único es el **dataset gold consumido** (`content_features`), no las tablas.

**Tablas / artefactos.** `raw_events`, `content_items`, `content_features`, el fichero `escala_referencia.json` y la tabla retirada `content_scores`.

**Claves y cardinalidades.**

```
content_items.id  1 ── 1  content_features.content_item_id   (FK, UNIQUE, ON DELETE CASCADE)
content_items.external_id  1 ── N  raw_events                 (enlace lógico vía external_id dentro del payload JSONB)
content_items.id  1 ── N  content_scores                     (retirada; sin filas nuevas)
content_items.corpus  →  {historial | referencia}            (partición de la misma tabla, no una relación)
```

- **`content_items` 1:1 `content_features`.** Una etiqueta nutricional por video (índice único + `upsert`).
- **`content_items` 1:N `raw_events`.** Un video puede verse muchas veces (varios eventos); el enlace es **lógico**, por el `external_id` que viaja dentro del `payload` JSONB, no una FK física —`raw_events` es deliberadamente inmutable y agnóstico al esquema—.
- **Ubicación en la escala (no es un join SQL sino un *lookup* contra el fichero).** Cada descriptor de `content_features` se ubica en `escala_referencia.json` por su clave, su `frame_version` y —para los descriptores `por_formato`— por el `formato` del video. Los continuos usan una grilla de percentiles (`grid`); los de presencia usan la grilla **solo de los que tienen** (`grid_presentes`) más `p_ausencia` ("% que no lo tiene").

**Cruces, agregaciones y problemas al combinar.**

- El **dashboard** hace `content_features ⋈ content_items` (por `content_item_id`) filtrando `corpus = 'historial'` y agrupando por semana/formato sobre `watched_at`.
- **Problema 1 — clave dentro de JSON:** el `external_id` que enlaza `raw_events` con `content_items` vive dentro de un `JSONB`; hay que extraerlo y tolerar payloads antiguos con otro nombre de campo.
- **Problema 2 — comparabilidad de escalas:** percentiles de `frame_version` distintas no son comparables; cruzar filas medidas contra escalas diferentes daría lecturas falsas. Por eso `content_features` guarda su `frame_version` y la caché se invalida si cambia.
- **Problema 3 — no mezclar corpus:** los percentiles se calculan **solo** sobre `corpus = 'referencia'`; incorporar el historial a la escala sería circular.
- **Problema 4 — formato desconocido:** los descriptores `por_formato` necesitan el `formato`, derivado de `category_id` antes de enriquecer; si la categoría falta, el descriptor cae al ámbito `_todos` (menos preciso).

---

## 6. Diccionario de datos inicial

Campos principales que consumen el panel, el dashboard y el análisis (no se documentan todas las columnas internas):

| Campo | Descripción | Tipo | Fuente | Obligatorio | Observaciones |
|---|---|---|---|---|---|
| `external_id` | ID nativo del video en YouTube | `varchar(100)` | Extensión / YouTube | Sí | Clave natural; `UNIQUE` en `content_items`. |
| `transcript` | Transcripción completa | `text` | youtube_transcript_api / Supadata | Sí (para medir) | Sin ella el video es no apto; no se imputa nada. |
| `transcript_source` | Procedencia de la transcripción | `varchar(20)` | Enriquecimiento | Sí | `youtube_manual/auto`, `supadata`, `extension`. |
| `transcript_is_generated` | ¿Subtítulos automáticos (ASR)? | `boolean` | Enriquecimiento | No | Los automáticos no traen puntuación. |
| `transcript_lang` | Código de la pista de subtítulos | `varchar(40)` | Enriquecimiento | No | No siempre ISO 639 (pistas manuales: `es-uYU-mmqFLq8`); agrupar con `split_part(...,'-',1)`. |
| `category_id` | ID de categoría de YouTube | `varchar(10)` | YouTube API | Sí (para el gate) | Determina el `formato`; su ausencia deja el video no apto. |
| `corpus` | Subpoblación del video | `varchar(20)` | Muestreo / ingesta | Sí | `historial` o `referencia`; nunca se mezclan en los percentiles. |
| `watched_at` | Instante de visualización | `timestamptz` | Extensión | Sí (historial) | Base de la agregación temporal del dashboard (UTC). |
| `apto` | ¿Video medible? | `boolean` | Generado (gate) | Sí | Variable clave del estudio. |
| `cobertura_transcripcion` | Palabras reales ÷ esperadas (150 wpm) | `real` | Generado | Sí | Completa si ∈ [0,45 ; 1,6]. |
| `ritmo_ppm` … `cobertura_titulo` | Los 8 descriptores (valor crudo) | `real` | Generado (nutriscore_features) | Sí | Ver §4.3; unidades por 100/1000 palabras, por minuto o 0–1. |
| `*_pct` (8 columnas) | Percentil 0–100 de cada descriptor | `real` | Generado (escala) | Sí | Lo que se muestra y se analiza; comparable solo dentro de un `frame_version`. |
| `formato` | Macroformato del video | `varchar(40)` | Derivado de `category_id` | Sí | 4 valores; necesario para descriptores `por_formato`. |
| `frame_version` | Versión de la escala | `varchar(40)` | Escala | Sí | `mm-2026-08-v1`. |
| `panel`, `etiquetas` | Panel completo y etiquetas `et_*` | `jsonb` | Generado | No | Lo que no entra en columnas tipadas. |

---

## 7. Problemas de calidad esperados

Aterrizados al caso concreto:

- **Transcripción ausente o incompleta.** Es el principal límite de cobertura. Videos sin subtítulos, o con transcripción truncada (`cobertura_transcripcion` fuera de [0,45 ; 1,6]), o sin voz (música, gameplay) caen en `apto = false`. A diferencia del scorer viejo —que rellenaba las señales faltantes con un `0.5` neutro que contaminaba todo—, aquí **un dato ausente se muestra como "no disponible", nunca se imputa**.
- **Subtítulos automáticos sin puntuación.** Los ASR de YouTube no traen puntuación; algunos indicadores fuera del panel (frases por oración, preguntas) no son calculables. Los 8 del panel se diseñaron para **no** depender de puntuación, pero la diferencia se guarda (`transcript_is_generated`) para no mezclarla en el análisis.
- **Idioma.** La escala se construyó con 344 videos **en español**. Una transcripción en otro idioma se mide igual pero sus percentiles comparan contra una población que no le corresponde; el endpoint lo **avisa** (`aviso_idioma`) en vez de ocultarlo. Además `transcript_lang` no siempre es ISO 639 (pistas manuales con identificadores largos), lo que ya rompió inserts hasta ensanchar la columna a `varchar(40)`.
- **Duplicados.** Un video visto N veces genera N `raw_events` (correcto), pero **un** `content_item` (`UNIQUE(external_id)`) y **una** fila en `content_features` (`upsert` que se pisa). Sin el `upsert`, cada apertura acumularía una fila y la tabla dejaría de servir para contar.
- **Sesgo de cobertura.** El historial personal es un espejo (94 videos, 41 % un canal, casi todo *News & Politics* en español): por eso **no** puede ser la escala. El corpus de referencia lo corrige con muestreo estratificado, pero sigue acotado a español y a regiones AR/ES; no es una muestra universal de YouTube.
- **Comparabilidad entre escalas.** Percentiles de `frame_version` distintas no son comparables. Si cambian las semillas de muestreo, las categorías o los cortes, sube la versión y **no** se cruzan lecturas de marcos distintos.
- **Corpus chico por celda.** El diseño reparte ~28–33 videos por cada una de las 12 celdas (4 formatos × 3 duraciones); con ese n, el error típico de una correlación ronda 0,2 y los percentiles por estrato tienen incertidumbre. El anexo por celda usa el corte global cuando una celda tiene menos de 15 videos útiles.
- **Categoría faltante → formato desconocido.** Sin `category_id` no hay `formato`, y los descriptores `por_formato` caen al ámbito `_todos`, menos afinado.
- **Dependencia de servicios de transcripción.** Supadata puede quedarse sin crédito (`exhausted`) o limitar por ritmo (`rate_limit`); `youtube_transcript_api` sufre bloqueos desde IPs de datacenter. Ambos dejan huecos que el gate refleja como no apto o "procesando".

---

## 8. Decisiones de limpieza y transformación previstas

- **Valores nulos: no se imputan.** Regla central heredada del rediseño: distinguir "ausente" de "medido". Un indicador sin dato se muestra "no disponible"; el **gate `apto`** decide si el video entra al panel y `cobertura_transcripcion` decide si la transcripción es completa. Se eliminó por completo el relleno con valores neutros.
- **Normalización.** Todo indicador va **por 100 palabras, por 1000 palabras, por minuto o en ventana fija** (`mattr_200` fija 200 tokens), nunca en total —un total mide duración disfrazada, el defecto que motivó todo el rediseño—. Única excepción justificada: `enlaces_externos` en conteo absoluto, porque la descripción es un artefacto fijo y dividir por minutos metía la inversa de la duración dentro del indicador.
- **Deduplicación.** `UNIQUE(external_id)` en `content_items`; `UNIQUE(content_item_id)` con `upsert` en `content_features`; los eventos de consumo **no** se deduplican (cada visualización es un dato).
- **Normalización de campos.** Fechas a `timestamptz` UTC; idioma agrupado con `split_part(transcript_lang,'-',1)`; `formato` derivado de `category_id` con `bucket_formato` **antes** de enriquecer (el estrato debe conocerse en el momento del muestreo).
- **Variables derivadas.** Los 8 descriptores y sus 8 percentiles; el gate (`apto`, `cobertura_transcripcion`, `motivo_no_apto`); las etiquetas `et_*` categóricas y auditables (porción de duración, formato editorial, caducidad, tipo de promesa del título, trazabilidad de fuentes, navegabilidad, calidad del dato, idioma, categoría).
- **Construcción de la escala (transformación estadística).** Sobre `corpus = 'referencia'`: para cada descriptor se calcula una **grilla de 101 percentiles**; una **prueba de permutación** (2000 remuestreos, α = 0,05) decide si el descriptor se mide **global** o **por formato** (si los formatos difieren significativamente); y la regla **`umbral_cero = 1/3`** decide si es de **presencia** (cuando más de un tercio del corpus vale exactamente 0, el tercil "bajo" dejaría de ser tercil) usando `grid_presentes` + `p_ausencia`. El historial se mide **contra** la escala sin entrar en ella.
- **Descartes.** En el muestreo, videos fuera de [2 min, 3 h] y tope de 2 videos por canal (anti-concentración); descriptores descartados del panel por correlacionar con la duración (p. ej. `hapax_ratio`, −0,82). La tabla `content_scores` se retiró (no se borró). Se conservan las filas **no aptas** en `content_features`: son parte del hallazgo.
- **Criterio de registro válido.** Para medir: transcripción presente + completa (0,45–1,6) + metadatos (`apto = true`). Para la escala: `corpus = 'referencia'`, con transcripción y estrato conocido.

---

## 9. Riesgos del modelo de datos

**¿Qué está más claro?** El flujo raw → processed → gold ya funciona y tiene datos reales. `content_features` es un `upsert` de valores calculados por un **único** cuerpo de reglas (`nutriscore_features.py`) compartido entre el estudio y el panel en vivo, de modo que ambos miden lo mismo por construcción.

**¿Qué genera más incertidumbre?** La **validez y estabilidad de la escala de referencia**. Al abandonar la nota agregada desapareció el riesgo anterior (definir un "valor cognitivo" subjetivo como *ground truth*), pero aparece otro: que el corpus sea suficientemente representativo (hoy español, AR/ES, ~28 por celda) y que `frame_version` se gestione con disciplina. Un percentil solo significa algo respecto de la población que lo generó.

**¿Qué fuente o tabla puede dar más problemas?** Dos. La **transcripción**, por su dependencia de servicios externos y por dejar formatos enteros fuera del gate (sin voz → no medibles). Y el fichero **`escala_referencia.json`**: si cambia el corpus, cambian *todos* los percentiles a la vez; hay que versionarlo y no comparar lecturas entre versiones.

**¿Qué ocurriría si no se puede construir la gold como está definida?** El sistema sigue siendo entregable. *Fallbacks*: mostrar los 8 descriptores en **valor crudo normalizado sin percentil** (se pierde la referencia poblacional pero el panel sigue informando), o quedarse con `content_features` sin el ámbito `por_formato` (que es lo que exige el muestreo estratificado).

**¿Qué alternativa hay para simplificar?** Reducir el panel a los descriptores **globales** (evitando la estratificación y el muestreo por celdas), sustituir la grilla de 101 percentiles por **cortes en tercios** (bajo/medio/alto) contra el mismo corpus, o —en el límite— prescindir del corpus de referencia y mostrar solo valores absolutos normalizados. Cualquiera de las tres mantiene la idea central —describir sin juzgar— con mucha menos maquinaria.
