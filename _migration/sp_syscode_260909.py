# -*- coding: utf-8 -*-
"""SP 안의 공통코드 미러 치환 — CM_M_MASTER_DETAIL → nx.v_code_detail (2026-09-09)

★대상은 웹이 실제 호출하는 3개뿐.
    nx.SP_PR_가공창고_이동계획_WEBPLAN   PR008 품목구분   1곳
    dbo.SP_PR_가공창고_이동계획_260213   PR008           1곳
    dbo.f_get_weight3                   PR019 금속구분   1곳  ★중량 계산 — 값 검증 필수
  셋 다 읽는 코드군(PR008·PR019)이 **가져온 41종 안에 있다**(사전 확인 완료).

★f_get_weight3 는 스칼라 함수라 CREATE FUNCTION → ALTER FUNCTION.
  치환 후 **같은 인자로 값이 동일한지** 전수 대조한다(중량이 틀리면 원가·소요가 다 틀어진다).

백업 = _schema/sp_backup_syscode_<STAMP>/*.sql

사용: python _migration\\sp_syscode_260909.py [--apply]
"""
import sys, os, io, re, datetime

BE = r"c:\Users\박근민\Desktop\NEW_ERP_1\PNC_ERP_Web\backend"
sys.path.insert(0, BE); os.chdir(BE)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
from common import _nx

APPLY = "--apply" in sys.argv
STAMP = datetime.datetime.now().strftime("%y%m%d_%H%M")
BK = r"c:\Users\박근민\Desktop\NEW_ERP_1\_schema\sp_backup_syscode_{}".format(STAMP)
T = "CM_M_MASTER_DETAIL"
TARGETS = ["SP_PR_가공창고_이동계획_WEBPLAN", "SP_PR_가공창고_이동계획_260213", "f_get_weight3"]
RX = re.compile(r"\b(?:(?:PARTNER_ERP_TEST3\.)?(?:nx|dbo)\.)?{}\b".format(T), re.I)


def mask(s):
    s = re.sub(r"/\*.*?\*/", lambda m: " " * len(m.group(0)), s, flags=re.S)
    return re.sub(r"--[^\n]*", lambda m: " " * len(m.group(0)), s)


nx = _nx(); nx.autocommit = False
cur = nx.cursor()

print("=" * 96)
print(" SP 공통코드 치환 — {} → nx.v_code_detail".format(T))
print(" 모드: {}".format("★실제 반영(--apply)" if APPLY else "조회만(dry-run)"))
print("=" * 96)

# ── f_get_weight3 사전 채증 (치환 전 값) ──────────────────────
before = []
if APPLY:
    cur.execute("""SELECT TOP 300 item_code FROM PARTNER_ERP_TEST3.nx.item
                    WHERE ISNULL(item_code,'')<>'' ORDER BY item_code""")
    items = [str(r[0]).strip() for r in cur.fetchall()]
    for it in items:
        try:
            cur.execute("SELECT dbo.f_get_weight3(?)", it)
            before.append((it, cur.fetchone()[0]))
        except Exception:
            before.append((it, "ERR"))
    print("\n① f_get_weight3 사전 채증 {}건".format(len(before)))

tot = 0
for sp in TARGETS:
    cur.execute("""SELECT o.name, s.name, sm.definition, o.type FROM sys.sql_modules sm
                     JOIN sys.objects o ON o.object_id=sm.object_id
                     JOIN sys.schemas s ON s.schema_id=o.schema_id WHERE o.name=?""", sp)
    r = cur.fetchone()
    if not r:
        print("\n■ {:<40s} ★없음".format(sp)); continue
    sch, d = str(r[1]), r[2]
    spans = [x.span() for x in RX.finditer(mask(d))]
    if not spans:
        print("\n■ {}.{:<38s} 0곳".format(sch, sp)); continue
    print("\n■ {}.{:<38s} {}곳".format(sch, sp, len(spans)))
    for a, b in spans:
        ls = d.rfind("\n", 0, a) + 1
        print("     {}".format(d[ls:d.find("\n", b)].strip()[:88]))
    tot += len(spans)
    if not APPLY: continue
    os.makedirs(BK, exist_ok=True)
    open(os.path.join(BK, "{}.{}.sql".format(sch, sp)), "w", encoding="utf-8").write(d)
    new = d
    for a, b in reversed(spans):
        new = new[:a] + "nx.v_code_detail" + new[b:]
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

# ── 검증 ───────────────────────────────────────────────────────
ok = True
# f_get_weight3 값 전수 대조
diff = 0
for it, v0 in before:
    try:
        cur.execute("SELECT dbo.f_get_weight3(?)", it)
        v1 = cur.fetchone()[0]
    except Exception:
        v1 = "ERR"
    a = float(v0) if isinstance(v0, (int, float)) else v0
    b = float(v1) if isinstance(v1, (int, float)) else v1
    if isinstance(a, float) and isinstance(b, float):
        if abs(a - b) > 1e-9:
            diff += 1
            if diff <= 5: print("   ★중량 불일치 {} {} → {}".format(it, a, b))
    elif a != b:
        diff += 1
        if diff <= 5: print("   ★중량 불일치 {} {} → {}".format(it, a, b))
print(" ② f_get_weight3 전수 대조 {}건 — 불일치 {}".format(len(before), diff))
if diff: ok = False

# SP 실행
try:
    cur.execute("SET NOCOUNT ON; EXEC [PARTNER_ERP_TEST3].[nx].[SP_PR_가공창고_이동계획_WEBPLAN] ?,?,?,?,?,?",
                "260909", "260916", "P2", "IS0001", "", "")
    rows = []
    while True:
        try:
            rows = cur.fetchall()
            if rows: break
        except Exception: pass
        if not cur.nextset(): break
    print(" ③ 580 WEBPLAN 실행 {}행".format(len(rows)))
    if len(rows) != 359:
        print("    ★행수가 359 와 다르다 — 확인 필요")
except Exception as e:
    ok = False; print(" ★580 실패: {}".format(str(e)[:170]))

if ok:
    nx.commit(); print("\n ✅ 치환 {}곳 커밋 · 백업 {}".format(tot, BK))
else:
    nx.rollback(); print("\n ★검증 실패 — 전체 롤백"); nx.close(); sys.exit(1)
nx.close()
