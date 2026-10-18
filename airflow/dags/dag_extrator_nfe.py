import hashlib
import logging
import os
from collections import Counter
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path

from airflow import DAG
from airflow.providers.standard.operators.python import PythonOperator
from airflow.providers.postgres.hooks.postgres import PostgresHook
from lxml import etree
from sqlalchemy import MetaData, Table, func, select
from sqlalchemy.dialects.postgresql import insert

# ============================================================
# CONFIGURAÇÕES
# ============================================================
PASTA_DATA = Path("/opt/airflow/data")
PASTA_XMLS = PASTA_DATA / "inbox"
PASTA_PROCESSADOS = PASTA_DATA / "processed"
PASTA_FALHAS = PASTA_DATA / "failed"

# True (fase de testes): os XMLs são COPIADOS para processed/failed e a inbox
#   fica intacta. A cada execução a inbox inteira é relida; o que já foi
#   classificado não é copiado de novo.
# False (rotina normal): os XMLs são MOVIDOS; a inbox passa a conter só o que
#   não foi concluído, inclusive falhas técnicas a tentar de novo.
MANTER_INBOX = True

SCHEMA_STAGING = "staging_nfe"
TABELA_STAGING = "tabela_nfe"
CONN_ID = "fiscalmind_dw"

# Colunas que a DAG grava. Se faltar alguma no banco, a DAG para antes
# de ler qualquer XML (ver BD/staging_nfe_itens.sql).
COLUNAS_OBRIGATORIAS = {
    "chave_nfe", "id_nfe", "numero_item", "modelo", "tp_nf", "fin_nfe",
    "natureza_operacao", "notas_referenciadas", "valor_total_nota",
    "qtd_itens_nota", "codigo_barras_tributavel", "unidade_tributavel",
    "quantidade_tributavel", "valor_unitario_tributavel", "origem_mercadoria",
    "valor_frete_item", "valor_seguro_item", "valor_outras_despesas_item",
    "valor_icms_item", "valor_icms_st_item", "valor_ipi_item",
    "valor_pis_item", "valor_cofins_item",
}

log = logging.getLogger(__name__)

default_args = {
    'owner': 'virla',
    'depends_on_past': False,
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
}


class NotaInconsistente(ValueError):
    """Conteúdo do XML inválido ou em conflito com a staging (vai para failed)."""


# ============================================================
# FUNÇÕES AUXILIARES
# ============================================================
def nome_tag(tag):
    if isinstance(tag, str):
        return tag.rsplit("}", 1)[-1]
    return ""  # comentários e instruções de processamento


def filho(elemento, nome):
    if elemento is None:
        return None
    return next((item for item in elemento if nome_tag(item.tag) == nome), None)


def filhos(elemento, nome):
    if elemento is None:
        return []
    return [item for item in elemento if nome_tag(item.tag) == nome]


def primeiro_grupo(elemento):
    """Primeiro filho de verdade (ex.: ICMS00, ICMSSN102, PISAliq, PISNT)."""
    if elemento is None:
        return None
    return next((item for item in elemento if nome_tag(item.tag)), None)


def texto(elemento, nome):
    encontrado = filho(elemento, nome)
    if encontrado is None:
        return None
    valor = (encontrado.text or "").strip()
    return valor if valor else None


def numero(elemento, nome):
    """Converte o texto de uma tag numérica em Decimal.

    Tag ausente -> None. Tag presente com valor inválido -> erro,
    para que um valor de compra não seja perdido em silêncio.
    """
    valor = texto(elemento, nome)
    if valor is None:
        return None
    try:
        return Decimal(valor)
    except InvalidOperation:
        raise NotaInconsistente(f"valor numérico inválido em {nome}: {valor!r}")


def data_hora(valor):
    """Converte dhEmi (ex.: 2026-06-26T11:29:05-03:00) ou dEmi em datetime."""
    if not valor:
        return None
    try:
        return datetime.fromisoformat(valor)
    except ValueError:
        return None


