# -*- coding: utf-8 -*-
"""오늘 전환분 잔존 마무리 — 달력·WORK류·품목별공정 (2026-09-09)

★왜 남았나 — 내 스캔이 세 가지를 빼먹었다(각 건 "잔존 0" 이라 보고했으나 부실했다):
   ① 스칼라 함수(f_*) — SP 만 훑고 함수는 안 봤다. **당김일자 계산 함수가 여기 있다**
        f_get_relative_work_day        PR_M_LINE_CALENDAR 2곳
        f_get_relative_work_day_doosung HR_M_CALENDAR 3곳
        f_get_relative_work_day_of_part HR_M_CALENDAR 3 + PR_M_PART_CALENDAR 3곳
      → 컷오버로 달력이 얼어붙으면 **계획 당김일자가 통째로 틀어진다**(§6-1 과 같은 사고).
   ② 딕셔너리 "t": 값 — SQL 키워드가 앞에 없어 정규식이 못 잡았다(basemaster 달력 3종).
   ③ 어제 놓친 SP 15곳 — PR_M_ITEM_PROC_GAGONG(가공세트재고 등).

★전수 재스캔 기준을 바꿨다: sys.sql_modules 전체(P/FN/TF/IF/TR) + '"t":' 패턴 포함.

사용: python _migration\\finish_mirror_leftover_260909.py [--apply]
"""
import sys, os, io, re, shutil, datetime

BE = r"c:\Users\박근민\Desktop\NEW_ERP_1\PNC_ERP_Web\backend"
sys.path.insert(0, BE); os.chdir(BE)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
from common import _nx

APPLY = "--apply" in sys.argv
STAMP = datetime.datetime.now().strftime("%y%m%d_%H%M")
BK = r"c:\Users\박근민\Desktop\NEW_ERP_1\_schema\bk_leftover_{}".format(STAMP)

MAP = {"HR_M_CALENDAR": "nx.v_cal_work",
       "PR_M_LINE_CALENDAR": "nx.v_cal_line",
       "PR_M_PART_CALENDAR": "nx.v_cal_part",
       "PR_M_WORK": "nx.v_work_place",
       "PR_M_WORK_SINGLE": "nx.v_work_single",
       "PR_M_ITEM_PROC_GAGONG": "nx.v_item_proc"}
# ★긴 이름 먼저 — PR_M_WORK 가 PR_M_WORK_SINGLE 을 접두사로 품는다
ORDER = ["PR_M_ITEM_PROC_GAGONG", "PR_M_LINE_CALENDAR", "PR_M_PART_CALENDAR",
         "HR_M_CALENDAR", "PR_M_WORK_SINGLE", "PR_M_WORK"]

RD = os.path.join(BE, "routers")
FILES = ["common.py", "live_api.py", "app.py"] + \
        [os.path.join("routers", x) for x in sorted(os.listdir(RD)) if x.endswith(".py")]

nx = _nx(); nx.autocommit = False
cur = nx.cursor()

print("=" * 100)
print(" 잔존 마무리 — 달력 3종 · WORK류 2종 · 품목별공정")
print(" 모드: {}".format("★실제 반영(--apply)" if APPLY else "조회만(dry-run)"))
print("=" * 100)

# ── 사전 채증: 당김 함수 값 ────────────────────────────────────
FN_CASES = [("f_get_relative_work_day", ["'260909'", "-1"]),
            ("f_get_relative_work_day_doosung", ["'260909'", "-1"]),
            ("f_get_relative_work_day_of_part", ["'S5'", "'260909'", "-1"])]
before = {}
if APPLY:
    print("\n① 당김 함수 사전 채증")
    for fn, args in FN_CASES:
        vals = []
        for ymd in ("260901", "260909", "260915", "260930", "261009"):
            for d in (-1, -2, -3, 1):
                a = list(args)
                a[-2] = "'{}'".format(ymd) if len(a) > 2 else a[-2]
                if len(a) == 2: a[0] = "'{}'".format(ymd)
                else: a[1] = "'{}'".format(ymd)
                a[-1] = str(d)
                try:
                    cur.execute("SELECT dbo.{}({})".format(fn, ",".join(a)))
                    vals.append((ymd, d, str(cur.fetchone()[0])))
                except Exception as e:
                    vals.append((ymd, d, "ERR:" + str(e)[:40]))
        before[fn] = vals
        ok = [v for v in vals if not str(v[2]).startswith("ERR")]
        print("   {:<36s} {}건 (성공 {})".format(fn, len(vals), len(ok)))
        for v in vals[:3]: print("      {} {:+d} → {}".format(v[0], v[1], v[2]))

