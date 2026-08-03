// 구글 시트의 한글 컬럼명 <-> 내부 필드키 매핑을 한 곳에서 관리합니다.
// 관리자용 시트와 매니저 개별 시트는 헤더 문구가 살짝 다른 경우가 있어(예: "컨택 히스토리(매니저)" vs "컨택 히스토리"),
// 필드마다 가능한 헤더 문구를 여러 개(aliases) 등록해두고 실제 헤더 행을 읽을 때 매칭합니다.

const FIELDS = [
  { key: 'managerSheetLink', headers: ['매니저 시트 바로가기'] },
  { key: 'seq', headers: ['seq'] },
  { key: 'group', headers: ['그룹'] },
  { key: 'brand', headers: ['브랜드'] },
  { key: 'wideInsta', headers: ['광역/인스타'] },
  { key: 'region', headers: ['권역'] },
  { key: 'name', headers: ['이름'] },
  { key: 'phone', headers: ['연락처'] },
  { key: 'branch', headers: ['지점/대리점 명'] },
  { key: 'manager', headers: ['담당매니저'] },
  { key: 'assignedDate', headers: ['배분일자'] },
  { key: 'priorityDealer', headers: ['우선컨택 딜러여부'] },
  { key: 'highEfficiency', headers: ['고효율딜러여부'] },
  { key: 'highEfficiencyScore', headers: ['고효율딜러수치'] },
  { key: 'contacted', headers: ['컨택여부'] },
  { key: 'firstContactDate', headers: ['최초컨택일자'] },
  { key: 'reContactDate', headers: ['재컨택일자'] },
  { key: 'smsSent', headers: ['문자여부'] },
  { key: 'contactSentiment', headers: ['컨택 호의도'] },
  { key: 'contactHistory', headers: ['컨택 히스토리(매니저)', '컨택 히스토리'] },
  { key: 'preRegistered', headers: ['사전예약여부'] },
  { key: 'appJoinDate', headers: ['App가입일자'] },
  { key: 'totalContracts', headers: ['누적 계약체결건수'] },
  { key: 'last60dContracts', headers: ['직전 60일 계약체결건수'] },
  { key: 'last1yContracts', headers: ['직전 1년 본인 계약 건수'] },
  { key: 'last1yTop10', headers: ['직전 1년 본인 10% 횟수'] },
  { key: 'adminNote', headers: ['관리자 특이사항'] },
  { key: 'lastModifiedBy', headers: ['수정자'] },
  { key: 'registeredAt', headers: ['등록일자'] },
];

// 화면에 보여줄 컬럼 순서/라벨 (테이블 렌더링용)
const DISPLAY_COLUMNS = [
  { key: 'name', label: '이름' },
  { key: 'phone', label: '연락처' },
  { key: 'manager', label: '담당매니저' },
  { key: 'group', label: '그룹' },
  { key: 'brand', label: '브랜드' },
  { key: 'branch', label: '지점/대리점' },
  { key: 'contacted', label: '컨택여부' },
  { key: 'firstContactDate', label: '최초컨택일자' },
  { key: 'reContactDate', label: '재컨택일자' },
  { key: 'smsSent', label: '문자여부' },
  { key: 'contactSentiment', label: '호의도' },
  { key: 'contactHistory', label: '컨택 히스토리' },
  { key: 'appJoinDate', label: 'App가입일자' },
  { key: 'totalContracts', label: '누적계약' },
  { key: 'last60dContracts', label: '직전60일' },
  { key: 'last1yContracts', label: '직전1년건수' },
  { key: 'last1yTop10', label: '직전1년계약' },
  { key: 'assignedDate', label: '등록일자' },
  { key: 'adminNote', label: '관리자 특이사항', adminOnly: true },
  { key: 'lastModifiedBy', label: '수정자', adminOnly: true },
];

// 매니저 권한으로 수정할 수 있는 필드
const MANAGER_EDITABLE = [
  'name',
  'phone',
  'group',
  'brand',
  'branch',
  'contacted',
  'firstContactDate',
  'reContactDate',
  'smsSent',
  'contactSentiment',
  'contactHistory',
  'preRegistered',
];

// 관리자 권한에서만 추가로 수정 가능한 필드 (매니저 수정 가능 필드 + 아래 항목)
const ADMIN_ONLY_EDITABLE = [
  'wideInsta',
  'region',
  'manager',
  'assignedDate',
  'priorityDealer',
  'highEfficiency',
  'highEfficiencyScore',
  'appJoinDate',
  'totalContracts',
  'last60dContracts',
  'last1yContracts',
  'last1yTop10',
  'adminNote',
];

