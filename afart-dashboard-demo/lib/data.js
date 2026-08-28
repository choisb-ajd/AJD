import fs from "fs";
import path from "path";
import { groupOf } from "./groups";

const CSV_PATH = path.join(process.cwd(), "data", "raw_query.csv");

const HEADER_MAP = [
  "channel", // 유입채널
  "counselId", // 상담ID
  "customerId", // 고객ID
  "customerName", // 고객명 (마스킹됨)
  "phone", // 연락처 (마스킹됨)
  "plateNumber", // 차량번호
  "vin", // 차대번호
  "premium", // 보험료
  "insurer", // 가입보험사
  "joinType", // 가입유형 (CM/TM/OFFLINE)
  "insuranceKind", // 보험종류
  "vehicleKind", // 차량구분
  "contractDate", // 체결일자
  "expiryDate", // 만기일자
  "currentStatus", // 현재상태 (counsel_status)
  "statusHistory", // 상태전환이력 "A(MM-DD HH:MM) → B(MM-DD HH:MM) → ..."
  "giftName", // 주유권
  "dealerPhone", // 딜러연락처
  "dealerName", // 딜러이름
  "dealerId", // 딜러ID
  "dealerType", // 딜러유형 (business_type)
  "dealerStatus", // 딜러상태 (business_card_status)
  "managerName", // 상담(체결)매니저 (counsel_manager_id)
  "dealerManagerName", // 딜러전담매니저 (users.manager_id)
];

