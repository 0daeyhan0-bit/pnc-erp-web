# -*- coding: utf-8 -*-
"""사용자 제공 dw_pr_stock_480 로직을 라인레벨로 실행 (가공 P0001 / 용접 그외)"""
import sys, io, warnings
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, r"d:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP")
import db_client

UNION = """
SELECT a.gagong_proc_code, A.MAT_CODE, A.STOCK_QTY as basic_qty, 0 in_qty,0 out_qty,0 etc_qty
  FROM PR_T_MONTH_STOCK_WH A WHERE A.STOCK_YYMM='2502'
UNION ALL
SELECT a.to_gagong_proc_code, A.MAT_CODE, iif(a.maint_ymd<'260701',-A.MAINT_QTY,0), iif(a.maint_ymd<'260701',0,-A.MAINT_QTY),0,0
  FROM PU_T_STOCK_MAINT A WHERE A.MAINT_YMD>'2502'+'99' and A.MAINT_YMD<='260717' AND a.maint_tag='B' AND isnull(a.out_wh_gubun,'1')='1'
UNION ALL
SELECT A.gagong_proc_code, a.mat_code, iif(a.cut_ymd<'260701',a.cut_QTY,0), iif(a.cut_ymd<'260701',0,a.cut_QTY),0,0
  FROM pu_t_cut_dtl a WHERE A.cut_ymd>'2502'+'99' and A.cut_ymd<='260717'
UNION ALL
SELECT a.to_gagong_proc_code, A.MAT_CODE, iif(a.MAINT_YMD<'260701',a.MAINT_QTY,0),0, iif(a.MAINT_YMD<'260701',0,-a.MAINT_QTY),0
  FROM PU_T_STOCK_MAINT A WHERE A.MAINT_YMD>'2502'+'99' and A.MAINT_YMD<='260717' AND a.maint_tag='T' and isnull(a.out_wh_gubun,'3')='3'
UNION ALL
SELECT a.to_gagong_proc_code, A.MAT_CODE, iif(a.MAINT_YMD<'260701',-a.MAINT_QTY,0),0, iif(a.MAINT_YMD<'260701',0,a.MAINT_QTY),0
  FROM PU_T_STOCK_MAINT A WHERE A.MAINT_YMD>'2502'+'99' and A.MAINT_YMD<='260717' AND a.maint_tag='C'
UNION ALL
SELECT A.stock_part_code, a.item_code, iif(a.prod_ymd<'260701',a.prod_qty,0), iif(a.prod_ymd<'260701',0,a.prod_qty),0,0
  FROM pr_t_prod_dtl a WHERE A.prod_ymd>'2502'+'99' and A.prod_ymd<='260717' and a.stock_part_code>''
   and not exists (select 1 from sa_t_stock_maint where maint_ymd=a.prod_ymd and item_code=a.item_code and in_part_code=a.stock_part_code)
UNION ALL
SELECT A.IN_PART_CODE, a.item_code, iif(a.MAINT_YMD<'260701',a.MAINT_QTY,0), iif(a.MAINT_YMD<'260701',0,a.MAINT_QTY),0,0
  FROM sa_t_stock_maint a WHERE A.maint_ymd>'2502'+'99' and A.MAINT_YMD<='260717' and a.in_part_code>''
UNION ALL
SELECT A.PART_CODE, A.MAT_CODE, iif(a.MAINT_YMD<'260701',a.MAINT_QTY,0), iif(a.MAINT_YMD<'260701',0,a.MAINT_QTY),0,0
  FROM PR_T_STOCK_MAINT_MAT A WHERE A.MAINT_YMD>'2502'+'99' and A.MAINT_YMD<='260717' AND A.MAINT_TAG='3'
UNION ALL
SELECT A.PART_CODE, A.MAT_CODE, iif(a.MAINT_YMD<'260701',a.MAINT_QTY,0),0,0, iif(a.MAINT_YMD<'260701',0,a.MAINT_QTY)
  FROM PR_T_STOCK_MAINT_MAT A WHERE A.MAINT_YMD>'2502'+'99' and A.MAINT_YMD<='260717' AND A.MAINT_TAG in ('2','1')
UNION ALL
SELECT A.PART_CODE, A.MAT_CODE, iif(a.MAINT_YMD<'260701',a.MAINT_QTY,0),0, iif(a.MAINT_YMD<'260701',0,-a.MAINT_QTY),0
  FROM PR_T_STOCK_MAINT_MAT A JOIN PR_M_ITEM M ON A.MAT_CODE=M.ITEM_CODE
  WHERE A.MAINT_YMD>'2502'+'99' and A.MAINT_YMD<='260717' AND A.MAINT_TAG='4'
"""

Q = f"""
SELECT CASE WHEN t.gagong_proc_code='P0001' THEN 'GAGONG' ELSE 'WELD' END stage,
       COUNT(*) line_rows, COUNT(DISTINCT t.mat_code) items,
       SUM(CASE WHEN sq<>0 THEN 1 ELSE 0 END) pos_rows
FROM (
  SELECT t.mat_code, t.gagong_proc_code,
         SUM(basic_qty)+SUM(in_qty)-SUM(out_qty)+SUM(etc_qty) sq
  FROM ({UNION}) t
  GROUP BY t.mat_code, t.gagong_proc_code
  HAVING SUM(basic_qty)+SUM(in_qty)-SUM(out_qty)+SUM(etc_qty) <> 0
) t
GROUP BY CASE WHEN t.gagong_proc_code='P0001' THEN 'GAGONG' ELSE 'WELD' END
"""
print("== 가공(P0001)/용접(그외) 재공 요약 ==")
print(db_client.run_query(Q).to_string(index=False))

print("\n== 용접 라인별(비P0001) 상위 ==")
print(db_client.run_query(f"""
SELECT TOP 15 t.gagong_proc_code line, COUNT(DISTINCT t.mat_code) items
FROM (SELECT t.mat_code,t.gagong_proc_code, SUM(basic_qty)+SUM(in_qty)-SUM(out_qty)+SUM(etc_qty) sq
      FROM ({UNION}) t GROUP BY t.mat_code,t.gagong_proc_code
      HAVING SUM(basic_qty)+SUM(in_qty)-SUM(out_qty)+SUM(etc_qty)<>0) t
WHERE t.gagong_proc_code<>'P0001'
GROUP BY t.gagong_proc_code ORDER BY items DESC
""").to_string(index=False))