// 매니저 화면에서 완전히 숨길 필드 (관리자만 보임)
const ADMIN_ONLY_VISIBLE = ['adminNote', 'managerSheetLink', 'lastModifiedBy'];

// 딜러 상세/추가 모달에서 항상 보이는 기본 정보 항목 (관리자·매니저 공통 순서)
const MODAL_PRIMARY_FIELDS = ['group', 'brand', 'branch', 'name', 'phone', 'contacted'];

// 모달에서 "접어두기"로 기본 숨김 처리되는 항목 (관리자·매니저 공통)
const MODAL_COMMON_COLLAPSIBLE = [
  'firstContactDate',
  'reContactDate',
  'smsSent',
  'contactSentiment',
  'preRegistered',
  'assignedDate',
  'priorityDealer',
  'highEfficiency',
  'highEfficiencyScore',
];

// 접어두기 영역 중 관리자에게만 추가로 보이는 항목
const MODAL_ADMIN_COLLAPSIBLE_EXTRA = ['manager', 'adminNote', 'lastModifiedBy'];

// 자동으로만 채워지는 값이라 상세/추가 모달에는 노출하지 않고 표(칼럼)에만 보여주는 항목
const MODAL_EXCLUDED_FIELDS = ['appJoinDate', 'totalContracts', 'last60dContracts', 'last1yContracts', 'last1yTop10', 'wideInsta', 'region'];

function buildColumnMap(headerRow) {
  const map = {};
  (headerRow || []).forEach((cell, idx) => {
    const text = (cell || '').toString().trim();
    if (!text) return;
    const field = FIELDS.find((f) => f.headers.includes(text));
    if (field && map[field.key] === undefined) map[field.key] = idx;
  });
  return map;
}

function rowArrayToValues(rowArray, columnMap) {
  const values = {};
  for (const key of Object.keys(columnMap)) {
    values[key] = (rowArray[columnMap[key]] || '').toString();
  }
  return values;
}

function normalizePhone(value) {
  return (value || '').toString().replace(/\D/g, '');
}

const GROUP_MAP = {
  G1: 'G1(수입)',
  G2: 'G2(국산)',
  G3: 'G3(중고차)',
  G4: 'G4(보험설계)',
  G5: 'G5(에이전시)',
};

function normalizeGroup(value) {
  const v = (value || '').toString().trim();
  return GROUP_MAP[v] || v;
}

// 딜러가 등록된 시각을 "YYYY-MM-DD HH:mm:ss" (한국시간) 형태로 만듭니다.
// 문자열로 그대로 정렬해도 시간 순서가 맞도록 고정폭으로 만든 형식입니다.
function formatRegisteredAt(date = new Date()) {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Seoul',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  }).formatToParts(date);
  const map = {};
  for (const p of parts) map[p.type] = p.value;
  return `${map.year}-${map.month}-${map.day} ${map.hour}:${map.minute}:${map.second}`;
}

// 시트에 섞여 저장된 여러 날짜 표기("2025. 6. 20", "2026.01.02", "2025-08-28" 등)를
// 화면에는 항상 "YYYY-MM-DD" 한 가지 형식으로 통일해서 보여줍니다.
function formatDateDisplay(value) {
  const raw = (value || '').toString().trim();
  if (!raw) return '';
  const m = raw.match(/(\d{4})\D+(\d{1,2})\D+(\d{1,2})/);
  if (!m) return raw;
  const [, y, mo, d] = m;
  return `${y}-${mo.padStart(2, '0')}-${d.padStart(2, '0')}`;
}

// 컨택 히스토리는 한 셀(문자열) 안에 줄 단위로 메모를 쌓아둡니다. 형식: "NOTE\t시각\t작성자\t내용"
// 형식에 맞지 않는 줄(과거에 자유롭게 입력해둔 텍스트)은 작성자/시각 없는 메모로 취급합니다.
function appendContactHistoryNote(existing, { author, text, timestamp }) {
  const ts = timestamp || formatRegisteredAt();
  const safeText = (text || '').toString().replace(/[\n\r\t]+/g, ' ').trim();
  const line = `NOTE\t${ts}\t${author || ''}\t${safeText}`;
  const base = (existing || '').toString();
  return base ? `${base}\n${line}` : line;
}

