"""Le do banco tudo o que o relatorio precisa, para um periodo."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from cruzamento.consulta import Resumo, ler as ler_cruzamento, resumir
from monitor import banco
from relatorio.campanhas import Campanha, Deteccao, agrupar


@dataclass
class Dados:
    inicio: datetime
    fim: datetime
    marcas: list[str]
    deteccoes: list[Deteccao]
    campanhas: list[Campanha]
    achados_recebidos: Counter                       # tecnica -> vezes, em e-mails e mensagens
    recebidos: dict[str, int] = field(default_factory=dict)   # canal -> quantos analisados
    recebidos_golpe: int = 0
    cruzamento: Resumo | None = None

    @property
    def por_nivel(self) -> Counter:
        return Counter(d.nivel for d in self.deteccoes)

    @property
    def por_tecnica(self) -> Counter:
        return Counter(d.tecnicas[0] for d in self.deteccoes if d.tecnicas)

    @property
    def por_tld(self) -> Counter:
        return Counter(d.dominio.rsplit(".", 1)[-1] for d in self.deteccoes)

    @property
    def por_emissor(self) -> Counter:
        return Counter(d.emissor or "desconhecido" for d in self.deteccoes)

    @property
    def por_hora(self) -> list[int]:
        horas = [0] * 24
        for d in self.deteccoes:
            horas[d.quando.astimezone().hour] += 1
        return horas


def coletar(conn, dias: int) -> Dados:
    fim = datetime.now(timezone.utc)
    inicio = fim - timedelta(days=dias)
    marcas = banco.carregar_marcas(conn)
    palavras = tuple(p for m in marcas for p in m.palavras_chave)

    deteccoes = [Deteccao(d, n or 0, nv or "baixo", list(t), e, q) for d, n, nv, t, e, q in conn.execute(
        "SELECT dominio, nota, nivel, tecnicas, emissor, detectado_em FROM vw_dominios_suspeitos "
        "WHERE detectado_em >= %s ORDER BY detectado_em", (inicio,)).fetchall()]

    achados = Counter()
    recebidos: Counter = Counter()
    golpe = 0
    for canal, lista, nivel in conn.execute(
        """
        SELECT 'e-mail', e.achados, r.nivel FROM email e LEFT JOIN vw_risco_atual r ON r.email_id = e.id
        WHERE e.analisado_em >= %s
        UNION ALL
        SELECT ms.canal, ms.achados, r.nivel FROM mensagem ms LEFT JOIN vw_risco_atual r ON r.mensagem_id = ms.id
        WHERE ms.analisada_em >= %s
        """, (inicio, inicio)).fetchall():
        recebidos[canal] += 1
        golpe += nivel in ("alto", "critico")
        achados.update(a["tecnica"] for a in lista)

    cruz = [c for c in ler_cruzamento(conn, 10_000) if c.chegou_em >= inicio]
    return Dados(inicio, fim, [m.nome for m in marcas], deteccoes, agrupar(deteccoes, palavras),
                 achados, dict(recebidos), golpe, resumir(cruz))
