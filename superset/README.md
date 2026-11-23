# Apache Superset — Dashboards do FiscalMind

O Superset é a interface de dashboards do FiscalMind. Ele lê os dados do Data Warehouse (`fiscalmind_dw`) e mostra os indicadores de compras em gráficos e filtros interativos.

Este guia explica como instalar o Superset no seu computador, importar o dashboard da equipe e publicar alterações.

---

## 1. Como funciona

```
Docker
├── superset        Interface web (http://localhost:8088)
└── superset-db     PostgreSQL 16, só para o Superset
                    (usuários, gráficos, dashboards e conexões)

PostgreSQL do seu computador
└── fiscalmind_dw   Data Warehouse, carregado pelo Airflow
```

- O **PostgreSQL 16 do Docker** guarda apenas as configurações do Superset. Ele não recebe notas fiscais.
- O **`fiscalmind_dw`** continua no PostgreSQL do seu computador. O Superset só **lê** os dados dele, com o usuário `superset_leitura`, que recebe permissão apenas de leitura nas tabelas do schema `dw`. A conexão no Superset também bloqueia comandos de escrita.
- Cada integrante tem o **próprio** Superset, com o próprio login. O dashboard é compartilhado pelo arquivo `dashboards/fiscalmind_analise_compras.zip`.

### Arquivos

| Arquivo | Função |
|---|---|
| `airflow/dockerfile.superset` | Constrói a imagem do Superset 6.1.0 com o driver do PostgreSQL |
| `airflow/docker-compose.superset.yaml` | Define o Superset, o banco interno e a inicialização automática |
| `airflow/superset_config.py` | Configura a chave de segurança, o banco interno, o formato brasileiro de números e datas (1.234,56 e dd/mm/aaaa) e a moeda BRL |
| `superset/dashboards/fiscalmind_analise_compras.zip` | Dashboard da equipe: conexão, 3 datasets, 17 gráficos, filtros e painel |

---

## 2. Pré-requisitos

- Docker Desktop instalado e em execução.
- Repositório atualizado (`git pull`).
- O `fiscalmind_dw` criado no PostgreSQL do seu computador e **com dados**, ou seja, as DAGs do Airflow já executadas ao menos uma vez. O Airflow não precisa estar ligado para ver o dashboard: ele só é necessário para carregar ou atualizar os dados.
- Acesso ao pgAdmin, conectado ao `fiscalmind_dw`, com um usuário que possa criar usuários e conceder permissões (normalmente o dono das tabelas ou o administrador do banco, como o `postgres`).

---

## 3. Primeira instalação

Faça esta parte **uma única vez**.

### 3.1. Configurar o `.env`

No arquivo `airflow/.env` (o mesmo usado pelo Airflow), **acrescente** ao final as variáveis do Superset que estão no `airflow/.env.example`. Não substitua o arquivo inteiro: as variáveis do Airflow precisam continuar lá.

```
SUPERSET_SECRET_KEY=
SUPERSET_DB_PASSWORD=
SUPERSET_ADMIN_USERNAME=admin
SUPERSET_ADMIN_PASSWORD=
SUPERSET_ADMIN_EMAIL=admin@fiscalmind.local
```

Para gerar a chave e a senha do banco interno, rode no PowerShell e copie os dois valores:

```powershell
python -c "import secrets; print('SUPERSET_SECRET_KEY=' + secrets.token_hex(32)); print('SUPERSET_DB_PASSWORD=' + secrets.token_hex(24))"
```

Em `SUPERSET_ADMIN_PASSWORD`, defina a senha que você vai usar para entrar no Superset.

> **Importante:** os valores gerados ficam só no seu `.env`, que nunca vai para o GitHub. Depois da primeira instalação, **não altere a `SUPERSET_DB_PASSWORD`**: o banco interno já foi criado com ela, e mudar a variável não muda a senha do banco. O Superset deixaria de conseguir se conectar.

### 3.2. Criar o usuário `superset_leitura` no Data Warehouse

