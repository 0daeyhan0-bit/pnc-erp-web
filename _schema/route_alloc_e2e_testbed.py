# -*- coding: utf-8 -*-
"""★R02 활성→생산계획 반영 E2E 테스트베드 (2026-08-31) — ★실제 엔드포인트 구동 방식.

원시 INSERT 금지. FLOW TestBed와 동일하게 **실제 app을 no-commit 공유커넥션으로 몽키패치**하고
in-process TestClient로 **실제 화면 API를 그대로 호출**한다:
    route/copy → route/finalize(route_edges) → route/approve → profile/save(업체·단가)
    → prodinfo/proc/save(생산정보 route_proc) → route/alloc/save(택1 활성)
그리고 **실제 엔진 함수** soyo._route_setup(plan_route_active)·_route_gate_incomplete로 반영/차단을 판정.

시나리오마다 RAW.rollback()으로 원상복귀(pristine 격리) → 각 시나리오 독립.
종료 시 전체 rollback + 기동시점 행수 대조로 **오염 0** 증명.

50+ 시나리오: 작동가능 품목 자동탐색 × [전체활성→반영 / 승인생략 / 업체·단가생략 / 생산정보생략 /
    미활성 / 비활성화 / 승인취소 / 업체만·단가없음 / 재활성] + 전역(baseline·R01활성·택1배타성).
"""
import sys, os, io, argparse

HERE = os.path.dirname(os.path.abspath(__file__))
BE = os.path.join(HERE, '..', 'PNC_ERP_Web', 'backend')
sys.path.insert(0, BE); os.chdir(BE)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
sys.path.insert(0, r'd:/피앤씨인더스트리/100_AI_AGENT/Projects/New_ERP')

import common, pyodbc, db_client
CS = (f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};'
      f'DATABASE=PARTNER_ERP_TEST3;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}')
RAW = pyodbc.connect(CS, autocommit=False)

class NoCommitConn:
    """트랜잭션(commit/rollback)만 무력화, 커서 수명은 정상 유지(FLOW harness와 동일)."""
    def __init__(self, cn):
        object.__setattr__(self, '_cn', cn); object.__setattr__(self, '_curs', [])
    def cursor(self):
        c = self._cn.cursor(); self._curs.append(c); return c
    def commit(self): pass
    def close(self):
        for c in self._curs:
            try: c.close()
            except Exception: pass
        self._curs.clear()
    def rollback(self): pass
    def __enter__(self): return self
    def __exit__(self, *a): self.close(); return False
    def __getattr__(self, n): return getattr(self._cn, n)

def _shared(): return NoCommitConn(RAW)
common._nx = _shared; common._nx_tx = _shared
os.environ["FLOW_TESTBED"] = "1"
import app as APP
_patched = 0
for name, mod in list(sys.modules.items()):
    if not (name.startswith('routers.') or name in ('live_api', 'common')): continue
    for attr in ('_nx', '_nx_tx'):
        if hasattr(mod, attr): setattr(mod, attr, _shared); _patched += 1
import routers.soyo as soyo

# ── uvicorn을 데몬 스레드로 기동(같은 프로세스=공유 RAW·soyo 엔진 직접 판정 가능) ──
import threading, time as _time, json as _json, urllib.request, urllib.error
import uvicorn
PORT = 8093
import socket as _socket
_srv = uvicorn.Server(uvicorn.Config(APP.app, host="127.0.0.1", port=PORT, log_level="error"))
threading.Thread(target=_srv.run, daemon=True).start()
_ready = False
for _ in range(160):
    try:
        s = _socket.create_connection(("127.0.0.1", PORT), timeout=1); s.close(); _ready = True; break
    except Exception: _time.sleep(0.5)
if not _ready:
    print("★서버 기동 실패"); RAW.rollback(); sys.exit(1)
TOKEN = [None]

# 오염0 기준(시나리오 입력이 닿는 테이블)
TABS = ("nx.sourcing_route", "nx.sourcing_route_line", "nx.sourcing_route_proc", "nx.sourcing_route_weld",
        "nx.sourcing_profile", "nx.route_edges", "nx.route_alloc", "nx.route_proc_gagong",
        "nx.prodinfo_proc", "nx.sub_registry")
def snap():
    c = pyodbc.connect(CS, autocommit=True).cursor(); out = {}
    for t in TABS:
        try: c.execute(f"SELECT COUNT(*) FROM {t}"); out[t] = c.fetchone()[0]
        except Exception: out[t] = None
    c.close(); return out
