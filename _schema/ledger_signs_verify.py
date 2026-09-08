# -*- coding: utf-8 -*-
"""수불장 부호·반영 전수 재검증 — 자재(MAT)·생산(PRD)·영업(SAL) × 입고/출고/반품/조정.

대표 지시(2026-09-08): "자재, 생산, 영업 관련 수불장 전체, 3부서의 입고, 출고, 반품 전체를 재검증".

방식 = **주입 → 측정**(읽기만으로 단정하지 않는다).
  ① 수불장 엔진(close._mat_ledger/_prd_ledger/_sal_ledger)으로 대상 품목 행을 측정
  ② 그 도메인의 실제 쓰기 경로가 넣는 것과 **같은 테이블·같은 태그·같은 부호**로 전표 1건 주입
  ③ 다시 측정 → 기말(잔량) 델타가 업무상 기대 방향과 같은가
  ④ **롤백**(무커밋) — 오염 0

★이 방식이 아니면 못 잡는다: 태그가 엔진에서 SUM(-QTY) 로 부호 반전되는 버킷에 들어가면
  전표·잔량 테이블엔 맞게 남는데 수불장에서만 반대로 잡힌다(2026-09-08 자재반품 실측 사례).

실행: python _schema/ledger_signs_verify.py
"""
import sys, os, datetime as _dt
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "PNC_ERP_Web", "backend"))
from routers import close

FR, TO = "260901", "260908"          # 짧은 창(속도). 계획이 바뀌어도 부호 판정엔 영향 없음.
QTY = 100.0

def _ledger(cur, dom):
    if dom == "MAT":
        rows, _b, _s = close._mat_ledger(cur, FR, TO, "0")
    elif dom == "PRD":
        rows, _b, _s = close._prd_ledger(cur, FR, TO)
    else:
        rows, _b, _s = close._sal_ledger(cur, FR, TO)
    return rows

def _find(rows, item):
    key = str(item).strip().upper()
    for r in rows:
        cd = str(r.get("cd") or r.get("item") or r.get("mat") or "").strip().upper()
        if cd == key:
            return r
    return None


def _sum_end(rows, item):
    """★품목의 **전 행(loc 포함) 기말 합**. PRD 수불장은 (품목, 파트) 그레인이라
       한 행만 보면 다른 파트에 들어간 이동을 놓쳐 '미반영'으로 오판한다."""
    key = str(item).strip().upper()
    tot, hit = 0.0, False
    for r in rows:
        cd = str(r.get("cd") or r.get("item") or r.get("mat") or "").strip().upper()
        if cd == key:
            v = _end_qty(r)
            if v is not None:
                tot += v; hit = True
    return tot if hit else None

def _end_qty(r):
    """기말 수량 — 엔진마다 키가 다르므로 후보를 순서대로 본다."""
    for k in ("eq", "sq", "qty", "end_qty", "endq"):
        if r and k in r:
            return float(r[k] or 0)
    return None

