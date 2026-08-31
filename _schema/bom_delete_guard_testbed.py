# -*- coding: utf-8 -*-
"""★품번 삭제 통제 로직 전 시나리오 검증(사용자 하드룰 2026-08-31).
   기록용 — 나중에 실행. 무커밋 롤백(오염0). 단일 공유 커서(MARS 없음 대응).

검증 시나리오(모든 사용처가 삭제를 차단해야 함):
  T1  src='web' 저장 → 품목마스터 src 마킹(조달경로 R01 수정가능 근거)
  T2  사용처 없음 → _usage_blockers=[] (삭제 가능)
  T3  bom_delete 완전삭제: BOM·평면·원가공정·생산정보(prodinfo_proc·route_proc_gagong)·마스터 전부 0
  G1  다른 BOM 자식으로 사용중 → 차단
  G2  모델BOM 구성(model_bom.C_ITEM_CODE) → 차단
  G3  다른 품번 조달경로 라인(sourcing_route_line.child_item) → 차단
  G4  생산계획 품목별(plan_item_dtl.C_ITEM_CODE) → 차단
  G5  생산계획 자재소요(plan_part_mat.mat_code/assy_item_code) → 차단
  G6  주문(recv_dtl.ITEM_CODE) → 차단
  M1  itemmaster_delete 도 동일 가드(_usage_blockers) 적용 → 사용중 차단
  M2  itemmaster_delete 도 동일 완전정리(_purge_item) 적용 → 미사용 완전삭제
  ※ 차단 시 품목/파생 보존(삭제 안 됨) 재확인
"""
import sys, os, io
sys.path.insert(0, r"d:/피앤씨인더스트리/100_AI_AGENT/Projects/_wt_order/PNC_ERP_Web/backend")
sys.path.insert(0, r"d:/피앤씨인더스트리/100_AI_AGENT/Projects/New_ERP")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import common, routers.bom as B, routers.item as I, routers.soyo as SOYO

PASS = []; FAIL = []
def chk(n, c, d=""):
    (PASS if c else FAIL).append(n); print(("  [OK] " if c else "  [FAIL] ") + n + ("" if c else " :: " + d))

NEW = 'ZZDEL_TEST_A'; PAR = 'ZZDEL_PARENT_B'

real = common._nx_tx()
class Tx:
    def __init__(s, cn): object.__setattr__(s, '_cn', cn); object.__setattr__(s, '_cur', cn.cursor())
    def cursor(s): return object.__getattribute__(s, '_cur')
    def commit(s): pass
    def rollback(s): pass
    def close(s): pass
    def __getattr__(s, n): return getattr(object.__getattribute__(s, '_cn'), n)
proxy = Tx(real)
B._nx = lambda: proxy; B._nx_tx = lambda: proxy
I._nx = lambda: proxy; I._nx_tx = lambda: proxy
cur = proxy.cursor()

def _seed_item(code, src=None):
    B.item_save({"rows": [{"item_code": code, "item_name": "삭제테스트", "sgroup": "130", "lgroup": "E",
                           "make_type": "1", "cost_gubun": "3", "status": "사용", **({"src": src} if src else {})}]})

def _seed_bom(parent, child):
    B.bom_save({"item": parent, "target_name": parent, "lines": [{"child_item": child, "qty": 1, "item_name": child}]})

def _clear(code):
    # 파생 전부(가드 우회 직접 정리 — 시나리오 격리용)
    try: B._purge_item(cur, code)
    except Exception: pass

