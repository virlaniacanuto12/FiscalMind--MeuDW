"""Extrai itens de NF-e para CSV. Python 3.10+, sem pacotes externos.

Uma linha por item (det). Não altera XMLs, não carrega o DW e não calcula tributos.
Os campos de imposto são preservados pelo caminho completo no XML.
"""

import argparse
import csv
import json
import re
import sys
import tempfile
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path


PROJETO = Path(__file__).resolve().parents[1]

CAMPOS_NOTA = {
    "numero_nota": "nNF",
    "serie": "serie",
    "modelo": "mod",
    "natureza_operacao": "natOp",
    "tipo_nfe": "tpNF",
    "finalidade_nfe": "finNFe",
    "destino_operacao": "idDest",
    "ambiente": "tpAmb",
}

CAMPOS_EMITENTE = {
    "nome": "xNome",
    "nome_fantasia": "xFant",
    "ie": "IE",
    "crt": "CRT",
}

CAMPOS_DESTINATARIO = {
    "nome": "xNome",
    "ie": "IE",
}

CAMPOS_ENDERECO = {
    "codigo_municipio": "cMun",
    "municipio": "xMun",
    "uf": "UF",
    "bairro": "xBairro",
}

CAMPOS_PRODUTO = {
    "codigo_produto": "cProd",
    "descricao_produto": "xProd",
    "ncm": "NCM",
    "cest": "CEST",
    "cfop": "CFOP",
    "gtin_comercial": "cEAN",
    "unidade_comercial": "uCom",
    "quantidade_comercial": "qCom",
    "valor_unitario_comercial": "vUnCom",
    "valor_produto": "vProd",
    "gtin_tributavel": "cEANTrib",
    "unidade_tributavel": "uTrib",
    "quantidade_tributavel": "qTrib",
    "valor_unitario_tributavel": "vUnTrib",
    "valor_desconto": "vDesc",
    "valor_outros": "vOutro",
    "compoe_total_nota": "indTot",
}

# Totais selecionados de ICMSTot.
# Não são extraídos frete, seguro, cobrança ou pagamento.
CAMPOS_TOTAIS = {
    "total_nota_valor_produtos": "vProd",
    "total_nota_valor_final": "vNF",
    "total_nota_valor_desconto": "vDesc",
    "total_nota_valor_outros": "vOutro",
    "total_nota_base_icms": "vBC",
    "total_nota_valor_icms": "vICMS",
    "total_nota_valor_icms_desonerado": "vICMSDeson",
    "total_nota_valor_fcp": "vFCP",
    "total_nota_base_icms_st": "vBCST",
    "total_nota_valor_icms_st": "vST",
    "total_nota_valor_fcp_st": "vFCPST",
    "total_nota_valor_fcp_st_retido": "vFCPSTRet",
    "total_nota_valor_imposto_importacao": "vII",
    "total_nota_valor_ipi": "vIPI",
    "total_nota_valor_ipi_devolvido": "vIPIDevol",
    "total_nota_valor_pis": "vPIS",
    "total_nota_valor_cofins": "vCOFINS",
    "total_nota_valor_aproximado_tributos": "vTotTrib",
}

COLUNAS_DECIMAIS_PRODUTO = {
    coluna
    for coluna, tag in CAMPOS_PRODUTO.items()
    if tag.startswith(("q", "v"))
}

COLUNAS_BASE = [
    "arquivo_origem",
    "chave_nfe",
    "versao_nfe",
    "numero_nota",
    "serie",
    "modelo",
    "data_hora_emissao",
    "data_emissao",
    "natureza_operacao",
    "tipo_nfe",
    "finalidade_nfe",
    "destino_operacao",
    "ambiente",
    "status_protocolo",
    "emitente_tipo_documento",
    "emitente_documento",
    *[f"emitente_{campo}" for campo in CAMPOS_EMITENTE],
    *[f"emitente_{campo}" for campo in CAMPOS_ENDERECO],
    "destinatario_tipo_documento",
    "destinatario_documento",
    *[f"destinatario_{campo}" for campo in CAMPOS_DESTINATARIO],
    *[f"destinatario_{campo}" for campo in CAMPOS_ENDERECO],
    "numero_item",
    *CAMPOS_PRODUTO,
    *CAMPOS_TOTAIS,
]

