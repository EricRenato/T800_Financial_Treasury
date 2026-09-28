"""Cloud Run API adapter for the spreadsheet-triggered reconciliation flow."""

import hmac
import logging
import os
import sqlite3
import tempfile
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from common import iso_date, money
from contract_engine import create_and_unfold_contract, validate_contract
from init_db import initialize_database
from reconcile import run_reconciliation

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("financial-reconciliation")
app = FastAPI(title="Financial Reconciliation API", version="0.1.0")


class ProcessRequest(BaseModel):
    contracts: list[dict[str, Any]] = Field(min_length=1)
    statements: list[dict[str, Any]] = Field(default_factory=list)


def _read_table(conn, table, where_clause="", parameters=()):
    cursor = conn.execute(f"SELECT * FROM {table} {where_clause}", parameters)
    columns = [item[0] for item in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def _insert_statements(conn, statements):
    for row_number, row in enumerate(statements, start=1):
        statement = {
            "statement_id": str(row.get("statement_id") or "").strip(),
            "external_ref": str(row.get("external_ref") or "").strip(),
            "bank_id": str(row.get("bank_id") or "").strip(),
            "statement_date": iso_date(row.get("statement_date")),
            "settlement_date": iso_date(row.get("settlement_date")),
            "description": str(row.get("description") or "").strip() or None,
            "face_amount": money(row.get("face_amount"), "face_amount"),
        }
        for required in ("statement_id", "external_ref", "bank_id"):
            if not statement[required]:
                raise ValueError(f"extrato {row_number}: {required} obrigatorio")
        conn.execute(
            """INSERT INTO statements
               (statement_id, external_ref, bank_id, statement_date, settlement_date,
                description, face_amount, reconciled)
               VALUES (?, ?, ?, ?, ?, ?, ?, NULL)""",
            (statement["statement_id"], statement["external_ref"], statement["bank_id"],
             statement["statement_date"], statement["settlement_date"], statement["description"],
             str(statement["face_amount"])),
        )


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/process")
def process(request: ProcessRequest, x_api_key: str = Header(default="")):
    expected_key = os.environ.get("RECONCILIATION_API_KEY", "")
    if not expected_key:
        raise HTTPException(status_code=503, detail="API key nao configurada no servico")
    if not hmac.compare_digest(x_api_key, expected_key):
        raise HTTPException(status_code=401, detail="Acesso nao autorizado")

    try:
        normalized_contracts = [validate_contract(item) for item in request.contracts]
        with tempfile.TemporaryDirectory(prefix="reconciliation-") as temp_dir:
            db_path = Path(temp_dir) / "run.sqlite"
            initialize_database(db_path)
            with sqlite3.connect(db_path) as conn:
                _insert_statements(conn, request.statements)

            for contract in normalized_contracts:
                create_and_unfold_contract(contract, db_path)
            result = run_reconciliation(db_path)

            with sqlite3.connect(db_path) as conn:
                tables = {
                    "contracts": _read_table(conn, "contracts"),
                    "installments": _read_table(conn, "installments"),
                    "accounting": _read_table(conn, "accounting"),
                    "reconciliations": _read_table(conn, "reconciliations"),
                    "statements": _read_table(conn, "statements"),
                    "evidence": _read_table(
                        conn, "reconciliation_evidence", "WHERE run_id=?", (result["run_id"],)
                    ),
                }

        logger.info("run_id=%s outcome_counts=%s", result["run_id"], result["counts"])
        return {
            "run_id": result["run_id"],
            "counts": result["counts"],
            "tables": tables,
        }
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except sqlite3.Error as exc:
        logger.exception("database error during reconciliation")
        raise HTTPException(status_code=500, detail="Falha interna ao processar reconciliacao") from exc
