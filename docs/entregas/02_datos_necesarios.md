# Entrega 2 — Selección de idea y análisis de datos necesarios

> **Autor:** Juan Taraciuk
> **Proyecto:** Cognitive Analysis — *Nutri-Score de Contenidos*
> **Idea seleccionada:** Nutri-Score de Contenidos (ver también [`01_ideas_producto.md`](01_ideas_producto.md))

---

## 1. Idea seleccionada

**Problema que resuelve.** Consumimos cada día una enorme cantidad de contenido digital —principalmente video— sin ninguna señal que nos indique cuánto valor real nos aporta antes de invertir nuestro tiempo. En alimentación existe la información nutricional: un vistazo basta para saber si un producto es más o menos saludable. En contenido no existe nada equivalente: decidimos qué mirar guiándonos por el título, la miniatura y el número de visualizaciones, señales optimizadas para captar la atención y no para reflejar el aporte cognitivo. El problema lo tiene cualquier persona que quiera consumir de forma más consciente —estudiantes, profesionales que aprenden de forma autodidacta, cualquiera que sienta que "pierde el tiempo" en YouTube— y es relevante porque el tiempo de atención es un recurso escaso: una etiqueta clara permitiría decidir mejor y, de forma agregada, entender los propios hábitos de consumo digital.

**Solución planteada.** Desde un enfoque de Data Science, propongo calcular automáticamente un *Nutri-Score cognitivo* (letra A–E y valor 0–100) para cada video de YouTube a partir de datos observables del contenido. Una extensión de navegador detecta el video que se está viendo y un backend lo enriquece con dos fuentes: los metadatos de la **YouTube Data API v3** (categoría, duración, estadísticas de engagement, descripción, etiquetas) y la **transcripción** del video. Sobre ese material se aplica ingeniería de características y procesamiento de lenguaje natural —densidad de datos y cifras, riqueza léxica, presencia de referencias a fuentes, legibilidad, señales de clickbait en el título, repetición, etc.— para producir la puntuación. El proyecto parte de un motor de puntuación **basado en reglas** (heurístico y transparente), que sirve además como base para etiquetar datos, y evoluciona hacia un **modelo de aprendizaje supervisado** que aprenda a predecir el score a partir de esas características.

**MVP del proyecto final.** Al final del curso quiero presentar dos piezas funcionando de forma conjunta. Primero, la **extensión** que, al abrir un video de YouTube, muestra en pantalla su Nutri-Score cognitivo (letra, valor y etiquetas descriptivas del tipo "🎓 educativo/científico", "🎣 título de alto estímulo emocional", "📚 cita fuentes"). Segundo, un **dashboard personal de "dieta cognitiva"** que agrega el historial de consumo del usuario y lo visualiza en el tiempo: distribución de scores A–E, mezcla por categorías, evolución semanal, tiempo dedicado a contenido de alto vs. bajo valor. La puntuación que alimenta ambas piezas la producirá el modelo de Machine Learning entrenado sobre un dataset de videos etiquetados. Ya existe un **MVP end-to-end operativo** (extensión + backend FastAPI desplegado en Render + base de datos PostgreSQL) que implementa el flujo de captura, enriquecimiento y puntuación por reglas con versionado del algoritmo; lo que resta del curso es construir el dataset etiquetado, entrenar y validar el modelo, y desarrollar el dashboard.

---

## 2. Datos necesarios

El proyecto trabaja con tres tipos de entidad de datos: **el contenido** (cada video), **el consumo** (cada visualización del usuario) y **la etiqueta** (el "valor cognitivo" de referencia para entrenar el modelo).

### 2.1. Variables o campos

**Por cada ítem de contenido (video).** Identificador de YouTube, URL, título, canal, duración en segundos, descripción, etiquetas (`tags`), categoría (id y nombre), y estadísticas: número de visualizaciones, de "me gusta" y de comentarios. A esto se suma la **transcripción** completa del audio, que es la materia prima del análisis de lenguaje. De estos campos brutos se derivan las **características (features)** que consume el scorer: densidad de cifras por cada 100 palabras, ratio de palabras únicas (riqueza léxica), número de referencias a fuentes/evidencia, índice de legibilidad (Flesch), ratio de bigramas únicos (repetición), proporción de mayúsculas y palabras emocionales en el título, ratio like/visualización y comentario/visualización, etc.

**Por cada evento de consumo (para el dashboard).** Identificador seudónimo de usuario, video visto y marca temporal de la visualización. Es lo que permite reconstruir la "dieta cognitiva" a lo largo del tiempo.

**Por cada ejemplo de entrenamiento (para el modelo ML).** El vector de características anterior más una **etiqueta objetivo (target)**: la puntuación de "valor cognitivo" de referencia (numérica 0–100 o la clase A–E) que el modelo debe aprender a predecir.

### 2.2. Granularidad

Se necesitan tres niveles. A nivel **ítem de contenido** (un registro por video único) para la puntuación. A nivel **evento de visualización** (usuario × video × timestamp) para el dashboard de consumo. Y, dentro de la transcripción, granularidad de **texto/segmento** para las features de NLP. Para las visualizaciones del dashboard, la agregación natural es por usuario y por día/semana.

