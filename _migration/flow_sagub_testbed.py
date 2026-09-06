# -*- coding: utf-8 -*-
"""사급 루프 쓰기 TestBed — 납품발행 → 바코드입고 → 검사승인 → 재고파생·사급소진

  대표 지시 흐름
    ② 판매(유상사급) → 업체 사급재고 +
    ③ 업체 상위품 입고(바코드) → 세트재고 + · 단품재고 + · 사급재고 −
       (유검사품은 검사승인을 해야 재고가 선다)

  ★안전: PARTNER_ERP_TEST3 단일 커넥션 · commit 무력화 · 끝에서 무조건 rollback
"""
import sys, os, io
BE = r"c:\Users\박근민\Desktop\NEW_ERP_1\PNC_ERP_Web\backend"
sys.path.insert(0, BE); os.chdir(BE)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
import common, db_client, pyodbc

CS = (f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};'
      f'DATABASE=PARTNER_ERP_TEST3;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}')
RAW = pyodbc.connect(CS, autocommit=False)


class NoCommitConn:
    def __init__(self, cn):
        object.__setattr__(self, '_cn', cn); object.__setattr__(self, '_curs', [])
    def cursor(self):
        c = self._cn.cursor(); self._curs.append(c); return c
    def commit(self): pass
    def rollback(self): pass
    def close(self):
        for c in self._curs:
            try: c.close()
            except Exception: pass
        object.__setattr__(self, '_curs', [])
    def __getattr__(self, k): return getattr(self._cn, k)


SHARED = NoCommitConn(RAW)
common._nx = lambda: SHARED
common._nx_tx = lambda: SHARED
import routers.setin as SETIN
for nm in ("_nx", "_nx_tx"):
    if hasattr(SETIN, nm): setattr(SETIN, nm, lambda: SHARED)

# 권한 게이트 우회(하네스는 super 로 동작) — staff_only 는 요청객체를 본다
try:
    SETIN.staff_only = lambda request, what="": {"user_id":"TESTBED","utype":"내부"}
    SETIN.require_user = lambda request: {"user_id":"TESTBED","utype":"내부","partner_code":""}
except Exception: pass


class Req:
    """staff_only 가 보는 최소 요청객체"""
    headers = {}
    cookies = {}
    class _S: pass
    state = _S()


cur = RAW.cursor()
OK, NG = [], []


def title(t):
    print("\n" + "=" * 84); print(" " + t); print("=" * 84)


def judge(n, c, d=""):
    (OK if c else NG).append(n)
    print(f"  {'✅ PASS' if c else '★FAIL '}  {n}")
    if d:
        for ln in str(d).split("\n"): print(f"            {ln}")


def q1(sql, *a):
    cur.execute(sql, *a) if a else cur.execute(sql)
    r = cur.fetchone()
    return float(r[0] or 0) if r else 0.0


def snap(cust, item):
    return {
        "사급재고": q1("SELECT ISNULL(SUM(STOCK_QTY),0) FROM nx.PU_T_SAGUB_STOCK WHERE CUST_CODE=?", cust),
        "세트재고": q1("SELECT ISNULL(SUM(STOCK_QTY),0) FROM nx.PU_T_SET_MAT_STOCK WHERE IN_CUST_CODE=?", cust),
        "세트원장": q1("SELECT ISNULL(SUM(maint_qty),0) FROM nx.set_stock_maint WHERE cust_code=?", cust),
        "단품(자재창고)": q1("""SELECT ISNULL(SUM(STOCK_QTY),0) FROM nx.PU_T_MAT_STOCK_WH
                                WHERE CUST_CODE='Z99990' AND GAGONG_PROC_CODE='IS0001'"""),
        "사급실적": q1("SELECT COUNT(*) FROM nx.PU_T_SAGUB_MAINT"),
        # ★바코드 입고 경로는 _post_sagub_out 이 **nx.sagub_maint**(웹 사급원장)에 쓴다.
        #   레거시 PU_T_SAGUB_STOCK 을 재면 0 이 나와 "사급 안 줄어든다"로 오판한다(setin.py:32,989).
        "웹사급원장": q1("SELECT ISNULL(SUM(maint_qty),0) FROM nx.sagub_maint WHERE cust_code=?", cust),
        "웹사급행수": q1("SELECT COUNT(*) FROM nx.sagub_maint WHERE cust_code=?", cust),
    }


