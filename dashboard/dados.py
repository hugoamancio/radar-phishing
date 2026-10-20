"""Consultas do dashboard. Tudo somente leitura: o dashboard nunca altera o banco.

Cada funcao devolve dados prontos para JSON (datas em ISO 8601). As mesmas
formas sao produzidas por dashboard/demo.py, com dados ficticios.
"""

from __future__ import annotations

from datetime import datetime

from cruzamento.consulta import duracao, ler as ler_cruzamento, resumir
from monitor.detector import NOMES_TECNICAS
from monitor.normalizacao import decodificar_idn
from risco.modelo import NOMES_NIVEIS

NIVEIS = ("baixo", "medio", "alto", "critico")


def _iso(m: datetime | None) -> str | None:
    return m.isoformat() if m else None


def resumo(conn) -> dict:
    total, ultimas_24h = conn.execute(
        "SELECT count(*), count(*) FILTER (WHERE detectado_em > now() - interval '24 hours') FROM deteccao_dominio"
    ).fetchone()
    niveis = dict(conn.execute(
        "SELECT nivel, count(*) FROM vw_dominios_suspeitos WHERE nivel IS NOT NULL GROUP BY nivel").fetchall())
    emails, emails_golpe = conn.execute(
        "SELECT count(*), count(*) FILTER (WHERE nivel IN ('alto', 'critico')) FROM vw_emails_analisados").fetchone()
    mensagens, mensagens_golpe = conn.execute(
        "SELECT count(*), count(*) FILTER (WHERE nivel IN ('alto', 'critico')) FROM vw_mensagens_analisadas").fetchone()
    # Batimento do monitor (sql/08): e ele, e nao o ultimo golpe achado, que diz se o monitor esta vivo.
    batimento = conn.execute("SELECT ultimo_sinal, ritmo, certificados FROM monitor_batimento WHERE id = 1").fetchone()
    r = resumir(ler_cruzamento(conn))
    return {
        "suspeitos": total, "suspeitos_24h": ultimas_24h,
        "niveis": [{"nivel": n, "nome": NOMES_NIVEIS[n], "total": niveis.get(n, 0)} for n in NIVEIS],
        "emails": emails, "emails_golpe": emails_golpe,
        "mensagens": mensagens, "mensagens_golpe": mensagens_golpe,
        "monitor": {"ultimo_sinal": _iso(batimento[0]) if batimento else None,
                    "ritmo": batimento[1] if batimento else 0,
                    "certificados": batimento[2] if batimento else 0},
        "cruzamento": {"total": r.total, "antes": r.antes, "depois": r.depois, "desconhecidos": r.desconhecidos,
                       "taxa": r.taxa_antecipada, "mediana": duracao(r.mediana), "maior": duracao(r.maior)},
    }


def serie(conn, dias: int = 14) -> list[dict]:
    """Deteccoes por dia, com zero nos dias sem nada (para a linha nao 'pular' dias)."""
    linhas = conn.execute(
        """
        SELECT dia::date, count(dd.id)
        FROM generate_series((now() AT TIME ZONE 'America/Sao_Paulo')::date - (%s - 1),
                             (now() AT TIME ZONE 'America/Sao_Paulo')::date, interval '1 day') AS dia
        LEFT JOIN deteccao_dominio dd ON (dd.detectado_em AT TIME ZONE 'America/Sao_Paulo')::date = dia::date
        GROUP BY dia ORDER BY dia
        """, (dias,)).fetchall()
    return [{"dia": d.isoformat(), "total": n} for d, n in linhas]


def tecnicas(conn) -> list[dict]:
    """Tecnica principal de cada deteccao (a primeira da lista, ja ordenada por gravidade)."""
    linhas = conn.execute(
        "SELECT tecnicas[1], count(*) FROM deteccao_dominio GROUP BY 1 ORDER BY 2 DESC").fetchall()
    return [{"tecnica": t, "nome": NOMES_TECNICAS.get(t, t), "total": n} for t, n in linhas]


def deteccoes(conn, limite: int = 40) -> list[dict]:
    linhas = conn.execute(
        "SELECT dominio, marca, tecnicas, trecho, detectado_em, emissor, nota, nivel "
        "FROM vw_dominios_suspeitos LIMIT %s", (limite,)).fetchall()
    return [{"dominio": d, "visivel": decodificar_idn(d), "marca": m, "tecnica": NOMES_TECNICAS.get(t[0], t[0]),
             "reforcos": [NOMES_TECNICAS.get(x, x) for x in t[1:] if x in ("palavra_isca", "tld_suspeito")],
             "trecho": tr, "quando": _iso(q), "emissor": e, "nota": n, "nivel": nv}
            for d, m, t, tr, q, e, n, nv in linhas]


def cruzamento(conn, limite: int = 12) -> list[dict]:
    return [{"dominio": c.dominio, "canal": c.canal, "chegou_em": _iso(c.chegou_em),
             "visto_nos_ct_em": _iso(c.visto_nos_ct_em), "situacao": c.situacao,
             "antecedencia": duracao(c.antecedencia), "nota": c.nota, "nivel": c.nivel}
            for c in ler_cruzamento(conn, limite)]


def recebidos(conn, limite: int = 10) -> list[dict]:
    """E-mails e mensagens analisados, mais recentes primeiro."""
    linhas = conn.execute(
        """
        SELECT 'e-mail', coalesce(remetente_nome || ' <' || remetente || '>', remetente), assunto,
               analisado_em, nota, nivel FROM vw_emails_analisados
        UNION ALL
        SELECT canal, remetente, NULL, analisada_em, nota, nivel FROM vw_mensagens_analisadas
        ORDER BY 4 DESC LIMIT %s
        """, (limite,)).fetchall()
    return [{"canal": c, "de": de, "assunto": a, "quando": _iso(q), "nota": n, "nivel": nv}
            for c, de, a, q, n, nv in linhas]
