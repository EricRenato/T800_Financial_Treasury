"""Run the local contract-processing and reconciliation flow."""

import argparse
from pathlib import Path

from common import CONTRACTS_PATH, DB_PATH
from contract_engine import calculate_accrual
from export_workbook import OUTPUT_PATH, export_results
from init_db import initialize_database
from ingest_excel import ingest_contracts_from_excel
from ingest_statements import STATEMENTS_PATH, ingest_statements
from reconcile import run_reconciliation


def run(input_path=CONTRACTS_PATH, db_path=DB_PATH, statements_path=STATEMENTS_PATH,
        output_path=OUTPUT_PATH, contract_id=None, accrual_date=None):
    initialize_database(db_path)
    statement_count = ingest_statements(statements_path, db_path)
    processed = ingest_contracts_from_excel(input_path, db_path, contract_id)
    accruals = []
    if accrual_date:
        accruals = [calculate_accrual(item["contract_id"], accrual_date, db_path,
                                      record_accounting=True) for item in processed]
    reconciliation = run_reconciliation(db_path)
    output = export_results(db_path, output_path, reconciliation["run_id"])
    return processed, accruals, reconciliation, statement_count, output


def main():
    parser = argparse.ArgumentParser(
        description="Valida contratos, gera parcelas e contabilizacao e concilia com extratos locais"
    )
    parser.add_argument("--input", type=Path, default=CONTRACTS_PATH,
                        help="arquivo Excel de contratos (default: data/T800_Contratos.xlsx)")
    parser.add_argument("--database", type=Path, default=DB_PATH,
                        help="banco SQLite local (default: data/t800.db)")
    parser.add_argument("--statements", type=Path, default=STATEMENTS_PATH,
                        help="CSV local de extratos (default: data/T800_Extratos.csv)")
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH,
                        help="planilha de resultado (default: data/T800_Resultado.xlsx)")
    parser.add_argument("--contract-id", help="processa apenas um contrato da planilha")
    parser.add_argument("--accrual-date", help="data-base opcional para gerar os dois lancamentos de accrual (DD/MM/AAAA)")
    args = parser.parse_args()

    processed, accruals, reconciliation, statement_count, output = run(
        args.input, args.database, args.statements, args.output, args.contract_id, args.accrual_date
    )
    print("\n--- PROCESSAMENTO DE CONTRATOS ---")
    for item in processed:
        print(f"[OK] {item['contract_id']}: 4 parcelas, 2 lancamentos contabeis; "
              f"juros projetados={item['gross_interest']:.2f}; IR={item['tax_amount']:.2f}")
    for accrual in accruals:
        print(f"[OK] Accrual de {accrual['contract_id']} em {accrual['as_of_date']}: "
              f"juros acumulados={accrual['gross_interest']:.2f}; IR={accrual['tax_amount']:.2f}")
    print(f"[OK] {statement_count} linhas de extrato carregadas de {args.statements}")
    print("\n--- CONCILIACAO ---")
    print(f"Execucao: {reconciliation['run_id']}")
    if not reconciliation["counts"]:
        print("Nenhum registro interno ou bancario disponivel para comparar.")
    for status, count in sorted(reconciliation["counts"].items()):
        print(f"{status}: {count}")
    print(f"Evidencias persistidas no banco: {reconciliation['evidence_count']}")
    print(f"Banco local: {args.database}")
    print(f"Planilha de saida: {output}")


if __name__ == "__main__":
    main()
