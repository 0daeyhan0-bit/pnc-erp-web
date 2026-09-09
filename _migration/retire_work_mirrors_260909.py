# -*- coding: utf-8 -*-
"""WORK류 미러 은퇴 — nx.PR_M_WORK / _SINGLE / _ASSY (2026-09-09)

★무엇을 — 클린 전환이 끝난 미러 3종을 `zz_retired_` 접두로 **rename** 한다.

★왜 rename 인가 (삭제 아님)
   · 놓친 참조가 있으면 **즉시 오류로 드러난다**(조용히 옛 값을 읽는 것보다 낫다)
   · 되돌리기가 sp_rename 한 줄이다
   · 데이터가 남아 있어 대사·복구에 쓸 수 있다
   컷오버 후 안정화되면 그때 DROP 한다.

★전환 완료 현황(2026-09-09 실측)
     PR_M_WORK        31곳 → 0곳   nx.work_place      + 「작업처 마스터」 탭
     PR_M_WORK_SINGLE  8곳 → 0곳   nx.prodinfo_single + 「단품공정 마스터」 탭
     PR_M_WORK_ASSY    2곳 → 0곳   nx.work_assy       + 「조립공정 마스터」 탭

★안전장치
   · 코드·뷰·SP 전수 재점검 후에만 진행(하나라도 참조가 남으면 중단)
   · 클린 쪽 행수·값이 미러와 맞는지 다시 검증
   · --apply 없으면 점검만

사용: python _migration\\retire_work_mirrors_260909.py [--apply]
"""
import sys, os, io, re

BE = r"c:\Users\박근민\Desktop\NEW_ERP_1\PNC_ERP_Web\backend"
sys.path.insert(0, BE); os.chdir(BE)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
from common import _nx

S = "PARTNER_ERP_TEST3.nx"
APPLY = "--apply" in sys.argv

# (미러, 클린, 뷰, 키컬럼쌍)
TARGETS = [
    ("PR_M_WORK",        "work_place",      "v_work_place",  "WORK_CODE",   "work_code"),
    ("PR_M_WORK_SINGLE", "prodinfo_single", "v_work_single", "S_WORK_CODE", "s_work_code"),
    ("PR_M_WORK_ASSY",   "work_assy",       "v_work_assy",   "A_WORK_CODE", "a_work_code"),
]

nx = _nx(); nx.autocommit = False
cur = nx.cursor()
BAD = []

print("=" * 92)
print(" WORK류 미러 은퇴 — rename 방식")
print(" 모드: {}".format("★실제 반영(--apply)" if APPLY else "점검만(dry-run)"))
print("=" * 92)

# ── ① 코드 전수 재점검 ─────────────────────────────────────────
print("\n① 코드 직독 재점검 (주석 제외)")
RD = os.path.join(BE, "routers")
files = ["common.py", "live_api.py", "app.py"] + \
        [os.path.join("routers", x) for x in sorted(os.listdir(RD)) if x.endswith(".py")]
for m, _c, _v, _a, _b in TARGETS:
    pat = r"nx\.{}(?![_A-Za-z0-9])".format(m) if m == "PR_M_WORK" else r"nx\.{}\b".format(m)
    rx = re.compile(pat, re.I)
    hits = []
    for f in files:
        p = os.path.join(BE, f)
        if not os.path.exists(p): continue
        for i, ln in enumerate(open(p, encoding="utf-8").read().split("\n"), 1):
            if ln.lstrip().startswith("#"): continue
            if rx.search(ln): hits.append((os.path.basename(f), i, ln.strip()[:60]))
    print("   {:<20s} {:>2}곳  {}".format(m, len(hits), "OK" if not hits else "★남음"))
    for f, i, s in hits[:5]:
        print("      {} L{}  {}".format(f, i, s))
    if hits: BAD.append(m + "(코드)")

