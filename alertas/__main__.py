"""Alertas no Telegram e no Discord.

    python -m alertas              fica rodando: confere a cada 30 s e avisa o que for novo
    python -m alertas uma-vez      confere uma vez e sai
    python -m alertas simular      mostra o que seria enviado agora, sem enviar nem registrar
    python -m alertas teste        manda um alerta de teste (ficticio) para os canais do .env

Canais e regras ficam no arquivo .env (veja .env.example). Sem canal
configurado, tudo roda em modo simulacao.
"""

from __future__ import annotations

import argparse
import time
from datetime import datetime, timezone

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from alertas import canais, config, fila
from alertas.mensagens import Alerta
from monitor import banco
from monitor.cores import COR_ALERTA, COR_BORDA, COR_DESTAQUE, COR_OK, COR_ROTULO
from risco.visual import COR_NIVEL

console = Console()
INTERVALO_S = 30


def mostrar(a: Alerta, canal: str, resultado: str) -> None:
    cor = COR_NIVEL[a.nivel]
    rodape = Text(f"\n{canal} · {resultado}", style=COR_OK if resultado in ("enviado", "simulado") else COR_ALERTA)
    console.print(Panel(Text(a.texto_simples(), style="white") + rodape, box=box.ROUNDED, border_style=cor,
                        padding=(0, 2)))


def ciclo(conn, cfg: config.Config, simular: bool = False) -> int:
    """Uma passada: envia o que estiver pendente em cada canal. Devolve quantos saíram."""
    total = 0
    for canal in cfg.canais:
        disponivel = cfg.limite_por_hora - fila.enviados_na_ultima_hora(conn, canal)
        pendentes = fila.pendentes(conn, cfg, canal)
        if pendentes and disponivel <= 0:
            console.print(Text(f"{canal}: limite de {cfg.limite_por_hora}/hora atingido; "
                               f"{len(pendentes)} alertas esperam a próxima hora.", style=COR_ROTULO))
            continue
        for a in pendentes[:max(disponivel, 0)]:
            if simular:
                mostrar(a, canal, "simulado (não enviado)")
                continue
            try:
                erro = canais.enviar(a, canal, cfg)
            except canais.LimiteDoCanal:
                console.print(Text(f"{canal} pediu para esperar; tento de novo no próximo ciclo.", style=COR_ROTULO))
                break
            fila.registrar(conn, a, canal, erro)
            mostrar(a, canal, f"falhou: {erro}" if erro else ("simulado" if canal == "simulacao" else "enviado"))
            total += erro is None
    return total


def teste(cfg: config.Config) -> None:
    a = Alerta("dominio", 0, "bradesco-teste-radar[.]xyz", 82, "alto", datetime.now(timezone.utc),
               [("Imita", "Bradesco"), ("Certificado", "Let's Encrypt")],
               ["Marca só no subdomínio", "TLD suspeito"])
    a.titulo += "  (ALERTA DE TESTE, NÃO É GOLPE REAL)"
    for canal in cfg.canais:
        erro = canais.enviar(a, canal, cfg)
        mostrar(a, canal, f"falhou: {erro}" if erro else ("simulado" if canal == "simulacao" else "enviado"))


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m alertas", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("comando", nargs="?", default="rodar", choices=("rodar", "uma-vez", "simular", "teste"))
    args = parser.parse_args()
    cfg = config.carregar()

    canais_txt = ", ".join(cfg.canais)
    console.print(Text.assemble(("Radar Phishing", "bold white"), ("  ·  ", COR_BORDA), ("Alertas", COR_DESTAQUE),
                                (f"   canais: {canais_txt}  ·  nível mínimo: {cfg.nivel_minimo}  ·  "
                                 f"até {cfg.limite_por_hora}/hora", COR_ROTULO)))
    if cfg.canais == ["simulacao"]:
        console.print(Text("Nenhum canal no .env: modo simulação, nada sai do computador. Veja .env.example.",
                           style=COR_ROTULO))

    if args.comando == "teste":
        teste(cfg)
        return
    conn = banco.conectar()
    if args.comando in ("uma-vez", "simular"):
        n = ciclo(conn, cfg, simular=args.comando == "simular")
        if args.comando == "uma-vez":
            console.print(Text(f"{n} alerta(s) enviados.", style=COR_ROTULO))
        return
    try:
        while True:
            ciclo(conn, cfg)
            time.sleep(INTERVALO_S)
    except KeyboardInterrupt:
        console.print(Text("Alertas encerrados.", style=COR_ROTULO))


if __name__ == "__main__":
    main()
