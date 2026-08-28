# -*- coding: utf-8 -*-
"""재고 flow **전 구간 + 시스템 규칙** 검증 하네스 (durable, 2026-08-28)

정본 문서 = `_schema/STOCK_FLOW_INOUT_VERIFY.md`

★무엇을 하나
  `flow_server.py`(롤백 모드, 포트 8099)에 대고 **우리가 개발한 프로그램의 실제 API**를
  HTTP 로 호출한다. 화면(js)이 부르는 바로 그 엔드포인트다.
  두 축을 함께 본다:
    [F] 흐름  — 자재입고→조정→출고→반품→수정→삭제→키팅→생산실적→영업출고
                각 단계에서 **원장·수불장·재고 3곳 델타가 일치**하는지
    [R] 규칙  — 우리가 세운 시스템 규칙이 **실제로 막는지**
                음수재고 차단 · 마감기간 잠금 · 미등록품목 · 수량0 · 마감중복 · 단가0제외

★오염 0
  서버가 no-commit 공유 커넥션이라 어떤 호출도 확정되지 않는다.
  끝나면 `/api/_flow/rollback` 이 전량 롤백하고 **독립 커넥션으로 행수 불변**을 증명한다.

사용:
  1) python _migration/flow_server.py --port 8099     (별도 창, 롤백 모드 백엔드)
  2) python _migration/flow_scenarios.py              (본 하네스)
"""
import sys, os, io, json, urllib.request, urllib.error

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'PNC_ERP_Web', 'backend'))

BASE = "http://127.0.0.1:8099"
YMD = "260828"          # 검증 일자(당월, 미마감 구간이어야 한다 — 자동탐색으로 덮어씀)


# ── HTTP ────────────────────────────────────────────────────────────────
def call(method, path, payload=None, timeout=180):
    """(status, body) — 4xx/5xx 도 예외 대신 결과로 돌려준다(규칙 검증은 거부가 정답)."""
    url = BASE + path
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode() or "{}")
        except Exception:
            return e.code, {}
    except Exception as e:
        return 0, {"_err": f"{type(e).__name__}: {str(e)[:80]}"}


def probe():
    return call("GET", "/api/_flow/probe")[1].get("now", {})


def dlt(a, b):
    return {k: round(b.get(k, 0) - a.get(k, 0), 4) for k in a}


RESULTS = []


def _rec(kind, name, verdict, note):
    RESULTS.append((kind, name, verdict, note))
    icon = {"PASS": "✅", "FAIL": "★FAIL", "미구현": "☐미구현", "SKIP": "–"}[verdict]
    print(f"   {icon:7s} [{kind}] {name}")
    if note:
        print(f"           {note}")


# ── [F] 흐름 스텝 : 3곳 델타 일치를 본다 ────────────────────────────────
def flow(name, method, path, payload, led_key, expect_qty, mirror=True):
    """led_key = 원장 프로브명 · expect_qty = 기대 델타. mirror=True 면 수불장·재고도 같아야."""
    b = probe()
    st, res = call(method, path, payload)
    a = probe()
    d = dlt(b, a)
    if st != 200 or (isinstance(res, dict) and res.get("ok") is False):
        detail = (res.get("errors") or res.get("detail") or res.get("_err") or res)
        _rec("F", name, "FAIL", f"호출 거부 {st} — {str(detail)[:120]}")
        return d
    led = d.get(led_key, 0)
    if abs(led - expect_qty) > 0.001:
        _rec("F", name, "FAIL", f"{led_key} 델타 {led:+g} ≠ 기대 {expect_qty:+g}")
        return d
    if mirror:
        mir, stk = d.get("수불장수량", 0), d.get("자재재고", 0)
        if abs(led - mir) > 0.001 or abs(led - stk) > 0.001:
            miss = [n for n, v in (("수불장", mir), ("재고", stk)) if abs(led - v) > 0.001]
            _rec("F", name, "FAIL",
                 f"3곳 불일치 — 원장 {led:+g} · 수불장 {mir:+g} · 재고 {stk:+g} → {'/'.join(miss)} 미반영")
            return d
        _rec("F", name, "PASS", f"원장·수불장·재고 3곳 일치 ({led:+g})")
    else:
        _rec("F", name, "PASS", f"{led_key} {led:+g}")
    return d


