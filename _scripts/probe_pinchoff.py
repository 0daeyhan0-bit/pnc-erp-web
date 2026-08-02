# -*- coding: utf-8 -*-
import sys, io, warnings
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, r"d:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP")
import db_client
def show(t,q):
    print(f"\n== {t} ==")
    try: print(db_client.run_query(q).to_string(index=False))
    except Exception as e: print("ERR:",e)

codes = ['4H00049A','4H00049A-1','4H00049C','4H00189A']
inlist = ",".join(f"'{c}'" for c in codes)

show("품목: SGROUP(소분류) · 매출등장(=납품) 여부 → 유형 판정근거", f"""
SELECT p.ITEM_CODE, p.ITEM_DESC, p.ITEM_LGROUP lg, p.ITEM_SGROUP sg,
  CASE WHEN EXISTS(SELECT 1 FROM SA_T_SALE_DTL s WHERE LTRIM(RTRIM(s.ITEM_CODE))=p.ITEM_CODE) THEN 'Y' ELSE 'N' END in_sale,
  CASE WHEN EXISTS(SELECT 1 FROM SA_T_LG_RECEIVING_DTL s WHERE LTRIM(RTRIM(s.ITEM_CODE))=p.ITEM_CODE) THEN 'Y' ELSE 'N' END in_lg_recv,
  (SELECT COUNT(*) FROM SA_T_SALE_DTL s WHERE LTRIM(RTRIM(s.ITEM_CODE))=p.ITEM_CODE) sale_rows,
  (SELECT COUNT(*) FROM SA_T_LG_RECEIVING_DTL s WHERE LTRIM(RTRIM(s.ITEM_CODE))=p.ITEM_CODE) lg_rows
FROM PR_M_ITEM p
WHERE p.ITEM_CODE IN ({inlist})
ORDER BY p.ITEM_CODE
""")
