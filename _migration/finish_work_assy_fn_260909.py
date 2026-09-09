# -*- coding: utf-8 -*-
"""조립 ST 함수 잔존 치환 — PR_M_WORK_ASSY → nx.v_work_assy (2026-09-09)

★아침 공유("PR_M_WORK_ASSY (2) = prodinfo 조립패널")는 **코드만 센 것**이었다.
   함수 2개를 놓쳤다(오늘 §6-6 과 같은 함정 — SP 만 훑고 FN 을 안 봄).

   f_assy_st_live      PARTNER_ERP_TEST3.nx.PR_M_WORK_ASSY  ★웹이 탄다
                       prod.py:31·46 → f_stday_live → f_assy_st_live
                       (생산실적현황 필요ST 계산)
   f_get_item_assy_st  PR_M_WORK_ASSY (무접두 = TEST3.dbo)
                       ★웹 경로 있다(체인 확인) —
                         prod.py:122 → f_get_item_st_day → f_get_item_assy_st
                       처음엔 "레거시 SP 전용"으로 오판했다. 직접 호출만 보고
                       **한 단계 더 들어가는 체인**을 안 따라간 탓이다.

★데이터는 안전하다(실측) — 3갈래 전부 라이브와 일치
     TEST3.dbo 371 · TEST3.nx 371 · 라이브 371 · 클린 371 · 뷰 371, 불일치 0
     두 함수 값도 40품목 40/40 동일
   달력에서 겪은 '낡은 사본' 문제는 여기 없다. 그래도 미러를 읽으면 컷오버에 얼어붙는다.

★f_get_item_assy_st 는 웹 미호출이라 **건드리지 않는다**(레거시 SP 가 쓰는 것).

사용: python _migration\\finish_work_assy_fn_260909.py [--apply]
"""
import sys, os, io, re, datetime

BE = r"c:\Users\박근민\Desktop\NEW_ERP_1\PNC_ERP_Web\backend"
sys.path.insert(0, BE); os.chdir(BE)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
from common import _nx

APPLY = "--apply" in sys.argv
STAMP = datetime.datetime.now().strftime("%y%m%d_%H%M")
BK = r"c:\Users\박근민\Desktop\NEW_ERP_1\_schema\sp_backup_assyfn_{}".format(STAMP)
T = "PR_M_WORK_ASSY"
# ★웹 경로가 있는 것만. (f_assy_st_live 는 1차 실행에서 이미 반영됨 — 멱등)
TARGETS = ["f_assy_st_live",       # prod.py:31,46 → f_stday_live → 이것
           "f_get_item_assy_st"]   # prod.py:122   → f_get_item_st_day → 이것
RX = re.compile(r"\b(?:(?:PARTNER_ERP_TEST3\.)?(?:nx|dbo)\.)?{}(?![_\w])".format(T), re.I)


def mask(s):
    s = re.sub(r"/\*.*?\*/", lambda m: " " * len(m.group(0)), s, flags=re.S)
    return re.sub(r"--[^\n]*", lambda m: " " * len(m.group(0)), s)


nx = _nx(); nx.autocommit = False
cur = nx.cursor()

print("=" * 96)
print(" 조립 ST 함수 — {} → nx.v_work_assy".format(T))
print(" 모드: {}".format("★실제 반영(--apply)" if APPLY else "조회만(dry-run)"))
print("=" * 96)

# ── 사전 채증 — 두 함수 + 웹이 실제 타는 상위 함수 ────────────
cur.execute("""SELECT TOP 60 RTRIM(item_code) FROM PARTNER_ERP_TEST3.nx.pr_m_item_assy_rt
                GROUP BY item_code ORDER BY item_code""")
items = [str(r[0]).strip() for r in cur.fetchall()]
# ★상위 함수까지 채증한다 — 값이 실제로 흘러가는 곳이 여기다
PROBE = TARGETS + ["f_get_item_st_day", "f_stday_live"]
before = {}
for fn in PROBE:
    vals = {}
    for it in items:
        try:
            cur.execute("SELECT dbo.{}(?)".format(fn), it)
            vals[it] = float(cur.fetchone()[0] or 0)
        except Exception:
            try:   # 일자 인자를 받는 것(f_stday_live·f_get_item_st_day)
                cur.execute("SELECT dbo.{}(?,?)".format(fn), it, "260909")
                vals[it] = float(cur.fetchone()[0] or 0)
            except Exception:
                pass
    before[fn] = vals
    print("① 사전 채증 {:<22s} {}품목".format(fn, len(vals)))

