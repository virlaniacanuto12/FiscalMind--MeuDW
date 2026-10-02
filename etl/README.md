# Extrator da tabela de NF-e — FiscalMind

## Objetivo

Gerar uma tabela intermediária com uma linha por item (`det`) de uma NF-e.
O programa lê todos os XMLs da pasta indicada e de suas subpastas.
Esta extração pode ser executada diretamente com Python, sem Docker ou Airflow.

## Requisitos e localização

- Python 3.10 ou superior.
- Nenhuma biblioteca adicional: usa apenas módulos da biblioteca padrão.
- O script confirmado nesta etapa é `etl/extrair_tabela_verificada.py`, dentro
  da pasta `etl` do repositório.
- Os XMLs do projeto estão em `data/xml`.

No terminal do VS Code, aberto na raiz `FiscalMind--MeuDW`:

```powershell
python --version
python etl/extrair_tabela_verificada.py
```

Se o Windows oferecer o Python pelo comando `py`, use:

```powershell
py -3 etl/extrair_tabela_verificada.py
```

Saídas padrão:

- `data/processados/tabela_nfe.csv`: uma linha por item, separador ponto e vírgula
  (`;`) e vírgula como separador decimal, preservando a precisão.
- `data/processados/tabela_nfe_relatorio.csv`: uma linha por arquivo, com resultado e observações.


É possível escolher outras pastas, por caminhos relativos ou absolutos:

```powershell
python etl/extrair_tabela_verificada.py --input data/xml --output data/processados/teste.csv
```

## O que é extraído

1. Origem: nome/caminho do arquivo, chave interna da NF-e e número do item.
2. Nota: número, série, modelo, emissão, natureza, tipo, finalidade, destino da
   operação, ambiente e código de status do protocolo quando presente.
3. Emitente e destinatário: documento, nome, fantasia quando presente, IE,
   CRT quando presente, município, UF e bairro.
4. Produto: código, descrição, NCM, CEST, CFOP, GTIN, unidades, quantidades,
   preços comerciais/tributáveis, valor do produto, desconto, outras despesas
   do item (`vOutro`) e indicador de composição do total.
5. Todos os campos terminais presentes nos grupos de item `imposto` e
   `impostoDevol`, preservando os nomes e o caminho dos grupos. Isso inclui
   ICMS, IPI, PIS, COFINS, IBS/CBS e outros grupos quando informados no XML.
6. Totais selecionados da nota, provenientes do grupo `total/ICMSTot`:
   valor total dos produtos, valor final da nota, descontos, outras despesas,
   bases de cálculo e valores de tributos. Essas colunas possuem o prefixo
   `total_nota_`.

Os totais pertencem à nota inteira e se repetem em cada linha de item da
mesma nota. Por isso, as colunas `total_nota_` não devem ser somadas linha
a linha. Os tributos dos itens continuam disponíveis nas colunas `imposto`
e `impostoDevol`.

Não são extraídos os grupos de cobrança, pagamentos e transporte, nem os
campos de frete e seguro. O valor final da nota é copiado conforme informado
no XML: a ausência da coluna de frete não significa que o frete tenha sido
descontado desse valor.

São extraídos somente os totais selecionados de `ICMSTot`; os totais
específicos dos grupos IBS/CBS, IS e ISSQN não estão incluídos nesta versão.

## Como entender as colunas de impostos

O caminho XML `imposto / ICMS / ICMS00 / vBC` vira a coluna
`imposto_ICMS_ICMS00_vBC`. Assim, bases e alíquotas de diferentes tributos
não se misturam. O sufixo continua sendo o nome oficial do campo de origem.

O script descobre a união das colunas fiscais encontradas na pasta. Por isso,
o conjunto de colunas pode aumentar quando a amostra recebe outros grupos
tributários. Campos ausentes ficam vazios; um valor informado como zero é
mantido como zero. Grupos repetidos recebem índices para não perder dados.

Este arquivo é uma extração para conferência, não um modelo dimensional
pronto e não um cálculo de tributos. Nenhuma alíquota é inferida, e códigos
não são traduzidos para decisões de compra/venda da distribuidora.

## Como o programa funciona

- `CAMPOS_NOTA`, `CAMPOS_EMPRESA` e `CAMPOS_PRODUTO` mapeiam nomes de colunas
  para marcações do XML.
- `filho` e `texto` localizam campos, inclusive em XML com namespace.
- `dados_empresa` reúne identificação e localização de cada parte da nota.
- `achatar_grupo` transforma a hierarquia dos tributos em colunas.
- `extrair_arquivo` valida a estrutura mínima e monta os itens de uma nota.
- A rotina de geração percorre os arquivos e produz a tabela CSV e o relatório.
- `main` interpreta as opções digitadas no terminal.

O programa lê um XML por vez. Guarda as linhas num arquivo temporário para
descobrir todas as colunas fiscais; depois escreve o CSV final e remove o
temporário automaticamente. Não mantém um DataFrame com todos os itens.
Pandas pode ler a saída posteriormente, se a equipe desejar.

## Conferência e limitações

- Chaves e códigos ficam em texto. Os valores decimais são exportados com
  vírgula no lugar do ponto do XML, preservando os dígitos e as casas decimais,
  sem conversão para `float` nem arredondamento.
- Para conferir no Excel, use Dados > De Texto/CSV, selecione UTF-8 e separador
  `;`, e configure documentos, chave, códigos e datas como texto. O CSV usa vírgula decimal:
  selecione uma localidade compatível, como Português (Brasil).
  No Google Planilhas, use a localidade Brasil e o separador `;` na importação. Evite salvar por cima do CSV original após a inspeção.
- O nome de um arquivo pode diferir da chave da NF-e. O programa usa
  `infNFe/@Id` e registra a diferença no relatório.
- Chaves repetidas entre arquivos são avisadas no relatório; não há remoção
  automática de notas. Linhas duplicadas podem, portanto, existir na saída.
- Um arquivo inválido não contribui com linhas; o erro fica no relatório.
  Outros arquivos continuam sendo processados. Havendo erros, o comando
  retorna código 1 e avisa que a saída é parcial.
- O script exige uma NF-e por arquivo. XMLs de eventos ou lotes com várias
  notas são registrados como erro, para não descartar conteúdo silenciosamente.
- Não valida XSD, assinatura, dígito verificador, situação fiscal em serviço
  externo nem enquadramento tributário. Preserva o status informado no XML,
  sem usá-lo como filtro automático.
- Esta etapa não classifica categorias, não relaciona produtos entre
  fornecedores e não distingue compra/venda do ponto de vista da empresa.
  Essas decisões pertencem ao tratamento e à carga do DW posteriores.


