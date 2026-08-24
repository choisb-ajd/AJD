import fs from "fs";
import path from "path";
import { assignManager, assignGroup } from "./mockAssign";

const CSV_PATH = path.join(process.cwd(), "data", "raw_query.csv");

const HEADER_MAP = [
  "channel", // 영업채널
  "counselId", // 상담ID
  "customerId", // 고객ID
  "customerName", // 고객명 (마스킹됨)
  "phone", // 연락처 (마스킹됨)
  "vin", // 차량차대번호 (이 raw pull은 차량번호/차대번호가 한 컬럼으로 합쳐져 있음)
  "premium", // 보험료
  "insurer", // 가입보험사
  "joinType", // 가입유형 (CM/TM/OFFLINE)
  "insuranceKind", // 보험종류
  "vehicleKind", // 차량구분
  "contractDate", // 체결일자
  "giftName", // 주유권
  "dealerPhone", // 딜러연락처
  "dealerName", // 딜러이름
  "dealerId", // 딜러ID
];

function parseCsv(text) {
  const lines = text.split(/\r?\n/).filter((l) => l.length > 0);
  const rows = [];
  for (let i = 1; i < lines.length; i++) {
    const cols = lines[i].split(",");
    if (cols.length < HEADER_MAP.length) continue;
    const row = {};
    HEADER_MAP.forEach((key, idx) => {
      row[key] = (cols[idx] ?? "").trim();
    });
    row.premium = row.premium === "" ? null : Number(row.premium);
    if (Number.isNaN(row.premium)) row.premium = null;
    rows.push(row);
  }
  return rows;
}

export function loadRawRows() {
  const text = fs.readFileSync(CSV_PATH, "utf-8");
  return parseCsv(text);
}

function dealerKey(r) {
  // 딜러ID가 비어있는 행이 있고, 마스킹된 딜러이름은 서로 다른 사람이 겹칠 수 있어
  // ID가 있으면 ID로, 없으면 이름+연락처로 묶는다.
  return r.dealerId || `${r.dealerName}|${r.dealerPhone}`;
}

// 빌드 시점에 한 번만 계산해서 클라이언트로 내려줄 가벼운 행 목록을 만든다.
// 고객명/연락처/차대번호 같은 개인정보는 여기 담지 않는다 — 전체 6천여 건을 브라우저로
// 보낼 이유가 없고(페이로드도 커짐), 검색은 /api/search 서버 라우트에서 처리한다.
//
// 필드명을 6천여 번 반복하지 않도록(JSON 페이로드 절감) 배열 형태로 내려보내고,
// 클라이언트에서 unpackRows()로 다시 객체로 복원한다.
export const CLIENT_ROW_FIELDS = [
  "date",
  "premium",
  "insurer",
  "joinType",
  "channel",
  "dealerKey",
  "dealerName",
  "managerName",
  "group",
];

export function toClientRows(rawRows) {
  return rawRows
    .filter((r) => r.contractDate)
    .map((r) => {
      const dk = dealerKey(r);
      return [
        r.contractDate,
        r.premium,
        r.insurer || "미상",
        r.joinType || "기타",
        r.channel || "기타",
        dk,
        r.dealerName || "미상",
        assignManager(dk),
        assignGroup(dk).code,
      ];
    });
}


// 주유권 발송 리스트는 건수가 적어(수십 건) 필요한 필드를 그대로 내려도 부담이 없다.
export function toGiftRows(rawRows) {
  return rawRows
    .filter((r) => r.contractDate && r.giftName)
    .map((r) => {
      const dk = dealerKey(r);
      return {
        date: r.contractDate,
        customerName: r.customerName || "",
        phone: r.phone || "",
        giftName: r.giftName,
        dealerName: r.dealerName || "미상",
        managerName: assignManager(dk),
      };
    });
}
