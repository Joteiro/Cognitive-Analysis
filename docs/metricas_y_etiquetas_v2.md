# Métricas y etiquetas para `content_items`

**Propuesta v2.0 — calculada y verificada sobre las 94 filas reales del CSV (2026-08-05)**

---

## La idea de fondo

Una etiqueta nutricional no dice "esta comida es buena". Dice *cuánta proteína, cuánto azúcar, cuánta sal por 100 g*, y deja que quien la lee decida según su objetivo. El que quiere ganar músculo mira una fila; el que quiere bajar de peso mira otra. **Ese es exactamente el reencuadre que ya tomaste**: descriptores verificables en vez de una letra A–E.

Entonces la pregunta "¿qué métricas?" se responde en cuatro capas, no en una lista:

| Capa | Qué es | Análogo nutricional |
|---|---|---|
| **0. Validez** | qué se puede medir en cada fila | si la balanza está calibrada |
| **1. Panel** | 8 números por 100 palabras / por minuto | la tabla del envase |
| **2. Tabla ancha** | ~40 indicadores para el estudio | el análisis de laboratorio |
| **3. Dieta** | qué consumiste y cuánto (dashboard) | el diario de comidas |

Las **etiquetas** son transversales: son las categorías del producto (marca, formato, fecha de caducidad), no números.

Todo esto está implementado y corrido: `nutriscore_features.py` → `content_features_draft.csv` (94 filas × 80 columnas).

---

## Capa 0 — Validez del dato

Esta es la capa que casi nadie pone y sin la cual todo lo demás miente. **Un indicador calculado sobre una transcripción truncada o sin puntuación no es un dato malo: es un dato falso.**

| Campo | Regla | Resultado en tu corpus |
|---|---|---|
| `v_tiene_transcripcion` | `transcript` no vacío | 62 / 94 |
| `v_fuente_transcripcion` | `transcript_source` | 45 auto, 11 manual, 6 supadata |
| `v_palabras_por_signo` | palabras ÷ signos `.!?` | mediana 13,6 |
| `v_tiene_puntuacion` | ratio < 60 | gate para `palabras_por_frase` y `preguntas_1000w` |
| `v_cobertura_transcripcion` | palabras ÷ (min × 150 ppm) | mediana **1,09**; mín 0,55 |
| `v_transcripcion_completa` | cobertura entre 0,45 y 1,6 | 60 sí, 2 parciales |
| **`v_apto_panel`** | transcripción completa + metadatos | **60 / 94** |

> El panel se muestra **sólo** si `v_apto_panel = 1`. En los otros 34 videos la interfaz dice "sin datos suficientes", no muestra ceros. Un cero y un "no medido" no son lo mismo, y confundirlos fue lo que hundió al scorer v1.

---

## Capa 1 — El panel visible (8 descriptores)

Criterios de admisión, todos comprobados empíricamente sobre tus 60 filas aptas:

1. **|corr| con log(duración) ≤ 0,35** — que no sea duración disfrazada
2. **Varianza real** en el corpus — que discrimine
3. **Verificable a mano** — un evaluador humano tiene que poder recontarlo
4. **Baja correlación entre sí** — máximo observado: 0,53

| # | Descriptor | Unidad | Qué mide | Análogo | corr. dur. | ⅓ / ⅔ del corpus |
|---|---|---|---|---|---|---|
| 1 | **Ritmo** | palabras/min | velocidad del habla | densidad energética | **0,09** | 155 / 179 |
| 2 | **Datos** | cifras/100 palabras | cantidades, fechas, unidades | proteína | **0,11** | 1,85 / 2,39 |
| 3 | **Fuentes citadas** | menciones/1000 palabras | "según", "un estudio", "los datos" | trazabilidad de origen | 0,19 | 0,00 / 0,55 |
| 4 | **Variedad léxica** | MATTR‑200 (0–1) | vocabulario sin repetir | fibra / variedad | −0,33 | 0,57 / 0,61 |
| 5 | **Razonamiento** | conectores/1000 palabras | "porque", "sin embargo", "por lo tanto" | estructura del alimento | **−0,02** | 8,2 / 11,6 |
| 6 | **Enlaces externos** | conteo absoluto | referencias fuera del propio canal | etiqueta de origen | **−0,05** | 1 / 3 |
| 7 | **Autopromoción** | CTA+patrocinio /1000 palabras | "suscribite", "código de descuento" | **azúcares añadidos** | −0,10 | 0,03 / 0,66 |
| 8 | **Fidelidad al título** | % de palabras clave del título presentes | lo que promete vs lo que dice | **% de ingrediente principal** | 0,15 | 0,50 / 0,71 |

**Los cortes bajo/medio/alto son tercios de tu propio corpus.** Hay que declararlo en la interfaz con esas palabras: *"alto respecto de los 60 videos analizados"*, no *"alto"* a secas.

