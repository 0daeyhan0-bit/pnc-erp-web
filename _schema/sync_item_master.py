# -*- coding: utf-8 -*-
"""
품목마스터(Phase②) 이관 — PR_M_ITEM / PR_M_ITEM_SUB / PR_M_ITEM_HIS → nx.item(+sub/valve/his)
  근거: _schema/ITEM_MASTER_ANALYSIS.md, nx_item_master_ext.sql
  방식: 컷오버 전 '전체 리프레시'(멱등 — 재실행 시 동일결과). nx.item 신규 20컬럼 UPDATE +
        item_sub/valve/his 는 DELETE→INSERT. **컷오버 후엔 nx가 단일원장 → 재실행 금지.**
  주의: nx.item 24,094 코드 기준(JOIN)으로만 채움. PR_M_ITEM_SUB 70,965(과거코드)는 교집합만.
대상 DB: PARTNER_ERP_TEST3 (nx = 스키마, dbo.PR_M_ITEM* = 레거시 복사본, 동일 인스턴스)
"""
import sys
sys.path.insert(0, r'd:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP')
import db_client

assert db_client.DB_DATABASE.strip().upper() != 'PARTNER_ERP', "운영DB 쓰기 금지"
print("대상 DB =", db_client.DB_DATABASE)
ex = db_client.execute_query
q  = db_client.run_query

# ── 1) nx.item 업무 20컬럼 리프레시 (PR_M_ITEM 조인) ────────────────────────
print("\n[1] nx.item 업무컬럼 UPDATE ...")
ex("""
UPDATE i SET
   i.item_group        = s.ITEM_GROUP,
   i.item_class        = s.ITEM_CLASS,
   i.item_status       = s.ITEM_STATUS,
   i.pipe_kind         = s.PIPE_KIND,
   i.work_code         = s.WORK_CODE,
   i.sale_cust         = s.SALE_CUST_CODE1,
   i.pur_gubun         = s.PUR_GUBUN,
   i.obtain_gubun      = s.OBTAIN_GUBUN,
   i.prod_rate         = s.PROD_RATE,
   i.kitting_min       = s.KITTING_MIN,
   i.sub_mat_flag      = s.SUB_MAT_FLAG,
   i.sub_mat_wh        = s.SUB_MAT_WH_CODE,
   i.proc_gubun        = s.PROC_GUBUN,
   i.prod_tag          = s.PROD_TAG,
   i.item_pipe_type    = s.ITEM_PIPE_TYPE,
   i.item_pipe_material= s.ITEM_PIPE_MATERIAL,
   i.item_radius       = s.ITEM_RADIUS,
   i.item_pipe_id      = s.ITEM_PIPE_ID,
   i.dlvy_except_flag  = s.DLVY_EXCEPT_FLAG,
   i.set_except_day    = s.SET_EXCEPT_DAY
FROM nx.item i JOIN dbo.PR_M_ITEM s ON i.item_code = s.ITEM_CODE
""")

# ── 2) nx.item_sub 리프레시 (실사용 필드, nx.item 교집합) ────────────────────
print("[2] nx.item_sub DELETE→INSERT ...")
ex("DELETE FROM nx.item_sub")
ex("""
INSERT INTO nx.item_sub
  (item_code, insp_flag, lg_obtain_flag, rack_no, remarks, pack_kind, pack_qty,
   pur_lead_time, prod_worker, insp_worker, min_pur_qty, safe_stock_qty, prod_step_memo)
SELECT s.ITEM_CODE, s.INSP_FLAG, s.LG_OBTAIN_FLAG, s.RACK_NO, s.REMARKS, s.PACK_KIND, s.PACK_QTY,
   s.PUR_LEAD_TIME, s.PROD_WORKER, s.INSP_WORKER, s.MIN_PUR_QTY, s.SAFE_STOCK_QTY, s.PROD_STEP_MEMO
FROM dbo.PR_M_ITEM_SUB s JOIN nx.item i ON i.item_code = s.ITEM_CODE
""")

