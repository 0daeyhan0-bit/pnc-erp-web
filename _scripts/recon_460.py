# -*- coding: utf-8 -*-
# 대조: 수불장 계산값(data.js prodStock) vs pr_t_mat_stock_wh 스냅샷
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
# 수불장(내 계산): data.js prodStock
raw=open(r"d:\피앤씨인더스트리\100_AI_AGENT\PNC_ERP_Web\js\data.js",encoding="utf-8").read()
DB=json.loads(raw[raw.index("const DB = ")+len("const DB = "):raw.rindex(";")])
led=pd.DataFrame([{'part':r[0],'mat':r[1],'desc':r[2],'led':r[5]} for r in DB['prodStock']])
pn=DB.get('prodPartNames',{})
# 스냅샷
snap=live("SELECT part_code part, UPPER(mat_code) mat, SUM(stock_qty) snap FROM pr_t_mat_stock_wh GROUP BY part_code, UPPER(mat_code)")
snap=snap[snap.snap.abs()>0.0001]
m=led.merge(snap,on=['part','mat'],how='outer')
m['led']=m['led'].fillna(0); m['snap']=m['snap'].fillna(0); m['desc']=m['desc'].fillna('')
m['diff']=m['led']-m['snap']
print("="*70)
print(f"수불장 계산  : {len(led):>6}품목  재고합 {led.led.sum():>14,.1f}")
print(f"스냅샷(pr_t_mat_stock_wh 실재고): {len(snap):>6}품목  재고합 {snap.snap.sum():>14,.1f}")
print(f"차이 품목수(>0.5): {int((m['diff'].abs()>0.5).sum())}   /  합계차 {m['diff'].sum():,.1f}")
print("="*70)
d=m[m['diff'].abs()>0.5].copy()
d['pname']=d['part'].map(lambda p:pn.get(str(p).strip(),p))
d=d.sort_values('diff',key=lambda s:s.abs(),ascending=False)
print("[차이 품목 전체 — 이 품목만 라이브 460에서 확인하시면 됩니다]")
print(d[['pname','part','mat','desc','led','snap','diff']].to_string(index=False,
      formatters={'led':lambda x:f'{x:,.0f}','snap':lambda x:f'{x:,.0f}','diff':lambda x:f'{x:+,.0f}'}))
