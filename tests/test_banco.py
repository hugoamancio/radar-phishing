"""Gravacao no PostgreSQL. Precisa do banco no ar (docker compose up); senao e pulado.

Tudo roda dentro de uma transacao desfeita no final: o banco nao fica sujo.
"""

import psycopg
import pytest

from monitor import banco
from monitor.detector import analisar


class _Desfazer(Exception):
    pass


@pytest.fixture
def conn():
    try:
        c = banco.conectar()
    except psycopg.OperationalError:
        pytest.skip("PostgreSQL fora do ar")
    yield c
    c.close()


def test_grava_e_reaparicao_nao_duplica(conn):
    marcas = banco.carregar_marcas(conn)
    det = analisar("bardesco-token-teste.top", marcas)[0]
    cert = {"emissor": "Teste", "emitido_em": 1_790_000_000, "serial": "AB01", "log": "Teste2027"}

    with pytest.raises(_Desfazer):
        with conn.transaction():
            assert banco.gravar(conn, det, cert) is True            # primeira vez: novo
            assert banco.gravar(conn, det, cert) is False           # mesmo certificado: nao duplica
            assert banco.gravar(conn, det, {**cert, "serial": "AB02"}) is False  # novo cert, mesmo dominio

            certs = conn.execute(
                "SELECT count(*) FROM certificado c JOIN dominio d ON d.id = c.dominio_id "
                "WHERE d.nome = %s", (det.dominio,)).fetchone()[0]
            assert certs == 2

            linha = conn.execute(
                "SELECT tecnicas, trecho, emissor FROM vw_dominios_suspeitos WHERE dominio = %s",
                (det.dominio,)).fetchone()
            assert linha == (["erro_de_digitacao", "palavra_isca", "tld_suspeito"], "bardesco", "Teste")
            raise _Desfazer

    assert conn.execute("SELECT count(*) FROM dominio WHERE nome = %s", (det.dominio,)).fetchone()[0] == 0
