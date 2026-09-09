# -*- coding: utf-8 -*-
"""달력 클린 동기화 — 미러 → 클린 (2026-09-09)

★왜 필요한가 (실측 경위)
  클린 달력은 **2026-07-23 에 미러를 복사해 만든 스냅샷**이고, 그 뒤 레거시에서
  달력을 고친 것이 클린에 안 넘어왔다.

    work_calendar  2026-08-28  클린 ws=1 (upd=MIGRATION 07-23)
                               미러 ws=4 (upd=조상협  08-20)   ← 레거시에서 휴무로 바뀜
    part_calendar  7/31·8/17·8/26 에 미러에만 12건(전부 ws=4 휴무)

  그동안은 코드 19곳이 **미러를 직독**해서 문제가 안 드러났다.
  ⟹ 코드를 클린으로 돌리기 **전에** 클린을 최신으로 맞춰야 한다.
     안 그러면 조상협님이 8월에 지정한 휴무가 사라진다.

★안전 원칙
  · 라이브는 읽지 않는다(미러 nx.* 만 읽는다). 쓰기는 nx 클린뿐(§1-1)
  · 근거키 스코프 UPDATE/INSERT 만. DELETE 없음(§1-3)
  · ★웹 입력분 보호 — line_calendar 의 src='MANUAL'·'LG' 는 건드리지 않는다
    (실측: 9/24·9/25 가 MANUAL. 미러로 덮으면 웹에서 지정한 값이 날아간다)
  · --apply 없으면 조회만(dry-run)

사용:
    python _migration\\sync_calendar_260909.py            # dry-run
    python _migration\\sync_calendar_260909.py --apply    # 반영
"""
import sys, os, io, datetime

BE = r"c:\Users\박근민\Desktop\NEW_ERP_1\PNC_ERP_Web\backend"
sys.path.insert(0, BE); os.chdir(BE)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
from common import _nx

S = "PARTNER_ERP_TEST3.nx"
STAMP = datetime.datetime.now().strftime("%y%m%d_%H%M")
APPLY = "--apply" in sys.argv

nx = _nx(); nx.autocommit = False
cur = nx.cursor()

print("=" * 100)
print(" 달력 클린 동기화 — 미러 → 클린")
print(" 모드: {}".format("★실제 반영(--apply)" if APPLY else "조회만(dry-run)"))
print("=" * 100)

# ── 1) work_calendar 값 갱신 ────────────────────────────────────
cur.execute("""
SELECT SUBSTRING(m.CALENDAR_YYMD,3,6) ymd6, CONVERT(varchar(10),c.cal_ymd,120) d,
       CAST(c.work_stats AS varchar(4)) old_ws, CAST(m.WORK_STATS AS varchar(4)) new_ws,
       ISNULL(c.upd_user,''), ISNULL(m.UPDATE_USER_ID,'')
  FROM {S}.HR_M_CALENDAR m WITH(NOLOCK)
  JOIN {S}.work_calendar c WITH(NOLOCK) ON FORMAT(c.cal_ymd,'yyMMdd')=SUBSTRING(m.CALENDAR_YYMD,3,6)
 WHERE m.WORK_TEAM='A' AND m.TIME_TYPE='A'
   AND ISNULL(CAST(m.WORK_STATS AS varchar(4)),'') <> ISNULL(CAST(c.work_stats AS varchar(4)),'')
 ORDER BY 1""".format(S=S))
wc_upd = [tuple(x) for x in cur.fetchall()]

print("\n① 근무달력(work_calendar) 값 갱신 — {}건".format(len(wc_upd)))
for r in wc_upd:
    print("   {}  {} → {}   (클린 upd={} / 미러 upd={})".format(
        r[1], str(r[2] or "-").strip(), str(r[3] or "-").strip(),
        str(r[4]).strip() or "-", str(r[5]).strip() or "-"))

# ── 2) part_calendar 신규 ───────────────────────────────────────
cur.execute("""
SELECT RTRIM(m.PART_CODE) pc, m.CALENDAR_YMD ymd6, CAST(m.WORK_STATS AS varchar(4)) ws
  FROM {S}.PR_M_PART_CALENDAR m WITH(NOLOCK)
 WHERE NOT EXISTS(SELECT 1 FROM {S}.part_calendar c WITH(NOLOCK)
                   WHERE RTRIM(c.part_code)=RTRIM(m.PART_CODE)
                     AND FORMAT(c.cal_ymd,'yyMMdd')=m.CALENDAR_YMD)
 ORDER BY m.CALENDAR_YMD, m.PART_CODE""".format(S=S))
pc_new = [tuple(x) for x in cur.fetchall()]

