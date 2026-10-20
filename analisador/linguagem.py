"""Frases de engenharia social: pressa, medo, recompensa e pedido de dados.

Golpe de phishing quase sempre combina duas coisas: um motivo para agir
AGORA (prazo, bloqueio, premio) e um pedido para entregar algo (senha,
token, dados). Cada grupo abaixo procura um desses ingredientes. A busca
ignora acentos e maiusculas: "ÚLTIMO AVISO" e "ultimo aviso" contam igual.
"""

from __future__ import annotations

import re
import unicodedata
from html.parser import HTMLParser

from analisador.achados import ALTA, MEDIA, Achado

GRUPOS = {
    "urgencia": ("Pressão de tempo", MEDIA, [
        r"em ate \d+ ?(?:h|horas?|dias?)", r"nas proximas \d+ ?(?:h|horas?)", r"imediatamente",
        r"ultimo aviso", r"ultima chance", r"prazo (?:final|encerra|expira)", r"hoje mesmo",
        r"o quanto antes", r"urgente", r"expir(?:a|am|em|ara|arao) (?:hoje|amanha|em)",
    ]),
    "ameaca": ("Ameaça de bloqueio ou perda", ALTA, [
        r"(?:conta|cartao|acesso|chave pix|cadastro) (?:sera |foi |esta )?(?:bloquead[oa]|suspens[oa]|cancelad[oa]|desativad[oa])",
        r"bloqueio (?:da|de sua|do seu|preventivo)", r"evite o bloqueio", r"suspensao",
        r"cobranca indevida", r"pendencia",
    ]),
    # "Compra de R$ 1.890 aprovada. Nao reconhece? Ligue/acesse..." O susto da
    # compra que voce nao fez e a isca para entregar os dados ao "cancelar".
    "compra_falsa": ("Falso alerta de compra", ALTA, [
        r"compra (?:aprovada|realizada|efetuada)\b.{0,80}(?:nao (?:reconhece|foi voce|realizou)|cancel)",
        r"nao reconhece (?:a|esta|essa)? ?(?:compra|transacao)", r"compra (?:nao reconhecida|suspeita)",
        r"transacao (?:suspeita|nao reconhecida)",
    ]),
    # Golpe do falso parente (WhatsApp): alguem "trocou de numero" e precisa de um Pix.
    "falso_parente": ("Golpe do falso parente", ALTA, [
        r"(?:mudei|troquei) de (?:numero|celular|whats)", r"(?:esse|este) (?:e|eh) (?:o )?meu (?:numero )?novo",
        r"meu numero novo", r"salva (?:esse|este|meu) (?:novo )?numero",
    ]),
    # Pedido de dinheiro por Pix, a segunda metade do golpe do falso parente.
    "pedido_pix": ("Pedido de Pix", MEDIA, [
        r"(?:me )?(?:empresta|passa|manda|faz|faca|transfere|transferir) (?:um |uns )?pix",
        r"pix (?:urgente|pra hoje|para hoje)", r"(?:me )?empresta (?:um )?dinheiro",
    ]),
    "recompensa": ("Promessa de prêmio ou benefício", MEDIA, [
        r"voce (?:foi|esta) (?:sorteado|premiado|selecionado)", r"resgat(?:e|ar) (?:seus |os )?pontos",
        r"pontos (?:vao |irao )?expira", r"premio", r"cashback", r"bonus",
    ]),
    "dados": ("Pedido de dados sensíveis", ALTA, [
        r"(?:atualize|confirme|valide|informe|digite|regularize) (?:seus |os |o seu |sua )?(?:dados|cadastro|senha|token|cpf)",
        # PEDIR o codigo e golpe; so CITAR o codigo, nao: o banco manda "seu codigo e
        # 482913, nao compartilhe" o tempo todo (falso positivo achado nos testes).
        r"senha (?:do cartao|de 4|de 6|eletronica)",
        r"(?:informe|digite|envie|passe|confirme|responda com|me (?:passa|manda)) (?:o |seu |esse |este )?(?:codigo|token)",
        r"dados (?:cadastrais|bancarios)", r"numero do cartao", r"recadastr",
    ]),
}


# 0800 123 4567, 4004-0000, (11) 91234-5678, 11 3003-1234, +55 11 91234 5678
TELEFONE = re.compile(
    r"(?<!\d)(?:0800[\s.-]?\d{3}[\s.-]?\d{4}|[34]00[0-9][\s.-]?\d{4}"
    r"|(?:\+?55[\s.-]?)?\(?\d{2}\)?[\s.-]?9?\d{4}[\s.-]?\d{4})(?!\d)")


def _normalizar(texto: str) -> tuple[str, list[int]]:
    """Texto sem acento e minusculo + a posicao original de cada caractere.

    A busca roda no texto normalizado, mas o trecho mostrado na tela sai do
    original: "Sua conta será bloqueada", e nao "sua conta sera bloqueada".
    """
    normal, posicoes = [], []
    for i, c in enumerate(texto):
        for d in unicodedata.normalize("NFKD", c.lower()):
            if not unicodedata.combining(d):
                normal.append(d)
                posicoes.append(i)
    return "".join(normal), posicoes


def _trecho(original: str, inicio: int, fim: int) -> str:
    """O trecho achado no texto original, com um pouco de contexto e sem cortar palavras."""
    a = original.rfind(" ", 0, max(0, inicio - 25)) + 1
    b = original.find(" ", min(len(original), fim + 25))
    b = len(original) if b == -1 else b
    return ("…" if a > 0 else "") + original[a:b].strip(" .,;") + ("…" if b < len(original) else "")


def achados(assunto: str, texto: str, html_como_texto: str) -> list[Achado]:
    corpo = " ".join(f"{assunto}. {texto} {html_como_texto}".split())
    normal, posicoes = _normalizar(corpo)
    lista: list[Achado] = []
    for grupo, (titulo, gravidade, padroes) in GRUPOS.items():
        for padrao in padroes:
            m = re.search(padrao, normal)
            if m:
                inicio, fim = posicoes[m.start()], posicoes[m.end() - 1] + 1
                lista.append(Achado("linguagem", grupo, titulo, f'"{_trecho(corpo, inicio, fim)}"',
                                    gravidade))
                break  # um exemplo por grupo basta; o que importa e o grupo estar presente
    # Golpe da falsa central: a mensagem pede para LIGAR para um numero que ela
    # mesma traz. Do outro lado, um "atendente" pede senha e token.
    m = TELEFONE.search(corpo)
    if m and re.search(r"\b(?:ligue|ligar|liga|entre em contato|contate|central)\b", normal):
        lista.append(Achado("linguagem", "pede_ligacao", "Pede para ligar para um número da própria mensagem",
                            f"número {m.group(0).strip()}: ligue só para o número do verso do cartão ou do site oficial",
                            MEDIA))
    if {a.tecnica for a in lista} >= {"dados"} and len(lista) >= 2:
        lista.append(Achado("linguagem", "combinacao_classica", "Combinação clássica de golpe",
                            "cria um motivo para agir já e pede seus dados no mesmo e-mail", ALTA))
    return lista


class _ExtratorDeTexto(HTMLParser):
    """Texto visivel de um HTML, ignorando <script> e <style>."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.partes: list[str] = []
        self._ocultos = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._ocultos += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self._ocultos:
            self._ocultos -= 1

    def handle_data(self, data):
        if not self._ocultos:
            self.partes.append(data)


def html_para_texto(html: str) -> str:
    extrator = _ExtratorDeTexto()
    extrator.feed(html or "")
    return " ".join(" ".join(extrator.partes).split())