CASES = [
    # (도메인, 유형, 설명, 테이블, 주입컬럼dict, 기대방향)  기대: +1 재고증가 / -1 재고감소
    ("MAT", "입고", "자재입고관리 (tag 9, +수량)",      "PU", dict(tag="9",  qty=+QTY), +1),
    ("MAT", "출고", "자재출고관리 (tag B, −수량)",      "PU", dict(tag="B",  qty=-QTY), -1),
    ("MAT", "반품", "자재반품 (RT→'T' 매핑, −수량)",    "PU", dict(tag="T",  qty=-QTY), -1),
    ("SAL", "입고", "생산입고 (tag P, +수량)",          "SA", dict(tag="P",  qty=+QTY), +1),
    ("SAL", "출고", "출하등록 (tag J, −수량)",          "SA", dict(tag="J",  qty=-QTY), -1),
    # ★부호는 추측하지 말고 레거시 실적을 따른다 — nx.SA_T_STOCK_MAINT tag 'R' 전기간 1건이
    #   **양수 저장**(240115). 엔진이 outq += (−qty) 로 받으므로 양수 저장 = 재고 증가가 된다.
    #   (처음에 −수량으로 가정해 "부호반대 FAIL" 오판을 냈다 — 검증 케이스의 부호 가정을
    #    데이터로 확인하지 않으면 없는 결함을 만든다.)
    ("SAL", "반품", "출하반품 (tag R, +수량 저장)",     "SA", dict(tag="R",  qty=+QTY), +1),
    ("SAL", "조정", "제품재고조정 (tag 2, +수량)",      "SA", dict(tag="2",  qty=+QTY), +1),
    ("SAL", "조정", "제품재고조정 **웹 신규테이블**",   "WEBADJ", dict(tag="2", qty=+QTY), +1),
    ("MAT", "조정", "자재재고조정 (tag 2, +수량)",      "PU", dict(tag="2",  qty=+QTY), +1),
    # 생산창고 입·반납은 PU_T_STOCK_MAINT 를 to_gagong_proc_code(파트)로 읽는다.
    #   입고 = tag B + out_wh_gubun '1' / 반납 = tag T + out_wh_gubun '3' (엔진 WHERE 그대로)
    ("PRD", "입고", "자재→생산 이동 (tag B/gubun1, −수량)", "PUP", dict(tag="B", qty=-QTY, wh="1"), +1),
    ("PRD", "반품", "생산창고 반납 (tag T/gubun3, −수량)",  "PUP", dict(tag="T", qty=-QTY, wh="3"), -1),
    ("PRD", "출고", "생산사용 (tag 4, −수량)",          "PR", dict(tag="4",  qty=-QTY), -1),
    ("PRD", "조정", "생산재고조정 (tag 2, +수량)",      "PR", dict(tag="2",  qty=+QTY), +1),
]

def pick_item(cur, dom):
    rows = _ledger(cur, dom)
    for r in rows:
        if _end_qty(r) and abs(_end_qty(r)) > 500:
            return str(r.get("cd") or r.get("item") or r.get("mat")).strip(), rows
    return (str(rows[0].get("cd")).strip(), rows) if rows else (None, rows)

def inject(cur, kind, item, tag, qty, part, wh="1"):
    if kind == "PU":
        cur.execute("SELECT ISNULL(MAX(MAINT_SEQ),19999)+1 FROM nx.PU_T_STOCK_MAINT WHERE MAINT_YMD=? AND MAINT_SEQ>=20000", TO)
        seq = cur.fetchone()[0]
        cur.execute("""INSERT INTO nx.PU_T_STOCK_MAINT(MAINT_YMD,MAINT_SEQ,MAINT_TAG,MAT_CODE,MAINT_QTY,
                                                       CUST_CODE,WH_CUST_CODE,GAGONG_PROC_CODE,INSERT_USER_ID)
                       VALUES(?,?,?,?,?,'2268','Z99990','IS0001','SIGNVFY')""", TO, seq, tag, item, qty)
    elif kind == "PUP":
        cur.execute("SELECT ISNULL(MAX(MAINT_SEQ),19999)+1 FROM nx.PU_T_STOCK_MAINT WHERE MAINT_YMD=? AND MAINT_SEQ>=20000", TO)
        seq = cur.fetchone()[0]
        cur.execute("""INSERT INTO nx.PU_T_STOCK_MAINT(MAINT_YMD,MAINT_SEQ,MAINT_TAG,MAT_CODE,MAINT_QTY,
                                                       CUST_CODE,WH_CUST_CODE,GAGONG_PROC_CODE,
                                                       TO_GAGONG_PROC_CODE,OUT_WH_GUBUN,INSERT_USER_ID)
                       VALUES(?,?,?,?,?,'2268','Z99990','IS0001',?,?,'SIGNVFY')""",
                    TO, seq, tag, item, qty, part, wh)
    elif kind == "SA":
        cur.execute("SELECT ISNULL(MAX(MAINT_SEQ),19999)+1 FROM nx.SA_T_STOCK_MAINT WHERE MAINT_YMD=? AND MAINT_SEQ>=20000", TO)
        seq = cur.fetchone()[0]
        cur.execute("""INSERT INTO nx.SA_T_STOCK_MAINT(MAINT_YMD,MAINT_SEQ,MAINT_TAG,ITEM_CODE,MAINT_QTY,INSERT_USER_ID)
                       VALUES(?,?,?,?,?,'SIGNVFY')""", TO, seq, tag, item, qty)
    elif kind == "PR":
        cur.execute("SELECT ISNULL(MAX(MAINT_SEQ),19999)+1 FROM nx.PR_T_STOCK_MAINT_MAT WHERE MAINT_YMD=? AND MAINT_SEQ>=20000", TO)
        seq = cur.fetchone()[0]
        cur.execute("""INSERT INTO nx.PR_T_STOCK_MAINT_MAT(MAINT_YMD,MAINT_SEQ,MAINT_TAG,MAT_CODE,MAINT_QTY,
                                                           PART_CODE,INSERT_USER_ID)
                       VALUES(?,?,?,?,?,?,'SIGNVFY')""", TO, seq, tag, item, qty, part or "P0002")
    elif kind == "WEBADJ":
        cur.execute("SELECT ISNULL(MAX(maint_seq),19999)+1 FROM nx.prod_stock_adjust WHERE maint_ymd=?", TO)
        seq = cur.fetchone()[0]
        cur.execute("""INSERT INTO nx.prod_stock_adjust(maint_ymd,maint_seq,maint_tag,item_code,maint_qty,insert_user_id)
                       VALUES(?,?,?,?,?,'SIGNVFY')""", TO, seq, tag, item, qty)

