-- ============================================================================
-- 차세대 ERP · 통합 BOM 스키마 (초안 v1, PostgreSQL)
-- 설계원칙
--   1) BOM은 "구성·소요량"만 저장한다. 단가는 일절 박지 않는다.
--   2) 모든 변동 단가(LG판가·사급가·LG인증동가·협력사LME운영가·동단가·임율·환율)는
--      "유효일자(effective-dated) 마스터"로 분리한다.  → 조정 시 '행 추가'만, BOM 일괄수정 없음.
--   3) 원가(내부용/실원가)는 저장하지 않고 "기준일 + 단가마스터 조인"으로 매번 재계산한다.
--   4) 공급원(조달 프로파일)은 후보를 다 보유하고, 발주·손익을 프로파일 단위로 구분한다.
--   5) 공정 담당(PNC/협력사)·부품 조달(사급/자체)은 프로파일에 귀속, 유효일자로 이벤트 변경.
-- 근거: PARTNER_ERP 실측 (PR_M_ITEM_BOM / CS_T_ITEM_PROC / PR_M_ITEM_ASSY_RT / PR_M_ITEM_COST
--       / CS_M_METERIAL_COST / CS_M_LABOR_COST_RATE / CM_T_LME_FX_RATE / SP_CS_견적서 로직)
-- ============================================================================

-- ── 기준 마스터 (거의 불변) ────────────────────────────────────────────────
CREATE TABLE partner (                       -- 거래처
  partner_code   varchar(10) PRIMARY KEY,
  partner_name   varchar(100) NOT NULL,
  partner_type   varchar(20)  NOT NULL,      -- LG / 협력사 / 원소재직거래 / 자사
  remark         text
);

CREATE TABLE item (                          -- 품목
  item_code      varchar(30) PRIMARY KEY,
  item_name      varchar(200) NOT NULL,
  item_spec      varchar(200),
  item_type      varchar(20)  NOT NULL,      -- 완제품 / 서브ASSY / 부품 / 부자재 / 원소재
  metal_gubun    varchar(10),                -- CU/STS/AL/FE/고강도
  use_gubun      varchar(10),                -- 절삭 / 설치   (동단가 소스 결정)
  diam           numeric(18,4),
  thick          numeric(18,4),
  length         numeric(18,4),
  net_weight     numeric(18,6),              -- 순중량(동 무게) → 원자재비·LME 산출
  unit           varchar(10)  NOT NULL DEFAULT 'EA',
  status         varchar(10)  NOT NULL DEFAULT '사용'
);

CREATE TABLE process_master (                -- 공정 마스터
  proc_code      varchar(10) PRIMARY KEY,
  proc_name      varchar(100) NOT NULL,
  proc_group     varchar(20)  NOT NULL,      -- 절삭 / 조립 / 단품 / 간접(관리·운반·이윤)
  std_st         numeric(18,2)              -- 표준공수(참고)
);

-- ── BOM 구성 (구조만 · 단가 없음) ──────────────────────────────────────────
CREATE TABLE bom_header (
  bom_id         bigserial PRIMARY KEY,
  item_code      varchar(30) NOT NULL REFERENCES item,
  version        int         NOT NULL DEFAULT 1,
  apply_from     date        NOT NULL,       -- BOM 유효 시작
  apply_to       date,                       -- null = 현재
  status         varchar(10) NOT NULL DEFAULT '확정',
  UNIQUE(item_code, version)
);

CREATE TABLE bom_line (
  bom_id         bigint      NOT NULL REFERENCES bom_header,
  seq            int         NOT NULL,
  child_item     varchar(30) NOT NULL REFERENCES item,   -- 서브ASSY면 그 서브품목 참조(재사용)
  qty            numeric(18,6) NOT NULL DEFAULT 1,
  node_type      varchar(20) NOT NULL,       -- 서브ASSY / 부품 / 부자재 / 키팅
  sagub_default  boolean     NOT NULL DEFAULT false,     -- 기본 사급 여부(프로파일서 override)
  is_optional    boolean     NOT NULL DEFAULT false,     -- 특정 프로파일에만 포함(예: 태국 SOCKET)
  PRIMARY KEY(bom_id, seq)
);

