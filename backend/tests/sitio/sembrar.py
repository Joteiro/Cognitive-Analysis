"""Siembra la base local de prueba. Los datos del dashboard salen de la foto
real (docs/dashboard_filas.json): si el endpoint en vivo devuelve exactamente
esas filas, reproduce la foto."""
import json
import os
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

import psycopg2
import psycopg2.extras

RAIZ = Path(__file__).resolve().parents[3]
DSN = os.getenv("DSN_PRUEBA", "postgresql://postgres@127.0.0.1:55432/ca")

# La foto real del dashboard si esta a mano (privado/, o docs/ antes de la
# mudanza). Si no, tres filas inventadas: la prueba compara el endpoint contra
# ESTA lista, sea cual sea su origen.
def foto() -> list:
    for ruta in (RAIZ / "privado" / "dashboard_filas.json",
                 RAIZ / "docs" / "dashboard_filas.json"):
        if ruta.exists():
            return json.loads(ruta.read_text(encoding="utf-8"))
    return [
        ["Un video informativo", "Canal A", "informativo", "2026-05-02", 12.5, 1800,
         70, 41, None, 55, 62, None, 30, 66],
        ["Otro, mas largo", "Canal B", "entretenimiento", "2026-05-03", 48.0, 7200,
         52, 77, 61, 44, 39, 60, 12, 48],
        ["Uno corto", "Canal A", "deporte_gaming", "2026-06-11", 4.2, 620,
         88, 12, None, 73, 20, None, None, 91],
    ]
PANEL_ORDEN = ["ritmo_ppm", "cifras_100w", "atribucion_1000w", "mattr_200",
               "conectores_1000w", "enlaces_externos", "promocional_1000w", "cobertura_titulo"]
PARIS_VERANO = timezone(timedelta(hours=2))

FRASES = [
    "el narrador explica que la biblioteca de Alejandria guardaba cuarenta mil rollos segun su calculo",
    "despues compara el incendio con la perdida de un disco duro sin copia de seguridad",
    "sostiene que la causa principal fue el abandono presupuestario y no un unico incendio",
    "cita al historiador Plutarco para fechar el primer dano en el ano cuarenta y ocho",
    "menciona que el faro de la ciudad tenia ciento treinta metros de altura aproximada",
    "concluye que el mito sobrevive porque es mas facil culpar a un villano que a la desidia",
    "este video esta patrocinado por una aplicacion de idiomas con descuento en la descripcion",
    "agrega que los copistas cobraban por linea y eso explicaba la calidad desigual",
]


def transcripcion(n_palabras: int, semilla: int) -> str:
    rng = random.Random(semilla)
    base = " ".join(FRASES)
    relleno = []
    while len(" ".join(relleno).split()) < n_palabras:
        relleno.append(rng.choice(["y entonces", "por otro lado", "en ese contexto",
                                   "vale la pena notar", "como veremos"]) + " " +
                       " ".join(rng.choice(["texto", "contexto", "detalle", "punto",
                                            "cuestion", "tema"]) for _ in range(8)))
    return base + " " + " ".join(relleno)


def panel_de(pcts):
    return [{"clave": k, "percentil": p, "tipo": "continuo"} for k, p in zip(PANEL_ORDEN, pcts)]