print("\n② 공장운영달력(part_calendar) 신규 — {}건".format(len(pc_new)))
for r in pc_new:
    print("   파트={:<8s} {} ws={}".format(str(r[0]), str(r[1]), str(r[2] or "-").strip()))

# ── 3) part_calendar 값 갱신 ────────────────────────────────────
cur.execute("""
SELECT RTRIM(m.PART_CODE) pc, m.CALENDAR_YMD ymd6,
       CAST(c.work_stats AS varchar(4)) old_ws, CAST(m.WORK_STATS AS varchar(4)) new_ws
  FROM {S}.PR_M_PART_CALENDAR m WITH(NOLOCK)
  JOIN {S}.part_calendar c WITH(NOLOCK)
    ON RTRIM(c.part_code)=RTRIM(m.PART_CODE) AND FORMAT(c.cal_ymd,'yyMMdd')=m.CALENDAR_YMD
 WHERE ISNULL(CAST(m.WORK_STATS AS varchar(4)),'')<>ISNULL(CAST(c.work_stats AS varchar(4)),'')
 ORDER BY 2,1""".format(S=S))
pc_upd = [tuple(x) for x in cur.fetchall()]
print("\n③ 공장운영달력 값 갱신 — {}건".format(len(pc_upd)))
for r in pc_upd[:20]:
    print("   파트={:<8s} {} {} → {}".format(
        str(r[0]), str(r[1]), str(r[2] or "-").strip(), str(r[3] or "-").strip()))

# ── 4) line_calendar — 미러 대비 결손/불일치 (MANUAL·LG 보호) ──
cur.execute("""
SELECT RTRIM(m.LINE_NO) ln, m.CALENDAR_YMD ymd6, CAST(m.WORK_STATS AS varchar(4)) ws
  FROM {S}.PR_M_LINE_CALENDAR m WITH(NOLOCK)
 WHERE NOT EXISTS(SELECT 1 FROM {S}.line_calendar c WITH(NOLOCK)
                   WHERE RTRIM(c.line_no)=RTRIM(m.LINE_NO)
                     AND FORMAT(c.cal_ymd,'yyMMdd')=m.CALENDAR_YMD)""".format(S=S))
lc_new = [tuple(x) for x in cur.fetchall()]
cur.execute("""
SELECT RTRIM(m.LINE_NO), m.CALENDAR_YMD,
       CAST(c.work_stats AS varchar(4)), CAST(m.WORK_STATS AS varchar(4)), ISNULL(c.src,'')
  FROM {S}.PR_M_LINE_CALENDAR m WITH(NOLOCK)
  JOIN {S}.line_calendar c WITH(NOLOCK)
    ON RTRIM(c.line_no)=RTRIM(m.LINE_NO) AND FORMAT(c.cal_ymd,'yyMMdd')=m.CALENDAR_YMD
 WHERE ISNULL(CAST(m.WORK_STATS AS varchar(4)),'')<>ISNULL(CAST(c.work_stats AS varchar(4)),'')
   AND ISNULL(c.src,'') = 'MIRROR'""".format(S=S))
lc_upd = [tuple(x) for x in cur.fetchall()]
print("\n④ 라인별달력(line_calendar) — 신규 {}건 · 값갱신 {}건 (src=MIRROR 만)".format(len(lc_new), len(lc_upd)))
for r in lc_upd[:10]:
    print("   라인={:<8s} {} {} → {}".format(str(r[0]), str(r[1]), str(r[2] or "-").strip(), str(r[3] or "-").strip()))

# ★웹 입력분 보호 현황
cur.execute("""SELECT ISNULL(src,''), COUNT(*) FROM {S}.line_calendar
                WHERE ISNULL(src,'') IN ('MANUAL','LG') GROUP BY ISNULL(src,'')""".format(S=S))
prot = [tuple(x) for x in cur.fetchall()]
print("   ※보호(미터치): " + (" · ".join("src={} {:,}행".format(str(p[0]), p[1]) for p in prot) or "없음"))

TOT = len(wc_upd) + len(pc_new) + len(pc_upd) + len(lc_new) + len(lc_upd)
if TOT == 0:
    print("\n   대상 0건 — 이미 최신입니다.")
    nx.rollback(); nx.close(); sys.exit(0)

if not APPLY:
    print("\n   합계 {}건. ※dry-run — 반영하려면 --apply 를 붙이세요.".format(TOT))
    nx.rollback(); nx.close(); sys.exit(0)

