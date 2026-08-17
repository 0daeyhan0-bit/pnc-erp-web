# -*- coding: utf-8 -*-
"""호환 뷰: nx 테이블을 라이브(PR/CS) 컬럼명 형태로 노출 → 프로그램 이관='테이블명만 교체'(저위험·기계적).
  nx.v_item_bom  ← nx.bom_line(+header)  = PR_M_ITEM_BOM / CS_M_ITEM_BOM 형태(단일BOM)
  nx.v_item      ← nx.item                = PR_M_ITEM 형태(상용 컬럼)
멱등(CREATE OR ALTER). 78테이블 이관 공용 인프라."""
import sys, io
sys.path.insert(0, r'd:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP')
import pyodbc, db_client
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
cn=pyodbc.connect(f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};DATABASE=PARTNER_ERP_TEST3;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}', autocommit=True)
c=cn.cursor()
V_ITEM_BOM = """CREATE OR ALTER VIEW nx.v_item_bom AS
SELECT h.item_code AS ITEM_CODE, bl.child_item AS MAT_CODE, ISNULL(bl.seq,0) AS BOM_SEQ,
   ISNULL(bl.from_ymd,'') AS FROM_APPLY_YMD, ISNULL(bl.to_ymd,'991231') AS TO_APPLY_YMD, bl.qty AS USE_QTY,
   CASE WHEN bl.except_flag=1 THEN '1' ELSE '0' END AS EXCEPT_FLAG,
   CASE WHEN bl.sagub_default=1 THEN '1' ELSE '0' END AS SAGUB_FLAG,
   CASE WHEN bl.set_except=1 THEN '1' ELSE '0' END AS SET_EXCEPT_FLAG,
   ISNULL(bl.cust_code,'') AS CUST_CODE,
   CASE WHEN bl.kitting=1 THEN '1' ELSE '0' END AS KITTING_FLAG,
   CASE WHEN bl.vir_item=1 THEN '1' ELSE '0' END AS VIR_ITEM_FLAG,
   ISNULL(bl.proc_gubun,'') AS PROC_GUBUN, ISNULL(bl.gagong_proc,'') AS GAGONG_PROC_CODE, ISNULL(bl.s_work,'') AS S_WORK_CODE,
   ISNULL(bl.wh_gagong,'') AS WH_GAGONG_PROC_CODE, ISNULL(bl.in_gagong,'') AS IN_GAGONG_PROC_CODE,
   CASE WHEN bl.cs_calc_except=1 THEN '1' ELSE '0' END AS CS_CALC_EXCEPT_FLAG,
   CASE WHEN bl.lme_except=1 THEN '1' ELSE '0' END AS LME_EXCEPT_FLAG,
   ISNULL(bl.remarks,'') AS REMARKS
FROM nx.bom_header h JOIN nx.bom_line bl ON bl.bom_id=h.bom_id"""
V_ITEM = """CREATE OR ALTER VIEW nx.v_item AS
SELECT item_code AS ITEM_CODE, ISNULL(item_name,'') AS ITEM_DESC, ISNULL(item_spec,'') AS ITEM_SPEC,
   ISNULL(diam,0) AS ITEM_DIAM, ISNULL(thick,0) AS ITEM_THICK, ISNULL(length,0) AS ITEM_LENGTH, ISNULL(net_weight,0) AS ITEM_WEIGHT,
   ISNULL(in_cust,'') AS IN_CUST_CODE, ISNULL(work_code,'') AS WORK_CODE, ISNULL(prod_rate,100) AS PROD_RATE,
   ISNULL(lgroup,'') AS ITEM_LGROUP, ISNULL(sgroup,'') AS ITEM_SGROUP, ISNULL(obtain_gubun,'') AS OBTAIN_GUBUN,
   ISNULL(item_class,'') AS ITEM_CLASS, ISNULL(pur_gubun,'') AS PUR_GUBUN, ISNULL(unit,'EA') AS UNIT,
   ISNULL(kitting_min,0) AS KITTING_MIN, ISNULL(dlvy_except_flag,'') AS DLVY_EXCEPT_FLAG, ISNULL(set_except_day,0) AS SET_EXCEPT_DAY,
   ISNULL(prod_tag,'') AS PROD_TAG, ISNULL(proc_gubun,'') AS PROC_GUBUN, ISNULL(item_radius,'') AS ITEM_RADIUS,
   ISNULL(item_pipe_id,0) AS ITEM_PIPE_ID, ISNULL(metal_gubun,'') AS METAL_GUBUN,
   ISNULL(item_pipe_type,'') AS ITEM_PIPE_TYPE, ISNULL(item_pipe_material,'') AS ITEM_PIPE_MATERIAL,
   ISNULL(sub_mat_flag,'') AS SUB_MAT_FLAG, ISNULL(sub_mat_wh,'') AS SUB_MAT_WH_CODE, ISNULL(cost_gubun,'') AS COST_GUBUN,
   ISNULL(item_status,'') AS ITEM_STATUS, ISNULL(make_type,'') AS MAKE_TYPE, ISNULL(pipe_kind,'') AS PIPE_KIND,
   ISNULL(item_group,'') AS ITEM_GROUP, ISNULL(silver_flag,0) AS SILVER_SOLDER, ISNULL(has_gagong,0) AS HAS_GAGONG
FROM nx.item"""
for name,sql in [('nx.v_item_bom',V_ITEM_BOM),('nx.v_item',V_ITEM)]:
    c.execute(sql)
    cnt=c.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
    print(f"  {name} 생성 ({cnt}행)")
print("호환 뷰 생성 완료")
cn.close()
