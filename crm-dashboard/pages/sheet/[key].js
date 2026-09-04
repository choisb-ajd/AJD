import { useEffect, useRef, useState } from 'react';
import { useRouter } from 'next/router';
import Link from 'next/link';
import cookie from 'cookie';
import { verifySession, COOKIE_NAME } from '../../lib/auth';
import { REF_SHEETS } from '../../lib/sheetSchema';
import ChangePasswordModal from '../../components/ChangePasswordModal';
import Announcement from '../../components/Announcement';
import FaqWidget from '../../components/FaqWidget';
import FaqNotepad from '../../components/FaqNotepad';
import LmsTemplates from '../../components/LmsTemplates';
import LeaseRegistry from '../../components/LeaseRegistry';
import LinkHub from '../../components/LinkHub';
import RenewalRegistry from '../../components/RenewalRegistry';

export async function getServerSideProps({ req, params }) {
  const cookies = cookie.parse(req.headers.cookie || '');
  const session = cookies[COOKIE_NAME] ? verifySession(cookies[COOKIE_NAME]) : null;
  if (!session) {
    return { redirect: { destination: '/login', permanent: false } };
  }
  const config = REF_SHEETS.find((s) => s.key === params.key);
  if (!config) {
    return { notFound: true };
  }
  const isNotepad = !!config.notepad;
  const isTemplates = !!config.templates;
  const isRegistry = !!config.registry;
  const isLinkHub = !!config.linkHub;
  const isRenewalTable = !!config.renewalTable;
  const sheetUrl =
    !isNotepad && !isTemplates && !isRegistry && !isLinkHub && !isRenewalTable && session.role === '관리자' && process.env.ADMIN_SPREADSHEET_ID
      ? `https://docs.google.com/spreadsheets/d/${process.env.ADMIN_SPREADSHEET_ID}/edit#gid=${config.gid}`
      : null;
  return {
    props: {
      role: session.role,
      name: session.name,
      sheetKey: config.key,
      sheetLabel: config.label,
      sheetUrl,
      isNotepad,
      isTemplates,
      isRegistry,
      isLinkHub,
      isRenewalTable,
    },
  };
}