COLUNAS_RELATORIO = [
    "arquivo_origem",
    "status",
    "quantidade_itens",
    "observacao",
]


def formatar_linha_csv(linha, decimal):
    """Altera somente o separador decimal das medidas."""
    if decimal == "ponto":
        return linha

    resultado = linha.copy()

    for coluna, valor in linha.items():
        fiscal = coluna.startswith(("imposto_", "impostoDevol_"))
        tag = re.sub(r"_\d+$", "", coluna).rsplit("_", 1)[-1]

        medida_fiscal = (
            fiscal
            and "_atributo_" not in coluna
            and tag.startswith(("v", "p", "q"))
        )

        medida = (
            coluna in COLUNAS_DECIMAIS_PRODUTO
            or coluna in CAMPOS_TOTAIS
            or medida_fiscal
        )

        if medida and re.fullmatch(r"[+-]?[0-9]+(?:\.[0-9]+)?", valor):
            resultado[coluna] = valor.replace(".", ",")

    return resultado


def nome_tag(tag):
    """Remove o namespace do nome da tag XML."""
    return tag.rsplit("}", 1)[-1]


def filho(elemento, nome):
    if elemento is None:
        return None

    return next(
        (item for item in elemento if nome_tag(item.tag) == nome),
        None,
    )


def texto(elemento, nome):
    encontrado = filho(elemento, nome)

    if encontrado is None:
        return ""

    return (encontrado.text or "").strip()


def achatar_grupo(elemento, prefixo):
    """Transforma campos terminais de um grupo XML em colunas."""
    resultado = {}

    def visitar(no, caminho):
        for atributo, valor in no.attrib.items():
            resultado[
                f"{caminho}_atributo_{nome_tag(atributo)}"
            ] = valor

        filhos = list(no)

        if not filhos:
            resultado[caminho] = (no.text or "").strip()
            return

        totais = Counter(nome_tag(item.tag) for item in filhos)
        ocorrencias = Counter()

        for item in filhos:
            nome = nome_tag(item.tag)
            ocorrencias[nome] += 1

            sufixo = (
                f"_{ocorrencias[nome]}"
                if totais[nome] > 1
                else ""
            )

            visitar(item, f"{caminho}_{nome}{sufixo}")

    visitar(elemento, prefixo)
    return resultado


def dados_parte(inf, grupo, prefixo):
    parte = filho(inf, grupo)

    if parte is None:
        if grupo == "emit":
            raise ValueError("Grupo emit ausente.")
        return {
            f"{prefixo}_tipo_documento": "",
            f"{prefixo}_documento": "",
            **{
                f"{prefixo}_{campo}": ""
                for campo in CAMPOS_DESTINATARIO
            },
            **{
                f"{prefixo}_{campo}": ""
                for campo in CAMPOS_ENDERECO
            },
        }

    if grupo == "emit":
        campos_parte = CAMPOS_EMITENTE
        endereco = filho(parte, "enderEmit")
        tipos_documento = ("CNPJ", "CPF")
    else:
        campos_parte = CAMPOS_DESTINATARIO
        endereco = filho(parte, "enderDest")
        tipos_documento = ("CNPJ", "CPF", "idEstrangeiro")

    documento_tipo = next(
        (
            tipo
            for tipo in tipos_documento
            if texto(parte, tipo)
        ),
        "",
    )

    dados = {
        f"{prefixo}_tipo_documento": documento_tipo,
        f"{prefixo}_documento": (
            texto(parte, documento_tipo)
            if documento_tipo
            else ""
        ),
    }

    dados.update({
        f"{prefixo}_{campo}": texto(parte, tag)
        for campo, tag in campos_parte.items()
    })

    dados.update({
        f"{prefixo}_{campo}": texto(endereco, tag)
        for campo, tag in CAMPOS_ENDERECO.items()
    })

    return dados


