-- ============================================================
-- 3_계약 시트 형식 — Snowflake에서 계약 내역 추출
-- Snowsight에서 실행 후 CSV 다운로드
-- ============================================================

WITH CONTRACT AS (
    SELECT CA.COUNSEL_ID,
           CA.USER_ID,
           CA.COUNSEL_MANAGER_ID,
           CA.SUBSCRIPTION_TYPE,
           CA.CHANNEL_PATH,
           CA.JOIN_INSURER_CODE,
           CA.VEHICLE_USAGE_CODE,
           CA.GIFT_ID,
           CA.CUSTOMER_ID,
           CV.COUNSEL_VEHICLE_ID,
           CV.CONTRACT_AMOUNT,
           CV.REGISTRATION_TYPE,
           CV.EXIST_INSURER_CODE,
           CV.LICENSE_PLATE_NUMBER,
           CV.VIN,
           CV.EXIST_INSURANCE_END_DT,
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
)
SELECT
    ROW_NUMBER() OVER (ORDER BY ct.CONTRACT_AT) AS "seq",

    -- 영업채널
    CASE
        WHEN ct.SUBSCRIPTION_TYPE = 'DEALER_APP' THEN '딜러앱'
        WHEN ct.SUBSCRIPTION_TYPE = 'CS'         THEN 'CS'
        WHEN ct.SUBSCRIPTION_TYPE = 'RENEWAL'    THEN '갱신'
        ELSE '기타'
    END AS "영업채널",

    -- 고객명
    C.CUSTOMER_NAME AS "고객명",

    -- 연락처
    C.CUSTOMER_PHONE_NUMBER AS "연락처",

    -- 차량번호
    COALESCE(ct.LICENSE_PLATE_NUMBER, ct.VIN) AS "차량번호",

    -- 보험료 (원수보험료)
    ct.CONTRACT_AMOUNT AS "보험료",

    -- 가입보험사
    ct.JOIN_INSURER_CODE AS "가입보험사",

    -- 기존보험사
    ct.EXIST_INSURER_CODE AS "기존보험사",

    -- 가입경로/유형 (CM/TM)
    CASE
        WHEN ct.CHANNEL_PATH LIKE '%CM%' THEN 'CM'
        WHEN ct.CHANNEL_PATH LIKE '%TM%' THEN 'TM'
        ELSE ct.CHANNEL_PATH
    END AS "가입경로",

    -- 만기일자
    ct.EXIST_INSURANCE_END_DT AS "만기일자",

    -- 만기월
    LPAD(MONTH(ct.EXIST_INSURANCE_END_DT), 2, '0') || '월' AS "만기월",

    -- 영업용 여부
    CASE WHEN ct.VEHICLE_USAGE_CODE = 'BUSINESS' THEN 'Y' ELSE NULL END AS "영업용여부",

    -- 체결일자
    ct.CONTRACT_AT::DATE AS "체결일자",

    -- 체결월
    TO_CHAR(ct.CONTRACT_AT, 'YY') || '-' || LPAD(MONTH(ct.CONTRACT_AT), 2, '0') || 'm' AS "체결월",

    -- 체결주차
    TO_CHAR(ct.CONTRACT_AT, 'YY') || '.' || LPAD(WEEKOFYEAR(ct.CONTRACT_AT), 2, '0') || 'w' AS "체결주차",

    -- 체결/담당매니저
    m.NAME AS "체결/담당매니저",

    -- 주유권
    g.GIFT_NAME AS "주유권",

    -- 딜러이름
    u.USER_NAME AS "딜러이름",

    -- 딜러연락처
    u.PHONE AS "딜러연락처",

    -- 딜러ID
    u.USER_ID AS "딜러ID",

    -- 딜러브랜드
    u.PRIMARY_AFFILIATION AS "딜러브랜드",

    -- 딜러지점
    u.SECONDARY_AFFILIATION AS "딜러지점",

    -- 자사갱신 여부
    CASE WHEN ct.EXIST_INSURER_CODE IS NOT NULL
              AND ct.EXIST_INSURER_CODE = ct.JOIN_INSURER_CODE
         THEN 'Y' ELSE NULL
    END AS "자사갱신여부"

FROM CONTRACT ct
JOIN AJDCAR_PROD.PUBLIC.CUSTOMER C
     ON C.CUSTOMER_ID = ct.CUSTOMER_ID
LEFT JOIN AJDCAR_PROD.PUBLIC.USERS u
     ON u.ID = ct.USER_ID
LEFT JOIN AJDCAR_PROD.PUBLIC.MANAGER m
     ON m.ID = ct.COUNSEL_MANAGER_ID
LEFT JOIN AJDCAR_PROD.PUBLIC.GIFT g
     ON g.GIFT_ID = ct.GIFT_ID
ORDER BY ct.CONTRACT_AT;
