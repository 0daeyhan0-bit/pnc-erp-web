# -*- coding: utf-8 -*-
"""달력 미러 직독 → 클린(호환뷰) 전환 (2026-09-09)

★무엇을 — 라우터 7개·19곳이 달력 미러를 직독하고 있다. 이를 호환뷰로 바꾼다.

    nx.HR_M_CALENDAR       → nx.v_cal_work    (work_calendar)
    nx.PR_M_LINE_CALENDAR  → nx.v_cal_line    (line_calendar)
    nx.PR_M_PART_CALENDAR  → nx.v_cal_part    (part_calendar)

★왜 — 클린은 2026-07-23 에 미러를 복사해 만든 스냅샷인데 코드는 계속 미러를 읽었다.
   그래서 화면에서 달력을 고쳐도 편성·키팅·가공에 반영되지 않았고,
   컷오버로 레거시가 은퇴하면 미러가 얼어붙어 **달력이 영영 안 바뀐다**(§1-9-1).
   전환 전 클린을 최신으로 맞춰두었다(sync_calendar_260909.py — 14건).

★왜 뷰인가 — 컬럼명·형식이 달라 단순 치환이 안 된다.
   미러 모양 그대로 노출하는 뷰를 쓰면 WHERE·SUBSTRING 을 그대로 둘 수 있어
   변경 폭이 '테이블명 한 단어'로 줄고, 되돌리기도 쉽다.
   뷰는 make_calendar_views_260909.py 로 만들고 미러와 diff0 검증을 마쳤다.

★안전 — 주석 줄은 건드리지 않는다(설명에 미러명이 남아야 경위를 안다).
   대소문자 무관 치환(실측: pr_m_line_calendar 소문자 표기도 있다).
   --apply 없으면 미리보기만.

사용: python _migration\\switch_calendar_to_clean_260909.py [--apply]
"""
import sys, os, io, re, shutil, datetime

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
RD = r"c:\Users\박근민\Desktop\NEW_ERP_1\PNC_ERP_Web\backend\routers"
APPLY = "--apply" in sys.argv
STAMP = datetime.datetime.now().strftime("%y%m%d_%H%M")

MAP = [
    (re.compile(r"nx\.HR_M_CALENDAR", re.I), "nx.v_cal_work"),
    (re.compile(r"nx\.PR_M_LINE_CALENDAR", re.I), "nx.v_cal_line"),
    (re.compile(r"nx\.PR_M_PART_CALENDAR", re.I), "nx.v_cal_part"),
]
FILES = ["planrev.py", "kitting.py", "gagong.py", "matinput.py",
         "setinstat.py", "coopplan.py", "prodinfo.py"]

print("=" * 100)
print(" 달력 미러 직독 → 클린(호환뷰) 전환")
print(" 모드: {}".format("★실제 반영(--apply)" if APPLY else "미리보기(dry-run)"))
print("=" * 100)

total = 0
for f in FILES:
    p = os.path.join(RD, f)
    if not os.path.exists(p):
        print("\n   {} — 없음".format(f)); continue
    src = open(p, encoding="utf-8").read()
    lines = src.split("\n")
    out, hits = [], []
    for i, ln in enumerate(lines, 1):
        stripped = ln.lstrip()
        # ★주석 줄은 원문 보존 — 경위 설명에 미러명이 남아야 한다
        if stripped.startswith("#"):
            out.append(ln); continue
        new = ln
        for rx, rep in MAP:
            new = rx.sub(rep, new)
        if new != ln:
            hits.append((i, ln.strip()[:88], new.strip()[:88]))
        out.append(new)
    if not hits:
        print("\n   {} — 변경 없음".format(f)); continue
    print("\n   ── {} ({}곳)".format(f, len(hits)))
    for ln, a, b in hits:
        print("      L{:<6d} {}".format(ln, a))
        print("             → {}".format(b))
    total += len(hits)
    if APPLY:
        shutil.copy2(p, p + ".bak_{}".format(STAMP))
        open(p, "w", encoding="utf-8").write("\n".join(out))

print()
print("=" * 100)
print("   합계 {}곳".format(total))
if not APPLY:
    print("   ※dry-run — 반영하려면 --apply")
else:
    print("   ✅ 반영 완료 (원본은 *.bak_{} 로 백업)".format(STAMP))
    print("   다음: py_compile → 백엔드 재기동 → 편성/키팅 화면 확인")