def extrair_arquivo(arquivo, pasta):
    """Lê uma NF-e e prepara uma linha para cada item."""
    raiz = ET.parse(arquivo).getroot()

    notas = [
        elemento
        for elemento in raiz.iter()
        if nome_tag(elemento.tag) == "infNFe"
    ]

    if len(notas) != 1:
        raise ValueError(
            "Esperado exatamente um grupo infNFe no arquivo."
        )

    inf = notas[0]

    identificador = (inf.get("Id") or "").strip()

    if not identificador.startswith("NFe"):
        raise ValueError("Atributo infNFe/@Id ausente ou inválido.")

    chave = identificador[3:]

    if not re.fullmatch(r"[A-Za-z0-9]{44}", chave):
        raise ValueError(
            "Chave de acesso em infNFe/@Id deve ter 44 caracteres alfanuméricos."
        )

    versao_nfe = (inf.get("versao") or "").strip()

    ide = filho(inf, "ide")

    if ide is None:
        raise ValueError("Grupo ide ausente.")

    emissao = texto(ide, "dhEmi") or texto(ide, "dEmi")

    if not emissao:
        raise ValueError("Data de emissão ausente.")

    protocolo = next(
        (
            elemento
            for elemento in raiz.iter()
            if nome_tag(elemento.tag) == "infProt"
        ),
        None,
    )

    chave_protocolo = texto(protocolo, "chNFe")

    observacoes = []

    if chave_protocolo and chave_protocolo != chave:
        observacoes.append(
            "Chave do protocolo diverge da chave de infNFe."
        )

    totais = filho(
        filho(inf, "total"),
        "ICMSTot",
    )

    comuns = {
        "arquivo_origem": arquivo.relative_to(pasta).as_posix(),
        "chave_nfe": chave,
        "versao_nfe": versao_nfe,
        "data_hora_emissao": emissao,
        "data_emissao": emissao[:10],
        "status_protocolo": texto(protocolo, "cStat"),
        **{
            campo: texto(ide, tag)
            for campo, tag in CAMPOS_NOTA.items()
        },
        **dados_parte(inf, "emit", "emitente"),
        **dados_parte(inf, "dest", "destinatario"),
        **{
            campo: texto(totais, tag)
            for campo, tag in CAMPOS_TOTAIS.items()
        },
    }

    itens = [
        elemento
        for elemento in inf
        if nome_tag(elemento.tag) == "det"
    ]

    if not itens:
        raise ValueError("NF-e sem itens det.")

    linhas = []
    numeros_itens = set()

    for item in itens:
        numero = (item.get("nItem") or "").strip()

        if not numero.isdigit() or int(numero) < 1:
            raise ValueError(
                "Item com atributo nItem ausente ou inválido."
            )

        numero_normalizado = int(numero)

        if numero_normalizado in numeros_itens:
            raise ValueError(
                "Número de item repetido na mesma NF-e."
            )

        numeros_itens.add(numero_normalizado)

        produto = filho(item, "prod")

        if produto is None:
            raise ValueError(
                f"Item {numero} sem grupo prod."
            )

        linha = {
            **comuns,
            "numero_item": numero,
            **{
                campo: texto(produto, tag)
                for campo, tag in CAMPOS_PRODUTO.items()
            },
        }

        for grupo in ("imposto", "impostoDevol"):
            elemento = filho(item, grupo)

            if elemento is not None:
                linha.update(
                    achatar_grupo(elemento, grupo)
                )

        linhas.append(linha)

    return linhas, observacoes


