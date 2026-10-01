#!/usr/bin/env python3
"""Puntua la prueba de reconocimiento y proyecta la fiabilidad del instrumento.

QUE CALCULA
  Por video:  aciertos (hits), falsas alarmas, d' (sensibilidad) y c (sesgo).
              d' = z(H) - z(F), con correccion log-lineal para que un 0 o un
              100 % no manden el puntaje a infinito.
  Global:     si discriminas o no (d' medio con intervalo bootstrap por video),
              la DE de d' ENTRE videos --que es el numero que vinimos a
              estimar-- y la fiabilidad proyectada para la corrida completa.

POR QUE LA DE ENTRE VIDEOS ES EL NUMERO
  La fiabilidad de una medida por video es sigma2_entre / (sigma2_entre + error2).
  El error de medicion lo fija el numero de items y se calcula; lo unico que no
  se sabia es cuanto varia la memoria REAL entre videos. Con DE 0,3 la
  fiabilidad de una prueba de 40 items queda en 0,34 y no vale la pena; con DE
  0,8 queda en 0,85 y cambia el proyecto. Por eso se pilotean 5 videos antes de
  comprometer horas.

USO
    python puntuar_reconocimiento.py --etiqueta piloto \\
        --respuestas docs/reconocimiento/respuestas/reconocimiento_juan-01_piloto.json
"""

import argparse
import json
import math
import sys
from pathlib import Path
from statistics import NormalDist

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from generar_quiz import DOCS  # noqa: E402

# La normal sale de la libreria estandar a proposito: scipy no esta en
# requirements-analisis.txt y no vale la pena agregar una dependencia de 40 MB
# por dos funciones.
_N = NormalDist()
z = _N.inv_cdf        # cuantil
phi = _N.pdf          # densidad

BASE = DOCS / "reconocimiento"
CLAVE = BASE / "clave_no_abrir"
RESPUESTAS = BASE / "respuestas"


def dprime(h, nt, f, nl):
    """d' y c con correccion log-lineal (Hautus 1995): se suma 0,5 a cada
    conteo y 1 a cada total. Sin esto un video con 20/20 aciertos y 0 falsas
    alarmas da d' infinito y rompe cualquier promedio."""
    H = (h + 0.5) / (nt + 1)
    F = (f + 0.5) / (nl + 1)
    zh, zf = z(H), z(F)
    return zh - zf, -(zh + zf) / 2, H, F


def var_muestreo(H, F, nt, nl):
    """Varianza de muestreo de d' por el metodo delta. Es el error de medicion
    del video: lo que hay que restarle a la varianza observada para quedarse
    con la variacion real entre videos."""
    fh, ff = phi(z(H)), phi(z(F))
    return H * (1 - H) / (nt * fh ** 2) + F * (1 - F) / (nl * ff ** 2)


