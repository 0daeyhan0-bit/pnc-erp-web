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
AP.add_argument('--kind', default='', choices=['', 'F', 'R', 'S'])
AP.add_argument('--list', action='store_true')
ARG = AP.parse_args()
BASE = f"http://127.0.0.1:{ARG.port}"
RESULTS = []


def call(method, path, payload=None, timeout=600, token=None):
    """(status, body) — 4xx/5xx 도 예외 대신 결과로 (규칙 검증은 '거부'가 정답).
       token 을 주면 Authorization 헤더를 붙인다(인증 도입 후 필수)."""
    data = json.dumps(payload).encode() if payload is not None else None
    _h = {"Content-Type": "application/json"}
    if token:
        _h["Authorization"] = "Bearer " + token
    req = urllib.request.Request(BASE + path, data=data, method=method, headers=_h)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            _b = r.read().decode("utf-8", "replace")
            # ★JSON 이 아닌 응답도 있다(QR=SVG, 인쇄=HTML). 파싱 실패를 '오류'로 세면
            #   멀쩡한 케이스가 거짓 FAIL 이 된다 — 본문을 그대로 돌려준다.
            try:
                return r.status, json.loads(_b or "{}")
            except Exception:
                return r.status, _b
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode() or "{}")
        except Exception:
            return e.code, {}
    except Exception as e:
        return 0, {"_err": f"{type(e).__name__}: {str(e)[:90]}"}


def probe():
    return call("GET", "/api/_flow/probe")[1].get("now", {})


def delta(before, after):
    """프로브 델타. ★flow_server 는 프로브 쿼리가 실패하면 None 을 넣는다.
       None - None 으로 러너가 죽으면 **멀쩡한 코드가 거짓 FAIL** 이 된다(하네스를 못 믿게 된다)."""
    return {k: round((after.get(k) or 0) - (before.get(k) or 0), 4) for k in before}


# ── 로그인 (인증 도입 후 하네스도 로그인해야 한다) ────────────────────
_TOKENS = {}


def token_for(uid):
    """계정 id -> 토큰. None 이면 무토큰(비로그인 상황을 그대로 재현)."""
    if not uid:
        return None
    if uid in _TOKENS:
        return _TOKENS[uid]
    pw = FC.ACCOUNTS.get(uid)
    if pw is None:
        _TOKENS[uid] = None
        return None
    st, res = call("POST", "/api/auth/login", {"id": uid, "pw": pw})
    tok = res.get("token") if isinstance(res, dict) else None
    if not tok and st >= 500:
        # ★일시적 서버오류(공유 커넥션 커서 충돌 등)로 한 번 실패하면 그 뒤 40케이스가
        #   통째로 SKIP 된다(2026-08-30 실측). 한 번은 다시 시도한다.
        import time as _t; _t.sleep(1.0)
        st, res = call("POST", "/api/auth/login", {"id": uid, "pw": pw})
        tok = res.get("token") if isinstance(res, dict) else None
    if not tok:
        print(f"   ⚠ 하네스 로그인 실패({uid}) — {st} {str(res)[:90]}")
    _TOKENS[uid] = tok
    return tok


def forget_token(uid):
    """로그아웃 검증처럼 토큰을 버려야 하는 케이스용."""
    _TOKENS.pop(uid, None)


def rec(kind, name, verdict, note=""):
    RESULTS.append((kind, name, verdict, note))
    icon = {"PASS": "✅", "FAIL": "★FAIL", "미구현": "☐미구현", "SKIP": "–"}[verdict]
    print(f"   {icon:7s} [{kind}] {name}")
    if note:
        print(f"           {note}")


