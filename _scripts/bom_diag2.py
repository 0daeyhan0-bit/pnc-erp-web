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

# SUB table structure (핵심: SUB 품번 거래처/공정 결합)
show("E1. PR_M_ITEM_BOM_SUB columns", """
SELECT COLUMN_NAME, DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_NAME='PR_M_ITEM_BOM_SUB' ORDER BY ORDINAL_POSITION
""")

show("E2. PR_M_ITEM_BOM_SUB 규모/거래처·공정 결합도", """
SELECT COUNT(*) rows_total,
 COUNT(DISTINCT ITEM_CODE) distinct_items
FROM PR_M_ITEM_BOM_SUB
""")

# Model vs Item BOM overlap (correct keys)
show("F1. 개발BOM vs 생산BOM 모품목 커버리지", """
SELECT
 (SELECT COUNT(DISTINCT MODEL_NO)  FROM PR_M_MODEL_BOM) AS model_bom_parents,
 (SELECT COUNT(DISTINCT ITEM_CODE) FROM PR_M_ITEM_BOM)  AS item_bom_parents,
 (SELECT COUNT(DISTINCT ITEM_CODE) FROM CS_M_ITEM_BOM)  AS cost_bom_parents
""")

# 개발BOM에는 있으나 생산BOM에 없는 모품목 (불일치)
show("F2. 개발BOM(MODEL)에만 있고 생산BOM(ITEM)엔 없는 모품목 수", """
SELECT COUNT(*) AS in_model_not_in_item FROM (
  SELECT DISTINCT MODEL_NO FROM PR_M_MODEL_BOM
  EXCEPT
  SELECT DISTINCT ITEM_CODE FROM PR_M_ITEM_BOM
) t
""")
show("F3. 생산BOM(ITEM)에만 있고 개발BOM(MODEL)엔 없는 모품목 수", """
SELECT COUNT(*) AS in_item_not_in_model FROM (
  SELECT DISTINCT ITEM_CODE FROM PR_M_ITEM_BOM
  EXCEPT
  SELECT DISTINCT MODEL_NO FROM PR_M_MODEL_BOM
) t
""")

# 생산BOM vs 원가BOM 실제 내용 불일치 (같은 제품·자재인데 소요량 다른 케이스)
show("G. 생산BOM vs 원가BOM 소요량(USE_QTY) 불일치 건수", """
SELECT COUNT(*) AS qty_mismatch_rows
FROM PR_M_ITEM_BOM a
JOIN CS_M_ITEM_BOM  b
  ON a.ITEM_CODE=b.ITEM_CODE AND a.MAT_CODE=b.MAT_CODE
 AND a.FROM_APPLY_YMD=b.FROM_APPLY_YMD
WHERE a.USE_QTY <> b.USE_QTY
""")

# 공정(가공)이 BOM 행에 박혀있음을 보여주는 분포
show("H. 생산BOM 행이 가공공정별로 분산된 분포 (GAGONG_PROC_CODE)", """
SELECT TOP 20 GAGONG_PROC_CODE, PROC_GUBUN, COUNT(*) rows
FROM PR_M_ITEM_BOM
GROUP BY GAGONG_PROC_CODE, PROC_GUBUN
ORDER BY COUNT(*) DESC
""")
