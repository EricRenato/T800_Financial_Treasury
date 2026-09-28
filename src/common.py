"""Shared paths and parsing helpers for the local reconciliation MVP."""

from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = PROJECT_ROOT / "data" / "t800.db"
CONTRACTS_PATH = PROJECT_ROOT / "data" / "T800_Ciclo_1_Contrato_Reconciliado.xlsx"
SCHEMA_PATH = PROJECT_ROOT / "sql" / "01_schema.sql"
CENT = Decimal("0.01")


def parse_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if value is None or not str(value).strip():
        raise ValueError("data obrigatoria nao informada")

    value = str(value).strip()
    for pattern in ("%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(value, pattern).date()
        except ValueError:
            continue
    raise ValueError(f"data invalida: {value!r}; use DD/MM/AAAA ou AAAA-MM-DD")


def iso_date(value):
    return parse_date(value).isoformat()


def money(value, field_name="valor"):
    if value is None or str(value).strip() == "":
        raise ValueError(f"{field_name} obrigatorio nao informado")
    raw = str(value).strip().replace(" ", "")
    if "," in raw and "." in raw:
        if raw.rfind(",") > raw.rfind("."):
            raw = raw.replace(".", "").replace(",", ".")
        else:
            raw = raw.replace(",", "")
    elif "," in raw:
        raw = raw.replace(",", ".")
    try:
        parsed = Decimal(raw)
    except (InvalidOperation, ValueError):
        raise ValueError(f"{field_name} invalido: {value!r}") from None
    if not parsed.is_finite():
        raise ValueError(f"{field_name} precisa ser um numero finito")
    return parsed.quantize(CENT, rounding=ROUND_HALF_UP)
