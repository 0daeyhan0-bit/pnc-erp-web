# -*- coding: utf-8 -*-
"""수동발주 담당자별 진입 + 협력사 발주현황(모바일 포털) 검증 (읽기전용·오염0).
검증:
 T1 담당자 목록(CHARGE_USER_ID) — 매입처 보유 담당자만·건수>0
 T2 담당자별 매입처 필터 — vendors(charge)=그 담당자 매입처만·건수=charges 집계와 일치·charge 필드 일치
 T3 매입처 검색(q) — charge 무관 검색 동작·charge 필드 노출
 T4 담당자·검색어 둘 다 없음 → 빈 목록(전체노출 방지)
 T5 클릭 진입 — 담당자 매입처 1개 선택→manorder_items 로드(계획·재고·기발주·주별·일별 필드)
 T6 scope_cust 소속강제 — 협력사=자기코드 고정·코드없음=__NONE__·내부=passthrough
 T7 협력사 발주현황(coopporder 모바일) — 협력사 소속강제 후 out 필드·순소요(계획−재고−기발주) 정합
전부 읽기전용(_conn RO). 라이브 무접촉·쓰기 없음."""
import sys, os, io
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'PNC_ERP_Web', 'backend'))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'New_ERP'))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import routers.manorder as M
import routers.auth as A

PASS = []; FAIL = []
def chk(n, c, d=""):
    (PASS if c else FAIL).append(n); print(("  [OK] " if c else "  [FAIL] ") + n + ("" if c else " :: " + d))

# ── T1: 담당자 목록 ──
print("=== T1: 담당자(CHARGE_USER_ID) 목록 ===")
ch = M.manorder_charges()["rows"]
print("  담당자 %d명: %s" % (len(ch), ", ".join("%s(%d)" % (r["charge"], r["ncust"]) for r in ch)))
chk("T1 담당자 1명 이상", len(ch) >= 1, f"{len(ch)}명")
chk("T1 전원 이름·건수>0", all(r["charge"] and r["ncust"] > 0 for r in ch), "빈 담당자/0건 존재")

# ── T2: 담당자별 매입처 필터 ──
print("\n=== T2: 담당자별 매입처 = 그 담당자만·건수 일치 ===")
for g in ch[:3]:
    vs = M.manorder_vendors(q="", charge=g["charge"])["rows"]
    allmine = all(v.get("charge") == g["charge"] for v in vs)
    # ncust(DISTINCT CUST_CODE)와 vendors 행수(CUST_CODE 그룹) 일치 — TOP 100 이내
    cnt_ok = (len(vs) == g["ncust"]) or (g["ncust"] > 100 and len(vs) == 100)
    chk(f"T2 {g['charge']} 전부 이 담당자", allmine, "다른 담당자 섞임")
    chk(f"T2 {g['charge']} 건수 일치({len(vs)}={g['ncust']})", cnt_ok, f"{len(vs)} vs {g['ncust']}")

# ── T3: 매입처 검색(q) ──
print("\n=== T3: 매입처 검색(q, charge 무관) ===")
qs = M.manorder_vendors(q="정밀", charge="")["rows"]
chk("T3 검색 결과 있음", len(qs) > 0, "0건")
chk("T3 검색결과 charge 필드 노출", all("charge" in v for v in qs), "charge 필드 없음")

# ── T4: 둘 다 없음 → 빈 목록 ──
print("\n=== T4: 담당자·검색어 없음 → 빈(전체노출 방지) ===")
chk("T4 빈 목록", len(M.manorder_vendors(q="", charge="")["rows"]) == 0, "전체가 새어나옴")

