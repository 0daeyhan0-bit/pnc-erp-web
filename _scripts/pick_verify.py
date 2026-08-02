# -*- coding: utf-8 -*-
import sys, io, json, warnings
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, r"d:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP")
import pandas as pd, db_client, pyodbc
def live(sql):
    cs=(f"DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};DATABASE=PARTNER_ERP;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}")
    cn=pyodbc.connect(cs, readonly=True);
    try: return pd.read_sql(sql, cn)
    finally: cn.close()
raw=open(r'd:\피앤씨인더스트리\100_AI_AGENT\PNC_ERP_Web\js\data.js',encoding='utf-8').read()
DB=json.loads(raw[raw.index('const DB = ')+11:raw.rindex(';')])
pn=DB.get('prodPartNames',{}); pName=lambda p: pn.get(str(p).strip(),p)
ps={ (r[0],r[1]):r for r in DB['prodStock'] }
mv=DB['prodMoves']
snap=live("SELECT part_code part, UPPER(mat_code) mat, SUM(stock_qty) snap FROM pr_t_mat_stock_wh GROUP BY part_code, UPPER(mat_code)")
snapm={ (r.part,r.mat):r.snap for r in snap.itertuples() }
def srcs(k):
    s=set(m[4] for m in mv.get(k,[])); return ','.join(sorted(s))
picked=[]; used=set()
def add(k,why):
    if k in used or k not in ps: return
    used.add(k); r=ps[k]; picked.append((why,pName(r[0]),r[0],r[1],r[5],snapm.get(k,0),srcs(r[0]+'||'+r[1])))
rows=list(ps.items())
# 1) 대형재고 top5
for k,_ in sorted(rows,key=lambda x:-abs(x[1][5]))[:5]: add(k,'대형재고')
# 2) 음수재고
for k,_ in sorted(rows,key=lambda x:x[1][5])[:3]: add(k,'음수재고')
# 3) 이동원천별 대표: 가공생산입고 / 자재창고반품 / 가공부품이동 / SUB생산실적 / 생산창고입고
for tag in ['가공생산입고','자재창고반품','가공부품이동','SUB생산실적','기초재고']:
    for k,r in sorted(rows,key=lambda x:-abs(x[1][5])):
        kk=r[0]+'||'+r[1]
        if tag in set(m[4] for m in mv.get(kk,[])): add(k,'원천:'+tag); break
# 4) 스냅샷과 큰 차이(수불장 정본 확인)
diffs=sorted(rows,key=lambda x:-abs(x[1][5]-snapm.get(x[0],0)))
for k,_ in diffs[:4]: add(k,'스냅샷차이')
# 5) 스냅샷과 일치(정상군 확인)
for k,r in sorted(rows,key=lambda x:-abs(x[1][5])):
    if abs(r[5]-snapm.get(k,0))<0.01 and abs(r[5])>50: add(k,'스냅샷일치');
    if sum(1 for p in picked if p[0]=='스냅샷일치')>=2: break
print(f"{'검증목적':<12}{'파트명':<14}{'파트':<7}{'자도번':<20}{'내값(수불장)':>14}{'스냅샷':>12}  주요이동원천")
print('-'*110)
for why,pnm,p,m,led,sn,sc in picked:
    print(f"{why:<12}{str(pnm)[:12]:<14}{p:<7}{m:<20}{led:>14,.3f}{sn:>12,.3f}  {sc}")