O dashboard se conecta ao DW com o usuário `superset_leitura`. Cada integrante precisa criá-lo no **próprio** `fiscalmind_dw`.

No pgAdmin, conectado ao `fiscalmind_dw`, descubra primeiro o dono das tabelas do schema `dw`:

```sql
SELECT DISTINCT tableowner FROM pg_tables WHERE schemaname = 'dw';
```

Depois execute o script abaixo, com o mesmo usuário administrador do pré-requisito, trocando:
- `TROQUE_ESTA_SENHA` pela senha que você vai digitar ao importar o dashboard. Evite usar apóstrofo (`'`) na senha: ele encerra o texto no SQL;
- `SEU_USUARIO` pelo nome retornado na consulta acima.

```sql
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'superset_leitura') THEN
        ALTER ROLE superset_leitura LOGIN PASSWORD 'TROQUE_ESTA_SENHA';
    ELSE
        CREATE ROLE superset_leitura LOGIN PASSWORD 'TROQUE_ESTA_SENHA';
    END IF;
END
$$;

GRANT CONNECT ON DATABASE fiscalmind_dw TO superset_leitura;
GRANT USAGE ON SCHEMA dw TO superset_leitura;
GRANT SELECT ON ALL TABLES IN SCHEMA dw TO superset_leitura;

-- Tabelas criadas no futuro por SEU_USUARIO também poderão ser lidas.
-- Se a consulta mostrou mais de um dono, repita este comando para cada um.
ALTER DEFAULT PRIVILEGES FOR ROLE SEU_USUARIO IN SCHEMA dw
    GRANT SELECT ON TABLES TO superset_leitura;
```

O script pode ser executado novamente sem erro: se o usuário já existir, apenas a senha é atualizada.

### 3.3. Subir o Superset

Na pasta `airflow`:

```powershell
docker compose -f docker-compose.yaml -f docker-compose.superset.yaml up -d superset
```

O comando indica só o serviço `superset`. O Docker sobe junto o `superset-db` e o `superset-init`, que são dependências dele, e não mexe no Airflow. Na primeira vez, o Docker também constrói a imagem e prepara o banco interno sozinho. Pode levar alguns minutos.

Confira o resultado:

```powershell
docker compose -f docker-compose.yaml -f docker-compose.superset.yaml ps -a superset-db superset-init superset
```

O esperado é:

| Serviço | Status |
|---|---|
| `superset-db` | `Up (healthy)` |
| `superset-init` | `Exited (0)`: terminou com sucesso |
| `superset` | `Up (healthy)` |

> **Nome do projeto Docker.** Execute os comandos sempre na pasta `airflow`. Se você costuma subir o Airflow com `-p <nome>` (ou definiu `COMPOSE_PROJECT_NAME` no `.env`), use o mesmo nome em **todos** os comandos deste guia: iniciar, parar, ver logs e conferir status. Com um nome diferente, o Docker trata os comandos como outro projeto e cria um segundo conjunto de contêineres e volumes.

### 3.4. Importar o dashboard

1. Abra `http://localhost:8088` e entre com o `SUPERSET_ADMIN_USERNAME` e a `SUPERSET_ADMIN_PASSWORD` do seu `.env`.
2. No menu superior, clique em **Dashboards**.
3. No canto superior direito, clique no ícone de **importar**.
4. Selecione `superset/dashboards/fiscalmind_analise_compras.zip`.
5. No campo de senha da conexão **FiscalMind DW**, digite a senha do `superset_leitura` (item 3.2).
6. Clique em **Import** e abra o dashboard **FiscalMind - Análise Gerencial de Compras**.

Os números exibidos são os do **seu** `fiscalmind_dw`.

> **Já tinha importado uma versão anterior do dashboard?** O dashboard atual tem um identificador interno diferente do primeiro publicado. Ao importar, aparecerão **dois dashboards** com o nome *FiscalMind - Análise Gerencial de Compras*. Apague o **antigo**, que é o que tem menos gráficos (10). Apagar um dashboard não apaga os gráficos.

---

## 4. Conteúdo do dashboard

### 4.1. Modelo semântico

