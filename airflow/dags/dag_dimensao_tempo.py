from datetime import datetime, timedelta
from airflow import DAG
from airflow.providers.standard.operators.python import PythonOperator
from airflow.providers.postgres.hooks.postgres import PostgresHook
import pandas as pd
import os

# Configurações da DAG
default_args = {
    'owner': 'virla',
    'depends_on_past': False,
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
}

# Caminhos dos arquivos temporários (dentro do contêiner)
TMP_DIR = '/opt/airflow/dags/tmp'
ARQUIVO_BRUTO = os.path.join(TMP_DIR, 'dim_tempo_bruto.parquet')
ARQUIVO_ENRIQUECIDO = os.path.join(TMP_DIR, 'dim_tempo_enriquecido.parquet')

# TASK 1 — Gerar as datas de 2025 a 2027
def gerar_datas():
    os.makedirs(TMP_DIR, exist_ok=True)
    datas = pd.date_range(start='2025-01-01', end='2027-12-31', freq='D')
    df = pd.DataFrame({'data': datas})
    df.to_parquet(ARQUIVO_BRUTO, index=False)
    print(f"Total de datas geradas: {len(df)}")
    print(f"Primeira data: {df['data'].min()}")
    print(f"Última data: {df['data'].max()}")

# ============================================================
# TASK 2 — Enriquecer com as colunas da dim_tempo
# ============================================================
def enriquecer_dimensao_tempo():
    df = pd.read_parquet(ARQUIVO_BRUTO)
    
    meses_pt = {
        1: 'janeiro', 2: 'fevereiro', 3: 'março', 4: 'abril',
        5: 'maio', 6: 'junho', 7: 'julho', 8: 'agosto',
        9: 'setembro', 10: 'outubro', 11: 'novembro', 12: 'dezembro'
    }
    
    dias_pt = {
        0: 'segunda-feira', 1: 'terça-feira', 2: 'quarta-feira',
        3: 'quinta-feira', 4: 'sexta-feira', 5: 'sábado', 6: 'domingo'
    }
    
    df['dia'] = df['data'].dt.day.astype('int16')
    df['mes'] = df['data'].dt.month.astype('int16')
    df['nome_mes'] = df['data'].dt.month.map(meses_pt)
    df['trimestre'] = df['data'].dt.quarter.astype('int16')
    df['ano'] = df['data'].dt.year.astype('int16')
    df['dia_semana'] = df['data'].dt.dayofweek.map(dias_pt)
    
    df = df[['data', 'dia', 'mes', 'nome_mes', 'trimestre', 'ano', 'dia_semana']]
    df['data'] = pd.to_datetime(df['data']).dt.date
    df.to_parquet(ARQUIVO_ENRIQUECIDO, index=False)
    
    print(f"Total de registros enriquecidos: {len(df)}")
    print(df.head(10).to_string())

# ============================================================
# TASK 3 — Carregar no DW (PostgreSQL)
# ============================================================
def carregar_no_dw():
    df = pd.read_parquet(ARQUIVO_ENRIQUECIDO)
    hook = PostgresHook(postgres_conn_id='fiscalmind_dw')
    engine = hook.get_sqlalchemy_engine()
    datas_existentes = pd.read_sql(
        "SELECT data FROM dw.dim_tempo",
        engine
    )

    df = df[~df['data'].isin(datas_existentes['data'])]

    if df.empty:
        print("Nenhum novo registro para inserir.")
        return
        
    df.to_sql(
        'dim_tempo',
        engine,
        schema='dw',         
        if_exists='append',
        index=False,
        method='multi',
        chunksize=1000
    )
    print(f"Total de registros gravados: {len(df)}")

# ============================================================
# Definição da DAG
# ============================================================
with DAG(
    dag_id='dag_dimensao_tempo',
    default_args=default_args,
    description='Gera e carrega a dimensão tempo de 2025 a 2027 no DW',
    schedule='@once',
    start_date=datetime(2025, 1, 1),
    catchup=False,
    tags=['dw', 'dimensao', 'tempo'],
) as dag:

    task_gerar = PythonOperator(
        task_id='gerar_datas',
        python_callable=gerar_datas,
    )

    task_enriquecer = PythonOperator(
        task_id='enriquecer_dimensao_tempo',
        python_callable=enriquecer_dimensao_tempo,
    )

    task_carregar = PythonOperator(
        task_id='carregar_no_dw',
        python_callable=carregar_no_dw,
    )

    task_gerar >> task_enriquecer >> task_carregar