/**
 * НейроЗнайко · Готовність до школи — приймач знеособлених даних.
 * Версія 0.1 (10.10.2026). Окрема таблиця й окремий скрипт: із дипломним дослідженням НейроЗнайко не пов'язані.
 *
 * Як підключити:
 *  1. Створіть нову Google-таблицю (наприклад, «Готовність до школи — дані»).
 *  2. Розширення → Apps Script. Видаліть увесь код, вставте цей. Ctrl+S.
 *  3. Deploy → New deployment → тип Web app → Execute as: Me, Who has access: Anyone → Deploy.
 *  4. Скопіюйте URL (закінчується на /exec) і вставте його в gotovnist.html у рядок ENDPOINT:"".
 *
 * Аркуші створюються автоматично:
 *   sessions — один рядок на проходження (оновлюється після кожного підтесту);
 *   trials   — один рядок на кожну пробу;
 *   parent, teacher — анкети (будуть на етапі 6);
 *   _batches — службовий: уже прийняті пакети, щоб повторне надсилання не дублювало рядки.
 * Ім'я та дата народження дитини застосунок НЕ надсилає.
 */
const SHEETS = ['sessions', 'trials', 'parent', 'teacher', '_batches'];

function doGet() { return ContentService.createTextOutput('Готовність до школи: приймач працює'); }

function doPost(e) {
  const lock = LockService.getScriptLock();
  lock.waitLock(25000);
  try {
    const p = JSON.parse(e.postData.contents);
    const ss = SpreadsheetApp.getActiveSpreadsheet();
    SHEETS.forEach(n => { if (!ss.getSheetByName(n)) ss.insertSheet(n); });
    if (p.batch && seen_(ss, p.batch)) return json_({ ok: true, duplicate: true });
    const now = new Date().toISOString();

    if (p.type === 'session') {
      if (!p.row || !p.row.session) return json_({ ok: false, error: 'no session' });
      upsert_(ss.getSheetByName('sessions'), 'session', Object.assign({ received_at: now }, p.row));
    } else if (p.type === 'trials') {
      const rows = (p.rows || []).map(r => Object.assign({ received_at: now }, r));
      if (rows.length) appendRows_(ss.getSheetByName('trials'), rows);
    } else if (p.type === 'parent' || p.type === 'teacher') {
      if (!p.row) return json_({ ok: false, error: 'no row' });
      appendRows_(ss.getSheetByName(p.type), [Object.assign({ received_at: now }, p.row)]);
    } else {
      return json_({ ok: false, error: 'unknown type' });
    }
    if (p.batch) ss.getSheetByName('_batches').appendRow([p.batch, now, p.type]);
    return json_({ ok: true });
  } catch (err) {
    return json_({ ok: false, error: String(err) });
  } finally {
    lock.releaseLock();
  }
}

/** Чи вже приймали пакет із таким ідентифікатором. */
function seen_(ss, batch) {
  const sh = ss.getSheetByName('_batches');
  if (sh.getLastRow() < 1) return false;
  return sh.getRange(1, 1, sh.getLastRow(), 1).createTextFinder(batch).matchEntireCell(true).findNext() !== null;
}

/** Рядок із таким ключем оновлюється, а якщо його немає — додається. */
function upsert_(sheet, key, obj) {
  const headers = ensureHeaders_(sheet, [obj]);
  const kc = headers.indexOf(key) + 1;
  let row = 0;
  if (sheet.getLastRow() > 1) {
    const f = sheet.getRange(2, kc, sheet.getLastRow() - 1, 1).createTextFinder(String(obj[key])).matchEntireCell(true).findNext();
    if (f) row = f.getRow();
  }
  if (!row) row = sheet.getLastRow() + 1;
  sheet.getRange(row, 1, 1, headers.length).setValues([headers.map(h => cell_(obj[h]))]);
}

/** Дописує рядки, автоматично додаючи нові стовпці, якщо з'являються нові поля. */
function appendRows_(sheet, objs) {
  const headers = ensureHeaders_(sheet, objs);
  sheet.getRange(sheet.getLastRow() + 1, 1, objs.length, headers.length).setValues(objs.map(o => headers.map(h => cell_(o[h]))));
}
function ensureHeaders_(sheet, objs) {
  let headers = sheet.getLastColumn() ? sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0].filter(String) : [];
  const missing = [];
  objs.forEach(o => Object.keys(o).forEach(k => { if (headers.indexOf(k) < 0 && missing.indexOf(k) < 0) missing.push(k); }));
  if (missing.length) {
    headers = headers.concat(missing);
    sheet.getRange(1, 1, 1, headers.length).setValues([headers]);
    sheet.setFrozenRows(1);
  }
  return headers;
}
function cell_(v) { return v === undefined || v === null ? '' : (typeof v === 'object' ? JSON.stringify(v) : v); }
function json_(obj) { return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON); }
