"""Deterministic investment-contract rules for the local MVP."""

import sqlite3
from decimal import Decimal, ROUND_HALF_UP

from common import CENT, DB_PATH, money, parse_date

# Demonstration assumption only; production accruals must use an observed CDI series.
ANNUAL_CDI_ASSUMPTION = Decimal("0.105")


def validate_contract(contract_data):
    required = ("contract_id", "bank_id", "asset_type", "start_date", "settlement_date", "due_date")
    missing = [field for field in required if not str(contract_data.get(field) or "").strip()]
    if missing:
        raise ValueError("campos obrigatorios ausentes: " + ", ".join(missing))

    contract = dict(contract_data)
    for field in ("contract_id", "bank_id", "asset_type"):
        contract[field] = str(contract[field]).strip()
    for field in ("contract_bank", "contract_id_bank", "notes"):
        contract[field] = str(contract.get(field) or "").strip() or None

    start = parse_date(contract["start_date"])
    settlement = parse_date(contract["settlement_date"])
    due = parse_date(contract["due_date"])
    if start > settlement:
        raise ValueError("start_date nao pode ser posterior a settlement_date")
    if settlement >= due:
        raise ValueError("due_date deve ser posterior a settlement_date")

    contract["start_date"] = start.isoformat()
    contract["settlement_date"] = settlement.isoformat()
    contract["due_date"] = due.isoformat()
    contract["principal"] = money(contract.get("principal"), "principal")
    contract["rate_cdi"] = money(contract.get("rate_cdi"), "rate_cdi")
    if contract["principal"] <= 0:
        raise ValueError("principal deve ser maior que zero")
    if contract["rate_cdi"] <= 0:
        raise ValueError("rate_cdi deve ser maior que zero")
    return contract


def get_tax_rate(conn, days):
    row = conn.execute(
        """SELECT rate_pct FROM taxes
           WHERE tax_type = 'IR' AND ? BETWEEN min_days AND max_days
           ORDER BY min_days LIMIT 1""",
        (days,),
    ).fetchone()
    if row is None:
        raise ValueError(f"nao existe faixa de IR configurada para {days} dias")
    return Decimal(str(row[0]))


def _next_id(conn, table, id_column):
    value = conn.execute(f"SELECT COALESCE(MAX({id_column}), 0) + 1 FROM {table}").fetchone()[0]
    return int(value)


def _upsert_installment(conn, contract, installment):
    installment_type, due_date, flow_type, amount, status, notes = installment
    existing = conn.execute(
        "SELECT installment_id FROM installments WHERE contract_id=? AND installment_type=? ORDER BY installment_id LIMIT 1",
        (contract["contract_id"], installment_type),
    ).fetchone()
    installment_id = int(existing[0]) if existing else _next_id(conn, "installments", "installment_id")
    conn.execute(
        """INSERT INTO installments
           (installment_id, contract_id, bank_id, installment_type, due_date, flow_type, amount, status, notes)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(installment_id) DO UPDATE SET
             contract_id=excluded.contract_id, bank_id=excluded.bank_id,
             installment_type=excluded.installment_type, due_date=excluded.due_date,
             flow_type=excluded.flow_type, amount=excluded.amount,
             status=excluded.status, notes=excluded.notes""",
        (installment_id, contract["contract_id"], contract["bank_id"], installment_type,
         due_date, flow_type, str(amount), status, notes),
    )
    return installment_id


def _upsert_accounting(conn, contract_id, entry_type, accounting_date, account, debit, credit, description, batch_id):
    existing = conn.execute(
        """SELECT entry_id FROM accounting
           WHERE contract_id=? AND entry_type=? AND accounting_date=? AND accounting_account=?
           ORDER BY entry_id LIMIT 1""",
        (contract_id, entry_type, accounting_date, account),
    ).fetchone()
    entry_id = int(existing[0]) if existing else _next_id(conn, "accounting", "entry_id")
    conn.execute(
        """INSERT INTO accounting
           (entry_id, contract_id, entry_type, accounting_date, accounting_account,
            debit, credit, description, accounting_batch_id)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(entry_id) DO UPDATE SET
             contract_id=excluded.contract_id, entry_type=excluded.entry_type,
             accounting_date=excluded.accounting_date, accounting_account=excluded.accounting_account,
             debit=excluded.debit, credit=excluded.credit, description=excluded.description,
             accounting_batch_id=excluded.accounting_batch_id""",
        (entry_id, contract_id, entry_type, accounting_date, account,
         str(debit) if debit is not None else None, str(credit) if credit is not None else None,
         description, batch_id),
    )
    return entry_id


