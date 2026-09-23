# Pruebas del sitio y de `/admin`

Las pruebas de `backend/tests/` corren sin red ni base. Estas dos necesitan algo más
—un Postgres local y un Chromium— porque justamente lo que verifican es el pegado:
SQL real, app real, navegador real. Lo único simulado es la red hacia Gemini.

| Archivo | Qué prueba |
|---|---|
| `esquema_local.sql` | El subconjunto del esquema de Supabase que hace falta (leído de la base real) |
| `sembrar.py` | Siembra datos: las filas de la foto del dashboard si está a mano, candidatos a quiz, el núcleo del reclutamiento y una participante |
| `test_admin.py` | El router `/admin` contra la app **real**: la clave, el dashboard en vivo, los candidatos, una generación entera y las RPC `obtener_quiz` / `registrar_respuestas` |
| `servidor_prueba.py` | Levanta esa misma app en uvicorn para la prueba del navegador |
| `test_sitio.py` | Las cuatro páginas en Chromium: clave equivocada, dashboard dibujando, generación de punta a punta, el quiz de la cola propia y el de una participante externa en celular |

## Correrlas

```bash
# 1. Postgres local (cualquiera sirve; el DSN se pasa por DSN_PRUEBA)
initdb -D /tmp/pg/data -U postgres -A trust
pg_ctl -D /tmp/pg/data -o "-p 55432" -l /tmp/pg/log start
createdb -h 127.0.0.1 -p 55432 -U postgres ca
psql -h 127.0.0.1 -p 55432 -U postgres -d ca -f esquema_local.sql
psql -h 127.0.0.1 -p 55432 -U postgres -d ca -f ../../migrations/013_quiz_pendientes_y_sitio.sql

# 2. Backend
python test_admin.py

# 3. Navegador (en dos consolas)
python servidor_prueba.py                       # la app en :8765
python -m http.server 8766 --directory ../../../docs
python test_sitio.py                            # deja capturas en fotos/
```

## Lo que NO se simula, a propósito

- **La clase `ClienteLLM` se construye de verdad**: lo que se reemplaza es `requests.Session`.
  Una subclase de prueba que saltee el constructor deja sin probar justo donde ya hubo un bug
  (`'Groq' object has no attribute 'limites'`).
- **Las funciones SQL son las de la migración**, corriendo en Postgres. La prueba del navegador
  intercepta las llamadas a Supabase y las ejecuta contra la base local, así que `obtener_quiz`
  y `registrar_respuestas` se ejercitan tal como están escritas.
- **El dashboard en vivo se compara fila por fila con la foto**: si el endpoint y el script
  dejaran de dar lo mismo —por ejemplo si alguien corta el día en UTC en vez de en hora de
  París— la prueba falla.
