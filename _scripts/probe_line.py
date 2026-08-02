# -*- coding: utf-8 -*-
import sys, io, warnings
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, r"d:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP")
import db_client
def cols(t):
    try: return ", ".join(db_client.run_query(f"SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME='{t}' ORDER BY ORDINAL_POSITION")['COLUMN_NAME'].tolist())
    except Exception as e: return "ERR"
def show(t,q):
    print(f"\n== {t} ==")
    try: print(db_client.run_query(q).to_string(index=False))
    except Exception as e: print("ERR:",str(e)[:130])

print("res_line cols:", cols("res_line"))
show("res_line 내용", "SELECT * FROM res_line")
print("\nPR_M_LINE_NO cols:", cols("PR_M_LINE_NO"))
show("PR_M_LINE_NO 내용", "SELECT TOP 30 * FROM PR_M_LINE_NO")
# PR_T_MAT_STOCK_WH PART_CODE 가 res_line/PR_M_LINE_NO 와 매칭되나
show("PART_CODE ∩ PR_M_LINE_NO", """
SELECT DISTINCT s.PART_CODE, l.* FROM PR_T_MAT_STOCK_WH s
LEFT JOIN PR_M_LINE_NO l ON LTRIM(RTRIM(l.LINE_NO))=LTRIM(RTRIM(s.PART_CODE))
""")