export default function RefSheetPage({ role, name, sheetKey, sheetLabel, sheetUrl, isNotepad, isTemplates, isRegistry, isLinkHub, isRenewalTable }) {
  const router = useRouter();
  const isAdmin = role === '관리자';
  const topbarRef = useRef(null);
  const [renewalPanelOpen, setRenewalPanelOpen] = useState(false);
  const [grid, setGrid] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [changingPassword, setChangingPassword] = useState(false);

  useEffect(() => {
    const el = topbarRef.current;
    if (!el) return;
    const update = () => document.documentElement.style.setProperty('--topbar-h', el.offsetHeight + 'px');
    update();
    const obs = new ResizeObserver(update);
    obs.observe(el);
    return () => obs.disconnect();
  }, []);
  const [editingCell, setEditingCell] = useState(null); // { r, c }
  const [editValue, setEditValue] = useState('');
  const [savingCell, setSavingCell] = useState(false);
  const [cellError, setCellError] = useState('');

  async function fetchGrid() {
    setLoading(true);
    setError('');
    try {
      const res = await fetch(`/api/refsheet/${sheetKey}`);
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || '시트를 불러오지 못했습니다.');
      setGrid(data);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (isNotepad || isTemplates || isRegistry || isLinkHub || isRenewalTable) {
      setLoading(false);
      return;
    }
    fetchGrid();
    setEditingCell(null);
    setCellError('');
  }, [sheetKey, isNotepad, isTemplates, isRegistry, isLinkHub, isRenewalTable]);

  async function handleLogout() {
    await fetch('/api/auth/logout', { method: 'POST' });
    router.push('/login');
  }

  function startEdit(r, c, currentValue) {
    if (!isAdmin) return;
    setCellError('');
    setEditingCell({ r, c });
    setEditValue(currentValue);
  }

  async function commitEdit() {
    if (!editingCell) return;
    const { r, c } = editingCell;
    const prevValue = grid.rows[r][c];
    setEditingCell(null);
    if (editValue === prevValue) return;

    setSavingCell(true);
    setGrid((g) => {
      const rows = g.rows.map((row) => row.slice());
      rows[r][c] = editValue;
      return { ...g, rows };
    });

    try {
      const res = await fetch(`/api/refsheet/${sheetKey}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ rowIndex: r, colIndex: c, value: editValue }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || '저장하지 못했습니다.');
    } catch (e) {
      setGrid((g) => {
        const rows = g.rows.map((row) => row.slice());
        rows[r][c] = prevValue;
        return { ...g, rows };
      });
      setCellError(e.message);
    } finally {
      setSavingCell(false);
    }
  }

  function handleEditKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      e.target.blur();
    } else if (e.key === 'Escape') {
      setEditingCell(null);
    }
  }

  return (
    <div className="app-shell">
      {!isNotepad && <FaqWidget isAdmin={isAdmin} />}
      <div className="topbar" ref={topbarRef}>
        <div className="topbar-main">
          <div className="topbar-left">
            <span className="topbar-title">My Dealer</span>
            <span className="topbar-badge">{role}</span>
            <nav className="topbar-nav">
              <Link className="topbar-nav-link" href="/dashboard">회원관리</Link>
              {REF_SHEETS.filter((s) => !s.hiddenFromNav).map((s) => (
                <Link
                  key={s.key}
                  className={`topbar-nav-link${s.key === sheetKey ? ' active' : ''}`}
                  href={`/sheet/${s.key}`}
                >
                  {s.label}
                </Link>
              ))}
              <Link className="topbar-nav-link" href="/retention">리텐션대상자</Link>
              {!isAdmin && <Link className="topbar-nav-link" href="/performance">실적현황</Link>}
              {isAdmin && <Link className="topbar-nav-link" href="/accounts">계정관리</Link>}
            </nav>
          </div>
          <div className="topbar-right">
            {sheetUrl && (
              <a className="logout-btn" href={sheetUrl} target="_blank" rel="noreferrer">
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

      <div className={`page-body${renewalPanelOpen ? ' panel-open' : ''}`}>
        <div className="page-heading">
          <div>
            <h1>{sheetLabel}</h1>
            <div className="count">
              {isNotepad
                ? isAdmin
                  ? '자유롭게 글자 크기·색상 등 서식을 적용해 작성하는 메모장입니다. 엑셀 등에서 붙여넣으면 서식 없이 글자만 들어갑니다.'
                  : '보기 전용 화면입니다. 수정은 관리자만 할 수 있습니다.'
                : isTemplates
                ? '왼쪽 카테고리마다 여러 개의 템플릿을 등록·수정·복사할 수 있습니다. 관리자 등록 템플릿은 상단에 고정되며 관리자가 수정하면 모두에게 즉시 반영됩니다.'
                : isRegistry
                ? isAdmin
                  ? '리스(질권사)와 사업자등록번호를 등록·수정·삭제할 수 있습니다. 수정하면 매니저 화면에도 바로 동일하게 반영됩니다.'
                  : '보기 전용 화면입니다. 수정은 관리자만 할 수 있습니다.'
                : isLinkHub
                ? isAdmin
                  ? '왼쪽 메뉴에서 항목을 선택해 등록·수정·삭제할 수 있습니다. 수정하면 매니저 화면에도 바로 동일하게 반영됩니다.'
                  : '보기 전용 화면입니다. 수정은 관리자만 할 수 있습니다.'
                : isRenewalTable
                ? isAdmin
                  ? '행을 클릭하면 상세 정보를 확인·수정할 수 있고, 컨택 히스토리는 기록이 계속 쌓입니다.'
                  : '본인이 담당하는 갱신배정 건만 보입니다. 딜러 정보 수정과 컨택 히스토리 기록을 할 수 있습니다.'
                : isAdmin
                ? '셀을 클릭하면 바로 수정할 수 있고, 저장하면 구글 시트에 즉시 반영됩니다.'
                : '보기 전용 화면입니다. 수정은 관리자만 할 수 있습니다.'}
            </div>
          </div>
          {!isNotepad && !isTemplates && !isRegistry && !isLinkHub && !isRenewalTable && <button className="btn" onClick={fetchGrid}>새로고침</button>}
        </div>

        {isNotepad ? (
          <FaqNotepad isAdmin={isAdmin} />
        ) : isTemplates ? (
          <LmsTemplates isAdmin={isAdmin} />
        ) : isRegistry ? (
          <LeaseRegistry isAdmin={isAdmin} />
        ) : isLinkHub ? (
          <LinkHub isAdmin={isAdmin} />
        ) : isRenewalTable ? (
          <RenewalRegistry isAdmin={isAdmin} name={name} onPanelChange={setRenewalPanelOpen} />
        ) : (
          <>
        {cellError && <div className="error-state ref-grid-error">{cellError}</div>}

        {loading ? (
          <div className="loading-state">불러오는 중...</div>
        ) : error ? (
          <div className="error-state">{error}</div>
        ) : (
          <div className="table-wrap ref-grid-wrap">
            <table className="ref-grid">
              <thead>
                <tr>
                  <th className="ref-grid-corner"></th>
                  {grid.colLetters.map((letter, i) => (
                    <th key={i}>{letter}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {grid.rows.length === 0 ? (
                  <tr className="empty-row">
                    <td colSpan={grid.colLetters.length + 1}>내용이 없습니다.</td>
                  </tr>
                ) : (
                  grid.rows.map((row, r) => (
                    <tr key={r}>
                      <td className="ref-grid-rownum">{r + 1}</td>
                      {row.map((cellValue, c) => {
                        const isEditing = !!editingCell && editingCell.r === r && editingCell.c === c;
                        return (
                          <td
                            key={c}
                            className={isAdmin ? 'ref-grid-cell editable' : 'ref-grid-cell'}
                            onClick={() => !isEditing && startEdit(r, c, cellValue)}
                          >
                            {isEditing ? (
                              <textarea
                                autoFocus
                                value={editValue}
                                onChange={(e) => setEditValue(e.target.value)}
                                onBlur={commitEdit}
                                onKeyDown={handleEditKeyDown}
                                disabled={savingCell}
                              />
                            ) : (
                              cellValue
                            )}
                          </td>
                        );
                      })}
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        )}
          </>
        )}
      </div>

      {changingPassword && (
        <ChangePasswordModal onClose={() => setChangingPassword(false)} />
      )}
    </div>
  );
}
