# Glosario: qué mide cada cosa y cómo se calcula

Documento de referencia para leer `validacion_escala.md`, `escala_referencia.csv` y `corpus_referencia_features.csv`.
Todo lo que está acá se calcula en `backend/scripts/nutriscore_features.py`, función `indicadores()`. Los léxicos están en la constante `LEX` del mismo archivo.

---

## 0. La idea de fondo

El sistema no dice si un video es bueno. Lee la transcripción y la descripción, y cuenta cosas verificables: cuántas cifras hay, cuántas veces se nombra una fuente, a qué velocidad se habla. Igual que la etiqueta de un paquete de galletitas no dice "esto es sano": dice cuántos gramos de azúcar hay, y vos decidís.

Cada número contesta una pregunta del tipo *"¿cuánto de X hay acá?"*, nunca *"¿qué tan bueno es esto?"*.

### La regla de normalización (el "por 100 g")

Un podcast de dos horas tiene más de todo que un video de tres minutos. Comparar totales sería comparar el tamaño del paquete, no su contenido. Por eso **casi todo va dividido**:

| Sufijo | Significa | Por qué así |
|---|---|---|
| `_100w` | por cada 100 palabras | para cosas frecuentes (cifras) |
| `_1000w` | por cada 1.000 palabras | para cosas raras (menciones de fuente) |
| `_ppm` | por minuto | cuando la unidad natural es el tiempo |
| sin sufijo | **valor absoluto** | sólo `enlaces_externos`, ver más abajo |

La regla que gobierna esto: **se normaliza por tiempo lo que ocurre *durante* el video; queda en absoluto lo que existe *alrededor* de él** (la descripción, los tags). Un video de 2 horas no tiene por qué tener el doble de enlaces en su descripción: la descripción es un cartel pegado en la puerta, no algo que pase adentro.

---

## 1. Los 8 descriptores del panel

### `ritmo_ppm` — velocidad del habla
**Cálculo:** `palabras de la transcripción / minutos de duración`.
**Qué mide:** a qué ritmo te llega la información. En tu corpus la media ronda las 133 palabras por minuto, que es conversación normal en español. Por encima de 180 suele indicar edición apretada, sin pausas.
**Qué NO mide:** calidad. Hablar rápido no es ni mejor ni peor; es un dato sobre el esfuerzo de atención que te va a pedir el video.

### `cifras_100w` — densidad de datos numéricos
**Cálculo:** se cuentan los números escritos en dígitos (`35`, `2,4`, `1998`) **más** los escritos en palabras (`tres`, `veinte`, `mil`), y se divide por el total de palabras × 100.
**Qué mide:** si el que habla se apoya en cantidades concretas. "El paro bajó al 11,2% en marzo" contra "el paro bajó bastante".
**Qué NO mide:** si las cifras son correctas. Un video lleno de números inventados puntúa alto. Esto es una limitación real y hay que decirla.

### `atribucion_1000w` — ¿dice de dónde lo saca?
**Cálculo:** se busca un léxico fijo de ~18 marcas de fuente (`según`, `de acuerdo con`, `un estudio`, `los datos`, `el informe`, `la encuesta`, `los expertos`, `la universidad`, `informó`, `publicó`…) y se cuenta cuántas aparecen por cada 1.000 palabras.
**Qué mide:** si el hablante señala el origen de lo que afirma. Es la diferencia entre "hay más casos" y "según el informe del ministerio hay más casos".
**Qué NO mide:** si la fuente es buena, ni si existe. Mide que la nombre, no que sea confiable. Es el equivalente a comprobar que el paquete tenga etiqueta, no a analizar el contenido en un laboratorio.

### `mattr_200` — variedad del vocabulario
**Cálculo:** se toma una ventana de 200 palabras consecutivas, se cuenta cuántas son distintas y se divide por 200. Después la ventana se desliza 50 palabras y se repite, hasta el final. El resultado es el promedio de todas esas ventanas. Va de 0 a 1.
**Qué mide:** si el vocabulario es rico o repetitivo.
**Por qué la ventana, y no simplemente "palabras distintas / palabras totales":** porque esa versión simple (el TTR clásico) **baja mecánicamente cuanto más largo es el texto**. Es inevitable: en 10.000 palabras vas a repetir "que" mil veces. Así que el TTR terminaba midiendo duración disfrazada de vocabulario. La ventana fija lo arregla — es como pesar siempre con el mismo vaso medidor en vez de comparar baldes de distinto tamaño. Éste fue uno de los errores del scorer v1.

