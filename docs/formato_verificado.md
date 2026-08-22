# Verificacion de la etiqueta de formato

Generado 2026-08-15 22:29 UTC · modelo `llama-3.3-70b-versatile` · version `verificar-formato-0.1`

## 1. Que es esto y que NO es

La etiqueta `formato` del proyecto se deriva **solo del `category_id` que el canal
se autodeclara en YouTube**: no mira titulo, duracion, capitulos ni transcripcion.
Es una etiqueta del canal, no del video.

Este informe **no corrige ninguna etiqueta**. La etiqueta oficial sigue siendo la de
la regla determinista. Lo que hace es medir cuanto se parece a lo que un modelo
observa en el contenido, y senalar los casos donde discrepan para no usarlos en el
quiz. El modelo es un evaluador mas, medido contra el instrumento; nunca la verdad
de referencia.

## 2. Capa 1 — etiquetas sin respaldo del contenido (cero tokens)

5 de 79 videos son `informativo` unicamente porque el canal
se declara asi, mientras su formato editorial (`et_formato`) apunta a conversacion
larga, directo, opinion o resumen de evento. No es una contradiccion —`formato` es un
eje de tema y `et_formato` de forma— pero si significa que la etiqueta no tiene
ningun respaldo en el contenido.

## 3. Capa 2 — concordancia entre la regla y el modelo

| | n | |
|---|---:|---:|
| Videos verificados | 79 | |
| Coinciden | 53 | 67 % |
| Discrepan | 26 | 33 % |
| Discrepan con confianza alta | 26 | 33 % |

**Kappa de Cohen: 0.49** (moderado).

El acuerdo bruto solo no basta: si una categoria domina el corpus, dos clasificadores
que la eligieran siempre acordarian mucho sin saber nada. Kappa descuenta ese acuerdo
esperable por azar.

### Tabla cruzada (filas: la regla · columnas: el modelo)

| regla \\ modelo | informativo | practico_personal | entretenimiento | deporte_gaming |
|---|---|---|---|---|
| **informativo** | 30 | 2 | 5 | 0 |
| **practico_personal** | 8 | 0 | 5 | 0 |
| **entretenimiento** | 5 | 0 | 14 | 0 |
| **deporte_gaming** | 0 | 0 | 1 | 9 |

## 4. Desacuerdos con confianza alta

**¿QUIÉN ES PAOLO ROCCA? | RADIOGRAFÍAS del PODER con Diego GENOUD**  
regla: `entretenimiento` · modelo: `informativo` · et_formato: `sin_clasificar` · 32 min  
> Análisis y explicación sobre un empresario y su imperio

**San Andrés: Los piratas del Caribe colombiano 🇨🇴**  
regla: `practico_personal` · modelo: `entretenimiento` · et_formato: `sin_clasificar` · 30 min  
> El tono distendido y la narrativa personal sugieren un vlog o una experiencia de viaje

**No podré volver a Haití...**  
regla: `practico_personal` · modelo: `entretenimiento` · et_formato: `sin_clasificar` · 17 min  
> El video es una charla personal y reflexiva del autor sobre su experiencia en Haití y las amenazas que recibió

**"Me cuesta verme trabajando en otro lado que no sea Paren La Mano" | G**  
regla: `informativo` · modelo: `entretenimiento` · et_formato: `conversacion_larga` · 30 min  
> Conversación distendida y charla larga con tono informal

**¿Por qué NADIE visita Paraguay? 🇵🇾 El país olvidado de Sudamérica**  
regla: `practico_personal` · modelo: `entretenimiento` · et_formato: `explicativo` · 28 min  
> El video parece ser un vlog con un tono distendido y descriptivo, enfocado en la experiencia personal del autor en Paraguay

**We’re Recreating a Lost Ecosystem**  
regla: `practico_personal` · modelo: `informativo` · et_formato: `sin_clasificar` · 13 min  
> Explicación detallada de un proyecto de restauración de ecosistemas

**🔴 EN VIVO | LA CASA DEL KUN CON EL POLLO, LAVEZZI, GALLARDO, TEVEZ, FA**  
regla: `deporte_gaming` · modelo: `entretenimiento` · et_formato: `conversacion_larga` · 90 min  
> charla distendida entre amigos sobre futbol

**El MUSEO MÁS RARO del MUNDO… y NADIE Cree Lo Que Hay Dentro 😳**  
regla: `informativo` · modelo: `entretenimiento` · et_formato: `divulgacion` · 17 min  
> El tono es distendido y el propósito es pasar el rato

**NEWTON y el MUNDO ANTES de la FÍSICA CUÁNTICA | Juan Pablo PAZ en INDU**  
regla: `entretenimiento` · modelo: `informativo` · et_formato: `sin_clasificar` · 59 min  
> La transcripción muestra un enfoque en la divulgación científica y explicación de conceptos

