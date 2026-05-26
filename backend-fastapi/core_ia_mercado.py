"""
core_ia_mercado.py
==================
Motor de IA do Mercado São José.
Responsabilidade: Receber perguntas em português, gerar SQL seguro via Ollama (Llama 3),
executar no banco ANALYTICS (read-only) e retornar respostas tratadas.

Arquitetura de Segurança:
- Banco de dados isolado: mercado_sao_jose_analytics (apenas leitura)
- Guardrail de Entrada: bloqueia comandos maliciosos e valida escopo
- Guardrail de Saída: formata respostas vazias e erros de forma amigável
"""

import re
import os
import logging
import time
from typing import Dict, Any, Tuple

from sqlalchemy import create_engine, text
from langchain_community.llms import Ollama
from langchain_community.utilities import SQLDatabase
from langchain_experimental.sql import SQLDatabaseChain

from observability_logger import IALogger, registrar_interacao

# ---------------------------------------------------------------------------
# Configuração de Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger("mercado_ia")

# ---------------------------------------------------------------------------
# Constantes de Segurança
# ---------------------------------------------------------------------------
# Lista de palavras-chave perigosas que NUNCA devem aparecer na pergunta
PALAVRAS_PROIBIDAS = [
    "drop", "delete", "truncate", "alter", "update", "insert",
    "create", "grant", "revoke", "exec", "execute", "sp_", "xp_",
    "union", "--", ";--", ";/*", "*/", "@@", "@", "char(", "nchar(",
    "varchar(", "nvarchar(", "cast(", "convert(", "script", "<script",
]

# Padrões regex para detectar injeção SQL avançada
PADROES_INJECAO = [
    re.compile(r"(\b(union|select|insert|update|delete|drop|create|alter|truncate|grant|revoke)\b.*){2,}", re.IGNORECASE),
    re.compile(r"(\-\-|\#|\/\*|\*\/)", re.IGNORECASE),
    re.compile(r"(\bwaitfor\b|\bdelay\b|\bshutdown\b|\breconfigure\b)", re.IGNORECASE),
    re.compile(r"(\bsp_\w+|\bxp_\w+)", re.IGNORECASE),
    re.compile(r"(\bchar\s*\(|\bnchar\s*\(|\bvarchar\s*\(|\bnvarchar\s*\()")
]

# Escopo permitido: termos relacionados ao supermercado
TERMOS_ESCOPO = [
    "produto", "produtos", "venda", "vendas", "estoque", "preço", "preço",
    "categoria", "quantidade", "total", "hoje", "ontem", "semana", "mês",
    "mercado", "são josé", "supermercado", "caixa", "cliente", "compra",
    "arroz", "feijão", "café", "leite", "pão", "refrigerante", "iogurte",
    "queijo", "manteiga", "macarrão", "óleo", "açúcar", "frango", "carne",
    "banana", "maçã", "tomate", "cebola", "alface", "shampoo", "sabão",
    "detergente", "papel", "higiene", "limpeza", "laticínio", "bebida",
    "hortifruti", "açougue", "padaria", "grão", "massa", "mais vendido",
    "menos vendido", "baixo", "mínimo", "máximo", "média", "soma", "total",
    "faturamento", "receita", "lucro", "ticket", "médio", "ranking", "top",
    "compare", "comparar", "diferença", "aumento", "queda", "tendência",
    "listar", "mostrar", "exibir", "quais", "qual", "quanto", "quantos",
    "onde", "quando", "por que", "como", "existe", "tem", "possui",
]

# ---------------------------------------------------------------------------
# Configuração do Banco de Dados (Analytics - Read-Only)
# ---------------------------------------------------------------------------
# URL com caracteres especiais escapados:
# Usuário: postgres | Senha: @Assis1# | Host: localhost
# @ -> %40 | # -> %23
DATABASE_URL = "postgresql://postgres:%40Assis1%23@localhost:5432/mercado_sao_jose_analytics"

# Engine SQLAlchemy com pool pequeno e timeout curto para segurança
engine = create_engine(
    DATABASE_URL,
    pool_size=2,
    max_overflow=0,
    pool_timeout=10,
    pool_recycle=300,
    connect_args={"connect_timeout": 10},
    execution_options={"isolation_level": "READ COMMITTED"},
)

