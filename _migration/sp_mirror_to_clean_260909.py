# -*- coding: utf-8 -*-
"""SP 안의 미러 직독 → 클린 호환뷰 치환 · 1단계 (2026-09-09)

★무엇을 — 웹이 실제로 호출하는 SP 6개 안에서, **클린 대체본이 이미 있는 미러 4종**을
   호환뷰로 바꾼다. SP 를 다시 쓰는 게 아니라 **테이블명만 치환**한다.

     nx.PR_M_WORK          → nx.v_work_place     (← work_place)
     nx.PR_M_WORK_SINGLE   → nx.v_work_single    (← prodinfo_single)
     nx.HR_M_CALENDAR      → nx.v_cal_work       (← work_calendar)
     nx.PR_M_LINE_CALENDAR → nx.v_cal_line       (← line_calendar)

★왜 — 이 SP 들이 미러를 읽고 있어 테이블 은퇴를 막고 있었다(실측: rename 시도 시 143개 객체 참조).
   컷오버로 미러가 얼어붙으면 **편성·가공 화면이 옛 값을 조용히 계속 읽는다**(§1-9-1).

★2단계로 미룬 것 — 클린 대체본은 있으나 **컬럼명이 달라** 호환뷰를 먼저 만들어야 하는 것:
     PR_M_ITEM(46) · PR_M_PROC_GAGONG(20) · PR_M_ITEM_PROC_GAGONG(17)
     PR_M_ITEM_BOM(13) · CM_M_CUST(6) · PR_M_ITEM_SUB(1)
   (IN_CUST_CODE vs in_cust 같은 이름 차이 — 2026-09-08 에 이미 겪은 함정)

★안전
   · 원본 정의를 파일로 백업(_schema/sp_backup_<stamp>/)
   · 주석(-- , /* */) 안의 이름은 건드리지 않는다
   · 치환 후 ALTER 가 실패하면 그 SP 는 원본 유지(개별 트랜잭션)
   · --apply 없으면 미리보기만

사용: python _migration\\sp_mirror_to_clean_260909.py [--apply]
"""
import sys, os, io, re, datetime

BE = r"c:\Users\박근민\Desktop\NEW_ERP_1\PNC_ERP_Web\backend"
ROOT = r"c:\Users\박근민\Desktop\NEW_ERP_1"
sys.path.insert(0, BE); os.chdir(BE)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
from common import _nx

STAMP = datetime.datetime.now().strftime("%y%m%d_%H%M")
APPLY = "--apply" in sys.argv
BKDIR = os.path.join(ROOT, "_schema", "sp_backup_{}".format(STAMP))

SPS = [
    ("SP_PR_CREATE_PLAN_파트별계획_생성_파트휴무당김", "편성 STEP6 (planrev.py)"),
    ("SP_PR_CREATE_PLAN_파트별_생산계획계산_NEW_250826", "파트별 계획 (kitting.py)"),
    ("SP_PR_가공창고_이동계획_WEBPLAN", "가공창고 이동계획 580 (gagongmove.py)"),
    ("SP_PR_가공창고_이동계획_260213", "가공창고 이동계획 구 (gagongmove.py)"),
    ("SP_PR_4주간_가공계획현황_250703", "4주간 가공계획현황 (gagong.py)"),
    ("SP_PR_가공생산진척관리_260602", "가공생산진척관리 420 (gagong.py)"),
]

# ★SP 안에서는 **스키마 접두어 없이 소문자**로 부른다(실측):
#     join pr_m_item c ... / select work_desc from pr_m_work where ...
#   SP 가 nx 스키마에 있으므로 접두어 없이 쓰면 같은 스키마에서 찾는다.
#   그래서 `nx.` 유무를 모두 받는다. _SINGLE·_ASSY 가 PR_M_WORK 에 걸리지 않게 긴 이름부터.
MAP = [
    (re.compile(r"\b(?:nx\.)?PR_M_WORK_SINGLE\b", re.I), "nx.v_work_single"),
    (re.compile(r"\b(?:nx\.)?PR_M_LINE_CALENDAR\b", re.I), "nx.v_cal_line"),
    (re.compile(r"\b(?:nx\.)?HR_M_CALENDAR\b", re.I), "nx.v_cal_work"),
    (re.compile(r"\b(?:nx\.)?PR_M_WORK(?![_\w])", re.I), "nx.v_work_place"),
]

nx = _nx(); nx.autocommit = True      # ALTER 는 개별 실행
cur = nx.cursor()

