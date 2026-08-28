-- ============================================================
-- B2G 파트너 광고비(사업소득) 지급 파일 형식
-- 딜러별 광고비 합산 + 3.3% 원천징수 자동 계산
-- ※ 주민등록번호, 은행명, 계좌번호는 SF에 없을 수 있음 → 빈값 처리
-- ※ 광고비요율은 SF에 저장되지 않아 수동 관리 필요 (아래 참고)
-- Snowsight에서 실행 후 CSV 다운로드
-- ============================================================

-- ▼ 기간 설정: 지급 대상 기간의 시작일/종료일을 변경하세요
SET START_DT = '2026-08-01';
SET END_DT   = '2026-08-28';

WITH CONTRACT AS (
    SELECT CA.COUNSEL_ID,
           CA.USER_ID,
           CA.SUBSCRIPTION_TYPE,
           CV.CONTRACT_AMOUNT,
           CASE WHEN LG.PENDING_AT IS NOT NULL
                THEN LG.PENDING_AT
                ELSE CA.JOIN_COMPLETED_AT
           END AS CONTRACT_AT
    FROM AJDCAR_PROD.PUBLIC.COUNSEL_APPLICATION CA
    JOIN AJDCAR_PROD.PUBLIC.CUSTOMER C
         ON C.CUSTOMER_ID = CA.CUSTOMER_ID AND C.IS_DELETED = FALSE
    JOIN AJDCAR_PROD.PUBLIC.COUNSEL_VEHICLE CV
         ON CV.COUNSEL_ID = CA.COUNSEL_ID AND CV.IS_DELETED = FALSE
    LEFT JOIN (
        SELECT COUNSEL_ID, MIN(CREATED_AT) AS PENDING_AT
        FROM AJDCAR_PROD.PUBLIC.COUNSEL_STATUS_LOG
        WHERE NEW_COUNSEL_STATUS = 'ACCUMULATE_PENDING'
        GROUP BY COUNSEL_ID
    ) LG ON LG.COUNSEL_ID = CA.COUNSEL_ID
    WHERE CA.IS_DELETED = FALSE
      AND CA.COUNSEL_STATUS IN ('JOIN_COMPLETED', 'ACCUMULATE_PENDING')
),
-- 딜러별 해당 기간 원수보험료 합산
DEALER_TOTAL AS (
    SELECT ct.USER_ID,
           SUM(ct.CONTRACT_AMOUNT) AS TOTAL_PREMIUM
    FROM CONTRACT ct
    WHERE ct.CONTRACT_AT::DATE BETWEEN $START_DT AND $END_DT
      AND ct.SUBSCRIPTION_TYPE = 'DEALER_APP'
    GROUP BY ct.USER_ID
    HAVING SUM(ct.CONTRACT_AMOUNT) > 0
)
SELECT
    ROW_NUMBER() OVER (ORDER BY u.USER_NAME) AS "NO",
    u.USER_NAME AS "소득자명",
    '' AS "주민등록번호",        -- SF에 없음: 수동 입력 또는 별도 테이블 필요
    '' AS "은행명",              -- SF에 없음
    '' AS "계좌번호",            -- SF에 없음
    '아정당자동차광고비' AS "입금통장표시내용",

    -- ▼ 광고비요율이 SF에 없으므로, 기본 6% 적용
    -- 실제로는 딜러별 요율이 다름 (6%, 7%, 8% 등)
    -- AD_POINT 잔액 기반이 아니라 원수보험료 × 요율 합산
    ROUND(dt.TOTAL_PREMIUM * 0.06, 0) AS "B2G파트너Fee",

    0 AS "프로모션",
    0 AS "추가수수료",
    ROUND(dt.TOTAL_PREMIUM * 0.06, 0) AS "지급총액",

    -- 사업소득세 3% (10원 단위 절사)
    FLOOR(ROUND(dt.TOTAL_PREMIUM * 0.06, 0) * 0.03 / 10) * 10 AS "사업소득세",

    -- 지방소득세 0.3% (10원 단위 절사)
    FLOOR(ROUND(dt.TOTAL_PREMIUM * 0.06, 0) * 0.003 / 10) * 10 AS "지방소득세",

    -- 공제총액
    FLOOR(ROUND(dt.TOTAL_PREMIUM * 0.06, 0) * 0.03 / 10) * 10
    + FLOOR(ROUND(dt.TOTAL_PREMIUM * 0.06, 0) * 0.003 / 10) * 10 AS "공제총액",

    -- 실지급액
    ROUND(dt.TOTAL_PREMIUM * 0.06, 0)
    - (FLOOR(ROUND(dt.TOTAL_PREMIUM * 0.06, 0) * 0.03 / 10) * 10
       + FLOOR(ROUND(dt.TOTAL_PREMIUM * 0.06, 0) * 0.003 / 10) * 10) AS "실지급액",

    $END_DT::DATE AS "지급일자",

    -- 참고: 원수보험료 합계
    dt.TOTAL_PREMIUM AS "원수보험료합계(참고)",
    u.AD_POINT AS "광고비포인트잔액(참고)"

FROM DEALER_TOTAL dt
JOIN AJDCAR_PROD.PUBLIC.USERS u ON u.ID = dt.USER_ID
WHERE u.IS_ASSOCIATE = 0
  AND u.USER_NAME NOT LIKE '%테스트%'
ORDER BY u.USER_NAME;