def tok_of(c):
    """케이스가 쓸 토큰. ★as_ 를 **명시**하면 그것(None=무토큰), 없으면 기본 내부계정.
       내부 API 전면 인증 이후 [F]/[R] 도 로그인해야 화면 API 를 부를 수 있다."""
    uid = c["as_"] if "as_" in c else getattr(FC, "DEFAULT_AS", None)
    return token_for(uid)


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
    st, res = call(c["method"], path_of(c, ctx), body_of(c, ctx), token=tok_of(c))
    a = probe()
    d = delta(b, a)
    if st == 404:
        rec("F", c["name"], "SKIP", "엔드포인트 없음 — 이 브랜치에 해당 기능이 아직 없다(404)"); return
    if st != 200 or (isinstance(res, dict) and res.get("ok") is False):
        detail = res.get("errors") or res.get("detail") or res.get("_err") or res
        # ★allow_reject: "프로그램이 정상 작동하는가" 관점의 케이스(재생 등).
        #   재고부족·마감 같은 **정당한 거부는 프로그램이 제 일을 한 것**이므로 FAIL 이 아니다.
        #   진짜 문제는 500(터짐)·연결실패·거부하면서 DB 에 쓰는 것이다.
        #   (2026-09-01 대표: "프로그램이 정상적으로 작동을 하는지, 그 관점에서 접근했으면 좋겠어")
        if c.get("allow_reject") and 400 <= st < 500:
            wrote = any(abs(v) > 0.001 for v in d.values())
            if wrote:
                rec("F", c["name"], "FAIL",
                    f"★거부했는데 DB 에 기록됨 — {[k for k, v in d.items() if abs(v) > 0.001]}")
            else:
                rec("F", c["name"], "PASS", f"정상 거부({st}) · 무기록 — {str(detail)[:110]}")
            return
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
    st, res = call(c["method"], path_of(c, ctx), body_of(c, ctx), token=tok_of(c))
    a = probe()
    d = delta(b, a)
    body = json.dumps(res, ensure_ascii=False)
    # ★404 를 '차단'으로 세면 안 된다 — 그 엔드포인트가 이 브랜치에 없을 뿐이다.
    #   (예: 마감 도메인은 feat/close-mgmt 에만 있다. main 에서 돌리면 404 가 난다.)
    if st == 404:
        rec("R", c["name"], "SKIP", "엔드포인트 없음 — 이 브랜치에 해당 기능이 아직 없다(404)")
        return
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


