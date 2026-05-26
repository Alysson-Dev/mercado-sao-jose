"""
app_mercado.py
==============
Dashboard Administrativo do Mercado São José.
Responsabilidade: Interface web para o gerente consultar dados via linguagem natural.

Funcionalidades:
- Campo de pergunta em PT-BR com envio para API FastAPI
- Exibição de respostas com destaque visual
- Auditoria do SQL gerado (expander)
- Alertas de guardrail (st.warning)
- Visualização rápida de produtos e estoque

Como rodar:
    streamlit run app_mercado.py
"""

import requests
import pandas as pd
import streamlit as st

# ---------------------------------------------------------------------------
# Configurações
# ---------------------------------------------------------------------------
API_BASE_URL = "http://localhost:8003"

st.set_page_config(
    page_title="Mercado São José - Painel do Gerente",
    page_icon="🛒",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Estilos CSS Customizados
# ---------------------------------------------------------------------------
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        color: #1f77b4;
        margin-bottom: 0.5rem;
    }
    .sub-header {
        font-size: 1.1rem;
        color: #666;
        margin-bottom: 2rem;
    }
    .resposta-box {
        background-color: #f0f8ff;
        border-left: 5px solid #1f77b4;
        padding: 1.5rem;
        border-radius: 0.5rem;
        margin: 1rem 0;
    }
    .sql-box {
        background-color: #f5f5f5;
        border: 1px solid #ddd;
        padding: 1rem;
        border-radius: 0.3rem;
        font-family: 'Courier New', monospace;
        font-size: 0.9rem;
    }
    .metric-card {
        background-color: #ffffff;
        border: 1px solid #e0e0e0;
        border-radius: 0.5rem;
        padding: 1rem;
        text-align: center;
    }
    .status-ok { color: #28a745; font-weight: bold; }
    .status-erro { color: #dc3545; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.image("https://img.icons8.com/color/96/supermarket.png", width=80)
    st.markdown("### 🛒 Mercado São José")
    st.markdown("*Painel Administrativo*")
    st.divider()

    # Health Check
    st.markdown("#### Status do Sistema")
    try:
        resp = requests.get(f"{API_BASE_URL}/health", timeout=5)
        if resp.status_code == 200:
            health = resp.json()
            st.markdown(f"API: <span class='status-ok'>● {health['api']}</span>", unsafe_allow_html=True)
            st.markdown(f"Banco: <span class='status-ok'>● {health['banco']}</span>", unsafe_allow_html=True)
            st.markdown(f"IA: <span class='status-ok'>● {health['ia']}</span>", unsafe_allow_html=True)
        else:
            st.markdown("<span class='status-erro'>● API indisponível</span>", unsafe_allow_html=True)
    except Exception as e:
        st.markdown(f"<span class='status-erro'>● Erro: {str(e)[:50]}</span>", unsafe_allow_html=True)

    st.divider()
    st.markdown("#### 💡 Dicas de Perguntas")
    st.markdown("""
    - "Qual produto vendeu mais hoje?"
    - "Quais itens estão com estoque baixo?"
    - "Qual o faturamento desta semana?"
    - "Liste todos os produtos da categoria Laticínios"
    - "Qual o preço do arroz?"
    """)

# ---------------------------------------------------------------------------
# Header Principal
# ---------------------------------------------------------------------------
st.markdown('<div class="main-header">🧠 Assistente Inteligente do Mercado</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">Faça perguntas em português e obtenha respostas baseadas nos dados reais do supermercado.</div>', unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Área de Pergunta
# ---------------------------------------------------------------------------
col1, col2 = st.columns([4, 1])

with col1:
    pergunta = st.text_input(
        "Sua pergunta:",
        placeholder="Ex: Qual produto vendeu mais hoje?",
        key="pergunta_input",
    )

with col2:
    st.markdown("<br>", unsafe_allow_html=True)
    enviar = st.button("🔍 Consultar", type="primary", use_container_width=True)

# ---------------------------------------------------------------------------
# Processamento da Pergunta
# ---------------------------------------------------------------------------
if enviar and pergunta:
    with st.spinner("🤖 Analisando sua pergunta e consultando o banco..."):
        try:
            response = requests.post(
                f"{API_BASE_URL}/perguntar",
                json={"pergunta": pergunta},
                timeout=60,
            )
            response.raise_for_status()
            resultado = response.json()

        except requests.exceptions.ConnectionError:
            st.error("❌ Não foi possível conectar à API. Verifique se o back-end está rodando na porta 8003.")
            st.stop()
        except requests.exceptions.Timeout:
            st.error("⏱️ A consulta demorou muito. Tente uma pergunta mais simples.")
            st.stop()
        except Exception as e:
            st.error(f"❌ Erro inesperado: {str(e)}")
            st.stop()

    # -----------------------------------------------------------------------
    # Tratamento da Resposta
    # -----------------------------------------------------------------------

    # Caso 1: Bloqueado pelo Guardrail de Entrada
    if resultado.get("bloqueado_por_guardrail"):
        st.warning(f"🛡️ **Pergunta bloqueada pelo sistema de segurança**\n\n{resultado['mensagem']}")
        st.info("💡 Dica: Faça perguntas apenas sobre produtos, vendas ou estoque do supermercado.")

    # Caso 2: Erro no processamento
    elif not resultado.get("sucesso"):
        st.error(f"❌ **Erro no processamento**\n\n{resultado['mensagem']}")

    # Caso 3: Resposta vazia (Guardrail de Saída)
    elif resultado.get("tipo_resposta") == "vazio":
        st.info(f"📭 {resultado['mensagem']}")
        if resultado.get("sql_gerado"):
            with st.expander("🔍 Auditar SQL Gerado"):
                st.code(resultado["sql_gerado"], language="sql")

    # Caso 4: Dados encontrados
    else:
        st.success("✅ Consulta realizada com sucesso!")

        # Box de resposta principal
        st.markdown('<div class="resposta-box">', unsafe_allow_html=True)
        st.markdown(f"**📝 Resposta:**\n\n{resultado['mensagem']}")
        st.markdown('</div>', unsafe_allow_html=True)

        # Exibir dados em tabela se houver múltiplas linhas
        dados = resultado.get("dados")
        if dados and isinstance(dados, list) and len(dados) > 0:
            df = pd.DataFrame(dados)
            st.markdown("**📊 Detalhes:**")
            st.dataframe(df, use_container_width=True, hide_index=True)

        # Expander para auditoria do SQL
        with st.expander("🔍 Auditar SQL Gerado pela IA"):
            st.markdown("**Query executada no banco:**")
            st.code(resultado.get("sql_gerado", "N/A"), language="sql")
            st.caption("⚠️ Este SQL foi gerado automaticamente pela IA e executado no banco de analytics (apenas leitura).")

elif enviar and not pergunta:
    st.warning("⚠️ Digite uma pergunta antes de consultar.")

# ---------------------------------------------------------------------------
# Seção de Produtos e Estoque (Visão Rápida)
# ---------------------------------------------------------------------------
st.divider()
st.markdown("### 📦 Visão Geral de Produtos e Estoque")

try:
    resp_produtos = requests.get(f"{API_BASE_URL}/produtos", timeout=10)
    if resp_produtos.status_code == 200:
        produtos = resp_produtos.json()
        df_produtos = pd.DataFrame(produtos)

        # Métricas rápidas
        col_m1, col_m2, col_m3, col_m4 = st.columns(4)
        with col_m1:
            st.metric("Total de Produtos", len(df_produtos))
        with col_m2:
            categorias = df_produtos["categoria"].nunique()
            st.metric("Categorias", categorias)
        with col_m3:
            estoque_baixo = len(df_produtos[df_produtos["estoque_actual"] <= df_produtos["estoque_minimo"]])
            st.metric("⚠️ Estoque Baixo", estoque_baixo, delta=None)
        with col_m4:
            valor_total = (df_produtos["preco_venda"] * df_produtos["estoque_actual"]).sum()
            st.metric("💰 Valor em Estoque", f"R$ {valor_total:,.2f}")

        # Destacar produtos com estoque baixo
        if estoque_baixo > 0:
            st.markdown("#### ⚠️ Produtos com Estoque Crítico")
            df_critico = df_produtos[df_produtos["estoque_actual"] <= df_produtos["estoque_minimo"]]
            st.dataframe(
                df_critico[["nome_produto", "categoria", "estoque_actual", "estoque_minimo", "preco_venda"]],
                use_container_width=True,
                hide_index=True,
            )

        # Tabela completa
        with st.expander("📋 Ver Todos os Produtos"):
            st.dataframe(df_produtos, use_container_width=True, hide_index=True)
    else:
        st.error("Não foi possível carregar os produtos.")
except Exception as e:
    st.error(f"Erro ao carregar produtos: {str(e)}")

# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------
st.divider()
st.caption("🛒 Mercado São José | Sistema de Inteligência Artificial | v1.0.0")