### `conectores_1000w` — ¿las ideas están enlazadas?
**Cálculo:** léxico fijo de ~20 conectores lógicos (`porque`, `por lo tanto`, `sin embargo`, `en cambio`, `por ejemplo`, `es decir`, `en consecuencia`, `aunque`, `dado que`…), contados por 1.000 palabras.
**Qué mide:** si el discurso explicita la relación entre una idea y la siguiente, o las yuxtapone. "Llovió. No salimos." contra "No salimos **porque** llovió."
**Qué NO mide:** si el razonamiento es válido. Un argumento pésimo lleno de "por lo tanto" puntúa alto.

### `enlaces_externos` — trazabilidad declarada
**Cálculo:** URLs en la descripción del video, **descartando** las de redes sociales del propio canal (Instagram, Twitter/X, TikTok, Patreon…). **Valor absoluto, sin dividir por nada.**
**Qué mide:** si el video te deja ir a comprobar algo por tu cuenta.
**Por qué en absoluto:** ésta fue una corrección importante. En la primera versión se dividía por minutos, y eso metía la inversa de la duración dentro del indicador: la correlación con la duración era **−0,68**, o sea que el indicador medía sobre todo "video corto". Al dejarlo en absoluto bajó a **−0,05**. La descripción no es un flujo que ocurre en el tiempo, es un objeto fijo.
**Ojo:** es un conteo entero y en muchas celdas la mayoría de los videos tiene 0. Cuando eso pasa no se pueden calcular terciles y aparece en la sección `sin_cortes` del JSON.

### `promocional_1000w` — los "azúcares añadidos"
**Cálculo:** suma de dos léxicos —llamadas a la acción (`suscribite`, `dale like`, `activá las notificaciones`, `link en la descripción`, `hazte miembro`) y patrocinio (`patrocinado`, `código de descuento`, `link de afiliado`, `este video es posible gracias a`)— por cada 1.000 palabras.
**Qué mide:** cuánto del habla no es sobre el tema sino sobre el negocio del canal.
**Por qué la analogía del azúcar:** no es veneno, no invalida el contenido, pero es algo que se agrega para que el producto funcione mejor comercialmente y que a vos no te aporta. Que esté en la etiqueta te deja decidir.

### `cobertura_titulo` — ¿cumple lo que promete?
**Cálculo:** se toman las palabras clave del título (las de más de 3 letras que no son artículos ni preposiciones) y se mira qué fracción de ellas aparece efectivamente en la transcripción. Va de 0 a 1.
**Qué mide:** correspondencia entre la promesa y el contenido. Un título que anuncia "la verdad sobre el conflicto en Medio Oriente" y después nunca menciona ni "conflicto" ni "Oriente" da bajo.
**Qué NO mide:** que el video conteste bien la pregunta del título. Mide que hable del tema, no que lo resuelva. Es la comprobación más débil de las ocho y conviene presentarla así.

---

## 2. Las columnas de validez (capa 0)

Antes de calcular nada, el sistema decide si esa fila **se puede** medir. Sin este paso, todo lo demás miente.

| Columna | Qué es |
|---|---|
| `v_tiene_transcripcion` | hay texto (0/1) |
| `v_cobertura_transcripcion` | `palabras / (minutos × 150)`. 150 palabras/min es el habla castellana media, así que este número es **"qué fracción del habla esperable hay realmente"**. Un 1,0 es un video que habla todo el tiempo; un 0,05 es un videoclip |
| `v_transcripcion_completa` | la cobertura cae entre 0,45 y 1,6 (0/1) |
| `v_tiene_puntuacion` | `palabras / signos de puntuación < 60`. Los subtítulos automáticos vienen sin puntos, así que este gate distingue una transcripción con puntuación real de una donde la insertó (o no) la máquina |
| `v_apto_panel` | transcripción + completa + metadatos. **Si es 0, el panel no se muestra: se dice "sin datos suficientes", nunca cero** |

El límite inferior de 0,45 es el que descarta música, karaoke, tomas con drone y gameplay silencioso. El superior de 1,6 caza el caso raro de subtítulos duplicados.

---

## 3. Las columnas del informe de validación

