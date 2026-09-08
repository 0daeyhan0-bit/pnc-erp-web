# -*- coding: utf-8 -*-
"""전 구간 재고 흐름 TestBed — 자재입고·자재출고·판매·생산준비·생산실적·영업출하

  ★목적 (대표 지시 2026-09-08)
    "비슷한 테이블 중 엉뚱한 걸 쓰는지, 미러 연계가 잘못됐는지 다 확인해야 한다"
    "자재입고 시 자재이력이 안 나와서 ledger 를 추가했다 — 이런 문제가 또 있는지"

    ⟹ 각 쓰기를 실제로 실행하고, **재고 3층 전부**를 전/후로 재서
       "어느 층에 들어갔고 어느 층이 비었는가" 를 드러낸다.

         ① 원장(클린)  nx.stock_ledger
         ② 잔액        PU_T_MAT_STOCK_WH · PR_T_MAT_STOCK_WH · SA_T_ITEM_STOCK · PU_T_READY_STOCK
         ③ 미러이력    PU_T_STOCK_MAINT · PR_T_STOCK_MAINT_MAT · SA_T_STOCK_MAINT
         ④ 클린 병존   nx.sale_dtl (미러 SA_T_SALE_DTL 의 짝)

    한 층에만 들어가면 그 층만 보는 화면과 다른 층을 보는 화면의 값이 갈린다.

  ★안전장치
    · PARTNER_ERP_TEST3 단일 커넥션 · autocommit=False · **끝에서 무조건 rollback**
    · 라우터가 commit() 해도 무력화(NoCommitConn) → DB 확정 안 됨(오염 0)
    · 라이브 PARTNER_ERP 는 읽지도 쓰지도 않는다
"""
import sys, os, io, traceback
BE = r"c:\Users\박근민\Desktop\NEW_ERP_1\PNC_ERP_Web\backend"
sys.path.insert(0, BE); os.chdir(BE)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
import common, db_client, pyodbc

CS = (f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};'
      f'DATABASE=PARTNER_ERP_TEST3;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}')
RAW = pyodbc.connect(CS, autocommit=False)


class NoCommitConn:
    def __init__(self, cn):
        object.__setattr__(self, '_cn', cn)
        object.__setattr__(self, '_curs', [])
    def cursor(self):
        c = self._cn.cursor(); self._curs.append(c); return c
    def commit(self): pass
    def rollback(self): pass
    def close(self): pass      # ★라우터의 finally: cn.close() 무력화 — 공유 커넥션을 닫으면 뒤 사례가 다 죽는다
    def __getattr__(self, k): return getattr(self._cn, k)


SHARED = NoCommitConn(RAW)
common._nx = lambda: SHARED
common._nx_tx = lambda: SHARED

import routers.stock as STOCK
import routers.ready as READY
import routers.sales as SALES
for m in (STOCK, READY, SALES):
    if hasattr(m, "_nx"): m._nx = lambda: SHARED
    if hasattr(m, "_nx_tx"): m._nx_tx = lambda: SHARED

cur = RAW.cursor()
RESULT = []   # (구간, 층, 변동, 판정)


def title(t):
    print("\n" + "=" * 86); print(" " + t); print("=" * 86)


def q1(sql, *a):
    """★같은 트랜잭션·같은 커넥션에서 읽어야 라우터의 미확정 쓰기가 보인다.
       (다른 커넥션으로 읽으면 rollback 전이라 안 보여 '변동 없음'으로 오판한다 — 실제로 겪음)"""
    try:
        c = RAW.cursor()
        c.execute(sql, *a) if a else c.execute(sql)
        r = c.fetchone()
        v = float(r[0] or 0) if r else 0.0
        c.close()
        return v
    except Exception as e:
        print("      [조회오류] %s" % str(e)[:90]); return 0.0


