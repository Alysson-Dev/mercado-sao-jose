# 🛒 Mercado São José - Sistema de Inteligência Artificial

Ecossistema completo de **Natural Language to SQL (NL2SQL)** para o Mercado São José, permitindo que o gerente faça perguntas em português e receba respostas baseadas em dados reais do banco de dados.

---

## 📁 Estrutura do Projeto

```
mercado-sao-jose/
├── database/
│   └── script.sql              # Script PostgreSQL (produção + analytics)
├── backend-fastapi/
│   ├── main_mercado.py         # API FastAPI (porta 8003)
│   ├── core_ia_mercado.py      # Motor de IA (LangChain + Ollama)
│   └── requirements.txt        # Dependências Python do back-end
├── dashboard-streamlit/
│   ├── app_mercado.py          # Dashboard do Gerente
│   └── requirements.txt        # Dependências Python do front-end
└── README.md                   # Este arquivo
```

---

## 🏗️ Arquitetura de Segurança

### 1. Banco de Dados Isolado

| Banco | Função | Permissões da IA |
|-------|--------|------------------|
| `mercado_sao_jose_producao` | Caixa e operações | ❌ Sem acesso |
| `mercado_sao_jose_analytics` | Réplica de leitura | ✅ Apenas SELECT |

- A IA só consulta o banco **analytics** com usuário `ia_mercado` (permissão `SELECT` apenas).
- Mesmo em caso de alucinação do modelo, nenhum dado de produção pode ser alterado.

### 2. Guardrail de Entrada (Input Shield)
- Bloqueia termos de SQL Injection: `DROP`, `DELETE`, `ALTER`, `UPDATE`, `INSERT`, etc.
- Valida escopo: apenas perguntas sobre o supermercado são aceitas.
- Limita comprimento da pergunta (máx. 500 caracteres).

### 3. Guardrail de Saída (Output Verification)
- Intercepta resultados vazios e formata mensagem amigável.
- Intercepta erros de execução e retorna explicação tratada.
- Exibe SQL gerado em área de auditoria (expander).

---

## 🚀 Como Executar

### Pré-requisitos

- Python 3.10+ com Anaconda
- PostgreSQL 14+ instalado e rodando
- Ollama instalado com modelo `llama3` baixado:
  ```bash
  ollama pull llama3
  ```

### Passo 1: Configurar o Banco de Dados

```bash
# Acesse o PostgreSQL
psql -U postgres

# Execute o script
\i database/script.sql

# Sincronize os dados do produção para analytics
\c mercado_sao_jose_analytics

INSERT INTO produtos SELECT * FROM dblink('host=localhost dbname=mercado_sao_jose_producao user=postgres password=@Assis1#', 'SELECT id, nome_produto, categoria, preco_venda, estoque_actual, estoque_minimo, data_cadastro FROM produtos') AS t(id int, nome_produto varchar, categoria varchar, preco_venda decimal, estoque_actual int, estoque_minimo int, data_cadastro timestamp);

INSERT INTO vendas_varejo SELECT * FROM dblink('host=localhost dbname=mercado_sao_jose_producao user=postgres password=@Assis1#', 'SELECT id, produto_id, quantidade, valor_total, data_venda FROM vendas_varejo') AS t(id int, produto_id int, quantidade int, valor_total decimal, data_venda timestamp);
```

> **Alternativa simples:** Use pgAdmin ou DBeaver para copiar os dados entre os bancos.

### Passo 2: Instalar Dependências

```bash
# Ambiente Anaconda (recomendado)
conda create -n mercado_ia python=3.11
conda activate mercado_ia

# Back-end
pip install -r backend-fastapi/requirements.txt

# Front-end
pip install -r dashboard-streamlit/requirements.txt
```

### Passo 3: Iniciar o Ollama

```bash
ollama serve
```

### Passo 4: Iniciar o Back-end (FastAPI)

```bash
cd backend-fastapi
uvicorn main_mercado:app --host 0.0.0.0 --port 8003 --reload
```

Acesse a documentação interativa: http://localhost:8003/docs

### Passo 5: Iniciar o Dashboard (Streamlit)

```bash
cd dashboard-streamlit
streamlit run app_mercado.py
```

Acesse o dashboard: http://localhost:8501

---

## 🔌 Endpoints da API

| Método | Rota | Descrição |
|--------|------|-----------|
| GET | `/` | Mensagem de boas-vindas |
| POST | `/perguntar` | Envia pergunta em PT-BR, retorna SQL + resposta |
| GET | `/produtos` | Lista todos os produtos (para app Kotlin) |
| GET | `/health` | Status da API, banco e IA |

### Exemplo de uso do `/perguntar`:

```bash
curl -X POST "http://localhost:8003/perguntar" \
  -H "Content-Type: application/json" \
  -d '{"pergunta": "Qual produto vendeu mais hoje?"}'
```

---

## 🛡️ Segurança

- **URL do banco com caracteres escapados:** `@` → `%40`, `#` → `%23`
- **Usuário da IA:** `ia_mercado` com senha `ia_readonly_2024` (apenas `SELECT`)
- **SQL Injection:** Bloqueado em múltiplas camadas (guardrail de entrada + verificação de query)
- **Read-Only:** O engine SQLAlchemy usa `execution_options` com isolamento READ COMMITTED

---

## 📝 Licença

Projeto privado - Mercado São José.
