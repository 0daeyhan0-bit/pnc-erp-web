# -*- coding: utf-8 -*-
"""잠정 스냅샷 stale 방지 검증 — 자재·생산·영업.

대표 확정(2026-09-08, CLOSE_REDESIGN §9-1): 일마감은 '잠정 스냅샷' 유지.
그 전제조건이 stale 방지다 — **잠정 스냅샷 일자 이전에 전표가 나중에 들어오면 낡는다.**

검증 시나리오 (도메인별, 전부 샌드박스·롤백):
  ① 최신 잠정 일마감에 지문을 기록  → stale 이면 안 된다
  ② 그 기초로 계산한 base_ymd 확보
  ③ 그 스냅샷 **이전 일자**에 전표 1건 주입 → stale 이어야 한다
  ④ 다시 기초를 구하면 그 스냅샷을 **건너뛰어야** 한다(base_ymd 가 더 과거로)
  ⑤ 롤백

★핵심은 "표시"가 아니라 "안 쓰는 것" — ④가 이 설계의 전부다.
   표시만 하고 계속 쓰면 사람이 잊는 순간 틀린 재고가 남는다.

실행: python _schema/snapshot_stale_verify.py
"""
import sys, os
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "PNC_ERP_Web", "backend"))
from routers import close

BASE_FN = {"MAT": lambda cur, t: close._mv_base(cur, t),
           "PRD": lambda cur, t: close._prd_base(cur, t),
           "SAL": lambda cur, t: close._sal_base(cur, t)}

INJECT = {
    "MAT": ("nx.PU_T_STOCK_MAINT",
            """INSERT INTO nx.PU_T_STOCK_MAINT(MAINT_YMD,MAINT_SEQ,MAINT_TAG,MAT_CODE,MAINT_QTY,
                                               CUST_CODE,WH_CUST_CODE,GAGONG_PROC_CODE,INSERT_USER_ID)
               VALUES(?,?,'9',?,5,'2268','Z99990','IS0001','STALEVFY')"""),
    "PRD": ("nx.PR_T_STOCK_MAINT_MAT",
            """INSERT INTO nx.PR_T_STOCK_MAINT_MAT(MAINT_YMD,MAINT_SEQ,MAINT_TAG,MAT_CODE,MAINT_QTY,
                                                   PART_CODE,INSERT_USER_ID)
               VALUES(?,?,'2',?,5,'P0002','STALEVFY')"""),
    "SAL": ("nx.SA_T_STOCK_MAINT",
            """INSERT INTO nx.SA_T_STOCK_MAINT(MAINT_YMD,MAINT_SEQ,MAINT_TAG,ITEM_CODE,MAINT_QTY,INSERT_USER_ID)
               VALUES(?,?,'2',?,5,'STALEVFY')"""),
}

ITEM_SQL = {
    "MAT": "SELECT TOP 1 MAT_CODE FROM nx.PU_T_STOCK_MAINT WHERE MAINT_TAG='9' AND MAINT_QTY>0",
    "PRD": "SELECT TOP 1 MAT_CODE FROM nx.PR_T_STOCK_MAINT_MAT WHERE MAINT_QTY<>0",
    "SAL": "SELECT TOP 1 ITEM_CODE FROM nx.SA_T_STOCK_MAINT WHERE MAINT_TAG='P' AND MAINT_QTY>0",
}


def run(dom):
    cn = close._nx_tx(); cur = cn.cursor()
    try:
        cur.execute("""SELECT TOP 1 period FROM nx.period_close
                        WHERE domain=? AND ptype='D' AND close_flag=1 ORDER BY period DESC""", dom)
        r = cur.fetchone()
        if not r:
            return (dom, "SKIP", "잠정 일마감 없음", "", "")
        per = r[0]
        target = close._next_ymd(per)

        # ① 지문 기록 → stale 아니어야 한다
        close._fp_store(cur, dom, "D", per)
        s1 = close._fp_stale(cur, dom, "D", per)

        # ② 기초 확보
        _st, base1, src1 = BASE_FN[dom](cur, target)

        # ③ 스냅샷 이전 일자에 전표 주입
        cur.execute(ITEM_SQL[dom]); it = cur.fetchone()[0]
        tbl, ins = INJECT[dom]
        cur.execute(f"SELECT ISNULL(MAX(MAINT_SEQ),19999)+1 FROM {tbl} WHERE MAINT_YMD=?", per)
        seq = cur.fetchone()[0]
        cur.execute(ins, per, seq, it)
        s2 = close._fp_stale(cur, dom, "D", per)

        # ④ 기초를 다시 구하면 그 스냅샷을 건너뛰어야 한다
        _st2, base2, src2 = BASE_FN[dom](cur, target)

        ok = (not s1) and s2 and (base2 != base1)
        note = f"주입전 stale={s1} · 주입후 stale={s2} · 기초 {base1} -> {base2}"
        return (dom, "PASS" if ok else "FAIL", note, src1, src2)
    except Exception as e:
        return (dom, "오류", str(e)[:90], "", "")
    finally:
        cn.rollback(); cn.close()


def main():
    print("잠정 스냅샷 stale 방지 검증 (샌드박스·롤백)\n")
    print(f"{'도메인':7s} {'판정':6s} 내용")
    print("-" * 96)
    bad = 0
    for dom in ("MAT", "PRD", "SAL"):
        d, verdict, note, s1, s2 = run(dom)
        if verdict not in ("PASS", "SKIP"):
            bad += 1
        print(f"{d:7s} {verdict:6s} {note}")
        if s1 or s2:
            print(f"{'':14s}기초출처: {s1}  ->  {s2}")
    print("-" * 96)
    print(f"\n*결과: 문제 {bad}건")
    print("(전 케이스 롤백 - 오염 0)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
