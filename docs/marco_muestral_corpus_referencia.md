# Marco muestral del corpus de referencia

**Versión del marco:** `mm-2026-08-v1` · **Fecha:** 2026-08-10
**Script:** `backend/scripts/build_reference_corpus.py` · **Migración:** `005_reference_corpus.sql`

---

## 1. El problema que resuelve

Hasta ahora los cortes bajo/medio/alto de cada descriptor eran **los tercios del historial personal**: 94 videos vistos por una sola persona, con el 41 % de los minutos concentrados en un único canal (Vorterix) y una fuerte sobrerrepresentación de *News & Politics* en español rioplatense.

Eso no es una escala de referencia. Es un espejo. Decir "este video tiene densidad informativa alta" cuando *alta* significa "por encima de dos tercios de lo que mira Juan" es una afirmación sobre Juan, no sobre el video.

La analogía es directa: una etiqueta nutricional que dijera "alto en proteínas" tomando como referencia lo que hay en **tu** heladera. Si vivís a base de fideos, un yogur sale "altísimo en proteínas". El número no cambió; cambió contra qué lo comparás. Los valores de referencia diarios existen justamente para que la comparación no dependa de la heladera de cada uno.

---

## 2. Población objetivo

Videos de YouTube que cumplen **todas** estas condiciones:

| Criterio | Valor | Por qué |
|---|---|---|
| Idioma | español (declarado o detectado) | los léxicos de conectores, marcas promocionales y atribución están calibrados en español |
| Región de búsqueda | AR y ES | cubre las dos variantes principales del corpus de trabajo |
| Duración | 2 a 180 minutos | por debajo de 2 min no hay texto suficiente para normalizar por 100 palabras; por encima de 3 h son streams que rompen cualquier normalización por minuto |
| Estado | público, sin restricción regional | los bloqueados por país fallan el enriquecimiento y contaminan la cola |
| Categoría | las 14 categorías mapeadas a un macroformato | las categorías residuales de YouTube no forman un estrato interpretable |

**Lo que queda fuera y hay que declararlo:** Shorts, videos privados o no listados, contenido en otros idiomas, transmisiones largas, y las categorías no mapeadas. El corpus **no** representa "todo YouTube": representa el YouTube en español de formato medio, que es exactamente el universo sobre el que el sistema pretende decir algo.

---

## 3. Diseño: estratificado con asignación igual

**12 celdas = 4 macroformatos × 3 duraciones**, con ~33 videos por celda (n ≈ 400).

Los macroformatos se asignan desde el `categoryId` de YouTube, **antes** de enriquecer, porque el estrato tiene que conocerse en el momento del sorteo:

- `informativo` — News & Politics, Education, Science & Technology
- `practico_personal` — Howto & Style, People & Blogs, Travel, Pets, Autos
- `entretenimiento` — Entertainment, Comedy, Film & Animation, Music
- `deporte_gaming` — Sports, Gaming

Duraciones: `corto` 2–10 min · `medio` 10–30 min · `largo` 30–180 min.

### Por qué estratificar y no muestrear al azar

Un ritmo de 180 palabras por minuto significa cosas opuestas en un videoclip de 3 minutos y en un podcast de 90. Una escala única castigaría formatos enteros de manera sistemática: la música siempre saldría "baja densidad informativa", lo cual no es un hallazgo sino un artefacto.

**Hay precedente exacto en el Nutri-Score real**: no usa una fórmula única. Tiene reglas distintas para quesos, para materias grasas y para bebidas, precisamente porque compararlos con la misma vara produce clasificaciones absurdas. La estratificación por formato es el mismo movimiento.

### Por qué asignación igual y no proporcional

Con asignación igual cada celda tiene la misma precisión, que es lo que hace falta para publicar percentiles por estrato. El costo es que la muestra **no** reproduce la mezcla real de YouTube: si el 40 % de los videos en español son de entretenimiento, en el corpus siguen siendo el 25 %.

Ese costo es recuperable. El script escribe `docs/corpus_referencia_auditoria.csv` con el número de candidatos observados por celda y el **peso de reponderación** correspondiente. Para cualquier afirmación sobre "YouTube en conjunto" hay que aplicar esos pesos; para afirmaciones dentro de un estrato, no.

---

## 4. Las dos fuentes

