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
