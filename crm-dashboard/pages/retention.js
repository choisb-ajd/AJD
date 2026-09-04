import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import cookie from 'cookie';
import { verifySession, COOKIE_NAME } from '../lib/auth';
import { REF_SHEETS, formatDateDisplay } from '../lib/sheetSchema';
import ChangePasswordModal from '../components/ChangePasswordModal';
import Announcement from '../components/Announcement';
import FaqWidget from '../components/FaqWidget';
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

// 리텐션 유형 판단
// 유형4의 '준회원' 기준: group 또는 brand 필드에 '준회원' 포함 여부.
// 실제 저장 필드가 다르면 아래 isAssocMember 로직을 수정하세요.
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

const TYPE_LABELS = {
  type1: '유형1',
  type2: '유형2',
  type3: '유형3',
  type4: '유형4',
};
const TYPE_DESCS = {
  type1: '누적계약 1건, 직전60일 0건',
  type2: '누적계약 2건↑, 직전60일 0건',
  type3: '계약 0건 + 가입 60일↑',
  type4: '준회원, 누적1건↑, 직전60일 0건',
};
const TYPE_COLORS = {
  type1: { bg: '#FEF9C3', text: '#854D0E', border: '#FDE68A' },
  type2: '#FEF2F2',
  type3: '#F0FDF4',
  type4: '#EFF6FF',
};
const TYPE_TAG_STYLE = {
  type1: { background: '#FEF9C3', color: '#854D0E', border: '1px solid #FDE68A' },
  type2: { background: '#FEE2E2', color: '#991B1B', border: '1px solid #FCA5A5' },
  type3: { background: '#DCFCE7', color: '#166534', border: '1px solid #86EFAC' },
  type4: { background: '#DBEAFE', color: '#1E40AF', border: '1px solid #93C5FD' },
};

const RETENTION_KEY = 'retention-v1';

export default function RetentionPage({ role, name }) {
  const isAdmin = role === '관리자';

  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [typeFilter, setTypeFilter] = useState('all');
  const [search, setSearch] = useState('');
  const [changingPassword, setChangingPassword] = useState(false);

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

  // 리텐션 계산 결과를 row에 붙임
  const enriched = useMemo(() =>
    rows.map((r) => ({ ...r, _ret: calcRetention(r) })),
    [rows]
  );

  // 대상자 필터링
  const targets = useMemo(() => {
    let list = enriched.filter((r) => r._ret.isTarget);

    if (typeFilter !== 'all') {
      list = list.filter((r) => r._ret[typeFilter]);
    }

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

  // 유형별 카운트
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
      <div className="topbar">
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

      <div className="page-body">
        <div className="page-heading">
          <div>
            <h1>리텐션 대상자</h1>
            <div className="count">총 {counts.all}명</div>
          </div>
        </div>

        {/* 유형 설명 카드 */}
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', marginBottom: 16 }}>
          {(['type1', 'type2', 'type3', 'type4']).map((t) => (
            <div key={t} style={{
              padding: '8px 14px', borderRadius: 8, fontSize: 12, lineHeight: 1.5,
              border: `1px solid ${TYPE_TAG_STYLE[t].border}`,
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
                </tr>
              </thead>
              <tbody>
                {targets.length === 0 && (
                  <tr>
                    <td colSpan={13} style={{ textAlign: 'center', padding: '40px 0', color: 'var(--muted)' }}>
                      해당하는 리텐션 대상자가 없습니다.
                    </td>
                  </tr>
                )}
                {targets.map((row, i) => {
                  const ret = row._ret;
                  return (
                    <tr key={row.phone || i}>
                      <td>{row.name || '-'}</td>
                      <td style={{ fontFamily: 'monospace', fontSize: 12 }}>
                        {row.phone || '-'}
                      </td>
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
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {changingPassword && (
        <ChangePasswordModal onClose={() => setChangingPassword(false)} />
      )}
    </div>
  );
}

function TypeCell({ active, type }) {
  if (!active) {
    return (
      <td style={{ textAlign: 'center', color: 'var(--muted)', fontSize: 12 }}>N</td>
    );
  }
  return (
    <td style={{ textAlign: 'center' }}>
      <span style={{
        display: 'inline-block',
        padding: '1px 8px',
        borderRadius: 10,
        fontSize: 11,
        fontWeight: 700,
        border: TYPE_TAG_STYLE[type].border,
        background: TYPE_TAG_STYLE[type].background,
        color: TYPE_TAG_STYLE[type].color,
      }}>Y</span>
    </td>
  );
}