# ── 3) nx.item_valve 리프레시 (설치품 밸브 — 값 있는 품목만) ─────────────────
print("[3] nx.item_valve DELETE→INSERT ...")
ex("DELETE FROM nx.item_valve")
ex("""
INSERT INTO nx.item_valve
  (item_code, item_od, item_id, valve_type, s_w_type, h_s_type, n_s_type, add_item_type,
   size1,size1_limit, size2,size2_limit, size3,size3_limit, size4,size4_limit,
   size5,size5_limit, size6,size6_limit, size7,size7_limit, size8,size8_limit)
SELECT s.ITEM_CODE, s.ITEM_OD, s.ITEM_ID, s.VALVE_TYPE, s.S_W_TYPE, s.H_S_TYPE, s.N_S_TYPE, s.ADD_ITEM_TYPE,
   s.ITEM_SIZE, s.ITEM_SIZE_LIMIT, s.ITEM_SIZE1, s.ITEM_SIZE_LIMIT1, s.ITEM_SIEZ2, s.ITEM_SIZE_LIMIT2,
   s.ITEM_SIZE3, s.ITEM_SIZE_LIMIT3, s.ITEM_SIZE4, s.ITEM_SIZE_LIMIT4, s.ITEM_SIZE5, s.ITEM_SIZE_LIMIT5,
   s.ITEM_SIZE6, s.ITEM_SIZE_LIMIT6, s.ITEM_SIZE7, s.ITEM_SIZE_LIMIT7
FROM dbo.PR_M_ITEM s JOIN nx.item i ON i.item_code = s.ITEM_CODE
WHERE s.VALVE_TYPE IS NOT NULL OR s.ITEM_SIZE IS NOT NULL OR s.ITEM_OD IS NOT NULL
   OR s.ITEM_ID IS NOT NULL OR s.S_W_TYPE IS NOT NULL OR s.ADD_ITEM_TYPE IS NOT NULL
""")

# ── 4) nx.item_his 리프레시 (품번변경 이력) ────────────────────────────────
print("[4] nx.item_his DELETE→INSERT ...")
ex("DELETE FROM nx.item_his")
ex("""
INSERT INTO nx.item_his (old_code, new_code, change_dt, user_id)
SELECT OLD_CODE, NEW_CODE, INSERT_DATETIME, INSERT_USER_ID FROM dbo.PR_M_ITEM_HIS
""")

# ── 검증 대사 ──────────────────────────────────────────────────────────────
print("\n" + "="*70 + "\n검증 대사\n" + "="*70)
def one(sql): return int(q(sql).iloc[0,0])
nx_item   = one("SELECT COUNT(*) FROM nx.item")
lg_item   = one("SELECT COUNT(*) FROM dbo.PR_M_ITEM")
filled_grp= one("SELECT COUNT(*) FROM nx.item WHERE item_group IS NOT NULL")
lg_grp    = one("SELECT COUNT(*) FROM dbo.PR_M_ITEM WHERE ITEM_GROUP IS NOT NULL")
sub_nx    = one("SELECT COUNT(*) FROM nx.item_sub")
sub_int   = one("SELECT COUNT(*) FROM dbo.PR_M_ITEM_SUB s JOIN nx.item i ON i.item_code=s.ITEM_CODE")
valve_nx  = one("SELECT COUNT(*) FROM nx.item_valve")
his_nx    = one("SELECT COUNT(*) FROM nx.item_his")
his_lg    = one("SELECT COUNT(*) FROM dbo.PR_M_ITEM_HIS")
insp_nx   = one("SELECT COUNT(*) FROM nx.item_sub WHERE insp_flag IS NOT NULL")
print(f"  nx.item 행수        = {nx_item:,}  (레거시 PR_M_ITEM {lg_item:,})")
print(f"  item_group 채움     = {filled_grp:,}  (레거시 {lg_grp:,})   {'OK' if filled_grp==lg_grp else 'DIFF'}")
print(f"  nx.item_sub 행수    = {sub_nx:,}  (nx교집합 {sub_int:,})     {'OK' if sub_nx==sub_int else 'DIFF'}")
print(f"    ├ insp_flag 채움  = {insp_nx:,}")
print(f"  nx.item_valve 행수  = {valve_nx:,}  (설치품 밸브)")
print(f"  nx.item_his 행수    = {his_nx:,}  (레거시 {his_lg:,})       {'OK' if his_nx==his_lg else 'DIFF'}")

print("\n[샘플] nx.item 확장컬럼 5건")
print(q("""SELECT TOP 5 item_code, item_group, item_class, item_status, pipe_kind, work_code,
   prod_rate, sub_mat_flag, item_pipe_id FROM nx.item
   WHERE item_group IS NOT NULL ORDER BY item_code""").to_string(index=False))
print("\n[샘플] nx.item_sub 5건(검사구분 有)")
print(q("SELECT TOP 5 item_code, insp_flag, lg_obtain_flag, rack_no FROM nx.item_sub WHERE insp_flag IS NOT NULL ORDER BY item_code").to_string(index=False))
print("\n[완료]")
