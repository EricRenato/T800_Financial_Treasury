"""Deterministic two-sided reconciliation with append-only evidence."""

from collections import Counter, defaultdict
from datetime import datetime, timezone
from decimal import Decimal
import sqlite3
from uuid import uuid4

from common import DB_PATH, CENT, money, parse_date


def _key(value):
    return str(value or "").strip().casefold()


def _number(value):
    return money(value)


def _date_text(value):
    if value is None or not str(value).strip():
        return None
    return parse_date(value).isoformat()


def _safe_date_text(value):
    try:
        return _date_text(value)
    except (TypeError, ValueError):
        return str(value) if value is not None else None


def _safe_money_text(value):
    try:
        return str(_number(value))
    except (TypeError, ValueError):
        return str(value) if value is not None else None


def _canonicalize_contract_refs(conn):
    aliases = {}
    ambiguous = set()
    for contract_id, contract_id_bank, contract_bank in conn.execute(
        "SELECT contract_id, contract_id_bank, contract_bank FROM contracts"
    ):
        for alias in (contract_id, contract_id_bank, contract_bank):
            alias_key = _key(alias)
            if not alias_key:
                continue
            existing = aliases.get(alias_key)
            if existing is not None and existing != contract_id:
                ambiguous.add(alias_key)
            else:
                aliases[alias_key] = contract_id
    for alias in ambiguous:
        aliases.pop(alias, None)
    return aliases


