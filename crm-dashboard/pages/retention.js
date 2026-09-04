import { useEffect, useMemo, useRef, useState } from 'react';
import Link from 'next/link';
import cookie from 'cookie';
import { verifySession, COOKIE_NAME } from '../lib/auth';
import { REF_SHEETS, formatDateDisplay, parseContactHistory } from '../lib/sheetSchema';
import ChangePasswordModal from '../components/ChangePasswordModal';
import Announcement from '../components/Announcement';
import FaqWidget from '../components/FaqWidget';
import useEscapeKey from '../lib/useEscapeKey';
import { fetchAndCache } from '../lib/dataCache';

export async function getServerSideProps({ req }) {
  const cookies = cookie.parse(req.headers.cookie || '');
  const session = cookies[COOKIE_NAME] ? verifySession(cookies[COOKIE_NAME]) : null;
  if (!session) return { redirect: { destination: '/login', permanent: false } };
  return { props: { role: session.role, name: session.name } };
}

// 날짜 문자열을 Date 객체로 파싱 (여러 포맷 지원)
function parseDate(str) {
  if (!str) return null;
  const s = str.toString().trim();
  const m = s.match(/(\d{4})\D+(\d{1,2})\D+(\d{1,2})/);
  if (!m) return null;
  const [, y, mo, d] = m;
  return new Date(`${y}-${mo.padStart(2, '0')}-${d.padStart(2, '0')}`);
}

function daysSince(str) {
  const d = parseDate(str);
  if (!d || isNaN(d.getTime())) return null;
  return Math.floor((Date.now() - d.getTime()) / 86400000);
}

function calcRetention(row) {
  const total = parseInt(row.totalContracts, 10) || 0;
  const last60 = parseInt(row.last60dContracts, 10) || 0;
  const joinDateStr = row.appJoinDate || row.registeredAt || '';
  const age = daysSince(joinDateStr);
  const isAssocMember = !!row.isAssocMember;
  const type1 = total === 1 && last60 === 0;
  const type2 = total >= 2 && last60 === 0;
  const type3 = total === 0 && age !== null && age >= 60;
  const type4 = isAssocMember && total >= 1 && last60 === 0;
  return { type1, type2, type3, type4, isTarget: type1 || type2 || type3 || type4 };
}

const TYPE_LABELS = { type1: '유형1', type2: '유형2', type3: '유형3', type4: '유형4' };
const TYPE_DESCS = {
  type1: '누적계약 1건, 직전60일 0건',
  type2: '누적계약 2건↑, 직전60일 0건',
  type3: '계약 0건 + 가입 60일↑',
  type4: '준회원, 누적1건↑, 직전60일 0건',
};
const TYPE_TAG_STYLE = {
  type1: { background: '#FEF9C3', color: '#854D0E', border: '1px solid #FDE68A' },
  type2: { background: '#FEE2E2', color: '#991B1B', border: '1px solid #FCA5A5' },
  type3: { background: '#DCFCE7', color: '#166534', border: '1px solid #86EFAC' },
  type4: { background: '#DBEAFE', color: '#1E40AF', border: '1px solid #93C5FD' },
};

const RETENTION_KEY = 'retention-v1';

function formatTimestamp(timestamp) {
  if (!timestamp) return '';
  const d = new Date(timestamp.replace(' ', 'T'));
  if (isNaN(d.getTime())) return timestamp;
  const y = d.getFullYear();
  const mo = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  const h = String(d.getHours()).padStart(2, '0');
  const m = String(d.getMinutes()).padStart(2, '0');
  return `${y}.${mo}.${day} ${h}:${m}`;
}

