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
-- 확인 완료된 매핑:
--   - "유입채널" = counsel_application.channel_path (DEALER_APP→딜러앱 / RENEWAL→갱신 / CS→CS / 그 외→기타)
--   - "가입유형" = counsel_application.subscription_type (원본 값 그대로 사용)
--   - "가입보험사" = counsel_application.join_insurer_code를 한글명으로 CASE 매핑
--   - "체결일자" = 현재 상태가 지급대기(ACCUMULATE_PENDING)면 상태이력에서 최초로
--     그 상태에 도달한 시각, 가입완료(JOIN_COMPLETED)면 counsel_application.join_completed_at,
--     가입취소(JOIN_CANCELLED)면 join_completed_at(성사 이력 없이 취소된 건은 NULL)
--
-- 대시보드 "가입취소 리스트"용으로 counsel_status = 'JOIN_CANCELLED'인 건도 함께 내려받습니다.
-- 체결(지급대기·가입완료) 집계에는 이 건들이 섞이지 않는데, 대시보드가 "체결일자"가 비어있는
-- 행은 체결 관련 집계(KPI·기간별 실적·매니저 랭킹)에서 자동으로 제외하기 때문입니다.
-- ============================================================================

WITH status_agg AS (
  -- 상담별 상태 이력을 하나의 문자열로 압축 + 지급대기 최초 도달 시각(pending_at) 계산.
  -- status_history는 대시보드가 파싱해서 지급대기/가입취소/비교견적 이력을 전부 뽑아내므로
  -- 별도 쿼리 없이 이 한 컬럼으로 충분합니다.
  SELECT
    csl.counsel_id,
    MIN(CASE WHEN csl.new_counsel_status = 'ACCUMULATE_PENDING'
             THEN csl.created_at END)                                   AS pending_at,
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
    ca.subscription_type,
    ca.insurance_type,
    ca.vehicle_usage_code,
    ca.join_insurer_code,
    ca.insurance_end_dt,
    ca.join_completed_at,
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
  JOIN AJDCAR_PROD.PUBLIC.COUNSEL_VEHICLE cv ON cv.counsel_id = ca.counsel_id AND cv.is_deleted = FALSE
  JOIN AJDCAR_PROD.PUBLIC.CUSTOMER cu        ON cu.customer_id = ca.customer_id AND cu.is_deleted = FALSE
  LEFT JOIN AJDCAR_PROD.PUBLIC.USERS u        ON u.id = ca.user_id
  WHERE ca.is_deleted = FALSE
    AND ca.counsel_status IN ('ACCUMULATE_PENDING', 'JOIN_COMPLETED', 'JOIN_CANCELLED')
    -- 지급대기 + 가입완료(체결) + 가입취소(가입취소 리스트용). 체결 집계에는 가입취소 건이 안 섞입니다.
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
  END                                                                   AS "유입채널",
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
  CASE m.join_insurer_code
    WHEN 'AXA'      THEN 'AXA손해보험'
    WHEN 'CARROT'   THEN '캐롯손해보험'
    WHEN 'DB'       THEN 'DB손해보험'
    WHEN 'HANA'     THEN '하나손해보험'
    WHEN 'HANHWA'   THEN '한화손해보험'
    WHEN 'HEUNGKUK' THEN '흥국화재'
    WHEN 'HYUNDAI'  THEN '현대해상'
    WHEN 'KB'       THEN 'KB손해보험'
    WHEN 'LOTTE'    THEN '롯데손해보험'
    WHEN 'MERITZ'   THEN '메리츠화재'
    WHEN 'SAMSUNG'  THEN '삼성화재'
    ELSE m.join_insurer_code
  END                                                                   AS "가입보험사",
  m.subscription_type                                                  AS "가입유형",
  m.insurance_type                                                     AS "보험종류",
  m.vehicle_usage_code                                                 AS "차량구분",
  TO_CHAR(
    CASE WHEN m.counsel_status = 'ACCUMULATE_PENDING' THEN sa.pending_at
         ELSE m.join_completed_at
    END, 'YYYY-MM-DD'
  )                                                                     AS "체결일자",
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
ORDER BY
  CASE WHEN m.counsel_status = 'ACCUMULATE_PENDING' THEN sa.pending_at ELSE m.join_completed_at END DESC NULLS LAST;
