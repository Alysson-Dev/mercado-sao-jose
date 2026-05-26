"""
main_mercado.py
===============
API FastAPI do Mercado São José.
Responsabilidade: Expor endpoints REST para o dashboard e para integrações futuras.

Endpoints:
- POST /perguntar  : Recebe pergunta em PT-BR, retorna SQL + resposta via IA
- GET  /produtos   : Lista todos os produtos (para app do cliente em Kotlin)
- GET  /health     : Healthcheck da API e do banco

Porta: 8003
"""

import logging
from typing import Any, Dict

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from core_ia_mercado import processar_pergunta, listar_produtos, guardrail_entrada

# ---------------------------------------------------------------------------
# Configuração de Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger("mercado_api")

# ---------------------------------------------------------------------------
# Inicialização do FastAPI
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Mercado São José - API de Inteligência",
    description="API para consultas em linguagem natural (NL2SQL) e gestão de produtos.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS liberado para desenvolvimento local (Streamlit roda em porta diferente)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Schemas Pydantic
# ---------------------------------------------------------------------------
class PerguntaRequest(BaseModel):
    pergunta: str = Field(
        ...,
        min_length=3,
        max_length=500,
        description="Pergunta em português sobre o supermercado",
        examples=["Qual produto vendeu mais hoje?"],
    )

class PerguntaResponse(BaseModel):
    sucesso: bool
    sql_gerado: str | None
    dados: Any | None
    mensagem: str
    tipo_resposta: str
    bloqueado_por_guardrail: bool = False

class Produto(BaseModel):
    id: int
    nome_produto: str
    categoria: str
    preco_venda: float
    estoque_actual: int
    estoque_minimo: int

class HealthResponse(BaseModel):
    status: str
    api: str
    banco: str
    ia: str

# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/", tags=["Root"])
def root():
    """Mensagem de boas-vindas da API."""
    return {
        "mensagem": "Bem-vindo à API do Mercado São José!",
        "docs": "/docs",
        "endpoints": {
            "perguntar": "POST /perguntar",
            "produtos": "GET /produtos",
            "health": "GET /health",
        },
    }


@app.post("/perguntar", response_model=PerguntaResponse, tags=["IA - NL2SQL"])
def perguntar(request: PerguntaRequest):
    """
    Recebe uma pergunta em português, processa via IA (Llama 3 + Ollama)
    e retorna o SQL gerado + resposta tratada do banco analytics.
    """
    logger.info(f"[API] Pergunta recebida: '{request.pergunta}'")

    # Chama o motor de IA (já inclui guardrails de entrada e saída)
    resultado = processar_pergunta(request.pergunta)

    # Se foi bloqueado pelo guardrail, ainda retornamos 200 com flag
    if resultado.get("bloqueado_por_guardrail"):
        logger.warning(f"[API] Pergunta bloqueada: '{request.pergunta}'")
        return PerguntaResponse(**resultado)

    if not resultado["sucesso"]:
        logger.error(f"[API] Erro no processamento: {resultado['mensagem']}")
        # Retornamos 200 mas com sucesso=False para o front tratar
        return PerguntaResponse(**resultado)

    logger.info(f"[API] Resposta enviada com sucesso.")
    return PerguntaResponse(**resultado)


@app.get("/produtos", response_model=list[Produto], tags=["Produtos"])
def get_produtos():
    """
    Retorna a lista completa de produtos do supermercado.
    Usado pelo aplicativo do cliente (Kotlin) e pelo dashboard.
    """
    logger.info("[API] Listando produtos")

    sucesso, resultado = listar_produtos()

    if not sucesso:
        logger.error(f"[API] Erro ao listar produtos: {resultado}")
        raise HTTPException(status_code=500, detail=str(resultado))

    return resultado


@app.get("/health", response_model=HealthResponse, tags=["Health"])
def health_check():
    """
    Verifica o status da API, do banco de dados e da IA.
    """
    status_banco = "ok"
    status_ia = "ok"

    # Testar banco
    try:
        sucesso, _ = listar_produtos()
        if not sucesso:
            status_banco = "erro"
    except Exception as e:
        status_banco = f"erro: {str(e)}"

    # Testar IA (Ollama)
    try:
        from core_ia_mercado import llm
        _ = llm.invoke("SELECT 1")
    except Exception as e:
        status_ia = f"erro: {str(e)}"

    return HealthResponse(
        status="healthy" if status_banco == "ok" and status_ia == "ok" else "degraded",
        api="ok",
        banco=status_banco,
        ia=status_ia,
    )


# ---------------------------------------------------------------------------
# Execução local (para desenvolvimento)
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main_mercado:app", host="0.0.0.0", port=8003, reload=True)