Estas no describen videos: describen **si los descriptores son de fiar**. Es control de calidad del instrumento, no medición del contenido.

### `n útil`
Cuántos videos de esa celda pasaron el gate y entran en el cálculo del percentil. No es 33 en todas partes, y por eso va publicado al lado de cada corte.

### `corr global` — correlación con log(duración)
**Cálculo:** correlación de Pearson entre el descriptor y el logaritmo de la duración, sobre los 344 aptos. Va de −1 a +1.
**Para qué sirve:** detectar que un indicador sea **duración disfrazada**. Si "cantidad de proteínas" resultara ser en realidad "peso del paquete", no estarías midiendo nutrición: estarías midiendo tamaño con otro nombre. Eso es exactamente lo que le pasaba al scorer v1, donde la correlación entre el score y la duración era 0,73 — la mitad de la varianza del "valor cognitivo" era, literalmente, cuánto duraba el video.
**Por qué el logaritmo:** las duraciones van de 2 a 180 minutos, muy desparejas. Sin log, un puñado de videos larguísimos domina el cálculo. El log comprime esa cola y deja ver la relación real.

### `corr intra (peor)` y `corr intra (media)`
**Cálculo:** la misma correlación, pero **dentro de cada celda por separado**. Después se reportan dos resúmenes de esas 12 correlaciones: la de mayor valor absoluto y el promedio.
**Por qué importa más que la global:** como el diseño estratifica por duración, en la práctica sólo vas a comparar videos de duración parecida entre sí. No te preocupa que los adultos pesen más que los niños si sólo vas a comparar adultos con adultos.
**Cómo leer las dos juntas — esto es clave:** con ~28 videos por celda, el error típico de una correlación es de alrededor de 0,2. Eso significa que valores de ±0,4 aparecen **por puro azar** con bastante frecuencia. Y como el "peor" es el máximo de 12 intentos, está inflado por construcción: pescar un 0,46 entre doce muestras chicas es lo esperable aunque la correlación real sea cero.
**La columna honesta es la media.** Si el promedio de las 12 está cerca de 0 y los signos están repartidos, lo que ves en el "peor" es ruido. Si la media se despega de 0, ahí sí hay un patrón.

### `eta² celda`
**Cálculo:** de toda la variación del descriptor entre los 344 videos, qué proporción se explica sabiendo en qué celda cae. Va de 0 a 1.
**Intuición:** si te digo la altura de una persona al azar, saber si es varón o mujer explica *parte* de por qué mide lo que mide, pero no todo. Eso es eta². Un 0,30 querría decir "el formato explica el 30% de por qué este descriptor varía"; un 0,03 quiere decir "saber el formato casi no te ayuda a predecirlo".
**Para qué sirve acá:** es la justificación empírica de haber estratificado. Si diera alto, comparar formatos con una vara única habría sido un error grave. Si da bajo, los cortes van a salir parecidos en las 12 celdas y una escala global habría bastado.

### `correlación mutua`
Correlación entre cada par de descriptores. Si dos dan casi 1, están midiendo lo mismo y sobra uno. Sirve para justificar que el panel tiene ocho números y no ocho copias del mismo número.

### `cribados`
Videos con transcripción que no pasan el gate de cobertura de habla. No son valores bajos: son casos donde el panel no aplica.

---

## 4. Cómo leer TU informe (corrida del 2026-08-12)

**344 aptos de 410.** Las celdas van de 22 a 33.

**El vicio de la duración no volvió.** Las correlaciones globales están todas entre −0,16 y +0,22, muy lejos del 0,73 del scorer v1. Las medias intra-celda están todas entre −0,04 y +0,13, o sea pegadas a cero. Los "peores" llegan a 0,46 pero, por lo explicado arriba, con n≈28 y tomando el máximo de 12 eso es exactamente lo que produce el ruido. **Los ocho descriptores sobreviven.**

**eta² entre 0,032 y 0,094: todos bajos.** Esto es un resultado, no un fracaso. Dice que los ocho descriptores **se distribuyen de forma parecida en los cuatro formatos**. Un video de entretenimiento y uno informativo, cuando ambos tienen habla suficiente, se parecen más de lo que uno esperaría en ritmo, en densidad de cifras y en diversidad léxica.

**Y acá está el hallazgo más interesante de todo el informe**, que sale de cruzar la sección 3 con la 5:

