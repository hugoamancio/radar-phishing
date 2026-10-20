import psycopg
import pytest

from bancario import pix
from mensagem import banco as banco_mensagem
from mensagem.analise import analisar, extrair_links
from monitor import banco
from monitor.detector import analisar as detectar
from tests.test_detector import BRADESCO

COMPRA_FALSA = ("BRADESCO: Compra aprovada de R$ 1.890,00 no cartao final 4421. Nao reconhece? "
                "Acesse bradesco-cancelar.top/c ou ligue 0800 591 2233")


def tecnicas(a) -> set[str]:
    return {x.tecnica for x in a.achados}


def test_falso_alerta_de_compra_por_sms():
    a = analisar(COMPRA_FALSA, [BRADESCO], "sms", "11987654321")
    assert {"remetente_celular_comum", "link_imita_marca", "compra_falsa", "pede_ligacao"} <= tecnicas(a)
    assert a.risco.nivel == "critico"


def test_golpe_do_falso_parente_no_whatsapp():
    a = analisar("Oi mae, mudei de numero, salva esse aqui. Me passa um pix pra mim? E urgente",
                 [BRADESCO], "whatsapp", "+55 11 91234-5678")
    assert "falso_parente" in tecnicas(a)
    assert a.risco.nivel in ("alto", "critico")


def test_sms_legitimo_de_codigo_nao_e_acusado():
    # Falso positivo encontrado durante o desenvolvimento: CITAR o codigo nao e golpe; PEDIR, sim.
    a = analisar("Bradesco: seu codigo de seguranca e 482913. Nao compartilhe com ninguem.",
                 [BRADESCO], "sms", "27888")
    assert a.achados == [] and a.risco.nota == 0


def test_numero_curto_nao_gera_sinal_de_remetente():
    a = analisar(COMPRA_FALSA, [BRADESCO], "sms", "27888")
    assert "remetente_celular_comum" not in tecnicas(a)


def test_pix_copia_e_cola_para_pessoa_em_nome_do_banco():
    codigo = pix.montar("12345678909", "JOSE CARLOS PEREIRA", "SAO PAULO", 199.90)
    a = analisar(f"Bradesco: regularize sua pendencia pagando o Pix abaixo\n{codigo}", [BRADESCO], "whatsapp")
    assert "pix_recebedor_divergente" in tecnicas(a)


@pytest.mark.parametrize("texto, dominios", [
    ("Acesse bradesco-cancelar.top/c agora", ["bradesco-cancelar.top"]),
    ("Veja https://exemplo.org/a e www.outro.com.br", ["exemplo.org", "www.outro.com.br"]),
    ("Sr.Joao, obrigado pela visita", []),
    ("Valor R$1.890,00 aprovado", []),
    ("me manda no email fulano@gmail.com", []),
])
def test_extrai_links_inclusive_sem_http(texto, dominios):
    assert [l.dominio for l in extrair_links(texto)] == dominios


class _Desfazer(Exception):
    pass


def test_link_ja_conhecido_e_mensagem_gravada_sem_o_texto():
    try:
        conn = banco.conectar()
    except psycopg.OperationalError:
        pytest.skip("PostgreSQL fora do ar")
    marcas = banco.carregar_marcas(conn)
    det = detectar("bradesco-cancelar.top", marcas)[0]
    cert = {"emissor": "Let's Encrypt", "emitido_em": 1_790_000_000, "serial": "EF01", "log": "Teste"}
    with pytest.raises(_Desfazer):
        with conn.transaction():
            banco.gravar(conn, det, cert)                      # o monitor ja tinha visto o dominio
            a = analisar(COMPRA_FALSA, marcas, "sms", "11987654321", conn=conn)
            assert "link_ja_conhecido" in tecnicas(a)
            assert a.links[0].suspeito

            mensagem_id = banco_mensagem.gravar(conn, a, marcas)
            assert banco_mensagem.gravar(conn, a, marcas) == mensagem_id     # mesma mensagem: nao duplica
            colunas = {c.name for c in conn.execute("SELECT * FROM mensagem LIMIT 0").description}
            assert "texto" not in colunas                                   # LGPD
            canal, links, nota = conn.execute(
                "SELECT canal, links, nota FROM vw_mensagens_analisadas WHERE id = %s", (mensagem_id,)).fetchone()
            assert (canal, links, nota) == ("sms", 1, a.risco.nota)
            raise _Desfazer
    conn.close()
