"""Relatorio de um e-mail analisado, no mesmo visual do monitor.

Ordem de leitura pensada para quem decide em segundos: a borda e o titulo
ja dao o veredito; depois vem quem mandou, se o remetente e autentico, para
onde os links levam de verdade e, por fim, cada sinal com a evidencia.
"""

from __future__ import annotations

from rich import box
from rich.console import Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from analisador.achados import ALTA, BAIXA, MEDIA
from analisador.analise import CATEGORIAS, Analise
from analisador.autenticacao import Verificacao
from monitor.normalizacao import decodificar_idn
from monitor.painel import COR_ALERTA, COR_ATENCAO, COR_BORDA, COR_OK, COR_ROTULO
from bancario.tela import secao as secao_bancaria
from risco.visual import COR_NIVEL, explicacao, medidor

NOMES_CATEGORIAS = {
    "remetente": "Remetente", "autenticacao": "Autenticação", "links": "Links",
    "linguagem": "Linguagem", "bancario": "Boleto, Pix e QR Code", "anexos": "Anexos",
}
COR_GRAVIDADE = {ALTA: COR_ALERTA, MEDIA: COR_ATENCAO, BAIXA: COR_ROTULO}
NOME_GRAVIDADE = {ALTA: "grave", MEDIA: "média", BAIXA: "leve"}

RESULTADOS = {
    "pass": ("passou", "bold #0d1117 on #57AB5A"),
    "fail": ("falhou", "bold white on #B62324"),
    "softfail": ("falhou (leve)", "bold #0d1117 on #C69026"),
    "permerror": ("registro inválido", "bold white on #B62324"),
    "neutral": ("neutro", "bold white on grey35"),
    "temperror": ("erro temporário", "bold white on grey35"),
    "none": ("ausente", "bold white on grey35"),
}
POLITICAS = {"reject": "recusar", "quarantine": "isolar", "none": "só monitorar"}

CONSELHO_GOLPE = ("Não clique nos links, não abra anexos e não responda. Se já informou algum dado, "
                  "ligue para o banco pelo número que está no verso do cartão.")


def _selo(v: Verificacao) -> Text:
    rotulo, estilo = RESULTADOS.get(v.resultado, (v.resultado, "bold white on grey35"))
    return Text(f" {rotulo} ", style=estilo)


def _linha_autenticacao(nome: str, v: Verificacao, explicacao: str) -> list:
    detalhe = Text(explicacao, style=COR_ROTULO)
    if v.dominio:
        detalhe.append(f"  ·  {v.dominio}", style="white")
    if v.politica:
        detalhe.append(f"  ·  o domínio pede para {POLITICAS.get(v.politica, v.politica)} falhas", style=COR_ROTULO)
    return [Text(nome, style="bold white"), _selo(v), detalhe]


def _veredito(a: Analise) -> tuple[str, str, str]:
    """Titulo, cor da borda e conselho, todos decididos pelo nivel de risco."""
    r = a.risco
    if r.nivel == "critico":
        return f"Golpe quase certo  ·  risco {r.nota}", COR_NIVEL["critico"], CONSELHO_GOLPE
    if r.nivel == "alto":
        return f"Provável golpe  ·  risco {r.nota}", COR_NIVEL["alto"], CONSELHO_GOLPE
    if r.nivel == "medio":
        return (f"Atenção  ·  risco {r.nota}", COR_NIVEL["medio"],
                "Desconfie: confira o remetente e não clique antes de ter certeza.")
    if a.achados:
        return (f"Risco baixo  ·  {r.nota}", COR_ROTULO, "Nada grave, mas há detalhes que valem um segundo olhar.")
    return ("Nenhum sinal de golpe", COR_OK,
            "Autenticação e conteúdo sem problemas. Mesmo assim, banco nenhum pede senha por e-mail.")


def _cabecalho(a: Analise) -> Table:
    m = a.mensagem
    grade = Table.grid(padding=(0, 3))
    grade.add_column(style=COR_ROTULO, no_wrap=True)
    grade.add_column(style="white", overflow="fold")
    grade.add_row("Assunto", Text(m.assunto or "(sem assunto)", style="bold white"))
    de = Text(m.remetente_nome + "  " if m.remetente_nome else "", style="white")
    de.append(f"<{m.remetente_endereco}>", style=COR_ROTULO)
    grade.add_row("De", de)
    if m.reply_to:
        grade.add_row("Responder para", m.reply_to)
    if m.recebido_em:
        grade.add_row("Recebido", f"{m.recebido_em.astimezone():%d/%m/%Y %H:%M}")
    return grade