# ============================================================
# 1. CABEÇALHO E IDENTIFICADOR DE 28 CARACTERES
# ============================================================
def montar_id_nfe(documento, modelo, serie, numero_nota):
    """CNPJ/CPF (14) + modelo (2) + série (3) + número (9)."""
    if not all((documento, modelo, serie, numero_nota)):
        raise NotaInconsistente("emit/CNPJ(CPF), ide/mod, ide/serie ou ide/nNF ausente")
    documento = documento.strip().upper()
    if len(documento) not in (11, 14) or not documento.isalnum():
        raise NotaInconsistente(f"documento do emitente inválido: {documento!r}")
    if not (modelo.isdigit() and serie.isdigit() and numero_nota.isdigit()):
        raise NotaInconsistente("modelo, série ou número não numérico")
    if len(modelo) > 2 or len(serie) > 3 or len(numero_nota) > 9:
        raise NotaInconsistente("modelo, série ou número maior que o permitido")
    return documento.zfill(14) + modelo.zfill(2) + serie.zfill(3) + numero_nota.zfill(9)


def ler_cabecalho(arquivo):
    """Lê o XML e valida chave, ide e emit. Os itens ainda não são montados."""
    parser = etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=True)
    raiz = etree.parse(str(arquivo), parser).getroot()  # XML malformado: XMLSyntaxError

    inf = next((e for e in raiz.iter() if nome_tag(e.tag) == "infNFe"), None)
    if inf is None:
        raise NotaInconsistente("sem infNFe")

    chave = (inf.get("Id") or "").removeprefix("NFe").strip().upper()
    # Mesmo formato do CHECK ck_staging_chave_formato (aceita CNPJ alfanumérico)
    if (len(chave) != 44 or not chave[:6].isdigit()
            or not chave[6:18].isalnum() or not chave[18:].isdigit()):
        raise NotaInconsistente(f"chave de acesso inválida: {chave!r}")

    ide = filho(inf, "ide")
    emit = filho(inf, "emit")
    if ide is None or emit is None:
        raise NotaInconsistente("sem ide ou emit")

    documento = texto(emit, "CNPJ") or texto(emit, "CPF")
    id_nfe = montar_id_nfe(documento, texto(ide, "mod"), texto(ide, "serie"), texto(ide, "nNF"))
    if id_nfe != chave[6:34]:
        raise NotaInconsistente(
            f"id_nfe montado ({id_nfe}) diverge das posições 7-34 da chave ({chave[6:34]})")

    return {"inf": inf, "ide": ide, "emit": emit, "dest": filho(inf, "dest"),
            "chave": chave, "id_nfe": id_nfe, "documento": documento}


