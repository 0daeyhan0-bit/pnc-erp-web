# -*- coding: utf-8 -*-
"""SP 안의 파트마스터 미러 치환 — PR_M_PROC_GAGONG → nx.v_part_master (2026-09-09)

★대상은 **웹이 실제 호출하는 6개**뿐. 나머지 73개(235곳)는 레거시 전용 구버전이라 안 만진다.
   같은 이름의 SP 가 날짜별로 여러 벌 있고 웹은 최신 한 벌만 부른다.

★SP 는 스키마 접두어 없이 소문자로 부른다 — `join pr_m_proc_gagong g`.
   `nx.PR_M_PROC_GAGONG` 형태만 찾으면 0곳이 나온다(2026-09-09 오전 실제로 겪음).
★주석 안의 인용은 건드리지 않는다(-- 와 /* */ 를 공백으로 지운 사본에서만 위치를 잡는다).

백업 = _schema/sp_backup_partmaster_<STAMP>/*.sql (원본 정의 전문)

사용: python _migration\\sp_part_master_260909.py [--apply]
"""
import sys, os, io, re, datetime

BE = r"c:\Users\박근민\Desktop\NEW_ERP_1\PNC_ERP_Web\backend"
sys.path.insert(0, BE); os.chdir(BE)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
from common import _nx

APPLY = "--apply" in sys.argv
STAMP = datetime.datetime.now().strftime("%y%m%d_%H%M")
BK = r"c:\Users\박근민\Desktop\NEW_ERP_1\_schema\sp_backup_partmaster_{}".format(STAMP)

TARGETS = ["SP_PR_4주간_가공계획현황_250703",
           "SP_PR_4주간계획현황_LIVE",
           "SP_PR_CREATE_PLAN_파트별_생산계획계산_생산준비등록_NEW",
           "SP_PR_가공생산진척관리_260602",
           "SP_PR_가공창고_이동계획_260213",
           "SP_PR_가공창고_이동계획_WEBPLAN"]

# _WORKER 제외 · 이미 붙은 스키마도 함께 흡수
RX = re.compile(r"\b(?:(?:PARTNER_ERP_TEST3\.)?(?:nx|dbo)\.)?PR_M_PROC_GAGONG(?!_)", re.I)


def mask(s):
    """주석을 같은 길이 공백으로 — 위치는 보존한 채 치환 대상에서 뺀다."""
    s = re.sub(r"/\*.*?\*/", lambda m: " " * len(m.group(0)), s, flags=re.S)
    return re.sub(r"--[^\n]*", lambda m: " " * len(m.group(0)), s)


nx = _nx(); nx.autocommit = False
cur = nx.cursor()

print("=" * 96)
print(" SP 파트마스터 치환 — PR_M_PROC_GAGONG → nx.v_part_master")
print(" 모드: {}".format("★실제 반영(--apply)" if APPLY else "조회만(dry-run)"))
print("=" * 96)

tot = 0
for sp in TARGETS:
    cur.execute("""SELECT o.object_id, sm.definition, s.name FROM sys.sql_modules sm
                     JOIN sys.objects o ON o.object_id=sm.object_id
                     JOIN sys.schemas s ON s.schema_id=o.schema_id WHERE o.name=?""", sp)
    r = cur.fetchone()
    if not r:
        print("\n■ {:<48s} ★없음".format(sp)); continue
    _oid, d, sch = r[0], r[1], str(r[2])
    m = mask(d)
    spans = [x.span() for x in RX.finditer(m)]
    if not spans:
        print("\n■ {}.{:<44s} 0곳(주석뿐)".format(sch, sp)); continue
    print("\n■ {}.{:<44s} {}곳".format(sch, sp, len(spans)))
    for a, b in spans[:8]:
        ls = d.rfind("\n", 0, a) + 1
        print("     {}".format(d[ls:d.find("\n", b)].strip()[:88]))
    tot += len(spans)
    if not APPLY: continue

    os.makedirs(BK, exist_ok=True)
    open(os.path.join(BK, "{}.{}.sql".format(sch, sp)), "w", encoding="utf-8").write(d)

    # 마스크에서 잡은 구간만 뒤에서부터 교체 → 주석·문자열 오염 없음
    new = d
    for a, b in reversed(spans):
        new = new[:a] + "nx.v_part_master" + new[b:]
    # CREATE → ALTER
    alt = re.sub(r"^\s*CREATE\s+(PROCEDURE|PROC)\b", r"ALTER \1", new, count=1, flags=re.I)
    if alt == new:
        print("     ★CREATE PROCEDURE 를 못 찾음 — 건너뜀"); continue
    try:
        cur.execute(alt); print("     ✔ 반영")
    except Exception as e:
        nx.rollback(); print("     ★실패 — 전체 롤백: {}".format(str(e)[:160])); nx.close(); sys.exit(1)

print("\n" + "=" * 96)
if APPLY:
    # 실행 확인 후에 커밋
    ok = True
    try:
        cur.execute("EXEC [dbo].[SP_PR_가공생산진척관리_260602] ?, ?, ?", "260909", "260916", "P2")
        print(" 420 실행 {}행".format(len(cur.fetchall())))
    except Exception as e:
        ok = False; print(" ★420 실패: {}".format(str(e)[:160]))
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
        print(" 580 실행 {}행".format(len(rows)))
    except Exception as e:
        ok = False; print(" ★580 실패: {}".format(str(e)[:160]))
    if ok:
        nx.commit(); print(" ✅ 치환 {}곳 커밋 · 백업 {}".format(tot, BK))
    else:
        nx.rollback(); print(" ★실행 검증 실패 — 롤백"); nx.close(); sys.exit(1)
else:
    nx.rollback(); print(" 치환 예정 {}곳 · ※dry-run — 반영하려면 --apply".format(tot))
nx.close()
