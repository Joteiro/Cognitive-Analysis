# Verificacion de la etiqueta de formato

Generado 2026-08-31 11:23 UTC · modelo `gemini-2.5-flash` · version `verificar-formato-0.2`

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

6 de 84 videos son `informativo` unicamente porque el canal
se declara asi, mientras su formato editorial (`et_formato`) apunta a conversacion
larga, directo, opinion o resumen de evento. No es una contradiccion —`formato` es un
eje de tema y `et_formato` de forma— pero si significa que la etiqueta no tiene
ningun respaldo en el contenido.

## 3. Fiabilidad del instrumento (test-retest)

Cada video se clasifico **dos veces mostrando partes distintas de la transcripcion**.
Solo se considera firme el desacuerdo que se repite en ambas pasadas.

El motivo es un hallazgo de la version anterior: se le pedia al modelo que declarara
su propia confianza y contesto **"alta" en el 100 % de los casos**. La
confianza autodeclarada no discriminaba nada, y el filtro que dependia de ella estaba
excluyendo todos los desacuerdos sin distinguir. La autoconsistencia entre pasadas es
una senal **medida** en vez de declarada — el mismo criterio de re-test que el proyecto
tiene previsto aplicar a los evaluadores humanos.

| | n | |
|---|---:|---:|
| Coincide consigo mismo | 82 | 98 % |
| Se contradice entre pasadas | 2 | 2 % |

**Kappa intra-evaluador (pasada 1 vs pasada 2): nan** (no calculable).

Los videos que se contradicen **no se excluyen del quiz**: el instrumento no tiene
nada firme que decir sobre ellos, y excluirlos seria castigar al video por la
indecision del verificador.

## 4. Capa 2 — concordancia entre la regla y el modelo

| | n | |
|---|---:|---:|
| Videos verificados | 82 | |
| Coinciden | 57 | 70 % |
| Discrepan | 25 | 30 % |
| Discrepan con confianza alta | 25 | 30 % |

**Kappa de Cohen: 0.54** (moderado).

El acuerdo bruto solo no basta: si una categoria domina el corpus, dos clasificadores
que la eligieran siempre acordarian mucho sin saber nada. Kappa descuenta ese acuerdo
esperable por azar.

### Tabla cruzada (filas: la regla · columnas: el modelo)

| regla \\ modelo | informativo | practico_personal | entretenimiento | deporte_gaming |
|---|---|---|---|---|
| **informativo** | 30 | 2 | 5 | 0 |
| **practico_personal** | 10 | 1 | 3 | 0 |
| **entretenimiento** | 5 | 0 | 15 | 0 |
| **deporte_gaming** | 0 | 0 | 0 | 11 |

## 5. Desacuerdos firmes (se repiten en las dos pasadas)

**¿QUIÉN ES PAOLO ROCCA? | RADIOGRAFÍAS del PODER con Diego GENOUD**  
regla: `entretenimiento` · modelo: `informativo` · et_formato: `sin_clasificar` · 32 min  
> El video analiza la figura de un empresario influyente y su impacto en el país, con el propósito principal de informar y explicar.

**San Andrés: Los piratas del Caribe colombiano 🇨🇴**  
regla: `practico_personal` · modelo: `entretenimiento` · et_formato: `sin_clasificar` · 30 min  
> Es un vlog de viajes donde el narrador comparte su experiencia personal, observaciones y reflexiones sobre San Andrés, con un propósito principal de entretener.

**No podré volver a Haití...**  
regla: `practico_personal` · modelo: `entretenimiento` · et_formato: `sin_clasificar` · 17 min  
> El video es una narración personal del creador sobre sus experiencias y amenazas, con reflexiones sobre Haití, lo que encaja en el formato de vlog o charla personal.

**"Me cuesta verme trabajando en otro lado que no sea Paren La Mano" | G**  
regla: `informativo` · modelo: `entretenimiento` · et_formato: `conversacion_larga` · 30 min  
> Es una entrevista larga y distendida donde el invitado comparte reflexiones personales y anécdotas.

**¿Por qué NADIE visita Paraguay? 🇵🇾 El país olvidado de Sudamérica**  
regla: `practico_personal` · modelo: `entretenimiento` · et_formato: `explicativo` · 28 min  
> Es un vlog de viajes donde el creador comparte su experiencia y descubrimientos personales, con un propósito principal de entretener.

**We’re Recreating a Lost Ecosystem**  
regla: `practico_personal` · modelo: `informativo` · et_formato: `sin_clasificar` · 13 min  
> El video explica la historia de un ecosistema perdido y los esfuerzos para recrearlo, con el propósito de informar al espectador sobre el tema.

**TRUMP SE RETIRA DE IRÁN pero Israel quiere seguir luchando - @SoloFons**  
regla: `informativo` · modelo: `entretenimiento` · et_formato: `actualidad` · 31 min  
> El video analiza la actualidad política con un tono sarcástico y dramático, buscando la interacción y el entretenimiento del espectador a través de la opinión del presentador.

**NEWTON y el MUNDO ANTES de la FÍSICA CUÁNTICA | Juan Pablo PAZ en INDU**  
regla: `entretenimiento` · modelo: `informativo` · et_formato: `sin_clasificar` · 59 min  
> El video se presenta como un espacio de divulgación científica para aprender y compartir conocimiento sobre física.

**¿Dónde podríamos fundar un nuevo país?**  
regla: `practico_personal` · modelo: `informativo` · et_formato: `sin_clasificar` · 11 min  
> El video analiza y explica los requisitos y desafíos para fundar un nuevo país en un ejercicio hipotético, buscando que el espectador entienda el tema.

