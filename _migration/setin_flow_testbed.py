# -*- coding: utf-8 -*-
"""세트입고 2경로 실행검증 — 수동입고 vs 바코드입고, 재고 3층 반영 비교

  ★목적 (대표 지시 2026-09-08)
    "자재세트입고관리에서 수동입고로 잡았는데 단품 재고 증가가 없네"
    "바코드 입고도 재고가 안 늘어나나? 같이 확인"
    "레거시에서 그대로 가지고 온거 같아 웹으로 테스트 해봐야 해"

    ⟹ 9/7 건은 레거시가 만든 것이라 대조군이 안 된다. 웹 라우터를 직접 실행해서 본다.

  ★안전장치 — 롤백 보장(DB 변경 0)
"""
import sys, os, io, traceback
BE = r"c:\Users\박근민\Desktop\NEW_ERP_1\PNC_ERP_Web\backend"
sys.path.insert(0, BE); os.chdir(BE)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
import common, db_client, pyodbc

CS = (f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};'
      f'DATABASE=PARTNER_ERP_TEST3;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}')
RAW = pyodbc.connect(CS, autocommit=False)


class NC:
    def __init__(s, cn): object.__setattr__(s, '_cn', cn)
    def cursor(s): return s._cn.cursor()
    def commit(s): pass
    def rollback(s): pass
    def close(s): pass
    def __getattr__(s, k): return getattr(s._cn, k)


SH = NC(RAW)
common._nx = lambda: SH
common._nx_tx = lambda: SH
import routers.setin as SETIN
SETIN._nx = lambda: SH
if hasattr(SETIN, "_nx_tx"): SETIN._nx_tx = lambda: SH

cur = RAW.cursor()
YMD = "260908"


def q1(sql, *a):
    try:
        c = RAW.cursor()
        c.execute(sql, *a) if a else c.execute(sql)
        r = c.fetchone(); v = float(r[0] or 0) if r else 0.0
        c.close(); return v
    except Exception as e:
        print("      [조회오류] %s" % str(e)[:90]); return 0.0


def snap(mats):
    """자재 3층 + 세트원장"""
    s = {}
    if mats:
        ph = ",".join("?" * len(mats))
        s["①원장 stock_ledger(MAT)"] = q1(
            f"SELECT ISNULL(SUM(MAINT_QTY),0) FROM nx.stock_ledger WHERE STOCK_POINT='MAT' AND RTRIM(MAT_CODE) IN ({ph})", *mats)
        s["②잔액 PU_T_MAT_STOCK_WH"] = q1(
            f"SELECT ISNULL(SUM(STOCK_QTY),0) FROM nx.PU_T_MAT_STOCK_WH WHERE RTRIM(MAT_CODE) IN ({ph}) AND CUST_CODE='Z99990' AND ISNULL(GAGONG_PROC_CODE,'')='IS0001'", *mats)
        s["③미러이력 PU_T_STOCK_MAINT"] = q1(
            f"SELECT ISNULL(SUM(MAINT_QTY),0) FROM nx.PU_T_STOCK_MAINT WHERE RTRIM(MAT_CODE) IN ({ph})", *mats)
    return s


def report(seg, b, a, note=""):
    print("\n  [%s] 단품 재고 3층 변동" % seg)
    if note: print("     기대: %s" % note)
    moved, still = [], []
    for k in b:
        d = round(a.get(k, 0) - b.get(k, 0), 4)
        mark = "움직임" if abs(d) > 1e-9 else "  —   "
        print("       {}  {:<34s} {:>+16,.2f}".format(mark, k, d))
        (moved if abs(d) > 1e-9 else still).append(k)
    return moved, still


