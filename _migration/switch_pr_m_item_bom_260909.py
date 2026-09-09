# -*- coding: utf-8 -*-
"""BOM 미러 → 정본 전환 : nx.PR_M_ITEM_BOM → nx.v_pr_bom (2026-09-09)

■ 근거 — §1-9-2 (대표 확정 2026-09-03)
    정본 = nx.bom_header + nx.bom_line (라이브 PR_M_ITEM_BOM 유래)
    nx.bom = LG 다운로드 계보로 별개, 은퇴 대상
  호환뷰 nx.v_pr_bom 이 이미 있고 미러 컬럼명을 그대로 노출한다(24컬럼).

■ 대상 — 코드 14곳 (쓰기 0곳)
    move580web 4 · setin 3 · prodsheet 2 · dragprod 3 · sales 1 · setinstat 1
  화면 = 파트별 생산계획 · 자재세트입고현황 · 제품재고조회 · 생산전표 · 가공창고 이동계획

■ ★소요·원가 엔진은 이미 정본을 쓴다 (실측)
    nx_soyo_engine.py   미러직독 0곳 · v_pr_bom 26곳 · bom_line 23곳
    nx_cost_engine.py   미러직독 0곳 · bom_line 12곳
  ⟹ 계획·원가는 이미 클린으로 돌고 있었고 **화면 14곳만 미러를 보고 있었다.**
     전환하면 화면이 엔진과 같은 소스를 보게 된다(정합성 개선).

■ ★차이 분석 — 처음 판정을 두 번 뒤집었다. 경위를 남긴다
  (1) 1차: "키(부모+자재+BOM_SEQ) 기준 미러에만 16,926 · 뷰에만 17,607" → 전환 불가로 판단
      → 오판. BOM_SEQ 번호 체계가 다를 뿐이었다(미러 2,3,4… / 뷰 1,2,3…). 자재 목록은 동일.
  (2) 2차: (부모,자재) 키로 재니 미러에만 45 · 뷰에만 294.
      라이브 대비 누락/과잉 = 미러 3/3 · 뷰 48/297 → "미러가 라이브에 가깝다, 전환 위험" 판단.
  (3) ★최종: 그 '과잉 297' 이 **라이브 세트입고요청(PU_T_SET_INPUT_REQ_DTL)에 2,351건 실제 등장**한다.
      즉 그 BOM 조합은 실재하고, 라이브 **마스터 테이블만** 낡은 것이다.
      게다가 과잉행은 대부분 except_flag=1(전개 제외)이라 계산에 쓰이지 않는다(가상품목 25/293).
      ⟹ 클린이 틀린 게 아니라 더 많이 갖고 있는 것. 전환 진행.

  ※남은 차이는 별도 동기화로 정리한다(대표 지시: "동기화는 나중에 하면 되니까").
    나중 기준값 = 라이브 대비 뷰 누락 48 · 과잉 297 (2026-09-09 실측)

■ 방식
  테이블명만 치환. 뷰가 미러 컬럼명을 그대로 내주므로 SQL 본문 무수정.
  ★코드가 쓰는 10컬럼이 전부 뷰에 있다 —
    ITEM_CODE · MAT_CODE · USE_QTY · EXCEPT_FLAG · SAGUB_FLAG · SET_EXCEPT_FLAG
    · VIR_ITEM_FLAG · GAGONG_PROC_CODE · WH_GAGONG_PROC_CODE · IN_GAGONG_PROC_CODE
  ★PR_M_ITEM_BOM 만 잡고 PR_M_ITEM · PR_M_ITEM_SUB 등은 건드리지 않는다.
"""
import sys, os, io, re, argparse, shutil, datetime

BE = r"c:\Users\박근민\Desktop\NEW_ERP_1\PNC_ERP_Web\backend"
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)

ap = argparse.ArgumentParser()
ap.add_argument("--apply", action="store_true")
A = ap.parse_args()

RX = re.compile(r"(\b(?:FROM|JOIN|INTO|UPDATE|DELETE\s+FROM)\s+)([\w\.\{\}\[\]]*?)(?<![_\w])PR_M_ITEM_BOM\b(?![_\w])",
                re.I)

RD = os.path.join(BE, "routers")
FILES = ["common.py", "live_api.py", "app.py"] + \
        [os.path.join("routers", x) for x in sorted(os.listdir(RD)) if x.endswith(".py")]

stamp = datetime.datetime.now().strftime("%y%m%d_%H%M")
bkdir = os.path.join(r"c:\Users\박근민\Desktop\NEW_ERP_1\_migration\bk", "bom_" + stamp)

print("=" * 96)
print(" nx.PR_M_ITEM_BOM → nx.v_pr_bom  ({})".format("반영" if A.apply else "DRY-RUN"))
print("=" * 96)

plan = []
tot = 0
for f in FILES:
    p = os.path.join(BE, f)
    if not os.path.exists(p):
        continue
    txt = open(p, encoding="utf-8").read()
    hits = [m for m in RX.finditer(txt)
            if not txt[:m.start()].split("\n")[-1].lstrip().startswith("#")]
    if not hits:
        continue
    new = RX.sub(lambda m: m.group(1) + m.group(2) + "v_pr_bom", txt)
    plan.append((p, f, txt, new, len(hits)))
    tot += len(hits)
    print("   {:<24s} {:>4}곳".format(os.path.basename(f), len(hits)))
    for m in hits[:4]:
        ln = txt[:m.start()].count("\n") + 1
        print("        L{:<6d} {}".format(ln, m.group(0).strip()[:62]))

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
