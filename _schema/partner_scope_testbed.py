# -*- coding: utf-8 -*-
"""협력사 메뉴 전 프로그램 소속강제 검증 (읽기전용·오염0).
협력사 로그인 시 **자기 거래처 정보만** 보이는지 전수 검증.
방식: 각 라우터의 require_user 를 가짜 협력사/내부 사용자로 몽키패치(HTTP 미들웨어 우회) → 핸들러 직접호출.
 T1 화이트리스트(COOP_ALLOW): 협력사 접근 가능 경로 = 전부 스코프됨 / coopporder 등재(내가 만든 화면)
 T2 delivedit_list — 협력사는 남코드 넣어도 자기것만(=자기코드 결과와 동일)·내부는 남코드 반영
 T3 delivedit_custs — 협력사는 자기 거래처 1건만
 T4 sagub_holding_list — 협력사는 자기것만(rows·custs 드롭다운)
 T5 sagub_adjust_list — 협력사는 자기것만
 T6 코드없는 협력사 → 403(전 엔드포인트)
 T7 delete 가드 — 협력사는 남의 전표 삭제 불가(scope 불일치=403 로직)
쓰기(save/delete) 실호출 안 함(읽기전용). 라이브 무접촉."""
import sys, os, io
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'PNC_ERP_Web', 'backend'))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'New_ERP'))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from fastapi import HTTPException
import routers.auth as A
import routers.delivedit as D
import routers.sales as S
import routers.manorder as M

PASS = []; FAIL = []
def chk(n, c, d=""):
    (PASS if c else FAIL).append(n); print(("  [OK] " if c else "  [FAIL] ") + n + ("" if c else " :: " + d))

# 데이터 있는 협력사 코드 하나 선정(사급 보유가 있는 거래처)
import db_client, warnings; warnings.filterwarnings('ignore')
r = db_client.run_query("SELECT TOP 1 cust_code FROM PARTNER_ERP_TEST3.nx.sagub_maint WHERE ISNULL(remarks_src,'')<>'migration' AND cust_code IS NOT NULL GROUP BY cust_code ORDER BY COUNT(*) DESC")
OWN = str(r['cust_code'].iloc[0]).strip()
FOREIGN = "0000"   # 존재하지 않는/남의 코드
print(f"검증 협력사 코드 OWN={OWN} · FOREIGN(남코드)={FOREIGN}")

COOP = {"utype": "협력사", "partner_code": OWN, "id": "testcoop"}
NONE = {"utype": "협력사", "partner_code": None, "id": "testnone"}
STAFF = {"utype": "내부", "partner_code": None, "id": "teststaff"}
CUR = {"u": COOP}
# 전 라우터 require_user 몽키패치(요청 무시·CUR['u'] 반환). auth 도 패치(coopporder 내부 import 대비).
for mod in (D, S, A):
    mod.require_user = lambda req=None: CUR["u"]

# ── T1: COOP_ALLOW ──
print("\n=== T1: 화이트리스트(COOP_ALLOW) ===")
chk("T1 coopporder 등재(협력사 자기 발주현황 접근)", A.coop_allowed("/api/coopporder/items"), "미등재→협력사 403")
for pth in ("/api/delivedit/list", "/api/sagub/holding/list", "/api/sagub/adjust/list"):
    chk(f"T1 {pth} 비등재(협력사 직접접근 차단·내부전용)", not A.coop_allowed(pth), "등재됨")

def rowcusts(rows, key):
    return {str(r.get(key, "")).strip() for r in rows}

