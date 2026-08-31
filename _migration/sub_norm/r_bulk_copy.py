# -*- coding: utf-8 -*-
"""★컷오버 대량이관 도구: 라이브 PARTNER_ERP 테이블 → nx 충실 복제(동일명·동일스키마·동일데이터).
프로그램 nx전환 = 참조 프리픽스만 'PARTNER_ERP.dbo.'→'nx.' (로직·BOM소스 불변 → 라이브와 100% 동일작동).
단일BOM 통일은 컷오버 후 별도. ※nx.bom_line/nx.item(재구축본)은 원가엔진·정규화용 별개 유지.
멱등(DROP+SELECT INTO). 컷오버 대량+델타 재사용. TABLES 리스트로 확장.
사용: python r_bulk_copy.py [--commit]  (기본 계획)"""
import sys, io
sys.path.insert(0, r'd:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP')
import pyodbc, db_client
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
DRY=('--commit' not in sys.argv)
# 이관 대상(라이브명=nx명). soyo+BOM+품목+가공 + 8프로그램(partplan·gagong·sourcing·backflush·item·salemagam·weight·cost).
TABLES=['PR_M_ITEM_BOM','CS_M_ITEM_BOM','PR_M_ITEM','PR_M_MAT',
        'PR_M_ITEM_PROC_GAGONG','PR_M_WORK_SINGLE','PR_M_PROC_GAGONG',
        # 8프로그램 추가
        'CM_M_CUST','CM_M_CUST_MAGAM','CM_USER_MEETING_1','CS_M_PROC','CS_T_ITEM_PROC','CS_T_ITEM_WELD',
        'PR_M_ITEM_COST','PR_M_MODEL_BOM','PR_M_MODEL_BOM_EXCEPT','PR_M_WORK','QA_M_MACHINE',
        'PR_T_INDI_CUTTING','PR_T_INDI_CUTTING_PROC_GAGONG','PR_T_MAT_STOCK_WH','PR_T_PLAN_PART_DTL','PR_T_PROD_DTL_GAGONG',
        'PU_T_MAT_STOCK_WH','PU_T_READY_STOCK','PU_T_SAGUB_STOCK','PU_T_STACKER_STOCK','PU_T_STOCK_MAINT',
        'SA_T_ITEM_STOCK','SA_T_RECV_DTL','SA_T_SALE_DTL',
        # common.py 공유헬퍼
        'CM_M_MASTER_DETAIL','PU_T_STOCK_MAINT_C',
        # ★전 ERP 나머지(범위외 35파일, r_scan_all)
        'CM_M_COMPANY','CS_M_ASSEM_PROC','HR_M_CALENDAR','HR_M_DEPT','HR_M_WORK_INFO','PR_M_CUST_MAT_LIST',
        'PR_M_ITEM_ASSY_RT','PR_M_ITEM_BLOB','PR_M_ITEM_ST','PR_M_ITEM_SUB','PR_M_LINE_CALENDAR','PR_M_LINE_NO',
        'PR_M_PART_CALENDAR','PR_M_PROC_GAGONG_WORKER','PR_M_WORK_ASSY','PR_T_INDI_SHEET2','PR_T_INDI_WELD_SHEET_DTL',
        'PR_T_MONTH_STOCK_WH','PR_T_PLAN_DTL','PR_T_PLAN_INPUT','PR_T_PLAN_ITEM_DTL','PR_T_PLAN_PART_COPY',
        'PR_T_PLAN_PART_DTL_FOR_CUST','PR_T_PLAN_PART_MAT','PR_T_PRINT_STICKER','PR_T_PROD_DTL','PR_T_PROD_DTL_PROC',
        'PR_T_PROD_DTL_STICKER','PR_T_STOCK_MAINT_MAT','PU_T_MONTH_READY_STOCK','PU_T_MONTH_STOCK_WH',
        'PU_T_MONTH_STOCK_WH_DAILY','PU_T_PURCHASE_DTL','PU_T_SET_INPUT_REQ','PU_T_SET_MAT_STOCK',
        'PU_T_STOCK_MAINT_GAGONG_MOVE','PU_T_STOCK_MOVE','QA_T_CUST_IQC_DTL','QA_T_CUST_IQC_HEAD','QA_T_ERROR',
        'QA_T_RAW_ERROR','QA_T_SPEC_REV','QA_T_SPEC_REV_APPLY','QA_T_SPEC_REV_BLOB','SA_T_ITEM_MOVE',
        'SA_T_MONTH_STOCK','SA_T_PLAN_DTL','SA_T_STOCK_MAINT']
