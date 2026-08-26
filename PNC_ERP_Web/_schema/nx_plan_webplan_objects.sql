/* ============================================================================
   신규DB(웹계획) 소스용 DB 객체 — 2026-08-26
   ----------------------------------------------------------------------------
   파트별생산계획(410)·준비실적처리(키팅)·출하실적등록(040)·가공생산진척관리(420)·
   가공창고이동계획(580) 의 소스 드롭다운에서 "신규DB(웹계획)" 을 고르면
   레거시 편성 대신 웹이 자체 편성한 계획을 읽는다. 그때 쓰이는 어댑터 객체들.

   ★모두 nx 스키마에만 만든다(§1-1 쓰기는 nx 만). 라이브 무변경.
   ★원본 테이블도 건드리지 않는다 — 읽기전용 뷰 + SP 복제본뿐.

   [배포 순서]
     1) 이 스크립트를 PARTNER_ERP_TEST3 에서 실행 (①②)
     2) ③ 은 별도 — nx 평문 SP 를 복제해야 하므로 아래 파이썬 절차 참조

   [무엇을 읽나]
     nx.plan_dtl (LG엑셀 업로드)
        → nx.plan_item_dtl  (STEP5 제번×완제품)  → ② v_plan_item_dtl_new   → 040
        → nx.plan_part_dtl  (STEP6 제번×파트)    → ① v_plan_part_copy_new  → 410·키팅·420·580
     ※ STEP5/6 을 만드는 것은 [자재소요·조달 편성] 버튼(/api/plan/compose_mat, soyo.py).

   [미구현분 — 거짓값을 만들지 않고 빈값/0 으로 노출한다]
     · PART_PLAN_YMD  : 리드타임 역산 미구현 → PLAN_YMD 그대로(레거시는 1~7일 당김)
     · OUTPUT_HM/AMPM : 시각 계산 미구현
     · CHANGE_DAY/LAST_LOT_QTY : 전차수 비교 미구현
     · 재고·실적 컬럼 : 화면이 매 조회마다 자체 계산하므로 0
   ============================================================================ */