# ---------------------------------------------------------------------------
# Inicialização do Modelo de IA (Ollama + Llama 3)
# ---------------------------------------------------------------------------
llm = Ollama(
    model="llama3",
    temperature=0.1,  # Baixa temperatura para respostas mais determinísticas
    num_ctx=4096,     # Contexto suficiente para schemas e perguntas
)

# Conexão LangChain com o banco (apenas para geração de SQL, não execução direta)
db = SQLDatabase(engine, include_tables=["produtos", "vendas_varejo"])

# Prompt customizado para forçar PostgreSQL e português
CUSTOM_PROMPT = """Você é um assistente de banco de dados para o Mercado São José, um supermercado.
Sua tarefa é converter perguntas em português para consultas SQL PostgreSQL válidas.

REGRAS ABSOLUTAS:
1. GERE APENAS SELECT statements. NUNCA gere INSERT, UPDATE, DELETE, DROP, ALTER, CREATE, TRUNCATE, GRANT ou REVOKE.
2. Use APENAS as tabelas: produtos e vendas_varejo.
3. O banco é PostgreSQL. Use sintaxe compatível.
4. Para datas, use CURRENT_DATE, INTERVAL, e funções como DATE(), EXTRACT().
5. Nunca use funções perigosas ou não-padrão.
6. Se a pergunta não puder ser respondida com SELECT nas tabelas disponíveis, retorne: "SELECT 'Não foi possível gerar uma consulta para esta pergunta.' AS resposta;"

Schema das tabelas:
- produtos(id, nome_produto, categoria, preco_venda, estoque_actual, estoque_minimo, data_cadastro)
- vendas_varejo(id, produto_id, quantidade, valor_total, data_venda)

Pergunta do usuário: {input}

SQL:"""

# ---------------------------------------------------------------------------
# GUARDRAIL DE ENTRADA (Input Shield)
# ---------------------------------------------------------------------------
def guardrail_entrada(pergunta: str) -> Tuple[bool, str]:
    """
    Valida a pergunta do usuário antes de enviar para a IA.
    Retorna: (permitido: bool, motivo_bloqueio: str)
    """
    if not pergunta or not isinstance(pergunta, str):
        return False, "Pergunta vazia ou inválida."

    pergunta_lower = pergunta.lower().strip()

    # 1. Verificar comprimento
    if len(pergunta) > 500:
        return False, "Pergunta muito longa. Limite de 500 caracteres."

    # 2. Verificar palavras proibidas
    for palavra in PALAVRAS_PROIBIDAS:
        if palavra in pergunta_lower:
            logger.warning(f"[GUARDRAIL] Palavra proibida detectada: '{palavra}'")
            return False, f"Termo bloqueado por segurança: '{palavra}'. Pergunte apenas sobre dados do supermercado."

    # 3. Verificar padrões de injeção SQL
    for padrao in PADROES_INJECAO:
        if padrao.search(pergunta):
            logger.warning(f"[GUARDRAIL] Padrão de injeção detectado: '{padrao.pattern}'")
            return False, "Padrão suspeito detectado na pergunta. Use apenas linguagem natural."

    # 4. Verificar escopo (deve conter pelo menos um termo relacionado ao mercado)
    # Permitir perguntas genéricas de listagem também
    termos_encontrados = [t for t in TERMOS_ESCOPO if t in pergunta_lower]
    if not termos_encontrados and not any(w in pergunta_lower for w in ["listar", "mostrar", "exibir", "todos", "todas"]):
        logger.warning(f"[GUARDRAIL] Pergunta fora de escopo: '{pergunta}'")
        return False, "Pergunta fora do escopo do supermercado. Faça perguntas sobre produtos, vendas ou estoque."

    logger.info(f"[GUARDRAIL] Pergunta aprovada: '{pergunta}'")
    return True, ""