ROWS0 = snap()

# ───────── 실제 프로그램 호출 헬퍼 ─────────
def post(path, body):
    data = _json.dumps(body).encode("utf-8")
    hdr = {"Content-Type": "application/json"}
    if TOKEN[0]: hdr["Authorization"] = "Bearer " + TOKEN[0]
    req = urllib.request.Request(f"http://127.0.0.1:{PORT}{path}", data=data, method="POST", headers=hdr)
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return _json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try: return _json.loads(e.read().decode("utf-8"))
        except Exception: return {"_err": str(e)}
    except Exception as e:
        return {"_err": str(e)[:200]}

def sql1(q, *a):
    cur = RAW.cursor()
    try: cur.execute(q, *a); r = cur.fetchone(); return r[0] if r else None
    finally: cur.close()

def active_cnt(item):
    """★실제 엔진 soyo._route_setup 구동 → nx.plan_route_active에 item 포함수."""
    cur = RAW.cursor()
    try:
        soyo._route_setup(cur)
        cur.execute("SELECT COUNT(*) FROM nx.plan_route_active WHERE assy_item_code=?", item.upper())
        return int(cur.fetchone()[0])
    finally: cur.close()

def gate_bad(item):
    cur = RAW.cursor()
    try:
        bad = soyo._route_gate_incomplete(cur)
        return [b for b in bad if str(b.get('item','')).strip().upper() == item.upper()]
    finally: cur.close()

def _relogin():
    """★로그인 세션은 no-commit 커넥션에 uncommitted 기록 → 롤백/스왑 시 소멸.
       auth _TOK_CACHE TTL=60s라 캐시 만료 후 DB세션 조회가 빈 세션을 만나 401.
       ⟹ 시나리오마다 재로그인해 토큰·캐시 갱신(각 시나리오 <60s이므로 캐시 항상 히트)."""
    TOKEN[0] = None
    r = post("/api/auth/login", {"id": "super", "pw": os.environ.get("FLOW_PW_SUPER", "super")})
    TOKEN[0] = r.get("token")
    return TOKEN[0]

def rollback():
    """★시나리오 격리 = 공유커넥션 통째 교체(닫기=미커밋 롤백) + 재로그인(세션 갱신).
       server 스레드/메인 모두 호출시점 전역 RAW를 읽으므로(요청 순차) 안전."""
    global RAW
    try: RAW.close()
    except Exception: pass
    RAW = pyodbc.connect(CS, autocommit=False)
    _relogin()

# ───────── 로그인(실제 인증) ─────────
_jl = post("/api/auth/login", {"id": "super", "pw": os.environ.get("FLOW_PW_SUPER", "super")})
TOKEN[0] = _jl.get("token")
print(f"로그인(super): {'OK' if TOKEN[0] else '실패 '+str(_jl)[:90]}")

# ───────── R02 생애주기(실제 엔드포인트) ─────────
YMD = "260630"
def copy_route(item):
    j = post("/api/sourcing/route/copy", {"item_code": item, "source": "", "ymd": YMD, "user": "e2e"})
    return int(j.get("route_id") or 0) if j.get("ok") else 0
def _edges_n(jf):
    re = jf.get("route_edges")
    return (re.get("edges", 0) if isinstance(re, dict) else (re or 0))
def build_edges(rid, item):
    jf = post("/api/sourcing/route/finalize", {"route_id": rid, "item_code": item, "ymd": YMD, "commit": 1})
    return jf, _edges_n(jf)
def approve(rid, on=True):
    return post("/api/sourcing/route/approve", {"route_id": rid, "approve": 1 if on else 0, "user": "e2e"})
def set_vendor_price(rid, vendor, buy=100, sagub=None):
    row = {"profile_id": 0, "vendor_code": vendor, "supply_gubun": "2", "lme_flag": 0,
           "apply_from": "2000-01-01", "is_active": 0, "is_internal": 0}
    if buy is not None: row["buy_price"] = buy
    if sagub is not None: row["sagub_price"] = sagub
    return post("/api/sourcing/profile/save", {"route_id": rid, "rows": [row]})
def set_prodinfo(rid, item):
    return post("/api/prodinfo/proc/save", {"item": item, "route_id": rid,
        "rows": [{"proc_seq": 1, "work_code": "P2", "gagong_proc_code": "", "s_work_code": 0, "work_qty": 1, "tot_st": 1}], "user": "e2e"})