def create_and_unfold_contract(contract_data, db_path=DB_PATH):
    contract = validate_contract(contract_data)
    settlement = parse_date(contract["settlement_date"])
    due = parse_date(contract["due_date"])
    days = (due - settlement).days

    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        tax_rate = get_tax_rate(conn, days)
        annual_return = (contract["rate_cdi"] / Decimal("100")) * ANNUAL_CDI_ASSUMPTION
        gross_interest = (contract["principal"] * annual_return * Decimal(days) / Decimal("365"))
        gross_interest = gross_interest.quantize(CENT, rounding=ROUND_HALF_UP)
        tax_amount = (gross_interest * tax_rate / Decimal("100")).quantize(CENT, rounding=ROUND_HALF_UP)

        conn.execute(
            """INSERT INTO contracts
               (contract_id, bank_id, asset_type, start_date, settlement_date, due_date,
                principal, rate_cdi, status, contract_bank, contract_id_bank, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'ACTIVE', ?, ?, ?)
               ON CONFLICT(contract_id) DO UPDATE SET
                 bank_id=excluded.bank_id, asset_type=excluded.asset_type,
                 start_date=excluded.start_date, settlement_date=excluded.settlement_date,
                 due_date=excluded.due_date, principal=excluded.principal,
                 rate_cdi=excluded.rate_cdi, status=excluded.status,
                 contract_bank=excluded.contract_bank, contract_id_bank=excluded.contract_id_bank,
                 notes=excluded.notes""",
            (contract["contract_id"], contract["bank_id"], contract["asset_type"],
             contract["start_date"], contract["settlement_date"], contract["due_date"],
             str(contract["principal"]), str(contract["rate_cdi"]), contract["contract_bank"],
             contract["contract_id_bank"], contract["notes"]),
        )

        installment_specs = [
            ("APPLICATION", contract["settlement_date"], "Out", -contract["principal"], "SETTLED",
             "Saida de caixa para aplicacao"),
            ("PRINCIPAL_RETURN", contract["due_date"], "In", contract["principal"], "PROJECTED",
             "Devolucao do principal no vencimento"),
            ("INTEREST", contract["due_date"], "In", gross_interest, "PROJECTED",
             f"Projecao simples ({contract['rate_cdi']}% CDI; CDI anual assumido em 10,5%)"),
            ("TAX_WITHHELD", contract["due_date"], "Out", -tax_amount, "PROJECTED",
             f"IR projetado ({tax_rate}% para {days} dias)"),
        ]
        installment_ids = {}
        for spec in installment_specs:
            installment_ids[spec[0]] = _upsert_installment(conn, contract, spec)

        description = "Saida de caixa para aplicacao"
        application_id = installment_ids["APPLICATION"]
        existing_rec = conn.execute(
            "SELECT reconciliation_id FROM reconciliations WHERE contract_id=? AND installment_id=? ORDER BY reconciliation_id LIMIT 1",
            (contract["contract_id"], application_id),
        ).fetchone()
        reconciliation_id = int(existing_rec[0]) if existing_rec else _next_id(conn, "reconciliations", "reconciliation_id")
        conn.execute(
            """INSERT INTO reconciliations
               (reconciliation_id, event_date, bank_id, contract_id, installment_id,
                description, amount, operation_bank_id, reconciled)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL)
               ON CONFLICT(reconciliation_id) DO UPDATE SET
                 event_date=excluded.event_date, bank_id=excluded.bank_id,
                 contract_id=excluded.contract_id, installment_id=excluded.installment_id,
                 description=excluded.description, amount=excluded.amount,
                 operation_bank_id=excluded.operation_bank_id, reconciled=NULL""",
            (reconciliation_id, contract["settlement_date"], contract["bank_id"],
             contract["contract_id"], application_id, description,
             str(-contract["principal"]), None),
        )

        batch_id = f"SETTLEMENT-{contract['contract_id']}"
        settlement_entries = [
            (f"1.1.2.01 - Aplicacoes {contract['asset_type']}", contract["principal"], None),
            (f"1.1.1.01 - Banco {contract['bank_id']} Conta Movimento", None, contract["principal"]),
        ]
        for account, debit, credit in settlement_entries:
            _upsert_accounting(
                conn, contract["contract_id"], "CASH_SETTLEMENT", contract["settlement_date"],
                account, debit, credit, f"Liquidacao aplicacao {contract['asset_type']} {contract['bank_id']}", batch_id,
            )

    return {
        "contract_id": contract["contract_id"],
        "installment_count": len(installment_specs),
        "accounting_count": 2,
        "reconciliation_id": reconciliation_id,
        "days": days,
        "gross_interest": gross_interest,
        "tax_rate": tax_rate,
        "tax_amount": tax_amount,
    }


def calculate_accrual(contract_id, target_date, db_path=DB_PATH, record_accounting=False):
    target = parse_date(target_date)
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        row = conn.execute(
            "SELECT principal, rate_cdi, settlement_date, asset_type, bank_id FROM contracts WHERE contract_id=?",
            (contract_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"contrato {contract_id!r} nao encontrado")
        principal, rate_cdi, settlement_value, asset_type, bank_id = row
        settlement = parse_date(settlement_value)
        days = (target - settlement).days
        if days < 0:
            raise ValueError("data de calculo anterior a liquidacao")
        rate = Decimal(str(rate_cdi))
        principal = Decimal(str(principal))
        interest = (principal * (rate / Decimal("100")) * ANNUAL_CDI_ASSUMPTION
                    * Decimal(days) / Decimal("365")).quantize(CENT, rounding=ROUND_HALF_UP)
        tax_rate = get_tax_rate(conn, days)
        tax = (interest * tax_rate / Decimal("100")).quantize(CENT, rounding=ROUND_HALF_UP)
        if record_accounting:
            description = f"Apropriacao de juros em {target.isoformat()} - {contract_id}"
            for account, debit, credit in (
                (f"1.1.2.02 - Juros a Receber s/ {asset_type}", interest, None),
                ("3.1.1.01 - Receita Financeira de Juros", None, interest),
            ):
                _upsert_accounting(conn, contract_id, "MONTHLY_ACCRUAL", target.isoformat(),
                                   account, debit, credit, description,
                                   f"ACCRUAL-{contract_id}-{target.isoformat()}")
    return {"contract_id": contract_id, "as_of_date": target.isoformat(), "days": days,
            "gross_interest": interest, "tax_rate": tax_rate, "tax_amount": tax,
            "gross_balance": principal + interest, "net_balance": principal + interest - tax}
