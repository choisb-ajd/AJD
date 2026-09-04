const { getSessionFromReq } = require('../../lib/auth');
const { getAdminRows, readKamasterLoginStatus, logErrorToSheet } = require('../../lib/sheetsRepo');
const { normalizePhone } = require('../../lib/sheetSchema');

export default async function handler(req, res) {
  if (req.method !== 'GET') {
    res.setHeader('Allow', 'GET');
    return res.status(405).json({ error: 'Method Not Allowed' });
  }

  const session = getSessionFromReq(req);
  if (!session) {
    return res.status(401).json({ error: '로그인이 필요합니다.' });
  }

  try {
    const force = req.query.force === '1';
    const [admin, loginStatusMap] = await Promise.all([
      getAdminRows({ useCache: !force }),
      readKamasterLoginStatus({ useCache: !force }),
    ]);

    const allRows = admin.rows.map((r) => {
      const phone = normalizePhone(r.values.phone || '');
      // loginStatusMap: phone → true(정회원) / false(준회원) / undefined(not in kamaster)
      const inKamaster = loginStatusMap.has(phone);
      const hasLoginId = inKamaster ? loginStatusMap.get(phone) : null;
      const isAssocMember = inKamaster && hasLoginId === false;
      return { ...r.values, isAssocMember };
    });

    const rows = session.role === '관리자'
      ? allRows
      : allRows.filter((r) => (r.manager || '') === session.name);

    res.setHeader('Cache-Control', 'no-cache');
    return res.status(200).json({ ok: true, rows });
  } catch (e) {
    logErrorToSheet({
      path: '/api/retention',
      statusCode: 500,
      message: e.message,
      userName: session?.name,
    });
    return res.status(500).json({ error: e.message });
  }
}
