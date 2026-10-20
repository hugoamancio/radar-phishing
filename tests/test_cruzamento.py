import io
from datetime import datetime, timedelta, timezone

import psycopg
import pytest
from rich.console import Console

from cruzamento.consulta import duracao, ler, resumir
from cruzamento.tela import TelaCruzamento
from monitor import banco

T0 = datetime(2026, 10, 16, 9, 12, tzinfo=timezone.utc)


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


def _dominio(conn, nome, marca=True):
    return conn.execute("INSERT INTO dominio (nome, marca_id) VALUES (%s, %s) RETURNING id",
                        (nome, 1 if marca else None)).fetchone()[0]


def _certificado(conn, dominio_id, visto_em, serial):
    conn.execute("INSERT INTO certificado (dominio_id, fonte, serial, visto_em) VALUES (%s, 'teste', %s, %s)",
                 (dominio_id, serial, visto_em))


def _email(conn, dominio_id, chegou_em, sha):
    email_id = conn.execute(
        "INSERT INTO email (remetente, recebido_em, arquivo_sha256) VALUES ('x@golpe.top', %s, %s) RETURNING id",
        (chegou_em, sha)).fetchone()[0]
    conn.execute("INSERT INTO link_email (email_id, dominio_id, url) VALUES (%s, %s, 'https://x')",
                 (email_id, dominio_id))


def test_os_quatro_casos_do_cruzamento(conn):
    with pytest.raises(_Desfazer):
        with conn.transaction():
            antes = _dominio(conn, "cz-antes.top")                       # CT 3 dias antes do e-mail
            _certificado(conn, antes, T0, "c1")
            _email(conn, antes, T0 + timedelta(days=3, hours=2), "e1")

            depois = _dominio(conn, "cz-depois.top")                     # e-mail chegou antes do CT
            _certificado(conn, depois, T0 + timedelta(hours=5), "c2")
            _email(conn, depois, T0, "e2")

            nunca = _dominio(conn, "cz-nunca.top")                       # nunca visto nos CT logs
            _email(conn, nunca, T0, "e3")

            pai = _dominio(conn, "cz-pai.top")                           # certificado do dominio "acima"
            _certificado(conn, pai, T0, "c3")
            filho = _dominio(conn, "login.cz-pai.top")
            _email(conn, filho, T0 + timedelta(days=1), "e4")

            oficial = _dominio(conn, "cz-oficial.com.br", marca=False)   # link legitimo: fica de fora
            _email(conn, oficial, T0, "e5")

            itens = {c.dominio: c for c in ler(conn) if c.dominio.startswith(("cz-", "login.cz-"))}
            assert itens["cz-antes.top"].situacao == "antes"
            assert itens["cz-antes.top"].antecedencia == timedelta(days=3, hours=2)
            assert itens["cz-depois.top"].situacao == "depois"
            assert itens["cz-nunca.top"].situacao == "desconhecido"
            assert itens["login.cz-pai.top"].situacao == "antes"
            assert "cz-oficial.com.br" not in itens

            r = resumir(list(itens.values()))
            assert (r.total, r.antes, r.depois, r.desconhecidos) == (4, 2, 1, 1)
            assert r.taxa_antecipada == 0.5
            assert r.maior == timedelta(days=3, hours=2)

            for largura in (140, 80):                                    # a tela desenha sem estourar
                console = Console(width=largura, record=True, file=io.StringIO())
                console.print(TelaCruzamento(list(itens.values()), r))
                texto = console.export_text()
                assert "3 d 2 h antes" in texto and "nunca visto nos CT logs" in texto
                assert all(len(l) <= largura for l in texto.splitlines())
            raise _Desfazer


@pytest.mark.parametrize("t, texto", [
    (timedelta(days=3, hours=2), "3 d 2 h"), (timedelta(days=2), "2 d"), (timedelta(hours=5, minutes=20), "5 h 20 min"),
    (timedelta(minutes=12), "12 min"), (None, "—"), (-timedelta(hours=5), "5 h"),
])
def test_duracao(t, texto):
    assert duracao(t) == texto