def _autenticacao(a: Analise) -> Table:
    aut = a.autenticacao
    grade = Table.grid(padding=(0, 2))
    grade.add_column(width=5, no_wrap=True)
    grade.add_column(no_wrap=True)
    grade.add_column(overflow="fold")
    grade.add_row(*_linha_autenticacao("SPF", aut.spf, "servidor autorizado a enviar"))
    grade.add_row(*_linha_autenticacao("DKIM", aut.dkim, "assinatura digital"))
    grade.add_row(*_linha_autenticacao("DMARC", aut.dmarc, "remetente confere com o \"De:\""))
    return grade


def _links(a: Analise) -> Table | Text:
    if not a.links:
        return Text("Nenhum link.", style=COR_ROTULO)
    tabela = Table(box=box.SIMPLE_HEAD, show_edge=False, pad_edge=False, expand=True,
                   header_style=COR_ROTULO, border_style=COR_BORDA)
    tabela.add_column("O que o e-mail mostra", ratio=1, overflow="fold")
    tabela.add_column("", width=1, no_wrap=True)
    tabela.add_column("Para onde o clique leva", ratio=1, overflow="fold")
    for link in a.links:
        destino = decodificar_idn(link.dominio) if link.dominio else link.url
        perigoso = link.suspeito   # este proprio link gerou algum sinal
        tabela.add_row(
            Text(link.texto_visivel or "(escrito no texto simples)",
                 style="white" if link.texto_visivel else COR_ROTULO),
            Text("→", style=COR_BORDA),
            Text(destino, style=COR_ALERTA if perigoso else COR_OK),
        )
    return tabela


def lista_sinais(achados: list, categorias: tuple[str, ...] = CATEGORIAS) -> Table:
    """Sinais agrupados por categoria, com gravidade e evidencia. Serve ao e-mail e ao SMS."""
    grade = Table.grid(padding=(0, 2), expand=True)
    grade.add_column(width=2, no_wrap=True)
    grade.add_column(width=7, no_wrap=True)
    grade.add_column(ratio=1, overflow="fold")
    primeira = True
    for categoria in categorias:
        itens = [x for x in achados if x.categoria == categoria]
        if not itens:
            continue
        if not primeira:
            grade.add_row("", "", "")
        primeira = False
        grade.add_row("", "", Text(NOMES_CATEGORIAS[categoria], style=COR_ROTULO))
        for x in itens:
            cor = COR_GRAVIDADE[x.gravidade]
            corpo = Text(x.titulo, style="bold white")
            corpo.append(f"\n{x.detalhe}", style=COR_ROTULO)
            grade.add_row(Text("●", style=cor), Text(NOME_GRAVIDADE[x.gravidade], style=cor), corpo)
    return grade


def _secao(titulo: str) -> Text:
    return Text(f"\n{titulo}", style="bold white")


def relatorio(a: Analise, gravado: bool | None = None) -> Panel:
    titulo, cor, conselho = _veredito(a)
    risco = a.risco
    partes: list = [medidor(risco.nota, risco.nivel, largura=30), Text(""), _cabecalho(a),
                    _secao("Autenticação"), _autenticacao(a),
                    _secao(f"Links ({len(a.links)})"), _links(a)]
    if a.bancario:
        suspeitos = {l.dominio for l in a.links if l.suspeito}
        bloco = secao_bancaria(a.bancario, suspeitos)
        if bloco is not None:
            partes += [_secao("Boleto, Pix e QR Code"), bloco]
    if a.achados:
        partes += [_secao(f"Sinais encontrados ({len(a.achados)})"), lista_sinais(a.achados),
                   _secao("Como a nota foi calculada"), explicacao(risco)]
    partes.append(Text(f"\n{conselho}", style=COR_ATENCAO if risco.nivel in ("alto", "critico") else COR_ROTULO))
    if gravado is not None:
        partes.append(Text("Análise gravada no banco (sem o corpo do e-mail)." if gravado
                           else "Banco indisponível: análise não gravada.", style=COR_BORDA))
    return Panel(Group(*partes), title=titulo, title_align="left", box=box.ROUNDED,
                 border_style=cor, padding=(1, 2))
