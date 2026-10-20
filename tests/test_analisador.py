from pathlib import Path

import psycopg
import pytest

from analisador import banco, links
from analisador.analise import analisar_mensagem
from analisador.autenticacao import dominio_organizacional
from analisador.leitura import ler
from monitor import banco as banco_monitor
from tests.test_detector import BRADESCO

EXEMPLOS = Path(__file__).parent / "exemplos"


def _offline(dominio):
    """Politica DMARC publicada, sem consultar o DNS de verdade."""
    return {"bradesco.com.br": "reject"}.get(dominio)


def analisar(nome: str):
    return analisar_mensagem(ler(EXEMPLOS / nome), [BRADESCO],
                             politica_dmarc=_offline, verificar_dkim=lambda m: None)


def tecnicas(analise) -> set[str]:
    return {a.tecnica for a in analise.achados}


def test_email_legitimo_nao_gera_sinal():
    a = analisar("legitimo.eml")
    assert a.achados == []
    assert (a.autenticacao.spf.resultado, a.autenticacao.dkim.resultado, a.autenticacao.dmarc.resultado) \
        == ("pass", "pass", "pass")


def test_golpe_com_dominio_parecido():
    a = analisar("golpe_dominio_parecido.eml")
    assert {"nome_falso", "dominio_imita_marca", "resposta_desviada", "dmarc_falhou", "spf_falhou",
            "link_disfarcado", "link_imita_marca", "ameaca", "dados", "urgencia",
            "combinacao_classica"} <= tecnicas(a)


def test_golpe_que_falsifica_o_endereco_oficial():
    a = analisar("golpe_falsifica_oficial.eml")
    assert {"endereco_oficial_falsificado", "dmarc_falhou", "arroba_na_url", "encurtador",
            "link_para_ip", "extensao_dupla", "recompensa", "urgencia"} <= tecnicas(a)
    assert a.autenticacao.dmarc.politica == "reject"


def test_ignora_authentication_results_forjado_mais_abaixo():
    # O segundo cabecalho, escrito pelo golpista, diz "pass" em tudo.
    a = analisar("golpe_falsifica_oficial.eml")
    assert a.autenticacao.spf.resultado == "fail"
    assert a.autenticacao.spf.dominio == "disparos-em-massa.ru"


def test_trecho_de_linguagem_mantem_acentos_do_original():
    a = analisar("golpe_dominio_parecido.eml")
    urgencia = next(x for x in a.achados if x.tecnica == "urgencia")
    assert "será bloqueada em até 24 horas" in urgencia.detalhe


def test_dmarc_calculado_quando_nao_ha_authentication_results():
    bruto = (b"From: Bradesco <avisos@bradesco.com.br>\r\nTo: x@exemplo.com\r\n"
             b"Subject: teste\r\n\r\ncorpo\r\n")
    a = analisar_mensagem(ler(bruto), [BRADESCO], politica_dmarc=_offline, verificar_dkim=lambda m: None)
    assert a.autenticacao.dmarc.resultado == "fail"
    assert a.autenticacao.dmarc.fonte == "verificação própria"
    assert "endereco_oficial_falsificado" in tecnicas(a)


@pytest.mark.parametrize("dominio, organizacional", [
    ("mail.bradesco.com.br", "bradesco.com.br"),
    ("bradesco.com.br", "bradesco.com.br"),
    ("envio.golpe.xyz", "golpe.xyz"),
    ("a.b.exemplo.co.uk", "exemplo.co.uk"),
])
def test_dominio_organizacional(dominio, organizacional):
    assert dominio_organizacional(dominio) == organizacional


def test_extrai_links_sem_mailto_e_sem_repetir():
    html = ('<a href="mailto:x@y.com">e-mail</a><a href="https://a.com/x">A</a>'
            '<a href="https://a.com/x">A de novo</a><a href="#topo">topo</a>')
    encontrados = links.extrair(html, "veja https://b.com/y. e https://a.com/x")
    assert [l.url for l in encontrados] == ["https://a.com/x", "https://a.com/x", "https://b.com/y"]
    assert encontrados[0].texto_visivel == "A"


