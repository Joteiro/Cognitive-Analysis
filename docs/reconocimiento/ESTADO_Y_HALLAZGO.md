# Instrumento de reconocimiento — estado, hallazgo de v1 y resultado de v2

**Última actualización:** 2026-09-25 · **Rama:** `reconocimiento-piloto`
**Estado: v2 implementado y piloteado. Calibrado y funcionando, con un límite duro identificado.**

Si retomás esto, leé la sección 6 (el límite del estimador de varianza) antes de
planificar nada: define qué se puede y qué no se puede demostrar con este diseño.

---

## 1. Por qué existe esto

El quiz de opción múltiple mide con ~5 ítems por video y azar 0,25. Sobre los datos
reales (50 videos, 307 ítems, juan-01):

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

---

## 2. Qué se construyó

Tres scripts en `backend/scripts/`, reutilizando la plomería de `generar_quiz.py`
(`ClienteLLM`, proveedores, recorte de transcripciones):

| script | qué hace |
|---|---|
| `generar_reconocimiento.py` | elige videos, genera afirmaciones y señuelos, aplica los filtros, escribe la clave |
| `armar_reconocimiento_html.py` | arma el formulario **sin la clave** (le quita `clase` y `origen_video_id`) |
| `puntuar_reconocimiento.py` | d′ y sesgo por video, DE entre videos, proyección de fiabilidad |

Más `--revisar`, que da el informe de calidad del lote sin mostrar ninguna afirmación
(el archivo que los tiene es el que no hay que abrir).

---

## 3. v1: señuelos de otro video — POR QUÉ FALLÓ

Los señuelos salían de otro video del corpus, emparejado por similitud de transcripción.
Piloto de 6 videos, 224 afirmaciones:

```
d' = 2,78  IC95 [2,36 · 3,15]   acierto 0,90 · falsas alarmas 0,09
varianza entre videos: NEGATIVA, recortada a 0 → fiabilidad 0,00
```

**Tres evidencias de que discriminaba la cosa equivocada:**

1. **Techo.** Con 20+20 ítems el d′ máximo es 3,96; tres de seis videos quedaron entre
   el 87 % y el 100 % de ese tope.
2. **La varianza negativa era artefacto del techo.** El término de error del método delta
   se dispara cuando el acierto tiende a 1 (aporta 0,087 con acierto 0,70 y 0,367 con
   0,976). El ruido estimado superó a la dispersión observada y la resta dio bajo cero.
3. **El dato decisivo:** los videos que no recordaba haber visto dieron d′ MÁS alto (3,26)
   que los que sí recordaba (2,42). 19/20 aciertos con cero falsas alarmas en un video
   que no recordaba haber mirado.

**La causa:** el formulario muestra el título —y tiene que mostrarlo, si no la pregunta
no tiene referente— pero los señuelos venían de otro video. Con el título alcanzaba para
rechazarlos por tema. d′ midió consistencia temática.

### El patrón: tres veces el mismo error

| instrumento | se podía resolver sin… |
|---|---|
| scorer v1 | el contenido — era duración disfrazada (r = 0,73 con log(duración)) |
| quiz de opción múltiple | haber visto el video — conocimiento general (persona 0,658 vs LLM ciego 0,645) |
| reconocimiento v1 | recordar nada — el tema del título |

**Regla:** antes de medir con un instrumento nuevo, preguntarse qué podría resolverlo
alguien que NO tenga la cosa que se quiere medir, y meter una pregunta de control que lo
delate. Acá fue «¿te acordás de haber visto este video?». Sin ella, el piloto habría dado
d′ = 2,78 con un intervalo lindo y habría mandado a gastar 5 horas y 10 participantes.

---

## 4. v2: señuelos del MISMO video

Variantes falsas pero plausibles del propio contenido, con cinco técnicas: cambiar una
cifra o fecha, invertir una relación causal, atribuir a otro interlocutor, negar o
exagerar la conclusión, fusionar dos afirmaciones en una que combina mal sus partes.

Así la consistencia temática con el título no sirve para nada. Es el diseño estándar de
señuelos relacionados en investigación de reconocimiento.

