import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv

# Ruta absoluta al .env para que funcione se corra desde donde se corra.
BASE_DIR = Path(__file__).resolve().parent.parent
env_path = BASE_DIR / ".env"

load_dotenv(dotenv_path=env_path)

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError(
        f"DATABASE_URL no esta definida. Se busco el .env en {env_path}")

# NO imprimir DATABASE_URL: lleva la contrasena de Postgres adentro y termina
# en la consola, en los logs de Render y en cualquier lado donde se pegue esa
# salida. Si hace falta depurar de donde salio la conexion, se imprime el host
# y nada mas.
if os.getenv("DEBUG_DB"):
    from urllib.parse import urlparse
    u = urlparse(DATABASE_URL)
    print(f"[db] .env: {env_path}")
    print(f"[db] host: {u.hostname}:{u.port}  base: {(u.path or '/').lstrip('/')}"
          f"  usuario: {u.username}")

engine = create_engine(DATABASE_URL, pool_pre_ping=True)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()
