# -*- coding: utf-8 -*-
# 자재불출명세서(dw_pu_input_130) 라인데이터 → data.js (라이브 읽기전용, 검증 포함)
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
    ,ISNULL((SELECT TOP 1 MAGAM_DAY FROM CM_M_CUST_MAGAM WHERE CUST_CODE=A.CUST_CODE AND APPLY_YYMM<=format(dateadd(MONTH,-1,convert(date,'2607'+'01',12)),'yyMM') ORDER BY APPLY_YYMM DESC),'31') JUN_MAGAM_DAY
    ,ISNULL((SELECT TOP 1 MAGAM_DAY FROM CM_M_CUST_MAGAM WHERE CUST_CODE=A.CUST_CODE AND APPLY_YYMM<='2607' ORDER BY APPLY_YYMM DESC),'31') MAGAM_DAY
  FROM CM_M_CUST A )"""
def W(P): return (f"('{P}'='1' and A.MAINT_YMD>mg.jun_yymm+mg.jun_magam_day and A.MAINT_YMD<='2607'+mg.magam_day "
                  f"or '{P}'='2' and A.MAINT_YMD between '260701' and '260718')")
def detail(P):
    return f"""{MAGAM}
SELECT A.MAINT_YMD ymd, A.MAINT_SEQ seq, A.CUST_CODE cc, C.CUST_DESC cnm, C.CUST_TYPE ct,
  A.MAT_CODE mat, A.ITEM_CODE ic, (SELECT CUST_DESC FROM CM_M_CUST WHERE CUST_CODE=M.IN_CUST_CODE) incust,
  M.ITEM_LGROUP lg, M.ITEM_SGROUP sg, M.ITEM_WEIGHT wt, M.UNIT unit, M.ITEM_DESC nm, M.ITEM_SPEC spec,
  -A.MAINT_QTY qty, 'KRW' cur, 1.0 rate, A.MAINT_COST cost, A.MAINT_COST kcost, -A.MAINT_AMT amt, -A.MAINT_AMT kamt, -A.MAINT_VAT vat
 FROM PU_T_STOCK_MAINT A JOIN pr_m_item M ON A.MAT_CODE=M.ITEM_CODE join MAGAM mg on a.cust_code=mg.cust_code join cm_m_cust C on A.CUST_CODE=C.CUST_CODE
 WHERE {W(P)} AND A.MAINT_TAG IN ('5')
UNION ALL
SELECT A.MAINT_YMD, A.MAINT_SEQ, A.CUST_CODE, C.CUST_DESC, C.CUST_TYPE,
  A.ITEM_CODE, '', (SELECT CUST_DESC FROM CM_M_CUST WHERE CUST_CODE=M.IN_CUST_CODE),
  M.ITEM_LGROUP, M.ITEM_SGROUP, M.ITEM_WEIGHT, M.UNIT, M.ITEM_DESC, M.ITEM_SPEC,
  -A.MAINT_QTY, 'KRW', 1.0, A.MAINT_COST, A.MAINT_COST, -A.MAINT_AMT, -A.MAINT_AMT, -A.MAINT_VAT
 FROM SA_T_STOCK_MAINT A JOIN pr_m_item M ON A.ITEM_CODE=M.ITEM_CODE join MAGAM mg on a.cust_code=mg.cust_code join cm_m_cust C on A.CUST_CODE=C.CUST_CODE
 WHERE {W(P)} AND A.MAINT_TAG IN ('5')
UNION ALL
SELECT A.MAINT_YMD, A.MAINT_SEQ, A.CUST_CODE, C.CUST_DESC, C.CUST_TYPE,
  A.MAT_CODE, A.ITEM_CODE, (SELECT CUST_DESC FROM CM_M_CUST WHERE CUST_CODE=M.IN_CUST_CODE),
  M.ITEM_LGROUP, M.ITEM_SGROUP, M.ITEM_WEIGHT, M.UNIT, M.ITEM_DESC, M.ITEM_SPEC,
  A.MAINT_QTY, A.CURRENCY, A.EXCHANGE_RATE, A.MAINT_COST, A.MAINT_COST*A.EXCHANGE_RATE, A.MAINT_AMT, A.TAXPAYERS, 0
 FROM PU_T_STOCK_MAINT_C A JOIN pr_m_item M ON A.MAT_CODE=M.ITEM_CODE join MAGAM mg on a.cust_code=mg.cust_code join cm_m_cust C on A.CUST_CODE=C.CUST_CODE
 WHERE {W(P)} AND A.DIVISION='Q'"""

close=live_df(detail('1')); issue=live_df(detail('2'))
print("마감:", len(close),"건 수량", round(close.qty.sum(),2), "금액", int(close.amt.sum()), " (목표 1,189 / 1,639,796.60)")
print("불출:", len(issue),"건 수량", round(issue.qty.sum(),2), "금액", int(issue.amt.sum()))

path=r"d:\피앤씨인더스트리\100_AI_AGENT\PNC_ERP_Web\js\data.js"
raw=open(path,encoding="utf-8").read()
head=raw[:raw.index("const DB = ")+len("const DB = ")]
DB=json.loads(raw[raw.index("const DB = ")+len("const DB = "):raw.rindex(";")])
DB['detailClose']=json.loads(close.to_json(orient='records',force_ascii=False))
DB['detailIssue']=json.loads(issue.to_json(orient='records',force_ascii=False))
open(path,"w",encoding="utf-8").write(head+json.dumps(DB,ensure_ascii=False,indent=0)+";\n")
print("data.js 패치완료 (detailClose/detailIssue)")
