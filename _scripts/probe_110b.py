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
print('### SA_T_ITEM_STOCK 컬럼 & 집계 ###')
print([c for c in live("SELECT TOP 1 * FROM SA_T_ITEM_STOCK").columns])
print(live("SELECT COUNT(*) n, SUM(stock_qty) q FROM SA_T_ITEM_STOCK").to_string(index=False), " (라이브 좌측 2,634건/50,104)")
BF="""
 SELECT item_code, stock_qty q FROM sa_t_month_stock WHERE stock_yymm='2502'
 UNION ALL SELECT item_code, MAINT_QTY FROM sa_t_stock_maint WHERE MAINT_YMD>'250299' AND maint_ymd<'260701' AND maint_tag IN ('B','V','J','2','8','R')
 UNION ALL SELECT item_code, MAINT_QTY FROM sa_t_stock_maint WHERE MAINT_YMD>'250299' AND maint_ymd<'260701' AND maint_tag='P' AND ISNULL(IN_PART_CODE,'')=''
 UNION ALL SELECT UPPER(mat_code), maint_qty*-1 FROM pu_t_stock_maint WHERE maint_ymd>'250299' AND maint_ymd<'260701' AND ISNULL(out_wh_gubun,'1')='2'
"""
CUR="""
 SELECT item_code, maint_qty inq, CAST(0 AS decimal(18,4)) outq, CAST(0 AS decimal(18,4)) etc FROM sa_t_stock_maint WHERE maint_ymd>='260701' AND maint_tag IN ('B','V') AND maint_qty<>0
 UNION ALL SELECT item_code, maint_qty,0,0 FROM sa_t_stock_maint WHERE maint_ymd>='260701' AND maint_tag='P' AND ISNULL(IN_PART_CODE,'')='' AND maint_qty<>0
 UNION ALL SELECT UPPER(mat_code), maint_qty*-1,0,0 FROM pu_t_stock_maint WHERE maint_ymd>='260701' AND ISNULL(out_wh_gubun,'1')='2'
 UNION ALL SELECT item_code, 0, maint_qty*-1, 0 FROM sa_t_stock_maint WHERE maint_ymd>='260701' AND maint_tag IN ('J','8','R') AND maint_qty<>0
 UNION ALL SELECT item_code, 0, 0, maint_qty*-1 FROM sa_t_stock_maint WHERE maint_ymd>='260701' AND maint_tag='2' AND maint_qty<>0
"""
bf=live(f"SELECT UPPER(item_code) item, SUM(q) bf FROM ({BF}) t GROUP BY UPPER(item_code)")
cur=live(f"SELECT UPPER(item_code) item, SUM(inq) inq, SUM(outq) outq, SUM(etc) etc FROM ({CUR}) t GROUP BY UPPER(item_code)")
m=bf.merge(cur,on='item',how='outer').fillna(0)
m['stock']=m['bf']+m['inq']-m['outq']+m['etc']
nz=m[m['stock'].abs()>0.0001]
print(f"\n### 제품 수불장 재구성: 전체 {len(m)}품목, 재고<>0 {len(nz)}품목, 재고합(nz) {nz['stock'].sum():,.1f} ###")
# SA_T_ITEM_STOCK 유니버스와 대조
uni=live("SELECT UPPER(item_code) item, SUM(stock_qty) snap FROM SA_T_ITEM_STOCK GROUP BY UPPER(item_code)")
cmp=uni.merge(m[['item','stock']],on='item',how='outer').fillna(0)
cmp['d']=(cmp['snap']-cmp['stock']).abs()
print("유니버스(SA_T_ITEM_STOCK) vs 수불장 재구성: 일치(<0.01)",int((cmp['d']<0.01).sum()),"/ 불일치",int((cmp['d']>=0.01).sum()))
for it in ['MJU64433701','10900O']:
    r=m[m['item']==it]
    print(f"검증 {it}:", None if r.empty else dict(bf=round(float(r.bf.iloc[0]),2),inq=round(float(r.inq.iloc[0]),2),outq=round(float(r.outq.iloc[0]),2),etc=round(float(r.etc.iloc[0]),2),stock=round(float(r.stock.iloc[0]),2)))
# 작업처 = pr_m_item.WORK_CODE -> 이름
print("\n### 작업처(WORK_CODE) 예시 매핑 ###")
print(live("""SELECT TOP 5 i.item_code, i.work_code, (SELECT cust_desc FROM cm_m_cust c WHERE c.cust_code=i.work_code) cust_nm FROM pr_m_item i WHERE i.work_code>'' """).to_string(index=False))
