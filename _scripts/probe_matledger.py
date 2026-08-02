# -*- coding: utf-8 -*-
import sys, io, warnings
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, r"d:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP")
import db_client
print("== PU_T_MONTH_STOCK_WH_DAILY 최근 날짜 TOP5 ==")
print(db_client.run_query("SELECT TOP 5 STOCK_YMD, COUNT(*) cnt FROM PU_T_MONTH_STOCK_WH_DAILY WHERE cust_code='Z99990' GROUP BY STOCK_YMD ORDER BY STOCK_YMD DESC").to_string(index=False))

for d in ('260717','260715'):
    print(f"\n== 일수불 합계 STOCK_YMD={d} ==")
    print(db_client.run_query(f"""
    select count(*) 건수,
      sum(t.basic_qty) 기초수량, sum(t.basic_amt) 기초금액,
      sum(t.input_qty) 입고수량, sum(t.input_amt) 입고금액,
      sum(t.output_qty) 출고수량, sum(t.output_amt) 출고금액,
      sum(t.trans_qty) 대체수량, sum(t.trans_amt) 대체금액,
      sum(t.stock_qty) 재고수량, sum(t.stock_amt) 재고금액
    from PU_T_MONTH_STOCK_WH_DAILY t
    join pr_m_item m on t.mat_code=m.item_code
    join pr_m_proc_gagong g on t.gagong_proc_code=g.gagong_proc_code
    left join cm_m_cust c on m.in_cust_code=c.cust_code
    where t.cust_code='Z99990' and t.STOCK_YMD='{d}'
    """).to_string(index=False))

print("\n== item_sgroup 분포 ==")
print(db_client.run_query("SELECT ISNULL(item_sgroup,'') sgroup, COUNT(*) cnt FROM pr_m_item GROUP BY item_sgroup ORDER BY cnt DESC").head(20).to_string(index=False))
print("\n== 소분류 코드→이름 후보 (CM_M_MASTER_DETAIL에 210/230/310) ==")
try:
    print(db_client.run_query("SELECT d.KIND_CODE, d.DETAIL_CODE, d.DETAIL_DESC FROM CM_M_MASTER_DETAIL d WHERE d.DETAIL_CODE IN ('210','230','310','310') ORDER BY d.KIND_CODE, d.DETAIL_CODE").to_string(index=False))
except Exception as e: print("ERR", str(e)[:100])