# ---------------------------------------------------------------------------
# EXECUÇÃO SEGURA DE SQL (Read-Only)
# ---------------------------------------------------------------------------
def executar_sql_seguro(sql_query: str) -> Tuple[bool, Any]:
    """
    Executa a consulta SQL no banco analytics com verificações de segurança.
    Retorna: (sucesso: bool, resultado: Any)
    """
    # Verificação final: garantir que é apenas SELECT
    sql_limpo = sql_query.strip().lower()

    # Remover comentários para análise
    sql_sem_comentarios = re.sub(r"--.*", "", sql_limpo)
    sql_sem_comentarios = re.sub(r"/\*.*?\*/", "", sql_sem_comentarios, flags=re.DOTALL)
    sql_sem_comentarios = sql_sem_comentarios.strip()

    # Verificar se começa com SELECT
    if not sql_sem_comentarios.startswith("select"):
        logger.error(f"[SQL BLOCKED] Consulta não é SELECT: {sql_query}")
        return False, "Erro de segurança: apenas consultas de leitura (SELECT) são permitidas."

    # Verificar comandos proibidos dentro da query
    comandos_proibidos = ["insert", "update", "delete", "drop", "alter", "create", "truncate", "grant", "revoke", "exec"]
    for cmd in comandos_proibidos:
        if re.search(rf"\b{cmd}\b", sql_sem_comentarios):
            logger.error(f"[SQL BLOCKED] Comando proibido detectado: {cmd}")
            return False, f"Erro de segurança: comando '{cmd}' não é permitido."

    try:
        with engine.connect() as conn:
            result = conn.execute(text(sql_query))
            rows = result.fetchall()
            # Converter para lista de dicionários
            colunas = result.keys()
            dados = [dict(zip(colunas, row)) for row in rows]
            logger.info(f"[SQL EXEC] Query executada com sucesso. Linhas retornadas: {len(dados)}")
            return True, dados
    except Exception as e:
        logger.error(f"[SQL ERROR] {e}")
        return False, f"Erro ao executar consulta: {str(e)}"


# ---------------------------------------------------------------------------
# GERAÇÃO DE SQL VIA IA (LangChain + Ollama)
# ---------------------------------------------------------------------------
def gerar_sql(pergunta: str) -> Tuple[bool, str, str]:
    """
    Usa o modelo Llama 3 via Ollama para gerar SQL a partir da pergunta.
    Retorna: (sucesso: bool, sql_gerado: str, erro: str)
    """
    try:
        prompt = CUSTOM_PROMPT.format(input=pergunta)
        resposta = llm.invoke(prompt)

        # Extrair apenas a parte SQL da resposta
        sql = resposta.strip()

        # Se o modelo retornou algo com ```sql ... ```, extrair
        if "```sql" in sql:
            sql = sql.split("```sql")[1].split("```")[0].strip()
        elif "```" in sql:
            sql = sql.split("```")[1].split("```")[0].strip()

        # Limpar a query
        sql = sql.replace("\n", " ").strip()

        # Remover ponto e vírgula no final (pode causar problemas com text())
        if sql.endswith(";"):
            sql = sql[:-1].strip()

        logger.info(f"[IA] SQL gerado: {sql}")
        return True, sql, ""
    except Exception as e:
        logger.error(f"[IA ERROR] {e}")
        return False, "", str(e)


# ---------------------------------------------------------------------------
# GUARDRAIL DE SAÍDA (Output Verification)
# ---------------------------------------------------------------------------
def guardrail_saida(resultado: Any, sql_query: str) -> Dict[str, Any]:
    """
    Processa o resultado da consulta e formata a resposta final.
    Trata casos de resultado vazio, erro e formatação amigável.
    """
    resposta = {
        "sucesso": True,
        "sql_gerado": sql_query,
        "dados": None,
        "mensagem": "",
        "tipo_resposta": "dados",
    }

    # Caso 1: Erro na execução
    if isinstance(resultado, str) and resultado.startswith("Erro"):
        resposta["sucesso"] = False
        resposta["tipo_resposta"] = "erro"
        resposta["mensagem"] = f"Não foi possível processar sua pergunta. {resultado}"
        return resposta

    # Caso 2: Resultado vazio
    if not resultado or (isinstance(resultado, list) and len(resultado) == 0):
        resposta["tipo_resposta"] = "vazio"
        resposta["mensagem"] = (
            "Não encontrei dados para essa pergunta no momento. "
            "Isso pode significar que não há registros no período consultado "
            "ou que os critérios de busca não retornaram resultados. "
            "Tente reformular sua pergunta ou consultar outro período."
        )
        return resposta

    # Caso 3: Dados encontrados
    resposta["dados"] = resultado
    resposta["tipo_resposta"] = "dados"

    # Gerar mensagem amigável baseada nos dados
    if isinstance(resultado, list) and len(resultado) > 0:
        if len(resultado) == 1 and len(resultado[0]) == 1:
            # Resposta única (ex: "Qual o total de vendas?")
            chave = list(resultado[0].keys())[0]
            valor = resultado[0][chave]
            resposta["mensagem"] = f"O valor consultado é: **{valor}**"
        else:
            resposta["mensagem"] = f"Encontrei **{len(resultado)}** registros para sua consulta."

    return resposta


