# -*- coding: utf-8 -*-
import sys, io, json, warnings
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, r"d:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP")
import db_client, pyodbc, pandas as pd
def live(sql):
    cs=(f"DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};DATABASE=PARTNER_ERP;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}")
    cn=pyodbc.connect(cs, readonly=True)
    try: return pd.read_sql(sql, cn)
    finally: cn.close()

# --- 라이브 t3 (업체별 집계, 마감기준 2607) ---
T3 = r"""
WITH MAGAM (CUST_CODE, JUN_YYMM, JUN_MAGAM_DAY, MAGAM_DAY) AS (
  SELECT CUST_CODE,format(dateadd(MONTH,-1,convert(date,'2607'+'01',12)),'yyMM') jun_yymm
    ,ISNULL((SELECT TOP 1 MAGAM_DAY FROM CM_M_CUST_MAGAM WHERE CUST_CODE=A.CUST_CODE AND APPLY_YYMM<=format(dateadd(MONTH,-1,convert(date,'2607'+'01',12)),'yyMM') ORDER BY APPLY_YYMM DESC),'31') JUN_MAGAM_DAY
    ,ISNULL((SELECT TOP 1 MAGAM_DAY FROM CM_M_CUST_MAGAM WHERE CUST_CODE=A.CUST_CODE AND APPLY_YYMM<='2607' ORDER BY APPLY_YYMM DESC),'31') MAGAM_DAY
  FROM CM_M_CUST A )
SELECT T.CUST_CODE cc, MAX(T.CUST_DESC) cnm, T.CUST_TYPE ct,
  SUM(T.MAINT_QTY) qty, SUM(T.MAINT_AMT) amt, SUM(T.MAINT_VAT) vat,
  SUM(T.KRW_MAINT_AMT) kamt, SUM(T.KRW_MAINT_VAT) kvat
FROM (
  SELECT A.CUST_CODE,MAX(C2.CUST_DESC) CUST_DESC,C2.CUST_TYPE,A.MAT_CODE,A.MAINT_COST,SUM(-A.MAINT_QTY) MAINT_QTY,SUM(-A.MAINT_AMT) MAINT_AMT,SUM(-A.MAINT_AMT) KRW_MAINT_AMT,SUM(-A.MAINT_VAT) MAINT_VAT,SUM(-A.MAINT_VAT) KRW_MAINT_VAT
   FROM PU_T_STOCK_MAINT A JOIN PR_M_ITEM M ON A.MAT_CODE=M.ITEM_CODE JOIN CM_M_CUST C2 ON A.CUST_CODE=C2.CUST_CODE join MAGAM mg on a.cust_code=mg.cust_code
   WHERE A.MAINT_YMD>mg.jun_yymm+mg.jun_magam_day AND A.MAINT_YMD<='2607'+mg.magam_day AND A.MAINT_TAG IN ('5')
   GROUP BY A.CUST_CODE,A.MAINT_TAG,A.GAGONG_PROC_CODE,A.MAT_CODE,A.ITEM_CODE,C2.CUST_TYPE,A.MAINT_COST,M.ITEM_LGROUP,M.ITEM_SGROUP
  UNION ALL
  SELECT A.CUST_CODE,MAX(C2.CUST_DESC),C2.CUST_TYPE,A.ITEM_CODE,A.MAINT_COST,SUM(-A.MAINT_QTY),SUM(-A.MAINT_AMT),SUM(-A.MAINT_AMT),SUM(-A.MAINT_VAT),SUM(-A.MAINT_VAT)
   FROM SA_T_STOCK_MAINT A JOIN PR_M_ITEM M ON A.ITEM_CODE=M.ITEM_CODE JOIN CM_M_CUST C2 ON A.CUST_CODE=C2.CUST_CODE join MAGAM mg on a.cust_code=mg.cust_code
   WHERE A.MAINT_YMD>mg.jun_yymm+mg.jun_magam_day AND A.MAINT_YMD<='2607'+mg.magam_day AND A.MAINT_TAG IN ('R')
   GROUP BY A.CUST_CODE,A.MAINT_TAG,A.ITEM_CODE,A.MAINT_COST,C2.CUST_TYPE,M.ITEM_LGROUP,M.ITEM_SGROUP
  UNION ALL
  SELECT A.CUST_CODE,MAX(C2.CUST_DESC),C2.CUST_TYPE,A.MAT_CODE,A.MAINT_COST,SUM(A.MAINT_QTY),SUM(A.MAINT_AMT),SUM(A.TAXPAYERS),0,0
   FROM PU_T_STOCK_MAINT_C A JOIN PR_M_ITEM M ON A.MAT_CODE=M.ITEM_CODE JOIN CM_M_CUST C2 ON A.CUST_CODE=C2.CUST_CODE join MAGAM mg on a.cust_code=mg.cust_code
   WHERE A.MAINT_YMD>mg.jun_yymm+mg.jun_magam_day AND A.MAINT_YMD<='2607'+mg.magam_day AND A.DIVISION='Q'
   GROUP BY A.CUST_CODE,A.MAINT_TAG,A.MAT_CODE,A.ITEM_CODE,A.MAINT_COST,C2.CUST_TYPE,A.EXCHANGE_RATE,M.ITEM_LGROUP,M.ITEM_SGROUP,A.CURRENCY
) T GROUP BY T.CUST_CODE,T.CUST_TYPE ORDER BY T.CUST_CODE
"""
erp = live(T3)
print("== 라이브 t3 업체별 총계 ==")
print("업체:",len(erp),"수량:",round(erp.qty.sum(),2),"금액:",int(erp.amt.sum()),"금액KRW:",int(erp.kamt.sum()),"부가세:",int(erp.vat.sum()),"부가세KRW:",int(erp.kvat.sum()))

