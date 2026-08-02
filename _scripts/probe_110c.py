# -*- coding: utf-8 -*-
import sys,io,warnings; warnings.filterwarnings('ignore')
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding='utf-8')
sys.path.insert(0,r'd:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP')
import pandas as pd,db_client,pyodbc
def live(sql):
    cs=f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};DATABASE=PARTNER_ERP;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}'
    cn=pyodbc.connect(cs,readonly=True)
    try: return pd.read_sql(sql,cn)
    finally: cn.close()
# 작업처 소스: 화면 예시 109000=조인테크, 3A00375A=동주금속, 1MPC0502018=삼화코리아
print("### 작업처 소스 찾기 (109000/3A00375A/1MPC0502018) ###")
print(live("""SELECT i.item_code,
  i.in_cust_code, (SELECT cust_desc FROM cm_m_cust c WHERE c.cust_code=i.in_cust_code) in_nm,
  i.sale_cust_code1, (SELECT cust_desc FROM cm_m_cust c WHERE c.cust_code=i.sale_cust_code1) sale_nm,
  i.work_code, i.org_work_code
 FROM pr_m_item i WHERE i.item_code IN ('109000','3A00375A','1MPC0502018','MJU64433701')""").to_string(index=False))
# MJU64433701 라인 재현(l1 그대로)
CUST="ISNULL((SELECT cust_desc FROM cm_m_cust m WHERE m.cust_code=a.cust_code),'')"
L1=f"""
 SELECT a.maint_ymd ymd, a.maint_qty inq, CAST(0 AS decimal(18,4)) outq, CAST(0 AS decimal(18,4)) etc, {CUST} cust, CASE a.maint_tag WHEN 'V' THEN '세트출하' WHEN 'P' THEN '생산완료' ELSE '입고' END div FROM sa_t_stock_maint a WHERE a.maint_ymd BETWEEN '260701' AND '999999' AND a.item_code='MJU64433701' AND a.maint_tag IN ('B','V') AND a.maint_qty<>0
 UNION ALL SELECT a.maint_ymd, a.maint_qty,0,0, {CUST}, '생산완료' FROM sa_t_stock_maint a WHERE a.maint_ymd BETWEEN '260701' AND '999999' AND a.item_code='MJU64433701' AND a.maint_tag='P' AND ISNULL(a.in_part_code,'')='' AND a.maint_qty<>0
 UNION ALL SELECT a.maint_ymd, a.maint_qty*-1,0,0, {CUST}, '자재창고에서입고' FROM pu_t_stock_maint a WHERE a.maint_ymd BETWEEN '260701' AND '999999' AND a.mat_code='MJU64433701' AND ISNULL(a.out_wh_gubun,'1')='2'
 UNION ALL SELECT a.maint_ymd, 0, a.maint_qty*-1, 0, {CUST}, CASE a.maint_tag WHEN '8' THEN '무상공급' WHEN 'R' THEN '출하반품' ELSE '출하' END FROM sa_t_stock_maint a WHERE a.maint_ymd BETWEEN '260701' AND '999999' AND a.item_code='MJU64433701' AND a.maint_tag IN ('J','8','R') AND a.maint_qty<>0
 UNION ALL SELECT a.maint_ymd, 0,0, a.maint_qty*-1, {CUST}, '재고조정' FROM sa_t_stock_maint a WHERE a.maint_ymd BETWEEN '260701' AND '999999' AND a.item_code='MJU64433701' AND a.maint_tag='2' AND a.maint_qty<>0
"""
BF="""SELECT SUM(q) bf FROM (
   SELECT stock_qty q FROM sa_t_month_stock WHERE stock_yymm='2502' AND item_code='MJU64433701'
   UNION ALL SELECT MAINT_QTY FROM sa_t_stock_maint WHERE MAINT_YMD>'250299' AND maint_ymd<'260701' AND item_code='MJU64433701' AND maint_tag IN ('B','V','J','2','8','R')
   UNION ALL SELECT MAINT_QTY FROM sa_t_stock_maint WHERE MAINT_YMD>'250299' AND maint_ymd<'260701' AND item_code='MJU64433701' AND maint_tag='P' AND ISNULL(IN_PART_CODE,'')=''
   UNION ALL SELECT maint_qty*-1 FROM pu_t_stock_maint WHERE maint_ymd>'250299' AND maint_ymd<'260701' AND mat_code='MJU64433701' AND ISNULL(out_wh_gubun,'1')='2') t"""
bf=float(live(BF).bf.iloc[0] or 0)
ln=live(f"SELECT ymd, inq, outq, etc, div, cust FROM ({L1}) x ORDER BY ymd")
bal=bf; si=so=se=0
print(f"\n### MJU64433701 라인재현 (bf={bf}) ###")
for r in ln.itertuples():
    bal+=r.inq-r.outq+r.etc; si+=r.inq;so+=r.outq;se+=r.etc
print(f"라인수 {len(ln)}  입합 {si}  출합 {so}  기타 {se}  => 최종재고 {round(bal,2)}  (probe_b 예상 5,058)")
