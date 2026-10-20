"""SPF, DKIM e DMARC: o remetente e quem diz ser?

    SPF    o servidor que entregou o e-mail tem permissao do dominio para enviar?
    DKIM   a assinatura digital do e-mail confere com a chave publicada pelo dominio?
    DMARC  o dominio que aparece no "De:" e o mesmo que passou no SPF ou no DKIM
           (alinhamento)? E o que o dono do dominio pede para fazer quando falha?

De onde vem cada resposta:

- SPF: so o servidor que recebeu o e-mail sabe com certeza qual IP entregou a
  mensagem, entao o resultado vem do cabecalho Authentication-Results que ele
  escreveu. Usamos SOMENTE o primeiro desses cabecalhos (o mais recente, do
  servidor de recebimento): os de baixo podem ter sido forjados pelo golpista.
- DKIM: verificado aqui mesmo com dkimpy, que busca a chave publica no DNS.
  Sem rede, cai para o que o servidor de recebimento registrou.
- DMARC: usa o resultado do servidor de recebimento; se nao houver, calcula o
  alinhamento aqui e consulta a politica publicada em _dmarc.<dominio>.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from analisador.achados import ALTA, BAIXA, MEDIA, Achado
from analisador.leitura import Mensagem
from monitor.normalizacao import dominio_organizacional  # noqa: F401  (usado aqui e por quem importa daqui)

RESULTADOS_OK = {"pass"}
RESULTADOS_FALHA = {"fail", "softfail", "permerror"}


@dataclass
class Verificacao:
    resultado: str          # pass, fail, softfail, neutral, none, temperror, permerror
    dominio: str | None     # dominio avaliado (mailfrom do SPF, d= do DKIM, From do DMARC)
    fonte: str              # "servidor de recebimento", "verificação própria", "ausente"
    politica: str | None = None   # so DMARC: none, quarantine, reject


@dataclass
class Autenticacao:
    spf: Verificacao
    dkim: Verificacao
    dmarc: Verificacao


def _primeiro_auth_results(msg: Mensagem) -> str:
    valores = msg.cabecalhos.get_all("Authentication-Results") or [] if msg.cabecalhos else []
    return " ".join(str(valores[0]).split()) if valores else ""


def _ler_metodo(ar: str, metodo: str) -> tuple[str | None, str | None]:
    """Resultado e dominio de um metodo dentro do Authentication-Results."""
    achado = re.search(rf"\b{metodo}=([a-z]+)([^;]*)", ar, re.IGNORECASE)
    if not achado:
        return None, None
    resultado, resto = achado.group(1).lower(), achado.group(2)
    chave = {"spf": r"smtp\.mailfrom=(?:[^@\s;]*@)?([^\s;]+)",
             "dkim": r"header\.(?:d|i)=@?([^\s;]+)",
             "dmarc": r"header\.from=([^\s;]+)"}[metodo]
    dom = re.search(chave, resto, re.IGNORECASE)
    return resultado, (dom.group(1).lower().strip(".") if dom else None)


def _verificar_dkim(msg: Mensagem, dnsfunc=None) -> Verificacao | None:
    """``dnsfunc`` troca a consulta de DNS da chave publica (usado nos testes)."""
    if not msg.cabecalhos or not msg.cabecalhos.get("DKIM-Signature"):
        return Verificacao("none", None, "ausente")
    assinatura = str(msg.cabecalhos["DKIM-Signature"])
    d = re.search(r"\bd=([^;\s]+)", assinatura)
    dominio = d.group(1).lower() if d else None
    try:
        import dkim
        extra = {"dnsfunc": dnsfunc} if dnsfunc else {}
        valido = dkim.verify(msg.bruto, timeout=5, **extra)
    except Exception:
        return None  # sem rede ou erro de DNS: deixa o servidor de recebimento responder
    return Verificacao("pass" if valido else "fail", dominio, "verificação própria")


def _politica_dmarc(dominio: str) -> str | None:
    try:
        import dns.resolver
        respostas = dns.resolver.resolve(f"_dmarc.{dominio}", "TXT", lifetime=4)
    except Exception:
        return None
    for r in respostas:
        texto = b"".join(r.strings).decode("ascii", "replace")
        if texto.lower().startswith("v=dmarc1"):
            p = re.search(r"\bp=(none|quarantine|reject)", texto, re.IGNORECASE)
            return p.group(1).lower() if p else "none"
    return None


def verificar(msg: Mensagem,
              politica_dmarc: Callable[[str], str | None] = _politica_dmarc,
              verificar_dkim: Callable[[Mensagem], Verificacao | None] = _verificar_dkim) -> Autenticacao:
    """As funcoes de rede entram como parametro para os testes rodarem offline."""
    ar = _primeiro_auth_results(msg)
    dominio_from = msg.dominio_remetente

    spf_res, spf_dom = _ler_metodo(ar, "spf")
    spf = Verificacao(spf_res, spf_dom, "servidor de recebimento") if spf_res \
        else Verificacao("none", None, "ausente")

    dkim_ar, dkim_dom_ar = _ler_metodo(ar, "dkim")
    dkim = verificar_dkim(msg)
    if dkim is None or (dkim.fonte == "ausente" and dkim_ar):
        dkim = Verificacao(dkim_ar or "none", dkim_dom_ar, "servidor de recebimento" if dkim_ar else "ausente")

    org_from = dominio_organizacional(dominio_from) if dominio_from else ""
    politica = politica_dmarc(org_from) if org_from else None

    dmarc_res, _ = _ler_metodo(ar, "dmarc")
    if dmarc_res:
        dmarc = Verificacao(dmarc_res, dominio_from, "servidor de recebimento", politica)
    elif politica is None:
        dmarc = Verificacao("none", dominio_from, "ausente")
    else:
        alinhado = any(
            v.resultado == "pass" and v.dominio and dominio_organizacional(v.dominio) == org_from
            for v in (spf, dkim)
        )
        dmarc = Verificacao("pass" if alinhado else "fail", dominio_from, "verificação própria", politica)

    return Autenticacao(spf, dkim, dmarc)


def achados(aut: Autenticacao) -> list[Achado]:
    """Traduz as verificacoes em sinais. Passar em tudo nao gera achado nenhum."""
    lista: list[Achado] = []
    if aut.dmarc.resultado in RESULTADOS_FALHA:
        detalhe = f'o domínio do "De:" ({aut.dmarc.dominio}) não confere com quem enviou'
        if aut.dmarc.politica in ("reject", "quarantine"):
            detalhe += f'; o dono do domínio pede para {"recusar" if aut.dmarc.politica == "reject" else "isolar"} e-mails assim'
        lista.append(Achado("autenticacao", "dmarc_falhou", "DMARC falhou", detalhe, ALTA))
    if aut.spf.resultado in RESULTADOS_FALHA:
        lista.append(Achado("autenticacao", "spf_falhou", "SPF falhou",
                            f"o servidor que entregou não tem permissão de {aut.spf.dominio or 'o domínio'} para enviar",
                            MEDIA))
    if aut.dkim.resultado in RESULTADOS_FALHA:
        lista.append(Achado("autenticacao", "dkim_falhou", "DKIM falhou",
                            "a assinatura digital não confere: o e-mail foi alterado ou forjado", MEDIA))
    if aut.dkim.resultado == "none" and aut.spf.resultado == "none" and aut.dmarc.resultado == "none":
        lista.append(Achado("autenticacao", "sem_autenticacao", "Sem nenhuma autenticação",
                            "não há SPF, DKIM nem DMARC para confirmar o remetente", BAIXA))
    return lista
