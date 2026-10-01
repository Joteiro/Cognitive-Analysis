#!/usr/bin/env python3
"""Contrasta dos estratos de demora de la prueba de reconocimiento.

QUE PREGUNTA CONTESTA
  ?El instrumento olvida? Una medida de memoria tiene que degradarse con el
  tiempo. Si el d' medido a los pocos dias es claramente mayor que el d'
  medido a los dos meses, el instrumento se comporta como memoria. Si sale
  plano, esta midiendo otra cosa --que es exactamente como murieron el scorer
  v1, el quiz de opcion multiple y el reconocimiento v1.

  Es la evidencia de validez de constructo que le falta a la v2. El d' con su
  intervalo dice que el instrumento DISCRIMINA; no dice que discrimine POR
  MEMORIA. Este contraste es lo que cierra esa brecha.

EL CONFUNDIDOR QUE HAY QUE MIRAR SI O SI
  Los dos lotes no son el mismo lote de videos. Si ademas difieren en
  duracion, el contraste queda contaminado: en los datos de este proyecto
  log(duracion) fue el predictor que le gano al panel entero de descriptores.
  Por eso el script no reporta solo la diferencia cruda: tambien la ajusta por
  log(duracion) y muestra las dos. Si la diferencia cruda es grande y la
  ajustada se desploma, la diferencia era duracion disfrazada de olvido.

USO
    python comparar_demora.py --a piloto2 --b demora0 --dias-a 72 --dias-b 0

  Busca solo las claves y las respuestas ya existentes; no llama a ningun
  modelo ni toca la base.
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

_N = NormalDist()
z = _N.inv_cdf
phi = _N.pdf

BASE = DOCS / "reconocimiento"
CLAVE = BASE / "clave_no_abrir"
RESPUESTAS = BASE / "respuestas"


def dprime(h, nt, f, nl):
    """d' y c con correccion log-lineal (Hautus 1995)."""
    H = (h + 0.5) / (nt + 1)
    F = (f + 0.5) / (nl + 1)
    return z(H) - z(F), -(z(H) + z(F)) / 2, H, F


def var_muestreo(H, F, nt, nl):
    """Varianza de muestreo de d' por metodo delta: el error de medicion del
    video. Crece rapido cuando H se acerca a 1 o F a 0, que es por que el
    techo de la v1 dejaba la varianza entre videos sin identificar."""
    return H * (1 - H) / (nt * phi(z(H)) ** 2) + F * (1 - F) / (nl * phi(z(F)) ** 2)


def cargar(etiqueta, ruta_resp=None):
    """Devuelve una fila por video puntuable del estrato."""
    ruta_clave = CLAVE / f"items_{etiqueta}.json"
    if not ruta_clave.exists():
        raise SystemExit(f"No existe {ruta_clave}")
    clave = json.loads(ruta_clave.read_text(encoding="utf-8"))

    if ruta_resp:
        rr = Path(ruta_resp)
    else:
        candidatas = sorted(RESPUESTAS.glob(f"*_{etiqueta}.json"))
        if not candidatas:
            raise SystemExit(f"No hay respuestas para '{etiqueta}' en {RESPUESTAS}")
        if len(candidatas) > 1:
            raise SystemExit(f"Hay {len(candidatas)} archivos para '{etiqueta}'; "
                             f"elegi uno con --respuestas-a/--respuestas-b")
        rr = candidatas[0]
    resp = json.loads(rr.read_text(encoding="utf-8"))

    por_video = {v["content_item_id"]: v for v in clave["videos"]}
    filas, fallos, total_at = [], 0, 0
    for rv in resp["videos"]:
        vid = rv["content_item_id"]
        if vid not in por_video:
            print(f"AVISO  [{etiqueta}] el video {vid} no esta en la clave; se saltea")
            continue
        items = {i["n"]: i for i in por_video[vid]["items"]}
        h = nt = f = nl = 0
        for r in rv["respuestas"]:
            it = items.get(r["n"])
            if it is None:
                continue
            if it["clase"] == "control_atencion":
                total_at += 1
                fallos += 1 if r["si"] else 0
                continue
            if it["clase"] == "objetivo":
                nt += 1
                h += 1 if r["si"] else 0
            else:
                nl += 1
                f += 1 if r["si"] else 0
        if nt < 3 or nl < 3:
            print(f"AVISO  [{etiqueta}] el video {vid} queda con {nt}/{nl}; se saltea")
            continue
        d, c, H, F = dprime(h, nt, f, nl)
        dur = por_video[vid].get("duration_seconds") or 0
        filas.append(dict(estrato=etiqueta, vid=vid, h=h, nt=nt, f=f, nl=nl,
                          H=H, F=F, d=d, c=c, ve=var_muestreo(H, F, nt, nl),
                          dur=dur, logdur=math.log(dur) if dur > 0 else 0.0,
                          recuerda=rv.get("recuerda_video"),
                          titulo=por_video[vid]["titulo"][:40]))
    return filas, fallos, total_at, rr.name


