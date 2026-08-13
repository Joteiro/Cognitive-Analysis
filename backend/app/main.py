# app/main.py
import logging
import os
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import models
from .database import engine
from .routes import videop, panel

logger = logging.getLogger(__name__)

models.Base.metadata.create_all(bind=engine)


# Precalentar carga pandas y numpy al arrancar, para que la primera consulta
# de panel no pague el import. Suena a mejora gratis y NO lo es: deja unos
# 150-200 MB residentes para siempre, y la instancia gratuita de Render tiene
# 512 MB en total. Con la memoria al limite, el proceso que se pasa lo mata el
# sistema operativo — y lo que se cae es la peticion que estuviera en vuelo,
# que desde el navegador se ve como "Failed to fetch", sin ningun error de
# servidor porque el servidor directamente dejo de existir.
#
# Por eso queda APAGADO por defecto. Desde que el panel se guarda en
# content_features, la mayoria de las consultas ni siquiera tocan pandas, asi
# que el precalentado ya casi no aporta. Para probarlo: PRECALENTAR_PANEL=1.
PRECALENTAR = os.getenv("PRECALENTAR_PANEL", "0") == "1"


@asynccontextmanager
async def lifespan(app: FastAPI):
    if PRECALENTAR:
        # En un hilo aparte: si bloqueara el arranque, Render consideraria que
        # el servicio no responde y podria matar el deploy.
        threading.Thread(target=panel.precalentar, daemon=True,
                         name="precalentar-panel").start()
    else:
        logger.info("panel: precalentado desactivado (PRECALENTAR_PANEL=0)")
    yield


app = FastAPI(title="Cognitive Analysis API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Los routers van DESPUES de crear `app`: include_router es un metodo del
# objeto, no una funcion suelta. Ponerlo arriba da NameError.
app.include_router(videop.router)
app.include_router(panel.router)


@app.exception_handler(Exception)
async def error_no_previsto(request: Request, exc: Exception):
    """Convierte cualquier error no manejado en un 500 con cabeceras CORS.

    POR QUE HACE FALTA
    ------------------
    Sin esto, una excepcion sube por encima del middleware de CORS y uvicorn
    devuelve un 500 pelado, SIN la cabecera Access-Control-Allow-Origin. El
    navegador entonces bloquea la respuesta y el codigo cliente no ve un 500:
    ve `TypeError: Failed to fetch`, que es indistinguible de "no hay
    internet" o "el servidor no existe".

    Costo real: horas de diagnostico el 2026-08-13 persiguiendo teorias de
    red, CORS, bloqueadores y arranque en frio, cuando el servidor estaba
    contestando un error clarisimo que el navegador tiraba a la basura.

    Con este handler el error viaja DENTRO del middleware de CORS, llega al
    cliente como 500 con cuerpo JSON, y se ve en la consola.
    """
    logger.exception(f"error no previsto en {request.method} {request.url.path}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Error interno", "tipo": type(exc).__name__},
    )


@app.get("/health")
def health():
    """Lo que pinguea UptimeRobot. Devuelve tambien si el panel ya esta
    precalentado, para poder distinguir 'el servidor esta dormido' de 'el
    servidor esta despierto pero todavia cargando pandas'."""
    return {"status": "ok", "panel_listo": panel.esta_precalentado()}
