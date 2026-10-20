"""Grava a analise de um e-mail. O corpo da mensagem nunca vai para o banco (LGPD)."""

from __future__ import annotations

import json

import psycopg

from analisador.analise import Analise
from monitor.detector import Marca, analisar
from risco.banco import gravar as gravar_risco


def gravar(conn: psycopg.Connection, a: Analise, marcas: list[Marca]) -> int:
    """Grava (ou atualiza, se o mesmo arquivo ja foi analisado) e devolve o id do e-mail."""
    m, aut = a.mensagem, a.autenticacao
    with conn.transaction():
        email_id = conn.execute(
            """
            INSERT INTO email (message_id, remetente, remetente_nome, reply_to, assunto, recebido_em,
                               spf, dkim, dmarc, dmarc_politica, achados, arquivo_sha256)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (arquivo_sha256) DO UPDATE SET
                spf = EXCLUDED.spf, dkim = EXCLUDED.dkim, dmarc = EXCLUDED.dmarc,
                dmarc_politica = EXCLUDED.dmarc_politica, achados = EXCLUDED.achados,
                analisado_em = now()
            RETURNING id
            """,
            (m.message_id, m.remetente_endereco, m.remetente_nome, m.reply_to, m.assunto, m.recebido_em,
             aut.spf.resultado, aut.dkim.resultado, aut.dmarc.resultado, aut.dmarc.politica,
             json.dumps([x.como_dict() for x in a.achados], ensure_ascii=False), m.sha256),
        ).fetchone()[0]

        # Reanalise: os links sao regravados do zero.
        conn.execute("DELETE FROM link_email WHERE email_id = %s", (email_id,))
        for link in a.links:
            if not link.dominio:
                continue
            marca_id = next((d.marca.id for d in analisar(link.dominio, marcas)), None)
            # primeiro_visto so e preenchido na primeira vez que o dominio aparece,
            # venha do CT log ou de um e-mail: e ele que permite o cruzamento da etapa 5.
            dominio_id = conn.execute(
                """
                INSERT INTO dominio (nome, marca_id) VALUES (%s, %s)
                ON CONFLICT (nome) DO UPDATE SET marca_id = COALESCE(dominio.marca_id, EXCLUDED.marca_id)
                RETURNING id
                """,
                (link.dominio, marca_id),
            ).fetchone()[0]
            conn.execute(
                "INSERT INTO link_email (email_id, dominio_id, url, texto_visivel) VALUES (%s, %s, %s, %s)",
                (email_id, dominio_id, link.url[:2000], (link.texto_visivel or "")[:500] or None),
            )

        gravar_risco(conn, a.risco, email_id=email_id)
    return email_id
