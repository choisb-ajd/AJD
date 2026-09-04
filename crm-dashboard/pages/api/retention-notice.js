const { getSessionFromReq } = require('../../lib/auth');
const { readRetentionNotice, saveRetentionNotice } = require('../../lib/sheetsRepo');

export default async function handler(req, res) {
  const session = getSessionFromReq(req);
  if (!session) {
    return res.status(401).json({ error: '로그인이 필요합니다.' });
  }

  if (req.method === 'GET') {
    try {
      const text = await readRetentionNotice();
      return res.status(200).json({ ok: true, text });
    } catch (e) {
      return res.status(500).json({ error: e.message });
    }
  }

  if (req.method === 'POST') {
    try {
      const text = await saveRetentionNotice((req.body || {}).text, session);
      return res.status(200).json({ ok: true, text });
    } catch (e) {
      return res.status(400).json({ error: e.message });
    }
  }

  res.setHeader('Allow', 'GET, POST');
  return res.status(405).json({ error: 'Method Not Allowed' });
}
