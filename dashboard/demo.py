"""Dados FICTICIOS para o modo demonstracao (python -m dashboard --demo).

Servem para mostrar o dashboard cheio, em print de portfolio ou apresentacao,
sem expor dados reais. A pagina mostra a faixa "demonstracao" em todo o tempo.
Mesmas formas de dashboard/dados.py.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

from cruzamento.consulta import duracao
from monitor.detector import NOMES_TECNICAS, Marca, analisar
from monitor.normalizacao import decodificar_idn
from risco.modelo import NOMES_NIVEIS, calcular

BRADESCO = Marca(1, "Bradesco", ("bradesco.com.br", "bradesco", "bradescoseguros.com.br", "next.me"),
                 ("bradesco", "bradesc0", "bradescco", "bradesko", "bradesconet"), "237")


def _agora() -> datetime:
    """Relogio de verdade a cada chamada: com um horario fixo, a demonstracao
    "envelhecia" e o status virava "monitor parado" minutos depois de ligar."""
    return datetime.now(timezone.utc)

DOMINIOS = [
    ("x7k2.bradesco.support.entregarapida.click", "Let's Encrypt"),
    ("bradesco-cancelar.top", "Let's Encrypt"),
    ("brаdesco-login.com".encode("idna").decode(), "Google Trust Services"),
    ("bradesco.com.br.acesso-seguro.xyz", "Let's Encrypt"),
    ("bardesco-token.top", "ZeroSSL"),
    ("br4desco-app.online", "Let's Encrypt"),
    ("atualizacao-bradesco-pix.com", "Let's Encrypt"),
    ("lwq9.bradesco.accounts.suporte-especializado.org", "Let's Encrypt"),
    ("bradesco-pontos-livelo.shop", "Google Trust Services"),
    ("bradezco-seguranca.site", "ZeroSSL"),
    ("bradesco-premiado.vip", "Let's Encrypt"),
    ("seguro.bradesco-net.info", "Let's Encrypt"),
]


def _deteccoes() -> list[dict]:
    linhas = []
    for i, (dominio, emissor) in enumerate(DOMINIOS):
        det = analisar(dominio, [BRADESCO])[0]
        r = calcular(det.tecnicas)
        linhas.append({
            "dominio": det.dominio, "visivel": decodificar_idn(det.dominio), "marca": "Bradesco", "tecnica": NOMES_TECNICAS[det.principal],
            "reforcos": [NOMES_TECNICAS[t] for t in det.tecnicas if t in ("palavra_isca", "tld_suspeito")],
            "trecho": det.trecho, "quando": (_agora() - timedelta(minutes=7 + i * 53)).isoformat(),
            "emissor": emissor, "nota": r.nota, "nivel": r.nivel,
        })
    return linhas


def resumo() -> dict:
    niveis = {"baixo": 3, "medio": 11, "alto": 19, "critico": 8}
    return {
        "suspeitos": sum(niveis.values()), "suspeitos_24h": 6,
        "niveis": [{"nivel": n, "nome": NOMES_NIVEIS[n], "total": t} for n, t in niveis.items()],
        "emails": 23, "emails_golpe": 9, "mensagens": 31, "mensagens_golpe": 14,
        "monitor": {"ultimo_sinal": (_agora() - timedelta(seconds=4)).isoformat(), "ritmo": 1402,
                    "certificados": 11_482_337},
        "cruzamento": {"total": 18, "antes": 11, "depois": 3, "desconhecidos": 4, "taxa": 11 / 18,
                       "mediana": "1 d 7 h", "maior": "4 d 2 h"},
    }


def serie(dias: int = 14) -> list[dict]:
    aleatorio = random.Random(7)
    hoje = _agora().astimezone(timezone(timedelta(hours=-3))).date()
    return [{"dia": (hoje - timedelta(days=dias - 1 - i)).isoformat(),
             "total": max(0, round(2 + 1.6 * (i % 5 == 3) * 3 + aleatorio.random() * 3))} for i in range(dias)]


def tecnicas() -> list[dict]:
    dados = [("marca_em_subdominio", 14), ("marca_no_dominio", 11), ("erro_de_digitacao", 7),
             ("subdominio_enganoso", 4), ("troca_de_caracteres", 3), ("homografo", 2)]
    return [{"tecnica": t, "nome": NOMES_TECNICAS[t], "total": n} for t, n in dados]


def deteccoes() -> list[dict]:
    return _deteccoes()


def cruzamento() -> list[dict]:
    casos = [("bradesco-cancelar.top", "sms", "antes", 74), ("x7k2.bradesco.support.entregarapida.click", "e-mail", "antes", 31),
             ("bradesco-pix-seguro.xyz", "whatsapp", "antes", 6.5), ("atualizacao-bradesco.online", "e-mail", "depois", -2),
             ("bardesco-token.top", "sms", "desconhecido", None)]
    saida = []
    for i, (dominio, canal, situacao, horas) in enumerate(casos):
        chegou = _agora() - timedelta(hours=10 * i + 2)
        det = analisar(dominio, [BRADESCO])
        r = calcular(det[0].tecnicas) if det else None
        visto = chegou - timedelta(hours=horas) if horas is not None else None
        saida.append({"dominio": dominio, "canal": canal, "chegou_em": chegou.isoformat(),
                      "visto_nos_ct_em": visto.isoformat() if visto else None, "situacao": situacao,
                      "antecedencia": duracao(timedelta(hours=abs(horas))) if horas is not None else "—",
                      "nota": r.nota if r else None, "nivel": r.nivel if r else None})
    return saida


def recebidos() -> list[dict]:
    itens = [("sms", "11987654321", None, 90, "critico"), ("e-mail", "Bradesco Cobranca <cobranca@bradesco-faturas.top>",
              "Fatura do cartao Bradesco disponivel", 99, "critico"), ("whatsapp", "+55 11 91234-5678", None, 71, "alto"),
             ("e-mail", "Bradesco <comunicados@bradesco.com.br>", "Novidades no aplicativo", 0, "baixo"),
             ("sms", "27888", None, 0, "baixo")]
    return [{"canal": c, "de": de, "assunto": a, "quando": (_agora() - timedelta(minutes=19 + i * 67)).isoformat(),
             "nota": n, "nivel": nv} for i, (c, de, a, n, nv) in enumerate(itens)]