### 2.3. Profundidad histórica

Los metadatos de la YouTube Data API son una **foto del momento** (las visualizaciones y likes cambian con el tiempo); para el objetivo del proyecto basta con capturarlos en el instante del visionado, sin necesidad de una serie temporal profunda por video. En cambio, el **dashboard de dieta cognitiva sí requiere histórico del propio usuario**: idealmente varias semanas o meses de consumo para que la evolución tenga sentido. Para el **dataset de entrenamiento** no se necesita profundidad temporal sino **cobertura**: un conjunto de videos suficientemente variado en categorías, formatos y niveles de calidad.

### 2.4. Volumen aproximado

Para que el modelo supervisado tenga sentido, un dataset etiquetado razonable estaría en el orden de **varios cientos a unos pocos miles de videos** (una diana realista para el curso: ~500–1.500 videos etiquetados, con sus features y transcripciones). El histórico de consumo para el dashboard es de menor volumen (decenas a cientos de eventos por usuario). La YouTube Data API impone además un límite práctico: su cuota gratuita de ~10.000 unidades/día permite enriquecer varios miles de videos diarios, más que suficiente para este orden de magnitud.

### 2.5. Datos imprescindibles vs. deseables

**Imprescindibles:** los metadatos de la YouTube Data API (título, duración, categoría, estadísticas de engagement, descripción), la transcripción del video, la marca temporal de consumo y, para el modelo, la etiqueta de valor cognitivo. Sin transcripción o sin metadatos, el scorer degrada su calidad (de hecho el motor actual asigna un valor neutro a las señales que dependen de la transcripción cuando ésta no está disponible).

**Deseables pero no obligatorios:** las etiquetas (`tags`) del video, el texto de los comentarios (como señal de reflexión que genera el contenido), subtítulos en varios idiomas, señales del audio (ritmo, pausas), la miniatura, y datos de canal (antigüedad, frecuencia de publicación). Aportan precisión pero el proyecto es viable sin ellos.

---

## 3. Fuentes de datos previstas

| Fuente | Qué aporta | Acceso | Formato | Histórico | Estabilidad |
|---|---|---|---|---|---|
| **YouTube Data API v3** | Metadatos y estadísticas del video | Pública, requiere API key gratuita | JSON (REST) | Snapshot del momento | Alta (mantenida por Google) |
| **Supadata API** | Transcripciones de video | Freemium / de pago, API key | JSON (REST) | N/A | Media (proveedor externo) |
| **Extensión propia (first-party)** | Eventos de consumo del usuario | Datos generados por el propio proyecto | JSON → PostgreSQL | Se acumula con el uso | Alta (bajo mi control) |
| **Etiquetado para ML** | Target de valor cognitivo | Generado (manual + weak supervision) | Interno | N/A | Depende de la metodología |

**Detalle y enlaces.**

