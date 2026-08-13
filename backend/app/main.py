# app/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import models
from .database import engine
from .routes import videop, panel

models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Cognitive Analysis API")

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
    return {"status": "ok"}