> Los formatos **no** se diferencian en cómo puntúan. Se diferencian en **si se pueden puntuar**.

El cribado va de 3,0% en informativo a 19,2% en entretenimiento — una diferencia de más de seis veces. Pero el eta² dice que, entre los que sí admiten panel, el formato apenas explica nada. La frontera relevante no pasa entre "informativo" y "entretenimiento": pasa entre "tiene habla" y "no tiene habla".

Eso tiene una consecuencia práctica: **los cortes por celda van a salir muy parecidos a los globales**, y es defendible usar una escala única declarando esta medición como respaldo. La estratificación igual sirvió, pero para otra cosa: para que la muestra estuviera equilibrada y para poder demostrar este resultado.

**Correlación mutua máxima 0,257.** Los ocho miden cosas distintas. El par más alto, `ritmo_ppm` ↔ `conectores_1000w` (+0,26), tiene sentido: quien habla más fluido encadena más. Pero 0,26 es poco; no hay redundancia que justifique sacar ninguno.

---

## 5. Diccionario completo de la tabla ancha (70 columnas)

`corpus_referencia_features.csv` y `historial_features.csv` traen 70 columnas, no 8. Están todas ahí a propósito, pero **no todas se pueden usar**. Hay cuatro estados:

| Estado | Qué significa |
|---|---|
| 🟢 **PANEL** | uno de los 8 validados. Se puede publicar |
| 🔵 **estudio** | válido, pero no se muestra en el panel. Sirve para la memoria y para explorar |
| 🔴 **DESCARTADO** | se sigue calculando **para que el descarte quede auditable**, pero usarlo sería reintroducir un error ya demostrado. No publicar |
| ⚪ identificación | metadatos, no miden nada |

Ésta es la razón de la confusión: el CSV no distingue estados por sí solo. Si una columna no está en la tabla de abajo como 🟢, no va al panel.

### 5.1 Forma del habla

| Columna | Estado | Qué es |
|---|---|---|
| `ritmo_ppm` | 🟢 | palabras por minuto |
| `ritmo_cv` | 🔵 | **variabilidad del ritmo**. Se parte la transcripción en tramos de 30 s, se cuentan palabras en cada uno, y se divide el desvío por la media. Alto = habla a tirones, con pausas o silencios; bajo = caudal constante |
| `p_tramo_silencioso` | 🔵 | fracción de tramos de 30 s con menos del 40 % de las palabras del promedio. Cuánto del video es silencio o casi |
| `palabras_por_frase` | 🔴 | sólo se calcula si hay puntuación real. **Mide al transcriptor, no al hablante**: en subtítulos automáticos los puntos los pone la máquina. Se reemplazó por `ritmo_ppm` |
| `preguntas_1000w` | 🔴 | signos de pregunta por 1.000 palabras. Correlación 0,70 con la duración y depende del ASR |

### 5.2 Léxico

| Columna | Estado | Qué es |
|---|---|---|
| `mattr_200` | 🟢 | diversidad léxica con ventana fija (ver sección 1) |
| `p_palabras_contenido` | 🔵 | fracción de palabras que no son relleno gramatical (artículos, preposiciones, pronombres) ni números. Densidad de carga semántica |
| `long_media_palabra` | 🔵 | largo medio de palabra en caracteres. Proxy grosero de registro: las palabras largas suelen ser técnicas o formales |
| `muletillas_1000w` | 🔵 | "este", "eh", "o sea", "digamos", "viste", "tipo", por 1.000 palabras. **Con una trampa**: las transcripciones manuales suelen limpiarlas, así que este número mide al transcriptor tanto como al hablante. Sólo comparable dentro de `transcript_source='youtube_auto'` |
| **`hapax_ratio`** | 🔴 | **la que preguntaste.** Proporción de palabras de contenido que aparecen **exactamente una vez**. "Hapax legomenon" es griego: *dicho una sola vez*. Pretendía medir riqueza de vocabulario. **Correlación −0,82 con log(duración): la peor de todas las probadas.** La razón es puramente mecánica: en un texto corto casi toda palabra es nueva, y en uno largo repetís inevitablemente. Así que no medía vocabulario, medía longitud con otro nombre. Es el ejemplo más puro del error que hundió al scorer v1 — y por eso vale la pena que siga en el CSV, como pieza de museo |

### 5.3 Evidencia y datos