def sd_entre(d, ve):
    """DE real entre videos: varianza observada menos el error de medicion
    esperado. Recortada en cero porque el estimador de momentos puede dar
    negativo con pocos videos --eso significa 'no distinguible de cero', no
    'es cero'."""
    return math.sqrt(max(d.var(ddof=1) - ve.mean(), 0.0)) if len(d) > 1 else 0.0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--a", default="piloto2", help="etiqueta del estrato de MAS demora")
    ap.add_argument("--b", default="demora0", help="etiqueta del estrato de MENOS demora")
    ap.add_argument("--dias-a", type=float, default=72.0)
    ap.add_argument("--dias-b", type=float, default=0.0)
    ap.add_argument("--respuestas-a", default=None)
    ap.add_argument("--respuestas-b", default=None)
    ap.add_argument("--remuestreos", type=int, default=20000)
    args = ap.parse_args()

    fa, fal_a, tot_a, nom_a = cargar(args.a, args.respuestas_a)
    fb, fal_b, tot_b, nom_b = cargar(args.b, args.respuestas_b)
    if not fa or not fb:
        print("Falta al menos un estrato con videos puntuables.")
        return 1
    print(f"estrato A: {args.a} ({args.dias_a:.0f} dias) <- {nom_a}")
    print(f"estrato B: {args.b} ({args.dias_b:.0f} dias) <- {nom_b}")

    print("\n== CONTROL DE ATENCION ==")
    for nom, fal, tot in ((args.a, fal_a, tot_a), (args.b, fal_b, tot_b)):
        marca = "" if not tot or fal / tot <= 0.25 else "   <- sesion no usable"
        print(f"  {nom:10s} {fal}/{tot} absurdas marcadas como vistas{marca}")

    # A demora 0 no acordarse de un video que viste hoy no es olvido: es que el
    # registro de visionado no corresponde a lo que efectivamente miraste.
    raros = [r for r in fb if r["recuerda"] == "no"]
    if raros and args.dias_b <= 2:
        print(f"\n  OJO: {len(raros)} video(s) del estrato de {args.dias_b:.0f} dias "
              f"marcados como NO recordados: {[r['vid'] for r in raros]}")
        print("  A demora cero eso no es olvido; revisa si el registro de visionado es correcto.")

    print("\n== POR VIDEO ==")
    print(f"{'estrato':>9s} {'video':>6s} {'recuerda':>9s} {'aciertos':>10s} "
          f"{'falsas al.':>11s} {'d prima':>8s} {'min':>5s}  titulo")
    for r in sorted(fa + fb, key=lambda x: (x["estrato"], -x["d"])):
        print(f"{r['estrato'][:9]:>9s} {r['vid']:6d} {str(r['recuerda']):>9s} "
              f"{r['h']:4d}/{r['nt']:<5d} {r['f']:4d}/{r['nl']:<6d} "
              f"{r['d']:8.2f} {r['dur']//60:5d}  {r['titulo']}")

    da = np.array([r["d"] for r in fa]); va = np.array([r["ve"] for r in fa])
    db = np.array([r["d"] for r in fb]); vb = np.array([r["ve"] for r in fb])

    print("\n== RESUMEN POR ESTRATO ==")
    print(f"{'estrato':>10s} {'dias':>5s} {'n':>3s} {'d medio':>8s} {'H':>6s} {'F':>6s} "
          f"{'min med':>8s} {'DE entre':>9s}")
    for nom, dias, fs, d, v in ((args.a, args.dias_a, fa, da, va),
                                (args.b, args.dias_b, fb, db, vb)):
        print(f"{nom[:10]:>10s} {dias:5.0f} {len(fs):3d} {d.mean():8.2f} "
              f"{np.mean([r['H'] for r in fs]):6.2f} {np.mean([r['F'] for r in fs]):6.2f} "
              f"{np.mean([r['dur'] for r in fs])/60:8.1f} {sd_entre(d, v):9.2f}")

    rng = np.random.default_rng(26)
    na, nb = len(da), len(db)

    print("\n== ?EL INSTRUMENTO OLVIDA? (diferencia cruda) ==")
    dif = db.mean() - da.mean()
    bs = np.array([db[rng.integers(0, nb, nb)].mean() - da[rng.integers(0, na, na)].mean()
                   for _ in range(args.remuestreos)])
    lo, hi = np.percentile(bs, [2.5, 97.5])
    print(f"  d'({args.dias_b:.0f}d) - d'({args.dias_a:.0f}d) = {dif:+.2f}   "
          f"IC95 bootstrap por video [{lo:+.2f}, {hi:+.2f}]")
    print(f"  P(diferencia > 0) = {(bs > 0).mean():.3f}")
    if lo > 0:
        print("  El intervalo no toca el cero: el d' cae con la demora. Eso es olvido,\n"
              "  y es evidencia de que la v2 mide memoria y no el tema del titulo.")
    else:
        print("  El intervalo toca el cero: con estos n no se distingue un efecto de demora.\n"
              "  No prueba que no exista; prueba que este contraste no lo detecta.")

    # Ajuste por duracion. Con ~15 videos y 3 parametros esto es exploratorio,
    # pero sirve para lo unico que importa: ver si la diferencia SOBREVIVE al
    # control, o si era duracion disfrazada de olvido.
    print(f"\n== LA MISMA DIFERENCIA, AJUSTADA POR log(duracion) ==")
    todas = fa + fb
    y = np.array([r["d"] for r in todas])
    demora_b = np.array([1.0 if r["estrato"] == args.b else 0.0 for r in todas])
    ld = np.array([r["logdur"] for r in todas])
    ld = ld - ld.mean()
    X = np.column_stack([np.ones(len(y)), demora_b, ld])
    beta = np.linalg.lstsq(X, y, rcond=None)[0]

    idx_a = np.arange(na)
    idx_b = np.arange(na, na + nb)
    bs2 = []
    for _ in range(args.remuestreos):
        i = np.concatenate([idx_a[rng.integers(0, na, na)], idx_b[rng.integers(0, nb, nb)]])
        Xi, yi = X[i], y[i]
        if np.linalg.matrix_rank(Xi) < Xi.shape[1]:
            continue
        bs2.append(np.linalg.lstsq(Xi, yi, rcond=None)[0][1])
    bs2 = np.array(bs2)
    lo2, hi2 = np.percentile(bs2, [2.5, 97.5])
    print(f"  efecto de demora ajustado = {beta[1]:+.2f}   IC95 [{lo2:+.2f}, {hi2:+.2f}]")
    print(f"  pendiente de log(duracion) = {beta[2]:+.2f} por unidad log "
          f"({beta[2]*math.log(2):+.2f} al duplicar la duracion)")
    print(f"  P(efecto ajustado > 0) = {(bs2 > 0).mean():.3f}")
    enc = abs(beta[1] - dif)
    if enc > 0.3 * max(abs(dif), 1e-9):
        print(f"  El ajuste movio la diferencia en {enc:.2f}: buena parte de lo crudo era\n"
              "  duracion, no demora. Reporta la ajustada, no la cruda.")
    else:
        print("  El ajuste casi no la movio: la diferencia no es un efecto de duracion.")

    print("\n== LIMITES DE ESTE CONTRASTE (decirlos en la defensa) ==")
    print(f"  · Son dos lotes de videos distintos, no los mismos videos medidos dos veces.")
    print(f"    Demora esta perfectamente confundida con lote; el ajuste por duracion tapa")
    print(f"    un confundidor, no todos.")
    print(f"  · n = {na} + {nb} videos, un solo participante. Es evidencia de validez,")
    print(f"    no una estimacion de la curva de olvido.")
    print(f"  · El diseno limpio es el mismo video medido a dos demoras con items")
    print(f"    disjuntos. Eso es lo que habilitan los videos que quedaron sin usar.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