Ninguna vía de acceso a YouTube produce una muestra aleatoria: la API no ofrece un muestreador uniforme. En vez de fingir que sí, el corpus se construye con dos fuentes de sesgo **conocido y opuesto**, guardando la procedencia de cada video en `sampling_source` para poder comparar las dos mitades.

> **La mezcla no es 50/50 y no debe declararse como tal.** El diseño inicial hablaba de dos fuentes al 50 %, pero el sorteo nunca impuso esa cuota: toma candidatos al azar dentro de cada celda, así que la mezcla final refleja el tamaño relativo de los dos *pools*. En la ejecución del 2026-08-10 quedó en **73 % `busqueda_semilla` / 27 % `chart_canal`** (291 y 105 de 396), porque la capa A aportó 411 candidatos válidos y la B 1.144.
>
> Se deja así a propósito en vez de forzar la cuota: la capa B es la menos sesgada hacia la cabeza de la distribución, de modo que la desviación va en la dirección correcta. Pero la memoria tiene que decir 73/27, no 50/50. El CSV de auditoría registra la mezcla celda por celda (`n_chart_canal`, `n_busqueda_semilla`).

### A. `chart_canal` — canales populares

Se toman los canales que aparecen en `mostPopular` de AR y ES por categoría, y de cada canal se **sortea un video cualquiera de sus últimas subidas**, no el que es tendencia.

El matiz importa: muestrear videos en tendencia daría un corpus fechado el día del muestreo, todo reciente y todo de formato corto. Muestrear *canales* en tendencia y después sortear dentro de su catálogo da "canales que la gente efectivamente mira, video cualquiera". Sesgo declarado: sobrerrepresenta canales establecidos, subrepresenta la cola larga.

### B. `busqueda_semilla` — búsquedas neutras con ventana temporal

`search.list` con un término de una **lista fija y pública de 70 palabras** (mitad de altísima frecuencia del español hablado, mitad sustantivos cotidianos sin tema propio), con dos decisiones que hacen el trabajo:

1. **Ventana temporal aleatoria de 30 días dentro de los últimos 5 años.** Reparte el corpus en el tiempo en vez de amontonarlo en lo reciente.
2. **`order=date`, no `order=relevance`.** Esta es la decisión clave. El ranking de relevancia de YouTube es la vía principal por la que un muestreo por búsqueda se sesga hacia la cabeza: devuelve lo más visto, lo más engagement, lo del canal más grande. Ordenar por fecha dentro de una ventana estrecha convierte la búsqueda en algo mucho más parecido a "todo lo que se publicó con esta palabra en estas cuatro semanas", que es un muestreo bastante más plano.

Sesgo declarado: depende del índice de búsqueda de YouTube, que no publica su cobertura; los videos sin texto indexable (títulos vacíos, sin descripción) quedan subrepresentados.

### Control de concentración

Tope de **2 videos por canal** en todo el corpus, aplicado con asignación en dos pasadas (la primera solo admite canales todavía no usados). Se reporta el HHI de canal contra el 0,216 del historial personal como línea de base.

El sorteo va **por rondas entre celdas, no celda por celda**. Probado con 4000 candidatos sintéticos, el orden fijo dejaba `deporte_gaming` con 2 videos de 33 mientras `informativo` se llevaba 99: el tope por canal es un presupuesto compartido y las primeras celdas se lo gastaban. Con rondas, las 12 celdas quedan en 33/33.

---

## 5. Reproducibilidad

- **Semilla del sorteo fija** (`--seed 20260810`). Mismo pool de candidatos y misma semilla → misma muestra.
- **`sampling_seed`** guarda, por video, el término y la ventana temporal que lo produjo.
- **`sampling_frame_version`** queda grabada en cada fila. Si cambian los términos semilla, las categorías o los cortes de duración, sube la versión: *los percentiles calculados sobre marcos distintos no son comparables*. Este es el mismo error que ya se cometió una vez con `scorer_version='1.0'`, cuando 81 scores de un scorer de 7 señales y 9 de uno de 10 quedaron guardados bajo la misma etiqueta.
- **Cuota de API contabilizada** en el script. `search.list` cuesta 100 unidades de las 10.000 diarias; todo lo demás cuesta 1. Con 55 búsquedas el presupuesto queda en ~5.800 unidades.

---

## 6. Separación estricta del historial personal

La columna `corpus` distingue `historial` (lo que vio el usuario, tiene `watched_at`) de `referencia` (lo muestreado).

