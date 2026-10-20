"""Decide se um dominio imita uma marca monitorada e explica por que.

Funcoes puras, sem rede nem banco: recebem texto, devolvem um resultado. Isso
permite testar cada tecnica de disfarce isoladamente (ver tests/).

Tecnicas que, sozinhas, bastam para marcar o dominio como suspeito:

    marca_no_dominio      a palavra da marca aparece no dominio
    subdominio_enganoso   o dominio oficial inteiro aparece como prefixo
                          (bradesco.com.br.acesso-seguro.xyz)
    marca_em_subdominio   a marca esta so na parte que o dono do dominio cria a
                          vontade; o dominio registrado e outro
                          (x.bradesco.support.bloodoperationbag.xyz)
    homografo             a marca so aparece depois de trocar letras de outros
                          alfabetos ou punycode (brаdesco com "а" cirilico)
    troca_de_caracteres   a marca so aparece depois de desfazer 0->o, rn->m...
    erro_de_digitacao     uma parte do dominio difere da marca por 1 letra
                          (bardesco, bradesc, bradescoo)

Tecnicas que so reforcam uma deteccao (sozinhas gerariam ruido demais):

    palavra_isca          termos tipicos de golpe: seguranca, token, pix...
    tld_suspeito          terminacoes baratas e preferidas em golpes
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from monitor.normalizacao import (decodificar_idn, dominio_organizacional, limpar, tem_disfarce,
                                  tokens, variantes)

PALAVRAS_ISCA = frozenset({
    "acesso", "app", "aplicativo", "atendimento", "atualiza", "atualizacao",
    "atualizar", "bloqueio", "cadastro", "cartao", "cliente", "clientes",
    "conta", "desbloqueio", "desbloquear", "ib", "internet", "login",
    "net", "online", "pix", "pontos", "premio", "premiado", "recadastro",
    "recadastramento", "regularizar", "resgate", "seguro", "seguranca",
    "sms", "suporte", "token", "validar", "validacao", "verificacao",
    "verificar", "web",
})

TLDS_SUSPEITOS = frozenset({
    "app", "buzz", "cfd", "click", "cyou", "icu", "info", "live", "online",
    "rest", "sbs", "shop", "site", "store", "top", "vip", "xyz",
})

# Tecnicas que, sozinhas, marcam o dominio. A ordem define a "principal".
TECNICAS_FORTES = (
    "subdominio_enganoso", "marca_em_subdominio", "homografo", "troca_de_caracteres",
    "erro_de_digitacao", "marca_no_dominio",
)
ORDEM_TECNICAS = TECNICAS_FORTES + ("palavra_isca", "tld_suspeito")

# Nome de cada tecnica como aparece para o usuario.
NOMES_TECNICAS = {
    "subdominio_enganoso": "Subdomínio enganoso",
    "marca_em_subdominio": "Marca só no subdomínio",
    "homografo": "Homógrafo",
    "troca_de_caracteres": "Troca de caracteres",
    "erro_de_digitacao": "Erro de digitação",
    "marca_no_dominio": "Marca no domínio",
    "palavra_isca": "Palavra-isca",
    "tld_suspeito": "TLD suspeito",
}


@dataclass(frozen=True)
class Marca:
    id: int
    nome: str
    dominios_oficiais: tuple[str, ...]
    palavras_chave: tuple[str, ...]
    codigo_banco: str | None = None     # codigo FEBRABAN (Bradesco = 237), para conferir boletos

    def eh_oficial(self, dominio: str) -> bool:
        return any(dominio == o or dominio.endswith("." + o) for o in self.dominios_oficiais)


@dataclass
class Deteccao:
    dominio: str
    marca: Marca
    trecho: str                       # parte do dominio que imita a marca
    motivos: list[dict] = field(default_factory=list)

    @property
    def tecnicas(self) -> list[str]:
        return [m["tecnica"] for m in self.motivos]

    @property
    def principal(self) -> str:
        return next(t for t in TECNICAS_FORTES if t in self.tecnicas)

    def adicionar(self, tecnica: str, detalhe: str) -> None:
        if tecnica not in self.tecnicas:
            self.motivos.append({"tecnica": tecnica, "detalhe": detalhe})
            # Mais grave primeiro: e a ordem em que o analista deve ler.
            self.motivos.sort(key=lambda m: ORDEM_TECNICAS.index(m["tecnica"]))


def distancia(a: str, b: str) -> int:
    """Distancia de Damerau-Levenshtein (insercao, remocao, troca e inversao de vizinhas)."""
    anterior2: list[int] = []
    anterior = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        atual = [i] + [0] * len(b)
        for j, cb in enumerate(b, 1):
            custo = ca != cb
            atual[j] = min(anterior[j] + 1, atual[j - 1] + 1, anterior[j - 1] + custo)
            if i > 1 and j > 1 and ca == b[j - 2] and a[i - 2] == cb:
                atual[j] = min(atual[j], anterior2[j - 2] + 1)
        anterior2, anterior = anterior, atual
    return anterior[-1]


def _trigramas(palavra: str) -> tuple[str, ...]:
    return tuple(palavra[i:i + 3] for i in range(len(palavra) - 2))


def _parecido_com(token: str, palavra: str) -> str | None:
    """Trecho do token a 1 edicao de distancia da palavra, ou None.

    Filtro barato antes do calculo caro: uma unica edicao altera no maximo 3
    trigramas, entao um parecido real ainda compartilha ao menos 2 trigramas
    com a palavra. Quase todos os tokens da internet tem zero e sao
    descartados aqui, o que mantem o monitor leve com ~1.500 certificados/s.
    """
    if len(palavra) < 6 or palavra in token:
        return None
    if sum(t in token for t in _trigramas(palavra)) < 2:
        return None
    n = len(palavra)
    for tamanho in (n, n - 1, n + 1):
        for inicio in range(0, len(token) - tamanho + 1):
            janela = token[inicio:inicio + tamanho]
            if distancia(janela, palavra) == 1 and _sobra_aceitavel(token[:inicio] + token[inicio + tamanho:]):
                return janela
    return None


def _sobra_aceitavel(sobra: str) -> bool:
    """O que sobra no token alem do trecho parecido com a marca.

    "bardescoapp" sobra "app": golpe. "bladescommercialwaterheaters" sobra
    "mmercialwaterheaters": e so uma palavra que comeca parecida (caso real,
    uma empresa inglesa de aquecedores, pego pelo monitor em 19/10/2026).
    """
    return len(sobra) <= 3 or sobra in PALAVRAS_ISCA


def analisar(dominio_bruto: str, marcas: list[Marca]) -> list[Deteccao]:
    """Analisa um dominio contra todas as marcas. Lista vazia = nada suspeito."""
    dominio = limpar(dominio_bruto)
    if not dominio or "." not in dominio:
        return []

    leituras = variantes(dominio)
    partes = tokens(dominio)
    tld = partes[-1] if partes else ""
    encontradas: list[Deteccao] = []

    for marca in marcas:
        if marca.eh_oficial(dominio):
            continue
        det: Deteccao | None = None

        for palavra in marca.palavras_chave:
            if palavra in dominio:
                det = det or Deteccao(dominio, marca, trecho=palavra)
                det.adicionar("marca_no_dominio", f'contém "{palavra}"')
            elif palavra in dominio.replace("-", ""):
                trecho = _trecho_com_hifen(dominio, palavra)
                det = det or Deteccao(dominio, marca, trecho=trecho)
                det.adicionar("marca_no_dominio", f'"{palavra}" partido por hífen: "{trecho}"')
            elif any(palavra in v for v in leituras):
                det = det or Deteccao(dominio, marca, trecho=_trecho_disfarcado(dominio, palavra))
                if tem_disfarce(dominio):
                    det.adicionar("homografo", f'"{palavra}" escrito com letras de outro alfabeto')
                else:
                    det.adicionar("troca_de_caracteres", f'"{palavra}" com caracteres trocados (0 por o, rn por m...)')

        # Erro de digitacao so e procurado quando a marca nao aparece de forma
        # direta; senao "bradesco" seria acusado por estar a 1 letra de "bradescco".
        if det is None:
            for palavra in marca.palavras_chave:
                parecido = next(filter(None, (_parecido_com(p, palavra) for p in partes)), None)
                if parecido:
                    det = Deteccao(dominio, marca, trecho=parecido)
                    det.adicionar("erro_de_digitacao", f'"{parecido}" difere de "{palavra}" por 1 letra')
                    break

        if det is None:
            continue

        for oficial in marca.dominios_oficiais:
            if "." in oficial and (dominio.startswith(oficial + ".") or f".{oficial}." in dominio):
                det.adicionar("subdominio_enganoso", f'usa "{oficial}" como fachada antes do domínio real')
                break
        else:
            # A parte que alguem registrou e paga e o dominio organizacional; o
            # resto (subdominios) o dono cria a vontade, sem pedir a ninguem.
            # Marca so no subdominio = fachada montada em cima de outro dominio.
            org = dominio_organizacional(dominio)
            if not _marca_em(org, det.trecho, marca):
                det.adicionar("marca_em_subdominio",
                              f'a marca está só no subdomínio; o domínio registrado é {decodificar_idn(org)}')

        iscas = sorted({p for p in partes[:-1] if p in PALAVRAS_ISCA}
                       | {p for p in PALAVRAS_ISCA if len(p) >= 5 and any(p in t for t in partes[:-1])})
        if iscas:
            det.adicionar("palavra_isca", "termos de golpe: " + ", ".join(iscas))
        if tld in TLDS_SUSPEITOS:
            det.adicionar("tld_suspeito", f'terminação ".{tld}", comum em golpes')

        encontradas.append(det)

    return encontradas


def _marca_em(org: str, trecho: str, marca: Marca) -> bool:
    """O dominio registrado contem a marca (direta, disfarcada ou o trecho parecido)?"""
    if trecho in org or trecho in decodificar_idn(org):
        return True
    leituras = variantes(org) | variantes(org.replace("-", ""))
    return any(p in v for p in marca.palavras_chave for v in leituras)


def _trecho_com_hifen(dominio: str, palavra: str) -> str:
    """Trecho original de uma marca partida por hifens (``bra-desco``)."""
    padrao = "-*".join(re.escape(c) for c in palavra)
    achado = re.search(padrao, dominio)
    return achado.group(0) if achado else palavra


def _trecho_disfarcado(dominio: str, palavra: str) -> str:
    """Parte do dominio, como o usuario a ve (punycode ja decodificado), que imita a marca."""
    partes = tokens(decodificar_idn(dominio))
    for parte in partes:
        if any(palavra in v for v in variantes(parte)):
            return parte
    return partes[0] if partes else palavra
