const { getSheetsClient } = require('./googleAuth');
const crypto = require('crypto');
const {
  buildColumnMap,
  rowArrayToValues,
  normalizePhone,
  normalizeGroup,
  columnIndexToLetter,
  letterToColumnIndex,
  MANAGER_EDITABLE,
  REF_SHEETS,
  RENEWAL_FIELDS,
  appendContactHistoryNote,
  parseContactHistory,
  LMS_TEMPLATE_CATEGORIES,
  LEASE_PLEDGE_DEFAULTS,
  formatRegisteredAt,
} = require('./sheetSchema');
const { sanitizeNotepadHtml, escapeHtml } = require('./sanitizeHtml');

const ADMIN_SPREADSHEET_ID = process.env.ADMIN_SPREADSHEET_ID;
const ACCOUNTS_SHEET_TITLE = '계정관리';
const MAX_FAILED_ATTEMPTS = 5;
// 관리자 계정은 잠기면 아무도 풀어줄 수 없으므로(잠금 해제는 관리자만 가능),
// 잠그는 대신 이 비밀번호로 자동 초기화합니다.
const ADMIN_AUTO_RESET_PASSWORD = '@dkwjd12';

// "계정관리" 탭의 컬럼 순서: 아이디 | 비밀번호 | 이름 | 권한 | 개인시트URL | 비고 | 실패횟수 | 잠김여부
const ACCOUNT_COLUMNS = {
  loginId: 'A',
  password: 'B',
  name: 'C',
  role: 'D',
  sheetUrl: 'E',
  note: 'F',
  failedAttempts: 'G',
  locked: 'H',
};

// 상단 공지사항은 새 탭을 만들지 않고 "계정관리" 탭의 사용하지 않는 셀(J1)에 텍스트 한 줄로 저장합니다.
const ANNOUNCEMENT_CELL = 'J1';
const ANNOUNCEMENT_MAX_LENGTH = 50;

// 같은 서버 인스턴스에서 너무 자주 구글 API를 호출하지 않도록 짧게 캐시합니다.
const CACHE_TTL_MS = 2 * 60 * 1000; // 2분 — Google Sheets API 호출 빈도 제한
const sheetDataCache = new Map(); // spreadsheetId -> { expires, data }
const dataSheetTitleCache = new Map(); // spreadsheetId -> title
const refSheetCache = new Map(); // refSheet key -> { expires, data }
const notepadCache = new Map(); // refSheet key -> { expires, data }
const templatesCache = new Map(); // refSheet key -> { expires, data }
const registryCache = new Map(); // refSheet key -> { expires, data }
const linkHubCache = new Map(); // refSheet key -> { expires, data }
let renewalCache = null; // { expires, data }
let accountsCache = null; // { expires, accounts }
let announcementCache = null; // { expires, text }
let performanceCache = null; // { expires, data }
// 병합·정렬·ETag까지 마친 최종 결과 캐시. 캐시 HIT 시 이 세 연산을 전부 건너뜁니다.
let adminResultCache = null;     // { expires, sheetTitle, columnMap, rows, etag }
let adminRebuildInFlight = null; // 동시 재빌드 중복 방지용 Promise

let kamasterCache = null; // { expires, loginStatusMap: Map<phone, hasLoginId> }

const PERFORMANCE_SHEET_TITLE = '관리_컨택 대시보드';

function quoteSheetTitle(title) {
  return `'${String(title).replace(/'/g, "''")}'`;
}

// 스프레드시트 안에서 "연락처"와 "담당매니저" 헤더가 모두 있는 탭을 데이터 탭으로 인식합니다.
// 관리자용/매니저용 모두 탭 이름이 달라도 동작하도록 만든 자동 탐색 로직입니다.
async function findDataSheetTitle(spreadsheetId) {
  if (dataSheetTitleCache.has(spreadsheetId)) {
    return dataSheetTitleCache.get(spreadsheetId);
  }
  const sheets = getSheetsClient();
  const meta = await sheets.spreadsheets.get({
    spreadsheetId,
    fields: 'sheets.properties.title',
  });
  const titles = (meta.data.sheets || []).map((s) => s.properties.title);
  if (titles.length === 0) {
    throw new Error(`스프레드시트(${spreadsheetId})에서 회원 데이터 탭을 찾지 못했습니다.`);
  }

  // 모든 탭 헤더를 한 번의 batchGet으로 읽음 (이전: 탭마다 순서대로 API 호출 → N회 → 6초+)
  const ranges = titles.map((t) => `${quoteSheetTitle(t)}!A1:Z1`);
  const batchRes = await sheets.spreadsheets.values.batchGet({ spreadsheetId, ranges });
  const valueRanges = batchRes.data.valueRanges || [];

  for (let i = 0; i < titles.length; i++) {
    const headerRow = (valueRanges[i]?.values?.[0]) || [];
    const map = buildColumnMap(headerRow);
    if (map.phone !== undefined && map.manager !== undefined) {
      dataSheetTitleCache.set(spreadsheetId, titles[i]);
      return titles[i];
    }
  }
  throw new Error(`스프레드시트(${spreadsheetId})에서 회원 데이터 탭을 찾지 못했습니다.`);
}

async function readSheetRows(spreadsheetId, { useCache = true } = {}) {
  const cached = sheetDataCache.get(spreadsheetId);
  if (useCache && cached && cached.expires > Date.now()) {
    return cached.data;
  }

  const sheets = getSheetsClient();
  const sheetTitle = await findDataSheetTitle(spreadsheetId);
  const range = quoteSheetTitle(sheetTitle);
  const res = await sheets.spreadsheets.values.get({ spreadsheetId, range });
  const values = res.data.values || [];
  const headerRow = values[0] || [];
  const columnMap = buildColumnMap(headerRow);

  const rows = values.slice(1).map((rowArray, i) => {
    const vals = rowArrayToValues(rowArray, columnMap);
    if (vals.group) vals.group = normalizeGroup(vals.group);
    return { rowNumber: i + 2, values: vals };
  }).filter((r) => r.values.phone || r.values.name);

  const data = { sheetTitle, columnMap, rows };
  sheetDataCache.set(spreadsheetId, { expires: Date.now() + CACHE_TTL_MS, data });
  return data;
}

function invalidateCache(spreadsheetId) {
  sheetDataCache.delete(spreadsheetId);
  if (spreadsheetId === ADMIN_SPREADSHEET_ID) {
    adminResultCache = null;
    // 쓰기 직후 백그라운드에서 미리 정렬+해싱까지 끝내둠 → 다음 읽기는 즉시 HIT
    rebuildAdminResultCache().catch((e) => console.error('admin result cache 재빌드 실패:', e));
  }
}

// 시트를 그대로 웹페이지에 심는 화면(REF_SHEETS)용: 의미별 컬럼 매핑 없이 셀 위치 그대로 읽고/씁니다.
function getRefSheetConfig(key) {
  const config = REF_SHEETS.find((s) => s.key === key);
  if (!config) throw new Error(`알 수 없는 시트입니다: ${key}`);
  return config;
}

function refSheetRange(config) {
  const base = quoteSheetTitle(config.title);
  if (config.colStart && config.colEnd) {
    return `${base}!${config.colStart}:${config.colEnd}`;
  }
  return base;
}

async function readRefSheetGrid(key, { useCache = true } = {}) {
  const config = getRefSheetConfig(key);
  const cached = refSheetCache.get(key);
  if (useCache && cached && cached.expires > Date.now()) {
    return cached.data;
  }

  const sheets = getSheetsClient();
  const res = await sheets.spreadsheets.values.get({
    spreadsheetId: ADMIN_SPREADSHEET_ID,
    range: refSheetRange(config),
  });
  const values = res.data.values || [];
  const width = Math.max(1, values.reduce((max, row) => Math.max(max, row.length), 0));
  const rows = values.map((row) => {
    const padded = row.slice(0, width);
    while (padded.length < width) padded.push('');
    return padded;
  });
  const startColIndex = config.colStart ? letterToColumnIndex(config.colStart) : 0;
  const colLetters = Array.from({ length: width }, (_, i) => columnIndexToLetter(startColIndex + i));

  const data = { key, title: config.title, label: config.label, gid: config.gid, colLetters, rows };
  refSheetCache.set(key, { expires: Date.now() + CACHE_TTL_MS, data });
  return data;
}

