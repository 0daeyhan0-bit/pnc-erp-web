# -*- coding: utf-8 -*-
# 생산재고입출고(460) → data.js. 좌:파트재고(pr_t_mat_stock_wh by part,mat), 우:입출고이력(July+)+전월이월(2502)
import sys, io, json, warnings
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, r"d:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP")
import db_client, pyodbc, pandas as pd
def live(sql):
    cs=(f"DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};DATABASE=PARTNER_ERP;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}")
    cn=pyodbc.connect(cs, readonly=True)
    try: return pd.read_sql(sql, cn)
    finally: cn.close()
INSP="NOT(ISNULL(a.insp_flag,'N') IN ('S','F') AND ISNULL(a.insp_proc_flag,'0')<>'1')"
CUST="ISNULL((SELECT cust_desc FROM cm_m_cust m WHERE m.cust_code=a.cust_code),'')"
FR="'260701'"; BFF="'250299'"; BFT="'260701'"   # 당월시작 / 전월이월범위(2502말~0701)
# 당월(July+) 이력 라인: part, mat, ymd, inq, outq, etc, div, tag, wo
def CUR():
    return f"""
 SELECT a.TO_GAGONG_PROC_CODE part, UPPER(a.mat_code) mat, a.maint_ymd ymd, a.maint_qty*-1 inq,CAST(0 AS decimal(18,4)) outq,CAST(0 AS decimal(18,4)) etc,'생산창고입고' div, {CUST} tag, ISNULL(a.work_order,'') wo
   FROM PU_T_STOCK_MAINT a WHERE a.maint_ymd>={FR} AND a.maint_tag='B' AND ISNULL(a.out_wh_gubun,'1')='1' AND a.maint_qty<>0 AND {INSP} AND a.TO_GAGONG_PROC_CODE>''
 UNION ALL SELECT a.gagong_proc_code, UPPER(a.mat_code), a.cut_ymd, a.cut_qty,0,0,'가공생산입고','제조1팀','' FROM pu_t_cut_dtl a WHERE a.cut_ymd>={FR} AND a.cut_qty<>0 AND a.cut_ymd>='180528' AND a.gagong_proc_code>''
 UNION ALL SELECT a.TO_GAGONG_PROC_CODE, UPPER(a.mat_code), a.maint_ymd, 0, a.maint_qty*-1,0,'자재창고반품',{CUST},ISNULL(a.work_order,'') FROM PU_T_STOCK_MAINT a WHERE a.maint_ymd>={FR} AND a.maint_tag='T' AND ISNULL(a.out_wh_gubun,'3')='3' AND a.maint_qty<>0 AND a.TO_GAGONG_PROC_CODE>''
 UNION ALL SELECT a.TO_GAGONG_PROC_CODE, UPPER(a.mat_code), a.maint_ymd, 0, a.maint_qty,0,'가공부품이동',{CUST},ISNULL(a.work_order,'') FROM PU_T_STOCK_MAINT a WHERE a.maint_ymd>={FR} AND a.maint_tag='C' AND a.maint_qty<>0 AND a.TO_GAGONG_PROC_CODE>''
 UNION ALL SELECT a.STOCK_PART_CODE, UPPER(a.item_code), a.prod_ymd, a.prod_qty,0,0,'SUB생산실적','','' FROM pr_t_prod_dtl a WHERE a.prod_ymd>={FR} AND a.STOCK_PART_CODE>'' AND NOT EXISTS(SELECT 1 FROM sa_t_stock_maint s WHERE s.maint_ymd=a.prod_ymd AND s.item_code=a.item_code AND s.in_part_code=a.stock_part_code)
 UNION ALL SELECT a.IN_PART_CODE, UPPER(a.item_code), a.maint_ymd, a.maint_qty,0,0,'생산실적',{CUST},ISNULL(a.work_order,'') FROM sa_t_stock_maint a WHERE a.maint_ymd>={FR} AND a.IN_PART_CODE>''
 UNION ALL SELECT a.part_code, UPPER(a.mat_code), a.maint_ymd, a.maint_qty,0,0,'기초재고',{CUST},ISNULL(a.work_order,'') FROM PR_T_STOCK_MAINT_MAT a WHERE a.maint_ymd>={FR} AND a.part_code>'' AND a.maint_tag='3' AND a.maint_qty<>0
 UNION ALL SELECT a.part_code, UPPER(a.mat_code), a.maint_ymd, 0,0,a.maint_qty,'재고조정',{CUST},ISNULL(a.work_order,'') FROM PR_T_STOCK_MAINT_MAT a WHERE a.maint_ymd>={FR} AND a.part_code>'' AND a.maint_tag IN ('2','1') AND a.maint_qty<>0
 UNION ALL SELECT a.part_code, UPPER(a.mat_code), a.maint_ymd, 0, a.maint_qty*-1,0,'생산사용',{CUST},ISNULL(a.work_order,'') FROM PR_T_STOCK_MAINT_MAT a WHERE a.maint_ymd>={FR} AND a.part_code>'' AND a.maint_tag='4' AND a.maint_qty<>0
"""
# 전월이월 bf (2502말~0701): part, mat, sq
def BF():
    return f"""
 SELECT a.gagong_proc_code part, UPPER(a.mat_code) mat, a.stock_qty sq FROM PR_T_MONTH_STOCK_WH a WHERE a.stock_yymm='2502'
 UNION ALL SELECT a.TO_GAGONG_PROC_CODE, UPPER(a.mat_code), a.maint_qty*-1 FROM PU_T_STOCK_MAINT a WHERE a.maint_ymd>'250299' AND a.maint_ymd<{BFT} AND a.maint_tag='B' AND ISNULL(a.out_wh_gubun,'1')='1' AND {INSP} AND a.TO_GAGONG_PROC_CODE>''
 UNION ALL SELECT a.STOCK_PART_CODE, UPPER(a.item_code), a.prod_qty FROM pr_t_prod_dtl a WHERE a.prod_ymd>'250299' AND a.prod_ymd<{BFT} AND a.STOCK_PART_CODE>'' AND NOT EXISTS(SELECT 1 FROM sa_t_stock_maint s WHERE s.maint_ymd=a.prod_ymd AND s.item_code=a.item_code AND s.in_part_code=a.stock_part_code)
 UNION ALL SELECT a.IN_PART_CODE, UPPER(a.item_code), a.MAINT_QTY FROM sa_t_stock_maint a WHERE a.maint_ymd>'250299' AND a.maint_ymd<{BFT} AND a.IN_PART_CODE>''
 UNION ALL SELECT a.gagong_proc_code, UPPER(a.mat_code), a.cut_qty FROM pu_t_cut_dtl a WHERE a.cut_ymd>'250299' AND a.cut_ymd<{BFT} AND a.gagong_proc_code>'' AND a.cut_qty<>0
 UNION ALL SELECT a.PART_CODE, UPPER(a.MAT_CODE), a.MAINT_QTY FROM PR_T_STOCK_MAINT_MAT a WHERE a.MAINT_YMD>'250299' AND a.MAINT_YMD<{BFT} AND a.PART_CODE>'' AND a.MAINT_TAG IN ('3','2','1')
 UNION ALL SELECT a.PART_CODE, UPPER(a.MAT_CODE), a.MAINT_QTY FROM PR_T_STOCK_MAINT_MAT a WHERE a.MAINT_YMD>'250299' AND a.MAINT_YMD<{BFT} AND a.PART_CODE>'' AND a.MAINT_TAG='4'
 UNION ALL SELECT a.TO_GAGONG_PROC_CODE, UPPER(a.mat_code), a.MAINT_QTY FROM PU_T_STOCK_MAINT a WHERE a.MAINT_YMD>'250299' AND a.MAINT_YMD<{BFT} AND a.maint_tag='T' AND a.TO_GAGONG_PROC_CODE>''
 UNION ALL SELECT a.TO_GAGONG_PROC_CODE, UPPER(a.mat_code), a.MAINT_QTY*-1 FROM PU_T_STOCK_MAINT a WHERE a.MAINT_YMD>'250299' AND a.MAINT_YMD<{BFT} AND a.maint_tag='C' AND a.TO_GAGONG_PROC_CODE>''
"""
left=live("SELECT part_code part, UPPER(mat_code) mat, SUM(stock_qty) stock FROM pr_t_mat_stock_wh GROUP BY part_code, UPPER(mat_code)")
print("좌측 pr_t_mat_stock_wh:", len(left),"행 재고합", round(left.stock.sum(),2)," (ERP 9,784 / 184,885)")
lines=live(f"SELECT part, mat, ymd, inq, outq, etc, div, tag, wo FROM ({CUR()}) x")
bf=live(f"SELECT part, mat, SUM(sq) bf FROM ({BF()}) b GROUP BY part, mat")
print("우측 라인(July+):", len(lines)," / bf(part,mat):", len(bf))
# 재현 검증: bf + July net, (part,mat) 별 → pr_t_mat_stock_wh 와 비교(샘플)
net=lines.assign(v=lines.inq-lines.outq+lines.etc).groupby(['part','mat'])['v'].sum().reset_index()
m=bf.merge(net,on=['part','mat'],how='outer').fillna(0); m['calc']=m['bf']+m['v']
chk=left.merge(m[['part','mat','calc']],on=['part','mat'],how='left').fillna(0)
chk['diff']=(chk['stock']-chk['calc']).abs()
print("좌(pr_t_mat_stock_wh) vs bf+July 재현 — 불일치(>0.5) 행수:", int((chk['diff']>0.5).sum()),"/", len(chk))
print(chk.sort_values('diff',ascending=False).head(6).to_string(index=False))
