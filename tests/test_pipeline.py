import sys
from decimal import Decimal
from pathlib import Path
import sqlite3
import pytest

# Adiciona pasta src ao sys.path
sys.path.append(str(Path(__file__).resolve().parent.parent / "src"))

from common import money, parse_date
from init_db import initialize_database
from contract_engine import create_and_unfold_contract, calculate_accrual, validate_contract
from reconcile import run_reconciliation

@pytest.fixture
def temp_db(tmp_path):
    db_file = tmp_path / "test_t800.db"
    initialize_database(db_file)
    return db_file

def test_validate_contract_success():
    payload = {
        'contract_id': 'CT-TEST-01',
        'bank_id': 'Itau',
        'asset_type': 'CDB',
        'start_date': '01/09/2026',
        'settlement_date': '01/09/2026',
        'due_date': '01/09/2027',
        'principal': '1000000.00',
        'rate_cdi': '103.50'
    }
    validated = validate_contract(payload)
    assert validated['contract_id'] == 'CT-TEST-01'
    assert validated['principal'] == Decimal('1000000.00')

def test_validate_contract_invalid_dates():
    payload = {
        'contract_id': 'CT-TEST-ERR',
        'bank_id': 'Itau',
        'asset_type': 'CDB',
        'start_date': '02/09/2026',
        'settlement_date': '01/09/2026',  # Invalido: start > settlement
        'due_date': '01/09/2027',
        'principal': '100000.00',
        'rate_cdi': '100.00'
    }
    with pytest.raises(ValueError):
        validate_contract(payload)

def test_contract_unfold(temp_db):
    payload = {
        'contract_id': 'CT-TEST-02',
        'bank_id': 'Itau',
        'asset_type': 'CDB',
        'start_date': '01/09/2026',
        'settlement_date': '01/09/2026',
        'due_date': '01/09/2027',
        'principal': '1000000.00',
        'rate_cdi': '103.50'
    }
    res = create_and_unfold_contract(payload, db_path=temp_db)
    assert res['installment_count'] == 4
    assert res['accounting_count'] == 2

    with sqlite3.connect(temp_db) as conn:
        insts = conn.execute("SELECT installment_type, amount FROM installments WHERE contract_id = ? ORDER BY installment_id", ('CT-TEST-02',)).fetchall()
        assert insts[0][0] == 'APPLICATION'
        assert Decimal(str(insts[0][1])) == Decimal('-1000000.00')
        assert insts[1][0] == 'PRINCIPAL_RETURN'
        assert Decimal(str(insts[1][1])) == Decimal('1000000.00')

def test_accrual_calculation(temp_db):
    payload = {
        'contract_id': 'CT-TEST-03',
        'bank_id': 'Itau',
        'asset_type': 'CDB',
        'start_date': '01/09/2026',
        'settlement_date': '01/09/2026',
        'due_date': '01/09/2027',
        'principal': '1000000.00',
        'rate_cdi': '103.50'
    }
    create_and_unfold_contract(payload, db_path=temp_db)
    accrual = calculate_accrual('CT-TEST-03', '30/09/2026', db_path=temp_db, record_accounting=True)
    assert accrual['days'] == 29
    assert accrual['tax_rate'] == Decimal('22.50')
    assert accrual['gross_interest'] > Decimal('0.00')

def test_reconciliation_scenarios(temp_db):
    payload = {
        'contract_id': 'CT-MATCH',
        'bank_id': 'Itau',
        'asset_type': 'CDB',
        'start_date': '01/09/2026',
        'settlement_date': '01/09/2026',
        'due_date': '01/09/2027',
        'principal': '1000000.00',
        'rate_cdi': '103.50'
    }
    create_and_unfold_contract(payload, db_path=temp_db)

    with sqlite3.connect(temp_db) as conn:
        conn.execute("""
            INSERT INTO statements (statement_id, external_ref, bank_id, statement_date, settlement_date, face_amount)
            VALUES ('EXT-OK', 'CT-MATCH', 'Itau', '2026-09-01', '2026-09-01', '-1000000.00');
        """)
        conn.execute("""
            INSERT INTO statements (statement_id, external_ref, bank_id, statement_date, settlement_date, face_amount)
            VALUES ('EXT-ORPHAN', 'CT-NONE', 'Itau', '2026-09-01', '2026-09-01', '-500000.00');
        """)

    recon = run_reconciliation(db_path=temp_db)
    assert recon['counts']['MATCHED'] == 1
    assert recon['counts']['MISSING_INTERNAL'] == 1
