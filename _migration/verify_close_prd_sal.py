# -*- coding: utf-8 -*-
"""C2 검증 — 생산(PRD)·영업(SAL) 마감 스냅샷.
   게이트1 스냅샷 == 정본 recipe(전수 diff0) / 게이트2 정본 단품함수 교차검증
   게이트3 원장 불변식 / 게이트4 음수재고
   ★쓰기 = nx.period_close / nx.stock_snapshot 만."""
import sys, io, json, urllib.request
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, r"d:\피앤씨인더스트리\100_AI_AGENT\Projects\_wt_close\PNC_ERP_Web\backend")
from common import _nx, _conn, _prod_avail, _finished_avail
from live_api import _prodstock, salesstock

API = "http://localhost:8012"
YM, D1, D2 = "2607", "260701", "260731"


def post(path, body):
    rq = urllib.request.Request(API + path, data=json.dumps(body).encode(),
                                headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(rq, timeout=900) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        try:    return e.code, json.loads(e.read().decode("utf-8", "replace"))
        except Exception: return e.code, {"detail": "(non-json)"}


cn = _nx(); cur = cn.cursor()
lc = _conn().cursor()

print("=== 사전 정리(멱등) ===")
for dom in ("PRD", "SAL"):
    cur.execute("DELETE FROM nx.period_close WHERE domain=? AND ptype='M' AND period=?", dom, YM)
cn.commit()
print("   PRD/SAL 2607 잠금 초기화")

print("")
print("=== 마감 실행 ===")
for dom in ("PRD", "SAL"):
    st, js = post("/api/close/run", {"domain": dom, "ptype": "M", "period": YM, "user": "C2검증"})
    print(f"   {dom}: {st} · {js.get('msg') or js.get('detail')} · 기준 {js.get('snapshot_asof')}")

print("")
print("=== 게이트1 — 스냅샷 == 정본 recipe (전수) ===")


def gate1(dom, recipe_rows, keyfn, qtyfn):
    cur.execute("""SELECT UPPER(LTRIM(RTRIM(item_code))), ISNULL(loc,''), stock_qty
                     FROM nx.stock_snapshot WHERE domain=? AND ptype='M' AND period=?""", dom, YM)
    snap = {(r[0], r[1]): float(r[2]) for r in cur.fetchall()}
    exp = {}
    for r in recipe_rows:
        q = qtyfn(r); k = keyfn(r)
        if abs(q) < 1e-9 or not k[0]:
            continue      # 잔량 0 제외 + 빈 품번 제외(키가 없어 확정 불가 = 레거시 데이터 흠)
        exp[k] = exp.get(k, 0.0) + q
    common = set(snap) & set(exp)
    ok = sum(1 for k in common if abs(snap[k] - exp[k]) < 0.001)
    print(f"   {dom}: 스냅 {len(snap):,} · recipe(0·빈품번 제외) {len(exp):,} · 공통 {len(common):,}"
          f" · 수량일치 {ok:,} · 스냅만 {len(set(snap)-set(exp))} · recipe만 {len(set(exp)-set(snap))}")
    verdict = (len(snap) == len(exp) == len(common) == ok)
    print(f"      → {'diff0 PASS' if verdict else '★FAIL'}")
    for k in list(set(snap) ^ set(exp))[:5]:
        print(f"        차이 {k}: 스냅 {snap.get(k)} · recipe {exp.get(k)}")
    return verdict


pr = _prodstock(YM, frm=D1, to=D2)
g1p = gate1("PRD", pr,
            lambda r: (str(r["cd"]).strip().upper(),
                       "" if str(r.get("stage")) == "GAGONG" else str(r.get("loc") or "")),
            lambda r: float(r.get("qty") or 0))
sa = (salesstock(dfrom=D1, dto=D2, source="live", zero="1").get("rows") or [])
g1s = gate1("SAL", sa,
            lambda r: (str(r["cd"]).strip().upper(), ""),
            lambda r: float(r.get("qty") or 0))

print("")
print("=== 게이트2 — 정본 단품함수 교차검증(별도 SQL 경로) ===")
# ★레거시 PR_T_MONTH_STOCK_WH · SA_T_MONTH_STOCK 은 2502 한 달치뿐(실측) — 레거시가 생산·제품
#   월마감을 그 뒤로 하지 않아 대조할 오라클이 없다. 그래서 독립 검증 = 게이팅 캐논 §4-C 가
#   정본으로 지정한 단품 함수(별도 SQL 경로, 2026-08-19 레거시 480/040 diff0 검증)로 표본 교차대조.


def gate2x(dom, fn, n=60):
    cur.execute(f"""SELECT TOP {n} UPPER(LTRIM(RTRIM(item_code))), stock_qty
                      FROM nx.stock_snapshot WHERE domain=? AND ptype='M' AND period=? AND loc=''
                     ORDER BY ABS(stock_qty) DESC""", dom, YM)
    rows = cur.fetchall()
    ok = bad = 0; samples = []
    for it, q in rows:
        v = fn(lc, it, asof=D2) if dom == "SAL" else fn(lc, it, line="P0001", asof=D2)
        if abs(float(q) - float(v)) < 0.001:
            ok += 1
        else:
            bad += 1
            if len(samples) < 5: samples.append((it, float(q), float(v)))
    print(f"   {dom}: 표본 {len(rows)}품목(잔량 큰 순) · 일치 {ok} · 불일치 {bad}"
          f" → {'diff0 PASS' if bad == 0 else '★차이'}")
    for it, a, b in samples:
        print(f"        {it:24s} 스냅 {a:12,.1f} · 단품함수 {b:12,.1f}")
    return bad == 0


g2p = gate2x("PRD", _prod_avail)
g2s = gate2x("SAL", _finished_avail)

print("")
print("=== 게이트3 — 불변식 기초+입−출+조정 = 기말 (recipe 전수) ===")
# ★함정: 두 화면의 조정(adj) 부호 규약이 반대다(레거시 원본이 그렇고, 각각 diff0 검증본).
#     생산 480 : qty = 기초 + 입 − 출 + 조정   (live_api._prodstock  SUM(basic)+SUM(inq)-SUM(outq)+SUM(etc))
#     제품 040 : qty = 기초 + 입 − 조정 − 출   (live_api.salesstock  sum(basic+inq-etc-outq))
#   같은 식으로 검사하면 SAL 이 19건 위반으로 오탐된다(2026-08-27 실제 겪음).
SIGN = {"PRD": +1, "SAL": -1}
for nm, rows in (("PRD", pr), ("SAL", sa)):
    sg = SIGN[nm]
    bad = [r for r in rows
           if abs((float(r.get("basic") or 0) + float(r.get("inq") or 0)
                   - float(r.get("outq") or 0) + sg * float(r.get("adj") or 0))
                  - float(r.get("qty") or 0)) > 0.001]
    print(f"   {nm}: {len(rows):,}행 중 불변식 위반 {len(bad)}건"
          f" (규약 조정부호 {'+' if sg > 0 else '−'}) → {'PASS' if not bad else '★FAIL'}")

print("")
print("=== 게이트4 — 확정 스냅샷 음수재고 ===")
for dom in ("PRD", "SAL"):
    cur.execute("""SELECT COUNT(*), ISNULL(SUM(CASE WHEN stock_qty<0 THEN 1 ELSE 0 END),0)
                     FROM nx.stock_snapshot WHERE domain=? AND ptype='M' AND period=?""", dom, YM)
    tot, neg = cur.fetchone()
    print(f"   {dom}: {tot:,}품목 중 음수 {neg}건" + ("" if not neg else "  ※실재고이므로 유지(대표 확정)"))

print("")
print("=== 확정 스냅샷 현황 ===")
cur.execute("""SELECT domain, ptype, COUNT(DISTINCT period), COUNT(*)
                 FROM nx.stock_snapshot GROUP BY domain, ptype ORDER BY domain, ptype""")
for r in cur.fetchall():
    print(f"   {r[0]} {r[1]}: 기간 {r[2]}개 · {r[3]:,}행")

print("")
print(f"종합 — 게이트1 PRD {'PASS' if g1p else 'FAIL'} / SAL {'PASS' if g1s else 'FAIL'}"
      f" · 게이트2 PRD {'PASS' if g2p else '차이'} / SAL {'PASS' if g2s else '차이'}")
cn.close()