**¿Dónde podríamos fundar un nuevo país?**  
regla: `practico_personal` · modelo: `informativo` · et_formato: `sin_clasificar` · 11 min  
> Análisis y explicación sobre los requisitos para fundar un nuevo país

**PADRE BOLUDO, HIJO BOLUDO #1 con ROBERTO y EIAL MOLDAVSKY**  
regla: `informativo` · modelo: `entretenimiento` · et_formato: `conversacion_larga` · 47 min  
> Conversación distendida y humorística

**¿Por qué existen las guayanas?**  
regla: `practico_personal` · modelo: `informativo` · et_formato: `explicativo` · 11 min  
> La transcripción muestra un análisis y explicación detallada sobre las guayanas

**Tengo 40 años, nadie me preparó para esto...**  
regla: `practico_personal` · modelo: `entretenimiento` · et_formato: `sin_clasificar` · 27 min  
> El tono distendido y la conversación personal sugieren un propósito de entretenimiento

**REBORD Y LA VERDAD SOBRE BLENDER - MOVISTAR ARENA HAGOVERO EL 19 DE OC**  
regla: `informativo` · modelo: `entretenimiento` · et_formato: `conversacion_larga` · 130 min  
> El tono y el lenguaje utilizado sugieren una conversación distendida y poética, más enfocada en el entretenimiento que en la información objetiva.

**Nuevo CHATGPT para Arquitectura e Interiorismo ▶ Proyectos completos**  
regla: `informativo` · modelo: `practico_personal` · et_formato: `divulgacion` · 8 min  
> El video enseña paso a paso el uso de una herramienta para proyectos de arquitectura e interiorismo

**ANÁLISIS FUTBORDISTICO: ARGENTINA - INGLATERRA | SE VIENE ESPAÑA**  
regla: `informativo` · modelo: `entretenimiento` · et_formato: `explicativo` · 53 min  
> El lenguaje y el tono utilizado son informales y distendidos, propio de un stream o vlog.

**Así es la Nueva Ciudad Privada de Elon Musk**  
regla: `entretenimiento` · modelo: `informativo` · et_formato: `sin_clasificar` · 21 min  
> La transcripcion se centra en explicar y describir la Nueva Ciudad Privada de Elon Musk

**We Let Beavers Transform an Old Farm**  
regla: `practico_personal` · modelo: `informativo` · et_formato: `sin_clasificar` · 14 min  
> Explica el proceso de restauración de un ecosistema con bevers

**Isla Nula, ¿real o imaginaria?**  
regla: `practico_personal` · modelo: `informativo` · et_formato: `sin_clasificar` · 9 min  
> Explicación detallada sobre la Isla Nula y su significado geográfico

**Trinidad y Tobago, ¿el 14° país sudamericano?**  
regla: `practico_personal` · modelo: `informativo` · et_formato: `sin_clasificar` · 9 min  
> Análisis y explicación sobre la posible clasificación de Trinidad y Tobago como país sudamericano

**How Manu Chao Lost Everything... Then Made a Masterpiece**  
regla: `entretenimiento` · modelo: `informativo` · et_formato: `sin_clasificar` · 14 min  
> analiza la vida y obra de Manu Chao de manera detallada

**Istmo de Panamá, ¿el puente que conectó dos mundos?**  
regla: `practico_personal` · modelo: `informativo` · et_formato: `sin_clasificar` · 10 min  
> El video explica y analiza la formación del istmo de Panamá y su impacto en la historia

**¿Qué pasa si un NIÑO nunca escucha HABLAR a nadie? | La Ratonera 06**  
regla: `practico_personal` · modelo: `entretenimiento` · et_formato: `conversacion_larga` · 28 min  
> Conversación distendida y humorística

**😱 ¿Por qué los economistas NUNCA se ponen de acuerdo? 💰 Hay una explic**  
regla: `entretenimiento` · modelo: `informativo` · et_formato: `None` · 16 min  
> El propósito principal es explicar y analizar la falta de consenso entre economistas

**8 técnicas científicas para aprender algo nuevo o prepararse para un e**  
regla: `informativo` · modelo: `practico_personal` · et_formato: `lista_ranking` · 10 min  
> El video ofrece consejos prácticos y técnicas para aprender algo nuevo

**Por Qué el Mar Más Mortal de Europa No Tiene Sentido**  
regla: `practico_personal` · modelo: `informativo` · et_formato: `explicativo` · 15 min  
> El video presenta curiosidades geográficas y explica la historia y características del Mar del Norte

## 5. Como se usa

`generar_quiz.py` lee `formato_verificado.json` y **se salta** los videos donde el
modelo discrepa con confianza alta, avisando por pantalla. Es una decision de uso
del dato, no una correccion del dato.

Si kappa es bajo, la conclusion NO es que el modelo tenga razon: es que la etiqueta
derivada de la categoria de YouTube y el contenido observable miden cosas distintas,
y eso hay que decirlo al presentar cualquier resultado partido por formato.