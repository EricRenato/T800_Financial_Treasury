/** Google Sheets button and visible run log for the financial reconciliation demo. */

function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu('Reconciliação')
    .addItem('Processar contrato selecionado', 'processSelectedContract')
    .addToUi();
}

function processSelectedContract() {
  const spreadsheet = SpreadsheetApp.getActiveSpreadsheet();
  const contractsSheet = spreadsheet.getSheetByName('contracts');
  if (!contractsSheet || spreadsheet.getActiveSheet().getName() !== 'contracts') {
    throw new Error('Abra a aba contracts e selecione uma linha de contrato.');
  }

  const selectedRow = contractsSheet.getActiveRange().getRow();
  if (selectedRow < 2) throw new Error('Selecione uma linha de contrato abaixo do cabeçalho.');

  const contract = rowObject_(contractsSheet, selectedRow);
  if (!contract.contract_id) throw new Error('A linha selecionada não contém contract_id.');

  const properties = PropertiesService.getScriptProperties();
  const apiUrl = (properties.getProperty('API_URL') || '').replace(/\/$/, '');
  const apiKey = properties.getProperty('API_KEY') || '';
  if (!apiUrl || !apiKey) {
    throw new Error('Configure API_URL e API_KEY nas propriedades do projeto Apps Script.');
  }

  const clientStartedAt = new Date();
  let runId = Utilities.getUuid();
  try {
    const payload = {
      contracts: [contract],
      statements: matchingStatements_(spreadsheet.getSheetByName('statements'), contract)
    };
    const response = UrlFetchApp.fetch(apiUrl + '/process', {
      method: 'post',
      contentType: 'application/json',
      headers: {'X-API-Key': apiKey},
      payload: JSON.stringify(payload),
      muteHttpExceptions: true
    });
    const statusCode = response.getResponseCode();
    const responseText = response.getContentText();
    if (statusCode < 200 || statusCode >= 300) {
      throw new Error('Serviço respondeu HTTP ' + statusCode + ': ' + responseText);
    }

    const result = JSON.parse(responseText);
    runId = result.run_id;
    writeOutputTable_(spreadsheet, 'installments', result.tables.installments,
      ['contract_id', 'installment_type']);
    writeOutputTable_(spreadsheet, 'accounting', result.tables.accounting,
      ['contract_id', 'entry_type']);
    const reconciliationIds = upsertReconciliations_(spreadsheet, result.tables.reconciliations);
    updateStatementStatuses_(spreadsheet, result.tables.statements);
    appendEvidence_(spreadsheet, result.tables.evidence, reconciliationIds);
    appendRunLog_(spreadsheet, [runId, clientStartedAt, contract.contract_id,
      summarizeCounts_(result.counts), 'Concluído', '']);

    spreadsheet.toast('Contrato processado. Resultado: ' + summarizeCounts_(result.counts), 'Reconciliação', 6);
  } catch (error) {
    appendRunLog_(spreadsheet, [runId, clientStartedAt, contract.contract_id,
      '', 'Erro', String(error.message || error)]);
    spreadsheet.toast('Falha no processamento. Veja a aba processing_runs.', 'Reconciliação', 8);
    throw error;
  }
}

function rowObject_(sheet, rowNumber) {
  const values = sheet.getRange(rowNumber, 1, 1, sheet.getLastColumn()).getValues()[0];
  const headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getDisplayValues()[0];
  const result = {};
  headers.forEach(function (header, index) {
    const key = canonicalField_(header, sheet.getName());
    if (key) result[key] = normalizeInput_(key, values[index], sheet.getParent());
  });
  return result;
}

function readRows_(sheet) {
  if (!sheet || sheet.getLastRow() < 2 || sheet.getLastColumn() < 1) return [];
  const values = sheet.getRange(1, 1, sheet.getLastRow(), sheet.getLastColumn()).getValues();
  const headers = values.shift().map(function (header) {
    return canonicalField_(header, sheet.getName());
  });
  return values.filter(function (row) {
    return row.some(function (value) { return value !== '' && value !== null; });
  }).map(function (row) {
    const item = {};
    headers.forEach(function (key, index) {
      if (key) item[key] = normalizeInput_(key, row[index], sheet.getParent());
    });
    return item;
  });
}

function matchingStatements_(sheet, contract) {
  const references = [contract.contract_id, contract.contract_id_bank, contract.contract_bank]
    .map(function (value) { return String(value || '').trim().toLowerCase(); })
    .filter(function (value) { return value; });
  const bank = String(contract.bank_id || '').trim().toLowerCase();
  return readRows_(sheet).filter(function (statement) {
    return String(statement.bank_id || '').trim().toLowerCase() === bank &&
      references.indexOf(String(statement.external_ref || '').trim().toLowerCase()) >= 0;
  });
}

