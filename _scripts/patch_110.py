# -*- coding: utf-8 -*-
# 제품입출고현황(110) → data.js. 좌:제품재고(수불장,SA_T_ITEM_STOCK 유니버스), 우:입출고이력(l1)
import sys,io,json,warnings; warnings.filterwarnings('ignore')
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding='utf-8')
sys.path.insert(0,r'd:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP')
import pandas as pd,db_client,pyodbc
def live(sql):
    cs=f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};DATABASE=PARTNER_ERP;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}'
    cn=pyodbc.connect(cs,readonly=True)
    try: return pd.read_sql(sql,cn)
    finally: cn.close()
CUST="ISNULL((SELECT cust_desc FROM cm_m_cust m WHERE m.cust_code=a.cust_code),'')"
# 전월이월 bf (2502~0701)
BF="""
 SELECT UPPER(item_code) item, stock_qty q FROM sa_t_month_stock WHERE stock_yymm='2502'
 UNION ALL SELECT UPPER(item_code), MAINT_QTY FROM sa_t_stock_maint WHERE MAINT_YMD>'250299' AND maint_ymd<'260701' AND maint_tag IN ('B','V','J','2','8','R')
 UNION ALL SELECT UPPER(item_code), MAINT_QTY FROM sa_t_stock_maint WHERE MAINT_YMD>'250299' AND maint_ymd<'260701' AND maint_tag='P' AND ISNULL(IN_PART_CODE,'')=''
 UNION ALL SELECT UPPER(mat_code), maint_qty*-1 FROM pu_t_stock_maint WHERE maint_ymd>'250299' AND maint_ymd<'260701' AND ISNULL(out_wh_gubun,'1')='2'
"""
# 당월 라인(l1)
L1=f"""
 SELECT UPPER(a.item_code) item, a.maint_ymd ymd, a.maint_qty inq, CAST(0 AS decimal(18,4)) outq, CAST(0 AS decimal(18,4)) etc, CASE a.maint_tag WHEN 'V' THEN '세트출하' WHEN 'P' THEN '생산완료' ELSE '입고' END div, {CUST} cust FROM sa_t_stock_maint a WHERE a.maint_ymd>='260701' AND a.maint_tag IN ('B','V') AND a.maint_qty<>0
 UNION ALL SELECT UPPER(a.item_code), a.maint_ymd, a.maint_qty,0,0,'생산완료', {CUST} FROM sa_t_stock_maint a WHERE a.maint_ymd>='260701' AND a.maint_tag='P' AND ISNULL(a.in_part_code,'')='' AND a.maint_qty<>0
 UNION ALL SELECT UPPER(a.mat_code), a.maint_ymd, a.maint_qty*-1,0,0,'자재창고에서입고', {CUST} FROM pu_t_stock_maint a WHERE a.maint_ymd>='260701' AND ISNULL(a.out_wh_gubun,'1')='2'
 UNION ALL SELECT UPPER(a.item_code), a.maint_ymd, 0, a.maint_qty*-1,0, CASE a.maint_tag WHEN '8' THEN '무상공급' WHEN 'R' THEN '출하반품' ELSE '출하' END, {CUST} FROM sa_t_stock_maint a WHERE a.maint_ymd>='260701' AND a.maint_tag IN ('J','8','R') AND a.maint_qty<>0
 UNION ALL SELECT UPPER(a.item_code), a.maint_ymd, 0,0, a.maint_qty*-1,'재고조정', {CUST} FROM sa_t_stock_maint a WHERE a.maint_ymd>='260701' AND a.maint_tag='2' AND a.maint_qty<>0
"""
uni=live("SELECT UPPER(item_code) item, SUM(stock_qty) snap FROM SA_T_ITEM_STOCK GROUP BY UPPER(item_code)")
bf=live(f"SELECT item, SUM(q) bf FROM ({BF}) t GROUP BY item")
lines=live(f"SELECT item, ymd, inq, outq, etc, div, cust FROM ({L1}) x ORDER BY item, ymd")
info=live("""SELECT UPPER(item_code) item, item_desc, in_cust_code,
  (SELECT cust_desc FROM cm_m_cust c WHERE c.cust_code=i.in_cust_code) work_nm FROM pr_m_item i""")
net=lines.assign(v=lines.inq-lines.outq-lines.etc).groupby('item')['v'].sum().reset_index()  # 재고=기초+입고-출고-기타출고(etc=maint_qty*-1)
# 유니버스 기준 좌측
left=uni.merge(bf,on='item',how='left').merge(net,on='item',how='left').fillna({'bf':0,'v':0})
left['stock']=left['bf']+left['v']
left=left.merge(info.drop_duplicates('item'),on='item',how='left').fillna({'item_desc':'','work_nm':''})
left=left[left.stock.abs()>0.0001].copy().sort_values(['work_nm','item'])
prodItemStock=[[r.item, r.item_desc or '', r.work_nm or '', round(float(r.stock),3), round(float(r.bf),3)] for r in left.itertuples()]
keys=set(r.item for r in left.itertuples())
mv={}
for r in lines.itertuples():
    if r.item in keys: mv.setdefault(r.item,[]).append([r.ymd, round(float(r.inq),3), round(float(r.outq),3), round(float(r.etc),3), r.div, (r.cust or '').strip()])
path=r"d:\피앤씨인더스트리\100_AI_AGENT\PNC_ERP_Web\js\data.js"
raw=open(path,encoding='utf-8').read()
head=raw[:raw.index("const DB = ")+len("const DB = ")]
DB=json.loads(raw[raw.index("const DB = ")+len("const DB = "):raw.rindex(";")])
DB['prodItemStock']=prodItemStock; DB['prodItemMoves']=mv
open(path,'w',encoding='utf-8').write(head+json.dumps(DB,ensure_ascii=False,indent=0)+";\n")
print("data.js 기록 — prodItemStock", len(prodItemStock),"품목(재고<>0), moves", len(mv),", 재고합", round(sum(r[3] for r in prodItemStock),1))
print("검증 MJU64433701:", [r for r in prodItemStock if r[0]=='MJU64433701'])