# ─────────────────────────────────────────────────────────────
# 재고 3층 스냅샷 — 자재 축
# ─────────────────────────────────────────────────────────────
def snap_mat(mat, cc="Z99990", gpc="IS0001"):
    return {
        "①원장 stock_ledger(MAT)": q1(
            "SELECT ISNULL(SUM(MAINT_QTY),0) FROM nx.stock_ledger WHERE STOCK_POINT='MAT' AND MAT_CODE=?", mat),
        "②잔액 PU_T_MAT_STOCK_WH": q1(
            "SELECT ISNULL(SUM(STOCK_QTY),0) FROM nx.PU_T_MAT_STOCK_WH WHERE MAT_CODE=? AND CUST_CODE=? AND GAGONG_PROC_CODE=?", mat, cc, gpc),
        "③미러이력 PU_T_STOCK_MAINT": q1(
            "SELECT ISNULL(SUM(MAINT_QTY),0) FROM nx.PU_T_STOCK_MAINT WHERE MAT_CODE=?", mat),
    }


def snap_item(item):
    return {
        "①원장 stock_ledger(ASY)": q1(
            "SELECT ISNULL(SUM(MAINT_QTY),0) FROM nx.stock_ledger WHERE STOCK_POINT='ASY' AND ITEM_CODE=?", item),
        "②잔액 SA_T_ITEM_STOCK": q1(
            "SELECT ISNULL(SUM(STOCK_QTY),0) FROM nx.SA_T_ITEM_STOCK WHERE ITEM_CODE=?", item),
        "③미러이력 SA_T_STOCK_MAINT": q1(
            "SELECT ISNULL(SUM(MAINT_QTY),0) FROM nx.SA_T_STOCK_MAINT WHERE ITEM_CODE=?", item),
        "③미러출하 SA_T_SALE_DTL": q1(
            "SELECT ISNULL(SUM(SALE_QTY),0) FROM nx.SA_T_SALE_DTL WHERE ITEM_CODE=?", item),
        "④클린출하 nx.sale_dtl": q1(
            "SELECT ISNULL(SUM(sale_qty),0) FROM nx.sale_dtl WHERE item_code=?", item),
    }


def snap_ready(item, gpc):
    return {
        "①원장 stock_ledger(RDY)": q1(
            "SELECT ISNULL(SUM(MAINT_QTY),0) FROM nx.stock_ledger WHERE STOCK_POINT='RDY' AND ITEM_CODE=?", item),
        "②잔액 PU_T_READY_STOCK": q1(
            "SELECT ISNULL(SUM(STOCK_QTY),0) FROM nx.PU_T_READY_STOCK WHERE ITEM_CODE=? AND CUST_CODE='Z99990' AND PROC_GUBUN=?", item, gpc),
        "②잔액 PR_T_MAT_STOCK_WH": q1(
            "SELECT ISNULL(SUM(STOCK_QTY),0) FROM nx.PR_T_MAT_STOCK_WH WHERE PART_CODE=?", gpc),
        # ★2026-09-08 추가 — 레거시 정본 준비재고 이력(tag 1=등록·2=취소·A=소진)
        "③준비이력 PU_T_READY_STOCK_MAINT": q1(
            "SELECT ISNULL(SUM(MAINT_QTY),0) FROM nx.PU_T_READY_STOCK_MAINT WHERE ITEM_CODE=? AND ISNULL(PROC_GUBUN,'')=?", item, gpc),
        "③미러이력 PR_T_STOCK_MAINT_MAT": q1(
            "SELECT ISNULL(SUM(MAINT_QTY),0) FROM nx.PR_T_STOCK_MAINT_MAT WHERE ITEM_CODE=?", item),
    }


def report(seg, before, after, expect_note="", case=""):
    """층별 변동을 찍고, 안 움직인 층을 드러낸다"""
    tag = "%s%s" % (seg, (" / " + case) if case else "")
    print("\n  [%s] 재고 층별 변동" % tag)
    if expect_note:
        print("     기대: %s" % expect_note)
    moved, still = [], []
    for k in before:
        d = round(after.get(k, 0) - before.get(k, 0), 4)
        mark = "움직임" if abs(d) > 1e-9 else "  —   "
        print("       {}  {:<34s} {:>+16,.2f}".format(mark, k, d))
        (moved if abs(d) > 1e-9 else still).append(k)
    RESULT.append((tag, moved, still))
    return moved, still


def sp(cur_, sql, *a):
    """savepoint 로 사례별 격리 — 한 사례가 실패해도 다음 사례가 영향 안 받게"""
    try:
        cur_.execute(sql, *a) if a else cur_.execute(sql)
    except Exception:
        pass


