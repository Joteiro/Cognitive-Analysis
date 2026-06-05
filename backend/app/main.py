# app/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from . import models
from .database import engine
from .routes import videop

models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Cognitive Analysis API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(videop.router)

@app.get("/health")
def health():
    return {"status": "ok"}
