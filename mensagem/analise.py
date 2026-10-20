"""Analisa um SMS ou mensagem de WhatsApp colado como texto.

No Brasil a maior parte dos golpes contra cliente de banco chega por SMS e
WhatsApp, nao por e-mail. A mensagem passa pelas mesmas pecas do resto do
sistema: detector de dominios, analise de linguagem, boleto/Pix, cruzamento
com os golpes ja vistos pelo monitor e o motor de risco.

Diferencas em relacao ao e-mail:
- nao ha SPF/DKIM/DMARC: o "remetente" e so um numero, e qualquer um o forja;
- links costumam vir SEM "http://" ("bradesco-cancelar.top/x"), entao
  dominios soltos no texto tambem contam como link.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timezone

from analisador import linguagem, links
from analisador.achados import MEDIA, ORDEM_GRAVIDADE, Achado
from bancario import analise as analise_bancaria
from monitor.detector import TLDS_SUSPEITOS, Marca
from monitor.pesquisa import extrair_dominio
from risco.modelo import Avaliacao, calcular

CANAIS = ("sms", "whatsapp", "outro")
CATEGORIAS = ("remetente", "links", "linguagem", "bancario")

# Terminacoes aceitas para dominio "solto" no texto. Sem a lista, "Sr.Joao"
# ou "obrigado.vlw" virariam links.
TLDS_COMUNS = {"com", "br", "net", "org", "me", "io", "co", "ly", "gl", "to", "cc", "gov", "edu", "biz"} \
    | set(TLDS_SUSPEITOS)
DOMINIO_SOLTO = re.compile(
    r"(?<![@\w.-])((?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+(?:" + "|".join(sorted(TLDS_COMUNS, key=len, reverse=True))
    + r"))(?:/[^\s<>\"']*)?(?![\w-])", re.IGNORECASE)


@dataclass
class AnaliseMensagem:
    texto: str                 # fica so em memoria: nunca e gravado
    canal: str
    remetente: str | None
    links: list[links.Link]
    achados: list[Achado]
    bancario: analise_bancaria.ResultadoBancario

    @property
    def sha256(self) -> str:
        return hashlib.sha256(" ".join(self.texto.split()).encode("utf-8")).hexdigest()

    @property
    def risco(self) -> Avaliacao:
        return calcular([a.tecnica for a in self.achados])

    def por_categoria(self, categoria: str) -> list[Achado]:
        return [a for a in self.achados if a.categoria == categoria]


def extrair_links(texto: str) -> list[links.Link]:
    """URLs com http/www (como no e-mail) e dominios soltos com terminacao conhecida."""
    lista = links.extrair("", texto)
    vistos = {l.dominio for l in lista}
    for m in DOMINIO_SOLTO.finditer(texto or ""):
        url = m.group(0).rstrip(".,;:!?)")
        dominio = extrair_dominio(url)
        if dominio and dominio not in vistos and not re.fullmatch(r"[\d.]+", dominio):
            vistos.add(dominio)
            lista.append(links.Link(url, dominio, None))
    return lista


def _achados_remetente(canal: str, remetente: str | None, alegada: Marca | None) -> list[Achado]:
    """SMS de banco costuma vir de numero curto (5 ou 6 digitos), nao de celular comum."""
    if canal != "sms" or not remetente or not alegada:
        return []
    digitos = re.sub(r"\D", "", remetente)
    if len(digitos) >= 10:
        return [Achado("remetente", "remetente_celular_comum", f"Diz ser o {alegada.nome}, mas veio de um celular",
                       f"o SMS veio de {remetente}; bancos costumam enviar SMS por números curtos, "
                       f"de 5 ou 6 dígitos", MEDIA)]
    return []


def analisar(texto: str, marcas: list[Marca], canal: str = "sms", remetente: str | None = None,
             conn=None) -> AnaliseMensagem:
    if canal not in CANAIS:
        raise ValueError(f"canal deve ser um de {CANAIS}")
    lista_links = extrair_links(texto)
    bancario = analise_bancaria.analisar([texto], [], marcas)
    todos = (_achados_remetente(canal, remetente, bancario.marca_alegada)
             + links.achados(lista_links, marcas)
             + links.achados_conhecidos(lista_links, conn, datetime.now(timezone.utc))
             + linguagem.achados("", texto, "")
             + bancario.achados)
    todos.sort(key=lambda a: (CATEGORIAS.index(a.categoria), ORDEM_GRAVIDADE[a.gravidade]))
    return AnaliseMensagem(texto, canal, remetente, lista_links, todos, bancario)
