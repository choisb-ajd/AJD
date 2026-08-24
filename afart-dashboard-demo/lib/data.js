import fs from "fs";
import path from "path";

const CSV_PATH = path.join(process.cwd(), "data", "raw_query.csv");

const HEADER_MAP = [
  "channel", // 영업채널
  "counselId", // 상담ID
  "customerId", // 고객ID
  "customerName", // 고객명 (마스킹됨)
  "phone", // 연락처 (마스킹됨)
  "vin", // 차량차대번호
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

// ---- helpers ----

function isoWeekInfo(dateStr) {
  const d = new Date(dateStr + "T00:00:00Z");
  const day = (d.getUTCDay() + 6) % 7; // Mon=0 .. Sun=6
  const monday = new Date(d);
  monday.setUTCDate(d.getUTCDate() - day);
  const sunday = new Date(monday);
  sunday.setUTCDate(monday.getUTCDate() + 6);
  const fmt = (x) =>
    `${String(x.getUTCMonth() + 1).padStart(2, "0")}/${String(
      x.getUTCDate()
    ).padStart(2, "0")}`;
  const key = monday.toISOString().slice(0, 10);
  return { key, label: `${fmt(monday)}~${fmt(sunday)}` };
}

function monthOf(dateStr) {
  return dateStr.slice(0, 7); // YYYY-MM
}

function sumPremium(rows) {
  return rows.reduce((acc, r) => acc + (r.premium || 0), 0);
}

function bucketBy(rows, keyFn, labelFn) {
  const map = new Map();
  for (const r of rows) {
    if (!r.contractDate) continue;
    const key = keyFn(r);
    if (!map.has(key)) map.set(key, []);
    map.get(key).push(r);
  }
  const out = [...map.entries()].map(([key, list]) => {
    const premiumSum = sumPremium(list);
    const withPremium = list.filter((r) => r.premium != null).length;
    return {
      key,
      label: labelFn ? labelFn(key, list) : key,
      count: list.length,
      premiumSum,
      avgPremium: withPremium > 0 ? Math.round(premiumSum / withPremium) : 0,
    };
  });
  out.sort((a, b) => (a.key < b.key ? -1 : a.key > b.key ? 1 : 0));
  return out;
}

function dealerKey(r) {
  // 딜러ID가 비어있는 행이 있고, 마스킹된 딜러이름은 서로 다른 사람이 겹칠 수 있어
  // ID가 있으면 ID로, 없으면 이름+연락처로 묶는다.
  return r.dealerId || `${r.dealerName}|${r.dealerPhone}`;
}

export function aggregate(rows) {
  const clean = rows.filter((r) => r.contractDate);

  const totals = {
    count: clean.length,
    premiumSum: sumPremium(clean),
    dealerCount: new Set(clean.map(dealerKey)).size,
    dateMin: clean.reduce(
      (m, r) => (r.contractDate < m ? r.contractDate : m),
      clean[0]?.contractDate ?? ""
    ),
    dateMax: clean.reduce(
      (m, r) => (r.contractDate > m ? r.contractDate : m),
      clean[0]?.contractDate ?? ""
    ),
  };
  totals.avgPremium = totals.count
    ? Math.round(totals.premiumSum / totals.count)
    : 0;

  const daily = bucketBy(clean, (r) => r.contractDate);
  const weekly = bucketBy(
    clean,
    (r) => isoWeekInfo(r.contractDate).key,
    (key, list) => isoWeekInfo(list[0].contractDate).label
  );
  const monthly = bucketBy(clean, (r) => monthOf(r.contractDate));

  // 보험사 x 가입유형 피벗
  const insurerSet = new Set();
  const typeSet = new Set();
  const pivotMap = new Map();
  for (const r of clean) {
    const insurer = r.insurer || "미상";
    const type = r.joinType || "기타";
    insurerSet.add(insurer);
    typeSet.add(type);
    const key = insurer + "|" + type;
    pivotMap.set(key, (pivotMap.get(key) || 0) + (r.premium || 0));
  }
  const typeOrder = ["CM", "TM", "OFFLINE"];
  const types = [...typeSet].sort(
    (a, b) => typeOrder.indexOf(a) - typeOrder.indexOf(b)
  );
  const insurerPivot = [...insurerSet]
    .map((insurer) => {
      const byType = {};
      let rowTotal = 0;
      for (const t of types) {
        const v = pivotMap.get(insurer + "|" + t) || 0;
        byType[t] = v;
        rowTotal += v;
      }
      return { insurer, byType, total: rowTotal };
    })
    .sort((a, b) => b.total - a.total);
  const typeTotals = types.reduce((acc, t) => {
    acc[t] = insurerPivot.reduce((s, row) => s + row.byType[t], 0);
    return acc;
  }, {});
  const grandTotal = insurerPivot.reduce((s, row) => s + row.total, 0);

  // 딜러별 실적 (매니저 컬럼이 없어 딜러 기준으로 대체)
  const dealerMap = new Map();
  for (const r of clean) {
    const key = dealerKey(r);
    if (!dealerMap.has(key)) dealerMap.set(key, []);
    dealerMap.get(key).push(r);
  }
  const dealerRank = [...dealerMap.entries()]
    .map(([, list]) => ({
      dealerName: list[0].dealerName || "미상",
      count: list.length,
      premiumSum: sumPremium(list),
    }))
    .sort((a, b) => b.premiumSum - a.premiumSum);

  // 영업채널별
  const channelMap = new Map();
  for (const r of clean) {
    const key = r.channel || "기타";
    if (!channelMap.has(key)) channelMap.set(key, []);
    channelMap.get(key).push(r);
  }
  const byChannel = [...channelMap.entries()]
    .map(([channel, list]) => ({
      channel,
      count: list.length,
      premiumSum: sumPremium(list),
    }))
    .sort((a, b) => b.count - a.count);

  // 주유권 발송 대상
  const giftRows = clean.filter((r) => r.giftName);
  const giftSummaryMap = new Map();
  for (const r of giftRows) {
    giftSummaryMap.set(r.giftName, (giftSummaryMap.get(r.giftName) || 0) + 1);
  }
  const giftSummary = [...giftSummaryMap.entries()]
    .map(([giftName, count]) => ({ giftName, count }))
    .sort((a, b) => b.count - a.count);
  const giftList = giftRows
    .map((r) => ({
      customerName: r.customerName,
      phone: r.phone,
      giftName: r.giftName,
      contractDate: r.contractDate,
      dealerName: r.dealerName,
    }))
    .sort((a, b) => (a.contractDate < b.contractDate ? 1 : -1));

  return {
    totals,
    periods: { daily, weekly, monthly },
    insurerPivot: { rows: insurerPivot, types, typeTotals, grandTotal },
    dealerRank,
    byChannel,
    gift: { summary: giftSummary, list: giftList },
  };
}
