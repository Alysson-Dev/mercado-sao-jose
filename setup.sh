#!/usr/bin/env bash
# =============================================================================
# setup.sh - Script de Instalação Completa do Mercado São José
# =============================================================================
# Responsabilidade: Configurar todo o ecossistema em uma única execução.
# Inclui: PostgreSQL, Ollama, dependências Python, bancos de dados e serviços.
#
# Como usar:
#   chmod +x setup.sh
#   ./setup.sh
#
# Requisitos:
#   - Ubuntu/Debian (ou adaptar para sua distro)
#   - Anaconda instalado
#   - Acesso sudo (para instalar PostgreSQL se necessário)
# =============================================================================

set -euo pipefail  # Fail fast em erros

# ---------------------------------------------------------------------------
# Cores para output
# ---------------------------------------------------------------------------
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

info() { echo -e "${BLUE}[INFO]${NC} $1"; }
success() { echo -e "${GREEN}[OK]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERRO]${NC} $1"; }

# ---------------------------------------------------------------------------
# Variáveis de Configuração
# ---------------------------------------------------------------------------
PROJECT_DIR="/home/ubuntu"
DB_USER="postgres"
DB_PASSWORD="@Assis1#"
DB_PROD="mercado_sao_jose_producao"
DB_ANALYTICS="mercado_sao_jose_analytics"
DB_IA_USER="ia_mercado"
DB_IA_PASSWORD="ia_readonly_2024"
CONDA_ENV="mercado_ia"
PYTHON_VERSION="3.11"

# ---------------------------------------------------------------------------
# Funções Auxiliares
# ---------------------------------------------------------------------------

check_command() {
    if ! command -v "$1" &> /dev/null; then
        return 1
    fi
    return 0
}

wait_for_postgres() {
    info "Aguardando PostgreSQL iniciar..."
    local retries=30
    while [ $retries -gt 0 ]; do
        if pg_isready -h localhost -p 5432 > /dev/null 2>&1; then
            success "PostgreSQL está pronto!"
            return 0
        fi
        sleep 1
        ((retries--))
    done
    error "PostgreSQL não respondeu após 30 segundos"
    return 1
}

# ---------------------------------------------------------------------------
# 1. Verificar Pré-requisitos
# ---------------------------------------------------------------------------
info "=========================================="
info "  SETUP - Mercado São José"
info "=========================================="
echo ""

info "Verificando pré-requisitos..."

# Verificar se está rodando como root (não deve)
if [ "$EUID" -eq 0 ]; then
    error "Não execute este script como root/sudo"
    exit 1
fi

# Verificar Anaconda
if ! check_command conda; then
    error "Anaconda não encontrado. Instale o Anaconda primeiro:"
    error "  https://docs.anaconda.com/free/anaconda/install/linux/"
    exit 1
fi
success "Anaconda encontrado"

# Verificar PostgreSQL
if ! check_command psql; then
    warn "PostgreSQL não encontrado. Tentando instalar..."
    if check_command apt-get; then
        sudo apt-get update
        sudo apt-get install -y postgresql postgresql-contrib
        sudo systemctl enable postgresql
        sudo systemctl start postgresql
    else
        error "Não foi possível instalar PostgreSQL automaticamente."
        error "Instale manualmente: sudo apt-get install postgresql"
        exit 1
    fi
fi
success "PostgreSQL encontrado"

# Verificar Ollama
if ! check_command ollama; then
    warn "Ollama não encontrado. Instalando..."
    curl -fsSL https://ollama.com/install.sh | sh
fi
success "Ollama encontrado"

# Verificar se modelo llama3 está disponível
if ! ollama list | grep -q "llama3"; then
    info "Baixando modelo Llama 3 (pode demorar alguns minutos)..."
    ollama pull llama3
fi
success "Modelo Llama 3 disponível"

echo ""

# ---------------------------------------------------------------------------
# 2. Criar Ambiente Conda
# ---------------------------------------------------------------------------
info "Configurando ambiente Python (conda)..."

if conda env list | grep -q "$CONDA_ENV"; then
    warn "Ambiente '$CONDA_ENV' já existe. Removendo para recriar..."
    conda env remove -n "$CONDA_ENV" -y
fi

conda create -n "$CONDA_ENV" python="$PYTHON_VERSION" -y
success "Ambiente conda '$CONDA_ENV' criado"