**PADRE BOLUDO, HIJO BOLUDO #1 con ROBERTO y EIAL MOLDAVSKY**  
regla: `informativo` · modelo: `entretenimiento` · et_formato: `conversacion_larga` · 47 min  
> Es una charla distendida y anecdótica entre padre e hijo, con el propósito principal de entretener.

**¿Por qué existen las guayanas?**  
regla: `practico_personal` · modelo: `informativo` · et_formato: `explicativo` · 11 min  
> El video explica las particularidades geográficas, culturales e históricas de las Guayanas para que el espectador entienda por qué son diferentes.

**REBORD Y LA VERDAD SOBRE BLENDER - MOVISTAR ARENA HAGOVERO EL 19 DE OC**  
regla: `informativo` · modelo: `entretenimiento` · et_formato: `conversacion_larga` · 130 min  
> El video es una charla larga y teatralizada con interacción directa con la audiencia, promoción de canal y un tono dramático/poético, característico de streams o contenido de entretenimiento.

**Nuevo CHATGPT para Arquitectura e Interiorismo ▶ Proyectos completos**  
regla: `informativo` · modelo: `practico_personal` · et_formato: `divulgacion` · 8 min  
> El video enseña cómo aplicar ChatGPT y la IA para diseñar proyectos de arquitectura e interiorismo, incluyendo un paso a paso y posibilidades prácticas.

**ANÁLISIS FUTBORDISTICO: ARGENTINA - INGLATERRA | SE VIENE ESPAÑA**  
regla: `informativo` · modelo: `entretenimiento` · et_formato: `explicativo` · 53 min  
> Es una charla larga y distendida sobre fútbol, con tono personal y de interacción con la audiencia, más allá de un análisis objetivo.

**We Let Beavers Transform an Old Farm**  
regla: `practico_personal` · modelo: `informativo` · et_formato: `sin_clasificar` · 14 min  
> El video explica cómo los castores pueden restaurar ecosistemas y muestra un proyecto real, buscando que el espectador entienda el proceso y sus beneficios.

**Isla Nula, ¿real o imaginaria?**  
regla: `practico_personal` · modelo: `informativo` · et_formato: `sin_clasificar` · 9 min  
> El video explica la naturaleza y el origen de la 'Isla Nula' y conceptos geográficos relacionados, buscando que el espectador entienda el tema.

**Trinidad y Tobago, ¿el 14° país sudamericano?**  
regla: `practico_personal` · modelo: `informativo` · et_formato: `sin_clasificar` · 9 min  
> El video explica y analiza los argumentos geográficos y culturales sobre la pertenencia de Trinidad y Tobago a Sudamérica, buscando que el espectador entienda el tema.

**How Manu Chao Lost Everything... Then Made a Masterpiece**  
regla: `entretenimiento` · modelo: `informativo` · et_formato: `sin_clasificar` · 14 min  
> El video analiza la historia, el contexto y los temas del álbum 'Clandestino' de Manu Chao, buscando que el espectador entienda su significado y creación.

**Istmo de Panamá, ¿el puente que conectó dos mundos?**  
regla: `practico_personal` · modelo: `informativo` · et_formato: `sin_clasificar` · 10 min  
> El video explica la formación y el impacto geográfico e histórico del Istmo de Panamá, buscando que el espectador entienda el tema.

**¿Qué pasa si un NIÑO nunca escucha HABLAR a nadie? | La Ratonera 06**  
regla: `practico_personal` · modelo: `informativo` · et_formato: `conversacion_larga` · 28 min  
> El propósito principal es divulgar y explicar conceptos lingüísticos y científicos, como se evidencia en el título, la discusión de puntos gramaticales y el agradecimiento del patrocinador por 'divulgar ciencia'.

**😱 ¿Por qué los economistas NUNCA se ponen de acuerdo? 💰 Hay una explic**  
regla: `entretenimiento` · modelo: `informativo` · et_formato: `None` · 16 min  
> El video explica y analiza las razones por las que los economistas no se ponen de acuerdo, divulgando conceptos sobre la naturaleza de la economía.

**8 técnicas científicas para aprender algo nuevo o prepararse para un e**  
regla: `informativo` · modelo: `practico_personal` · et_formato: `lista_ranking` · 10 min  
> El video ofrece 8 consejos prácticos y probados científicamente para aprender algo nuevo o prepararse para un examen, con el propósito de que el espectador HAGA algo.

**Por Qué el Mar Más Mortal de Europa No Tiene Sentido**  
regla: `practico_personal` · modelo: `informativo` · et_formato: `explicativo` · 15 min  
> El video explica curiosidades geográficas e históricas del Mar del Norte, con el propósito principal de que el espectador aprenda y entienda.

**¿Cómo vive la gente a 400 KM sobre la tierra? ¿Cómo funciona ISS? Esta**  
regla: `practico_personal` · modelo: `informativo` · et_formato: `directo` · 4 min  
> El video explica el funcionamiento de la ISS y la vida en ella, con el propósito de divulgar conocimiento.

**Trump y Macri: una historia de negocios | #BIZELANEAS de verano**  
regla: `entretenimiento` · modelo: `informativo` · et_formato: `sin_clasificar` · 9 min  
> El video narra y explica una historia de negocios histórica entre Trump y Macri, con el propósito principal de que el espectador entienda los eventos.

## 6. Como se usa

`generar_quiz.py` lee `formato_verificado.json` y **se salta** los videos donde el
modelo discrepa con confianza alta, avisando por pantalla. Es una decision de uso
del dato, no una correccion del dato.

Si kappa es bajo, la conclusion NO es que el modelo tenga razon: es que la etiqueta
derivada de la categoria de YouTube y el contenido observable miden cosas distintas,
y eso hay que decirlo al presentar cualquier resultado partido por formato.