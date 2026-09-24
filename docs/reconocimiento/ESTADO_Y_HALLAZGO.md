# Instrumento de reconocimiento — estado y hallazgo del piloto

**Fecha:** 2026-09-24 · **Rama:** `reconocimiento-piloto` · **Estado: PAUSADO con una falla de validez identificada.**

Si retomás esto: leé la sección «El hallazgo» antes de tocar una línea de código. El
instrumento funciona mecánicamente y **mide la cosa equivocada**. Escalarlo como está
sería gastar horas y participantes en una medida que lee títulos.

---

## 1. Por qué existe esto

El quiz de opción múltiple mide con ~5 ítems por video y azar 0,25. Medido sobre los
datos reales (50 videos, 307 ítems, juan-01):

| | |
|---|---|
| Varianza observada de la retención | 0,0490 |
| Varianza esperada por puro azar binomial | 0,0443 (**90 % del total**) |
| Fiabilidad de la medida por video | **0,097** |
| Correlación máxima alcanzable por cualquier descriptor perfecto | r = 0,31 |
| Correlación mínima detectable con n = 50 | r = 0,39 |
| n efectivo del estudio | **4,9 videos** medidos sin error |

El techo está por debajo del piso: el diseño no podía detectar nada. El cuello de
botella es la medición, no el algoritmo.

La prueba de reconocimiento apuntaba a eso: 20 afirmaciones verdaderas del video +
20 señuelos (verdaderos también, pero de **otro** video del corpus), la persona dice
si cada una apareció, y el puntaje es **d′** (sensibilidad), no el acierto. Sin azar
de 0,25, con 40 ítems en vez de 5, y con la línea de base incorporada al propio
instrumento (los señuelos son el control, en la misma sesión y para la misma persona).

Proyección previa: fiabilidad ~0,58 con 40 ítems, n efectivo ~55 sobre 94 videos.

---

## 2. Qué se construyó

Tres scripts en `backend/scripts/`, todos reutilizando la plomería de `generar_quiz.py`
(`ClienteLLM`, proveedores, recorte de transcripciones):

| script | qué hace |
|---|---|
| `generar_reconocimiento.py` | elige videos, genera afirmaciones y señuelos, aplica los filtros, escribe la clave |
| `armar_reconocimiento_html.py` | arma el formulario **sin la clave** (le quita `clase` y `origen_video_id`) |
| `puntuar_reconocimiento.py` | d′ y sesgo por video, DE entre videos, proyección de fiabilidad |

### Los cuatro filtros del generador

1. **Emparejamiento por similitud real** (TF-IDF + coseno sobre la transcripción), no por
   `category_name`: esa etiqueta la declara el canal y junta un podcast de fútbol con una
   receta de cheesecake. Diagnóstico relativo al pool: a cuántos desvíos quedó el elegido.
2. **Mismo idioma**: sin esto, el único objetivo en inglés se emparejó con el único otro
   video en inglés del pool (geología contra un chimpancé) y el coseno dio 0,41 — estaba
   midiendo idioma, no tema.
3. **Anti-anclaje**: el control ciego juzga las 40 mezcladas contra la transcripción del
   objetivo. Se cae el objetivo que no encuentra (generador inventando) y el señuelo que
   **sí** aparece en el objetivo (convertiría un «no» correcto en falsa alarma).
4. **Nombres propios**: fuera el señuelo que nombra algo que el objetivo nunca menciona.
   Es una *preferencia*, no un corte duro — el corte duro dejó 6 señuelos contra 31
   objetivos en el video 27 y arruinó el balance.

Más: balanceo `min(objetivos, señuelos)` de cada clase (d′ sale de dos tasas; la
precisión la manda la más chica) y 2 afirmaciones absurdas por video como control de
atención.

---

## 3. El piloto

6 videos ya vistos del historial, informativos o prácticos, **sin quiz previo** (para
evitar el efecto del testeo: el quiz viejo mostraba las soluciones al terminar).
224 afirmaciones, 18 minutos de respuesta.

```
d' medio = 2,78   IC95 bootstrap por video [2,36 · 3,15]
aciertos 98/106 (0,90) · falsas alarmas 8/106 (0,09)
varianza observada de d' 0,291 · error de medición esperado 0,502
varianza entre videos: NEGATIVA, recortada a 0 → fiabilidad 0,00
control de atención: 2 de 12 absurdas marcadas como vistas
```

---

## 4. EL HALLAZGO

**El instrumento discrimina casi perfecto y discrimina la cosa equivocada.**

### La evidencia

**a) Estaba contra el techo.** Con 20+20 ítems el d′ máximo observable es 3,96. Tres de
los seis videos quedaron entre el 87 % y el 100 % de ese tope.

**b) La varianza negativa es un artefacto del techo, no una ausencia de señal.** El
término de error del método delta se dispara cuando la tasa de aciertos tiende a 1:

| tasa de aciertos | aporte al error de medición |
|---|---|
| 0,70 | 0,087 |
| 0,85 | 0,117 |
| 0,95 | 0,223 |
| 0,976 | 0,367 |

Con acierto medio 0,905, el ruido estimado (0,502) superó a la dispersión observada
(0,291) y la resta dio bajo cero. No es «no hay variación entre videos»: es «desde acá
la fórmula no puede verla».

**c) El dato que parte el diagnóstico:**

