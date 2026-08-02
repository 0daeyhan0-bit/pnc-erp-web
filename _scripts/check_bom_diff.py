# -*- coding: utf-8 -*-
import sys, io, warnings
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, r"d:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP")
import db_client
# SP 결과(용접 BOM풀기)가 임시테이블에 남아있음
print(db_client.run_query("""
SELECT
  COUNT(*) 전체건수,
  SUM(CASE WHEN stock_qty<>0 THEN 1 ELSE 0 END) 재고있는건수,
  SUM(CASE WHEN stock_qty=0 THEN 1 ELSE 0 END) 재고0건수,
  CAST(SUM(stock_qty) AS DECIMAL(18,2)) 수량합,
  CAST(SUM(ROUND(stock_qty*ISNULL(item_cost2,0),0)) AS DECIMAL(18,0)) 금액_행별반올림합,
  CAST(ROUND(SUM(stock_qty*ISNULL(item_cost2,0)),0) AS DECIMAL(18,0)) 금액_합계후반올림
FROM PR_T_TEMP_STOCK_480_T3
""").to_string(index=False))
print("\n화면(ERP): 3,072건 / 142,353.03 / 346,498,882")