A camada semântica fica nos próprios datasets: cada coluna tem um **rótulo** legível e os indicadores são **métricas oficiais**, definidas uma única vez e usadas por todos os gráficos. Assim, por exemplo, "ticket médio" é calculado sempre da mesma forma.

| Dataset | Uma linha é | Uso |
|---|---|---|
| **FiscalMind - Compras** | um item de nota fiscal de compra | Indicadores gerais, rankings, filtros, tabela dinâmica |
| **FiscalMind - Alerta de custo** | um produto em um mês | Alertas de variação de custo e de volume atípico |
| **FiscalMind - Tendência semanal** | uma semana | Regressão linear do valor comprado |

Métricas oficiais do dataset **FiscalMind - Compras**:

| Métrica | Fórmula |
|---|---|
| Valor total de compras (R$) | `SUM(valor_produto)` |
| Notas fiscais | `COUNT(DISTINCT nota)` |
| Fornecedores com compras | `COUNT(DISTINCT id_fornecedor)` |
| Ticket médio por nota (R$) | `SUM(valor_produto) / NULLIF(COUNT(DISTINCT nota), 0)` |
| Itens por nota (média) | `COUNT(*) * 1.0 / NULLIF(COUNT(DISTINCT nota), 0)` |
| Produtos comprados | `COUNT(DISTINCT id_produto)` |
| Quantidade comprada | `SUM(quantidade)` |
| Custo médio de aquisição (R$) | `SUM(valor_produto) / NULLIF(SUM(quantidade), 0)` (média ponderada pela quantidade) |
| Itens de nota | `COUNT(*)` |

O "% do total" (por exemplo, a participação de cada fornecedor) é feito no próprio gráfico, em **Percentage metrics**, sem métrica separada.

### 4.2. Gráficos

| Nº | Gráfico | Dataset |
|---|---|---|
| 01–04 | Cartões: valor total, notas fiscais, fornecedores, ticket médio | Compras |
| 05 | Evolução mensal das compras | Compras |
| 06 | Top 10 fornecedores por valor de compras | Compras |
| 07 | Compras por região do fornecedor | Compras |
| 08 | Top 10 produtos por valor de compras | Compras |
| 09 | Concentração de compras por fornecedor (%) | Compras |
| 10 | Monitoramento da variação dos preços de aquisição | Compras |
| 11 | Alertas de variação de custo | Alerta de custo |
| 12 | Variação atípica de volume (produtos por mês) | Alerta de custo |
| 13 | Tendência semanal das compras (regressão linear) | Tendência semanal |
| 14 | Variação semanal da tendência (inclinação da reta) | Tendência semanal |
| 15 | R² da regressão | Tendência semanal |
| 16 | Compras por região e mês (tabela dinâmica) | Compras |
| 17 | Compras do último mês vs mês anterior | Compras |

### 4.3. Regras dos alertas e da regressão

Os limites abaixo são **regras de negócio** definidas pela equipe. Para alterá-los, edite o SQL do dataset (**Datasets → editar → Source**) e troque os números nos `CASE`.

| Indicador | Regra |
|---|---|
| **Alerta de custo** | Compara o custo médio ponderado do mês com o da **compra anterior** do mesmo produto. Alta: subiu 10% ou mais. Queda: caiu 10% ou mais. Estável: variou menos de 10%. |
| **Volume atípico** | Compara a quantidade do mês com a média mensal do produto (meses com compra). Acima do normal: 1,5 vez a média ou mais. Abaixo do normal: metade da média ou menos. Exige pelo menos 3 meses de compra; com menos, fica como "Histórico insuficiente". |
| **Regressão linear** | Reta do valor comprado por semana, calculada no PostgreSQL com `REGR_SLOPE`, `REGR_INTERCEPT` e `REGR_R2`. A inclinação mostra quanto o valor sobe ou desce por semana; o R² mostra quanto da variação a reta explica (perto de 0%: tendência fraca; perto de 100%: tendência forte). |

Os alertas e a regressão são calculados sobre **todo o histórico**. Os filtros do dashboard só escondem linhas; eles não refazem as comparações nem a reta.