try:
    # ── 시료: BOM 이 있는 세트 도번 찾기
    print("=" * 92)
    print(" W0. 시료 선정 — BOM 구성품이 있는 세트 도번")
    print("=" * 92)
    cur.execute("""SELECT TOP 40 RTRIM(b.ITEM_CODE) doban, COUNT(*) n
                     FROM nx.CS_M_ITEM_BOM b WITH(NOLOCK)
                    WHERE ISNULL(b.MAT_CODE,'')<>'' AND ISNULL(b.USE_QTY,0)>0
                    GROUP BY RTRIM(b.ITEM_CODE) HAVING COUNT(*) BETWEEN 2 AND 8
                    ORDER BY COUNT(*) DESC""")
    cands = [(str(x[0]).strip(), x[1]) for x in cur.fetchall()]
    pick = None
    for doban, n in cands:
        try:
            jd = SETIN._set_bom_expand(cur, doban, "2337", YMD)
        except Exception:
            jd = []
        if jd:
            pick = (doban, n, jd); break
    if not pick:
        # 전개가 안 되면 BOM 직접 사용
        doban, n = cands[0]
        cur.execute("""SELECT RTRIM(MAT_CODE), USE_QTY FROM nx.CS_M_ITEM_BOM WITH(NOLOCK)
                        WHERE RTRIM(ITEM_CODE)=?""", doban)
        pick = (doban, n, [{"mat_code": str(x[0]).strip(), "use_qty": float(x[1] or 0), "cost": 0}
                           for x in cur.fetchall()])
        print("   ★_set_bom_expand 가 빈 결과 → BOM 직접 사용")
    doban, n, jd = pick
    mats = [str(x["mat_code"]).strip() for x in jd]
    print("   도번=%s · BOM %d건 · 전개 %d건" % (doban, n, len(jd)))
    print("   구성품: %s" % ", ".join(mats[:8]))

    # ══════════════════════════════════════════════
    print()
    print("=" * 92)
    print(" ① 수동입고 — /api/setstock/manual")
    print("=" * 92)
    # ★payload 키 = rows (items 아님) · scope='all' 이어야 하위 단품이 파생된다
    for scope in ("all", "set"):
        print("\n   --- scope='%s' ---" % scope)
        b = snap(mats)
        try:
            res = SETIN.setstock_manual(payload={
                "ymd": YMD, "cust": "2337", "user": "TESTBED", "scope": scope,
                "rows": [{"item_code": doban, "qty": 100, "remark": "TESTBED"}]})
            print("   실행결과: %s" % str(res)[:220])
        except Exception as e:
            print("   ★실행오류: %s" % str(e)[:260])
        a = snap(mats)
        note = ("구성품 3층 모두 증가해야" if scope == "all"
                else "★scope='set' = 하위 단품 건드리지 않는 것이 정상")
        report("수동입고 scope=%s" % scope, b, a, note)

    # ── 원장에 무엇이 들어갔나
    cur.execute("""SELECT RTRIM(ISNULL(MAT_CODE,'')), RTRIM(ISNULL(ITEM_CODE,'')), MAINT_QTY, ISNULL(REMARKS,'')
                     FROM nx.stock_ledger WHERE MAINT_YMD=? AND MAINT_TAG='S'
                      AND ISNULL(REMARKS,'') LIKE '%수동%' ORDER BY MAINT_SEQ DESC""", YMD)
    rs = cur.fetchall()
    print("\n   원장 tag=S(수동) 기록 %d건:" % len(rs))
    for x in rs[:8]:
        m_, i_ = str(x[0]).strip(), str(x[1]).strip()
        kind = "★세트자신" if m_ == i_ or m_.startswith(i_) else "(단품)"
        print("      mat={:<22s} item={:<16s} qty={:>8,.0f} {}".format(m_, i_, float(x[2] or 0), kind))

    # ══════════════════════════════════════════════
    print()
    print("=" * 92)
    print(" ② 바코드입고 — /api/setstock/receive")
    print("=" * 92)
    cur.execute("""SELECT COLUMN_NAME FROM PARTNER_ERP_TEST3.INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_SCHEMA='nx' AND TABLE_NAME='set_input_req' ORDER BY ORDINAL_POSITION""")
    print("   set_input_req 컬럼: " + ", ".join(r[0] for r in cur.fetchall()))
    cur.execute("""SELECT TOP 3 sheet_no FROM nx.set_input_req WITH(NOLOCK) ORDER BY sheet_no DESC""")
    reqs = [tuple(x) for x in cur.fetchall()]
    print("   set_input_req 최근: %s" % (reqs if reqs else "(없음)"))
    if reqs:
        sheet = reqs[0][0]
        cur.execute("""SELECT RTRIM(mat_code) FROM nx.set_input_req_dtl WITH(NOLOCK) WHERE sheet_no=?""", sheet)
        bmats = [str(x[0]).strip() for x in cur.fetchall()]
        print("   시료 sheet=%s · 명세 %d건" % (sheet, len(bmats)))
        if bmats:
            b2 = snap(bmats)
            try:
                res2 = SETIN.setstock_receive(request=None, payload={
                    "barcode": str(sheet), "ymd": YMD, "user": "TESTBED"})
                print("   실행결과: %s" % str(res2)[:220])
            except Exception as e:
                print("   ★실행오류: %s" % str(e)[:260])
            a2 = snap(bmats)
            report("바코드입고", b2, a2, "구성품 재고 3층 반영")
        else:
            print("   ★명세가 비어 시료 불가")
    else:
        print("   ★set_input_req 없음 — 바코드 경로 미검증")

except Exception:
    print("\n★TestBed 중단"); traceback.print_exc()
finally:
    try: RAW.rollback(); print("\n[안전] rollback 완료 — DB 변경 0")
    except Exception: pass
    try: cur.close(); RAW.close()
    except Exception: pass