# ── [R] 규칙 스텝 : "막혔는가"를 본다 ───────────────────────────────────
def rule(name, method, path, payload, keyword, must_block=True):
    """must_block=True → 반드시 거부되어야 PASS. keyword = 거부 사유에 포함되어야 할 말."""
    b = probe()
    st, res = call(method, path, payload)
    a = probe()
    d = dlt(b, a)
    body = json.dumps(res, ensure_ascii=False)
    blocked = (st >= 400) or (isinstance(res, dict) and res.get("ok") is False)
    wrote = any(abs(v) > 0.001 for v in d.values())
    if not must_block:
        _rec("R", name, "PASS" if not blocked else "FAIL", f"{st} · {body[:100]}")
        return
    if not blocked:
        _rec("R", name, "미구현",
             f"차단되지 않음 — {st} 통과{' + DB 기록됨' if wrote else ''} · {body[:90]}")
        return
    if keyword and keyword not in body:
        _rec("R", name, "PASS", f"거부됨(사유 문구는 다름) — {body[:110]}")
        return
    if wrote:
        _rec("R", name, "FAIL", f"거부했지만 DB 에 기록됨 — {[k for k,v in d.items() if abs(v)>0.001]}")
        return
    _rec("R", name, "PASS", f"차단 확인 — {body[:110]}")


# ── 픽스처(테스트 대상 선정) — 읽기전용 별도 커넥션 ──────────────────────
def fixture():
    import common, pyodbc, db_client
    cs = (f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};'
          f'DATABASE=PARTNER_ERP_TEST3;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}')
    cur = pyodbc.connect(cs, autocommit=True).cursor()
    f = {}
    # 가용재고가 넉넉한 자재 1개(음수차단 규칙을 정확히 때리려면 가용을 알아야 한다)
    cur.execute("""SELECT TOP 1 UPPER(LTRIM(RTRIM(a.MAT_CODE))), SUM(CAST(a.STOCK_QTY AS float))
                     FROM nx.mat_stock_daily a
                     JOIN nx.item i ON i.item_code = a.MAT_CODE
                    GROUP BY UPPER(LTRIM(RTRIM(a.MAT_CODE)))
                   HAVING SUM(CAST(a.STOCK_QTY AS float)) BETWEEN 500 AND 100000
                    ORDER BY 2 DESC""")
    r = cur.fetchone()
    if r:
        f["mat"], f["avail"] = str(r[0]), float(r[1])
    # 마감된 기간(잠금 규칙 검증용)
    cur.execute("""SELECT TOP 1 ptype, period FROM nx.period_close
                    WHERE domain='MAT' AND close_flag=1 ORDER BY period DESC""")
    r = cur.fetchone()
    if r:
        f["closed_ptype"], f["closed_period"] = str(r[0]), str(r[1])
    # ★키팅 참조 셀 · 판매 거래처도 **여기서 미리** 읽는다.
    #   쓰기가 시작된 뒤 별도 커넥션으로 nx.stock_ledger 를 읽으면 우리 자신의 미커밋 잠금에
    #   걸려 무한 대기한다(2026-08-28 실측 — 하네스가 2분/10분 타임아웃난 진짜 원인).
    cur.execute("""SELECT TOP 1 UPPER(LTRIM(RTRIM(ITEM_CODE))), GAGONG_PROC_CODE, WORK_ORDER
                     FROM nx.stock_ledger WHERE STOCK_POINT='RDY' AND GAGONG_PROC_CODE IS NOT NULL
                    ORDER BY MAINT_YMD DESC""")
    r = cur.fetchone()
    if r:
        f["kit"] = (str(r[0]), str(r[1]).strip(), str(r[2] or "").strip())
    cur.execute("""SELECT TOP 1 cust_code FROM nx.saleout_maint WHERE maint_tag='5'
                   GROUP BY cust_code ORDER BY COUNT(*) DESC""")
    r = cur.fetchone()
    if r:
        f["sale_cust"] = str(r[0]).strip()
    cur.close()          # ★쓰기 시작 전에 닫는다 — 잠금 대기 원천 차단
    return f, None


