# -*- coding: utf-8 -*-
# 060 좌측 재고 = 상세 union(전품목) net 집계. 검증: 7,651건 / 재고합 299,913.0076
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
INSP="NOT(ISNULL(a.insp_flag,'N') IN ('S','F') AND ISNULL(a.insp_proc_flag,'0')<>'1')"
W="ISNULL(a.wh_cust_code,'Z99990')='Z99990' AND ISNULL(a.gagong_proc_code,'')='IS0001'"
# 당월(07/01~) 이동: mat, in,out,etc,move
CUR=f"""
 SELECT UPPER(a.mat_code) mat, a.maint_qty inq,0 outq,0 etc,0 mv FROM pu_t_stock_maint a WHERE a.maint_ymd>='260701' AND a.maint_tag IN ('3','9','C','G','H','S','P','R') AND a.maint_qty<>0 AND {INSP} AND {W}
 UNION ALL SELECT UPPER(a.mat_code), a.maint_qty,0,0,0 FROM pu_t_stock_maint_c a WHERE a.maint_ymd>='260701' AND a.maint_qty<>0 AND a.wh_cust_code='Z99990' AND a.part_code='IS0001' AND a.division='P'
 UNION ALL SELECT UPPER(a.mat_code), a.maint_qty*-1,0,0,0 FROM pu_t_stock_maint a WHERE a.maint_ymd>='260701' AND a.maint_tag IN ('T') AND a.maint_qty<>0 AND {INSP} AND {W}
 UNION ALL SELECT UPPER(a.mat_code), a.cut_qty,0,0,0 FROM pu_t_cut_dtl a WHERE a.cut_ymd>='260701' AND a.cut_qty<>0 AND a.cut_ymd>='180528' AND {W}
 UNION ALL SELECT UPPER(a.mat_code), 0,0,a.maint_qty,0 FROM pu_t_stock_maint a WHERE a.maint_ymd>='260701' AND a.maint_tag='2' AND a.maint_qty<>0 AND {W}
 UNION ALL SELECT UPPER(a.item_code),0,0,0, CASE WHEN a.to_cust_code='Z99990' AND a.to_gagong_proc_code='IS0001' THEN a.move_qty ELSE 0 END FROM PU_T_STOCK_MOVE a WHERE a.move_ymd>='260701' AND a.move_qty<>0 AND a.to_cust_code='Z99990' AND a.to_gagong_proc_code='IS0001'
 UNION ALL SELECT UPPER(a.item_code),0,0,0, CASE WHEN a.fr_cust_code='Z99990' AND a.fr_gagong_proc_code='IS0001' THEN a.move_qty*-1 ELSE 0 END FROM PU_T_STOCK_MOVE a WHERE a.move_ymd>='260701' AND a.move_qty<>0 AND a.fr_cust_code='Z99990' AND a.fr_gagong_proc_code='IS0001'
 UNION ALL SELECT UPPER(a.mat_code), 0, a.maint_qty*-1,0,0 FROM pu_t_stock_maint a WHERE a.maint_ymd>='260701' AND a.maint_tag IN ('1','4','5','6','8','A','B','J') AND a.maint_qty<>0 AND {W}
 UNION ALL SELECT UPPER(a.mat_code), 0, a.maint_qty,0,0 FROM pu_t_stock_maint_c a WHERE a.maint_ymd>='260701' AND a.maint_qty<>0 AND a.wh_cust_code='Z99990' AND a.part_code='IS0001' AND a.division='Q'
"""
# 전월이월 bf: mat, bf
BF=f"""
 SELECT UPPER(a.mat_code) mat, a.stock_qty sq FROM pu_t_month_stock_wh a WHERE a.stock_yymm='2606' AND a.cust_code='Z99990' AND ISNULL(a.gagong_proc_code,'')='IS0001'
 UNION ALL SELECT UPPER(a.mat_code), a.maint_qty FROM pu_t_stock_maint a WHERE a.maint_ymd>'260699' AND a.maint_ymd<'260701' AND a.maint_tag IN ('3','9','C','G','H','S','P','R') AND {INSP} AND {W}
 UNION ALL SELECT UPPER(a.mat_code), IIF(a.division='Q',-a.maint_qty,a.maint_qty) FROM pu_t_stock_maint_c a WHERE a.maint_ymd>'260699' AND a.maint_ymd<'260701' AND a.wh_cust_code='Z99990' AND a.part_code='IS0001'
 UNION ALL SELECT UPPER(a.mat_code), a.maint_qty*-1 FROM pu_t_stock_maint a WHERE a.maint_ymd>'260699' AND a.maint_ymd<'260701' AND a.maint_tag IN ('T') AND {INSP} AND {W}
 UNION ALL SELECT UPPER(a.mat_code), a.cut_qty FROM pu_t_cut_dtl a WHERE a.cut_ymd>'260699' AND a.cut_ymd<'260701' AND a.cut_ymd>='180528' AND {W}
 UNION ALL SELECT UPPER(a.mat_code), a.maint_qty FROM pu_t_stock_maint a WHERE a.maint_ymd>'260699' AND a.maint_ymd<'260701' AND a.maint_tag='2' AND {W}
 UNION ALL SELECT UPPER(a.item_code), (CASE WHEN a.fr_cust_code='Z99990' AND a.fr_gagong_proc_code='IS0001' THEN a.move_qty*-1 ELSE 0 END)+(CASE WHEN a.to_cust_code='Z99990' AND a.to_gagong_proc_code='IS0001' THEN a.move_qty ELSE 0 END) FROM PU_T_STOCK_MOVE a WHERE a.move_ymd>'260699' AND a.move_ymd<'260701' AND ('Z99990' IN (a.fr_cust_code,a.to_cust_code)) AND ('IS0001' IN (a.fr_gagong_proc_code,a.to_gagong_proc_code))
 UNION ALL SELECT UPPER(a.mat_code), a.maint_qty FROM pu_t_stock_maint a WHERE a.maint_ymd>'260699' AND a.maint_ymd<'260701' AND a.maint_tag IN ('1','4','5','6','8','A','B','J') AND {W}
"""
Q=f"""
SELECT COUNT(*) rows, SUM(stock) totstock FROM (
 SELECT mat, SUM(v) stock FROM (
   SELECT mat, (inq-outq+etc+mv) v FROM ({CUR}) c
   UNION ALL SELECT mat, sq FROM ({BF}) b
 ) x GROUP BY mat
) y"""
print("== 060 좌측 재고 집계 검증 (목표 7,651 / 299,913.0076) ==")
print(live(Q).to_string(index=False))
