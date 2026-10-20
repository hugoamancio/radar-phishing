"""Junta as cinco frentes de analise de um e-mail num unico resultado."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePath

from analisador import autenticacao, linguagem, links, remetente
from analisador.achados import ALTA, MEDIA, ORDEM_GRAVIDADE, Achado
from analisador.leitura import Mensagem
from bancario import analise as analise_bancaria
from monitor.detector import Marca
from risco.modelo import Avaliacao, calcular

# Anexos que executam algo ao abrir, ou que costumam esconder quem executa.
EXTENSOES_PERIGOSAS = {
    ".exe", ".scr", ".bat", ".cmd", ".com", ".pif", ".msi", ".js", ".jse", ".vbs", ".vbe",
    ".wsf", ".hta", ".ps1", ".lnk", ".iso", ".img", ".jar", ".apk",
}
EXTENSOES_INOCENTES = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".jpg", ".jpeg", ".png", ".txt"}
EXTENSOES_ATENCAO = {".html", ".htm", ".zip", ".rar", ".7z", ".docm", ".xlsm", ".pptm", ".svg"}

CATEGORIAS = ("remetente", "autenticacao", "links", "linguagem", "bancario", "anexos")


@dataclass
class Analise:
    mensagem: Mensagem
    autenticacao: autenticacao.Autenticacao
    links: list[links.Link]
    achados: list[Achado]
    bancario: analise_bancaria.ResultadoBancario | None = None

    @property
    def risco(self) -> Avaliacao:
        return calcular([a.tecnica for a in self.achados])

    def por_categoria(self, categoria: str) -> list[Achado]:
        return [a for a in self.achados if a.categoria == categoria]

    def contagem(self) -> dict[str, int]:
        return {g: sum(a.gravidade == g for a in self.achados) for g in ORDEM_GRAVIDADE}


def _achados_anexos(msg: Mensagem) -> list[Achado]:
    lista = []
    for anexo in msg.anexos:
        sufixos = [s.lower() for s in PurePath(anexo.nome).suffixes]
        ext = sufixos[-1] if sufixos else ""
        disfarce = sufixos[-2] if len(sufixos) >= 2 and sufixos[-2] in EXTENSOES_INOCENTES else None
        if ext in EXTENSOES_PERIGOSAS and disfarce:
            lista.append(Achado("anexos", "extensao_dupla", f"Programa disfarçado de {disfarce}",
                                f'{anexo.nome}: parece um "{disfarce}", mas é um programa ({ext}). Nunca abra',
                                ALTA))
        elif ext in EXTENSOES_PERIGOSAS:
            lista.append(Achado("anexos", "anexo_executavel", "Anexo que executa programa",
                                f"{anexo.nome}: nunca abra", ALTA))
        elif ext in EXTENSOES_ATENCAO:
            lista.append(Achado("anexos", "anexo_arriscado", "Anexo que pode esconder golpe",
                                f"{anexo.nome} ({ext})", MEDIA))
    return lista


def analisar_mensagem(msg: Mensagem, marcas: list[Marca], conn=None, **verificadores) -> Analise:
    """``conn`` liga o cruzamento com o banco (link ja conhecido como golpe).

    ``verificadores`` repassa as funcoes de DNS/DKIM; os testes as trocam para rodar offline.
    """
    aut = autenticacao.verificar(msg, **verificadores)
    texto_html = linguagem.html_para_texto(msg.html)

    # Boleto, Pix e QR Code: no texto, nos anexos e nas imagens do corpo.
    bancario = analise_bancaria.analisar(
        [msg.remetente_nome, msg.assunto, msg.texto, texto_html],
        [(a.nome, a.tipo, a.dados) for a in msg.anexos + msg.imagens], marcas)
    # Links escondidos em QR Code entram na mesma analise dos links do texto.
    lista_links = links.extrair(msg.html, msg.texto) + bancario.links

    # Endereco oficial no "De:" + DMARC falhando = alguem usou o endereco do banco
    # sem ser o banco. O sinal vai para "Remetente", que e onde o usuario procura.
    falsificado = []
    if aut.dmarc.resultado in autenticacao.RESULTADOS_FALHA:
        for marca in marcas:
            if marca.eh_oficial(msg.dominio_remetente):
                falsificado.append(Achado(
                    "remetente", "endereco_oficial_falsificado", f"Usa o endereço do {marca.nome} sem ser ele",
                    f"{msg.remetente_endereco} aparece no \"De:\", mas a autenticação mostra que o e-mail "
                    f"não saiu dos servidores do {marca.nome}", ALTA))

    todos = (falsificado + remetente.achados(msg, marcas)
             + autenticacao.achados(aut)
             + links.achados(lista_links, marcas)
             + links.achados_conhecidos(lista_links, conn, msg.recebido_em)
             + linguagem.achados(msg.assunto, msg.texto, texto_html)
             + bancario.achados
             + _achados_anexos(msg))
    todos.sort(key=lambda a: (CATEGORIAS.index(a.categoria), ORDEM_GRAVIDADE[a.gravidade]))
    return Analise(msg, aut, lista_links, todos, bancario)
