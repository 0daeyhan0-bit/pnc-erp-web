-- ============================================================================
-- 차세대 ERP · 품목마스터(Phase②) nx 확장 스키마
--   근거: _schema/ITEM_MASTER_ANALYSIS.md (레거시 w_pr_master_010 + PR_M_ITEM 실측)
--   원칙: nx.item(19코어, BOM/원가 FK)은 변경금지·ADD만. 서브/밸브/이력은 1:1 신설.
--   승인(2026-07-23): 0%·상수 컬럼 제외 / 밸브=별도 item_valve / 위하고 나중
--   대상: PARTNER_ERP_TEST3.nx  (멱등 — 재실행 안전, GO 배치 구분)
-- ============================================================================

-- ── 1) nx.item 업무컬럼 ADD (기존 19코어 외, 중복 제외) ─────────────────────
IF COL_LENGTH('nx.item','item_group')         IS NULL ALTER TABLE nx.item ADD item_group         nvarchar(10)  NULL;   -- 품목군 PR001
GO
IF COL_LENGTH('nx.item','item_class')         IS NULL ALTER TABLE nx.item ADD item_class         nvarchar(2)   NULL;   -- 품목구분 PR008
GO
IF COL_LENGTH('nx.item','item_status')        IS NULL ALTER TABLE nx.item ADD item_status        nvarchar(2)   NULL;   -- 품목상태 1~9 (status='사용'과 별개)
GO
IF COL_LENGTH('nx.item','pipe_kind')          IS NULL ALTER TABLE nx.item ADD pipe_kind          nvarchar(4)   NULL;   -- 품목형태 PR021
GO
IF COL_LENGTH('nx.item','work_code')          IS NULL ALTER TABLE nx.item ADD work_code          nvarchar(4)   NULL;   -- 작업장(P1가공/P2 등)
GO
IF COL_LENGTH('nx.item','sale_cust')          IS NULL ALTER TABLE nx.item ADD sale_cust          nvarchar(10)  NULL;   -- 매출처 SALE_CUST_CODE1
GO
IF COL_LENGTH('nx.item','pur_gubun')          IS NULL ALTER TABLE nx.item ADD pur_gubun          nvarchar(2)   NULL;   -- 매입구분
GO
IF COL_LENGTH('nx.item','obtain_gubun')       IS NULL ALTER TABLE nx.item ADD obtain_gubun       nvarchar(2)   NULL;   -- 입수구분
GO
IF COL_LENGTH('nx.item','prod_rate')          IS NULL ALTER TABLE nx.item ADD prod_rate          smallint      NULL;   -- 생산율(수율) %
GO
IF COL_LENGTH('nx.item','kitting_min')        IS NULL ALTER TABLE nx.item ADD kitting_min        smallint      NULL;   -- 최소키팅
GO
IF COL_LENGTH('nx.item','sub_mat_flag')       IS NULL ALTER TABLE nx.item ADD sub_mat_flag       nvarchar(1)   NULL;   -- 부자재여부
GO
IF COL_LENGTH('nx.item','sub_mat_wh')         IS NULL ALTER TABLE nx.item ADD sub_mat_wh         nvarchar(10)  NULL;   -- 부자재 생산사용창고
GO
IF COL_LENGTH('nx.item','proc_gubun')         IS NULL ALTER TABLE nx.item ADD proc_gubun         nvarchar(1)   NULL;   -- 공정구분
GO
IF COL_LENGTH('nx.item','prod_tag')           IS NULL ALTER TABLE nx.item ADD prod_tag           nvarchar(1)   NULL;   -- 생산태그
GO
IF COL_LENGTH('nx.item','item_pipe_type')     IS NULL ALTER TABLE nx.item ADD item_pipe_type     nvarchar(20)  NULL;   -- 파이프타입
GO
IF COL_LENGTH('nx.item','item_pipe_material') IS NULL ALTER TABLE nx.item ADD item_pipe_material nvarchar(20)  NULL;   -- 파이프재질
GO
IF COL_LENGTH('nx.item','item_radius')        IS NULL ALTER TABLE nx.item ADD item_radius        nvarchar(20)  NULL;   -- 반경(R)
GO
IF COL_LENGTH('nx.item','item_pipe_id')       IS NULL ALTER TABLE nx.item ADD item_pipe_id       decimal(18,4) NULL;   -- 내경 = 외경 - 두께×2 (자동계산)
GO
IF COL_LENGTH('nx.item','dlvy_except_flag')   IS NULL ALTER TABLE nx.item ADD dlvy_except_flag   nvarchar(1)   NULL;   -- 납품제외
GO
IF COL_LENGTH('nx.item','set_except_day')     IS NULL ALTER TABLE nx.item ADD set_except_day     smallint      NULL;   -- 세트제외일
GO

