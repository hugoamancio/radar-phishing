"""Grava avaliacoes de risco. Uma linha nova so quando a nota (ou o modelo) muda."""

from __future__ import annotations

import json

import psycopg

from risco.modelo import Avaliacao


def gravar(conn: psycopg.Connection, a: Avaliacao, *, dominio_id: int | None = None,
           email_id: int | None = None, mensagem_id: int | None = None) -> bool:
    """Devolve True se gravou uma avaliacao nova.

    O monitor reve o mesmo dominio a cada certificado novo; sem essa checagem
    a tabela teria uma linha identica por certificado.
    """
    if sum(x is not None for x in (dominio_id, email_id, mensagem_id)) != 1:
        raise ValueError("informe exatamente um: dominio_id, email_id ou mensagem_id")
    atual = conn.execute(
        "SELECT nota, modelo, motivos FROM vw_risco_atual "
        "WHERE dominio_id IS NOT DISTINCT FROM %s AND email_id IS NOT DISTINCT FROM %s "
        "AND mensagem_id IS NOT DISTINCT FROM %s",
        (dominio_id, email_id, mensagem_id),
    ).fetchone()
    if atual and (atual[0], atual[1], atual[2]) == (a.nota, a.modelo, a.motivos()):
        return False
    conn.execute(
        "INSERT INTO avaliacao_risco (dominio_id, email_id, mensagem_id, nota, nivel, motivos, modelo) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s)",
        (dominio_id, email_id, mensagem_id, a.nota, a.nivel, json.dumps(a.motivos(), ensure_ascii=False), a.modelo),
    )
    return True
