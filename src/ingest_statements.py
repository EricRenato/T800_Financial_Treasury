"""Load a local bank-statement CSV into the SQLite source table."""

import csv
from pathlib import Path
import sqlite3

from common import DB_PATH, PROJECT_ROOT, iso_date, money

STATEMENTS_PATH = PROJECT_ROOT / "data" / "T800_Extratos.csv"
REQUIRED_COLUMNS = {
    "statement_id", "external_ref", "bank_id", "statement_date", "settlement_date", "face_amount"
}


def load_statements_from_csv(csv_path=STATEMENTS_PATH):
    csv_path = Path(csv_path)
    if not csv_path.exists():
        raise FileNotFoundError(f"arquivo local de extratos nao encontrado: {csv_path}")

    statements = []
    with csv_path.open("r", encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        columns = {str(name).strip().lower() for name in (reader.fieldnames or [])}
        missing = sorted(REQUIRED_COLUMNS - columns)
        if missing:
            raise ValueError("colunas obrigatorias ausentes no CSV: " + ", ".join(missing))
        for row_number, original in enumerate(reader, start=2):
            row = {str(key).strip().lower(): value for key, value in original.items() if key}
            try:
                item = {
                    "statement_id": str(row.get("statement_id") or "").strip(),
                    "external_ref": str(row.get("external_ref") or "").strip(),
                    "bank_id": str(row.get("bank_id") or "").strip(),
                    "statement_date": iso_date(row.get("statement_date")),
                    "settlement_date": iso_date(row.get("settlement_date")),
                    "description": str(row.get("description") or "").strip() or None,
                    "face_amount": money(row.get("face_amount"), "face_amount"),
                }
                for field in ("statement_id", "external_ref", "bank_id"):
                    if not item[field]:
                        raise ValueError(f"{field} obrigatorio nao informado")
                statements.append(item)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"linha {row_number}: {exc}") from exc
    return statements


def ingest_statements(csv_path=STATEMENTS_PATH, db_path=DB_PATH):
    statements = load_statements_from_csv(csv_path)
    with sqlite3.connect(db_path) as conn:
        for item in statements:
            conn.execute(
                """INSERT INTO statements
                   (statement_id, external_ref, bank_id, statement_date, settlement_date,
                    description, face_amount, reconciled)
                   VALUES (?, ?, ?, ?, ?, ?, ?, NULL)
                   ON CONFLICT(statement_id) DO UPDATE SET
                     external_ref=excluded.external_ref, bank_id=excluded.bank_id,
                     statement_date=excluded.statement_date, settlement_date=excluded.settlement_date,
                     description=excluded.description, face_amount=excluded.face_amount,
                     reconciled=NULL""",
                (item["statement_id"], item["external_ref"], item["bank_id"],
                 item["statement_date"], item["settlement_date"], item["description"],
                 str(item["face_amount"])),
            )
    return len(statements)