Ninguno de los ocho lleva signo de valor. El nº 7 (autopromoción) es el más tentador de leer como "malo", y por eso conviene rotularlo como *"minutos dedicados al canal en vez de al tema"* — dato, no juicio.

---

## Capa 2 — La tabla ancha (para el estudio)

Todo lo calculable, se muestre o no. Es lo que vas a correlacionar contra los juicios de los evaluadores.

**Forma del habla:** `ritmo_ppm`, `ritmo_cv` (variabilidad del ritmo en tramos de 30 s, desde `transcript_segments`), `p_tramo_silencioso`, `palabras_por_frase`*, `preguntas_1000w`*, `muletillas_1000w`

**Léxico:** `mattr_200`, `p_palabras_contenido`, `long_media_palabra`, `hapax_ratio`†

**Evidencia:** `cifras_100w`, `anios_1000w`, `porcentajes_1000w`, `unidades_1000w`, `atribucion_1000w`

**Carga cognitiva:** `conectores_1000w`, `matizadores_1000w` ("quizá", "se estima"), `absolutos_1000w` ("siempre", "sin duda"), `ratio_matiz_absoluto`

**Estructura:** `marcadores_estructura_1000w`†, `capitulos_10min`, `tiene_indice`, `desc_timestamps`

**Retención:** `cta_1000w`, `patrocinio_1000w`, `anticipacion_1000w` ("quedate hasta el final"), `promocional_1000w`

**Trazabilidad:** `enlaces_total`, `enlaces_externos`, `enlaces_fuente` (dominios .edu/.gov/doi/prensa), `desc_caracteres`

**Promesa:** `cobertura_titulo`, `densidad_tema_100w`†, `foco_promesa`†, `n_tags`, `titulo_palabras_clave`

**Señales del título (banderas, no puntaje):** `titulo_p_mayusculas`, `titulo_exclamaciones`, `titulo_es_pregunta`, `titulo_superlativos`, `titulo_numero_lista`, `titulo_banderas`

<sub>\* sólo válidos con `v_tiene_puntuacion = 1`  ·  † calculados pero **fuera del panel**, ver más abajo</sub>

---

## Etiquetas — 9, todas por reglas deterministas

Sin LLM. Cada etiqueta es un `if` que podés mostrarle al tribunal y que da el mismo resultado siempre.

| Etiqueta | Valores | Regla | Distribución en tu corpus |
|---|---|---|---|
| `et_porcion` | short / corto / medio / largo / muy_largo | cortes en 1, 10, 30, 60 min | 38 / 26 / 15 / 12 |
| `et_formato` | resumen_evento, conversacion_larga, actualidad, divulgacion, explicativo, instructivo, lista_ranking, directo, opinion_review, sin_clasificar | cascada de reglas sobre título + tags + capítulos + duración + categoría | 33 resumen, 19 actualidad, 15 conversación, **14 sin clasificar** |
| `et_caducidad` | **perecedero / perenne** | marcas temporales en título/tags ("jornada", "hoy", "2026", "highlights") | 60 / 34 |
| `et_promesa` | pregunta / lista / imperativa / declarativa | puntuación y primer token del título | 83 declarativa, 10 pregunta |
| `et_trazabilidad` | con_fuentes_verificables / con_enlaces_externos / solo_enlaces_propios / sin_enlaces | dominios de la descripción | 16 / 46 / 29 / 3 |
| `et_navegabilidad` | con_indice / timestamps_en_descripcion / bloque_continuo | `n_chapters ≥ 2` o ≥2 timestamps | 14 / 1 / 79 |
| `et_calidad_dato` | transcripcion_humana / automatica / parcial / sin_transcripcion | `transcript_source` + cobertura | 11 / 49 / 2 / 32 |
| `et_idioma` | es / en | `video_language` con fallback | 92 / 2 |
| `et_categoria_yt` | categoría nativa de YouTube | `category_name` | 35 Sports, 24 News |

**`et_caducidad` es la etiqueta que más te va a rendir.** Es la fecha de vencimiento del envase: separa lo que pierde valor en 48 horas de lo que sigue sirviendo en dos años. En tu corpus, **el 64 % de los minutos que consumiste fue contenido perecedero** — y eso es un hallazgo, no un juicio.

**`et_formato` deja 14 sin clasificar y eso está bien.** Con reglas puras, "sin clasificar" es un valor honesto. La alternativa —forzar una categoría— es justo la clase de circularidad que marcó tu profesor.

---

## Capa 3 — La dieta (sólo dashboard)

Ninguna herramienta de "score de contenido" tiene esto, porque nadie más guarda `watched_at`. Es tu diferencial real: **la etiqueta del envase no sirve de nada sin el diario de comidas.**

