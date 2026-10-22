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
# SQL — CARGA DA DIMENSÃO PRODUTO
# ============================================================
# O código do produto (cProd) é próprio de cada fornecedor, por isso
# o produto é identificado por fornecedor + código.
SQL_UPSERT = """
INSERT INTO dw.dim_produto AS d (
    documento_fornecedor,
    codigo_produto,
    descricao_produto,
    ncm,
    cest,
    codigo_barras,
    unidade_comercial
)
-- A staging tem uma linha por item de nota, então o mesmo produto
-- aparece várias vezes. DISTINCT ON fica com uma linha por
-- fornecedor + código: a da nota mais recente. Se o produto aparecer
-- mais de uma vez na mesma nota, fica o último item (numero_item),
-- para que o resultado seja sempre o mesmo a cada execução.
SELECT DISTINCT ON (s.emitente_documento, s.codigo_produto)
    s.emitente_documento,
    s.codigo_produto,
    s.descricao_produto,
    s.ncm,
    s.cest,
    -- "SEM GTIN" indica que o produto não tem código de barras
    NULLIF(s.codigo_barras, 'SEM GTIN'),
    s.unidade_comercial
FROM staging_nfe.tabela_nfe AS s
WHERE s.emitente_documento IS NOT NULL
  AND s.codigo_produto IS NOT NULL
ORDER BY
    s.emitente_documento,
    s.codigo_produto,
    s.data_emissao DESC NULLS LAST,
    s.chave_nfe DESC,
    s.numero_item DESC
 
ON CONFLICT (documento_fornecedor, codigo_produto) DO UPDATE
SET
    descricao_produto = EXCLUDED.descricao_produto,
    ncm = EXCLUDED.ncm,
    cest = EXCLUDED.cest,
    codigo_barras = EXCLUDED.codigo_barras,
    unidade_comercial = EXCLUDED.unidade_comercial
 
WHERE (
    d.descricao_produto,
    d.ncm,
    d.cest,
    d.codigo_barras,
    d.unidade_comercial
)
IS DISTINCT FROM (
    EXCLUDED.descricao_produto,
    EXCLUDED.ncm,
    EXCLUDED.cest,
    EXCLUDED.codigo_barras,
    EXCLUDED.unidade_comercial
);
"""
 
 
# ============================================================
# SQL — VALIDAÇÃO DA CARGA
# ============================================================
SQL_VALIDACAO = """
SELECT
    (
        SELECT COUNT(*)
        FROM (
            SELECT DISTINCT emitente_documento, codigo_produto
            FROM staging_nfe.tabela_nfe
            WHERE emitente_documento IS NOT NULL
              AND codigo_produto IS NOT NULL
        ) AS p
    ) AS qtd_staging,
 
    (
        SELECT COUNT(*)
        FROM dw.dim_produto
    ) AS qtd_dimensao,
 
    (
        SELECT COUNT(*)
        FROM (
            SELECT DISTINCT s.emitente_documento, s.codigo_produto
            FROM staging_nfe.tabela_nfe AS s
            LEFT JOIN dw.dim_produto AS d
                ON  d.documento_fornecedor = s.emitente_documento
                AND d.codigo_produto = s.codigo_produtogit 
            WHERE s.emitente_documento IS NOT NULL
              AND s.codigo_produto IS NOT NULL
              AND d.id_produto IS NULL
        ) AS f
    ) AS qtd_faltando;
"""
 
 
# ============================================================
# TASK 1 — CARREGAR DIMENSÃO
# ============================================================
def carregar_dim_produto():
    """Insere ou atualiza os produtos (fornecedor + código) na dimensão."""
 
    hook = PostgresHook(postgres_conn_id=CONN_ID)
 
    hook.run(SQL_UPSERT)
 
    print("Carga da dimensão produto concluída.")
 
 
# ============================================================
# TASK 2 — VALIDAR DIMENSÃO
# ============================================================
def validar_dim_produto():
    """Verifica se os produtos da staging chegaram à dimensão."""
 
    hook = PostgresHook(postgres_conn_id=CONN_ID)
 
    resultado = hook.get_first(SQL_VALIDACAO)
 
    if resultado is None:
        raise ValueError("A consulta de validação não retornou dados.")
 
    qtd_staging, qtd_dimensao, qtd_faltando = resultado
 
    print(f"Produtos (fornecedor + código) na staging: {qtd_staging}")
    print(f"Registros na dimensão: {qtd_dimensao}")
    print(f"Produtos sem correspondência: {qtd_faltando}")
 
    if qtd_faltando > 0:
        raise ValueError(
            f"{qtd_faltando} produto(s) não encontrados na dimensão."
        )
 
    print("Validação concluída com sucesso.")
 
 
# ============================================================
# DAG — DIMENSÃO PRODUTO
# ============================================================
with DAG(
    dag_id="dag_dim_produto",
    default_args=default_args,
    description="Carrega e valida a dimensão produto",
    schedule=None,
    start_date=datetime(2025, 1, 1),
    catchup=False,
    tags=["dw", "dimensao", "produto"],
) as dag:
 
    task_carregar = PythonOperator(
        task_id="carregar_dim_produto",
        python_callable=carregar_dim_produto,
    )
 
    task_validar = PythonOperator(
        task_id="validar_dim_produto",
        python_callable=validar_dim_produto,
    )
 
    task_carregar >> task_validar
 