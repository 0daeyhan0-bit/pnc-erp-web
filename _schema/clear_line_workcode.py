# -*- coding: utf-8 -*-
"""라인별 LG 가동시간(work_code) 비우기 — 공통 달력 근무유형을 따르게 (2026-09-01)

왜
  라인당김(③)의 종업시각은 `nx.line_calendar.work_code`(LG 가동시간)를 먼저 보고,
  없을 때만 공통 달력의 근무유형(work_stats)으로 내려간다(planrev.py `_end_of`).
    가동 8h·7.5h → 17:00   /   근무유형 '1'(잔업2h) → 19:30     차이 150분
  2026-08-31 17:20 에 LG 가동시간이 처음 유입되면서 그 직후 편성부터 종업시각이
  바뀌었고, 레거시(가동시간을 안 봄)와 1,461건이 어긋났다.
  ⟹ 대표 지시: 라인별 가동시간을 비워 **공통 달력 하나로 통일**한다.

안전 확인 (실행 전 실측)
  · 대상 8개 라인(C1·CA·CE·CG·CH·CJ·CK·CM) · 260629~261030 · 645행 · 전부 src='LG'
  · 공통 달력이 9~10월 61일을 모두 덮는다 → 지워도 빈 날 없음
  · **공통이 휴무인데 가동시간만 있던 날 = 0건** → 근무일 판정은 바뀌지 않는다
    (있었다면 그 날이 휴무로 바뀌어 계획이 밀렸을 것)

★안전 원칙
  · `work_code` 만 비운다. `work_stats`(근무유형)·`note` 는 건드리지 않는다.
  · 실행 전 **백업 테이블**에 원본을 남긴다(LG 원본을 다시 못 받을 수 있으므로).
  · `--apply` 없이는 조회만 한다(기본 dry-run).
  · 라이브는 읽지도 쓰지도 않는다(nx 전용).

사용
    python _schema/clear_line_workcode.py                 # 조회만
    python _schema/clear_line_workcode.py --apply         # 전체 기간 실행
    python _schema/clear_line_workcode.py --apply --from 260901   # 그 날짜 이후만
"""
import sys, os, io, argparse, datetime

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8',
                              errors='replace', line_buffering=True)
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, '..', 'PNC_ERP_Web', 'backend'))
sys.path.insert(0, os.path.join(_HERE, '..', '..', 'New_ERP'))

AP = argparse.ArgumentParser()
AP.add_argument('--apply', action='store_true', help='실제 실행(없으면 조회만)')
AP.add_argument('--from', dest='frm', default='', help='이 일자(YYMMDD) 이후만. 비우면 전체')
ARG = AP.parse_args()

import pyodbc, db_client

CS = (f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};'
      f'DATABASE=PARTNER_ERP_TEST3;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}')
BK = 'nx.bk_line_workcode_' + datetime.datetime.now().strftime('%y%m%d_%H%M')
FRM = ''.join(ch for ch in str(ARG.frm or '') if ch.isdigit())
WH = "ISNULL(RTRIM(work_code),'')<>'' AND RTRIM(line_no)<>'공통'"
if len(FRM) == 6:
    WH += f" AND CONVERT(varchar(6),cal_ymd,12) >= '{FRM}'"

cn = pyodbc.connect(CS, autocommit=False)
cur = cn.cursor()

print('=' * 74)
print(' 라인별 가동시간(work_code) 비우기  ' + ('[APPLY]' if ARG.apply else '[DRY-RUN — 조회만]'))
print(f' 범위: {FRM + " 이후" if len(FRM) == 6 else "전체 기간"}')
print('=' * 74)

# ── 1. 대상 ────────────────────────────────────────────────────────
cur.execute(f"""SELECT RTRIM(line_no), COUNT(*), MIN(CONVERT(varchar(6),cal_ymd,12)),
                       MAX(CONVERT(varchar(6),cal_ymd,12))
                  FROM nx.line_calendar WHERE {WH}
                 GROUP BY RTRIM(line_no) ORDER BY 1""")
rows = cur.fetchall()
tot = sum(r[1] for r in rows)
print(f'\n① 대상 {len(rows)}개 라인 · {tot}행')
for r in rows:
    print(f'   {r[0]:6s} {r[1]:>4}행  {r[2]}~{r[3]}')
if not rows:
    print('   비울 것이 없습니다.')
    cn.close(); sys.exit(0)