# ---------------------------------------------------------------------------
# FUNÇÃO PRINCIPAL (Orquestração)
# ---------------------------------------------------------------------------
def processar_pergunta(pergunta: str) -> Dict[str, Any]:
    """
    Pipeline completo: validação -> geração SQL -> execução -> formatação -> logging.
    """
    logger_ia = IALogger()
    logger_ia.iniciar_timer()

    # Passo 1: Guardrail de Entrada
    permitido, motivo = guardrail_entrada(pergunta)
    if not permitido:
        resposta = {
            "sucesso": False,
            "sql_gerado": None,
            "dados": None,
            "mensagem": motivo,
            "tipo_resposta": "bloqueado",
            "bloqueado_por_guardrail": True,
        }
        registrar_interacao(
            pergunta=pergunta,
            sql_gerado=None,
            sucesso=False,
            tipo_resposta="bloqueado",
            mensagem=motivo,
            bloqueado_por_guardrail=True,
            tempo_resposta_ms=logger_ia.finalizar_timer(),
        )
        return resposta

    # Passo 2: Gerar SQL via IA
    sucesso_sql, sql_query, erro_sql = gerar_sql(pergunta)
    if not sucesso_sql:
        resposta = {
            "sucesso": False,
            "sql_gerado": None,
            "dados": None,
            "mensagem": f"Erro ao gerar a consulta: {erro_sql}",
            "tipo_resposta": "erro_ia",
        }
        registrar_interacao(
            pergunta=pergunta,
            sql_gerado=None,
            sucesso=False,
            tipo_resposta="erro_ia",
            mensagem=resposta["mensagem"],
            tempo_resposta_ms=logger_ia.finalizar_timer(),
        )
        return resposta

    # Passo 3: Executar SQL de forma segura
    sucesso_exec, resultado = executar_sql_seguro(sql_query)
    if not sucesso_exec:
        resposta = {
            "sucesso": False,
            "sql_gerado": sql_query,
            "dados": None,
            "mensagem": resultado,
            "tipo_resposta": "erro_execucao",
        }
        registrar_interacao(
            pergunta=pergunta,
            sql_gerado=sql_query,
            sucesso=False,
            tipo_resposta="erro_execucao",
            mensagem=resultado,
            tempo_resposta_ms=logger_ia.finalizar_timer(),
        )
        return resposta

    # Passo 4: Guardrail de Saída
    resposta_final = guardrail_saida(resultado, sql_query)

    # Passo 5: Registrar interação no log de auditoria
    registrar_interacao(
        pergunta=pergunta,
        sql_gerado=sql_query,
        sucesso=resposta_final["sucesso"],
        tipo_resposta=resposta_final["tipo_resposta"],
        mensagem=resposta_final["mensagem"],
        dados=resposta_final.get("dados"),
        tempo_resposta_ms=logger_ia.finalizar_timer(),
    )

    return resposta_final


# ---------------------------------------------------------------------------
# Função auxiliar para listar produtos (rota /produtos)
# ---------------------------------------------------------------------------
def listar_produtos() -> Tuple[bool, Any]:
    """Retorna todos os produtos do banco analytics."""
    sql = "SELECT * FROM produtos ORDER BY categoria, nome_produto"
    return executar_sql_seguro(sql)
