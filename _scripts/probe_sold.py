# -*- coding: utf-8 -*-
import sys, io, warnings
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, r"d:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP")
import db_client

def cols(t):
    print(f"\n-- {t} 컬럼 --")
    try:
        print(", ".join(db_client.run_query(f"SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME='{t}' ORDER BY ORDINAL_POSITION")['COLUMN_NAME'].tolist()))
    except Exception as e: print("ERR:",e)

cols("SA_T_SALE_DTL")
cols("SA_T_LG_RECEIVING_DTL")

def show(t,q):
    print(f"\n===== {t} =====")
    try: print(db_client.run_query(q).to_string(index=False))
    except Exception as e: print("ERR:",e)

# 매출에 등장하는 '납품된' 품목 집합 크기 (item 컬럼명은 위 결과 보고 판단하지만 흔히 ITEM_CODE)
show("매출상세/리시빙에 등장하는 distinct 품목수 시도", """
SELECT
 (SELECT COUNT(DISTINCT ITEM_CODE) FROM SA_T_SALE_DTL)       AS sale_items,
 (SELECT COUNT(DISTINCT ITEM_CODE) FROM SA_T_LG_RECEIVING_DTL) AS lg_recv_items
""")

# 이 '납품된' 품목들이 어떤 SGROUP에 분포하는가 (110/120/130 위주 확인)
show("납품품목(SALE+LG리시빙)의 SGROUP 분포", """
;WITH sold AS (
  SELECT DISTINCT ITEM_CODE FROM SA_T_SALE_DTL
  UNION SELECT DISTINCT ITEM_CODE FROM SA_T_LG_RECEIVING_DTL
)
SELECT p.ITEM_SGROUP, COUNT(*) sold_cnt
FROM sold s JOIN PR_M_ITEM p ON p.ITEM_CODE=s.ITEM_CODE
GROUP BY p.ITEM_SGROUP ORDER BY sold_cnt DESC
""")
