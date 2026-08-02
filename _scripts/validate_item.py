# -*- coding: utf-8 -*-
import sys, io, warnings
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, r"d:\피앤씨인더스트리\100_AI_AGENT\Projects")
from db_client import run_query

def show(title, q):
    print(f"\n===== {title} =====")
    try:
        print(run_query(q).to_string(index=False))
    except Exception as e:
        print("ERR:", e)

# 1. 실제 PR_M_ITEM 컬럼 전체
show("1. PR_M_ITEM 전체 컬럼", """
SELECT COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH len
FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME='PR_M_ITEM'
ORDER BY ORDINAL_POSITION
""")

# 2. 마이그레이션이 참조하는 컬럼들이 실제 존재하는지
cols_used = ['ITEM_CODE','ITEM_DESC','ITEM_LGROUP','ITEM_SGROUP','ITEM_PIPE_MATERIAL',
 'ITEM_DIAM','ITEM_PIPE_ID','ITEM_THICK','ITEM_LENGTH','ITEM_WEIGHT','ITEM_SPEC',
 'KITTING_MIN','WELD_POINT_IN','WELD_POINT_OUT','WELD_TABLE_QTY','MAKE_TYPE',
 'SAFE_STOCK_MIN','SAFE_STOCK_MAX','JIG_LOCATION','UNIT','ITEM_BUY_PRICE','USE_YN',
 'CUST_CODE','VENDOR_CODE']
inlist = ",".join(f"'{c}'" for c in cols_used)
show("2. 마이그레이션 참조 컬럼 중 PR_M_ITEM에 실제 존재하는 것", f"""
SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_NAME='PR_M_ITEM' AND COLUMN_NAME IN ({inlist})
ORDER BY COLUMN_NAME
""")

# 3. 총 건수
show("3. PR_M_ITEM 총 품목수", "SELECT COUNT(*) AS total_items FROM PR_M_ITEM")

# 4. 대분류(ITEM_LGROUP) 분포 -> 분류로직 검증
show("4. ITEM_LGROUP 분포", """
SELECT ITEM_LGROUP, COUNT(*) cnt FROM PR_M_ITEM
GROUP BY ITEM_LGROUP ORDER BY cnt DESC
""")

# 5. 소분류(ITEM_SGROUP) 상위
show("5. ITEM_SGROUP 상위 25", """
SELECT TOP 25 ITEM_SGROUP, COUNT(*) cnt FROM PR_M_ITEM
GROUP BY ITEM_SGROUP ORDER BY cnt DESC
""")

# 6. New_ERP 결과 테이블이 생성/적재됐는지
show("6. New_ERP 테이블 존재 및 적재 건수", """
SELECT 'CM_ITEM_MST' t, COUNT(*) c FROM CM_ITEM_MST
UNION ALL SELECT 'CM_ITEM_RAW_MAT', COUNT(*) FROM CM_ITEM_RAW_MAT
UNION ALL SELECT 'CM_ITEM_SUB_MAT', COUNT(*) FROM CM_ITEM_SUB_MAT
UNION ALL SELECT 'CM_ITEM_CON', COUNT(*) FROM CM_ITEM_CON
UNION ALL SELECT 'CM_ITEM_S_ASSY', COUNT(*) FROM CM_ITEM_S_ASSY
UNION ALL SELECT 'CM_ITEM_PROD', COUNT(*) FROM CM_ITEM_PROD
UNION ALL SELECT 'CM_ITEM_SUPPLIER', COUNT(*) FROM CM_ITEM_SUPPLIER
""")