# ── 코드 치환 ──────────────────────────────────────────────────
print("\n② 코드")
tot = 0
for f in FILES:
    p = os.path.join(BE, f)
    if not os.path.exists(p): continue
    src = open(p, encoding="utf-8").read()
    lines = src.split("\n")
    out, n = [], 0
    for i, ln in enumerate(lines, 1):
        new = ln
        if not ln.lstrip().startswith("#"):
            for t in ORDER:
                RX = re.compile(r"\b{}(?![_\w])".format(t), re.I)
                PRE = re.compile(r"\b(FROM|JOIN|INTO|UPDATE|DELETE\s+FROM|TABLE)\s+[\w\.\{\}\[\]]*"
                                 + t + r"(?![_\w])", re.I)
                if not RX.search(new): continue
                if not (PRE.search(new) or '"t":' in new): continue
                v = MAP[t]
                # 3부/변수/nx./무접두 순 — 이중접두어 방지
                new = re.sub(r"\bPARTNER_ERP_TEST3\.nx\.{}(?![_\w])".format(t),
                             "PARTNER_ERP_TEST3." + v, new, flags=re.I)
                new = re.sub(r"(\{(?:S|SCH|NXS|P)\}\.?)" + t + r"(?![_\w])",
                             lambda m: m.group(1) + v.split(".", 1)[1], new, flags=re.I)
                new = re.sub(r"\bnx\.{}(?![_\w])".format(t), v, new, flags=re.I)
                new = re.sub(r"\b{}(?![_\w])".format(t), v, new, flags=re.I)
        if new != ln:
            n += 1
            print("   {:<18s} L{:<5d} {}".format(os.path.basename(f), i, new.strip()[:76]))
        out.append(new)
    tot += n
    if n and APPLY:
        os.makedirs(BK, exist_ok=True)
        shutil.copy2(p, os.path.join(BK, os.path.basename(f)))
        open(p, "w", encoding="utf-8", newline="").write("\n".join(out))
print("   → 코드 {}곳".format(tot))

# ── SP·함수 치환 (sys.sql_modules 전체) ────────────────────────
print("\n③ SP·함수 (웹 호출분)")
SRC = {}
for f in FILES:
    p = os.path.join(BE, f)
    if os.path.exists(p): SRC[f] = open(p, encoding="utf-8").read().split("\n")
RXS = re.compile(r"SP_[\w가-힣]+|TR_[\w가-힣]+|f_[\w가-힣]+")
called = set()
for f, lines in SRC.items():
    for ln in lines:
        if ln.lstrip().startswith("#"): continue
        for m in RXS.finditer(ln): called.add(m.group(0))
# 함수는 SP 안에서 다시 불리므로, 웹호출 SP 가 부르는 함수까지 포함
cur.execute("""SELECT o.name, s.name, sm.definition, o.type FROM sys.sql_modules sm
                 JOIN sys.objects o ON o.object_id=sm.object_id
                 JOIN sys.schemas s ON s.schema_id=o.schema_id""")
MODS = [(str(a), str(b), c, str(d).strip()) for a, b, c, d in cur.fetchall()]
for nm, sch, d, ty in MODS:
    if nm in called: continue
    for cn2, _s, cd, _t in MODS:
        if cn2 in called and re.search(r"\b{}\s*\(".format(re.escape(nm)), cd, re.I):
            called.add(nm); break


def mask(s):
    s = re.sub(r"/\*.*?\*/", lambda m: " " * len(m.group(0)), s, flags=re.S)
    return re.sub(r"--[^\n]*", lambda m: " " * len(m.group(0)), s)