try:
    # ══════════════════════════════════════════════════════════
    title("사전 — 병존 테이블 쌍 최신성 (엉뚱한 걸 쓰고 있는가)")
    PAIRS = [
        ("출하실적", "nx.SA_T_SALE_DTL", "SALE_YMD", "nx.sale_dtl", "sale_ymd"),
        ("품목계획", "nx.PR_T_PLAN_ITEM_DTL", "PLAN_YMD", "nx.plan_item_dtl", "plan_ymd"),
        ("파트계획", "nx.PR_T_PLAN_PART_DTL", "PLAN_YMD", "nx.plan_part_dtl", "plan_ymd"),
    ]
    for nm, mt, mc, ct, cc_ in PAIRS:
        mmax = None; cmax = None; mn = 0; cn_ = 0
        try:
            cur.execute("SELECT MAX(%s), COUNT(*) FROM %s WITH(NOLOCK)" % (mc, mt))
            r = cur.fetchone(); mmax, mn = r[0], r[1]
        except Exception as e: mmax = "ERR"
        try:
            cur.execute("SELECT MAX(%s), COUNT(*) FROM %s WITH(NOLOCK)" % (cc_, ct))
            r = cur.fetchone(); cmax, cn_ = r[0], r[1]
        except Exception as e: cmax = "ERR"
        flag = ""
        if str(mmax) != str(cmax): flag = "  ★최신일자 불일치"
        print("   %-8s 미러 %-26s max=%-8s %7s행 | 클린 %-20s max=%-8s %7s행%s"
              % (nm, mt, mmax, "{:,}".format(mn), ct, cmax, "{:,}".format(cn_), flag))

    # ══════════════════════════════════════════════════════════
    title("① 자재입고 — /api/matrecv/receive (발주분 입고 확정) · 다중 사례")
    cur.execute("""SELECT TOP 4 RTRIM(d.ITEM_CODE), RTRIM(d.PUR_YMD), d.PUR_SEQ, d.PUR_SEQ_ROW,
                          RTRIM(ISNULL(d.CUST_CODE,'')),
                          ISNULL(d.PUR_QTY,0)-ISNULL(d.IN_QTY,0)-ISNULL(d.CANCEL_QTY,0) remain
                     FROM nx.PU_T_PURCHASE_DTL d WITH(NOLOCK)
                    WHERE ISNULL(d.ITEM_CODE,'')<>''
                      AND ISNULL(d.PUR_QTY,0)-ISNULL(d.IN_QTY,0)-ISNULL(d.CANCEL_QTY,0) >= 5
                      AND ISNULL(d.IN_FINISH_FLAG,'0')='0'
                    ORDER BY d.PUR_YMD DESC""")
    recv_cases = [tuple(x) for x in cur.fetchall()]
    MAT_SEEN = []
    if not recv_cases:
        print("   ★시료 없음 — 발주 데이터를 못 찾음")
    for ci, rc in enumerate(recv_cases, 1):
        mat, pymd, pseq, prow, pcust = rc[0], rc[1], rc[2], rc[3], rc[4]
        RQ = min(5.0, float(rc[5] or 0))
        MAT_SEEN.append(mat)
        print("\n   [사례%d] 자재=%s  발주=%s-%s-%s  거래처=%s  잔량=%s → 입고 %s"
              % (ci, mat, pymd, pseq, prow, pcust, rc[5], RQ))
        b = snap_mat(mat)
        try:
            res = STOCK.matrecv_receive(payload={
                "ymd": "260908", "cust_code": pcust, "wh": "IS0001", "user": "TESTBED",
                "rows": [{"item": mat, "qty": RQ, "pur_ymd": pymd,
                          "pur_seq": pseq, "pur_seq_row": prow}]})
            print("      실행결과: %s" % str(res)[:170])
        except Exception as e:
            print("      ★실행오류: %s" % str(e)[:190])
        a = snap_mat(mat)
        report("자재입고", b, a,
               "원장·잔액·미러이력 3층 모두 +%s 여야 화면 간 값이 일치" % RQ,
               case="사례%d %s" % (ci, mat))

    # ══════════════════════════════════════════════════════════
    title("①-B 결함검증 — 품번 키 이름이 틀리면 어떻게 되는가")
    print("   프론트가 'item' 대신 'mat_code' 로 보내면? (레거시 화면·타 라우터는 mat_code 를 쓴다)")
    if recv_cases:
        rc = recv_cases[0]
        bmat = rc[0]
        b = snap_mat(bmat)
        try:
            res = STOCK.matrecv_receive(payload={
                "ymd": "260908", "cust_code": rc[4], "wh": "IS0001", "user": "TESTBED",
                "rows": [{"mat_code": bmat, "qty": 5, "pur_ymd": rc[1],
                          "pur_seq": rc[2], "pur_seq_row": rc[3]}]})
            print("      응답: %s" % str(res)[:150])
        except Exception as e:
            print("      실행오류: %s" % str(e)[:150])
        a = snap_mat(bmat)
        mv, st = report("결함검증", b, a,
                        "★품번이 빈 채로 통과하면 'ok:True' 인데 아무것도 안 들어간다(조용한 실패)",
                        case="mat_code 키로 전송")
        if not mv:
            print("      ★★확인됨 — 응답은 성공(ok:True)인데 재고 3층 어디에도 안 들어갔다.")
            print("         품번 빈값을 검증이 못 걸러낸다(stock.py:616 r.get('item')).")

    # ══════════════════════════════════════════════════════════
    title("② 자재출고 — /api/stock/save (screen=issue) · 다중 사례")
    # ★재고가 실제로 있는 자재로 골라야 출고가 통과한다(가드가 음수를 막는다)
    cur.execute("""SELECT TOP 3 RTRIM(MAT_CODE), SUM(STOCK_QTY)
                     FROM nx.PU_T_MAT_STOCK_WH WITH(NOLOCK)
                    WHERE CUST_CODE='Z99990' AND ISNULL(GAGONG_PROC_CODE,'')='IS0001'
                      AND ISNULL(STOCK_QTY,0) > 100 AND ISNULL(MAT_CODE,'')<>''
                    GROUP BY RTRIM(MAT_CODE) ORDER BY SUM(STOCK_QTY) DESC""")
    issue_mats = [(tuple(x)[0], float(tuple(x)[1] or 0)) for x in cur.fetchall()]
    for ci, (mat, have) in enumerate(issue_mats, 1):
        print("\n   [사례%d] 자재=%s (현재고 %s) 출고 5" % (ci, mat, have))
        b = snap_mat(mat)
        try:
            res = STOCK.stock_save(payload={
                "screen": "issue", "user": "TESTBED",
                "rows": [{"MAINT_YMD": "260908", "MAINT_TAG": "B", "MAT_CODE": mat,
                          "CUST_CODE": "Z99990", "GAGONG_PROC_CODE": "IS0001",
                          "qty": 5, "REMARKS": "TESTBED"}]})
            print("      실행결과: %s" % str(res)[:170])
        except Exception as e:
            print("      ★실행오류: %s" % str(e)[:190])
        a = snap_mat(mat)
        report("자재출고", b, a, "원장 −5. 잔액·미러이력도 따라가야 화면이 일치",
               case="사례%d %s" % (ci, mat))

    # ══════════════════════════════════════════════════════════
    title("③ 생산준비등록 — /api/ready/commit · 다중 사례")
    cur.execute("""SELECT TOP 40 RTRIM(d.assy_item_code) item, RTRIM(ISNULL(d.gagong_proc_code,'')) gpc,
                          MAX(RTRIM(ISNULL(d.plan_ymd,''))) ymd
                     FROM nx.plan_part_dtl d WITH(NOLOCK)
                    WHERE ISNULL(d.assy_item_code,'')<>'' AND ISNULL(d.gagong_proc_code,'')<>''
                    GROUP BY RTRIM(d.assy_item_code), RTRIM(ISNULL(d.gagong_proc_code,''))
                    ORDER BY MAX(RTRIM(ISNULL(d.plan_ymd,''))) DESC""")
    cands = [tuple(x) for x in cur.fetchall()]
    picks = []
    for c in cands:
        if len(picks) >= 3: break
        it, gp, ym = c[0], c[1], c[2]
        try:
            chk = READY.ready_setcheck(item=it, ymd=ym, qty=1)
        except Exception:
            continue
        if (chk.get("rows") or []) and float(chk.get("set_able") or 0) >= 1:
            picks.append(dict(item=it, gpc=gp, ymd=ym, able=float(chk["set_able"]),
                              nbom=len(chk["rows"])))
    if not picks:
        print("   ★세트가능 시료 없음 — 준비등록 구간 건너뜀")
    for ci, pk in enumerate(picks, 1):
        print("\n   [사례%d] 도번=%s 파트=%s 계획일=%s 세트가능=%s BOM=%d행"
              % (ci, pk["item"], pk["gpc"], pk["ymd"], pk["able"], pk["nbom"]))
        b = snap_ready(pk["item"], pk["gpc"])
        try:
            res = READY.ready_commit(payload={
                "mode": "register", "item": pk["item"], "gpc": pk["gpc"],
                "qty": 1, "ymd": pk["ymd"], "weld_print": False, "user": "TESTBED"})
            print("      실행결과: %s" % str(res)[:190])
        except Exception as e:
            print("      ★실행오류: %s" % str(e)[:230])
        a = snap_ready(pk["item"], pk["gpc"])
        report("생산준비등록", b, a,
               "준비재고 +, 자재 −. 원장(RDY)에도 남아야 원장 기준 화면과 일치",
               case="사례%d %s/%s" % (ci, pk["item"], pk["gpc"]))

    # ══════════════════════════════════════════════════════════
    title("④ 영업출하 확정 — /api/sale040/confirm")
    cur.execute("""SELECT TOP 4 RTRIM(s.ITEM_CODE), s.STOCK_QTY
                     FROM nx.SA_T_ITEM_STOCK s WITH(NOLOCK)
                    WHERE ISNULL(s.STOCK_QTY,0) > 50 AND ISNULL(s.ITEM_CODE,'')<>''
                    ORDER BY s.STOCK_QTY DESC""")
    sale_rows = [tuple(x) for x in cur.fetchall()]
    if not sale_rows:
        print("   ★재고 있는 완제품 없음")
    for ci, r2 in enumerate(sale_rows, 1):
        sitem, sqty = r2[0], float(r2[1] or 0)
        c2 = RAW.cursor()
        c2.execute("""SELECT TOP 1 RTRIM(WORK_ORDER), RTRIM(ISNULL(SPLIT_WORK_ORDER,''))
                        FROM nx.SA_T_SALE_DTL WITH(NOLOCK)
                       WHERE ITEM_CODE=? ORDER BY SALE_YMD DESC""", sitem)
        rw = c2.fetchone(); c2.close()
        wo = rw[0] if rw else ""
        swo = rw[1] if rw else ""
        print("\n   [사례%d] 도번=%s 현재고=%s 제번=%s" % (ci, sitem, sqty, wo))
        b = snap_item(sitem)
        try:
            res = SALES.sale040_confirm(payload={
                "ymd": "260908", "user": "TESTBED",
                "cells": [{"wo": wo, "swo": swo, "item": sitem, "qty": 3}]})
            print("      실행결과: %s" % str(res)[:190])
        except Exception as e:
            print("      ★실행오류: %s" % str(e)[:230])
        a = snap_item(sitem)
        report("영업출하", b, a,
               "미러출하 +3 · 잔액 −3. ★클린 nx.sale_dtl 이 안 움직이면 클린 기준 화면에서 안 보인다",
               case="사례%d %s" % (ci, sitem))

except Exception:
    print("\n★TestBed 중단"); traceback.print_exc()
finally:
    try: RAW.rollback(); print("\n[안전] rollback 완료 — DB 변경 0")
    except Exception: pass
    try: cur.close(); RAW.close()
    except Exception: pass

# ══════════════════════════════════════════════════════════════
print("\n" + "=" * 86)
print(" 종합 — 어느 층이 비었는가")
print("=" * 86)
for seg, moved, still in RESULT:
    print("\n  ■ %s" % seg)
    print("     들어간 층 : %s" % (", ".join(moved) if moved else "★없음(쓰기 실패 또는 미반영)"))
    print("     안 간 층  : %s" % (", ".join(still) if still else "(없음 — 전 층 일치)"))
