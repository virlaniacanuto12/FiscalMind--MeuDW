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
# SQL — CARGA DA DIMENSÃO FORNECEDOR
# ============================================================
SQL_UPSERT = """
INSERT INTO dw.dim_fornecedor AS d (
    documento,
    nome,
    nome_fantasia,
    municipio,
    uf,
    bairro
)
SELECT
    s.emitente_documento,
    s.emitente_nome,
    s.emitente_nome_fantasia,
    s.emitente_municipio,
    s.emitente_uf,
    s.emitente_bairro
FROM staging_nfe.tabela_nfe AS s
WHERE s.emitente_documento IS NOT NULL

ON CONFLICT (documento) DO UPDATE
SET
    nome = EXCLUDED.nome,
    nome_fantasia = EXCLUDED.nome_fantasia,
    municipio = EXCLUDED.municipio,
    uf = EXCLUDED.uf,
    bairro = EXCLUDED.bairro

WHERE (
    d.nome,
    d.nome_fantasia,
    d.municipio,
    d.uf,
    d.bairro
)
IS DISTINCT FROM (
    EXCLUDED.nome,
    EXCLUDED.nome_fantasia,
    EXCLUDED.municipio,
    EXCLUDED.uf,
    EXCLUDED.bairro
);
"""


# ============================================================
# SQL — VALIDAÇÃO DA CARGA
# ============================================================
SQL_VALIDACAO = """
SELECT
    (
        SELECT COUNT(DISTINCT emitente_documento)
        FROM staging_nfe.tabela_nfe
        WHERE emitente_documento IS NOT NULL
    ) AS qtd_staging,

    (
        SELECT COUNT(*)
        FROM dw.dim_fornecedor
    ) AS qtd_dimensao,

    (
        SELECT COUNT(*)
        FROM staging_nfe.tabela_nfe AS s
        LEFT JOIN dw.dim_fornecedor AS d
            ON s.emitente_documento = d.documento
        WHERE d.documento IS NULL
    ) AS qtd_faltando;
"""


# ============================================================
# TASK 1 — CARREGAR DIMENSÃO
# ============================================================
def carregar_dim_fornecedor():
    """Insere ou atualiza os emitentes na dimensão fornecedor."""

    hook = PostgresHook(postgres_conn_id=CONN_ID)

    hook.run(SQL_UPSERT)

    print("Carga da dimensão fornecedor concluída.")


# ============================================================
# TASK 2 — VALIDAR DIMENSÃO
# ============================================================
def validar_dim_fornecedor():
    """Verifica se os emitentes da staging chegaram à dimensão."""

    hook = PostgresHook(postgres_conn_id=CONN_ID)

    resultado = hook.get_first(SQL_VALIDACAO)

    if resultado is None:
        raise ValueError("A consulta de validação não retornou dados.")

    qtd_staging, qtd_dimensao, qtd_faltando = resultado

    print(f"Emitentes na staging: {qtd_staging}")
    print(f"Registros na dimensão: {qtd_dimensao}")
    print(f"Documentos sem correspondência: {qtd_faltando}")

    if qtd_faltando > 0:
        raise ValueError(
            f"{qtd_faltando} documento(s) não encontrados na dimensão."
        )

    print("Validação concluída com sucesso.")


# ============================================================
# DAG — DIMENSÃO FORNECEDOR
# ============================================================
with DAG(
    dag_id="dag_dim_fornecedor",
    default_args=default_args,
    description="Carrega e valida a dimensão fornecedor",
    schedule=None,
    start_date=datetime(2025, 1, 1),
    catchup=False,
    tags=["dw", "dimensao", "fornecedor"],
) as dag:

    task_carregar = PythonOperator(
        task_id="carregar_dim_fornecedor",
        python_callable=carregar_dim_fornecedor,
    )

    task_validar = PythonOperator(
        task_id="validar_dim_fornecedor",
        python_callable=validar_dim_fornecedor,
    )

    task_carregar >> task_validar
