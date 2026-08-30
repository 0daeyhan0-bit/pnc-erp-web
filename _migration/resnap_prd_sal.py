# -*- coding: utf-8 -*-
"""생산·영업 확정 스냅샷 재생성 (2026-08-29 · 대표 승인 '백업 없이 덮어써도 된다')

왜
  `_prd_price_bom` 의 사전필터가 `nx.bom` 을 봤는데 엔진은 `nx.bom_header` 를 쓴다.
  SUB·은납 반제품이 전부 스킵돼 **단가 0 → 재고금액에서 빠졌다**(용접만 +6,438만원).
  필터를 교정했으므로 **이미 확정된 스냅샷은 옛 값**이다 → 다시 만든다.

★연대순으로 돌린다 (필수)
  일마감은 `_prd_base` 로 **직전 확정 스냅샷**을 기초로 삼는다.
  순서를 지키지 않으면 옛 기초 위에 새 값을 쌓아 어긋난다.
    M 2606 → M 2607 → D 260801 → … → D 260828

사용
  python _migration/resnap_prd_sal.py            DRY-RUN(대상·현재값만)
  python _migration/resnap_prd_sal.py --commit   실제 재생성
  python _migration/resnap_prd_sal.py --commit --domain PRD
"""
import io
import os
import sys
import time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
_BE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "PNC_ERP_Web", "backend")
sys.path.insert(0, os.path.abspath(_BE))
os.chdir(os.path.abspath(_BE))

from common import _nx                                              # noqa: E402
from routers.close import _snap_prd, _snap_sal, _ledger_cache_clear  # noqa: E402

COMMIT = "--commit" in sys.argv
DOMS = ["PRD", "SAL"]
if "--domain" in sys.argv:
    DOMS = [sys.argv[sys.argv.index("--domain") + 1].upper()]


def snapshot_state(cur):
    cur.execute("""SELECT domain, ptype, period, COUNT(*), SUM(CAST(stock_amt AS float))
                     FROM nx.stock_snapshot WHERE domain IN ('PRD','SAL')
                    GROUP BY domain, ptype, period""")
    return {(str(a).strip(), str(b).strip(), str(c).strip()): (d, float(e or 0))
            for a, b, c, d, e in cur.fetchall()}


def main():
    cn = _nx()
    cur = cn.cursor()
    before = snapshot_state(cur)

    # ★연대순 — 월(2606→2607) 먼저, 그 다음 일(오름차순)
    cur.execute("""SELECT domain, ptype, period FROM nx.period_close
                    WHERE close_flag=1 AND domain IN ('PRD','SAL')""")
    todo = [(str(a).strip(), str(b).strip(), str(c).strip()) for a, b, c in cur.fetchall()]
    todo = [t for t in todo if t[0] in DOMS]
    todo.sort(key=lambda t: (t[0], 0 if t[1] == "M" else 1, t[2]))

    print("=" * 74)
    print(f"  확정 스냅샷 재생성   ({'COMMIT' if COMMIT else 'DRY-RUN'})   대상 {len(todo)}건")
    print("=" * 74)
    for d in DOMS:
        sub = [t for t in todo if t[0] == d]
        print(f"  {d}: 월 {sum(1 for t in sub if t[1]=='M')} · 일 {sum(1 for t in sub if t[1]=='D')}"
              f"  ({sub[0][2] if sub else '-'} ~ {sub[-1][2] if sub else '-'})")

    if not COMMIT:
        print("\n  현재 값(월마감):")
        for k, v in sorted(before.items()):
            if k[1] == "M":
                print(f"    {k[0]} {k[1]} {k[2]:<7} {v[0]:>6,}행 · {v[1]:>16,.0f}원")
        print("\n  DRY-RUN — 반영하려면 --commit")
        return

    t0 = time.time()
    done = []
    for i, (dom, pt, pe) in enumerate(todo, 1):
        s = time.time()
        try:
            fn = _snap_prd if dom == "PRD" else _snap_sal
            n, note = fn(cur, pt, pe)
            cn.commit()
            done.append((dom, pt, pe, n, None))
            print(f"  [{i:>2}/{len(todo)}] {dom} {pt} {pe:<7} {n:>6,}행  {time.time()-s:5.1f}s   {note}")
        except Exception as e:
            cn.rollback()
            done.append((dom, pt, pe, 0, str(e)[:90]))
            print(f"  [{i:>2}/{len(todo)}] {dom} {pt} {pe:<7} ★실패 — {str(e)[:90]}")

    _ledger_cache_clear()          # ★스냅샷이 바뀌었으니 수불장 캐시를 버린다
    after = snapshot_state(cur)

    print("\n" + "=" * 74)
    print(f"  완료 {sum(1 for x in done if not x[4])}/{len(todo)} · {time.time()-t0:.0f}초")
    fail = [x for x in done if x[4]]
    if fail:
        print(f"  ★실패 {len(fail)}건:")
        for x in fail:
            print(f"    {x[0]} {x[1]} {x[2]} — {x[4]}")

    print("\n  === 변화 (월마감) ===")
    for k in sorted(set(before) | set(after)):
        if k[1] != "M":
            continue
        b = before.get(k, (0, 0.0)); a = after.get(k, (0, 0.0))
        d = a[1] - b[1]
        print(f"    {k[0]} {k[1]} {k[2]:<7} {b[0]:>6,}→{a[0]:>6,}행 · "
              f"{b[1]:>15,.0f} → {a[1]:>15,.0f}  ({d:+,.0f})")
    for dom in DOMS:
        bs = sum(v[1] for k, v in before.items() if k[0] == dom)
        as_ = sum(v[1] for k, v in after.items() if k[0] == dom)
        print(f"\n  {dom} 전체 합계 {bs:,.0f} → {as_:,.0f}  ({as_-bs:+,.0f})")
    cn.close()


if __name__ == "__main__":
    main()
