import csv
import io
import json
import re
from collections import Counter
from datetime import datetime, timedelta, timezone

import psycopg
import pytest

from monitor import banco
from relatorio import iocs, pagina
from relatorio.campanhas import Deteccao, agrupar, molde
from relatorio.coleta import Dados, coletar

PALAVRAS = ("bradesco", "bradesc0", "bradescco", "bradesko", "bradesconet")
T0 = datetime(2026, 10, 19, 15, 0, tzinfo=timezone.utc)

# Os domínios reais pegos pelo monitor em 19/10/2026.
REAIS = [
    ("fcxwpuwj.bradesco.support.bloodoperationbag.xyz", 82, "alto", ["marca_em_subdominio"], "Let's Encrypt"),
    ("www.fcxwpuwj.bradesco.support.bloodoperationbag.xyz", 82, "alto", ["marca_em_subdominio"], "Let's Encrypt"),
    ("www.gsvgecou.bradesco.support.yearbladeoven.click", 82, "alto", ["marca_em_subdominio"], "Let's Encrypt"),
    ("lwavbhoy.bradesco.www.www.www.accounts.atendimento-especializado.org", 83, "alto", ["marca_em_subdominio"], "Let's Encrypt"),
    ("www.xvdjmjgk.bradesco.accounts.atendimento-especializado.org", 83, "alto", ["marca_em_subdominio"], "ZeroSSL GmbH"),
    ("tradescops.com", 45, "medio", ["erro_de_digitacao"], "Let's Encrypt"),
    ("www.tradescops.com", 45, "medio", ["erro_de_digitacao"], "Let's Encrypt"),
]


def deteccoes(lista=REAIS):
    return [Deteccao(d, n, nv, t, e, T0 + timedelta(minutes=i)) for i, (d, n, nv, t, e) in enumerate(lista)]


def dados(lista=REAIS) -> Dados:
    ds = deteccoes(lista)
    return Dados(T0 - timedelta(days=7), T0 + timedelta(hours=1), ["Bradesco"], ds, agrupar(ds, PALAVRAS), Counter())


@pytest.mark.parametrize("dominio, esperado", [
    ("fcxwpuwj.bradesco.support.bloodoperationbag.xyz", "bradesco.support"),
    ("lwavbhoy.bradesco.www.www.www.accounts.atendimento-especializado.org", "bradesco.accounts"),
    ("bradesco-cancelar.top", None),          # marca no proprio dominio registrado: sem molde
    ("www.tradescops.com", None),
])
def test_molde(dominio, esperado):
    assert molde(dominio, PALAVRAS) == esperado


def test_campanhas_reais():
    campanhas = {c.chave: c for c in agrupar(deteccoes(), PALAVRAS)}
    sup = campanhas["bradesco.support"]
    assert sup.e_campanha and sup.dominios_registrados == ["bloodoperationbag.xyz", "yearbladeoven.click"]
    assert len(sup.enderecos) == 2 and len(sup.hosts) == 3       # com e sem www: o mesmo endereco
    assert campanhas["bradesco.accounts"].e_campanha
    assert not campanhas["tradescops.com"].e_campanha           # so www + sem www: nao e campanha


def test_csv_de_indicadores():
    linhas = list(csv.DictReader(io.StringIO(iocs.csv_texto(dados()))))
    assert len(linhas) == 7
    assert linhas[0]["nota"] == "83" and linhas[0]["campanha"] == "bradesco.accounts"
    assert all("[.]" in l["desarmado"] for l in linhas)


def test_stix_segue_o_padrao():
    bundle = json.loads(iocs.stix_texto(dados()))
    assert bundle["type"] == "bundle" and re.fullmatch(r"bundle--[0-9a-f-]{36}", bundle["id"])
    identidade, *indicadores = bundle["objects"]
    assert identidade["type"] == "identity"
    for ind in indicadores:
        for campo in ("type", "spec_version", "id", "created", "modified", "pattern", "pattern_type", "valid_from"):
            assert campo in ind, campo
        assert ind["spec_version"] == "2.1" and ind["pattern_type"] == "stix"
        assert re.fullmatch(r"\[domain-name:value = '[^']+'\]", ind["pattern"])
        assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z", ind["valid_from"])
        assert ind["created_by_ref"] == identidade["id"]


def test_ids_stix_sao_os_mesmos_a_cada_exportacao():
    a = {o["id"] for o in iocs.stix(dados())["objects"]}
    b = {o["id"] for o in iocs.stix(dados())["objects"]}
    assert a == b


def test_relatorio_mostra_campanhas_e_resumo():
    html = pagina.montar(dados())
    assert "bradesco.support" in html and "bloodoperationbag.xyz, yearbladeoven.click" in html
    assert "Marca só no subdomínio" in html
    assert "<a " not in html                                     # nenhum endereco de golpe vira link


def test_dominio_com_html_vira_texto():
    maligno = [('x.bradesco.support.<script>alert(1)</script>.xyz', 90, "critico", ["marca_em_subdominio"], "<b>CA</b>")]
    html = pagina.montar(dados(maligno))
    assert "<script>alert" not in html and "&lt;script&gt;" in html
    assert "<b>CA</b>" not in html


def test_periodo_sem_nada():
    html = pagina.montar(dados([]))
    assert "Sem detecções no período." in html and "Nenhum indicador no período." in html


def test_coleta_do_banco():
    try:
        conn = banco.conectar()
    except psycopg.OperationalError:
        pytest.skip("PostgreSQL fora do ar")
    d = coletar(conn, 3650)
    assert d.marcas == ["Bradesco"] and d.inicio < d.fim
    pagina.montar(d)                                             # monta sem erro com os dados reais
    conn.close()
