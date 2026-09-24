# Pruebas del panel

Corren desde la raíz del repositorio, **sin red y sin base de datos**.

```
python backend/tests/test_panel_alternativas.py
npm install jsdom && node backend/tests/test_content_panel.mjs
```

## Qué prueba cada uno

`test_panel_alternativas.py` — simula sqlalchemy y el motor de base de datos, e
importa el `panel.py` real. Comprueba que extraer `leer_contra()` no cambió
ninguno de los ocho percentiles, que las alternativas por formato son
consistentes con la lectura oficial, los casos borde, y que lo que se **guarda**
sigue teniendo la misma forma (el dashboard lee esa tabla por posición). Incluye
un chequeo de código muerto con `ast`.

`test_content_panel.mjs` — simula el DOM, `chrome.*` y `fetch`, y ejecuta el
`content.js` entero, arranque incluido. **La respuesta con la que se prueba la
extensión la genera el backend real**, no está escrita a mano: si las dos
mitades se separan, la prueba se entera. Cubre también el despliegue desparejo
(extensión nueva contra backend viejo).

`test_dashboard_procedencia.py` — arma el dashboard con la misma plantilla que
`build_dashboard.py` y lo abre en Chromium para leer la línea de procedencia que ve
el usuario. Cubre los tres casos que van a existir: datos con `transcript_source`,
una foto anterior al cambio (sin el campo) y la mezcla, más que la línea se recalcule
al filtrar. Necesita Chromium; usa `privado/dashboard_filas.json` si está a mano y si
no inventa un recorte equivalente.

`test_comparar.py` — abre `docs/comparar.html` en Chromium cortando la llamada
a `/admin/dieta` con una respuesta falsa. Verifica los dos modos (un video y
dos), las diferencias, los avisos de formato distinto y de origen de
transcripción distinto, un id que no está en el historial, y que **no aparezca
ningún veredicto** en la página. No guarda fixture en el repositorio: lo arma al
vuelo, porque el repo es público y un fixture con datos reales publicaría el
historial de visionado.

## Regenerar el fixture

```
python - <<'PY'
import json, sys
sys.path.insert(0, 'backend/tests')
# ...ver el bloque de carga de dobles en test_panel_alternativas.py
PY
```

Más simple: correr `test_panel_alternativas.py`, que ya carga el módulo real, y
serializar `armar_respuesta(...)` a `backend/tests/fixture_panel.json`.

## Capturar el panel real

```
python backend/tests/captura_panel.py cognitive-analysis-ext/content.js \
       backend/tests/fixture_panel.json /tmp/panel.png
```

Levanta un servidor mínimo que responde en `/watch`, inyecta el `content.js` que
se instala y fotografía lo que el código dibuja. No es un mockup.