# Ativar ambiente
source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate "$CONDA_ENV"
success "Ambiente ativado"

# ---------------------------------------------------------------------------
# 3. Instalar Dependências Python
# ---------------------------------------------------------------------------
info "Instalando dependências do back-end..."
pip install -r "$PROJECT_DIR/backend-fastapi/requirements.txt"
success "Dependências do back-end instaladas"

info "Instalando dependências do dashboard..."
pip install -r "$PROJECT_DIR/dashboard-streamlit/requirements.txt"
success "Dependências do dashboard instaladas"

# Instalar psycopg2-binary explicitamente (para o ETL)
pip install psycopg2-binary

echo ""

# ---------------------------------------------------------------------------
# 4. Configurar PostgreSQL
# ---------------------------------------------------------------------------
info "Configurando bancos de dados PostgreSQL..."

# Garantir que PostgreSQL está rodando
sudo systemctl start postgresql
wait_for_postgres

# Criar bancos e usuários
info "Criando bancos de dados..."
sudo -u postgres psql <<EOF
-- Criar banco de produção
DROP DATABASE IF EXISTS $DB_PROD;
CREATE DATABASE $DB_PROD;

-- Criar banco de analytics
DROP DATABASE IF EXISTS $DB_ANALYTICS;
CREATE DATABASE $DB_ANALYTICS;

-- Criar usuário da IA (se não existir)
DROP USER IF EXISTS $DB_IA_USER;
CREATE USER $DB_IA_USER WITH PASSWORD '$DB_IA_PASSWORD';

-- Conceder permissões no analytics
\c $DB_ANALYTICS;
GRANT CONNECT ON DATABASE $DB_ANALYTICS TO $DB_IA_USER;
GRANT USAGE ON SCHEMA public TO $DB_IA_USER;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO $DB_IA_USER;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO $DB_IA_USER;
EOF

success "Bancos de dados criados"

# ---------------------------------------------------------------------------
# 5. Criar Tabelas e Dados Iniciais
# ---------------------------------------------------------------------------
info "Criando tabelas e inserindo dados fictícios..."

# Conectar ao banco de produção e executar script
sudo -u postgres psql -d "$DB_PROD" -f "$PROJECT_DIR/database/script.sql"

success "Tabelas e dados criados no banco de produção"

# ---------------------------------------------------------------------------
# 6. Sincronizar Dados para Analytics
# ---------------------------------------------------------------------------
info "Sincronizando dados para banco analytics..."

sudo -u postgres psql <<EOF
\c $DB_ANALYTICS;

-- Copiar produtos
INSERT INTO produtos SELECT * FROM dblink(
    'host=localhost dbname=$DB_PROD user=$DB_USER password=$DB_PASSWORD',
    'SELECT id, nome_produto, categoria, preco_venda, estoque_actual, estoque_minimo, data_cadastro FROM produtos'
) AS t(
    id int, nome_produto varchar, categoria varchar,
    preco_venda decimal, estoque_actual int, estoque_minimo int, data_cadastro timestamp
);

-- Copiar vendas
INSERT INTO vendas_varejo SELECT * FROM dblink(
    'host=localhost dbname=$DB_PROD user=$DB_USER password=$DB_PASSWORD',
    'SELECT id, produto_id, quantidade, valor_total, data_venda FROM vendas_varejo'
) AS t(
    id int, produto_id int, quantidade int,
    valor_total decimal, data_venda timestamp
);

-- Verificar
SELECT 'Produtos: ' || COUNT(*) FROM produtos;
SELECT 'Vendas: ' || COUNT(*) FROM vendas_varejo;
EOF

success "Dados sincronizados para analytics"

# ---------------------------------------------------------------------------
# 7. Criar Diretórios de Logs
# ---------------------------------------------------------------------------
info "Criando estrutura de diretórios..."
mkdir -p "$PROJECT_DIR/logs"
success "Diretórios criados"

# ---------------------------------------------------------------------------
# 8. Criar Scripts de Inicialização
# ---------------------------------------------------------------------------
info "Criando scripts de inicialização..."

# Script para iniciar Ollama
cat > "$PROJECT_DIR/start_ollama.sh" <<'EOF'
#!/bin/bash
# Inicia o servidor Ollama
echo "Iniciando Ollama..."
ollama serve
EOF
chmod +x "$PROJECT_DIR/start_ollama.sh"

