# -*- coding: utf-8 -*-
import sys, io, warnings
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, r"d:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP")
import db_client
print("목표(화면 금액): 346,498,882")
print(db_client.run_query("""
SELECT
 CAST(SUM(ROUND(stock_qty*ISNULL(item_cost2,0),0)) AS DECIMAL(18,0)) A_item_cost2,
 CAST(SUM(ROUND(stock_qty*ISNULL(MAT_COST,0),0)) AS DECIMAL(18,0)) B_matcost,
 CAST(SUM(ROUND(stock_qty*ISNULL(NULLIF(MAT_COST,0),item_cost2),0)) AS DECIMAL(18,0)) C_matcost_else_ic2,
 CAST(SUM(ROUND(stock_qty*CASE WHEN WORK_CODE='P2' THEN ISNULL(MAT_COST,0) ELSE ISNULL(item_cost2,0) END,0)) AS DECIMAL(18,0)) D_P2matcost,
 CAST(SUM(ROUND(stock_qty*CASE WHEN IN_CUST_CODE>'' THEN ISNULL(item_cost2,0) WHEN WORK_CODE='P2' THEN ISNULL(MAT_COST,0) ELSE ISNULL(item_cost2,0) END,0)) AS DECIMAL(18,0)) E_mix,
 CAST(SUM(ROUND(stock_qty*(ISNULL(MAT_COST,0)+ISNULL(LME_COST,0)),0)) AS DECIMAL(18,0)) F_mat_plus_lme
FROM PR_T_TEMP_STOCK_480_T3
""").to_string(index=False))
