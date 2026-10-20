import pytest

from monitor.detector import NOMES_TECNICAS
from risco.modelo import NOTA_MAXIMA, PESOS, calcular, nivel_da_nota


def test_sem_sinais_e_zero():
    a = calcular([])
    assert (a.nota, a.nivel, a.contribuicoes) == (0, "baixo", [])


def test_combina_como_chances_independentes():
    # 100 x (1 - 0,6 x 0,7) = 58
    assert calcular(["marca_no_dominio", "palavra_isca"]).nota == 58


def test_mesma_familia_conta_pela_metade():
    # link_disfarcado (70) + link_imita_marca (70 -> 35): 100 x (1 - 0,3 x 0,65) = 80,5
    a = calcular(["link_disfarcado", "link_imita_marca"])
    assert a.nota == 80
    assert [c.peso for c in a.contribuicoes] == [70, 35]


def test_soma_das_contribuicoes_e_a_nota():
    for tecnicas in (["homografo", "palavra_isca", "tld_suspeito"],
                     ["dmarc_falhou", "link_disfarcado", "dados", "urgencia", "ameaca"],
                     list(PESOS)):
        a = calcular(tecnicas)
        assert sum(c.pontos for c in a.contribuicoes) == a.nota


def test_nunca_passa_de_99():
    assert calcular(list(PESOS)).nota == NOTA_MAXIMA


def test_ordem_e_repeticao_nao_mudam_a_nota():
    assert calcular(["tld_suspeito", "homografo"]).nota == calcular(["homografo", "tld_suspeito", "homografo"]).nota


def test_mais_sinais_nunca_baixam_a_nota():
    base = calcular(["erro_de_digitacao"]).nota
    for extra in PESOS:
        assert calcular(["erro_de_digitacao", extra]).nota >= base


def test_tecnica_desconhecida_e_listada_e_nao_quebra():
    a = calcular(["marca_no_dominio", "tecnica_nova"])
    assert a.nota == 40 and a.ignoradas == ["tecnica_nova"]


@pytest.mark.parametrize("nota, nivel", [(0, "baixo"), (29, "baixo"), (30, "medio"), (59, "medio"),
                                         (60, "alto"), (84, "alto"), (85, "critico"), (99, "critico")])
def test_niveis(nota, nivel):
    assert nivel_da_nota(nota) == nivel


def test_toda_tecnica_de_dominio_tem_peso():
    assert set(NOMES_TECNICAS) <= set(PESOS)


def test_toda_tecnica_de_email_tem_peso():
    from pathlib import Path
    import re
    fontes = " ".join(p.read_text(encoding="utf-8")
                      for pasta in ("analisador", "bancario", "mensagem") for p in Path(pasta).glob("*.py"))
    tecnicas = set(re.findall(r'Achado\(\s*"[a-z]+",\s*"([a-z_]+)"', fontes))
    tecnicas |= set(re.findall(r'"(urgencia|ameaca|recompensa|dados|falso_parente|compra_falsa|pedido_pix)": \(', fontes))
    assert tecnicas and tecnicas <= set(PESOS), tecnicas - set(PESOS)


def test_nenhuma_contribuicao_negativa_mesmo_no_teto():
    a = calcular(list(PESOS))
    assert all(c.pontos >= 0 for c in a.contribuicoes)


def test_painel_desenha_nas_tres_larguras_sem_quebrar_borda():
    from rich.console import Console

    from monitor.painel import Painel
    from scripts.previa_painel import estado_exemplo

    import io

    for largura in (150, 120, 90, 60):
        console = Console(width=largura, height=44, record=True, file=io.StringIO())
        console.print(Painel(estado_exemplo(), ["Bradesco"]), height=44)
        texto = console.export_text()
        assert all(len(l) <= largura for l in texto.splitlines())
        assert "82" in texto                         # nota do caso "marca so no subdominio"
        assert "Marca só no subdomínio" in texto     # nome da tecnica nunca cortado
        if largura < 75:                             # compacto: dominio inteiro, sem quebrar no meio
            assert "x7k2.bradesco.support.entregarapida.click" in texto


class _Desfazer(Exception):
    pass


def test_grava_nota_so_quando_muda():
    import psycopg

    from monitor import banco
    from risco.banco import gravar

    try:
        conn = banco.conectar()
    except psycopg.OperationalError:
        pytest.skip("PostgreSQL fora do ar")
    with pytest.raises(_Desfazer):
        with conn.transaction():
            dominio_id = conn.execute("INSERT INTO dominio (nome) VALUES ('teste-risco.xyz') RETURNING id").fetchone()[0]
            a = calcular(["marca_no_dominio", "tld_suspeito"])
            assert gravar(conn, a, dominio_id=dominio_id) is True
            assert gravar(conn, a, dominio_id=dominio_id) is False          # igual: nao duplica
            b = calcular(["marca_em_subdominio", "marca_no_dominio", "tld_suspeito"])
            assert gravar(conn, b, dominio_id=dominio_id) is True           # mudou: historico
            nota, nivel = conn.execute("SELECT nota, nivel FROM vw_risco_atual WHERE dominio_id = %s",
                                       (dominio_id,)).fetchone()
            assert (nota, nivel) == (b.nota, b.nivel)
            assert conn.execute("SELECT count(*) FROM avaliacao_risco WHERE dominio_id = %s",
                                (dominio_id,)).fetchone()[0] == 2
            raise _Desfazer
    conn.close()