CREATE TABLE routing (                       -- 품목별 공정 배정(라우팅)
  item_code      varchar(30) NOT NULL REFERENCES item,
  proc_code      varchar(10) NOT NULL REFERENCES process_master,
  seq            int,
  work_qty       numeric(18,4),              -- 작업량
  prod_uph       numeric(18,4),              -- UPH (절삭계통)
  cost_gubun     varchar(2),                 -- 3=임율 8=중량 9=적용율
  PRIMARY KEY(item_code, proc_code)
);

-- ── 조달 프로파일 (공급원 후보 · 공정담당 · 부품조달) ───────────────────────
CREATE TABLE sourcing_profile (
  profile_id     bigserial PRIMARY KEY,
  item_code      varchar(30) NOT NULL REFERENCES item,   -- 이 서브/완제품의 조달
  profile_name   varchar(50) NOT NULL,       -- 내부용 / 명진 / 미래 / 태국
  supply_gubun   varchar(20) NOT NULL,       -- 자체 / 유상사급 / 매입
  vendor_code    varchar(10) REFERENCES partner,
  lme_flag       boolean     NOT NULL DEFAULT false,     -- LME 대상(유상사급)
  apply_from     date        NOT NULL,
  apply_to       date,
  is_active      boolean     NOT NULL DEFAULT true,
  legacy_code    varchar(30)                 -- 구 접미사 품번(이관 추적)
);

CREATE TABLE profile_process_split (         -- 공정별 담당(PNC/협력사) · 이벤트 시에만 변경
  profile_id     bigint      NOT NULL REFERENCES sourcing_profile,
  proc_code      varchar(10) NOT NULL REFERENCES process_master,
  performer      varchar(10) NOT NULL,       -- PNC / 협력사
  apply_from     date        NOT NULL,
  apply_to       date,
  PRIMARY KEY(profile_id, proc_code, apply_from)
);

CREATE TABLE profile_part_supply (           -- 부품 조달구분(PNC사급 / 협력사자체)
  profile_id     bigint      NOT NULL REFERENCES sourcing_profile,
  child_item     varchar(30) NOT NULL REFERENCES item,
  supply_by      varchar(12) NOT NULL,       -- PNC사급 / 협력사자체
  PRIMARY KEY(profile_id, child_item)
);

-- ── 시계열 단가 마스터군 (유효일자 · 조정 시 '행 추가'만) ────────────────────
CREATE TABLE price_item (                    -- 품목 단가(매입 / 사급가공 / LG판가 / 사급가)
  item_code      varchar(30) NOT NULL REFERENCES item,
  price_type     varchar(20) NOT NULL,       -- 매입 / 사급가공 / LG판가 / 사급가
  vendor_code    varchar(10),
  currency       varchar(3)  NOT NULL DEFAULT 'KRW',
  apply_ym       char(6)     NOT NULL,        -- 적용 연월 (YYYYMM)
  price          numeric(18,4) NOT NULL,
  PRIMARY KEY(item_code, price_type, vendor_code, apply_ym)
);

CREATE TABLE price_metal (                    -- 동단가(절삭=LG유상사급 인증가 / 설치=직거래 거래처별 산식가)
  metal_gubun    varchar(10) NOT NULL,
  use_gubun      varchar(10) NOT NULL,        -- 절삭 / 설치
  vendor_code    varchar(10) NOT NULL,        -- LG / LS메탈 / 부광금속 / 대동신관 / 하이량 …
  apply_ym       char(6)     NOT NULL,
  currency       varchar(3)  NOT NULL DEFAULT 'KRW',
  unit_price     numeric(18,4) NOT NULL,       -- 최종 동단가
  lme_avg        numeric(18,4),               -- (직거래 산식) 전월 LME 평균
  fx_rate        numeric(18,4),               -- 전월 평균 환율
  proc_cost      numeric(18,4),               -- 가공비
  premium        numeric(18,4),               -- 프리미엄
  PRIMARY KEY(metal_gubun, use_gubun, vendor_code, apply_ym)
);

