# -*- coding: utf-8 -*-
import sys, io, warnings
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, r"d:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP")
import db_client
def cols(t):
    try: return ", ".join(db_client.run_query(f"SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME='{t}' ORDER BY ORDINAL_POSITION")['COLUMN_NAME'].tolist())
    except Exception as e: return "ERR:"+str(e)[:60]
def show(t,q):
    print(f"\n== {t} ==")
    try: print(db_client.run_query(q).to_string(index=False))
    except Exception as e: print("ERR:",str(e)[:130])

# 1) 가공/용접/SET/READY 재고 테이블 후보
show("가공/용접/SET/READY 재고 테이블 + 행수", """
SELECT t.TABLE_NAME, p.rows FROM INFORMATION_SCHEMA.TABLES t
JOIN sys.tables st ON st.name=t.TABLE_NAME JOIN sys.partitions p ON p.object_id=st.object_id AND p.index_id IN (0,1)
WHERE t.TABLE_TYPE='BASE TABLE' AND (
  LOWER(t.TABLE_NAME) LIKE '%gagong%' OR LOWER(t.TABLE_NAME) LIKE '%weld%'
  OR LOWER(t.TABLE_NAME) LIKE '%set%stock%' OR LOWER(t.TABLE_NAME) LIKE '%ready%'
  OR TABLE_NAME LIKE '%용접%' OR TABLE_NAME LIKE '%가공%')
  AND p.rows>0 ORDER BY p.rows DESC
""")

# 2) 라인(PART_CODE) 이 가공/용접 중 무엇인지 — 공정/라인 마스터 찾기
show("라인/공정 마스터 후보", """
SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_TYPE='BASE TABLE'
AND (TABLE_NAME LIKE 'PR_M_PROC%' OR TABLE_NAME LIKE '%LINE%' OR TABLE_NAME LIKE '%WORK_CENTER%' OR TABLE_NAME='res_proc')
""")
print("\nPR_M_PROC cols:", cols("PR_M_PROC"))
print("res_proc cols:", cols("res_proc"))
show("res_proc 내용(라인/공정 정의?)", "SELECT TOP 30 * FROM res_proc")

# 3) SET(설치/이지링크) 재고 구조
print("\nPU_T_SET_MAT_STOCK cols:", cols("PU_T_SET_MAT_STOCK"))
show("PU_T_SET_MAT_STOCK 샘플", "SELECT TOP 5 * FROM PU_T_SET_MAT_STOCK")
print("\nPU_T_READY_STOCK cols:", cols("PU_T_READY_STOCK"))
show("PU_T_READY_STOCK 샘플(키팅/준비재고?)", "SELECT TOP 5 * FROM PU_T_READY_STOCK")
