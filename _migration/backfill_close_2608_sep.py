"""마감 백필 — 2608 월마감 + 8월잔여/9월 일마감(→260904).
   일일 영업/매입 현황(재고 기초/기말)이 9월에 260830 스냅샷으로 얼어붙어 8월과 동일하게 나오는 문제 해소.
   원인: nx.stock_snapshot 에 2608 월마감·9월 일마감이 없어 화면이 옛 스냅샷으로 폴백.
   방법: close.close_run() 을 순서대로 호출(모든 가드·원자성 그대로, HTTP auth 미들웨어만 우회).
   멱등: 이미 마감된 기간은 409 로 건너뜀. 되돌리기 = /api/close/cancel.
   실행: python _migration/backfill_close_2608_sep.py            # DRY(계획만)
         python _migration/backfill_close_2608_sep.py --commit   # 실제 마감
"""
import sys, os, datetime as _dt
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "PNC_ERP_Web", "backend"))
from routers import close
from fastapi import HTTPException

COMMIT = "--commit" in sys.argv
USER = "admin"          # close 권한자(시스템관리자) — period_close close_user 이력 확인
END_D = "260904"        # 9월 조회 종료일까지
DOMAINS = ["MAT", "PRD", "SAL"]


def _dnext(ymd):
    d = _dt.date(2000 + int(ymd[:2]), int(ymd[2:4]), int(ymd[4:])) + _dt.timedelta(days=1)
    return f"{d.year % 100:02d}{d.month:02d}{d.day:02d}"


def _last_closed_d(cur, dom):
    cur.execute("""SELECT MAX(period) FROM nx.period_close
                   WHERE domain=? AND ptype='D' AND close_flag=1""", dom)
    return cur.fetchone()[0]


def build_plan():
    """도메인별 (ptype, period) 순서 리스트. D=마지막마감+1 ~ 260904, 그다음 2608 M."""
    cn = close._nx(); cur = cn.cursor()
    plan = []
    for dom in DOMAINS:
        last = _last_closed_d(cur, dom)
        d = _dnext(last) if last else END_D
        days = []
        while d <= END_D:
            days.append(d); d = _dnext(d)
        for p in days:
            plan.append((dom, "D", p))
        plan.append((dom, "M", "2608"))   # 8월 월마감(9월 기초)
    cn.close()
    return plan


def main():
    plan = build_plan()
    print(f"=== 마감 백필 계획 (총 {len(plan)}건) · COMMIT={COMMIT} ===")
    for dom, t, p in plan:
        print(f"  {close.DOMAINS[dom]}({dom}) {'일' if t=='D' else '월'}마감 {p}")
    if not COMMIT:
        print("\n[DRY] 실행하려면 --commit")
        return
    print("\n=== 실행 ===")
    ok = skip = fail = 0
    for dom, t, p in plan:
        try:
            r = close.close_run({"domain": dom, "ptype": t, "period": p, "user": USER})
            ok += 1
            print(f"  ✅ {close.DOMAINS[dom]} {t}{p} · {r.get('msg','')}")
        except HTTPException as e:
            if e.status_code == 409:      # 이미 마감 — 멱등 건너뜀
                skip += 1
                print(f"  ⏭  {close.DOMAINS[dom]} {t}{p} · 이미 마감(skip)")
            else:
                fail += 1
                print(f"  ❌ {close.DOMAINS[dom]} {t}{p} · {e.status_code} {e.detail}")
                print("     ★가드 실패 — 중단(순서/미래/권한 확인)")
                break
        except Exception as e:
            fail += 1
            print(f"  ❌ {close.DOMAINS[dom]} {t}{p} · {type(e).__name__}: {str(e)[:120]}")
            break
    print(f"\n결과: 성공 {ok} · 건너뜀 {skip} · 실패 {fail}")


if __name__ == "__main__":
    main()