| Columna | Estado | Qué es |
|---|---|---|
| `cifras_100w` | 🟢 | números (en dígitos y en palabras) por 100 palabras |
| `atribucion_1000w` | 🟢 | marcas de fuente por 1.000 palabras |
| `anios_1000w` | 🔵 | años entre 1600 y 2049, por 1.000 palabras. Subtipo de `cifras_100w` |
| `porcentajes_1000w` | 🔵 | porcentajes ("35 %", "por ciento"), por 1.000 palabras |
| `unidades_1000w` | 🔵 | unidades de medida (km, kg, litros, toneladas…), por 1.000 palabras |

Los tres subtipos permiten decir **de qué tipo** son las cifras de un video: un video con muchos años es histórico; con muchos porcentajes, estadístico.

### 5.4 Razonamiento

| Columna | Estado | Qué es |
|---|---|---|
| `conectores_1000w` | 🟢 | conectores lógicos por 1.000 palabras |
| `matizadores_1000w` | 🔵 | *hedges*: "quizá", "probablemente", "aproximadamente", "se estima", "no está claro". Marcan **incertidumbre declarada** |
| `absolutos_1000w` | 🔵 | "siempre", "nunca", "obviamente", "sin duda", "el mejor". Afirmación sin matiz |
| `ratio_matiz_absoluto` | 🔵 | `(matizadores + 0,5) / (absolutos + 0,5)`. El 0,5 es para no dividir por cero cuando no hay ninguno. Alto = discurso cauto; bajo = tajante. **Ninguno de los dos es mejor**: un tutorial de cocina tajante está bien, un análisis geopolítico tajante es sospechoso |
| `marcadores_estructura_1000w` | 🔴 | metadiscurso: "en primer lugar", "en resumen", "para cerrar". **Fuera del panel: correlación −0,50 con la duración.** Tiene la mejor anécdota del proyecto: en la primera versión incluía ordinales sueltos ("primero", "segundo"), y los resúmenes de fútbol encabezaban el ranking de "buena estructura" porque decían "el **segundo** gol" y "**primer** tiempo". Se limpió a expresiones multipalabra y mejoró, pero sigue correlacionando demasiado |

### 5.5 Estructura y navegabilidad

| Columna | Estado | Qué es |
|---|---|---|
| `capitulos_10min` | 🔵 | capítulos declarados por cada 10 minutos de video |
| `tiene_indice` | 🔵 | binaria: tiene 2 o más capítulos |
| `desc_timestamps` | 🔵 | marcas de tiempo tipo `12:34` en la descripción. Capítulos hechos a mano |

### 5.6 Optimización para retención (los "azúcares añadidos")

| Columna | Estado | Qué es |
|---|---|---|
| `promocional_1000w` | 🟢 | suma de `cta_1000w` + `patrocinio_1000w` |
| `cta_1000w` | 🔵 | llamadas a la acción: "suscribite", "dale like", "activá la campanita", "hazte miembro" |
| `patrocinio_1000w` | 🔵 | "patrocinado", "código de descuento", "link de afiliado", "este video es posible gracias a" |
| `anticipacion_1000w` | 🔵 | ganchos de retención: "quedate hasta el final", "más adelante te cuento", "ahora vas a ver". **No entra en `promocional`** porque no vende nada: retiene. Misma familia, efecto distinto |

### 5.7 Trazabilidad (todo desde la descripción, en absoluto)

| Columna | Estado | Qué es |
|---|---|---|
| `enlaces_externos` | 🟢 | URLs que no son redes sociales del propio canal |
| `enlaces_total` | 🔵 | todas las URLs de la descripción |
| `enlaces_fuente` | 🔵 | los que apuntan a dominios considerados trazables (medios, `.gov`, `.edu`, repositorios de papers). Es el subconjunto más exigente |
| `tiene_fuentes_externas` | 🔵 | binaria |
| `desc_caracteres` | 🔵 | largo de la descripción en caracteres |

### 5.8 Promesa contra contenido

| Columna | Estado | Qué es |
|---|---|---|
| `cobertura_titulo` | 🟢 | fracción de las palabras clave del título que aparecen en la transcripción |
| `densidad_tema_100w` | 🔵 | cuántas veces por 100 palabras se menciona el tema del título. Distingue "lo nombra al pasar" de "habla de eso todo el tiempo" |
| `titulo_palabras_clave` | 🔵 | cuántas palabras clave tiene el título (denominador de `cobertura_titulo`) |
| `n_tags` | 🔵 | cantidad de tags |
| `foco_promesa` | 🔴 | posición relativa de la **primera** mención del tema (0 = arranca por el tema). **Descartado: mediana 0,03.** Casi todos los videos nombran el tema en las primeras palabras, así que no discrimina nada |

