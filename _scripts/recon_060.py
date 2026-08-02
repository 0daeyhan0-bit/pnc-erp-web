# -*- coding: utf-8 -*-
import sys,io,json,warnings; warnings.filterwarnings('ignore')
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding='utf-8')
sys.path.insert(0,r'd:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP')
import pandas as pd,db_client,pyodbc
def live(sql):
    cs=f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};DATABASE=PARTNER_ERP;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}'
    cn=pyodbc.connect(cs,readonly=True)
    try: return pd.read_sql(sql,cn)
    finally: cn.close()
raw=open(r'd:\피앤씨인더스트리\100_AI_AGENT\PNC_ERP_Web\js\data.js',encoding='utf-8').read()
DB=json.loads(raw[raw.index('const DB = ')+11:raw.rindex(';')])
ms={r['mat']:float(r['stock'] or 0) for r in DB['matStock060']}
print("matStock060: %d품목 재고합 %.1f"%(len(ms),sum(ms.values())))
# 자재재고 스냅샷 (PU_T_MAT_STOCK_WH, mat_code 합산)
snap=live("SELECT UPPER(mat_code) mat, SUM(stock_qty) q FROM PU_T_MAT_STOCK_WH GROUP BY UPPER(mat_code)")
sm={r.mat:r.q for r in snap.itertuples()}
print("PU_T_MAT_STOCK_WH(mat합산): %d품목 재고합 %.1f"%(len(sm),sum(sm.values())))
allk=set(ms)|set(sm); big=[]
for k in allk:
    a=ms.get(k,0); b=sm.get(k,0)
    if abs(a-b)>0.5: big.append((k,a,b,a-b))
print("\n060 vs IS0001스냅샷 — 일치 %d / 불일치(>0.5) %d"%(len(allk)-len(big),len(big)))
for k,a,b,d in sorted(big,key=lambda x:-abs(x[3]))[:15]:
    print("  %-16s 060 %12.1f  IS0001스냅 %12.1f  차 %+12.1f"%(k,a,b,d))