function invalidateRefSheetCache(key) {
  refSheetCache.delete(key);
}

async function updateRefSheetCell(key, rowIndex, colIndex, value) {
  const config = getRefSheetConfig(key);
  const startColIndex = config.colStart ? letterToColumnIndex(config.colStart) : 0;
  const colLetter = columnIndexToLetter(startColIndex + colIndex);
  const rowNumber = rowIndex + 1; // 그리드 0번째 행 = 시트 1행
  const sheets = getSheetsClient();
  await sheets.spreadsheets.values.update({
    spreadsheetId: ADMIN_SPREADSHEET_ID,
    range: `${quoteSheetTitle(config.title)}!${colLetter}${rowNumber}`,
    valueInputOption: 'RAW',
    requestBody: { values: [[value]] },
  });
  invalidateRefSheetCache(key);
}

// 갱신배정 탭: 헤더는 2행, 데이터는 3행부터 시작합니다(REF_SHEETS의 renewalTable:true).
// 다른 참고용 시트들과 달리 칼럼별 의미(RENEWAL_FIELDS)를 그대로 사용해 회원관리와 같은
// 표/모달 UI로 보여줍니다. 딜러연락처(L열)와 딜러이름(M열)은 각각 별도 칼럼에 저장됩니다.
function invalidateRenewalCache() {
  renewalCache = null;
}

async function readRenewalRows({ useCache = true } = {}) {
  const config = getRefSheetConfig('renewal');
  if (useCache && renewalCache && renewalCache.expires > Date.now()) {
    return renewalCache.data;
  }

  const sheets = getSheetsClient();
  const res = await sheets.spreadsheets.values.get({
    spreadsheetId: ADMIN_SPREADSHEET_ID,
    range: `${quoteSheetTitle(config.title)}!B3:Q`,
  });
  const values = res.data.values || [];
  const baseIndex = letterToColumnIndex('B');

  const rows = values
    .map((rowArray, i) => {
      const get = (col) => (rowArray[letterToColumnIndex(col) - baseIndex] || '').toString().trim();
      return {
        rowNumber: i + 3, // 시트 상의 실제 행 번호 (1~2행은 빈줄/헤더)
        values: {
          renewalMonth: get('B'),
          assignedDate: get('C'),
          assignOrder: get('D'),
          manager: get('E'),
          customerName: get('F'),
          residentNumber: get('G'),
          phone: get('H'),
          carNumber: get('I'),
          expiryDate: get('J'),
          insurer: get('K'),
          dealerContact: get('L'),
          dealerName: get('M'),
          dealerType: get('N'),
          dealerRecent60d: get('O'),
          dealerLastContractDate: get('P'),
          callHistory: get('Q'),
        },
      };
    })
    .filter((r) => r.values.customerName || r.values.phone);

  const data = { rows };
  renewalCache = { expires: Date.now() + CACHE_TTL_MS, data };
  return data;
}

async function updateRenewalRecord({ rowNumber, updates }) {
  const config = getRefSheetConfig('renewal');
  const colOf = Object.fromEntries(RENEWAL_FIELDS.map((f) => [f.key, f.col]));
  const data = [];
  for (const [key, value] of Object.entries(updates)) {
    const col = colOf[key];
    if (!col) continue;
    data.push({
      range: `${quoteSheetTitle(config.title)}!${col}${rowNumber}`,
      values: [[value == null ? '' : String(value)]],
    });
  }
  if (data.length === 0) return { ok: true };

  const sheets = getSheetsClient();
  await sheets.spreadsheets.values.batchUpdate({
    spreadsheetId: ADMIN_SPREADSHEET_ID,
    requestBody: { valueInputOption: 'RAW', data },
  });
  invalidateRenewalCache();
  return { ok: true };
}

async function addRenewalCallNote(rowNumber, currentHistory, text, author) {
  const config = getRefSheetConfig('renewal');
  const newHistory = appendContactHistoryNote(currentHistory, { author, text });
  const sheets = getSheetsClient();
  await sheets.spreadsheets.values.update({
    spreadsheetId: ADMIN_SPREADSHEET_ID,
    range: `${quoteSheetTitle(config.title)}!Q${rowNumber}`,
    valueInputOption: 'RAW',
    requestBody: { values: [[newHistory]] },
  });
  invalidateRenewalCache();
  return newHistory;
}

// U~AD열에 매니저별로 기록된 메모를 Q열(callHistory)로 가져옵니다.
// ① Q열에 plain-text(NOTE 형식이 아닌) 내용이 있으면 갱신담당매니저 이름으로 NOTE 형식으로 변환합니다.
// ② NOTE 형식으로 등록된 동일 내용(author+text 쌍)만 중복으로 간주하고 건너뜁니다.
async function importManagerNotesToCallHistory() {
  const config = getRefSheetConfig('renewal');
  const MANAGER_COLS = [
    { col: 'U', name: '김미희' },
    { col: 'V', name: '김경선' },
    { col: 'W', name: '박순미' },
    { col: 'X', name: '이선' },
    { col: 'Y', name: '이선이' },
    { col: 'Z', name: '조예나' },
    { col: 'AA', name: '정혜령' },
    { col: 'AB', name: '최현정' },
    { col: 'AC', name: '신영란' },
    { col: 'AD', name: '송민선' },
  ];

  const sheets = getSheetsClient();
  const res = await sheets.spreadsheets.values.get({
    spreadsheetId: ADMIN_SPREADSHEET_ID,
    range: `${quoteSheetTitle(config.title)}!B3:AD`,
  });
  const values = res.data.values || [];
  const baseIndex = letterToColumnIndex('B');

  const data = [];
  let importedCount = 0;
  let convertedCount = 0;

  for (let i = 0; i < values.length; i++) {
    const rowArray = values[i];
    const rowNumber = i + 3;
    const get = (col) => (rowArray[letterToColumnIndex(col) - baseIndex] || '').toString().trim();

    const rowManager = get('E'); // 갱신담당매니저
    let currentHistory = get('Q');
    let changed = false;

    // ① Q열 plain-text 항목을 NOTE 형식으로 변환 (작성자 = 갱신담당매니저)
    const rawLines = (currentHistory || '').split('\n').map((l) => l.trim()).filter(Boolean);
    const hasPlainLines = rawLines.some((line) => {
      const parts = line.split('\t');
      return !(parts[0] === 'NOTE' && parts.length >= 4);
    });
    if (hasPlainLines) {
      const newLines = rawLines.map((line) => {
        const parts = line.split('\t');
        if (parts[0] === 'NOTE' && parts.length >= 4) return line;
        const safeText = line.replace(/[\n\r\t]+/g, ' ').trim();
        return `NOTE\t\t${rowManager || ''}\t${safeText}`;
      });
      currentHistory = newLines.join('\n');
      changed = true;
      convertedCount++;
    }

    // ② NOTE 형식 기준으로 dedup set 구성 (author+text 쌍)
    const existingNotes = parseContactHistory(currentHistory);
    const existingSet = new Set(
      existingNotes.filter((n) => n.author).map((n) => `${n.author}|||${n.text}`)
    );

    // ③ U~AD 매니저 컬럼 가져오기
    for (const { col, name } of MANAGER_COLS) {
      const cellText = get(col);
      if (!cellText) continue;
      const key = `${name}|||${cellText}`;
      if (existingSet.has(key)) continue;
      currentHistory = appendContactHistoryNote(currentHistory, { author: name, text: cellText });
      existingSet.add(key);
      changed = true;
      importedCount++;
    }

    if (changed) {
      data.push({
        range: `${quoteSheetTitle(config.title)}!Q${rowNumber}`,
        values: [[currentHistory]],
      });
    }
  }

  if (data.length > 0) {
    await sheets.spreadsheets.values.batchUpdate({
      spreadsheetId: ADMIN_SPREADSHEET_ID,
      requestBody: { valueInputOption: 'RAW', data },
    });
    invalidateRenewalCache();
  }

  return { imported: importedCount, converted: convertedCount, rowsUpdated: data.length };
}

