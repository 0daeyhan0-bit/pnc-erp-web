# -*- coding: utf-8 -*-
import sys, io, warnings
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, r"d:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP")
import db_client, pyodbc, pandas as pd
def live(sql):
    cs=(f"DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};DATABASE=PARTNER_ERP;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}")
    cn=pyodbc.connect(cs, readonly=True)
    try: return pd.read_sql(sql, cn)
    finally: cn.close()
P="AJR76562819"
print("### 1. pr_t_mat_stock_wh (스냅샷) 의 이 도번 관련 행 ###")
print(live(f"SELECT part_code, mat_code, stock_qty FROM pr_t_mat_stock_wh WHERE mat_code LIKE '{P}%' ORDER BY part_code").to_string(index=False))
print("\n### 2. pr_t_mat_stock_wh 에 IS0001 파트가 존재? (전체 part_code distinct 중 IS/자재창고류) ###")
print(live("SELECT part_code, COUNT(*) n, SUM(stock_qty) q FROM pr_t_mat_stock_wh GROUP BY part_code ORDER BY part_code").to_string(index=False))
print("\n### 3. 내 이동원천별 이 도번 집계 (part, mat, source, sum) ###")
INSP="NOT(ISNULL(a.insp_flag,'N') IN ('S','F') AND ISNULL(a.insp_proc_flag,'0')<>'1')"
q=f"""
 SELECT '1.생산창고입고B' src, a.TO_GAGONG_PROC_CODE part, a.mat_code mat, SUM(a.maint_qty*-1) q FROM PU_T_STOCK_MAINT a WHERE a.maint_tag='B' AND ISNULL(a.out_wh_gubun,'1')='1' AND {INSP} AND a.mat_code LIKE '{P}%' GROUP BY a.TO_GAGONG_PROC_CODE,a.mat_code
 UNION ALL SELECT '2.가공생산입고', a.gagong_proc_code, a.mat_code, SUM(a.cut_qty) FROM pu_t_cut_dtl a WHERE a.mat_code LIKE '{P}%' GROUP BY a.gagong_proc_code,a.mat_code
 UNION ALL SELECT '3.자재창고반품T', a.TO_GAGONG_PROC_CODE, a.mat_code, SUM(a.maint_qty*-1) FROM PU_T_STOCK_MAINT a WHERE a.maint_tag='T' AND a.mat_code LIKE '{P}%' GROUP BY a.TO_GAGONG_PROC_CODE,a.mat_code
 UNION ALL SELECT '4.가공부품이동C', a.TO_GAGONG_PROC_CODE, a.mat_code, SUM(a.maint_qty) FROM PU_T_STOCK_MAINT a WHERE a.maint_tag='C' AND a.mat_code LIKE '{P}%' GROUP BY a.TO_GAGONG_PROC_CODE,a.mat_code
 UNION ALL SELECT '5.SUB생산실적', a.STOCK_PART_CODE, a.item_code, SUM(a.prod_qty) FROM pr_t_prod_dtl a WHERE a.item_code LIKE '{P}%' GROUP BY a.STOCK_PART_CODE,a.item_code
 UNION ALL SELECT '6.생산실적', a.IN_PART_CODE, a.item_code, SUM(a.maint_qty) FROM sa_t_stock_maint a WHERE a.item_code LIKE '{P}%' GROUP BY a.IN_PART_CODE,a.item_code
 UNION ALL SELECT '7.기초재고3', a.part_code, a.mat_code, SUM(a.maint_qty) FROM PR_T_STOCK_MAINT_MAT a WHERE a.maint_tag='3' AND a.mat_code LIKE '{P}%' GROUP BY a.part_code,a.mat_code
 UNION ALL SELECT '8.재고조정21', a.part_code, a.mat_code, SUM(a.maint_qty) FROM PR_T_STOCK_MAINT_MAT a WHERE a.maint_tag IN('2','1') AND a.mat_code LIKE '{P}%' GROUP BY a.part_code,a.mat_code
 UNION ALL SELECT '9.생산사용4', a.part_code, a.mat_code, SUM(a.maint_qty*-1) FROM PR_T_STOCK_MAINT_MAT a WHERE a.maint_tag='4' AND a.mat_code LIKE '{P}%' GROUP BY a.part_code,a.mat_code
 UNION ALL SELECT '0.전월이월2502', a.gagong_proc_code, a.mat_code, SUM(a.stock_qty) FROM PR_T_MONTH_STOCK_WH a WHERE a.stock_yymm='2502' AND a.mat_code LIKE '{P}%' GROUP BY a.gagong_proc_code,a.mat_code
"""
d=live(q)
print(d[d['q']!=0].sort_values(['mat','part','src']).to_string(index=False))
