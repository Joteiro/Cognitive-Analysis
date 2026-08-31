# Protocolo de reclutamiento y medición de la variable objetivo

**Proyecto:** Cognitive Analysis (TFM)
**Fecha:** 2026-08-31
**Estado:** diseño cerrado, pendiente de construcción

Este documento define cómo reclutar participantes externos y medir la retención (la variable objetivo del estudio) desde la propia computadora de cada persona. Nace del feedback del profesor a la entrega 4: la estrategia de medición y el modelo están bien encaminados, pero el cuello de botella ya no es el algoritmo sino la variable objetivo. Hoy todas las respuestas provienen de un solo participante (juan-01), lo que impide dos cosas: estimar si el score generaliza entre usuarios distintos, y tratar cada quiz como evidencia independiente. Reclutar varias personas externas es, en esta etapa, más importante que probar otro modelo.

---

## 1. Objetivo

Pasar de una muestra de una sola persona a una de 10-20 participantes, de modo que exista por primera vez variabilidad *entre* personas. Esa variabilidad es la que permite separar dos cosas que hoy están confundidas: cuánto retiene un contenido en general, y cuánto retiene una persona en particular. Sin ella, aunque el score fuera perfecto, no habría forma de demostrar que predice la retención de la gente y no solo la relación entre unos videos y una cabeza.

## 2. Diseño general

Cuatro definiciones estructuran todo el protocolo:

**Participantes.** 10-20 personas externas, reclutadas del entorno cercano y de conocidos de conocidos. Muestra de conveniencia, declarada como tal.

**Videos: núcleo común + rotación.** Todos ven un mismo núcleo de videos; además cada persona recibe unos pocos videos rotados. El núcleo común es lo que hace posible el análisis: si varias personas ven exactamente los mismos videos, el modelo puede separar el efecto del video del efecto de la persona. Si cada uno viera un conjunto distinto, ambos efectos volverían a mezclarse.

**Timing a criterio del participante.** No se fija un plazo entre ver el video y responder; cada persona lo hace cuando quiere, sea de inmediato o días después. En consecuencia, el retraso deja de ser un factor controlado y pasa a ser una covariable que se *registra*. Esto sacrifica control a cambio de realismo, y agrega una señal valiosa: cómo cae la retención con el tiempo.

**Acceso remoto por enlace web propio.** Cada persona recibe un enlace personal único; contesta en su navegador y la respuesta se guarda directamente en Supabase, sin que el investigador quede en el circuito de cada respuesta.

## 3. Núcleo de videos

Seis a ocho videos era el rango previsto; el núcleo final quedó en cuatro videos breves, elegidos para maximizar la finalización sin resignar diversidad de canal y tema. Suman unos 35 minutos, repartibles en varias sesiones gracias al timing flexible.

| # | id | Video | Canal | Min | Tema | Caducidad | Base LLM | Ítems difíciles |
|---|----|-------|-------|-----|------|-----------|----------|-----------------|
| 1 | 609 | "Teoría del loco" que usa Trump | BBC News Mundo | 6.5 | Política | perenne | 0.33 | 4/6 |
| 2 | 610 | Cómo las pantallas cambian tu percepción del tiempo | DW | 7.5 | Ciencia/Tecnología | perenne | 0.67 | 2/6 |
| 3 | 94 | Isla Nula, ¿real o imaginaria? | Un Mundo Inmenso | 9.1 | Geografía/curiosidad | perenne | 0.67 | 2/6 |
| 4 | 623 | ¿Por qué queremos volver a la Luna? | QuantumFracture | 11.8 | Ciencia/espacio | perecedero | 0.80 | 1/5 |

Los cuatro son del historial, están marcados como aptos y ya tienen quiz cargado. Se verificó además que los cuatro permiten incrustación (el endpoint oEmbed de YouTube devuelve metadatos válidos para todos; un video con embed deshabilitado respondería 401).

**Limitación conocida del núcleo.** Las líneas de base del LLM (0.33, 0.67, 0.67, 0.80) y la baja cantidad de ítems difíciles indican que el conjunto se inclina hacia la parte *adivinable* de la escala: en tres de los cuatro, un modelo sin ver el video ya acierta la mayoría de las preguntas. Parte de la varianza medida será entonces conocimiento previo más que retención. Lo mitigan la covariable de retraso y el ítem de honestidad (sección 5). Queda como opción sumar más adelante un video de base baja (por ejemplo el 39, Bienal de Venecia, con base 0.00 y 6/6 ítems difíciles) como quinto elemento del núcleo o en la rotación.

## 4. Rotación

El resto del pool de videos con quiz utilizable se reparte como rotación: además del núcleo, cada persona recibe 3-4 de estos videos. Conviene concentrar la rotación en un subconjunto acotado para que cada video rotado lo vean dos o tres personas, y no una sola; así incluso fuera del núcleo hay algo de cruce entre participantes. En la rotación entran los videos que, por duración o peso, no conviene imponerle a todo el mundo: los análisis políticos largos, el video de divulgación de 51 minutos, etc.

## 5. Qué se registra por respuesta

La tabla `quiz_respuestas` ya guarda, por cada (pregunta, persona, intento): la opción elegida, el acierto, los segundos de respuesta (cronómetro por pregunta) y `dias_transcurridos`. El protocolo agrega:

