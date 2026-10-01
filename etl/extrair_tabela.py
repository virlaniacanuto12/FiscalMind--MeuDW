"""Extrai itens de NF-e para CSV. Python 3.10+, sem pacotes externos.

Uma linha por det. Não altera XMLs, não carrega o DW e não calcula tributos.
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
    "numero_nota": "nNF", "serie": "serie", "modelo": "mod",
    "natureza_operacao": "natOp", "tipo_nfe": "tpNF",
    "finalidade_nfe": "finNFe", "destino_operacao": "idDest",
    "ambiente": "tpAmb",
}
CAMPOS_EMPRESA = {
    "nome": "xNome", "nome_fantasia": "xFant", "ie": "IE", "crt": "CRT",
}
CAMPOS_ENDERECO = {
    "codigo_municipio": "cMun", "municipio": "xMun",
    "uf": "UF", "bairro": "xBairro",
}
CAMPOS_PRODUTO = {
    "codigo_produto": "cProd", "descricao_produto": "xProd",
    "ncm": "NCM", "cest": "CEST", "cfop": "CFOP",
    "gtin_comercial": "cEAN", "unidade_comercial": "uCom",
    "quantidade_comercial": "qCom", "valor_unitario_comercial": "vUnCom",
    "valor_produto": "vProd", "gtin_tributavel": "cEANTrib",
    "unidade_tributavel": "uTrib", "quantidade_tributavel": "qTrib",
    "valor_unitario_tributavel": "vUnTrib", "valor_desconto": "vDesc",
    "valor_outros": "vOutro", "compoe_total_nota": "indTot",
}
# Totais informados no XML, sem frete, seguro, cobrança ou pagamento.
# Repetem-se nos itens da nota e não devem ser somados linha a linha.
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
    c for c, tag in CAMPOS_PRODUTO.items() if tag.startswith(("q", "v"))
}
COLUNAS_BASE = [
    "arquivo_origem", "chave_nfe", "numero_nota", "serie", "modelo",
    "data_hora_emissao", "data_emissao", "natureza_operacao", "tipo_nfe",
    "finalidade_nfe", "destino_operacao", "ambiente", "status_protocolo",
]
for prefixo in ("emitente", "destinatario"):
    COLUNAS_BASE.extend([
        f"{prefixo}_tipo_documento", f"{prefixo}_documento",
        *[f"{prefixo}_{campo}" for campo in CAMPOS_EMPRESA],
        *[f"{prefixo}_{campo}" for campo in CAMPOS_ENDERECO],
    ])
COLUNAS_BASE.extend(["numero_item", *CAMPOS_PRODUTO])
COLUNAS_BASE.extend(CAMPOS_TOTAIS)
COLUNAS_RELATORIO = ["arquivo_origem", "status", "quantidade_itens", "observacao"]


def formatar_linha_csv(linha, decimal):
    """Muda somente o separador decimal das medidas, sem usar float.

    Identificadores e códigos mantêm seu texto, inclusive zeros iniciais.
    Os dados internos e o XML continuam com a representação original.
    """
    if decimal == "ponto":
        return linha
    resultado = linha.copy()
    for coluna, valor in linha.items():
        fiscal = coluna.startswith(("imposto_", "impostoDevol_"))
        tag = re.sub(r"_\d+$", "", coluna).rsplit("_", 1)[-1]
        medida_fiscal = fiscal and "_atributo_" not in coluna and tag.startswith(("v", "p", "q"))
        medida = coluna in COLUNAS_DECIMAIS_PRODUTO or coluna in CAMPOS_TOTAIS or medida_fiscal
        if medida and re.fullmatch(r"[+-]?[0-9]+(?:\.[0-9]+)?", valor):
            resultado[coluna] = valor.replace(".", ",")
    return resultado


def nome_tag(tag):
    """Remove só o namespace do nome da marcação: {uri}vICMS vira vICMS."""
    return tag.rsplit("}", 1)[-1]


def filho(elemento, nome):
    if elemento is None:
        return None
    return next((e for e in elemento if nome_tag(e.tag) == nome), None)


def texto(elemento, nome):
    encontrado = filho(elemento, nome)
    return (encontrado.text or "").strip() if encontrado is not None else ""


def achatar_grupo(elemento, prefixo):
    """Transforma cada campo terminal em uma coluna, sem somar ou recalcular.

    Ex.: imposto/ICMS/ICMS00/vBC -> imposto_ICMS_ICMS00_vBC.
    Grupos repetidos recebem índices para não sobrescrever os valores.
    """
    resultado = {}

    def visitar(no, caminho):
        for atributo, valor in no.attrib.items():
            resultado[f"{caminho}_atributo_{nome_tag(atributo)}"] = valor
        filhos = list(no)
        if not filhos:
            resultado[caminho] = (no.text or "").strip()
            return
        totais = Counter(nome_tag(e.tag) for e in filhos)
        ocorrencias = Counter()
        for e in filhos:
            nome = nome_tag(e.tag)
            ocorrencias[nome] += 1
            sufixo = f"_{ocorrencias[nome]}" if totais[nome] > 1 else ""
            visitar(e, f"{caminho}_{nome}{sufixo}")

    visitar(elemento, prefixo)
    return resultado


def dados_empresa(inf, grupo, prefixo):
    empresa = filho(inf, grupo)
    endereco = filho(empresa, "enderEmit" if grupo == "emit" else "enderDest")
    documento_tipo = next(
        (tipo for tipo in ("CNPJ", "CPF", "idEstrangeiro") if texto(empresa, tipo)), ""
    )
    dados = {
        f"{prefixo}_tipo_documento": documento_tipo,
        f"{prefixo}_documento": texto(empresa, documento_tipo),
    }
    dados.update({f"{prefixo}_{c}": texto(empresa, tag) for c, tag in CAMPOS_EMPRESA.items()})
    dados.update({f"{prefixo}_{c}": texto(endereco, tag) for c, tag in CAMPOS_ENDERECO.items()})
    return dados


def extrair_arquivo(arquivo, pasta):
    """Lê e prepara os itens de uma NF-e inteira antes de incluí-la na saída."""
    raiz = ET.parse(arquivo).getroot()
    notas = [e for e in raiz.iter() if nome_tag(e.tag) == "infNFe"]
    if len(notas) != 1:
        raise ValueError("Esperada uma NF-e por arquivo (grupo infNFe).")
    inf = notas[0]
    chave = inf.get("Id", "").removeprefix("NFe")
    if not re.fullmatch(r"[0-9]{44}", chave):
        raise ValueError("infNFe/@Id não contém chave com 44 dígitos.")
    ide = filho(inf, "ide")
    if ide is None:
        raise ValueError("Grupo ide ausente.")
    emissao = texto(ide, "dhEmi") or texto(ide, "dEmi")
    if not emissao:
        raise ValueError("Data de emissão ausente.")
    protocolo = next((e for e in raiz.iter() if nome_tag(e.tag) == "infProt"), None)
    totais = filho(filho(inf, "total"), "ICMSTot")
    chave_protocolo = texto(protocolo, "chNFe")
    observacoes = []
    if chave_protocolo and chave_protocolo != chave:
        observacoes.append("Chave do protocolo diverge de infNFe/@Id.")
    if arquivo.stem.isdigit() and len(arquivo.stem) == 44 and arquivo.stem != chave:
        observacoes.append("Nome do arquivo difere da chave interna; usada a chave interna.")
    comuns = {
        "arquivo_origem": arquivo.relative_to(pasta).as_posix(),
        "chave_nfe": chave, "data_hora_emissao": emissao,
        "data_emissao": emissao[:10], "status_protocolo": texto(protocolo, "cStat"),
        **{c: texto(ide, tag) for c, tag in CAMPOS_NOTA.items()},
        **dados_empresa(inf, "emit", "emitente"),
        **dados_empresa(inf, "dest", "destinatario"),
        **{c: texto(totais, tag) for c, tag in CAMPOS_TOTAIS.items()},
    }
    itens = [e for e in inf if nome_tag(e.tag) == "det"]
    if not itens:
        raise ValueError("NF-e sem itens det.")
    linhas = []
    numeros = set()
    for item in itens:
        numero = item.get("nItem", "").strip()
        if not numero.isdigit() or int(numero) < 1:
            raise ValueError("Item sem nItem inteiro positivo.")
        normalizado = int(numero)
        if normalizado in numeros:
            raise ValueError("Número de item repetido na mesma NF-e.")
        numeros.add(normalizado)
        produto = filho(item, "prod")
        if produto is None:
            raise ValueError(f"Item {numero} sem grupo prod.")
        linha = {
            **comuns, "numero_item": numero,
            **{c: texto(produto, tag) for c, tag in CAMPOS_PRODUTO.items()},
        }
        for grupo in ("imposto", "impostoDevol"):
            elemento = filho(item, grupo)
            if elemento is not None:
                linha.update(achatar_grupo(elemento, grupo))
        linhas.append(linha)
    return linhas, observacoes


def gerar_tabela(entrada, saida, decimal="virgula"):
    if decimal not in ("virgula", "ponto"):
        raise ValueError("Separador decimal precisa ser virgula ou ponto.")
    entrada, saida = Path(entrada).resolve(), Path(saida).resolve()
    if not entrada.is_dir():
        raise ValueError(f"Pasta de entrada não encontrada: {entrada}")
    arquivos = sorted(p for p in entrada.rglob("*") if p.is_file() and p.suffix.lower() == ".xml")
    if not arquivos:
        raise ValueError("Nenhum arquivo XML encontrado na pasta de entrada.")
    if saida.suffix.lower() != ".csv":
        raise ValueError("O arquivo de saída precisa ter extensão .csv.")
    relatorio = saida.with_name(saida.stem + "_relatorio.csv")
    saida.parent.mkdir(parents=True, exist_ok=True)
    colunas_extras = set()
    resultados = []
    chaves_vistas = set()
    total_itens = 0
    erros = 0

    # O arquivo temporário guarda as linhas enquanto descobrimos as colunas
    # fiscais. Cada XML é lido uma vez, sem acumular todos os itens em memória.
    with tempfile.TemporaryFile(mode="w+", encoding="utf-8", dir=saida.parent) as temporario:
        for arquivo in arquivos:
            nome = arquivo.relative_to(entrada).as_posix()
            try:
                linhas, observacoes = extrair_arquivo(arquivo, entrada)
            except (ET.ParseError, ValueError, OSError) as erro:
                resultados.append({"arquivo_origem": nome, "status": "erro",
                                   "quantidade_itens": 0, "observacao": str(erro)})
                erros += 1
                continue
            chave = linhas[0]["chave_nfe"]
            if chave in chaves_vistas:
                observacoes.append("Chave repetida em outro arquivo; itens mantidos para conferência.")
            chaves_vistas.add(chave)
            for linha in linhas:
                colunas_extras.update(set(linha) - set(COLUNAS_BASE))
                temporario.write(json.dumps(linha, ensure_ascii=False) + "\n")
            total_itens += len(linhas)
            resultados.append({"arquivo_origem": nome, "status": "processado",
                               "quantidade_itens": len(linhas), "observacao": " ".join(observacoes)})

        # ';' separa colunas; UTF-8 com BOM facilita a abertura com acentos no Excel.
        with saida.open("w", newline="", encoding="utf-8-sig") as destino:
            escritor = csv.DictWriter(destino, fieldnames=COLUNAS_BASE + sorted(colunas_extras), delimiter=";")
            escritor.writeheader()
            temporario.seek(0)
            for linha_json in temporario:
                escritor.writerow(formatar_linha_csv(json.loads(linha_json), decimal))

    with relatorio.open("w", newline="", encoding="utf-8-sig") as destino:
        escritor = csv.DictWriter(destino, fieldnames=COLUNAS_RELATORIO, delimiter=";")
        escritor.writeheader()
        escritor.writerows(resultados)
    resumo = {"arquivos_encontrados": len(arquivos), "arquivos_processados": len(arquivos) - erros,
              "arquivos_com_erro": erros, "itens_extraidos": total_itens,
              "colunas": len(COLUNAS_BASE) + len(colunas_extras),
              "saida": str(saida), "relatorio": str(relatorio)}
    return resumo


def main():
    print("versao_extrator: totais_e_virgula_v2")
    print(f"script_executado: {Path(__file__).resolve()}")
    parser = argparse.ArgumentParser(description="Gera a tabela de itens de NF-e, incluindo CFOP e tributos.")
    parser.add_argument("--input", type=Path, default=PROJETO / "data" / "xml", help="Pasta dos XMLs (inclui subpastas).")
    parser.add_argument("--output", type=Path, default=PROJETO / "data" / "processados" / "tabela_nfe.csv", help="Caminho do CSV de saída.")
    parser.add_argument("--decimal", choices=("virgula", "ponto"), default="virgula", help="Separador decimal das medidas no CSV (padrão: virgula, para planilhas em português).")
    args = parser.parse_args()
    try:
        resumo = gerar_tabela(args.input, args.output, args.decimal)
    except (ValueError, OSError) as erro:
        print(f"Erro: {erro}", file=sys.stderr)
        return 1
    for campo, valor in resumo.items():
        print(f"{campo}: {valor}")
    if resumo["arquivos_com_erro"]:
        print("A saída é parcial. Confira os erros no relatório.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
