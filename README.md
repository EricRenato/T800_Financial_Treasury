# T-800 Financial Treasury — Reconciliation Platform

A deterministic treasury reconciliation and cash investment validation engine. Replicates corporate treasury logic by independently calculating CDI-indexed accruals, generating balanced double-entry accounting entries, and matching internal events against bank statements with an append-only audit trail.

---

## Overview

Corporate treasuries handle high-volume fixed-income assets (e.g., CDBs indexed to CDI). Discrepancies between bank-reported figures and internal accounting can compromise financial reporting. 

The **T-800 Platform** provides an independent analytics layer that:
1. **Validates Contracts:** Ingests investment contracts and unfolds them into operational cash flows.
2. **Projects Accrual & Taxes:** Computes independent daily CDI accrual and Brazilian regressive income tax (IR 22.5% to 15.0%).
3. **Generates Ledger Entries:** Automatically books balanced double-entry accounting records.
4. **Reconciles Two-Sided Flows:** Matches internal records against bank statements within configurable tolerances.
5. **Audits Discrepancies:** Persists execution evidence with unique run IDs and deterministic mismatch categorization.

---

## Architecture & Workflow