// 메모장 형태(REF_SHEETS의 notepad:true)의 시트는 한 개의 셀(noteCell)에 리치텍스트(HTML)를
// 통째로 저장합니다. 그 셀이 비어있으면(아직 한 번도 저장 전이라면) 예전에 시트에 그리드 형태로
// 입력돼있던 내용을 1회성으로 읽어와 보여줍니다(저장 전까지는 실제로 옮겨쓰지 않습니다).
async function readNotepadSheet(key, { useCache = true } = {}) {
  const config = getRefSheetConfig(key);
  if (!config.notepad) throw new Error(`메모장 형태가 아닌 시트입니다: ${key}`);

  const cached = notepadCache.get(key);
  if (useCache && cached && cached.expires > Date.now()) {
    return cached.data;
  }

  const sheets = getSheetsClient();
  const res = await sheets.spreadsheets.values.get({
    spreadsheetId: ADMIN_SPREADSHEET_ID,
    range: `${quoteSheetTitle(config.title)}!${config.noteCell}`,
  });
  const cellValue = ((res.data.values && res.data.values[0] && res.data.values[0][0]) || '').toString();

  let html = cellValue;
  let migrated = false;
  if (!html.trim()) {
    const grid = await readRefSheetGrid(key, { useCache });
    const lines = grid.rows
      .map((row) => row.map((cell) => (cell || '').toString().trim()).filter(Boolean).join('  '))
      .filter(Boolean);
    if (lines.length) {
      html = lines.map((line) => `<div>${escapeHtml(line)}</div>`).join('');
      migrated = true;
    }
  }

  const data = { key, html, migrated };
  notepadCache.set(key, { expires: Date.now() + CACHE_TTL_MS, data });
  return data;
}

async function saveNotepadSheet(key, html) {
  const config = getRefSheetConfig(key);
  if (!config.notepad) throw new Error(`메모장 형태가 아닌 시트입니다: ${key}`);

  const safeHtml = sanitizeNotepadHtml(html);
  const sheets = getSheetsClient();
  await sheets.spreadsheets.values.update({
    spreadsheetId: ADMIN_SPREADSHEET_ID,
    range: `${quoteSheetTitle(config.title)}!${config.noteCell}`,
    valueInputOption: 'RAW',
    requestBody: { values: [[safeHtml]] },
  });
  notepadCache.delete(key);
  return { html: safeHtml };
}

function makeTemplateId() {
  return `t${Date.now().toString(36)}${Math.random().toString(36).slice(2, 7)}`;
}

// LMS템플릿 탭(REF_SHEETS의 templates:true)은 한 개의 셀(templatesCell)에
// { categories: [{id,title}], entries: [{id,categoryId,content,isAdminTemplate,updatedBy,updatedAt}] }
// 형태의 JSON을 통째로 저장합니다. 카테고리(사이드바) 하나에 여러 개의 템플릿을 등록할 수 있고,
// isAdminTemplate인 항목은 관리자만 수정·삭제할 수 있어 매니저 화면에는 항상 관리자가 등록한
// 최신 내용 그대로 보입니다(같은 데이터를 공유하므로 별도 동기화가 필요 없습니다).
// 쓸 때마다 시트에서 최신 데이터를 다시 읽어 해당 항목만 바꾼 뒤 전체를 다시 씁니다
// (동시에 다른 템플릿을 수정 중인 다른 사람의 내용을 덮어쓰지 않도록).
async function readTemplatesSheet(key, { useCache = true } = {}) {
  const config = getRefSheetConfig(key);
  if (!config.templates) throw new Error(`템플릿 형태가 아닌 시트입니다: ${key}`);

  const cached = templatesCache.get(key);
  if (useCache && cached && cached.expires > Date.now()) {
    return cached.data;
  }

  const sheets = getSheetsClient();
  const res = await sheets.spreadsheets.values.get({
    spreadsheetId: ADMIN_SPREADSHEET_ID,
    range: `${quoteSheetTitle(config.title)}!${config.templatesCell}`,
  });
  const raw = ((res.data.values && res.data.values[0] && res.data.values[0][0]) || '').toString();

  let parsed = null;
  if (raw.trim()) {
    try {
      parsed = JSON.parse(raw);
    } catch {
      parsed = null;
    }
  }

  let categories;
  let entries;
  if (parsed && Array.isArray(parsed.categories)) {
    categories = parsed.categories;
    entries = Array.isArray(parsed.entries) ? parsed.entries : [];
  } else if (Array.isArray(parsed)) {
    // 이전 형식(카테고리 1개 = 템플릿 1개) 호환: 내용이 있던 항목만 해당 카테고리의 템플릿으로 옮겨줍니다.
    categories = LMS_TEMPLATE_CATEGORIES.map((c) => ({ id: c.id, title: c.title }));
    entries = parsed
      .filter((t) => (t.content || '').toString().trim())
      .map((t) => ({
        id: t.id,
        categoryId: t.id,
        content: t.content,
        isAdminTemplate: false,
        updatedBy: '',
        updatedAt: '',
      }));
  } else {
    categories = LMS_TEMPLATE_CATEGORIES.map((c) => ({ id: c.id, title: c.title }));
    entries = [];
  }

  const data = { key, categories, entries };
  templatesCache.set(key, { expires: Date.now() + CACHE_TTL_MS, data });
  return data;
}

async function writeTemplatesData(key, { categories, entries }) {
  const config = getRefSheetConfig(key);
  const sheets = getSheetsClient();
  await sheets.spreadsheets.values.update({
    spreadsheetId: ADMIN_SPREADSHEET_ID,
    range: `${quoteSheetTitle(config.title)}!${config.templatesCell}`,
    valueInputOption: 'RAW',
    requestBody: { values: [[JSON.stringify({ categories, entries })]] },
  });
  templatesCache.delete(key);
}

async function addTemplateCategory(key, title, actor) {
  const trimmedTitle = (title || '').toString().trim();
  if (!trimmedTitle) throw new Error('카테고리 이름을 입력해주세요.');

  const data = await readTemplatesSheet(key, { useCache: false });
  const isAdminCategory = actor && actor.role === '관리자';
  const categories = [...data.categories, { id: makeTemplateId(), title: trimmedTitle, isAdminCategory }];
  await writeTemplatesData(key, { categories, entries: data.entries });
  return { categories, entries: data.entries };
}

async function addTemplateEntry(key, { categoryId, content, isAdminTemplate }, actor) {
  if (isAdminTemplate && actor.role !== '관리자') {
    throw new Error('관리자만 관리자 등록 템플릿을 추가할 수 있습니다.');
  }

  const data = await readTemplatesSheet(key, { useCache: false });
  if (!data.categories.some((c) => c.id === categoryId)) {
    throw new Error('존재하지 않는 카테고리입니다.');
  }
  const entry = {
    id: makeTemplateId(),
    categoryId,
    content: (content || '').toString(),
    isAdminTemplate: !!isAdminTemplate,
    updatedBy: actor.name || '',
    updatedAt: formatRegisteredAt(),
  };
  const entries = [...data.entries, entry];
  await writeTemplatesData(key, { categories: data.categories, entries });
  return { categories: data.categories, entries };
}

