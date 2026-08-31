# -*- coding: utf-8 -*-
import sys, os, io
sys.path.insert(0, r"d:/피앤씨인더스트리/100_AI_AGENT/Projects/_wt_order/PNC_ERP_Web/backend")
sys.path.insert(0, r"d:/피앤씨인더스트리/100_AI_AGENT/Projects/New_ERP")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import common, routers.bom as B
PASS=[];FAIL=[]
def chk(n,c,d=""):
    (PASS if c else FAIL).append(n);print(("  [OK] " if c else "  [FAIL] ")+n+("" if c else " :: "+d))
SRC='AJR73364008'; TGT='ZZTEST_COPYPROD_1'
cn=common._nx_tx(); cur=cn.cursor()
try:
    # source 유효 생산정보 행수(prodinfo_proc 우선, 없으면 레거시)
    cur.execute("SELECT COUNT(*) FROM nx.prodinfo_proc WHERE item_code=?", SRC); snx=cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM PARTNER_ERP_TEST3.nx.PR_M_ITEM_PROC_GAGONG WHERE ITEM_CODE=?", SRC); sleg=cur.fetchone()[0]
    expect = snx if snx>0 else sleg
    print(f"원본 {SRC}: prodinfo_proc={snx} · 레거시={sleg} → 기대 복사={expect}")
    n=B._copy_prodinfo(cur, SRC, TGT)
    print("_copy_prodinfo 반환:", n)
    cur.execute("SELECT COUNT(*) FROM nx.prodinfo_proc WHERE item_code=?", TGT); tgot=cur.fetchone()[0]
    chk("T1 생산정보 target 복사 = source 유효본", tgot==expect and expect>0, f"{tgot} vs {expect}")
    # 단품공정(s_work_code) 보존 확인(STEP6 키)
    cur.execute("SELECT COUNT(*) FROM nx.prodinfo_proc WHERE item_code=? AND s_work_code>0", TGT); tsw=cur.fetchone()[0]
    chk("T2 단품공정(s_work_code) 복사됨", tsw>0 or expect==0, f"s_work>0 행 {tsw}")
    # 원가축(routing/proc_weld)은 별개 — _copy_prodinfo가 안 건드림
    cur.execute("SELECT COUNT(*) FROM nx.routing WHERE item_code=? OR p_item=?", TGT, TGT); trt=cur.fetchone()[0]
    chk("T3 두 축 분리: _copy_prodinfo는 routing(원가) 무접촉", trt==0, f"routing {trt}")
finally:
    cn.rollback(); cn.close()
print(f"\n=== PASS {len(PASS)} · FAIL {len(FAIL)} ===")
if FAIL: print("실패:",FAIL)
print("✓무커밋 롤백(오염0)")
