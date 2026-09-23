"""La app REAL en uvicorn contra la base local, con la red a Gemini simulada."""
import os, sys, time, types, json, re
from pathlib import Path
AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
import sembrar
os.environ.update({"DATABASE_URL": sembrar.DSN, "ADMIN_KEY": "clave-de-prueba-larga-123",
                   "GEMINI_API_KEY": "falsa"})
sys.path.insert(0, str(sembrar.RAIZ / "backend"))
import requests, uvicorn
from app.main import app
from app.routes import admin
gq = admin._script("generar_quiz")

# reutiliza las preguntas y la sesion falsa de la prueba de backend
src = (AQUI / "test_admin.py").read_text(encoding="utf-8")
ini = src.index("PREGUNTAS = ["); fin = src.index("gq.requests = ")
ns = {"sembrar": sembrar, "json": json, "re": re, "requests": requests,
      "threading": __import__("threading")}
exec(src[ini:fin], ns)
_real_sleep = time.sleep
gq.requests = types.SimpleNamespace(Session=ns["SesionFalsa"], RequestException=requests.RequestException)
# la pausa de 6,5 s se acorta a 1 s para ver el estado "corriendo" sin esperar
gq.time = types.SimpleNamespace(sleep=lambda s: _real_sleep(min(s, 1.0)), time=time.time)
uvicorn.run(app, host="127.0.0.1", port=8765, log_level="warning")
