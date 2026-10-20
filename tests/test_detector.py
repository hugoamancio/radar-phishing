import pytest

from monitor.detector import Marca, analisar, distancia
from monitor.normalizacao import decodificar_idn, variantes

BRADESCO = Marca(
    id=1,
    nome="Bradesco",
    dominios_oficiais=("bradesco.com.br", "bradesco", "bradescoseguros.com.br", "next.me"),
    palavras_chave=("bradesco", "bradesc0", "bradescco", "bradesko", "bradesconet"),
    codigo_banco="237",
)


def tecnicas(dominio: str) -> set[str]:
    resultado = analisar(dominio, [BRADESCO])
    return set(resultado[0].tecnicas) if resultado else set()


# --- Sites oficiais e dominios comuns: nunca podem ser acusados -------------

@pytest.mark.parametrize("dominio", [
    "bradesco.com.br",
    "www.bradesco.com.br",
    "*.internetbanking.bradesco.com.br",
    "banco.bradesco",
    "bradescoseguros.com.br",
    "next.me",
    "google.com",
    "bradford.ac.uk",
    "desconto.com.br",
    "brasil.gov.br",
    "localhost",
])
def test_nao_acusa_oficiais_nem_dominios_comuns(dominio):
    assert analisar(dominio, [BRADESCO]) == []


# --- Cada tecnica de disfarce ------------------------------------------------

def test_marca_no_dominio_com_palavra_isca():
    assert tecnicas("bradesco-seguranca.com") == {"marca_no_dominio", "palavra_isca"}


def test_marca_partida_por_hifen():
    resultado = analisar("bra-desco-login.com", [BRADESCO])[0]
    assert "marca_no_dominio" in resultado.tecnicas
    assert resultado.trecho == "bra-desco"


def test_subdominio_enganoso():
    t = tecnicas("bradesco.com.br.acesso-seguro.xyz")
    assert {"subdominio_enganoso", "tld_suspeito", "palavra_isca"} <= t
    assert analisar("bradesco.com.br.acesso-seguro.xyz", [BRADESCO])[0].principal == "subdominio_enganoso"


def test_troca_de_caracteres_zero_por_o():
    # "bradesc0" esta na lista de palavras-chave, entao conta como marca direta
    assert "marca_no_dominio" in tecnicas("bradesc0-app.online")
    # ja "br4desco" so aparece depois de desfazer o leet
    assert "troca_de_caracteres" in tecnicas("br4desco-app.online")


def test_troca_de_caracteres_cl_por_d():
    assert "troca_de_caracteres" in tecnicas("braclesco.net")


def test_homografo_cirilico_em_punycode():
    falso = "brаdesco-login.com"            # o "а" e cirilico (U+0430)
    puny = falso.encode("idna").decode("ascii")
    assert puny.startswith("xn--")
    det = analisar(puny, [BRADESCO])[0]
    assert "homografo" in det.tecnicas
    assert decodificar_idn(puny) == falso


@pytest.mark.parametrize("dominio, trecho", [
    ("bardesco-token.top", "bardesco"),     # inversao de letras vizinhas
    ("bradeco.com", "bradeco"),             # letra faltando
    ("bradezco-pix.com", "bradezco"),       # letra trocada
])
def test_erro_de_digitacao(dominio, trecho):
    det = analisar(dominio, [BRADESCO])[0]
    assert det.principal == "erro_de_digitacao"
    assert det.trecho == trecho


# --- Casos reais pegos pelo monitor em 19/10/2026 ---------------------------

def test_real_marca_so_no_subdominio():
    det = analisar("fcxwpuwj.bradesco.support.bloodoperationbag.xyz", [BRADESCO])[0]
    assert det.principal == "marca_em_subdominio"
    assert "bloodoperationbag.xyz" in det.motivos[0]["detalhe"]


def test_real_falso_positivo_empresa_de_aquecedores():
    assert analisar("bladescommercialwaterheaters.co.uk", [BRADESCO]) == []


def test_erro_de_digitacao_colado_em_palavra_isca_continua_valendo():
    assert analisar("bardescoapp.com", [BRADESCO])[0].principal == "erro_de_digitacao"


def test_marca_no_dominio_registrado_nao_vira_marca_em_subdominio():
    assert "marca_em_subdominio" not in tecnicas("login.bradesco-seguranca.com")


# --- Pecas internas ----------------------------------------------------------

def test_distancia_damerau():
    assert distancia("bradesco", "bradesco") == 0
    assert distancia("bardesco", "bradesco") == 1   # inversao conta como 1
    assert distancia("bradeco", "bradesco") == 1
    assert distancia("bradford", "bradesco") > 1


def test_variantes_desfazem_leet_e_combinacoes():
    leituras = variantes("brad3sc0")
    assert "bradesco" in leituras
    assert "bradesco" in variantes("braclesco")
