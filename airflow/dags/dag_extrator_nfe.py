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
from sqlalchemy import MetaData, Table, select
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
TAMANHO_LOTE_XML = 10
 
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
# IDENTIFICAÇÃO DA NF-e
# ============================================================
def identificar_xml(arquivo):
    """Obtém a identificação fiscal da NF-e."""

    parser = etree.XMLParser(recover=False, huge_tree=True)
    raiz = etree.parse(str(arquivo), parser).getroot()

    inf = next(
        (e for e in raiz.iter() if nome_tag(e.tag) == "infNFe"),
        None
    )
    if inf is None:
        raise ValueError("XML sem infNFe")

    chave = (inf.get("Id") or "").strip().removeprefix("NFe").upper()
    if not FORMATO_CHAVE.fullmatch(chave):
        raise ValueError("Chave de acesso inválida")

    ide = filho(inf, "ide")
    emit = filho(inf, "emit")

    emitente = texto(emit, "CNPJ") or texto(emit, "CPF")
    modelo = texto(ide, "mod")
    serie = texto(ide, "serie")
    numero_nota = texto(ide, "nNF")

    if not all((emitente, modelo, serie, numero_nota)):
        raise ValueError("Identificação fiscal incompleta")

    try:
        modelo = int(modelo)
        serie = int(serie)
        numero_nota = int(numero_nota)
    except ValueError as erro:
        raise ValueError(
            "Modelo, série ou número da nota inválido"
        ) from erro

    esperado = (
        emitente.upper().zfill(14)
        + f"{modelo:02d}{serie:03d}{numero_nota:09d}"
    )

    if esperado != chave[6:34]:
        raise ValueError(
            "CNPJ, modelo, série ou número divergem da chave de acesso"
        )

    return {
        "chave_nfe": chave,
        "emitente_documento": emitente,
        "modelo": modelo,
        "serie": serie,
        "numero_nota": numero_nota,
    }

def consultar_nota_staging(conexao, tabela, identificacao):
    """Consulta os itens da NF-e na staging."""

    consulta = select(
        tabela.c.chave_nfe,
        tabela.c.numero_item
    ).where(
        tabela.c.emitente_documento == identificacao["emitente_documento"],
        tabela.c.modelo == identificacao["modelo"],
        tabela.c.serie == identificacao["serie"],
        tabela.c.numero_nota == identificacao["numero_nota"]
    )

    return conexao.execute(consulta).all()

def classificar_xmls(conexao, tabela, arquivos):
    """Classifica XMLs sem mover ou excluir arquivos."""
    pendentes = []
    encontrados = []
    invalidos = []

    for arquivo in arquivos:
        try:
            identificacao = identificar_xml(arquivo)
        except (ValueError, etree.XMLSyntaxError) as erro:
            invalidos.append((arquivo, str(erro)))
            continue

        registros = consultar_nota_staging(
            conexao, tabela, identificacao
        )

        if registros:
            encontrados.append(
                (arquivo, identificacao, registros)
            )
        else:
            pendentes.append(
                (arquivo, identificacao)
            )

    return pendentes, encontrados, invalidos

def mover_xml(arquivo, pasta_destino):
    """Move o XML sem sobrescrever arquivos existentes."""

    data = datetime.now(
        ZoneInfo("America/Fortaleza")
    ).strftime("%Y-%m-%d")

    pasta_data = pasta_destino / data
    pasta_data.mkdir(parents=True, exist_ok=True)

    destino = pasta_data / arquivo.name
    contador = 1

    while destino.exists():
        destino = pasta_data / (
            f"{arquivo.stem}_{contador}{arquivo.suffix}"
        )
        contador += 1

    arquivo.rename(destino)
    return destino

# ============================================================
# EXTRAÇÃO — ITENS DE NF-e
# ============================================================
def extrair_nota(arquivo):
    """Lê um XML e devolve uma lista de linhas (uma por item da nota)."""
    parser = etree.XMLParser(recover=False, huge_tree=True)
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
            raise ValueError(
                f"Item inválido em {arquivo.name}: det sem prod ou nItem"
            )
 
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

    numeros = [linha["numero_item"] for linha in linhas]

    if len(numeros) != len(set(numeros)):
        raise ValueError(
            f"NF-e com números de itens repetidos: {arquivo.name}"
        )

    return linhas
 
