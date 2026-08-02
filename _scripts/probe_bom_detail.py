# -*- coding: utf-8 -*-
import sys, io, warnings
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, r"d:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP")
import db_client
def show(t,q):
    print(f"\n===== {t} =====")
    try: print(db_client.run_query(q).to_string(index=False))
    except Exception as e: print("ERR:",e)

# FROM/TO_APPLY_YMD 형식 샘플
show("1. FROM/TO_APPLY_YMD 형식", "SELECT TOP 5 ITEM_CODE, MAT_CODE, FROM_APPLY_YMD, TO_APPLY_YMD, USE_QTY, SAGUB_FLAG FROM PR_M_ITEM_BOM")

# 자식(MAT_CODE)이 CM_ITEM_MST에 없는 고아 수
show("2. BOM 부모/자식의 품목마스터 커버리지", """
SELECT
 (SELECT COUNT(DISTINCT LTRIM(RTRIM(ITEM_CODE))) FROM PR_M_ITEM_BOM) parents,
 (SELECT COUNT(DISTINCT LTRIM(RTRIM(ITEM_CODE))) FROM PR_M_ITEM_BOM b
    WHERE NOT EXISTS(SELECT 1 FROM CM_ITEM_MST m WHERE m.item_cd=LTRIM(RTRIM(b.ITEM_CODE)))) parent_orphan,
 (SELECT COUNT(DISTINCT LTRIM(RTRIM(MAT_CODE))) FROM PR_M_ITEM_BOM) children,
 (SELECT COUNT(DISTINCT LTRIM(RTRIM(MAT_CODE))) FROM PR_M_ITEM_BOM b
    WHERE NOT EXISTS(SELECT 1 FROM CM_ITEM_MST m WHERE m.item_cd=LTRIM(RTRIM(b.MAT_CODE)))) child_orphan
""")

# 리비전 개수: 한 품목이 여러 FROM_APPLY_YMD (이력)
show("3. 다중 리비전 품목 (FROM_APPLY_YMD 여러개)", """
SELECT versions AS 리비전수, COUNT(*) AS 품목수 FROM (
  SELECT ITEM_CODE, COUNT(DISTINCT FROM_APPLY_YMD) versions FROM PR_M_ITEM_BOM GROUP BY ITEM_CODE
) t GROUP BY versions ORDER BY versions
""")

# 공정마스터 존재?
show("4. 공정마스터 후보 (CM_M_PROC / PU_M_PROC / CM_M_MASTER PR008 등)", """
SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_TYPE='BASE TABLE' AND (TABLE_NAME LIKE '%PROC%' OR TABLE_NAME LIKE '%_PROC%')
ORDER BY TABLE_NAME
""")
show("4b. CM_M_PROC 컬럼(있으면)", "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME='CM_M_PROC' ORDER BY ORDINAL_POSITION")
show("4c. GAGONG_PROC_CODE 실제 값 상위", "SELECT TOP 15 GAGONG_PROC_CODE, COUNT(*) c FROM PR_M_ITEM_BOM GROUP BY GAGONG_PROC_CODE ORDER BY c DESC")