### 5.9 Señales del título (banderas, no juicios)

| Columna | Estado | Qué es |
|---|---|---|
| `titulo_p_mayusculas` | 🔴 como número | proporción de letras en mayúscula. Correlación 0,61 con la duración. **Sólo se usa como bandera binaria** (más del 50 %) |
| `titulo_exclamaciones` | 🔵 | cantidad de `!` y `¡` |
| `titulo_es_pregunta` | 🔵 | binaria: el título es una pregunta |
| `titulo_superlativos` | 🔵 | "increíble", "brutal", "impactante", "no vas a creer" |
| `titulo_numero_lista` | 🔵 | binaria: el título arranca con un número o con "top N" |
| `titulo_banderas` | 🔵 | suma de tres banderas (mayúsculas > 50 %, alguna exclamación, algún superlativo). De 0 a 3. Es el resumen de clickbait declarado, **sin decir que sea malo** |

### 5.10 Etiquetas categóricas (100 % por reglas, sin LLM)

Éstas no son números: clasifican. Todas son deterministas y auditables — dada la misma fila, siempre dan lo mismo.

| Columna | Valores posibles |
|---|---|
| `et_porcion` | `short` (≤1 min) · `corto` (≤10) · `medio` (≤30) · `largo` (≤60) · `muy_largo` · `desconocida` |
| `et_formato` | cascada de reglas por título y tags, la primera que coincide gana: `conversacion_larga`, `resumen_evento`, `instructivo`, `lista_ranking`, `directo`, `explicativo`, `opinion_review`, `actualidad`, `divulgacion`, `sin_clasificar`. **`sin_clasificar` es un valor legítimo**, no un fallo |
| `et_caducidad` | `perecedero` / `perenne`. Busca marcas temporales ("hoy", "ayer", "última hora", "en vivo") en título y tags. Fue la etiqueta más rendidora del conjunto |
| `et_promesa` | `pregunta` · `lista` · `imperativa` · `declarativa`. Qué tipo de contrato propone el título |
| `et_trazabilidad` | `con_fuentes_verificables` · `con_enlaces_externos` · `solo_enlaces_propios` · `sin_enlaces` |
| `et_navegabilidad` | `con_indice` (≥2 capítulos) · `timestamps_en_descripcion` · `bloque_continuo` |
| `et_calidad_dato` | `sin_transcripcion` · `transcripcion_parcial` · `transcripcion_automatica` · `transcripcion_humana`. **Es el gate del panel en forma de etiqueta** |
| `et_idioma` | `es` / `en` |
| `et_categoria_yt` | la categoría cruda de YouTube |

### 5.11 Columnas de validez que faltaban

| Columna | Qué es |
|---|---|
| `v_fuente_transcripcion` | `youtube_auto` · `youtube_manual` · `ninguna` |
| `v_transcripcion_auto` | binaria: la transcripción la generó la máquina |
| `v_palabras_por_signo` | palabras por cada signo de puntuación. Insumo de `v_tiene_puntuacion` |
| `v_tiene_descripcion` | binaria: la descripción no está vacía |

### 5.12 Identificación

⚪ `id`, `external_id`, `title`, `channel`, `duration_seconds`, `stratum_format`, `stratum_duration`, `sampling_source`. No miden nada: sirven para saber de qué video se habla y de qué celda salió.

---

## 6. La regla para no perderse

Cuando te encuentres con una columna que no reconocés, la pregunta útil no es "¿qué mide?" sino **"¿está en la tabla de arriba con 🟢?"**.

Si no está, hay dos posibilidades. O es 🔵 y podés usarla para explorar y para la memoria, siempre declarando que no pasó por la validación del panel. O es 🔴, y entonces alguien —vos, hace unas semanas— ya demostró con datos que usarla sería un error. Están en el CSV justamente para que ese descarte se pueda auditar en la defensa: si alguien pregunta "¿y por qué no midieron riqueza de vocabulario con hapax?", la respuesta es una columna y un número, no una opinión.
