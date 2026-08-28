# -*- coding: utf-8 -*-
"""흐름 TestBed — **실행기** (보통은 이 파일을 고칠 일이 없다)

정본 문서 = `_schema/FLOW_TESTBED.md`
케이스 정의 = `_migration/flow_cases.py`  ← **자기 프로그램은 여기에 추가**

무엇을 하나
  `flow_server.py`(롤백 모드, 기본 8099)에 대고 **우리가 개발한 프로그램의 실제 API** 를
  HTTP 로 호출한다. 화면(js)이 부르는 바로 그 엔드포인트다.
    [F] 흐름 — 값이 원장·수불장·재고 **3곳에 같은 값으로** 적히는지
    [R] 규칙 — 우리가 세운 규칙이 **실제로 막는지**(음수·마감·권한·유효성)

오염 0
  서버가 no-commit 공유 커넥션이라 어떤 호출도 확정되지 않는다.
  끝나면 `/api/_flow/rollback` 이 전량 롤백하고 **기동시점 행수와 대조해 증명**한다.

사용
  1) python _migration/flow_server.py --port 8099      (창 1 · 롤백 모드 백엔드)
  2) python _migration/flow_scenarios.py               (창 2 · 전체 실행)
     python _migration/flow_scenarios.py --list        케이스 목록만
     python _migration/flow_scenarios.py --only 키팅   이름에 '키팅' 포함만
     python _migration/flow_scenarios.py --kind R      규칙만
     python _migration/flow_scenarios.py --port 8098
"""
import sys, os, io, json, argparse, urllib.request, urllib.error

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, '..', 'PNC_ERP_Web', 'backend'))

import flow_cases as FC

AP = argparse.ArgumentParser()
AP.add_argument('--port', type=int, default=8099)
AP.add_argument('--only', default='')
AP.add_argument('--kind', default='', choices=['', 'F', 'R'])
AP.add_argument('--list', action='store_true')
ARG = AP.parse_args()
BASE = f"http://127.0.0.1:{ARG.port}"
RESULTS = []


def call(method, path, payload=None, timeout=600):
    """(status, body) — 4xx/5xx 도 예외 대신 결과로 (규칙 검증은 '거부'가 정답)."""
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method,
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
        return 0, {"_err": f"{type(e).__name__}: {str(e)[:90]}"}


def probe():
    return call("GET", "/api/_flow/probe")[1].get("now", {})


def rec(kind, name, verdict, note=""):
    RESULTS.append((kind, name, verdict, note))
    icon = {"PASS": "✅", "FAIL": "★FAIL", "미구현": "☐미구현", "SKIP": "–"}[verdict]
    print(f"   {icon:7s} [{kind}] {name}")
    if note:
        print(f"           {note}")


def body_of(c, ctx):
    b = c.get("body")
    return b(ctx) if callable(b) else b


def path_of(c, ctx):
    p = c.get("path")
    return p(ctx) if callable(p) else p


# ── 픽스처 : 쓰기 시작 **전에** 전부 읽고 커서를 닫는다 ─────────────────
def fixture():
    import common, pyodbc, db_client
    cs = (f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};'
          f'DATABASE=PARTNER_ERP_TEST3;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}')
    cn = pyodbc.connect(cs, autocommit=True); cur = cn.cursor()
    ctx = {}
    for key, sql, apply_ in FC.FIXTURES:
        try:
            cur.execute(sql); r = cur.fetchone()
            if r:
                apply_(ctx, r)
        except Exception as e:
            print(f"   ⚠ 픽스처 {key} 실패: {str(e)[:80]}")
    cur.close(); cn.close()      # ★쓰기 전에 닫는다 — 미커밋 잠금 대기 원천 차단
    return ctx


