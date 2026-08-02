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

# 1) BOM 레벨 사급 플래그 분포
show("1. PR_M_ITEM_BOM.SAGUB_FLAG 분포 (BOM 구성행 기준)", """
SELECT ISNULL(NULLIF(LTRIM(RTRIM(SAGUB_FLAG)),''),'(blank)') sagub_flag, COUNT(*) rows,
       COUNT(DISTINCT MAT_CODE) distinct_mat
FROM PR_M_ITEM_BOM GROUP BY ISNULL(NULLIF(LTRIM(RTRIM(SAGUB_FLAG)),''),'(blank)')
ORDER BY rows DESC
""")

# 2) 사급으로 쓰이는 자재(MAT_CODE)의 원래 SGROUP 분포 -> 사급이 특정 종류에 국한 안 됨을 확인
show("2. BOM에서 사급(SAGUB_FLAG=Y)인 자재의 SGROUP(성격) 분포", """
SELECT p.ITEM_SGROUP, COUNT(DISTINCT b.MAT_CODE) sagub_items
FROM PR_M_ITEM_BOM b JOIN PR_M_ITEM p ON p.ITEM_CODE=b.MAT_CODE
WHERE LTRIM(RTRIM(ISNULL(b.SAGUB_FLAG,'')))='Y'
GROUP BY p.ITEM_SGROUP ORDER BY sagub_items DESC
""")

# 3) SGROUP 310(LG사급)으로 분류된 품목들이 BOM에서 실제 사급으로 쓰이나
show("3. SGROUP 310 품목 vs BOM 사급플래그 교차", """
SELECT
 (SELECT COUNT(*) FROM PR_M_ITEM WHERE LTRIM(RTRIM(ITEM_SGROUP))='310') sg310_items,
 (SELECT COUNT(DISTINCT b.MAT_CODE) FROM PR_M_ITEM_BOM b JOIN PR_M_ITEM p ON p.ITEM_CODE=b.MAT_CODE
    WHERE LTRIM(RTRIM(p.ITEM_SGROUP))='310' AND LTRIM(RTRIM(ISNULL(b.SAGUB_FLAG,'')))='Y') sg310_used_as_sagub
""")

# 4) 별도 LG 사급 실적 테이블
show("4. SA_T_LG_SAGUB_DTL 컬럼/건수", """
SELECT COUNT(*) rows, COUNT(DISTINCT ITEM_CODE) distinct_items FROM SA_T_LG_SAGUB_DTL
""")
show("4b. SA_T_LG_SAGUB_DTL 컬럼", """
SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME='SA_T_LG_SAGUB_DTL' ORDER BY ORDINAL_POSITION
""")
