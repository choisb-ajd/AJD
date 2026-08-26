-- ============================================================================
-- AFART 실적 대시보드 수기 업데이트용 매출 데이터 export 쿼리 (Snowflake)
--
-- 스키마 확인 완료: AJDCAR_PROD.PUBLIC (2026-08-25 SHOW TABLES로 실물 확인됨)
--   COUNSEL_APPLICATION / COUNSEL_VEHICLE / COUNSEL_STATUS_LOG / CUSTOMER /
--   USERS / MANAGER / GIFT / COMMON_CODE 전부 이 스키마에 있습니다.
--
-- 사용법: Snowflake 워크시트에서 그대로 실행 (DB/스키마 따로 안 골라도 됨,
--        아래 테이블명에 AJDCAR_PROD.PUBLIC.을 이미 붙여놨습니다)
--        → 결과창 우측 상단 "Download Results" → CSV로 다운로드
--        → afart-dashboard-demo/data/raw_query.csv 교체.
--
-- 그레인: 상담(counsel_application) x 차량(counsel_vehicle) 1행 = 기존 raw CSV와 동일.
--        차량이 여러 대인 상담은 여러 행으로 나옵니다 (기존 파일과 동일한 방식).
--
-- ⚠ 확인 필요한 사항:
--   1) "영업채널"은 counsel_application.channel_path를 CASE로 매핑해서 만듭니다
--      (DEALER_APP→딜러앱 / RENEWAL→갱신 / CS→CS / 그 외→기타). 확인 완료.
--   2) "가입유형"(CM/TM/OFFLINE)의 실제 소스 컬럼은 아직 못 찾았습니다.
--      원래 channel_path를 가입유형으로 가정했었는데, channel_path는 위처럼
--      영업채널(DEALER_APP/RENEWAL/CS)용 값이라 가입유형과는 다른 컬럼입니다.
--      일단 NULL로 비워뒀습니다 — 아시면 알려주세요.
-- ============================================================================

WITH status_agg AS (
  -- 상담별 상태 이력을 하나의 문자열로 압축 + "체결일자"(지급대기/가입완료 최초 도달 시각) 계산
  -- 대시보드가 이 문자열을 파싱해서 지급대기/가입취소/비교견적 이력을 전부 뽑아내므로
  -- 별도 쿼리 없이 이 한 컬럼으로 충분합니다.
  SELECT
    csl.counsel_id,
    MIN(CASE WHEN csl.new_counsel_status IN ('ACCUMULATE_PENDING', 'JOIN_COMPLETED')
             THEN csl.created_at END)                                   AS contract_at,
    LISTAGG(
      csl.new_counsel_status || '(' || TO_CHAR(csl.created_at, 'MM-DD HH24:MI') || ')',
      ' → '
    ) WITHIN GROUP (ORDER BY csl.created_at)                            AS status_history
  FROM AJDCAR_PROD.PUBLIC.COUNSEL_STATUS_LOG csl
  GROUP BY csl.counsel_id
),

-- 이름/연락처 마스킹 (기존 CSV들과 동일한 표기: "구*셉", "010****1234")
masked AS (
  SELECT
    ca.counsel_id,
    ca.customer_id,
    ca.user_id,
    ca.channel_path,
    ca.counsel_status,
    ca.insurance_type,
    ca.vehicle_usage_code,
    ca.join_insurer_code,
    ca.insurance_end_dt,
    ca.gift_id,
    ca.counsel_manager_id,
    cv.counsel_vehicle_id,
    cv.license_plate_number,
    cv.vin,
    cv.contract_amount,
    cu.customer_name,
    cu.customer_phone_number,
    u.user_id                                                          AS dealer_login_id,
    u.user_name                                                        AS dealer_name_raw,
    u.phone                                                            AS dealer_phone_raw,
    u.business_type,
    u.business_card_status,
    u.manager_id                                                       AS dealer_manager_id,
    u.sales_channel_id
  FROM AJDCAR_PROD.PUBLIC.COUNSEL_APPLICATION ca
  JOIN AJDCAR_PROD.PUBLIC.COUNSEL_VEHICLE cv ON cv.counsel_id = ca.counsel_id AND cv.is_deleted = 0
  JOIN AJDCAR_PROD.PUBLIC.CUSTOMER cu        ON cu.customer_id = ca.customer_id AND cu.is_deleted = 0
  LEFT JOIN AJDCAR_PROD.PUBLIC.USERS u        ON u.id = ca.user_id
  WHERE ca.is_deleted = 0
    AND ca.counsel_status IN ('ACCUMULATE_PENDING', 'JOIN_COMPLETED')   -- 체결 = 지급대기 + 가입완료
    AND (u.business_card_status IS NULL OR u.business_card_status <> 'REJECTED')  -- 탈퇴 딜러 제외
    -- 기간을 좁히고 싶으면 아래 주석 해제 (예: 최근 6개월)
    -- AND ca.created_at >= DATEADD('month', -6, CURRENT_DATE())
)

