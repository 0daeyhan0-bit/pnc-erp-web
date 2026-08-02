# -*- coding: utf-8 -*-
# 생산재고조회 prodStock 복구 + 460데이터를 prodPartStock로 이관
import sys,io,json,warnings; warnings.filterwarnings('ignore')
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding='utf-8')
sys.path.insert(0,r'd:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP')
import db_client
def q(sql):
    import json as _j
    return _j.loads(db_client.run_query(sql).to_json(orient='records',force_ascii=False))
_U = """
SELECT a.gagong_proc_code gpc, A.MAT_CODE mat, A.STOCK_QTY basic,0 inq,0 outq,0 etc FROM PR_T_MONTH_STOCK_WH A WHERE A.STOCK_YYMM='2502'
UNION ALL SELECT a.to_gagong_proc_code,A.MAT_CODE,iif(a.maint_ymd<'260701',-A.MAINT_QTY,0),iif(a.maint_ymd<'260701',0,-A.MAINT_QTY),0,0 FROM PU_T_STOCK_MAINT A WHERE A.MAINT_YMD>'250299' and A.MAINT_YMD<='260715' AND a.maint_tag='B' AND isnull(a.out_wh_gubun,'1')='1'
UNION ALL SELECT A.gagong_proc_code,a.mat_code,iif(a.cut_ymd<'260701',a.cut_QTY,0),iif(a.cut_ymd<'260701',0,a.cut_QTY),0,0 FROM pu_t_cut_dtl a WHERE A.cut_ymd>'250299' and A.cut_ymd<='260715'
UNION ALL SELECT a.to_gagong_proc_code,A.MAT_CODE,iif(a.MAINT_YMD<'260701',a.MAINT_QTY,0),0,iif(a.MAINT_YMD<'260701',0,-a.MAINT_QTY),0 FROM PU_T_STOCK_MAINT A WHERE A.MAINT_YMD>'250299' and A.MAINT_YMD<='260715' AND a.maint_tag='T' and isnull(a.out_wh_gubun,'3')='3'
UNION ALL SELECT a.to_gagong_proc_code,A.MAT_CODE,iif(a.MAINT_YMD<'260701',-a.MAINT_QTY,0),0,iif(a.MAINT_YMD<'260701',0,a.MAINT_QTY),0 FROM PU_T_STOCK_MAINT A WHERE A.MAINT_YMD>'250299' and A.MAINT_YMD<='260715' AND a.maint_tag='C'
UNION ALL SELECT A.stock_part_code,a.item_code,iif(a.prod_ymd<'260701',a.prod_qty,0),iif(a.prod_ymd<'260701',0,a.prod_qty),0,0 FROM pr_t_prod_dtl a WHERE A.prod_ymd>'250299' and A.prod_ymd<='260715' and a.stock_part_code>'' and not exists (select 1 from sa_t_stock_maint where maint_ymd=a.prod_ymd and item_code=a.item_code and in_part_code=a.stock_part_code)
UNION ALL SELECT A.IN_PART_CODE,a.item_code,iif(a.MAINT_YMD<'260701',a.MAINT_QTY,0),iif(a.MAINT_YMD<'260701',0,a.MAINT_QTY),0,0 FROM sa_t_stock_maint a WHERE A.maint_ymd>'250299' and A.MAINT_YMD<='260715' and a.in_part_code>''
UNION ALL SELECT A.PART_CODE,A.MAT_CODE,iif(a.MAINT_YMD<'260701',a.MAINT_QTY,0),iif(a.MAINT_YMD<'260701',0,a.MAINT_QTY),0,0 FROM PR_T_STOCK_MAINT_MAT A WHERE A.MAINT_YMD>'250299' and A.MAINT_YMD<='260715' AND A.MAINT_TAG='3'
UNION ALL SELECT A.PART_CODE,A.MAT_CODE,iif(a.MAINT_YMD<'260701',a.MAINT_QTY,0),0,0,iif(a.MAINT_YMD<'260701',0,a.MAINT_QTY) FROM PR_T_STOCK_MAINT_MAT A WHERE A.MAINT_YMD>'250299' and A.MAINT_YMD<='260715' AND A.MAINT_TAG in ('2','1')
UNION ALL SELECT A.PART_CODE,A.MAT_CODE,iif(a.MAINT_YMD<'260701',a.MAINT_QTY,0),0,iif(a.MAINT_YMD<'260701',0,-a.MAINT_QTY),0 FROM PR_T_STOCK_MAINT_MAT A JOIN PR_M_ITEM M ON A.MAT_CODE=M.ITEM_CODE WHERE A.MAINT_YMD>'250299' and A.MAINT_YMD<='260715' AND A.MAINT_TAG='4'
"""
_C2 = "(select top 1 q.item_cost from pr_m_item_cost q where q.item_code=agg.mat and q.cost_tag='1' and q.cost_apply_ymd<='260701' and q.cust_code=case when pi.work_code='P2' then '2228' else pi.in_cust_code end order by q.cost_apply_ymd desc)"
sql=f"""
;WITH agg AS (
  SELECT LTRIM(RTRIM(t.mat)) mat, ISNULL(LTRIM(RTRIM(t.gpc)),'') line,
     SUM(basic) basic, SUM(inq) inq, SUM(outq) outq, SUM(etc) adj,
     SUM(basic)+SUM(inq)-SUM(outq)+SUM(etc) qty
  FROM ({_U}) t GROUP BY LTRIM(RTRIM(t.mat)), ISNULL(LTRIM(RTRIM(t.gpc)),'')
  HAVING (SUM(basic)<>0 OR SUM(inq)<>0 OR SUM(outq)<>0 OR SUM(etc)<>0)
)
SELECT CASE WHEN agg.line='P0001' THEN 'GAGONG' ELSE 'WELD' END stage,
  CASE WHEN agg.line='P0001' THEN '' ELSE agg.line END loc,
  agg.mat cd, m.item_nm nm, m.item_type type,
  agg.basic, agg.inq, agg.outq, agg.adj, agg.qty,
  {_C2} cost, CAST(ROUND(agg.qty*ISNULL({_C2},0),0) AS DECIMAL(18,0)) amt
FROM agg JOIN CM_ITEM_MST m ON m.item_cd=agg.mat JOIN PR_M_ITEM pi ON pi.item_code=agg.mat
"""
print("prodStock 쿼리 실행중...")
ps=q(sql)
print("복구 prodStock:",len(ps),"행")
import collections
by=collections.Counter(r['stage'] for r in ps)
for st in ['GAGONG','WELD']:
    rows=[r for r in ps if r['stage']==st]
    print(f"  {st}: {len(rows)}건 재고합 {sum(float(r['qty'] or 0) for r in rows):,.0f} 금액 {sum(float(r['amt'] or 0) for r in rows):,.0f}")
path=r"d:\피앤씨인더스트리\100_AI_AGENT\PNC_ERP_Web\js\data.js"
raw=open(path,encoding='utf-8').read()
DB=json.loads(raw[raw.index("const DB = ")+len("const DB = "):raw.rindex(";")])
DB['prodPartStock']=DB.get('prodStock')   # 460데이터 이관
DB['prodStock']=ps                         # 생산재고조회 복구
head=raw[:raw.index("const DB = ")+len("const DB = ")]
open(path,'w',encoding='utf-8').write(head+json.dumps(DB,ensure_ascii=False,indent=0)+";\n")
print("data.js: prodStock 복구 + prodPartStock 이관(460)", "prodPartStock",len(DB['prodPartStock']))
