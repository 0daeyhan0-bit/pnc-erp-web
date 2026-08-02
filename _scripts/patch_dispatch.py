# -*- coding: utf-8 -*-
# 기존 data.js 에 자재불출집계표(dispatch) 데이터만 추가 (LIVE 읽기전용 + 소형 TEST3 매핑)
import sys, io, os, json, warnings
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, r"d:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP")
import db_client, pyodbc, pandas as pd
def q(sql):
    return json.loads(db_client.run_query(sql).to_json(orient='records', force_ascii=False))
def q_live(sql):
    cs=(f"DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};"
        f"DATABASE=PARTNER_ERP;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}")
    cn=pyodbc.connect(cs, readonly=True)
    try: return json.loads(pd.read_sql(sql, cn).to_json(orient='records', force_ascii=False))
    finally: cn.close()

path=r"d:\피앤씨인더스트리\100_AI_AGENT\PNC_ERP_Web\js\data.js"
raw=open(path,encoding="utf-8").read()
head=raw[:raw.index("const DB = ")+len("const DB = ")]
body=raw[raw.index("const DB = ")+len("const DB = "):raw.rindex(";")]
DB=json.loads(body)

DB['lgroupNames'] = {r['cd']:r['nm'] for r in q("SELECT DETAIL_CODE cd, REPLACE(REPLACE(DETAIL_DESC,CHAR(13),''),CHAR(10),'') nm FROM CM_M_MASTER_DETAIL WHERE KIND_CODE='PR005'")}
DB['custInfo'] = {r['cc']:{'biz':r['biz'],'tel':r['tel'],'fax':r['fax']} for r in q(
  "SELECT cust_code cc, isnull(BUSINESS_NO,'') biz, isnull(PHONE_NO,'') tel, isnull(FAX_NO,'') fax FROM cm_m_cust")}

MAGAM="""WITH MAGAM (CUST_CODE, JUN_YYMM, JUN_MAGAM_DAY, MAGAM_DAY) AS (
  SELECT CUST_CODE
    ,format(dateadd(MONTH,-1,convert(date,'2607'+'01',12)),'yyMM') jun_yymm
    ,ISNULL((SELECT TOP 1 MAGAM_DAY FROM CM_M_CUST_MAGAM WHERE CUST_CODE=A.CUST_CODE AND APPLY_YYMM<=format(dateadd(MONTH,-1,convert(date,'2607'+'01',12)),'yyMM') ORDER BY APPLY_YYMM DESC),'31') JUN_MAGAM_DAY
    ,ISNULL((SELECT TOP 1 MAGAM_DAY FROM CM_M_CUST_MAGAM WHERE CUST_CODE=A.CUST_CODE AND APPLY_YYMM<='2607' ORDER BY APPLY_YYMM DESC),'31') MAGAM_DAY
  FROM CM_M_CUST A )"""
