"""
observability_logger.py
=======================
Sistema de observabilidade e auditoria para o motor de IA do Mercado São José.

Responsabilidade:
- Registrar toda interação com a IA em arquivo de log estruturado
- Salvar a tríade: pergunta do usuário, SQL gerado, timestamp
- Permitir auditoria e refinamento de prompts baseado em histórico
- Detectar padrões de "alucinação" do modelo

Formato do log (JSON Lines - .jsonl):
    {"timestamp": "2024-05-26T10:30:00", "pergunta": "...", "sql_gerado": "...", "sucesso": true, "tipo_resposta": "dados"}
"""

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------
LOG_DIR = Path("/home/ubuntu/logs")
LOG_FILE = LOG_DIR / "ia_queries.jsonl"
REPORT_FILE = LOG_DIR / "relatorio_auditoria.md"

# Garantir que o diretório de logs existe
LOG_DIR.mkdir(parents=True, exist_ok=True)

# Logger Python padrão para erros do sistema
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger("observability")


# ---------------------------------------------------------------------------
# Funções Principais
# ---------------------------------------------------------------------------
def registrar_interacao(
    pergunta: str,
    sql_gerado: Optional[str],
    sucesso: bool,
    tipo_resposta: str,
    mensagem: str,
    dados: Optional[Any] = None,
    bloqueado_por_guardrail: bool = False,
    tempo_resposta_ms: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Registra uma interação completa com a IA no arquivo de log JSONL.
    Retorna o registro criado.
    """
    registro = {
        "timestamp": datetime.now().isoformat(),
        "pergunta": pergunta,
        "sql_gerado": sql_gerado,
        "sucesso": sucesso,
        "tipo_resposta": tipo_resposta,
        "mensagem": mensagem,
        "bloqueado_por_guardrail": bloqueado_por_guardrail,
        "tempo_resposta_ms": tempo_resposta_ms,
        "quantidade_dados": len(dados) if isinstance(dados, list) else None,
    }

    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(registro, ensure_ascii=False) + "\n")
        logger.info(f"[AUDIT] Interação registrada: '{pergunta[:50]}...'")
    except Exception as e:
        logger.error(f"[AUDIT] Falha ao registrar interação: {e}")

    return registro


def ler_historico(limit: int = 100) -> list:
    """
    Lê os últimos N registros do log de interações.
    Útil para análise e auditoria.
    """
    if not LOG_FILE.exists():
        return []

    registros = []
    try:
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        registros.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
    except Exception as e:
        logger.error(f"[AUDIT] Erro ao ler histórico: {e}")

    return registros[-limit:]


def gerar_relatorio_auditoria() -> str:
    """
    Gera um relatório de auditoria em Markdown com estatísticas de uso.
    Retorna o caminho do arquivo gerado.
    """
    registros = ler_historico(limit=10000)  # Ler todos os registros disponíveis

    if not registros:
        return "Nenhum registro encontrado para auditoria."

    total = len(registros)
    sucessos = sum(1 for r in registros if r.get("sucesso"))
    falhas = total - sucessos
    bloqueados = sum(1 for r in registros if r.get("bloqueado_por_guardrail"))
    vazios = sum(1 for r in registros if r.get("tipo_resposta") == "vazio")

    # Perguntas mais comuns (simples contagem)
    perguntas = {}
    for r in registros:
        p = r.get("pergunta", "")
        perguntas[p] = perguntas.get(p, 0) + 1

    top_perguntas = sorted(perguntas.items(), key=lambda x: x[1], reverse=True)[:10]

    # Detectar possíveis alucinações (SQL que não é SELECT ou vazio)
    possiveis_alucinacoes = [
        r for r in registros
        if r.get("sql_gerado") and not r.get("sql_gerado", "").strip().lower().startswith("select")
    ]

    relatorio = f"""# 📊 Relatório de Auditoria - IA Mercado São José

**Gerado em:** {datetime.now().strftime("%d/%m/%Y %H:%M:%S")}

---

## 📈 Estatísticas Gerais

| Métrica | Valor |
|---------|-------|
| Total de interações | {total} |
| Consultas bem-sucedidas | {sucessos} ({sucessos/total*100:.1f}%) |
| Consultas com falha | {falhas} ({falhas/total*100:.1f}%) |
| Bloqueadas pelo guardrail | {bloqueados} ({bloqueados/total*100:.1f}%) |
| Respostas vazias | {vazios} ({vazios/total*100:.1f}%) |

---

## 🔝 Perguntas Mais Frequentes

| # | Pergunta | Ocorrências |
|---|----------|-------------|
"""

    for i, (pergunta, count) in enumerate(top_perguntas, 1):
        relatorio += f"| {i} | {pergunta[:80]}{'...' if len(pergunta) > 80 else ''} | {count} |\n"

    relatorio += f"""
---

## ⚠️ Possíveis Alucinações do Modelo

**Definição:** SQL gerado que não começa com SELECT ou contém comandos perigosos.

**Quantidade detectada:** {len(possiveis_alucinacoes)}

"""

    if possiveis_alucinacoes:
        relatorio += "| Timestamp | Pergunta | SQL Gerado |\n"
        relatorio += "|-----------|----------|------------|\n"
        for r in possiveis_alucinacoes[:20]:  # Limitar a 20 exemplos
            ts = r.get("timestamp", "N/A")
            p = r.get("pergunta", "N/A")[:60]
            sql = r.get("sql_gerado", "N/A")[:80]
            relatorio += f"| {ts} | {p} | `{sql}` |\n"
    else:
        relatorio += "✅ Nenhuma alucinação detectada no período analisado.\n"

    relatorio += f"""
---

## 💡 Recomendações

1. **Se houver muitas respostas vazias:** Verifique se os dados do ETL estão atualizados.
2. **Se houver alucinações:** Considere ajustar o prompt no `core_ia_mercado.py` ou aumentar a temperatura.
3. **Se houver muitos bloqueios:** Avalie se o guardrail de entrada está muito restritivo.

---

*Relatório gerado automaticamente pelo sistema de observabilidade.*
"""

    try:
        with open(REPORT_FILE, "w", encoding="utf-8") as f:
            f.write(relatorio)
        logger.info(f"[AUDIT] Relatório gerado: {REPORT_FILE}")
        return str(REPORT_FILE)
    except Exception as e:
        logger.error(f"[AUDIT] Erro ao gerar relatório: {e}")
        return f"Erro ao gerar relatório: {e}"


def analisar_tendencias() -> Dict[str, Any]:
    """
    Analisa tendências nas perguntas dos usuários.
    Retorna estatísticas úteis para melhorar o sistema.
    """
    registros = ler_historico(limit=10000)

    if not registros:
        return {"erro": "Nenhum dado para análise"}

    # Agrupar por hora do dia
    horarios = {}
    for r in registros:
        ts = r.get("timestamp", "")
        if ts:
            hora = ts[11:13]  # Extrair HH
            horarios[hora] = horarios.get(hora, 0) + 1

    # Taxa de sucesso por tipo de resposta
    taxa_sucesso = {}
    for tipo in ["dados", "vazio", "erro", "bloqueado"]:
        tipo_regs = [r for r in registros if r.get("tipo_resposta") == tipo]
        if tipo_regs:
            taxa_sucesso[tipo] = {
                "total": len(tipo_regs),
                "sucesso": sum(1 for r in tipo_regs if r.get("sucesso")),
            }

    return {
        "total_interacoes": len(registros),
        "distribuicao_horaria": horarios,
        "taxa_sucesso_por_tipo": taxa_sucesso,
        "primeira_interacao": registros[0].get("timestamp"),
        "ultima_interacao": registros[-1].get("timestamp"),
    }


# ---------------------------------------------------------------------------
# Wrapper para integração com core_ia_mercado.py
# ---------------------------------------------------------------------------
class IALogger:
    """
    Classe wrapper para facilitar o logging de interações no motor de IA.
    Uso: from observability_logger import IALogger
    """

    def __init__(self):
        self.inicio = None

    def iniciar_timer(self):
        self.inicio = datetime.now()

    def finalizar_timer(self) -> float:
        if self.inicio:
            return (datetime.now() - self.inicio).total_seconds() * 1000
        return 0.0

    def log(self, **kwargs):
        registrar_interacao(**kwargs)


# ---------------------------------------------------------------------------
# Execução direta (gerar relatório)
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("=" * 60)
    print("SISTEMA DE OBSERVABILIDADE - Mercado São José")
    print("=" * 60)

    # Verificar se existe log
    if LOG_FILE.exists():
        registros = ler_historico()
        print(f"\n📁 Arquivo de log: {LOG_FILE}")
        print(f"📊 Total de interações registradas: {len(registros)}")

        if registros:
            print(f"🕐 Primeira interação: {registros[0].get('timestamp')}")
            print(f"🕐 Última interação: {registros[-1].get('timestamp')}")

            # Gerar relatório
            caminho = gerar_relatorio_auditoria()
            print(f"\n✅ Relatório de auditoria gerado: {caminho}")

            # Mostrar tendências
            tendencias = analisar_tendencias()
            print(f"\n📈 Tendências:")
            print(f"   - Total de interações: {tendencias['total_interacoes']}")
            print(f"   - Horários mais ativos: {', '.join(sorted(tendencias['distribuicao_horaria'].keys())[:5])}")
    else:
        print(f"\n⚠️ Nenhum log encontrado em: {LOG_FILE}")
        print("   O log será criado automaticamente quando a IA receber a primeira pergunta.")

    print("\n" + "=" * 60)