async function updateTemplateEntry(key, id, { content, isAdminTemplate }, actor) {
  const data = await readTemplatesSheet(key, { useCache: false });
  let found = false;
  const entries = data.entries.map((e) => {
    if (e.id !== id) return e;
    found = true;
    if (e.isAdminTemplate && actor.role !== '관리자') {
      throw new Error('관리자 등록 템플릿은 관리자만 수정할 수 있습니다.');
    }
    if (isAdminTemplate !== undefined && actor.role !== '관리자') {
      throw new Error('관리자만 관리자 등록 템플릿 여부를 변경할 수 있습니다.');
    }
    return {
      ...e,
      content: content !== undefined ? (content || '').toString() : e.content,
      isAdminTemplate: isAdminTemplate !== undefined ? !!isAdminTemplate : e.isAdminTemplate,
      updatedBy: actor.name || '',
      updatedAt: formatRegisteredAt(),
    };
  });
  if (!found) throw new Error('존재하지 않는 템플릿입니다.');
  await writeTemplatesData(key, { categories: data.categories, entries });
  return { categories: data.categories, entries };
}

async function deleteTemplateEntry(key, id, actor) {
  const data = await readTemplatesSheet(key, { useCache: false });
  const target = data.entries.find((e) => e.id === id);
  if (!target) throw new Error('존재하지 않는 템플릿입니다.');
  if (target.isAdminTemplate && actor.role !== '관리자') {
    throw new Error('관리자 등록 템플릿은 관리자만 삭제할 수 있습니다.');
  }
  const entries = data.entries.filter((e) => e.id !== id);
  await writeTemplatesData(key, { categories: data.categories, entries });
  return { categories: data.categories, entries };
}

async function renameTemplateCategory(key, id, title, actor) {
  const trimmedTitle = (title || '').toString().trim();
  if (!trimmedTitle) throw new Error('카테고리 이름을 입력해주세요.');
  const data = await readTemplatesSheet(key, { useCache: false });
  let found = false;
  const categories = data.categories.map((c) => {
    if (c.id !== id) return c;
    found = true;
    if (c.isAdminCategory && actor.role !== '관리자') {
      throw new Error('관리자가 등록한 카테고리는 관리자만 수정할 수 있습니다.');
    }
    return { ...c, title: trimmedTitle };
  });
  if (!found) throw new Error('존재하지 않는 카테고리입니다.');
  await writeTemplatesData(key, { categories, entries: data.entries });
  return { categories, entries: data.entries };
}

async function deleteTemplateCategory(key, id, actor) {
  const data = await readTemplatesSheet(key, { useCache: false });
  const target = data.categories.find((c) => c.id === id);
  if (!target) throw new Error('존재하지 않는 카테고리입니다.');
  if (target.isAdminCategory && actor.role !== '관리자') {
    throw new Error('관리자가 등록한 카테고리는 관리자만 삭제할 수 있습니다.');
  }
  const categories = data.categories.filter((c) => c.id !== id);
  const entries = data.entries.filter((e) => e.categoryId !== id);
  await writeTemplatesData(key, { categories, entries });
  return { categories, entries };
}

function makeLeaseEntryId() {
  return `lp${Date.now().toString(36)}${Math.random().toString(36).slice(2, 7)}`;
}

function assertAdmin(actor) {
  if (!actor || actor.role !== '관리자') {
    throw new Error('관리자만 수정할 수 있습니다.');
  }
}

// 리스(질권사) 탭(REF_SHEETS의 registry:true)은 한 개의 셀(registryCell)에
// [{id, company, businessNumber}] 형태의 JSON 배열을 통째로 저장합니다.
// 전체 탭이 관리자 전용 수정 권한이라(개별 항목 단위 구분 없음) 매니저 화면에는
// 항상 관리자가 등록한 최신 내용 그대로 보입니다(같은 데이터를 공유하므로 별도 동기화가 필요 없습니다).
async function readLeaseRegistry(key, { useCache = true } = {}) {
  const config = getRefSheetConfig(key);
  if (!config.registry) throw new Error(`등록부 형태가 아닌 시트입니다: ${key}`);

  const cached = registryCache.get(key);
  if (useCache && cached && cached.expires > Date.now()) {
    return cached.data;
  }

  const sheets = getSheetsClient();
  const res = await sheets.spreadsheets.values.get({
    spreadsheetId: ADMIN_SPREADSHEET_ID,
    range: `${quoteSheetTitle(config.title)}!${config.registryCell}`,
  });
  const raw = ((res.data.values && res.data.values[0] && res.data.values[0][0]) || '').toString();

  let entries;
  if (raw.trim()) {
    try {
      const parsed = JSON.parse(raw);
      entries = Array.isArray(parsed) ? parsed : LEASE_PLEDGE_DEFAULTS;
    } catch {
      entries = LEASE_PLEDGE_DEFAULTS;
    }
  } else {
    entries = LEASE_PLEDGE_DEFAULTS;
  }

  const data = { key, entries };
  registryCache.set(key, { expires: Date.now() + CACHE_TTL_MS, data });
  return data;
}

async function writeLeaseRegistryData(key, entries) {
  const config = getRefSheetConfig(key);
  const sheets = getSheetsClient();
  await sheets.spreadsheets.values.update({
    spreadsheetId: ADMIN_SPREADSHEET_ID,
    range: `${quoteSheetTitle(config.title)}!${config.registryCell}`,
    valueInputOption: 'RAW',
    requestBody: { values: [[JSON.stringify(entries)]] },
  });
  registryCache.delete(key);
}

async function addLeaseEntry(key, { company, businessNumber }, actor) {
  assertAdmin(actor);
  const trimmedCompany = (company || '').toString().trim();
  if (!trimmedCompany) throw new Error('리스(질권사) 이름을 입력해주세요.');

  const data = await readLeaseRegistry(key, { useCache: false });
  const entry = {
    id: makeLeaseEntryId(),
    company: trimmedCompany,
    businessNumber: (businessNumber || '').toString().trim(),
  };
  const entries = [...data.entries, entry];
  await writeLeaseRegistryData(key, entries);
  return { entries };
}

async function updateLeaseEntry(key, id, { company, businessNumber }, actor) {
  assertAdmin(actor);
  const data = await readLeaseRegistry(key, { useCache: false });
  let found = false;
  const entries = data.entries.map((e) => {
    if (e.id !== id) return e;
    found = true;
    return {
      ...e,
      company: company !== undefined ? (company || '').toString().trim() : e.company,
      businessNumber: businessNumber !== undefined ? (businessNumber || '').toString().trim() : e.businessNumber,
    };
  });
  if (!found) throw new Error('존재하지 않는 항목입니다.');
  await writeLeaseRegistryData(key, entries);
  return { entries };
}

async function deleteLeaseEntry(key, id, actor) {
  assertAdmin(actor);
  const data = await readLeaseRegistry(key, { useCache: false });
  const entries = data.entries.filter((e) => e.id !== id);
  await writeLeaseRegistryData(key, entries);
  return { entries };
}

function makeLinkId() {
  return `lk${Date.now().toString(36)}${Math.random().toString(36).slice(2, 7)}`;
}

