from datetime import datetime, timedelta
from airflow import DAG
from airflow.providers.standard.operators.python import PythonOperator
from airflow.providers.postgres.hooks.postgres import PostgresHook
import pandas as pd
from lxml import etree
from pathlib import Path

# ============================================================
# CONFIGURAÇÕES
# ============================================================
PASTA_XMLS = Path("/opt/airflow/data/inbox")
SCHEMA_STAGING = "staging_nfe"
TABELA_STAGING = "tabela_nfe"
CONN_ID = "fiscalmind_dw"

default_args = {
    'owner': 'virla',
    'depends_on_past': False,
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
}

# ============================================================
# FUNÇÕES AUXILIARES
# ============================================================
def nome_tag(tag):
    if isinstance(tag, str):
        return tag.rsplit("}", 1)[-1]
    return ""

def filho(elemento, nome):
    if elemento is None:
        return None
    return next((item for item in elemento if nome_tag(item.tag) == nome), None)

def texto(elemento, nome):
    encontrado = filho(elemento, nome)
    if encontrado is None:
        return None
    valor = (encontrado.text or "").strip()
    return valor if valor else None

# ============================================================
# EXTRAÇÃO — FORNECEDORES (emitente)
# ============================================================
def extrair_fornecedores():
    """Extrai dados do emitente (fornecedor) de cada XML.
    
    Retorna uma lista de dicionários, um por fornecedor único.
    """
    arquivos = sorted(PASTA_XMLS.rglob("*.xml"))
    if not arquivos:
        raise ValueError(f"Nenhum XML encontrado em {PASTA_XMLS}")
    
    print(f"Encontrados {len(arquivos)} arquivos XML.")
    
    fornecedores = {}  # chave: documento (CNPJ/CPF)
    erros = 0
    
    for arquivo in arquivos:
        try:
            parser = etree.XMLParser(recover=True, huge_tree=True)
            tree = etree.parse(str(arquivo), parser)
            raiz = tree.getroot()
            
            inf = next(
                (e for e in raiz.iter() if nome_tag(e.tag) == "infNFe"),
                None
            )
            if inf is None:
                print(f"Sem infNFe em {arquivo.name}")
                erros += 1
                continue
            
            emit = filho(inf, "emit")
            if emit is None:
                print(f"Sem emit em {arquivo.name}")
                erros += 1
                continue
            
            cnpj = texto(emit, "CNPJ")
            cpf = texto(emit, "CPF")
            documento = cnpj or cpf
            if not documento:
                print(f"Sem documento em {arquivo.name}")
                erros += 1
                continue
            
            ender = filho(emit, "enderEmit")
            
            fornecedores[documento] = {
                "arquivo_origem": arquivo.name,
                "emitente_documento": documento,
                "emitente_nome": texto(emit, "xNome"),
                "emitente_nome_fantasia": texto(emit, "xFant"),
                "emitente_municipio": texto(ender, "xMun") if ender is not None else None,
                "emitente_uf": texto(ender, "UF") if ender is not None else None,
                "emitente_bairro": texto(ender, "xBairro") if ender is not None else None,
            }
        
        except Exception as e:
            print(f"Erro em {arquivo.name}: {e}")
            erros += 1
    
    print(f"Fornecedores únicos encontrados: {len(fornecedores)}")
    print(f"Erros: {erros}")
    
    return list(fornecedores.values())

# ============================================================
# CARGA — STAGING (staging_nfe.tabela_nfe)
# ============================================================
def carregar_no_staging():
    """Carrega os fornecedores extraídos na tabela staging_nfe.tabela_nfe."""
    fornecedores = extrair_fornecedores()
    
    if not fornecedores:
        raise ValueError("Nenhum fornecedor extraído.")
    
    df = pd.DataFrame(fornecedores)
    print(f"Total de fornecedores: {len(df)}")
    print(df.head().to_string())
    
    hook = PostgresHook(postgres_conn_id=CONN_ID)
    engine = hook.get_sqlalchemy_engine()
    
    
    df.to_sql(
        'tabela_nfe',
        engine,
        schema= 'staging_nfe',
        if_exists='append',
        index=False,
        method='multi',
        chunksize=500
    )
    
    print(f"Total de registros gravados no staging: {len(df)}")

# ============================================================
# DAG
# ============================================================
with DAG(
    dag_id='dag_extrator_nfe',
    default_args=default_args,
    description='Extrai dados de NF-e e carrega no staging (incremental)',
    schedule='@once',
    start_date=datetime(2025, 1, 1),
    catchup=False,
    tags=['nfe', 'extrator', 'staging'],
) as dag:

    # Fase 1 — Fornecedores
    task_carregar_fornecedores = PythonOperator(
        task_id='carregar_fornecedores_staging',
        python_callable=carregar_no_staging,
    )