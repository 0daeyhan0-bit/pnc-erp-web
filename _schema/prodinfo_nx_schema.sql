/* =====================================================================
   생산정보등록 (w_pr_master_090 우측 3패널) — nx 편집 저장용 신규 테이블
   대상 DB: PARTNER_ERP_TEST3 (스키마 nx). 쓰기 전용, 조회는 라이브 PARTNER_ERP ∪ nx(nx우선).
   원천 대응(컬럼 그대로 + 감사컬럼):
     nx.prodinfo_assy    ← PR_M_ITEM_ASSY_RT    (품목별 조립공정수, 패널①)
     nx.prodinfo_single  ← PR_M_WORK_SINGLE      (단품공정 마스터+외경별 표준ST, 패널②)
     nx.prodinfo_proc    ← PR_M_ITEM_PROC_GAGONG (품목 생산공정순서 라우팅, 패널③)
     nx.prodinfo_item_st ← PR_M_ITEM_ST          (생산구분별 인원/CAPA, 하단 LOB탭)
   작성 2026-07-28.
   ===================================================================== */

/* 패널① 조립(공정수) — 품목별 A_WORK_CODE 공정수(work_qty만 입력). 키=(item,a_work) */
IF OBJECT_ID('nx.prodinfo_assy') IS NULL
CREATE TABLE nx.prodinfo_assy (
    item_code    varchar(20)  NOT NULL,
    a_work_code  smallint     NOT NULL,
    work_qty     smallint     NULL,
    upd_user     varchar(30)  NULL,
    upd_at       datetime     NOT NULL DEFAULT getdate(),
    CONSTRAINT PK_prodinfo_assy PRIMARY KEY (item_code, a_work_code)
);

/* 패널② 단품(공정수) = 외경별 표준ST 매트릭스 (전사 공유 마스터). 키=s_work_code */
IF OBJECT_ID('nx.prodinfo_single') IS NULL
CREATE TABLE nx.prodinfo_single (
    s_work_code        smallint    NOT NULL,
    work_desc          nvarchar(20) NULL,
    sort_seq           smallint    NULL,
    gc_gubun           varchar(1)  NULL,
    work_code          varchar(4)  NULL,   -- 작업처(PR_M_WORK)
    gagong_proc_code   varchar(10) NULL,   -- 파트(PR_M_PROC_GAGONG)
    cutting_proc_flag  varchar(1)  NULL,
    hour_pay           int         NULL,
    st_635  real NULL, st_794 real NULL, st_952 real NULL, st_127 real NULL,
    st_1588 real NULL, st_1905 real NULL, st_22 real NULL, st_254 real NULL, st_28 real NULL,
    sub_weld_flag      varchar(1)  NULL,
    gagong_group_code  varchar(2)  NULL,
    upd_user           varchar(30) NULL,
    upd_at             datetime    NOT NULL DEFAULT getdate(),
    CONSTRAINT PK_prodinfo_single PRIMARY KEY (s_work_code)
);

/* 패널③ 생산공정순서(가공 라우팅) — 품목별. 키=(item,proc_seq). 전 컬럼 그대로 */
IF OBJECT_ID('nx.prodinfo_proc') IS NULL
CREATE TABLE nx.prodinfo_proc (
    item_code        varchar(20)  NOT NULL,
    proc_seq         tinyint      NOT NULL,
    work_code        varchar(4)   NULL,    -- 작업처
    gagong_proc_code varchar(10)  NULL,    -- 파트
    s_work_code      smallint     NULL,    -- 가공공정(PR_M_WORK_SINGLE)
    mach_code        varchar(10)  NULL,    -- 가공설비(QA_M_MACHINE)
    work_qty         decimal(18,1) NULL,   -- 공정횟수
    std_size         varchar(100) NULL,    -- 규격(자유텍스트)
    mix_gagong       tinyint      NULL,
    gagong_proc_flag varchar(1)   NULL,
    gagong_proc_seq  tinyint      NULL,    -- 파트내 순번
    ready_st         decimal(18,3) NULL,   -- 준비시간(초)
    mach_ct          decimal(18,3) NULL,   -- 설비(CT)
    inwon            tinyint      NULL,    -- 인원
    human_st         decimal(18,3) NULL,   -- TT(초)
    tot_st           decimal(18,3) NULL,   -- ST(초) 정본
    jp_proc_method   varchar(1)   NULL,    -- 전표처리방법 J/G/L
    lt_hr            decimal(18,3) NULL,   -- LT(Hr)
    key_id           int          NULL,
    upd_user         varchar(30)  NULL,
    upd_at           datetime     NOT NULL DEFAULT getdate(),
    CONSTRAINT PK_prodinfo_proc PRIMARY KEY (item_code, proc_seq)
);

