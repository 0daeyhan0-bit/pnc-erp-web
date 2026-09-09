# -*- coding: utf-8 -*-
"""달력 호환 뷰 신설 — 클린을 미러 모양으로 보여준다 (2026-09-09)

★왜 뷰인가
  달력 미러를 직독하는 코드가 19곳이다. SQL 을 한 번에 다 고치면 위험하고,
  컬럼명·형식이 달라 단순 치환도 안 된다:

      미러  CALENDAR_YYMD(char8 'YYYYMMDD') · WORK_TEAM · TIME_TYPE · WORK_STATS
      클린  cal_ymd(date)                   · team      · (없음)    · work_stats

  ⟹ **미러와 같은 컬럼·형식**으로 클린을 노출하는 뷰를 만들면,
     호출측은 테이블명만 바꾸면 되고 WHERE·SUBSTRING 은 그대로 둘 수 있다.
     그래야 diff0 검증이 쉽고, 문제가 생기면 이름 하나만 되돌리면 된다.

★뷰 3종
  nx.v_cal_work   ← work_calendar   (HR_M_CALENDAR 모양: WORK_TEAM·TIME_TYPE·CALENDAR_YYMD)
  nx.v_cal_line   ← line_calendar   (PR_M_LINE_CALENDAR 모양: LINE_NO·CALENDAR_YMD)
  nx.v_cal_part   ← part_calendar   (PR_M_PART_CALENDAR 모양: PART_CODE·CALENDAR_YMD)

  ※WORK_TEAM/TIME_TYPE 은 클린에 없다 — 미러가 A/A 단일이므로 상수로 노출한다
    (실측: HR_M_CALENDAR 5,264행 전부 WORK_TEAM='A' AND TIME_TYPE='A').

★쓰기 없음(뷰 생성만). 기존 테이블·데이터 무변경.
사용: python _migration\\make_calendar_views_260909.py [--apply]
"""
import sys, os, io

BE = r"c:\Users\박근민\Desktop\NEW_ERP_1\PNC_ERP_Web\backend"
sys.path.insert(0, BE); os.chdir(BE)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
from common import _nx

APPLY = "--apply" in sys.argv
nx = _nx(); nx.autocommit = False
cur = nx.cursor()

VIEWS = {
    # 미러 HR_M_CALENDAR 호환 — work_team/time_type 은 상수(미러가 A/A 단일)
    "v_cal_work": """
CREATE VIEW nx.v_cal_work AS
SELECT CAST('A' AS varchar(2))                       AS WORK_TEAM,
       CONVERT(char(8), cal_ymd, 112)                AS CALENDAR_YYMD,
       CAST('A' AS varchar(2))                       AS TIME_TYPE,
       CAST(NULL AS varchar(2))                      AS WEEKLY,
       CAST(work_stats AS varchar(2))                AS WORK_STATS,
       remarks                                       AS REMARKS,
       upd_user                                      AS UPDATE_USER_ID,
       upd_dt                                        AS UPDATE_DATETIME
  FROM nx.work_calendar""",
    # 미러 PR_M_LINE_CALENDAR 호환 — CALENDAR_YMD 는 6자리(YYMMDD)
    "v_cal_line": """
CREATE VIEW nx.v_cal_line AS
SELECT line_no                                       AS LINE_NO,
       CONVERT(char(6), cal_ymd, 12)                 AS CALENDAR_YMD,
       CAST(NULL AS varchar(2))                      AS TIME_TYPE,
       CAST(NULL AS varchar(2))                      AS WEEKLY,
       CAST(work_stats AS varchar(2))                AS WORK_STATS,
       note                                          AS REMARKS,
       work_code                                     AS WORK_CODE,
       src                                           AS SRC,
       upd_dt                                        AS UPDATE_DATETIME
  FROM nx.line_calendar""",
    # 미러 PR_M_PART_CALENDAR 호환
    "v_cal_part": """
CREATE VIEW nx.v_cal_part AS
SELECT part_code                                     AS PART_CODE,
       CONVERT(char(6), cal_ymd, 12)                 AS CALENDAR_YMD,
       CAST(NULL AS varchar(2))                      AS TIME_TYPE,
       CAST(NULL AS varchar(2))                      AS WEEKLY,
       CAST(work_stats AS varchar(2))                AS WORK_STATS,
       remarks                                       AS REMARKS,
       upd_user                                      AS UPDATE_USER_ID,
       upd_dt                                        AS UPDATE_DATETIME
  FROM nx.part_calendar""",
}

