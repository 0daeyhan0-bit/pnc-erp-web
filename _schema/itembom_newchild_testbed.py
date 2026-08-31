# -*- coding: utf-8 -*-
"""P2 검증: 인라인 신규 자식 등록 — item_save가 없는 품번을 품목마스터(nx.item)에 생성.
무커밋 롤백(오염0): 신규 코드로 item_save→nx.item 생성 확인→rollback."""
import sys, os, io
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'PNC_ERP_Web', 'backend'))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'New_ERP'))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import common
import routers.bom as B

PASS = []; FAIL = []
def chk(n, c, d=""):
    (PASS if c else FAIL).append(n); print(("  [OK] " if c else "  [FAIL] ") + n + ("" if c else " :: " + d))

NEW = 'ZZNEWCHILD_TEST_1'
real = common._nx_tx()
class Tx:
    def __init__(s, cn): object.__setattr__(s, '_cn', cn)
    def cursor(s): return object.__getattribute__(s, '_cn').cursor()
    def commit(s): pass
    def rollback(s): pass
    def close(s): pass
    def __getattr__(s, n): return getattr(object.__getattribute__(s, '_cn'), n)
proxy = Tx(real)
B._nx = lambda: proxy; B._nx_tx = lambda: proxy
cur = real.cursor()

try:
    cur.execute("DELETE FROM nx.item WHERE item_code=?", NEW)
    # 없는 품번 사전확인
    cur.execute("SELECT COUNT(*) FROM nx.item WHERE item_code=?", NEW)
    chk("T0 시작 시 미존재", cur.fetchone()[0] == 0)
    # 인라인 신규 자식 = 그리드에서 입력한 필드로 item_save (프론트 mrows 형태)
    row = {"item_code": NEW, "item_name": "테스트 신규자재", "item_spec": "", "metal_gubun": "CU",
           "diam": 6.35, "thick": 0.7, "length": 100, "net_weight": None, "unit": "EA",
           "in_cust": "", "sgroup": "130", "lgroup": "E", "make_type": "1", "cost_gubun": "3", "status": "사용"}
    r = B.item_save({"rows": [row]})
    print("  item_save:", r)
    # 생성 확인
    cur.execute("SELECT item_name, metal_gubun, diam, thick, sgroup, lgroup, make_type, cost_gubun, unit FROM nx.item WHERE item_code=?", NEW)
    got = cur.fetchone()
    chk("T1 nx.item 생성됨", got is not None, "미생성")
    if got:
        chk("T2 품명 저장", (got[0] or '').strip() == "테스트 신규자재", got[0])
        chk("T3 재질/치수 저장(CU·6.35·0.7)", (got[1] or '') == 'CU' and float(got[2] or 0) == 6.35 and float(got[3] or 0) == 0.7, f"{got[1]}/{got[2]}/{got[3]}")
        chk("T4 대분류/소분류/생산구분/단가구분", (got[5], got[6], got[7]) == ('E', '1', '3') and (got[4] or '') == '130', f"{got[4]}/{got[5]}/{got[6]}/{got[7]}")
        # cost_gubun='3'(소재) → net_weight 기하중량 자동재계산 됐는지(레거시 f_get_weight3)
        cur.execute("SELECT net_weight FROM nx.item WHERE item_code=?", NEW)
        nw = cur.fetchone()[0]
        chk("T5 소재단가(3)=중량 자동재계산", nw is not None and float(nw or 0) > 0, f"net_weight={nw}")
finally:
    B._nx = common._nx; B._nx_tx = common._nx_tx
    real.rollback(); real.close()

print(f"\n=== 결과 === PASS {len(PASS)} · FAIL {len(FAIL)}")
if FAIL: print("실패:", FAIL)
print("✓무커밋 롤백(신규 테스트품목 제거·오염0)")