- **YouTube Data API v3** — endpoint `videos.list` con `part=snippet,statistics`. Fuente abierta y bien documentada, ampliamente utilizada. Documentación: <https://developers.google.com/youtube/v3/docs/videos/list>. Ya está integrada en el MVP (`youtube_api.py`).
- **Supadata** (<https://supadata.ai>) — se eligió porque resuelve un problema concreto detectado en el MVP: YouTube bloquea la extracción directa de subtítulos desde IPs de *datacenter* (como las de Render), por lo que la librería gratuita `youtube-transcript-api` deja de funcionar en producción. Supadata obtiene el transcript por su cuenta (subtítulos nativos, con *fallback* a Whisper si el video no tiene subtítulos).
- **Datos de consumo propios** — los genera la extensión y se almacenan en PostgreSQL en tres tablas: `raw_events` (ingesta cruda e inmutable, para auditoría), `content_items` (video enriquecido y limpio) y `content_scores` (historial de puntuaciones, una fila por ejecución del scorer, etiquetada con la versión del algoritmo). Este diseño permite **re-puntuar el histórico** y comparar versiones del modelo.
- **Etiquetado para el modelo ML** — se prevé construir el *ground truth* combinando (a) etiquetado manual de una muestra por mi parte según una rúbrica explícita de "valor cognitivo", y (b) *weak supervision*: usar el propio scorer por reglas y/o un LLM como etiquetador inicial para escalar el volumen, reservando la muestra manual para validar.

**Riesgos detectados en las fuentes.**

- *YouTube Data API:* límite de cuota diaria; cambios de la API o de sus términos de uso (p. ej. el conteo de "no me gusta" dejó de estar disponible públicamente); campos que pueden venir vacíos.
- *Supadata:* dependencia de un tercero y de su modelo de precios; videos sin subtítulos ni audio transcribible; respuestas asíncronas (jobs de Whisper) que la versión actual del MVP aún no procesa con *polling*; latencia en videos largos.
- *Etiquetas ML:* la principal fuente de riesgo del proyecto — el "valor cognitivo" es intrínsecamente subjetivo, y una etiqueta mal definida contamina todo el modelo (ver §5).
- *Datos de consumo:* dependen de que la extensión funcione sobre la estructura del DOM de YouTube, que cambia sin previo aviso.

---

## 4. Consideraciones de privacidad y protección de datos

**¿Hay datos personales?** Sí, y es el punto más sensible del proyecto. Los **metadatos de los videos** son información pública publicada por los creadores y no plantean problema. Pero el **historial de consumo** que alimenta el dashboard sí es un dato personal: lo que una persona mira revela intereses y puede llegar a inferir categorías especialmente protegidas por el RGPD (ideología, salud, orientación, etc.). Agregar ese historial es precisamente lo que da valor al dashboard, pero también lo que exige tratarlo con cuidado.

**Anonimización, agregación y filtrado.** Para el alcance académico del curso, la estrategia es minimizar: trabajar principalmente con **mi propio consumo** (auto-datos) y, si se incorpora algún usuario de prueba, hacerlo con **identificador seudónimo** y consentimiento explícito, sin almacenar datos identificativos (nombre, email, cuenta de Google). Los comentarios que se usen como señal se tratarían de forma agregada, sin nombres de usuario. El dashboard puede construirse sobre datos **agregados** sin necesidad de exponer el detalle evento a evento.

**Uso seguro en contexto académico.** El proyecto es seguro para un trabajo de máster si se limita a (a) metadatos públicos de videos y (b) el consumo propio o de voluntarios con consentimiento. No se recolecta consumo de terceros sin su conocimiento ni se construyen perfiles de personas ajenas.

**Riesgos éticos y legales a tener en cuenta.**

- **Términos de las APIs:** las *YouTube API Services Terms* imponen restricciones sobre almacenamiento y retención de datos y sobre la creación de perfiles; hay que respetarlas (no acumular indefinidamente estadísticas, no usar los datos para fines no permitidos).
- **RGPD** (contexto España/UE): base de legitimación (consentimiento), minimización de datos y derecho de supresión si hubiera usuarios reales.
- **Sesgo y encuadre del propio score:** el scorer incorpora juicios de valor (penaliza formatos cortos, favorece ciertas categorías como Educación/Ciencia). Presentar una letra A–E sobre contenido ajeno tiene un riesgo ético de "juzgar" creadores; conviene comunicar el score como orientativo y transparente en sus criterios, no como verdad objetiva.

**Datos que se decide evitar.** No se recolectará consumo de usuarios sin consentimiento, ni información personal identificable de los espectadores, ni datos de creadores más allá de lo ya publicado por ellos. Se evita almacenar credenciales o identificadores de cuenta de Google.

---

## 5. Viabilidad inicial del proyecto

**¿Es viable obtener los datos?** Sí. Las dos fuentes externas son accesibles (la YouTube Data API es abierta y gratuita dentro de cuota; Supadata tiene plan de acceso vía API key) y los datos de consumo los genera el propio proyecto. El hecho de que ya exista un **MVP funcionando end-to-end** —captura, enriquecimiento, puntuación y almacenamiento— es la mejor evidencia de viabilidad.

**¿Tienen calidad, granularidad e histórico suficientes?** Los metadatos de YouTube tienen buena calidad y granularidad. La **transcripción es la variable más irregular**: no todos los videos tienen subtítulos y la calidad varía, lo que degrada las señales de NLP en parte del catálogo. El histórico de consumo se construye con el uso, sin fricción. La pieza que **hoy no existe y hay que crear es el dataset etiquetado** para el modelo supervisado.

**¿Se puede desarrollar de forma realista durante el curso?** Sí. El flujo técnico ya está resuelto; el trabajo restante —construir el dataset, entrenar y validar un modelo, y montar el dashboard— es acotado y encaja en el tiempo del curso, sobre todo porque el scorer por reglas ya proporciona una línea base y una vía de etiquetado.

**¿Qué es lo más arriesgado en este momento?** Dos cosas. La primera y principal: **definir un *ground truth* defendible de "valor cognitivo"**. Es una etiqueta subjetiva; si no se define con una rúbrica clara y consistente, el modelo aprenderá ruido. La segunda: la **dependencia de Supadata** para las transcripciones, que es un tercero de pago y un punto único de fallo.

**¿Qué alternativa hay si la fuente principal falla?**

- Si falla la **YouTube Data API** (cuota/términos): usar `yt-dlp` para obtener metadatos básicos, o reducir el enriquecimiento a lo que aporta la propia página.
- Si falla **Supadata** (transcripciones): volver a `youtube-transcript-api` ejecutada desde una IP residencial, o transcribir localmente con **Whisper** (open source), asumiendo más coste de cómputo.
- Si el **modelo ML** no rinde por falta de datos etiquetados: mantener el **scorer por reglas** como producto final, calibrado y validado contra la muestra etiquetada manualmente. El proyecto sigue siendo entregable y defendible con esta ruta, lo que reduce el riesgo global.

**Valoración global.** El proyecto es viable: fuentes accesibles, MVP ya operativo y un plan de contingencia claro en cada eslabón. El riesgo se concentra en la definición y construcción del dataset etiquetado, que es también la parte más interesante desde el punto de vista de Data Science.