# Script para iniciar API
cat > "$PROJECT_DIR/start_api.sh" <<EOF
#!/bin/bash
# Inicia a API FastAPI
cd "$PROJECT_DIR/backend-fastapi"
source "\$(conda info --base)/etc/profile.d/conda.sh"
conda activate $CONDA_ENV
echo "Iniciando API FastAPI na porta 8003..."
uvicorn main_mercado:app --host 0.0.0.0 --port 8003 --reload
EOF
chmod +x "$PROJECT_DIR/start_api.sh"

# Script para iniciar Dashboard
cat > "$PROJECT_DIR/start_dashboard.sh" <<EOF
#!/bin/bash
# Inicia o Dashboard Streamlit
cd "$PROJECT_DIR/dashboard-streamlit"
source "\$(conda info --base)/etc/profile.d/conda.sh"
conda activate $CONDA_ENV
echo "Iniciando Dashboard Streamlit na porta 8501..."
streamlit run app_mercado.py
EOF
chmod +x "$PROJECT_DIR/start_dashboard.sh"

# Script para executar ETL
cat > "$PROJECT_DIR/run_etl.sh" <<EOF
#!/bin/bash
# Executa sincronização ETL
cd "$PROJECT_DIR/backend-fastapi"
source "\$(conda info --base)/etc/profile.d/conda.sh"
conda activate $CONDA_ENV
python etl_sincronizacao.py
EOF
chmod +x "$PROJECT_DIR/run_etl.sh"

# Script para gerar relatório
cat > "$PROJECT_DIR/run_auditoria.sh" <<EOF
#!/bin/bash
# Gera relatório de auditoria
cd "$PROJECT_DIR/backend-fastapi"
source "\$(conda info --base)/etc/profile.d/conda.sh"
conda activate $CONDA_ENV
python observability_logger.py
EOF
chmod +x "$PROJECT_DIR/run_auditoria.sh"

success "Scripts de inicialização criados"

# ---------------------------------------------------------------------------
# 9. Configurar Cron para ETL Automático
# ---------------------------------------------------------------------------
info "Configurando cron para ETL automático..."

# Remover entrada antiga se existir
(crontab -l 2>/dev/null | grep -v "etl_sincronizacao.py") || true

# Adicionar nova entrada
(crontab -l 2>/dev/null; echo "0 * * * * cd $PROJECT_DIR/backend-fastapi && $HOME/anaconda3/envs/$CONDA_ENV/bin/python etl_sincronizacao.py >> $PROJECT_DIR/logs/etl.log 2>&1") | crontab -

success "Cron configurado (ETL a cada hora)"

# ---------------------------------------------------------------------------
# 10. Resumo Final
# ---------------------------------------------------------------------------
echo ""
echo "=========================================="
echo -e "${GREEN}  SETUP CONCLUÍDO COM SUCESSO!${NC}"
echo "=========================================="
echo ""
echo "Ambiente: $CONDA_ENV (Python $PYTHON_VERSION)"
echo ""
echo "Bancos de dados:"
echo "  • Produção:  $DB_PROD"
echo "  • Analytics: $DB_ANALYTICS (read-only para IA)"
echo ""
echo "Scripts disponíveis:"
echo "  ./start_ollama.sh      - Inicia Ollama"
echo "  ./start_api.sh         - Inicia API FastAPI (porta 8003)"
echo "  ./start_dashboard.sh   - Inicia Dashboard Streamlit (porta 8501)"
echo "  ./run_etl.sh           - Executa sincronização manual"
echo "  ./run_auditoria.sh     - Gera relatório de auditoria"
echo ""
echo "Como iniciar o sistema:"
echo ""
echo "  Terminal 1: ./start_ollama.sh"
echo "  Terminal 2: ./start_api.sh"
echo "  Terminal 3: ./start_dashboard.sh"
echo ""
echo "Acesse:"
echo "  • Dashboard:  http://localhost:8501"
echo "  • API Docs:   http://localhost:8003/docs"
echo "  • Health:     http://localhost:8003/health"
echo ""
echo "Logs:"
echo "  • Interações IA: $PROJECT_DIR/logs/ia_queries.jsonl"
echo "  • ETL:           $PROJECT_DIR/logs/etl.log"
echo ""
echo "=========================================="
