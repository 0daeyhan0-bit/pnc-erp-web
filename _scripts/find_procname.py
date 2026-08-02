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

# 공통코드마스터에서 이 코드들이 있는 KIND 찾기
show("1. CM_M_MASTER_DETAIL 에서 P0001/Q1000/RAC/S1/IS0001 를 가진 KIND", """
SELECT d.KIND_CODE, m.KIND_DESC, d.DETAIL_CODE, d.DETAIL_DESC
FROM CM_M_MASTER_DETAIL d LEFT JOIN CM_M_MASTER m ON m.KIND_CODE=d.KIND_CODE
WHERE d.DETAIL_CODE IN ('P0001','Q1000','RAC','S1','IS0001','S5-2','S13')
ORDER BY d.KIND_CODE, d.DETAIL_CODE
""")

# 혹시 별도 테이블(가공공정코드 마스터)
show("2. 코드-이름 후보 테이블", """
SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_TYPE='BASE TABLE'
AND (TABLE_NAME LIKE '%GAGONG_PROC%' OR TABLE_NAME LIKE '%PART_CODE%' OR TABLE_NAME LIKE '%STOCK_PART%')
ORDER BY TABLE_NAME
""")
# 컬럼명에 gagong_proc_code + desc/name 있는 테이블
show("3. gagong_proc 관련 이름 컬럼 보유 테이블", """
SELECT DISTINCT c1.TABLE_NAME FROM INFORMATION_SCHEMA.COLUMNS c1
JOIN INFORMATION_SCHEMA.COLUMNS c2 ON c1.TABLE_NAME=c2.TABLE_NAME
WHERE LOWER(c1.COLUMN_NAME) LIKE '%gagong_proc_code%'
  AND (LOWER(c2.COLUMN_NAME) LIKE '%desc%' OR LOWER(c2.COLUMN_NAME) LIKE '%name%' OR LOWER(c2.COLUMN_NAME) LIKE '%nm%')
""")