// 원수사별 CM/TM 탭(REF_SHEETS의 linkHub:true)은 한 개의 셀(linkHubCell)에
// { internalLinks: [{id,category,detail}], insurerLinks: [{id,insurer,tmNumber,cmUrlPc,cmUrlMobile,note,remark}] }
// 형태의 JSON을 통째로 저장합니다. 두 목록 모두 관리자 전용 수정 권한이라
// 매니저 화면에는 항상 관리자가 등록한 최신 내용 그대로 보입니다.
async function readLinkHub(key, { useCache = true } = {}) {
  const config = getRefSheetConfig(key);
  if (!config.linkHub) throw new Error(`링크 모음 형태가 아닌 시트입니다: ${key}`);

  const cached = linkHubCache.get(key);
  if (useCache && cached && cached.expires > Date.now()) {
    return cached.data;
  }

  const sheets = getSheetsClient();
  const res = await sheets.spreadsheets.values.get({
    spreadsheetId: ADMIN_SPREADSHEET_ID,
    range: `${quoteSheetTitle(config.title)}!${config.linkHubCell}`,
  });
  const raw = ((res.data.values && res.data.values[0] && res.data.values[0][0]) || '').toString();

  let parsed = null;
  if (raw.trim()) {
    try {
      parsed = JSON.parse(raw);
    } catch {
      parsed = null;
    }
  }

  const internalLinks = parsed && Array.isArray(parsed.internalLinks) ? parsed.internalLinks : [];
  const insurerLinks = parsed && Array.isArray(parsed.insurerLinks) ? parsed.insurerLinks : [];

  const data = { key, internalLinks, insurerLinks };
  linkHubCache.set(key, { expires: Date.now() + CACHE_TTL_MS, data });
  return data;
}

async function writeLinkHubData(key, { internalLinks, insurerLinks }) {
  const config = getRefSheetConfig(key);
  const sheets = getSheetsClient();
  await sheets.spreadsheets.values.update({
    spreadsheetId: ADMIN_SPREADSHEET_ID,
    range: `${quoteSheetTitle(config.title)}!${config.linkHubCell}`,
    valueInputOption: 'RAW',
    requestBody: { values: [[JSON.stringify({ internalLinks, insurerLinks })]] },
  });
  linkHubCache.delete(key);
}

async function addInternalLink(key, { category, detail }, actor) {
  assertAdmin(actor);
  const data = await readLinkHub(key, { useCache: false });
  const entry = {
    id: makeLinkId(),
    category: (category || '').toString().trim(),
    detail: (detail || '').toString(),
  };
  const internalLinks = [...data.internalLinks, entry];
  await writeLinkHubData(key, { internalLinks, insurerLinks: data.insurerLinks });
  return { internalLinks, insurerLinks: data.insurerLinks };
}

async function updateInternalLink(key, id, { category, detail }, actor) {
  assertAdmin(actor);
  const data = await readLinkHub(key, { useCache: false });
  let found = false;
  const internalLinks = data.internalLinks.map((e) => {
    if (e.id !== id) return e;
    found = true;
    return {
      ...e,
      category: category !== undefined ? (category || '').toString().trim() : e.category,
      detail: detail !== undefined ? (detail || '').toString() : e.detail,
    };
  });
  if (!found) throw new Error('존재하지 않는 항목입니다.');
  await writeLinkHubData(key, { internalLinks, insurerLinks: data.insurerLinks });
  return { internalLinks, insurerLinks: data.insurerLinks };
}

async function deleteInternalLink(key, id, actor) {
  assertAdmin(actor);
  const data = await readLinkHub(key, { useCache: false });
  const internalLinks = data.internalLinks.filter((e) => e.id !== id);
  await writeLinkHubData(key, { internalLinks, insurerLinks: data.insurerLinks });
  return { internalLinks, insurerLinks: data.insurerLinks };
}

async function addInsurerLink(key, { insurer, tmNumber, cmUrlPc, cmUrlMobile, note, remark }, actor) {
  assertAdmin(actor);
  const data = await readLinkHub(key, { useCache: false });
  const entry = {
    id: makeLinkId(),
    insurer: (insurer || '').toString().trim(),
    tmNumber: (tmNumber || '').toString().trim(),
    cmUrlPc: (cmUrlPc || '').toString().trim(),
    cmUrlMobile: (cmUrlMobile || '').toString().trim(),
    note: (note || '').toString(),
    remark: (remark || '').toString(),
  };
  const insurerLinks = [...data.insurerLinks, entry];
  await writeLinkHubData(key, { internalLinks: data.internalLinks, insurerLinks });
  return { internalLinks: data.internalLinks, insurerLinks };
}

async function updateInsurerLink(key, id, { insurer, tmNumber, cmUrlPc, cmUrlMobile, note, remark }, actor) {
  assertAdmin(actor);
  const data = await readLinkHub(key, { useCache: false });
  let found = false;
  const insurerLinks = data.insurerLinks.map((e) => {
    if (e.id !== id) return e;
    found = true;
    return {
      ...e,
      insurer: insurer !== undefined ? (insurer || '').toString().trim() : e.insurer,
      tmNumber: tmNumber !== undefined ? (tmNumber || '').toString().trim() : e.tmNumber,
      cmUrlPc: cmUrlPc !== undefined ? (cmUrlPc || '').toString().trim() : e.cmUrlPc,
      cmUrlMobile: cmUrlMobile !== undefined ? (cmUrlMobile || '').toString().trim() : e.cmUrlMobile,
      note: note !== undefined ? (note || '').toString() : e.note,
      remark: remark !== undefined ? (remark || '').toString() : e.remark,
    };
  });
  if (!found) throw new Error('존재하지 않는 항목입니다.');
  await writeLinkHubData(key, { internalLinks: data.internalLinks, insurerLinks });
  return { internalLinks: data.internalLinks, insurerLinks };
}

async function deleteInsurerLink(key, id, actor) {
  assertAdmin(actor);
  const data = await readLinkHub(key, { useCache: false });
  const insurerLinks = data.insurerLinks.filter((e) => e.id !== id);
  await writeLinkHubData(key, { internalLinks: data.internalLinks, insurerLinks });
  return { internalLinks: data.internalLinks, insurerLinks };
}

// 최종 결과(병합 완료 rows + ETag)를 adminResultCache에 채웁니다.
// 동시에 여러 요청이 이 함수를 호출해도 Google API는 한 번만 호출됩니다.
async function rebuildAdminResultCache() {
  if (adminRebuildInFlight) return adminRebuildInFlight;
  adminRebuildInFlight = (async () => {
    const data = await readSheetRows(ADMIN_SPREADSHEET_ID, { useCache: false });
    const rows = data.rows.slice().sort((a, b) => a.rowNumber - b.rowNumber);
    const payload = rows.map((r) => ({ ...r.values, rowNumber: r.rowNumber }));
    const etag = '"' + crypto.createHash('md5').update(JSON.stringify(payload)).digest('hex') + '"';
    adminResultCache = { expires: Date.now() + CACHE_TTL_MS, sheetTitle: data.sheetTitle, columnMap: data.columnMap, rows, etag };
  })().catch((e) => {
    console.error('admin result cache 재빌드 실패:', e);
    adminResultCache = null;
  }).finally(() => {
    adminRebuildInFlight = null;
  });
  return adminRebuildInFlight;
}

async function getAdminRows({ useCache = true } = {}) {
  if (useCache && adminResultCache && adminResultCache.expires > Date.now()) {
    return adminResultCache;
  }
  if (useCache && adminResultCache) {
    rebuildAdminResultCache().catch((e) => console.error('백그라운드 재빌드 실패:', e));
    return adminResultCache;
  }
  await rebuildAdminResultCache();
  return adminResultCache;
}

