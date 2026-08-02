# -*- coding: utf-8 -*-
import sys, io, os, warnings
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, r"d:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP")
import db_client
print("DB:", db_client.DB_DATABASE)

# SP 정의 가져오기 (조회)
d = db_client.run_query("""
SELECT OBJECT_DEFINITION(OBJECT_ID('dbo.[SP_PR_생산재고수불현황_BOM풀기]')) AS def
""")
definition = d.iloc[0,0]
if definition is None:
    print("SP 정의를 찾을 수 없음 (이름 확인 필요)")
    print(db_client.run_query("SELECT name FROM sys.procedures WHERE name LIKE '%생산재고%' OR name LIKE '%BOM%'").to_string(index=False))
else:
    out = r"C:\Users\admin\AppData\Local\Temp\claude\d-----------100-AI-AGENT\02b63e35-1303-4eb0-8eb4-29df63d29c62\scratchpad\SP_BOM.sql"
    open(out,"w",encoding="utf-8").write(definition)
    print(f"SP 길이: {len(definition)}자, 저장: {out}")
    print("\n===== SP 앞부분 (2500자) =====")
    print(definition[:2500])
    # 쓰기 위험 키워드 점검
    import re
    for kw in ['INSERT ','UPDATE ','DELETE ','DROP ','TRUNCATE ','CREATE TABLE','ALTER ']:
        n = len(re.findall(kw, definition, re.I))
        if n: print(f"  [주의] '{kw.strip()}' {n}회 등장")
