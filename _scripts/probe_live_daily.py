# -*- coding: utf-8 -*-
# 라이브 PARTNER_ERP 를 '읽기 전용(SELECT)'으로만 조회 — 일수불장 7월 가용일 확인
import sys, io, warnings
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, r"d:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP")
import db_client, pyodbc, pandas as pd

def live_read(sql):
    conn_str=(f"DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};"
              f"DATABASE=PARTNER_ERP;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}")
    conn=pyodbc.connect(conn_str, readonly=True)   # 읽기전용 연결
    try: return pd.read_sql(sql, conn)
    finally: conn.close()

print("== [LIVE] PU_T_MONTH_STOCK_WH_DAILY 7월 STOCK_YMD 분포 ==")
print(live_read("SELECT STOCK_YMD, COUNT(*) cnt FROM PU_T_MONTH_STOCK_WH_DAILY WHERE cust_code='Z99990' AND STOCK_YMD LIKE '2607%' GROUP BY STOCK_YMD ORDER BY STOCK_YMD").to_string(index=False))

print("\n== [LIVE] 일수불 합계 STOCK_YMD=260715 ==")
print(live_read("""
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
where t.cust_code='Z99990' and t.STOCK_YMD='260715'
""").to_string(index=False))
