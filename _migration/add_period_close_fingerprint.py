# -*- coding: utf-8 -*-
"""nx.period_close 에 스냅샷 지문(fingerprint) 컬럼 추가 — 잠정 스냅샷 stale 방지.

★왜: 일마감이 '잠정'이 되면서(CLOSE_REDESIGN §3·§5) 그 일자 이전에 전표가 **나중에** 들어오면
   스냅샷이 낡는다. 훅(common.stock_changed) 42곳에 일자를 흘리는 방식은 한 곳만 빠져도
   구멍이라 채택하지 않았다 → **읽기 시점에 매번 지문을 대조**한다(§9-1 전제조건).

지문 = (행수, 수량합, 최근 INSERT, 최근 UPDATE)
  · 행수·수량합이 있어야 **삭제**도 잡힌다(삭제는 datetime 으로 안 잡힌다)
  · 창 = 직전 확정 월마감 다음날 ~ 스냅샷일 (월마감 구간은 규칙B로 잠겨 변할 수 없다)

멱등: 이미 있으면 건너뛴다. additive 라 기존 코드·데이터 무영향.
★nx.period_close 는 우리 신규 테이블(소문자)이라 r_delta_sync 재복제 대상이 아니다 → ALTER 안전.

실행: python _migration/add_period_close_fingerprint.py            # DRY
      python _migration/add_period_close_fingerprint.py --commit
"""
import sys, os
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "PNC_ERP_Web", "backend"))
from common import _nx, _nx_tx

COLS = [("src_rows", "bigint"), ("src_sum", "decimal(28,4)"),
        ("src_ins", "datetime"), ("src_upd", "datetime")]
COMMIT = "--commit" in sys.argv


def main():
    cn = _nx(); cur = cn.cursor()
    cur.execute("SELECT LOWER(name) FROM sys.columns WHERE object_id=OBJECT_ID('nx.period_close')")
    have = {r[0] for r in cur.fetchall()}
    cn.close()
    todo = [(c, t) for c, t in COLS if c not in have]
    print(f"nx.period_close 기존 컬럼 {len(have)}개 · 추가 대상 {len(todo)}개 -> {[c for c, _ in todo]}")
    if not todo:
        print("*이미 적용됨(멱등) - 할 일 없음")
        return 0
    if not COMMIT:
        for c, t in todo:
            print(f"   [DRY] ALTER TABLE nx.period_close ADD {c} {t} NULL")
        print("")
        print("--commit 을 붙이면 실제 적용")
        return 0
    cn = _nx_tx(); cur = cn.cursor()
    try:
        for c, t in todo:
            cur.execute(f"ALTER TABLE nx.period_close ADD {c} {t} NULL")
            print(f"   추가: {c} {t}")
        cn.commit()
        print("*적용 완료 (기존 행은 NULL = 지문없음 -> 판정에서 '알 수 없음'으로 취급)")
    finally:
        cn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
