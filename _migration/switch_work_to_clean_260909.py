# -*- coding: utf-8 -*-
"""작업처 미러 직독 → 클린(호환뷰) 전환 (2026-09-09)

    nx.PR_M_WORK  →  nx.v_work_place  (← nx.work_place)

★왜 — 작업처가 네 곳에 흩어져 있었다(미러·백엔드상수·프론트상수·하드코드).
   미러는 컷오버에 얼어붙는다(§1-9-1). 클린 nx.work_place 로 모았다.

★호환 뷰를 쓰는 이유 — 28곳이 `LEFT JOIN nx.PR_M_WORK w ON w.WORK_CODE=...` 형태로
   `WORK_CODE`·`WORK_DESC` 를 참조한다. 뷰가 같은 컬럼명을 노출하므로 테이블명만 바꾸면 된다.

★주석은 건드리지 않는다(경위 설명에 미러명이 남아야 한다).
사용: python _migration\\switch_work_to_clean_260909.py [--apply]
"""
import sys, os, io, re, shutil, datetime

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
BE = r"c:\Users\박근민\Desktop\NEW_ERP_1\PNC_ERP_Web\backend"
RD = os.path.join(BE, "routers")
APPLY = "--apply" in sys.argv
STAMP = datetime.datetime.now().strftime("%y%m%d_%H%M")

# ★_SINGLE·_ASSY 는 건드리지 않는다 — 클린 대체본이 아직 없다(prodinfo_single 0행).
#   \b 로 끝을 막아 PR_M_WORK_SINGLE / PR_M_WORK_ASSY 가 안 걸리게 한다.
RX = re.compile(r"nx\.PR_M_WORK(?![_A-Za-z0-9])", re.I)
REP = "nx.v_work_place"

print("=" * 96)
print(" 작업처 미러 → 클린(호환뷰) 전환")
print(" 모드: {}".format("★실제 반영(--apply)" if APPLY else "미리보기(dry-run)"))
print("=" * 96)

targets = [BE + os.sep + "common.py"] + [os.path.join(RD, f) for f in sorted(os.listdir(RD)) if f.endswith(".py")]
total = 0
for p in targets:
    if not os.path.exists(p):
        continue
    name = os.path.basename(p)
    src = open(p, encoding="utf-8").read()
    lines = src.split("\n")
    out, hits = [], []
    for i, ln in enumerate(lines, 1):
        s = ln.lstrip()
        if s.startswith("#"):          # 주석 원문 보존
            out.append(ln); continue
        new = RX.sub(REP, ln)
        if new != ln:
            hits.append((i, ln.strip()[:86], new.strip()[:86]))
        out.append(new)
    if not hits:
        continue
    print("\n   ── {} ({}곳)".format(name, len(hits)))
    for ln, a, b in hits:
        print("      L{:<6d} {}".format(ln, a))
        print("             → {}".format(b))
    total += len(hits)
    if APPLY:
        shutil.copy2(p, p + ".bak_{}".format(STAMP))
        open(p, "w", encoding="utf-8").write("\n".join(out))

print()
print("=" * 96)
print("   합계 {}곳".format(total))
if not APPLY:
    print("   ※dry-run — 반영하려면 --apply")
else:
    print("   ✅ 반영 완료 (원본 *.bak_{})".format(STAMP))