function parseContactHistory(raw) {
  const lines = (raw || '').toString().split('\n').map((l) => l.trim()).filter(Boolean);
  const notes = [];
  for (const line of lines) {
    const parts = line.split('\t');
    if (parts[0] === 'NOTE' && parts.length >= 4) {
      notes.push({ timestamp: parts[1], author: parts[2], text: parts.slice(3).join('\t') });
    } else {
      notes.push({ timestamp: '', author: '', text: line });
    }
  }
  return notes.reverse();
}

function columnIndexToLetter(index) {
  let i = index + 1;
  let s = '';
  while (i > 0) {
    const m = (i - 1) % 26;
    s = String.fromCharCode(65 + m) + s;
    i = Math.floor((i - 1) / 26);
  }
  return s;
}

function letterToColumnIndex(letters) {
  let n = 0;
  for (const ch of String(letters).toUpperCase()) {
    n = n * 26 + (ch.charCodeAt(0) - 64);
  }
  return n - 1;
}

// "시트를 그대로 웹페이지에 심는" 범용 그리드 뷰/편집 화면에 노출할 참고용 시트 목록입니다.
// title은 관리자용 종합 스프레드시트 안의 실제 탭 이름과 정확히 일치해야 합니다.
// colStart/colEnd를 지정하면 그 범위(예: 갱신배정 탭의 B~P열)만 읽고/씁니다. 지정하지 않으면 탭 전체를 사용합니다.
const REF_SHEETS = [
  { key: 'renewal', title: '갱신배정', label: '갱신배정', gid: '1205371231', renewalTable: true },
  { key: 'dealer-faq', title: '딜러앱 FAQ', label: '딜러앱 FAQ', gid: '470466582', notepad: true, noteCell: 'A1', hiddenFromNav: true },
  { key: 'lms-template', title: 'LMS템플릿', label: 'LMS템플릿', templates: true, templatesCell: 'A1' },
  { key: 'lease-pledge', title: '리스(질권사)', label: '리스(질권사)', gid: '1656883024', registry: true, registryCell: 'A1' },
  { key: 'cm-tm', title: '원수사별 CM/TM', label: '원수사별 CM/TM', linkHub: true, linkHubCell: 'A1' },
];

// 갱신배정 탭: 헤더는 2행, 데이터는 3행부터 시작합니다. 헤더 문구로 찾지 않고 칼럼 위치(B~Q)를 고정 매핑합니다.
// 딜러연락처(L열)와 딜러이름(M열)은 각각 별도 칼럼에 저장됩니다.
const RENEWAL_FIELDS = [
  { key: 'renewalMonth', label: '갱신월', col: 'B' },
  { key: 'assignedDate', label: '배정일', col: 'C' },
  { key: 'assignOrder', label: '배정순번', col: 'D', adminOnly: true },
  { key: 'manager', label: '갱신담당매니저', col: 'E' },
  { key: 'customerName', label: '고객명', col: 'F' },
  { key: 'residentNumber', label: '주민번호', col: 'G' },
  { key: 'phone', label: '연락처', col: 'H' },
  { key: 'carNumber', label: '차량번호', col: 'I' },
  { key: 'expiryDate', label: '만기일자', col: 'J' },
  { key: 'insurer', label: '가입보험사', col: 'K' },
  { key: 'dealerContact', label: '딜러연락처', col: 'L' },
  { key: 'dealerName', label: '딜러이름', col: 'M' },
  { key: 'dealerType', label: '딜러유형', col: 'N' },
  { key: 'dealerRecent60d', label: '딜러 직전 60일 계약여부', col: 'O', type: 'select', options: ['', 'Y', 'N'] },
  { key: 'dealerLastContractDate', label: '딜러 최종 계약일자', col: 'P' },
  { key: 'callHistory', label: '컨택 히스토리', col: 'Q' },
];

function splitDealerContactName(raw) {
  const v = (raw || '').toString().trim();
  if (!v || v === '-') return { dealerContact: '', dealerName: '' };
  const idx = v.indexOf('/');
  if (idx === -1) return { dealerContact: '', dealerName: v };
  return { dealerContact: v.slice(0, idx).trim(), dealerName: v.slice(idx + 1).trim() };
}

function joinDealerContactName(dealerContact, dealerName) {
  const c = (dealerContact || '').toString().trim();
  const n = (dealerName || '').toString().trim();
  if (!c && !n) return '';
  if (!c) return n;
  if (!n) return c;
  return `${c} / ${n}`;
}

