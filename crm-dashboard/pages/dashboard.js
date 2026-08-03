import { useEffect, useMemo, useRef, useState } from 'react';
import { useRouter } from 'next/router';
import Link from 'next/link';
import cookie from 'cookie';
import { verifySession, COOKIE_NAME } from '../lib/auth';
import {
  DISPLAY_COLUMNS,
  MANAGER_EDITABLE,
  ADMIN_ONLY_EDITABLE,
  MODAL_COMMON_COLLAPSIBLE,
  MODAL_ADMIN_COLLAPSIBLE_EXTRA,
  REF_SHEETS,
  formatDateDisplay,
  parseContactHistory,
} from '../lib/sheetSchema';
import ChangePasswordModal from '../components/ChangePasswordModal';
import Announcement from '../components/Announcement';
import FaqWidget from '../components/FaqWidget';
import useEscapeKey from '../lib/useEscapeKey';
import { getEntry, fetchAndCache, mergeEntry } from '../lib/dataCache';

export async function getServerSideProps({ req }) {
  const cookies = cookie.parse(req.headers.cookie || '');
  const session = cookies[COOKIE_NAME] ? verifySession(cookies[COOKIE_NAME]) : null;
  if (!session) {
    return { redirect: { destination: '/login', permanent: false } };
  }
  return {
    props: {
      role: session.role,
      name: session.name,
      adminSheetUrl:
        session.role === '관리자' && process.env.ADMIN_SPREADSHEET_ID
          ? `https://docs.google.com/spreadsheets/d/${process.env.ADMIN_SPREADSHEET_ID}/edit`
          : null,
    },
  };
}

const FIELD_META = {
  name: { label: '이름', type: 'text', required: true },
  phone: { label: '연락처', type: 'text', placeholder: '예: 010-1234-5678', required: true },
  contacted: { label: '컨택여부', type: 'select', options: ['', 'Y', 'N'] },
  firstContactDate: { label: '최초컨택일자', type: 'date' },
  reContactDate: { label: '재컨택일자', type: 'date' },
  smsSent: { label: '문자여부', type: 'select', options: ['', 'Y', 'N'] },
  contactSentiment: { label: '컨택 호의도', type: 'select', options: ['', 'A', 'B', 'C'] },
  contactHistory: { label: '컨택 히스토리', type: 'textarea' },
  preRegistered: { label: '사전예약여부', type: 'select', options: ['', 'Y', 'N'] },
  group: {
    label: '그룹',
    type: 'select',
    options: [
      { value: '', label: '(미선택)' },
      { value: 'G1(수입)', label: 'G1(수입)' },
      { value: 'G2(국산)', label: 'G2(국산)' },
      { value: 'G3(중고차)', label: 'G3(중고차)' },
      { value: 'G4(보험설계)', label: 'G4(보험설계)' },
      { value: 'G5(에이전시)', label: 'G5(에이전시)' },
    ],
  },
  brand: { label: '브랜드', type: 'text' },
  wideInsta: { label: '광역/인스타', type: 'text' },
  region: { label: '권역', type: 'text' },
  branch: { label: '지점/대리점 명', type: 'text' },
  manager: { label: '담당매니저', type: 'text' },
  assignedDate: { label: '배분일자', type: 'date' },
  priorityDealer: { label: '우선컨택 딜러여부', type: 'select', options: ['', 'Y', 'N'] },
  highEfficiency: { label: '고효율딜러여부', type: 'select', options: ['', 'Y', 'N'] },
  highEfficiencyScore: { label: '고효율딜러수치', type: 'text' },
  appJoinDate: { label: 'App가입일자', type: 'text' },
  totalContracts: { label: '누적 계약체결건수', type: 'text' },
  last60dContracts: { label: '직전 60일 계약체결건수', type: 'text' },
  last1yContracts: { label: '직전 1년 본인 계약 건수', type: 'text' },
  last1yTop10: { label: '직전 1년 본인 10% 횟수', type: 'text' },
  adminNote: { label: '관리자 특이사항', type: 'textarea' },
};

const PAGE_SIZE_OPTIONS = [20, 50, 100, 200];

// 회원관리 표에 표시할 칼럼 (10개)
const TABLE_COLUMNS = [
  { key: 'name', label: '이름' },
  { key: 'phone', label: '연락처' },
  { key: 'manager', label: '담당매니저' },
  { key: 'group', label: '그룹' },
  { key: 'brand', label: '브랜드' },
  { key: 'branch', label: '지점/대리점' },
  { key: 'last60dContracts', label: '직전 60일 계약' },
  { key: 'last1yContracts', label: '직전1년건수' },
  { key: 'contacted', label: '컨택여부' },
  { key: 'firstContactDate', label: '최초컨택일자' },
  { key: 'contactHistory', label: '컨택 히스토리' },
];

// 이름·연락처·담당매니저만 열고정 (슬림한 9칼럼 표)
const FROZEN_KEYS = ['name', 'phone', 'manager'];
const FROZEN_KEY_SET = new Set(FROZEN_KEYS);

function maskPhone(phone) {
  if (!phone) return '-';
  return String(phone).replace(/(\d{4})$/, '****');
}

function getNoteClasses(text) {
  const t = (text || '').replace(/\s/g, '');
  if (t.includes('계약완료') || t.includes('체결완료')) return 'note-kw-contract';
  if (t.includes('타사가입')) return 'note-kw-other';
  if (t.includes('명의이전')) return 'note-kw-transfer';
  return '';
}

// 현재 페이지를 기준으로 "1 2 3 4 5 ... 85" 같은 페이지 번호 목록을 만듭니다.
// 페이지 수가 적으면 전부 보여주고, 많으면 앞/뒤 또는 현재 위치 주변만 보여주고 가운데는 '...'로 줄입니다.
function buildPageList(current, total) {
  if (total <= 7) return Array.from({ length: total }, (_, i) => i + 1);
  if (current <= 4) return [1, 2, 3, 4, 5, '...', total];
  if (current >= total - 3) return [1, '...', total - 4, total - 3, total - 2, total - 1, total];
  return [1, '...', current - 1, current, current + 1, '...', total];
}

function Badge({ value }) {
  if (!value) return <span style={{ color: '#C2C7CC' }}>-</span>;
  const v = value.trim().toUpperCase();
  if (v === 'Y') return <span className="badge badge-y">Y</span>;
  if (v === 'N') return <span className="badge badge-n">N</span>;
  if (v === 'A') return <span className="badge badge-a">A</span>;
  if (v === 'B') return <span className="badge badge-b">B</span>;
  if (v === 'C') return <span className="badge badge-c">C</span>;
  return <span>{value}</span>;
}

