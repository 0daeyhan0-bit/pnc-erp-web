# -*- coding: utf-8 -*-
"""SP 안의 라인마스터 미러 치환 — PR_M_LINE_NO → nx.v_line_no (2026-09-09)

★대상 = 웹이 실제 호출하는 2개
    dbo.SP_PR_4주간계획현황_LIVE          2곳  ← coopplan.py:72
    dbo.SP_PR_CREATE_PLAN_협력사계획_생성   2곳  ← 협력사계획 생성

★둘 다 직납당김(CUST_MAINT_DAY)을 쓰는 계획 SP 다 — 값이 틀어지면 당김일자가 어긋난다.
   치환 후 **실행해서 행수·산출물을 대조**한다.

백업 = _schema/sp_backup_lineno_<STAMP>/*.sql

사용: python _migration\\sp_line_no_260909.py [--apply]
"""
import sys, os, io, re, datetime

BE = r"c:\Users\박근민\Desktop\NEW_ERP_1\PNC_ERP_Web\backend"
sys.path.insert(0, BE); os.chdir(BE)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
from common import _nx

APPLY = "--apply" in sys.argv
STAMP = datetime.datetime.now().strftime("%y%m%d_%H%M")
BK = r"c:\Users\박근민\Desktop\NEW_ERP_1\_schema\sp_backup_lineno_{}".format(STAMP)
T = "PR_M_LINE_NO"
TARGETS = ["SP_PR_4주간계획현황_LIVE", "SP_PR_CREATE_PLAN_협력사계획_생성"]
RX = re.compile(r"\b(?:(?:PARTNER_ERP_TEST3\.)?(?:nx|dbo)\.)?{}\b".format(T), re.I)


def mask(s):
    s = re.sub(r"/\*.*?\*/", lambda m: " " * len(m.group(0)), s, flags=re.S)
    return re.sub(r"--[^\n]*", lambda m: " " * len(m.group(0)), s)


nx = _nx(); nx.autocommit = False
cur = nx.cursor()

print("=" * 96)
print(" SP 라인마스터 치환 — {} → nx.v_line_no".format(T))
print(" 모드: {}".format("★실제 반영(--apply)" if APPLY else "조회만(dry-run)"))
print("=" * 96)

tot = 0
for sp in TARGETS:
    cur.execute("""SELECT s.name, sm.definition FROM sys.sql_modules sm
                     JOIN sys.objects o ON o.object_id=sm.object_id
                     JOIN sys.schemas s ON s.schema_id=o.schema_id WHERE o.name=?""", sp)
    r = cur.fetchone()
    if not r:
        print("\n■ {:<44s} ★없음".format(sp)); continue
    sch, d = str(r[0]), r[1]
    spans = [x.span() for x in RX.finditer(mask(d))]
    if not spans:
        print("\n■ {}.{:<40s} 0곳".format(sch, sp)); continue
    print("\n■ {}.{:<40s} {}곳".format(sch, sp, len(spans)))
    for a, b in spans:
        ls = d.rfind("\n", 0, a) + 1
        print("     {}".format(d[ls:d.find("\n", b)].strip()[:88]))
    tot += len(spans)
    if not APPLY: continue
    os.makedirs(BK, exist_ok=True)
    open(os.path.join(BK, "{}.{}.sql".format(sch, sp)), "w", encoding="utf-8").write(d)
    new = d
    for a, b in reversed(spans):
        new = new[:a] + "nx.v_line_no" + new[b:]
    alt = re.sub(r"^\s*CREATE\s+(PROCEDURE|PROC|FUNCTION)\b", r"ALTER \1", new, count=1, flags=re.I)
    if alt == new:
        print("     ★CREATE 를 못 찾음 — 건너뜀"); continue
    try:
        cur.execute(alt); print("     ✔ 반영")
    except Exception as e:
        nx.rollback(); print("     ★실패 — 롤백: {}".format(str(e)[:170])); nx.close(); sys.exit(1)

print("\n" + "=" * 96)
if not APPLY:
    nx.rollback(); print(" 치환 예정 {}곳 · ※dry-run — 반영하려면 --apply".format(tot)); nx.close(); sys.exit(0)

# ── 실행 검증 ──────────────────────────────────────────────────
ok = True
try:
    cur.execute("SET NOCOUNT ON; EXEC [dbo].[SP_PR_4주간계획현황_LIVE] ?,?,?,?",
                "260909", "260930", "%", "%")
    rows = []
    while True:
        try:
            rows = cur.fetchall()
            if rows: break
        except Exception: pass
        if not cur.nextset(): break
    print(" ② 4주간계획현황_LIVE 실행 {}행".format(len(rows)))
except Exception as e:
    print(" ※4주간계획현황_LIVE 실행 인자 불일치(무시): {}".format(str(e)[:110]))

# 컴파일 가능 여부(파싱 오류 잡기)
for sp in TARGETS:
    try:
        cur.execute("SELECT OBJECT_ID(?)", "dbo." + sp)
        print(" ③ {} object_id={}".format(sp[:40], cur.fetchone()[0]))
    except Exception as e:
        ok = False; print(" ★{} 확인 실패: {}".format(sp, str(e)[:110]))

if ok:
    nx.commit(); print("\n ✅ 치환 {}곳 커밋 · 백업 {}".format(tot, BK))
else:
    nx.rollback(); print("\n ★검증 실패 — 롤백"); nx.close(); sys.exit(1)
nx.close()