def fiabilidad(sigma2_entre, error2):
    return sigma2_entre / (sigma2_entre + error2) if (sigma2_entre + error2) > 0 else 0.0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--etiqueta", default="piloto")
    ap.add_argument("--respuestas", default=None)
    ap.add_argument("--videos-objetivo", type=int, default=94,
                    help="cuantos videos tendria la corrida completa")
    ap.add_argument("--conf-minima", type=int, default=0,
                    help="descarta respuestas con seguridad menor a este valor")
    args = ap.parse_args()

    clave = json.loads((CLAVE / f"items_{args.etiqueta}.json").read_text(encoding="utf-8"))
    ruta_r = Path(args.respuestas) if args.respuestas else \
        next(RESPUESTAS.glob(f"*_{args.etiqueta}.json"))
    resp = json.loads(Path(ruta_r).read_text(encoding="utf-8"))
    print(f"clave: items_{args.etiqueta}.json · respuestas: {Path(ruta_r).name}")

    por_video = {v["content_item_id"]: v for v in clave["videos"]}
    filas = []
    fallos_atencion = total_atencion = 0

    for rv in resp["videos"]:
        vid = rv["content_item_id"]
        if vid not in por_video:
            print(f"AVISO  el video {vid} no esta en la clave; se saltea")
            continue
        items = {i["n"]: i for i in por_video[vid]["items"]}
        h = nt = f = nl = 0
        for r in rv["respuestas"]:
            it = items.get(r["n"])
            if it is None:
                continue
            if args.conf_minima and (r.get("confianza") or 0) < args.conf_minima:
                continue
            if it["clase"] == "control_atencion":
                total_atencion += 1
                if r["si"]:
                    fallos_atencion += 1
                continue
            if it["clase"] == "objetivo":
                nt += 1
                h += 1 if r["si"] else 0
            else:
                nl += 1
                f += 1 if r["si"] else 0
        if nt < 3 or nl < 3:
            print(f"AVISO  el video {vid} queda con {nt} objetivos y {nl} senuelos; se saltea")
            continue
        d, c, H, F = dprime(h, nt, f, nl)
        filas.append(dict(vid=vid, titulo=por_video[vid]["titulo"][:42],
                          h=h, nt=nt, f=f, nl=nl, H=H, F=F, d=d, c=c,
                          ve=var_muestreo(H, F, nt, nl),
                          recuerda=rv.get("recuerda_video"),
                          dur=por_video[vid].get("duration_seconds")))

    if not filas:
        print("No quedo ningun video puntuable.")
        return 1

    print(f"\n== CONTROL DE ATENCION ==")
    print(f"  {fallos_atencion} de {total_atencion} afirmaciones absurdas marcadas como vistas"
          + ("   <- la sesion no es usable" if total_atencion and fallos_atencion / total_atencion > 0.25
             else "   (bien)"))

    print(f"\n== POR VIDEO ==")
    print(f"{'video':>6s} {'recuerda':>9s} {'aciertos':>10s} {'falsas al.':>11s} "
          f"{'d prima':>8s} {'sesgo c':>8s}  titulo")
    for r in sorted(filas, key=lambda x: -x["d"]):
        print(f"{r['vid']:6d} {str(r['recuerda']):>9s} {r['h']:4d}/{r['nt']:<5d} "
              f"{r['f']:4d}/{r['nl']:<6d} {r['d']:8.2f} {r['c']:8.2f}  {r['titulo']}")

    d = np.array([r["d"] for r in filas])
    ve = np.array([r["ve"] for r in filas])
    k = len(filas)

    print(f"\n== DISCRIMINAS? (la pregunta previa a todo lo demas) ==")
    rng = np.random.default_rng(11)
    bs = [d[rng.integers(0, k, k)].mean() for _ in range(20000)]
    print(f"  d' medio = {d.mean():.2f}   IC95 bootstrap por video "
          f"[{np.percentile(bs,2.5):.2f}, {np.percentile(bs,97.5):.2f}]")
    print(f"  aciertos {sum(r['h'] for r in filas)}/{sum(r['nt'] for r in filas)} · "
          f"falsas alarmas {sum(r['f'] for r in filas)}/{sum(r['nl'] for r in filas)}")
    if np.percentile(bs, 2.5) <= 0:
        print("  El intervalo toca el cero: con estos items no se distingue lo visto de lo no visto.")
        print("  Antes de escalar hay que revisar los items, no sumar videos.")

    var_obs = d.var(ddof=1)
    err = ve.mean()
    s2 = max(var_obs - err, 0.0)
    print(f"\n== LA DE ENTRE VIDEOS (el numero que vinimos a buscar) ==")
    print(f"  varianza observada de d'      : {var_obs:.3f}")
    print(f"  error de medicion esperado    : {err:.3f}   (EE de d' por video = {math.sqrt(err):.2f})")
    print(f"  varianza real entre videos    : {s2:.3f}   -> DE = {math.sqrt(s2):.2f}")
    print(f"  fiabilidad de ESTA prueba     : {fiabilidad(s2, err):.2f}")
    if s2 == 0:
        print("  La estimacion dio negativa y se recorto a cero: con 5 videos el estimador es\n"
              "  inestable. Significa 'no se puede distinguir de cero', no 'es cero'.")

    # Con 5 videos este numero es ruidoso; el intervalo lo dice sin adornos.
    bs2 = []
    for _ in range(20000):
        i = rng.integers(0, k, k)
        bs2.append(math.sqrt(max(d[i].var(ddof=1) - ve[i].mean(), 0.0)))
    print(f"  IC95 de la DE entre videos    : [{np.percentile(bs2,2.5):.2f}, "
          f"{np.percentile(bs2,97.5):.2f}]  (con {k} videos es ancho a proposito)")

    print(f"\n== PROYECCION A LA CORRIDA COMPLETA ({args.videos_objetivo} videos) ==")
    nt_m = int(np.mean([r["nt"] for r in filas]))
    H_m, F_m = float(np.mean([r["H"] for r in filas])), float(np.mean([r["F"] for r in filas]))
    print(f"{'items por video':>16s} {'error2':>8s} {'fiabilidad':>11s} {'n efectivo':>11s} {'horas':>7s}")
    for m in [10, 20, 30, 40, 60]:
        e2 = var_muestreo(H_m, F_m, m, m)
        fi = fiabilidad(s2, e2)
        horas = 2 * m * args.videos_objetivo * 5 / 3600
        print(f"{2*m:>13d}    {e2:8.3f} {fi:11.2f} {fi*args.videos_objetivo:11.1f} {horas:7.1f}")
    print(f"  (hoy, con opcion multiple: fiabilidad 0,10 y n efectivo 4,9 sobre 50 videos)")
    print(f"  medido en este piloto: {2*nt_m} items por video, H={H_m:.2f}, F={F_m:.2f}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
