# -*- coding: utf-8 -*-
"""추가계획(생산계획추가입력) 전체 재동기화 — nx.prod_plan_input ← 레거시 PR_T_PLAN_INPUT.

왜 필요한가(2026-08-31 실측):
  기존 `_schema/sync_prod_plan_input.py` 는 **NOT EXISTS 로 추가만** 한다(멱등 INSERT).
  그래서 레거시에서 **일자가 바뀌거나 삭제된 건**이 웹에 옛 상태로 남는다.
  실측 차이(plan_ymd >= 260801):
      레거시 1,179행 / 웹 1,178행 · 수량은 500,339 로 **동일**
      레거시에만 4키 · 웹에만 3키 · 수량불일치 3키
    내용은 전부 "같은 제번인데 계획일자가 다름" —
      레거시 260907 WO1093226SVC  ↔  웹 260831 (같은 제번·수량 10)
      레거시 260911 WO1088404KS   ↔  웹 260831 (같은 제번·수량 300)
    ⟹ 레거시가 계획일자를 옮겼는데 웹은 옛 날짜를 그대로 들고 있다.
    이 상태로 편성을 돌리면 A/S·긴급 계획이 엉뚱한 날에 잡혀 레거시와 대사가 안 된다.

안전성:
  · 웹 직접입력분 = src IN ('web','web-bulk') = **0행**(2026-08-31 확인) → 전량 교체 안전.
    (upd_user 의 사람 이름은 레거시 원본 등록자를 그대로 옮긴 값이지 웹 입력분이 아니다.)
  · 그래도 web/web-bulk 는 **보존**한다 — 나중에 웹으로 입력한 뒤 이 스크립트를 다시 돌려도
    사용자 입력이 날아가지 않게. (CLAUDE.md §1-3 정신: 근거 스코프로만 지운다)
  · 라이브 PARTNER_ERP 는 **읽기만** 한다(§1-1).

사용:
  python resync_prod_plan_input.py           # 미리보기(변경 안 함)
  python resync_prod_plan_input.py --commit  # 실제 반영
"""
import sys, io

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

sys.path.insert(0, r'c:\Users\박근민\Desktop\NEW_ERP_1\PNC_ERP_Web\backend')
sys.path.insert(0, r'c:\Users\박근민\Desktop\New_ERP')
from common import _conn, _nx_tx          # _conn=라이브 RO가드 / _nx_tx=nx 쓰기

COMMIT = '--commit' in sys.argv
SRC = "PARTNER_ERP.dbo.PR_T_PLAN_INPUT"   # 레거시 원본(읽기전용)
DST = "nx.prod_plan_input"                # 웹 정본

# 대사 키 = 편성이 실제로 구분하는 단위
KEY_N = "LTRIM(RTRIM(ISNULL(plan_ymd,''))), LTRIM(RTRIM(ISNULL(work_order,''))), " \
        "LTRIM(RTRIM(ISNULL(item_code,''))), LTRIM(RTRIM(ISNULL(line_no,''))), " \
        "LTRIM(RTRIM(ISNULL(output_hm,'')))"
KEY_L = "LTRIM(RTRIM(ISNULL(PLAN_YMD,''))), LTRIM(RTRIM(ISNULL(WORK_ORDER,''))), " \
        "LTRIM(RTRIM(ISNULL(ITEM_CODE,''))), LTRIM(RTRIM(ISNULL(LINE_NO,''))), " \
        "LTRIM(RTRIM(ISNULL(OUTPUT_HM,'')))"


def snap(cur, sql, *p):
    cur.execute(sql, *p)
    return cur.fetchone()


