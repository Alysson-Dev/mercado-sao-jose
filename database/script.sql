-- ============================================================
-- MERCADO SÃO JOSÉ - BANCO DE DADOS ISOLADO
-- Estratégia: Banco de Produção + Banco Analytics (Read-Only para IA)
-- ============================================================

-- ============================================================
-- 1. BANCO DE PRODUÇÃO (Caixa e Operações do Dia a Dia)
-- ============================================================
CREATE DATABASE mercado_sao_jose_producao;

\c mercado_sao_jose_producao;

-- Tabela de Produtos
CREATE TABLE produtos (
    id SERIAL PRIMARY KEY,
    nome_produto VARCHAR(255) NOT NULL,
    categoria VARCHAR(100) NOT NULL,
    preco_venda DECIMAL(10, 2) NOT NULL,
    estoque_actual INTEGER NOT NULL DEFAULT 0,
    estoque_minimo INTEGER NOT NULL DEFAULT 0,
    data_cadastro TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Tabela de Vendas no Varejo
CREATE TABLE vendas_varejo (
    id SERIAL PRIMARY KEY,
    produto_id INTEGER NOT NULL REFERENCES produtos(id),
    quantidade INTEGER NOT NULL,
    valor_total DECIMAL(10, 2) NOT NULL,
    data_venda TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Inserindo dados fictícios realistas de supermercado
INSERT INTO produtos (nome_produto, categoria, preco_venda, estoque_actual, estoque_minimo) VALUES
('Arroz Tipo 1 5kg', 'Grãos', 28.90, 150, 30),
('Feijão Carioca 1kg', 'Grãos', 8.50, 200, 50),
('Açúcar Refinado 1kg', 'Grãos', 4.99, 120, 25),
('Café em Pó 500g', 'Bebidas', 15.90, 80, 20),
('Leite Integral 1L', 'Laticínios', 6.49, 300, 60),
('Iogurte de Morango 6 un', 'Laticínios', 12.90, 90, 15),
('Queijo Mussarela 500g', 'Laticínios', 24.50, 45, 10),
('Refrigerante Cola 2L', 'Bebidas', 9.99, 110, 30),
('Suco de Laranja 1L', 'Bebidas', 7.90, 60, 15),
('Pão de Forma 500g', 'Padaria', 6.99, 75, 20),
('Manteiga 200g', 'Laticínios', 9.80, 55, 12),
('Macarrão Espaguete 500g', 'Massas', 5.49, 130, 30),
('Óleo de Soja 900ml', 'Grãos', 7.90, 100, 25),
('Sabão em Pó 1kg', 'Limpeza', 14.90, 85, 20),
('Detergente Líquido 500ml', 'Limpeza', 3.99, 150, 40),
('Papel Higiênico 12 rolos', 'Higiene', 18.90, 70, 15),
('Shampoo 400ml', 'Higiene', 16.50, 50, 10),
('Condicionador 400ml', 'Higiene', 15.90, 45, 10),
('Frango Inteiro kg', 'Açougue', 12.90, 40, 10),
('Carne Moída kg', 'Açougue', 29.90, 35, 8),
('Banana Prata kg', 'Hortifruti', 5.99, 100, 25),
('Maçã Gala kg', 'Hortifruti', 8.90, 80, 20),
('Tomate kg', 'Hortifruti', 6.49, 90, 20),
('Cebola kg', 'Hortifruti', 4.99, 110, 25),
('Alface Unidade', 'Hortifruti', 3.49, 60, 15);

-- Inserindo vendas fictícias (últimos 30 dias)
INSERT INTO vendas_varejo (produto_id, quantidade, valor_total, data_venda) VALUES
(1, 5, 144.50, CURRENT_DATE - INTERVAL '1 day'),
(2, 10, 85.00, CURRENT_DATE - INTERVAL '1 day'),
(4, 3, 47.70, CURRENT_DATE - INTERVAL '1 day'),
(5, 20, 129.80, CURRENT_DATE - INTERVAL '1 day'),
(6, 8, 103.20, CURRENT_DATE - INTERVAL '1 day'),
(8, 12, 119.88, CURRENT_DATE - INTERVAL '1 day'),
(10, 15, 104.85, CURRENT_DATE - INTERVAL '1 day'),
(14, 6, 89.40, CURRENT_DATE - INTERVAL '1 day'),
(20, 4, 119.60, CURRENT_DATE - INTERVAL '1 day'),
(22, 10, 89.00, CURRENT_DATE - INTERVAL '1 day'),
(1, 3, 86.70, CURRENT_DATE - INTERVAL '2 days'),
(3, 8, 39.92, CURRENT_DATE - INTERVAL '2 days'),
(7, 5, 122.50, CURRENT_DATE - INTERVAL '2 days'),
(9, 4, 31.60, CURRENT_DATE - INTERVAL '2 days'),
(11, 6, 58.80, CURRENT_DATE - INTERVAL '2 days'),
(13, 7, 55.30, CURRENT_DATE - INTERVAL '2 days'),
(15, 10, 39.90, CURRENT_DATE - INTERVAL '2 days'),
(17, 3, 49.50, CURRENT_DATE - INTERVAL '2 days'),
(19, 5, 64.50, CURRENT_DATE - INTERVAL '2 days'),
(21, 15, 89.85, CURRENT_DATE - INTERVAL '2 days'),
(23, 8, 51.92, CURRENT_DATE - INTERVAL '2 days'),
(2, 12, 102.00, CURRENT_DATE - INTERVAL '3 days'),
(4, 5, 79.50, CURRENT_DATE - INTERVAL '3 days'),
(6, 10, 129.00, CURRENT_DATE - INTERVAL '3 days'),
(8, 8, 79.92, CURRENT_DATE - INTERVAL '3 days'),
(12, 15, 82.35, CURRENT_DATE - INTERVAL '3 days'),
(14, 4, 59.60, CURRENT_DATE - INTERVAL '3 days'),
(16, 5, 94.50, CURRENT_DATE - INTERVAL '3 days'),
(18, 4, 63.60, CURRENT_DATE - INTERVAL '3 days'),
(20, 6, 179.40, CURRENT_DATE - INTERVAL '3 days'),
(24, 12, 59.88, CURRENT_DATE - INTERVAL '3 days');

-- ============================================================
-- 2. BANCO DE ANALYTICS (Réplica de Leitura para IA)
-- ============================================================
CREATE DATABASE mercado_sao_jose_analytics;

\c mercado_sao_jose_analytics;

-- Replicação das mesmas tabelas (sem FKs para performance de leitura)
CREATE TABLE produtos (
    id INTEGER PRIMARY KEY,
    nome_produto VARCHAR(255) NOT NULL,
    categoria VARCHAR(100) NOT NULL,
    preco_venda DECIMAL(10, 2) NOT NULL,
    estoque_actual INTEGER NOT NULL DEFAULT 0,
    estoque_minimo INTEGER NOT NULL DEFAULT 0,
    data_cadastro TIMESTAMP
);

CREATE TABLE vendas_varejo (
    id INTEGER PRIMARY KEY,
    produto_id INTEGER NOT NULL,
    quantidade INTEGER NOT NULL,
    valor_total DECIMAL(10, 2) NOT NULL,
    data_venda TIMESTAMP
);

-- Criar usuário de leitura exclusivo para a IA
CREATE USER ia_mercado WITH PASSWORD 'ia_readonly_2024';
GRANT CONNECT ON DATABASE mercado_sao_jose_analytics TO ia_mercado;
GRANT USAGE ON SCHEMA public TO ia_mercado;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO ia_mercado;

-- Garantir que novas tabelas também recebam permissão de SELECT
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO ia_mercado;

-- Instruções para sincronização manual (ou usar pg_dump/pg_restore)
-- psql -U postgres -d mercado_sao_jose_analytics -c "\COPY produtos FROM PROGRAM 'psql -U postgres -d mercado_sao_jose_producao -c \"COPY produtos TO STDOUT\"'"
-- psql -U postgres -d mercado_sao_jose_analytics -c "\COPY vendas_varejo FROM PROGRAM 'psql -U postgres -d mercado_sao_jose_producao -c \"COPY vendas_varejo TO STDOUT\"'"

-- Comando para sincronização periódica (pode ser automatizado com cron)
-- pg_dump -U postgres -d mercado_sao_jose_producao --data-only --table=produtos --table=vendas_varejo | psql -U postgres -d mercado_sao_jose_analytics