def run_flow(c, ctx):
    b = probe()
    st, res = call(c["method"], path_of(c, ctx), body_of(c, ctx))
    a = probe()
    d = {k: round(a.get(k, 0) - b.get(k, 0), 4) for k in b}
    if st != 200 or (isinstance(res, dict) and res.get("ok") is False):
        detail = res.get("errors") or res.get("detail") or res.get("_err") or res
        rec("F", c["name"], "FAIL", f"호출 거부 {st} — {str(detail)[:130]}"); return
    led = d.get(c["probe"], 0)
    if abs(led - c["delta"]) > 0.001:
        rec("F", c["name"], "FAIL", f"{c['probe']} 델타 {led:+g} ≠ 기대 {c['delta']:+g}"); return
    if c.get("mirror"):
        mir, stk = d.get("수불장수량", 0), d.get("자재재고", 0)
        if abs(led - mir) > 0.001 or abs(led - stk) > 0.001:
            miss = [n for n, v in (("수불장", mir), ("재고", stk)) if abs(led - v) > 0.001]
            rec("F", c["name"], "FAIL",
                f"3곳 불일치 — 원장 {led:+g} · 수불장 {mir:+g} · 재고 {stk:+g} → {'/'.join(miss)} 미반영")
            return
        rec("F", c["name"], "PASS", f"원장·수불장·재고 3곳 일치 ({led:+g})")
    else:
        rec("F", c["name"], "PASS", f"{c['probe']} {led:+g}")


def run_rule(c, ctx):
    b = probe()
    st, res = call(c["method"], path_of(c, ctx), body_of(c, ctx))
    a = probe()
    d = {k: round(a.get(k, 0) - b.get(k, 0), 4) for k in b}
    body = json.dumps(res, ensure_ascii=False)
    blocked = (st >= 400) or (isinstance(res, dict) and res.get("ok") is False)
    wrote = any(abs(v) > 0.001 for v in d.values())
    if not blocked:
        rec("R", c["name"], "미구현",
            f"차단되지 않음 — {st} 통과{' + DB 기록됨' if wrote else ''} · {body[:110]}"); return
    if wrote:
        rec("R", c["name"], "FAIL",
            f"거부했지만 DB 에 기록됨 — {[k for k, v in d.items() if abs(v) > 0.001]}"); return
    kw = c.get("keyword")
    tail = f"차단 확인 — {body[:120]}" if (not kw or kw in body) else f"거부됨(문구는 다름) — {body[:120]}"
    rec("R", c["name"], "PASS", tail)