def test_texto_visivel_que_nao_e_endereco_nao_conta_como_disfarce():
    lista = links.extrair('<a href="https://loja.com/oferta">Clique aqui</a>', "")
    assert links.achados(lista, [BRADESCO]) == []


def test_dkim_verificado_de_verdade_e_adulteracao_detectada():
    """Assina um e-mail com uma chave gerada na hora e verifica com o dkimpy.

    A chave publica e entregue por um DNS falso, entao o teste roda offline,
    mas o calculo criptografico e o mesmo de um e-mail real.
    """
    import base64

    import dkim
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    from analisador.autenticacao import _verificar_dkim

    chave = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    privada = chave.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                  serialization.NoEncryption())
    publica = base64.b64encode(chave.public_key().public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)).decode()
    dns_falso = lambda nome, timeout=5: f"v=DKIM1; k=rsa; p={publica}".encode() \
        if nome.startswith(b"sel1._domainkey.exemplo.com") else None

    mensagem = (b"From: Loja <contato@exemplo.com>\r\nTo: x@exemplo.com\r\nSubject: Pedido enviado\r\n"
                b"\r\nSeu pedido 123 foi enviado.\r\n")
    assinada = dkim.sign(mensagem, b"sel1", b"exemplo.com", privada,
                         include_headers=[b"from", b"to", b"subject"]) + mensagem

    ok = _verificar_dkim(ler(assinada), dnsfunc=dns_falso)
    assert (ok.resultado, ok.dominio, ok.fonte) == ("pass", "exemplo.com", "verificação própria")

    adulterada = assinada.replace(b"pedido 123", b"pedido 999")
    assert _verificar_dkim(ler(adulterada), dnsfunc=dns_falso).resultado == "fail"


class _Desfazer(Exception):
    pass


def test_grava_sem_corpo_e_com_links():
    try:
        conn = banco_monitor.conectar()
    except psycopg.OperationalError:
        pytest.skip("PostgreSQL fora do ar")
    marcas = banco_monitor.carregar_marcas(conn)
    a = analisar_mensagem(ler(EXEMPLOS / "golpe_dominio_parecido.eml"), marcas,
                          politica_dmarc=_offline, verificar_dkim=lambda m: None)
    with pytest.raises(_Desfazer):
        with conn.transaction():
            email_id = banco.gravar(conn, a, marcas)
            assert banco.gravar(conn, a, marcas) == email_id      # reanalise nao duplica
            colunas = {c.name for c in conn.execute("SELECT * FROM email LIMIT 0").description}
            assert not colunas & {"corpo", "texto", "html"}           # LGPD: corpo nunca gravado
            sinais, graves, n_links = conn.execute(
                "SELECT sinais, sinais_graves, links FROM vw_emails_analisados WHERE id = %s",
                (email_id,)).fetchone()
            assert (sinais, n_links) == (len(a.achados), 2) and graves >= 5
            marca = conn.execute(
                "SELECT d.marca_id FROM link_email l JOIN dominio d ON d.id = l.dominio_id "
                "WHERE l.email_id = %s AND d.nome = 'bradesco-app-seguro.xyz'", (email_id,)).fetchone()[0]
            assert marca == marcas[0].id
            raise _Desfazer
    conn.close()


def test_so_o_link_que_gerou_sinal_fica_marcado_como_suspeito():
    # O texto simples cita o site oficial; so o botao do HTML leva ao golpe.
    a = analisar("golpe_dominio_parecido.eml")
    por_dominio = {l.dominio: l.suspeito for l in a.links}
    assert por_dominio == {"bradesco-app-seguro.xyz": True, "www.bradesco.com.br": False}