- **`visto_at`**: momento en que la persona terminó de ver el video (marca objetiva desde el reproductor embebido).
- **`respondido_at`**: momento del envío del quiz (ya existe).
- El **retraso** = `respondido_at − visto_at`, que alimenta `dias_transcurridos` y entra al modelo como covariable a nivel de ítem.
- **Ítem de honestidad** por video ("¿viste el video completo?"), además de la opción "no vi este video" que ya existe, para filtrar respuestas sin exposición real.
- **Señal de reproducción** (que el reproductor registre que se llegó al final, o al menos a un porcentaje mínimo), como respaldo objetivo del autoreporte.

## 6. Recorrido del participante

1. **Invitación** con un enlace personal único que lleva un token seudónimo. Un clic, sin instalar nada, desde su computadora.
2. **Consentimiento**: pantalla que explica qué es el estudio, qué datos se guardan, que es anónimo y voluntario y que puede interrumpirse en cualquier momento. Aceptar habilita el ingreso.
3. **Video embebido**. La persona lo mira dentro de la página; al terminar se registra `visto_at`.
4. **Elección**: "responder ahora" o "responder después". Si elige después, su enlace personal recuerda qué videos ya vio y cuáles le quedan pendientes de quiz para cuando vuelva.
5. **Quiz** con el formato actual: cronómetro por pregunta, no se puede dejar en blanco, opción "no vi este video". Al enviar se registra `respondido_at` y se escribe en Supabase.
6. **Revisión con soluciones** al final (ya construida): aparece recién con las respuestas ya guardadas, mostrando la opción correcta, la elegida si se erró y la cita del video como evidencia.
7. **Recordatorio** (solo para quienes eligieron responder después): un correo suave a los pocos días con el mismo enlace personal.

## 7. Infraestructura técnica

**Escritura directa a Supabase.** El formulario es HTML estático que escribe en Supabase usando la clave pública (anon). La seguridad no la da la clave —que es pública por definición— sino las políticas de fila (RLS): deben permitir *insertar* respuestas y *no* permitir leer las respuestas de otras personas ni las tablas que no correspondan. Esto se diseña una sola vez y con cuidado.

**Enlace personal.** Cada participante lleva un token en su URL que lo identifica de forma seudónima y permite: atribuir sus respuestas, excluir los videos que ya contestó y retomar el progreso cuando vuelve.

**Hosting.** Al ser estático, el formulario puede publicarse en cualquier hosting estático (el propio Supabase, Netlify, Vercel, GitHub Pages). No hace falta servidor propio.

**Exposición de la respuesta correcta.** Como el quiz muestra las soluciones al final, la opción correcta llega al navegador en algún momento y un participante curioso podría inspeccionarla antes de responder. Para un estudio voluntario de buena fe el riesgo es bajo; la decisión para esta tanda es aceptarlo y apoyarse en el ítem de honestidad, en lugar de complejizar con validación del lado del servidor.

## 8. Consentimiento y anonimato

El identificador de persona es un seudónimo (`persona_id`), ya previsto en el esquema. El único dato personal real que el protocolo necesita es un correo, y solo para el recordatorio de quienes responden en diferido. Ese correo se guarda en una tabla aparte, desvinculada de las respuestas y del `persona_id`, de modo que la base de respuestas quede anónima. El consentimiento deja claro que los datos se usan de forma agregada y anónima para el TFM.

## 9. Análisis previsto

Las respuestas se modelan a **nivel de ítem**, no promediando por persona ni por video: cada respuesta es un ensayo Bernoulli (acierto/error), con **efectos aleatorios cruzados por video y por persona**. Esta estructura es la que trata correctamente el hecho de que varios quizzes de una misma persona no son evidencia independiente, y varias personas sobre un mismo video tampoco: son medidas correlacionadas dentro de cada agrupamiento. El núcleo común es lo que da el cruce necesario para estimar ambos efectos.

Como covariables a nivel de ítem entran el **retraso** desde el visionado y la **línea de base** del LLM. Sobre la línea de base, una precisión que el profesor marcó y que el protocolo respeta: se usa como **diagnóstico de preguntas débiles** (si un modelo sin ver el video acierta de más, la pregunta es adivinable), **no** como si su tasa de conocimiento previo equivaliera a la de la persona. No se la mete como "cero humano" en la fórmula principal de retención.

Este diseño responde de forma directa a los cuatro puntos del feedback: la muestra multi-persona habilita la generalización entre usuarios; los efectos aleatorios tratan la no-independencia de los quizzes; el retraso registrado enriquece la variable objetivo; y la línea de base queda en su rol de control de calidad, no de grupo de control humano.

## 10. Limitaciones declaradas

- **Sesgo del núcleo** hacia contenidos adivinables (sección 3): parte de la varianza será conocimiento previo.
- **Autoreporte de visionado**: mitigado por la señal de reproducción, pero no eliminado.
- **Muestra de conveniencia**, no representativa de la población general.
- **Posible consulta de la respuesta correcta** en el navegador (sección 7), asumido como riesgo bajo.

## 11. Pendiente de construir

- Formulario web que reutilice el HTML actual (cronómetro por pregunta, revisión con soluciones).
- Token personal por persona con memoria de progreso.
- Escritura a Supabase con políticas RLS de inserción.
- Pantalla de consentimiento.
- Almacenamiento de `visto_at` y de la señal de reproducción del video embebido.
- Tabla de correos separada para el recordatorio del diferido.
- Publicación en un hosting estático.
