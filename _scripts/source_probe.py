# -*- coding: utf-8 -*-
import sys, io, warnings
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, r"d:\피앤씨인더스트리\100_AI_AGENT\Projects")
from db_client import run_query

def cols(t):
    print(f"\n----- {t} columns -----")
    try:
        df = run_query(f"""SELECT COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH len
        FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME='{t}' ORDER BY ORDINAL_POSITION""")
        print(df.to_string(index=False))
    except Exception as e:
        print("ERR:", e)

def show(title, q):
    print(f"\n===== {title} =====")
    try:
        print(run_query(q).to_string(index=False))
    except Exception as e:
        print("ERR:", e)

# 단가/원가 원천
cols("PR_M_ITEM_COST")
show("PR_M_ITEM_COST 건수/시계열 키 확인 (상위 3행)", "SELECT TOP 3 * FROM PR_M_ITEM_COST")
cols("LG_UNIT_PRICE_DOOSUNG")

# 거래처 마스터
cols("CM_M_CUST")

# 품목분류/공통코드 마스터 후보
show("공통코드/분류 마스터 후보 테이블", """
SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_TYPE='BASE TABLE' AND (
 LOWER(TABLE_NAME) LIKE '%code%' OR LOWER(TABLE_NAME) LIKE '%group%'
 OR TABLE_NAME LIKE 'CM_M_MASTER%' OR LOWER(TABLE_NAME) LIKE '%unit%' OR LOWER(TABLE_NAME) LIKE '%uom%')
ORDER BY TABLE_NAME
""")
cols("CM_M_MASTER")
cols("CM_M_MASTER_DETAIL")

# UNIT 값 분포 (단위 마스터 대체 파악)
show("PR_M_ITEM UNIT 분포", "SELECT UNIT, COUNT(*) c FROM PR_M_ITEM GROUP BY UNIT ORDER BY c DESC")

# 품목마스터 이원화: CM_M_ITEM vs PR_M_ITEM
show("CM_M_ITEM vs PR_M_ITEM 건수", """
SELECT (SELECT COUNT(*) FROM CM_M_ITEM) cm_m_item, (SELECT COUNT(*) FROM PR_M_ITEM) pr_m_item
""")
cols("CM_M_ITEM")