def activate(item, rid, on=True):
    return post("/api/sourcing/route/alloc/save", {"item": item,
        "rows": [{"route_id": rid, "is_active": 1 if on else 0, "alloc_ratio": (100 if on else None), "apply_from": "2000-01-01"}]})
def get_route(item, do_approve=True):
    """copy(현행복사)→finalize(edges). 성공 시 rid, 실패 0."""
    rid = copy_route(item)
    if not rid: return 0
    jf, en = build_edges(rid, item)
    if en <= 0: return 0
    if do_approve: approve(rid, True)
    return rid
def full_setup(item):
    """실제 엔드포인트 완전세팅+활성 → rid(실패 0)."""
    rid = get_route(item)
    if not rid: return 0
    set_vendor_price(rid, VEN); set_prodinfo(rid, item); activate(item, rid, True)
    return rid
def active_rid(item):
    cur = RAW.cursor()
    try:
        soyo._route_setup(cur)
        cur.execute("SELECT MIN(route_id) FROM nx.plan_route_active WHERE assy_item_code=?", item.upper())
        r = cur.fetchone(); return r[0] if r and r[0] is not None else None
    finally: cur.close()
def old_active_cnt(item):
    """★대조: 옛 스킴(sourcing_route.current_flag) 기준 활성수 — 수정 전이면 항상 0(버그)."""
    cur = RAW.cursor()
    try:
        cur.execute("""SELECT COUNT(*) FROM nx.sourcing_route h WHERE ISNULL(h.current_flag,0)=1 AND ISNULL(h.route_no,1)>1
              AND UPPER(LTRIM(RTRIM(h.item_code)))=?
              AND EXISTS(SELECT 1 FROM nx.route_edges re WHERE re.route_id=h.route_id)""", item.upper())
        return int(cur.fetchone()[0])
    finally: cur.close()

# ───────── 결과 집계 ─────────
PASS = []; FAIL = []; SKIP = []
def rec(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}{('  — '+detail) if detail else ''}")
def skip(name, why):
    SKIP.append(name); print(f"  [SKIP] {name}  — {why}")

# ───────── 작동가능 품목 자동탐색(전부-제작 조립품: 현행복사→finalize→활성 완주) ─────────
print(f"몽키패치 {_patched}곳 · 실제 엔드포인트 구동(uvicorn+urllib)\n=== 작동가능 품목 탐색 ===")
VEN = str(sql1("""SELECT TOP 1 LTRIM(RTRIM(partner_code)) FROM nx.partner
    WHERE LTRIM(RTRIM(partner_code))<>'' AND LEN(LTRIM(RTRIM(partner_code)))>=4""") or
    sql1("SELECT TOP 1 LTRIM(RTRIM(partner_code)) FROM nx.partner WHERE LTRIM(RTRIM(partner_code))<>''")).strip()
cur = RAW.cursor()
cur.execute("""SELECT UPPER(LTRIM(RTRIM(b.item_code))) assy FROM nx.v_pr_bom b
   LEFT JOIN nx.item i ON UPPER(LTRIM(RTRIM(i.item_code)))=UPPER(LTRIM(RTRIM(b.mat_code)))
   WHERE ISNULL(b.except_flag,0)<>1 AND b.item_code NOT LIKE '%-S%' AND b.item_code NOT LIKE '%-J%'
   GROUP BY UPPER(LTRIM(RTRIM(b.item_code)))
   HAVING COUNT(*) BETWEEN 2 AND 6 AND SUM(CASE WHEN ISNULL(i.make_type,'') IN ('1','') THEN 0 ELSE 1 END)=0
   ORDER BY COUNT(*)""")
_seed = ["AJR74107910", "AJR74230603", "AJR73767514-1"]   # 프로브 확인 정상품목 우선(탐색 저비용)
cands = _seed + [str(r[0]).strip() for r in cur.fetchall() if str(r[0]).strip() and str(r[0]).strip() not in _seed]
cur.close()
WORK = []; _tries = 0
for it in cands:
    if len(WORK) >= 5 or _tries >= 25: break
    _tries += 1
    try:
        rid = full_setup(it)
        if rid and active_cnt(it) == 1:
            WORK.append(it); print(f"  OK {it} (완주·활성반영 rid={rid})")
    except Exception as e:
        pass
    finally:
        rollback()
