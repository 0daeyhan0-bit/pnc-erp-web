# -*- coding: utf-8 -*-
"""★nx 호환 레이어 (프로그램 nx 전환 공용 인프라). nx에 라이브 테이블명 그대로 객체 생성 →
   프로그램 이관 = 참조 프리픽스만 'PARTNER_ERP.dbo.'→'nx.' 교체 (최소변경·저위험).
  뷰(매핑): nx.PR_M_ITEM_BOM·nx.CS_M_ITEM_BOM(←nx.bom_line 단일BOM), nx.PR_M_ITEM(←nx.item), nx.PR_M_MAT(빈 필터)
  실테이블(원본복제): nx.PR_M_ITEM_PROC_GAGONG·nx.PR_M_WORK_SINGLE·nx.PR_M_PROC_GAGONG
멱등. 컷오버 대량이관+델타 재사용. 구 중간명(item_proc·v_item*)은 정리."""
import sys, io
sys.path.insert(0, r'd:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP')
import pyodbc, db_client
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
cn=pyodbc.connect(f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};DATABASE=PARTNER_ERP_TEST3;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}', autocommit=True)
c=cn.cursor()
# 구 중간명 정리
for t in ['item_proc','work_single','proc_gagong']:
    c.execute(f"IF OBJECT_ID('nx.{t}','U') IS NOT NULL DROP TABLE nx.{t}")
for v in ['v_item_bom','v_item']:
    c.execute(f"IF OBJECT_ID('nx.{v}','V') IS NOT NULL DROP VIEW nx.{v}")
# 실테이블 복제(원본 충실, 라이브명)
for nxt, src in [('PR_M_ITEM_PROC_GAGONG','PARTNER_ERP.dbo.PR_M_ITEM_PROC_GAGONG'),
                 ('PR_M_WORK_SINGLE','PARTNER_ERP.dbo.PR_M_WORK_SINGLE'),
                 ('PR_M_PROC_GAGONG','PARTNER_ERP.dbo.PR_M_PROC_GAGONG')]:
    c.execute(f"IF OBJECT_ID('nx.{nxt}','U') IS NOT NULL DROP TABLE nx.{nxt}")
    c.execute(f"SELECT * INTO nx.{nxt} FROM {src}")
    n=c.execute(f"SELECT COUNT(*) FROM nx.{nxt}").fetchone()[0]
    print(f"  nx.{nxt} 복제 {n}행")
