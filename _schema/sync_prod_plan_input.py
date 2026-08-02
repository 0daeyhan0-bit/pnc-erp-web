# -*- coding: utf-8 -*-
"""
생산계획추가입력 — nx.prod_plan_input 신규 + 레거시 PR_T_PLAN_INPUT 이관.
근거: w_pr_plan_060(소스無, INSERT_WINDOW로 확증) · dw_pr_plan_060_1(update=PR_T_PLAN_INPUT).
슬림설계: 런타임/집계 12컬럼(AM_PM·PROD_FINISH_*·WORK_QTY·ITEM_ST 등 전부 0%) 제외.
멱등: 복합키(plan_ymd,line_no,item_code,output_hm,work_order,prod_tag) 미존재분만.
"""
import sys
try: sys.stdout.reconfigure(encoding='utf-8')
except Exception: pass
sys.path.insert(0, r'd:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP')
import db_client
ex, q = db_client.execute_query, db_client.run_query
assert db_client.DB_DATABASE.strip().upper() != 'PARTNER_ERP', "운영DB 금지"

ex("""
IF OBJECT_ID('nx.prod_plan_input') IS NULL
CREATE TABLE nx.prod_plan_input (
  ppi_id     bigint IDENTITY(1,1) PRIMARY KEY,
  plan_ymd   nvarchar(8)   NULL,   -- 계획일자 YYMMDD
  line_no    nvarchar(10)  NULL,   -- 라인
  item_code  nvarchar(20)  NULL,   -- 품번(도번)
  output_hm  nvarchar(4)   NULL,   -- 산출/마감시각 HHMM
  plan_qty   int           NULL,   -- 계획수량
  work_order nvarchar(20)  NULL,   -- 제번/작업오더
  work_code  nvarchar(10)  NULL,   -- 공정(P1용접/P2가공)
  prod_tag   nvarchar(1)   NULL,   -- 생산구분
  remarks    nvarchar(255) NULL,
  src        nvarchar(10)  NULL,   -- legacy/web (리프레시 보호)
  upd_user   nvarchar(20)  NULL,
  upd_dt     datetime NULL CONSTRAINT df_ppi_dt DEFAULT getdate()
);
""")
print("nx.prod_plan_input 준비 완료")

ex("""
INSERT INTO nx.prod_plan_input
  (plan_ymd,line_no,item_code,output_hm,plan_qty,work_order,work_code,prod_tag,remarks,src,upd_user,upd_dt)
SELECT s.PLAN_YMD, s.LINE_NO, s.ITEM_CODE, s.OUTPUT_HM, s.PLAN_QTY, s.WORK_ORDER, s.WORK_CODE, s.PROD_TAG,
   LTRIM(RTRIM(s.REMARKS)), 'legacy', 'legacy', GETDATE()
FROM dbo.PR_T_PLAN_INPUT s
WHERE NOT EXISTS (SELECT 1 FROM nx.prod_plan_input t
   WHERE t.plan_ymd=s.PLAN_YMD AND t.line_no=s.LINE_NO AND t.item_code=s.ITEM_CODE
     AND t.output_hm=s.OUTPUT_HM AND ISNULL(t.work_order,'')=ISNULL(s.WORK_ORDER,'') AND ISNULL(t.prod_tag,'')=ISNULL(s.PROD_TAG,''))
""")

nx_n=int(q("SELECT COUNT(*) n FROM nx.prod_plan_input")['n'][0])
lg_n=int(q("SELECT COUNT(*) n FROM dbo.PR_T_PLAN_INPUT")['n'][0])
print(f"이관: nx {nx_n} / 레거시 {lg_n} (복합키 dedup으로 nx≤레거시 가능)")
print("\n샘플(최근):")
print(q("SELECT TOP 5 plan_ymd,line_no,item_code,output_hm,plan_qty,work_order,work_code,prod_tag FROM nx.prod_plan_input ORDER BY plan_ymd DESC").to_string(index=False))
print("\nwork_code 분포:", q("SELECT ISNULL(work_code,'(null)') wc, COUNT(*) n FROM nx.prod_plan_input GROUP BY work_code ORDER BY n DESC").to_string(index=False))
