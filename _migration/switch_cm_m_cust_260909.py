# -*- coding: utf-8 -*-
"""거래처 미러 → 클린 전환 : nx.CM_M_CUST → nx.v_cm_m_cust (2026-09-09)

■ 배경 — 기존 기록이 틀렸다
  WORKLOG §8 에 "클린 partner 가 357행·컬럼겹침 0/63 — 사실상 재구축, 대표 결정 필요"
  라고 적어 두었으나 **거래처 클린 정본은 nx.partner 가 아니라 nx.cust** 다.
  (기준 마스터 관리 화면 부제: "원장 nx.cust(레거시 이관)")
  nx.partner 는 4컬럼짜리 별개 테이블이었고, 그것을 보고 오판했다.

  또 "브랜치 feat/single-source-price-260908 에 147건 전환분 미병합" 도 틀렸다 —
  실측하니 그 브랜치의 CM_M_CUST 참조도 148곳으로 내 브랜치와 같다(전환분 없음).

■ 실측 근거 (2026-09-09)
  nx.cust            361행 · 미러와 결손 0 · 초과 0
  nx.v_cm_m_cust     이미 존재 · 미러 63컬럼 전부 커버(누락 0)
  코드 참조 149곳    전부 조회(INSERT/UPDATE/DELETE 0곳) → 뷰 대체 가능
  코드가 쓰는 컬럼 5종 = CUST_CODE · CUST_DESC · CUST_TYPE · CHARGE_NAME · CHARGE_USER_ID
                        → 전부 뷰에 있고, 라이브와 값 일치(361/361)

  ※ 뷰 vs 미러 26컬럼 차이는 전부 **정규화**이지 결손이 아니다
       플래그 ''→'0' · 이름/주소 앞공백 제거 · 감사흔적(이관시각)
     실질 결손이던 CHARGE_USER_ID 2건은 fix_cust_charge_260909.py 로 선행 보정 완료.

■ 방식
  테이블명만 치환한다. 컬럼 별칭이 미러와 동일하므로 SQL 본문은 손대지 않는다.
  ★키워드(FROM/JOIN/INTO/UPDATE/DELETE FROM)가 테이블명 **바로 앞**에 있어야 실제 쿼리로 본다
    — 주석·독스트링의 단순 언급을 건드리지 않기 위함(과거 gongsu.py 오탐 이력).
"""
import sys, os, io, re, argparse, shutil, datetime

BE = r"c:\Users\박근민\Desktop\NEW_ERP_1\PNC_ERP_Web\backend"
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)

ap = argparse.ArgumentParser()
ap.add_argument("--commit", action="store_true")
A = ap.parse_args()

T = "CM_M_CUST"
NEW = "v_cm_m_cust"
# 키워드가 테이블명 바로 앞 + 접두어(nx. / PARTNER_ERP_TEST3.nx. / {S}. …) 보존
RX = re.compile(r"(\b(?:FROM|JOIN|INTO|UPDATE|DELETE\s+FROM)\s+)([\w\.\{\}\[\]]*?)\b" + T + r"\b(?![_\w])",
                re.I)

RD = os.path.join(BE, "routers")
FILES = ["common.py", "live_api.py", "app.py"] + \
        [os.path.join("routers", x) for x in sorted(os.listdir(RD)) if x.endswith(".py")]

stamp = datetime.datetime.now().strftime("%y%m%d_%H%M")
bkdir = os.path.join(r"c:\Users\박근민\Desktop\NEW_ERP_1\_migration\bk", "cust_" + stamp)

print("=" * 96)
print(" nx.CM_M_CUST → nx.v_cm_m_cust  ({})".format("반영" if A.commit else "DRY-RUN"))
print("=" * 96)

tot = 0
plan = []
for f in FILES:
    p = os.path.join(BE, f)
    if not os.path.exists(p):
        continue
    txt = open(p, encoding="utf-8").read()
    hits = list(RX.finditer(txt))
    if not hits:
        continue
    new = RX.sub(lambda m: m.group(1) + m.group(2) + NEW, txt)
    plan.append((p, f, txt, new, len(hits)))
    tot += len(hits)
    print("   {:<24s} {:>4}곳".format(os.path.basename(f), len(hits)))

print("   ─ 총 {}곳 · {}파일".format(tot, len(plan)))

if not A.commit:
    print("\n   [DRY-RUN] 표본 —")
    for p, f, txt, new, n in plan[:3]:
        for m in list(RX.finditer(txt))[:2]:
            ln = txt[:m.start()].count("\n") + 1
            print("     {:<18s} L{:<5d} {}".format(os.path.basename(f), ln, m.group(0)[:60]))
    print("\n   --commit 을 붙이면 반영한다.")
    sys.exit(0)

os.makedirs(bkdir, exist_ok=True)
for p, f, txt, new, n in plan:
    shutil.copy2(p, os.path.join(bkdir, os.path.basename(p)))
    with open(p, "w", encoding="utf-8", newline="") as fh:
        fh.write(new)
print("\n   백업 {}".format(bkdir))
print("   반영 {}파일 · {}곳".format(len(plan), tot))

# ── 잔존 확인
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