**Los percentiles se calculan solo sobre `corpus='referencia'`.** El historial nunca entra en la escala: entra como *objeto medido contra* la escala. Mezclarlos reintroduciría por la ventana la circularidad que todo este rediseño saca por la puerta.

La capa de dieta (`watched_at`, minutos por día, ráfagas, HHI de canal) sigue corriendo solo sobre `historial`, que es donde tiene sentido.

---

## 7. Limitaciones a declarar en la memoria

1. **No hay muestreo uniforme de YouTube.** El corpus es una aproximación construida con dos sesgos opuestos y documentados, no una muestra aleatoria simple. Cualquier afirmación de representatividad tiene que ir con esta advertencia.
2. **n = 400 sostiene medianas y terciles por estrato, no deciles.** Con ~33 por celda, un percentil extremo se mueve con dos o tres videos.

3. **La dimensión temporal es un muestreo por conglomerados, no simple.** La unidad que se sortea al azar es la *ventana de 30 días*, no el video: cada búsqueda devuelve hasta 50 videos del mismo mes. Con 55 búsquedas, el n efectivo para cualquier propiedad que varíe con el tiempo está más cerca de **55 que de 396**. Se ve en el histograma de la ejecución del 2026-08-10: 2026 con 123 videos y 2022 con 98, contra 2024 con 37. No es un fallo del sorteo, es la geometría del diseño, y hay que declararlo antes de afirmar cualquier tendencia temporal. Corregirlo cuesta cuota: más ventanas y más estrechas, a 100 unidades cada una.
4. **La detección de idioma es heurística** cuando la API no declara `defaultAudioLanguage`, que es la mayoría de los casos. Se usa proporción de stopwords del español, con umbral 0,12.
5. **El corpus es una foto de agosto de 2026.** Los percentiles envejecen con las normas de la plataforma: lo que hoy es "ritmo alto" puede ser la media en dos años.
6. **Sin evaluadores humanos en esta versión.** El corpus permite verificar que los descriptores discriminan y construir la escala, pero no valida que lo que miden se corresponda con el juicio de una persona. Es una limitación explícita del alcance, no un olvido.

---

## 8. Resultado de la ejecución (2026-08-10)

| | |
|---|---|
| Candidatos válidos | 1.555 (411 capa A · 1.144 capa B) |
| Muestra | **396** — las 12 celdas completas a 33 |
| Canales distintos | **396** (un video por canal; el tope de 2 nunca se activó) |
| HHI de canal | **0,0025** frente a 0,2160 del historial personal |
| Mezcla de fuentes | 291 `busqueda_semilla` / 105 `chart_canal` |
| Duración total | 195,1 h · mediana 16,0 min |
| Cuota consumida | 6.148 de 10.000 unidades |

**Composición del pool de candidatos** — es un dato sobre el YouTube en español alcanzable por este marco, no sobre la muestra: entretenimiento 37 %, práctico/personal 32 %, deporte/gaming 16 %, informativo 16 %. Lo informativo es escaso; la asignación igual lo sobrerrepresenta a propósito y los pesos del CSV lo corrigen.

**Por qué se descarta lo que se descarta** (medido, no supuesto):

| Motivo | Capa A | Capa B |
|---|---|---|
| Menos de 2 min (Shorts y clips) | 67 % | 42 % |
| Restringido por región | 5 % | 10 % |
| Idioma declarado ≠ es | 2 % | 5 % |
| Más de 3 h (streams) | 1 % | 1 % |
| **Aceptados** | **26 %** | **42 %** |

El filtro que domina, por lejos, son los Shorts. En la capa A se llevan dos tercios de los candidatos, algo esperable: un canal establecido sube muchos más Shorts que videos de más de dos minutos, y la capa A sortea dentro de las últimas subidas de cada canal. No es un problema del muestreo — es la composición real de lo que suben los canales hoy — pero explica por qué la capa A rinde 26 % y la B 42 %, y por qué la mezcla final se corre hacia la capa B.

**Verificación de reproducibilidad**: el sorteo se rehízo de forma independiente a partir de `corpus_candidatos_cache.json` y devolvió los mismos 396 videos, el mismo HHI, los mismos cinco canales encabezando y el mismo histograma anual. `--commit --cache` inserta exactamente la muestra revisada.