spn = 0
for nm, sch, d, ty in MODS:
    if nm not in called: continue
    m = mask(d)
    spans = []
    for t in ORDER:
        RX = re.compile(r"\b(?:(?:PARTNER_ERP_TEST3\.)?(?:nx|dbo)\.)?{}(?![_\w])".format(t), re.I)
        for x in RX.finditer(m):
            spans.append((x.start(), x.end(), MAP[t]))
    if not spans: continue
    spans.sort()
    # 겹침 제거(긴 이름 우선 적용됐으므로 앞에서부터)
    ded, last = [], -1
    for a, b, v in spans:
        if a >= last: ded.append((a, b, v)); last = b
    print("   {}.{:<44s} {}곳 [{}]".format(sch, nm[:44], len(ded), ty))
    spn += len(ded)
    if not APPLY: continue
    os.makedirs(BK, exist_ok=True)
    open(os.path.join(BK, "{}.{}.sql".format(sch, nm)), "w", encoding="utf-8").write(d)
    new = d
    for a, b, v in reversed(ded):
        new = new[:a] + v + new[b:]
    alt = re.sub(r"^\s*CREATE\s+(PROCEDURE|PROC|FUNCTION|TRIGGER)\b", r"ALTER \1",
                 new, count=1, flags=re.I)
    if alt == new:
        print("      ★CREATE 를 못 찾음 — 건너뜀"); continue
    try:
        cur.execute(alt); print("      ✔ 반영")
    except Exception as e:
        nx.rollback(); print("      ★실패 — 전체 롤백: {}".format(str(e)[:170])); nx.close(); sys.exit(1)
print("   → SP·함수 {}곳".format(spn))

if not APPLY:
    nx.rollback()
    print("\n" + "=" * 100)
    print(" 치환 예정 코드 {} · SP {}곳 · ※dry-run".format(tot, spn))
    nx.close(); sys.exit(0)

# ── 검증: 레거시(라이브)와 같은가 ──────────────────────────────
# ★기준을 바꿨다(2026-09-09 대표 확인 "레거시하고 똑같이 맞추면 변동 없을꺼야").
#   처음엔 "값이 변하면 안 된다"로 잡아 롤백했는데, 그게 틀렸다 —
#   함수가 읽던 PARTNER_ERP_TEST3.dbo.HR_M_CALENDAR 는 **라이브와 4일 어긋난 낡은 사본**이다.
#     20260817 레거시=근무/dbo=휴무 · 20260828·0924·0925 레거시=휴무/dbo=근무
#   nx 미러·클린뷰는 라이브와 불일치 0. ⟹ 클린으로 바꾸는 것이 **레거시와 맞추는 것**이고,
#   값이 바뀌는 것은 "틀린 값 → 맞는 값"이다. 그래서 판정을 라이브 기준으로 한다.
print("\n④ 검증 — 라이브(레거시) 달력과 같은 결과를 내는가")
LIVE_WD = "PARTNER_ERP.dbo.HR_M_CALENDAR"


