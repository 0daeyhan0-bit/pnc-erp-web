# -*- coding: utf-8 -*-
import sys, io, warnings
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, r"d:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP")
import db_client
print("== PU_T_MONTH_STOCK_WH 월 분포 TOP8 ==")
print(db_client.run_query("SELECT TOP 8 STOCK_YYMM, COUNT(*) cnt FROM PU_T_MONTH_STOCK_WH WHERE cust_code='Z99990' GROUP BY STOCK_YYMM ORDER BY STOCK_YYMM DESC").to_string(index=False))

for ym in ('2606','2605'):
    print(f"\n== 월수불 합계 STOCK_YYMM={ym} ==")
    print(db_client.run_query(f"""
    select count(*) 건수,
      sum(t.basic_qty) 기초수량, sum(t.basic_amt) 기초금액,
      sum(t.input_qty) 입고수량, sum(t.input_amt) 입고금액,
      sum(t.output_qty) 출고수량, sum(t.output_amt) 출고금액,
      sum(t.trans_qty) 기타수량, sum(t.trans_amt) 기타금액,
      sum(t.stock_qty) 재고수량, sum(t.stock_amt) 재고금액
    from PU_T_MONTH_STOCK_WH t
    join pr_m_item m on t.mat_code=m.item_code
    join pr_m_proc_gagong g on t.gagong_proc_code=g.gagong_proc_code
    left join cm_m_cust c on m.in_cust_code=c.cust_code
    where t.cust_code='Z99990' and t.STOCK_YYMM='{ym}'
    """).to_string(index=False))
