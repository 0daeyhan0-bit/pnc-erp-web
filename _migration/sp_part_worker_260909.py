# -*- coding: utf-8 -*-
"""SP 안의 작업자 미러 치환 — PR_M_PROC_GAGONG_WORKER → nx.v_part_worker (2026-09-09)

★대상은 웹이 실제 호출하는 SP 뿐. 나머지는 레거시 전용 구버전이라 안 만진다.
★SP 는 스키마 접두어 없이 소문자로 부른다 — 정규식이 그걸 흡수한다.
★주석 인용은 마스크로 제외.

백업 = _schema/sp_backup_partworker_<STAMP>/*.sql

사용: python _migration\\sp_part_worker_260909.py [--apply]
"""
import sys, os, io, re, datetime

BE = r"c:\Users\박근민\Desktop\NEW_ERP_1\PNC_ERP_Web\backend"
sys.path.insert(0, BE); os.chdir(BE)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
from common import _nx

APPLY = "--apply" in sys.argv
STAMP = datetime.datetime.now().strftime("%y%m%d_%H%M")
BK = r"c:\Users\박근민\Desktop\NEW_ERP_1\_schema\sp_backup_partworker_{}".format(STAMP)
T = "PR_M_PROC_GAGONG_WORKER"
RX = re.compile(r"\b(?:(?:PARTNER_ERP_TEST3\.)?(?:nx|dbo)\.)?{}\b".format(T), re.I)


def mask(s):
    s = re.sub(r"/\*.*?\*/", lambda m: " " * len(m.group(0)), s, flags=re.S)
    return re.sub(r"--[^\n]*", lambda m: " " * len(m.group(0)), s)


nx = _nx(); nx.autocommit = False
cur = nx.cursor()

# 웹이 부르는 SP 이름 수집
RD = os.path.join(BE, "routers")
RXS = re.compile(r"SP_[\w가-힣]+|TR_[\w가-힣]+|f_[\w가-힣]+")
called = set()
for f in ["common.py", "live_api.py", "app.py"] + \
         [os.path.join("routers", x) for x in sorted(os.listdir(RD)) if x.endswith(".py")]:
    p = os.path.join(BE, f)
    if not os.path.exists(p): continue
    for ln in open(p, encoding="utf-8").read().split("\n"):
        if ln.lstrip().startswith("#"): continue
        for m in RXS.finditer(ln): called.add(m.group(0))

cur.execute("""SELECT o.object_id, o.name, s.name, sm.definition FROM sys.sql_modules sm
                 JOIN sys.objects o ON o.object_id=sm.object_id
                 JOIN sys.schemas s ON s.schema_id=o.schema_id
                WHERE sm.definition LIKE ?""", "%{}%".format(T))
mods = [(a, str(b), str(c), d) for a, b, c, d in cur.fetchall()]

print("=" * 96)
print(" SP 작업자 치환 — {} → nx.v_part_worker".format(T))
print(" 모드: {}".format("★실제 반영(--apply)" if APPLY else "조회만(dry-run)"))
print("=" * 96)

tot = dead = 0
for _oid, nm, sch, d in mods:
    m = mask(d)
    spans = [x.span() for x in RX.finditer(m)]
    if not spans: continue
    if nm not in called:
        dead += len(spans); continue
    print("\n■ {}.{:<44s} {}곳".format(sch, nm, len(spans)))
    for a, b in spans[:6]:
        ls = d.rfind("\n", 0, a) + 1
        print("     {}".format(d[ls:d.find("\n", b)].strip()[:88]))
    tot += len(spans)
    if not APPLY: continue
    os.makedirs(BK, exist_ok=True)
    open(os.path.join(BK, "{}.{}.sql".format(sch, nm)), "w", encoding="utf-8").write(d)
    new = d
    for a, b in reversed(spans):
        new = new[:a] + "nx.v_part_worker" + new[b:]
    alt = re.sub(r"^\s*CREATE\s+(PROCEDURE|PROC|FUNCTION)\b", r"ALTER \1", new, count=1, flags=re.I)
    if alt == new:
        print("     ★CREATE 를 못 찾음 — 건너뜀"); continue
    try:
        cur.execute(alt); print("     ✔ 반영")
    except Exception as e:
        nx.rollback(); print("     ★실패 — 롤백: {}".format(str(e)[:160])); nx.close(); sys.exit(1)

print("\n" + "=" * 96)
print(" 웹호출 {}곳 · 미호출(구버전) {}곳 — 후자는 미터치".format(tot, dead))
if APPLY:
    ok = True
    try:
        cur.execute("EXEC [dbo].[SP_PR_가공생산진척관리_260602] ?, ?, ?", "260909", "260916", "P2")
        print(" 420 실행 {}행".format(len(cur.fetchall())))
    except Exception as e:
        ok = False; print(" ★420 실패: {}".format(str(e)[:160]))
    if ok:
        nx.commit(); print(" ✅ 치환 {}곳 커밋 · 백업 {}".format(tot, BK))
    else:
        nx.rollback(); print(" ★실행 검증 실패 — 롤백"); nx.close(); sys.exit(1)
else:
    nx.rollback(); print(" ※dry-run — 반영하려면 --apply")
nx.close()
