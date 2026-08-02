# -*- coding: utf-8 -*-
"""화면(w_pr_stock_480, 가공창고, ~07/16) 대조: 수량 48,338 / 금액 321,496,145 / 665건 재현 검증"""
import sys, io, warnings
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, r"d:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP")
import db_client
TO='260715'   # 화면 수불기간 종료일
FR='260701'   # 당월 시작

UNION = f"""
SELECT a.gagong_proc_code gpc, A.MAT_CODE mat, A.STOCK_QTY basic,0 inq,0 outq,0 etc FROM PR_T_MONTH_STOCK_WH A WHERE A.STOCK_YYMM='2502'
UNION ALL SELECT a.to_gagong_proc_code,A.MAT_CODE,iif(a.maint_ymd<'{FR}',-A.MAINT_QTY,0),iif(a.maint_ymd<'{FR}',0,-A.MAINT_QTY),0,0 FROM PU_T_STOCK_MAINT A WHERE A.MAINT_YMD>'250299' and A.MAINT_YMD<='{TO}' AND a.maint_tag='B' AND isnull(a.out_wh_gubun,'1')='1'
UNION ALL SELECT A.gagong_proc_code,a.mat_code,iif(a.cut_ymd<'{FR}',a.cut_QTY,0),iif(a.cut_ymd<'{FR}',0,a.cut_QTY),0,0 FROM pu_t_cut_dtl a WHERE A.cut_ymd>'250299' and A.cut_ymd<='{TO}'
UNION ALL SELECT a.to_gagong_proc_code,A.MAT_CODE,iif(a.MAINT_YMD<'{FR}',a.MAINT_QTY,0),0,iif(a.MAINT_YMD<'{FR}',0,-a.MAINT_QTY),0 FROM PU_T_STOCK_MAINT A WHERE A.MAINT_YMD>'250299' and A.MAINT_YMD<='{TO}' AND a.maint_tag='T' and isnull(a.out_wh_gubun,'3')='3'
UNION ALL SELECT a.to_gagong_proc_code,A.MAT_CODE,iif(a.MAINT_YMD<'{FR}',-a.MAINT_QTY,0),0,iif(a.MAINT_YMD<'{FR}',0,a.MAINT_QTY),0 FROM PU_T_STOCK_MAINT A WHERE A.MAINT_YMD>'250299' and A.MAINT_YMD<='{TO}' AND a.maint_tag='C'
UNION ALL SELECT A.stock_part_code,a.item_code,iif(a.prod_ymd<'{FR}',a.prod_qty,0),iif(a.prod_ymd<'{FR}',0,a.prod_qty),0,0 FROM pr_t_prod_dtl a WHERE A.prod_ymd>'250299' and A.prod_ymd<='{TO}' and a.stock_part_code>'' and not exists (select 1 from sa_t_stock_maint where maint_ymd=a.prod_ymd and item_code=a.item_code and in_part_code=a.stock_part_code)
UNION ALL SELECT A.IN_PART_CODE,a.item_code,iif(a.MAINT_YMD<'{FR}',a.MAINT_QTY,0),iif(a.MAINT_YMD<'{FR}',0,a.MAINT_QTY),0,0 FROM sa_t_stock_maint a WHERE A.maint_ymd>'250299' and A.MAINT_YMD<='{TO}' and a.in_part_code>''
UNION ALL SELECT A.PART_CODE,A.MAT_CODE,iif(a.MAINT_YMD<'{FR}',a.MAINT_QTY,0),iif(a.MAINT_YMD<'{FR}',0,a.MAINT_QTY),0,0 FROM PR_T_STOCK_MAINT_MAT A WHERE A.MAINT_YMD>'250299' and A.MAINT_YMD<='{TO}' AND A.MAINT_TAG='3'
UNION ALL SELECT A.PART_CODE,A.MAT_CODE,iif(a.MAINT_YMD<'{FR}',a.MAINT_QTY,0),0,0,iif(a.MAINT_YMD<'{FR}',0,a.MAINT_QTY) FROM PR_T_STOCK_MAINT_MAT A WHERE A.MAINT_YMD>'250299' and A.MAINT_YMD<='{TO}' AND A.MAINT_TAG in ('2','1')
UNION ALL SELECT A.PART_CODE,A.MAT_CODE,iif(a.MAINT_YMD<'{FR}',a.MAINT_QTY,0),0,iif(a.MAINT_YMD<'{FR}',0,-a.MAINT_QTY),0 FROM PR_T_STOCK_MAINT_MAT A JOIN PR_M_ITEM M ON A.MAT_CODE=M.ITEM_CODE WHERE A.MAINT_YMD>'250299' and A.MAINT_YMD<='{TO}' AND A.MAINT_TAG='4'
"""

Q = f"""
SELECT COUNT(*) 건수,
       CAST(SUM(stock_qty) AS DECIMAL(18,0)) 총수량,
       CAST(SUM(ROUND(stock_qty*ISNULL(cost1,0),0)) AS DECIMAL(18,0)) 금액_품목단가,
       CAST(SUM(ROUND(stock_qty*ISNULL(cost2,0),0)) AS DECIMAL(18,0)) 금액_거래처단가
FROM (
  SELECT t.mat,
    SUM(basic)+SUM(inq)-SUM(outq)+SUM(etc) stock_qty,
    (select top 1 item_cost from pr_m_item_cost where item_code=t.mat and cost_apply_ymd<='{TO}' and cost_tag='1' order by cost_apply_ymd desc) cost1,
    (select top 1 item_cost from pr_m_item_cost q where q.item_code=t.mat and q.cost_tag='1' and q.cost_apply_ymd<='260701'
        and q.cust_code = case when m.work_code='P2' then '2228' else m.in_cust_code end
        order by q.cost_apply_ymd desc) cost2
  FROM ({UNION}) t
  JOIN pr_m_item m ON t.mat=m.item_code
  WHERE t.gpc='P0001'
  GROUP BY t.mat, m.work_code, m.in_cust_code
  HAVING (SUM(basic)<>0 or SUM(inq)<>0 or SUM(outq)<>0 or SUM(etc)<>0)
) x
"""
print("화면 기준값(07/15):  건수 642 / 수량 46,136 / 금액 320,593,440")
print("내 재현값:")
print(db_client.run_query(Q).to_string(index=False))
