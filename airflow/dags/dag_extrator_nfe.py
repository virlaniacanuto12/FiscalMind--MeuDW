import logging
import re
from zoneinfo import ZoneInfo
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
 
from airflow import DAG
from airflow.providers.standard.operators.python import PythonOperator
from airflow.providers.postgres.hooks.postgres import PostgresHook
from lxml import etree
from sqlalchemy import MetaData, Table, func, select
from sqlalchemy.dialects.postgresql import insert
 
logger = logging.getLogger(__name__)

# ============================================================
# CONFIGURAÇÕES
# ============================================================
PASTA_XMLS = Path("/opt/airflow/data/inbox")
PASTA_PROCESSADOS = PASTA_XMLS.parent / "processed"
PASTA_FALHAS = PASTA_XMLS.parent / "failed"
SCHEMA_STAGING = "staging_nfe"
TABELA_STAGING = "tabela_nfe"
CONN_ID = "fiscalmind_dw"
TAMANHO_LOTE = 500
 
# UNIQUE (emitente_documento, modelo, serie, numero_nota, numero_item)
CONSTRAINT_UNICIDADE = "uq_staging_nfe_item"
 
# Mesmo formato do CHECK ck_staging_chave_formato (aceita CNPJ alfanumérico)
FORMATO_CHAVE = re.compile(r"^[0-9]{6}[0-9A-Z]{12}[0-9]{26}$")
 
default_args = {
    'owner': 'virla',
    'depends_on_past': False,
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
}
 
# ============================================================
# FUNÇÕES AUXILIARES
# ============================================================
def verificar_entrada():
    """Verifica as pastas e a existência de XMLs para processamento."""

    if not PASTA_XMLS.is_dir():
        logger.info("Inbox não encontrada: %s", PASTA_XMLS)
        return False

    PASTA_PROCESSADOS.mkdir(parents=True, exist_ok=True)
    PASTA_FALHAS.mkdir(parents=True, exist_ok=True)

    if not any(PASTA_XMLS.glob("*.xml")):
        logger.info("Inbox vazia: nenhum XML para processar.")
        return False

    return True

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
 
def numero(elemento, nome):
    """Converte o texto de uma tag numérica em Decimal (ou None)."""
    valor = texto(elemento, nome)
    if valor is None:
        return None
    try:
        return Decimal(valor)
    except InvalidOperation:
        return None
 
def data_hora(valor):
    """Converte dhEmi (ex.: 2026-06-26T11:29:05-03:00) em datetime."""
    if not valor:
        return None
    try:
        return datetime.fromisoformat(valor)
    except ValueError:
        return None
 
# ============================================================
# EXTRAÇÃO — ITENS DE NF-e
# ============================================================
def extrair_nota(arquivo):
    """Lê um XML e devolve uma lista de linhas (uma por item da nota)."""
    parser = etree.XMLParser(recover=True, huge_tree=True)
    raiz = etree.parse(str(arquivo), parser).getroot()
 
    inf = next((e for e in raiz.iter() if nome_tag(e.tag) == "infNFe"), None)
    if inf is None:
        raise ValueError("sem infNFe")
 
    chave = (inf.get("Id") or "").strip().removeprefix("NFe").strip().upper()
    if not FORMATO_CHAVE.match(chave):
        raise ValueError(f"chave de acesso inválida: {chave!r}")
 
    ide = filho(inf, "ide")
    emit = filho(inf, "emit")
    dest = filho(inf, "dest")
    if emit is None:
        raise ValueError("sem emit")
 
    emitente_documento = texto(emit, "CNPJ") or texto(emit, "CPF")
    if not emitente_documento:
        raise ValueError("emitente sem CNPJ/CPF")

    modelo = texto(ide, "mod")
    serie = texto(ide, "serie")
    numero_nota = texto(ide, "nNF")
    if not (modelo and serie and numero_nota):
        raise ValueError("nota sem modelo, série ou número")
    
    ender = filho(emit, "enderEmit")
 
    # Dados que se repetem em todos os itens da nota
    cabecalho = {
        "chave_nfe": chave,
        "modelo": int(modelo),
        "numero_nota": int(numero_nota),
        "serie": int(serie),
        "data_emissao": data_hora(texto(ide, "dhEmi") or texto(ide, "dEmi")),
        "arquivo_origem": arquivo.name,
        "emitente_documento": emitente_documento,
        "emitente_nome": texto(emit, "xNome"),
        "emitente_nome_fantasia": texto(emit, "xFant"),
        "emitente_ie": texto(emit, "IE"),
        "emitente_crt": texto(emit, "CRT"),
        "emitente_cod_municipio": texto(ender, "cMun"),
        "emitente_municipio": texto(ender, "xMun"),
        "emitente_uf": texto(ender, "UF"),
        "emitente_bairro": texto(ender, "xBairro"),
        "destinatario_documento": texto(dest, "CNPJ") or texto(dest, "CPF"),
        "destinatario_nome": texto(dest, "xNome"),
    }
 
    linhas = []
    for det in (e for e in inf if nome_tag(e.tag) == "det"):
        prod = filho(det, "prod")
        n_item = det.get("nItem")
        if prod is None or not n_item:
            print(f"Item ignorado em {arquivo.name}: det sem prod ou nItem")
            continue
 
        linhas.append({
            **cabecalho,
            "numero_item": int(n_item),
            "codigo_produto": texto(prod, "cProd"),
            "descricao_produto": texto(prod, "xProd"),
            "ncm": texto(prod, "NCM"),
            "cest": texto(prod, "CEST"),
            "codigo_barras": texto(prod, "cEAN"),
            "cfop": texto(prod, "CFOP"),
            "unidade_comercial": texto(prod, "uCom"),
            "quantidade": numero(prod, "qCom"),
            "valor_unitario": numero(prod, "vUnCom"),
            "valor_produto": numero(prod, "vProd"),
            "valor_desconto": numero(prod, "vDesc") or Decimal("0"),
        })
 
    if not linhas:
        raise ValueError("nota sem itens")
 
    return linhas
 
 
