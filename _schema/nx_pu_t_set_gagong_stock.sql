/* nx.PU_T_SET_GAGONG_STOCK — 가공세트재고 미러 (2026-08-27 신설)

   배경: 가공이동580 SP(nx.SP_PR_가공창고_이동계획_WEBPLAN)가 전표발행(JP_PRINT_QTY)을
         이 테이블 + PU_T_STOCK_MAINT_GAGONG_MOVE 합으로 계산한다.
         SP 는 nx 스키마 소속이라 무접두 참조가 nx→dbo 순으로 해석되는데,
         이 테이블만 nx 에 없어서 PARTNER_ERP_TEST3.dbo 로 빠지고 있었다
         (1,468행/43,113 vs 라이브 1,511행/43,623 → 전표발행 수치 차이 원인).

   조치: nx 에 동일 구조로 만들고 라이브를 복사. SP 는 명시적으로 nx 를 참조하도록 변경.
   PK = (ITEM_CODE, IN_CUST_CODE) — 라이브와 동일 그레인.
   ※쓰기는 nx 만(§1). 라이브 PARTNER_ERP 는 읽기 전용. */
IF OBJECT_ID('nx.PU_T_SET_GAGONG_STOCK') IS NULL
CREATE TABLE nx.PU_T_SET_GAGONG_STOCK (
  ITEM_CODE        varchar(20)   NOT NULL,
  IN_CUST_CODE     varchar(10)   NOT NULL,
  STOCK_QTY        decimal(18,4) NULL,
  UPDATE_USER_ID   varchar(20)   NULL,
  UPDATE_DATETIME  datetime      NULL,
  UPDATE_IP        varchar(20)   NULL,
  UPDATE_COMPUTER  varchar(20)   NULL,
  UPDATE_WINDOW    varchar(30)   NULL,
  CONSTRAINT pk_nx_set_gagong_stock PRIMARY KEY (ITEM_CODE, IN_CUST_CODE)
);