# ── 2. 안전 확인 — 지우면 휴무가 되는 날이 있나 ────────────────────
cur.execute(f"""SELECT COUNT(*) FROM nx.line_calendar c
                 LEFT JOIN nx.line_calendar b ON RTRIM(b.line_no)='공통' AND b.cal_ymd=c.cal_ymd
                WHERE ISNULL(RTRIM(c.work_code),'')<>'' AND RTRIM(c.line_no)<>'공통'
                  {"AND CONVERT(varchar(6),c.cal_ymd,12) >= '" + FRM + "'" if len(FRM) == 6 else ""}
                  AND ISNULL(RTRIM(c.work_stats),'')=''
                  AND ISNULL(b.work_stats,'') IN ('3','4','')""")
risky = int(cur.fetchone()[0] or 0)
print(f'\n② 안전 확인 — 지우면 **휴무가 되는** 날: {risky}건')
if risky:
    print('   ★주의: 그 날은 공통이 휴무인데 가동시간으로 근무 취급되던 날이다.')
    cur.execute(f"""SELECT TOP 15 RTRIM(c.line_no), CONVERT(varchar(6),c.cal_ymd,12),
                           RTRIM(c.work_code), ISNULL(b.work_stats,'(없음)')
                      FROM nx.line_calendar c
                      LEFT JOIN nx.line_calendar b ON RTRIM(b.line_no)='공통' AND b.cal_ymd=c.cal_ymd
                     WHERE ISNULL(RTRIM(c.work_code),'')<>'' AND RTRIM(c.line_no)<>'공통'
                       {"AND CONVERT(varchar(6),c.cal_ymd,12) >= '" + FRM + "'" if len(FRM) == 6 else ""}
                       AND ISNULL(RTRIM(c.work_stats),'')=''
                       AND ISNULL(b.work_stats,'') IN ('3','4','')
                     ORDER BY 2, 1""")
    for r in cur.fetchall():
        print(f'      {r[1]} {r[0]:5s} code={r[2]:6s} 공통={r[3]}')
else:
    print('   ✅ 없음 — 근무일 판정은 바뀌지 않는다(종업시각만 공통을 따른다)')

# ── 3. 공통 달력이 그 기간을 덮는지 ────────────────────────────────
cur.execute(f"""SELECT COUNT(*) FROM (
      SELECT DISTINCT c.cal_ymd FROM nx.line_calendar c
       WHERE ISNULL(RTRIM(c.work_code),'')<>'' AND RTRIM(c.line_no)<>'공통'
         {"AND CONVERT(varchar(6),c.cal_ymd,12) >= '" + FRM + "'" if len(FRM) == 6 else ""}
         AND NOT EXISTS(SELECT 1 FROM nx.line_calendar b
                         WHERE RTRIM(b.line_no)='공통' AND b.cal_ymd=c.cal_ymd
                           AND ISNULL(RTRIM(b.work_stats),'')<>'')) t""")
gap = int(cur.fetchone()[0] or 0)
print(f'\n③ 공통 달력에 근무유형이 없는 날: {gap}일'
      + ('   ✅ 전부 덮인다' if gap == 0 else '   ★그 날은 기본값(19:30)으로 떨어진다'))

if not ARG.apply:
    print('\n※ DRY-RUN 입니다. 실제로 비우려면 --apply 를 붙이세요.')
    cn.close(); sys.exit(0)

# ── 4. 백업 → 비우기 ───────────────────────────────────────────────
print(f'\n④ 백업 → {BK}')
cur.execute(f"""SELECT line_no, cal_ymd, work_code, work_stats, note, src, upd_dt
                  INTO {BK} FROM nx.line_calendar WHERE {WH}""")
print(f'    {cur.rowcount}행 백업')

cur.execute(f"""UPDATE nx.line_calendar SET work_code = NULL, upd_dt = GETDATE()
                 WHERE {WH}""")
n = cur.rowcount
cn.commit()
print(f'    work_code 비움 {n}행')

# ── 5. 검증 ────────────────────────────────────────────────────────
cur.execute(f"SELECT COUNT(*) FROM nx.line_calendar WHERE {WH}")
left = int(cur.fetchone()[0] or 0)
cur.execute("""SELECT COUNT(*) FROM nx.line_calendar
                WHERE RTRIM(line_no)='공통' AND ISNULL(RTRIM(work_stats),'')<>''""")
common = int(cur.fetchone()[0] or 0)
print(f'\n⑤ 검증 — 잔여 {left}행 · 공통 근무유형 {common:,}일')
print('   ' + ('✅ 완료 — 이제 종업시각이 공통 달력을 따릅니다'
                if left == 0 else '★아직 남았다'))
print(f'\n   되돌리려면:')
print(f'     UPDATE c SET c.work_code=b.work_code FROM nx.line_calendar c')
print(f'       JOIN {BK} b ON b.line_no=c.line_no AND b.cal_ymd=c.cal_ymd')
print('\n   ⚠ 편성(③ 라인별 투입시간조정 → ④ → ⑤)을 다시 돌려야 반영됩니다.')
cn.close()
