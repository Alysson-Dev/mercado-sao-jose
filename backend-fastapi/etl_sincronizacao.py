"""
etl_sincronizacao.py
====================
Script de sincronização periódica entre o banco de PRODUÇÃO e o banco ANALYTICS.

Responsabilidade:
- Copiar dados das tabelas produtos e vendas_varejo do banco produção para o analytics
- Garantir que o banco analytics esteja sempre atualizado para consultas da IA
- Ser executado via cron a cada hora ou manualmente

Como usar:
    python etl_sincronizacao.py

Para automação (cron), adicione ao crontab:
    0 * * * * cd /home/ubuntu/backend-fastapi && /home/ubuntu/anaconda3/envs/mercado_ia/bin/python etl_sincronizacao.py >> /home/ubuntu/logs/etl.log 2>&1
"""

import logging
import sys
from datetime import datetime
from typing import Tuple

import psycopg2
from psycopg2.extras import execute_values

# ---------------------------------------------------------------------------
# Configuração de Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ]
)
logger = logging.getLogger("etl_mercado")

# ---------------------------------------------------------------------------
# Configuração dos Bancos
# ---------------------------------------------------------------------------
# Produção (fonte dos dados)
DB_PRODUCAO = {
    "host": "localhost",
    "port": 5432,
    "dbname": "mercado_sao_jose_producao",
    "user": "postgres",
    "password": "@Assis1#",
}

# Analytics (destino - apenas leitura para IA)
DB_ANALYTICS = {
    "host": "localhost",
    "port": 5432,
    "dbname": "mercado_sao_jose_analytics",
    "user": "postgres",
    "password": "@Assis1#",
}

TABELAS = ["produtos", "vendas_varejo"]

# ---------------------------------------------------------------------------
# Funções de Conexão
# ---------------------------------------------------------------------------
def conectar(config: dict) -> psycopg2.extensions.connection:
    """Cria conexão com o PostgreSQL."""
    try:
        conn = psycopg2.connect(**config)
        logger.info(f"Conectado ao banco: {config['dbname']}")
        return conn
    except psycopg2.Error as e:
        logger.error(f"Erro ao conectar em {config['dbname']}: {e}")
        raise


# ---------------------------------------------------------------------------
# ETL - Sincronização
# ---------------------------------------------------------------------------
def sincronizar_tabela(
    conn_origem: psycopg2.extensions.connection,
    conn_destino: psycopg2.extensions.connection,
    tabela: str,
) -> Tuple[int, int]:
    """
    Sincroniza uma tabela do banco produção para o analytics.
    Estratégia: TRUNCATE + INSERT (carga completa).
    Retorna: (linhas_deletadas, linhas_inseridas)
    """
    logger.info(f"[ETL] Iniciando sincronização da tabela: {tabela}")

    cursor_origem = conn_origem.cursor()
    cursor_destino = conn_destino.cursor()

    try:
        # 1. Ler todos os dados da origem
        cursor_origem.execute(f"SELECT * FROM {tabela}")
        colunas = [desc[0] for desc in cursor_origem.description]
        dados = cursor_origem.fetchall()
        logger.info(f"[ETL] {len(dados)} registros lidos de {tabela}")

        # 2. Limpar a tabela de destino
        cursor_destino.execute(f"TRUNCATE TABLE {tabela} RESTART IDENTITY CASCADE")
        linhas_deletadas = cursor_destino.rowcount
        logger.info(f"[ETL] Tabela {tabela} truncada no destino")

        # 3. Inserir dados no destino
        if dados:
            colunas_str = ", ".join(colunas)
            query_insert = f"INSERT INTO {tabela} ({colunas_str}) VALUES %s"
            execute_values(cursor_destino, query_insert, dados)
            linhas_inseridas = cursor_destino.rowcount
            logger.info(f"[ETL] {linhas_inseridas} registros inseridos em {tabela}")
        else:
            linhas_inseridas = 0
            logger.warning(f"[ETL] Nenhum dado para inserir em {tabela}")

        conn_destino.commit()
        return linhas_deletadas, linhas_inseridas

    except Exception as e:
        conn_destino.rollback()
        logger.error(f"[ETL] Erro ao sincronizar {tabela}: {e}")
        raise
    finally:
        cursor_origem.close()
        cursor_destino.close()


def executar_etl_completo() -> dict:
    """
    Executa o pipeline ETL completo para todas as tabelas.
    Retorna relatório de execução.
    """
    inicio = datetime.now()
    logger.info("=" * 60)
    logger.info("[ETL] INICIANDO SINCRONIZAÇÃO")
    logger.info(f"[ETL] Timestamp: {inicio.isoformat()}")
    logger.info("=" * 60)

    relatorio = {
        "inicio": inicio.isoformat(),
        "tabelas": {},
        "sucesso": False,
        "erro": None,
    }

    conn_origem = None
    conn_destino = None

    try:
        conn_origem = conectar(DB_PRODUCAO)
        conn_destino = conectar(DB_ANALYTICS)

        for tabela in TABELAS:
            deletadas, inseridas = sincronizar_tabela(conn_origem, conn_destino, tabela)
            relatorio["tabelas"][tabela] = {
                "deletadas": deletadas,
                "inseridas": inseridas,
            }

        relatorio["sucesso"] = True
        logger.info("[ETL] Sincronização concluída com sucesso!")

    except Exception as e:
        relatorio["erro"] = str(e)
        logger.error(f"[ETL] Falha na sincronização: {e}")

    finally:
        if conn_origem:
            conn_origem.close()
            logger.info("[ETL] Conexão produção fechada")
        if conn_destino:
            conn_destino.close()
            logger.info("[ETL] Conexão analytics fechada")

        fim = datetime.now()
        duracao = (fim - inicio).total_seconds()
        relatorio["fim"] = fim.isoformat()
        relatorio["duracao_segundos"] = duracao

        logger.info(f"[ETL] Duração total: {duracao:.2f} segundos")
        logger.info("=" * 60)

    return relatorio


# ---------------------------------------------------------------------------
# Execução
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    relatorio = executar_etl_completo()

    # Saída resumida para facilitar leitura
    print("\n" + "=" * 60)
    print("RELATÓRIO DE SINCRONIZAÇÃO")
    print("=" * 60)
    print(f"Status: {'✅ SUCESSO' if relatorio['sucesso'] else '❌ FALHA'}")
    print(f"Início: {relatorio['inicio']}")
    print(f"Fim: {relatorio.get('fim', 'N/A')}")
    print(f"Duração: {relatorio.get('duracao_segundos', 0):.2f}s")
    print("\nTabelas sincronizadas:")
    for tabela, stats in relatorio["tabelas"].items():
        print(f"  • {tabela}: {stats['inseridas']} registros inseridos")
    if relatorio["erro"]:
        print(f"\nErro: {relatorio['erro']}")
    print("=" * 60)
