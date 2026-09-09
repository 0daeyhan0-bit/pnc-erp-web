# -*- coding: utf-8 -*-
"""계획 과거분 이관 + 편성 방식 교정 (2026-09-09)

★문제 — 미러는 누적인데 클린은 현재분만이다.
     미러 nx.SA_T_PLAN_ITEM_DTL  231016 ~ 261009 · 346,670행  (2023-10 부터 누적)
     클린 nx.sale_plan_item      260909 ~ 261009 ·   8,646행  (편성 때 전량 DELETE)
   그래서 영업예상매출·예상 LG사급금액(soyo.py 4곳)이 아직 미러를 읽는다 —
   클린으로 바꾸면 과거가 통째로 사라지기 때문이다.

★대표 확인 — "해당 테이블 자체가 과거까지 계속 누적한거 아니야 당일만 삭제, 삽입되는거고"
              "당일 계획 업로드 데이터 삭제, 등록 이렇게 하거던"
   맞다. 레거시는 **업로드한 일자분만** 지우고 넣어 과거가 쌓인다.
   웹은 `DELETE FROM nx.sale_plan_item`(전량)이라 과거가 안 남는다.

★조치 2가지
   ① 과거분 이관 — 미러에만 있는 338,055행(231016~261009)을 클린으로 복사
      컬럼이 완전히 같다(미러 22 ⊂ 클린 23, compose_dt 만 추가) → 그대로 옮긴다
   ② 편성 방식 교정 — planrev.py:900·938 의 전량 DELETE 를
      **nx.plan_dtl 에 있는 일자 범위만** 지우도록 변경(이 스크립트는 ① 만, ②는 코드 편집)

★안전 — 미러 읽기 + 클린 INSERT 만. 기존 클린 행은 건드리지 않는다.
사용: python _migration\\seed_sale_plan_hist_260909.py [--apply]
"""
import sys, os, io, datetime

BE = r"c:\Users\박근민\Desktop\NEW_ERP_1\PNC_ERP_Web\backend"
sys.path.insert(0, BE); os.chdir(BE)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
from common import _nx

APPLY = "--apply" in sys.argv
S = "PARTNER_ERP_TEST3.nx"

CASES = [
    # (미러, 클린, 키컬럼들)
    # ★도번단위만 이관한다. 실측으로 두 표의 성격이 다름을 확인했다:
    #     SA_T_PLAN_DTL      라이브 260909~261009 4,907행  = **누적 아님**
    #                        (업로드 원본이 당일 이후만 담아 과거가 애초에 안 쌓인다)
    #     SA_T_PLAN_ITEM_DTL 라이브 231016~261009 346,390행 = ★누적
    #   상위 미러에만 있는 200행도 260910~261009(오늘 이후)라 편성이 다시 만든다 → 이관 불요.
    ("SA_T_PLAN_ITEM_DTL", "sale_plan_item",
     ["PLAN_YMD", "WORK_ORDER", "SPLIT_WORK_ORDER", "C_ITEM_CODE"]),
]

nx = _nx(); nx.autocommit = False
cur = nx.cursor()

print("=" * 100)
print(" 계획 과거분 이관 — 미러 누적분 → 클린")
print(" 모드: {}".format("★실제 반영(--apply)" if APPLY else "조회만(dry-run)"))
print("=" * 100)

