-- nx.PU_T_CUT_DTL — 가공바코드 실적이력(레거시 dbo.PU_T_CUT_DTL 구조 동일)
--
-- 용도: 웹 '가공바코드 실적처리'(w_pr_input_018 이식)가 실적/취소 이력을 쌓는 대상.
--       nx 에 이 테이블이 없으면 실적처리가 500 으로 실패한다.
-- 실행: 운영 배포 시 1회. 재실행해도 안전(있으면 건너뜀).
-- ★nx(PARTNER_ERP_TEST3)에만 생성 — 라이브 PARTNER_ERP 는 절대 건드리지 않는다(CLAUDE.md §1-1).
--
-- PK = (LINE_NO, ITEM_CODE, MAT_CODE, CUT_YMD, CUT_HMS) 5개 복합키(라이브 동일).
--   같은 초에 같은 자도번을 두 번 등록하면 중복키가 나므로,
--   레거시 018 은 f_get_today() 후 1초 지연(sleep(1))으로 회피한다.
USE PARTNER_ERP_TEST3;
GO
IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.TABLES
               WHERE TABLE_SCHEMA='nx' AND TABLE_NAME='PU_T_CUT_DTL')
BEGIN
  CREATE TABLE nx.PU_T_CUT_DTL(
    [LINE_NO]           varchar(10)   NOT NULL,
    [ITEM_CODE]         varchar(20)   NOT NULL,
    [MAT_CODE]          varchar(20)   NOT NULL,
    [CUT_YMD]           varchar(6)    NOT NULL,
    [CUT_HMS]           varchar(6)    NOT NULL,
    [CUT_QTY]           int           NULL,
    [ERR_QTY]           int           NULL,
    [CUT_USER_ID]       varchar(20)   NULL,
    [ITEM_DIAM]         numeric(18,4) NULL,
    [ITEM_THICK]        numeric(18,4) NULL,
    [ITEM_WEIGHT]       decimal(11,4) NULL,
    [CUT_WEIGHT]        decimal(11,4) NULL,
    [BOX_NO]            int           NULL,
    [MAT_IN_CUST_CODE]  varchar(10)   NULL,
    [ITEM_WORK_CODE]    varchar(10)   NULL,
    [ITEM_IN_CUST_CODE] varchar(10)   NULL,
    [MAT_WORK_CODE]     varchar(10)   NULL,
    [INSERT_USER_ID]    varchar(20)   NULL,
    [INSERT_DATETIME]   datetime      NULL,
    [INSERT_IP]         varchar(20)   NULL,
    [INSERT_COMPUTER]   varchar(20)   NULL,
    [INSERT_WINDOW]     varchar(30)   NULL,
    [mix_gagong]        tinyint       NULL,
    [WH_CUST_CODE]      varchar(10)   NULL,
    [GAGONG_PROC_CODE]  varchar(10)   NULL,
    CONSTRAINT PK_nx_PU_T_CUT_DTL PRIMARY KEY CLUSTERED
      ([LINE_NO], [ITEM_CODE], [MAT_CODE], [CUT_YMD], [CUT_HMS])
  );
  CREATE INDEX IX_nx_cutdtl_box ON nx.PU_T_CUT_DTL(BOX_NO);
  CREATE INDEX IX_nx_cutdtl_ymd ON nx.PU_T_CUT_DTL(CUT_YMD);
  PRINT 'nx.PU_T_CUT_DTL 생성 완료';
END
ELSE
  PRINT 'nx.PU_T_CUT_DTL 이미 존재 - 건너뜀';
GO
