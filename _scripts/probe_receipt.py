# -*- coding: utf-8 -*-
# 확정입고집계표(dw_pu_input_120) 라이브 검증 — 마감/불출 기준, 2607
import sys, io, warnings
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, r"d:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP")
import db_client, pyodbc, pandas as pd
def live(sql):
    cs=(f"DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};DATABASE=PARTNER_ERP;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}")
    cn=pyodbc.connect(cs, readonly=True)
    try: return pd.read_sql(sql, cn)
    finally: cn.close()

MAGAM="""WITH MAGAM (CUST_CODE, JUN_YYMM, JUN_MAGAM_DAY, MAGAM_DAY) AS (
  SELECT CUST_CODE,format(dateadd(MONTH,-1,convert(date,'2607'+'01',12)),'yyMM') jun_yymm
    ,ISNULL((SELECT TOP 1 MAGAM_DAY FROM CM_M_CUST_MAGAM (nolock) WHERE CUST_CODE=A.CUST_CODE AND APPLY_YYMM<=format(dateadd(MONTH,-1,convert(date,'2607'+'01',12)),'yyMM') ORDER BY APPLY_YYMM DESC),'31') JUN_MAGAM_DAY
    ,ISNULL((SELECT TOP 1 MAGAM_DAY FROM CM_M_CUST_MAGAM (nolock) WHERE CUST_CODE=A.CUST_CODE AND APPLY_YYMM<='2607' ORDER BY APPLY_YYMM DESC),'31') MAGAM_DAY
  FROM CM_M_CUST (nolock) A )"""
def W(P): return (f"('{P}'='1' and A.MAINT_YMD>mg.jun_yymm+mg.jun_magam_day and A.MAINT_YMD<='2607'+mg.magam_day "
                  f"or '{P}'='2' and A.MAINT_YMD between '260701' and '260718')")
def base(P):
    # 최적화: LIKE '%' 제거, merge 힌트 제거, INSP 확정필터 의미 보존
    return f"""
  SELECT A.CUST_CODE cc, A.ITEM_CODE ic, A.MAT_CODE mat,
    SUM(A.MAINT_QTY) qty, SUM(A.MAINT_AMT) amt, SUM(A.MAINT_AMT) kamt, SUM(A.MAINT_VAT) vat
   FROM PU_T_STOCK_MAINT (nolock) A JOIN pr_m_item (nolock) M ON A.MAT_CODE=M.ITEM_CODE
     JOIN cm_m_cust (nolock) C ON A.CUST_CODE=C.CUST_CODE JOIN MAGAM mg ON A.CUST_CODE=mg.CUST_CODE
   WHERE {W(P)} AND A.MAINT_TAG IN ('9','S','C','G','H')
     AND ((ISNULL(A.INSP_FLAG,'N') IN ('','N')) OR (ISNULL(A.INSP_FLAG,'N') IN ('S','F') AND A.INSP_PROC_YMD >= ''))
   GROUP BY A.CUST_CODE,A.ITEM_CODE,A.MAT_CODE
  UNION ALL
  SELECT A.CUST_CODE, A.ITEM_CODE, A.MAT_CODE,
    SUM(A.MAINT_QTY), SUM(A.MAINT_AMT), SUM(A.TAXPAYERS), 0
   FROM PU_T_STOCK_MAINT_C (nolock) A JOIN pr_m_item (nolock) M ON A.MAT_CODE=M.ITEM_CODE
     JOIN cm_m_cust (nolock) C ON A.CUST_CODE=C.CUST_CODE JOIN MAGAM mg ON A.CUST_CODE=mg.CUST_CODE
   WHERE {W(P)} AND A.DIVISION IN ('P')
   GROUP BY A.CUST_CODE,A.ITEM_CODE,A.MAT_CODE"""
for lbl,P in (("마감",'1'),("불출",'2')):
    df=live(f"{MAGAM} SELECT COUNT(*) 라인, COUNT(DISTINCT cc) 업체, SUM(qty) 수량, SUM(amt) 금액, SUM(kamt) 금액KRW, SUM(vat) 부가세 FROM ({base(P)}) x")
    print(f"== 확정입고 {lbl}기준 2607 ==")
    print(df.to_string(index=False)); print()
