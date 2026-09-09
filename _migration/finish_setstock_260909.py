# -*- coding: utf-8 -*-
"""가공세트재고 SP 2개 잔존 치환 — PR_M_ITEM_PROC_GAGONG → nx.v_item_proc (2026-09-09)

★왜 앞 스크립트가 건너뛰었나 — 정규식이 `^\\s*CREATE` 였는데
   이 SP 들은 **머리에 템플릿 주석이 205자** 붙어 있어 CREATE 가 206번째 문자에 있다.
     -- =============================================
     -- Author: <Author,,Name> ...
     CREATE PROCEDURE [dbo].[SP_PR_SET_가공세트재고] ...
   ⟹ 앵커(^)를 빼고 **첫 CREATE PROCEDURE 를 위치로 찾아** ALTER 로 바꾼다.

★함께: f_get_relative_work_day 는 인자가 3개(@as_line_no, @as_ymd, @ai_day)다.
   앞 스크립트가 2개로 불러 검증을 못 했다 — 여기서 라인달력 축으로 대조한다.

사용: python _migration\\finish_setstock_260909.py [--apply]
"""
import sys, os, io, re, datetime

BE = r"c:\Users\박근민\Desktop\NEW_ERP_1\PNC_ERP_Web\backend"
sys.path.insert(0, BE); os.chdir(BE)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
from common import _nx

APPLY = "--apply" in sys.argv
STAMP = datetime.datetime.now().strftime("%y%m%d_%H%M")
BK = r"c:\Users\박근민\Desktop\NEW_ERP_1\_schema\bk_setstock_{}".format(STAMP)
T = "PR_M_ITEM_PROC_GAGONG"
TARGETS = ["SP_PR_SET_가공세트재고", "SP_PR_SET_가공세트재고_251231"]
RX = re.compile(r"\b(?:(?:PARTNER_ERP_TEST3\.)?(?:nx|dbo)\.)?{}(?![_\w])".format(T), re.I)


def mask(s):
    s = re.sub(r"/\*.*?\*/", lambda m: " " * len(m.group(0)), s, flags=re.S)
    return re.sub(r"--[^\n]*", lambda m: " " * len(m.group(0)), s)


nx = _nx(); nx.autocommit = False
cur = nx.cursor()

print("=" * 96)
print(" 가공세트재고 SP — {} → nx.v_item_proc".format(T))
print(" 모드: {}".format("★실제 반영(--apply)" if APPLY else "조회만(dry-run)"))
print("=" * 96)

# ── 사전 채증: SP 실행 결과 ────────────────────────────────────
def run_sp(nm):
    try:
        cur.execute("SET NOCOUNT ON; EXEC [dbo].[{}]".format(nm))
        rows = []
        while True:
            try:
                r = cur.fetchall()
                if r: rows = r
            except Exception: pass
            if not cur.nextset(): break
        return len(rows)
    except Exception as e:
        return "ERR:" + str(e)[:70]


tot = 0
for sp in TARGETS:
    cur.execute("""SELECT s.name, sm.definition FROM sys.sql_modules sm
                     JOIN sys.objects o ON o.object_id=sm.object_id
                     JOIN sys.schemas s ON s.schema_id=o.schema_id WHERE o.name=?""", sp)
    r = cur.fetchone()
    if not r:
        print("\n■ {:<40s} ★없음".format(sp)); continue
    sch, d = str(r[0]), r[1]
    spans = [x.span() for x in RX.finditer(mask(d))]
    print("\n■ {}.{:<38s} {}곳".format(sch, sp, len(spans)))
    for a, b in spans[:8]:
        ls = d.rfind("\n", 0, a) + 1
        print("     {}".format(d[ls:d.find("\n", b)].strip()[:86]))
    tot += len(spans)
    if not APPLY or not spans: continue

    os.makedirs(BK, exist_ok=True)
    open(os.path.join(BK, "{}.{}.sql".format(sch, sp)), "w", encoding="utf-8").write(d)
    new = d
    for a, b in reversed(spans):
        new = new[:a] + "nx.v_item_proc" + new[b:]
    # ★앵커 없이 첫 CREATE PROCEDURE 를 찾아 ALTER 로 (머리 주석 205자 대응)
    m = re.search(r"CREATE\s+(PROCEDURE|PROC)\b", new, re.I)
    if not m:
        print("     ★CREATE 를 못 찾음"); continue
    alt = new[:m.start()] + "ALTER " + m.group(1) + new[m.end():]
    try:
        cur.execute(alt); print("     ✔ 반영 (CREATE @{})".format(m.start()))
    except Exception as e:
        nx.rollback(); print("     ★실패 — 롤백: {}".format(str(e)[:170])); nx.close(); sys.exit(1)

