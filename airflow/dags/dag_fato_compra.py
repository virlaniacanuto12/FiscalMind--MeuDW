from datetime import datetime, timedelta
from airflow import DAG
from airflow.providers.standard.operators.python import PythonOperator
from airflow.providers.postgres.hooks.postgres import PostgresHook
 
 
# ============================================================
# CONFIGURAÇÕES
# ============================================================
CONN_ID = "fiscalmind_dw"
 
default_args = {
    "owner": "virla",
    "depends_on_past": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}
 
 
# ============================================================
# SQL — CARGA DA FATO COMPRA
# ============================================================
# Pré-requisito: dim_tempo, dim_fornecedor e dim_produto já carregadas.
#
# Grão: 1 linha = 1 item de 1 nota (o mesmo grão da staging).
# Cada item da staging busca a chave substituta (id_*) de cada dimensão.
# Um item já gravado (mesmo fornecedor + modelo + série + número da nota
# + número do item) é ignorado: a fato registra eventos que não mudam,
# por isso não há atualização.
#
# OBSERVAÇÃO: Quando a staging passar a receber notas de venda, esta carga e a
# validação precisam filtrar só as compras (destinatário = empresa). Ver issue #14.
SQL_CARGA = """
WITH inseridos AS (
    INSERT INTO dw.fato_compra (
        id_tempo,
        id_produto,
        id_fornecedor,
        modelo,
        serie,
        numero_nota,
        numero_item,
        quantidade,
        valor_unitario,
        valor_produto
    )
    SELECT
        t.id_tempo,
        p.id_produto,
        f.id_fornecedor,
        s.modelo,
        s.serie,
        s.numero_nota,
        s.numero_item,
        s.quantidade,
        s.valor_unitario,
        s.valor_produto
    FROM staging_nfe.tabela_nfe AS s
    -- Data da emissão no horário de Brasília
    JOIN dw.dim_tempo AS t
        ON t.data = (s.data_emissao AT TIME ZONE 'America/Sao_Paulo')::date
    JOIN dw.dim_fornecedor AS f
        ON f.documento = s.emitente_documento
    -- O produto é identificado por fornecedor + código
    JOIN dw.dim_produto AS p
        ON  p.documento_fornecedor = s.emitente_documento
        AND p.codigo_produto = s.codigo_produto
 
    ON CONFLICT (id_fornecedor, modelo, serie, numero_nota, numero_item) DO NOTHING
    RETURNING 1
)
SELECT COUNT(*) FROM inseridos;
"""
 
 
# ============================================================
# SQL — VALIDAÇÃO DA CARGA
# ============================================================
# Todo item da staging deve estar na fato. Se faltar algum, mostra
# qual dimensão não encontrou correspondência.
#
# A dim_fornecedor entra ANTES da fato: a fato é identificada pelo
# id_fornecedor, que só existe depois de achar o fornecedor pelo documento.
SQL_VALIDACAO = """
WITH faltando AS (
    SELECT
        s.*,
        t.id_tempo,
        f.id_fornecedor,
        p.id_produto
    FROM staging_nfe.tabela_nfe AS s
    LEFT JOIN dw.dim_fornecedor AS f
        ON f.documento = s.emitente_documento
    LEFT JOIN dw.fato_compra AS fc
        ON  fc.id_fornecedor = f.id_fornecedor
        AND fc.modelo        = s.modelo
        AND fc.serie         = s.serie
        AND fc.numero_nota   = s.numero_nota
        AND fc.numero_item   = s.numero_item
    LEFT JOIN dw.dim_tempo AS t
        ON t.data = (s.data_emissao AT TIME ZONE 'America/Sao_Paulo')::date
    LEFT JOIN dw.dim_produto AS p
        ON  p.documento_fornecedor = s.emitente_documento
        AND p.codigo_produto = s.codigo_produto
    WHERE fc.id_compra IS NULL
)
SELECT
    (SELECT COUNT(*) FROM staging_nfe.tabela_nfe) AS qtd_staging,
    (SELECT COUNT(*) FROM dw.fato_compra)         AS qtd_fato,
    (SELECT COUNT(*) FROM faltando)               AS qtd_faltando,
    (SELECT COUNT(*) FROM faltando WHERE id_tempo IS NULL)      AS sem_tempo,
    (SELECT COUNT(*) FROM faltando WHERE id_fornecedor IS NULL) AS sem_fornecedor,
    (SELECT COUNT(*) FROM faltando WHERE id_produto IS NULL)    AS sem_produto;
"""
 
 
# ============================================================
# TASK 1 — CARREGAR FATO
# ============================================================
def carregar_fato_compra():
    """Insere na fato os itens da staging que ainda não estão nela."""
 
    hook = PostgresHook(postgres_conn_id=CONN_ID)
 
    # run() executa e confirma (COMMIT); o handler devolve o resultado
    inseridos = hook.run(SQL_CARGA, handler=lambda cursor: cursor.fetchone()[0])
 
    print(f"Itens inseridos na fato_compra: {inseridos}")
 
 
# ============================================================
# TASK 2 — VALIDAR FATO
# ============================================================
def validar_fato_compra():
    """Verifica se todos os itens da staging chegaram à fato."""
 
    hook = PostgresHook(postgres_conn_id=CONN_ID)
 
    resultado = hook.get_first(SQL_VALIDACAO)
 
    if resultado is None:
        raise ValueError("A consulta de validação não retornou dados.")
 
    (qtd_staging, qtd_fato, qtd_faltando,
     sem_tempo, sem_fornecedor, sem_produto) = resultado
 
    print(f"Itens na staging: {qtd_staging}")
    print(f"Itens na fato: {qtd_fato}")
    print(f"Itens faltando na fato: {qtd_faltando}")
 
    if qtd_faltando > 0:
        print(f"  sem data na dim_tempo: {sem_tempo}")
        print(f"  sem fornecedor na dim_fornecedor: {sem_fornecedor}")
        print(f"  sem produto na dim_produto: {sem_produto}")
        raise ValueError(
            f"{qtd_faltando} item(ns) da staging não chegaram à fato. "
            "Verifique se as dimensões foram carregadas."
        )
 
    print("Validação concluída com sucesso.")
 
 
# ============================================================
# DAG — FATO COMPRA
# ============================================================
with DAG(
    dag_id="dag_fato_compra",
    default_args=default_args,
    description="Carrega e valida a fato compra (um item de nota por linha)",
    schedule=None,
    start_date=datetime(2025, 1, 1),
    catchup=False,
    tags=["dw", "fato", "compra"],
) as dag:
 
    task_carregar = PythonOperator(
        task_id="carregar_fato_compra",
        python_callable=carregar_fato_compra,
    )
 
    task_validar = PythonOperator(
        task_id="validar_fato_compra",
        python_callable=validar_fato_compra,
    )
 
    task_carregar >> task_validar
 