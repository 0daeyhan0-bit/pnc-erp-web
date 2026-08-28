# -*- coding: utf-8 -*-
"""재고 flow(자재→키팅→생산→완성/영업) 수불장 in/out 검증 하네스 — durable 재작성 2026-08-28

정본 문서 = `_schema/STOCK_FLOW_INOUT_VERIFY.md`

★왜 durable 인가: 원본 하네스(flow_verify_all/v2/rollback.py)가 `scratchpad/` 에 있어 소실됐고
  결과 문서도 auto snapshot 커밋에만 남아 있었다. 같은 사고 재발 방지로 `_migration/` 에 둔다.

★오염 0 원리
  실제 엔드포인트 **함수**를 그대로 호출하되, 각 라우터 모듈이 임포트해 쓰는 이름
  (`_nx`, `_nx_tx`)을 **no-commit 공유 커넥션**으로 몽키패치한다.
    · 공유 커넥션 = autocommit=False, commit()/close() 는 no-op
    · 모든 쓰기가 한 트랜잭션에 모이고, 마지막에 rollback() → **DB 에 아무것도 안 남는다**
  검증 전후 행수를 대조해 오염 0 을 매번 증명한다.

사용:
  python _migration/flow_verify.py            # 검증만(항상 롤백)
  python _migration/flow_verify.py --verbose  # 델타 상세
"""
import sys, os, io, traceback
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
HERE = os.path.dirname(os.path.abspath(__file__))
BE = os.path.join(HERE, '..', 'PNC_ERP_Web', 'backend')
sys.path.insert(0, BE)
os.chdir(BE)

import common          # ★common 이 db_client 경로(../../../New_ERP)를 sys.path 에 넣어준다 — 먼저 임포트
import pyodbc, db_client

VERBOSE = '--verbose' in sys.argv

CS = (f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};'
      f'DATABASE=PARTNER_ERP_TEST3;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}')


class NoCommitConn:
    """공유 트랜잭션 커넥션 — commit/close 를 무력화해 라우터가 커밋하지 못하게 한다."""
    def __init__(self, cn): object.__setattr__(self, '_cn', cn)
    def cursor(self): return self._cn.cursor()
    def commit(self): pass          # ★no-op — 라우터가 커밋해도 반영 안 됨
    def close(self): pass           # ★no-op — 커넥션 유지
    def rollback(self): pass        # 최종 롤백은 하네스가 원본으로 직접 수행
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def __getattr__(self, n): return getattr(self._cn, n)


# ── 관측 대상 (원장 · 자재수불장 · 자재재고) ─────────────────────────────
PROBES = [
    ("원장",       "SELECT COUNT(*) FROM nx.stock_ledger"),
    ("원장MAT",    "SELECT ISNULL(SUM(CAST(MAINT_QTY AS float)),0) FROM nx.stock_ledger WHERE STOCK_POINT='MAT'"),
    ("자재수불장", "SELECT COUNT(*) FROM nx.PU_T_STOCK_MAINT"),
    # ★행수만 보면 UPDATE(수정)를 판정할 수 없다 — 수량합도 같이 본다(2026-08-28 교훈)
    ("수불장수량", "SELECT ISNULL(SUM(CAST(MAINT_QTY AS float)),0) FROM nx.PU_T_STOCK_MAINT"),
    ("자재재고",   "SELECT ISNULL(SUM(CAST(STOCK_QTY AS float)),0) FROM nx.PU_T_MAT_STOCK_WH"),
]


def snap(cur):
    out = {}
    for nm, q in PROBES:
        cur.execute(q); out[nm] = float(cur.fetchone()[0] or 0)
    return out


def delta(a, b):
    return {k: round(b[k] - a[k], 4) for k in a}


