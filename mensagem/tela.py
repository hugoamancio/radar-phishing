"""Relatorio de um SMS ou WhatsApp, no mesmo visual do relatorio de e-mail."""

from __future__ import annotations

from rich import box
from rich.console import Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from analisador.tela import _secao, _veredito, lista_sinais
from bancario.tela import secao as secao_bancaria
from mensagem.analise import CATEGORIAS, AnaliseMensagem
from monitor.cores import COR_ALERTA, COR_ATENCAO, COR_BORDA, COR_OK, COR_ROTULO
from monitor.normalizacao import decodificar_idn
from risco.visual import explicacao, medidor

NOMES_CANAIS = {"sms": "SMS", "whatsapp": "WhatsApp", "outro": "Mensagem"}


def _texto_destacado(a: AnaliseMensagem) -> Text:
    """A mensagem como chegou, com os links suspeitos em vermelho."""
    texto = Text(a.texto.strip(), style="white")
    for link in a.links:
        pos = a.texto.strip().find(link.url)
        if pos >= 0:
            texto.stylize(COR_ALERTA if link.suspeito else COR_OK, pos, pos + len(link.url))
    return texto


def _links(a: AnaliseMensagem) -> Table | Text:
    if not a.links:
        return Text("Nenhum link.", style=COR_ROTULO)
    grade = Table.grid(padding=(0, 2))
    grade.add_column(overflow="fold", ratio=1)
    grade.add_column(width=1)
    grade.add_column(overflow="fold", ratio=1)
    for link in a.links:
        destino = decodificar_idn(link.dominio) if link.dominio else link.url
        grade.add_row(Text(link.url, style=COR_ROTULO), Text("→", style=COR_BORDA),
                      Text(destino, style=COR_ALERTA if link.suspeito else COR_OK))
    return grade


def relatorio(a: AnaliseMensagem, gravado: bool | None = None) -> Panel:
    titulo, cor, conselho = _veredito(a)
    # Conselhos escritos para mensagem: o texto do e-mail fala em autenticacao e anexos, que SMS nao tem.
    if not a.achados:
        conselho = "Nenhum sinal de golpe. Mesmo assim, banco nenhum pede senha, token ou Pix por mensagem."
    elif "falso_parente" in {x.tecnica for x in a.achados}:
        conselho = ("Não mande Pix. Ligue para o número ANTIGO da pessoa, ou fale com ela pessoalmente, "
                    "e confirme se ela realmente trocou de número.")
    elif a.risco.nivel in ("alto", "critico"):
        conselho = ("Não clique no link, não ligue para números da mensagem e não responda. Se já informou "
                    "algum dado, ligue para o banco pelo número que está no verso do cartão.")
    risco = a.risco
    origem = Text(NOMES_CANAIS[a.canal], style="bold white")
    if a.remetente:
        origem.append(f"  ·  de {a.remetente}", style=COR_ROTULO)
    corpo = Panel(_texto_destacado(a), box=box.ROUNDED, border_style=COR_BORDA, padding=(0, 1))

    partes: list = [medidor(risco.nota, risco.nivel, largura=30), Text(""), origem, corpo,
                    _secao(f"Links ({len(a.links)})"), _links(a)]
    bloco = secao_bancaria(a.bancario, {l.dominio for l in a.links if l.suspeito})
    if bloco is not None:
        partes += [_secao("Boleto, Pix e QR Code"), bloco]
    if a.achados:
        partes += [_secao(f"Sinais encontrados ({len(a.achados)})"), lista_sinais(a.achados, CATEGORIAS),
                   _secao("Como a nota foi calculada"), explicacao(risco)]
    partes.append(Text(f"\n{conselho}", style=COR_ATENCAO if risco.nivel in ("alto", "critico") else COR_ROTULO))
    if gravado is not None:
        partes.append(Text("Análise gravada no banco (sem o texto da mensagem)." if gravado
                           else "Banco indisponível: análise não gravada.", style=COR_BORDA))
    return Panel(Group(*partes), title=titulo, title_align="left", box=box.ROUNDED,
                 border_style=cor, padding=(1, 2))
