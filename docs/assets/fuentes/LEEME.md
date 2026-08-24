# Fuentes de las imágenes de la Entrega 5

Las tres imágenes de `docs/assets/` no se dibujaron a mano: son páginas HTML
renderizadas a PNG con Chromium a 2x, para que el texto quede nítido y para poder
regenerarlas si cambia un dato.

| Fuente | Imagen |
|---|---|
| `mockup_frontal.html` | `../05_mockup_frontal.png` |
| `mockup_dieta.html` | `../05_pantalla_dieta.png` |
| `mockup_quiz.html` | `../05_pantalla_quiz.png` |

`05_captura_dashboard.png` es una captura del dashboard real
(`docs/dieta_cognitiva.html`) con el filtro de formato en «informativo» y el
denominador en minutos; `mockup_dieta.html` la embebe y le agrega las llamadas.

## Regenerar

```
pip install playwright && playwright install chromium
python render.py mockup_frontal.html ../05_mockup_frontal.png 1900
python render.py mockup_dieta.html   ../05_pantalla_dieta.png 1740
python render.py mockup_quiz.html    ../05_pantalla_quiz.png  1740
```

Tipografía: Inter, con «Liberation Sans» de reserva. Si no está instalada, el
resultado sigue siendo legible pero cambia el espaciado.
