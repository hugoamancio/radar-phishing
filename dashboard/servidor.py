"""Servidor do dashboard (FastAPI).

Seguranca, por ser um projeto de seguranca:
- escuta so em 127.0.0.1: nenhum outro aparelho da rede abre o dashboard;
- somente leitura: nenhuma rota grava no banco;
- a pesquisa NUNCA acessa o endereco pesquisado, so consulta o banco;
- Content-Security-Policy sem script inline e sem nada de fora: mesmo que um
  dominio malicioso tenha um nome estranho, ele vira texto, nunca codigo
  (o JavaScript tambem so usa textContent, nunca innerHTML com dados).
"""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from dashboard import dados, demo
from monitor import banco
from monitor.detector import NOMES_TECNICAS
from monitor.pesquisa import CONHECIDO, CONHECIDO_PAI, pesquisar

ESTATICOS = Path(__file__).parent / "estatico"

CABECALHOS = {
    "Content-Security-Policy": "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; "
                               "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
}


def criar_app(modo_demo: bool = False) -> FastAPI:
    app = FastAPI(title="Radar Phishing", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.demo = modo_demo
    app.mount("/estatico", StaticFiles(directory=ESTATICOS), name="estatico")

    @app.middleware("http")
    async def seguranca(request: Request, call_next):
        resposta = await call_next(request)
        resposta.headers.update(CABECALHOS)
        if request.url.path.startswith("/api/"):
            resposta.headers["Cache-Control"] = "no-store"
        return resposta

    def consultar(nome: str, *args):
        """Chama a funcao de mesmo nome em dados (banco) ou demo (ficticio)."""
        if app.state.demo:
            return getattr(demo, nome)(*args)
        conn = banco.conectar()
        try:
            return getattr(dados, nome)(conn, *args)
        finally:
            conn.close()

    @app.get("/")
    def pagina():
        return FileResponse(ESTATICOS / "index.html")

    @app.get("/api/estado")
    def estado():
        return {"demo": app.state.demo}

    @app.get("/api/resumo")
    def resumo():
        return consultar("resumo")

    @app.get("/api/serie")
    def serie(dias: int = Query(14, ge=7, le=60)):
        return consultar("serie", dias)

    @app.get("/api/tecnicas")
    def tecnicas():
        return consultar("tecnicas")

    @app.get("/api/deteccoes")
    def deteccoes():
        return consultar("deteccoes")

    @app.get("/api/cruzamento")
    def cruzamento():
        return consultar("cruzamento")

    @app.get("/api/recebidos")
    def recebidos():
        return consultar("recebidos")

    @app.get("/api/pesquisa")
    def pesquisa(q: str = Query(..., min_length=1, max_length=500)):
        conn = None
        try:
            if not app.state.demo:
                conn = banco.conectar()
            marcas = banco.carregar_marcas(conn) if conn else [demo.BRADESCO]
            r = pesquisar(q, marcas, conn)
        finally:
            if conn:
                conn.close()
        risco = r.risco
        saida = {"entrada": q, "dominio": r.dominio, "tipo": r.tipo, "marca_oficial": r.marca_oficial,
                 "nota": risco.nota if risco else None, "nivel": risco.nivel if risco else None,
                 "motivos": [], "registro": None}
        if r.tipo in (CONHECIDO, CONHECIDO_PAI):
            reg = asdict(r.registro)
            saida["registro"] = {k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in reg.items()}
            saida["motivos"] = r.registro.motivos
        elif r.deteccoes:
            saida["motivos"] = r.deteccoes[0].motivos
            saida["trecho"] = r.deteccoes[0].trecho
            saida["marca"] = r.deteccoes[0].marca.nome
        saida["motivos"] = [{**m, "nome": NOMES_TECNICAS.get(m["tecnica"], m["tecnica"])} for m in saida["motivos"]]
        return saida

    @app.exception_handler(Exception)
    async def erro(request: Request, exc: Exception):
        # Sem detalhes internos na resposta: so o suficiente para a tela avisar.
        return JSONResponse({"erro": "banco indisponível"}, status_code=503)

    return app
