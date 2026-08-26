/* nx.v_plan_part_copy_new — 웹 자체편성(nx.plan_part_dtl) → 레거시 PR_T_PLAN_PART_COPY 호환 뷰.
   소스='신규DB(웹계획)' 일 때 파트별생산계획(410)·준비실적처리(키팅)·가공생산진척관리(420) 가 읽는다.

   ★2026-08-26 변경 — 리드타임 당김 컬럼 하드코딩 해제.
     뷰가 '당김 미구현' 시절에 만들어져 아래를 고정값으로 노출하고 있었다:
         PART_PLAN_YMD  = PLAN_YMD (당김 미적용)
         PART_OUTPUT_HM = ''  ·  PART_AMPM = ''  ·  OUTPUT_HM = ''  ·  AMPM = ''
         CUM_LT_HR      = 0
     그 결과 410 화면의 PART INPUT · 당일이전계획 · LG INPUT시간 이 전부 비어 있었다.
     이제 ③ 라인별투입시간조정(_stepL_pull) 이 nx.plan_part_dtl 에 실제 값을 채우므로
     그대로 노출한다. 실측 대사(기준일 동일 16,579행):
         PART_PLAN_YMD 99.98% · PART_OUTPUT_HM 99.39% · CUM_LT_HR 99.98%

     ※ nx.plan_part_dtl 은 STEP6 가 SELECT INTO 로 재생성하므로 당김 컬럼이 매번 사라진다.
       _stepL_pull 이 진입 시 ALTER 로 멱등 추가한다(planrev.py). 즉 ④ 뒤에 ③을 돌려야 채워진다.

   ※그밖의 미구현분은 NULL/0/'' 으로 노출한다(거짓값을 만들지 않는다):
     - CHANGE_DAY/LAST_LOT_QTY : 전차수 비교 미구현
     - 재고·실적 컬럼 : 화면이 매 조회마다 자체 계산하므로 0
   ※산출 가능한 것은 채운다:
     - PRIOR_GAGONG_PROC_* : 같은 (wo,assy,item) 안 PROC_SEQ 직전값(LAG)
     - TUIP_GAGONG_PROC_CODE : 투입파트 = 상위품목(UPPER_ITEM_CODE)의 파트 */
ALTER VIEW nx.v_plan_part_copy_new AS
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
    CAST(ISNULL(d.OUTPUT_HM,'') AS varchar(4)) AS OUTPUT_HM,
    CAST(ISNULL(d.AMPM,'') AS varchar(2))      AS AMPM,
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
    CAST(ISNULL(d.CUM_LT_HR,0) AS decimal(18,3)) AS CUM_LT_HR,
    ISNULL(NULLIF(d.PART_PLAN_YMD,''), d.PLAN_YMD) AS PART_PLAN_YMD,   -- ★당김 반영(2026-08-26)
    CAST(ISNULL(d.PART_OUTPUT_HM,'') AS varchar(4)) AS PART_OUTPUT_HM,
    CAST(ISNULL(d.PART_AMPM,'') AS varchar(2)) AS PART_AMPM,
    CAST(ISNULL(d.PART_PLAN_QTY,0) AS int)     AS PART_PLAN_QTY,
    CAST(0 AS tinyint)                         AS FINISH_TAG,
    CAST(0 AS int)                             AS COLOR,
    CAST(0 AS int)                             AS LAST_FINISH_QTY,
    CAST(0 AS int)                             AS FINISH_QTY,
    CAST(0 AS int)                             AS SALE_QTY,
    CAST(0 AS int)                             AS ASSY_STOCK_QTY,
    CAST(0 AS int)                             AS FIX_PR_STOCK_QTY,
    CAST(0 AS int)                             AS PR_STOCK_QTY,
    CAST(0 AS int)                             AS STOCK_QTY,
    CAST(0 AS int)                             AS PART_STOCK_QTY,
    CAST(0 AS int)                             AS PRIOR_JP_FINISH_QTY,
    CAST(0 AS int)                             AS JP_FINISH_QTY,
    CAST(0 AS int)                             AS READY_STOCK_QTY,
    CAST(0 AS int)                             AS READY_QTY,
    CAST(0 AS int)                             AS CUM_JAN_QTY,
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
    CAST(ISNULL(t.GPC,'') AS varchar(10))      AS TUIP_GAGONG_PROC_CODE,  -- ★투입파트=상위품목의 파트
    CAST('IS0001' AS varchar(10))              AS WH_GAGONG_PROC_CODE,
    CAST('' AS varchar(10))                    AS IN_GAGONG_PROC_CODE,
    CAST('0' AS varchar(1))                    AS VIR_SET_FLAG
  FROM nx.plan_part_dtl d
  LEFT JOIN (SELECT S_WORK_CODE,
                    MAX(WORK_CODE)       AS WORK_CODE,
                    MAX(JP_PROC_METHOD)  AS JP_PROC_METHOD
               FROM nx.PR_M_ITEM_PROC_GAGONG
              GROUP BY S_WORK_CODE) w ON w.S_WORK_CODE = d.S_WORK_CODE
  OUTER APPLY (SELECT TOP 1 u.GAGONG_PROC_CODE AS GPC
                 FROM nx.plan_part_dtl u
                WHERE u.WORK_ORDER = d.WORK_ORDER
                  AND ISNULL(u.SPLIT_WORK_ORDER,'') = ISNULL(d.SPLIT_WORK_ORDER,'')
                  AND u.ASSY_ITEM_CODE = d.ASSY_ITEM_CODE
                  AND u.ITEM_CODE = d.UPPER_ITEM_CODE) t
