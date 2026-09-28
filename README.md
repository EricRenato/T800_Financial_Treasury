# Financial Reconciliation Platform — MVP de conciliação

Protótipo de processamento de contratos de investimento e conciliação financeira. O fluxo local continua disponível; o diretório `apps_script` e a API FastAPI preparam a integração demonstrativa com Google Sheets e Google Cloud Run.

## Integração Google (código preparado)

- `apps_script/Code.gs`: menu/botão **Processar**, atualização das abas e registro visível de execuções.
- `src/api.py`: API que recebe um contrato e extratos relacionados, executa as regras existentes e devolve parcelas, lançamentos, conciliação e evidências.
- `Dockerfile` e `requirements-cloud.txt`: imagem do serviço para Cloud Run.
- As instruções de ligação estão em [`apps_script/README.md`](apps_script/README.md).

A integração está preparada localmente, mas ainda não foi implantada na conta Google nem testada dentro da planilha ao vivo. O protótipo Cloud Run usa uma chave de API e endpoint acessível pela internet; destina-se apenas a dados sintéticos de demonstração. Não use dados de clientes. A implantação exige um projeto Google Cloud com faturamento habilitado e pode gerar cobrança conforme o uso.

## Fluxo

1. O processo lê as linhas da aba `contracts` em `data/T800_Ciclo_1_Contrato_Reconciliado.xlsx`.
2. Carrega os extratos da fonte externa local `data/T800_Extratos.csv`.
3. Valida IDs, campos obrigatórios, datas, principal e percentual CDI.
4. Registra ou atualiza o contrato no SQLite e gera quatro parcelas: aplicação, devolução do principal, juros e IR.
5. Gera dois lançamentos contábeis de liquidação. Se informada uma data-base de accrual, gera também os dois lançamentos mensais correspondentes.
6. Concilia os eventos internos com os extratos e atualiza o status nos dois lados; cada correspondência, divergência, duplicidade ou ausência gera evidência em `reconciliation_evidence`.
7. Exporta uma planilha revisável em `data/T800_Resultado.xlsx`, com abas de contratos, parcelas, conciliações, extratos, contabilização, evidências da execução atual e faixas de impostos.

O cruzamento localiza o contrato pela referência interna ou por um alias (`contract_id_bank`/`contract_bank`) junto com o banco. Depois compara o valor e a data de liquidação. A data interna usada é `event_date`; a externa é `settlement_date`.

## Executar no Windows

Instale Python 3.10 ou superior e as dependências:

```powershell
py -3 -m venv venv
venv\Scripts\python.exe -m pip install -r requirements.txt
```

Execute o ciclo completo:

```powershell
venv\Scripts\python.exe src\run_pipeline.py
```

Para processar um contrato específico e registrar accrual até uma data escolhida:

```powershell
venv\Scripts\python.exe src\run_pipeline.py --contract-id CT-2026-001 --accrual-date 30/09/2026
```

Para indicar outros arquivos de entrada, use `--input caminho.xlsx` e `--statements caminho.csv`. A planilha compartilhada foi copiada localmente e é a entrada padrão.
Para escolher outro arquivo de resultado, use `--output caminho.xlsx`.

Também é possível executar `Processar.bat`; argumentos como `--contract-id` e `--accrual-date` podem ser passados ao arquivo.

O banco padrão é `data/t800.db`; outro caminho pode ser indicado com `--database`. A planilha de entrada pode ser trocada com `--input`. O comando de inicialização usa `CREATE TABLE IF NOT EXISTS`: preserva os dados já existentes e não recria o banco do zero.

## Conferir resultados

As tabelas principais são `contracts`, `installments`, `accounting`, `reconciliations`, `statements` e `reconciliation_evidence`. A última tabela mantém um histórico de evidências por execução (`run_id`), incluindo status, valores, datas, diferença e motivo.

Status possíveis incluem `MATCHED`, `AMOUNT_MISMATCH`, `DATE_MISMATCH`, `AMOUNT_AND_DATE_MISMATCH`, `MISSING_BANK`, `MISSING_INTERNAL`, `DUPLICATE_INTERNAL`, `DUPLICATE_BANK`, `AMBIGUOUS_MATCH` e `DATA_QUALITY_ERROR`.

## Hipóteses e limites atuais

- A projeção de juros usa juros simples, base de 365 dias e CDI anual didático fixo em 10,5%, multiplicado pelo percentual CDI do contrato. Não representa uma série diária observada de CDI.
- A conciliação deste MVP cobre o evento de aplicação inicial; não reconcilia automaticamente todos os eventos futuros do contrato.
- A tolerância de valor inicial é R$ 0,01 e a tolerância de data é zero dias.
- O accrual depende de uma data-base; por isso só é gravado quando `--accrual-date` é informada.
- A origem do extrato é o CSV local `data/T800_Extratos.csv`, carregado de forma idempotente na tabela `statements`.
- A planilha original de contratos não é alterada. O processo cria/atualiza uma planilha de resultado separada para revisão.
