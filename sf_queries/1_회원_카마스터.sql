-- ============================================================
-- 1_회원_카마스터 시트 형식 — Snowflake에서 딜러(회원) 현황 추출
-- Snowsight에서 실행 후 CSV 다운로드
-- ============================================================

WITH DEALER_CONTRACTS AS (
    SELECT CA.USER_ID,
           COUNT(*) AS "누적계약건수",
           SUM(CV.CONTRACT_AMOUNT) AS "누적원수보험료",
           MIN(CASE WHEN LG.PENDING_AT IS NOT NULL THEN LG.PENDING_AT
                    ELSE CA.JOIN_COMPLETED_AT END) AS "최초계약인입일",
           MAX(CASE WHEN LG.PENDING_AT IS NOT NULL THEN LG.PENDING_AT
                    ELSE CA.JOIN_COMPLETED_AT END) AS "최종계약인입일",
           COUNT(CASE WHEN (CASE WHEN LG.PENDING_AT IS NOT NULL THEN LG.PENDING_AT
                                 ELSE CA.JOIN_COMPLETED_AT END)::DATE
                           >= CURRENT_DATE - 60 THEN 1 END) AS "직전60일건수",
           COUNT(CASE WHEN (CASE WHEN LG.PENDING_AT IS NOT NULL THEN LG.PENDING_AT
                                 ELSE CA.JOIN_COMPLETED_AT END)::DATE
                           >= CURRENT_DATE - 90 THEN 1 END) AS "직전90일건수",
           COUNT(CASE WHEN DATE_TRUNC('MONTH',
                      CASE WHEN LG.PENDING_AT IS NOT NULL THEN LG.PENDING_AT
                           ELSE CA.JOIN_COMPLETED_AT END)
                      = DATE_TRUNC('MONTH', CURRENT_DATE) THEN 1 END) AS "당월실적",
           SUM(CASE WHEN DATE_TRUNC('MONTH',
                    CASE WHEN LG.PENDING_AT IS NOT NULL THEN LG.PENDING_AT
                         ELSE CA.JOIN_COMPLETED_AT END)
                    = DATE_TRUNC('MONTH', CURRENT_DATE)
                    THEN CV.CONTRACT_AMOUNT ELSE 0 END) AS "당월원수보험료"
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
    GROUP BY CA.USER_ID
)
SELECT
    ROW_NUMBER() OVER (ORDER BY u.CREATED_AT) AS "seq",
    u.CREATED_AT::DATE AS "회원확보일자",
    u.USER_NAME AS "딜러성명",
    u.USER_ID AS "로그인ID",
    u.PHONE AS "연락처",
    m.NAME AS "담당매니저",
    CASE WHEN u.IS_ASSOCIATE = 0 AND u.BUSINESS_CARD_STATUS = 'APPROVED'
         THEN 'Y' ELSE '-' END AS "앱가입여부",
    u.PRIMARY_AFFILIATION AS "브랜드",
    u.SECONDARY_AFFILIATION AS "지점명",
    u.AD_POINT AS "광고비포인트잔액",

    COALESCE(dc."누적계약건수", 0) AS "누적계약체결건수",
    COALESCE(dc."누적원수보험료", 0) AS "누적총원수보험료",
    dc."최초계약인입일"::DATE AS "최초계약인입일",
    dc."최종계약인입일"::DATE AS "최종계약인입일",
    COALESCE(dc."직전60일건수", 0) AS "직전60일계약체결건수",
    COALESCE(dc."직전90일건수", 0) AS "직전90일계약체결건수",
    COALESCE(dc."당월실적", 0) AS "당월실적",
    COALESCE(dc."당월원수보험료", 0) AS "당월원수보험료",

    CASE WHEN COALESCE(dc."직전60일건수", 0) > 0 THEN 'Y' ELSE 'N' END AS "활동회원여부(직전60일)",
    CASE WHEN COALESCE(dc."직전90일건수", 0) > 0 THEN 'Y' ELSE 'N' END AS "활동회원여부(직전90일)"

FROM AJDCAR_PROD.PUBLIC.USERS u
LEFT JOIN AJDCAR_PROD.PUBLIC.MANAGER m
     ON m.ID = u.MANAGER_ID
LEFT JOIN DEALER_CONTRACTS dc
     ON dc.USER_ID = u.ID
WHERE u.IS_ASSOCIATE = 0
  AND u.USER_NAME NOT LIKE '%테스트%'
  AND (u.IS_DELETED = FALSE OR u.IS_DELETED IS NULL)
ORDER BY u.CREATED_AT;