**Lo que cambió en el código:**

- `PROMPT_ALTERACIONES` es nuevo, con tres reglas que no se negocian: plausible en el
  mundo (que nadie la descarte por absurda sin haber visto el video), mismo tema y
  vocabulario, mismo largo ±3 palabras.
- El anti-anclaje se **invirtió** y es la misma llamada: el objetivo que el control no
  encuentra se descarta por inventado, la alterada que **sí** encuentra se descarta
  porque la alteración falló.
- Se cayeron los tres filtros que existían solo para elegir el video de señuelos:
  similitud, idioma y nombres propios.
- `procesar()` ya no recibe `senuelo_src`.
- **Invariante:** los hechos se parten en dos mitades sin superposición. Si el mismo
  hecho apareciera como verdadero y como alterado, el par se delataría por contradicción.
- `--sutileza baja|media|alta` para calibrar la dificultad.

### La muestra

Seis videos que Juan miró con la extensión apagada (ids 644–649), dados de alta a mano y
enriquecidos con `enrich_local.py`. **Ventajas sobre cualquier otra muestra disponible:**
ninguno pasó por un quiz de opción múltiple (sin efecto del testeo), ninguno estaba
quemado por el piloto de v1, y son todos del mismo mes, así que la demora es constante en
vez de ir de 1 a 148 días — que fue el confundidor que dejó sin identificar el olvido.

`watched_at` = 2026-07-15 es una fecha **aproximada**, no medida: 72 días de demora.
Todos en español, de 1.598 a 4.374 palabras, de 10 a 25 minutos.

### Calidad del lote

240 afirmaciones (114 objetivos + 114 señuelos + 12 controles de atención), sutileza
media. El control descartó 16 objetivos inventados y **21 alteradas que seguían siendo
verdaderas (13 %)** — un número sano: en cero, la alteración no estaría cambiando el
contenido; en la mitad, estaría rompiendo demasiado. Sin asimetrías de largo, sin
muletillas concentradas, sin duplicadas. El 646 quedó en 14+14 porque el generador
inventó 12 objetivos en ese video.

---

## 5. RESULTADO DE v2

```
d' = 0,89  IC95 [0,48 · 1,28]   acierto 0,72 · falsas alarmas 0,40
control de atención: 0 de 12 absurdas marcadas como vistas
```

| | v1 (señuelo de otro video) | v2 (mismo video) |
|---|---|---|
| Acierto | 0,90 | **0,72** |
| Falsas alarmas | 0,09 | 0,40 |
| d′ medio | 2,78 | 0,89 |
| % del techo de d′ | 70 % | **22 %** |
| Error de medición | 0,502 | **0,191** |
| Varianza entre videos | 0,000 (negativa) | **0,105** → DE 0,32 |
| **Fiabilidad** | **0,00** | **0,36** |

**El techo desapareció y por primera vez la varianza entre videos dio positiva.** El
acierto cayó a 0,72 contra el 0,75 que se buscaba: la calibración salió casi exacta.

**Por qué bajó el error de medición a la mitad:** depende de cuán lejos del 0,5 estén las
tasas. Con acierto 0,72 aporta 0,094; con 0,90 aportaba 0,235. Estar en el medio no es
solo «más difícil», es **más preciso**.

Por video: 646 d′=1,49 · 649 1,46 · 644 1,00 · 645 0,76 · 648 0,48 · **647 0,12**. El 647
no discrimina (12/20 aciertos, 11/20 falsas alarmas) pese a que Juan dijo recordarlo.
El criterio dio negativo en los seis videos: hubo sesgo hacia el «sí», que infla acierto
y falsas alarmas juntos pero no afecta a d′.

---

## 6. EL LÍMITE DURO (el hallazgo metodológico de esta ronda)

El intervalo de la DE entre videos es **[0,00 – 0,51]**: incluye el cero. Con 6 videos un
estimador positivo no es evidencia.

**Y eso no se arregla sumando videos.** Simulado con los parámetros medidos (DE real 0,32,
error por video 0,44), la probabilidad de que el IC95 de la DE excluya el cero es:

