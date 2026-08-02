# -*- coding: utf-8 -*-
import sys, io, warnings
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, r"d:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP")
import db_client
def cols(t):
    print(f"\n-- {t} 컬럼 --")
    try: print(", ".join(db_client.run_query(f"SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME='{t}' ORDER BY ORDINAL_POSITION")['COLUMN_NAME'].tolist()))
    except Exception as e: print("ERR:",str(e)[:100])
def show(t,q):
    print(f"\n== {t} ==")
    try: print(db_client.run_query(q).to_string(index=False))
    except Exception as e: print("ERR:",str(e)[:120])

for t in ["PU_T_MAT_STOCK_WH","PR_T_MAT_STOCK_WH","SA_T_ITEM_STOCK","res_wh"]:
    cols(t)

show("PU_T_MAT_STOCK_WH 상위 5행", "SELECT TOP 5 * FROM PU_T_MAT_STOCK_WH")
show("res_wh 전체(창고 마스터?)", "SELECT * FROM res_wh")
# 창고 코드 정의 (코드마스터에서)
show("코드마스터 창고 관련 KIND", """
SELECT KIND_CODE, KIND_DESC FROM CM_M_MASTER WHERE KIND_DESC LIKE N'%창고%' OR KIND_DESC LIKE N'%WH%'
""")
