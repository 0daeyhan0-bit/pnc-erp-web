# -*- coding: utf-8 -*-
"""전 구간 쓰기 TestBed — 생산준비등록 → BOM 재고이동 → 생산바코드 실적 → 완제품 재고

  ★안전장치
    · PARTNER_ERP_TEST3 단일 커넥션 · autocommit=False · **끝에서 무조건 rollback**
    · 라우터가 commit() 해도 무력화(NoCommitConn) → DB 확정 안 됨(오염 0)
    · 라이브 PARTNER_ERP 는 읽지도 쓰지도 않는다

  측정: 각 단계 전/후로 재고 5곳을 재서 '실제로 움직였는가'를 본다.
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
    """commit 만 무력화. 커서 수명은 정상(MARS 미지원 대응 — flow_server.py 와 같은 방식)."""
    def __init__(self, cn):
        object.__setattr__(self, '_cn', cn)
        object.__setattr__(self, '_curs', [])
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
import routers.ready as READY
import routers.procbc as PROCBC
for m in (READY, PROCBC):
    if hasattr(m, "_nx"): m._nx = lambda: SHARED
    if hasattr(m, "_nx_tx"): m._nx_tx = lambda: SHARED

cur = RAW.cursor()
OK, NG = [], []


def title(t):
    print("\n" + "=" * 82); print(" " + t); print("=" * 82)


def judge(name, cond, detail=""):
    (OK if cond else NG).append(name)
    print(f"  {'✅ PASS' if cond else '★FAIL '}  {name}")
    if detail:
        for ln in str(detail).split("\n"):
            print(f"            {ln}")


def q1(sql, *a):
    cur.execute(sql, *a) if a else cur.execute(sql)
    r = cur.fetchone()
    return float(r[0] or 0) if r else 0.0


def snap(item, gpc, mats):
    """재고 5곳 스냅샷"""
    s = {}
    s["준비재고"] = q1("""SELECT ISNULL(SUM(STOCK_QTY),0) FROM nx.PU_T_READY_STOCK
                          WHERE ITEM_CODE=? AND CUST_CODE='Z99990' AND PROC_GUBUN=?""", item, gpc)
    s["파트재고"] = q1("""SELECT ISNULL(SUM(STOCK_QTY),0) FROM nx.PR_T_MAT_STOCK_WH
                          WHERE PART_CODE=?""", gpc)
    if mats:
        ph = ",".join("?" * len(mats))
        s["자재창고"] = q1(f"""SELECT ISNULL(SUM(STOCK_QTY),0) FROM nx.PU_T_MAT_STOCK_WH
                              WHERE CUST_CODE='Z99990' AND GAGONG_PROC_CODE='IS0001'
                                AND MAT_CODE IN ({ph})""", *mats)
        s["자재수불"] = q1(f"""SELECT ISNULL(SUM(MAINT_QTY),0) FROM nx.PU_T_STOCK_MAINT
                              WHERE MAT_CODE IN ({ph})""", *mats)
    s["완제품"] = q1("SELECT ISNULL(SUM(STOCK_QTY),0) FROM nx.SA_T_ITEM_STOCK WHERE ITEM_CODE=?", item)
    return s


def diff(a, b):
    return {k: round(b.get(k, 0) - a.get(k, 0), 4) for k in set(a) | set(b)}


def show(d):
    return " · ".join(f"{k} {v:+,.2f}" for k, v in sorted(d.items()) if abs(v) > 1e-9) or "(변동 없음)"


try:
    # ══════════════════════════════════════════════════════════════
    title("W0. 시료 선정 — 준비등록이 실제로 소비할 재료가 다 있는 건")
    # 키팅 대상 BOM 이 있고 자재가 충분한 (도번, 파트) 를 찾는다
    cur.execute("""SELECT TOP 25 RTRIM(d.assy_item_code) item, RTRIM(ISNULL(d.gagong_proc_code,'')) gpc,
                          RTRIM(ISNULL(d.split_work_order,'')) wo, MAX(RTRIM(ISNULL(d.plan_ymd,''))) ymd
                     FROM nx.plan_part_dtl d WITH(NOLOCK)
                    WHERE ISNULL(d.assy_item_code,'')<>'' AND ISNULL(d.gagong_proc_code,'')<>''
                    GROUP BY RTRIM(d.assy_item_code), RTRIM(ISNULL(d.gagong_proc_code,'')),
                             RTRIM(ISNULL(d.split_work_order,''))
                    ORDER BY MAX(RTRIM(ISNULL(d.plan_ymd,''))) DESC""")
    cands = cur.fetchall()
    print(f"  후보 {len(cands)}건 — 세트가능 수량이 나오는 첫 건을 고른다")

    pick = None
    for c in cands:
        item, gpc, wo, ymd = c[0], c[1], c[2], c[3]
        try:
            chk = READY.ready_setcheck(item=item, ymd=ymd, qty=1)
        except Exception:
            continue
        rows = chk.get("rows") or []
        able = float(chk.get("set_able") or 0)
        if rows and able >= 1:
            pick = dict(item=item, gpc=gpc, wo=wo, ymd=ymd, bom=rows, able=able)
            break

    if not pick:
        judge("W0 시료 확보", False, "세트가능≥1 인 (도번·파트) 를 못 찾음 — 이후 단계 진행 불가")
        raise SystemExit
    mats = [str(r.get("mat") or r.get("mat_code") or "").strip() for r in pick["bom"]]
    mats = [m for m in mats if m][:40]
    judge("W0 시료 확보", True,
          f"도번 {pick['item']} · 파트 {pick['gpc']} · 계획일 {pick['ymd']}\n"
          f"BOM 자재 {len(pick['bom'])}종 · 세트가능 {pick['able']:g}")

    QTY = 1.0
    # ══════════════════════════════════════════════════════════════
    title(f"W1. 생산준비등록 실적 — /api/ready/commit  (도번 {pick['item']} · {QTY:g}세트)")
    before = snap(pick["item"], pick["gpc"], mats)
    print(f"  before : {', '.join(f'{k} {v:,.2f}' for k, v in sorted(before.items()))}")
    r1 = READY.ready_commit({"mode": "register", "item": pick["item"], "gpc": pick["gpc"],
                             "qty": QTY, "ymd": pick["ymd"], "wo": pick["wo"],
                             "weld_print": False, "user": "TESTBED"})
    print(f"  응답   : {str(r1)[:220]}")
    after = snap(pick["item"], pick["gpc"], mats)
    d1 = diff(before, after)
    judge("W1 준비등록이 성공했는가", bool(r1.get("ok")), r1.get("detail") or r1.get("msg") or "")
    judge("W1 준비재고가 늘었는가", d1.get("준비재고", 0) > 0, f"준비재고 {d1.get('준비재고', 0):+,.2f}")
    judge("W1 ★BOM 기준 자재가 빠졌는가", d1.get("자재창고", 0) < 0 or d1.get("자재수불", 0) < 0,
          f"자재창고 {d1.get('자재창고', 0):+,.2f} · 자재수불 {d1.get('자재수불', 0):+,.2f}")
    judge("W1 ★파트재고로 옮겨갔는가", d1.get("파트재고", 0) > 0, f"파트재고 {d1.get('파트재고', 0):+,.2f}")
    print(f"  변동   : {show(d1)}")

    # ══════════════════════════════════════════════════════════════
    title("W2. 생산 바코드 실적 — /api/gagong/barcode/register")
    cur.execute("""SELECT TOP 5 RTRIM(BOX_NO), RTRIM(ISNULL(ITEM_CODE,'')), ISNULL(CUT_QTY,0)
                     FROM nx.PR_T_INDI_CUTTING WITH(NOLOCK)
                    WHERE ISNULL(DEL_FLAG,'0')<>'1' AND ISNULL(PROD_FLAG,'0')<>'1'
                      AND ISNULL(BOX_NO,'')<>''
                    ORDER BY PLAN_YMD DESC, BOX_NO DESC""")
    boxes = cur.fetchall()
    if not boxes:
        judge("W2 미실적 가공간판 확보", False, "PROD_FLAG<>1 인 전표가 없음 — 바코드 실적 테스트 불가")
    else:
        box, bitem, bqty = boxes[0][0], boxes[0][1], float(boxes[0][2] or 0)
        judge("W2 미실적 가공간판 확보", True, f"BOX_NO {box} · 품목 {bitem} · 절단수량 {bqty:g}")
        b2 = snap(bitem, pick["gpc"], mats)
        g = max(1, int(bqty)) if bqty else 1
        r2 = PROCBC.gagong_bc_register({"box_no": box, "good_qty": g, "bad_qty": 0,
                                        "user": "TESTBED"})
        print(f"  응답   : {str(r2)[:300]}")
        a2 = snap(bitem, pick["gpc"], mats)
        d2 = diff(b2, a2)
        judge("W2 바코드 실적등록이 성공했는가", bool(r2.get("ok")),
              r2.get("msg") or str(r2.get("shortage") or "")[:200])
        if r2.get("ok"):
            mv = r2.get("moved") or []
            judge("W2 ★재고가 4갈래로 이동했는가", len(mv) > 0,
                  " / ".join(f"{m['kind']} {m['code']} {m['qty']:+g}" for m in mv[:6]) or "moved 비었음")
            neg = [m for m in mv if float(m.get("qty", 0)) < 0]
            pos = [m for m in mv if float(m.get("qty", 0)) > 0]
            judge("W2 ★자재가 차감됐는가(−)", len(neg) > 0, f"차감 {len(neg)}건")
            judge("W2 ★가공창고가 증가했는가(+)", len(pos) > 0, f"증가 {len(pos)}건")
        print(f"  변동   : {show(d2)}")

    # ══════════════════════════════════════════════════════════════
    title("W3. 완제품(영업) 재고 — 출하가 줄이는가")
    cur.execute("""SELECT TOP 1 RTRIM(ITEM_CODE), ISNULL(STOCK_QTY,0)
                     FROM nx.SA_T_ITEM_STOCK WITH(NOLOCK)
                    WHERE ISNULL(STOCK_QTY,0) > 10 ORDER BY STOCK_QTY DESC""")
    f = cur.fetchone()
    if f:
        fitem, fqty = f[0], float(f[1])
        judge("W3 완제품 재고 시료", True, f"{fitem} 현재고 {fqty:,.0f}")
        print("  ※출하 API(/api/lgsale/save)는 실적·마감과 얽혀 별도 케이스로 다룬다(F9 가 읽기로 검증).")
    else:
        judge("W3 완제품 재고 시료", False, "재고>10 인 품목 없음")

finally:
    title("정리 — 전량 롤백")
    try:
        RAW.rollback()
        print("  ✅ ROLLBACK 완료 — DB 오염 0")
    except Exception as e:
        print("  ★롤백 실패:", str(e)[:150])
    print(f"\n  결과: PASS {len(OK)} · FAIL {len(NG)}")
    if NG:
        print("  실패 목록:")
        for n in NG: print("    ★", n)
    try: RAW.close()
    except Exception: pass