def extrair_itens():
    """Percorre todos os XMLs e devolve uma linha por item de nota.
 
    Não remove duplicatas aqui: quem garante a unicidade é o banco,
    pela UNIQUE (id_nfe, numero_item). Se a mesma nota aparecer em
    mais de um arquivo, prevalece a primeira gravada.
    """
    arquivos = sorted(PASTA_XMLS.rglob("*.xml"))
    if not arquivos:
        raise ValueError(f"Nenhum XML encontrado em {PASTA_XMLS}")
 
    print(f"Encontrados {len(arquivos)} arquivos XML.")
 
    itens = []
    notas = set()
    erros = 0
 
    for arquivo in arquivos:
        try:
            linhas = extrair_nota(arquivo)
            itens.extend(linhas)
            notas.add(linhas[0]["chave_nfe"])
        except Exception as e:
            print(f"Erro em {arquivo.name}: {e}")
            erros += 1
 
    emitentes = {linha["emitente_documento"] for linha in itens}
 
    print(f"Notas lidas: {len(notas)}")
    print(f"Itens extraídos: {len(itens)}")
    print(f"Emitentes distintos: {len(emitentes)}")
    print(f"Arquivos com erro: {erros}")
 
    return itens
 
# ============================================================
# CARGA — STAGING (staging_nfe.tabela_nfe)
# ============================================================
def carregar_no_staging():
    """Carrega os itens extraídos em staging_nfe.tabela_nfe.
 
    Item novo é inserido; item já existente (mesmo id_nfe + item)
    é ignorado (ON CONFLICT DO NOTHING), sem sobrescrever o que já
    está gravado. Rodar a DAG de novo não duplica linhas.
    """

    # Verificar se existem as pastas

    # Verificar se existem arquivos XML na INBOX
    # Se não existir sair

    hook = PostgresHook(postgres_conn_id=CONN_ID)
    engine = hook.get_sqlalchemy_engine()
 
    # Referência à tabela existente no PostgreSQL
    # (criada por BD/staging_nfe_itens.sql)
    tabela = Table(
        TABELA_STAGING,
        MetaData(),
        schema=SCHEMA_STAGING,
        autoload_with=engine,
    )
 
    # Verificar se o arquivo já foi processado
    # verificar_chave_nfe(engine, tabela)
    
    # adicionar um laço até o INBOX zerar

    registros = extrair_itens() # Colocar uma quantidade de arquivo
 
    if not registros:
        raise ValueError("Nenhum item extraído.")
 
    inseridos = 0
    with engine.begin() as conexao:
        for i in range(0, len(registros), TAMANHO_LOTE):
            lote = registros[i:i + TAMANHO_LOTE]
 
            comando = (
                insert(tabela)
                .values(lote)
                .on_conflict_do_nothing(constraint=CONSTRAINT_UNICIDADE)
                .returning(tabela.c.numero_item)  # só as linhas realmente inseridas
            )
            inseridos += len(conexao.execute(comando).all())
 
        total = conexao.execute(
            select(func.count()).select_from(tabela)
        ).scalar_one()
 
    print(f"Itens lidos nos XMLs: {len(registros)}")
    print(f"Itens inseridos (novos): {inseridos}")
    print(f"Itens ignorados (já existiam): {len(registros) - inseridos}")
    print(f"Total de itens na staging: {total}")
 
# ============================================================
# DAG
# ============================================================
with DAG(
    dag_id='dag_extrator_nfe',
    default_args=default_args,
    description='Extrai os itens das NF-e e carrega no staging (uma linha por item)',
    schedule=None,
    start_date=datetime(2025, 1, 1),
    catchup=False,
    tags=['nfe', 'extrator', 'staging'],
) as dag:
 
    task_carregar_itens = PythonOperator(
        task_id='carregar_itens_staging',
        python_callable=carregar_no_staging,
    )
