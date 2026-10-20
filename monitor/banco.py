"""Leitura das marcas e gravacao das deteccoes no PostgreSQL."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone

import psycopg
import psycopg.conninfo

from monitor import configuracao
from monitor.detector import Deteccao, Marca
from risco.banco import gravar as gravar_risco
from risco.modelo import calcular


def _dsn() -> str:
    """Conexao do .env. A senha nunca fica no codigo: so no .env, que o Git ignora."""
    if os.environ.get("RADAR_DSN"):
        return os.environ["RADAR_DSN"]
    env = configuracao.ler_env()
    senha = os.environ.get("POSTGRES_PASSWORD") or env.get("POSTGRES_PASSWORD")
    if not senha:
        raise psycopg.OperationalError("POSTGRES_PASSWORD não definida: copie .env.example para .env e preencha")
    return psycopg.conninfo.make_conninfo(host="127.0.0.1", port=5433, dbname="radar", user="analista", password=senha)


def conectar() -> psycopg.Connection:
    return psycopg.connect(_dsn(), autocommit=True, connect_timeout=5)


def carregar_marcas(conn: psycopg.Connection) -> list[Marca]:
    linhas = conn.execute(
        "SELECT id, nome, dominios_oficiais, palavras_chave, codigo_banco FROM marca ORDER BY id"
    ).fetchall()
    return [Marca(id_, nome, tuple(oficiais), tuple(p.lower() for p in palavras), codigo)
            for id_, nome, oficiais, palavras, codigo in linhas]


def gravar(conn: psycopg.Connection, det: Deteccao, cert: dict) -> bool:
    """Grava dominio, certificado e deteccao numa transacao.

    Devolve True se o dominio e novo para esta marca (primeira deteccao).
    Reaparicoes so atualizam as tecnicas e registram o novo certificado.
    """
    with conn.transaction():
        dominio_id = conn.execute(
            """
            INSERT INTO dominio (nome, marca_id) VALUES (%s, %s)
            ON CONFLICT (nome) DO UPDATE SET marca_id = COALESCE(dominio.marca_id, EXCLUDED.marca_id)
            RETURNING id
            """,
            (det.dominio, det.marca.id),
        ).fetchone()[0]

        conn.execute(
            """
            INSERT INTO certificado (dominio_id, emissor, emitido_em, fonte, serial, log_ct)
            VALUES (%s, %s, %s, 'certstream', %s, %s)
            ON CONFLICT (dominio_id, serial) DO NOTHING
            """,
            (dominio_id, cert.get("emissor"), _data(cert.get("emitido_em")),
             cert.get("serial"), cert.get("log")),
        )

        novo = conn.execute(
            """
            INSERT INTO deteccao_dominio (dominio_id, marca_id, tecnicas, motivos, trecho)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (dominio_id, marca_id) DO UPDATE
               SET tecnicas = EXCLUDED.tecnicas,
                   motivos = EXCLUDED.motivos,
                   atualizado_em = now()
            RETURNING (xmax = 0)
            """,
            (dominio_id, det.marca.id, det.tecnicas, json.dumps(det.motivos, ensure_ascii=False), det.trecho),
        ).fetchone()[0]

        gravar_risco(conn, calcular(det.tecnicas), dominio_id=dominio_id)
    return bool(novo)


def contar_suspeitos(conn: psycopg.Connection) -> int:
    return conn.execute("SELECT count(*) FROM deteccao_dominio").fetchone()[0]


def _data(epoch: float | int | None) -> datetime | None:
    if not epoch:
        return None
    return datetime.fromtimestamp(float(epoch), tz=timezone.utc)


def bater(conn: psycopg.Connection, certificados: int, ritmo: int, iniciado_em: datetime) -> None:
    """Batimento do monitor: uma linha unica, sobrescrita a cada 10 s."""
    conn.execute(
        """
        INSERT INTO monitor_batimento (id, ultimo_sinal, certificados, ritmo, iniciado_em)
        VALUES (1, now(), %s, %s, %s)
        ON CONFLICT (id) DO UPDATE SET ultimo_sinal = now(), certificados = EXCLUDED.certificados,
                                       ritmo = EXCLUDED.ritmo, iniciado_em = EXCLUDED.iniciado_em
        """,
        (certificados, ritmo, iniciado_em),
    )