// 갱신배정 탭에서 매니저가 직접 수정할 수 있는 항목 (딜러와 통화하며 알게 되는 내용).
// 통화이력은 회원관리의 컨택 히스토리처럼 별도 메모 추가 API로만 기록합니다(본문 저장과 분리).
const RENEWAL_MANAGER_EDITABLE = ['dealerContact', 'dealerName', 'dealerType', 'dealerRecent60d', 'dealerLastContractDate'];

// 관리자만 수정 가능한 항목 (배정 단계에서 정해지는 기본 데이터)
const RENEWAL_ADMIN_ONLY_EDITABLE = [
  'renewalMonth',
  'assignedDate',
  'assignOrder',
  'manager',
  'customerName',
  'residentNumber',
  'phone',
  'carNumber',
  'expiryDate',
  'insurer',
];

// LMS템플릿 탭의 기본 카테고리(사이드바) 목록(처음 한 번도 저장되기 전 보여줄 기본값).
// 카테고리 하나에 여러 개의 템플릿(문구)을 등록할 수 있습니다.
// id는 고정값으로 둬서, 시트 셀이 비어있는 동안 매번 다시 만들어내도(저장 전이라) 항상 같은 id가 유지되게 합니다.
const LMS_TEMPLATE_CATEGORIES = [
  { id: 'dealer-promo', title: '딜러 홍보 메시지' },
  { id: 'new-car-quote', title: '신차 견적 요청(딜러 발송용)' },
  { id: 'existing-dealer-referral', title: '기존 가입딜러(소개 가입)' },
  { id: 'signup-complete', title: '가입완료(고객용)' },
  { id: 'insurer-cs-numbers', title: '원수사별 고객센터 대표전화' },
  { id: 'commission-schedule', title: '수수료 지급 일정 안내' },
  { id: 'off-handover-request', title: '오프 인수요청(총무님 전송)' },
  { id: 'birthday-coupon-before', title: '생일쿠폰발송 안내(생일 전)' },
  { id: 'birthday-coupon-after', title: '생일쿠폰발송 안내(생일 후)' },
  { id: 'etc', title: '기타' },
  { id: 'insurer-endorsement-numbers', title: '보험사별 배서 전용 번호' },
  { id: 'extra-discount-request', title: '추가할인 요청 안내' },
  { id: 'ad-fee-adjustment', title: '광고비 조정 안내 문자' },
];