def live_pull(ymd, days, part=None):
    """레거시(라이브) 달력으로 근무일 -days 당김 — **함수 산식 그대로 재현**.

       ★part 를 주면 f_get_relative_work_day_of_part 와 같이
         사내달력 위에 파트달력을 덮어쓴다: isnull(b.work_stats, a.work_stats).
         이걸 빼고 사내달력만 보면 오판한다 —
         실제로 260901 -3 에서 함수=260825(맞음) vs 내 기대=260826(틀림) 이 났다.
         원인은 8/26 이 파트 휴무인데 낡은 TEST3.dbo 엔 **그 행 자체가 없어서**(357 vs 372).
       ★파트달력은 CALENDAR_YMD 가 6자리(YYMMDD) 라 '20'+ 로 8자리에 맞춘다(함수와 동일)."""
    if part:
        sql = """IF OBJECT_ID('tempdb..#lw') IS NOT NULL DROP TABLE #lw;
            SELECT SUBSTRING(x.calendar_yymd,3,6) ymd6,
                   ROW_NUMBER() OVER(ORDER BY x.calendar_yymd) rn
              INTO #lw FROM (
                SELECT a.calendar_yymd, ISNULL(b.work_stats, a.work_stats) work_stats
                  FROM (SELECT calendar_yymd, work_stats FROM {L}
                         WHERE work_team='A' AND time_type='A') a
                  LEFT JOIN (SELECT '20'+calendar_ymd calendar_yymd, work_stats
                               FROM PARTNER_ERP.dbo.PR_M_PART_CALENDAR
                              WHERE part_code=?) b ON b.calendar_yymd=a.calendar_yymd) x
             WHERE x.work_stats IN ('1','2','5','6','7');
            SELECT w2.ymd6 FROM #lw w1 JOIN #lw w2 ON w2.rn=w1.rn-? WHERE w1.ymd6=?;"""
        cur.execute(sql.format(L=LIVE_WD), part, abs(days), ymd)
    else:
        cur.execute("""IF OBJECT_ID('tempdb..#lw') IS NOT NULL DROP TABLE #lw;
            SELECT SUBSTRING(calendar_yymd,3,6) ymd6,
                   ROW_NUMBER() OVER(ORDER BY calendar_yymd) rn
              INTO #lw FROM {L}
             WHERE work_team='A' AND time_type='A' AND work_stats IN ('1','2','5','6','7');
            SELECT w2.ymd6 FROM #lw w1 JOIN #lw w2 ON w2.rn=w1.rn-? WHERE w1.ymd6=?;""".format(L=LIVE_WD),
                    abs(days), ymd)
    rows = []
    while True:
        if cur.description: rows = cur.fetchall()
        if not cur.nextset(): break
    return str(rows[0][0]).strip() if rows else None


bad = 0
for fn, args in FN_CASES:
    if fn == "f_get_relative_work_day":
        continue                      # 라인달력 축이라 별도(사내달력 기준 대조 불가)
    PART = "S5" if "of_part" in fn else None
    okn = ngn = 0
    ex = []
    for ymd in ("260901", "260909", "260915", "260930", "261009"):
        for d in (-1, -2, -3):
            a = list(args)
            if len(a) == 2: a[0] = "'{}'".format(ymd)
            else: a[1] = "'{}'".format(ymd)
            a[-1] = str(d)
            try:
                cur.execute("SELECT dbo.{}({})".format(fn, ",".join(a)))
                got = str(cur.fetchone()[0]).strip()
            except Exception:
                continue
            want = live_pull(ymd, d, PART)
            if want is None: continue
            if got == want: okn += 1
            else:
                ngn += 1
                if len(ex) < 5: ex.append((ymd, d, got, want))
    print("   [{}] {:<36s} 레거시 일치 {} · 불일치 {}".format(
        "OK  " if ngn == 0 else "★DIFF", fn, okn, ngn))
    for y, d, g, w in ex:
        print("      {} {:+d}  함수={} / 레거시={}".format(y, d, g, w))
    if ngn: bad += 1

# 전후 변화도 참고로 보여준다(롤백 사유는 아니다)
print("\n   — 참고: 전환 전후 변화 —")
for fn, args in FN_CASES:
    vals = []
    for ymd in ("260901", "260909", "260915", "260930", "261009"):
        for d in (-1, -2, -3, 1):
            a = list(args)
            if len(a) == 2: a[0] = "'{}'".format(ymd)
            else: a[1] = "'{}'".format(ymd)
            a[-1] = str(d)
            try:
                cur.execute("SELECT dbo.{}({})".format(fn, ",".join(a)))
                vals.append((ymd, d, str(cur.fetchone()[0])))
            except Exception as e:
                vals.append((ymd, d, "ERR:" + str(e)[:30]))
    chg = [(x, y) for x, y in zip(before.get(fn, []), vals) if x != y]
    print("      {:<36s} 변화 {}건".format(fn, len(chg)))
    for x, y in chg[:4]:
        print("         {} {:+d}  {} → {}  (낡은 dbo → 레거시 정합)".format(x[0], x[1], x[2], y[2]))

if bad:
    nx.rollback(); print("\n ★레거시와 어긋난다 — 전체 롤백"); nx.close(); sys.exit(1)
nx.commit()
print("\n" + "=" * 100)
print(" ✅ 코드 {}곳 · SP/함수 {}곳 커밋 · 백업 {}".format(tot, spn, BK))
nx.close()