function normalizeInput_(field, value, spreadsheet) {
  if (value instanceof Date) {
    return Utilities.formatDate(value, spreadsheet.getSpreadsheetTimeZone(), 'yyyy-MM-dd');
  }
  if (field === 'settlement_date' || field === 'statement_date' || field === 'start_date' ||
      field === 'due_date' || field === 'event_date' || field === 'accounting_date') {
    const text = String(value || '').trim();
    const match = text.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/);
    if (match) return match[3] + '-' + match[2].padStart(2, '0') + '-' + match[1].padStart(2, '0');
  }
  if (typeof value === 'string') return value.trim();
  return value;
}

function canonicalField_(header, sheetName) {
  const raw = String(header || '').trim().toLowerCase().replace(/[^a-z0-9]/g, '');
  const aliases = {
    contractid: 'contract_id', bankid: 'bank_id', assettype: 'asset_type',
    startdate: 'start_date', settlementdate: 'settlement_date', duedate: 'due_date',
    principal: 'principal', ratecdi: 'rate_cdi', contractbank: 'contract_bank',
    contractidbank: 'contract_id_bank', installmentid: 'installment_id',
    installmenttype: 'installment_type', statementid: 'statement_id',
    externalref: 'external_ref', statementdate: 'statement_date', faceamount: 'face_amount',
    entryid: 'entry_id', entrytype: 'entry_type', accountingaccount: 'accounting_account',
    accountingbatchid: 'accounting_batch_id', reconciliationid: 'reconciliation_id',
    eventdate: 'event_date', operationbankid: 'operation_bank_id',
    flowtype: 'flow_type', accountingdate: 'accounting_date',
    accountbankid: 'account_bank_id', accountbalance: 'account_balance',
    tax_type: 'tax_type', mintaxdays: 'min_days', maxdays: 'max_days',
    ratepct: 'rate_pct', amount: 'amount', debit: 'debit', credit: 'credit',
    description: 'description', status: 'status', reconciled: 'reconciled', notes: 'notes',
    mindays: 'min_days', max_days: 'max_days', taxrate: 'rate_pct'
  };
  if (sheetName === 'reconciliations' && raw === 'date') return 'event_date';
  if (sheetName === 'account balance' && raw === 'bank') return 'bank';
  if (raw === 'date' && (sheetName === 'accountbalance')) return 'date';
  if (sheetName === 'accounting' && raw === 'd') return 'debit';
  if (sheetName === 'accounting' && raw === 'c') return 'credit';
  if (sheetName === 'accounting' && raw === 'accoutingdate') return 'accounting_date';
  if (raw === 'acoountingid' || raw === 'accoutingid') return 'accounting_batch_id';
  if (aliases[raw]) return aliases[raw];
  return raw;
}

function writeOutputTable_(spreadsheet, sheetName, newRows, replaceKeys) {
  if (!newRows || !newRows.length) return;
  const sheet = getOrCreateSheet_(spreadsheet, sheetName);
  const headers = Object.keys(newRows[0]);
  const current = sheet.getDataRange().getValues();
  const oldHeaders = current.length ? current[0].map(function (header) {
    return canonicalField_(header, sheetName);
  }) : [];
  const preserved = [];
  for (let rowIndex = 1; rowIndex < current.length; rowIndex++) {
    const oldObject = {};
    oldHeaders.forEach(function (header, columnIndex) {
      if (header) oldObject[header] = current[rowIndex][columnIndex];
    });
    const isSameRecord = replaceKeys.every(function (key) {
      return String(oldObject[key] || '').trim() === String(newRows[0][key] || '').trim();
    });
    if (!isSameRecord && Object.keys(oldObject).some(function (key) { return oldObject[key] !== ''; })) {
      preserved.push(headers.map(function (header) { return oldObject[header] === undefined ? '' : oldObject[header]; }));
    }
  }
  const output = [headers].concat(preserved).concat(newRows.map(function (row) {
    return headers.map(function (header) { return row[header] === undefined ? '' : row[header]; });
  }));
  sheet.clearContents();
  sheet.getRange(1, 1, output.length, headers.length).setValues(output);
  sheet.setFrozenRows(1);
  sheet.getRange(1, 1, 1, headers.length).setFontWeight('bold');
}

