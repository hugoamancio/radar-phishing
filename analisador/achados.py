"""Formato comum dos sinais encontrados por todas as partes do analisador."""

from __future__ import annotations

from dataclasses import asdict, dataclass

ALTA, MEDIA, BAIXA = "alta", "media", "baixa"
ORDEM_GRAVIDADE = {ALTA: 0, MEDIA: 1, BAIXA: 2}


@dataclass(frozen=True)
class Achado:
    categoria: str      # remetente, autenticacao, links, linguagem, anexos
    tecnica: str        # identificador estavel, usado pelo motor de risco (etapa 3)
    titulo: str         # frase curta para a tela
    detalhe: str        # evidencia concreta: o trecho, o dominio, o resultado
    gravidade: str      # alta, media, baixa

    def como_dict(self) -> dict:
        return asdict(self)
