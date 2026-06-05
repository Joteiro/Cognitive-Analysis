# app/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from . import models
from .database import engine
from .routes import videop

models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Cognitive Analysis API")

# CORS — permite que la extension de Chrome acceda al backend local
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(videop.router)
