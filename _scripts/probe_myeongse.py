# -*- coding: utf-8 -*-
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
def show(t,q):
    print(f"\n== {t} ==");
    try: print(live(q).to_string(index=False))
    except Exception as e: print("ERR",str(e)[:150])

show("PU_T_STOCK_MAINT SEQ/YMD 컬럼","SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME='PU_T_STOCK_MAINT' AND (COLUMN_NAME LIKE '%SEQ%' OR COLUMN_NAME LIKE '%YMD%' OR COLUMN_NAME LIKE '%NO%')")
show("SA_T_STOCK_MAINT SEQ/YMD 컬럼","SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME='SA_T_STOCK_MAINT' AND (COLUMN_NAME LIKE '%SEQ%' OR COLUMN_NAME LIKE '%YMD%')")
show("PU_T_STOCK_MAINT_C SEQ/YMD 컬럼","SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME='PU_T_STOCK_MAINT_C' AND (COLUMN_NAME LIKE '%SEQ%' OR COLUMN_NAME LIKE '%YMD%')")

# 라인 단위(마감기준 2607) 건수/합계 — 원시행 그대로
MAGAM="""WITH MAGAM (CUST_CODE, JUN_YYMM, JUN_MAGAM_DAY, MAGAM_DAY) AS (
  SELECT CUST_CODE,format(dateadd(MONTH,-1,convert(date,'2607'+'01',12)),'yyMM') jun_yymm
    ,ISNULL((SELECT TOP 1 MAGAM_DAY FROM CM_M_CUST_MAGAM WHERE CUST_CODE=A.CUST_CODE AND APPLY_YYMM<=format(dateadd(MONTH,-1,convert(date,'2607'+'01',12)),'yyMM') ORDER BY APPLY_YYMM DESC),'31') JUN_MAGAM_DAY
    ,ISNULL((SELECT TOP 1 MAGAM_DAY FROM CM_M_CUST_MAGAM WHERE CUST_CODE=A.CUST_CODE AND APPLY_YYMM<='2607' ORDER BY APPLY_YYMM DESC),'31') MAGAM_DAY
  FROM CM_M_CUST A )"""
LINE=f"""{MAGAM}
SELECT COUNT(*) 라인, SUM(qty) 수량, SUM(amt) 금액 FROM (
  SELECT A.MAINT_YMD, A.MAINT_SEQ, -A.MAINT_QTY qty, -A.MAINT_AMT amt
   FROM PU_T_STOCK_MAINT A JOIN PR_M_ITEM M ON A.MAT_CODE=M.ITEM_CODE join MAGAM mg on a.cust_code=mg.cust_code
   WHERE A.MAINT_YMD>mg.jun_yymm+mg.jun_magam_day AND A.MAINT_YMD<='2607'+mg.magam_day AND A.MAINT_TAG='5'
  UNION ALL
  SELECT A.MAINT_YMD, A.MAINT_SEQ, -A.MAINT_QTY, -A.MAINT_AMT
   FROM SA_T_STOCK_MAINT A JOIN PR_M_ITEM M ON A.ITEM_CODE=M.ITEM_CODE join MAGAM mg on a.cust_code=mg.cust_code
   WHERE A.MAINT_YMD>mg.jun_yymm+mg.jun_magam_day AND A.MAINT_YMD<='2607'+mg.magam_day AND A.MAINT_TAG='R'
  UNION ALL
  SELECT A.MAINT_YMD, A.MAINT_SEQ, A.MAINT_QTY, A.MAINT_AMT
   FROM PU_T_STOCK_MAINT_C A JOIN PR_M_ITEM M ON A.MAT_CODE=M.ITEM_CODE join MAGAM mg on a.cust_code=mg.cust_code
   WHERE A.MAINT_YMD>mg.jun_yymm+mg.jun_magam_day AND A.MAINT_YMD<='2607'+mg.magam_day AND A.DIVISION='Q'
) x"""
print("\n== 라인단위 원시행 (목표 1,189건 / 1,639,796.60) ==")
try: print(live(LINE).to_string(index=False))
except Exception as e: print("ERR",str(e)[:200])
