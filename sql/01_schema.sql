-- Idempotent local schema. This file intentionally does not drop user data.
CREATE TABLE IF NOT EXISTS contracts (
    contract_id TEXT PRIMARY KEY,
    bank_id TEXT NOT NULL,
    asset_type TEXT NOT NULL,
    start_date TEXT NOT NULL,
    settlement_date TEXT NOT NULL,
    due_date TEXT NOT NULL,
    principal NUMERIC NOT NULL,
    rate_cdi NUMERIC NOT NULL,
    status TEXT NOT NULL,
    contract_bank TEXT,
    contract_id_bank TEXT,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS installments (
    installment_id INTEGER PRIMARY KEY,
    contract_id TEXT NOT NULL,
    bank_id TEXT NOT NULL,
    installment_type TEXT NOT NULL,
    due_date TEXT NOT NULL,
    flow_type TEXT NOT NULL,
    amount NUMERIC NOT NULL,
    status TEXT NOT NULL,
    notes TEXT,
    FOREIGN KEY (contract_id) REFERENCES contracts(contract_id)
);

CREATE TABLE IF NOT EXISTS reconciliations (
    reconciliation_id INTEGER PRIMARY KEY,
    event_date TEXT NOT NULL,
    bank_id TEXT NOT NULL,
    contract_id TEXT,
    installment_id INTEGER,
    description TEXT NOT NULL,
    amount NUMERIC NOT NULL,
    operation_bank_id TEXT,
    reconciled TEXT
);

CREATE TABLE IF NOT EXISTS statements (
    statement_id TEXT PRIMARY KEY,
    external_ref TEXT NOT NULL,
    bank_id TEXT NOT NULL,
    statement_date TEXT NOT NULL,
    settlement_date TEXT NOT NULL,
    description TEXT,
    face_amount NUMERIC NOT NULL,
    reconciled TEXT
);

CREATE TABLE IF NOT EXISTS accounting (
    entry_id INTEGER PRIMARY KEY,
    contract_id TEXT NOT NULL,
    entry_type TEXT NOT NULL,
    accounting_date TEXT NOT NULL,
    accounting_account TEXT NOT NULL,
    debit NUMERIC,
    credit NUMERIC,
    description TEXT NOT NULL,
    accounting_batch_id TEXT,
    FOREIGN KEY (contract_id) REFERENCES contracts(contract_id)
);

CREATE TABLE IF NOT EXISTS account_balance (
    account_bank_id INTEGER NOT NULL,
    bank_id TEXT NOT NULL,
    balance_date TEXT NOT NULL,
    balance NUMERIC NOT NULL,
    PRIMARY KEY (account_bank_id, balance_date)
);

CREATE TABLE IF NOT EXISTS taxes (
    tax_id INTEGER PRIMARY KEY AUTOINCREMENT,
    tax_type TEXT NOT NULL,
    min_days INTEGER,
    max_days INTEGER,
    rate_pct NUMERIC,
    description TEXT
);

CREATE TABLE IF NOT EXISTS divergences (
    divergence_id INTEGER PRIMARY KEY AUTOINCREMENT,
    reconciliation_id INTEGER NOT NULL,
    divergence_type TEXT NOT NULL,
    field_name TEXT NOT NULL,
    expected_value TEXT NOT NULL,
    actual_value TEXT NOT NULL,
    financial_impact NUMERIC NOT NULL DEFAULT 0,
    evidence_notes TEXT,
    FOREIGN KEY (reconciliation_id) REFERENCES reconciliations(reconciliation_id)
);

-- Append-only, auditable output from each reconciliation execution.
CREATE TABLE IF NOT EXISTS reconciliation_evidence (
    evidence_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    processed_at TEXT NOT NULL,
    reconciliation_id INTEGER,
    statement_id TEXT,
    status TEXT NOT NULL,
    contract_ref TEXT,
    bank_id TEXT,
    internal_amount TEXT,
    bank_amount TEXT,
    amount_difference TEXT,
    internal_date TEXT,
    bank_date TEXT,
    date_difference_days INTEGER,
    financial_impact TEXT NOT NULL DEFAULT '0.00',
    reason TEXT NOT NULL,
    FOREIGN KEY (reconciliation_id) REFERENCES reconciliations(reconciliation_id),
    FOREIGN KEY (statement_id) REFERENCES statements(statement_id)
);

CREATE INDEX IF NOT EXISTS idx_reconciliations_contract_bank
    ON reconciliations(contract_id, bank_id);
CREATE INDEX IF NOT EXISTS idx_statements_external_bank
    ON statements(external_ref, bank_id);
CREATE INDEX IF NOT EXISTS idx_evidence_run
    ON reconciliation_evidence(run_id);

INSERT INTO taxes (tax_type, min_days, max_days, rate_pct, description)
SELECT 'IR', 0, 180, 22.50, 'Ate 180 dias corridos'
WHERE NOT EXISTS (SELECT 1 FROM taxes WHERE tax_type='IR' AND min_days=0 AND max_days=180);
INSERT INTO taxes (tax_type, min_days, max_days, rate_pct, description)
SELECT 'IR', 181, 360, 20.00, 'De 181 a 360 dias corridos'
WHERE NOT EXISTS (SELECT 1 FROM taxes WHERE tax_type='IR' AND min_days=181 AND max_days=360);
INSERT INTO taxes (tax_type, min_days, max_days, rate_pct, description)
SELECT 'IR', 361, 720, 17.50, 'De 361 a 720 dias corridos'
WHERE NOT EXISTS (SELECT 1 FROM taxes WHERE tax_type='IR' AND min_days=361 AND max_days=720);
INSERT INTO taxes (tax_type, min_days, max_days, rate_pct, description)
SELECT 'IR', 721, 9999, 15.00, 'Acima de 720 dias corridos'
WHERE NOT EXISTS (SELECT 1 FROM taxes WHERE tax_type='IR' AND min_days=721 AND max_days=9999);