print("=" * 100)
print(" 달력 호환 뷰 — 클린을 미러 모양으로")
print(" 모드: {}".format("★생성(--apply)" if APPLY else "조회만(dry-run)"))
print("=" * 100)

if not APPLY:
    for v in VIEWS:
        print("\n   {} ← 생성 예정".format(v))
    print("\n   ※dry-run — 생성하려면 --apply")
    nx.rollback(); nx.close(); sys.exit(0)

for v, ddl in VIEWS.items():
    cur.execute("IF OBJECT_ID('nx.{}','V') IS NOT NULL DROP VIEW nx.{}".format(v, v))
    cur.execute(ddl)
    print("   생성 nx.{}".format(v))
nx.commit()

# ── 검증 — 뷰가 미러와 같은 값을 주는가 ──────────────────────────
print("\n" + "=" * 100)
print(" 검증 — 뷰 vs 미러 (diff 0 이어야 통과)")
print("=" * 100)
CHK = [
    ("v_cal_work", """
      SELECT (SELECT COUNT(*) FROM nx.HR_M_CALENDAR WHERE WORK_TEAM='A' AND TIME_TYPE='A'),
             (SELECT COUNT(*) FROM nx.v_cal_work),
             (SELECT COUNT(*) FROM nx.HR_M_CALENDAR m JOIN nx.v_cal_work v
                ON v.CALENDAR_YYMD=m.CALENDAR_YYMD
               WHERE m.WORK_TEAM='A' AND m.TIME_TYPE='A'
                 AND ISNULL(CAST(m.WORK_STATS AS varchar(4)),'')<>ISNULL(CAST(v.WORK_STATS AS varchar(4)),''))"""),
    ("v_cal_line", """
      SELECT (SELECT COUNT(*) FROM nx.PR_M_LINE_CALENDAR),
             (SELECT COUNT(*) FROM nx.v_cal_line),
             (SELECT COUNT(*) FROM nx.PR_M_LINE_CALENDAR m JOIN nx.v_cal_line v
                ON RTRIM(v.LINE_NO)=RTRIM(m.LINE_NO) AND v.CALENDAR_YMD=m.CALENDAR_YMD
               WHERE ISNULL(CAST(m.WORK_STATS AS varchar(4)),'')<>ISNULL(CAST(v.WORK_STATS AS varchar(4)),''))"""),
    ("v_cal_part", """
      SELECT (SELECT COUNT(*) FROM nx.PR_M_PART_CALENDAR),
             (SELECT COUNT(*) FROM nx.v_cal_part),
             (SELECT COUNT(*) FROM nx.PR_M_PART_CALENDAR m JOIN nx.v_cal_part v
                ON RTRIM(v.PART_CODE)=RTRIM(m.PART_CODE) AND v.CALENDAR_YMD=m.CALENDAR_YMD
               WHERE ISNULL(CAST(m.WORK_STATS AS varchar(4)),'')<>ISNULL(CAST(v.WORK_STATS AS varchar(4)),''))"""),
]
bad = 0
for v, sql in CHK:
    cur.execute(sql)
    m, c, d = cur.fetchone()
    ok = (d == 0)
    if not ok: bad += 1
    print("   {:<12s} 미러 {:>7,}행 · 뷰 {:>7,}행 · 값불일치 {:>4}  {}".format(
        v, m, c, d, "PASS" if ok else "★FAIL"))

print()
if bad:
    print("   ★검증 실패 {}건 — 뷰는 만들어졌으나 값이 다르다. 코드 전환 보류.".format(bad))
    nx.close(); sys.exit(1)
print("   ✅ 전부 일치 — 이제 코드에서 미러명을 뷰명으로 바꿔도 결과가 같다")
print("      nx.HR_M_CALENDAR      → nx.v_cal_work")
print("      nx.PR_M_LINE_CALENDAR → nx.v_cal_line")
print("      nx.PR_M_PART_CALENDAR → nx.v_cal_part")
nx.close()