def run_reconciliation(db_path=DB_PATH, amount_tolerance=Decimal("0.01"), date_tolerance_days=0):
    """Reconcile internal application events to bank statements and persist evidence."""
    run_id = str(uuid4())
    processed_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    amount_tolerance = Decimal(str(amount_tolerance))
    groups = defaultdict(lambda: {"internal": [], "bank": []})

    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        aliases = _canonicalize_contract_refs(conn)

        internal_rows = conn.execute(
            """SELECT reconciliation_id, event_date, bank_id, contract_id, installment_id,
                      description, amount, operation_bank_id
               FROM reconciliations"""
        ).fetchall()
        bank_rows = conn.execute(
            """SELECT statement_id, external_ref, bank_id, statement_date, settlement_date,
                      description, face_amount
               FROM statements"""
        ).fetchall()

        for row in internal_rows:
            rec_id, event_date, bank_id, contract_ref = row[:4]
            canonical = aliases.get(_key(contract_ref), contract_ref)
            if not canonical:
                canonical = f"<NO_INTERNAL_REF:{rec_id}>"
            group_key = (_key(bank_id), _key(canonical))
            groups[group_key]["internal"].append(row)

        for row in bank_rows:
            statement_id, external_ref, bank_id = row[:3]
            canonical = aliases.get(_key(external_ref), external_ref)
            if not canonical:
                canonical = f"<NO_BANK_REF:{statement_id}>"
            group_key = (_key(bank_id), _key(canonical))
            groups[group_key]["bank"].append(row)

        evidence = []

        def add_evidence(status, internal=None, bank=None, reason="", impact=Decimal("0.00"),
                         amount_difference=None, date_difference_days=None):
            internal_ref = internal[3] if internal else (bank[1] if bank else None)
            internal_date = _safe_date_text(internal[1]) if internal else None
            bank_date = _safe_date_text(bank[4]) if bank else None
            internal_amount = _safe_money_text(internal[6]) if internal else None
            bank_amount = _safe_money_text(bank[6]) if bank else None
            evidence.append((
                run_id, processed_at, internal[0] if internal else None, bank[0] if bank else None,
                status, str(internal_ref) if internal_ref is not None else None,
                internal[2] if internal else (bank[2] if bank else None),
                internal_amount,
                bank_amount,
                str(amount_difference) if amount_difference is not None else None,
                internal_date, bank_date, date_difference_days, str(impact), reason,
            ))

        internal_statuses = {}
        bank_statuses = {}
        status_counts = Counter()

        for group_key, members in groups.items():
            internals, banks = members["internal"], members["bank"]
            canonical_ref = group_key[1]
            if not banks:
                for internal in internals:
                    impact = abs(_number(internal[6]))
                    reason = f"Registro interno {internal[0]} sem lancamento bancario para a referencia {canonical_ref}."
                    add_evidence("MISSING_BANK", internal=internal, reason=reason, impact=impact)
                    internal_statuses[internal[0]] = "MISSING_BANK"
                    status_counts["MISSING_BANK"] += 1
                continue
            if not internals:
                for bank in banks:
                    impact = abs(_number(bank[6]))
                    reason = f"Lancamento bancario {bank[0]} sem registro interno para a referencia {canonical_ref}."
                    add_evidence("MISSING_INTERNAL", bank=bank, reason=reason, impact=impact)
                    bank_statuses[bank[0]] = "MISSING_INTERNAL"
                    status_counts["MISSING_INTERNAL"] += 1
                continue
            if len(internals) != 1 or len(banks) != 1:
                for internal in internals:
                    status = "DUPLICATE_INTERNAL" if len(internals) > 1 else "AMBIGUOUS_MATCH"
                    reason = (f"Referencia {canonical_ref}: {len(internals)} registros internos e "
                              f"{len(banks)} lancamentos bancarios; correspondencia ambigua.")
                    add_evidence(status, internal=internal, reason=reason, impact=abs(_number(internal[6])))
                    internal_statuses[internal[0]] = status
                    status_counts[status] += 1
                for bank in banks:
                    status = "DUPLICATE_BANK" if len(banks) > 1 else "AMBIGUOUS_MATCH"
                    reason = (f"Referencia {canonical_ref}: {len(internals)} registros internos e "
                              f"{len(banks)} lancamentos bancarios; correspondencia ambigua.")
                    add_evidence(status, bank=bank, reason=reason, impact=abs(_number(bank[6])))
                    bank_statuses[bank[0]] = status
                    status_counts[status] += 1
                continue

            internal, bank = internals[0], banks[0]
            try:
                internal_amount, bank_amount = _number(internal[6]), _number(bank[6])
                amount_difference = (internal_amount - bank_amount).quantize(CENT)
                internal_date, bank_date = parse_date(internal[1]), parse_date(bank[4])
                date_difference = (bank_date - internal_date).days
            except (TypeError, ValueError) as exc:
                status = "DATA_QUALITY_ERROR"
                reason = f"Dados insuficientes ou invalidos para comparar: {exc}"
                try:
                    impact = max(abs(_number(internal[6])), abs(_number(bank[6])))
                except (TypeError, ValueError):
                    impact = Decimal("0.00")
                add_evidence(status, internal=internal, bank=bank, reason=reason,
                             impact=impact)
                internal_statuses[internal[0]] = status
                bank_statuses[bank[0]] = status
                status_counts[status] += 1
                continue

            amount_differs = abs(amount_difference) > amount_tolerance
            date_differs = abs(date_difference) > date_tolerance_days
            if amount_differs and date_differs:
                status = "AMOUNT_AND_DATE_MISMATCH"
            elif amount_differs:
                status = "AMOUNT_MISMATCH"
            elif date_differs:
                status = "DATE_MISMATCH"
            else:
                status = "MATCHED"

            reason = (f"Chave: contrato={canonical_ref}, banco={internal[2]}; "
                      f"valor interno={internal_amount}, banco={bank_amount}, diferenca={amount_difference}; "
                      f"data interna={internal_date.isoformat()}, liquidacao bancaria={bank_date.isoformat()}, "
                      f"diferenca de dias={date_difference}.")
            impact = abs(amount_difference) if amount_differs else (
                max(abs(internal_amount), abs(bank_amount)) if date_differs else Decimal("0.00")
            )
            add_evidence(status, internal, bank, reason, impact, amount_difference, date_difference)
            internal_statuses[internal[0]] = status
            bank_statuses[bank[0]] = status
            status_counts[status] += 1

        for rec_id, status in internal_statuses.items():
            conn.execute("UPDATE reconciliations SET reconciled=? WHERE reconciliation_id=?", (status, rec_id))
        for statement_id, status in bank_statuses.items():
            conn.execute("UPDATE statements SET reconciled=? WHERE statement_id=?", (status, statement_id))

        conn.executemany(
            """INSERT INTO reconciliation_evidence
               (run_id, processed_at, reconciliation_id, statement_id, status, contract_ref,
                bank_id, internal_amount, bank_amount, amount_difference, internal_date,
                bank_date, date_difference_days, financial_impact, reason)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            evidence,
        )

    return {"run_id": run_id, "counts": dict(status_counts), "evidence_count": len(evidence)}


if __name__ == "__main__":
    result = run_reconciliation()
    print(f"Conciliacao {result['run_id']}: {result['evidence_count']} evidencias")
    for status, count in sorted(result["counts"].items()):
        print(f"  {status}: {count}")
