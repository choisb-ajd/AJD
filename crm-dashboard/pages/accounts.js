import { useEffect, useState } from 'react';
import { useRouter } from 'next/router';
import Link from 'next/link';
import cookie from 'cookie';
import { verifySession, COOKIE_NAME } from '../lib/auth';
import ChangePasswordModal from '../components/ChangePasswordModal';
import Announcement from '../components/Announcement';
import FaqWidget from '../components/FaqWidget';
import useEscapeKey from '../lib/useEscapeKey';
import { REF_SHEETS } from '../lib/sheetSchema';
import { getEntry, fetchAndCache } from '../lib/dataCache';

const ACCOUNTS_KEY = 'accounts';

export async function getServerSideProps({ req }) {
  const cookies = cookie.parse(req.headers.cookie || '');
  const session = cookies[COOKIE_NAME] ? verifySession(cookies[COOKIE_NAME]) : null;
  if (!session) {
    return { redirect: { destination: '/login', permanent: false } };
  }
  if (session.role !== '관리자') {
    return { redirect: { destination: '/dashboard', permanent: false } };
  }
  return { props: { role: session.role, name: session.name } };
}

export default function AccountsPage({ role, name }) {
  const router = useRouter();
  const initialAccounts = getEntry(ACCOUNTS_KEY);
  const [accounts, setAccounts] = useState(() => (initialAccounts ? initialAccounts.data.accounts || [] : []));
  const [loading, setLoading] = useState(() => !initialAccounts);
  const [error, setError] = useState('');
  const [resetTarget, setResetTarget] = useState(null);
  const [changingPassword, setChangingPassword] = useState(false);
  const [addingAccount, setAddingAccount] = useState(false);

  async function fetchAccounts({ force = false } = {}) {
    setLoading(true);
    setError('');
    try {
      const data = await fetchAndCache(ACCOUNTS_KEY, '/api/accounts', { force });
      if (data) setAccounts(data.accounts);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (getEntry(ACCOUNTS_KEY)) return;
    fetchAccounts();
  }, []);

  async function handleLogout() {
    await fetch('/api/auth/logout', { method: 'POST' });
    router.push('/login');
  }

  return (
    <div className="app-shell">
      <FaqWidget isAdmin={role === '관리자'} />
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
              <Link className="topbar-nav-link" href="/retention">리텐션대상자</Link>
              <Link className="topbar-nav-link active" href="/accounts">계정관리</Link>
            </nav>
          </div>
          <div className="topbar-right">
            <span className="topbar-user">{name}님</span>
            <button className="logout-btn" onClick={() => setChangingPassword(true)}>비밀번호 변경</button>
            <button className="logout-btn" onClick={handleLogout}>로그아웃</button>
          </div>
        </div>
        <Announcement isAdmin={role === '관리자'} />
      </div>

      <div className="page-body">
        <div className="page-heading">
          <div>
            <h1>계정관리</h1>
            <div className="count">등록된 계정 수: {accounts.length.toLocaleString()}개</div>
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            <button className="btn" onClick={() => fetchAccounts({ force: true })}>새로고침</button>
            <button className="btn btn-primary" onClick={() => setAddingAccount(true)}>계정 추가</button>
          </div>
        </div>

        {loading ? (
          <div className="loading-state">불러오는 중...</div>
        ) : error ? (
          <div className="error-state">{error}</div>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>아이디</th>
                  <th>이름</th>
                  <th>권한</th>
                  <th>로그인 실패횟수</th>
                  <th>잠김여부</th>
                  <th>비고</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {accounts.length === 0 ? (
                  <tr className="empty-row">
                    <td colSpan={7}>등록된 계정이 없습니다.</td>
                  </tr>
                ) : (
                  accounts.map((a) => (
                    <tr key={a.loginId}>
                      <td>{a.loginId}</td>
                      <td>{a.name || '-'}</td>
                      <td>{a.role || '-'}</td>
                      <td>{a.failedAttempts}</td>
                      <td>
                        {a.locked ? (
                          <span className="badge badge-lock">잠김</span>
                        ) : (
                          <span className="badge badge-unlock">정상</span>
                        )}
                      </td>
                      <td title={a.note}>{a.note || '-'}</td>
                      <td>
                        <button className="btn" onClick={() => setResetTarget(a)}>
                          비밀번호 초기화
                        </button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {resetTarget && (
        <ResetPasswordModal
          account={resetTarget}
          onClose={() => setResetTarget(null)}
          onDone={() => {
            setResetTarget(null);
            fetchAccounts({ force: true });
          }}
        />
      )}

      {changingPassword && (
        <ChangePasswordModal onClose={() => setChangingPassword(false)} />
      )}

      {addingAccount && (
        <AddAccountModal
          onClose={() => setAddingAccount(false)}
          onDone={() => {
            setAddingAccount(false);
            fetchAccounts({ force: true });
          }}
        />
      )}
    </div>
  );
}

function AddAccountModal({ onClose, onDone }) {
  const [form, setForm] = useState({ loginId: '', password: '', name: '', role: '매니저', sheetUrl: '', note: '' });
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState(null);
  useEscapeKey(onClose);

  function set(key, value) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setMessage(null);
    if (!form.loginId.trim()) { setMessage({ type: 'err', text: '아이디를 입력해주세요.' }); return; }
    if (form.password.length < 4) { setMessage({ type: 'err', text: '비밀번호는 4자 이상이어야 합니다.' }); return; }
    if (!form.name.trim()) { setMessage({ type: 'err', text: '이름을 입력해주세요.' }); return; }

    setSaving(true);
    try {
      const res = await fetch('/api/accounts', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(form),
      });
      const data = await res.json();
      if (!res.ok) {
        setMessage({ type: 'err', text: data.error || '계정 생성에 실패했습니다.' });
        setSaving(false);
        return;
      }
      onDone();
    } catch (e) {
      setMessage({ type: 'err', text: '네트워크 오류가 발생했습니다.' });
      setSaving(false);
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-card" style={{ width: 420 }} onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>계정 추가</h2>
          <button className="modal-close" onClick={onClose}>&times;</button>
        </div>

        {message && <div className={`modal-message ${message.type}`}>{message.text}</div>}

        <form onSubmit={handleSubmit}>
          <div className="modal-field">
            <label>아이디 <span style={{ color: 'var(--danger, #e53e3e)' }}>*</span></label>
            <input value={form.loginId} onChange={(e) => set('loginId', e.target.value)} autoFocus placeholder="로그인 아이디" />
          </div>
          <div className="modal-field">
            <label>비밀번호 <span style={{ color: 'var(--danger, #e53e3e)' }}>*</span></label>
            <input type="password" value={form.password} onChange={(e) => set('password', e.target.value)} placeholder="4자 이상" />
          </div>
          <div className="modal-field">
            <label>이름 <span style={{ color: 'var(--danger, #e53e3e)' }}>*</span></label>
            <input value={form.name} onChange={(e) => set('name', e.target.value)} placeholder="실명 (딜러 배정 시 표시됨)" />
          </div>
          <div className="modal-field">
            <label>권한</label>
            <select value={form.role} onChange={(e) => set('role', e.target.value)}>
              <option value="매니저">매니저</option>
              <option value="관리자">관리자</option>
            </select>
          </div>
          <div className="modal-field">
            <label>개인 시트 URL <span style={{ color: 'var(--muted)', fontSize: 12 }}>(선택)</span></label>
            <input value={form.sheetUrl} onChange={(e) => set('sheetUrl', e.target.value)} placeholder="https://docs.google.com/spreadsheets/d/..." />
          </div>
          <div className="modal-field">
            <label>비고 <span style={{ color: 'var(--muted)', fontSize: 12 }}>(선택)</span></label>
            <input value={form.note} onChange={(e) => set('note', e.target.value)} placeholder="메모" />
          </div>
          <div className="modal-actions">
            <button type="button" className="btn" onClick={onClose}>취소</button>
            <button type="submit" className="btn btn-primary" disabled={saving}>
              {saving ? '생성 중...' : '계정 생성'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

function ResetPasswordModal({ account, onClose, onDone }) {
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState(null);
  useEscapeKey(onClose);

  async function handleSubmit(e) {
    e.preventDefault();
    setMessage(null);

    if (newPassword.length < 4) {
      setMessage({ type: 'err', text: '새 비밀번호는 4자 이상이어야 합니다.' });
      return;
    }
    if (newPassword !== confirmPassword) {
      setMessage({ type: 'err', text: '새 비밀번호가 서로 일치하지 않습니다.' });
      return;
    }

    setSaving(true);
    try {
      const res = await fetch('/api/accounts/reset-password', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ loginId: account.loginId, newPassword }),
      });
      const data = await res.json();
      if (!res.ok) {
        setMessage({ type: 'err', text: data.error || '초기화에 실패했습니다.' });
        setSaving(false);
        return;
      }
      onDone();
    } catch (e) {
      setMessage({ type: 'err', text: '네트워크 오류가 발생했습니다.' });
      setSaving(false);
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-card" style={{ width: 380 }} onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <div>
            <h2>비밀번호 초기화</h2>
            <div className="sub">{account.name} ({account.loginId})</div>
          </div>
          <button className="modal-close" onClick={onClose}>&times;</button>
        </div>

        {message && <div className={`modal-message ${message.type}`}>{message.text}</div>}

        <form onSubmit={handleSubmit}>
          <div className="modal-field">
            <label>새 비밀번호</label>
            <input
              type="password"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              autoFocus
            />
          </div>
          <div className="modal-field">
            <label>새 비밀번호 확인</label>
            <input
              type="password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
            />
          </div>
          <div className="modal-actions">
            <button type="button" className="btn" onClick={onClose}>취소</button>
            <button type="submit" className="btn btn-primary" disabled={saving}>
              {saving ? '처리 중...' : '초기화하기'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