# BOM 뷰(단일BOM=nx.bom_line, PR/CS 양쪽 동일 노출) — ★라이브 타입으로 CAST(재귀CTE 타입일치+전프로그램 호환)
BOMV="""SELECT CAST(h.item_code AS varchar(20)) AS ITEM_CODE, CAST(bl.child_item AS varchar(20)) AS MAT_CODE,
   CAST(ISNULL(bl.seq,0) AS smallint) AS BOM_SEQ,
   CAST(ISNULL(bl.from_ymd,'') AS varchar(6)) AS FROM_APPLY_YMD, CAST(ISNULL(bl.to_ymd,'991231') AS varchar(6)) AS TO_APPLY_YMD,
   CAST(bl.qty AS float) AS USE_QTY,
   CAST(CASE WHEN bl.except_flag=1 THEN '1' ELSE '0' END AS varchar(1)) AS EXCEPT_FLAG,
   CAST(CASE WHEN bl.sagub_default=1 THEN '1' ELSE '0' END AS varchar(1)) AS SAGUB_FLAG,
   CAST(CASE WHEN bl.set_except=1 THEN '1' ELSE '0' END AS varchar(1)) AS SET_EXCEPT_FLAG,
   CAST(ISNULL(bl.cust_code,'') AS varchar(10)) AS CUST_CODE,
   CAST(CASE WHEN bl.kitting=1 THEN '1' ELSE '0' END AS varchar(1)) AS KITTING_FLAG,
   CAST(CASE WHEN bl.vir_item=1 THEN '1' ELSE '0' END AS varchar(1)) AS VIR_ITEM_FLAG,
   CAST(ISNULL(bl.proc_gubun,'') AS varchar(1)) AS PROC_GUBUN,
   CAST(ISNULL(bl.gagong_proc,'') AS varchar(10)) AS GAGONG_PROC_CODE,
   TRY_CAST(bl.s_work AS smallint) AS S_WORK_CODE,
   CAST(ISNULL(bl.wh_gagong,'') AS varchar(10)) AS WH_GAGONG_PROC_CODE,
   CAST(ISNULL(bl.in_gagong,'') AS varchar(10)) AS IN_GAGONG_PROC_CODE,
   CAST(CASE WHEN bl.cs_calc_except=1 THEN '1' ELSE '0' END AS varchar(1)) AS CS_CALC_EXCEPT_FLAG,
   CAST(CASE WHEN bl.lme_except=1 THEN '1' ELSE '0' END AS varchar(1)) AS LME_EXCEPT_FLAG,
   CAST(ISNULL(bl.remarks,'') AS varchar(15)) AS REMARKS
FROM nx.bom_header h JOIN nx.bom_line bl ON bl.bom_id=h.bom_id"""
c.execute(f"CREATE OR ALTER VIEW nx.PR_M_ITEM_BOM AS {BOMV}")
c.execute(f"CREATE OR ALTER VIEW nx.CS_M_ITEM_BOM AS {BOMV}")
# 품목 뷰 — 라이브 타입 CAST
c.execute("""CREATE OR ALTER VIEW nx.PR_M_ITEM AS
SELECT CAST(item_code AS varchar(20)) AS ITEM_CODE, CAST(ISNULL(item_name,'') AS varchar(50)) AS ITEM_DESC,
   CAST(ISNULL(item_spec,'') AS varchar(200)) AS ITEM_SPEC,
   CAST(ISNULL(diam,0) AS numeric(18,4)) AS ITEM_DIAM, CAST(ISNULL(thick,0) AS numeric(18,4)) AS ITEM_THICK,
   CAST(ISNULL(length,0) AS numeric(18,4)) AS ITEM_LENGTH, CAST(ISNULL(net_weight,0) AS numeric(18,4)) AS ITEM_WEIGHT,
   CAST(ISNULL(in_cust,'') AS varchar(10)) AS IN_CUST_CODE, CAST(ISNULL(work_code,'') AS varchar(4)) AS WORK_CODE,
   CAST(ISNULL(prod_rate,100) AS smallint) AS PROD_RATE,
   CAST(ISNULL(lgroup,'') AS varchar(10)) AS ITEM_LGROUP, CAST(ISNULL(sgroup,'') AS varchar(10)) AS ITEM_SGROUP,
   CAST(ISNULL(obtain_gubun,'') AS varchar(1)) AS OBTAIN_GUBUN, CAST(ISNULL(item_class,'') AS varchar(1)) AS ITEM_CLASS,
   CAST(ISNULL(pur_gubun,'') AS varchar(1)) AS PUR_GUBUN, CAST(ISNULL(unit,'EA') AS varchar(2)) AS UNIT,
   CAST(ISNULL(kitting_min,0) AS smallint) AS KITTING_MIN, CAST(ISNULL(dlvy_except_flag,'') AS varchar(1)) AS DLVY_EXCEPT_FLAG,
   CAST(ISNULL(set_except_day,0) AS tinyint) AS SET_EXCEPT_DAY, CAST(ISNULL(prod_tag,'') AS varchar(1)) AS PROD_TAG,
   CAST(ISNULL(proc_gubun,'') AS varchar(1)) AS PROC_GUBUN, CAST(ISNULL(item_radius,'') AS varchar(20)) AS ITEM_RADIUS,
   CAST(ISNULL(item_pipe_id,0) AS numeric(18,4)) AS ITEM_PIPE_ID, CAST(ISNULL(metal_gubun,'') AS varchar(20)) AS METAL_GUBUN,
   CAST(ISNULL(item_pipe_type,'') AS varchar(20)) AS ITEM_PIPE_TYPE, CAST(ISNULL(item_pipe_material,'') AS varchar(20)) AS ITEM_PIPE_MATERIAL,
   CAST(ISNULL(sub_mat_flag,'') AS varchar(1)) AS SUB_MAT_FLAG, CAST(ISNULL(sub_mat_wh,'') AS varchar(10)) AS SUB_MAT_WH_CODE,
   CAST(ISNULL(cost_gubun,'') AS varchar(10)) AS COST_GUBUN, CAST(ISNULL(item_status,'') AS varchar(10)) AS ITEM_STATUS,
   CAST(ISNULL(make_type,'') AS varchar(10)) AS MAKE_TYPE, CAST(ISNULL(pipe_kind,'') AS varchar(2)) AS PIPE_KIND,
   CAST(ISNULL(item_group,'') AS varchar(10)) AS ITEM_GROUP, CAST(CASE WHEN silver_flag=1 THEN '1' ELSE '0' END AS varchar(2)) AS SILVER_SOLDER
FROM nx.item""")
# PR_M_MAT: 라이브 0행(빈 필터) → 빈 뷰(현행 동작 보존)
c.execute("CREATE OR ALTER VIEW nx.PR_M_MAT AS SELECT CAST('' AS varchar(30)) AS MAT_CODE, CAST('' AS varchar(100)) AS MAT_DESC WHERE 1=0")
for v in ['PR_M_ITEM_BOM','CS_M_ITEM_BOM','PR_M_ITEM','PR_M_MAT']:
    cnt=c.execute(f"SELECT COUNT(*) FROM nx.{v}").fetchone()[0]
    print(f"  nx.{v} (뷰) {cnt}행")
print("호환 레이어 완료")
cn.close()
