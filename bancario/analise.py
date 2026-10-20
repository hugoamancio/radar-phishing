"""Boleto, Pix e QR Code dentro de um e-mail ou mensagem.

A pergunta central de cada verificacao e a mesma: o dinheiro vai para quem a
mensagem diz? Para responder, primeiro descobrimos que banco a mensagem
ALEGA ser (pelo texto e pelo nome do remetente) e depois comparamos com o
banco do boleto e com o recebedor do Pix.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from analisador.achados import ALTA, MEDIA, Achado
from analisador.links import Link
from bancario import arquivos, boleto, pix
from monitor.detector import Marca
from monitor.pesquisa import extrair_dominio

PADRAO_VALOR = re.compile(r"R\$\s?(\d{1,3}(?:\.\d{3})*,\d{2})")


@dataclass
class Origem:
    """Onde o item foi achado, para a tela dizer "no PDF fatura.pdf"."""
    descricao: str


@dataclass
class ResultadoBancario:
    marca_alegada: Marca | None
    boletos: list[tuple[boleto.Boleto, str]] = field(default_factory=list)
    pix: list[tuple[pix.Pix, str]] = field(default_factory=list)
    qr_links: list[tuple[str, str]] = field(default_factory=list)   # (url, onde)
    achados: list[Achado] = field(default_factory=list)
    valores_citados: set[float] = field(default_factory=set)       # "R$ ..." no texto da mensagem

    @property
    def links(self) -> list[Link]:
        """Links escondidos em QR Code, para passarem pela mesma analise dos links do texto."""
        return [Link(url, extrair_dominio(url), f"(QR Code em {onde})") for url, onde in self.qr_links]

    @property
    def vazio(self) -> bool:
        return not (self.boletos or self.pix or self.qr_links)


def _sem_acento(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", (texto or "").lower()) if not unicodedata.combining(c))


def marca_alegada(textos: list[str], marcas: list[Marca]) -> Marca | None:
    corpo = _sem_acento(" ".join(textos))
    for marca in marcas:
        if any(re.search(rf"\b{re.escape(p)}\b", corpo) for p in marca.palavras_chave):
            return marca
    return None


def _valores_citados(texto: str) -> set[float]:
    return {float(v.replace(".", "").replace(",", ".")) for v in PADRAO_VALOR.findall(texto or "")}


def _real(valor: float) -> str:
    return "R$ " + f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def analisar(textos: list[str], arquivos_recebidos: list[tuple[str, str, bytes]], marcas: list[Marca]) -> ResultadoBancario:
    """``textos``: corpo e assunto. ``arquivos_recebidos``: (nome, tipo, bytes) de anexos e imagens."""
    alegada = marca_alegada(textos, marcas)
    r = ResultadoBancario(alegada)
    texto_corpo = "\n".join(textos)

    # 1. Coleta: o que tem no texto e o que tem dentro de imagens e PDFs.
    fontes_texto = [(texto_corpo, "no texto")]
    codigos_qr: list[tuple[str, str]] = []
    for nome, tipo, dados in arquivos_recebidos:
        if arquivos.eh_pdf(nome, tipo, dados):
            fontes_texto.append((arquivos.texto_de_pdf(dados), f"no PDF {nome}"))
            codigos_qr += [(q, f"PDF {nome}") for q in arquivos.qrcodes_em_pdf(dados)]
        elif arquivos.eh_imagem(nome, tipo, dados):
            codigos_qr += [(q, f"imagem {nome}") for q in arquivos.qrcodes_em_imagem(dados)]

    vistos_boleto: set[str] = set()
    for texto, onde in fontes_texto:
        for b in boleto.encontrar(texto):
            if b.linha not in vistos_boleto:
                vistos_boleto.add(b.linha)
                r.boletos.append((b, onde))
        for codigo in pix.encontrar_em_texto(texto):
            p = pix.ler(codigo)
            if p:
                r.pix.append((p, f"Pix copia e cola {onde}"))
    for conteudo, onde in codigos_qr:
        p = pix.ler(conteudo)
        if p:
            r.pix.append((p, f"QR Code de Pix na {onde}"))
        elif extrair_dominio(conteudo):
            r.qr_links.append((conteudo, onde))

    # 2. Sinais.
    # Compara com o valor que a MENSAGEM promete, nao com o do PDF: o golpista
    # deixa o PDF coerente com o boleto falso; quem destoa e o texto do e-mail.
    citados = r.valores_citados = _valores_citados(texto_corpo)
    for b, onde in r.boletos:
        if not b.valido:
            r.achados.append(Achado("bancario", "boleto_adulterado", "Boleto com linha digitável adulterada",
                                    f"{onde}: {'; '.join(b.problemas)}", ALTA))
        if alegada and alegada.codigo_banco and b.tipo == "bancario" and b.banco_codigo != alegada.codigo_banco:
            r.achados.append(Achado(
                "bancario", "boleto_banco_divergente", f"Diz ser do {alegada.nome}, mas o boleto é de outro banco",
                f"{onde}: o boleto começa com {b.banco_codigo} ({b.banco_nome or 'banco desconhecido'}); "
                f"o {alegada.nome} é {alegada.codigo_banco}", ALTA))
        if b.valor and citados and not any(abs(b.valor - v) < 0.005 for v in citados):
            r.achados.append(Achado(
                "bancario", "boleto_valor_divergente", "Valor do boleto diferente do texto",
                f"o texto fala em {', '.join(_real(v) for v in sorted(citados))}; o boleto cobra {_real(b.valor)}",
                MEDIA))

    for p, onde in r.pix:
        if not p.crc_ok:
            r.achados.append(Achado("bancario", "pix_alterado", "Código Pix alterado ou corrompido",
                                    f"{onde}: {'; '.join(p.problemas)}", MEDIA))
        if alegada and p.recebedor:
            recebedor = _sem_acento(p.recebedor)
            if not any(palavra in recebedor for palavra in alegada.palavras_chave):
                r.achados.append(Achado(
                    "bancario", "pix_recebedor_divergente", f"O Pix não vai para o {alegada.nome}",
                    f'{onde}: o dinheiro vai para "{p.recebedor}"'
                    + (f" (chave {p.tipo_chave}: {p.chave})" if p.chave else ""), ALTA))
        if p.url:
            r.qr_links.append((p.url if "://" in p.url else "https://" + p.url, f"Pix dinâmico ({onde})"))

    for url, onde in r.qr_links:
        if not onde.startswith("Pix dinâmico"):
            r.achados.append(Achado(
                "bancario", "qrcode_esconde_link", "Link escondido em QR Code",
                f"{onde} leva para {extrair_dominio(url)}; filtros de e-mail não leem imagens", MEDIA))
    return r