// 리스(질권사) 탭의 기본 등록 목록(처음 한 번도 저장되기 전 보여줄 기본값).
// id는 고정값으로 둬서, 시트 셀이 비어있는 동안 매번 다시 만들어내도(저장 전이라) 항상 같은 id가 유지되게 합니다.
const LEASE_PLEDGE_DEFAULTS = [
  { id: 'lp1', company: '하나캐피탈(주)', businessNumber: '220-81-09337' },
  { id: 'lp2', company: '한국캐피탈(주)', businessNumber: '314-81-15454' },
  { id: 'lp3', company: '한국캐피탈주식회사부산지점', businessNumber: '607-85-36140' },
  { id: 'lp4', company: '현대캐피탈(주)강서지점', businessNumber: '109-85-12377' },
  { id: 'lp5', company: '현대캐피탈(주)분당지점', businessNumber: '129-85-19365' },
  { id: 'lp6', company: '현대캐피탈주식회사', businessNumber: '116-81-36248' },
  { id: 'lp7', company: '삼성카드주식회사', businessNumber: '202-81-45602' },
  { id: 'lp8', company: '스타리스(주)', businessNumber: '104-81-28838' },
  { id: 'lp9', company: '신한카드주식회사', businessNumber: '202-81-48079' },
  { id: 'lp10', company: '신한캐피탈(주)', businessNumber: '134-81-11323' },
  { id: 'lp11', company: '씨앤에이치캐피탈(주)', businessNumber: '130-81-26203' },
  { id: 'lp12', company: '씨앤에이치캐피탈(주)서울지점', businessNumber: '104-85-04042' },
  { id: 'lp13', company: '알씨아이파이낸셜서비스코리아(주)', businessNumber: '104-81-79808' },
  { id: 'lp14', company: '엔에이치농협캐피탈(주)', businessNumber: '104-86-06955' },
  { id: 'lp15', company: '엠캐피탈(주)', businessNumber: '105-81-87072' },
  { id: 'lp16', company: '오케이캐피탈 [(주)한국씨티그룹캐피탈]', businessNumber: '102-81-11985' },
  { id: 'lp17', company: '우리금융캐피탈주식회사', businessNumber: '306-81-18407' },
  { id: 'lp18', company: '제이비우리캐피탈(주)', businessNumber: '501-81-18905' },
  { id: 'lp19', company: '주식회사아이엠캐피탈', businessNumber: '220-87-87408' },
  { id: 'lp20', company: '주식회사우리카드', businessNumber: '101-86-79070' },
  { id: 'lp21', company: '케이비캐피탈(주)서울지점', businessNumber: '214-85-08573' },
  { id: 'lp22', company: '케이비캐피탈주식회사', businessNumber: '124-81-25121' },
  { id: 'lp23', company: '토요타파이낸셜서비스코리아(주)', businessNumber: '220-87-04770' },
  { id: 'lp24', company: '포르쉐파이낸셜서비스코리아주식회사', businessNumber: '114-87-12728' },
  { id: 'lp25', company: '(주)두산캐피탈', businessNumber: '116-81-53683' },
  { id: 'lp26', company: '(주)아이비케이캐피탈', businessNumber: '220-81-28519' },
  { id: 'lp27', company: '(주)애큐온캐피탈', businessNumber: '214-87-99739' },
  { id: 'lp28', company: '(주)오릭스캐피탈코리아', businessNumber: '120-86-63282' },
  { id: 'lp29', company: '도이치파이낸셜주식회사', businessNumber: '264-81-17050' },
  { id: 'lp30', company: '롯데오토리스(주)', businessNumber: '138-81-71361' },
  { id: 'lp31', company: '롯데캐피탈(주)부산지점', businessNumber: '604-85-08965' },
  { id: 'lp32', company: '롯데캐피탈(주)서울본점', businessNumber: '120-81-55981' },
  { id: 'lp33', company: '메르세데스벤츠파이낸셜서비스코리아㈜', businessNumber: '220-86-47637' },
  { id: 'lp34', company: '메리츠종합금융증권(주)', businessNumber: '116-81-22502' },
  { id: 'lp35', company: '메리츠캐피탈주식회사', businessNumber: '107-87-67865' },
  { id: 'lp36', company: '미래에셋캐피탈(주)', businessNumber: '634-85-00493' },
  { id: 'lp37', company: '미래에셋캐피탈(주)서울본점', businessNumber: '410-81-40265' },
  { id: 'lp38', company: '미래에셋캐피탈(주)인천지점', businessNumber: '345-85-00517' },
  { id: 'lp39', company: '비엔케이캐피탈(주)', businessNumber: '605-86-01190' },
  { id: 'lp40', company: '비엠더블유파이낸셜서비스코리아(주)부산지점', businessNumber: '260-85-00351' },
  { id: 'lp41', company: '비엠더블유파이낸셜서비스코리아(주)서울본점', businessNumber: '211-86-78437' },
  { id: 'lp42', company: '비엠더블유파이낸셜서비스코리아(주)송도지점', businessNumber: '131-85-25165' },
  { id: 'lp43', company: '산은캐피탈주식회사', businessNumber: '202-81-50051' },
  { id: 'lp44', company: '엠지캐피탈(주)', businessNumber: '105-81-87072' },
  { id: 'lp45', company: '폭스바겐 파이낸셜', businessNumber: '' },
];

module.exports = {
  FIELDS,
  DISPLAY_COLUMNS,
  MANAGER_EDITABLE,
  ADMIN_ONLY_EDITABLE,
  ADMIN_ONLY_VISIBLE,
  MODAL_PRIMARY_FIELDS,
  MODAL_COMMON_COLLAPSIBLE,
  MODAL_ADMIN_COLLAPSIBLE_EXTRA,
  MODAL_EXCLUDED_FIELDS,
  REF_SHEETS,
  RENEWAL_FIELDS,
  RENEWAL_MANAGER_EDITABLE,
  RENEWAL_ADMIN_ONLY_EDITABLE,
  splitDealerContactName,
  joinDealerContactName,
  LMS_TEMPLATE_CATEGORIES,
  LEASE_PLEDGE_DEFAULTS,
  buildColumnMap,
  rowArrayToValues,
  normalizePhone,
  normalizeGroup,
  columnIndexToLetter,
  letterToColumnIndex,
  formatRegisteredAt,
  formatDateDisplay,
  appendContactHistoryNote,
  parseContactHistory,
};
