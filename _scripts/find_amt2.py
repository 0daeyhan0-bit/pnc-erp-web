# -*- coding: utf-8 -*-
import sys, io, warnings
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, r"d:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP")
import db_client
print("목표: 346,498,882   / item_cost2 단순합=346,540,312")
print(db_client.run_query("""
SELECT
 CAST(SUM(ROUND(stock_qty*ISNULL(item_cost,0),0)) AS DECIMAL(18,0)) item_cost,
 CAST(SUM(ROUND(stock_qty*ROUND(ISNULL(item_cost2,0),0),0)) AS DECIMAL(18,0)) ic2_단가정수,
 CAST(ROUND(SUM(stock_qty*ISNULL(item_cost2,0)),0) AS DECIMAL(18,0)) ic2_합계반올림,
 CAST(SUM(ROUND(ROUND(stock_qty,0)*ISNULL(item_cost2,0),0)) AS DECIMAL(18,0)) 수량정수_ic2,
 CAST(SUM(CASE WHEN stock_qty<>0 THEN ROUND(stock_qty*ISNULL(item_cost2,0),0) ELSE 0 END) AS DECIMAL(18,0)) 재고0제외_ic2
FROM PR_T_TEMP_STOCK_480_T3
""").to_string(index=False))