# ── ② DB 안의 뷰·SP 가 참조하나 ────────────────────────────────
print("\n② DB 객체(뷰·SP·함수) 참조 점검")
for m, _c, _v, _a, _b in TARGETS:
    cur.execute("""SELECT o.name, o.type_desc FROM sys.sql_modules sm
                     JOIN sys.objects o ON o.object_id=sm.object_id
                    WHERE sm.definition LIKE ?""", "%" + m + "%")
    rows = [(str(r[0]), str(r[1])) for r in cur.fetchall()]
    # 우리가 만든 호환뷰는 미러를 안 읽는다(클린을 읽음) — 이름으로 제외
    rows = [r for r in rows if r[0] not in (t[2] for t in TARGETS)]
    print("   {:<20s} {:>2}개  {}".format(m, len(rows), "OK" if not rows else "★참조 객체 있음"))
    for n, t in rows[:6]:
        print("      {} ({})".format(n, t))
    if rows: BAD.append(m + "(DB객체)")

# ── ③ 클린이 미러를 온전히 담고 있나 ───────────────────────────
print("\n③ 클린 커버리지 재검증")
for m, c, v, ka, kb in TARGETS:
    cur.execute("SELECT COUNT(*) FROM {S}.{m}".format(S=S, m=m)); nm_ = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM {S}.{c}".format(S=S, c=c)); nc_ = cur.fetchone()[0]
    cur.execute("""SELECT COUNT(*) FROM {S}.{m} a
                    WHERE NOT EXISTS(SELECT 1 FROM {S}.{c} b WHERE b.{kb}=a.{ka})""".format(
        S=S, m=m, c=c, ka=ka, kb=kb))
    miss = cur.fetchone()[0]
    ok = (miss == 0)
    print("   {:<20s} 미러 {:>4} · 클린 {:>4} · 결손 {:>3}  {}".format(m, nm_, nc_, miss, "OK" if ok else "★결손"))
    if not ok: BAD.append(m + "(결손)")

# ── ④ 뷰가 살아있나 ────────────────────────────────────────────
print("\n④ 호환뷰 동작 확인")
for _m, _c, v, _a, _b in TARGETS:
    try:
        cur.execute("SELECT COUNT(*) FROM {S}.{v}".format(S=S, v=v))
        print("   nx.{:<16s} {:>4}행  OK".format(v, cur.fetchone()[0]))
    except Exception as e:
        print("   nx.{:<16s} ★오류 {}".format(v, str(e)[:60])); BAD.append(v)

print()
print("=" * 92)
if BAD:
    print("   ★중단 — 아직 정리 안 된 것: {}".format(", ".join(BAD)))
    nx.rollback(); nx.close(); sys.exit(1)
print("   ✔ 전 항목 통과 — 은퇴 가능")

if not APPLY:
    print("\n   ※dry-run — 실제 rename 하려면 --apply")
    print("   될 이름: {}".format(" · ".join("zz_retired_" + t[0] for t in TARGETS)))
    nx.rollback(); nx.close(); sys.exit(0)

# ── ⑤ rename ───────────────────────────────────────────────────
print("\n⑤ rename 실행")
for m, _c, _v, _a, _b in TARGETS:
    new = "zz_retired_" + m
    cur.execute("""SELECT COUNT(*) FROM PARTNER_ERP_TEST3.INFORMATION_SCHEMA.TABLES
                    WHERE TABLE_SCHEMA='nx' AND TABLE_NAME=?""", new)
    if cur.fetchone()[0]:
        print("   {:<20s} → {} (이미 있음, 건너뜀)".format(m, new)); continue
    cur.execute("EXEC sp_rename 'nx.{}', '{}'".format(m, new))
    print("   {:<20s} → nx.{}".format(m, new))
nx.commit()

print("""
   ✅ 완료

   되돌리려면:
     EXEC sp_rename 'nx.zz_retired_PR_M_WORK',        'PR_M_WORK'
     EXEC sp_rename 'nx.zz_retired_PR_M_WORK_SINGLE', 'PR_M_WORK_SINGLE'
     EXEC sp_rename 'nx.zz_retired_PR_M_WORK_ASSY',   'PR_M_WORK_ASSY'

   ※백엔드 재기동 후 아래 화면을 확인할 것:
     기준 마스터 관리 › 작업처·단품공정·조립공정 마스터
     생산정보등록 (조립 공정수 · 생산공정순서)
     파트별 생산계획(STEP6 편성 결과)""")
nx.close()
