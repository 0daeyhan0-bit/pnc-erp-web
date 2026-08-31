# -*- coding: utf-8 -*-
"""P4 검증: route별 생산정보(생산 ST축 분리) — 스키마·prodinfo route-aware·R02 편성 게이트.
무커밋 롤백(오염0): 테스트 R02 route+생산정보 삽입→검증→전체 rollback.
두 축 분리 확인: R01(품번키 prodinfo_proc)·R02(route_proc_gagong) 서로 안 섞임."""
import sys, os, io
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'PNC_ERP_Web', 'backend'))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'New_ERP'))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import common
import routers.prodinfo as P
import routers.soyo as S

PASS = []; FAIL = []
def chk(n, c, d=""):
    (PASS if c else FAIL).append(n); print(("  [OK] " if c else "  [FAIL] ") + n + ("" if c else " :: " + d))

real = common._nx_tx()  # autocommit=False
class Tx:
    def __init__(s, cn): object.__setattr__(s, '_cn', cn)
    def cursor(s): return object.__getattribute__(s, '_cn').cursor()
    def commit(s): pass
    def rollback(s): pass
    def close(s): pass
    def __getattr__(s, n): return getattr(object.__getattribute__(s, '_cn'), n)
proxy = Tx(real)
P._nx = lambda: proxy; P._nx_tx = lambda: proxy
cur = real.cursor()

