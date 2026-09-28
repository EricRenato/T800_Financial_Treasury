"""Create a review workbook from the local database without changing inputs."""

from pathlib import Path
import sqlite3

import openpyxl

from common import DB_PATH, PROJECT_ROOT

OUTPUT_PATH = PROJECT_ROOT / "data" / "T800_Resultado.xlsx"

SHEETS = (
    ("contracts", "SELECT * FROM contracts ORDER BY contract_id", None),
    ("installments", "SELECT * FROM installments ORDER BY contract_id, installment_id", None),
    ("reconciliations", "SELECT * FROM reconciliations ORDER BY reconciliation_id", None),
    ("statements", "SELECT * FROM statements ORDER BY statement_id", None),
    ("accounting", "SELECT * FROM accounting ORDER BY contract_id, accounting_date, entry_id", None),
    ("reconciliation_evidence", "SELECT * FROM reconciliation_evidence WHERE run_id=? ORDER BY evidence_id", "run_id"),
    ("taxes", "SELECT * FROM taxes ORDER BY tax_type, min_days", None),
)


def export_results(db_path=DB_PATH, output_path=OUTPUT_PATH, run_id=None):
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    workbook = openpyxl.Workbook()
    workbook.remove(workbook.active)

    with sqlite3.connect(db_path) as conn:
        for sheet_name, query, filter_name in SHEETS:
            sheet = workbook.create_sheet(sheet_name)
            cursor = conn.execute(query, (run_id,)) if filter_name else conn.execute(query)
            sheet.append([column[0] for column in cursor.description])
            for row in cursor:
                sheet.append(list(row))
            sheet.freeze_panes = "A2"
            sheet.auto_filter.ref = sheet.dimensions

    workbook.save(output_path)
    workbook.close()
    return output_path