def gerar_tabela(entrada, saida, decimal="ponto"):
    if decimal not in ("virgula", "ponto"):
        raise ValueError(
            "Separador decimal deve ser 'virgula' ou 'ponto'."
        )

    entrada = Path(entrada).resolve()
    saida = Path(saida).resolve()

    if not entrada.is_dir():
        raise ValueError(
            f"Pasta de entrada não encontrada: {entrada}"
        )

    arquivos = sorted(
        arquivo
        for arquivo in entrada.rglob("*")
        if arquivo.is_file()
        and arquivo.suffix.lower() == ".xml"
    )

    if not arquivos:
        raise ValueError(
            "Nenhum arquivo XML encontrado na pasta de entrada."
        )

    if saida.suffix.lower() != ".csv":
        raise ValueError(
            "O arquivo de saída deve ter extensão .csv."
        )

    relatorio = saida.with_name(
        f"{saida.stem}_relatorio.csv"
    )

    saida.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    colunas_extras = set()
    resultados = []
    chaves_vistas = set()
    total_itens = 0
    erros = 0

    with tempfile.TemporaryFile(
        mode="w+",
        encoding="utf-8",
        dir=saida.parent,
    ) as temporario:

        for arquivo in arquivos:
            nome = arquivo.relative_to(entrada).as_posix()

            try:
                linhas, observacoes = extrair_arquivo(
                    arquivo,
                    entrada,
                )
            except (
                ET.ParseError,
                ValueError,
                OSError,
            ) as erro:
                resultados.append({
                    "arquivo_origem": nome,
                    "status": "erro",
                    "quantidade_itens": 0,
                    "observacao": str(erro),
                })
                erros += 1
                continue

            chave = linhas[0]["chave_nfe"]

            if chave in chaves_vistas:
                observacoes.append(
                    "Chave de acesso repetida em outro arquivo da mesma execução."
                )

            chaves_vistas.add(chave)

            for linha in linhas:
                colunas_extras.update(
                    set(linha) - set(COLUNAS_BASE)
                )

                temporario.write(
                    json.dumps(
                        linha,
                        ensure_ascii=False,
                    )
                    + "\n"
                )

            total_itens += len(linhas)

            resultados.append({
                "arquivo_origem": nome,
                "status": "processado",
                "quantidade_itens": len(linhas),
                "observacao": " ".join(observacoes),
            })

        with saida.open(
            "w",
            newline="",
            encoding="utf-8-sig",
        ) as destino:
            escritor = csv.DictWriter(
                destino,
                fieldnames=(
                    COLUNAS_BASE
                    + sorted(colunas_extras)
                ),
                delimiter=";",
            )

            escritor.writeheader()
            temporario.seek(0)

            for linha_json in temporario:
                escritor.writerow(
                    formatar_linha_csv(
                        json.loads(linha_json),
                        decimal,
                    )
                )

    with relatorio.open(
        "w",
        newline="",
        encoding="utf-8-sig",
    ) as destino:
        escritor = csv.DictWriter(
            destino,
            fieldnames=COLUNAS_RELATORIO,
            delimiter=";",
        )

        escritor.writeheader()
        escritor.writerows(resultados)

    return {
        "arquivos_encontrados": len(arquivos),
        "arquivos_processados": len(arquivos) - erros,
        "arquivos_com_erro": erros,
        "itens_extraidos": total_itens,
        "colunas": len(COLUNAS_BASE) + len(colunas_extras),
        "saida": str(saida),
        "relatorio": str(relatorio),
    }


def main():
    print("versao_extrator: v3")
    print(f"script_executado: {Path(__file__).resolve()}")

    parser = argparse.ArgumentParser(
        description=(
            "Gera tabela intermediária de itens de NF-e, "
            "incluindo CFOP e tributos."
        )
    )

    parser.add_argument(
        "--input",
        type=Path,
        default=PROJETO / "data" / "inbox",
        help="Pasta de entrada dos XMLs.",
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=(
            PROJETO
            / "data"
            / "processados"
            / "tabela_nfe.csv"
        ),
        help="Arquivo CSV de saída.",
    )

    parser.add_argument(
        "--decimal",
        choices=("virgula", "ponto"),
        default="ponto",
        help="Separador decimal das medidas no CSV.",
    )

    args = parser.parse_args()

    try:
        resumo = gerar_tabela(
            args.input,
            args.output,
            args.decimal,
        )
    except (
        ValueError,
        OSError,
    ) as erro:
        print(
            f"Erro: {erro}",
            file=sys.stderr,
        )
        return 1

    for campo, valor in resumo.items():
        print(f"{campo}: {valor}")

    if resumo["arquivos_com_erro"]:
        print(
            "A saída é parcial. Consulte o relatório.",
            file=sys.stderr,
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())