def main():
    cn0 = close._nx(); c0 = cn0.cursor()
    items = {}
    for dom in ("MAT", "PRD", "SAL"):
        it, rows = pick_item(c0, dom)
        items[dom] = it
        print(f"[{dom}] 대상품목 {it} · 수불장 행 {len(rows):,}")
    cn0.close()
    print()
    print(f"{'도메인':6s} {'유형':4s} {'검증 내용':38s} {'기말Δ':>10s} {'기대':>5s}  판정")
    print("─" * 92)
    fails = []
    for dom, kind_nm, desc, tbl, kw, expect in CASES:
        item = items[dom]
        cn = close._nx_tx(); cur = cn.cursor()
        try:
            bq = _sum_end(_ledger(cur, dom), item)
            inject(cur, tbl, item, kw["tag"], kw["qty"], "P0002", kw.get("wh", "1"))
            aq = _sum_end(_ledger(cur, dom), item)
            if bq is None or aq is None:
                verdict, d = "SKIP(행없음)", 0.0
            else:
                d = aq - bq
                if abs(d) < 1e-6:
                    verdict = "★FAIL 미반영"
                elif (d > 0) == (expect > 0):
                    verdict = "PASS"
                else:
                    verdict = "★FAIL 부호반대"
            print(f"{dom:6s} {kind_nm:4s} {desc:38s} {d:+10.1f} {('증가' if expect>0 else '감소'):>5s}  {verdict}")
            if verdict.startswith("★"):
                fails.append((dom, kind_nm, desc, d, expect, verdict))
        except Exception as e:
            print(f"{dom:6s} {kind_nm:4s} {desc:38s} {'':>10s} {'':>5s}  오류 {str(e)[:60]}")
            fails.append((dom, kind_nm, desc, 0, expect, "오류"))
        finally:
            cn.rollback(); cn.close()
    print("─" * 92)
    print(f"\n★결과: 전체 {len(CASES)}건 · 문제 {len(fails)}건")
    for f in fails:
        print(f"   - [{f[0]}/{f[1]}] {f[2]} → {f[5]} (Δ{f[3]:+.1f}, 기대 {'증가' if f[4]>0 else '감소'})")
    print("\n(전 케이스 롤백 — 오염 0)")

if __name__ == "__main__":
    main()