SELECT
  CASE m.channel_path
    WHEN 'DEALER_APP' THEN '딜러앱'
    WHEN 'RENEWAL'    THEN '갱신'
    WHEN 'CS'         THEN 'CS'
    ELSE '기타'
  END                                                                   AS "영업채널",
  m.counsel_id                                                         AS "상담ID",
  m.customer_id                                                        AS "고객ID",
  CASE
    WHEN LENGTH(m.customer_name) <= 1 THEN m.customer_name
    WHEN LENGTH(m.customer_name) = 2 THEN LEFT(m.customer_name, 1) || '*'
    ELSE LEFT(m.customer_name, 1) || REPEAT('*', LENGTH(m.customer_name) - 2) || RIGHT(m.customer_name, 1)
  END                                                                   AS "고객명",
  LEFT(REGEXP_REPLACE(m.customer_phone_number, '[^0-9]', ''), 3)
    || '****'
    || RIGHT(REGEXP_REPLACE(m.customer_phone_number, '[^0-9]', ''), 4) AS "연락처",
  m.license_plate_number                                               AS "차량번호",
  m.vin                                                                 AS "차대번호",
  m.contract_amount                                                    AS "보험료",
  m.join_insurer_code                                                  AS "가입보험사",
  NULL                                                                  AS "가입유형", -- TODO: 실제 소스 확인 후 채우기
  m.insurance_type                                                     AS "보험종류",
  m.vehicle_usage_code                                                 AS "차량구분",
  TO_CHAR(sa.contract_at, 'YYYY-MM-DD')                                AS "체결일자",
  TO_CHAR(m.insurance_end_dt, 'YYYY-MM-DD')                            AS "만기일자",
  m.counsel_status                                                     AS "현재상태",
  sa.status_history                                                    AS "상태전환이력",
  g.gift_name                                                          AS "주유권",
  LEFT(REGEXP_REPLACE(m.dealer_phone_raw, '[^0-9]', ''), 3)
    || '****'
    || RIGHT(REGEXP_REPLACE(m.dealer_phone_raw, '[^0-9]', ''), 4)      AS "딜러연락처",
  CASE
    WHEN LENGTH(m.dealer_name_raw) <= 1 THEN m.dealer_name_raw
    WHEN LENGTH(m.dealer_name_raw) = 2 THEN LEFT(m.dealer_name_raw, 1) || '*'
    ELSE LEFT(m.dealer_name_raw, 1) || REPEAT('*', LENGTH(m.dealer_name_raw) - 2) || RIGHT(m.dealer_name_raw, 1)
  END                                                                   AS "딜러이름",
  m.dealer_login_id                                                    AS "딜러ID",
  m.business_type                                                      AS "딜러유형",
  m.business_card_status                                               AS "딜러상태",
  cm.name                                                               AS "상담(체결)매니저",
  dm.name                                                               AS "딜러전담매니저"
FROM masked m
JOIN status_agg sa        ON sa.counsel_id = m.counsel_id
LEFT JOIN AJDCAR_PROD.PUBLIC.GIFT g           ON g.gift_id = m.gift_id
LEFT JOIN AJDCAR_PROD.PUBLIC.MANAGER cm       ON cm.id = m.counsel_manager_id
LEFT JOIN AJDCAR_PROD.PUBLIC.MANAGER dm       ON dm.id = m.dealer_manager_id
ORDER BY sa.contract_at DESC;