try:
    for it in (NEW, PAR): cur.execute("DELETE FROM nx.item WHERE item_code=?", it)

    # ── T1 src='web' ──
    _seed_item(NEW, src='web')
    cur.execute("SELECT ISNULL(src,'') FROM nx.item WHERE item_code=?", NEW)
    chk("T1 src='web' 저장(R01 수정가능 근거)", (cur.fetchone()[0] or '') == 'web')

    # ── 파생 데이터 심기(BOM=실제 경로 + 생산정보 + route별) ──
    _seed_bom(NEW, '4H00049C')
    cur.execute("INSERT INTO nx.prodinfo_proc(item_code,proc_seq,s_work_code) VALUES(?,1,124)", NEW)
    SOYO._ensure_route_proc(cur)
    cur.execute("INSERT INTO nx.route_proc_gagong(route_id,item_code,proc_seq,s_work_code) VALUES(9911,?,1,124)", NEW)

    # ── T2 사용처 없음 → 삭제가능 ──
    chk("T2 사용처 없음 → 가드 통과(삭제가능)", B._usage_blockers(cur, NEW) == [])

    # ── T3 bom_delete 완전삭제 ──
    r = B.bom_delete({"item": NEW})
    chk("T3 bom_delete ok", r.get("ok"), str(r)[:120])
    for t, col in [('item', 'item_code'), ('bom_header', 'item_code'), ('prodinfo_proc', 'item_code'), ('route_proc_gagong', 'item_code')]:
        cur.execute(f"SELECT COUNT(*) FROM nx.{t} WHERE {col}=?", NEW)
        chk(f"T3 완전삭제:{t}=0", cur.fetchone()[0] == 0)

    # ══════ G1~G6: 각 사용처별 차단 (사용처 심기 → 가드 차단 확인 → 사용처 정리) ══════
    def guard_case(tag, seed_fn, unseed_fn, where_kw):
        _clear(NEW); _seed_item(NEW, src='web')
        seed_fn()
        blk = B._usage_blockers(cur, NEW)
        chk(f"{tag} 사용중 → 가드 차단", len(blk) > 0 and any(where_kw in b['where'] for b in blk), f"blk={blk}")
        r2 = B.bom_delete({"item": NEW})
        chk(f"{tag} bom_delete 거부(blocked)", (not r2.get("ok")) and r2.get("blocked"), str(r2)[:100])
        cur.execute("SELECT COUNT(*) FROM nx.item WHERE item_code=?", NEW)
        chk(f"{tag} 차단 시 품목 보존", cur.fetchone()[0] == 1)
        unseed_fn()

    # G1 다른 BOM 자식
    def g1s(): _seed_item(PAR); _seed_bom(PAR, NEW)
    def g1u(): _clear(PAR)
    guard_case("G1 다른BOM 자식", g1s, g1u, "BOM")

    # G2 모델BOM (MODEL_NO,C_ITEM_CODE NOT NULL)
    def g2s(): cur.execute("INSERT INTO nx.model_bom(MODEL_NO,C_ITEM_CODE,USE_QTY) VALUES('ZZMODEL',?,1)", NEW)
    def g2u(): cur.execute("DELETE FROM nx.model_bom WHERE MODEL_NO='ZZMODEL'")
    guard_case("G2 모델BOM", g2s, g2u, "모델BOM")

    # G3 다른 품번 조달경로 라인(sourcing_route_line) — PAR 소유 route에 NEW를 자식으로
    def g3s():
        _seed_item(PAR)
        cur.execute("""INSERT INTO nx.sourcing_route(item_code,route_no,route_name,current_flag,approve_flag)
                       OUTPUT INSERTED.route_id VALUES(?,2,N'G3',0,0)""", PAR)
        rid = int(cur.fetchone()[0])
        cur.execute("INSERT INTO nx.sourcing_route_line(route_id,child_item,qty) VALUES(?,?,1)", rid, NEW)
        g3s.rid = rid
    def g3u():
        cur.execute("DELETE FROM nx.sourcing_route_line WHERE route_id=?", g3s.rid)
        cur.execute("DELETE FROM nx.sourcing_route WHERE route_id=?", g3s.rid); _clear(PAR)
    guard_case("G3 타품번 조달경로 라인", g3s, g3u, "조달경로")

    # G4 생산계획 품목별(plan_item_dtl.C_ITEM_CODE)
    def g4s(): cur.execute("INSERT INTO nx.plan_item_dtl(PLAN_YMD,WORK_ORDER,C_ITEM_CODE,PLAN_QTY) VALUES('260901','ZZWO',?,1)", NEW)
    def g4u(): cur.execute("DELETE FROM nx.plan_item_dtl WHERE WORK_ORDER='ZZWO'")
    guard_case("G4 생산계획 품목별", g4s, g4u, "생산계획 품목별")

    # G5 생산계획 자재소요(plan_part_mat.mat_code)
    def g5s(): cur.execute("INSERT INTO nx.plan_part_mat(plan_ymd,work_order,mat_code,part_plan_qty) VALUES('260901','ZZWO',?,1)", NEW)
    def g5u(): cur.execute("DELETE FROM nx.plan_part_mat WHERE work_order='ZZWO'")
    guard_case("G5 생산계획 자재소요", g5s, g5u, "자재소요")

    # G6 주문(recv_dtl.ITEM_CODE, ORDER_NO NOT NULL)
    def g6s(): cur.execute("INSERT INTO nx.recv_dtl(ORDER_NO,WORK_ORDER,ITEM_CODE,ORDER_QTY) VALUES('ZZORD','ZZWO',?,1)", NEW)
    def g6u(): cur.execute("DELETE FROM nx.recv_dtl WHERE ORDER_NO='ZZORD'")
    guard_case("G6 주문(recv_dtl)", g6s, g6u, "주문")

    # ══════ M1/M2: itemmaster_delete 도 동일 가드+정리 ══════
    # M1 사용중 → 차단
    _clear(NEW); _seed_item(NEW, src='web'); _seed_item(PAR); _seed_bom(PAR, NEW)   # NEW가 PAR의 자식
    rm1 = I.itemmaster_delete({"codes": [NEW]})
    chk("M1 itemmaster_delete 사용중 차단", (not rm1.get("ok")) and rm1.get("blocked"), str(rm1)[:120])
    cur.execute("SELECT COUNT(*) FROM nx.item WHERE item_code=?", NEW)
    chk("M1 차단 시 품목 보존", cur.fetchone()[0] == 1)
    # M2 미사용 → 완전삭제
    _clear(PAR)   # 부모 제거 → NEW 미사용
    _seed_item(NEW, src='web'); _seed_bom(NEW, '4H00049C')
    cur.execute("INSERT INTO nx.prodinfo_proc(item_code,proc_seq,s_work_code) VALUES(?,1,124)", NEW)
    rm2 = I.itemmaster_delete({"codes": [NEW]})
    chk("M2 itemmaster_delete 미사용 완전삭제", rm2.get("ok") and rm2.get("deleted") == 1, str(rm2)[:120])
    for t in ('item', 'bom_header', 'prodinfo_proc'):
        cur.execute(f"SELECT COUNT(*) FROM nx.{t} WHERE item_code=?", NEW)
        chk(f"M2 완전삭제:{t}=0", cur.fetchone()[0] == 0)

finally:
    B._nx = common._nx; B._nx_tx = common._nx_tx
    I._nx = common._nx; I._nx_tx = common._nx_tx
    real.rollback(); real.close()

print(f"\n=== 결과 === PASS {len(PASS)} · FAIL {len(FAIL)}")
if FAIL: print("실패:", FAIL)
print("✓무커밋 롤백(오염0) · 전 시나리오(BOM자식·모델BOM·조달경로·생산계획·자재소요·주문 + itemmaster 동일가드)")