def sembrar():
    c = psycopg2.connect(DSN)
    c.autocommit = False
    cur = c.cursor()
    cur.execute("""truncate quiz_respuestas, quiz_preguntas, quiz_visionados,
                   participante_asignacion, participante_contacto, participantes,
                   content_features, content_items restart identity cascade""")

    # 1) Las 79 filas de la foto real -> content_items + content_features.
    filas = foto()
    for i, f in enumerate(filas):
        titulo, canal, formato, fecha, minutos, palabras, *pcts = f
        # 00:30 hora de Paris = 22:30 UTC del dia ANTERIOR: si algo cortara el
        # dia en UTC, la fecha saldria corrida y la comparacion lo detecta.
        visto = datetime.fromisoformat(fecha).replace(hour=0, minute=30, tzinfo=PARIS_VERANO)
        cur.execute("""insert into content_items (id, external_id, url, title, channel,
                         duration_seconds, watched_at, transcript, transcript_word_count)
                       values (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (1000 + i, f"vid{i:04d}", "https://youtu.be/x", titulo,
                     None if canal == "(sin canal)" else canal,
                     round(minutos * 60), visto, "x " * 10, None))   # sin conteo: no son candidatos a quiz
        cur.execute("""insert into content_features (content_item_id, features_version,
                         n_words, duration_seconds, formato, panel, apto)
                       values (%s,'2.0',%s,%s,%s,%s,true)""",
                    (1000 + i, palabras, round(minutos * 60), formato,
                     json.dumps(panel_de(pcts))))

    # 2) Afuera del dashboard: 2 con transcripcion sin panel, 1 sin transcripcion.
    ahora = datetime(2026, 9, 20, 10, 0, tzinfo=timezone.utc)
    for j, tiene_txt in enumerate([True, True, False]):
        cur.execute("""insert into content_items (id, external_id, url, title, channel,
                         watched_at, transcript) values (%s,%s,'u',%s,'c',%s,%s)""",
                    (1200 + j, f"afuera{j}", f"Afuera {j}", ahora, "txt" if tiene_txt else None))

    # 3) Candidatos a quiz (historial, aptos, >=400 palabras, sin quiz).
    cands = [
        # id, titulo, formato, palabras, dias atras
        (2, "Discrepante: el modelo lo ve informativo", "entretenimiento", 900, 3),
        (3001, "Alejandria: el mito del incendio", "informativo", 1200, 10),
        (3002, "Un video de gaming largo", "deporte_gaming", 800, 5),
        (3003, "Muy corto (no entra)", "informativo", 300, 2),
        (3004, "No apto (no entra)", "informativo", 900, 2),
        (3005, "Ya tiene quiz (no entra)", "informativo", 900, 40),
    ]
    for cid, titulo, formato, palabras, dias in cands:
        txt = transcripcion(palabras, cid)
        cur.execute("""insert into content_items (id, external_id, url, title, channel,
                         duration_seconds, watched_at, transcript, transcript_word_count, corpus)
                       values (%s,%s,'u',%s,'Canal Prueba',600,%s,%s,%s,'historial')""",
                    (cid, f"yt{cid}", titulo, ahora - timedelta(days=dias), txt, palabras))
        cur.execute("""insert into content_features (content_item_id, features_version,
                         formato, apto) values (%s,'2.0',%s,%s)""",
                    (cid, formato, cid != 3004))

    # 4) Nucleo del reclutamiento (609, 610, 94, 623) con preguntas; 623 sin
    #    ninguna utilizable (antes viajaba con preguntas = null).
    for cid in (609, 610, 94, 623):
        cur.execute("""insert into content_items (id, external_id, url, title, channel, corpus)
                       values (%s,%s,'u',%s,'Canal Nucleo','referencia')""",
                    (cid, f"nuc{cid}", f"Nucleo {cid}"))
        for n in range(3):
            cur.execute("""insert into quiz_preguntas (content_item_id, version, modelo, n_orden,
                             pregunta, opciones, correcta, cita, utilizable)
                           values (%s,'quiz-1.2','m',%s,%s,%s,1,'cita',%s)""",
                        (cid, n, f"P{n} de {cid}", json.dumps(["a", "b", "c", "d"]), cid != 623))
    # el que ya tiene quiz
    cur.execute("""insert into quiz_preguntas (content_item_id, version, modelo, n_orden,
                     pregunta, opciones, correcta, cita, utilizable)
                   values (3005,'quiz-1.1','m',0,'Vieja',%s,0,'c',true)""",
                (json.dumps(["a", "b", "c", "d"]),))
    cur.execute("insert into participantes (persona_id, token) values ('luna-01','tok-luna')")
    c.commit()
    c.close()


if __name__ == "__main__":
    sembrar()
    print("sembrada")
