"""O que ainda precisa ser avisado, e o registro do que ja foi.

Entra na fila: dominio, e-mail ou mensagem com risco acima do nivel minimo,
que apareceu dentro da janela (ultimas N horas) e ainda nao foi avisado
naquele canal. A janela existe para a primeira execucao nao despejar o
historico inteiro de uma vez.
"""

from __future__ import annotations

from alertas.config import Config
from alertas.mensagens import NOMES_CANAL, Alerta, desarmar
from cruzamento.consulta import duracao
from monitor.detector import NOMES_TECNICAS
from risco.modelo import PESOS


def _nomes(motivos: list[dict]) -> list[str]:
    return [PESOS.get(m["tecnica"], (0, "", NOMES_TECNICAS.get(m["tecnica"], m["tecnica"])))[2]
            for m in motivos if m.get("pontos", 1) > 0][:4]


def pendentes(conn, cfg: Config, canal: str) -> list[Alerta]:
    niveis = list(cfg.niveis_alertados)
    janela = f"{cfg.janela_horas} hours"
    fila: list[Alerta] = []

    for dominio_id, nome, marca, nota, nivel, motivos, quando, emissor in conn.execute(
        """
        SELECT d.id, d.nome, m.nome, r.nota, r.nivel, r.motivos, dd.detectado_em,
               (SELECT emissor FROM certificado c WHERE c.dominio_id = d.id ORDER BY visto_em DESC LIMIT 1)
        FROM deteccao_dominio dd
        JOIN dominio d ON d.id = dd.dominio_id
        JOIN marca m ON m.id = dd.marca_id
        JOIN vw_risco_atual r ON r.dominio_id = d.id
        WHERE r.nivel = ANY(%s) AND dd.detectado_em > now() - %s::interval
          AND NOT EXISTS (SELECT 1 FROM alerta a WHERE a.tipo = 'dominio' AND a.alvo_id = d.id AND a.canal = %s)
        ORDER BY r.nota DESC, dd.detectado_em
        """, (niveis, janela, canal)).fetchall():
        fila.append(Alerta("dominio", dominio_id, desarmar(nome), nota, nivel, quando,
                           [("Imita", marca), ("Certificado", emissor or "—")], _nomes(motivos)))

    for email_id, remetente, assunto, nota, nivel, motivos, quando in conn.execute(
        """
        SELECT e.id, e.remetente, e.assunto, r.nota, r.nivel, r.motivos, e.analisado_em
        FROM email e JOIN vw_risco_atual r ON r.email_id = e.id
        WHERE r.nivel = ANY(%s) AND e.analisado_em > now() - %s::interval
          AND NOT EXISTS (SELECT 1 FROM alerta a WHERE a.tipo = 'email' AND a.alvo_id = e.id AND a.canal = %s)
        ORDER BY r.nota DESC
        """, (niveis, janela, canal)).fetchall():
        fila.append(Alerta("email", email_id, desarmar(remetente or "remetente desconhecido"), nota, nivel, quando,
                           [("Assunto", assunto or "—")] + _links(conn, "link_email", "email_id", email_id),
                           _nomes(motivos)))

    for mensagem_id, canal_msg, remetente, nota, nivel, motivos, quando in conn.execute(
        """
        SELECT ms.id, ms.canal, ms.remetente, r.nota, r.nivel, r.motivos, ms.analisada_em
        FROM mensagem ms JOIN vw_risco_atual r ON r.mensagem_id = ms.id
        WHERE r.nivel = ANY(%s) AND ms.analisada_em > now() - %s::interval
          AND NOT EXISTS (SELECT 1 FROM alerta a WHERE a.tipo = 'mensagem' AND a.alvo_id = ms.id AND a.canal = %s)
        ORDER BY r.nota DESC
        """, (niveis, janela, canal)).fetchall():
        titulo = f"{NOMES_CANAL.get(canal_msg, canal_msg)} de {remetente}" if remetente else NOMES_CANAL.get(canal_msg, canal_msg)
        fila.append(Alerta("mensagem", mensagem_id, titulo, nota, nivel, quando,
                           _links(conn, "link_mensagem", "mensagem_id", mensagem_id), _nomes(motivos)))
    return fila


def _links(conn, tabela: str, coluna: str, alvo_id: int) -> list[tuple[str, str]]:
    """Links suspeitos da mensagem, desarmados, e se o monitor ja os conhecia (cruzamento)."""
    linhas = conn.execute(
        f"SELECT DISTINCT d.nome FROM {tabela} l JOIN dominio d ON d.id = l.dominio_id "  # noqa: S608 (nomes fixos)
        f"WHERE l.{coluna} = %s AND d.marca_id IS NOT NULL", (alvo_id,)).fetchall()
    detalhes = [("Link", desarmar(nome)) for (nome,) in linhas[:3]]
    for (nome,) in linhas[:3]:
        cruz = conn.execute("SELECT situacao, antecedencia FROM vw_cruzamento WHERE dominio = %s LIMIT 1",
                            (nome,)).fetchone()
        if cruz and cruz[0] == "antes":
            detalhes.append(("Já conhecido", f"{desarmar(nome)} visto nos CT logs {duracao(cruz[1])} antes"))
    return detalhes


def enviados_na_ultima_hora(conn, canal: str) -> int:
    return conn.execute("SELECT count(*) FROM alerta WHERE canal = %s AND status = 'enviado' "
                        "AND criado_em > now() - interval '1 hour'", (canal,)).fetchone()[0]


def registrar(conn, a: Alerta, canal: str, erro: str | None) -> None:
    """Grava o resultado. Falha tambem fica registrada (e nao e reenviada sem parar)."""
    conn.execute(
        "INSERT INTO alerta (tipo, alvo_id, canal, nota, status, erro) VALUES (%s, %s, %s, %s, %s, %s) "
        "ON CONFLICT (tipo, alvo_id, canal) DO UPDATE SET status = EXCLUDED.status, erro = EXCLUDED.erro, "
        "criado_em = now()",
        (a.tipo, a.alvo_id, canal, a.nota, "falhou" if erro else "enviado", (erro or "")[:300] or None),
    )
