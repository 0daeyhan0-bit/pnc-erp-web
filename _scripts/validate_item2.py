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

# 진짜 매입처/단가 마스터가 별도 테이블인지 확인
show("A. 매입처/단가 관련 테이블 후보", """
SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_TYPE='BASE TABLE'
 AND (TABLE_NAME LIKE '%매입처%' OR LOWER(TABLE_NAME) LIKE '%cust%price%'
      OR LOWER(TABLE_NAME) LIKE '%item%cost%' OR LOWER(TABLE_NAME) LIKE 'pu_m%'
      OR LOWER(TABLE_NAME) LIKE '%_price%' OR TABLE_NAME LIKE 'CM_M%')
ORDER BY TABLE_NAME
""")

# ITEM_COST 실제 채워져 있는지 (마이그레이션은 없는 ITEM_BUY_PRICE를 읽어 0이 됨)
show("B. ITEM_COST 실제 값 존재율", """
SELECT COUNT(*) total,
 SUM(CASE WHEN ITEM_COST IS NOT NULL AND ITEM_COST>0 THEN 1 ELSE 0 END) has_cost
FROM PR_M_ITEM
""")

# 사급/조달 구분 플래그 분포 (새 모델이 버린 핵심 속성)
show("C. 조달/사급 구분 플래그 분포", """
SELECT
 SUM(CASE WHEN SAGUB_STOCK_FLAG='Y' THEN 1 ELSE 0 END) sagub_stock_Y,
 SUM(CASE WHEN STD_WON_MAT_FLAG='Y' THEN 1 ELSE 0 END) std_won_mat_Y,
 SUM(CASE WHEN SUB_MAT_FLAG='Y' THEN 1 ELSE 0 END) sub_mat_Y
FROM PR_M_ITEM
""")
show("C2. OBTAIN_GUBUN(조달구분)/PUR_GUBUN(구매구분)/METAL_GUBUN 분포", """
SELECT OBTAIN_GUBUN, PUR_GUBUN, COUNT(*) c FROM PR_M_ITEM
GROUP BY OBTAIN_GUBUN, PUR_GUBUN ORDER BY c DESC
""")

# 상태값(사용여부) 실제 컬럼
show("D. ITEM_STATUS / AUTO_SALE_STOP_FLAG 분포", """
SELECT ITEM_STATUS, AUTO_SALE_STOP_FLAG, COUNT(*) c FROM PR_M_ITEM
GROUP BY ITEM_STATUS, AUTO_SALE_STOP_FLAG ORDER BY c DESC
""")

# 매입처정보 별도 테이블 컬럼 (있으면)
show("E. 품목별_매입처정보2 컬럼 (존재시)", """
SELECT COLUMN_NAME, DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_NAME='품목별_매입처정보2' ORDER BY ORDINAL_POSITION
""")
