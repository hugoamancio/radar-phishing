import psycopg
import pytest

from monitor import banco
from monitor.detector import analisar
from monitor.pesquisa import (CONHECIDO, CONHECIDO_PAI, NADA, OFICIAL, SUSPEITO_AGORA,
                              dominios_acima, extrair_dominio, pesquisar)
from tests.test_detector import BRADESCO


@pytest.mark.parametrize("entrada, esperado", [
    ("https://bradesco-app.xyz/login?id=123", "bradesco-app.xyz"),
    ("bradesco-app.xyz", "bradesco-app.xyz"),
    ("  HTTPS://WWW.Bradesco-App.XYZ:443/ ", "www.bradesco-app.xyz"),
    ("http://usuario:senha@golpe.top/x", "golpe.top"),
    ("hxxps://golpe[.]top/login", "golpe.top"),
    ("golpe(.)top", "golpe.top"),
    ("<https://golpe.top>", "golpe.top"),
    ("brаdesco-login.com", "xn--brdesco-login-x1k.com"),   # "а" cirilico vira punycode
])
def test_extrai_dominio(entrada, esperado):
    assert extrair_dominio(entrada) == esperado


@pytest.mark.parametrize("entrada", ["", "   ", "não é endereço", "localhost", "http://"])
def test_rejeita_entrada_invalida(entrada):
    assert extrair_dominio(entrada) is None


def test_dominios_acima():
    assert dominios_acima("login.seguro.golpe.xyz") == ["seguro.golpe.xyz", "golpe.xyz"]
    assert dominios_acima("golpe.xyz") == []


def test_sem_banco_oficial_suspeito_e_nada():
    assert pesquisar("https://www.bradesco.com.br/html/classic/index.shtm", [BRADESCO]).tipo == OFICIAL
    assert pesquisar("hxxps://bardesco-token[.]top", [BRADESCO]).tipo == SUSPEITO_AGORA
    r = pesquisar("https://exemplo.org", [BRADESCO])
    assert r.tipo == NADA and r.banco_ok is False
    assert pesquisar("qualquer coisa", [BRADESCO]).dominio is None


class _Desfazer(Exception):
    pass


def test_com_banco_acha_dominio_e_subdominio():
    try:
        conn = banco.conectar()
    except psycopg.OperationalError:
        pytest.skip("PostgreSQL fora do ar")
    marcas = banco.carregar_marcas(conn)
    det = analisar("bradesco-pix-teste.xyz", marcas)[0]
    cert = {"emissor": "Let's Encrypt", "emitido_em": 1_790_000_000, "serial": "CD01", "log": "Teste"}

    with pytest.raises(_Desfazer):
        with conn.transaction():
            banco.gravar(conn, det, cert)

            r = pesquisar("https://bradesco-pix-teste.xyz/entrar", marcas, conn)
            assert r.tipo == CONHECIDO
            assert r.registro.marca == "Bradesco"
            assert r.registro.certificados == 1
            assert r.registro.ultimo_emissor == "Let's Encrypt"
            assert r.registro.emails == 0
            assert r.registro.motivos[0]["tecnica"] == "marca_no_dominio"

            r = pesquisar("login.seguro.bradesco-pix-teste.xyz", marcas, conn)
            assert r.tipo == CONHECIDO_PAI
            assert r.registro.dominio == "bradesco-pix-teste.xyz"
            raise _Desfazer
    conn.close()
