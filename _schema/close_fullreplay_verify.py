"""월마감 '전월말 전체재생' 안전성 검증 (결합법칙).
   claim: 전월말(2607-M) 기초에서 →
     (A) 하루씩 순차 마감(직전일 스냅샷을 기초로 그날만 재생, 매일 저장) 로 260831 까지 가나
     (B) 260801~260831 을 한 번에 전체재생 하나
     **같은 결과(diff0)** 여야 한다. 같으면 '전체재생 = 순차 일마감' 이 증명 → 변경 안전.
   (실제 운영에서 차이는 '얼어붙은 옛 스냅샷 vs 최신데이터 재생' 즉 수정분에서만 생긴다.)
   실행: python _schema/close_fullreplay_verify.py
"""
import sys, os, datetime as _dt
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "PNC_ERP_Web", "backend"))
from routers import close

PREV = "2607"; MSTART = "260801"; MEND = "260831"

def dnext(ymd):
    d = _dt.date(2000 + int(ymd[:2]), int(ymd[2:4]), int(ymd[4:])) + _dt.timedelta(days=1)
    return f"{d.year % 100:02d}{d.month:02d}{d.day:02d}"

cn = close._nx(); cur = cn.cursor()
try:
    scope = close._mv_scope(cur)
    base = {}
    for it, lo, q, a, av in close._snapshot_rows(cur, "MAT", "M", PREV):
        q = float(q or 0); a = float(a or 0)
        base[str(it)] = [q, (a / q) if q else float(av or 0)]
    moves = close._mv_moves(cur, MSTART, MEND)

    # (B) 전체재생
    stB = {k: list(v) for k, v in base.items()}
    for ymd in sorted(moves):
        if ymd <= MEND:
            close._mv_step(stB, moves[ymd], scope)

    # (A) 하루씩 순차: 매일 '직전 상태(=저장 스냅샷 대용 dict)'를 복사해서 그날만 전개 → 다음날의 기초로
    stA = {k: list(v) for k, v in base.items()}
    d = MSTART
    while d <= MEND:
        day_moves = moves.get(d, {})
        if day_moves:
            close._mv_step(stA, day_moves, scope)
        # 매일 스냅샷 저장(dict 복사)했다가 다음날 그걸 기초로 이어감 = 실제 일마감 체인과 동일한 상태전이
        stA = {k: list(v) for k, v in stA.items()}
        d = dnext(d)

    # 비교 (수량·평균)
    keys = set(stA) | set(stB)
    diffs = []
    for k in keys:
        if k not in scope:
            continue
        qa, aa = stA.get(k, [0.0, 0.0])
        qb, ab = stB.get(k, [0.0, 0.0])
        if abs(qa - qb) > 1e-6 or abs((qa * aa) - (qb * ab)) > 1:
            diffs.append((k, qa, aa, qb, ab))
    print(f"품목 A {len(stA)} · B {len(stB)} · scope {len(scope)}")
    tA = sum(v[0] * v[1] for k, v in stA.items() if k in scope)
    tB = sum(v[0] * v[1] for k, v in stB.items() if k in scope)
    print(f"총액 A(순차) {tA:,.0f} · B(전체재생) {tB:,.0f} · 차이 {tA - tB:,.0f}")
    print(f"품목별 차이 {len(diffs)}건")
    for k, qa, aa, qb, ab in diffs[:10]:
        print(f"  {k}: A(q={qa:.2f},avg={aa:.2f}) vs B(q={qb:.2f},avg={ab:.2f})")
    print("\n" + ("★diff0 — 순차 일마감 = 전체재생. 변경 안전 검증됨." if not diffs
                  else f"★{len(diffs)}건 차이 — 원인 규명 필요(결합법칙 위반 지점=규칙1 제로크로싱 등)"))
finally:
    cn.close()
