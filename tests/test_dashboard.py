from pathlib import Path

import psycopg
import pytest
from fastapi.testclient import TestClient

from dashboard.servidor import criar_app
from monitor import banco

ESTATICOS = Path("dashboard/estatico")
ROTAS = ["/api/resumo", "/api/serie", "/api/tecnicas", "/api/deteccoes", "/api/cruzamento", "/api/recebidos"]


@pytest.fixture
def demo():
    return TestClient(criar_app(modo_demo=True))


def test_todas_as_rotas_respondem_no_modo_demo(demo):
    assert demo.get("/").status_code == 200
    for rota in ROTAS:
        r = demo.get(rota)
        assert r.status_code == 200, rota
        assert r.headers["cache-control"] == "no-store"
    assert demo.get("/api/estado").json() == {"demo": True}


def test_cabecalhos_de_seguranca(demo):
    h = demo.get("/").headers
    assert "script-src 'self'" in h["content-security-policy"]
    assert "unsafe-inline" not in h["content-security-policy"]
    assert h["x-frame-options"] == "DENY" and h["x-content-type-options"] == "nosniff"


def test_documentacao_automatica_desligada(demo):
    # A FastAPI publica /docs por padrao; num painel de seguranca isso so expoe a API.
    for rota in ("/docs", "/redoc", "/openapi.json"):
        assert demo.get(rota).status_code == 404


def test_pesquisa_responde_e_valida_tamanho(demo):
    r = demo.get("/api/pesquisa", params={"q": "hxxps://login.br4desco-app[.]online/conta"}).json()
    assert r["tipo"] == "suspeito_agora" and r["nivel"] in ("alto", "critico")
    assert r["motivos"][0]["nome"] == "Troca de caracteres"
    assert demo.get("/api/pesquisa", params={"q": "x" * 501}).status_code == 422
    assert demo.get("/api/pesquisa").status_code == 422


def test_javascript_nunca_injeta_html():
    # Dado do banco (nome de dominio de golpe!) so pode entrar como texto.
    codigo = (ESTATICOS / "app.js").read_text(encoding="utf-8")
    assert "innerHTML" not in codigo and "outerHTML" not in codigo and "insertAdjacentHTML" not in codigo
    assert "eval(" not in codigo


def test_pagina_sem_script_ou_estilo_inline():
    html = (ESTATICOS / "index.html").read_text(encoding="utf-8")
    assert "<script>" not in html and "style=" not in html and "<style" not in html


def test_servidor_so_escuta_no_proprio_computador():
    assert 'host="127.0.0.1"' in Path("dashboard/__main__.py").read_text(encoding="utf-8")


def test_rotas_com_dados_reais():
    try:
        banco.conectar().close()
    except psycopg.OperationalError:
        pytest.skip("PostgreSQL fora do ar")
    real = TestClient(criar_app(modo_demo=False))
    for rota in ROTAS:
        assert real.get(rota).status_code == 200, rota
    resumo = real.get("/api/resumo").json()
    assert {"suspeitos", "niveis", "monitor", "cruzamento"} <= set(resumo)
    assert len(real.get("/api/serie", params={"dias": 14}).json()) == 14