# ============================================================
# 2. EXTRAÇÃO DOS ITENS (somente para notas novas)
# ============================================================
def extrair_itens(arquivo, cab):
    """Devolve uma linha por item: fornecedor, produto e compras."""
    inf, ide, emit, dest = cab["inf"], cab["ide"], cab["emit"], cab["dest"]
    ender = filho(emit, "enderEmit")
    icms_tot = filho(filho(inf, "total"), "ICMSTot")
    dets = filhos(inf, "det")
    if not dets:
        raise NotaInconsistente("nota sem itens")

    referenciadas = [r for r in (texto(ref, "refNFe") for ref in filhos(ide, "NFref")) if r]

    # Dados que se repetem em todos os itens da nota
    cabecalho = {
        "chave_nfe": cab["chave"],
        "numero_nota": texto(ide, "nNF"),
        "serie": texto(ide, "serie"),
        "modelo": texto(ide, "mod"),
        "tp_nf": texto(ide, "tpNF"),
        "fin_nfe": texto(ide, "finNFe"),
        "natureza_operacao": texto(ide, "natOp"),
        "notas_referenciadas": referenciadas or None,
        "data_emissao": data_hora(texto(ide, "dhEmi") or texto(ide, "dEmi")),
        "arquivo_origem": arquivo.name,
        "valor_total_nota": numero(icms_tot, "vNF"),
        "qtd_itens_nota": len(dets),
        "emitente_documento": cab["documento"],
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
    for det in dets:
        prod = filho(det, "prod")
        n_item = (det.get("nItem") or "").strip()
        if prod is None or not n_item.isdigit() or int(n_item) < 1:
            raise NotaInconsistente(f"item sem prod ou com nItem inválido ({n_item!r})")

        imposto = filho(det, "imposto")
        icms = primeiro_grupo(filho(imposto, "ICMS"))   # ICMS00, ICMS10, ICMSSN102...
        ipi = filho(filho(imposto, "IPI"), "IPITrib")
        pis = primeiro_grupo(filho(imposto, "PIS"))     # PISAliq, PISNT, PISOutr...
        cofins = primeiro_grupo(filho(imposto, "COFINS"))

        linhas.append({
            **cabecalho,
            "numero_item": int(n_item),
            # Produto
            "codigo_produto": texto(prod, "cProd"),
            "descricao_produto": texto(prod, "xProd"),
            "ncm": texto(prod, "NCM"),
            "cest": texto(prod, "CEST"),
            "codigo_barras": texto(prod, "cEAN"),
            "codigo_barras_tributavel": texto(prod, "cEANTrib"),
            "unidade_comercial": texto(prod, "uCom"),
            "unidade_tributavel": texto(prod, "uTrib"),
            "quantidade_tributavel": numero(prod, "qTrib"),
            "valor_unitario_tributavel": numero(prod, "vUnTrib"),
            "origem_mercadoria": texto(icms, "orig"),
            # Compras
            "cfop": texto(prod, "CFOP"),
            "quantidade": numero(prod, "qCom"),
            "valor_unitario": numero(prod, "vUnCom"),
            "valor_produto": numero(prod, "vProd"),
            "valor_desconto": numero(prod, "vDesc"),
            "valor_frete_item": numero(prod, "vFrete"),
            "valor_seguro_item": numero(prod, "vSeg"),
            "valor_outras_despesas_item": numero(prod, "vOutro"),
            "valor_icms_item": numero(icms, "vICMS"),
            "valor_icms_st_item": numero(icms, "vICMSST"),
            "valor_ipi_item": numero(ipi, "vIPI"),
            "valor_pis_item": numero(pis, "vPIS"),
            "valor_cofins_item": numero(cofins, "vCOFINS"),
        })

    itens = [linha["numero_item"] for linha in linhas]
    if len(itens) != len(set(itens)):
        raise NotaInconsistente("nItem repetido na mesma nota")
    return linhas


# ============================================================
# 3. ARQUIVAMENTO (processed / failed), sem sobrescrever nada
# ============================================================
def sha256(caminho):
    return hashlib.sha256(Path(caminho).read_bytes()).hexdigest()


def mesmo_conteudo(caminho, hash_origem):
    return Path(caminho).is_file() and sha256(caminho) == hash_origem


def arquivar(arquivo, pasta, motivo=None):
    """Copia o XML para a pasta e confere a cópia; nunca sobrescreve.

    - Se o mesmo arquivo (mesmo conteúdo) já estiver na pasta, não copia de novo.
    - Se o nome estiver ocupado por outro conteúdo, usa <nome>__<sha256[:16]>.xml.
    - A cópia é criada em modo exclusivo e conferida pelo SHA-256.
    - Com MANTER_INBOX = False, o original só é apagado depois da cópia conferida.
    Qualquer falha gera exceção e o original permanece na inbox.
    """
    pasta.mkdir(parents=True, exist_ok=True)
    hash_origem = sha256(arquivo)

    destino = None
    for candidato in (pasta / arquivo.name,
                      pasta / f"{arquivo.stem}__{hash_origem[:16]}{arquivo.suffix}"):
        if mesmo_conteudo(candidato, hash_origem):
            destino = candidato  # já arquivado antes
            break
        if not candidato.exists():
            with open(candidato, "xb") as saida:  # "x": falha se o arquivo existir
                saida.write(arquivo.read_bytes())
                saida.flush()
                os.fsync(saida.fileno())
            if not mesmo_conteudo(candidato, hash_origem):
                candidato.unlink()
                raise OSError(f"cópia de {arquivo.name} para {pasta} não conferiu")
            destino = candidato
            break
    if destino is None:
        raise FileExistsError(
            f"{arquivo.name}: nomes de destino ocupados por outro conteúdo em {pasta}")

    if motivo:
        Path(f"{destino}.erro.txt").write_text(
            f"{datetime.now().isoformat(timespec='seconds')}\n{motivo}\n", encoding="utf-8")
    if not MANTER_INBOX:
        arquivo.unlink()
    return destino


# ============================================================
# 4. CONSULTA DA NOTA NA STAGING PELO ÍNDICE DE 28 CARACTERES
# ============================================================
def consultar_nota(engine, tabela, id_nfe):
    """Situação da nota no banco: chaves, itens gravados, qtd esperada e arquivos."""
    with engine.connect() as conexao:
        return conexao.execute(
            select(tabela.c.chave_nfe,
                   func.count().label("itens"),
                   func.min(tabela.c.qtd_itens_nota).label("qtd_min"),
                   func.max(tabela.c.qtd_itens_nota).label("qtd_max"),
                   func.array_agg(func.distinct(tabela.c.arquivo_origem)).label("arquivos"))
            .where(tabela.c.id_nfe == id_nfe)
            .group_by(tabela.c.chave_nfe)
        ).all()


# ============================================================
# CARGA — STAGING (staging_nfe.tabela_nfe)
# ============================================================
def carregar_no_staging():
    """Carrega cada NF-e nova na staging, uma nota por vez.

    Para cada XML:
      1. lê o cabeçalho e confere o id_nfe (28) com a chave (44);
      2. confere se a nota já foi CONCLUÍDA nesta execução;
      3. consulta a staging pelo id_nfe e confere se a nota existente está completa;
      4. se é nova, extrai os itens e grava todos numa transação (tudo ou nada).

    Destino dos arquivos:
      processed/  nota gravada com sucesso (ou o mesmo arquivo que a gravou antes);
      failed/     duplicada, inconsistente ou ilegível, com <arquivo>.erro.txt;
      inbox/      falha técnica (banco, disco...): tentada de novo na próxima execução.
    Rodar a DAG de novo não duplica nem sobrescreve nada.
    """
    arquivos = sorted(PASTA_XMLS.rglob("*.xml"))
    if not arquivos:
        log.info("Nenhum XML em %s: nada a processar.", PASTA_XMLS)
        return

    engine = PostgresHook(postgres_conn_id=CONN_ID).get_sqlalchemy_engine()
    tabela = Table(TABELA_STAGING, MetaData(), schema=SCHEMA_STAGING, autoload_with=engine)

    faltando = COLUNAS_OBRIGATORIAS - set(tabela.c.keys())
    if faltando:
        raise RuntimeError(
            "A staging não tem as colunas novas. Siga a implantação descrita no "
            f"cabeçalho de BD/staging_nfe_itens.sql. Faltando: {sorted(faltando)}")

    resumo = Counter()
    concluidas = {}  # id_nfe -> (chave, arquivo): só notas com carga confirmada ou verificada

    log.info("Encontrados %d arquivos XML.", len(arquivos))

    for arquivo in arquivos:
        resumo["arquivos_lidos"] += 1
        etapa = "leitura"
        try:
            cab = ler_cabecalho(arquivo)
            id_nfe, chave = cab["id_nfe"], cab["chave"]

            # 2. Nota já concluída nesta execução
            if id_nfe in concluidas:
                chave_vista, arquivo_visto = concluidas[id_nfe]
                if chave_vista != chave:
                    raise NotaInconsistente(
                        f"id_nfe {id_nfe} com duas chaves nesta execução: "
                        f"{chave_vista} ({arquivo_visto}) e {chave}")
                etapa = "arquivamento"
                arquivar(arquivo, PASTA_FALHAS,
                         f"Duplicada: a nota {chave} já foi concluída nesta execução "
                         f"pelo arquivo {arquivo_visto}.")
                resumo["duplicadas"] += 1
                log.warning("Duplicada nesta execução: %s (nota de %s)", arquivo.name, arquivo_visto)
                continue

            # 3. Consulta pelo índice de 28 caracteres
            etapa = "consulta"
            existentes = consultar_nota(engine, tabela, id_nfe)
            if existentes:
                outras = sorted(r.chave_nfe for r in existentes if r.chave_nfe != chave)
                if outras:
                    raise NotaInconsistente(
                        f"id_nfe {id_nfe} já está na staging com outra chave: {', '.join(outras)}")
                nota = existentes[0]
                if nota.qtd_min is None or nota.qtd_min != nota.qtd_max or nota.itens != nota.qtd_min:
                    raise NotaInconsistente(
                        f"nota {chave} está incompleta na staging ({nota.itens} item(ns) gravado(s), "
                        f"qtd_itens_nota={nota.qtd_max}); provável carga de versão anterior: "
                        "faça a recarga descrita em BD/staging_nfe_itens.sql")

                arquivos_banco = set(nota.arquivos or [])
                hash_atual = sha256(arquivo)
                no_processed = PASTA_PROCESSADOS / arquivo.name
                mesmo_arquivo = (arquivo.name in arquivos_banco
                                 and (not no_processed.exists()
                                      or mesmo_conteudo(no_processed, hash_atual)))
                etapa = "arquivamento"
                if mesmo_arquivo:
                    # Este é o arquivo que gravou a nota (execução anterior ou
                    # arquivamento que falhou): só garante que esteja em processed.
                    arquivar(arquivo, PASTA_PROCESSADOS)
                    resumo["ja_carregadas"] += 1
                    log.info("Já carregada por este mesmo arquivo: %s", arquivo.name)
                else:
                    arquivar(arquivo, PASTA_FALHAS,
                             f"Duplicada: a nota {chave} já está na staging, carregada pelo "
                             f"arquivo {', '.join(sorted(arquivos_banco))}.")
                    resumo["duplicadas"] += 1
                    log.warning("Duplicada (já na staging): %s", arquivo.name)
                concluidas[id_nfe] = (chave, ", ".join(sorted(arquivos_banco)))
                continue

            # 4. Nota nova: extrai e grava tudo ou nada
            etapa = "extração"
            linhas = extrair_itens(arquivo, cab)
            etapa = "gravação"
            with engine.begin() as conexao:
                # Sem alvo: cobre as duas UNIQUE (chave+item e id_nfe+item)
                comando = (insert(tabela).values(linhas)
                           .on_conflict_do_nothing()
                           .returning(tabela.c.numero_item))
                inseridos = len(conexao.execute(comando).all())
                if inseridos != len(linhas):
                    # Exceção dentro do begin(): a transação é desfeita
                    raise NotaInconsistente(
                        f"gravados {inseridos} de {len(linhas)} itens; nota desfeita")

            # Só depois do COMMIT a nota conta como concluída
            concluidas[id_nfe] = (chave, arquivo.name)
            resumo["notas_novas"] += 1
            resumo["itens_novos"] += len(linhas)
            log.info("Carregada: %s (%d itens)", arquivo.name, len(linhas))

            etapa = "arquivamento"
            arquivar(arquivo, PASTA_PROCESSADOS)

        except etree.XMLSyntaxError as e:
            resumo["erro_leitura"] += 1
            log.error("Erro de leitura em %s: %s", arquivo.name, e)
            arquivar_falha(arquivo, f"Erro de leitura do XML: {e}", resumo)
        except NotaInconsistente as e:
            resumo["inconsistentes"] += 1
            log.error("Inconsistência em %s: %s", arquivo.name, e)
            arquivar_falha(arquivo, f"Inconsistência: {e}", resumo)
        except Exception:
            # Falha técnica (banco fora do ar, disco, permissão...): o XML fica na
            # inbox. Se a nota já tinha sido gravada, a próxima execução a encontra
            # pelo id_nfe e apenas completa o arquivamento, sem gravar de novo.
            resumo["erro_tecnico"] += 1
            log.exception("Falha técnica em %s (etapa: %s); arquivo mantido na inbox",
                          arquivo.name, etapa)

    log.info(
        "Resumo: arquivos lidos=%d | notas novas=%d (itens=%d) | já carregadas=%d | "
        "duplicadas=%d | inconsistentes=%d | erro de leitura=%d | falha técnica=%d",
        resumo["arquivos_lidos"], resumo["notas_novas"], resumo["itens_novos"],
        resumo["ja_carregadas"], resumo["duplicadas"], resumo["inconsistentes"],
        resumo["erro_leitura"], resumo["erro_tecnico"])

    problemas = resumo["inconsistentes"] + resumo["erro_leitura"] + resumo["erro_tecnico"]
    if problemas:
        raise RuntimeError(
            f"{problemas} XML(s) com problema. As notas válidas foram gravadas; "
            f"veja o log e a pasta {PASTA_FALHAS}.")


def arquivar_falha(arquivo, motivo, resumo):
    """Envia para failed; se nem isso for possível, o XML fica na inbox."""
    try:
        arquivar(arquivo, PASTA_FALHAS, motivo)
    except Exception:
        resumo["erro_tecnico"] += 1
        log.exception("Não foi possível arquivar %s em failed; mantido na inbox", arquivo.name)


# ============================================================
# DAG
# ============================================================
with DAG(
    dag_id='dag_extrator_nfe',
    default_args=default_args,
    description='Extrai fornecedor, produto e compras das NF-e novas para a staging (uma linha por item)',
    schedule=None,
    start_date=datetime(2025, 1, 1),
    catchup=False,
    max_active_runs=1,  # duas execuções nunca consultam e gravam ao mesmo tempo
    tags=['nfe', 'extrator', 'staging'],
) as dag:

    task_carregar_itens = PythonOperator(
        task_id='carregar_itens_staging',
        python_callable=carregar_no_staging,
    )