function parseCsv(text) {
  const lines = text.split(/\r?\n/).filter((l) => l.length > 0);
  const rows = [];
  for (let i = 1; i < lines.length; i++) {
    const cols = lines[i].split(",");
    if (cols.length < HEADER_MAP.length) continue;
    const row = {};
    HEADER_MAP.forEach((key, idx) => {
      row[key] = (cols[idx] ?? "").trim().replace(/^"|"$/g, "");
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

// AFART 앱 회원(딜러) 집계 공통 규칙: 탈퇴(REJECTED)만 제외, APPROVED/PENDING(+미기재)은 포함.
// 이 raw pull엔 REJECTED가 아직 없어 사실상 전건 포함되지만, 규칙은 그대로 반영해둔다.
function isEligibleDealer(r) {
  return r.dealerStatus !== "REJECTED";
}

// "STATUS(MM-DD HH:MM) → STATUS(MM-DD HH:MM) → ..." 를 순서대로 파싱
const HISTORY_RE = /([A-Z_]+)\((\d{2}-\d{2} \d{2}:\d{2})\)/g;

function parseHistory(str) {
  if (!str) return [];
  return [...str.matchAll(HISTORY_RE)].map((m) => ({ status: m[1], at: m[2] }));
}

// 이력 타임스탬프엔 연도가 없다 — 이 raw pull은 전부 2026년이라 2026 고정으로 파싱한다.
function toTime(mmddhhmm) {
  const [md, hm] = mmddhhmm.split(" ");
  const [mm, dd] = md.split("-");
  const [hh, mi] = hm.split(":");
  return Date.UTC(2026, Number(mm) - 1, Number(dd), Number(hh), Number(mi));
}

function funnelOf(r) {
  const events = parseHistory(r.statusHistory);
  const prospect = events.find((e) => e.status === "PROSPECT_COUNSEL");
  const comparison = events.find((e) => e.status === "COMPARISON_COMPLETED");
  const final = events[events.length - 1];

  let prospectToCompDays = null;
  let compToJoinDays = null;
  if (comparison) {
    if (prospect) {
      prospectToCompDays = Math.max(0, (toTime(comparison.at) - toTime(prospect.at)) / 86400000);
    }
    if (final) {
      compToJoinDays = Math.max(0, (toTime(final.at) - toTime(comparison.at)) / 86400000);
    }
  }
  return { hasComparison: !!comparison, prospectToCompDays, compToJoinDays };
}

// 빌드 시점에 한 번만 계산해서 클라이언트로 내려줄 가벼운 행 목록을 만든다.
// 고객명/연락처/차대번호 같은 개인정보는 여기 담지 않는다 — 검색은 /api/search 서버 라우트에서 처리한다.
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
  "hasComparison",
  "prospectToCompDays",
  "compToJoinDays",
  "currentStatus",
  "dealerManagerName",
];

export function toClientRows(rawRows) {
  return rawRows
    .filter((r) => r.contractDate && isEligibleDealer(r))
    .map((r) => {
      const f = funnelOf(r);
      return [
        r.contractDate,
        r.premium,
        r.insurer || "미상",
        r.joinType || "기타",
        r.channel || "기타",
        dealerKey(r),
        r.dealerName || "미상",
        r.managerName || "미배정",
        groupOf(r.dealerType).code,
        f.hasComparison ? 1 : 0,
        f.prospectToCompDays,
        f.compToJoinDays,
        r.currentStatus,
        r.dealerManagerName || "미배정",
      ];
    });
}

// 주유권 발송 리스트는 건수가 적어(수십 건) 필요한 필드를 그대로 내려도 부담이 없다.
export function toGiftRows(rawRows) {
  return rawRows
    .filter((r) => r.contractDate && r.giftName && isEligibleDealer(r))
    .map((r) => ({
      date: r.contractDate,
      customerName: r.customerName || "",
      phone: r.phone || "",
      giftName: r.giftName,
      dealerName: r.dealerName || "미상",
      managerName: r.managerName || "미배정",
    }));
}

// '지급대기' 전환 리스트 — 현재상태가 ACCUMULATE_PENDING인 실제 건.
export function toPendingRows(rawRows) {
  return rawRows
    .filter((r) => r.currentStatus === "ACCUMULATE_PENDING" && isEligibleDealer(r))
    .map((r) => {
      const events = parseHistory(r.statusHistory);
      const last = [...events].reverse().find((e) => e.status === "ACCUMULATE_PENDING");
      return {
        date: r.contractDate,
        transitionAt: last ? `2026-${last.at.replace(" ", " ")}` : r.contractDate,
        customerName: r.customerName || "",
        phone: r.phone || "",
        premium: r.premium,
        managerName: r.managerName || "미배정",
        dealerName: r.dealerName || "미상",
      };
    });
}

// '가입취소' 리스트 — 현재상태가 실제로 가입취소(JOIN_CANCELLED)인 건만 보여준다.
// 이 raw pull은 counsel_status IN (ACCUMULATE_PENDING, JOIN_COMPLETED)인 최종 성사 건만
// 담고 있어 실제로는 항상 비어 보인다 — 실 서비스 데이터가 붙으면 정상적으로 채워진다.
export function toCancelledRows(rawRows) {
  return rawRows
    .filter((r) => r.currentStatus === "JOIN_CANCELLED" && isEligibleDealer(r))
    .map((r) => {
      const events = parseHistory(r.statusHistory);
      const cancelled = [...events].reverse().find((e) => e.status === "JOIN_CANCELLED");
      // 체결까지 못 가고 취소된 건은 체결일자(contractDate)가 비어있을 수 있어, 상단 날짜
      // 필터에 걸리는 기준일은 항상 가입취소일시로 삼는다 (date/cancelledAt 동일 값).
      const cancelledAt = cancelled ? `2026-${cancelled.at.replace(" ", " ")}` : r.contractDate;
      return {
        date: cancelledAt,
        cancelledAt,
        customerName: r.customerName || "",
        phone: r.phone || "",
        contractDate: r.contractDate || "",
        insurer: r.insurer || "미상",
        joinType: r.joinType || "기타",
        premium: r.premium,
        managerName: r.managerName || "미배정",
        dealerName: r.dealerName || "미상",
        dealerManagerName: r.dealerManagerName || "미배정",
      };
    });
}

// 매출 로우 데이터 리스트(/api/sales)용 — 기간으로 걸러 필요한 컬럼만 내려준다.
// 차량(차대)번호는 차량번호가 있으면 그걸, 없으면 차대번호를 보여준다 (둘 다 비어있는 행도 있음).
export function toSalesRows(rawRows, { dateFrom, dateTo }) {
  return rawRows
    .filter((r) => {
      if (!r.contractDate || !isEligibleDealer(r)) return false;
      if (dateFrom && r.contractDate < dateFrom) return false;
      if (dateTo && r.contractDate > dateTo) return false;
      return true;
    })
    .map((r) => ({
      channel: r.channel || "기타",
      customerName: r.customerName || "",
      vin: r.plateNumber || r.vin || "",
      expiryDate: r.expiryDate || "",
      premium: r.premium,
      contractDate: r.contractDate,
      counselManagerName: r.managerName || "미배정",
      dealerName: r.dealerName || "미상",
      dealerManagerName: r.dealerManagerName || "미배정",
    }))
    .sort((a, b) => (a.contractDate < b.contractDate ? 1 : -1));
}

// 갱신 관리 — 만기일자가 있는 건을 전부 후보로 두고, 화면에서 "오늘로부터 N일 이내" 필터를 건다.
export function toRenewalRows(rawRows) {
  return rawRows
    .filter((r) => r.expiryDate && isEligibleDealer(r))
    .map((r) => ({
      dueDate: r.expiryDate,
      customerName: r.customerName || "",
      phone: r.phone || "",
      insurer: r.insurer || "",
      dealerName: r.dealerName || "미상",
      managerName: r.managerName || "미배정",
    }));
}