// "계정관리" 탭: 아이디 | 비밀번호 | 이름 | 권한 | 개인시트URL | 비고 | 실패횟수 | 잠김여부
async function getAccountsConfig({ useCache = true } = {}) {
  if (useCache && accountsCache && accountsCache.expires > Date.now()) {
    return accountsCache.accounts;
  }
  const sheets = getSheetsClient();
  const range = `${quoteSheetTitle(ACCOUNTS_SHEET_TITLE)}!A2:H`;
  const res = await sheets.spreadsheets.values.get({
    spreadsheetId: ADMIN_SPREADSHEET_ID,
    range,
  });
  const accounts = (res.data.values || [])
    .map((r, i) => ({
      rowNumber: i + 2, // 시트 상의 실제 행 번호 (1행은 헤더)
      loginId: (r[0] || '').trim(),
      password: (r[1] || '').trim(),
      name: (r[2] || '').trim(),
      role: (r[3] || '').trim(), // '관리자' | '매니저'
      sheetUrl: (r[4] || '').trim(),
      note: (r[5] || '').trim(),
      failedAttempts: parseInt(r[6], 10) || 0,
      locked: (r[7] || '').trim().toUpperCase() === 'Y',
    }))
    .filter((a) => a.loginId);
  accountsCache = { expires: Date.now() + CACHE_TTL_MS, accounts };
  return accounts;
}

function invalidateAccountsCache() {
  accountsCache = null;
}

// 상단 공지사항: "계정관리" 탭의 빈 셀(J1)에 텍스트 한 줄을 저장/조회합니다.
async function readAnnouncement({ useCache = true } = {}) {
  if (useCache && announcementCache && announcementCache.expires > Date.now()) {
    return announcementCache.text;
  }
  const sheets = getSheetsClient();
  const range = `${quoteSheetTitle(ACCOUNTS_SHEET_TITLE)}!${ANNOUNCEMENT_CELL}`;
  const res = await sheets.spreadsheets.values.get({
    spreadsheetId: ADMIN_SPREADSHEET_ID,
    range,
  });
  const text = ((res.data.values && res.data.values[0] && res.data.values[0][0]) || '').trim();
  announcementCache = { expires: Date.now() + CACHE_TTL_MS, text };
  return text;
}

async function saveAnnouncement(text, actor) {
  if (!actor || actor.role !== '관리자') {
    throw new Error('관리자만 공지사항을 수정할 수 있습니다.');
  }
  const trimmedText = (text || '').toString().trim();
  if (trimmedText.length > ANNOUNCEMENT_MAX_LENGTH) {
    throw new Error(`공지사항은 ${ANNOUNCEMENT_MAX_LENGTH}자 이내로 입력해주세요.`);
  }
  const sheets = getSheetsClient();
  await sheets.spreadsheets.values.update({
    spreadsheetId: ADMIN_SPREADSHEET_ID,
    range: `${quoteSheetTitle(ACCOUNTS_SHEET_TITLE)}!${ANNOUNCEMENT_CELL}`,
    valueInputOption: 'RAW',
    requestBody: { values: [[trimmedText]] },
  });
  announcementCache = { expires: Date.now() + CACHE_TTL_MS, text: trimmedText };
  return trimmedText;
}

async function findAccountByLoginId(loginId, opts) {
  const accounts = await getAccountsConfig(opts);
  return accounts.find((a) => a.loginId === loginId) || null;
}

async function updateAccountFields(rowNumber, fieldsToUpdate) {
  const sheets = getSheetsClient();
  const data = [];
  for (const [key, value] of Object.entries(fieldsToUpdate)) {
    const col = ACCOUNT_COLUMNS[key];
    if (!col) continue;
    data.push({
      range: `${quoteSheetTitle(ACCOUNTS_SHEET_TITLE)}!${col}${rowNumber}`,
      values: [[value]],
    });
  }
  if (data.length === 0) return;
  await sheets.spreadsheets.values.batchUpdate({
    spreadsheetId: ADMIN_SPREADSHEET_ID,
    requestBody: { valueInputOption: 'RAW', data },
  });
  invalidateAccountsCache();
}

// 로그인 비밀번호가 틀렸을 때 호출: 실패횟수를 올리고, 5회 이상이면 계정을 잠급니다.
// 단, 관리자 계정은 잠그지 않고 비밀번호를 자동으로 초기화합니다(관리자가 잠기면
// 아무도 풀어줄 수 없기 때문).
async function recordFailedLogin(account) {
  const failedAttempts = account.failedAttempts + 1;

  if (account.role === '관리자') {
    if (failedAttempts >= MAX_FAILED_ATTEMPTS) {
      await updateAccountFields(account.rowNumber, {
        password: ADMIN_AUTO_RESET_PASSWORD,
        failedAttempts: 0,
        locked: '',
      });
      return { failedAttempts, locked: false, passwordReset: true };
    }
    await updateAccountFields(account.rowNumber, { failedAttempts });
    return { failedAttempts, locked: false, passwordReset: false };
  }

  const locked = failedAttempts >= MAX_FAILED_ATTEMPTS;
  await updateAccountFields(account.rowNumber, {
    failedAttempts,
    locked: locked ? 'Y' : '',
  });
  return { failedAttempts, locked, passwordReset: false };
}

// 로그인에 성공했을 때 호출: 실패횟수를 0으로 되돌립니다.
// (예전에 잠겼던 관리자 계정이 남아있을 수 있어 잠김 표시도 함께 정리합니다.)
async function recordSuccessfulLogin(account) {
  if (account.failedAttempts === 0 && !account.locked) return;
  await updateAccountFields(account.rowNumber, { failedAttempts: 0, locked: '' });
}

// 본인이 비밀번호를 변경할 때 사용합니다.
async function changeOwnPassword(loginId, newPassword) {
  const account = await findAccountByLoginId(loginId, { useCache: false });
  if (!account) throw new Error('계정을 찾을 수 없습니다.');
  await updateAccountFields(account.rowNumber, { password: newPassword });
}

// 관리자가 매니저 계정의 비밀번호를 초기화할 때 사용합니다. 잠금/실패횟수도 함께 풀어줍니다.
async function adminResetPassword(loginId, newPassword) {
  const account = await findAccountByLoginId(loginId, { useCache: false });
  if (!account) throw new Error('계정을 찾을 수 없습니다.');
  await updateAccountFields(account.rowNumber, {
    password: newPassword,
    failedAttempts: 0,
    locked: '',
  });
}

// 관리자용 계정관리 화면에 보여줄 목록 (비밀번호 값은 제외)
async function listAccountsForAdmin() {
  const accounts = await getAccountsConfig({ useCache: false });
  return accounts.map(({ password, ...rest }) => rest);
}

async function createAccount({ loginId, password, name, role, sheetUrl = '', note = '' }) {
  const accounts = await getAccountsConfig({ useCache: false });
  if (accounts.find((a) => a.loginId === loginId.trim())) {
    throw new Error('이미 사용 중인 아이디입니다.');
  }
  const sheets = getSheetsClient();
  await sheets.spreadsheets.values.append({
    spreadsheetId: ADMIN_SPREADSHEET_ID,
    range: `${quoteSheetTitle(ACCOUNTS_SHEET_TITLE)}!A:H`,
    valueInputOption: 'RAW',
    insertDataOption: 'INSERT_ROWS',
    requestBody: {
      values: [[loginId.trim(), password, name.trim(), role, sheetUrl.trim(), note.trim(), '0', '']],
    },
  });
  invalidateAccountsCache();
}

function extractSpreadsheetId(url) {
  const m = (url || '').match(/\/d\/([a-zA-Z0-9-_]+)/);
  return m ? m[1] : null;
}

async function getManagerSpreadsheetId(managerName) {
  const accounts = await getAccountsConfig();
  const account = accounts.find(
    (a) => a.role === '매니저' && a.name === managerName && a.sheetUrl
  );
  if (!account) return null;
  return extractSpreadsheetId(account.sheetUrl);
}

// API를 호출하지 않고 batchUpdate용 data 배열만 만듭니다.
// (여러 행의 변경을 한 번에 모아서 batchUpdate 한 번으로 보내기 위해 분리해두었습니다.)
function buildRowUpdateData(sheetTitle, rowNumber, columnMap, fieldsToUpdate) {
  const data = [];
  for (const [key, value] of Object.entries(fieldsToUpdate)) {
    if (columnMap[key] === undefined) continue; // 그 시트에 없는 컬럼이면 건너뜀
    const col = columnIndexToLetter(columnMap[key]);
    data.push({
      range: `${quoteSheetTitle(sheetTitle)}!${col}${rowNumber}`,
      values: [[value]],
    });
  }
  return data;
}

