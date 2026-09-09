# -*- coding: utf-8 -*-
"""품목별 공정순서 미러 → 클린(호환뷰) 치환 · 2단계-① (2026-09-09)

    nx.PR_M_ITEM_PROC_GAGONG  →  nx.v_item_proc  (← nx.prodinfo_proc)

★대상 — SP 17곳 + 파이썬 코드 22곳.
★근거 — 뷰 검증 완료(결손 0 · 핵심컬럼 불일치 0 · make_procgagong_view_260909.py).
★안전 — SP 는 원본을 파일 백업 후 ALTER, 코드는 *.bak 백업. 주석은 건드리지 않는다.
   ★prodinfo.py 는 이미 클린(nx.prodinfo_proc)을 직접 읽으므로 대상이 아니다 —
     그쪽을 뷰로 바꾸면 편집 저장 경로가 꼬인다(뷰는 읽기 전용).

사용: python _migration\\switch_item_proc_260909.py [--apply]
"""
import sys, os, io, re, shutil, datetime

BE = r"c:\Users\박근민\Desktop\NEW_ERP_1\PNC_ERP_Web\backend"
ROOT = r"c:\Users\박근민\Desktop\NEW_ERP_1"
sys.path.insert(0, BE); os.chdir(BE)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
from common import _nx

STAMP = datetime.datetime.now().strftime("%y%m%d_%H%M")
APPLY = "--apply" in sys.argv
BKDIR = os.path.join(ROOT, "_schema", "sp_backup_{}".format(STAMP))
RD = os.path.join(BE, "routers")

RX = re.compile(r"\b(?:nx\.)?PR_M_ITEM_PROC_GAGONG\b", re.I)
REP = "nx.v_item_proc"
SPS = ["SP_PR_CREATE_PLAN_파트별계획_생성_파트휴무당김",
       "SP_PR_CREATE_PLAN_파트별_생산계획계산_NEW_250826",
       "SP_PR_가공창고_이동계획_WEBPLAN", "SP_PR_가공창고_이동계획_260213",
       "SP_PR_4주간_가공계획현황_250703", "SP_PR_가공생산진척관리_260602"]


def strip_c(s):
    s = re.sub(r"/\*.*?\*/", lambda m: " " * len(m.group(0)), s, flags=re.S)
    return re.sub(r"--[^\n]*", lambda m: " " * len(m.group(0)), s)


nx = _nx(); nx.autocommit = True
cur = nx.cursor()
print("=" * 96)
print(" 품목별 공정순서 → 클린 치환")
print(" 모드: {}".format("★실제 반영(--apply)" if APPLY else "미리보기(dry-run)"))
print("=" * 96)

# ── SP ─────────────────────────────────────────────────────────
print("\n① SP")
sp_tot = 0
if APPLY and not os.path.isdir(BKDIR):
    os.makedirs(BKDIR)
for sp in SPS:
    cur.execute("""SELECT sm.definition FROM sys.sql_modules sm
                     JOIN sys.objects o ON o.object_id=sm.object_id WHERE o.name=?""", sp)
    r = cur.fetchone()
    if not r: continue
    d = r[0]; masked = strip_c(d)
    hits = [(m.start(), m.end()) for m in RX.finditer(masked)]
    if not hits:
        continue
    new = d
    for s0, e0 in sorted(hits, key=lambda x: -x[0]):
        new = new[:s0] + REP + new[e0:]
    print("   {:<48s} {}곳".format(sp[:48], len(hits)))
    sp_tot += len(hits)
    if not APPLY:
        continue
    with io.open(os.path.join(BKDIR, sp + ".sql"), "w", encoding="utf-8") as f:
        f.write(d)
    alt = re.sub(r"\bCREATE\s+(PROCEDURE|PROC)\b", "ALTER \\1", new, count=1, flags=re.I)
    try:
        cur.execute(alt); print("      ✅ ALTER")
    except Exception as e:
        print("      ★실패(원본 유지): {}".format(str(e)[:130]))

# ── 코드 ───────────────────────────────────────────────────────
print("\n② 파이썬 코드")
py_tot = 0
files = ["common.py", "live_api.py", "app.py"] + \
        [os.path.join("routers", x) for x in sorted(os.listdir(RD)) if x.endswith(".py")]
for f in files:
    p = os.path.join(BE, f)
    if not os.path.exists(p): continue
    src = open(p, encoding="utf-8").read()
    lines = src.split("\n"); out = []; hits = []
    # ★설명 줄은 건드리지 않는다 — 경위 기록이 사라지면 안 된다.
    #   실측: prodinfo.py:90 "나머지(4,187품번)는 미러 PR_M_ITEM_PROC_GAGONG 로 떨어졌다"
    #   판정 = SQL 키워드가 같은 줄에 있어야 실제 쿼리로 본다(FROM/JOIN/INTO/UPDATE/EXISTS…).
    #   docstring 안이라도 cur.execute(\"\"\"SELECT ... 형태는 실제 SQL 이므로 이 방식이 안전하다.
    SQLKW = re.compile(r"\b(FROM|JOIN|INTO|UPDATE|DELETE|EXISTS|SELECT)\b", re.I)
    for i, ln in enumerate(lines, 1):
        s = ln.strip()
        if s.startswith("#") or not RX.search(ln):
            out.append(ln); continue
        if not SQLKW.search(ln):          # 설명 문장 — 원문 보존
            out.append(ln); continue
        n = RX.sub(REP, ln)
        hits.append((i, ln.strip()[:74]))
        out.append(n)
    if not hits: continue
    print("   {:<20s} {}곳".format(os.path.basename(f), len(hits)))
    for i, s in hits[:4]:
        print("      L{:<6d} {}".format(i, s))
    if len(hits) > 4:
        print("      … 외 {}곳".format(len(hits) - 4))
    py_tot += len(hits)
    if APPLY:
        shutil.copy2(p, p + ".bak_{}".format(STAMP))
        open(p, "w", encoding="utf-8").write("\n".join(out))

print()
print("=" * 96)
print("   SP {}곳 · 코드 {}곳 · 합계 {}곳".format(sp_tot, py_tot, sp_tot + py_tot))
if not APPLY:
    print("   ※dry-run — 반영하려면 --apply")
    nx.close(); sys.exit(0)

# ── 검증 ───────────────────────────────────────────────────────
print("\n③ 검증 — 남은 직독")
left = 0
for sp in SPS:
    cur.execute("""SELECT sm.definition FROM sys.sql_modules sm
                     JOIN sys.objects o ON o.object_id=sm.object_id WHERE o.name=?""", sp)
    r = cur.fetchone()
    if not r: continue
    n = len(RX.findall(strip_c(r[0])))
    left += n
    if n: print("   ★SP {} {}곳".format(sp[:44], n))
for f in files:
    p = os.path.join(BE, f)
    if not os.path.exists(p): continue
    n = 0
    for ln in open(p, encoding="utf-8").read().split("\n"):
        if ln.lstrip().startswith("#"): continue
        n += len(RX.findall(ln))
    left += n
    if n: print("   ★코드 {} {}곳".format(os.path.basename(f), n))
print("   → 남은 곳 {} {}".format(left, "★전부 전환됨" if left == 0 else ""))
print("\n   백업: {}".format(BKDIR))
nx.close()
