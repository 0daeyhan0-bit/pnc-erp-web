# -*- coding: utf-8 -*-
# 확정입고집계표(dw_pu_input_120) 라인데이터 → data.js (라이브, 검증 포함). grain=(cc,ic,mat)
import sys, io, json, warnings
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, r"d:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP")
import db_client, pyodbc, pandas as pd
def live_df(sql):
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
def inner(P):
    return f"""
  SELECT A.CUST_CODE cc, C.CUST_DESC cnm, C.CUST_TYPE ct, A.ITEM_CODE ic, A.MAT_CODE mat,
    M.ITEM_DESC nm, M.ITEM_SPEC spec, M.ITEM_LGROUP lg, M.ITEM_SGROUP sg, M.ITEM_WEIGHT wt, M.UNIT unit,
    'KRW' cur, 1.0 rate, A.MAINT_COST cost, A.MAINT_COST kcost,
    A.MAINT_QTY qty, A.MAINT_AMT amt, A.MAINT_AMT kamt, A.MAINT_VAT vat, A.MAINT_VAT kvat
   FROM PU_T_STOCK_MAINT (nolock) A JOIN pr_m_item (nolock) M ON A.MAT_CODE=M.ITEM_CODE JOIN cm_m_cust (nolock) C ON A.CUST_CODE=C.CUST_CODE JOIN MAGAM mg ON A.CUST_CODE=mg.CUST_CODE
   WHERE {W(P)} AND A.MAINT_TAG IN ('9','S','C','G','H')
     AND ((ISNULL(A.INSP_FLAG,'N') IN ('','N')) OR (ISNULL(A.INSP_FLAG,'N') IN ('S','F') AND A.INSP_PROC_YMD >= ''))
  UNION ALL
  SELECT A.CUST_CODE, C.CUST_DESC, C.CUST_TYPE, A.ITEM_CODE, A.MAT_CODE,
    M.ITEM_DESC, M.ITEM_SPEC, M.ITEM_LGROUP, M.ITEM_SGROUP, M.ITEM_WEIGHT, M.UNIT,
    A.CURRENCY, A.EXCHANGE_RATE, A.MAINT_COST, A.MAINT_COST*A.EXCHANGE_RATE,
    A.MAINT_QTY, A.MAINT_AMT, A.TAXPAYERS, 0, 0
   FROM PU_T_STOCK_MAINT_C (nolock) A JOIN pr_m_item (nolock) M ON A.MAT_CODE=M.ITEM_CODE JOIN cm_m_cust (nolock) C ON A.CUST_CODE=C.CUST_CODE JOIN MAGAM mg ON A.CUST_CODE=mg.CUST_CODE
   WHERE {W(P)} AND A.DIVISION IN ('P')"""
def receipt(P):
    return f"""{MAGAM}
    SELECT T.cc, MAX(T.cnm) cnm, MAX(T.ct) ct, T.ic, T.mat, MAX(T.nm) nm, MAX(T.spec) spec,
      MAX(T.lg) lg, MAX(T.sg) sg, MAX(T.wt) wt, MAX(T.unit) unit, MAX(T.cur) cur, MAX(T.rate) rate,
      MAX(T.cost) cost, MAX(T.kcost) kcost,
      SUM(T.qty) qty, SUM(T.amt) amt, SUM(T.kamt) kamt, SUM(T.vat) vat, SUM(T.kvat) kvat
    FROM ({inner(P)}) T GROUP BY T.cc, T.ic, T.mat"""
close=live_df(receipt('1')); issue=live_df(receipt('2'))
print("마감:",len(close),"라인",len(close.cc.unique()),"업체 수량",int(close.qty.sum()),"금액",int(close.amt.sum()),"금액KRW",int(close.kamt.sum()),"부가세",int(close.vat.sum()),"(목표 2226/3,018,413/4,018,933,437)")
print("입고:",len(issue),"라인 수량",int(issue.qty.sum()),"금액",int(issue.amt.sum()))
path=r"d:\피앤씨인더스트리\100_AI_AGENT\PNC_ERP_Web\js\data.js"
raw=open(path,encoding="utf-8").read()
head=raw[:raw.index("const DB = ")+len("const DB = ")]
DB=json.loads(raw[raw.index("const DB = ")+len("const DB = "):raw.rindex(";")])
DB['receiptClose']=json.loads(close.to_json(orient='records',force_ascii=False))
DB['receiptIssue']=json.loads(issue.to_json(orient='records',force_ascii=False))
open(path,"w",encoding="utf-8").write(head+json.dumps(DB,ensure_ascii=False,indent=0)+";\n")
print("data.js 패치완료 (receiptClose/receiptIssue)")