async function updateRowFields(spreadsheetId, sheetTitle, rowNumber, columnMap, fieldsToUpdate) {
  const data = buildRowUpdateData(sheetTitle, rowNumber, columnMap, fieldsToUpdate);
  if (data.length === 0) return;
  const sheets = getSheetsClient();
  await sheets.spreadsheets.values.batchUpdate({
    spreadsheetId,
    requestBody: { valueInputOption: 'RAW', data },
  });
  invalidateCache(spreadsheetId);
}

async function appendRowToSheet(spreadsheetId, sheetTitle, columnMap, fieldsObject) {
  const sheets = getSheetsClient();
  const width = Math.max(...Object.values(columnMap)) + 1;
  const rowArray = new Array(width).fill('');
  for (const [key, idx] of Object.entries(columnMap)) {
    if (fieldsObject[key] !== undefined) rowArray[idx] = fieldsObject[key];
  }
  await sheets.spreadsheets.values.append({
    spreadsheetId,
    range: quoteSheetTitle(sheetTitle),
    valueInputOption: 'RAW',
    insertDataOption: 'OVERWRITE',
    requestBody: { values: [rowArray] },
  });
  invalidateCache(spreadsheetId);
}

async function deleteMemberRecord({ phone }) {
  const admin = await getAdminRows({ useCache: false });
  const targetPhone = normalizePhone(phone);
  const adminRow = admin.rows.find((r) => normalizePhone(r.values.phone) === targetPhone);
  if (!adminRow) throw new Error('관리자 시트에서 해당 연락처의 회원을 찾지 못했습니다.');

  const sheets = getSheetsClient();
  const meta = await sheets.spreadsheets.get({
    spreadsheetId: ADMIN_SPREADSHEET_ID,
    fields: 'sheets.properties',
  });
  const sheetMeta = (meta.data.sheets || []).find((s) => s.properties.title === admin.sheetTitle);
  if (!sheetMeta) throw new Error('시트 정보를 찾을 수 없습니다.');

  await sheets.spreadsheets.batchUpdate({
    spreadsheetId: ADMIN_SPREADSHEET_ID,
    requestBody: {
      requests: [{
        deleteDimension: {
          range: {
            sheetId: sheetMeta.properties.sheetId,
            dimension: 'ROWS',
            startIndex: adminRow.rowNumber - 1,
            endIndex: adminRow.rowNumber,
          },
        },
      }],
    },
  });
  invalidateCache(ADMIN_SPREADSHEET_ID);
  return { ok: true };
}

async function createMemberRecord(fields) {
  const admin = await getAdminRows({ useCache: false });
  const targetPhone = normalizePhone(fields.phone);
  const dup = admin.rows.find((r) => normalizePhone(r.values.phone) === targetPhone);
  if (dup) throw new Error('이미 등록된 연락처입니다.');
  await appendRowToSheet(ADMIN_SPREADSHEET_ID, admin.sheetTitle, admin.columnMap, fields);
  return { ok: true };
}

async function updateMemberRecord({ phone, updates }) {
  const admin = await getAdminRows({ useCache: false });
  const targetPhone = normalizePhone(phone);
  const adminRow = admin.rows.find((r) => normalizePhone(r.values.phone) === targetPhone);
  if (!adminRow) throw new Error('관리자 시트에서 해당 연락처의 회원을 찾지 못했습니다.');
  await updateRowFields(ADMIN_SPREADSHEET_ID, admin.sheetTitle, adminRow.rowNumber, admin.columnMap, updates);
  return { ok: true };
}

const ERROR_LOG_SHEET_TITLE = '오류로그';

// API 핸들러의 catch 블록에서 호출합니다. 실패해도 조용히 넘어가고 응답 속도에 영향 없습니다.
async function logErrorToSheet({ path, statusCode, message, userName }) {
  try {
    const sheets = getSheetsClient();
    const timestamp = formatRegisteredAt();
    await sheets.spreadsheets.values.append({
      spreadsheetId: ADMIN_SPREADSHEET_ID,
      range: quoteSheetTitle(ERROR_LOG_SHEET_TITLE),
      valueInputOption: 'RAW',
      insertDataOption: 'OVERWRITE',
      requestBody: {
        values: [[timestamp, path || '', String(statusCode ?? ''), (message || '').slice(0, 500), userName || '']],
      },
    });
  } catch (e) {
    console.error('오류 로그 기록 실패:', e.message);
  }
}

async function readPerformanceDashboard({ useCache = true } = {}) {
  if (useCache && performanceCache && performanceCache.expires > Date.now()) {
    return performanceCache.data;
  }
  const sheets = getSheetsClient();
  const res = await sheets.spreadsheets.values.get({
    spreadsheetId: ADMIN_SPREADSHEET_ID,
    range: quoteSheetTitle(PERFORMANCE_SHEET_TITLE),
  });
  const allValues = res.data.values || [];

  // 행 14 B열에 "매니저" 헤더가 있습니다 (0-indexed: 13번째 행)
  const hIdx = allValues.findIndex((row) => (row[1] || '').trim() === '매니저');
  if (hIdx < 2) throw new Error('"매니저" 헤더를 찾을 수 없습니다. (B열에 "매니저" 텍스트 필요)');

  const monthRow = allValues[hIdx - 2] || []; // 월 단위 라벨 행
  const weekRow  = allValues[hIdx - 1] || []; // 주 단위 라벨 행
  const mainRow  = allValues[hIdx];           // 고정 칼럼명 + 일별 날짜

  // "구분" 칼럼: 고정 칼럼들의 마지막 칼럼 (이후는 날짜 칼럼)
  const catColIdx = mainRow.findIndex((h) => (h || '').trim() === '구분');
  if (catColIdx < 0) throw new Error('"구분" 칼럼을 찾을 수 없습니다.');

  // 고정 칼럼 인덱스 (헤더에서 이름으로 탐색)
  const CI = {
    manager:  1, // B열 고정
    group:    mainRow.findIndex((h, i) => i > 1 && (h || '').trim() === '그룹'),
    totalDB:  mainRow.findIndex((h) => (h || '').trim().includes('총DB')),
    appJoin:  mainRow.findIndex((h) => (h || '').trim() === 'App가입'),
    prev60:   mainRow.findIndex((h) => (h || '').trim().includes('60')),
    prev90:   mainRow.findIndex((h) => (h || '').trim().includes('90')),
    category: catColIdx,
  };

  // 날짜 칼럼 구성 (구분 칼럼 이후, 병합셀 fill-forward 처리)
  // mainRow는 일별 날짜 라벨만 있어 월집계 전용 칼럼이 범위 밖으로 밀릴 수 있으므로
  // 세 헤더 행 중 가장 긴 것을 기준으로 스캔합니다.
  const scanLen = Math.max(monthRow.length, weekRow.length, mainRow.length);
  const dateColumns = [];
  let fillMonth = '', fillWeek = '';
  for (let ci = catColIdx + 1; ci < scanLen; ci++) {
    const rawMonth = (monthRow[ci] || '').trim();
    const rawWeek  = (weekRow[ci]  || '').trim();
    const day      = (mainRow[ci]  || '').trim();
    // monthRow에는 "26-07m 계" 같은 월 라벨 외에 "07-27-07-31" 같은 주간 날짜 범위도
    // 들어올 수 있어 YY-MMm 패턴인 경우에만 fillMonth를 갱신합니다.
    if (rawMonth && /\d{2}-\d{2}m/.test(rawMonth)) fillMonth = rawMonth;
    if (rawWeek)  fillWeek  = rawWeek;
    if (!rawMonth && !rawWeek && !day) continue;

    // 칼럼 유형: 주소계를 일별보다 우선 판별(주소계 칼럼 mainRow에 날짜 범위가 있어도 올바르게 분류)
    const isMonthlyAgg = rawMonth.includes('계') && !rawWeek && !day;
    const isWeeklyAgg  = rawWeek.includes('소계');
    const isDaily      = !!day && !isWeeklyAgg && !isMonthlyAgg;
    // 주소계 칼럼의 monthRow에 있는 날짜 범위(예: "07-27-07-31")를 보관합니다.
    const weekRange = isWeeklyAgg && rawMonth && !/\d{2}-\d{2}m/.test(rawMonth) ? rawMonth : '';
    dateColumns.push({
      ci,
      month:        fillMonth,
      week:         fillWeek,
      day,
      weekRange,
      isMonthlyAgg,
      isWeeklyAgg,
      isDaily,
    });
  }

  // 데이터 행: 헤더 행 +2 부터 (필터 행 1개 skip)
  const dataRows = allValues
    .slice(hIdx + 2)
    .map((row) => ({
      manager: (row[CI.manager]  || '').trim(),
      group:   (CI.group >= 0 ? row[CI.group]    : row[2]) && (CI.group >= 0 ? row[CI.group] : row[2]).trim() || '',
      totalDB: (CI.totalDB >= 0 ? row[CI.totalDB] : row[3]) && String(CI.totalDB >= 0 ? row[CI.totalDB] : row[3]).trim() || '',
      appJoin: (CI.appJoin >= 0 ? row[CI.appJoin] : row[4]) && String(CI.appJoin >= 0 ? row[CI.appJoin] : row[4]).trim() || '',
      prev60:  (CI.prev60 >= 0 ? row[CI.prev60]  : row[5]) && String(CI.prev60 >= 0 ? row[CI.prev60] : row[5]).trim() || '',
      prev90:  (CI.prev90 >= 0 ? row[CI.prev90]  : row[6]) && String(CI.prev90 >= 0 ? row[CI.prev90] : row[6]).trim() || '',
      metric:  (row[CI.category] || '').trim(),
      dateValues: dateColumns.map((dc) => (row[dc.ci] || '').trim()),
    }))
    .filter((r) => r.manager);

  const data = { dateColumns, dataRows };
  performanceCache = { expires: Date.now() + CACHE_TTL_MS, data };
  return data;
}

