# Validacion y construccion de la escala de referencia

**Marco:** `mm-2026-08-v1` - **Generado:** 2026-08-12T20:09:58+00:00 - **script v2.0**

410 filas - 394 con transcripcion - **344 aptas para el panel**


## 1. Como se construyo cada descriptor (decidido por medicion)

Dos decisiones independientes por descriptor, ninguna tomada a mano:

- **ambito**: `por_formato` si la prueba de permutacion rechaza que los cuatro macroformatos vengan de la misma distribucion (alfa = 0.05, 2000 remezclas). Si no, `global`.

- **tipo**: `presencia` si mas de un tercio del corpus vale exactamente 0. Ahi el tercil 'bajo' abarcaria a mas de un tercio y dejaria de ser un tercil: lo informativo pasa a ser si esta o no.

| descriptor | % en cero | p permutacion | tipo | ambito |
|---|---|---|---|---|
| ritmo_ppm | 0% | 0.263 | continuo | global |
| cifras_100w | 2% | **0.003** | continuo | **por formato** |
| atribucion_1000w | 51% | **0.002** | presencia | **por formato** |
| mattr_200 | 0% | 0.653 | continuo | global |
| conectores_1000w | 4% | 0.840 | continuo | global |
| enlaces_externos | 54% | **0.019** | presencia | **por formato** |
| promocional_1000w | 55% | **0.004** | presencia | **por formato** |
| cobertura_titulo | 2% | **0.008** | continuo | **por formato** |

**3 de 8 usan escala global**: los cortes por formato se movian, pero se mueven igual al remezclar las etiquetas al azar. Con ~86 casos por grupo esa dispersion es ruido de estimacion, no diferencia real. **5 si difieren** y llevan corte por formato.

**3 de 8 son de tipo presencia.** No se publican terciles de esos: se publica si el video lo tiene y, si lo tiene, cuanto compara con los que tambien lo tienen.


## 2. Volvio el vicio de la duracion?

El panel se eligio contra 60 videos del historial personal. Esta es la comprobacion sobre el corpus publico. **La columna que manda es la media intra-celda**, no el peor: con n cercano a 28 el error tipico de una correlacion ronda 0,2, asi que valores de mas o menos 0,4 salen por azar, y tomar el maximo de 12 celdas los infla por construccion.

| descriptor | corr global | corr intra (peor) | corr intra (media) | eta2 celda |
|---|---|---|---|---|
| ritmo_ppm | -0.107 | -0.272 | -0.043 | 0.039 |
| cifras_100w | 0.022 | 0.37 | -0.021 | 0.053 |
| atribucion_1000w | -0.05 | 0.241 | -0.04 | 0.094 |
| mattr_200 | 0.057 | -0.459 | 0.064 | 0.053 |
| conectores_1000w | 0.08 | 0.325 | 0.025 | 0.032 |
| enlaces_externos | -0.025 | 0.318 | -0.007 | 0.039 |
| promocional_1000w | -0.16 | 0.437 | -0.04 | 0.085 |
| cobertura_titulo | 0.224 | 0.463 | 0.13 | 0.077 |

Peor **media** intra-celda: **0.130**. El scorer v1 tenia 0,73 entre su score y la duracion. Los ocho descriptores sobreviven.


## 3. Hay descriptores redundantes?

Correlacion mutua maxima: **0.257**. Los cinco pares mas altos:

- `ritmo_ppm` <-> `conectores_1000w`: +0.257
- `mattr_200` <-> `cobertura_titulo`: +0.242
- `ritmo_ppm` <-> `mattr_200`: +0.193
- `atribucion_1000w` <-> `mattr_200`: +0.165
- `conectores_1000w` <-> `cobertura_titulo`: +0.147

Ninguno mide lo mismo que otro: el panel tiene ocho numeros, no ocho copias del mismo numero.


## 4. Cribado por formato (los que no admiten panel)

| formato | con transcripcion | aptos | cribados | % |
|---|---|---|---|---|
| informativo | 99 | 96 | 3 | 3.0% |
| practico_personal | 98 | 81 | 17 | 17.3% |
| entretenimiento | 99 | 80 | 19 | 19.2% |
| deporte_gaming | 98 | 87 | 11 | 11.2% |

Los cribados son videos sin habla suficiente: musica, karaoke, tomas aereas, gameplay con comentario esporadico. No son valores bajos: el panel no les aplica.

**Cruzando esta seccion con la 1 sale el resultado principal**: los formatos casi no se diferencian en como puntuan (6 de 8 descriptores no distinguen formato), pero se diferencian mucho en **si se pueden puntuar** (del 3 % al 19 % de cribado). La frontera relevante no pasa entre informativo y entretenimiento: pasa entre tener habla y no tenerla.


## Anexo. Cortes por celda (12 celdas), como evidencia

No es la escala que se publica: es el material sobre el que se corrio la prueba de la seccion 1. Se conserva para que la decision sea auditable.

| formato | corto | medio | largo |
|---|---|---|---|
| informativo | 32 | 31 | 33 |
| practico_personal | 25 | 28 | 28 |
| entretenimiento | 22 | 28 | 30 |
| deporte_gaming | 28 | 30 | 29 |

(n util por celda; los cortes correspondientes estan en `escala_por_celda_anexo.csv`)
