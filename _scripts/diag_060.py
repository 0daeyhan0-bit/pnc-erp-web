# -*- coding: utf-8 -*-
import sys,io,warnings; warnings.filterwarnings('ignore')
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding='utf-8')
sys.path.insert(0,r'd:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP')
import pandas as pd,db_client,pyodbc,json
def live(sql):
    cs=f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};DATABASE=PARTNER_ERP;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}'
    cn=pyodbc.connect(cs,readonly=True)
    try: return pd.read_sql(sql,cn)
    finally: cn.close()
# PU_T_MAT_STOCK_WH: gagong_proc_code(위치) 별
print("### PU_T_MAT_STOCK_WH gagong_proc_code(위치)별 상위 ###")
print(live("SELECT ISNULL(gagong_proc_code,'(blank)') loc, COUNT(*) n, SUM(stock_qty) q FROM PU_T_MAT_STOCK_WH GROUP BY gagong_proc_code ORDER BY SUM(stock_qty) DESC").head(12).to_string(index=False))
# MBM65584007: cust/gagong 분해
print("\n### MBM65584007 위치분해 (PU_T_MAT_STOCK_WH) ###")
print(live("""SELECT ISNULL(cust_code,'') cust, (SELECT cust_desc FROM cm_m_cust c WHERE c.cust_code=x.cust_code) cnm,
 ISNULL(gagong_proc_code,'') loc, SUM(stock_qty) q FROM PU_T_MAT_STOCK_WH x WHERE UPPER(mat_code)='MBM65584007' GROUP BY cust_code, gagong_proc_code ORDER BY SUM(stock_qty) DESC""").to_string(index=False))
raw=open(r'd:\피앤씨인더스트리\100_AI_AGENT\PNC_ERP_Web\js\data.js',encoding='utf-8').read()
DB=json.loads(raw[raw.index('const DB = ')+11:raw.rindex(';')])
r=[x for x in DB['matStock060'] if x['mat']=='MBM65584007']
print("\n060 내값 MBM65584007:", r)
mv=DB.get('matMoves060',{}).get('MBM65584007',[])
print("060 이동라인수:", len(mv), " 앞 3:", mv[:3])