// 기존에 등록된 데이터 중 등록일자(registeredAt)가 비어있는 행을 일괄 보정합니다.
// - 배분일자(assignedDate)가 있으면 → 등록일자 = 배분일자
// - 배분일자도 없으면 → 등록일자 = 배분일자 = 오늘 날짜
async function backfillRegisteredAt() {
  // 관리자 시트에서 배분일자가 있고 등록일자가 비어있는 행만 찾아
  // 등록일자 = 배분일자로 채워줍니다. 딱 이것만 합니다.
  const admin = await readSheetRows(ADMIN_SPREADSHEET_ID, { useCache: true });
  const data = [];
  for (const row of admin.rows) {
    if ((row.values.registeredAt || '').trim()) continue;
    const assignedDate = (row.values.assignedDate || '').trim();
    if (!assignedDate) continue;
    data.push(...buildRowUpdateData(admin.sheetTitle, row.rowNumber, admin.columnMap, { registeredAt: assignedDate }));
  }
  if (data.length === 0) return { adminFixed: 0 };

  const sheets = getSheetsClient();
  await sheets.spreadsheets.values.batchUpdate({
    spreadsheetId: ADMIN_SPREADSHEET_ID,
    requestBody: { valueInputOption: 'RAW', data },
  });
  // 캐시만 비우고 즉시 재빌드는 하지 않음 (다음 요청 때 자연스럽게 갱신)
  sheetDataCache.delete(ADMIN_SPREADSHEET_ID);
  adminResultCache = null;

  return { adminFixed: data.length };
}

// 카마스터 시트에서 연락처별 로그인ID 유무를 읽어 반환합니다.
// 로그인ID가 공백인 회원 = 준회원.
async function readKamasterLoginStatus({ useCache = true } = {}) {
  if (useCache && kamasterCache && kamasterCache.expires > Date.now()) {
    return kamasterCache.loginStatusMap;
  }

  const sheets = getSheetsClient();

  // '카마스터' 문자열을 포함하는 탭을 자동 탐색
  const meta = await sheets.spreadsheets.get({
    spreadsheetId: ADMIN_SPREADSHEET_ID,
    fields: 'sheets.properties.title',
  });
  const titles = (meta.data.sheets || []).map((s) => s.properties.title);
  const sheetTitle = titles.find((t) => t.includes('카마스터'));
  if (!sheetTitle) {
    console.warn('카마스터 탭을 찾지 못했습니다. 탭 목록:', titles);
    kamasterCache = { expires: Date.now() + CACHE_TTL_MS, loginStatusMap: new Map() };
    return kamasterCache.loginStatusMap;
  }

  const res = await sheets.spreadsheets.values.get({
    spreadsheetId: ADMIN_SPREADSHEET_ID,
    range: `${quoteSheetTitle(sheetTitle)}!A1:AZ`,
  });
  const allRows = res.data.values || [];
  const loginStatusMap = new Map(); // normalizedPhone → hasLoginId (bool)

  if (allRows.length < 2) {
    kamasterCache = { expires: Date.now() + CACHE_TTL_MS, loginStatusMap };
    return loginStatusMap;
  }

  const header = allRows[0].map((h) => (h || '').toString().trim());
  const phoneIdx = header.findIndex((h) => ['연락처', '전화번호', '핸드폰번호', '휴대폰'].includes(h));
  const loginIdx = header.findIndex((h) => h.includes('로그인'));

  for (let i = 1; i < allRows.length; i++) {
    const row = allRows[i];
    if (phoneIdx < 0) continue;
    const phone = normalizePhone(row[phoneIdx] || '');
    if (!phone) continue;
    const loginId = loginIdx >= 0 ? (row[loginIdx] || '').toString().trim() : '';
    loginStatusMap.set(phone, !!loginId); // true = 정회원, false = 준회원
  }

  kamasterCache = { expires: Date.now() + CACHE_TTL_MS, loginStatusMap };
  return loginStatusMap;
}

module.exports = {
  ADMIN_SPREADSHEET_ID,
  MAX_FAILED_ATTEMPTS,
  logErrorToSheet,
  getAdminRows,
  deleteMemberRecord,
  getAccountsConfig,
  findAccountByLoginId,
  updateMemberRecord,
  createMemberRecord,
  recordFailedLogin,
  recordSuccessfulLogin,
  changeOwnPassword,
  adminResetPassword,
  listAccountsForAdmin,
  createAccount,
  readRefSheetGrid,
  updateRefSheetCell,
  readRenewalRows,
  updateRenewalRecord,
  addRenewalCallNote,
  importManagerNotesToCallHistory,
  readNotepadSheet,
  saveNotepadSheet,
  readTemplatesSheet,
  addTemplateCategory,
  renameTemplateCategory,
  deleteTemplateCategory,
  addTemplateEntry,
  updateTemplateEntry,
  deleteTemplateEntry,
  readLeaseRegistry,
  addLeaseEntry,
  updateLeaseEntry,
  deleteLeaseEntry,
  readLinkHub,
  addInternalLink,
  updateInternalLink,
  deleteInternalLink,
  addInsurerLink,
  updateInsurerLink,
  deleteInsurerLink,
  readAnnouncement,
  saveAnnouncement,
  readPerformanceDashboard,
  backfillRegisteredAt,
  readKamasterLoginStatus,
};