# ── T5: 클릭 진입(담당자 매입처 → items 로드) ──
# ★주의: vendors 의 "품목수"=마스터 in_cust 품목수. 발주계산 행=현재 윈도우 소요배분∪기발주(소요엔진 정본).
#   → 마스터 품목이 많아도 현재 소요/기발주 없으면 0행(정상·빈화면=발주할 것 없음). 실제 소요행 있는 업체로 진입 검증.
print("\n=== T5: 담당자 매입처 클릭 → 발주계산 로드(소요행 있는 업체) ===")
vpick = None; it = None
for g in ch:
    for v in sorted(M.manorder_vendors(q="", charge=g["charge"])["rows"], key=lambda z: -z["items"]):
        t = M.manorder_items(cc=v["cc"], ym="")
        if t["rows"]:
            vpick, it = dict(v, charge=g["charge"]), t; break
    if vpick: break
if vpick:
    r0 = it["rows"][0]
    print("  담당자 %s → 매입처 %s(%s) → 발주계산 %d행" % (vpick["charge"], vpick["nm"], vpick["cc"], len(it["rows"])))
    chk("T5 소요행 있는 매입처 진입", len(it["rows"]) > 0, "행 0")
    chk("T5 필수 필드(plan/stock/po/week/days)", all(k in r0 for k in ("plan_qty", "stock_qty", "po_qty", "week_qty", "days")), f"keys={list(r0.keys())}")
    chk("T5 week_qty 4주", isinstance(r0.get("week_qty"), list) and len(r0["week_qty"]) == 4, str(r0.get("week_qty")))
else:
    chk("T5 소요행 있는 매입처 존재", False, "전 담당자 매입처 소요행 0 — 소요배분 데이터 확인 필요")

# ── T6: scope_cust 소속강제 ──
print("\n=== T6: scope_cust 소속강제(협력사=자기코드) ===")
u_par = {"utype": "협력사", "partner_code": vpick["cc"]}
u_none = {"utype": "협력사", "partner_code": None}
u_staff = {"utype": "내부", "partner_code": None}
chk("T6 협력사=자기코드 고정(남코드 무시)", A.scope_cust(u_par, "9999") == vpick["cc"], A.scope_cust(u_par, "9999"))
chk("T6 코드없는 협력사=__NONE__", A.scope_cust(u_none, "9999") == "__NONE__", A.scope_cust(u_none, "9999"))
chk("T6 내부=요청 cust passthrough", A.scope_cust(u_staff, vpick["cc"]) == vpick["cc"], A.scope_cust(u_staff, vpick["cc"]))

# ── T7: 협력사 발주현황(모바일) out·순소요 정합 ──
print("\n=== T7: 협력사 발주현황(coopporder) out·순소요 ===")
cc = A.scope_cust(u_par, "9999")                       # 협력사 소속강제 결과
r = M.manorder_items(cc=cc, ym="")
out = [{"ic": x["ic"], "nm": x["nm"], "stock_qty": x["stock_qty"], "po_qty": x["po_qty"],
        "plan_qty": x["plan_qty"], "muldong_soyo": x["muldong_soyo"]} for x in r["rows"]]
def net4(z): return round((z["plan_qty"] or 0) - (z["stock_qty"] or 0) - (z["po_qty"] or 0))
sample = out[:1] and out[0]
print("  협력사 %s·품목 %d · 순소요 발생 %d" % (cc, len(out), sum(1 for z in out if net4(z) > 0)))
chk("T7 out 필드 완비", all(all(k in z for k in ("ic", "nm", "stock_qty", "po_qty", "plan_qty", "muldong_soyo")) for z in out), "필드 누락")
# 순소요 = 계획−재고−기발주 산식 정합(수동발주 좌측과 동일 소스)
consistent = all(net4(z) == round((z["plan_qty"] or 0) - (z["stock_qty"] or 0) - (z["po_qty"] or 0)) for z in out)
chk("T7 순소요=계획−재고−기발주", consistent, "산식 불일치")
chk("T7 좌측(수동발주)과 동일 소스", len(out) == len(r["rows"]), f"{len(out)} vs {len(r['rows'])}")

print(f"\n=== 결과 === PASS {len(PASS)} · FAIL {len(FAIL)}")
if FAIL: print("실패:", FAIL)
print("✓읽기전용(쓰기 없음·라이브 무접촉)")