try:
    # 실재 ASSY(품번키 생산정보 보유) 하나 선택 — R01 시드/무영향 확인용
    cur.execute("SELECT TOP 1 ITEM_CODE FROM PARTNER_ERP_TEST3.nx.PR_M_ITEM_PROC_GAGONG GROUP BY ITEM_CODE HAVING COUNT(*)>=2 ORDER BY ITEM_CODE")
    ASSY = str(cur.fetchone()[0]).strip()
    cur.execute("SELECT COUNT(*) FROM PARTNER_ERP_TEST3.nx.PR_M_ITEM_PROC_GAGONG WHERE ITEM_CODE=?", ASSY)
    base_proc_cnt = cur.fetchone()[0]
    print(f"테스트 ASSY={ASSY} · 품번키 생산정보 {base_proc_cnt}행")

    S._ensure_route_proc(cur); P._ensure_route_proc(cur)

    # 테스트 R02 route 헤더(route_no=2·current_flag=1=활성지정, route_id=IDENTITY auto) + 게이트 4조건 충족 준비
    cur.execute("""INSERT INTO nx.sourcing_route(item_code,route_no,route_name,current_flag,approve_flag,vendor_code,gubun)
                   OUTPUT INSERTED.route_id VALUES(?,2,N'테스트R02',1,1,N'',N'외주가공')""", ASSY)
    RID = int(cur.fetchone()[0])
    print(f"테스트 R02 route_id={RID}")
    cur.execute("DELETE FROM nx.route_proc_gagong WHERE route_id=?", RID)
    cur.execute("DELETE FROM nx.route_edges WHERE route_id=?", RID)
    cur.execute("INSERT INTO nx.route_edges(route_id,item_code,mat_code,use_qty_pr) VALUES(?,?,?,1)", RID, ASSY, ASSY)
    # sourcing_profile: 업체+단가 충족
    S._ensure_profile_price(cur)
    cur.execute("SELECT TOP 1 partner_code FROM nx.partner ORDER BY partner_code")
    VEND = str(cur.fetchone()[0]).strip()
    cur.execute("DELETE FROM nx.sourcing_profile WHERE route_id=?", RID)
    cur.execute("""INSERT INTO nx.sourcing_profile(item_code,route_id,profile_name,supply_gubun,vendor_code,lme_flag,apply_from,is_active,is_internal,buy_price)
                   VALUES(?,?,N'테스트프로파일',N'매입',?,0,'2026-01-01',1,0,100)""", ASSY, RID, VEND)

    # ── T1: 게이트 — 4조건 충족·생산정보 미등록 → "생산정보 미등록" 차단 ──
    bad = S._route_gate_incomplete(cur)
    mine = [b for b in bad if b["route_id"] == RID]
    chk("T1 게이트: R02 생산정보 미등록 시 차단", len(mine) == 1 and "생산정보 미등록" in mine[0]["missing"],
        f"bad={mine}")
    # 다른 사유는 없어야(4조건 충족) — 생산정보만 걸림
    chk("T1b 게이트: 생산정보 외 사유 없음(4조건 충족)", mine and mine[0]["missing"] == ["생산정보 미등록"],
        f"missing={mine[0]['missing'] if mine else None}")

    # ── T2: prodinfo route-aware 저장 → route_proc_gagong 기록(R02) ──
    rows = [{"proc_seq": 1, "work_code": "S5", "gagong_proc_code": "P0002", "s_work_code": 0,
             "work_qty": 5, "tot_st": 12.5, "lt_hr": 2, "gagong_proc_seq": 1},
            {"proc_seq": 2, "work_code": "S1", "gagong_proc_code": "P0003", "s_work_code": 0,
             "work_qty": 3, "tot_st": 8.0, "lt_hr": 1, "gagong_proc_seq": 1}]
    r = P.prodinfo_proc_save({"item": ASSY, "rows": rows, "route_id": RID, "user": "테스트"})
    chk("T2 prodinfo 저장 scope=route", r.get("ok") and r.get("scope") == "route", str(r))
    cur.execute("SELECT COUNT(*) FROM nx.route_proc_gagong WHERE route_id=? AND item_code=?", RID, ASSY)
    chk("T2b route_proc_gagong 2행 기록", cur.fetchone()[0] == 2)
    # ★R01 품번키(prodinfo_proc/PR_M_ITEM_PROC_GAGONG)는 무변경 = 두 축 분리
    cur.execute("SELECT COUNT(*) FROM PARTNER_ERP_TEST3.nx.PR_M_ITEM_PROC_GAGONG WHERE ITEM_CODE=?", ASSY)
    chk("T2c 두 축 분리: 품번키 생산정보 무변경", cur.fetchone()[0] == base_proc_cnt, "품번키 오염됨")

    # ── T3: 저장 후 게이트 통과(생산정보 미등록 해제) ──
    bad2 = S._route_gate_incomplete(cur)
    mine2 = [b for b in bad2 if b["route_id"] == RID]
    chk("T3 게이트: 생산정보 등록 후 통과", len(mine2) == 0, f"still bad={mine2}")

    # ── T4: prodinfo_get route_id → route 스코프 읽기(proc_src=route) ──
    P._nx = lambda: proxy
    g = P.prodinfo_get(ASSY, 0, RID)
    chk("T4 prodinfo_get route: proc_src=route", g.get("proc_src") == "route", f"src={g.get('proc_src')}")
    chk("T4b prodinfo_get route: 2공정 반환", len(g.get("proc", [])) == 2, f"n={len(g.get('proc',[]))}")
    # R01(route_id=0) 조회는 품번키(현행) — route 데이터 안 섞임
    g0 = P.prodinfo_get(ASSY, 0, 0)
    chk("T4c R01 조회는 품번키(route 데이터 미혼입)", g0.get("proc_src") in ("nx", "legacy") and len(g0.get("proc", [])) == base_proc_cnt,
        f"src={g0.get('proc_src')} n={len(g0.get('proc',[]))}")

    # ── T5: 활성판정 plan_route_active — 생산정보 있는 R02만 활성(_ROUTE_GATE_SQL) ──
    S._route_setup(cur)
    cur.execute("SELECT COUNT(*) FROM nx.plan_route_active WHERE route_id=?", RID)
    chk("T5 활성판정: 생산정보 갖춘 R02 활성 등록", cur.fetchone()[0] == 1)
    # 생산정보 지우면 활성서 빠짐
    cur.execute("DELETE FROM nx.route_proc_gagong WHERE route_id=?", RID)
    S._route_setup(cur)
    cur.execute("SELECT COUNT(*) FROM nx.plan_route_active WHERE route_id=?", RID)
    chk("T5b 활성판정: 생산정보 지우면 활성 제외", cur.fetchone()[0] == 0)

finally:
    P._nx = common._nx; P._nx_tx = common._nx_tx
    real.rollback(); real.close()   # ★전체 롤백(테스트 route·생산정보 전부 제거·오염0)

print(f"\n=== 결과 === PASS {len(PASS)} · FAIL {len(FAIL)}")
if FAIL: print("실패:", FAIL)
print("✓무커밋 롤백(테스트 R02·route_proc_gagong 제거·라이브 무접촉)")