| videos | P(el intervalo excluye el cero) |
|---|---|
| 6 | 0,00 |
| 10 | 0,01 |
| 15 | 0,04 |
| 20 | 0,09 |
| 30 | **0,21** |

Harían falta del orden de 70–80 videos, y usables no hay tantos.

**Pero demostrar que la DE es distinta de cero es la pregunta equivocada.** Es un test
sobre una componente de varianza, de lo más caro que existe en estadística. La pregunta
real es si alcanza el **n efectivo** para detectar que un descriptor predice la retención,
y ahí la fiabilidad entra como factor de atenuación, no como algo que haya que probar por
separado.

| ítems por video | 45 videos | 94 videos |
|---|---|---|
| 20 | 10,6 | 22,2 |
| 40 | 17,2 | 36,0 |
| 60 | 21,7 | 45,3 |

Contra los **4,9** de hoy con opción múltiple: entre 3 y 9 veces más.

**El límite que queda en pie:** para un r verdadero de 0,3 —el escenario realista para un
predictor basado en una característica del texto— hacía falta un n efectivo de ~85. Ni el
mejor caso de la tabla llega. **El instrumento nuevo multiplica por siete lo que había y
sigue sin alcanzar para una sola persona.** Lo que desbloquea de verdad es sumar gente, y
ahora eso es barato: a los participantes se les piden clics, no horas de video.

---

## 7. Trampas ya pagadas (no volver a descubrirlas)

- **Los modelos 2.5 de Gemini piensan por defecto y el razonamiento sale del MISMO
  presupuesto de salida que el texto.** Omitir `reasoning_effort` NO lo apaga: hay que
  mandar `"none"` explícito. Costó tres corridas (generación cortada a la afirmación 11,
  veredictos truncados, `KeyError: 'message'`).
- **No fijar `max_salida` a mano**: la config de Gemini ya trae 24000 y pisarla con 8000
  fue lo que cortaba la generación.
- **El control NO puede ser Groq en el nivel gratis.** Recibe la transcripción entera:
  ~22.000 tokens contra un cupo de 8.000/min. Hay un prechequeo que lo detecta antes de
  gastar llamadas.
- **La salida del control es una cadena de bits** (`"1010..."`), no una lista JSON. Si
  igual vuelve desalineada, se trocea en lotes de 16. Nunca aceptar una lista corta:
  desalinearía los veredictos en silencio.
- **El video 23 falla siempre** con `KeyError: 'message'` y solo ése. Probable filtro de
  contenido de Gemini sobre esa transcripción. No perseguirlo.
- **Hay una guardia estática** que verifica que toda llamada a `.format()` de un prompt
  pase exactamente los huecos declarados. Se agregó después de que un `{n}` nuevo rompiera
  el prechequeo.
- **El repo vive en OneDrive**, que se pelea con git: deja `.git/index.lock` fantasma de
  0 bytes. Verificar la edad del lock antes de borrarlo, y nunca correr `git gc --prune`
  sin confirmar primero que el commit está referenciado por una rama.

---

## 8. Videos quemados

No se pueden reutilizar para reconocimiento: la persona ya vio afirmaciones sobre ellos.

- **Piloto v1:** 85, 10, 80, 607, 27, 8
- **Piloto v2:** 644, 645, 646, 647, 648, 649

Con ítems generados pero nunca contestados (siguen limpios): 40, 23, 617.

---

## 9. Para retomar

```powershell
cd backend\scripts
.venv\Scripts\python generar_reconocimiento.py --etiqueta piloto2 --revisar
.venv\Scripts\python puntuar_reconocimiento.py --etiqueta piloto2
```

Usar **siempre** `.venv\Scripts\python` parado en `backend\scripts` — el `.venv` de la
raíz del repo está vacío (solo pip y setuptools) y `python` a secas falla con
«Falta requests».

**El siguiente paso no es más videos de una persona: son más personas.** El instrumento
ya está calibrado y el costo por participante es de clics. Con 10 personas sobre los
mismos videos, el n efectivo se multiplica sin que nadie tenga que mirar nada.