# 기존 실제 R02 route(매입/사급 부품 보유 — 사용자가 등록·승인했으나 미반영 중인 실제 사례)
cur = RAW.cursor()
cur.execute("SELECT route_id, LTRIM(RTRIM(item_code)) FROM nx.sourcing_route WHERE ISNULL(route_no,1)>1 AND ISNULL(approve_flag,0)=1")
EXIST = [(int(r[0]), str(r[1]).strip()) for r in cur.fetchall()]
cur.close()
print(f"작동가능(완주) 품목 {len(WORK)}개 · 기존 실제 R02 {len(EXIST)}개 · vendor={VEN}")
if not WORK:
    print("★작동 품목 0 — 하네스 점검 필요."); RAW.rollback(); sys.exit(1)

# ───────── 품목별 시나리오 배터리(12개, 각 rollback 격리) ─────────
def battery(item):
    tag = item[:14]
    # 1. 전체활성 → 반영(NEW) + gate 없음
    try:
        rid = full_setup(item)
        rec(f"[{tag}] 전체활성→계획반영(active=1)", rid and active_cnt(item) == 1 and len(gate_bad(item)) == 0)
    finally: rollback()
    # 2. 전체활성인데 OLD스킴(current_flag)으론 미반영 = 버그 대조
    try:
        rid = full_setup(item)
        rec(f"[{tag}] NEW반영 vs OLD(current_flag) 미반영(버그대조)", active_cnt(item) == 1 and old_active_cnt(item) == 0)
    finally: rollback()
    # 3. 활성 시 plan_route_active.route_id == 그 route
    try:
        rid = full_setup(item)
        rec(f"[{tag}] 반영 route_id 일치", active_rid(item) == rid, f"active_rid={active_rid(item)} rid={rid}")
    finally: rollback()
    # 4. 구조미반영(finalize 안 함=edges 없음) → 미반영·사유'구조'
    try:
        rid = copy_route(item); approve(rid, True); set_vendor_price(rid, VEN); set_prodinfo(rid, item); activate(item, rid, True)
        bad = gate_bad(item)
        rec(f"[{tag}] 구조미반영(edges없음)→미반영", active_cnt(item) == 0)
    finally: rollback()
    # 5. 승인생략 → 업체지정 NOT_APPROVED·미반영
    try:
        rid = get_route(item, do_approve=False)
        jv = set_vendor_price(rid, VEN)
        rec(f"[{tag}] 승인생략→업체지정거부·미반영", (not jv.get("ok")) and jv.get("gate") == "NOT_APPROVED" and active_cnt(item) == 0, f"gate={jv.get('gate')}")
    finally: rollback()
    # 6. 업체·단가 생략 → 미반영
    try:
        rid = get_route(item); set_prodinfo(rid, item); activate(item, rid, True)
        rec(f"[{tag}] 업체·단가생략→미반영", active_cnt(item) == 0)
    finally: rollback()
    # 7. 생산정보 생략 → 미반영·사유'생산정보'
    try:
        rid = get_route(item); set_vendor_price(rid, VEN); activate(item, rid, True)
        bad = gate_bad(item); miss = bad and ("생산정보 미등록" in bad[0]["missing"])
        rec(f"[{tag}] 생산정보생략→미반영·사유'생산정보'", active_cnt(item) == 0 and miss, f"missing={bad[0]['missing'] if bad else '-'}")
    finally: rollback()
    # 8. 미활성(택1 안함) → 미반영
    try:
        rid = get_route(item); set_vendor_price(rid, VEN); set_prodinfo(rid, item)
        rec(f"[{tag}] 활성안함(택1미지정)→미반영", active_cnt(item) == 0)
    finally: rollback()
    # 9. 활성 후 비활성 → 미반영
    try:
        rid = full_setup(item); a1 = active_cnt(item); activate(item, rid, False)
        rec(f"[{tag}] 활성→비활성→미반영", a1 == 1 and active_cnt(item) == 0)
    finally: rollback()
    # 10. 반영 후 승인취소 → 미반영·사유'미승인'
    try:
        rid = full_setup(item); a1 = active_cnt(item); approve(rid, False); bad = gate_bad(item)
        rec(f"[{tag}] 반영→승인취소→미반영", a1 == 1 and active_cnt(item) == 0 and bad and ("미승인" in bad[0]["missing"]))
    finally: rollback()
    # 11. 업체만·단가없음(profile INCOMPLETE) → 미반영
    try:
        rid = get_route(item); jp = set_vendor_price(rid, VEN, buy=None, sagub=None); set_prodinfo(rid, item); activate(item, rid, True)
        rec(f"[{tag}] 업체만·단가없음→미반영", active_cnt(item) == 0 and (not jp.get("ok")), f"profile_gate={jp.get('gate')}")
    finally: rollback()
    # 12. 사급가(sagub_price)로 단가 지정 → 반영(단가 게이트 sagub 경로)
    try:
        rid = get_route(item); set_vendor_price(rid, VEN, buy=None, sagub=50); set_prodinfo(rid, item); activate(item, rid, True)
        rec(f"[{tag}] 사급가로 단가→반영", active_cnt(item) == 1)
    finally: rollback()

