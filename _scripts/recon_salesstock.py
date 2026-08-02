# -*- coding: utf-8 -*-
# salesstock(dw_pr_stock_040) 대조: 내 스냅샷 vs 검증된 110수불장(현재) vs 07/15기준 재구성
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
ss=DB.get('salesStock',[])
print("### salesStock(내 스냅샷) 구조 ###")
print(" 건수:",len(ss)," 샘플:",ss[0] if ss else None)
import collections
tot_qty=sum(float(r.get('qty',0) or 0) for r in ss)
tot_amt=sum(float(r.get('amt',0) or 0) for r in ss)
# 품목단위 합산(작업장 분해 합치기)
byitem=collections.defaultdict(float)
for r in ss: byitem[r.get('cd')]+=float(r.get('qty',0) or 0)
print(f" 재고수량합 {tot_qty:,.1f}  금액합 {tot_amt:,.0f}  고유품목 {len(byitem)}")
# 110 수불장(현재) 비교
p110={r[0]:r[3] for r in DB['prodItemStock']}
print(f"\n### 110 수불장(현재): {len(p110)}품목/{sum(p110.values()):,.1f} ###")
# 공통품목 차이 (작업장 합산 vs 110)
common=set(byitem)&set(p110)
big=[]
for it in common:
    d=byitem[it]-p110[it]
    if abs(d)>0.5: big.append((it,byitem[it],p110[it],d))
only_ss=[(it,byitem[it]) for it in byitem if it not in p110 and abs(byitem[it])>0.5]
only_110=[(it,p110[it]) for it in p110 if it not in byitem and abs(p110[it])>0.5]
print(f"공통 {len(common)}품목 중 차이(>0.5): {len(big)}  | salesstock에만 있고 110없음: {len(only_ss)} | 110에만: {len(only_110)}")
print("\n[차이 상위 15 — salesstock(07/15) vs 110(현재)]  ※날짜차이로 정상적 차이 가능")
for it,a,b,d in sorted(big,key=lambda x:-abs(x[3]))[:15]:
    print('  %-16s ss(07/15) %10.1f  110(현재) %10.1f  차이 %+9.1f'%(it,a,b,d))