| Métrica | Tu dato |
|---|---|
| Minutos totales / por día activo | 2.591 min · **81 min/día** |
| Frescura al consumir (mediana) | **1 día** desde publicación |
| Videos vistos en ráfaga (<30 min del anterior) | **45 / 94** |
| Concentración por canal (HHI) | 0,216 · top‑1 = Vorterix, **41 % del tiempo** |
| % de minutos en contenido perecedero | **64 %** |

Y el hallazgo que sólo aparece midiendo minutos en vez de videos:

| | Por cantidad de videos | Por minutos consumidos |
|---|---|---|
| Sports | **35 (37 %)** | 11,7 % |
| Entertainment | 15 (16 %) | **46,6 %** |
| conversacion_larga | 15 | **53,4 %** |

Contás muchos resúmenes de fútbol de 5 minutos, pero **la mitad de tu tiempo se va en charlas largas**. Es la diferencia entre "por porción" y "por 100 g" del envase: cambiar el denominador cambia la conclusión. Ese contraste vale un gráfico entero del dashboard.

> Como es dato sensible: consentimiento explícito, borrado en un clic, y en el TFM reportarlo agregado.

---

## Lo que descarté, con la evidencia

Esto es la mitad del valor del análisis: **cada descarte es una prueba de que el método funciona.**

| Indicador | Por qué se cae | Evidencia |
|---|---|---|
| `hapax_ratio` | duración disfrazada | **corr −0,82** con log(duración) |
| `preguntas_1000w` | ídem, y depende del ASR | corr 0,70 |
| `enlaces_externos` **÷ minutos** | normalizar por duración metía la inversa de la duración dentro del indicador | corr **−0,68** normalizado → **−0,05** en absoluto |
| `marcadores_estructura` | léxico contaminado | con "primero/segundo" sueltos, los **resúmenes de fútbol encabezaban el ranking de estructura** ("el segundo gol", "primer tiempo"). Limpiado a multipalabra bajó de 10,8 a 6,5, pero sigue en corr −0,50 → fuera del panel |
| `foco_promesa` | no discrimina | mediana 0,03: el tema del título aparece casi siempre en el primer 3 % |
| `longitud media de frase` | mide al transcriptor, no al hablante | ya descartado; ahora con gate explícito `v_tiene_puntuacion` |
| `titulo_p_mayusculas` | corr 0,61 | queda sólo como **bandera binaria**, no como número |

La descripción no es un flujo, es un artefacto fijo. **Dividir por minutos lo que no fluye en el tiempo fabrica correlación con la duración.** Regla general: normalizás por minuto lo que ocurre *durante* el video, y dejás en absoluto lo que existe *alrededor* del video.

---

## Lo que decidimos no usar

`view_count`, `like_count`, `comment_count` quedan fuera. Miden al canal, al algoritmo y a la antigüedad del video — no al contenido. Meterlas convertiría el panel en un medidor de popularidad, que es lo contrario del proyecto. En el envase de un alimento no figura cuánta gente lo compró.

Si el tribunal pregunta: podés reportarlas **una sola vez**, en el capítulo de validación, para mostrar que tus descriptores **no** correlacionan con popularidad. Ese es el uso legítimo: control negativo, no variable.

---

## Cómo se conecta con la validación humana

El panel de 8 es la variable independiente; el juicio de los evaluadores es la dependiente. La rúbrica de los evaluadores debería preguntar **por los mismos ejes, en lenguaje natural**:

> *"¿Cuántas afirmaciones de este video podrías verificar por tu cuenta?"* → contrasta con `atribucion_1000w` + `enlaces_fuente`
> *"¿El video cumple lo que promete el título?"* → contrasta con `cobertura_titulo`
> *"¿Cuánto del video habla del canal en vez del tema?"* → contrasta con `promocional_1000w`

Si el acuerdo inter‑evaluador es alto **y** el indicador automático correlaciona con el juicio humano, tenés el argumento del TFM. Si el acuerdo es bajo, ese es un resultado igual de publicable: *"este eje no es medible de forma intersubjetiva"*. Las dos ramas te sirven.

---

## Próximos pasos sugeridos

1. **Integrar** `nutriscore_features.py` en `compute_features.py` y migrar `content_features` a estas columnas
2. **Ampliar el corpus** con la muestra estratificada pública — con 60 filas aptas y 41 % de un solo canal, los tercios no son estables todavía
3. **Recalcular los cortes** cuando el corpus llegue a ~200 videos con mezcla de categorías
4. **Congelar los léxicos** con número de versión (`lexicon_version`) — si cambian, los números viejos dejan de ser comparables. Ese es el error que ya cometiste una vez con `scorer_version='1.0'`

---

### Archivos

- `nutriscore_features.py` — implementación completa, comentada
- `content_features_draft.csv` — las 94 filas con todo calculado
