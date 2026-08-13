# app/main.py
import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import models
from .database import engine
from .routes import videop, panel

logger = logging.getLogger(__name__)

models.Base.metadata.create_all(bind=engine)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Precalienta el panel al arrancar el proceso.

    EL PROBLEMA QUE RESUELVE
    ------------------------
    Calcular un panel obliga a importar pandas y numpy. En el plan gratuito de
    Render eso son 10-20 segundos, y se pagan una vez por PROCESO: cada deploy
    y cada reinicio vuelven a cobrarlo.

    UptimeRobot mantiene el servicio despierto, pero le pega a /health, que no
    toca pandas. Asi que el servidor estaba despierto y la primera consulta de
    panel seguia tardando igual — que es exactamente el sintoma de "a veces
    tarda muchisimo y no entiendo por que".

    Se hace en un hilo aparte a proposito. Si bloqueara el arranque, Render
    consideraria que el servicio no responde y podria matar el deploy. Asi, la
    API queda disponible enseguida y pandas termina de cargar por detras.
    """
    threading.Thread(target=panel.precalentar, daemon=True,
                     name="precalentar-panel").start()
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


@app.get("/health")
def health():
    """Lo que pinguea UptimeRobot. Devuelve tambien si el panel ya esta
    precalentado, para poder distinguir 'el servidor esta dormido' de 'el
    servidor esta despierto pero todavia cargando pandas'."""
    return {"status": "ok", "panel_listo": panel.esta_precalentado()}
