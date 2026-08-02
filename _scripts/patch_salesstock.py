# -*- coding: utf-8 -*-
# 제품재고조회(salesStock)를 현재일자(07/18)로 재생성 → 제품입출고현황(110)과 재고수량 완전일치
import sys,io,json,warnings; warnings.filterwarnings('ignore')
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding='utf-8')
sys.path.insert(0,r'd:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP')
import pandas as pd,db_client,pyodbc
def live(sql):
    cs=f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};DATABASE=PARTNER_ERP;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}'
    cn=pyodbc.connect(cs,readonly=True)
    try: return pd.read_sql(sql,cn)
    finally: cn.close()
END="'260718'"
# 기초(07/01 opening) = 2502 + (2502~0701)  == 110 bf
BF="""
 SELECT UPPER(item_code) item, stock_qty q FROM sa_t_month_stock WHERE stock_yymm='2502'
 UNION ALL SELECT UPPER(item_code), MAINT_QTY FROM sa_t_stock_maint WHERE MAINT_YMD>'250299' AND maint_ymd<'260701' AND maint_tag IN ('B','V','J','2','8','R')
 UNION ALL SELECT UPPER(item_code), MAINT_QTY FROM sa_t_stock_maint WHERE MAINT_YMD>'250299' AND maint_ymd<'260701' AND maint_tag='P' AND ISNULL(IN_PART_CODE,'')=''
 UNION ALL SELECT UPPER(mat_code), maint_qty*-1 FROM pu_t_stock_maint WHERE maint_ymd>'250299' AND maint_ymd<'260701' AND ISNULL(out_wh_gubun,'1')='2'
"""
CUR=f"""
 SELECT UPPER(item_code) item, maint_qty inq, CAST(0 AS decimal(18,4)) outq, CAST(0 AS decimal(18,4)) etc FROM sa_t_stock_maint WHERE maint_ymd BETWEEN '260701' AND {END} AND maint_tag IN ('B','V') AND maint_qty<>0
 UNION ALL SELECT UPPER(item_code), maint_qty,0,0 FROM sa_t_stock_maint WHERE maint_ymd BETWEEN '260701' AND {END} AND maint_tag='P' AND ISNULL(in_part_code,'')='' AND maint_qty<>0
 UNION ALL SELECT UPPER(mat_code), maint_qty*-1,0,0 FROM pu_t_stock_maint WHERE maint_ymd BETWEEN '260701' AND {END} AND ISNULL(out_wh_gubun,'1')='2'
 UNION ALL SELECT UPPER(item_code), 0, maint_qty*-1, 0 FROM sa_t_stock_maint WHERE maint_ymd BETWEEN '260701' AND {END} AND maint_tag IN ('J','8','R') AND maint_qty<>0
 UNION ALL SELECT UPPER(item_code), 0,0, maint_qty*-1 FROM sa_t_stock_maint WHERE maint_ymd BETWEEN '260701' AND {END} AND maint_tag='2' AND maint_qty<>0
"""
bf=live(f"SELECT item, SUM(q) bf FROM ({BF}) t GROUP BY item")
cur=live(f"SELECT item, SUM(inq) inq, SUM(outq) outq, SUM(etc) etc FROM ({CUR}) t GROUP BY item")
info=live("""SELECT UPPER(item_code) item, item_desc, item_spec, item_cost,
  (SELECT cust_desc FROM cm_m_cust c WHERE c.cust_code=i.in_cust_code) wc, in_cust_code FROM pr_m_item i""")
m=bf.merge(cur,on='item',how='outer').fillna(0)
m['qty']=m['bf']+m['inq']-m['outq']-m['etc']
m=m.merge(info.drop_duplicates('item'),on='item',how='left').fillna({'item_desc':'','item_spec':'','item_cost':0,'wc':'','in_cust_code':''})
path=r"d:\피앤씨인더스트리\100_AI_AGENT\PNC_ERP_Web\js\data.js"
raw=open(path,encoding='utf-8').read()
DB=json.loads(raw[raw.index("const DB = ")+len("const DB = "):raw.rindex(";")])
# 기존 단가(cost) 유지 우선, 없으면 item_cost
oldcost={r['cd']:float(r.get('cost',0) or 0) for r in DB.get('salesStock',[])}
out=[]
for r in m.itertuples():
    if abs(r.qty)<0.0001: continue   # 0재고 제외(110과 동일 정책)
    cost=oldcost.get(r.item, float(r.item_cost or 0)) or float(r.item_cost or 0)
    out.append({'cd':r.item,'nm':r.item_desc or '','spec':r.item_spec or '','cls':'',
      'basic':round(float(r.bf),3),'inq':round(float(r.inq),3),'outq':round(float(r.outq),3),'adj':round(float(r.etc),3),
      'qty':round(float(r.qty),3),'cost':round(cost,2),'wc_cd':str(r.in_cust_code or ''),'wc':r.wc or '','amt':round(float(r.qty)*cost)})
out.sort(key=lambda x:-abs(x['amt']))
DB['salesStock']=out
head=raw[:raw.index("const DB = ")+len("const DB = ")]
open(path,'w',encoding='utf-8').write(head+json.dumps(DB,ensure_ascii=False,indent=0)+";\n")
print("salesStock 재생성:", len(out),"품목, 재고수량합", round(sum(x['qty'] for x in out),1),"(110=50,104)")
