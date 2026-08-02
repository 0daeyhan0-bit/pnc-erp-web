# -*- coding: utf-8 -*-
import sys, io, warnings
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, r"d:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP")
import db_client, pyodbc, pandas as pd
def live(sql):
    cs=(f"DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};"
        f"DATABASE=PARTNER_ERP;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}")
    cn=pyodbc.connect(cs, readonly=True)
    try: return pd.read_sql(sql, cn)
    finally: cn.close()

print("== 1) MAGAM_DAY 값 형식(자릿수) 분포 ==")
print(live("SELECT MAGAM_DAY, LEN(MAGAM_DAY) len, COUNT(*) cnt FROM CM_M_CUST_MAGAM GROUP BY MAGAM_DAY ORDER BY MAGAM_DAY").to_string(index=False))

print("\n== 2) MAINT_YMD 형식 확인(길이) — PU_T_STOCK_MAINT 최근 ==")
print(live("SELECT TOP 3 MAINT_YMD, LEN(MAINT_YMD) len FROM PU_T_STOCK_MAINT WHERE MAINT_YMD LIKE '2607%' ORDER BY MAINT_YMD DESC").to_string(index=False))

print("\n== 3) 경계 자릿수 위험: MAGAM_DAY 단일자리 업체가 실제 거래에 있나 ==")
print(live("""
SELECT g.CUST_CODE, g.MAGAM_DAY, LEN(g.MAGAM_DAY) len
FROM CM_M_CUST_MAGAM g
WHERE LEN(LTRIM(RTRIM(g.MAGAM_DAY)))<2
""").to_string(index=False))

print("\n== 4) 마감기준 vs 재고장(실제일) 차이 = 익월이월분(마감 초과분) 규모: 2607 마감 이후~07/18 매입('5') ==")
print(live("""
WITH MG AS (SELECT CUST_CODE, ISNULL((SELECT TOP 1 MAGAM_DAY FROM CM_M_CUST_MAGAM WHERE CUST_CODE=A.CUST_CODE AND APPLY_YYMM<='2607' ORDER BY APPLY_YYMM DESC),'31') MAGAM_DAY FROM CM_M_CUST A)
SELECT COUNT(*) 라인, SUM(-A.MAINT_AMT) 금액
FROM PU_T_STOCK_MAINT A JOIN MG ON A.CUST_CODE=MG.CUST_CODE
WHERE A.MAINT_TAG='5' AND A.MAINT_YMD>'2607'+MG.MAGAM_DAY AND A.MAINT_YMD<='260718'
""").to_string(index=False))
