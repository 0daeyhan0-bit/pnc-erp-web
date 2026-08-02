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
ps={r[0]:r for r in DB['prodItemStock']}; mv=DB['prodItemMoves']
uni=live("SELECT UPPER(item_code) item, SUM(stock_qty) snap FROM SA_T_ITEM_STOCK GROUP BY UPPER(item_code)")
sm={r.item:r.snap for r in uni.itertuples()}
# 스냅샷 vs 수불장 차이 (전 유니버스)
diffs=[]
allitems=set(sm)|set(ps)
for it in allitems:
    led=ps[it][3] if it in ps else 0; sn=sm.get(it,0)
    if abs(led-sn)>=0.01: diffs.append((it, ps.get(it,[it,'','',0,0])[1], ps.get(it,[it,'','',0,0])[2], led, sn, led-sn))
print("### 스냅샷(SA_T_ITEM_STOCK) vs 수불장 재구성 — 불일치 전체 (라이브 스팟체크) ###")
print('%-16s %-22s %-10s %10s %10s %9s'%('P/N','품명','작업처','수불장','스냅샷','차이'))
for it,ds,wk,led,sn,d in sorted(diffs,key=lambda x:-abs(x[5])):
    print('%-16s %-22s %-10s %10.2f %10.2f %+9.2f'%(it,str(ds)[:21],str(wk)[:9],led,sn,d))
# 이동경로별 대표
def divs(it): return set(m[4] for m in mv.get(it,[]))
picked={};
def add(why,pred):
    for it,r in sorted(ps.items(),key=lambda x:-abs(x[1][3])):
        if pred(it,r) and why not in picked: picked[why]=(it,r[1],r[2],r[3]); return
add('자재창고에서입고', lambda it,r:'자재창고에서입고' in divs(it))
add('세트출하(V)', lambda it,r:'세트출하' in divs(it))
add('생산완료(P)', lambda it,r:'생산완료' in divs(it))
add('무상공급(8)', lambda it,r:'무상공급' in divs(it))
add('출하반품(R)', lambda it,r:'출하반품' in divs(it))
add('재고조정(2)', lambda it,r:'재고조정' in divs(it))
add('출하(J)-대형', lambda it,r:'출하' in divs(it) and r[3]>1000)
add('음수재고', lambda it,r:r[3]<0)
print("\n### 이동경로/유형별 대표 검증품목 ###")
print('%-16s %-16s %-22s %-10s %10s'%('검증목적','P/N','품명','작업처','수불장'))
for why,(it,ds,wk,st) in picked.items():
    print('%-16s %-16s %-22s %-10s %10.2f'%(why,it,str(ds)[:21],str(wk)[:9],st))