### 4.4. Filtros e exploração

- **Filtros do dashboard:** Período, Região, Categoria (NCM) e Fornecedor. Depois de escolher os valores, clique em **Apply filters**. No filtro Período, prefira o tipo **Advanced**, com datas: opções como "Last month" contam a partir de hoje e podem não ter dados.
- **Drill by:** clique com o botão direito numa barra (por exemplo, uma região) e escolha outra coluna (Fornecedor, Produto...) para detalhar.
- **Drill to detail:** clique com o botão direito e veja as linhas que formam aquele valor.
- **Comparação com o período anterior:** o gráfico 17 mostra o último mês do período filtrado e a variação em relação ao mês anterior.

### 4.5. Limitações dos dados atuais

- A `fato_compra` ainda não filtra o **CFOP**: devoluções e bonificações entram nos valores.
- Os dados de teste cobrem poucos meses, e o último mês está incompleto. Por isso os alertas, a comparação mensal e a regressão são **demonstrativos**.

---

## 5. Usuário gerente (somente consulta)

Usuários **não** vão no ZIP: cada integrante cria o seu no próprio Superset. Nunca coloque senhas no GitHub.

1. **Publicar o dashboard:** abra o dashboard e troque o status **Draft** para **Published**. Dashboards em rascunho só aparecem para os donos.
2. **Criar o papel:** em **Settings → List Roles → + Role**, crie o papel `Gerente`. Em **Permissions**, digite `FiscalMind` na busca e marque a permissão `database access on [FiscalMind DW]` (ou as três `datasource access` dos datasets do FiscalMind).
3. **Criar o usuário:** em **Settings → List Users → + User**, preencha nome, usuário, e-mail e senha, e marque os papéis **Gamma** e **Gerente**.
4. **Testar:** numa janela anônima, entre com o usuário criado. O dashboard deve abrir com filtros e drill, e **sem** o botão **Edit dashboard**.

O papel **Gamma** é o perfil de consulta do Superset: o gerente não altera os gráficos nem o dashboard da equipe, nem mexe em conexões, datasets e usuários. Ele pode criar gráficos próprios a partir dos datasets liberados. Os dados continuam protegidos pelo `superset_leitura`, que só tem permissão de leitura no DW.

---

## 6. Uso diário

Todos os comandos são executados na pasta `airflow`, **sempre com os dois arquivos** (`-f`) e indicando os serviços do Superset, para não afetar o Airflow:

| Ação | Comando |
|---|---|
| Ligar | `docker compose -f docker-compose.yaml -f docker-compose.superset.yaml up -d superset` |
| Desligar | `docker compose -f docker-compose.yaml -f docker-compose.superset.yaml stop superset superset-db` |
| Ver logs | `docker compose -f docker-compose.yaml -f docker-compose.superset.yaml logs superset` |

Usuários, gráficos e dashboards ficam guardados no volume do Docker e continuam disponíveis depois de desligar o computador.

> ⚠️ **Nunca use `down -v`.** O `-v` apaga o volume do banco interno, com todos os seus dashboards e gráficos.

### Receber uma atualização da equipe

1. `git pull`.
2. Se o `airflow/superset_config.py` mudou, reinicie só o Superset (não é preciso reconstruir a imagem):
   ```powershell
   docker compose -f docker-compose.yaml -f docker-compose.superset.yaml restart superset
   ```
3. Reimporte o `fiscalmind_analise_compras.zip` (item 3.4) e confirme a substituição.

---

## 7. Criar indicadores e atualizar o dashboard da equipe

Qualquer integrante pode criar indicadores no próprio Superset. Para que a equipe receba a alteração, é preciso exportar um ZIP novo e publicá-lo no GitHub.

> **Regra: uma pessoa altera o dashboard por vez.** O ZIP não pode ser mesclado pelo Git. Se duas pessoas publicarem versões ao mesmo tempo, a última apaga as alterações da outra.

### Passo a passo

