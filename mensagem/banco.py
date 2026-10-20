"""Grava a analise de um SMS/WhatsApp. O texto da mensagem nunca vai para o banco (LGPD)."""

from __future__ import annotations

import json

import psycopg

from mensagem.analise import AnaliseMensagem
from monitor.detector import Marca, analisar
from risco.banco import gravar as gravar_risco


def gravar(conn: psycopg.Connection, a: AnaliseMensagem, marcas: list[Marca]) -> int:
    with conn.transaction():
        mensagem_id = conn.execute(
            """
            INSERT INTO mensagem (texto_sha256, canal, remetente, achados) VALUES (%s, %s, %s, %s)
            ON CONFLICT (texto_sha256) DO UPDATE SET achados = EXCLUDED.achados, analisada_em = now()
            RETURNING id
            """,
            (a.sha256, a.canal, a.remetente, json.dumps([x.como_dict() for x in a.achados], ensure_ascii=False)),
        ).fetchone()[0]
        conn.execute("DELETE FROM link_mensagem WHERE mensagem_id = %s", (mensagem_id,))
        for link in a.links:
            if not link.dominio:
                continue
            marca_id = next((d.marca.id for d in analisar(link.dominio, marcas)), None)
            dominio_id = conn.execute(
                """
                INSERT INTO dominio (nome, marca_id) VALUES (%s, %s)
                ON CONFLICT (nome) DO UPDATE SET marca_id = COALESCE(dominio.marca_id, EXCLUDED.marca_id)
                RETURNING id
                """,
                (link.dominio, marca_id),
            ).fetchone()[0]
            conn.execute("INSERT INTO link_mensagem (mensagem_id, dominio_id, url) VALUES (%s, %s, %s)",
                         (mensagem_id, dominio_id, link.url[:2000]))
        gravar_risco(conn, a.risco, mensagem_id=mensagem_id)
    return mensagem_id
