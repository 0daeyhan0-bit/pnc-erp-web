# -*- coding: utf-8 -*-
import sys, io, warnings
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, r"d:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP")
import db_client
print("== 소분류(PR006) 전체 매핑 ==")
print(db_client.run_query("SELECT DETAIL_CODE cd, DETAIL_DESC nm FROM CM_M_MASTER_DETAIL WHERE KIND_CODE='PR006' ORDER BY DETAIL_CODE").to_string(index=False))

print("\n== 일수불 합계 STOCK_YMD=260531 ==")
print(db_client.run_query("""
select count(*) 건수,
  sum(t.basic_qty) 기초수량, sum(t.basic_amt) 기초금액,
  sum(t.input_qty) 입고수량, sum(t.input_amt) 입고금액,
  sum(t.output_qty) 출고수량, sum(t.output_amt) 출고금액,
  sum(t.trans_qty) 기타수량, sum(t.trans_amt) 기타금액,
  sum(t.stock_qty) 재고수량, sum(t.stock_amt) 재고금액
from PU_T_MONTH_STOCK_WH_DAILY t
join pr_m_item m on t.mat_code=m.item_code
join pr_m_proc_gagong g on t.gagong_proc_code=g.gagong_proc_code
left join cm_m_cust c on m.in_cust_code=c.cust_code
where t.cust_code='Z99990' and t.STOCK_YMD='260531'
""").to_string(index=False))