def main():
    print("=" * 78)
    print(f" 흐름 TestBed — 프로그램 실구동 검증  (롤백 모드 · 오염 0)   :{ARG.port}")
    print("=" * 78)

    cases = [c for c in FC.CASES
             if (not ARG.kind or c["kind"] == ARG.kind)
             and (not ARG.only or ARG.only in c["name"])]
    if ARG.list:
        for c in cases:
            print(f"   [{c['kind']}] {c['name']:44s} {c['method']} {c.get('path')}")
        print(f"\n   총 {len(cases)}건 (전체 {len(FC.CASES)})")
        return 0

    if call("GET", "/api/_flow/probe")[0] != 200:
        print(f"★flow_server 가 :{ARG.port} 에 없습니다 — 먼저 기동하세요.\n"
              f"   python _migration/flow_server.py --port {ARG.port}")
        return 1

    ctx = fixture()
    if "mat" not in ctx:
        print("★테스트 자재를 못 찾음"); return 1
    call("POST", "/api/_flow/scope", {"ymd": FC.YMD, "mat": ctx["mat"]})   # 관측 스코프(속도)
    print(f"\n 대상 자재 = {ctx['mat']} (가용 {ctx['avail']:,.0f})"
          f" · 마감 {ctx.get('closed_ptype','-')}/{ctx.get('closed_period','-')}"
          f" · 생산품 {ctx.get('prod_item','-')}\n")

    last_kind = None
    for c in cases:
        if c["kind"] != last_kind:
            print(f"── [{c['kind']}] {'흐름 — 값이 제대로 적히는가' if c['kind']=='F' else '규칙 — 제대로 막는가'} "
                  + "─" * 24)
            last_kind = c["kind"]
        if c.get("skip_if") and c["skip_if"](ctx):
            rec(c["kind"], c["name"], "SKIP", "픽스처 부족 — 참조할 실데이터 없음"); continue
        # 원장행 키가 필요한 케이스: 방금 넣은 입고행(+100)을 **미커밋 조회**로 찾는다
        if c.get("needs_ledger_key"):
            _, q = call("POST", "/api/_flow/sql", {
                "sql": "SELECT TOP 1 MAINT_YMD, MAINT_SEQ FROM nx.stock_ledger "
                       "WHERE MAINT_YMD=? AND MAT_CODE=? AND STOCK_POINT='MAT' AND MAINT_QTY=100 "
                       "ORDER BY MAINT_SEQ DESC", "args": [FC.YMD, ctx["mat"]]})
            rows = q.get("rows") or []
            if not rows:
                rec(c["kind"], c["name"], "SKIP", "선행 입고행을 못 찾음"); continue
            ctx["_kymd"], ctx["_kseq"] = str(rows[0][0]).strip(), int(rows[0][1])
        try:
            (run_flow if c["kind"] == "F" else run_rule)(c, ctx)
        except Exception as e:
            rec(c["kind"], c["name"], "FAIL", f"케이스 실행 오류 — {type(e).__name__}: {str(e)[:90]}")

    # 사유 고지 검사 (규칙 A-0-1) — 차단 메시지가 '왜 안 되는지' 를 담고 있는가
    if not ARG.kind or ARG.kind == "R":
        if FC.REASON_CHECKS:
            print("── [R] 차단 사유 고지 " + "─" * 40)
        for c in FC.REASON_CHECKS:
            if not ARG.only or ARG.only in c["name"]:
                if c.get("skip_if") and c["skip_if"](ctx):
                    rec("R", c["name"], "SKIP", "픽스처 부족"); continue
                _, res = call(c["method"], path_of(c, ctx), body_of(c, ctx))
                s = json.dumps(res, ensure_ascii=False)
                miss = [w for w in c["must_contain"] if w not in s]
                rec("R", c["name"], "PASS" if not miss else "FAIL",
                    s[:190] if not miss else f"사유에 빠진 항목 {miss} · {s[:120]}")

    # 조회형 점검
    if not ARG.kind:
        print("── [R] 조회 리포트 " + "─" * 43)
        for c in FC.READ_CHECKS:
            if ARG.only and ARG.only not in c["name"]:
                continue
            st, res = call(c["method"], path_of(c, ctx))
            ok = (st == 200)
            note = json.dumps(res.get("summary") or res.get("totals") or res, ensure_ascii=False)[:150]
            rec("R", c["name"], "PASS" if ok else "FAIL", f"{st} · {note}")

    # ── 롤백 + 오염 0 ────────────────────────────────────────────────
    print("── 롤백 & 오염 0 증명 " + "─" * 40)
    st, rb = call("POST", "/api/_flow/rollback")
    if st == 200 and rb.get("clean"):
        print("   ✅ 오염 0 PASS — 기동시점 행수와 불변(독립 커넥션 확인)")
    else:
        print(f"   ★★오염 의심 — {json.dumps(rb, ensure_ascii=False)[:300]}")

    print("\n" + "=" * 78)
    n = {}
    for k, nm, v, _ in RESULTS:
        n[v] = n.get(v, 0) + 1
    print(f" 결과: PASS {n.get('PASS',0)} · FAIL {n.get('FAIL',0)} · "
          f"미구현 {n.get('미구현',0)} · SKIP {n.get('SKIP',0)}  (총 {len(RESULTS)})")
    bad = [(k, nm, v, nt) for k, nm, v, nt in RESULTS if v in ("FAIL", "미구현")]
    if bad:
        print("\n ★조치 필요")
        for k, nm, v, nt in bad:
            print(f"   [{k}] {nm} — {v}\n       {nt}")
    print("=" * 78)
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
