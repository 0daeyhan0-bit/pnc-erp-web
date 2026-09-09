# -*- coding: utf-8 -*-
"""시스템코드 코드 전환 — CM_M_MASTER_DETAIL → nx.v_code_detail (2026-09-09)

seed_syscode_260909.py 로 클린을 만든 뒤 실행한다(순서 중요 — §1-9-1).

★가져온 건 41종 334건뿐이다(대표 확정 "필요한것만"). 웹이 읽는 5종은 전부 포함돼 있다
   — PR003 라인 · PR006 소분류 · PR008 품목구분 · PR011 거래처분류 · CM701 은행코드.
   동적 KIND_CODE(파라미터)로 조회하는 3곳(common:480 · bom:181 · price:171)은
   전환 후 **가져오지 않은 코드군을 물으면 빈 결과**가 된다 → 검증에서 확인한다.

★판정 = 키워드가 테이블명 **바로 앞**에 있어야 한다(§6-3 함정).
   "같은 줄에 SQL 키워드" 로 보면 docstring 까지 바꾼다.

사용: python _migration\\switch_syscode_260909.py [--apply]
"""
import sys, os, io, re, shutil, datetime

BE = r"c:\Users\박근민\Desktop\NEW_ERP_1\PNC_ERP_Web\backend"
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
APPLY = "--apply" in sys.argv
STAMP = datetime.datetime.now().strftime("%y%m%d_%H%M")
T = "CM_M_MASTER_DETAIL"

PAT3 = re.compile(r"\bPARTNER_ERP_TEST3\.nx\.{}\b".format(T), re.I)
PATV = re.compile(r"(\{(?:S|SCH|NXS|P)\}\.?)" + T + r"\b", re.I)
PATN = re.compile(r"\bnx\.{}\b".format(T), re.I)
PATB = re.compile(r"\b{}\b".format(T), re.I)
ANY = re.compile(r"\b{}\b".format(T), re.I)
SQLPRE = re.compile(r"\b(FROM|JOIN|INTO|UPDATE|DELETE\s+FROM|TABLE)\s+[\w\.\{\}\[\]]*" + T + r"\b", re.I)

RD = os.path.join(BE, "routers")
files = ["common.py", "live_api.py", "app.py"] + \
        [os.path.join("routers", x) for x in sorted(os.listdir(RD)) if x.endswith(".py")]

print("=" * 96)
print(" 시스템코드 전환 — {} → nx.v_code_detail".format(T))
print(" 모드: {}".format("★실제 반영(--apply)" if APPLY else "조회만(dry-run)"))
print("=" * 96)

BK = os.path.join(r"c:\Users\박근민\Desktop\NEW_ERP_1\_schema", "bk_syscode_{}".format(STAMP))
tot = kept = 0
for f in files:
    p = os.path.join(BE, f)
    if not os.path.exists(p): continue
    src = open(p, encoding="utf-8").read()
    if not ANY.search(src): continue
    out, n, keep = [], 0, []
    for i, ln in enumerate(src.split("\n"), 1):
        if not ANY.search(ln):
            out.append(ln); continue
        if ln.lstrip().startswith("#") or not SQLPRE.search(ln):
            out.append(ln); keep.append((i, ln.strip()[:68])); continue
        new = PAT3.sub("PARTNER_ERP_TEST3.nx.v_code_detail", ln)
        new = PATV.sub(lambda m: m.group(1) + "v_code_detail", new)
        new = PATN.sub("nx.v_code_detail", new)
        new = PATB.sub("nx.v_code_detail", new)
        if new != ln: n += 1
        out.append(new)
    if n or keep:
        print("\n■ {:<26s} 치환 {:<3d} 보존 {}".format(f, n, len(keep)))
        for i, s in keep: print("     보존 L{:<5d} {}".format(i, s))
    tot += n; kept += len(keep)
    if n and APPLY:
        os.makedirs(BK, exist_ok=True)
        shutil.copy2(p, os.path.join(BK, os.path.basename(f)))
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
            if re.search(r"\}\.nx\.v_code_detail|nx\.nx\.", ln):
                print("   ★이중접두어 {} L{}".format(os.path.basename(f), i)); bad += 1
    print(" 이중접두어 점검: {}".format("✔ 없음" if bad == 0 else "★{}곳".format(bad)))
else:
    print(" ※dry-run — 반영하려면 --apply")