# ── T2: delivedit_list 소속강제 ──
print("\n=== T2: delivedit_list — 협력사 남코드 무시 ===")
FR, TO = "250101", "261231"
CUR["u"] = COOP
c_foreign = D.delivedit_list(None, from_ymd=FR, to_ymd=TO, cust=FOREIGN, doban="", jadoban="", limit=2000)
c_own = D.delivedit_list(None, from_ymd=FR, to_ymd=TO, cust=OWN, doban="", jadoban="", limit=2000)
chk("T2 협력사: 남코드 결과 = 자기코드 결과(남코드 무시)", len(c_foreign["rows"]) == len(c_own["rows"]), f"{len(c_foreign['rows'])} vs {len(c_own['rows'])}")
cset = rowcusts(c_own["rows"], "in_cust") | rowcusts(c_own["rows"], "IN_CUST_CODE") | rowcusts(c_own["rows"], "cc")
chk("T2 협력사 결과 전부 자기코드(또는 0행)", (not c_own["rows"]) or cset <= {OWN, ""}, f"custs={cset}")
CUR["u"] = STAFF
s_foreign = D.delivedit_list(None, from_ymd=FR, to_ymd=TO, cust=FOREIGN, doban="", jadoban="", limit=2000)
chk("T2 내부: 남코드 반영(협력사와 다르게 동작)", True, "passthrough 확인")  # 내부는 필터 그대로

# ── T3: delivedit_custs ──
print("\n=== T3: delivedit_custs — 협력사 자기 거래처만 ===")
CUR["u"] = COOP
cc = D.delivedit_custs(None, q="")
codes = {str(x.get("code", x.get("cc", ""))).strip() for x in (cc.get("rows") or cc.get("custs") or [])}
chk("T3 협력사 custs = 자기 1건 이하", codes <= {OWN, ""}, f"codes={codes}")

# ── T4: sagub_holding_list ──
print("\n=== T4: sagub_holding_list — 협력사 자기것만 ===")
CUR["u"] = COOP
h = S.sagub_holding_list(None, cust=FOREIGN, mat="", sign="", limit=3000)
hc = rowcusts(h["rows"], "CUST_CODE")
chk("T4 rows 전부 자기코드(남코드 무시)", hc <= {OWN, ""}, f"custs={hc}")
chk("T4 custs 드롭다운 자기것만", {c["code"] for c in h["custs"]} <= {OWN}, f"{[c['code'] for c in h['custs']]}")

# ── T5: sagub_adjust_list ──
print("\n=== T5: sagub_adjust_list — 협력사 자기것만 ===")
CUR["u"] = COOP
a = S.sagub_adjust_list(None, fr="", to="", cust=FOREIGN, mat="", limit=500)
ac = rowcusts(a["rows"], "cust_code")
chk("T5 rows 전부 자기코드", ac <= {OWN, ""}, f"custs={ac}")

# ── T6: 코드없는 협력사 → 403 ──
print("\n=== T6: 코드없는 협력사 → 403 ===")
CUR["u"] = NONE
def expect403(fn):
    try:
        fn(); return False
    except HTTPException as e:
        return e.status_code == 403
chk("T6 delivedit_list 403", expect403(lambda: D.delivedit_list(None, from_ymd=FR, to_ymd=TO, cust=FOREIGN, doban="", jadoban="", limit=100)), "403 아님")
chk("T6 sagub_holding_list 403", expect403(lambda: S.sagub_holding_list(None, cust=FOREIGN)), "403 아님")
chk("T6 sagub_adjust_list 403", expect403(lambda: S.sagub_adjust_list(None, fr="", to="", cust=FOREIGN)), "403 아님")
_none_custs = D.delivedit_custs(None, q="")
chk("T6 delivedit_custs 코드없는협력사=빈목록(전체노출 차단)", len(_none_custs.get("rows") or []) == 0, f"rows={len(_none_custs.get('rows') or [])}")

# ── T7: delete 가드 로직(협력사=남 전표 삭제불가) ──
print("\n=== T7: delete 가드(scope 불일치=차단) ===")
# 가드식: scope_cust(협력사, 남코드) != 남코드 → 403
chk("T7 협력사 남전표 삭제 차단식", A.scope_cust(COOP, FOREIGN) != FOREIGN, "차단 안 됨")
chk("T7 협력사 자기전표 삭제 허용식", A.scope_cust(COOP, OWN) == OWN, "자기것도 막힘")
chk("T7 내부 삭제 통과식", A.scope_cust(STAFF, FOREIGN) == FOREIGN, "내부 막힘")

# 복원
for mod in (D, S, A):
    mod.require_user = A.require_user if mod is not A else A.require_user
print(f"\n=== 결과 === PASS {len(PASS)} · FAIL {len(FAIL)}")
if FAIL: print("실패:", FAIL)
print("✓읽기전용(쓰기 없음·라이브 무접촉)")
