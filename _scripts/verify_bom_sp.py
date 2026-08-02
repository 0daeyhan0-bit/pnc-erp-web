# -*- coding: utf-8 -*-
"""SP_PR_생산재고수불현황_BOM풀기 를 TEST3에서 실행 → 화면값(용접 BOM풀기) 대조"""
import sys, io, warnings
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, r"d:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP")
import db_client
assert db_client.DB_DATABASE.strip().upper() != 'PARTNER_ERP', "운영 DB에서는 실행 금지!"
print("DB:", db_client.DB_DATABASE)

# 1) SP 실행 (임시테이블 PR_T_TEMP_STOCK_480_T3 적재) — TEST3
db_client.execute_query("EXEC dbo.[SP_PR_생산재고수불현황_BOM풀기] '260701','260715','1'")
print("SP 실행 완료")

# 2) 결과 집계 (임시테이블에서 조회)
print("\n화면 기준값: 건수 3,072 / 현재고 142,353.03 / 금액 346,498,882")
print("\n내 재현값:")
print(db_client.run_query("""
SELECT COUNT(*) 건수,
       CAST(SUM(stock_qty) AS DECIMAL(18,2)) 현재고,
       CAST(SUM(ROUND(stock_qty*ISNULL(MAT_COST,0),0)) AS DECIMAL(18,0)) 금액_MATCOST,
       CAST(SUM(ROUND(stock_qty*ISNULL(item_cost2,0),0)) AS DECIMAL(18,0)) 금액_item_cost2
FROM PR_T_TEMP_STOCK_480_T3
""").to_string(index=False))

# 3) 컬럼 확인 + 샘플
print("\n[임시테이블 컬럼]")
print(", ".join(db_client.run_query("SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME='PR_T_TEMP_STOCK_480_T3' ORDER BY ORDINAL_POSITION")['COLUMN_NAME'].tolist()))
print("\n[샘플 5행]")
print(db_client.run_query("SELECT TOP 5 item_code, mat_code, stock_qty, MAT_COST, item_cost2, item_desc FROM PR_T_TEMP_STOCK_480_T3 WHERE stock_qty<>0 ORDER BY stock_qty DESC").to_string(index=False))