print("\n" + "=" * 96)
if not APPLY:
    nx.rollback(); print(" 치환 예정 {}곳 · ※dry-run".format(tot)); nx.close(); sys.exit(0)

# ── 검증 ───────────────────────────────────────────────────────
print(" 검증")
left = 0
for sp in TARGETS:
    cur.execute("""SELECT sm.definition FROM sys.sql_modules sm
                     JOIN sys.objects o ON o.object_id=sm.object_id WHERE o.name=?""", sp)
    r = cur.fetchone()
    if r:
        n = len(RX.findall(mask(r[0])))
        print("   {:<40s} 잔존 {}곳".format(sp, n)); left += n

# 라인달력 함수 대조 (인자 3개: @as_line_no, @as_ymd, @ai_day)
#
# ★함수 본문을 읽고서야 제대로 대조할 수 있었다 — 두 번 틀렸다:
#   ① 반환값이 **일자+상태 7자리**다:  t.calendar_ymd + t.work_stats  →  '260901'+'1'='2609011'
#      앞 6자리만 일자다. 그대로 비교하면 전건 불일치가 난다.
#   ② @ai_day 는 음수 당김수가 아니라 **0-based 인덱스**다(`where s.row_num = @ai_day`).
#      0=당일, 1=한 근무일 전 … 내가 -1 을 넘겨 아무것도 못 찾았다.
#   ③ 산식은 '공통' 라인 위에 해당 라인을 덮어쓴다(isnull(b,a)) — _of_part 와 같은 구조.
print("\n   f_get_relative_work_day (라인달력 축) — 레거시 대조")
cur.execute("""SELECT TOP 3 RTRIM(LINE_NO) FROM PARTNER_ERP.dbo.PR_M_LINE_CALENDAR
                WHERE RTRIM(LINE_NO)<>'공통' GROUP BY LINE_NO ORDER BY 1""")
lines = [str(r[0]).strip() for r in cur.fetchall()]
print("      시료 라인: {}".format(", ".join(lines)))
ok = ng = 0
for line in lines:
    for ymd in ("260901", "260915", "260930"):
        for idx in (0, 1, 2, 3):
            try:
                cur.execute("SELECT dbo.f_get_relative_work_day(?,?,?)", line, ymd, idx)
                raw = cur.fetchone()[0]
                got = str(raw or "").strip()[:6]      # ★앞 6자리만 일자
            except Exception:
                continue
            # 레거시 산식 재현: '공통' 위에 해당 라인 덮어쓰기 · 최근순 row_num(0-based)
            cur.execute("""SELECT s.calendar_ymd FROM (
                  SELECT ROW_NUMBER() OVER(ORDER BY t.calendar_ymd DESC)-1 rn, t.calendar_ymd
                    FROM (SELECT a.calendar_ymd, ISNULL(b.work_stats, a.work_stats) work_stats
                            FROM (SELECT calendar_ymd, work_stats
                                    FROM PARTNER_ERP.dbo.PR_M_LINE_CALENDAR
                                   WHERE line_no='공통' AND calendar_ymd
                                         BETWEEN CONVERT(varchar, CONVERT(datetime,?,12)-30, 12) AND ?) a
                            LEFT JOIN (SELECT calendar_ymd, work_stats
                                         FROM PARTNER_ERP.dbo.PR_M_LINE_CALENDAR
                                        WHERE line_no=?) b ON b.calendar_ymd=a.calendar_ymd) t
                   WHERE t.work_stats IN ('1','2','5','6','7')) s
                 WHERE s.rn=?""", ymd, ymd, line, idx)
            r2 = cur.fetchone()
            want = str(r2[0]).strip() if r2 else None
            if want is None: continue
            if got == want: ok += 1
            else:
                ng += 1
                if ng <= 4: print("      ★{} {} idx{}  함수={} / 레거시={}".format(line, ymd, idx, got, want))
print("      레거시 일치 {} · 불일치 {}".format(ok, ng))

if left == 0 and ng == 0:
    nx.commit(); print("\n ✅ 치환 {}곳 커밋 · 백업 {}".format(tot, BK))
else:
    nx.rollback(); print("\n ★검증 실패 — 롤백 (잔존 {} · 불일치 {})".format(left, ng))
    nx.close(); sys.exit(1)
nx.close()