def run_secure(c, ctx):
    """[S] 인증·소속 강제 — **실제 응답값**을 보여주며 판정한다.

       [R] 은 '막혔는가'만 본다. 소속 강제는 그것으로 부족하다 —
       200 이 나오되 **자기 데이터만** 나와야 하기 때문이다.
    """
    uid = c["as_"] if "as_" in c else getattr(FC, "DEFAULT_AS", None)
    tok = token_for(uid)
    if uid and not tok:
        rec("S", c["name"], "SKIP", f"하네스가 {uid} 로 로그인하지 못함"); return
    b = probe()
    st, res = call(c["method"], path_of(c, ctx), body_of(c, ctx), token=tok)
    a = probe()
    d = delta(b, a)

    exp = c.get("expect")
    exps = tuple(exp) if isinstance(exp, (tuple, list)) else (exp,)
    ok_st = (exp is None) or (st in exps)

    # ★call() 이 예외로 죽으면(status 0) 그 사유를 **먼저** 보여준다.
    #   check 함수의 note 로 덮이면 "HTTP 0 · 값 None" 만 남아 원인을 못 찾는다(2026-08-29 실측).
    if st == 0:
        _e = res.get("_err") if isinstance(res, dict) else str(res)[:120]
        rec("S", c["name"], "FAIL", f"[{uid or '무토큰'}] 호출 실패 — {_e}")
        return

    ok_ck, note = True, ""
    if c.get("check"):
        try:
            ok_ck, note = c["check"](res, ctx)
        except Exception as e:
            ok_ck, note = False, f"검사 예외 {type(e).__name__}: {str(e)[:70]}"

    # ★거부한 케이스는 DB 에 아무것도 남기면 안 된다
    wrote = [k for k, v in d.items() if abs(v) > 0.001]
    if st >= 400 and wrote:
        rec("S", c["name"], "FAIL", f"거부했지만 DB 에 기록됨 — {wrote}"); return

    who = f"[{uid or '무토큰'}]"
    detail = ""
    if isinstance(res, dict) and res.get("detail"):
        detail = " · " + str(res["detail"])[:90]
    obs = f"{who} HTTP {st}{detail}"
    if note:
        obs += f"\n           ⟹ {note}"
    if not ok_st:
        obs += f"   ← 기대 {exp}"
    rec("S", c["name"], "PASS" if (ok_st and ok_ck) else "FAIL", obs)


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

    # ★준비 확인은 ping 으로 — probe(관측 쿼리 10여개)로 두들기면 기동 중 공유 커넥션이 꼬인다
    if call("GET", "/api/_flow/ping")[0] != 200:
        print(f"★flow_server 가 :{ARG.port} 에 없습니다 — 먼저 기동하세요.\n"
              f"   python _migration/flow_server.py --port {ARG.port}")
        return 1

    ctx = fixture()
    if "mat" not in ctx:
        print("★테스트 자재를 못 찾음"); return 1
    call("POST", "/api/_flow/scope", {"ymd": FC.YMD, "mat": ctx["mat"]})   # 관측 스코프(속도)
    # [S] check 함수가 **미커밋 상태의 DB** 를 직접 볼 수 있게 헬퍼를 넣어준다
    #   (별도 커넥션으로는 우리가 방금 쓴 행이 안 보인다 — 2026-08-28 교훈)
    ctx["_sql"] = lambda q, *a: (call("POST", "/api/_flow/sql", {"sql": q, "args": list(a)})[1] or {}).get("rows", [])
    print(f"\n 대상 자재 = {ctx['mat']} (가용 {ctx['avail']:,.0f})"
          f" · 마감 {ctx.get('closed_ptype','-')}/{ctx.get('closed_period','-')}"
          f" · 생산품 {ctx.get('prod_item','-')}\n")

    # ★재생 총합 대조용 시작 기준점 — 케이스를 하나도 실행하기 전에 잡는다
    BASE0 = probe() if os.environ.get('REPLAY_YMD') else None

    last_kind = None
    for c in cases:
        if c["kind"] != last_kind:
            _lab = {"F": "흐름 — 값이 제대로 적히는가",
                    "R": "규칙 — 제대로 막는가",
                    "S": "인증·소속 — 남의 것이 보이는가"}.get(c["kind"], c["kind"])
            print(f"── [{c['kind']}] {_lab} " + "─" * 24)
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
            {"F": run_flow, "R": run_rule, "S": run_secure}[c["kind"]](c, ctx)
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
                _, res = call(c["method"], path_of(c, ctx), body_of(c, ctx), token=tok_of(c))
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
            st, res = call(c["method"], path_of(c, ctx), token=tok_of(c))
            note = json.dumps(res.get("summary") or res.get("totals") or res, ensure_ascii=False)[:150]
            if st == 404:
                rec("R", c["name"], "SKIP", "엔드포인트 없음 — 이 브랜치에 해당 기능이 아직 없다(404)")
            else:
                rec("R", c["name"], "PASS" if st == 200 else "FAIL", f"{st} · {note}")

    # ── 캐시 무효화 검사 ────────────────────────────────────────────────
    #   ★값이 아니라 **재계산 발생**으로 판정한다(이유 = flow_cases.CACHE_CHECKS 주석).
    #     수불장은 라이브 전표를 읽고 웹 쓰기는 nx 원장에 쓴다 — 축이 달라 값으로는 못 잰다.
    import time as _t
    for c in getattr(FC, "CACHE_CHECKS", []):
        if ARG.only and ARG.only not in c["name"]:
            continue
        print("── [R] 캐시 정합 " + "─" * 44)
        path = c["ledger"](ctx)
        _tk = tok_of(c)
        call("GET", path, token=_tk)                        # ① 캐시 채움
        _s = _t.time(); call("GET", path, token=_tk); hit = _t.time() - _s   # ② 캐시 히트 시간
        st, res = call("POST", c["write_path"], c["write_body"](ctx), token=_tk)
        wrote = (st == 200 and not (isinstance(res, dict) and res.get("ok") is False))
        _s = _t.time(); call("GET", path, token=_tk); after = _t.time() - _s   # ③ 쓰기 후 조회
        if not wrote:
            rec("R", c["name"], "SKIP", f"선행 쓰기 실패 — {str(res)[:100]}")
        elif after > max(hit * 3, hit + 1.0):
            rec("R", c["name"], "PASS",
                f"캐시가 버려져 재계산됨 — 캐시히트 {hit:.2f}s → 쓰기후 {after:.2f}s")
        else:
            rec("R", c["name"], "FAIL",
                f"★캐시 stale — 쓰기 후에도 캐시히트({hit:.2f}s → {after:.2f}s). 무효화 미연결")

    # ── 재생 총합 대조 (롤백 **전**에 읽어야 보인다) ──────────────────
    #   케이스별 probe 는 그 케이스가 직접 만든 값만 본다. 그런데 재생의 진짜 질문은
    #   "우리가 사람 입력(①)을 넣었을 때 시스템이 파생(②)을 레거시만큼 만들어내는가" 다.
    #   ②는 케이스에 없으므로(재생 금지 대상) 여기서 **총합으로** 대조한다.
    #   ★롤백하면 사라지므로 반드시 롤백 전에.
    if os.environ.get('REPLAY_YMD'):
        try:
            from replay_cases import expected_totals
            exp = expected_totals(os.environ['REPLAY_YMD'])
            got = delta(BASE0, probe()) if BASE0 else {}
            print("── 재생 총합 대조 (레거시 파생 vs 우리 결과) " + "─" * 18)
            for k, want in exp.items():
                have = float(got.get(k, 0) or 0)
                ok = abs(have - want) < max(abs(want) * 0.001, 0.5)
                print("   %s %-12s 레거시 %12.1f / 우리 %12.1f  차 %+.1f"
                      % ("✅" if ok else "★차이", k, want, have, have - want))
        except Exception as _e:
            print("   재생 총합 대조 생략 — %s" % str(_e)[:120])

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
