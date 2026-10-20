from datetime import date
from pathlib import Path

import pytest

from analisador.analise import analisar_mensagem
from analisador.leitura import ler
from bancario import arquivos, boleto, pix
from bancario.analise import analisar as analisar_bancario
from tests.test_detector import BRADESCO

EXEMPLOS = Path(__file__).parent / "exemplos"
LINHA = boleto.montar("237", 1890.00, date(2026, 10, 30), "1234567890123456789012345")


# --- Boleto -----------------------------------------------------------------

def test_boleto_montado_confere_e_e_lido_corretamente():
    b = boleto.conferir(LINHA)
    assert b.valido and b.problemas == []
    assert (b.banco_codigo, b.banco_nome, b.valor, b.vencimento) == ("237", "Bradesco", 1890.0, date(2026, 10, 30))


def test_qualquer_digito_trocado_nos_tres_campos_e_detectado():
    # Os campos 1, 2 e 3 tem DV proprio (modulo 10): troca de 1 digito SEMPRE aparece.
    posicoes = [i for i in range(32) if i not in (9, 20, 31)]
    for i in posicoes:
        for novo in "0123456789":
            if novo != LINHA[i]:
                assert not boleto.conferir(LINHA[:i] + novo + LINHA[i + 1:]).valido, (i, novo)


def test_troca_no_valor_e_pega_pelo_dv_geral_quase_sempre():
    # Valor e vencimento so tem o DV geral (modulo 11). Pela regra FEBRABAN, os
    # restos 0, 1 e 10 viram todos DV 1, entao uma fracao pequena das trocas passa.
    trocas = detectadas = 0
    for i in range(33, 47):
        for novo in "0123456789":
            if novo != LINHA[i]:
                trocas += 1
                detectadas += not boleto.conferir(LINHA[:i] + novo + LINHA[i + 1:]).valido
    assert detectadas / trocas >= 0.80


def test_fator_de_vencimento_antes_e_depois_do_reinicio_de_2025():
    assert boleto.vencimento_do_fator(9999, hoje=date(2025, 1, 1)) == date(2025, 2, 21)
    assert boleto.vencimento_do_fator(1000, hoje=date(2025, 3, 1)) == date(2025, 2, 22)
    assert boleto.vencimento_do_fator(0) is None


def test_arrecadacao_48_digitos():
    corpo = "816" + "0000000450" + "0" + "1234" + "5" * 25       # 8, segmento 1, valor real (6), mod 10
    barras = corpo[:3] + str(boleto.modulo10(corpo)) + corpo[3:]
    blocos = [barras[i:i + 11] for i in range(0, 44, 11)]
    linha = "".join(b + str(boleto.modulo10(b)) for b in blocos)
    b = boleto.conferir(linha)
    assert b.tipo == "arrecadacao" and b.valido
    assert not boleto.conferir(linha[:20] + str((int(linha[20]) + 1) % 10) + linha[21:]).valido


def test_encontra_linha_com_pontos_e_espacos_e_ignora_telefone():
    texto = f"Pague: {boleto.conferir(LINHA).formatada}. Duvidas: (11) 91234-5678"
    achados = boleto.encontrar(texto)
    assert [b.linha for b in achados] == [LINHA]


# --- Pix ----------------------------------------------------------------------

def test_crc16_valor_de_referencia():
    # Valor de conferencia publicado do CRC-16/CCITT-FALSE para "123456789".
    assert pix.crc16("123456789") == "29B1"


def test_pix_montado_e_lido_de_volta():
    codigo = pix.montar("12345678909", "JOSE CARLOS PEREIRA", "SAO PAULO", 450.0, "FATURA1")
    p = pix.ler(codigo)
    assert p.crc_ok
    assert (p.chave, p.tipo_chave, p.recebedor, p.cidade, p.valor, p.txid) == \
        ("12345678909", "CPF", "JOSE CARLOS PEREIRA", "SAO PAULO", 450.0, "FATURA1")


def test_pix_com_valor_trocado_falha_na_conferencia():
    codigo = pix.montar("12345678909", "JOSE", "SAO PAULO", 450.0)
    adulterado = codigo.replace("450.00", "950.00")
    assert pix.ler(adulterado).crc_ok is False


@pytest.mark.parametrize("chave, tipo", [("fulano@exemplo.com", "e-mail"), ("+5511912345678", "telefone"),
                                         ("12345678000199", "CNPJ"),
                                         ("123e4567-e89b-12d3-a456-426614174000", "chave aleatória")])
def test_tipo_de_chave(chave, tipo):
    assert pix.ler(pix.montar(chave, "X", "Y")).tipo_chave == tipo


def test_texto_que_nao_e_pix():
    assert pix.ler("https://exemplo.org") is None


# --- Arquivos (QR Code e PDF) -------------------------------------------------

def test_le_qrcode_de_imagem():
    assert arquivos.qrcodes_em_imagem((EXEMPLOS / "qrcode_link.png").read_bytes()) == \
        ["https://bradesco-pontos.top/resgate"]


def test_arquivo_corrompido_nao_derruba_a_analise():
    assert arquivos.qrcodes_em_imagem(b"isto nao e uma imagem") == []
    assert arquivos.texto_de_pdf(b"%PDF-1.4 quebrado") == ""


# --- Juntando tudo ------------------------------------------------------------

def test_email_com_boleto_de_outro_banco_e_pix_para_pessoa_fisica():
    a = analisar_mensagem(ler(EXEMPLOS / "golpe_boleto_pix.eml"), [BRADESCO],
                          politica_dmarc=lambda d: None, verificar_dkim=lambda m: None)
    tecnicas = {x.tecnica for x in a.achados}
    assert {"boleto_banco_divergente", "boleto_valor_divergente", "pix_recebedor_divergente"} <= tecnicas
    assert "boleto_adulterado" not in tecnicas          # o golpista refez as contas: DV confere
    (b, onde), = a.bancario.boletos
    assert b.banco_codigo == "341" and onde == "no PDF fatura_bradesco.pdf"
    (p, _), = a.bancario.pix
    assert p.recebedor == "JOSE CARLOS PEREIRA"


def test_email_legitimo_com_boleto_do_bradesco_nao_gera_sinal():
    a = analisar_mensagem(ler(EXEMPLOS / "boleto_legitimo.eml"), [BRADESCO],
                          politica_dmarc=lambda d: "reject", verificar_dkim=lambda m: None)
    assert a.achados == []
    assert len(a.bancario.boletos) == 1


def test_qrcode_com_link_vira_link_analisado():
    dados = (EXEMPLOS / "qrcode_link.png").read_bytes()
    r = analisar_bancario(["Bradesco: resgate seus pontos"], [("qr.png", "image/png", dados)], [BRADESCO])
    assert [a.tecnica for a in r.achados] == ["qrcode_esconde_link"]
    assert r.links[0].dominio == "bradesco-pontos.top"


def test_sem_marca_alegada_nao_compara_banco_nem_recebedor():
    # Uma loja qualquer cobrando por boleto de qualquer banco e normal.
    r = analisar_bancario([f"Loja X: pague {LINHA}"], [], [BRADESCO])
    assert r.marca_alegada is None and r.achados == []


def test_encontra_pix_copia_e_cola_com_espacos_no_meio_do_texto():
    codigo = pix.montar("12345678909", "JOSE CARLOS PEREIRA", "SAO PAULO", 10.0)
    assert pix.encontrar_em_texto(f"Pague aqui: {codigo} obrigado") == [codigo]
    assert pix.encontrar_em_texto("nada aqui 000201 quebrado") == []