-- ── 2) nx.item_sub (1:1) — PR_M_ITEM_SUB 실사용 필드만(죽은 QC_*/AQL_* 제외) ──
IF OBJECT_ID('nx.item_sub') IS NULL
CREATE TABLE nx.item_sub (
  item_code       nvarchar(30) NOT NULL PRIMARY KEY,
  insp_flag       nvarchar(1)  NULL,          -- 검사구분 F/N/S
  lg_obtain_flag  nvarchar(1)  NULL,          -- LG사급여부(make_type=4 자동)
  rack_no         nvarchar(20) NULL,          -- 적치(RACK)
  remarks         nvarchar(500) NULL,         -- 비고
  pack_kind       nvarchar(30) NULL,          -- 포장종류
  pack_qty        smallint     NULL,          -- 포장수량
  pur_lead_time   smallint     NULL,          -- 구매리드타임(일)
  prod_worker     nvarchar(10) NULL,          -- 생산작업자
  insp_worker     nvarchar(10) NULL,          -- 검사작업자
  min_pur_qty     int          NULL,          -- 최소구매수량
  safe_stock_qty  smallint     NULL,          -- 안전재고
  prod_step_memo  nvarchar(200) NULL,         -- 공정메모
  CONSTRAINT fk_item_sub_item FOREIGN KEY(item_code) REFERENCES nx.item(item_code)
);
GO

-- ── 3) nx.item_valve (1:1, 설치품 밸브 QC치수 — 272품목만, 본체 오염방지 분리) ──
IF OBJECT_ID('nx.item_valve') IS NULL
CREATE TABLE nx.item_valve (
  item_code       nvarchar(30) NOT NULL PRIMARY KEY,
  item_od         nvarchar(100) NULL,         -- 외경
  item_id         nvarchar(100) NULL,         -- 내경
  valve_type      nvarchar(400) NULL,
  s_w_type        nvarchar(400) NULL,
  h_s_type        nvarchar(400) NULL,
  n_s_type        nvarchar(400) NULL,
  add_item_type   nvarchar(400) NULL,
  size1 nvarchar(30) NULL, size1_limit nvarchar(30) NULL,
  size2 nvarchar(30) NULL, size2_limit nvarchar(30) NULL,
  size3 nvarchar(30) NULL, size3_limit nvarchar(30) NULL,
  size4 nvarchar(30) NULL, size4_limit nvarchar(30) NULL,
  size5 nvarchar(30) NULL, size5_limit nvarchar(30) NULL,
  size6 nvarchar(30) NULL, size6_limit nvarchar(30) NULL,
  size7 nvarchar(30) NULL, size7_limit nvarchar(30) NULL,
  size8 nvarchar(30) NULL, size8_limit nvarchar(30) NULL,
  CONSTRAINT fk_item_valve_item FOREIGN KEY(item_code) REFERENCES nx.item(item_code)
);
GO

-- ── 4) nx.item_his — 품번 변경 이력(PR_M_ITEM_HIS) ──────────────────────────
IF OBJECT_ID('nx.item_his') IS NULL
CREATE TABLE nx.item_his (
  his_id     bigint IDENTITY(1,1) PRIMARY KEY,
  old_code   nvarchar(30) NOT NULL,
  new_code   nvarchar(30) NOT NULL,
  change_dt  datetime     NOT NULL CONSTRAINT df_item_his_dt DEFAULT getdate(),
  user_id    nvarchar(20) NULL
);
GO
