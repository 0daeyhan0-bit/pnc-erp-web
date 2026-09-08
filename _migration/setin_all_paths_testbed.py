# -*- coding: utf-8 -*-
"""세트입고 전 경로 3층 검증 — 수동·바코드·IQC검사완료·취소

  ★대표 지시 (2026-09-08)
    "세트입고 되면 자재재고 _WH 업데이트 되고, 이력도 추가되게 하면 되지 않아?"
    "바코드 입고, IQC검사 입고시도 그렇게"

    ⟹ 3층(①원장 ②PU_T_MAT_STOCK_WH ③PU_T_STOCK_MAINT)이 전 경로에서 맞는지 실제로 실행해 본다.

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
SETIN._nx_tx = lambda: SH
SETIN.staff_only = lambda *a, **k: {"id": "TESTBED", "nm": "TESTBED"}

cur = RAW.cursor()
cur.execute("SELECT FORMAT(GETDATE(),'yyMMdd')")
YMD = str(cur.fetchone()[0]).strip()
RESULT = []


def q1(sql, *a):
    c = RAW.cursor()
    try:
        c.execute(sql, *a) if a else c.execute(sql)
        r = c.fetchone(); return float(r[0] or 0) if r else 0.0
    finally:
        c.close()


def snap(mats):
    ph = ",".join("?" * len(mats))
    return {
        "①원장": q1(f"SELECT ISNULL(SUM(MAINT_QTY),0) FROM nx.stock_ledger WHERE STOCK_POINT='MAT' AND RTRIM(MAT_CODE) IN ({ph})", *mats),
        "②잔액_WH": q1(f"SELECT ISNULL(SUM(STOCK_QTY),0) FROM nx.PU_T_MAT_STOCK_WH WHERE RTRIM(MAT_CODE) IN ({ph}) AND CUST_CODE='Z99990' AND ISNULL(GAGONG_PROC_CODE,'')='IS0001'", *mats),
        "③미러이력": q1(f"SELECT ISNULL(SUM(MAINT_QTY),0) FROM nx.PU_T_STOCK_MAINT WHERE RTRIM(MAT_CODE) IN ({ph})", *mats),
    }


def rep(seg, b, a, expect=None):
    print("\n  [{}]".format(seg))
    moved = []
    for k in b:
        d = round(a.get(k, 0) - b.get(k, 0), 4)
        mark = "움직임" if abs(d) > 1e-9 else "  —   "
        print("       {}  {:<14s} {:>+14,.2f}".format(mark, k, d))
        if abs(d) > 1e-9: moved.append(k)
    ok = (len(moved) == 3) if expect == "all3" else (len(moved) == 0 if expect == "none" else None)
    if expect:
        print("       ⟹ {}".format(
            "✅ 3층 전부" if ok and expect == "all3" else
            "✅ 변동없음(정상)" if ok and expect == "none" else
            "★{}층만 움직임".format(len(moved))))
    RESULT.append((seg, len(moved), ok))
    return moved


try:
    # 시료
    cur.execute("""SELECT TOP 40 RTRIM(h.item_code) d, RTRIM(h.in_cust_code) c
                     FROM nx.set_input_req h WITH(NOLOCK)
                    WHERE ISNULL(h.item_code,'')<>'' AND ISNULL(h.in_cust_code,'')<>''
                    GROUP BY RTRIM(h.item_code), RTRIM(h.in_cust_code)
                    ORDER BY MAX(h.sheet_no) DESC""")
    pick = None
    for doban, cc in [(str(x[0]).strip(), str(x[1]).strip()) for x in cur.fetchall()]:
        jd = SETIN._set_bom_expand(cur, doban, cc, YMD)
        if jd:
            pick = (doban, cc, jd); break
    if not pick:
        print("★시료 없음"); raise SystemExit
    DOBAN, CUST, JD = pick
    MATS = [str(x["mat_code"]).strip() for x in JD]
    print("=" * 92)
    print(" 시료: 도번={} 거래처={} 하위 {}건 — {}".format(DOBAN, CUST, len(JD), ", ".join(MATS[:5])))
    print("=" * 92)

    # ══ ① 수동입고 등록/취소
    print("\n" + "=" * 92); print(" ① 수동입고 — /api/setstock/manual"); print("=" * 92)
    b = snap(MATS)
    r1 = SETIN.setstock_manual(payload={"ymd": YMD, "cust": CUST, "user": "TESTBED", "scope": "all",
                                        "rows": [{"item_code": DOBAN, "qty": 100, "remark": "TB"}]})
    print("   등록: ok={} manual_no={} jado={}".format(
        r1.get("ok"), r1.get("manual_no"), (r1.get("rows") or [{}])[0].get("jado")))
    rep("수동입고 등록", b, snap(MATS), "all3")
    b2 = snap(MATS)
    r2 = SETIN.setstock_manual_delete(payload={"manual_no": str(r1.get("manual_no"))})
    print("\n   취소: {}".format(str(r2)[:150]))
    rep("수동입고 취소", b2, snap(MATS), "all3")
    a_end = snap(MATS)
    print("\n   원복 판정: {}".format(
        "✅" if all(abs(a_end[k]-b[k]) < 0.001 for k in b) else "★잔여 있음"))

    # ══ ② 바코드 입고 + IQC 검사완료
    print("\n" + "=" * 92); print(" ② 바코드 입고 — /api/setstock/receive"); print("=" * 92)
    cur.execute("""SELECT TOP 5 h.barcode_no, h.sheet_no, RTRIM(h.item_code), ISNULL(h.insp_flag,'0'), h.status
                     FROM nx.set_input_req h WITH(NOLOCK)
                    WHERE h.status IN ('10','20','30') AND ISNULL(h.barcode_no,'')<>''
                      AND NOT EXISTS(SELECT 1 FROM nx.set_stock_maint m WITH(NOLOCK)
                                      WHERE m.sheet_no=h.barcode_no AND m.in_tag='1')
                    ORDER BY h.sheet_no DESC""")
    br = [tuple(x) for x in cur.fetchall()]
    if not br:
        # ★미입고 송장이 없으면 **직접 만들어** 검증한다(롤백되므로 안전)
        print("   미입고 송장이 없어 시료를 생성한다(롤백됨)")
        cur.execute("""SELECT ISNULL(MAX(v),900000)+1 FROM (
                           SELECT MAX(CAST(sheet_no AS bigint)) v FROM nx.set_input_req WHERE ISNUMERIC(sheet_no)=1
                           UNION ALL
                           SELECT MAX(CAST(sheet_no AS bigint)) FROM nx.set_input_req_dtl WHERE ISNUMERIC(sheet_no)=1
                       ) t""")
        _sh = int(cur.fetchone()[0])
        _bc = "79" + str(_sh)[-4:]
        cur.execute("""INSERT INTO nx.set_input_req
               (sheet_no,input_ymd,input_hms,in_cust_code,item_code,item_gubun,plan_ymd,am_pm,
                input_req_qty,deliver_qty,pack_qty,insp_flag,status,barcode_no,issue_ymd,
                remarks,insert_user_id,insert_datetime)
               VALUES(?,?,'120000',?,?,'1',?,'P',10,10,10,'0','10',?,?, 'TESTBED','TESTBED',getdate())""",
            str(_sh), YMD, CUST, DOBAN, YMD, _bc, YMD)
        _ln = 0
        for _m in JD:
            _ln += 1
            cur.execute("""INSERT INTO nx.set_input_req_dtl
                   (sheet_no,line_no,mat_code,use_qty,mat_qty,insp_flag,insert_datetime)
                   VALUES(?,?,?,?,?,?,getdate())""",
                str(_sh), _ln, _m["mat_code"], float(_m.get("use_qty") or 1),
                10 * float(_m.get("use_qty") or 1), '0')
        print("   생성: sheet={} barcode={} 명세 {}건".format(_sh, _bc, _ln))
        br = [(_bc, str(_sh), DOBAN, '0', '10')]

    if br:
        bc, sh, dob, insp, st = str(br[0][0]).strip(), br[0][1], str(br[0][2]).strip(), str(br[0][3]).strip(), str(br[0][4]).strip()
        cur.execute("SELECT RTRIM(mat_code) FROM nx.set_input_req_dtl WITH(NOLOCK) WHERE sheet_no=?", sh)
        bm = [str(x[0]).strip() for x in cur.fetchall()]
        print("   barcode={} sheet={} 도번={} insp={} status={} 명세 {}건".format(bc, sh, dob, insp, st, len(bm)))
        if bm:
            b3 = snap(bm)
            r3 = SETIN.setstock_receive(request=None, payload={"barcode": bc, "tag": "2"})
            print("   입고: {}".format(str(r3)[:180]))
            mv = rep("바코드입고", b3, snap(bm))
            cur.execute("""SELECT maint_ymd, maint_seq, ISNULL(status,''), ISNULL(derived_flag,'')
                             FROM nx.set_stock_maint WHERE sheet_no=? ORDER BY maint_seq DESC""", bc)
            sr = cur.fetchone()
            if sr:
                print("   세트원장 status={} derived={}".format(str(sr[2]).strip(), str(sr[3]).strip()))
                if str(sr[2]).strip() == '30':
                    print("\n   ── 입고대기(30) → IQC 검사완료 실행")
                    b4 = snap(bm)
                    r4 = SETIN.setinsp_complete(request=None, payload={
                        "rows": [{"maint_ymd": str(sr[0]).strip(), "maint_seq": int(sr[1])}], "user": "TESTBED"})
                    print("   검사완료: {}".format(str(r4)[:180]))
                    rep("IQC 검사완료", b4, snap(bm), "all3")
                elif str(sr[2]).strip() == '90':
                    print("   ⟹ 무검사품이라 입고 즉시 90(완료) — 위 '바코드입고' 에서 3층이 움직여야 정상")

    print("\n" + "=" * 92); print(" 종합"); print("=" * 92)
    for seg, n, ok in RESULT:
        print("   {:<20s} 움직인 층 {}/3  {}".format(seg, n, "✅" if ok else ("★" if ok is False else "")))

except SystemExit:
    pass
except Exception:
    traceback.print_exc()
finally:
    try: RAW.rollback(); print("\n[안전] rollback 완료 — DB 변경 0")
    except Exception: pass
    try: cur.close(); RAW.close()
    except Exception: pass
