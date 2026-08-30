# -*- coding: utf-8 -*-
"""nx 성능 유지관리 — 인덱스 카탈로그(우리쿼리 기반) 멱등 생성 + 통계갱신.
   정본카탈로그=_schema/PERF_OPTIMIZATION_DESIGN.md §1. 컬럼검증(없으면 스킵)·기존인덱스 스킵(이름 ix_nxp_*)·NONCLUSTERED.
   MODE=dry(계획만)/commit(생성+통계). ★off-hours 권장(대용량 CREATE는 자원사용). 비파괴적.
   ★상보 도구=r_add_indexes.py: 마스터키 6개 UNIQUE(pr_m_item·cm_m_cust·pr_m_proc_gagong·pr_m_mat·
     PU_T_MONTH_STOCK_WH(_DAILY)) 소유 → 이 카탈로그와 스코프 분리(PR_M_ITEM 등 중복 금지).
     이 도구=거래대용량 heap+원가/BOM. 둘 다 컷오버 SELECT INTO 재동기 후 재실행 필요(인덱스 유실)."""
import sys, io, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, r'd:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP')
import db_client, pyodbc
MODE = sys.argv[1] if len(sys.argv) > 1 else 'dry'

# 인덱스 카탈로그: 테이블 -> [(접미명, [컬럼...])]  (우리쿼리 grep 기반, NONCLUSTERED)
CATALOG = {
    'PU_T_STOCK_MAINT':      [('ymmat', ['MAINT_YMD','MAT_CODE']), ('mat', ['MAT_CODE']), ('custym', ['CUST_CODE','MAINT_YMD'])],
    'PR_T_STOCK_MAINT_MAT':  [('ymmat', ['MAINT_YMD','MAT_CODE']), ('mat', ['MAT_CODE'])],
    'PU_T_READY_STOCK_MAINT':[('ymitem', ['MAINT_YMD','ITEM_CODE'])],
    'SA_T_STOCK_MAINT':      [('ymitem', ['MAINT_YMD','ITEM_CODE']), ('item', ['ITEM_CODE'])],
    'PR_T_PROD_DTL':         [('prodym_item', ['PROD_YMD','ITEM_CODE']), ('wo', ['WORK_ORDER'])],
    'PR_T_PROD_DTL_PROC':    [('wo', ['WORK_ORDER','SPLIT_WORK_ORDER']), ('item', ['ITEM_CODE'])],
    'SA_T_SALE_DTL':         [('wo', ['WORK_ORDER','SPLIT_WORK_ORDER']), ('item', ['ITEM_CODE'])],
    'SA_T_LG_RECEIVING_DTL': [('item', ['ITEM_CODE']), ('recvym', ['RECEIVING_YMD'])],
    'SA_T_PLAN_ITEM_DTL':    [('item', ['ITEM_CODE']), ('citem', ['C_ITEM_CODE'])],
    'PR_T_PLAN_ITEM_DTL':    [('item', ['ITEM_CODE']), ('citem', ['C_ITEM_CODE'])],
    'PU_T_SET_INPUT_REQ':    [('item', ['ITEM_CODE']), ('barcode', ['BARCODE_NO'])],
    'CS_T_ITEM_PROC':        [('pitem', ['P_ITEM_CODE','ITEM_CODE'])],
    # PR_M_ITEM(ITEM_CODE)=r_add_indexes.py의 UNIQUE ix_nx_prmitem_code 소유 → 여기서 제외(중복금지)
    'PR_M_ITEM_COST':        [('itemkey', ['ITEM_CODE','CUST_CODE','COST_TAG','COST_APPLY_YMD'])],
    'PR_M_ITEM_SUB':         [('item', ['ITEM_CODE'])],
    'CS_M_ITEM_BOM':         [('item', ['ITEM_CODE']), ('mat', ['MAT_CODE'])],
    'PR_M_ITEM_BOM':         [('item', ['ITEM_CODE']), ('mat', ['MAT_CODE'])],
    'PR_M_ITEM_ASSY_RT':     [('item', ['ITEM_CODE'])],
    'plan_part_mat':         [('woitem', ['WORK_ORDER','ITEM_CODE']), ('mat', ['MAT_CODE'])],
    # ★plan_mat_source(업체배분): soyo 계획쿼리 3중 self-join 키. 힙이면 44s→1.3s(2026-08-31 실측). 재생성 후 재보장 필수.
    'plan_mat_source':       [('womat', ['WORK_ORDER','MAT_CODE'])],
}

cn = pyodbc.connect(f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};DATABASE=PARTNER_ERP_TEST3;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}', autocommit=True)
c = cn.cursor()

def cols_of(t):
    c.execute("SELECT UPPER(name) FROM sys.columns WHERE object_id=OBJECT_ID('nx.'+?)", t)
    return set(r[0] for r in c.fetchall())
def idx_names(t):
    c.execute("SELECT name FROM sys.indexes WHERE object_id=OBJECT_ID('nx.'+?) AND name IS NOT NULL", t)
    return set(r[0] for r in c.fetchall())

print(f"=== nx 성능 유지관리 [{MODE.upper()}] ===")
created = skipped = missing = 0
for t, idxs in CATALOG.items():
    if not c.execute("SELECT OBJECT_ID('nx.'+?)", t).fetchone()[0]:
        print(f"  {t}: 테이블없음 스킵"); continue
    have = idx_names(t); avail = cols_of(t)
    for suf, cols in idxs:
        name = f"ix_nxp_{t}_{suf}"[:128]
        if name in have:
            skipped += 1; continue
        miss = [col for col in cols if col.upper() not in avail]
        if miss:
            missing += 1; print(f"  ⚠ {t}.{name}: 컬럼없음 {miss} → 스킵"); continue
        collist = ",".join(f"[{x}]" for x in cols)
        if MODE == 'commit':
            t0 = time.time()
            try:
                c.execute(f"CREATE NONCLUSTERED INDEX [{name}] ON nx.[{t}] ({collist})")
                print(f"  ✅ {name} ({','.join(cols)}) {time.time()-t0:.1f}s"); created += 1
            except Exception as e:
                print(f"  ✖ {name}: {str(e)[:80]}")
        else:
            print(f"  [생성예정] {name} ON nx.{t} ({','.join(cols)})"); created += 1
    if MODE == 'commit':
        try: c.execute(f"UPDATE STATISTICS nx.[{t}]")
        except Exception: pass
print(f"\n{'생성' if MODE=='commit' else '생성예정'} {created} · 이미있음 {skipped} · 컬럼없어스킵 {missing}")
if MODE == 'commit': print("+ 통계갱신 완료")
cn.close()
