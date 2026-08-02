# -*- coding: utf-8 -*-
import sys, io, warnings
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, r"d:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP")
import db_client
print("== PU_T_MONTH_STOCK_WH_DAILY 를 참조하는 프로시저 ==")
print(db_client.run_query("""
SELECT o.name, o.type_desc
FROM sys.sql_modules m JOIN sys.objects o ON o.object_id=m.object_id
WHERE m.definition LIKE '%PU_T_MONTH_STOCK_WH_DAILY%'
ORDER BY o.name
""").to_string(index=False))