def d(a, b):
    return {k: round(b.get(k, 0) - a.get(k, 0), 4) for k in set(a) | set(b)}


def show(x):
    return " · ".join(f"{k} {v:+,.2f}" for k, v in sorted(x.items()) if abs(v) > 1e-9) or "(변동 없음)"


try:
    # ── S0. 시료: 발행 대기(status 00) 인 세트요청 ───────────────
    title("S0. 시료 — 발행 가능한 세트요청(status 00) 찾기")
    cur.execute("""SELECT TOP 12 RTRIM(ISNULL(r.in_cust_code,'')) cust,
                          RTRIM(ISNULL(r.item_code,'')) item,
                          RTRIM(ISNULL(r.sheet_no,'')) sheet,
                          CAST(ISNULL(r.input_req_qty,0) AS float) q,
                          RTRIM(ISNULL(r.status,'')) st
                     FROM nx.set_input_req r WITH(NOLOCK)
                    WHERE RTRIM(ISNULL(r.status,''))='00'
                      AND ISNULL(r.input_req_qty,0) > 0
                      AND EXISTS(SELECT 1 FROM nx.set_input_req_dtl x WITH(NOLOCK)
                                  WHERE RTRIM(ISNULL(x.sheet_no,''))=RTRIM(ISNULL(r.sheet_no,'')))
                      -- ★사급자재를 쓰는 건만(setin.py:410 — bom_sub.sagub_flag='1' 이 차감 판정축)
                      --   이 조건을 빼면 사급 0종인 건이 뽑혀 "사급 감소 안 됨"으로 오판한다(실제 겪음).
                      AND EXISTS(SELECT 1 FROM nx.pr_m_item_bom b WITH(NOLOCK)
                                   JOIN nx.pr_m_item_bom_sub c WITH(NOLOCK)
                                     ON b.item_code=c.item_code AND b.mat_code=c.mat_code
                                  WHERE b.item_code=r.item_code AND c.sagub_flag='1')
                    ORDER BY r.sheet_no DESC""")
    cands = cur.fetchall()
    print(f"  발행대기(명세 있음) 후보 {len(cands)}건")
    for c in cands[:5]:
        print(f"      {c[0]:<7}{c[1]:<24}sheet {c[2]:<12}{c[3]:>9,.0f}")
    if not cands:
        judge("S0 시료 확보", False, "status='00' + 명세 있는 세트요청이 없음")
        raise SystemExit
    cust, item, sheet, rq = cands[0][0], cands[0][1], cands[0][2], cands[0][3]
    judge("S0 시료 확보", True, f"업체 {cust} · 도번 {item} · sheet {sheet} · 요청 {rq:g}")

    base = snap(cust, item)
    print(f"\n  기준선: {', '.join(f'{k} {v:,.2f}' for k, v in sorted(base.items()))}")

    # ── S1. 납품처리(거래명세서 발행) ────────────────────────────
    title("S1. 납품처리 — /api/setin/issue (상태 00요청 → 10발행)")
    r1 = SETIN.setin_issue(Req(), {"items": [{"sheet": sheet, "qty": rq}], "user": "TESTBED"})
    print(f"  응답: {str(r1)[:300]}")
    bc = (r1.get("barcode_no") or r1.get("barcode") or "")
    judge("S1 발행 성공", bool(r1.get("ok")), r1.get("msg") or r1.get("detail") or "")
    judge("S1 SET바코드 채번", bool(bc), f"barcode_no = {bc}")

    if bc:
        # ── S2. 바코드 입고 ──────────────────────────────────────
        title("S2. 업체 상위품 입고 — /api/setstock/receive")
        b2 = snap(cust, item)
        r2 = SETIN.setstock_receive(Req(), {"barcode": bc, "tag": "2", "user": "TESTBED"})
        print(f"  응답: {str(r2)[:300]}")
        a2 = snap(cust, item)
        dd2 = d(b2, a2)
        judge("S2 입고 성공", bool(r2.get("ok")), r2.get("msg") or r2.get("detail") or "")
        judge("S2 세트원장 기록", abs(dd2.get("세트원장", 0)) > 0, f"세트원장 {dd2.get('세트원장', 0):+,.2f}")
        print(f"  변동: {show(dd2)}")

        # 검사대기(30) 인지 확인 — 유검사면 여기서 재고가 아직 안 선다
        n30 = q1("""SELECT COUNT(*) FROM nx.set_stock_maint
                     WHERE RTRIM(ISNULL(sheet_no,''))=? AND RTRIM(ISNULL(status,''))='30'""", bc)
        n90 = q1("""SELECT COUNT(*) FROM nx.set_stock_maint
                     WHERE RTRIM(ISNULL(sheet_no,''))=? AND RTRIM(ISNULL(status,''))='90'""", bc)
        print(f"  상태: 검사대기(30) {n30:g}건 · 입고완료(90) {n90:g}건")

        # ── S3. 검사승인 ─────────────────────────────────────────
        if n30 > 0:
            title("S3. 검사승인 — /api/setinsp/complete (유검사품)")
            cur.execute("""SELECT RTRIM(ISNULL(maint_ymd,'')), maint_seq
                             FROM nx.set_stock_maint WITH(NOLOCK)
                            WHERE RTRIM(ISNULL(sheet_no,''))=? AND RTRIM(ISNULL(status,''))='30'""", bc)
            items = [{"ymd": x[0], "seq": int(x[1])} for x in cur.fetchall()]
            b3 = snap(cust, item)
            r3 = SETIN.setinsp_complete(Req(), {"items": items, "user": "TESTBED"})
            print(f"  응답: {str(r3)[:300]}")
            a3 = snap(cust, item)
            dd3 = d(b3, a3)
            judge("S3 검사승인 성공", bool(r3.get("ok")) and int(r3.get("done") or 0) > 0,
                  f"done={r3.get('done')} · ledger_posted={r3.get('ledger_posted')} · skipped={r3.get('skipped')}")
            judge("S3 ★재고가 실제로 섰는가", int(r3.get("ledger_posted") or 0) > 0,
                  f"ledger_posted={r3.get('ledger_posted')}")
            judge("S3 ★사급재고가 소진(−)됐는가",
                  dd3.get("웹사급원장", 0) < 0 or dd3.get("사급재고", 0) < 0,
                  f"웹사급원장 {dd3.get('웹사급원장', 0):+,.2f} · 레거시사급 {dd3.get('사급재고', 0):+,.2f}")
            judge("S3 ★사급 사용실적이 남았는가", dd3.get("사급실적", 0) > 0,
                  f"PU_T_SAGUB_MAINT {dd3.get('사급실적', 0):+,.0f}행")
            print(f"  변동: {show(dd3)}")
        else:
            title("S3. 검사승인 — 생략(무검사품이라 입고 즉시 90)")
            judge("S3 무검사 경로 — 입고 즉시 재고", n90 > 0, f"입고완료 {n90:g}건")

        # ── S4. 최종 누적 변동 ───────────────────────────────────
        title("S4. 사급 루프 전체 변동 (기준선 대비)")
        fin = snap(cust, item)
        dt = d(base, fin)
        for k in ("세트재고", "세트원장", "단품(자재창고)", "웹사급원장", "웹사급행수", "사급재고", "사급실적"):
            print(f"      {k:<14}{dt.get(k, 0):+16,.2f}")
        judge("S4 ★세트재고 증가", dt.get("세트재고", 0) > 0 or dt.get("세트원장", 0) != 0,
              f"세트재고 {dt.get('세트재고', 0):+,.2f} · 세트원장 {dt.get('세트원장', 0):+,.2f}")
        judge("S4 ★사급재고 감소(웹 사급원장)",
              dt.get("웹사급원장", 0) < 0,
              f"웹사급원장 {dt.get('웹사급원장', 0):+,.2f} ({dt.get('웹사급행수', 0):+,.0f}행) · 레거시 {dt.get('사급재고', 0):+,.2f}")

finally:
    title("정리 — 전량 롤백")
    try:
        RAW.rollback(); print("  ✅ ROLLBACK 완료 — DB 오염 0")
    except Exception as e:
        print("  ★롤백 실패:", str(e)[:150])
    print(f"\n  결과: PASS {len(OK)} · FAIL {len(NG)}")
    if NG:
        for n in NG: print("    ★", n)
    try: RAW.close()
    except Exception: pass
