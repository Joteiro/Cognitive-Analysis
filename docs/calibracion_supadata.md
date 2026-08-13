# Calibracion: subtitulos de YouTube contra Supadata

**Generado:** 2026-08-13T09:59:08+00:00 · **n = 7** videos del corpus de referencia, pareados (mismo video, mismos metadatos, sola diferencia el texto de la transcripcion).

La escala se construyo con subtitulos propios de YouTube. Si el panel va a funcionar con Supadata, hay que saber cuanto corre eso las mediciones.


## Volumen de texto

- Palabras con YouTube: mediana **745**
- Palabras con Supadata: mediana **749** (+0.5 % respecto de YouTube)
- Videos que dejan de ser aptos al cambiar de fuente: **0** de 7


## Desplazamiento por descriptor

| descriptor | n | corr Pearson | corr Spearman | cambio rel. mediano | desplaz. percentil (mediana / p90) | % que cambian de tramo |
|---|---|---|---|---|---|---|
| ritmo_ppm | 7 | 1.0 | 0.964 | 0.002 | 1.0 / 1.4 | 0% |
| cifras_100w | 7 | 1.0 | 1.0 | 0.0 | 0.0 / 1.0 | 0% |
| atribucion_1000w | 7 | 1.0 | 1.0 | 0.004 | 0.0 / 0.0 | 0% |
| mattr_200 | 7 | 1.0 | 1.0 | 0.001 | 0.0 / 2.4 | 0% |
| conectores_1000w | 7 | 0.996 | 1.0 | 0.005 | 0.0 / 3.8 | 0% |
| enlaces_externos | 7 | 1.0 | 1.0 | 0.0 | 0.0 / 0.0 | 0% |
| promocional_1000w | 7 | 1.0 | 1.0 | 0.0 | 0.0 / 0.4 | 0% |
| cobertura_titulo | 7 | 1.0 | 1.0 | 0.0 | 0.0 / 0.0 | 0% |

**La columna que decide es la ultima.** La correlacion puede ser alta y aun asi el panel mentir: si Supadata mide sistematicamente 20 % mas alto, la correlacion da 0,99 y todos los videos suben de tramo igual. Lo que importa es cuantos videos quedarian en un cajon distinto.


> **Veredicto: la escala se puede reutilizar.** El descriptor mas afectado cambia de tramo en el 0 % de los videos. Alcanza con declarar el cambio de instrumento como limitacion.


## Puntuacion: la huella del instrumento

- Palabras por signo con YouTube: **23**
- Palabras por signo con Supadata: **23.2**

Si el segundo numero es mucho menor, Supadata esta insertando puntuacion que el hablante no dijo. No afecta a los 8 del panel (ninguno depende de puntuacion) pero confirma que es post-procesado, e invalida cualquier indicador futuro basado en frases.