function csvEscape(v) {
  const s = v === undefined || v === null ? '' : String(v);
  if (/[",\n]/.test(s)) return '"' + s.replace(/"/g, '""') + '"';
  return s;
}

const NUMERIC_SORT_KEYS = ['totalContracts', 'last60dContracts', 'last1yContracts', 'last1yTop10', 'highEfficiencyScore'];
const DATE_SORT_KEYS = ['registeredAt', 'firstContactDate', 'reContactDate', 'assignedDate', 'appJoinDate'];
// 표/모달에서 날짜 표기를 "YYYY-MM-DD" 한 형식으로 통일해서 보여줄 칼럼들
const DATE_DISPLAY_KEYS = ['firstContactDate', 'reContactDate', 'assignedDate', 'appJoinDate'];

// 칼럼 종류에 따라 숫자/날짜/문자열 중 알맞은 방식으로 두 값을 비교합니다.
// 값이 없는 경우(특히 날짜)는 가장 오래된/작은 값으로 취급해 정렬 시 뒤로 밀립니다.
function compareRows(a, b, key) {
  const av = a[key] || '';
  const bv = b[key] || '';
  if (NUMERIC_SORT_KEYS.includes(key)) {
    return (Number(av) || 0) - (Number(bv) || 0);
  }
  if (DATE_SORT_KEYS.includes(key)) {
    return (Date.parse(av) || 0) - (Date.parse(bv) || 0);
  }
  return av.toString().localeCompare(bv.toString(), 'ko');
}

// 칼럼별 기본 너비(px). 글자수를 고려해 라벨/내용이 잘리지 않을 정도로 잡아둔 값이며,
// 칼럼 머리글의 손잡이를 드래그하면 사용자가 직접 더 늘리거나 줄일 수 있습니다.
const DEFAULT_COL_WIDTHS = {
  name: 100,
  phone: 130,
  manager: 110,
  group: 90,
  brand: 90,
  branch: 160,
  last60dContracts: 100,
  last1yContracts: 90,
  contacted: 90,
  firstContactDate: 120,
  contactHistory: 280,
};
const DEFAULT_COL_WIDTH = 110;
const MIN_COL_WIDTH = 50;
const ACTION_COL_WIDTH = 70;

const POLL_INTERVAL_MS = 60 * 60 * 1000; // 1시간 — 자동 업데이트 주기
const MEMBERS_KEY = 'members';

export default function DashboardPage({ role, name, adminSheetUrl }) {
  const router = useRouter();
  const isAdmin = role === '관리자';

  // 로그인 직후 프리페치되었거나(_app.js) 다른 탭에서 이미 불러온 데이터가 캐시에 있으면
  // 재방문/첫 진입 시 로딩 화면 없이 바로 표를 그립니다.
  const initialMembers = getEntry(MEMBERS_KEY);
  const [rows, setRows] = useState(() => (initialMembers ? initialMembers.data.rows : []));
  const [loading, setLoading] = useState(() => !initialMembers);
  const [error, setError] = useState('');
  const [refreshTick, setRefreshTick] = useState(0);

  const [search, setSearch] = useState('');
  const [managerFilter, setManagerFilter] = useState('');
  const [contactedFilter, setContactedFilter] = useState('');
  const [preRegFilter, setPreRegFilter] = useState('');
  const [appJoinFilter, setAppJoinFilter] = useState('');
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);
  const [gotoInput, setGotoInput] = useState('');

  const [editing, setEditing] = useState(null);
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState(null);
  const [changingPassword, setChangingPassword] = useState(false);
  const [addingDealer, setAddingDealer] = useState(false);
  const [addSaving, setAddSaving] = useState(false);
  const [addMsg, setAddMsg] = useState(null);
  const [lastSynced, setLastSynced] = useState(null);
  const [managerOptions, setManagerOptions] = useState(null);
  const [showSearchPopup, setShowSearchPopup] = useState(false);
  const searchPopupTimerRef = useRef(null);
  const [showGlobalSearch, setShowGlobalSearch] = useState(false);
  const [sortKey, setSortKey] = useState('assignedDate');
  const [sortDir, setSortDir] = useState('desc');
  const [colWidths, setColWidths] = useState(DEFAULT_COL_WIDTHS);
  const [focusNote, setFocusNote] = useState(false);
  const topbarRef = useRef(null);

  const [selectedPhones, setSelectedPhones] = useState(() => new Set());
  const [bulkManagerModal, setBulkManagerModal] = useState(false);
  const [bulkSaving, setBulkSaving] = useState(false);
  const [bulkResult, setBulkResult] = useState(null);
  const [syncingManagers, setSyncingManagers] = useState(false);
  const [syncManagersMsg, setSyncManagersMsg] = useState(null);

  // silent=true면 화면에 "불러오는 중..." 스피너를 띄우지 않고 조용히 최신 데이터로 교체합니다.
  // 구글 시트에서 직접 수정한 내용도 이 폴링을 통해 자동으로 화면에 반영됩니다.
  // ETag를 보내 데이터가 바뀌지 않았으면(304) 상태 업데이트를 건너뜁니다.
  // force=true면 서버 캐시까지 건너뛰고 구글 시트에서 바로 최신 데이터를 가져옵니다("새로고침" 버튼 전용).
  async function fetchRows({ silent = false, force = false } = {}) {
    if (!silent) setLoading(true);
    setError('');
    try {
      const data = await fetchAndCache(MEMBERS_KEY, '/api/members', { force });
      if (data) setRows(data.rows);
      setLastSynced(new Date());
    } catch (e) {
      if (!silent) setError(e.message);
    } finally {
      if (!silent) setLoading(false);
    }
  }

  // 로컬에서 즉시 반영하는 변경(저장/메모 추가 등)도 캐시에 함께 기록해둬야
  // 다른 탭에 갔다가 돌아왔을 때 방금 한 수정 내용이 사라지지 않습니다.
  function updateRowsLocal(updater) {
    setRows((prev) => {
      const next = updater(prev);
      mergeEntry(MEMBERS_KEY, { rows: next });
      return next;
    });
  }

  async function handleManualRefresh() {
    await fetchRows({ force: true });
    setRefreshTick((t) => t + 1);
  }

  useEffect(() => {
    if (!getEntry(MEMBERS_KEY)) {
      fetchRows();
    }
  }, []);

  // 공지 배너 유무에 따라 topbar 높이가 달라지므로 ResizeObserver로 측정 후 CSS 변수에 반영.
  // detail-side-panel은 top: var(--topbar-h) 으로 topbar 바로 아래에 붙어 표시됩니다.
  useEffect(() => {
    const el = topbarRef.current;
    if (!el) return;
    const update = () => document.documentElement.style.setProperty('--topbar-h', el.offsetHeight + 'px');
    update();
    const obs = new ResizeObserver(update);
    obs.observe(el);
    return () => obs.disconnect();
  }, []);

  // 담당매니저 드롭박스에 쓸 매니저 이름 목록을 계정관리 탭 데이터에서 가져옵니다. (관리자만)
  useEffect(() => {
    if (!isAdmin) return;
    fetch('/api/accounts')
      .then((res) => res.json())
      .then((data) => {
        if (!Array.isArray(data.accounts)) return;
        const names = data.accounts
          .filter((a) => a.role === '매니저')
          .map((a) => a.name)
          .filter(Boolean)
          .sort();
        setManagerOptions(names);
      })
      .catch(() => {});
  }, [isAdmin]);

  // 편집창이 열려있지 않을 때, 캐시된 데이터를 마지막으로 불러온 시점 기준 1시간 후에
  // 자동으로 한 번 조용히 새 데이터를 가져옵니다. 그 전까지는 같은 데이터를 그대로 보여줍니다.
  // (편집 중에 화면이 바뀌면 입력 중인 내용을 잃어버릴 수 있어 그 동안은 잠시 멈춥니다)
  useEffect(() => {
    if (editing || addingDealer) return;
    const entry = getEntry(MEMBERS_KEY);
    const age = entry ? Date.now() - entry.fetchedAt : 0;
    const delay = entry ? Math.max(0, POLL_INTERVAL_MS - age) : POLL_INTERVAL_MS;
    let interval;
    const timeout = setTimeout(() => {
      fetchRows({ silent: true });
      interval = setInterval(() => fetchRows({ silent: true }), POLL_INTERVAL_MS);
    }, delay);
    return () => {
      clearTimeout(timeout);
      if (interval) clearInterval(interval);
    };
  }, [editing, addingDealer, refreshTick]);

  const managers = useMemo(() => {
    const set = new Set(rows.map((r) => r.manager).filter(Boolean));
    return Array.from(set).sort();
  }, [rows]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return rows.filter((r) => {
      if (q) {
        const hay = `${r.name || ''} ${r.phone || ''} ${r.branch || ''} ${r.manager || ''}`.toLowerCase();
        if (!hay.includes(q)) return false;
      }
      if (isAdmin && managerFilter && r.manager !== managerFilter) return false;
      if (contactedFilter && (r.contacted || '').toUpperCase() !== contactedFilter) return false;
      if (preRegFilter && (r.preRegistered || '').toUpperCase() !== preRegFilter) return false;
      if (appJoinFilter) {
        const hasAppJoinDate = !!(r.appJoinDate || '').toString().trim();
        if (appJoinFilter === 'Y' && !hasAppJoinDate) return false;
        if (appJoinFilter === 'N' && hasAppJoinDate) return false;
      }
      return true;
    });
  }, [rows, search, managerFilter, contactedFilter, preRegFilter, appJoinFilter, isAdmin]);

  const sorted = useMemo(() => {
    const list = [...filtered];
    list.sort((a, b) => {
      const cmp = compareRows(a, b, sortKey);
      return sortDir === 'asc' ? cmp : -cmp;
    });
    return list;
  }, [filtered, sortKey, sortDir]);

  const searchPopupMatches = useMemo(() => {
    const q = search.trim();
    if (q.length < 2) return [];
    const qLower = q.toLowerCase();
    const qPhone = q.replace(/\D/g, '');
    return rows.filter((r) => {
      const rName = (r.name || '').toLowerCase();
      const rPhone = (r.phone || '').replace(/\D/g, '');
      return rName.includes(qLower) || (qPhone.length >= 3 && rPhone.includes(qPhone));
    }).slice(0, 15);
  }, [rows, search]);

  const totalPages = Math.max(1, Math.ceil(sorted.length / pageSize));
  const paged = sorted.slice((page - 1) * pageSize, page * pageSize);
  const rangeStart = sorted.length === 0 ? 0 : (page - 1) * pageSize + 1;
  const rangeEnd = Math.min(page * pageSize, sorted.length);
  const pageNumbers = buildPageList(page, totalPages);

  function gotoPage() {
    const n = parseInt(gotoInput, 10);
    if (!n || n < 1 || n > totalPages) return;
    setPage(n);
    setGotoInput('');
  }

  useEffect(() => {
    setPage(1);
  }, [search, managerFilter, contactedFilter, preRegFilter, appJoinFilter, pageSize]);

  useEffect(() => {
    setSelectedPhones(new Set());
    setBulkResult(null);
  }, [search, managerFilter, contactedFilter, preRegFilter, appJoinFilter]);

  function resetFilters() {
    setSearch('');
    setManagerFilter('');
    setContactedFilter('');
    setPreRegFilter('');
    setAppJoinFilter('');
  }

  // 칼럼 제목을 클릭하면 그 칼럼으로 정렬하고, 같은 칼럼을 다시 클릭하면 방향을 반대로 바꿉니다.
  function toggleSort(key) {
    if (sortKey === key) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortKey(key);
      setSortDir('asc');
    }
  }

  // 칼럼 머리글의 우측 손잡이를 마우스로 드래그하면 그 칼럼의 너비를 직접 조절합니다.
  function startColumnResize(e, key) {
    e.preventDefault();
    e.stopPropagation();
    const startX = e.clientX;
    const startWidth = colWidths[key] || DEFAULT_COL_WIDTH;
    const prevUserSelect = document.body.style.userSelect;
    document.body.style.userSelect = 'none';
    function onMouseMove(ev) {
      const nextWidth = Math.max(MIN_COL_WIDTH, startWidth + (ev.clientX - startX));
      setColWidths((prev) => ({ ...prev, [key]: nextWidth }));
    }
    function onMouseUp() {
      document.body.style.userSelect = prevUserSelect;
      document.removeEventListener('mousemove', onMouseMove);
      document.removeEventListener('mouseup', onMouseUp);
    }
    document.addEventListener('mousemove', onMouseMove);
    document.addEventListener('mouseup', onMouseUp);
  }

  async function handleSyncManagers() {
    setSyncingManagers(true);
    setSyncManagersMsg(null);
    try {
      const res = await fetch('/api/admin/sync-managers', { method: 'POST' });
      const data = await res.json();
      if (!res.ok) {
        setSyncManagersMsg({ type: 'err', text: data.error || '동기화 실패' });
      } else {
        setSyncManagersMsg({ type: 'ok', text: `동기화 완료 (삭제 ${data.deletedRows}행, 추가 ${data.appendedRows}행, 업데이트 ${data.updatedFields}건)` });
      }
    } catch (e) {
      setSyncManagersMsg({ type: 'err', text: '네트워크 오류' });
    } finally {
      setSyncingManagers(false);
    }
  }

  function exportCsv() {
    const cols = DISPLAY_COLUMNS.filter((c) => isAdmin || !c.adminOnly);
    const header = cols.map((c) => csvEscape(c.label)).join(',');
    const body = sorted
      .map((r) => cols.map((c) => csvEscape(DATE_DISPLAY_KEYS.includes(c.key) ? formatDateDisplay(r[c.key]) : r[c.key])).join(','))
      .join('\n');
    const csv = '﻿' + header + '\n' + body;
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    const today = new Date().toISOString().slice(0, 10).replace(/-/g, '');
    a.href = url;
    a.download = `회원목록_${today}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }

  async function handleLogout() {
    await fetch('/api/auth/logout', { method: 'POST' });
    window.location.href = '/login';
  }

  function openEdit(row, withFocusNote = false) {
    setEditing(row);
    setFocusNote(withFocusNote);
    setSaveMsg(null);
  }

  async function handleDelete(phone) {
    setSaving(true);
    setSaveMsg(null);
    try {
      const res = await fetch('/api/members/delete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ phone }),
      });
      const data = await res.json();
      if (!res.ok) {
        setSaveMsg({ type: 'err', text: data.error || '삭제에 실패했습니다.' });
        setSaving(false);
        return;
      }
      updateRowsLocal((prev) => prev.filter((r) => r.phone !== phone));
      setEditing(null);
    } catch (e) {
      setSaveMsg({ type: 'err', text: '네트워크 오류가 발생했습니다.' });
      setSaving(false);
    } finally {
      setSaving(false);
    }
  }

  async function handleSave(formValues) {
    setSaving(true);
    setSaveMsg(null);
    try {
      const res = await fetch('/api/members/update', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ phone: editing.phone, updates: formValues }),
      });
      const data = await res.json();
      if (!res.ok) {
        setSaveMsg({ type: 'err', text: data.error || '저장에 실패했습니다.' });
        setSaving(false);
        return;
      }
      const merged = { ...formValues, ...(data.updates || {}) };
      updateRowsLocal((prev) =>
        prev.map((r) => (r.phone === editing.phone ? { ...r, ...merged } : r))
      );
      setEditing((prev) => (prev ? { ...prev, ...merged } : prev));
      setSaveMsg(
        data.syncedToManagerSheet
          ? { type: 'ok', text: '저장되었습니다. (담당매니저 개별 시트에도 반영됨)' }
          : { type: 'warn', text: data.warning || '저장되었습니다.' }
      );
    } catch (e) {
      setSaveMsg({ type: 'err', text: '네트워크 오류가 발생했습니다.' });
    } finally {
      setSaving(false);
    }
  }

  // 컨택 히스토리 패널에서 메모를 추가하면(서버가 컨택히스토리/최초컨택일자를 갱신) 목록과
  // 열려있는 상세 모달에도 즉시 반영합니다.
  function handleRowFieldsUpdated(updates) {
    updateRowsLocal((prev) =>
      prev.map((r) => (r.phone === editing.phone ? { ...r, ...updates } : r))
    );
    setEditing((prev) => (prev ? { ...prev, ...updates } : prev));
  }

  async function handleAddDealer(formValues) {
    setAddSaving(true);
    setAddMsg(null);
    try {
      const res = await fetch('/api/members/create', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(formValues),
      });
      const data = await res.json();
      if (!res.ok) {
        setAddMsg({ type: 'err', text: data.error || '딜러 추가에 실패했습니다.' });
        setAddSaving(false);
        return;
      }
      setAddMsg(
        data.syncedToManagerSheet
          ? { type: 'ok', text: '딜러가 추가되었습니다. (담당매니저 개별 시트에도 반영됨)' }
          : { type: 'warn', text: data.warning || '딜러가 추가되었습니다.' }
      );
      fetchRows({ silent: true });
    } catch (e) {
      setAddMsg({ type: 'err', text: '네트워크 오류가 발생했습니다.' });
    } finally {
      setAddSaving(false);
    }
  }

  async function handleBulkManagerChange(newManager) {
    setBulkSaving(true);
    setBulkResult(null);
    try {
      const phones = Array.from(selectedPhones);
      const res = await fetch('/api/members/bulk-manager', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ phones, manager: newManager }),
      });
      const data = await res.json();
      if (!res.ok) {
        setBulkResult({ type: 'err', text: data.error || '일괄 변경에 실패했습니다.' });
        setBulkSaving(false);
        return;
      }
      const updatedSet = new Set(data.updated || []);
      updateRowsLocal((prev) =>
        prev.map((r) =>
          updatedSet.has(r.phone) ? { ...r, manager: newManager, lastModifiedBy: '관리자' } : r
        )
      );
      setBulkManagerModal(false);
      setSelectedPhones(new Set());
      const failedCount = data.failed?.length || 0;
      const successText = `${updatedSet.size}명의 담당매니저가 '${newManager}'(으)로 변경되었습니다.`;
      setBulkResult({
        type: failedCount > 0 ? 'warn' : 'ok',
        text: failedCount > 0 ? `${successText} (${failedCount}명 실패)` : successText,
      });
    } catch (e) {
      setBulkResult({ type: 'err', text: '네트워크 오류가 발생했습니다.' });
      setBulkSaving(false);
    } finally {
      setBulkSaving(false);
    }
  }

  const visibleColumns = TABLE_COLUMNS;

  const frozenLefts = useMemo(() => {
    const result = {};
    let acc = isAdmin ? 40 : 0; // 관리자는 체크박스 칼럼(40px) 선행
    for (const key of FROZEN_KEYS) {
      result[key] = acc;
      acc += colWidths[key] || DEFAULT_COL_WIDTHS[key] || DEFAULT_COL_WIDTH;
    }
    return result;
  }, [isAdmin, colWidths]);

  return (
    <div className="app-shell">
      <FaqWidget isAdmin={isAdmin} />
      <div className="topbar" ref={topbarRef}>
        <div className="topbar-main">
          <div className="topbar-left">
            <span className="topbar-title">My Dealer</span>
            <span className="topbar-badge">{role}</span>
            <nav className="topbar-nav">
              <Link className="topbar-nav-link active" href="/dashboard">회원관리</Link>
              {REF_SHEETS.filter((s) => !s.hiddenFromNav).map((s) => (
                <Link key={s.key} className="topbar-nav-link" href={`/sheet/${s.key}`}>{s.label}</Link>
              ))}
              {!isAdmin && <Link className="topbar-nav-link" href="/performance">실적현황</Link>}
              {isAdmin && <Link className="topbar-nav-link" href="/accounts">계정관리</Link>}
            </nav>
          </div>
          <div className="topbar-right">
            {adminSheetUrl && (
              <a className="logout-btn" href={adminSheetUrl} target="_blank" rel="noreferrer">
                구글 시트 원본 열기
              </a>
            )}
            <span className="topbar-user">{name}님</span>
            <button className="logout-btn" onClick={() => setChangingPassword(true)}>비밀번호 변경</button>
            <button className="logout-btn" onClick={handleLogout}>로그아웃</button>
          </div>
        </div>
        <Announcement isAdmin={isAdmin} />
      </div>

      <div className={`page-body${editing ? ' panel-open' : ''}`}>
        <div className="page-heading">
          <div>
            <h1>회원 관리</h1>
            <div className="count">
              검색된 회원 수: {filtered.length.toLocaleString()}명
              {lastSynced && ` · 마지막 동기화: ${lastSynced.toLocaleTimeString('ko-KR')}`}
            </div>
          </div>
          {isAdmin && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              {syncManagersMsg && (
                <span style={{ fontSize: 12, color: syncManagersMsg.type === 'ok' ? 'var(--green)' : 'var(--red)' }}>
                  {syncManagersMsg.text}
                </span>
              )}
              <button className="btn-secondary" onClick={handleSyncManagers} disabled={syncingManagers}>
                {syncingManagers ? '동기화 중...' : '매니저 시트 동기화'}
              </button>
            </div>
          )}
        </div>

        <div className="filters-card">
          <div className="filter-field" style={{ minWidth: 240, position: 'relative' }}>
            <label>통합검색 (이름/연락처/지점/매니저)</label>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              <input
                style={{ flex: 1, minWidth: 0 }}
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="검색어 입력"
                onFocus={() => {
                  clearTimeout(searchPopupTimerRef.current);
                  setShowSearchPopup(true);
                }}
                onBlur={() => {
                  searchPopupTimerRef.current = setTimeout(() => setShowSearchPopup(false), 200);
                }}
              />
              <button className="btn" style={{ whiteSpace: 'nowrap' }} onClick={() => setShowGlobalSearch(true)}>
                딜러 검색
              </button>
            </div>
            {showSearchPopup && searchPopupMatches.length > 0 && (
              <div style={{
                position: 'absolute', top: '100%', left: 0, zIndex: 300, minWidth: 540,
                background: '#f8f9fa', border: '1.5px solid var(--border)',
                borderRadius: 8, boxShadow: '0 6px 24px rgba(0,0,0,0.22)', marginTop: 4,
                maxHeight: 340, overflowY: 'auto', color: 'var(--text)',
              }}>
                <div style={{ padding: '8px 14px', fontSize: 12, color: 'var(--muted)', borderBottom: '1px solid var(--border)', fontWeight: 500 }}>
                  이름·연락처 매칭 결과 {searchPopupMatches.length}건 (클릭 시 상세 보기)
                </div>
                <table style={{ width: '100%', fontSize: 13, borderCollapse: 'collapse', color: 'var(--text)' }}>
                  <thead>
                    <tr style={{ background: 'var(--table-head-bg)' }}>
                      <th style={{ padding: '7px 14px', textAlign: 'left', fontWeight: 700, color: 'var(--text)', whiteSpace: 'nowrap' }}>이름</th>
                      <th style={{ padding: '7px 14px', textAlign: 'left', fontWeight: 700, color: 'var(--text)', whiteSpace: 'nowrap' }}>연락처</th>
                      <th style={{ padding: '7px 14px', textAlign: 'left', fontWeight: 700, color: 'var(--text)', whiteSpace: 'nowrap' }}>담당매니저</th>
                      <th style={{ padding: '7px 14px', textAlign: 'left', fontWeight: 700, color: 'var(--text)', whiteSpace: 'nowrap' }}>배분일자</th>
                    </tr>
                  </thead>
                  <tbody>
                    {searchPopupMatches.map((r, i) => (
                      <tr
                        key={i}
                        style={{ cursor: 'pointer', borderTop: '1px solid var(--border)' }}
                        onMouseDown={() => { clearTimeout(searchPopupTimerRef.current); setShowSearchPopup(false); openEdit(r); }}
                        onMouseEnter={(e) => e.currentTarget.style.background = 'var(--hover-bg)'}
                        onMouseLeave={(e) => e.currentTarget.style.background = ''}
                      >
                        <td style={{ padding: '8px 14px', color: 'var(--text)', fontWeight: 600 }}>{r.name}</td>
                        <td style={{ padding: '8px 14px', color: 'var(--text)' }}>{r.phone}</td>
                        <td style={{ padding: '8px 14px', color: 'var(--text)' }}>{r.manager || '-'}</td>
                        <td style={{ padding: '8px 14px', color: 'var(--muted)' }}>{formatDateDisplay(r.assignedDate) || '-'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
          {isAdmin && (
            <div className="filter-field">
              <label>담당매니저</label>
              <select value={managerFilter} onChange={(e) => setManagerFilter(e.target.value)}>
                <option value="">전체</option>
                {managers.map((m) => (
                  <option key={m} value={m}>{m}</option>
                ))}
              </select>
            </div>
          )}
          <div className="filter-field">
            <label>컨택여부</label>
            <select value={contactedFilter} onChange={(e) => setContactedFilter(e.target.value)}>
              <option value="">전체</option>
              <option value="Y">Y</option>
              <option value="N">N</option>
            </select>
          </div>
          <div className="filter-field">
            <label>사전예약여부</label>
            <select value={preRegFilter} onChange={(e) => setPreRegFilter(e.target.value)}>
              <option value="">전체</option>
              <option value="Y">Y</option>
              <option value="N">N</option>
            </select>
          </div>
          <div className="filter-field">
            <label>App 가입여부</label>
            <select value={appJoinFilter} onChange={(e) => setAppJoinFilter(e.target.value)}>
              <option value="">전체</option>
              <option value="Y">Y (가입)</option>
              <option value="N">N (미가입)</option>
            </select>
          </div>
          <div className="filter-field">
            <label>정렬기준</label>
            <select
              value={`${sortKey}:${sortDir}`}
              onChange={(e) => {
                const [k, d] = e.target.value.split(':');
                setSortKey(k);
                setSortDir(d);
              }}
            >
              <option value="assignedDate:desc">최신 등록순</option>
              <option value="name:asc">이름순 (가나다)</option>
            </select>
          </div>
          <div className="filter-actions">
            <button className="btn" onClick={resetFilters}>초기화</button>
            {isAdmin && <button className="btn" onClick={handleManualRefresh}>새로고침</button>}
            {isAdmin && <button className="btn btn-primary" onClick={exportCsv}>엑셀(CSV) 다운로드</button>}
            <button className="btn btn-primary" onClick={() => { setAddMsg(null); setAddingDealer(true); }}>
              딜러 추가
            </button>
            {isAdmin && (
              <button
                className="btn btn-primary"
                disabled={selectedPhones.size === 0}
                onClick={() => setBulkManagerModal(true)}
              >
                매니저 일괄 변경{selectedPhones.size > 0 ? ` (${selectedPhones.size}명)` : ''}
              </button>
            )}
          </div>
        </div>

        {bulkResult && (
          <div className={`modal-message ${bulkResult.type}`} style={{ margin: '8px 0' }}>
            {bulkResult.text}
            <button
              style={{ marginLeft: 12, background: 'none', border: 'none', cursor: 'pointer', fontWeight: 700 }}
              onClick={() => setBulkResult(null)}
            >
              ✕
            </button>
          </div>
        )}

        {loading ? (
          <div className="loading-state">불러오는 중...</div>
        ) : error ? (
          <div className="error-state">{error}</div>
        ) : (
          <>
            <div className="table-wrap">
              <table className="resizable-table">
                <colgroup>
                  {isAdmin && <col style={{ width: 40 }} />}
                  {visibleColumns.map((c) => (
                    <col key={c.key} style={{ width: colWidths[c.key] || DEFAULT_COL_WIDTH }} />
                  ))}
                </colgroup>
                <thead>
                  <tr>
                    {isAdmin && (
                      <th style={{ width: 40, textAlign: 'center', padding: '0 8px', position: 'sticky', left: 0, zIndex: 6, background: '#FAFBFD' }}>
                        <input
                          type="checkbox"
                          title="전체 선택 (현재 필터 기준)"
                          checked={filtered.length > 0 && filtered.every((r) => selectedPhones.has(r.phone))}
                          onChange={(e) => {
                            if (e.target.checked) {
                              setSelectedPhones(new Set(filtered.map((r) => r.phone)));
                            } else {
                              setSelectedPhones(new Set());
                            }
                          }}
                        />
                      </th>
                    )}
                    {visibleColumns.map((c) => {
                      const isFrozen = FROZEN_KEY_SET.has(c.key);
                      return (
                        <th
                          key={c.key}
                          onClick={() => c.key !== 'contactHistory' && toggleSort(c.key)}
                          style={{
                            cursor: c.key !== 'contactHistory' ? 'pointer' : 'default',
                            ...(isFrozen ? { position: 'sticky', left: frozenLefts[c.key], zIndex: 6, background: '#FAFBFD' } : {}),
                          }}
                        >
                          {c.label}
                          {sortKey === c.key ? (sortDir === 'asc' ? ' ▲' : ' ▼') : ''}
                          {c.key !== 'contactHistory' && (
                            <span
                              className="col-resize-handle"
                              onMouseDown={(e) => startColumnResize(e, c.key)}
                              onClick={(e) => e.stopPropagation()}
                            />
                          )}
                        </th>
                      );
                    })}
                  </tr>
                </thead>
                <tbody>
                  {paged.length === 0 ? (
                    <tr className="empty-row">
                      <td colSpan={visibleColumns.length + (isAdmin ? 1 : 0)}>검색 결과가 없습니다.</td>
                    </tr>
                  ) : (
                    paged.map((row) => (
                      <tr
                        key={row.phone + row.rowNumber}
                        onClick={() => openEdit(row)}
                        className={editing && editing.phone === row.phone ? 'row-selected' : ''}
                      >
                        {isAdmin && (
                          <td
                            className="frozen-cell"
                            style={{ textAlign: 'center', padding: '0 8px', position: 'sticky', left: 0, zIndex: 1 }}
                            onClick={(e) => e.stopPropagation()}
                          >
                            <input
                              type="checkbox"
                              checked={selectedPhones.has(row.phone)}
                              onChange={(e) => {
                                setSelectedPhones((prev) => {
                                  const next = new Set(prev);
                                  if (e.target.checked) next.add(row.phone);
                                  else next.delete(row.phone);
                                  return next;
                                });
                              }}
                            />
                          </td>
                        )}
                        {visibleColumns.map((c) => {
                          const isFrozen = FROZEN_KEY_SET.has(c.key);

                          if (c.key === 'contactHistory') {
                            const notes = parseContactHistory(row.contactHistory);
                            const latest = notes[0];
                            const latestText = latest ? latest.text : '';
                            const latestAuthor = latest ? latest.author : '';
                            const tooltipText = latest
                              ? `[${formatRelativeTime(latest.timestamp)} · ${latestAuthor || ''}]\n${latestText}`
                              : '';
                            const authorPrefix = latestAuthor ? `[${latestAuthor}] ` : '';
                            const combined = latestText ? authorPrefix + latestText : '';
                            const displayText = combined.length > 55 ? combined.slice(0, 55) + '…' : combined;
                            return (
                              <td key="contactHistory">
                                <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                                  <span className="history-snippet" title={tooltipText || undefined}>
                                    {displayText || <span style={{ color: '#C2C7CC' }}>-</span>}
                                  </span>
                                  <button
                                    className="btn-add-note"
                                    title="메모 추가"
                                    onClick={(e) => { e.stopPropagation(); openEdit(row, true); }}
                                  >+</button>
                                </div>
                              </td>
                            );
                          }

                          const val = row[c.key];
                          const isBadgeField = ['contacted', 'smsSent', 'priorityDealer', 'highEfficiency', 'contactSentiment'].includes(c.key);
                          const rawDisplay = DATE_DISPLAY_KEYS.includes(c.key) ? formatDateDisplay(val) : val;
                          const display = c.key === 'phone' ? maskPhone(val) : rawDisplay;
                          return (
                            <td
                              key={c.key}
                              title={rawDisplay || undefined}
                              className={isFrozen ? 'frozen-cell' : undefined}
                              style={isFrozen ? { position: 'sticky', left: frozenLefts[c.key], zIndex: 1 } : undefined}
                            >
                              {isBadgeField ? <Badge value={val} /> : (display || '-')}
                            </td>
                          );
                        })}
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>

            <div className="pagination">
              <span className="pagination-summary">
                전체 {sorted.length.toLocaleString()}명 중 {rangeStart}-{rangeEnd}
              </span>
              <button disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>‹</button>
              {pageNumbers.map((n, idx) =>
                n === '...' ? (
                  <span key={`ellipsis-${idx}`} className="page-ellipsis">…</span>
                ) : (
                  <button
                    key={n}
                    className={`page-num ${n === page ? 'active' : ''}`}
                    onClick={() => setPage(n)}
                  >
                    {n}
                  </button>
                )
              )}
              <button disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)}>›</button>
              <select value={pageSize} onChange={(e) => setPageSize(Number(e.target.value))}>
                {PAGE_SIZE_OPTIONS.map((n) => (
                  <option key={n} value={n}>{n}개씩</option>
                ))}
              </select>
              <span className="page-goto">
                <input
                  type="number"
                  min={1}
                  max={totalPages}
                  value={gotoInput}
                  onChange={(e) => setGotoInput(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && gotoPage()}
                  placeholder="페이지"
                />
                <button onClick={gotoPage}>이동</button>
              </span>
            </div>
          </>
        )}
      </div>

      {editing && (
        <DetailPanel
          key={editing.phone}
          row={editing}
          isAdmin={isAdmin}
          saving={saving}
          message={saveMsg}
          managerOptions={managerOptions}
          focusNote={focusNote}
          onClose={() => { setEditing(null); setFocusNote(false); }}
          onSave={handleSave}
          onDelete={handleDelete}
          onRowUpdated={handleRowFieldsUpdated}
        />
      )}

      {changingPassword && (
        <ChangePasswordModal onClose={() => setChangingPassword(false)} />
      )}

      {addingDealer && (
        <AddDealerModal
          isAdmin={isAdmin}
          name={name}
          saving={addSaving}
          message={addMsg}
          managerOptions={managerOptions}
          onClose={() => setAddingDealer(false)}
          onSave={handleAddDealer}
        />
      )}

      {bulkManagerModal && (
        <BulkManagerModal
          count={selectedPhones.size}
          managerOptions={managerOptions}
          saving={bulkSaving}
          onClose={() => setBulkManagerModal(false)}
          onConfirm={handleBulkManagerChange}
        />
      )}

      {showGlobalSearch && (
        <GlobalSearchModal onClose={() => setShowGlobalSearch(false)} />
      )}
    </div>
  );
}

// 우측 고정 상세 패널 — 딜러 클릭 시 표 옆에 고정 표시됩니다.
// 컨택 히스토리가 최상단에 위치해 전화 응대 중 바로 입력하기 편합니다.
function DetailPanel({ row, isAdmin, saving, message, managerOptions, focusNote, onClose, onSave, onDelete, onRowUpdated }) {
  const editableKeys = (isAdmin ? [...MANAGER_EDITABLE, ...ADMIN_ONLY_EDITABLE] : MANAGER_EDITABLE).filter(
    (k) => k !== 'contactHistory' && k !== 'firstContactDate'
  );
  const [form, setForm] = useState(() => {
    const init = {};
    for (const key of editableKeys) init[key] = row[key] || '';
    return init;
  });
  const [confirmDelete, setConfirmDelete] = useState(false);
  useEscapeKey(onClose);

  function update(key, value) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  const adminExtraKeys = MODAL_ADMIN_COLLAPSIBLE_EXTRA.filter((k) => k !== 'lastModifiedBy');

  return (
    <div className="detail-side-panel">
      {/* 헤더 */}
      <div className="detail-panel-header">
        <h2>{row.name}</h2>
        <button className="modal-close" onClick={onClose}>&times;</button>
      </div>

      {/* 컨택 히스토리 — 전화 응대용, 상단 고정 */}
      <div className="detail-panel-history">
        <ContactHistoryPanel row={row} focusNote={focusNote} onUpdated={onRowUpdated} />
      </div>

      {/* 편집 폼 — 스크롤 가능 */}
      <div className="detail-panel-body">
        {message && <div className={`modal-message ${message.type}`}>{message.text}</div>}

        <div className="modal-header-grid" style={{ gridTemplateColumns: 'repeat(2, 1fr)', gap: '10px 14px', marginBottom: 4 }}>
          <FieldInput fieldKey="group" value={form.group} onChange={update} />
          <FieldInput fieldKey="brand" value={form.brand} onChange={update} />
          <FieldInput fieldKey="branch" value={form.branch} onChange={update} />
          <FieldInput fieldKey="name" value={form.name} onChange={update} />
          <FieldInput fieldKey="phone" value={form.phone} onChange={update} />
          <FieldInput fieldKey="contacted" value={form.contacted} onChange={update} />
          <ReadOnlyField label="App가입일자" value={formatDateDisplay(row.appJoinDate)} />
          <ReadOnlyField label="누적 계약체결건수" value={row.totalContracts} />
          <ReadOnlyField label="직전 60일 계약건수" value={row.last60dContracts} />
          <ReadOnlyField label="직전 1년 본인 계약건수" value={row.last1yContracts} />
        </div>

        {isAdmin && (
          <CollapsibleSection title="관리자 전용 항목">
            {adminExtraKeys.map((key) => (
              <FieldInput key={key} fieldKey={key} value={form[key]} onChange={update} managerOptions={managerOptions} />
            ))}
            <ReadOnlyField label="수정자" value={row.lastModifiedBy} />
          </CollapsibleSection>
        )}

        <CollapsibleSection title="상세 정보">
          {MODAL_COMMON_COLLAPSIBLE.map((key) => {
            if (key === 'firstContactDate') {
              return (
                <ReadOnlyField
                  key={key}
                  label="최초컨택일자"
                  value={formatDateDisplay(row.firstContactDate)}
                  placeholder="컨택 히스토리 등록 시 자동 입력"
                />
              );
            }
            if (isAdmin || MANAGER_EDITABLE.includes(key)) {
              return <FieldInput key={key} fieldKey={key} value={form[key]} onChange={update} />;
            }
            return <ReadOnlyField key={key} label={FIELD_META[key].label} value={row[key]} />;
          })}
        </CollapsibleSection>
      </div>

      {/* 하단 액션 버튼 — 항상 노출 */}
      <div className="detail-panel-footer">
        {!confirmDelete ? (
          <>
            <button className="btn btn-danger" disabled={saving} onClick={() => setConfirmDelete(true)}>삭제</button>
            <button className="btn" onClick={onClose}>닫기</button>
            <button className="btn btn-primary" disabled={saving} onClick={() => onSave(form)}>
              {saving ? '저장 중...' : '저장'}
            </button>
          </>
        ) : (
          <>
            <span style={{ fontSize: 12, color: 'var(--red)', marginRight: 'auto', alignSelf: 'center' }}>
              '{row.name}' 딜러를 삭제하시겠습니까?
            </span>
            <button className="btn" onClick={() => setConfirmDelete(false)}>취소</button>
            <button className="btn btn-danger" disabled={saving} onClick={() => onDelete(row.phone)}>
              {saving ? '삭제 중...' : '확인'}
            </button>
          </>
        )}
      </div>
    </div>
  );
}

// 딜러 상세 화면에서 항상 보이는 읽기 전용 정보 한 칸을 그립니다.
function ReadOnlyField({ label, value, placeholder }) {
  return (
    <div className="modal-field modal-field-readonly">
      <label>{label}</label>
      <div className="readonly-value">{value || placeholder || '-'}</div>
    </div>
  );
}

// 기본은 접혀있고, 클릭하면 펼쳐지는 섹션입니다. "중요하지 않은 항목"을 평소엔 숨겨서
// 화면을 간단하게 보여주고, 필요할 때만 펼쳐서 보게 합니다.
function CollapsibleSection({ title, children, defaultOpen = false }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="collapsible-section">
      <button type="button" className="collapsible-toggle" onClick={() => setOpen((o) => !o)}>
        <span>{title}</span>
        <span className={`collapsible-chevron ${open ? 'open' : ''}`}>▾</span>
      </button>
      {open && <div className="collapsible-body">{children}</div>}
    </div>
  );
}

// 등록 시각 문자열("YYYY-MM-DD HH:mm:ss")을 "n분 전" 같은 상대 시간으로 바꿔줍니다.
// 일주일이 지난 항목은 상대 시간 대신 날짜만 보여줍니다.
function formatRelativeTime(timestamp) {
  if (!timestamp) return '';
  const ts = Date.parse(timestamp.replace(' ', 'T'));
  if (!ts) return timestamp;
  const diffMs = Date.now() - ts;
  const min = Math.floor(diffMs / 60000);
  if (min < 1) return '방금 전';
  if (min < 60) return `${min}분 전`;
  const hour = Math.floor(min / 60);
  if (hour < 24) return `${hour}시간 전`;
  const day = Math.floor(hour / 24);
  if (day < 7) return `${day}일 전`;
  return timestamp.slice(0, 10);
}

// 딜러를 클릭했을 때 옆에 표시되는 상담 메모 피드입니다. 메모 추가는 본문 저장 폼과 별도로
// 즉시 서버에 반영됩니다(같은 값을 두 곳에서 들고 있다가 저장 시점이 엇갈리는 걸 방지).
// focusNote=true면 패널이 열리자마자 입력창에 포커스 → 전화 응대 중 빠른 입력 지원.
function ContactHistoryPanel({ row, focusNote, onUpdated }) {
  const [contactHistory, setContactHistory] = useState(row.contactHistory || '');
  const [noteText, setNoteText] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const textareaRef = useRef(null);

  const notes = useMemo(() => parseContactHistory(contactHistory), [contactHistory]);

  useEffect(() => {
    if (focusNote && textareaRef.current) {
      textareaRef.current.focus();
    }
  }, [focusNote]);

  async function submitNote() {
    const trimmed = noteText.trim();
    if (!trimmed) return;
    setSaving(true);
    setError('');
    try {
      const res = await fetch('/api/members/add-note', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ phone: row.phone, text: trimmed }),
      });
      const data = await res.json();
      if (!res.ok) {
        setError(data.error || '메모 저장에 실패했습니다.');
        setSaving(false);
        return;
      }
      setContactHistory(data.updates.contactHistory);
      setNoteText('');
      if (onUpdated) onUpdated(data.updates);
    } catch (e) {
      setError('네트워크 오류가 발생했습니다.');
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="history-panel">
      <div className="history-section-title">컨택 히스토리</div>

      {/* 입력창을 피드 위에 배치 — 전화하면서 바로 적기 */}
      <div className="history-add-box">
        {error && <div className="modal-message err">{error}</div>}
        <textarea
          ref={textareaRef}
          value={noteText}
          maxLength={300}
          placeholder="상담 내용 입력 (Ctrl+Enter 저장)"
          onChange={(e) => setNoteText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
              e.preventDefault();
              submitNote();
            }
          }}
        />
        <div className="history-add-footer">
          <span className="history-char-count">{noteText.length}/300자</span>
          <button className="btn btn-primary" disabled={saving || !noteText.trim()} onClick={submitNote}>
            {saving ? '저장 중...' : '메모 추가'}
          </button>
        </div>
      </div>

      <div className="history-feed">
        {notes.length === 0 ? (
          <div className="history-empty">등록된 메모가 없습니다.</div>
        ) : (
          notes.map((n, i) => (
            <div className={`history-note ${getNoteClasses(n.text)}`} key={i}>
              <div className="history-note-meta">
                {n.author && <span className="history-note-author">{n.author}</span>}
                {n.timestamp && <span className="history-note-time">{formatRelativeTime(n.timestamp)}</span>}
              </div>
              <div className="history-note-text">{n.text}</div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

// 딜러 추가 모달도 상세 모달과 같은 3단계 순서(상시노출/접어두기)를 따릅니다. 다만 최초컨택일자는
// 등록 시점엔 항상 비어있어(컨택 히스토리를 적어야 자동으로 채워지므로) 입력칸으로 보여줄 필요가 없어 제외합니다.
function AddDealerModal({ isAdmin, name, saving, message, managerOptions, onClose, onSave }) {
  // 매니저는 다른 매니저에게 배분(manager)하거나 본인이 볼 수 없는 관리자 특이사항(adminNote)은 입력할 수 없습니다.
  const collapsibleKeys = MODAL_COMMON_COLLAPSIBLE.filter((k) => k !== 'firstContactDate');
  const baseKeys = ['group', 'brand', 'branch', 'name', 'phone', 'contacted', 'contactHistory', ...collapsibleKeys];
  const adminExtraKeys = MODAL_ADMIN_COLLAPSIBLE_EXTRA.filter((k) => k !== 'lastModifiedBy');
  const fieldKeys = isAdmin ? [...baseKeys, ...adminExtraKeys] : baseKeys;
  const [form, setForm] = useState(() => {
    const init = {};
    for (const key of fieldKeys) init[key] = '';
    return init;
  });
  const [validationError, setValidationError] = useState('');
  const [dupMatch, setDupMatch] = useState(null);
  const [checking, setChecking] = useState(false);
  useEscapeKey(onClose);

  function update(key, value) {
    setForm((prev) => ({ ...prev, [key]: value }));
    if (dupMatch) setDupMatch(null);
  }

  async function submit(force = false) {
    if (!form.name.trim() || !form.phone.trim()) {
      setValidationError('이름과 연락처는 필수 입력 항목입니다.');
      return;
    }
    setValidationError('');
    if (!force) {
      const normalizedPhone = form.phone.replace(/\D/g, '');
      setChecking(true);
      try {
        const res = await fetch(`/api/members/search?q=${encodeURIComponent(normalizedPhone)}`);
        const data = await res.json();
        const existing = (data.rows || []).find(
          (m) => m.phone && m.phone.replace(/\D/g, '') === normalizedPhone
        );
        if (existing) {
          setDupMatch(existing);
          setChecking(false);
          return;
        }
      } catch (e) {
        // 검색 실패 시 그냥 진행
      }
      setChecking(false);
    }
    setDupMatch(null);
    onSave(form);
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-card modal-card-wide" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header-fixed">
          <div className="modal-header">
            <div>
              <h2>딜러 추가</h2>
              <div className="sub">
                새로운 딜러 정보를 입력해주세요. (이름·연락처는 필수)
                {!isAdmin && ` 담당매니저는 본인(${name})으로 자동 등록됩니다.`}
              </div>
            </div>
            <button className="modal-close" onClick={onClose}>&times;</button>
          </div>

          {message && <div className={`modal-message ${message.type}`}>{message.text}</div>}
          {validationError && <div className="modal-message err">{validationError}</div>}
          {dupMatch && (
            <div className="modal-message warn" style={{ lineHeight: 1.8 }}>
              <strong>동일한 연락처로 이미 등록된 딜러가 있습니다.</strong><br />
              이름: <strong>{dupMatch.name}</strong> &nbsp;·&nbsp; 연락처: <strong>{dupMatch.phone}</strong><br />
              담당매니저: <strong>{dupMatch.manager || '-'}</strong> &nbsp;·&nbsp; 배분일자: <strong>{formatDateDisplay(dupMatch.assignedDate) || '-'}</strong><br />
              <div style={{ marginTop: 10, display: 'flex', gap: 8 }}>
                <button className="btn" onClick={() => setDupMatch(null)}>취소</button>
                <button className="btn btn-primary" onClick={() => submit(true)}>확인 후 등록</button>
              </div>
            </div>
          )}

          <div className="modal-header-grid">
            <FieldInput fieldKey="group" value={form.group} onChange={update} />
            <FieldInput fieldKey="brand" value={form.brand} onChange={update} />
            <FieldInput fieldKey="branch" value={form.branch} onChange={update} />
            <FieldInput fieldKey="name" value={form.name} onChange={update} />
            <FieldInput fieldKey="phone" value={form.phone} onChange={update} />
            <FieldInput fieldKey="contacted" value={form.contacted} onChange={update} />
          </div>
        </div>

        <div className="modal-split-body modal-split-body-single">
          <div className="modal-main-col">
            <FieldInput fieldKey="contactHistory" value={form.contactHistory} onChange={update} />

            {isAdmin && (
              <>
                <div className="modal-section-divider">관리자 전용 항목</div>
                {adminExtraKeys.map((key) => (
                  <FieldInput
                    key={key}
                    fieldKey={key}
                    value={form[key]}
                    onChange={update}
                    managerOptions={managerOptions}
                  />
                ))}
              </>
            )}

            <CollapsibleSection title="상세 정보">
              {collapsibleKeys.map((key) => (
                <FieldInput key={key} fieldKey={key} value={form[key]} onChange={update} />
              ))}
            </CollapsibleSection>

            <div className="modal-actions">
              <button className="btn" onClick={onClose}>닫기</button>
              <button className="btn btn-primary" disabled={saving || checking} onClick={submit}>
                {checking ? '확인 중...' : saving ? '추가 중...' : '추가'}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function BulkManagerModal({ count, managerOptions, saving, onClose, onConfirm }) {
  const [selectedManager, setSelectedManager] = useState('');
  useEscapeKey(onClose);

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-card" style={{ width: 400 }} onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <div>
            <h2>매니저 일괄 변경</h2>
            <div className="sub">선택한 {count.toLocaleString()}명의 담당매니저를 변경합니다.</div>
          </div>
          <button className="modal-close" onClick={onClose}>&times;</button>
        </div>

        <div style={{ padding: '16px 24px 0' }}>
          <div className="modal-field">
            <label>변경할 매니저</label>
            <select
              value={selectedManager}
              onChange={(e) => setSelectedManager(e.target.value)}
              autoFocus
            >
              <option value="">-- 매니저 선택 --</option>
              {(managerOptions || []).map((m) => (
                <option key={m} value={m}>{m}</option>
              ))}
            </select>
          </div>
        </div>

        <div className="modal-actions">
          <button type="button" className="btn" onClick={onClose} disabled={saving}>취소</button>
          <button
            type="button"
            className="btn btn-primary"
            disabled={!selectedManager || saving}
            onClick={() => onConfirm(selectedManager)}
          >
            {saving ? '변경 중...' : '변경하기'}
          </button>
        </div>
      </div>
    </div>
  );
}

function GlobalSearchModal({ onClose }) {
  const [name, setName] = useState('');
  const [phone, setPhone] = useState('');
  const [results, setResults] = useState(null); // null=미검색, []=결과없음
  const [searching, setSearching] = useState(false);
  useEscapeKey(onClose);

  const nameTrimmed = name.trim();
  const phoneDigits = phone.replace(/\D/g, '');

  // 검색 가능 여부 판단
  // - 이름 3자+ : 전화번호 없어도 검색 가능
  // - 전화번호 8자리+ : 이름 없어도 검색 가능
  // - 이름 2자 : 전화번호 8자리+ 도 함께 있어야 검색 가능
  const nameOnlyWarnNeeded = nameTrimmed.length === 2 && phoneDigits.length < 8;
  const canSearch =
    (nameTrimmed.length >= 3) ||
    (phoneDigits.length >= 8) ||
    (nameTrimmed.length >= 2 && phoneDigits.length >= 8);

  async function doSearch() {
    if (!canSearch) return;
    setSearching(true);
    try {
      const params = new URLSearchParams();
      if (nameTrimmed) params.set('name', nameTrimmed);
      if (phoneDigits) params.set('phone', phoneDigits);
      const res = await fetch(`/api/members/search?${params.toString()}`);
      const data = await res.json();
      setResults(data.rows || []);
    } catch {
      setResults([]);
    } finally {
      setSearching(false);
    }
  }

  function handleKeyDown(e) {
    if (e.key === 'Enter') doSearch();
  }

  function handleChange(setter) {
    return (e) => { setter(e.target.value); setResults(null); };
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-card" style={{ width: 560, maxHeight: '80vh', display: 'flex', flexDirection: 'column', overflow: 'hidden' }} onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <div>
            <h2>전체 딜러 검색</h2>
            <div className="sub">이름(3자+) 또는 연락처(8자리+) 입력 후 🔍 또는 Enter</div>
          </div>
          <button className="modal-close" onClick={onClose}>&times;</button>
        </div>
        <div style={{ padding: '16px 24px', flex: 1, overflowY: 'auto', overflowX: 'hidden' }}>
          <div style={{ display: 'flex', gap: 8, alignItems: 'stretch' }}>
            <input
              autoFocus
              value={name}
              onChange={handleChange(setName)}
              onKeyDown={handleKeyDown}
              placeholder="이름 (2자 이상)"
              style={{
                flex: '1 1 0', minWidth: 0, padding: '9px 13px', fontSize: 14,
                border: '1.5px solid var(--border)', borderRadius: 6,
                background: 'var(--input-bg)', color: 'var(--text)',
                boxSizing: 'border-box',
              }}
            />
            <input
              value={phone}
              onChange={handleChange(setPhone)}
              onKeyDown={handleKeyDown}
              placeholder="연락처 (8자리 이상)"
              style={{
                flex: '1 1 0', minWidth: 0, padding: '9px 13px', fontSize: 14,
                border: '1.5px solid var(--border)', borderRadius: 6,
                background: 'var(--input-bg)', color: 'var(--text)',
                boxSizing: 'border-box',
              }}
            />
            <button
              onClick={doSearch}
              disabled={searching || !canSearch}
              style={{
                flexShrink: 0, width: 44, height: 40, fontSize: 18,
                border: '1.5px solid var(--border)', borderRadius: 6,
                background: 'var(--btn-bg, #f1f3f5)', cursor: canSearch ? 'pointer' : 'default',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                opacity: canSearch ? 1 : 0.4,
              }}
              title="검색"
            >
              🔍
            </button>
          </div>
          {nameOnlyWarnNeeded && (
            <div style={{ marginTop: 8, fontSize: 12, color: '#e57c00', fontWeight: 500 }}>
              이름 2자 검색 시 연락처(8자리 이상)도 함께 입력해주세요.
            </div>
          )}
          {searching && (
            <div style={{ padding: '14px 0', color: 'var(--muted)', fontSize: 13 }}>검색 중...</div>
          )}
          {!searching && results !== null && results.length === 0 && (
            <div style={{ padding: '14px 0', color: 'var(--muted)', fontSize: 13 }}>검색 결과가 없습니다.</div>
          )}
          {results !== null && results.length > 0 && (
            <table style={{ width: '100%', fontSize: 13, borderCollapse: 'collapse', marginTop: 14, color: 'var(--text)' }}>
              <thead>
                <tr style={{ background: 'var(--table-head-bg)' }}>
                  <th style={{ padding: '7px 14px', textAlign: 'left', fontWeight: 700, color: 'var(--text)' }}>이름</th>
                  <th style={{ padding: '7px 14px', textAlign: 'left', fontWeight: 700, color: 'var(--text)' }}>연락처</th>
                  <th style={{ padding: '7px 14px', textAlign: 'left', fontWeight: 700, color: 'var(--text)' }}>담당매니저</th>
                  <th style={{ padding: '7px 14px', textAlign: 'left', fontWeight: 700, color: 'var(--text)' }}>배분일자</th>
                </tr>
              </thead>
              <tbody>
                {results.map((r, i) => (
                  <tr key={i} style={{ borderTop: '1px solid var(--border)' }}>
                    <td style={{ padding: '9px 14px', fontWeight: 600, color: 'var(--text)' }}>{r.name}</td>
                    <td style={{ padding: '9px 14px', color: 'var(--text)' }}>{r.phone}</td>
                    <td style={{ padding: '9px 14px', color: 'var(--text)' }}>
                      <span style={{
                        display: 'inline-block', padding: '2px 8px', borderRadius: 4, fontSize: 12,
                        background: 'var(--hover-bg)', fontWeight: 600,
                      }}>{r.manager || '-'}</span>
                    </td>
                    <td style={{ padding: '9px 14px', color: 'var(--muted)' }}>{formatDateDisplay(r.assignedDate) || '-'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
        <div className="modal-actions">
          <button className="btn" onClick={onClose}>닫기</button>
        </div>
      </div>
    </div>
  );
}

function FieldInput({ fieldKey, value, onChange, managerOptions }) {
  const meta = FIELD_META[fieldKey] || { label: fieldKey, type: 'text' };
  // 담당매니저는 계정관리에 등록된 매니저 이름만 드롭박스로 선택하게 합니다. (오타·미등록 이름 방지)
  if (fieldKey === 'manager' && Array.isArray(managerOptions)) {
    const options = value && !managerOptions.includes(value) ? [value, ...managerOptions] : managerOptions;
    return (
      <div className="modal-field">
        <label>{meta.label}{meta.required && <span className="required-mark"> *</span>}</label>
        <select value={value} onChange={(e) => onChange(fieldKey, e.target.value)}>
          <option value="">(미선택)</option>
          {options.map((opt) => (
            <option key={opt} value={opt}>{opt}</option>
          ))}
        </select>
      </div>
    );
  }
  return (
    <div className="modal-field">
      <label>{meta.label}{meta.required && <span className="required-mark"> *</span>}</label>
      {meta.type === 'select' ? (
        <select value={value} onChange={(e) => onChange(fieldKey, e.target.value)}>
          {meta.options.map((opt) => {
            const { value: optValue, label: optLabel } =
              typeof opt === 'string' ? { value: opt, label: opt === '' ? '(미입력)' : opt } : opt;
            return (
              <option key={optValue} value={optValue}>{optLabel}</option>
            );
          })}
        </select>
      ) : meta.type === 'textarea' ? (
        <textarea value={value} onChange={(e) => onChange(fieldKey, e.target.value)} />
      ) : meta.type === 'date' ? (
        <input
          type="date"
          value={formatDateDisplay(value)}
          onChange={(e) => onChange(fieldKey, e.target.value)}
        />
      ) : (
        <input
          type="text"
          value={value}
          placeholder={meta.placeholder}
          onChange={(e) => onChange(fieldKey, e.target.value)}
        />
      )}
    </div>
  );
}
