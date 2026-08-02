# -*- coding: utf-8 -*-
import sys, io, warnings
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, r"d:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP")
import db_client  # TEST2

def show(t,q):
    print(f"\n===== {t} =====")
    try: print(db_client.run_query(q).to_string(index=False))
    except Exception as e: print("ERR:",e)

# 1) 공통코드 마스터에서 품목분류 관련 KIND 찾기
show("1. CM_M_MASTER 중 품목/분류 관련 KIND", """
SELECT KIND_CODE, KIND_DESC FROM CM_M_MASTER
WHERE KIND_DESC LIKE N'%품목%' OR KIND_DESC LIKE N'%분류%' OR KIND_DESC LIKE N'%그룹%'
   OR KIND_DESC LIKE N'%대분류%' OR KIND_DESC LIKE N'%소분류%' OR KIND_DESC LIKE N'%GROUP%'
""")

# 2) SGROUP 코드값들이 DETAIL_CODE로 어떤 KIND에 정의돼 있나 + 그 뜻
show("2. DETAIL_CODE가 SGROUP값과 일치하는 코드정의", """
SELECT d.KIND_CODE, m.KIND_DESC, d.DETAIL_CODE, d.DETAIL_DESC
FROM CM_M_MASTER_DETAIL d
LEFT JOIN CM_M_MASTER m ON m.KIND_CODE=d.KIND_CODE
WHERE d.DETAIL_CODE IN ('110','120','130','210','220','230','310','910','991','992','993')
ORDER BY d.KIND_CODE, d.DETAIL_CODE
""")

# 3) LGROUP 코드(E/G/F/H/I/K) 정의 후보
show("3. DETAIL_CODE가 LGROUP값과 일치하는 코드정의", """
SELECT d.KIND_CODE, m.KIND_DESC, d.DETAIL_CODE, d.DETAIL_DESC
FROM CM_M_MASTER_DETAIL d LEFT JOIN CM_M_MASTER m ON m.KIND_CODE=d.KIND_CODE
WHERE d.DETAIL_CODE IN ('E','F','G','H','I','K')
ORDER BY d.KIND_CODE, d.DETAIL_CODE
""")

# 4) '납품=완제품' 판정 신호 후보들의 커버리지
show("4. 판매신호 후보 커버리지 (PR_M_ITEM 24,093 기준)", """
SELECT
 SUM(CASE WHEN LTRIM(RTRIM(ISNULL(SALE_CUST_CODE1,'')))<>'' THEN 1 ELSE 0 END) has_sale_cust,
 (SELECT COUNT(DISTINCT LTRIM(RTRIM(PART_NO))) FROM LG_UNIT_PRICE_DOOSUNG) lg_price_items
FROM PR_M_ITEM
""")

# 5) 판매실적 테이블에 등장하는 품목 수 (SA_ 계열)
show("5. SA_ 매출 계열 테이블 목록", """
SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_TYPE='BASE TABLE' AND TABLE_NAME LIKE 'SA[_]%' ORDER BY TABLE_NAME
""")