def main():
    raw = pyodbc.connect(CS, autocommit=False)
    shared = NoCommitConn(raw)
    probe = raw.cursor()

    # 검증 전 전량 스냅(오염 0 증명용)
    base_rows = {}
    for t in ("nx.stock_ledger", "nx.PU_T_STOCK_MAINT", "nx.PU_T_MAT_STOCK_WH"):
        probe.execute(f"SELECT COUNT(*) FROM {t}"); base_rows[t] = probe.fetchone()[0]
    print("=== 검증 전 행수 ===")
    for t, n in base_rows.items(): print(f"   {t:26s} {n:>10,}")

    # ── 몽키패치: common + 각 라우터 모듈이 임포트한 이름 ───────────────
    import importlib
    mods = ['routers.stock', 'routers.kitting', 'routers.prodwrite', 'routers.backflush']
    patched = []
    orig_common = (common._nx, common._nx_tx)
    common._nx = lambda: shared
    common._nx_tx = lambda: shared
    for m in mods:
        try:
            mod = importlib.import_module(m)
        except Exception as e:
            print(f"   ⚠ {m} 임포트 실패: {str(e)[:60]}"); continue
        for nm in ('_nx', '_nx_tx'):
            if hasattr(mod, nm):
                patched.append((mod, nm, getattr(mod, nm)))
                setattr(mod, nm, lambda: shared)
    print(f"\n   몽키패치 {len(patched)}곳 (+ common 2곳)")

    results = []

    def step(label, fn):
        """한 시나리오 실행 → 3곳 델타 측정. 예외도 결과로 남긴다."""
        before = snap(probe)
        err = None
        try:
            fn()
        except Exception as e:
            err = f"{type(e).__name__}: {str(e)[:70]}"
        after = snap(probe)
        d = delta(before, after)
        results.append((label, d, err))
        mark = "✖" if err else "·"
        print(f"   {mark} {label:34s} 원장 {d['원장']:+5.0f}행/{d['원장MAT']:+8.1f} · "
              f"수불장 {d['자재수불장']:+4.0f}행/{d['수불장수량']:+8.1f} · 재고 {d['자재재고']:+8.1f}"
              + (f"   {err}" if err else ""))
        if VERBOSE and err:
            traceback.print_exc()

    # ── 시나리오: 문서 §2 의 14개 중 자재 3대 쓰기 + F1/F2 초점 ──────────
    print("\n=== 시나리오 실행 (전부 롤백됨) ===")
    from routers import stock as R

    # 테스트 대상 자재 = 실제 재고가 있는 품목 1개
    probe.execute("""SELECT TOP 1 UPPER(LTRIM(RTRIM(item_code))) FROM nx.stock_snapshot
                      WHERE domain='MAT' AND ptype='M' AND stock_qty > 100 ORDER BY stock_qty DESC""")
    r = probe.fetchone()
    MAT = str(r[0]) if r else None
    if not MAT:
        probe.execute("SELECT TOP 1 UPPER(LTRIM(RTRIM(MAT_CODE))) FROM nx.PU_T_MAT_STOCK_WH WHERE STOCK_QTY>100")
        r = probe.fetchone(); MAT = str(r[0]) if r else 'TESTMAT'
    print(f"   대상 자재 = {MAT}\n")

    # ★payload 스펙(routers/stock.py 실측)
    #   stock_save   : {screen, rows:[{MAINT_YMD, MAT_CODE, qty, ...}]}   screen=adjust/receipt/issue/return
    #   stock_update : {screen, MAINT_YMD, MAINT_SEQ, qty, ...}
    #   stock_delete : {MAINT_YMD, MAINT_SEQ}
    YMD = '260828'

    def save(screen, qty):
        return R.stock_save({"screen": screen, "user": "flowverify",
                             "rows": [{"MAINT_YMD": YMD, "MAT_CODE": MAT, "qty": qty}]})

    res = {}
    step("자재입고 stock_save(receipt) +100", lambda: res.__setitem__('r', save("receipt", 100)))
    step("자재조정 stock_save(adjust)  +50",  lambda: res.__setitem__('a', save("adjust", 50)))
    step("자재출고 stock_save(issue)   -30",  lambda: res.__setitem__('i', save("issue", 30)))
    step("자재반품 stock_save(return)  -15  ★F2", lambda: res.__setitem__('t', save("return", 15)))

    # ★F1 — 방금 넣은 입고행의 키(MAINT_YMD, MAINT_SEQ)를 원장에서 직접 찾는다
    probe.execute("""SELECT TOP 1 MAINT_YMD, MAINT_SEQ FROM nx.stock_ledger
                      WHERE MAINT_YMD=? AND MAT_CODE=? AND STOCK_POINT='MAT'
                      ORDER BY MAINT_SEQ DESC""", YMD, MAT)
    k = probe.fetchone()
    if k:
        kymd, kseq = str(k[0]), int(k[1])
        print(f"   대상 원장행 = {kymd}/{kseq}")
        step("자재수정 stock_update      ★F1",
             lambda: R.stock_update({"screen": "receipt", "MAINT_YMD": kymd, "MAINT_SEQ": kseq,
                                     "qty": 150, "user": "flowverify"}))
        step("자재삭제 stock_delete      ★F1",
             lambda: R.stock_delete({"MAINT_YMD": kymd, "MAINT_SEQ": kseq, "user": "flowverify"}))
    else:
        print("   ★입고행이 원장에 안 들어감 — 앞 단계 실패. F1 판정 불가")

    # ── 롤백 + 오염 0 증명 ───────────────────────────────────────────────
    raw.rollback()
    for mod, nm, fn in patched:
        setattr(mod, nm, fn)
    common._nx, common._nx_tx = orig_common

    print("\n=== 롤백 후 행수 (오염 0 증명) ===")
    ok = True
    chk = pyodbc.connect(CS, autocommit=True).cursor()
    for t, n0 in base_rows.items():
        chk.execute(f"SELECT COUNT(*) FROM {t}"); n1 = chk.fetchone()[0]
        same = (n0 == n1); ok &= same
        print(f"   {t:26s} {n0:>10,} → {n1:>10,}  {'✅ 불변' if same else '★★오염!'}")
    print(f"\n   오염 0 : {'PASS' if ok else '★★FAIL — 즉시 확인 필요'}")

    print("\n=== 판정 (F1/F2) ===")
    for label, d, err in results:
        if "★F" not in label:
            continue
        if err:
            print(f"   {label}: 실행오류 — {err}"); continue
        led, mir, stk = d['원장MAT'], d['수불장수량'], d['자재재고']
        if abs(led) < 1e-9 and abs(mir) < 1e-9 and abs(stk) < 1e-9:
            print(f"   {label}: 판정불가(델타 없음)")
        elif abs(led - mir) < 0.001 and abs(led - stk) < 0.001:
            print(f"   {label}: ✅ 정상 — 원장·수불장·재고 3곳 일치 ({led:+.1f})")
        else:
            miss = [n for n, v in (("수불장", mir), ("재고", stk)) if abs(led - v) >= 0.001]
            print(f"   {label}: ★불일치 — 원장 {led:+.1f} vs " +
                  " · ".join(f"{n} {v:+.1f}" for n, v in (("수불장", mir), ("재고", stk))) +
                  f"   → {'/'.join(miss)} 미반영")
    raw.close()


if __name__ == '__main__':
    main()
