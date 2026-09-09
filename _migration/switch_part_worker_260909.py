# -*- coding: utf-8 -*-
"""작업자 코드 전환 — PR_M_PROC_GAGONG_WORKER → nx.v_part_worker (2026-09-09)

seed_part_worker_260909.py 로 클린을 만든 뒤 실행한다(순서 중요 — §1-9-1).

★partmaster.py 는 제외 — 쓰기 7곳이 컬럼명까지 소문자로 바뀌므로 뷰로 대신할 수 없다(수동 편집 완료).
★설명 문장은 원문 보존(SQL 키워드가 같은 줄에 있어야 실제 쿼리로 판정).
★변수 스키마({SCH} 등)는 이미 "PARTNER_ERP_TEST3.nx" 라 테이블명만 간다(이중접두어 방지).

사용: python _migration\\switch_part_worker_260909.py [--apply]
"""
import sys, os, io, re, shutil, datetime

BE = r"c:\Users\박근민\Desktop\NEW_ERP_1\PNC_ERP_Web\backend"
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
APPLY = "--apply" in sys.argv
STAMP = datetime.datetime.now().strftime("%y%m%d_%H%M")
T = "PR_M_PROC_GAGONG_WORKER"

PAT3 = re.compile(r"\bPARTNER_ERP_TEST3\.nx\.{}\b".format(T), re.I)
PATV = re.compile(r"(\{(?:S|SCH|NXS|P)\}\.?)" + T + r"\b", re.I)
PATN = re.compile(r"\bnx\.{}\b".format(T), re.I)
PATB = re.compile(r"\b{}\b".format(T), re.I)
ANY = re.compile(r"\b{}\b".format(T), re.I)
# ★키워드가 **테이블명 바로 앞**에 있어야 실제 쿼리로 본다.
#   그냥 "같은 줄에 SQL 키워드가 있으면 SQL" 로 판정하면 설명 문장까지 바꾼다 —
#   실제로 gongsu.py:143 docstring 의 `exists=True 로 표시` 가 EXISTS 로 잡혔다.
SQLPRE = re.compile(r"\b(FROM|JOIN|INTO|UPDATE|DELETE\s+FROM|TABLE)\s+[\w\.\{\}\[\]]*"
                    + T + r"\b", re.I)

SKIP = {"partmaster.py"}     # 쓰기 경로 — 수동 편집 완료

RD = os.path.join(BE, "routers")
files = ["common.py", "live_api.py", "app.py"] + \
        [os.path.join("routers", x) for x in sorted(os.listdir(RD)) if x.endswith(".py")]

print("=" * 96)
print(" 작업자 코드 전환 — {} → nx.v_part_worker".format(T))
print(" 모드: {}".format("★실제 반영(--apply)" if APPLY else "조회만(dry-run)"))
print("=" * 96)

BK = os.path.join(r"c:\Users\박근민\Desktop\NEW_ERP_1\_schema", "bk_partworker_{}".format(STAMP))
tot = kept = 0
for f in files:
    p = os.path.join(BE, f)
    if not os.path.exists(p): continue
    src = open(p, encoding="utf-8").read()
    if not ANY.search(src): continue
    base = os.path.basename(f)
    out, n, keep = [], 0, []
    for i, ln in enumerate(src.split("\n"), 1):
        if not ANY.search(ln):
            out.append(ln); continue
        if ln.lstrip().startswith("#") or not SQLPRE.search(ln):
            out.append(ln); keep.append((i, ln.strip()[:66])); continue
        if base in SKIP:
            out.append(ln); keep.append((i, "[쓰기경로 — 수동완료] " + ln.strip()[:46])); continue
        new = PAT3.sub("PARTNER_ERP_TEST3.nx.v_part_worker", ln)
        new = PATV.sub(lambda m: m.group(1) + "v_part_worker", new)
        new = PATN.sub("nx.v_part_worker", new)
        new = PATB.sub("nx.v_part_worker", new)
        if new != ln: n += 1
        out.append(new)
    if n or keep:
        print("\n■ {:<26s} 치환 {:<3d} 보존 {}".format(f, n, len(keep)))
        for i, s in keep: print("     보존 L{:<5d} {}".format(i, s))
    tot += n; kept += len(keep)
    if n and APPLY:
        os.makedirs(BK, exist_ok=True)
        shutil.copy2(p, os.path.join(BK, base))
        open(p, "w", encoding="utf-8", newline="").write("\n".join(out))

print("\n" + "=" * 96)
print(" 치환 {}곳 · 보존 {}곳".format(tot, kept))
if APPLY:
    print(" 백업 = {}".format(BK))
    bad = 0
    for f in files:
        p = os.path.join(BE, f)
        if not os.path.exists(p): continue
        for i, ln in enumerate(open(p, encoding="utf-8").read().split("\n"), 1):
            if re.search(r"\}\.nx\.v_part_worker|nx\.nx\.", ln):
                print("   ★이중접두어 {} L{}".format(os.path.basename(f), i)); bad += 1
    print(" 이중접두어 점검: {}".format("✔ 없음" if bad == 0 else "★{}곳".format(bad)))
else:
    print(" ※dry-run — 반영하려면 --apply")