def inner(dc):
    return f"""
   SELECT A.CUST_CODE, MAX(C2.CUST_DESC) CUST_DESC, C2.CUST_TYPE, A.MAT_CODE, A.MAINT_COST, A.MAINT_COST KRW_MAINT_COST, A.ITEM_CODE,
     MAX(M.ITEM_DESC) ITEM_DESC, MAX(M.ITEM_SPEC) ITEM_SPEC, MAX(M.UNIT) UNIT, M.ITEM_LGROUP, M.ITEM_SGROUP,
     SUM(-A.MAINT_QTY) MAINT_QTY, SUM(-A.MAINT_AMT) MAINT_AMT, SUM(-A.MAINT_AMT) KRW_MAINT_AMT, SUM(-A.MAINT_VAT) MAINT_VAT, SUM(-A.MAINT_VAT) KRW_MAINT_VAT,
     1 EXCHANGE_RATE, MAX(M.IN_CUST_CODE) IN_CUST_CODE, 'KRW' CURRENCY, MAX(M.ITEM_WEIGHT) ITEM_WEIGHT
    FROM PU_T_STOCK_MAINT A JOIN PR_M_ITEM M ON A.MAT_CODE=M.ITEM_CODE JOIN CM_M_CUST C2 ON A.CUST_CODE=C2.CUST_CODE join MAGAM mg on a.cust_code=mg.cust_code
    WHERE {dc} AND A.MAINT_TAG IN ('5')
    GROUP BY A.CUST_CODE,A.MAINT_TAG,A.GAGONG_PROC_CODE,A.MAT_CODE,A.ITEM_CODE,C2.CUST_TYPE,A.MAINT_COST,M.ITEM_LGROUP,M.ITEM_SGROUP
   UNION ALL
   SELECT A.CUST_CODE, MAX(C2.CUST_DESC), C2.CUST_TYPE, A.ITEM_CODE, A.MAINT_COST, A.MAINT_COST, '',
     MAX(M.ITEM_DESC), MAX(M.ITEM_SPEC), MAX(M.UNIT), M.ITEM_LGROUP, M.ITEM_SGROUP,
     SUM(-A.MAINT_QTY), SUM(-A.MAINT_AMT), SUM(-A.MAINT_AMT), SUM(-A.MAINT_VAT), SUM(-A.MAINT_VAT), 1, MAX(M.IN_CUST_CODE), 'KRW', MAX(M.ITEM_WEIGHT)
    FROM SA_T_STOCK_MAINT A JOIN PR_M_ITEM M ON A.ITEM_CODE=M.ITEM_CODE JOIN CM_M_CUST C2 ON A.CUST_CODE=C2.CUST_CODE join MAGAM mg on a.cust_code=mg.cust_code
    WHERE {dc} AND A.MAINT_TAG IN ('R')
    GROUP BY A.CUST_CODE,A.MAINT_TAG,A.ITEM_CODE,A.MAINT_COST,C2.CUST_TYPE,M.ITEM_LGROUP,M.ITEM_SGROUP
   UNION ALL
   SELECT A.CUST_CODE, MAX(C2.CUST_DESC), C2.CUST_TYPE, A.MAT_CODE, A.MAINT_COST, (A.MAINT_COST*A.EXCHANGE_RATE), A.ITEM_CODE,
     MAX(M.ITEM_DESC), MAX(M.ITEM_SPEC), MAX(M.UNIT), M.ITEM_LGROUP, M.ITEM_SGROUP,
     SUM(A.MAINT_QTY), SUM(A.MAINT_AMT), SUM(A.TAXPAYERS), 0, 0, A.EXCHANGE_RATE, MAX(M.IN_CUST_CODE), A.CURRENCY, MAX(M.ITEM_WEIGHT)
    FROM PU_T_STOCK_MAINT_C A JOIN PR_M_ITEM M ON A.MAT_CODE=M.ITEM_CODE JOIN CM_M_CUST C2 ON A.CUST_CODE=C2.CUST_CODE join MAGAM mg on a.cust_code=mg.cust_code
    WHERE {dc} AND A.DIVISION='Q'
    GROUP BY A.CUST_CODE,A.MAINT_TAG,A.MAT_CODE,A.ITEM_CODE,A.MAINT_COST,C2.CUST_TYPE,A.EXCHANGE_RATE,M.ITEM_LGROUP,M.ITEM_SGROUP,A.CURRENCY"""
def dispatch(dc):
    return q_live(f"""{MAGAM}
    SELECT T.CUST_CODE cc, MAX(T.CUST_DESC) cnm, T.CUST_TYPE ct, T.MAT_CODE mat, T.ITEM_CODE ic,
      MAX(T.ITEM_DESC) nm, MAX(T.ITEM_SPEC) spec, MAX(T.UNIT) unit, T.ITEM_LGROUP lg, T.ITEM_SGROUP sg,
      T.MAINT_COST cost, T.KRW_MAINT_COST kcost, T.EXCHANGE_RATE rate, T.CURRENCY cur,
      (SELECT CUST_DESC FROM CM_M_CUST WHERE CUST_CODE=MAX(T.IN_CUST_CODE)) incust, isnull(MAX(T.ITEM_WEIGHT),0) wt,
      SUM(T.MAINT_QTY) qty, SUM(T.MAINT_AMT) amt, SUM(T.MAINT_VAT) vat, SUM(T.KRW_MAINT_AMT) kamt, SUM(T.KRW_MAINT_VAT) kvat
    FROM ({inner(dc)}) T
    GROUP BY T.CUST_CODE,T.CUST_TYPE,T.ITEM_CODE,T.MAT_CODE,T.ITEM_LGROUP,T.ITEM_SGROUP,T.MAINT_COST,T.KRW_MAINT_COST,T.EXCHANGE_RATE,T.CURRENCY""")

DB['dispatchYm']='2026-07'
DB['dispatchClose']=dispatch("A.MAINT_YMD > mg.jun_yymm+mg.jun_magam_day AND A.MAINT_YMD <= '2607'+mg.magam_day")
DB['dispatchIssue']=dispatch("A.MAINT_YMD between '260701' and '260718'")
for lbl,k in (("마감",'dispatchClose'),("불출",'dispatchIssue')):
    Q=sum((r.get('qty') or 0) for r in DB[k]); A=sum((r.get('amt') or 0) for r in DB[k]); C=len(set(r['cc'] for r in DB[k]))
    print(f"dispatch({lbl}): {len(DB[k])}라인 {C}업체 수량={Q:,.2f} 금액={A:,.0f}")

open(path,"w",encoding="utf-8").write(head+json.dumps(DB,ensure_ascii=False,indent=0)+";\n")
print("data.js 패치완료. lgroup:",len(DB['lgroupNames']),"custInfo:",len(DB['custInfo']))