| ¿recuerda haber visto el video? | videos | d′ medio |
|---|---|---|
| Sí | 3 | 2,42 |
| Vagamente | 1 | 2,93 |
| **No me acuerdo** | 2 | **3,26** |

19 de 20 aciertos con cero falsas alarmas **en un video que no recordaba haber visto**.
Al revés de lo que predeciría la memoria.

### La causa

**El formulario muestra el título del video** — y tiene que mostrarlo, porque si no la
pregunta «¿esto apareció en este video?» no tiene referente. Pero los señuelos vienen de
*otro* video, así que con el título alcanza para rechazarlos por tema, sin recordar nada.

d′ midió **consistencia temática con el título**. Por eso da casi perfecto, por eso no
varía entre videos, y por eso los videos que no recordaba salieron mejor.

### El patrón, que ya va por la tercera vez

| instrumento | se podía resolver sin… |
|---|---|
| scorer v1 | …el contenido: era duración disfrazada (r = 0,73 con log(duración)) |
| quiz de opción múltiple | …haber visto el video: conocimiento general (la persona no le gana al LLM ciego: 0,658 vs 0,645) |
| **reconocimiento v1** | **…recordar nada: el tema del título** |

**Regla para la próxima:** antes de medir con un instrumento nuevo, preguntarse qué
podría resolverlo alguien que NO tenga la cosa que se quiere medir. Y meter siempre una
pregunta de control que lo delate — acá fue «¿te acordás de haber visto este video?», y
sin esa pregunta el piloto habría dado d′ = 2,78 con un intervalo lindo y habría mandado
a gastar cinco horas y diez participantes.

---

## 5. El rediseño (v2)

**Los señuelos tienen que salir del MISMO video, no de otro.** Variantes falsas pero
plausibles de su propio contenido:

- cambiar una cifra o una fecha
- invertir una relación causal
- atribuirle la afirmación a otro interlocutor
- negar o exagerar una conclusión
- fusionar dos afirmaciones verdaderas en una falsa

Así la consistencia temática con el título no sirve para nada y solo discrimina la
memoria episódica. Es el diseño estándar de señuelos relacionados en investigación de
reconocimiento.

**Lo bueno: casi todo el código sirve.** El filtro de anti-anclaje se **invierte** y
sigue siendo el mismo llamado — la variante alterada **no** tiene que estar respaldada
por la transcripción, y la verdadera sí. Se caen los filtros 1, 2 y 4 (similitud,
idioma, nombres propios), que existían solo para elegir el video de señuelos.

**Lo que hay que rehacer:** `PROMPT_AFIRMACIONES` necesita una segunda variante que
genere las alteraciones, y `procesar()` deja de necesitar `senuelo_src`.

**Y la dificultad hay que calibrarla.** El v1 estaba contra el techo; los señuelos del
mismo video van a ser bastante más difíciles. Apuntar a acierto ~0,75 y falsas alarmas
~0,25, que es donde la medida tiene margen para moverse en las dos direcciones.

---

## 6. Trampas ya pagadas (no volver a descubrirlas)

- **Los modelos 2.5 de Gemini piensan por defecto y el razonamiento sale del MISMO
  presupuesto de salida que el texto.** Omitir `reasoning_effort` NO lo apaga: hay que
  mandar `"none"` explícito. Costó tres corridas (generación cortada a la afirmación 11,
  veredictos truncados, `KeyError: 'message'`).
- **No fijar `max_salida` a mano**: la config de Gemini ya trae 24000 y pisarla con 8000
  fue lo que cortaba la generación.
- **El control NO puede ser Groq en el nivel gratis.** A diferencia de `generar_quiz.py`,
  acá el control recibe la transcripción entera: ~22.000 tokens contra un cupo de 8.000/min.
  Nunca entra. Hay un prechequeo que lo detecta antes de gastar llamadas.
- **La salida del control es una cadena de bits** (`"1010..."`), no una lista JSON: 64
  caracteres contra ~200 tokens. Si igual vuelve desalineada, se trocea en lotes de 16.
  Nunca aceptar una lista corta: desalinearía los veredictos en silencio.
- **El video 23 falla siempre** con `KeyError: 'message'` y solo ése. Probable filtro de
  contenido de Gemini sobre esa transcripción. No perseguirlo.
- **Hay una guardia estática** que verifica que toda llamada a `.format()` de un prompt
  pase exactamente los huecos declarados. Se agregó después de que un `{n}` nuevo rompiera
  el prechequeo.

## 7. Calidad del lote del piloto

| id | obj | señ | nota |
|---|---|---|---|
| 85, 10, 80, 607 | 20 | 20 | limpios |
| 27 | 19 | 19 | el control descartó 10 objetivos y 13 señuelos |
| 8 | 7 | 7 | el control descartó **25 de 32** objetivos — revisar por qué |
| 40 | — | — | **excluido**: pista de estilo (17 vs 12 palabras, 0 vs 4 muletillas) y señuelo FLOJO (2,9 desvíos) |
| 23 | — | — | **excluido**: falla de API persistente |

---

## 8. Para retomar

```powershell
cd backend\scripts
.venv\Scripts\python generar_reconocimiento.py --etiqueta piloto --revisar   # informe sin mostrar la clave
.venv\Scripts\python puntuar_reconocimiento.py --etiqueta piloto             # rehacer el análisis
```

Usar **siempre** `.venv\Scripts\python` parado en `backend\scripts` — el `.venv` de la
raíz del repo está vacío (solo pip y setuptools) y `python` a secas falla con
«Falta requests».
