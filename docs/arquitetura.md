# 🏗️ Arquitetura do Sistema - Mercado São José

## Visão Geral

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           USUÁRIO (Gerente)                                  │
│                    Acessa via navegador (Streamlit)                          │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                      DASHBOARD STREAMLIT (Porta 8501)                        │
│  • Campo de pergunta em linguagem natural                                   │
│  • Exibe respostas com destaque visual                                      │
│  • Auditoria do SQL via st.expander                                         │
│  • Alertas de guardrail (st.warning)                                        │
│  • Visão geral de produtos e estoque                                        │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼ HTTP POST /perguntar
┌─────────────────────────────────────────────────────────────────────────────┐
│                      BACK-END FASTAPI (Porta 8003)                           │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                    GUARDRAIL DE ENTRADA                              │    │
│  │  • Bloqueia: DROP, DELETE, ALTER, UPDATE, INSERT, etc.              │    │
│  │  • Valida escopo (apenas sobre supermercado)                        │    │
│  │  • Limita tamanho da pergunta (500 chars)                           │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                      │                                       │
│                                      ▼                                       │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │              MOTOR DE IA (LangChain + Ollama Llama 3)                │    │
│  │  • Prompt customizado forçando SELECT apenas                        │    │
│  │  • Temperatura baixa (0.1) para respostas determinísticas           │    │
│  │  • Contexto do schema das tabelas                                   │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                      │                                       │
│                                      ▼                                       │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │              VERIFICAÇÃO DE SEGURANÇA DO SQL                         │    │
│  │  • Confirma que query começa com SELECT                             │    │
│  │  • Remove comentários e verifica comandos proibidos                 │    │
│  │  • Rejeita qualquer comando que não seja SELECT                     │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                      │                                       │
│                                      ▼                                       │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                    GUARDRAIL DE SAÍDA                                │    │
│  │  • Resultado vazio → mensagem amigável                              │    │
│  │  • Erro de execução → explicação tratada                            │    │
│  │  • Formata resposta final em JSON                                   │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                      │                                       │
│                                      ▼                                       │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                 OBSERVABILIDADE (Logger JSONL)                       │    │
│  │  • Registra: pergunta, SQL gerado, timestamp, tempo de resposta     │    │
│  │  • Arquivo: /home/ubuntu/logs/ia_queries.jsonl                      │    │
│  │  • Relatório: /home/ubuntu/logs/relatorio_auditoria.md              │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼ psycopg2 (apenas SELECT)
┌─────────────────────────────────────────────────────────────────────────────┐
│              BANCO POSTGRESQL - ANALYTICS (mercado_sao_jose_analytics)       │
│                                                                              │
│  Usuário: ia_mercado                                                         │
│  Permissões: CONNECT, USAGE, SELECT (apenas)                                 │
│  Senha: ia_readonly_2024                                                     │
│                                                                              │
│  Tabelas:                                                                    │
│    • produtos (id, nome_produto, categoria, preco_venda, estoque, ...)      │
│    • vendas_varejo (id, produto_id, quantidade, valor_total, data_venda)    │
│                                                                              │
│  ⚠️ APENAS LEITURA - Nenhum INSERT/UPDATE/DELETE permitido                 │
└─────────────────────────────────────────────────────────────────────────────┘
                                      ▲
                                      │
                                      │ ETL (a cada hora via cron)
                                      │
┌─────────────────────────────────────────────────────────────────────────────┐
│              BANCO POSTGRESQL - PRODUÇÃO (mercado_sao_jose_producao)         │
│                                                                              │
│  Usuário: postgres                                                           │
│  Permissões: FULL (todas as operações)                                       │
│                                                                              │
│  Tabelas:                                                                    │
│    • produtos (id, nome_produto, categoria, preco_venda, estoque, ...)      │
│    • vendas_varejo (id, produto_id, quantidade, valor_total, data_venda)    │
│                                                                              │
│  📝 Caixa e operações do dia a dia                                           │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Fluxo de Dados (NL2SQL)