# ============================================================
# CARGA — STAGING (staging_nfe.tabela_nfe)
# ============================================================
def carregar_no_staging():
    """Classifica os XMLs, carrega as notas novas e encaminha os arquivos."""
    if not verificar_entrada():
        return

    engine = PostgresHook(postgres_conn_id=CONN_ID).get_sqlalchemy_engine()
    tabela = Table(
        TABELA_STAGING,
        MetaData(),
        schema=SCHEMA_STAGING,
        autoload_with=engine,
    )
    arquivos = sorted(PASTA_XMLS.glob("*.xml"))
    resumo = {"carregadas": 0, "ja_carregadas": 0, "invalidas": 0, "itens": 0}

    # 1. Identifica todos os arquivos e consulta as notas já cadastradas.
    with engine.connect() as conexao:
        pendentes, encontrados, invalidos = classificar_xmls(
            conexao, tabela, arquivos
        )

    # 2. Trata arquivos cuja nota já existia na staging.
    for arquivo, identificacao, registros in encontrados:
        if any(chave != identificacao["chave_nfe"] for chave, _ in registros):
            destino = mover_xml(arquivo, PASTA_FALHAS)
            resumo["invalidas"] += 1
            logger.warning("Chave divergente: %s -> %s", arquivo.name, destino)
        else:
            arquivo.unlink()
            resumo["ja_carregadas"] += 1
            logger.info("Nota já cadastrada, XML excluído: %s", arquivo.name)

    for arquivo, motivo in invalidos:
        destino = mover_xml(arquivo, PASTA_FALHAS)
        resumo["invalidas"] += 1
        logger.warning("XML inválido: %s | %s | %s", arquivo.name, motivo, destino)

    # TODO Remover o LOTE porque com o INSERT em BATCH vamos processar um XML por vez
    # 3. Processa os pendentes em grupos de 10 arquivos XML.
    for inicio in range(0, len(pendentes), TAMANHO_LOTE_XML):
        lote = pendentes[inicio:inicio + TAMANHO_LOTE_XML]
        logger.info("Lote de %s XMLs pendentes", len(lote))

        for arquivo, identificacao in lote:
            # TODO Verificar se é necessario
            # # Outra cópia da nota pode ter sido carregada neste mesmo lote.
            # with engine.connect() as conexao:
            #     registros = consultar_nota_staging(conexao, tabela, identificacao)

            # if registros:
            #     if any(chave != identificacao["chave_nfe"] for chave, _ in registros):
            #         destino = mover_xml(arquivo, PASTA_FALHAS)
            #         resumo["invalidas"] += 1
            #         logger.warning("Chave divergente: %s -> %s", arquivo.name, destino)
            #     else:
            #         arquivo.unlink()
            #         resumo["ja_carregadas"] += 1
            #         logger.info("Nota já cadastrada, XML excluído: %s", arquivo.name)
            #     continue

            try:
                linhas = extrair_nota(arquivo)
            except (ValueError, etree.XMLSyntaxError) as erro:
                destino = mover_xml(arquivo, PASTA_FALHAS)
                resumo["invalidas"] += 1
                logger.warning("XML inválido: %s | %s | %s", arquivo.name, erro, destino)
                continue

            # TODO Mudar o loop por um INSERT em BATCH
            # Uma transação por nota. Qualquer erro faz ROLLBACK.
            inseridos = 0
            with engine.begin() as conexao:
                for i in range(0, len(linhas), TAMANHO_LOTE):
                    comando = (
                        insert(tabela)
                        .values(linhas[i:i + TAMANHO_LOTE])
                        .on_conflict_do_nothing(constraint=CONSTRAINT_UNICIDADE)
                        .returning(tabela.c.numero_item)
                    )
                    inseridos += len(conexao.execute(comando).all())

                if inseridos != len(linhas):
                    raise RuntimeError(
                        f"Itens inseridos ({inseridos}) diferentes dos "
                        f"extraídos ({len(linhas)}): {arquivo.name}"
                    )

            # Só move a nota nova para processed após o COMMIT.
            destino = mover_xml(arquivo, PASTA_PROCESSADOS)
            resumo["carregadas"] += 1
            resumo["itens"] += inseridos
            logger.info("NF-e carregada: %s | %s itens -> %s", arquivo.name, inseridos, destino)

    logger.info(
        "Resumo: %s XMLs | %s notas carregadas | %s já cadastradas "
        "| %s inválidos | %s itens inseridos",
        len(arquivos), resumo["carregadas"], resumo["ja_carregadas"],
        resumo["invalidas"], resumo["itens"],
    )

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
    max_active_runs=1,
    tags=['nfe', 'extrator', 'staging'],
) as dag:
 
    task_carregar_itens = PythonOperator(
        task_id='carregar_itens_staging',
        python_callable=carregar_no_staging,
    )
