"""Extrai os links do e-mail e procura disfarces neles.

O disfarce classico: o texto do botao mostra ``www.bradesco.com.br``, mas o
link de verdade (href) leva para outro lugar. No HTML o golpista escreve o
que quiser como texto visivel; so o href diz para onde o clique vai.
"""

from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass
from datetime import datetime
from html.parser import HTMLParser
from urllib.parse import unquote, urlsplit

from analisador.achados import ALTA, BAIXA, MEDIA, Achado
from cruzamento.consulta import duracao
from monitor.detector import NOMES_TECNICAS, Marca, analisar
from monitor.pesquisa import buscar_registro, dominios_acima, extrair_dominio

ENCURTADORES = frozenset({
    "bit.ly", "tinyurl.com", "cutt.ly", "is.gd", "t.co", "rebrand.ly", "ow.ly", "s.id",
    "shorturl.at", "encurtador.com.br", "rb.gy", "t.ly", "tiny.cc", "goo.gl", "bitly.com",
    "l1nk.dev", "abre.ai", "u.to",
})

URL_NO_TEXTO = re.compile(r"\b(?:https?://|www\.)[^\s<>\"')\]]+", re.IGNORECASE)
PARECE_DOMINIO = re.compile(r"^(?:https?://)?(?:www\.)?[a-z0-9-]+(?:\.[a-z0-9-]+)+(?:/\S*)?$", re.IGNORECASE)


@dataclass
class Link:
    url: str
    dominio: str | None
    texto_visivel: str | None   # o que o usuario ve; None para link solto no texto
    suspeito: bool = False      # algum sinal saiu deste link (usado para colorir a tela)


class _ColetorDeLinks(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[Link] = []
        self._href: str | None = None
        self._texto: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            href = dict(attrs).get("href")
            if href and not href.lower().startswith(("mailto:", "tel:", "#", "javascript:void")):
                self._href, self._texto = href.strip(), []

    def handle_data(self, data):
        if self._href is not None:
            self._texto.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self._href is not None:
            texto = " ".join("".join(self._texto).split())
            self.links.append(Link(self._href, extrair_dominio(self._href), texto or None))
            self._href = None


def extrair(html: str, texto: str) -> list[Link]:
    """Links do HTML (com texto visivel) e URLs soltas no texto puro, sem repetir."""
    coletor = _ColetorDeLinks()
    if html:
        coletor.feed(html)
    links = coletor.links
    vistos = {l.url for l in links}
    for url in URL_NO_TEXTO.findall(texto or ""):
        url = url.rstrip(".,;:!?")
        if url not in vistos:
            vistos.add(url)
            links.append(Link(url, extrair_dominio(url), None))
    return links


def _dominio_do_texto(texto: str | None) -> str | None:
    """Se o texto visivel tem cara de endereco, qual dominio ele promete."""
    if not texto:
        return None
    candidato = texto.strip().rstrip("/")
    return extrair_dominio(candidato) if PARECE_DOMINIO.match(candidato) else None


def _mesmo_site(a: str, b: str) -> bool:
    a, b = a.removeprefix("www."), b.removeprefix("www.")
    return a == b or a.endswith("." + b) or b.endswith("." + a)


def achados(links: list[Link], marcas: list[Marca]) -> list[Achado]:
    lista: list[Achado] = []
    for link in links:
        antes = len(lista)
        _achados_do_link(link, marcas, lista)
        link.suspeito = len(lista) > antes

    # Mesmo achado no mesmo detalhe aparece uma vez so (um botao repetido no rodape, por exemplo).
    unicos = {(a.tecnica, a.detalhe): a for a in lista}
    return list(unicos.values())


def _achados_do_link(link: Link, marcas: list[Marca], lista: list[Achado]) -> None:
    dominio = link.dominio
    if dominio is None:
        return

    prometido = _dominio_do_texto(link.texto_visivel)
    if prometido and not _mesmo_site(prometido, dominio):
        lista.append(Achado("links", "link_disfarcado", "Link disfarçado",
                            f'o texto mostra "{link.texto_visivel}", mas o clique leva para {dominio}', ALTA))

    partes = urlsplit(link.url if "://" in link.url else "http://" + link.url)
    if "@" in partes.netloc:
        enganoso = unquote(partes.netloc.rsplit("@", 1)[0])
        lista.append(Achado("links", "arroba_na_url", "Endereço com @ enganoso",
                            f'"{enganoso}" antes do @ é ignorado; o destino real é {dominio}', ALTA))

    try:
        ipaddress.ip_address(dominio)
        lista.append(Achado("links", "link_para_ip", "Link para número de IP",
                            f"leva direto para {dominio}, sem nome de site", MEDIA))
        return
    except ValueError:
        pass

    if dominio.removeprefix("www.") in ENCURTADORES:
        lista.append(Achado("links", "encurtador", "Link encurtado",
                            f"{dominio} esconde o destino real até o clique", MEDIA))

    for det in analisar(dominio, marcas):
        nomes = ", ".join(NOMES_TECNICAS[m["tecnica"]].lower().replace("tld", "TLD") for m in det.motivos[:2])
        lista.append(Achado("links", "link_imita_marca", f"Link imita o {det.marca.nome}",
                            f"{dominio} ({nomes})", ALTA))

    if "xn--" in dominio:
        lista.append(Achado("links", "link_punycode", "Link com letras disfarçadas",
                            f"{dominio} usa letras de outro alfabeto", MEDIA))

    if partes.scheme == "http" and link.texto_visivel is not None:
        lista.append(Achado("links", "link_sem_https", "Link sem HTTPS",
                            f"{dominio} não usa conexão segura", BAIXA))


def achados_conhecidos(links: list[Link], conn, referencia: datetime | None = None) -> list[Achado]:
    """Links cujo dominio (ou dominio "acima") ja esta no banco como golpe.

    E o cruzamento entre as frentes: o monitor viu o certificado do site falso
    nascer nos CT logs; dias depois o mesmo dominio chega num e-mail ou SMS.
    """
    lista: list[Achado] = []
    if conn is None:
        return lista
    for link in links:
        if not link.dominio:
            continue
        for candidato in [link.dominio, *dominios_acima(link.dominio)]:
            try:
                reg = buscar_registro(conn, candidato)
            except Exception:
                return lista
            if reg:
                quando = reg.detectado_em.astimezone().strftime("%d/%m/%Y %H:%M")
                detalhe = f"{reg.dominio} está no banco desde {quando} (imita o {reg.marca})"
                # ``referencia`` = quando a mensagem chegou: quanto antes o sistema ja sabia.
                if referencia and referencia > reg.detectado_em:
                    detalhe += f"; o monitor já sabia {duracao(referencia - reg.detectado_em)} antes desta mensagem"
                lista.append(Achado("links", "link_ja_conhecido", "Link já conhecido como golpe", detalhe, ALTA))
                link.suspeito = True
                break
    return list({a.detalhe: a for a in lista}.values())
