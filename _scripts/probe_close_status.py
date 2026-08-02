# -*- coding: utf-8 -*-
import sys, io, json, warnings
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, r"d:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP")
import db_client, pyodbc, pandas as pd
def live1(sql):
    cs=(f"DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};DATABASE=PARTNER_ERP;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}")
    cn=pyodbc.connect(cs, readonly=True)
    try:
        df=pd.read_sql(sql, cn); return df.iloc[0,0]
    except Exception as e: return "ERR:"+str(e)[:60]
    finally: cn.close()

rows=[]
def add(domain, ctype, tbl, col):
    v=live1(f"SELECT MAX({col}) FROM {tbl}")
    rows.append({'domain':domain,'ctype':ctype,'tbl':tbl,'last':str(v)})
    print(f"{domain:14}{ctype:6}{tbl:28}{v}")

add("자재(월마감)","월","PU_T_MONTH_STOCK_WH","STOCK_YYMM")
add("자재(일마감)","일","PU_T_MONTH_STOCK_WH_DAILY","STOCK_YMD")
add("생산파트(월마감)","월","PR_T_MONTH_STOCK_WH","STOCK_YYMM")
add("영업제품(월마감)","월","SA_T_MONTH_STOCK","STOCK_YYMM")
add("세트(월마감)","월","PU_T_SET_MONTH_STOCK","STOCK_YYMM")
# 저장
DB={'closeStatus':rows,'closeAsof':'2026-07-18','curYm':'2607'}
open(r"C:\Users\admin\AppData\Local\Temp\claude\d-----------100-AI-AGENT\02b63e35-1303-4eb0-8eb4-29df63d29c62\scratchpad\_close.json","w",encoding="utf-8").write(json.dumps(DB,ensure_ascii=False))
print("\nsaved _close.json")