for mir, cln, keys in CASES:
    # 컬럼 대응 확인
    cur.execute("""SELECT COLUMN_NAME FROM PARTNER_ERP_TEST3.INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_SCHEMA='nx' AND TABLE_NAME=? ORDER BY ORDINAL_POSITION""", mir)
    mc = [str(r[0]) for r in cur.fetchall()]
    cur.execute("""SELECT COLUMN_NAME FROM PARTNER_ERP_TEST3.INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_SCHEMA='nx' AND TABLE_NAME=? ORDER BY ORDINAL_POSITION""", cln)
    cc = {str(r[0]).upper(): str(r[0]) for r in cur.fetchall()}
    use = [c for c in mc if c.upper() in cc]
    miss = [c for c in mc if c.upper() not in cc]

    on = " AND ".join("RTRIM(ISNULL(CAST(c.[{k}] AS varchar(60)),''))="
                      "RTRIM(ISNULL(CAST(m.[{k}] AS varchar(60)),''))".format(k=k) for k in keys)
    cur.execute("""SELECT COUNT(*), MIN(m.PLAN_YMD), MAX(m.PLAN_YMD) FROM {S}.[{m}] m
                    WHERE NOT EXISTS(SELECT 1 FROM {S}.[{c}] c WHERE {on})""".format(
        S=S, m=mir, c=cln, on=on))
    r = cur.fetchone()
    n_only, ymin, ymax = r[0], str(r[1] or "").strip(), str(r[2] or "").strip()
    cur.execute("SELECT COUNT(*) FROM {S}.[{c}]".format(S=S, c=cln)); n_cln = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM {S}.[{m}]".format(S=S, m=mir)); n_mir = cur.fetchone()[0]

    print("\n■ {} → {}".format(mir, cln))
    print("   미러 {:,}행 · 클린 {:,}행 · ★미러에만 {:,}행 ({} ~ {})".format(
        n_mir, n_cln, n_only, ymin, ymax))
    print("   컬럼 {}개 이관 · 클린에 없는 컬럼 {}".format(len(use), ", ".join(miss) or "없음"))
    if not n_only:
        print("   → 이관할 것 없음"); continue
    if not APPLY:
        print("   → 이관 예정 {:,}행".format(n_only)); continue

    cols = ", ".join("[{}]".format(cc[c.upper()]) for c in use)
    sel = ", ".join("m.[{}]".format(c) for c in use)
    cur.execute("""INSERT INTO {S}.[{c}]({cols})
                   SELECT {sel} FROM {S}.[{m}] m
                    WHERE NOT EXISTS(SELECT 1 FROM {S}.[{c}] c WHERE {on})""".format(
        S=S, c=cln, m=mir, cols=cols, sel=sel, on=on))
    ins = cur.rowcount
    cur.execute("SELECT COUNT(*) FROM {S}.[{c}]".format(S=S, c=cln)); n_new = cur.fetchone()[0]
    cur.execute("""SELECT COUNT(*) FROM {S}.[{m}] m
                    WHERE NOT EXISTS(SELECT 1 FROM {S}.[{c}] c WHERE {on})""".format(
        S=S, m=mir, c=cln, on=on))
    left = cur.fetchone()[0]
    print("   ✔ {:,}행 삽입 · 클린 {:,} → {:,} · 잔여 {}".format(ins, n_cln, n_new, left))
    if left:
        nx.rollback(); print("   ★잔여가 남았다 — 롤백"); nx.close(); sys.exit(1)

if not APPLY:
    nx.rollback()
    print("\n" + "=" * 100)
    print(" ※dry-run — 반영하려면 --apply")
    print("""
 ★이관 후 반드시 함께 할 것 — planrev.py 편성 방식 교정
   L900  DELETE FROM nx.sale_plan            ← 전량
   L938  DELETE FROM nx.sale_plan_item       ← 전량
   이대로 두면 다음 편성에 방금 이관한 과거가 **다시 사라진다.**
   → nx.plan_dtl 에 있는 일자 범위만 지우도록 바꿔야 한다(레거시 = 업로드분만 삭제).""")
    nx.close(); sys.exit(0)

# ── 검증 ───────────────────────────────────────────────────────
print("\n" + "=" * 100)
print(" 검증")
print("=" * 100)
ok = True
for mir, cln, keys in CASES:
    cur.execute("SELECT COUNT(*), MIN(PLAN_YMD), MAX(PLAN_YMD) FROM {S}.[{c}]".format(S=S, c=cln))
    r = cur.fetchone()
    cur.execute("SELECT COUNT(*), MIN(PLAN_YMD), MAX(PLAN_YMD) FROM {S}.[{m}]".format(S=S, m=mir))
    r2 = cur.fetchone()
    print("   {:<22s} 클린 {:>9,} ({} ~ {}) · 미러 {:>9,} ({} ~ {})".format(
        cln, r[0], str(r[1]).strip(), str(r[2]).strip(),
        r2[0], str(r2[1]).strip(), str(r2[2]).strip()))
    if r[0] < r2[0]:
        ok = False; print("      ★클린이 미러보다 적다")

if ok:
    nx.commit()
    print("\n ✅ 커밋")
    print("""
 ★다음 — planrev.py 편성 방식 교정이 **반드시** 따라와야 한다.
   지금 상태로 편성을 돌리면 L900·L938 의 전량 DELETE 가 과거를 다시 지운다.""")
else:
    nx.rollback(); print("\n ★검증 실패 — 롤백"); nx.close(); sys.exit(1)
nx.close()