```
1. Usuário digita: "Qual produto vendeu mais hoje?"
        │
        ▼
2. Streamlit envia POST /perguntar para FastAPI
        │
        ▼
3. Guardrail de Entrada valida:
   ✓ Sem palavras proibidas
   ✓ Dentro do escopo do supermercado
   ✓ Tamanho aceitável
        │
        ▼
4. LangChain + Ollama (Llama 3) gera SQL:
   SELECT p.nome_produto, SUM(v.quantidade) as total_vendido
   FROM produtos p
   JOIN vendas_varejo v ON p.id = v.produto_id
   WHERE v.data_venda >= CURRENT_DATE
   GROUP BY p.nome_produto
   ORDER BY total_vendido DESC
   LIMIT 1;
        │
        ▼
5. Verificação de Segurança:
   ✓ Começa com SELECT
   ✓ Sem comandos proibidos
        │
        ▼
6. Executa no banco ANALYTICS (read-only)
        │
        ▼
7. Guardrail de Saída:
   ✓ Resultado encontrado → formata mensagem amigável
   ✓ Registra no log de auditoria
        │
        ▼
8. Retorna JSON para Streamlit:
   {
     "sucesso": true,
     "sql_gerado": "SELECT ...",
     "dados": [{"nome_produto": "Arroz Tipo 1 5kg", "total_vendido": 15}],
     "mensagem": "Encontrei 1 registro para sua consulta.",
     "tipo_resposta": "dados"
   }
        │
        ▼
9. Streamlit exibe resposta com destaque + auditoria SQL
```

---

## Camadas de Segurança

| Camada | Mecanismo | O que protege |
|--------|-----------|---------------|
| **1. Input Shield** | Lista de palavras proibidas + regex | SQL Injection na pergunta |
| **2. Prompt Engineering** | Instrução explícita no prompt | Modelo gerando SQL malicioso |
| **3. SQL Verification** | Verificação de `SELECT` apenas | Execução de comandos perigosos |
| **4. Database Isolation** | Banco separado (analytics) | Dados de produção nunca expostos |
| **5. Read-Only User** | Usuário `ia_mercado` com apenas SELECT | Alteração acidental de dados |
| **6. Output Verification** | Tratamento de erros e vazios | Exposição de informações sensíveis |

---

## Componentes e Tecnologias

| Componente | Tecnologia | Função |
|------------|------------|--------|
| Front-end | Streamlit | Interface do gerente |
| API | FastAPI | Rotas REST e validação |
| Motor de IA | LangChain + Ollama (Llama 3) | NL2SQL |
| Banco Analytics | PostgreSQL | Dados para consulta da IA |
| Banco Produção | PostgreSQL | Dados operacionais do caixa |
| ETL | Python + psycopg2 | Sincronização periódica |
| Observabilidade | Python + JSONL | Auditoria e logs |

---

## URLs e Portas

| Serviço | URL Local | Porta |
|---------|-----------|-------|
| Dashboard Streamlit | http://localhost:8501 | 8501 |
| API FastAPI | http://localhost:8003 | 8003 |
| Documentação API | http://localhost:8003/docs | 8003 |
| PostgreSQL | localhost | 5432 |
| Ollama | http://localhost:11434 | 11434 |

---

## Arquivos Principais

```
/home/ubuntu/
├── database/
│   └── script.sql                    # Criação dos bancos e dados iniciais
├── backend-fastapi/
│   ├── main_mercado.py               # API FastAPI (rotas)
│   ├── core_ia_mercado.py            # Motor de IA + Guardrails
│   ├── etl_sincronizacao.py          # Sincronização produção → analytics
│   ├── observability_logger.py       # Sistema de logs e auditoria
│   └── requirements.txt              # Dependências Python
├── dashboard-streamlit/
│   ├── app_mercado.py                # Dashboard do gerente
│   └── requirements.txt              # Dependências Python
├── docs/
│   └── arquitetura.md                # Este documento
└── logs/
    ├── ia_queries.jsonl              # Log de interações com a IA
    └── relatorio_auditoria.md        # Relatório periódico de auditoria
```

---

## Comandos Úteis

### Iniciar o sistema completo

```bash
# 1. Ollama (em um terminal)
ollama serve

# 2. API FastAPI (em outro terminal)
cd /home/ubuntu/backend-fastapi
uvicorn main_mercado:app --host 0.0.0.0 --port 8003 --reload

# 3. Dashboard Streamlit (em outro terminal)
cd /home/ubuntu/dashboard-streamlit
streamlit run app_mercado.py
```

### Executar ETL manualmente

```bash
cd /home/ubuntu/backend-fastapi
python etl_sincronizacao.py
```

### Configurar cron para ETL automático (a cada hora)

```bash
# Editar crontab
crontab -e

# Adicionar linha:
0 * * * * cd /home/ubuntu/backend-fastapi && /home/ubuntu/anaconda3/envs/mercado_ia/bin/python etl_sincronizacao.py >> /home/ubuntu/logs/etl.log 2>&1
```

### Gerar relatório de auditoria

```bash
cd /home/ubuntu/backend-fastapi
python observability_logger.py
```

### Ver logs de interação

```bash
# Últimas 10 interações
tail -n 10 /home/ubuntu/logs/ia_queries.jsonl

# Formatar para leitura
jq . /home/ubuntu/logs/ia_queries.jsonl | tail -n 50
```

---

*Documento gerado automaticamente. Última atualização: 2024-05-26*
