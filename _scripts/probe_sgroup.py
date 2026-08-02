# -*- coding: utf-8 -*-
import sys, io, warnings
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, r"d:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP")
import db_client  # now points to TEST2

def show(t,q):
    print(f"\n===== {t} =====")
    try: print(db_client.run_query(q).to_string(index=False))
    except Exception as e: print("ERR:",e)

# SGROUP별 특성: 파이프소재/용접/부자재플래그/중량 + 대표 품명
show("SGROUP별 특성 프로파일", """
SELECT ITEM_SGROUP,
  COUNT(*) cnt,
  SUM(CASE WHEN ITEM_PIPE_MATERIAL<>'' AND ITEM_PIPE_MATERIAL IS NOT NULL THEN 1 ELSE 0 END) has_pipe_mat,
  SUM(CASE WHEN (WELD_POINT_IN>0 OR WELD_POINT_OUT>0) THEN 1 ELSE 0 END) has_weld,
  SUM(CASE WHEN SUB_MAT_FLAG='Y' THEN 1 ELSE 0 END) sub_mat,
  SUM(CASE WHEN JIG_CODE<>'' AND JIG_CODE IS NOT NULL THEN 1 ELSE 0 END) has_jig,
  SUM(CASE WHEN ITEM_DESC LIKE '%ASSY%' OR ITEM_DESC LIKE '%ASSEMBLY%' THEN 1 ELSE 0 END) has_assy_nm
FROM PR_M_ITEM GROUP BY ITEM_SGROUP ORDER BY cnt DESC
""")

for sg in ['130','110','120','230','220','310','910','210']:
    show(f"SGROUP {sg} 대표 품명 8건", f"""
    SELECT TOP 8 ITEM_CODE, ITEM_DESC, ITEM_PIPE_MATERIAL pmat, ITEM_LGROUP lg
    FROM PR_M_ITEM WHERE ITEM_SGROUP='{sg}' ORDER BY ITEM_CODE
    """)