cn=pyodbc.connect(f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};DATABASE=PARTNER_ERP_TEST3;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}', autocommit=True)
c=cn.cursor()
FAIL=[]; SKIP=0
for t in TABLES:
    src=f"PARTNER_ERP.dbo.{t}"; nxt=f"nx.{t}"
    try:
        sc=c.execute(f"SELECT COUNT(*) FROM {src}").fetchone()[0]
    except Exception as e:
        print(f"  ✖ {t}: 원본없음/오류 {str(e)[:50]}"); FAIL.append(t); continue
    isview=c.execute("SELECT COUNT(*) FROM sys.views WHERE schema_id=SCHEMA_ID('nx') AND name=?", t).fetchone()[0]
    istab=c.execute("SELECT COUNT(*) FROM sys.tables WHERE schema_id=SCHEMA_ID('nx') AND name=?", t).fetchone()[0]
    # skip: 테이블 이미존재 & 행일치(멱등 고속)
    if istab and not isview:
        ec=c.execute(f"SELECT COUNT(*) FROM {nxt}").fetchone()[0]
        if ec==sc:
            SKIP+=1; continue
    if DRY:
        print(f"  계획: {src} ({sc}행) → {nxt} {'[뷰교체]' if isview else '[테이블교체]' if istab else '[신설]'}")
        continue
    try:
        if isview: c.execute(f"DROP VIEW {nxt}")
        if istab: c.execute(f"DROP TABLE {nxt}")
        c.execute(f"SELECT * INTO {nxt} FROM {src}")
        nc=c.execute(f"SELECT COUNT(*) FROM {nxt}").fetchone()[0]
        print(f"  {nxt}: {nc}행 (원본 {sc}) {'✔' if nc==sc else '✖'}")
        if nc!=sc: FAIL.append(t)
    except Exception as e:
        print(f"  ✖ {t}: 복제오류 {str(e)[:80]}"); FAIL.append(t)
if DRY: print("\nDRY (--commit 실행)")
else: print(f"\n충실 복제 완료 (스킵 {SKIP}, 실패 {len(FAIL)}: {FAIL})")

# ── nx 전용 확장 코드 재주입(라이브 코드마스터엔 없는 우리 클린분류 — 미러 재복사가 덮으므로 복원) ──
#    common._KINDMAP_EXT 와 정합. 컷오버 후 미러 은퇴 시 함께 정리.
if not DRY:
    NX_CODE_EXT = [('PR006', '240', '용접봉', 240)]  # 소분류 240=용접봉(2026-08-27, 재고평가 대상)
    for _kd, _cd, _ds, _sq in NX_CODE_EXT:
        if not c.execute("SELECT COUNT(*) FROM nx.CM_M_MASTER_DETAIL WHERE KIND_CODE=? AND DETAIL_CODE=?", _kd, _cd).fetchone()[0]:
            c.execute("""INSERT INTO nx.CM_M_MASTER_DETAIL (KIND_CODE,DETAIL_CODE,APPLY_YMD,DETAIL_DESC,SORT_SEQ,USE_FLAG,UPDATE_USER_ID,UPDATE_DATETIME)
                VALUES (?,?,'20260827',?,?,'1','MASTER',GETDATE())""", _kd, _cd, _ds, _sq)
            print(f"  nx코드확장 재주입: {_kd}.{_cd}={_ds}")
# ── nx 전용 컬럼 재주입(라이브엔 없는 웹 신규컬럼 — SELECT * INTO 재복사가 스키마를 덮으므로 복원) ──
#    파트마스터 공수화면(routers/partmaster.py·dragprod.py)이 read/write. 2026-08-31.
#    ★데이터(웹 입력값)는 DROP+재복사로 초기화됨(mirror∪웹 부채·§14) — 컷오버 후 별도 side테이블 권고.
if not DRY:
    NX_COL_EXT = [('PR_M_PROC_GAGONG', 'BARCODE_FLAG', 'NVARCHAR(1) NULL'),
                  ('PR_M_PROC_GAGONG', 'PROD_RESULT_TYPE', 'NVARCHAR(1) NULL')]
    for _tb, _col, _ty in NX_COL_EXT:
        if c.execute("SELECT COUNT(*) FROM sys.tables WHERE schema_id=SCHEMA_ID('nx') AND name=?", _tb).fetchone()[0] \
           and not c.execute("SELECT COUNT(*) FROM sys.columns WHERE object_id=OBJECT_ID('nx.'+?) AND name=?", _tb, _col).fetchone()[0]:
            c.execute(f"ALTER TABLE nx.{_tb} ADD {_col} {_ty}")
            print(f"  nx컬럼확장 재주입: nx.{_tb}.{_col}")
cn.close()
