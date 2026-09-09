# -*- coding: utf-8 -*-
"""파트마스터 코드 전환 — nx.PR_M_PROC_GAGONG → nx.v_part_master (2026-09-09)

seed_part_master_260909.py 로 클린을 만든 뒤 실행한다(순서 중요 — §1-9-1).

★어제 겪은 함정 셋을 모두 반영한다
  ① 이중 접두어 — `{S}.PR_M_PROC_GAGONG` 를 `{S}.nx.v_part_master` 로 바꾸면 깨진다.
     변수 스키마(S·SCH·NXS·P)는 이미 "PARTNER_ERP_TEST3.nx" 또는 "nx." 라
     테이블명만 갈아야 한다 → `{S}.v_part_master`
  ② 설명 문장 — 같은 줄에 SQL 키워드가 없으면 원문 보존.
     특히 qareview.py L13 은 **레거시 버그를 인용한 주석**이라 바꾸면 기록이 훼손된다.
  ③ 조인 별칭 — 뷰가 미러 컬럼명을 그대로 노출하므로 별칭 참조는 무영향.

★_WORKER 는 별개 테이블 — `PR_M_PROC_GAGONG_WORKER` 는 건드리지 않는다(부정 전방탐색).
★쓰기(partmaster.py)는 뷰가 아니라 실테이블 — 이 스크립트가 아니라 수동 편집.

사용: python _migration\\switch_part_master_260909.py [--apply]
"""
import sys, os, io, re, shutil, datetime

BE = r"c:\Users\박근민\Desktop\NEW_ERP_1\PNC_ERP_Web\backend"
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
APPLY = "--apply" in sys.argv
STAMP = datetime.datetime.now().strftime("%y%m%d_%H%M")

# ★_WORKER 제외 = (?!_)
PAT3 = re.compile(r"\bPARTNER_ERP_TEST3\.nx\.PR_M_PROC_GAGONG(?!_)", re.I)   # 3부 이름
PATV = re.compile(r"(\{(?:S|SCH|NXS|P)\}\.?)PR_M_PROC_GAGONG(?!_)", re.I)     # 변수 스키마
PATN = re.compile(r"\bnx\.PR_M_PROC_GAGONG(?!_)", re.I)                       # nx. 접두
PATB = re.compile(r"\bPR_M_PROC_GAGONG(?!_)", re.I)                           # 접두어 없음
ANY = re.compile(r"\bPR_M_PROC_GAGONG(?!_)", re.I)
SQLKW = re.compile(r"\b(FROM|JOIN|INTO|UPDATE|DELETE|EXISTS|SELECT|TABLE|COL_LENGTH)\b", re.I)

# 쓰기 경로 — 뷰로 바꾸면 안 되므로 이 스크립트에서 제외(수동 편집)
SKIP = {"partmaster.py"}

RD = os.path.join(BE, "routers")
files = ["common.py", "live_api.py", "app.py"] + \
        [os.path.join("routers", x) for x in sorted(os.listdir(RD)) if x.endswith(".py")]

print("=" * 96)
print(" 파트마스터 코드 전환 — nx.PR_M_PROC_GAGONG → nx.v_part_master")
print(" 모드: {}".format("★실제 반영(--apply)" if APPLY else "조회만(dry-run)"))
print("=" * 96)

BK = os.path.join(r"c:\Users\박근민\Desktop\NEW_ERP_1\_schema", "bk_partmaster_{}".format(STAMP))
tot = skipped = 0
for f in files:
    p = os.path.join(BE, f)
    if not os.path.exists(p): continue
    src = open(p, encoding="utf-8").read()
    if not ANY.search(src): continue
    base = os.path.basename(f)
    lines = src.split("\n")
    out, n, keep = [], 0, []
    for i, ln in enumerate(lines, 1):
        if not ANY.search(ln):
            out.append(ln); continue
        # 설명 문장·주석 — 원문 보존
        if ln.lstrip().startswith("#") or not SQLKW.search(ln):
            out.append(ln); keep.append((i, ln.strip()[:70])); continue
        if base in SKIP:
            out.append(ln); keep.append((i, "[쓰기경로 — 수동] " + ln.strip()[:56])); continue
        new = PAT3.sub("PARTNER_ERP_TEST3.nx.v_part_master", ln)
        new = PATV.sub(lambda m: m.group(1) + "v_part_master", new)
        new = PATN.sub("nx.v_part_master", new)
        new = PATB.sub("nx.v_part_master", new)          # 접두어 없는 잔여
        if new != ln: n += 1
        out.append(new)
    if n or keep:
        print("\n■ {:<26s} 치환 {:<3d} 보존 {}".format(f, n, len(keep)))
        for i, s in keep: print("     보존 L{:<5d} {}".format(i, s))
    tot += n; skipped += len(keep)
    if n and APPLY:
        os.makedirs(BK, exist_ok=True)
        shutil.copy2(p, os.path.join(BK, base))
        open(p, "w", encoding="utf-8", newline="").write("\n".join(out))

print("\n" + "=" * 96)
print(" 치환 {}곳 · 보존 {}곳".format(tot, skipped))
if APPLY:
    print(" 백업 = {}".format(BK))
    # 이중 접두어 재점검 (어제 8곳 사고)
    bad = 0
    for f in files:
        p = os.path.join(BE, f)
        if not os.path.exists(p): continue
        for i, ln in enumerate(open(p, encoding="utf-8").read().split("\n"), 1):
            if re.search(r"\}\.nx\.v_part_master|nx\.nx\.", ln):
                print("   ★이중접두어 {} L{}  {}".format(os.path.basename(f), i, ln.strip()[:70])); bad += 1
    print(" 이중접두어 점검: {}".format("✔ 없음" if bad == 0 else "★{}곳".format(bad)))
else:
    print(" ※dry-run — 반영하려면 --apply")
