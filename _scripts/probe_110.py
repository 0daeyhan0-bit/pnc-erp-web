# -*- coding: utf-8 -*-
import sys,io,warnings; warnings.filterwarnings('ignore')
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding='utf-8')
sys.path.insert(0,r'd:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP')
import pandas as pd,db_client,pyodbc
def live(sql):
    cs=f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};DATABASE=PARTNER_ERP;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}'
    cn=pyodbc.connect(cs,readonly=True)
    try: return pd.read_sql(sql,cn)
    finally: cn.close()
# 제품재고 관련 테이블 후보
print('### sa_t %stock% 테이블 ###')
print(live("SELECT name FROM sys.tables WHERE name LIKE 'sa_t%stock%' OR name LIKE 'sa_t%prod%' ORDER BY name").to_string(index=False))
print('\n### sa_t_month_stock 컬럼 & 최신 stock_yymm ###')
print([c for c in live("SELECT TOP 1 * FROM sa_t_month_stock").columns])
print(live("SELECT stock_yymm, COUNT(*) n, SUM(stock_qty) q FROM sa_t_month_stock GROUP BY stock_yymm ORDER BY stock_yymm DESC").head(6).to_string(index=False))
print('\n### pr_m_item 작업처 관련 컬럼 ###')
print([c for c in live("SELECT TOP 1 * FROM pr_m_item").columns])
# 제품 수불장 = bf(2502) + 이동(현행~) : 전 품목 재구성 (bf CTE 논리 = l1 전월이월 union 확장)
BF="""
 SELECT item_code, stock_qty q FROM sa_t_month_stock WHERE stock_yymm='2502'
 UNION ALL SELECT item_code, MAINT_QTY FROM sa_t_stock_maint WHERE MAINT_YMD>'250299' AND maint_ymd<'260701' AND maint_tag IN ('B','V','J','2','8','R')
 UNION ALL SELECT item_code, MAINT_QTY FROM sa_t_stock_maint WHERE MAINT_YMD>'250299' AND maint_ymd<'260701' AND maint_tag='P' AND ISNULL(IN_PART_CODE,'')=''
 UNION ALL SELECT UPPER(mat_code), maint_qty*-1 FROM pu_t_stock_maint WHERE maint_ymd>'250299' AND maint_ymd<'260701' AND ISNULL(out_wh_gubun,'1')='2'
"""
CUR="""
 SELECT item_code, maint_qty inq, 0 outq, 0 etc FROM sa_t_stock_maint WHERE maint_ymd>='260701' AND maint_tag IN ('B','V') AND maint_qty<>0
 UNION ALL SELECT item_code, maint_qty,0,0 FROM sa_t_stock_maint WHERE maint_ymd>='260701' AND maint_tag='P' AND ISNULL(IN_PART_CODE,'')='' AND maint_qty<>0
 UNION ALL SELECT UPPER(mat_code), maint_qty*-1,0,0 FROM pu_t_stock_maint WHERE maint_ymd>='260701' AND ISNULL(out_wh_gubun,'1')='2'
 UNION ALL SELECT item_code, 0, maint_qty*-1, 0 FROM sa_t_stock_maint WHERE maint_ymd>='260701' AND maint_tag IN ('J','8','R') AND maint_qty<>0
 UNION ALL SELECT item_code, 0, 0, maint_qty*-1 FROM sa_t_stock_maint WHERE maint_ymd>='260701' AND maint_tag='2' AND maint_qty<>0
"""
bf=live(f"SELECT UPPER(item_code) item, SUM(q) bf FROM ({BF}) t GROUP BY UPPER(item_code)")
cur=live(f"SELECT UPPER(item) item, SUM(inq) inq, SUM(outq) outq, SUM(etc) etc FROM ({CUR}) t GROUP BY UPPER(item)")
m=bf.merge(cur,on='item',how='outer').fillna(0)
m['stock']=m['bf']+m['inq']-m['outq']+m['etc']
nz=m[m['stock'].abs()>0.0001]
print(f"\n### 제품 수불장 재구성: 전체 {len(m)}품목, 재고<>0 {len(nz)}품목, 재고합(nz) {nz['stock'].sum():,.1f}  (라이브 좌측 2,634건/50,104) ###")
for it in ['MJU64433701','10900O']:
    r=m[m['item']==it]
    print(f"검증 {it}:", None if r.empty else dict(bf=round(float(r.bf.iloc[0]),2),inq=round(float(r.inq.iloc[0]),2),outq=round(float(r.outq.iloc[0]),2),etc=round(float(r.etc.iloc[0]),2),stock=round(float(r.stock.iloc[0]),2)))
