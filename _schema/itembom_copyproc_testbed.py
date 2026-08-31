# -*- coding: utf-8 -*-
"""P3 검증: 생산정보(공정·용접·관경) 복사 _copy_proc. 원본 AJR73364008 → 임시 target.
무커밋 롤백(오염0): 임시 target item 삽입→_copy_proc→검증→전체 rollback."""
import sys, os, io
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'PNC_ERP_Web', 'backend'))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'New_ERP'))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import common
import routers.bom as B

PASS = []; FAIL = []
def chk(n, c, d=""):
    (PASS if c else FAIL).append(n); print(("  [OK] " if c else "  [FAIL] ") + n + ("" if c else " :: " + d))

SRC = 'AJR73364008'; TGT = 'ZZTEST_COPYPROC_9'
cn = common._nx_tx(); cur = cn.cursor()
try:
    # 원본 보유량
    cur.execute("SELECT COUNT(*) FROM nx.routing WHERE item_code=? OR p_item=?", SRC, SRC); src_rt = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM nx.item_weld WHERE item_code=?", SRC); src_iw = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM nx.proc_weld WHERE parent_item=?", SRC); src_pw = cur.fetchone()[0]
    print(f"원본 {SRC}: routing {src_rt} · item_weld {src_iw} · proc_weld {src_pw}")

    # 임시 target item (copyproc은 target nx.item 존재 가정)
    cur.execute("DELETE FROM nx.item WHERE item_code=?", TGT)
    cur.execute("INSERT INTO nx.item(item_code,item_name,item_type) VALUES(?,?,N'제품')", TGT, 'TEST copyproc')

    # 복사 실행
    n = B._copy_proc(cur, SRC, TGT)
    print(f"copyproc 결과: {n}")

    # 검증: target 보유량 = 원본과 동일
    cur.execute("SELECT COUNT(*) FROM nx.routing WHERE item_code=? OR p_item=?", TGT, TGT); t_rt = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM nx.item_weld WHERE item_code=?", TGT); t_iw = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM nx.proc_weld WHERE parent_item=?", TGT); t_pw = cur.fetchone()[0]
    chk("T1 routing 복사 = 원본", t_rt == src_rt, f"{t_rt} vs {src_rt}")
    chk("T2 item_weld 복사 = 원본", t_iw == src_iw, f"{t_iw} vs {src_iw}")
    chk("T3 proc_weld 복사 = 원본", t_pw == src_pw, f"{t_pw} vs {src_pw}")

    # 품번레벨 routing: item_code=TGT 로 치환됐는지(carrier=용접봉 유지)
    cur.execute("SELECT COUNT(*) FROM nx.routing WHERE item_code=?", TGT); t_lvl = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM nx.routing WHERE item_code=?", SRC + '||NEVER'); _ = cur.fetchone()
    cur.execute("SELECT COUNT(*) FROM nx.routing WHERE p_item=? AND item_code LIKE 'RAC%'", TGT); t_carrier = cur.fetchone()[0]
    print(f"  target 품번레벨 {t_lvl} · 용접carrier(RAC) {t_carrier}")
    chk("T4 품번레벨 공정 item_code=target 치환", t_lvl > 0, "치환 안됨")
    chk("T5 용접carrier(RAC) 유지·p_item=target", t_carrier > 0, "carrier 없음")
    # 값 정합(work_qty 합)
    cur.execute("SELECT SUM(CAST(work_qty AS float)) FROM nx.routing WHERE item_code=? OR p_item=?", SRC, SRC); s_sum = cur.fetchone()[0] or 0
    cur.execute("SELECT SUM(CAST(work_qty AS float)) FROM nx.routing WHERE item_code=? OR p_item=?", TGT, TGT); t_sum = cur.fetchone()[0] or 0
    chk("T6 work_qty 합 동일(값 손실 없음)", abs(float(s_sum) - float(t_sum)) < 0.01, f"{s_sum} vs {t_sum}")
finally:
    cn.rollback(); cn.close()   # ★전체 롤백(임시 target·복사분 전부 제거·오염0)

print(f"\n=== 결과 === PASS {len(PASS)} · FAIL {len(FAIL)}")
if FAIL: print("실패:", FAIL)
print("✓무커밋 롤백(임시 target·복사분 제거·라이브 무접촉)")
