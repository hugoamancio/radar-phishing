"""O remetente finge ser o banco?

O nome que aparece na caixa de entrada ("Bradesco") e texto livre: qualquer
um escreve o que quiser. O que identifica o remetente e o endereco depois
do @, e mesmo ele so vale se a autenticacao (SPF/DKIM/DMARC) confirmar.
"""

from __future__ import annotations

from analisador.achados import ALTA, MEDIA, Achado
from analisador.autenticacao import dominio_organizacional
from analisador.leitura import Mensagem
from monitor.detector import Marca, analisar
from monitor.normalizacao import variantes

PROVEDORES_GRATUITOS = frozenset({
    "gmail.com", "hotmail.com", "outlook.com", "live.com", "yahoo.com", "yahoo.com.br",
    "bol.com.br", "uol.com.br", "terra.com.br", "icloud.com", "proton.me", "protonmail.com",
})


def achados(msg: Mensagem, marcas: list[Marca]) -> list[Achado]:
    lista: list[Achado] = []
    dominio = msg.dominio_remetente
    if not dominio:
        return [Achado("remetente", "sem_remetente", "Sem remetente válido",
                       "o campo \"De:\" está vazio ou malformado", MEDIA)]

    nome_normal = " ".join(variantes(msg.remetente_nome.lower())) if msg.remetente_nome else ""
    for marca in marcas:
        cita_marca = any(p in nome_normal for p in marca.palavras_chave)
        if cita_marca and not marca.eh_oficial(dominio):
            gratuito = dominio in PROVEDORES_GRATUITOS
            lista.append(Achado(
                "remetente", "nome_falso", f"Diz ser o {marca.nome}, mas não é",
                f'o nome mostra "{msg.remetente_nome}", mas o endereço é {msg.remetente_endereco}'
                + (" (e-mail gratuito, que banco nenhum usa)" if gratuito else ""),
                ALTA))

    for det in analisar(dominio, marcas):
        lista.append(Achado("remetente", "dominio_imita_marca", f"Domínio do remetente imita o {det.marca.nome}",
                            f"{dominio}: " + "; ".join(m["detalhe"] for m in det.motivos[:2]), ALTA))

    if msg.reply_to and dominio_organizacional(msg.reply_to.rpartition("@")[2]) != dominio_organizacional(dominio):
        lista.append(Achado("remetente", "resposta_desviada", "Resposta vai para outro lugar",
                            f"quem responder escreve para {msg.reply_to}, não para {msg.remetente_endereco}",
                            MEDIA))
    return lista
