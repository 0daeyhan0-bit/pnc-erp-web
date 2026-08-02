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

# --- A. Row counts of the LIVE (non-backup) BOM tables ---
show("A. LIVE BOM TABLE ROW COUNTS", """
SELECT 'PR_M_ITEM_BOM (생산BOM 헤더)' AS tbl, COUNT(*) c FROM PR_M_ITEM_BOM
UNION ALL SELECT 'PR_M_ITEM_BOM_DTL (전개상세)', COUNT(*) FROM PR_M_ITEM_BOM_DTL
UNION ALL SELECT 'PR_M_ITEM_BOM_SUB', COUNT(*) FROM PR_M_ITEM_BOM_SUB
UNION ALL SELECT 'PR_M_MODEL_BOM (개발/모델BOM)', COUNT(*) FROM PR_M_MODEL_BOM
UNION ALL SELECT 'CS_M_ITEM_BOM (원가BOM)', COUNT(*) FROM CS_M_ITEM_BOM
""")

# --- B. Vendor/Process coupling in 생산BOM: same ITEM+MAT appearing under multiple vendors/processes ---
show("B1. PR_M_ITEM_BOM: distinct 조합 규모", """
SELECT COUNT(*) AS total_rows,
       COUNT(DISTINCT ITEM_CODE) AS distinct_items,
       COUNT(DISTINCT CUST_CODE) AS distinct_custcode_in_bom,
       COUNT(DISTINCT GAGONG_PROC_CODE) AS distinct_gagong_proc,
       COUNT(DISTINCT PROC_GUBUN) AS distinct_proc_gubun
FROM PR_M_ITEM_BOM
""")

# how many (ITEM_CODE, MAT_CODE) pairs are duplicated because CUST_CODE / proc differs
show("B2. 같은 (제품+자재)인데 거래처(CUST_CODE)가 달라 행이 쪼개진 사례 수", """
SELECT COUNT(*) AS pairs_split_by_vendor FROM (
  SELECT ITEM_CODE, MAT_CODE
  FROM PR_M_ITEM_BOM
  GROUP BY ITEM_CODE, MAT_CODE
  HAVING COUNT(DISTINCT ISNULL(CUST_CODE,'')) > 1
) t
""")

show("B3. 같은 (제품+자재)인데 가공공정(GAGONG_PROC_CODE)이 달라 행이 쪼개진 사례 수", """
SELECT COUNT(*) AS pairs_split_by_proc FROM (
  SELECT ITEM_CODE, MAT_CODE
  FROM PR_M_ITEM_BOM
  GROUP BY ITEM_CODE, MAT_CODE
  HAVING COUNT(DISTINCT ISNULL(GAGONG_PROC_CODE,'')) > 1
) t
""")

show("B4. 유효기간(FROM/TO_APPLY_YMD)으로 세대분리된 제품 수 (한 제품이 여러 버전)", """
SELECT COUNT(*) AS items_with_multiple_versions FROM (
  SELECT ITEM_CODE FROM PR_M_ITEM_BOM
  GROUP BY ITEM_CODE
  HAVING COUNT(DISTINCT FROM_APPLY_YMD) > 1
) t
""")

# --- C. Dev(Model) BOM vs Prod(Item) BOM mismatch ---
show("C1. 개발BOM(MODEL) vs 생산BOM(ITEM) 커버리지", """
SELECT
 (SELECT COUNT(DISTINCT ITEM_CODE) FROM PR_M_MODEL_BOM) AS model_bom_items,
 (SELECT COUNT(DISTINCT ITEM_CODE) FROM PR_M_ITEM_BOM)  AS item_bom_items
""")

# --- D. columns of PR_M_MODEL_BOM & CS_M_ITEM_BOM for structure comparison ---
show("D1. PR_M_MODEL_BOM columns", """
SELECT COLUMN_NAME, DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_NAME='PR_M_MODEL_BOM' ORDER BY ORDINAL_POSITION
""")
show("D2. CS_M_ITEM_BOM columns", """
SELECT COLUMN_NAME, DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_NAME='CS_M_ITEM_BOM' ORDER BY ORDINAL_POSITION
""")