# ── 치환 ───────────────────────────────────────────────────────
print("\n② 치환")
tot = 0
for TARGET in TARGETS:
    cur.execute("""SELECT s.name, sm.definition FROM sys.sql_modules sm
                     JOIN sys.objects o ON o.object_id=sm.object_id
                     JOIN sys.schemas s ON s.schema_id=o.schema_id WHERE o.name=?""", TARGET)
    r = cur.fetchone()
    if not r:
        print("   ★{} 없음".format(TARGET)); continue
    sch, d = str(r[0]), r[1]
    spans = [x.span() for x in RX.finditer(mask(d))]
    print("\n   {}.{:<24s} {}곳".format(sch, TARGET, len(spans)))
    for a, b in spans:
        ls = d.rfind("\n", 0, a) + 1
        print("      {}".format(d[ls:d.find("\n", b)].strip()[:86]))
    if not spans:
        print("      (이미 전환됨 — 건너뜀)"); continue
    tot += len(spans)
    if not APPLY: continue
    os.makedirs(BK, exist_ok=True)
    open(os.path.join(BK, "{}.{}.sql".format(sch, TARGET)), "w", encoding="utf-8").write(d)
    new = d
    for a, b in reversed(spans):
        new = new[:a] + "nx.v_work_assy" + new[b:]
    m = re.search(r"CREATE\s+(FUNCTION)\b", new, re.I)
    if not m:
        print("      ★CREATE FUNCTION 못 찾음"); nx.rollback(); nx.close(); sys.exit(1)
    alt = new[:m.start()] + "ALTER " + m.group(1) + new[m.end():]
    try:
        cur.execute(alt); print("      ✔ 반영")
    except Exception as e:
        nx.rollback(); print("      ★실패 — 롤백: {}".format(str(e)[:170])); nx.close(); sys.exit(1)

if not APPLY:
    nx.rollback(); print("\n ※dry-run — 치환 예정 {}곳".format(tot)); nx.close(); sys.exit(0)

# ── 검증 — 값 동일 (상위 함수 포함) ───────────────────────────
print("\n③ 값 대조 (상위 함수까지)")
diff = 0
for fn, vals in before.items():
    d2 = 0
    for it, v0 in vals.items():
        try:
            cur.execute("SELECT dbo.{}(?)".format(fn), it)
            v1 = float(cur.fetchone()[0] or 0)
        except Exception:
            try:
                cur.execute("SELECT dbo.{}(?,?)".format(fn), it, "260909")
                v1 = float(cur.fetchone()[0] or 0)
            except Exception:
                continue
        if abs(v0 - v1) > 1e-6:
            d2 += 1
            if d2 <= 3: print("   ★{} {} : {} → {}".format(fn, it, v0, v1))
    diff += d2
    print("   [{}] {:<22s} {}품목 · 불일치 {}".format(
        "OK  " if d2 == 0 else "DIFF", fn, len(vals), d2))

# ── 잔존 ───────────────────────────────────────────────────────
left = 0
for TARGET in TARGETS:
    cur.execute("""SELECT sm.definition FROM sys.sql_modules sm
                     JOIN sys.objects o ON o.object_id=sm.object_id WHERE o.name=?""", TARGET)
    r = cur.fetchone()
    if r: left += len(RX.findall(mask(r[0])))
print("\n④ 잔존 {}곳".format(left))

if diff == 0 and left == 0:
    nx.commit(); print("\n ✅ 치환 {}곳 커밋 · 백업 {}".format(tot, BK))
    print("""
 ★교훈 — 직접 호출만 보면 놓친다. 체인을 한 단계 더 따라가야 한다:
     prod.py:31,46 → f_stday_live      → f_assy_st_live      → PR_M_WORK_ASSY
     prod.py:122   → f_get_item_st_day → f_get_item_assy_st  → PR_M_WORK_ASSY
   처음엔 f_get_item_assy_st 를 "레거시 SP 전용"으로 오판했다.""")
else:
    nx.rollback(); print("\n ★검증 실패 — 롤백"); nx.close(); sys.exit(1)
nx.close()
