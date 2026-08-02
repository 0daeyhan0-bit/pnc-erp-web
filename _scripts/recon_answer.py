# -*- coding: utf-8 -*-
import sys,io,json,warnings; warnings.filterwarnings('ignore')
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding='utf-8')
sys.path.insert(0,r'd:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP')
import pandas as pd,db_client,pyodbc
cs=f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};DATABASE=PARTNER_ERP;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}'
cn=pyodbc.connect(cs,readonly=True)
snap=pd.read_sql('SELECT part_code part, UPPER(mat_code) mat, SUM(stock_qty) snap FROM pr_t_mat_stock_wh GROUP BY part_code, UPPER(mat_code)',cn); cn.close()
sm={(r.part,r.mat):r.snap for r in snap.itertuples()}
raw=open(r'd:\피앤씨인더스트리\100_AI_AGENT\PNC_ERP_Web\js\data.js',encoding='utf-8').read()
DB=json.loads(raw[raw.index('const DB = ')+11:raw.rindex(';')]); pn=DB.get('prodPartNames',{})
same=0; dl=[]
for r in DB['prodStock']:
    s=sm.get((r[0],r[1]),0)
    if abs(r[5]-s)<0.01: same+=1
    else: dl.append((pn.get(r[0],r[0]),r[0],r[1],r[5],s,r[5]-s))
print('총 %d품목 | 스냅샷과 자동일치(교차검증): %d | 수불장<>스냅샷: %d'%(len(DB['prodStock']),same,len(dl)))
print('\n[수불장<>스냅샷 전체 목록 — 라이브 스팟체크 대상]')
print('%-11s %-6s %-20s %11s %11s %10s'%('파트명','파트','자도번','수불장','스냅샷','차이'))
for pnm,p,m,l,s,d in sorted(dl,key=lambda x:-abs(x[5])):
    print('%-11s %-6s %-20s %11.2f %11.2f %+10.2f'%(str(pnm)[:11],p,m,l,s,d))
