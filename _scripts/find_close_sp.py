# -*- coding: utf-8 -*-
import sys, io, warnings
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, r"d:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP")
import db_client
print("== 정의에 trans_amt 또는 basic_amt+input_amt 포함 SP ==")
print(db_client.run_query("""
SELECT o.name, o.type_desc FROM sys.sql_modules m JOIN sys.objects o ON o.object_id=m.object_id
WHERE m.definition LIKE '%trans_amt%'
   OR (m.definition LIKE '%basic_amt%' AND m.definition LIKE '%input_amt%')
ORDER BY o.name
""").to_string(index=False))

print("\n== 이름에 마감/CLOSE/MONTH/월 포함 프로시저 ==")
print(db_client.run_query("""
SELECT name FROM sys.objects WHERE type='P'
AND (name LIKE '%마감%' OR name LIKE '%CLOSE%' OR name LIKE '%MONTH%' OR name LIKE '%월수불%' OR name LIKE '%수불마감%')
ORDER BY name
""").to_string(index=False))

print("\n== 정의에 PU_T_MONTH_STOCK_WH_DAILY 를 문자열로 포함(대소문자/공백 무관) ==")
print(db_client.run_query("""
SELECT o.name FROM sys.sql_modules m JOIN sys.objects o ON o.object_id=m.object_id
WHERE REPLACE(REPLACE(LOWER(m.definition),' ',''),CHAR(9),'') LIKE '%pu_t_month_stock_wh_daily%'
ORDER BY o.name
""").to_string(index=False))