print("\n=== 품목별 시나리오 배터리(실제 엔드포인트 구동) ===")
for it in WORK:
    battery(it)

# ───────── 기존 실제 R02 route 시나리오(사용자가 실제로 겪는 미반영 사례) ─────────
print("\n=== 기존 실제 R02 route(매입/사급 부품) ===")
for rid, item in EXIST:
    tag = item[:14]
    # E1. finalize+승인+생산정보+활성 시도 → 부품별 업체 미충족(alloc VENDOR게이트) → 미반영
    try:
        jf, en = build_edges(rid, item); approve(rid, True); set_prodinfo(rid, item)
        jac = activate(item, rid, True)
        rec(f"[{tag}·기존R02] 업체(부품별)미충족→활성거부·미반영", active_cnt(item) == 0, f"alloc_gate={jac.get('gate')}")
    finally: rollback()
    # E2. edges만 만들고 활성 안 함 → 미반영(현행)
    try:
        build_edges(rid, item)
        rec(f"[{tag}·기존R02] 활성 안함→미반영(현행 diff0)", active_cnt(item) == 0)
    finally: rollback()

# ───────── 전역 시나리오 ─────────
print("\n=== 전역 시나리오 ===")
g_item = WORK[0]
# G1. pristine → 미반영(현행 diff0)
try:
    rec("[전역] 활성 R02 없음→plan_route_active 비어있음(현행 diff0)", active_cnt(g_item) == 0)
finally: rollback()
# G2. R01(route_id=0) 택1 활성 → 구조축 미반영(route_no>1만)
try:
    rid = full_setup(g_item)
    post("/api/sourcing/route/alloc/save", {"item": g_item, "rows": [
        {"route_id": 0, "is_active": 1, "alloc_ratio": 100, "apply_from": "2000-01-01"},
        {"route_id": rid, "is_active": 0, "alloc_ratio": None}]})
    rec("[전역] R01(현행) 택1 활성→구조축 미반영(route_no>1만)", active_cnt(g_item) == 0)
finally: rollback()
# G3. 택1 배타성 — R02 2개 활성 시도 → ≤1행
try:
    rid1 = full_setup(g_item)
    rid2 = get_route(g_item)
    if rid2:
        set_vendor_price(rid2, VEN); set_prodinfo(rid2, g_item); activate(g_item, rid2, True)
        rec("[전역] R02 2개 활성시도→plan_route_active ≤1행(택1)", active_cnt(g_item) <= 1)
    else:
        skip("[전역] 택1 배타성", "두번째 route 생성 실패")
finally: rollback()
# G4. 전체활성 후 전부 비활성 → 미반영
try:
    rid = full_setup(g_item); a1 = active_cnt(g_item); activate(g_item, rid, False)
    rec("[전역] 전체활성→비활성→미반영", a1 == 1 and active_cnt(g_item) == 0)
finally: rollback()

# ───────── 종료: 오염0 증명 ─────────
RAW.rollback()
after = snap()
clean = all(ROWS0.get(t) == after.get(t) for t in TABS)
diff = {t: (after.get(t), ROWS0.get(t)) for t in TABS if after.get(t) != ROWS0.get(t)}
RAW.close()

print(f"\n{'='*56}")
print(f"결과: PASS {len(PASS)} / FAIL {len(FAIL)} / SKIP {len(SKIP)}  (총 {len(PASS)+len(FAIL)+len(SKIP)} 시나리오)")
print(f"오염0: {'CLEAN' if clean else '★DIRTY '+str(diff)}")
if FAIL:
    print("실패:", FAIL)
if len(PASS) + len(FAIL) < 50:
    print(f"★경고: 실행 시나리오 {len(PASS)+len(FAIL)} < 50 (작동가능 품목 {len(WORK)}개)")
sys.exit(1 if (FAIL or not clean) else 0)