------------------------------------------------------------------------------
-- ① nx.v_plan_part_copy_new  : STEP6(파트별) → PR_T_PLAN_PART_COPY 호환
--    사용 화면 = 410 · 키팅 · 420 · 580(복제SP 경유)
------------------------------------------------------------------------------
CREATE OR ALTER VIEW nx.v_plan_part_copy_new AS
SELECT
    d.PLAN_YMD,
    d.WORK_ORDER,
    d.SPLIT_WORK_ORDER,
    d.ASSY_ITEM_CODE,
    CAST(d.BOM_LEVEL AS tinyint)               AS BOM_LEVEL,
    d.UPPER_ITEM_CODE,
    d.ITEM_CODE,
    CAST(d.PROC_SEQ AS smallint)               AS PROC_SEQ,
    d.P_ITEM_CODE,
    d.GC_GUBUN,
    CAST('' AS varchar(4))                     AS OUTPUT_HM,
    CAST('' AS varchar(2))                     AS AMPM,
    CAST(d.LINE_NO AS varchar(10))             AS LINE_NO,
    d.USE_QTY,
    CAST('' AS varchar(10))                    AS CHANGE_DAY,
    CAST(0 AS int)                             AS LAST_LOT_QTY,
    CAST(ISNULL(d.LOT_QTY,0) AS int)           AS LOT_QTY,
    CAST(ISNULL(d.PLAN_QTY,0) AS int)          AS PLAN_QTY,
    CAST(ISNULL(w.WORK_CODE,'') AS varchar(4)) AS WORK_CODE,
    d.GAGONG_PROC_CODE,
    CAST(d.GAGONG_PROC_SEQ AS smallint)        AS GAGONG_PROC_SEQ,
    CAST(ISNULL(w.JP_PROC_METHOD,'') AS varchar(1)) AS JP_PROC_METHOD,
    d.LT_HR,
    CAST(0 AS decimal(18,3))                   AS CUM_LT_HR,
    d.PLAN_YMD                                 AS PART_PLAN_YMD,   -- ★리드타임 역산 미적용
    CAST('' AS varchar(4))                     AS PART_OUTPUT_HM,
    CAST('' AS varchar(2))                     AS PART_AMPM,
    CAST(ISNULL(d.PART_PLAN_QTY,0) AS int)     AS PART_PLAN_QTY,
    CAST(0 AS tinyint)  AS FINISH_TAG,      CAST(0 AS int) AS COLOR,
    CAST(0 AS int)      AS LAST_FINISH_QTY, CAST(0 AS int) AS FINISH_QTY,
    CAST(0 AS int)      AS SALE_QTY,        CAST(0 AS int) AS ASSY_STOCK_QTY,
    CAST(0 AS int)      AS FIX_PR_STOCK_QTY,CAST(0 AS int) AS PR_STOCK_QTY,
    CAST(0 AS int)      AS STOCK_QTY,       CAST(0 AS int) AS PART_STOCK_QTY,
    CAST(0 AS int)      AS PRIOR_JP_FINISH_QTY, CAST(0 AS int) AS JP_FINISH_QTY,
    CAST(0 AS int)      AS READY_STOCK_QTY, CAST(0 AS int) AS READY_QTY,
    CAST(0 AS int)      AS CUM_JAN_QTY,
    CAST('' AS varchar(200))                   AS CUM_ITEM_CODE,
    CAST('' AS varchar(100))                   AS NEXT_PART_INFO,
    CAST('web' AS varchar(20))                 AS INSERT_USER_ID,
    CAST(NULL AS datetime)                     AS INSERT_DATETIME,
    CAST('' AS varchar(20))                    AS INSERT_IP,
    CAST('' AS varchar(30))                    AS INSERT_COMPUTER,
    CAST('plan_compose_mat' AS varchar(30))    AS INSERT_WINDOW,
    CAST(LAG(d.GAGONG_PROC_CODE) OVER (
         PARTITION BY d.WORK_ORDER, ISNULL(d.SPLIT_WORK_ORDER,''), d.ASSY_ITEM_CODE, d.ITEM_CODE
         ORDER BY d.PROC_SEQ) AS varchar(10))  AS PRIOR_GAGONG_PROC_CODE,
    CAST(ISNULL(LAG(d.GAGONG_PROC_SEQ) OVER (
         PARTITION BY d.WORK_ORDER, ISNULL(d.SPLIT_WORK_ORDER,''), d.ASSY_ITEM_CODE, d.ITEM_CODE
         ORDER BY d.PROC_SEQ),0) AS smallint)  AS PRIOR_GAGONG_PROC_SEQ,
    CAST(ISNULL(t.GPC,'') AS varchar(10))      AS TUIP_GAGONG_PROC_CODE,  -- 투입파트=상위품목의 파트
    CAST('IS0001' AS varchar(10))              AS WH_GAGONG_PROC_CODE,
    CAST('' AS varchar(10))                    AS IN_GAGONG_PROC_CODE,
    CAST('0' AS varchar(1))                    AS VIR_SET_FLAG
  FROM nx.plan_part_dtl d
  LEFT JOIN (SELECT S_WORK_CODE, MAX(WORK_CODE) AS WORK_CODE, MAX(JP_PROC_METHOD) AS JP_PROC_METHOD
               FROM nx.PR_M_ITEM_PROC_GAGONG GROUP BY S_WORK_CODE) w ON w.S_WORK_CODE = d.S_WORK_CODE
  OUTER APPLY (SELECT TOP 1 u.GAGONG_PROC_CODE AS GPC
                 FROM nx.plan_part_dtl u
                WHERE u.WORK_ORDER = d.WORK_ORDER
                  AND ISNULL(u.SPLIT_WORK_ORDER,'') = ISNULL(d.SPLIT_WORK_ORDER,'')
                  AND u.ASSY_ITEM_CODE = d.ASSY_ITEM_CODE
                  AND u.ITEM_CODE = d.UPPER_ITEM_CODE) t;
GO