print("=" * 96)
print(" SP 미러 → 클린(호환뷰) 치환 · 1단계")
print(" 모드: {}".format("★실제 반영(--apply)" if APPLY else "미리보기(dry-run)"))
print("=" * 96)


def strip_comments(s):
    """주석을 공백으로 바꾼 사본 — 치환 대상 위치 판정에만 쓴다(원문은 보존)."""
    s = re.sub(r"/\*.*?\*/", lambda m: " " * len(m.group(0)), s, flags=re.S)
    s = re.sub(r"--[^\n]*", lambda m: " " * len(m.group(0)), s)
    return s


total = 0
done, failed = [], []
if APPLY and not os.path.isdir(BKDIR):
    os.makedirs(BKDIR)

for sp, nm in SPS:
    cur.execute("""SELECT sm.definition FROM sys.sql_modules sm
                     JOIN sys.objects o ON o.object_id=sm.object_id WHERE o.name=?""", sp)
    r = cur.fetchone()
    if not r:
        print("\n   ── {}  ★DB에 없음".format(nm)); continue
    d = r[0] or ""
    masked = strip_comments(d)

    # 주석 밖에서만 치환 — masked 에서 위치를 찾아 원문 d 에 적용
    hits = []
    for rx, rep in MAP:
        for m in rx.finditer(masked):
            hits.append((m.start(), m.end(), rep, d[m.start():m.end()]))
    hits.sort(key=lambda x: -x[0])         # 뒤에서부터 치환(오프셋 유지)
    new = d
    for s0, e0, rep, orig in hits:
        new = new[:s0] + rep + new[e0:]

    print("\n   ── {}".format(nm))
    print("      {}".format(sp))
    if not hits:
        print("      치환 대상 없음"); continue
    cnt = {}
    for _s, _e, rep, orig in hits:
        cnt[orig + " → " + rep] = cnt.get(orig + " → " + rep, 0) + 1
    for k, v in sorted(cnt.items()):
        print("      {:<52s} {}곳".format(k, v))
    total += len(hits)

    if not APPLY:
        continue

    # 백업
    bkp = os.path.join(BKDIR, sp + ".sql")
    with io.open(bkp, "w", encoding="utf-8") as f:
        f.write(d)

    # ALTER — CREATE PROCEDURE → ALTER PROCEDURE
    alt = re.sub(r"^\s*CREATE\s+(PROCEDURE|PROC)\b", "ALTER \\1", new, count=1, flags=re.I)
    if alt == new:
        alt = re.sub(r"\bCREATE\s+(PROCEDURE|PROC)\b", "ALTER \\1", new, count=1, flags=re.I)
    try:
        cur.execute(alt)
        print("      ✅ ALTER 적용 ({}곳) · 백업 {}".format(len(hits), os.path.basename(bkp)))
        done.append(sp)
    except Exception as e:
        print("      ★ALTER 실패 — 원본 유지: {}".format(str(e)[:150]))
        failed.append((sp, str(e)[:200]))

print()
print("=" * 96)
print("   치환 대상 합계 {}곳".format(total))
if not APPLY:
    print("   ※dry-run — 반영하려면 --apply")
    nx.close(); sys.exit(0)

print("   적용 {}개 · 실패 {}개".format(len(done), len(failed)))
if failed:
    for sp, e in failed:
        print("      ★{} : {}".format(sp, e))

# ── 검증 — 남은 미러 참조 ──────────────────────────────────────
print()
print("=" * 96)
print(" 검증 — SP 안에 미러 4종이 남았나")
print("=" * 96)
left = 0
for sp, nm in SPS:
    cur.execute("""SELECT sm.definition FROM sys.sql_modules sm
                     JOIN sys.objects o ON o.object_id=sm.object_id WHERE o.name=?""", sp)
    r = cur.fetchone()
    if not r: continue
    masked = strip_comments(r[0] or "")
    n = sum(len(rx.findall(masked)) for rx, _ in MAP)
    left += n
    print("   {:<46s} {}곳 {}".format(nm[:46], n, "OK" if n == 0 else "★남음"))
print("\n   → 합계 {}곳 {}".format(left, "★1단계 완료" if left == 0 else ""))
print("""
   되돌리려면 백업 폴더의 .sql 을 그대로 실행(CREATE→ALTER 로 바꿔서):
     {}

   ※다음: 백엔드 재기동 후 아래를 확인
     파트별 생산계획(편성) · 준비실적처리(키팅) · 가공창고 이동계획 · 4주간 가공계획 · 420""".format(BKDIR))
nx.close()
