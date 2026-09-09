# -*- coding: utf-8 -*-
"""품목 미러 → 클린 전환 : nx.PR_M_ITEM → nx.v_pr_m_item (2026-09-09)

■ 실측 근거
  코드 15곳 (move580web 12 · prodsheet/sales/setinstat 각 1) · **쓰기 0곳**
  웹이 부르는 SP 24개 중 PR_M_ITEM 을 읽는 것 **0개**
     → §8 에 적어둔 "코드 27 + SP 94" 는 과대평가였다(당시 집계 기준이 느슨했다).

  클린 nx.item 25,403행 · 미러 24,154행 · **미러에만 있는 품목 0건**(결손 없음)
  코드가 실제로 쓰는 컬럼 6종 —
     ITEM_CODE · IN_CUST_CODE · WORK_CODE · ITEM_CLASS · SAGUB_STOCK_FLAG · GC_GUBUN

  뷰 vs 라이브 전수 대조(뷰 생성 후):
     ITEM_CODE / IN_CUST_CODE / WORK_CODE / SAGUB_STOCK_FLAG / GC_GUBUN  24,154/24,154
     ITEM_CLASS                                                          24,154/24,154
     ★오히려 미러가 1건 낡았다(MJU63010102: 미러 빈값 · 라이브 'K').

  선행 조치
     fix_item_class_260909.py --commit   클린 결손 12건 보정(백업 nx.bk_item_class_260909)
     make_item_view_260909.py --apply    호환뷰 nx.v_pr_m_item 생성

■ 방식
  테이블명만 치환. 뷰가 미러 컬럼명을 그대로 노출하므로 SQL 본문은 손대지 않는다.
  ★키워드(FROM/JOIN/INTO/UPDATE/DELETE FROM)가 테이블명 **바로 앞**에 있어야 실제 쿼리로 본다
    — 주석·독스트링의 단순 언급을 건드리지 않기 위함(gongsu.py 오탐 이력).
  ★PR_M_ITEM_BOM·PR_M_ITEM_SUB 등 접미사가 붙은 다른 테이블을 건드리면 안 되므로
    뒤에 [_\w] 가 오면 제외한다.
"""
import sys, os, io, re, argparse, shutil, datetime

BE = r"c:\Users\박근민\Desktop\NEW_ERP_1\PNC_ERP_Web\backend"
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)

ap = argparse.ArgumentParser()
ap.add_argument("--apply", action="store_true")
A = ap.parse_args()

# 접두어 보존 + 뒤에 _ 나 글자가 오면 제외(PR_M_ITEM_BOM 등 보호)
RX = re.compile(r"(\b(?:FROM|JOIN|INTO|UPDATE|DELETE\s+FROM)\s+)([\w\.\{\}\[\]]*?)(?<![_\w])PR_M_ITEM\b(?![_\w])",
                re.I)

RD = os.path.join(BE, "routers")
FILES = ["common.py", "live_api.py", "app.py"] + \
        [os.path.join("routers", x) for x in sorted(os.listdir(RD)) if x.endswith(".py")]

stamp = datetime.datetime.now().strftime("%y%m%d_%H%M")
bkdir = os.path.join(r"c:\Users\박근민\Desktop\NEW_ERP_1\_migration\bk", "item_" + stamp)

print("=" * 96)
print(" nx.PR_M_ITEM → nx.v_pr_m_item  ({})".format("반영" if A.apply else "DRY-RUN"))
print("=" * 96)

plan = []
tot = 0
for f in FILES:
    p = os.path.join(BE, f)
    if not os.path.exists(p):
        continue
    txt = open(p, encoding="utf-8").read()
    hits = [m for m in RX.finditer(txt) if not txt[:m.start()].split("\n")[-1].lstrip().startswith("#")]
    if not hits:
        continue
    new = RX.sub(lambda m: m.group(1) + m.group(2) + "v_pr_m_item", txt)
    plan.append((p, f, txt, new, len(hits)))
    tot += len(hits)
    print("   {:<24s} {:>4}곳".format(os.path.basename(f), len(hits)))
    for m in hits[:3]:
        ln = txt[:m.start()].count("\n") + 1
        print("        L{:<6d} {}".format(ln, m.group(0).strip()[:64]))

print("   ─ 총 {}곳 · {}파일".format(tot, len(plan)))

if not A.apply:
    print("\n   --apply 를 붙이면 반영한다.")
    sys.exit(0)

os.makedirs(bkdir, exist_ok=True)
for p, f, txt, new, n in plan:
    shutil.copy2(p, os.path.join(bkdir, os.path.basename(p)))
    with open(p, "w", encoding="utf-8", newline="") as fh:
        fh.write(new)
print("\n   백업 {}".format(bkdir))
print("   반영 {}파일 · {}곳".format(len(plan), tot))

left = 0
for f in FILES:
    p = os.path.join(BE, f)
    if not os.path.exists(p):
        continue
    for i, ln in enumerate(open(p, encoding="utf-8").read().split("\n"), 1):
        if ln.lstrip().startswith("#"):
            continue
        if RX.search(ln):
            print("   ★잔존 {:<18s} L{:<5d} {}".format(os.path.basename(f), i, ln.strip()[:56]))
            left += 1
print("   잔존 {}곳 {}".format(left, "✔" if left == 0 else ""))
