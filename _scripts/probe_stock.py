# -*- coding: utf-8 -*-
import sys, io, warnings
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, r"d:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP")
import db_client
def show(t,q):
    print(f"\n== {t} ==")
    try: print(db_client.run_query(q).to_string(index=False))
    except Exception as e: print("ERR:",str(e)[:120])

# 재고/창고 관련 테이블 후보 + 행수
show("재고/창고 테이블 후보", """
SELECT t.TABLE_NAME, p.rows
FROM INFORMATION_SCHEMA.TABLES t
JOIN sys.tables st ON st.name=t.TABLE_NAME
JOIN sys.partitions p ON p.object_id=st.object_id AND p.index_id IN (0,1)
WHERE t.TABLE_TYPE='BASE TABLE'
 AND (LOWER(t.TABLE_NAME) LIKE '%stock%' OR LOWER(t.TABLE_NAME) LIKE '%_wh%'
      OR LOWER(t.TABLE_NAME) LIKE '%재고%' OR LOWER(t.TABLE_NAME) LIKE '%inv%'
      OR LOWER(t.TABLE_NAME) LIKE '%창고%' OR LOWER(t.TABLE_NAME) LIKE 'cm_m_wh%')
ORDER BY p.rows DESC
""")

# 창고 마스터 후보
show("창고 마스터 후보 컬럼(CM_M_WH 있으면)", """
SELECT COLUMN_NAME, DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME='CM_M_WH' ORDER BY ORDINAL_POSITION
""")
show("WH 관련 테이블", """
SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_TYPE='BASE TABLE'
 AND (TABLE_NAME LIKE '%WH%' OR TABLE_NAME LIKE '%WARE%') ORDER BY TABLE_NAME
""")