function upsertReconciliations_(spreadsheet, records) {
  const sheet = getOrCreateSheet_(spreadsheet, 'reconciliations');
  if (!records || !records.length) return {};
  let lastColumn = Math.max(sheet.getLastColumn(), 1);
  let headers = sheet.getRange(1, 1, 1, lastColumn).getDisplayValues()[0];
  const required = Object.keys(records[0]);
  const canonicalHeaders = headers.map(function (header) { return canonicalField_(header, 'reconciliations'); });
  required.forEach(function (field) {
    if (canonicalHeaders.indexOf(field) < 0) {
      lastColumn++;
      sheet.getRange(1, lastColumn).setValue(field);
      headers.push(field);
      canonicalHeaders.push(field);
    }
  });

  const rows = sheet.getLastRow() > 1
    ? sheet.getRange(2, 1, sheet.getLastRow() - 1, lastColumn).getValues() : [];
  const idColumn = canonicalHeaders.indexOf('reconciliation_id');
  const contractColumn = canonicalHeaders.indexOf('contract_id');
  const installmentColumn = canonicalHeaders.indexOf('installment_id');
  const resultIds = {};
  records.forEach(function (record) {
    let targetRow = -1;
    for (let index = 0; index < rows.length; index++) {
      if (String(rows[index][contractColumn] || '').trim() === String(record.contract_id || '').trim() &&
          String(rows[index][installmentColumn] || '').trim() === String(record.installment_id || '').trim()) {
        targetRow = index + 2;
        break;
      }
    }
    let outputRecord = Object.assign({}, record);
    if (targetRow < 0) {
      const maxId = rows.reduce(function (currentMax, row) {
        return Math.max(currentMax, Number(row[idColumn]) || 0);
      }, 0);
      outputRecord.reconciliation_id = maxId + 1;
      targetRow = sheet.getLastRow() + 1;
    } else if (idColumn >= 0) {
      outputRecord.reconciliation_id = rows[targetRow - 2][idColumn];
    }
    const outputValues = canonicalHeaders.map(function (field) {
      return outputRecord[field] === undefined ? '' : outputRecord[field];
    });
    sheet.getRange(targetRow, 1, 1, outputValues.length).setValues([outputValues]);
    rows[targetRow - 2] = outputValues;
    resultIds[String(record.reconciliation_id)] = outputRecord.reconciliation_id;
  });
  return resultIds;
}

function updateStatementStatuses_(spreadsheet, records) {
  const sheet = spreadsheet.getSheetByName('statements');
  if (!sheet || !records || !records.length) return;
  const values = sheet.getDataRange().getValues();
  const headers = values[0].map(function (header) { return canonicalField_(header, 'statements'); });
  const idColumn = headers.indexOf('statement_id');
  let statusColumn = headers.indexOf('reconciled');
  if (statusColumn < 0) {
    statusColumn = headers.length;
    sheet.getRange(1, statusColumn + 1).setValue('reconciled');
  }
  const statuses = {};
  records.forEach(function (record) { statuses[String(record.statement_id)] = record.reconciled; });
  for (let rowIndex = 1; rowIndex < values.length; rowIndex++) {
    const statementId = String(values[rowIndex][idColumn] || '');
    if (Object.prototype.hasOwnProperty.call(statuses, statementId)) {
      sheet.getRange(rowIndex + 1, statusColumn + 1).setValue(statuses[statementId]);
    }
  }
}

function appendEvidence_(spreadsheet, records, reconciliationIds) {
  if (!records || !records.length) return;
  const sheet = getOrCreateSheet_(spreadsheet, 'reconciliation_evidence');
  const headers = Object.keys(records[0]);
  if (sheet.getLastRow() === 0) sheet.appendRow(headers);
  const mapped = records.map(function (record) {
    const output = Object.assign({}, record);
    output.reconciliation_id = reconciliationIds[String(record.reconciliation_id)] || record.reconciliation_id;
    return headers.map(function (header) { return output[header] === undefined ? '' : output[header]; });
  });
  sheet.getRange(sheet.getLastRow() + 1, 1, mapped.length, headers.length).setValues(mapped);
}

function appendRunLog_(spreadsheet, row) {
  const sheet = getOrCreateSheet_(spreadsheet, 'processing_runs');
  if (sheet.getLastRow() === 0) {
    sheet.appendRow(['run_id', 'started_at', 'contract_id', 'result_summary', 'status', 'message']);
    sheet.setFrozenRows(1);
    sheet.getRange(1, 1, 1, 6).setFontWeight('bold');
  }
  sheet.appendRow(row);
}

function getOrCreateSheet_(spreadsheet, name) {
  return spreadsheet.getSheetByName(name) || spreadsheet.insertSheet(name);
}

function summarizeCounts_(counts) {
  return Object.keys(counts).sort().map(function (key) { return key + ': ' + counts[key]; }).join(', ') || 'Sem registros';
}