# ── 백업 ────────────────────────────────────────────────────────
for t, keys in (("work_calendar", "team,cal_ymd"), ("part_calendar", "part_code,cal_ymd"),
                ("line_calendar", "line_no,cal_ymd")):
    bk = "bk_{}_{}".format(t, STAMP)
    cur.execute("SELECT * INTO {S}.{bk} FROM {S}.{t}".format(S=S, bk=bk, t=t))
    print("\n   백업 {}.{}".format(S, bk))

# ── 반영 ────────────────────────────────────────────────────────
n1 = n2 = n3 = n4 = n5 = 0
for r in wc_upd:
    cur.execute("""UPDATE {S}.work_calendar SET work_stats=?, upd_user='SYNC260909', upd_dt=GETDATE()
                    WHERE FORMAT(cal_ymd,'yyMMdd')=?""".format(S=S), str(r[3]).strip(), str(r[0]))
    n1 += cur.rowcount
for r in pc_new:
    cur.execute("""INSERT INTO {S}.part_calendar(part_code,cal_ymd,work_stats,upd_user,upd_dt)
                   VALUES(?, CONVERT(date, '20'+?, 112), ?, 'SYNC260909', GETDATE())""".format(S=S),
                str(r[0]), str(r[1]), str(r[2]).strip())
    n2 += cur.rowcount
for r in pc_upd:
    cur.execute("""UPDATE {S}.part_calendar SET work_stats=?, upd_user='SYNC260909', upd_dt=GETDATE()
                    WHERE RTRIM(part_code)=? AND FORMAT(cal_ymd,'yyMMdd')=?""".format(S=S),
                str(r[3]).strip(), str(r[0]), str(r[1]))
    n3 += cur.rowcount
for r in lc_new:
    cur.execute("""INSERT INTO {S}.line_calendar(line_no,cal_ymd,work_stats,src,upd_dt)
                   VALUES(?, CONVERT(date, '20'+?, 112), ?, 'MIRROR', GETDATE())""".format(S=S),
                str(r[0]), str(r[1]), str(r[2]).strip())
    n4 += cur.rowcount
for r in lc_upd:
    cur.execute("""UPDATE {S}.line_calendar SET work_stats=?, upd_dt=GETDATE()
                    WHERE RTRIM(line_no)=? AND FORMAT(cal_ymd,'yyMMdd')=? AND ISNULL(src,'')='MIRROR'""".format(S=S),
                str(r[3]).strip(), str(r[0]), str(r[1]))
    n5 += cur.rowcount
print("\n   반영 — 근무갱신 {} · 파트신규 {} · 파트갱신 {} · 라인신규 {} · 라인갱신 {}".format(n1, n2, n3, n4, n5))

# ── 검증 ────────────────────────────────────────────────────────
cur.execute("""SELECT COUNT(*) FROM {S}.HR_M_CALENDAR m WITH(NOLOCK)
                 JOIN {S}.work_calendar c ON FORMAT(c.cal_ymd,'yyMMdd')=SUBSTRING(m.CALENDAR_YYMD,3,6)
                WHERE m.WORK_TEAM='A' AND m.TIME_TYPE='A'
                  AND ISNULL(CAST(m.WORK_STATS AS varchar(4)),'')<>ISNULL(CAST(c.work_stats AS varchar(4)),'')""".format(S=S))
v1 = cur.fetchone()[0]
cur.execute("""SELECT COUNT(*) FROM {S}.PR_M_PART_CALENDAR m WITH(NOLOCK)
                WHERE NOT EXISTS(SELECT 1 FROM {S}.part_calendar c
                                  WHERE RTRIM(c.part_code)=RTRIM(m.PART_CODE)
                                    AND FORMAT(c.cal_ymd,'yyMMdd')=m.CALENDAR_YMD)""".format(S=S))
v2 = cur.fetchone()[0]
cur.execute("""SELECT COUNT(*) FROM {S}.PR_M_LINE_CALENDAR m WITH(NOLOCK)
                WHERE NOT EXISTS(SELECT 1 FROM {S}.line_calendar c
                                  WHERE RTRIM(c.line_no)=RTRIM(m.LINE_NO)
                                    AND FORMAT(c.cal_ymd,'yyMMdd')=m.CALENDAR_YMD)""".format(S=S))
v3 = cur.fetchone()[0]
print("   검증 — 근무 불일치 {} · 파트 결손 {} · 라인 결손 {}".format(v1, v2, v3))

if v1 == 0 and v2 == 0 and v3 == 0:
    nx.commit(); print("   ✅ 커밋 완료")
else:
    nx.rollback(); print("   ★검증 실패 — 롤백"); nx.close(); sys.exit(1)

print("\n   ※다음 단계 = 코드 19곳의 미러 직독을 클린으로 전환")
nx.close()
