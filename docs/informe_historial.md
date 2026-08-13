# Tu historial medido contra la escala de referencia

**Esto no es una nota.** Dice donde cae lo que miras respecto de lo que hay en YouTube en espanol, nada mas. Un percentil bajo en densidad de cifras no significa que hayas perdido el tiempo: significa que miras contenido con menos cifras que la mediana. Si eso esta bien o mal lo decidis vos segun para que lo mirabas.

96 videos en el historial - **62 admiten panel** (34 sin transcripcion completa o sin metadatos)


## Descriptores continuos: en que percentil cae tu consumo

Se calcula el percentil de **cada** video y se reporta la mediana de esos percentiles. p50 seria consumir exactamente la mediana de YouTube.

| descriptor | ambito de la escala | mediana de tus percentiles | tu mediana | mediana YouTube |
|---|---|---|---|---|
| ritmo_ppm | global | **p66** | 163.35 | 145.35 |
| cifras_100w | por formato | **p60** | 2.055 | 1.835 |
| mattr_200 | global | **p72** | 0.59545 | 0.566 |
| conectores_1000w | global | **p60** | 10.615 | 9.27 |
| cobertura_titulo | por formato | **p43** | 0.646 | 0.667 |


## Descriptores de presencia

En estos, mas de un tercio del corpus vale exactamente cero, asi que el tercil no existe. Lo informativo es **si esta o no**, y recien despues cuanto.

| descriptor | tus videos que lo tienen | videos de YouTube que lo tienen | percentil entre los que tienen |
|---|---|---|---|
| atribucion_1000w | 65% | 49% | p40 |
| enlaces_externos | 94% | 46% | p74 |
| promocional_1000w | 65% | 45% | p39 |


## Por video contra por minuto

El mismo dato cambia segun el denominador. Contar videos trata igual a un short y a un podcast de dos horas; contar minutos pesa lo que realmente ocupo tu tiempo. Es el *por porcion* contra el *por 100 g* del envase.

Los tramos son del percentil: bajo = p0-p33, medio = p33-p67, alto = p67-p100.

| descriptor | bajo (vid/min) | medio (vid/min) | alto (vid/min) | inversion |
|---|---|---|---|---|
| ritmo_ppm | 13% / 6% | 40% / 55% | 47% / 38% | -9 pp  |
| cifras_100w | 19% / 8% | 37% / 31% | 44% / 60% | +17 pp **si** |
| mattr_200 | 23% / 44% | 21% / 23% | 56% / 33% | -23 pp **si** |
| conectores_1000w | 15% / 5% | 52% / 65% | 34% / 29% | -5 pp  |
| cobertura_titulo | 30% / 20% | 49% / 60% | 21% / 21% | -1 pp  |

La ultima columna es la diferencia entre el porcentaje de minutos y el de videos en el tramo alto. Marcada cuando supera 12 puntos: ahi el denominador cambia la conclusion.


## Como se reparte tu historial entre los formatos

| formato | tus videos | tus minutos | % de tus minutos |
|---|---|---|---|
| deporte_gaming | 9 | 179 min | 7% |
| entretenimiento | 15 | 1179 min | 49% |
| informativo | 29 | 888 min | 37% |
| practico_personal | 9 | 160 min | 7% |

El estrato que mas tiempo te ocupa es **entretenimiento / largo**: 1151 minutos, el 48 % de tu tiempo total.