1. **Avise a equipe** de que vai alterar o dashboard.
2. **Atualize o repositório:** `git pull`.
3. **Importe o ZIP mais recente** (item 3.4). Como o dashboard já existe no seu Superset, ele avisa que os objetos serão sobrescritos: confirme. Cada objeto tem um identificador fixo, então ele é **atualizado**, e não duplicado.
4. **Crie o gráfico:** em **Charts → + Chart**, escolha o dataset (normalmente **FiscalMind - Compras**), o tipo de gráfico e as **métricas oficiais** (aba **Saved**). Ao salvar, escolha o dashboard em **Add to dashboard**. Ao alterar um gráfico existente, use **Save (Overwrite)**: o **Save as** cria uma cópia nova, sem vínculo com o dashboard.
5. **Posicione o gráfico no dashboard:** abra o dashboard, clique em **Edit dashboard**, arraste o gráfico para o lugar desejado e salve.
6. **Exporte o dashboard:** em **Dashboards**, exporte o dashboard **FiscalMind - Análise Gerencial de Compras**. Logo depois, aperte **Ctrl+J** no navegador para pegar o arquivo **mais recente**: todos os exports começam com `dashboard_export_` e é fácil abrir um antigo.
7. **Copie o arquivo** para o projeto, sempre com o mesmo nome, e confira o conteúdo:
   ```powershell
   Copy-Item "$HOME\Downloads\NOME_DO_ARQUIVO.zip" superset\dashboards\fiscalmind_analise_compras.zip -Force
   tar -tf superset/dashboards/fiscalmind_analise_compras.zip
   ```
   A lista deve mostrar o gráfico novo em `charts/`.
8. **Publique só o ZIP:**
   ```powershell
   git add superset/dashboards/fiscalmind_analise_compras.zip
   git commit -m "feat: adiciona indicador <nome do indicador> ao dashboard"
   git push
   ```
9. **Avise a equipe** para fazer `git pull` e reimportar o ZIP.

Se o novo indicador precisar de uma coluna que o dataset não tem, edite a consulta em **Datasets → FiscalMind - Compras → Edit dataset**. A alteração vai junto no ZIP exportado.

Se o indicador precisar comparar uma linha com outra (por exemplo, um mês com o anterior do mesmo produto) ou de uma regressão, uma métrica não resolve: crie um dataset virtual no **SQL Lab** (**Save dataset**), como os datasets *Alerta de custo* e *Tendência semanal*.

---

## 8. Problemas comuns

| Sintoma | Causa provável | Solução |
|---|---|---|
| `required variable ... is missing a value` | Falta uma variável no `.env` | Conferir o item 3.1 |
| `superset-init` com `Exited (1)` | Falha na inicialização | Ver o motivo com `docker compose -f docker-compose.yaml -f docker-compose.superset.yaml logs superset-init` |
| Erro de conexão ao importar ou ao abrir os gráficos | `superset_leitura` não existe, senha errada ou sem permissão | Refazer o item 3.2 e reimportar, digitando a mesma senha |
| Porta 8088 em uso | Outro Superset já está ligado | Desligar o outro antes de subir este |
| Valores sem R$ ou no formato 1,234.56 | O Superset não leu o `superset_config.py` atualizado | Reiniciar o Superset (item 6, "Receber uma atualização da equipe") e recarregar a página com Ctrl+F5 |
| Gráfico novo não aparece no ZIP exportado | O gráfico não está vinculado ao dashboard (coluna **On dashboards** vazia em **Charts**) | Abrir o gráfico, **Save → Save (Overwrite)**, escolher o dashboard em **Add to dashboard** e exportar de novo |
| O usuário gerente não vê o dashboard | Dashboard em rascunho, ou papel sem acesso aos dados | Publicar o dashboard e conferir o item 5 |
| Dashboard vazio ou sem dados | O `fiscalmind_dw` ainda não tem dados, ou o `superset_leitura` não tem acesso às tabelas | Executar as DAGs do Airflow, conferir se o script do item 3.2 foi executado no `fiscalmind_dw` e atualizar a página, conferindo também os filtros do dashboard |