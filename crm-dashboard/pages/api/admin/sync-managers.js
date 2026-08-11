export default function handler(req, res) {
  res.status(410).json({ error: '매니저 시트 동기화 기능이 제거되었습니다. 관리자 시트가 단일 데이터 소스입니다.' });
}