/* 하단 LOB분석 탭 — 생산구분별 인원/CAPA. 키=(item,prod_gubun) */
IF OBJECT_ID('nx.prodinfo_item_st') IS NULL
CREATE TABLE nx.prodinfo_item_st (
    item_code   varchar(20) NOT NULL,
    prod_gubun  varchar(2)  NOT NULL,
    member_qty  smallint    NULL,
    capa_qty    smallint    NULL,
    upd_user    varchar(30) NULL,
    upd_at      datetime    NOT NULL DEFAULT getdate(),
    CONSTRAINT PK_prodinfo_item_st PRIMARY KEY (item_code, prod_gubun)
);

/* =====================================================================
   추가 3종 (2026-07-29) — 하단 탭 ⑥ 양산준비 파일첨부 · ⑦ 지그정보 · ⑧ 수율(공정수)
   전용 dw 미발견(ITEM_MASTER_090_ANALYSIS §5) → nx 신규 편집저장. 조회=라이브∪nx, 편집=nx만.
   ===================================================================== */

/* ⑥ 양산준비 파일첨부 — 14종 문서 × 품목(다중첨부). 파일 실체=DOC_STORAGE_PATH\YANGSAN\ 하위 */
IF OBJECT_ID('nx.prodinfo_yangsan') IS NULL
CREATE TABLE nx.prodinfo_yangsan (
    yid           int IDENTITY(1,1) NOT NULL,
    item_code     varchar(20)   NOT NULL,
    doc_type      varchar(20)   NOT NULL,   -- 14종 문서구분 코드(YANGSAN_DOCS)
    orig_filename nvarchar(260) NULL,
    storage_uri   nvarchar(400) NULL,       -- DOC_STORAGE_PATH 상대경로
    ext           varchar(10)   NULL,
    byte_size     int           NULL,
    sha256        varchar(64)   NULL,
    del_flag      bit           NOT NULL DEFAULT 0,
    upd_user      varchar(30)   NULL,
    upd_at        datetime      NOT NULL DEFAULT getdate(),
    CONSTRAINT PK_prodinfo_yangsan PRIMARY KEY (yid)
);
IF OBJECT_ID('nx.prodinfo_yangsan') IS NOT NULL AND NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name='IX_prodinfo_yangsan_item')
CREATE INDEX IX_prodinfo_yangsan_item ON nx.prodinfo_yangsan(item_code, doc_type);

/* ⑦ 지그정보 — 품목별 다행(지그구분·수량·보관위치RACK·제작일). 키=(item,seq) */
IF OBJECT_ID('nx.prodinfo_jig') IS NULL
CREATE TABLE nx.prodinfo_jig (
    item_code   varchar(20)  NOT NULL,
    seq         smallint     NOT NULL,
    jig_gubun   nvarchar(40) NULL,    -- 지그구분(명)
    jig_qty     int          NULL,    -- 수량
    rack_loc    nvarchar(40) NULL,    -- 보관위치(RACK)
    make_ymd    varchar(8)   NULL,    -- 제작일 YYYYMMDD
    upd_user    varchar(30)  NULL,
    upd_at      datetime     NOT NULL DEFAULT getdate(),
    CONSTRAINT PK_prodinfo_jig PRIMARY KEY (item_code, seq)
);

/* ⑧ 수율(공정수) — 품목별 다행(수율공정·공정수·표준ST·ST). 키=(item,seq) */
IF OBJECT_ID('nx.prodinfo_yield') IS NULL
CREATE TABLE nx.prodinfo_yield (
    item_code   varchar(20)  NOT NULL,
    seq         smallint     NOT NULL,
    yield_proc  nvarchar(60) NULL,    -- 수율공정(명)
    proc_qty    decimal(18,1) NULL,   -- 공정수
    std_st      decimal(18,3) NULL,   -- 표준ST
    st          decimal(18,3) NULL,   -- ST
    upd_user    varchar(30)  NULL,
    upd_at      datetime     NOT NULL DEFAULT getdate(),
    CONSTRAINT PK_prodinfo_yield PRIMARY KEY (item_code, seq)
);