# --- 내 data.js dispatchClose 를 업체별 집계 ---
raw=open(r"d:\피앤씨인더스트리\100_AI_AGENT\PNC_ERP_Web\js\data.js",encoding="utf-8").read()
DB=json.loads(raw[raw.index("const DB = ")+11:raw.rindex(";")])
lines=DB['dispatchClose']
agg={}
for r in lines:
    o=agg.setdefault(r['cc'],{'qty':0,'amt':0,'vat':0,'kamt':0,'kvat':0})
    for k in ('qty','amt','vat','kamt','kvat'): o[k]+=(r.get(k) or 0)
print("\n== 내 dispatchClose 업체별 총계 ==")
print("업체:",len(agg),"수량:",round(sum(o['qty'] for o in agg.values()),2),"금액:",int(sum(o['amt'] for o in agg.values())),
      "금액KRW:",int(sum(o['kamt'] for o in agg.values())),"부가세:",int(sum(o['vat'] for o in agg.values())),"부가세KRW:",int(sum(o['kvat'] for o in agg.values())))

# --- 업체별 차이 ---
print("\n== 업체별 차이(금액 또는 부가세 불일치) ==")
em={r.cc:r for _,r in erp.iterrows()}
diff=0
for cc,o in sorted(agg.items()):
    e=em.get(cc)
    if e is None: print(f"  {cc}: 내쪽만 있음"); diff+=1; continue
    if abs(o['amt']-e.amt)>0.5 or abs(o['vat']-e.vat)>0.5 or abs(o['kamt']-e.kamt)>0.5:
        print(f"  {cc} {e.cnm}: 금액 {int(o['amt'])} vs {int(e.amt)} | 부가세 {int(o['vat'])} vs {int(e.vat)} | 금액KRW {int(o['kamt'])} vs {int(e.kamt)}"); diff+=1
for cc in em:
    if cc not in agg: print(f"  {cc} {em[cc].cnm}: ERP만 있음"); diff+=1
print("차이 업체수:",diff)