def main():
    print("=" * 74)
    print(f"추가계획 재동기화  {SRC} → {DST}   [{'실행' if COMMIT else '미리보기'}]")
    print("=" * 74)

    # ── 1) 레거시 원본을 통째로 읽어온다(읽기전용 커넥션) ──
    lc = _conn(); lcu = lc.cursor()
    lcu.execute(f"""SELECT LTRIM(RTRIM(ISNULL(PLAN_YMD,''))), LTRIM(RTRIM(ISNULL(LINE_NO,''))),
                           LTRIM(RTRIM(ISNULL(ITEM_CODE,''))), LTRIM(RTRIM(ISNULL(OUTPUT_HM,''))),
                           CAST(ISNULL(PLAN_QTY,0) AS int),
                           LTRIM(RTRIM(ISNULL(WORK_ORDER,''))), LTRIM(RTRIM(ISNULL(WORK_CODE,''))),
                           LTRIM(RTRIM(ISNULL(PROD_TAG,''))), LTRIM(RTRIM(ISNULL(REMARKS,''))),
                           LTRIM(RTRIM(ISNULL(INSERT_USER_ID,'')))
                      FROM {SRC} WITH(NOLOCK)""")
    src_rows = lcu.fetchall()
    lc.close()
    print(f"\n[1] 레거시 원본 {len(src_rows):,}행 읽음")

    cn = _nx_tx(); cur = cn.cursor()
    try:
        # ── 2) 반영 전 상태 ──
        b_all = snap(cur, f"SELECT COUNT(*) FROM {DST}")[0]
        b_web = snap(cur, f"SELECT COUNT(*) FROM {DST} WHERE ISNULL(src,'') IN ('web','web-bulk')")[0]
        b_fut = snap(cur, f"SELECT COUNT(*), ISNULL(SUM(CAST(plan_qty AS bigint)),0) "
                          f"FROM {DST} WHERE plan_ymd>='260801'")
        print(f"[2] 반영 전  전체 {b_all:,}행 · 웹입력(보존대상) {b_web:,}행 "
              f"· 260801~ {b_fut[0]:,}행/{b_fut[1]:,}")

        if not COMMIT:
            # 미리보기 = 차이만 계산하고 끝
            cur.execute(f"""SELECT COUNT(*) FROM {DST} n
                             WHERE ISNULL(n.src,'') NOT IN ('web','web-bulk')
                               AND NOT EXISTS (SELECT 1 FROM {SRC} s WITH(NOLOCK)
                                    WHERE LTRIM(RTRIM(ISNULL(s.PLAN_YMD,'')))=LTRIM(RTRIM(ISNULL(n.plan_ymd,'')))
                                      AND LTRIM(RTRIM(ISNULL(s.WORK_ORDER,'')))=LTRIM(RTRIM(ISNULL(n.work_order,'')))
                                      AND LTRIM(RTRIM(ISNULL(s.ITEM_CODE,'')))=LTRIM(RTRIM(ISNULL(n.item_code,'')))
                                      AND LTRIM(RTRIM(ISNULL(s.LINE_NO,'')))=LTRIM(RTRIM(ISNULL(n.line_no,'')))
                                      AND LTRIM(RTRIM(ISNULL(s.OUTPUT_HM,'')))=LTRIM(RTRIM(ISNULL(n.output_hm,''))))""")
            gone = cur.fetchone()[0]
            print(f"\n  재이관 시 사라질 행(레거시에 없음) : {gone:,}")
            print(f"  재이관 후 예상 전체               : {len(src_rows) + b_web:,}행")
            print("\n  ※ 미리보기 — 아무것도 바꾸지 않았습니다. 실제 반영은 --commit")
            cn.rollback()
            return

        # ── 3) 전량 교체(웹 입력분만 남긴다) ──
        cur.execute(f"DELETE FROM {DST} WHERE ISNULL(src,'') NOT IN ('web','web-bulk')")
        deleted = cur.rowcount
        print(f"[3] 레거시 유래분 {deleted:,}행 삭제(웹 입력분 {b_web:,}행 보존)")

        # ── 4) 레거시 현재 상태를 그대로 적재 ──
        cur.fast_executemany = True
        cur.executemany(
            f"""INSERT INTO {DST}
                (plan_ymd,line_no,item_code,output_hm,plan_qty,work_order,work_code,prod_tag,
                 remarks,src,upd_user,upd_dt)
                VALUES(?,?,?,?,?,?,?,?,?,'sync',?,GETDATE())""",
            [(r[0], r[1] or None, r[2] or None, r[3] or None, int(r[4] or 0),
              r[5] or None, r[6] or None, r[7] or None, r[8] or None, (r[9] or 'legacy')[:20])
             for r in src_rows])
        print(f"[4] 레거시 현재 상태 {len(src_rows):,}행 적재")

        # ── 5) 반영 후 검증 ──
        a_all = snap(cur, f"SELECT COUNT(*) FROM {DST}")[0]
        a_fut = snap(cur, f"SELECT COUNT(*), ISNULL(SUM(CAST(plan_qty AS bigint)),0) "
                          f"FROM {DST} WHERE plan_ymd>='260801'")
        print(f"[5] 반영 후  전체 {a_all:,}행 · 260801~ {a_fut[0]:,}행/{a_fut[1]:,}")
        cn.commit()
        print("\n  ✅ 커밋 완료")
    except Exception as e:
        cn.rollback()
        print(f"\n  ★실패 — 롤백했습니다: {e}")
        raise
    finally:
        cn.close()


if __name__ == '__main__':
    main()
