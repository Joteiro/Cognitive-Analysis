#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
probar_dsn.py — valida la cadena de conexion ANTES de desplegar.

Cada intento fallido en Render son minutos de build. Esto tarda dos segundos y
dice exactamente que esta mal, sin imprimir nunca la contrasena.

Comprueba, en este orden:
  1. Que la URL se pueda parsear.
  2. Que el usuario sea coherente con el host. Con el pooler de Supabase
     (`...pooler.supabase.com`) el usuario DEBE ser `postgres.<ref_proyecto>`;
     con la conexion directa (`db.<ref>.supabase.co`) es `postgres` a secas.
     Mezclarlos da "password authentication failed" aunque la clave este bien,
     y el mensaje no dice nada de esto: culpa a la contrasena.
  3. Que la contrasena no tenga caracteres sin codificar que rompan la URL.
  4. Que la conexion efectivamente abra.

USO
    python probar_dsn.py                 # lee DATABASE_URL de backend/.env
    python probar_dsn.py "postgresql://..."
"""
import os
import sys
from pathlib import Path
from urllib.parse import urlparse, quote

ROTOS = set('@:/?#[]!$&\'()*+,;= ')   # separadores de URL: van codificados


def main() -> int:
    dsn = sys.argv[1] if len(sys.argv) > 1 else None
    if not dsn:
        env = Path(__file__).resolve().parent.parent / ".env"
        try:
            from dotenv import load_dotenv
            load_dotenv(env)
        except ImportError:
            pass
        dsn = os.getenv("DATABASE_URL")
    if not dsn:
        print("No hay DATABASE_URL. Pasala como argumento o ponela en backend/.env")
        return 2

    try:
        u = urlparse(dsn)
    except Exception as e:
        print(f"FALLA  La URL no se puede parsear: {e}")
        return 1

    print("=" * 60)
    print(f"esquema   {u.scheme}")
    print(f"usuario   {u.username}")
    print(f"host      {u.hostname}")
    print(f"puerto    {u.port}")
    print(f"base      {(u.path or '/').lstrip('/')}")
    print(f"clave     {'(presente, ' + str(len(u.password or '')) + ' caracteres)' if u.password else 'AUSENTE'}")
    print("=" * 60)

    problemas = []

    host = u.hostname or ""
    user = u.username or ""

    # Primero: detectar que el parseo mismo salio mal. Si la contrasena tiene
    # una '@' sin codificar, urlparse corta en el lugar equivocado y devuelve un
    # host absurdo sin quejarse. Mirar la contrasena "parseada" no sirve, porque
    # ya viene truncada. Hay que mirar el destrozo que quedo alrededor.
    resto = (u.path or "") + (u.netloc or "")
    if not host or "." not in host or len(host) < 4:
        problemas.append(
            f"El host quedo en '{host}', que no es un host valido.\n"
            "     Sintoma clasico de una contrasena con '@' sin codificar: la URL\n"
            "     se parte en el lugar equivocado y todo lo de despues se corre.")
    if "@" in (u.path or "") or "@" in (u.password or ""):
        problemas.append(
            "Hay una '@' donde no deberia. La contrasena tiene que ir codificada:\n"
            "     @ se escribe %40, : se escribe %3A, / se escribe %2F.")
    if u.path and u.path.count("/") > 1:
        problemas.append(f"La parte de la base ('{u.path}') tiene barras de mas.")
    if "pooler.supabase.com" in host:
        if "." not in user:
            problemas.append(
                "El host es el POOLER pero el usuario es '" + user + "'.\n"
                "     Con el pooler el usuario tiene que ser 'postgres.<ref_del_proyecto>'.\n"
                "     Es el error que da 'password authentication failed' con la clave correcta.")
        else:
            print(f"OK    usuario con ref de proyecto: {user.split('.', 1)[1]}")
        if u.port != 6543:
            problemas.append(f"El pooler suele ir por el 6543 y aca dice {u.port}.")
    elif host.startswith("db.") and "." in user:
        problemas.append(
            "El host es la conexion DIRECTA pero el usuario lleva el ref del "
            "proyecto. Ahi el usuario es 'postgres' a secas.")

    if u.password:
        sin_codificar = [c for c in u.password if c in ROTOS]
        if sin_codificar:
            problemas.append(
                "La contrasena tiene caracteres que rompen la URL: "
                + " ".join(sorted(set(sin_codificar)))
                + "\n     Codificala con:  python -c \"from urllib.parse import "
                  "quote; print(quote(input(), safe=''))\"")

    if problemas:
        print("\nPROBLEMAS ENCONTRADOS:")
        for p in problemas:
            print("  -> " + p)
        print("\nNo se intenta conectar hasta que esto este resuelto.")
        return 1

    print("\nEstructura correcta. Probando la conexion real...")
    try:
        import psycopg2
    except ImportError:
        print("psycopg2 no esta en este entorno; no se puede probar la conexion.")
        print("Corrre con el Python del venv:  scripts\\.venv\\Scripts\\python probar_dsn.py")
        return 0

    try:
        c = psycopg2.connect(dsn, connect_timeout=15)
        with c.cursor() as cur:
            cur.execute("select current_user, current_database(), count(*) "
                        "from content_items")
            usuario, base, n = cur.fetchone()
        c.close()
        print(f"OK    conectado como '{usuario}' a '{base}'")
        print(f"OK    content_items tiene {n} filas")
        print("\nLa cadena sirve. Copiala TAL CUAL a las variables de Render.")
        return 0
    except Exception as e:
        msg = str(e).strip().splitlines()[0]
        print(f"FALLA  {msg}")
        if "password authentication failed" in msg:
            print("\n     La estructura esta bien, asi que es la contrasena en si:")
            print("     - resetealas de nuevo en Supabase y copiala completa")
            print("     - si tiene caracteres raros, generala solo con letras y numeros")
        return 1


if __name__ == "__main__":
    sys.exit(main())
