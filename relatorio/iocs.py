"""Exporta os indicadores (IOCs) em CSV e em STIX 2.1.

STIX e o formato padrao (OASIS) para trocar inteligencia de ameacas entre
equipes e ferramentas: um SIEM, um MISP ou o time de seguranca de um banco
importa o arquivo direto. Cada dominio suspeito vira um "indicator" com o
padrao [domain-name:value = '...'].

Os ids sao deterministicos (uuid5 do dominio): exportar de novo nao cria
indicadores "novos" para o mesmo dominio, so os atualiza.
"""

from __future__ import annotations

import csv
import io
import json
import uuid
from datetime import datetime, timezone

from alertas.mensagens import desarmar
from monitor.detector import NOMES_TECNICAS
from relatorio.campanhas import Campanha
from relatorio.coleta import Dados

ESPACO = uuid.UUID("6f2b0c1e-9a57-4d1e-8f43-52a1d1b0a7c3")      # fixo: mesmos ids a cada exportacao
IDENTIDADE = f"identity--{uuid.uuid5(ESPACO, 'radar-phishing')}"
NIVEIS_EXPORTADOS = ("medio", "alto", "critico")


def _iso(m: datetime) -> str:
    return m.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _campanha_de(dados: Dados) -> dict[str, Campanha]:
    return {h: c for c in dados.campanhas if c.e_campanha for h in c.hosts}


def linhas(dados: Dados) -> list[dict]:
    campanha = _campanha_de(dados)
    vistos: dict[str, dict] = {}
    for d in dados.deteccoes:
        if d.nivel not in NIVEIS_EXPORTADOS or d.dominio in vistos:
            continue
        vistos[d.dominio] = {
            "dominio": d.dominio, "desarmado": desarmar(d.dominio), "nota": d.nota, "nivel": d.nivel,
            "tecnica": NOMES_TECNICAS.get(d.tecnicas[0], d.tecnicas[0]) if d.tecnicas else "",
            "campanha": campanha[d.dominio].chave if d.dominio in campanha else "",
            "visto_em": _iso(d.quando), "emissor": d.emissor or "",
        }
    return sorted(vistos.values(), key=lambda l: (-l["nota"], l["dominio"]))


def csv_texto(dados: Dados) -> str:
    saida = io.StringIO()
    campos = ["dominio", "desarmado", "nota", "nivel", "tecnica", "campanha", "visto_em", "emissor"]
    escritor = csv.DictWriter(saida, fieldnames=campos, lineterminator="\n")
    escritor.writeheader()
    escritor.writerows(linhas(dados))
    return saida.getvalue()


def stix(dados: Dados) -> dict:
    agora = _iso(dados.fim)
    objetos: list[dict] = [{
        "type": "identity", "spec_version": "2.1", "id": IDENTIDADE, "created": agora, "modified": agora,
        "name": "Radar Phishing", "identity_class": "system",
        "description": "Detector de phishing contra clientes de bancos (CT logs, e-mail, SMS e WhatsApp).",
    }]
    for l in linhas(dados):
        descricao = f"Imita {', '.join(dados.marcas)}. Técnica principal: {l['tecnica']}. Nota de risco {l['nota']}."
        if l["campanha"]:
            descricao += f" Campanha (molde): {l['campanha']}."
        objetos.append({
            "type": "indicator", "spec_version": "2.1",
            "id": f"indicator--{uuid.uuid5(ESPACO, l['dominio'])}",
            "created_by_ref": IDENTIDADE, "created": l["visto_em"], "modified": agora,
            "name": f"Domínio de phishing: {l['desarmado']}", "description": descricao,
            "indicator_types": ["malicious-activity" if l["nivel"] in ("alto", "critico") else "anomalous-activity"],
            # O valor no padrao vai cru (e o que as ferramentas comparam); aspas simples escapadas pela regra do STIX.
            "pattern": f"[domain-name:value = '{l['dominio'].replace(chr(92), chr(92) * 2).replace(chr(39), chr(92) + chr(39))}']",
            "pattern_type": "stix", "valid_from": l["visto_em"], "confidence": l["nota"],
            "labels": ["phishing"] + ([f"campanha:{l['campanha']}"] if l["campanha"] else []),
        })
    return {"type": "bundle", "id": f"bundle--{uuid.uuid4()}", "objects": objetos}


def stix_texto(dados: Dados) -> str:
    return json.dumps(stix(dados), ensure_ascii=False, indent=2)