export default function RetentionPage({ role, name }) {
  const isAdmin = role === '관리자';

  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [typeFilter, setTypeFilter] = useState('all');
  const [search, setSearch] = useState('');
  const [changingPassword, setChangingPassword] = useState(false);
  const [selectedRow, setSelectedRow] = useState(null);
  const [focusNote, setFocusNote] = useState(false);
  const topbarRef = useRef(null);

  useEffect(() => {
    const el = topbarRef.current;
    if (!el) return;
    const update = () => document.documentElement.style.setProperty('--topbar-h', el.offsetHeight + 'px');
    update();
    const obs = new ResizeObserver(update);
    obs.observe(el);
    return () => obs.disconnect();
  }, []);

  useEffect(() => {
    (async () => {
      setLoading(true);
      try {
        const data = await fetchAndCache(RETENTION_KEY, '/api/retention');
        if (data) setRows(data.rows);
      } catch (e) {
        setError(e.message);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  async function handleLogout() {
    await fetch('/api/auth/logout', { method: 'POST' });
    window.location.href = '/login';
  }

  function handleRowNoteUpdated(phone, updates) {
    setRows((prev) => prev.map((r) => r.phone === phone ? { ...r, ...updates } : r));
    setSelectedRow((prev) => prev && prev.phone === phone ? { ...prev, ...updates } : prev);
  }

  function openPanel(row, withFocus = false) {
    setSelectedRow(row);
    setFocusNote(withFocus);
  }

  const enriched = useMemo(() =>
    rows.map((r) => ({ ...r, _ret: calcRetention(r) })),
    [rows]
  );

  const targets = useMemo(() => {
    let list = enriched.filter((r) => r._ret.isTarget);
    if (typeFilter !== 'all') list = list.filter((r) => r._ret[typeFilter]);
    if (search.trim()) {
      const q = search.trim().toLowerCase();
      list = list.filter((r) =>
        (r.name || '').toLowerCase().includes(q) ||
        (r.phone || '').includes(q) ||
        (r.manager || '').toLowerCase().includes(q) ||
        (r.branch || '').toLowerCase().includes(q)
      );
    }
    return list;
  }, [enriched, typeFilter, search]);

  const counts = useMemo(() => {
    const base = enriched.filter((r) => r._ret.isTarget);
    return {
      all: base.length,
      type1: base.filter((r) => r._ret.type1).length,
      type2: base.filter((r) => r._ret.type2).length,
      type3: base.filter((r) => r._ret.type3).length,
      type4: base.filter((r) => r._ret.type4).length,
    };
  }, [enriched]);

  return (
    <div className="app-shell">
      <FaqWidget isAdmin={isAdmin} />
      <div className="topbar" ref={topbarRef}>
        <div className="topbar-main">
          <div className="topbar-left">
            <span className="topbar-title">My Dealer</span>
            <span className="topbar-badge">{role}</span>
            <nav className="topbar-nav">
              <Link className="topbar-nav-link" href="/dashboard">회원관리</Link>
              {REF_SHEETS.filter((s) => !s.hiddenFromNav).map((s) => (
                <Link key={s.key} className="topbar-nav-link" href={`/sheet/${s.key}`}>{s.label}</Link>
              ))}
              <Link className="topbar-nav-link active" href="/retention">리텐션대상자</Link>
              {!isAdmin && <Link className="topbar-nav-link" href="/performance">실적현황</Link>}
              {isAdmin && <Link className="topbar-nav-link" href="/accounts">계정관리</Link>}
            </nav>
          </div>
          <div className="topbar-right">
            <span className="topbar-user">{name}님</span>
            <button className="logout-btn" onClick={() => setChangingPassword(true)}>비밀번호 변경</button>
            <button className="logout-btn" onClick={handleLogout}>로그아웃</button>
          </div>
        </div>
        <Announcement isAdmin={isAdmin} />
      </div>

      <div className={`page-body${selectedRow ? ' panel-open' : ''}`}>
        <div className="page-heading">
          <div>
            <h1>리텐션 대상자</h1>
            <div className="count">총 {counts.all}명</div>
          </div>
        </div>

        <RetentionNotice isAdmin={isAdmin} />

        {/* 유형 설명 카드 */}
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', marginBottom: 16 }}>
          {(['type1', 'type2', 'type3', 'type4']).map((t) => (
            <div key={t} style={{
              padding: '8px 14px', borderRadius: 8, fontSize: 12, lineHeight: 1.5,
              border: TYPE_TAG_STYLE[t].border,
              background: TYPE_TAG_STYLE[t].background,
              color: TYPE_TAG_STYLE[t].color,
            }}>
              <strong>{TYPE_LABELS[t]}</strong>: {TYPE_DESCS[t]}
            </div>
          ))}
        </div>

        {/* 필터 바 */}
        <div className="filters-card" style={{ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
          <div style={{ display: 'flex', gap: 6 }}>
            {[['all', '전체'], ['type1', '유형1'], ['type2', '유형2'], ['type3', '유형3'], ['type4', '유형4']].map(([val, label]) => (
              <button
                key={val}
                onClick={() => setTypeFilter(val)}
                style={{
                  padding: '5px 14px', borderRadius: 20, fontSize: 13, fontWeight: 600,
                  cursor: 'pointer', transition: 'all .12s',
                  border: typeFilter === val ? '2px solid var(--blue-dk)' : '1.5px solid var(--border)',
                  background: typeFilter === val ? 'var(--blue-dk)' : 'var(--white)',
                  color: typeFilter === val ? '#fff' : 'var(--text)',
                }}
              >
                {label}
                <span style={{ marginLeft: 5, opacity: .75, fontWeight: 400 }}>
                  {val === 'all' ? counts.all : counts[val]}
                </span>
              </button>
            ))}
          </div>
          <input
            style={{ flex: 1, minWidth: 180, maxWidth: 280 }}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="이름 / 연락처 / 매니저 / 지점"
          />
        </div>

        {loading && <div className="loading">불러오는 중...</div>}
        {error && <div className="error-msg">{error}</div>}

        {!loading && !error && (
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th style={{ minWidth: 72 }}>이름</th>
                  <th style={{ minWidth: 110 }}>연락처</th>
                  <th style={{ minWidth: 80 }}>담당매니저</th>
                  <th style={{ minWidth: 90 }}>그룹</th>
                  <th style={{ minWidth: 80 }}>브랜드</th>
                  <th style={{ minWidth: 100 }}>지점/대리점</th>
                  <th style={{ minWidth: 90 }}>App가입일</th>
                  <th style={{ minWidth: 60, textAlign: 'center' }}>누적계약</th>
                  <th style={{ minWidth: 60, textAlign: 'center' }}>직전60일</th>
                  <th style={{ minWidth: 52, textAlign: 'center' }}>유형1</th>
                  <th style={{ minWidth: 52, textAlign: 'center' }}>유형2</th>
                  <th style={{ minWidth: 52, textAlign: 'center' }}>유형3</th>
                  <th style={{ minWidth: 52, textAlign: 'center' }}>유형4</th>
                  <th style={{ minWidth: 120 }}>최근 메모</th>
                </tr>
              </thead>
              <tbody>
                {targets.length === 0 && (
                  <tr>
                    <td colSpan={14} style={{ textAlign: 'center', padding: '40px 0', color: 'var(--muted)' }}>
                      해당하는 리텐션 대상자가 없습니다.
                    </td>
                  </tr>
                )}
                {targets.map((row, i) => {
                  const ret = row._ret;
                  const notes = parseContactHistory(row.contactHistory);
                  const latest = notes[0];
                  const latestText = latest ? latest.text : '';
                  const latestAuthor = latest ? latest.author : '';
                  const combined = latestText ? (latestAuthor ? `[${latestAuthor}] ` : '') + latestText : '';
                  const displayText = combined.length > 40 ? combined.slice(0, 40) + '…' : combined;
                  const isSelected = selectedRow && selectedRow.phone === row.phone;
                  return (
                    <tr
                      key={row.phone || i}
                      onClick={() => openPanel(row)}
                      className={isSelected ? 'row-selected' : ''}
                      style={{ cursor: 'pointer' }}
                    >
                      <td>{row.name || '-'}</td>
                      <td style={{ fontFamily: 'monospace', fontSize: 12 }}>{row.phone || '-'}</td>
                      <td>{row.manager || '-'}</td>
                      <td>{row.group || '-'}</td>
                      <td>{row.brand || '-'}</td>
                      <td>{row.branch || '-'}</td>
                      <td style={{ fontSize: 12 }}>{formatDateDisplay(row.appJoinDate) || '-'}</td>
                      <td style={{ textAlign: 'center' }}>{row.totalContracts || '0'}</td>
                      <td style={{ textAlign: 'center' }}>{row.last60dContracts || '0'}</td>
                      <TypeCell active={ret.type1} type="type1" />
                      <TypeCell active={ret.type2} type="type2" />
                      <TypeCell active={ret.type3} type="type3" />
                      <TypeCell active={ret.type4} type="type4" />
                      <td>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                          <span className="history-snippet" style={{ fontSize: 12, color: displayText ? undefined : 'var(--muted)' }}>
                            {displayText || '-'}
                          </span>
                          <button
                            className="btn-add-note"
                            title="메모 추가"
                            onClick={(e) => { e.stopPropagation(); openPanel(row, true); }}
                          >+</button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {selectedRow && (
        <RetentionPanel
          row={selectedRow}
          isAdmin={isAdmin}
          focusNote={focusNote}
          onClose={() => setSelectedRow(null)}
          onNoteUpdated={(updates) => handleRowNoteUpdated(selectedRow.phone, updates)}
        />
      )}

      {changingPassword && (
        <ChangePasswordModal onClose={() => setChangingPassword(false)} />
      )}
    </div>
  );
}

function RetentionPanel({ row, isAdmin, focusNote, onClose, onNoteUpdated }) {
  useEscapeKey(onClose);
  const ret = calcRetention(row);
  const activeTypes = (['type1', 'type2', 'type3', 'type4']).filter((t) => ret[t]);

  return (
    <div className="detail-side-panel">
      <div className="detail-panel-header">
        <div>
          <h2>{row.name || '-'}</h2>
          <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', marginTop: 4 }}>
            {activeTypes.map((t) => (
              <span key={t} style={{
                display: 'inline-block', padding: '1px 8px', borderRadius: 10, fontSize: 11, fontWeight: 700,
                border: TYPE_TAG_STYLE[t].border,
                background: TYPE_TAG_STYLE[t].background,
                color: TYPE_TAG_STYLE[t].color,
              }}>{TYPE_LABELS[t]}</span>
            ))}
          </div>
        </div>
        <button className="modal-close" onClick={onClose}>&times;</button>
      </div>

      {/* 기본 정보 */}
      <div style={{ padding: '10px 16px', borderBottom: '1px solid var(--border)', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '6px 12px', fontSize: 13 }}>
        <InfoRow label="연락처" value={row.phone} mono />
        <InfoRow label="담당매니저" value={row.manager} />
        <InfoRow label="그룹" value={row.group} />
        <InfoRow label="브랜드" value={row.brand} />
        <InfoRow label="지점/대리점" value={row.branch} />
        <InfoRow label="App가입일" value={formatDateDisplay(row.appJoinDate)} />
        <InfoRow label="누적계약" value={row.totalContracts || '0'} />
        <InfoRow label="직전60일" value={row.last60dContracts || '0'} />
      </div>

      {/* 관리자 메모 */}
      <AdminNoteSection
        row={row}
        isAdmin={isAdmin}
        onUpdated={onNoteUpdated}
      />

      {/* 컨택 히스토리 */}
      <div className="detail-panel-history" style={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
        <ContactHistoryPanel
          row={row}
          focusNote={focusNote}
          onUpdated={onNoteUpdated}
        />
      </div>
    </div>
  );
}

function AdminNoteSection({ row, isAdmin, onUpdated }) {
  const [value, setValue] = useState(row.adminNote || '');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    setValue(row.adminNote || '');
    setError('');
    setSaved(false);
  }, [row.phone]);

  if (!isAdmin && !row.adminNote) return null;

  async function handleSave() {
    setSaving(true);
    setError('');
    setSaved(false);
    try {
      const res = await fetch('/api/members/update', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ phone: row.phone, updates: { adminNote: value } }),
      });
      const data = await res.json();
      if (!res.ok) { setError(data.error || '저장 실패'); setSaving(false); return; }
      setSaved(true);
      if (onUpdated) onUpdated({ adminNote: value });
      setTimeout(() => setSaved(false), 2000);
    } catch (e) {
      setError('네트워크 오류가 발생했습니다.');
    } finally {
      setSaving(false);
    }
  }

  return (
    <div style={{
      margin: '0 16px 0', padding: '10px 12px',
      background: isAdmin ? '#FFFBEB' : '#FFFBEB',
      border: '1px solid #FDE68A', borderRadius: 8,
      marginTop: 10, marginBottom: 2,
    }}>
      <div style={{ fontSize: 11, fontWeight: 700, color: '#92400E', marginBottom: 6 }}>📌 관리자 메모</div>
      {isAdmin ? (
        <>
          <textarea
            value={value}
            onChange={(e) => { setValue(e.target.value); setSaved(false); }}
            placeholder="날짜 기준 안내나 특이사항 입력 (매니저에게 노출됩니다)"
            maxLength={500}
            style={{
              width: '100%', minHeight: 64, resize: 'vertical', fontSize: 13,
              border: '1px solid #FDE68A', borderRadius: 6, padding: '6px 8px',
              background: '#FFFEF7', boxSizing: 'border-box',
            }}
          />
          {error && <div style={{ color: 'var(--red)', fontSize: 12, marginTop: 4 }}>{error}</div>}
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 6, marginTop: 6 }}>
            <span style={{ fontSize: 12, color: saved ? '#16A34A' : 'var(--muted)', alignSelf: 'center' }}>
              {saved ? '저장됨' : `${value.length}/500자`}
            </span>
            <button className="btn btn-primary" disabled={saving} onClick={handleSave} style={{ fontSize: 12, padding: '3px 12px' }}>
              {saving ? '저장 중...' : '저장'}
            </button>
          </div>
        </>
      ) : (
        <div style={{ fontSize: 13, whiteSpace: 'pre-wrap', color: '#78350F', lineHeight: 1.6 }}>
          {row.adminNote}
        </div>
      )}
    </div>
  );
}

function InfoRow({ label, value, mono }) {
  return (
    <div>
      <span style={{ color: 'var(--muted)', fontSize: 11 }}>{label}</span>
      <div style={{ fontFamily: mono ? 'monospace' : undefined, fontSize: 13 }}>{value || '-'}</div>
    </div>
  );
}

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

  // 외부에서 row가 바뀌면 (다른 row 선택 시) 히스토리 동기화
  useEffect(() => {
    setContactHistory(row.contactHistory || '');
    setNoteText('');
    setError('');
  }, [row.phone]);

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
    <div className="history-panel" style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <div className="history-section-title">컨택 히스토리</div>
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
            <div className="history-note" key={i}>
              <div className="history-note-meta">
                {n.author && <span className="history-note-author">{n.author}</span>}
                <span className="history-note-time">
                  {n.timestamp ? formatTimestamp(n.timestamp) : '시간 미기록'}
                </span>
              </div>
              <div className="history-note-text">{n.text}</div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

function RetentionNotice({ isAdmin }) {
  const [text, setText] = useState('');
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;
    fetch('/api/retention-notice')
      .then((r) => r.json())
      .then((d) => { if (!cancelled && d.ok) setText(d.text || ''); })
      .catch(() => {});
    return () => { cancelled = true; };
  }, []);

  function startEdit() { setDraft(text); setError(''); setEditing(true); }
  function cancelEdit() { setEditing(false); setError(''); }

  async function save() {
    setSaving(true); setError('');
    try {
      const res = await fetch('/api/retention-notice', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: draft.trim() }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || '저장 실패');
      setText(data.text || '');
      setEditing(false);
    } catch (e) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  }

  if (!text && !isAdmin) return null;

  if (editing) {
    return (
      <div style={{
        background: '#EFF6FF', border: '1px solid #93C5FD', borderRadius: 10,
        padding: '12px 16px', marginBottom: 16,
      }}>
        <div style={{ fontSize: 12, fontWeight: 700, color: '#1E40AF', marginBottom: 8 }}>📌 리텐션 공지 편집</div>
        <textarea
          autoFocus
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          maxLength={300}
          placeholder="매니저에게 전달할 공지 내용을 입력하세요 (300자 이내)"
          style={{
            width: '100%', minHeight: 80, resize: 'vertical', fontSize: 13,
            border: '1px solid #93C5FD', borderRadius: 6, padding: '8px 10px',
            background: '#F8FBFF', boxSizing: 'border-box',
          }}
        />
        {error && <div style={{ color: 'var(--red)', fontSize: 12, marginTop: 4 }}>{error}</div>}
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 8, alignItems: 'center' }}>
          <span style={{ fontSize: 12, color: 'var(--muted)' }}>{draft.length}/300자</span>
          <button className="btn" onClick={cancelEdit} disabled={saving}>취소</button>
          <button className="btn btn-primary" onClick={save} disabled={saving}>
            {saving ? '저장 중...' : '저장'}
          </button>
        </div>
      </div>
    );
  }

  return (
    <div
      style={{
        background: '#EFF6FF', border: '1px solid #93C5FD', borderRadius: 10,
        padding: '12px 16px', marginBottom: 16,
        cursor: isAdmin ? 'pointer' : 'default',
        display: 'flex', gap: 10, alignItems: 'flex-start',
      }}
      onClick={isAdmin ? startEdit : undefined}
      title={isAdmin ? '클릭하여 편집' : undefined}
    >
      <span style={{ fontSize: 16, flexShrink: 0 }}>📌</span>
      <span style={{ fontSize: 13, color: '#1E40AF', whiteSpace: 'pre-wrap', lineHeight: 1.6, flex: 1 }}>
        {text || (isAdmin ? '공지를 입력하려면 클릭하세요' : '')}
      </span>
      {isAdmin && <span style={{ fontSize: 11, color: '#93C5FD', flexShrink: 0, alignSelf: 'center' }}>편집</span>}
    </div>
  );
}

function TypeCell({ active, type }) {
  if (!active) {
    return <td style={{ textAlign: 'center', color: 'var(--muted)', fontSize: 12 }}>N</td>;
  }
  return (
    <td style={{ textAlign: 'center' }}>
      <span style={{
        display: 'inline-block', padding: '1px 8px', borderRadius: 10, fontSize: 11, fontWeight: 700,
        border: TYPE_TAG_STYLE[type].border,
        background: TYPE_TAG_STYLE[type].background,
        color: TYPE_TAG_STYLE[type].color,
      }}>Y</span>
    </td>
  );
}
