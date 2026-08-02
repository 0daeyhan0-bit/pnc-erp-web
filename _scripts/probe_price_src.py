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

# 화면 품목 6851A20022(W) 의 PR_M_ITEM_COST 원본
show("1. PR_M_ITEM_COST — 품목 6851A20022%", """
SELECT ITEM_CODE, CUST_CODE, COST_TAG, MKT, MAIN_FLAG, COST_APPLY_YMD, CURRENCY,
       MAT_COST, PROC_COST, OTHER_COST, ITEM_COST
FROM PR_M_ITEM_COST WHERE ITEM_CODE LIKE '6851A20022%'
ORDER BY COST_TAG, CUST_CODE, COST_APPLY_YMD DESC
""")

# COST_TAG / MKT 의미 파악 (전체 분포)
show("2. COST_TAG 분포", "SELECT ISNULL(COST_TAG,'(null)') COST_TAG, COUNT(*) c FROM PR_M_ITEM_COST GROUP BY COST_TAG ORDER BY c DESC")
show("3. MKT 분포", "SELECT ISNULL(MKT,'(null)') MKT, COUNT(*) c FROM PR_M_ITEM_COST GROUP BY MKT ORDER BY c DESC")
show("4. COST_TAG x MKT 교차", "SELECT ISNULL(COST_TAG,'-') tag, ISNULL(MKT,'-') mkt, COUNT(*) c FROM PR_M_ITEM_COST GROUP BY COST_TAG, MKT ORDER BY c DESC")

# 화면의 매입처(2022,2197,2198,2326) vs 매출처(1020) 가 이 테이블에 다 있나
show("5. 해당 거래처들이 PR_M_ITEM_COST에서 이 품목에 어떻게 나오나", """
SELECT CUST_CODE, COST_TAG, MKT, COUNT(*) rows, MAX(ITEM_COST) sample_cost
FROM PR_M_ITEM_COST WHERE ITEM_CODE LIKE '6851A20022%'
GROUP BY CUST_CODE, COST_TAG, MKT ORDER BY CUST_CODE
""")

# 별도 판매단가 테이블 후보
show("6. 판매단가/판가 테이블 후보", """
SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_TYPE='BASE TABLE' AND (LOWER(TABLE_NAME) LIKE '%sale%' OR LOWER(TABLE_NAME) LIKE '%price%'
   OR TABLE_NAME LIKE '%판매%' OR TABLE_NAME LIKE '%판가%' OR LOWER(TABLE_NAME) LIKE 'res_price%')
ORDER BY TABLE_NAME
""")
# res_price_ct 구조 (판가 후보)
show("7. res_price_ct 컬럼", "SELECT COLUMN_NAME, DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME='res_price_ct' ORDER BY ORDINAL_POSITION")
