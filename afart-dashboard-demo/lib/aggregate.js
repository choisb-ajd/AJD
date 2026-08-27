// 순수 함수 모음 — 서버(getStaticProps)와 브라우저(필터 변경 시) 양쪽에서 동일하게 사용한다.
// 입력은 lib/data.js의 toClientRows()가 만든 압축 행 배열.

function isoWeekInfo(dateStr) {
  const d = new Date(dateStr + "T00:00:00Z");
  const day = (d.getUTCDay() + 6) % 7; // Mon=0 .. Sun=6
  const monday = new Date(d);
  monday.setUTCDate(d.getUTCDate() - day);
  const sunday = new Date(monday);
  sunday.setUTCDate(monday.getUTCDate() + 6);
  const fmt = (x) =>
    `${String(x.getUTCMonth() + 1).padStart(2, "0")}/${String(x.getUTCDate()).padStart(2, "0")}`;
  return { key: monday.toISOString().slice(0, 10), label: `${fmt(monday)}~${fmt(sunday)}` };
}

const monthOf = (d) => d.slice(0, 7);
const sumPremium = (rows) => rows.reduce((a, r) => a + (r.premium || 0), 0);

function bucketBy(rows, keyFn, labelFn) {
  const map = new Map();
  for (const r of rows) {
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

export function filterRows(rows, { dateFrom, dateTo, manager }) {
  return rows.filter((r) => {
    if (dateFrom && r.date < dateFrom) return false;
    if (dateTo && r.date > dateTo) return false;
    if (manager && manager !== "ALL" && r.managerName !== manager) return false;
    return true;
  });
}

export function aggregate(rows) {
  const totals = {
    count: rows.length,
    joinCompletedCount: rows.filter((r) => r.currentStatus === "JOIN_COMPLETED").length,
    pendingCount: rows.filter((r) => r.currentStatus === "ACCUMULATE_PENDING").length,
    premiumSum: sumPremium(rows),
    dealerCount: new Set(rows.map((r) => r.dealerKey)).size,
    dateMin: rows.reduce((m, r) => (m === "" || r.date < m ? r.date : m), ""),
    dateMax: rows.reduce((m, r) => (m === "" || r.date > m ? r.date : m), ""),
  };
  totals.avgPremium = totals.count ? Math.round(totals.premiumSum / totals.count) : 0;

  const daily = bucketBy(rows, (r) => r.date);
  const weekly = bucketBy(rows, (r) => isoWeekInfo(r.date).key, (k, l) => isoWeekInfo(l[0].date).label);
  const monthly = bucketBy(rows, (r) => monthOf(r.date));

  // 보험사 x 가입유형 피벗
  const insurerSet = new Set();
  const typeSet = new Set();
  const pivotMap = new Map();
  for (const r of rows) {
    insurerSet.add(r.insurer);
    typeSet.add(r.joinType);
    const k = r.insurer + "|" + r.joinType;
    pivotMap.set(k, (pivotMap.get(k) || 0) + (r.premium || 0));
  }
  const typeOrder = ["CM", "TM", "OFFLINE"];
  const types = [...typeSet].sort((a, b) => typeOrder.indexOf(a) - typeOrder.indexOf(b));
  const insurerRows = [...insurerSet]
    .map((insurer) => {
      const byType = {};
      let total = 0;
      for (const t of types) {
        const v = pivotMap.get(insurer + "|" + t) || 0;
        byType[t] = v;
        total += v;
      }
      return { insurer, byType, total };
    })
    .sort((a, b) => b.total - a.total);
  const typeTotals = types.reduce((acc, t) => {
    acc[t] = insurerRows.reduce((s, row) => s + row.byType[t], 0);
    return acc;
  }, {});
  const insurerPivot = {
    rows: insurerRows,
    types,
    typeTotals,
    grandTotal: insurerRows.reduce((s, r) => s + r.total, 0),
  };

  // 딜러별
  const dealerMap = new Map();
  for (const r of rows) {
    if (!dealerMap.has(r.dealerKey)) dealerMap.set(r.dealerKey, []);
    dealerMap.get(r.dealerKey).push(r);
  }
  const dealerRank = [...dealerMap.entries()]
    .map(([, list]) => ({
      dealerName: list[0].dealerName,
      managerName: list[0].managerName,
      group: list[0].group,
      count: list.length,
      premiumSum: sumPremium(list),
    }))
    .sort((a, b) => b.premiumSum - a.premiumSum);

  // 채널별
  const channelMap = new Map();
  for (const r of rows) {
    if (!channelMap.has(r.channel)) channelMap.set(r.channel, []);
    channelMap.get(r.channel).push(r);
  }
  const byChannel = [...channelMap.entries()]
    .map(([channel, list]) => ({ channel, count: list.length, premiumSum: sumPremium(list) }))
    .sort((a, b) => b.count - a.count);

  // 매니저별 (실제 counsel_manager 기준)
  const managerMap = new Map();
  for (const r of rows) {
    if (!managerMap.has(r.managerName)) managerMap.set(r.managerName, []);
    managerMap.get(r.managerName).push(r);
  }
  const managerRank = [...managerMap.entries()]
    .map(([managerName, list]) => ({
      managerName,
      count: list.length,
      premiumSum: sumPremium(list),
      dealerCount: new Set(list.map((r) => r.dealerKey)).size,
    }))
    .sort((a, b) => b.premiumSum - a.premiumSum);

  // 딜러유형 그룹별 (실제 business_type 기준) - 배정 딜러 수
  const groupMap = new Map();
  for (const r of rows) {
    if (!groupMap.has(r.group)) groupMap.set(r.group, new Set());
    groupMap.get(r.group).add(r.dealerKey);
  }

  // 비견(비교견적완료) 퍼널 — 이 raw pull은 성사된 건만 담고 있어 "손실 포함 전환율"은 계산할 수 없다.
  // 대신 체결 건 중 비교견적 단계를 거친 비율과, 단계별 평균 소요일을 본다.
  const comparisonRows = rows.filter((r) => r.hasComparison);
  const avg = (arr) => (arr.length ? arr.reduce((s, v) => s + v, 0) / arr.length : null);
  const funnel = {
    comparisonCount: comparisonRows.length,
    comparisonRate: totals.count ? (comparisonRows.length / totals.count) * 100 : 0,
    avgProspectToCompDays: avg(
      comparisonRows.map((r) => r.prospectToCompDays).filter((v) => v != null)
    ),
    avgCompToJoinDays: avg(comparisonRows.map((r) => r.compToJoinDays).filter((v) => v != null)),
  };

  return {
    totals,
    periods: { daily, weekly, monthly },
    insurerPivot,
    dealerRank,
    byChannel,
    managerRank,
    groupDealerCount: groupMap,
    funnel,
  };
}

// 주유권/지급대기/가입취소처럼 건수가 적은 리스트형 데이터를 기간·매니저로 거르는 공용 함수.
// (건 단위 배열이면 무엇이든 재사용 — 각 항목은 date, managerName 필드를 가진다고 가정)
export function filterListRows(list, { dateFrom, dateTo, manager }) {
  return list
    .filter((r) => {
      if (dateFrom && r.date < dateFrom) return false;
      if (dateTo && r.date > dateTo) return false;
      if (manager && manager !== "ALL" && r.managerName !== manager) return false;
      return true;
    })
    .sort((a, b) => (a.date < b.date ? 1 : -1));
}

// 주유권 리스트 전용 — filterListRows에 권종별 요약을 더한다.
export function filterGiftRows(giftRows, filters) {
  const list = filterListRows(giftRows, filters);
  const summaryMap = new Map();
  for (const r of list) summaryMap.set(r.giftName, (summaryMap.get(r.giftName) || 0) + 1);
  return {
    summary: [...summaryMap.entries()]
      .map(([giftName, count]) => ({ giftName, count }))
      .sort((a, b) => b.count - a.count),
    list,
  };
}
