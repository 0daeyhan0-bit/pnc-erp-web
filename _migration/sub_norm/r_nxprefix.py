# -*- coding: utf-8 -*-
"""프로그램 nx전환 헬퍼: 파일 내 bare 라이브테이블 참조(FROM/JOIN/comma) → PARTNER_ERP_TEST3.nx.<T> 풀패스.
풀패스는 어느 커넥션에서도 작동(커넥션 변경 불필요). 이미 nx.·PARTNER_ERP_TEST3.nx.·PARTNER_ERP.dbo. 는 미매칭(안전).
utf-8 안전. 사용: python r_nxprefix.py <file> [--apply]  (기본 dry)"""
import sys, io, re, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
TABLES=['PR_M_ITEM_BOM','CS_M_ITEM_BOM','PR_M_ITEM_PROC_GAGONG','PR_M_WORK_SINGLE','PR_M_PROC_GAGONG','PR_M_ITEM',
        'PR_M_MAT','CM_M_CUST_MAGAM','CM_M_CUST','CM_USER_MEETING_1','CS_M_PROC','CS_T_ITEM_PROC','CS_T_ITEM_WELD',
        'PR_M_ITEM_COST','PR_M_MODEL_BOM_EXCEPT','PR_M_MODEL_BOM','PR_M_WORK','QA_M_MACHINE',
        'PR_T_INDI_CUTTING_PROC_GAGONG','PR_T_INDI_CUTTING','PR_T_MAT_STOCK_WH','PR_T_PLAN_PART_DTL','PR_T_PROD_DTL_GAGONG',
        'PU_T_MAT_STOCK_WH','PU_T_READY_STOCK','PU_T_SAGUB_STOCK','PU_T_STACKER_STOCK','PU_T_STOCK_MAINT',
        'SA_T_ITEM_STOCK','SA_T_RECV_DTL','SA_T_SALE_DTL',
        'CM_M_MASTER_DETAIL','PU_T_STOCK_MAINT_C',
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
# 긴 이름 우선(부분매칭 방지)
TABLES=sorted(TABLES, key=len, reverse=True)
fp=sys.argv[1]; APPLY='--apply' in sys.argv
txt=open(fp,encoding='utf-8').read(); orig=txt; total=0
# 0) 명시 PARTNER_ERP.dbo. → PARTNER_ERP_TEST3.nx. (블랭킷)
nb=txt.count('PARTNER_ERP.dbo.'); txt=txt.replace('PARTNER_ERP.dbo.','PARTNER_ERP_TEST3.nx.'); total+=nb
if nb: print(f"   [PARTNER_ERP.dbo.→nx]: {nb}")
for t in TABLES:
    # FROM/JOIN/comma + 공백 + 테이블(대소문자무관) + 경계. 앞이 '.'이면(이미 qualified) 미매칭.
    pat=re.compile(r'(\b(?:FROM|JOIN)\s+)(?<![.\w])('+t+r')\b', re.IGNORECASE)
    txt,n=pat.subn(lambda m: m.group(1)+'PARTNER_ERP_TEST3.nx.'+m.group(2), txt)
    total+=n
    # comma-join: ", TABLE alias" (FROM A T, B U)
    pat2=re.compile(r'(,\s*)(?<![.\w])('+t+r')(\s+[A-Za-z])', re.IGNORECASE)
    txt,n2=pat2.subn(lambda m: m.group(1)+'PARTNER_ERP_TEST3.nx.'+m.group(2)+m.group(3), txt)
    total+=n2
    if n+n2: print(f"   {t}: {n+n2}")
print(f"{os.path.basename(fp)}: 총 {total}건 {'APPLIED' if APPLY else '(dry)'}")
if APPLY and txt!=orig:
    open(fp,'w',encoding='utf-8').write(txt); print("  저장됨")