CREATE TABLE price_lme_lg (                    -- LG 인증 동가(LME 인정가) · 월
  metal_gubun    varchar(10) NOT NULL,
  apply_ym       char(6)     NOT NULL,
  lg_recog_price numeric(18,4) NOT NULL,
  PRIMARY KEY(metal_gubun, apply_ym)
);

CREATE TABLE price_lme_partner (              -- 협력사 LME 운영가 · 유효기간(조정 시에만 새 행)
  vendor_code    varchar(10) NOT NULL REFERENCES partner,
  metal_gubun    varchar(10) NOT NULL,
  apply_from     date        NOT NULL,
  apply_to       date,
  oper_price     numeric(18,4) NOT NULL,
  PRIMARY KEY(vendor_code, metal_gubun, apply_from)
);

CREATE TABLE labor_rate (                     -- 임율 · 월
  labor_tag      varchar(2)  NOT NULL DEFAULT '3',
  apply_ym       char(6)     NOT NULL,
  rate           numeric(18,2) NOT NULL,
  PRIMARY KEY(labor_tag, apply_ym)
);

CREATE TABLE fx_rate (                         -- 환율 · 월
  currency       varchar(3)  NOT NULL,
  apply_ym       char(6)     NOT NULL,
  rate           numeric(18,4) NOT NULL,
  PRIMARY KEY(currency, apply_ym)
);

-- ── 실적/거래 (손익 집계 · 다음 단계 상세화) ────────────────────────────────
CREATE TABLE plan_sourcing (                  -- 생산계획 × 품목 × 프로파일 배분(구분 확정)
  plan_id        bigint      NOT NULL,
  item_code      varchar(30) NOT NULL REFERENCES item,
  profile_id     bigint      NOT NULL REFERENCES sourcing_profile,
  plan_qty       numeric(18,4) NOT NULL,
  PRIMARY KEY(plan_id, item_code, profile_id)
);

CREATE TABLE partner_po (                      -- 협력사 PO (프로파일 구분 각인)
  po_id          bigserial PRIMARY KEY,
  profile_id     bigint      NOT NULL REFERENCES sourcing_profile,
  order_date     date        NOT NULL,
  order_qty      numeric(18,4) NOT NULL
);

CREATE TABLE sagub_issue (                     -- 유상사급 원소재 출고(무게·매출)
  issue_id       bigserial PRIMARY KEY,
  profile_id     bigint      NOT NULL REFERENCES sourcing_profile,
  item_code      varchar(30) NOT NULL REFERENCES item,   -- 사급 원소재/반제품
  issue_date     date        NOT NULL,
  issue_qty      numeric(18,4) NOT NULL,
  cu_weight      numeric(18,6)               -- 사급 동 무게(LME 정산용)
);

CREATE TABLE receipt (                         -- 입고(프로파일별) · 손익 수량 소스
  receipt_id     bigserial PRIMARY KEY,
  profile_id     bigint      NOT NULL REFERENCES sourcing_profile,
  item_code      varchar(30) NOT NULL REFERENCES item,
  receipt_date   date        NOT NULL,
  receipt_qty    numeric(18,4) NOT NULL,
  process_gubun  varchar(12)                 -- 직납 / 추가가공
);

-- ── 원가는 테이블이 아니라 "기준일 파라미터 함수/뷰"로 재계산 ────────────────
-- fn_cost(item_code, profile_id, base_date) →
--   재료비(원자재비 = net_weight × 동단가@기준일 / 부자재비 = 부품 매입가@기준일 / LG사급비)
--   + 가공비(PNC 담당 공정 Σ ST×임율@기준일 ÷ UPH)
--   + 일반관리비 + 이윤 + LME차액(= (LG인증동가 − 협력사LME운영가)@기준일 × 무게)
--   = 실원가 ;  손익 = LG판가@기준일 − 실원가
-- 내부용 = 전 공정을 PNC 수행 가정(profile=내부용) 으로 같은 함수 재사용.
