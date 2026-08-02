# -*- coding: utf-8 -*-
# salesstock(07/15) vs 110수불장 07/15컷오프 재구성 — 같은날짜 기준 정합성 판정
import sys,io,json,warnings; warnings.filterwarnings('ignore')
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding='utf-8')
sys.path.insert(0,r'd:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP')
import pandas as pd,db_client,pyodbc,collections
def live(sql):
    cs=f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};DATABASE=PARTNER_ERP;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}'
    cn=pyodbc.connect(cs,readonly=True)
    try: return pd.read_sql(sql,cn)
    finally: cn.close()
END="'260715'"
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
m=bf.merge(cur,on='item',how='outer').fillna(0)
m['stock']=m['bf']+m['inq']-m['outq']-m['etc']   # 재고=기초+입고-출고-기타출고
rec={r.item:(r.bf,r.inq,r.outq,r.etc,r.stock) for r in m.itertuples()}
raw=open(r'd:\피앤씨인더스트리\100_AI_AGENT\PNC_ERP_Web\js\data.js',encoding='utf-8').read()
DB=json.loads(raw[raw.index('const DB = ')+11:raw.rindex(';')])
ssq=collections.defaultdict(float); ssrow={}
for r in DB['salesStock']:
    ssq[r['cd']]+=float(r['qty'] or 0); ssrow[r['cd']]=r
big=[]
for it,q in ssq.items():
    rq=rec.get(it,(0,0,0,0,0))[4]
    if abs(q-rq)>0.5: big.append((it,q,rq,q-rq))
print(f"salesStock 고유품목 {len(ssq)} / 07-15컷 재구성 품목 {len(rec)}")
print(f"재고<>0.5 차이 품목수: {len(big)}  (0이면 salesstock=110로직 완전정합)")
print("\n[차이 상위 12 — salesStock(내) vs 07/15컷 수불장(라이브재구성)]")
for it,a,b,d in sorted(big,key=lambda x:-abs(x[3]))[:12]:
    rr=rec.get(it,(0,0,0,0,0)); s=ssrow.get(it,{})
    print(f"  {it:15} ss재고 {a:9.1f} vs 재구성 {b:9.1f} (차 {d:+8.1f}) | ss입{s.get('inq')} 출{s.get('outq')} / 재구성입{rr[1]:.0f} 출{rr[2]:.0f}")