------------------------------------------------------------------------------
-- ② nx.v_plan_item_dtl_new  : STEP5(제번×완제품) → SA_T_PLAN_ITEM_DTL 호환
--    사용 화면 = 040 출하실적등록 (b1 LG계획 갈래만 교체)
--    ※예외생산(PR_T_PLAN_INPUT)·전일계획잔여(SA_T_PLAN_DTL_DAILY)는 웹에 대응물이
--      아예 없어 040 에서 레거시 원천을 그대로 쓴다.
------------------------------------------------------------------------------
CREATE OR ALTER VIEW nx.v_plan_item_dtl_new AS
SELECT
    d.PLAN_YMD,
    d.WORK_ORDER,
    d.SPLIT_WORK_ORDER,
    d.C_ITEM_CODE,
    CAST(ISNULL(u.MODEL_NO,'') AS varchar(30))  AS MODEL_NO,
    CAST(d.LINE_NO AS varchar(10))              AS LINE_NO,
    CAST('' AS varchar(6))                      AS CLS_YMD,
    CAST(ISNULL(d.OUTPUT_HM,'') AS varchar(4))  AS OUTPUT_HM,
    d.USE_QTY,
    CAST(ISNULL(d.LOT_QTY,0) AS int)            AS LOT_QTY,
    CAST(ISNULL(d.PLAN_QTY,0) AS int)           AS PLAN_QTY,
    CAST('' AS varchar(100))                    AS REMARKS1,
    CAST('' AS varchar(100))                    AS REMARKS2,
    CAST(0 AS int)                              AS EXCEL_SEQ,
    CAST('' AS varchar(50))                     AS TOOLS_DESC,
    CAST(ISNULL(u.FROM_SEQ,0) AS int)           AS FROM_SEQ,
    CAST(ISNULL(u.TO_SEQ,0) AS int)             AS TO_SEQ,
    CAST('' AS varchar(10))                     AS CHANGE_DAY,
    CAST(ISNULL(u.CR_FLAG,'') AS varchar(1))    AS CR_FLAG,
    CAST(ISNULL(d.ORG_PLAN_YMD,d.PLAN_YMD) AS varchar(6)) AS ORG_PLAN_YMD,
    CAST(ISNULL(d.OUTPUT_HM,'') AS varchar(4))  AS ORG_OUTPUT_HM,
    CAST('0' AS varchar(1))                     AS VIR_SET_FLAG
  FROM nx.plan_item_dtl d
  LEFT JOIN (SELECT WORK_ORDER, MAX(MODEL_NO) MODEL_NO, MAX(FROM_SEQ) FROM_SEQ,
                    MAX(TO_SEQ) TO_SEQ, MAX(CR_FLAG) CR_FLAG
               FROM nx.plan_dtl GROUP BY WORK_ORDER) u ON u.WORK_ORDER = d.WORK_ORDER;
GO

------------------------------------------------------------------------------
-- ③ nx.SP_PR_가공창고_이동계획_WEBPLAN  : 580 용 복제 SP
--    ★여기에 본문을 싣지 않는다(61,949자). 레거시 SP 의 nx 평문사본을 복제하고
--      계획테이블 참조 1곳만 치환하는 방식이라, 원본이 바뀌면 다시 떠야 한다.
--
--    [생성 방법] PARTNER_ERP_TEST3 에 접속해 아래를 실행:
--
--      import re, db_client
--      cn = db_client.get_connection(); cu = cn.cursor()
--      SRC = "SP_PR_가공창고_이동계획_260213"      # 라이브 운영본과 같은 버전
--      DST = "SP_PR_가공창고_이동계획_WEBPLAN"
--      cu.execute("""SELECT m.definition FROM PARTNER_ERP_TEST3.sys.sql_modules m
--                      JOIN PARTNER_ERP_TEST3.sys.objects o ON o.object_id=m.object_id
--                     WHERE o.name=?""", SRC)
--      d = cu.fetchone()[0]
--      d = re.sub(r"(CREATE|ALTER)\s+PROC(EDURE)?\s+(\[dbo\]\.)?\[?"+re.escape(SRC)+r"\]?",
--                 "CREATE OR ALTER PROCEDURE nx."+DST, d, count=1, flags=re.I)
--      # 주석줄은 건드리지 않고 계획테이블만 치환(실질 1곳)
--      d = "\n".join(l if re.match(r"\s*--", l) else
--                    re.sub(r"\bPR_T_PLAN_PART_COPY\b",
--                           "PARTNER_ERP_TEST3.nx.v_plan_part_copy_new", l, flags=re.I)
--                    for l in d.split("\n"))
--      cu.execute(d); cn.commit()
--
--    [검증] 원본 SP 와 반환 컬럼 174개가 같아야 한다(2026-08-26 실측 확인).
------------------------------------------------------------------------------