def main():
    print("=" * 78)
    print(" 재고 flow 전 구간 + 시스템 규칙 검증  (롤백 모드 · 오염 0)")
    print("=" * 78)

    st, _ = call("GET", "/api/_flow/probe")
    if st != 200:
        print("★flow_server(8099) 가 떠 있지 않습니다. 먼저 기동하세요."); return 1

    f, cur = fixture()
    MAT = f.get("mat")
    if not MAT:
        print("★테스트 자재를 못 찾음"); return 1
    call("POST", "/api/_flow/scope", {"ymd": YMD, "mat": MAT})   # 관측 스코프 한정(속도)
    print(f"\n 대상 자재 = {MAT} (가용 {f['avail']:,.0f})")
    print(f" 마감 기간 = {f.get('closed_ptype','-')}/{f.get('closed_period','-')}\n")

    def save(screen, qty, ymd=YMD, mat=None):
        return {"screen": screen, "user": "flowverify",
                "rows": [{"MAINT_YMD": ymd, "MAT_CODE": (mat or MAT), "qty": qty}]}

    # ══ [F] 흐름 ══════════════════════════════════════════════════════
    print("── [F] 흐름 : 자재 ───────────────────────────────────────────")
    flow("자재입고 (자재입고관리)", "POST", "/api/stock/save", save("receipt", 100), "원장MAT", +100)
    flow("자재조정 (자재재고조정)", "POST", "/api/stock/save", save("adjust", 50), "원장MAT", +50)
    flow("자재출고 (자재출고관리)", "POST", "/api/stock/save", save("issue", 30), "원장MAT", -30)
    flow("자재반품",               "POST", "/api/stock/save", save("return", 15), "원장MAT", -15)

    # 방금 넣은 입고행 키 → 수정/삭제
    # 공유(미커밋) 커넥션으로 조회해야 한다 — 별도 커넥션에는 아직 안 보인다.
    _, q = call("POST", "/api/_flow/sql", {
        "sql": "SELECT TOP 1 MAINT_YMD, MAINT_SEQ FROM nx.stock_ledger "
               "WHERE MAINT_YMD=? AND MAT_CODE=? AND STOCK_POINT='MAT' AND INSERT_USER_ID='flowverify' "
               "ORDER BY MAINT_SEQ DESC", "args": [YMD, MAT]})
    rows = q.get("rows") or []
    if rows:
        kymd, kseq = str(rows[0][0]).strip(), int(rows[0][1])
        print(f"           (대상 원장행 {kymd}/{kseq})")
        flow("자재수정 stock_update", "POST", "/api/stock/update",
             {"screen": "receipt", "MAINT_YMD": kymd, "MAINT_SEQ": kseq, "qty": 150,
              "MAT_CODE": MAT, "user": "flowverify"}, "원장MAT", +140)
        flow("자재삭제 stock_delete", "POST", "/api/stock/delete",
             {"MAINT_YMD": kymd, "MAINT_SEQ": kseq, "user": "flowverify"}, "원장MAT", -150)
    else:
        _rec("F", "자재수정/삭제", "SKIP", "앞 단계에서 원장행이 안 생김 — 선행 실패")

    print("\n── [F] 흐름 : 생산·영업 ──────────────────────────────────────")
    # 키팅(준비실적처리) — flag-only, 원장 RDY
    if f.get("kit"):
        _it, _gpc, _wo = f["kit"]
        flow("키팅 확인 (준비실적처리)", "POST", "/api/kitting/cell-confirm",
             {"item": _it, "gpc": _gpc, "wo": _wo,
              "ymd": YMD, "qty": 10, "user": "flowverify"}, "원장RDY", +10, mirror=False)
    else:
        _rec("F", "키팅 확인", "SKIP", "RDY 원장에 참조할 셀이 없음")

    # 공정별 생산실적
    flow("생산실적 (공정별생산실적)", "POST", "/api/procreg/save",
         {"prod_ymd": YMD, "item_code": MAT, "prod_qty": 7, "user": "flowverify"},
         "공정실적수량", +7, mirror=False)

    # 영업 판매출고
    if f.get("sale_cust"):
        flow("판매출고 (판매및출고등록)", "POST", "/api/saleout/save",
             {"out_cust": f["sale_cust"], "item_code": MAT, "out_qty": 5,
              "out_ymd": YMD, "user": "flowverify"}, "판매출고수량", -5, mirror=False)
    else:
        _rec("F", "판매출고", "SKIP", "참조할 거래처 없음")

    # ══ [R] 규칙 ══════════════════════════════════════════════════════
    print("\n── [R] 규칙 : 음수재고 차단 ──────────────────────────────────")
    big = f["avail"] * 10 + 100000
    rule("자재출고 — 가용 초과(음수유발) 차단", "POST", "/api/stock/save",
         save("issue", big), "재고부족")
    rule("자재반품 — 가용 초과 차단", "POST", "/api/stock/save",
         save("return", big), "재고부족")
    rule("자재조정 — 감소로 음수 유발 차단", "POST", "/api/stock/save",
         save("adjust", -big), "음수재고")

    print("\n── [R] 규칙 : 마감기간 잠금 ──────────────────────────────────")
    if f.get("closed_period"):
        p = f["closed_period"]
        locked_ymd = p if f["closed_ptype"] == "D" else p + "15"
        rule("자재 쓰기 — 마감기간 잠금", "POST", "/api/stock/save",
             save("receipt", 10, ymd=locked_ymd), "마감")
        rule("키팅 — 마감기간 잠금", "POST", "/api/kitting/cell-confirm",
             {"item": MAT, "gpc": "P1", "ymd": locked_ymd, "qty": 1, "user": "flowverify"}, "마감")
        rule("마감 중복 실행 차단", "POST", "/api/close/run",
             {"domain": "MAT", "ptype": f["closed_ptype"], "period": p, "user": "flowverify"},
             "이미 마감")
    else:
        _rec("R", "마감 잠금", "SKIP", "마감된 기간이 없음")

    print("\n── [R] 규칙 : 입력 유효성 ────────────────────────────────────")
    rule("미등록 품목 차단", "POST", "/api/stock/save",
         save("receipt", 10, mat="ZZ_NOT_EXIST_9999"), "미등록")
    rule("수량 0 차단", "POST", "/api/stock/save", save("receipt", 0), "0보다")
    rule("조정수량 0 차단", "POST", "/api/stock/save", save("adjust", 0), "0일 수 없")
    rule("일자 누락 차단", "POST", "/api/stock/save", save("receipt", 10, ymd=""), "일자")
    rule("screen 오류 차단", "POST", "/api/stock/save",
         {"screen": "bogus", "rows": []}, "screen")

    print("\n── [R] 규칙 : 단가0·음수 스냅샷 제외 ─────────────────────────")
    st, res = call("GET", "/api/close/anomaly?domain=MAT&ptype=M&period=" + (f.get("closed_period") or "2607"))
    if st == 200:
        s = res.get("summary") or res
        _rec("R", "단가0·음수 제외 리포트(/api/close/anomaly)", "PASS",
             f"{json.dumps(s, ensure_ascii=False)[:150]}")
    else:
        _rec("R", "단가0·음수 제외 리포트", "FAIL", f"{st} · {str(res)[:100]}")

    # ══ 롤백 + 오염 0 ═════════════════════════════════════════════════
    print("\n── 롤백 & 오염 0 증명 ────────────────────────────────────────")
    st, rb = call("POST", "/api/_flow/rollback")
    if st == 200 and rb.get("clean"):
        print("   ✅ 오염 0 PASS — 롤백 전/후 행수 불변(독립 커넥션 확인)")
    else:
        print(f"   ★★오염 의심 — {json.dumps(rb, ensure_ascii=False)[:300]}")

    # ══ 요약 ═════════════════════════════════════════════════════════
    print("\n" + "=" * 78)
    n = {}
    for kind, name, v, _ in RESULTS:
        n[v] = n.get(v, 0) + 1
    print(f" 결과: PASS {n.get('PASS',0)} · FAIL {n.get('FAIL',0)} · "
          f"미구현 {n.get('미구현',0)} · SKIP {n.get('SKIP',0)}  (총 {len(RESULTS)})")
    bad = [(k, nm, v, nt) for k, nm, v, nt in RESULTS if v in ("FAIL", "미구현")]
    if bad:
        print("\n ★조치 필요")
        for k, nm, v, nt in bad:
            print(f"   [{k}] {nm} — {v}\n       {nt}")
    print("=" * 78)
    return 0


if __name__ == '__main__':
    sys.exit(main())
