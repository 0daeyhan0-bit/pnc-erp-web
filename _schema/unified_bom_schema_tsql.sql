-- ============================================================================
-- 차세대 ERP · 통합 BOM 스키마 (T-SQL, PARTNER_ERP_TEST3 · 스키마 [nx])
-- 원칙: BOM=구성만 / 단가=유효일자 마스터 분리 / 원가=기준일 재계산 / 조달 프로파일
-- 구 817테이블과 격리 위해 별도 스키마 [nx]. 한글 데이터 → NVARCHAR.
-- ============================================================================
IF SCHEMA_ID('nx') IS NULL EXEC('CREATE SCHEMA nx');
GO
-- 재생성(개발단계): 자식→부모 순 DROP
IF OBJECT_ID('nx.receipt') IS NOT NULL DROP TABLE nx.receipt;
IF OBJECT_ID('nx.sagub_issue') IS NOT NULL DROP TABLE nx.sagub_issue;
IF OBJECT_ID('nx.partner_po') IS NOT NULL DROP TABLE nx.partner_po;
IF OBJECT_ID('nx.plan_sourcing') IS NOT NULL DROP TABLE nx.plan_sourcing;
IF OBJECT_ID('nx.profile_part_supply') IS NOT NULL DROP TABLE nx.profile_part_supply;
IF OBJECT_ID('nx.profile_process_split') IS NOT NULL DROP TABLE nx.profile_process_split;
IF OBJECT_ID('nx.sourcing_profile') IS NOT NULL DROP TABLE nx.sourcing_profile;
IF OBJECT_ID('nx.bom_line') IS NOT NULL DROP TABLE nx.bom_line;
IF OBJECT_ID('nx.bom_header') IS NOT NULL DROP TABLE nx.bom_header;
IF OBJECT_ID('nx.routing') IS NOT NULL DROP TABLE nx.routing;
IF OBJECT_ID('nx.price_item') IS NOT NULL DROP TABLE nx.price_item;
IF OBJECT_ID('nx.price_metal') IS NOT NULL DROP TABLE nx.price_metal;
IF OBJECT_ID('nx.price_lme_lg') IS NOT NULL DROP TABLE nx.price_lme_lg;
IF OBJECT_ID('nx.price_lme_partner') IS NOT NULL DROP TABLE nx.price_lme_partner;
IF OBJECT_ID('nx.labor_rate') IS NOT NULL DROP TABLE nx.labor_rate;
IF OBJECT_ID('nx.fx_rate') IS NOT NULL DROP TABLE nx.fx_rate;
IF OBJECT_ID('nx.process_master') IS NOT NULL DROP TABLE nx.process_master;
IF OBJECT_ID('nx.item') IS NOT NULL DROP TABLE nx.item;
IF OBJECT_ID('nx.partner') IS NOT NULL DROP TABLE nx.partner;
GO
-- ── 기준 마스터 ────────────────────────────────────────────────────────────
CREATE TABLE nx.partner (
  partner_code  NVARCHAR(10)  NOT NULL PRIMARY KEY,
  partner_name  NVARCHAR(100) NOT NULL,
  partner_type  NVARCHAR(20)  NOT NULL,       -- LG / 협력사 / 원소재직거래 / 자사
  remark        NVARCHAR(MAX)
);
CREATE TABLE nx.item (
  item_code   NVARCHAR(30)  NOT NULL PRIMARY KEY,
  item_name   NVARCHAR(200) NOT NULL,
  item_spec   NVARCHAR(200),
  item_type   NVARCHAR(20)  NOT NULL,          -- 완제품/서브ASSY/부품/부자재/원소재
  sgroup      NVARCHAR(10),                    -- 소분류(110/120/130/220/230/310/910) → 재료비 3분해
  metal_gubun NVARCHAR(10),                    -- CU/STS/AL/FE/고강도
  use_gubun   NVARCHAR(10),                    -- 절삭/설치 (동단가 소스)
  diam        DECIMAL(18,4), thick DECIMAL(18,4), length DECIMAL(18,4),
  net_weight  DECIMAL(18,6),                   -- 순중량(동무게)
  unit        NVARCHAR(10)  NOT NULL DEFAULT 'EA',
  make_type   NVARCHAR(2),                     -- 생산구분 1사내/2외주/5직납
  in_cust     NVARCHAR(10),                    -- 제조처(거래처=매입가 결정)
  silver_flag BIT NOT NULL DEFAULT 0,          -- 은납/용접봉(가공비 조립노무 귀속)
  status      NVARCHAR(10)  NOT NULL DEFAULT '사용'
);
CREATE TABLE nx.process_master (
  proc_code  NVARCHAR(10)  NOT NULL PRIMARY KEY,
  proc_name  NVARCHAR(100) NOT NULL,
  proc_group NVARCHAR(20)  NOT NULL,           -- 절삭/조립/단품/간접
  sort_seq   INT,
  calc_type  NVARCHAR(2),                      -- 3임율/8중량/9적용율
  std_st     DECIMAL(18,2)
);
-- ── BOM 구성(구조만) ──────────────────────────────────────────────────────
CREATE TABLE nx.bom_header (
  bom_id     BIGINT IDENTITY(1,1) PRIMARY KEY,
  item_code  NVARCHAR(30) NOT NULL REFERENCES nx.item(item_code),
  version    INT NOT NULL DEFAULT 1,
  apply_from DATE NOT NULL, apply_to DATE,
  status     NVARCHAR(10) NOT NULL DEFAULT '확정',
  CONSTRAINT uq_bom_ver UNIQUE(item_code, version)
);
CREATE TABLE nx.bom_line (
  bom_id     BIGINT NOT NULL REFERENCES nx.bom_header(bom_id),
  seq        INT NOT NULL,
  child_item NVARCHAR(30) NOT NULL REFERENCES nx.item(item_code),
  qty        DECIMAL(18,6) NOT NULL DEFAULT 1,
  node_type  NVARCHAR(20) NOT NULL,            -- 서브ASSY/부품/부자재/키팅
  cs_calc_except BIT NOT NULL DEFAULT 0,       -- 원가계산 제외(선택안된 대체서브)
  lme_except     BIT NOT NULL DEFAULT 0,
  sagub_default  BIT NOT NULL DEFAULT 0,
  is_optional    BIT NOT NULL DEFAULT 0,
  CONSTRAINT pk_bom_line PRIMARY KEY(bom_id, seq)
);
CREATE TABLE nx.routing (
  item_code NVARCHAR(30) NOT NULL REFERENCES nx.item(item_code),
  proc_code NVARCHAR(10) NOT NULL REFERENCES nx.process_master(proc_code),
  db_item   NVARCHAR(30),                      -- 공정 귀속 부모(은납/용접봉 노무)
  seq       INT,
  work_qty  DECIMAL(18,4),
  prod_uph  DECIMAL(18,4),
  calc_gubun NVARCHAR(2),                      -- 3임율/8중량/9적용율(91일반/92운반/93이윤)
  CONSTRAINT pk_routing PRIMARY KEY(item_code, proc_code)
);
-- ── 조달 프로파일 ──────────────────────────────────────────────────────────
CREATE TABLE nx.sourcing_profile (
  profile_id   BIGINT IDENTITY(1,1) PRIMARY KEY,
  item_code    NVARCHAR(30) NOT NULL REFERENCES nx.item(item_code),
  profile_name NVARCHAR(50) NOT NULL,          -- 내부용/명진/미래/태국
  supply_gubun NVARCHAR(20) NOT NULL,          -- 자체/유상사급/매입
  vendor_code  NVARCHAR(10) REFERENCES nx.partner(partner_code),
  lme_flag     BIT NOT NULL DEFAULT 0,
  apply_from   DATE NOT NULL, apply_to DATE,
  is_active    BIT NOT NULL DEFAULT 1,
  legacy_code  NVARCHAR(30)
);
CREATE TABLE nx.profile_process_split (
  profile_id BIGINT NOT NULL REFERENCES nx.sourcing_profile(profile_id),
  proc_code  NVARCHAR(10) NOT NULL REFERENCES nx.process_master(proc_code),
  performer  NVARCHAR(10) NOT NULL,            -- PNC/협력사
  apply_from DATE NOT NULL, apply_to DATE,
  CONSTRAINT pk_pps PRIMARY KEY(profile_id, proc_code, apply_from)
);
CREATE TABLE nx.profile_part_supply (
  profile_id BIGINT NOT NULL REFERENCES nx.sourcing_profile(profile_id),
  child_item NVARCHAR(30) NOT NULL REFERENCES nx.item(item_code),
  supply_by  NVARCHAR(12) NOT NULL,            -- PNC사급/협력사자체
  CONSTRAINT pk_ppsup PRIMARY KEY(profile_id, child_item)
);
-- ── 시계열 단가 마스터군 ───────────────────────────────────────────────────
CREATE TABLE nx.price_item (
  item_code  NVARCHAR(30) NOT NULL REFERENCES nx.item(item_code),
  price_type NVARCHAR(20) NOT NULL,            -- 매입/사급가공/LG판가/사급가
  vendor_code NVARCHAR(10) NOT NULL DEFAULT '',
  currency   NVARCHAR(3) NOT NULL DEFAULT 'KRW',
  apply_ymd  CHAR(6) NOT NULL,                 -- 적용일 YYMMDD
  price      DECIMAL(18,4) NOT NULL,
  CONSTRAINT pk_price_item PRIMARY KEY(item_code, price_type, vendor_code, apply_ymd)
);
CREATE TABLE nx.price_metal (
  metal_gubun NVARCHAR(10) NOT NULL,
  diam        DECIMAL(18,4) NOT NULL DEFAULT 0,
  thick       DECIMAL(18,4) NOT NULL DEFAULT 0,
  apply_ym    CHAR(6) NOT NULL,                -- YYYYMM
  std_price   DECIMAL(18,4) NOT NULL,          -- 표준동가(TOT_COST)
  partner_price DECIMAL(18,4),                 -- 협력사동가(TOT_COST_SUB) → LME차액
  CONSTRAINT pk_price_metal PRIMARY KEY(metal_gubun, diam, thick, apply_ym)
);
CREATE TABLE nx.labor_rate (
  labor_tag NVARCHAR(2) NOT NULL DEFAULT '3',
  apply_ym  CHAR(6) NOT NULL,
  rate      DECIMAL(18,2) NOT NULL,
  CONSTRAINT pk_labor PRIMARY KEY(labor_tag, apply_ym)
);
CREATE TABLE nx.fx_rate (
  currency NVARCHAR(3) NOT NULL,               -- USD/EUR/YEN/RMB(CNY)
  apply_ymd CHAR(6) NOT NULL,
  rate     DECIMAL(18,4) NOT NULL,
  CONSTRAINT pk_fx PRIMARY KEY(currency, apply_ymd)
);
CREATE TABLE nx.price_lme_lg (                  -- LG 인증 동가 · 월
  metal_gubun NVARCHAR(10) NOT NULL, apply_ym CHAR(6) NOT NULL,
  lg_recog_price DECIMAL(18,4) NOT NULL,
  CONSTRAINT pk_lme_lg PRIMARY KEY(metal_gubun, apply_ym)
);
CREATE TABLE nx.price_lme_partner (            -- 협력사 LME 운영가 · 유효기간
  vendor_code NVARCHAR(10) NOT NULL REFERENCES nx.partner(partner_code),
  metal_gubun NVARCHAR(10) NOT NULL,
  apply_from DATE NOT NULL, apply_to DATE,
  oper_price DECIMAL(18,4) NOT NULL,
  CONSTRAINT pk_lme_p PRIMARY KEY(vendor_code, metal_gubun, apply_from)
);
-- ── 실적/거래(손익) ────────────────────────────────────────────────────────
CREATE TABLE nx.plan_sourcing (
  plan_id BIGINT NOT NULL, item_code NVARCHAR(30) NOT NULL REFERENCES nx.item(item_code),
  profile_id BIGINT NOT NULL REFERENCES nx.sourcing_profile(profile_id),
  plan_qty DECIMAL(18,4) NOT NULL,
  CONSTRAINT pk_plan PRIMARY KEY(plan_id, item_code, profile_id)
);
CREATE TABLE nx.partner_po (
  po_id BIGINT IDENTITY(1,1) PRIMARY KEY,
  profile_id BIGINT NOT NULL REFERENCES nx.sourcing_profile(profile_id),
  order_date DATE NOT NULL, order_qty DECIMAL(18,4) NOT NULL
);
CREATE TABLE nx.sagub_issue (
  issue_id BIGINT IDENTITY(1,1) PRIMARY KEY,
  profile_id BIGINT NOT NULL REFERENCES nx.sourcing_profile(profile_id),
  item_code NVARCHAR(30) NOT NULL REFERENCES nx.item(item_code),
  issue_date DATE NOT NULL, issue_qty DECIMAL(18,4) NOT NULL, cu_weight DECIMAL(18,6)
);
CREATE TABLE nx.receipt (
  receipt_id BIGINT IDENTITY(1,1) PRIMARY KEY,
  profile_id BIGINT NOT NULL REFERENCES nx.sourcing_profile(profile_id),
  item_code NVARCHAR(30) NOT NULL REFERENCES nx.item(item_code),
  receipt_date DATE NOT NULL, receipt_qty DECIMAL(18,4) NOT NULL,
  process_gubun NVARCHAR(12)
);
GO
