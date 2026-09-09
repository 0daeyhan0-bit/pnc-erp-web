# -*- coding: utf-8 -*-
"""조립공정 클린 이관 — nx.work_assy 신설 + 씨딩 + 호환뷰 (2026-09-09)

★무엇을 — 미러 nx.PR_M_WORK_ASSY(371행)을 클린 nx.work_assy 로 옮긴다.

★왜 — 「생산정보등록 › ① 조립(공정수)」 패널의 **뼈대**다.
   화면의 "전체공정(371)" 이 이 테이블 행수 그대로다. 미러가 컷오버에 얼어붙으면
   371개 안에서만 골라 쓸 수 있고 **새 조립공정을 만들 수 없다**(§1-9-1).

★명칭 정리 (대표 확인 2026-09-09)
     nx.CS_M_ASSEM_PROC (21행)  = 원가 계보  → 탭 「원가포장공정 마스터」로 개칭
     nx.PR_M_WORK_ASSY (371행)  = 생산 계보  → 탭 「조립공정 마스터」 (이게 진짜)
   코드 체계가 다르다(01·02 vs 517·202). 단품공정(CS_M_PROC vs PR_M_WORK_SINGLE)과 같은 구도.

★prodinfo_assy 와 혼동 금지
     nx.prodinfo_assy = item_code + a_work_code + work_qty = **품목별 조립공정 수량**(15행)
     nx.work_assy     = a_work_code 기준 = **조립공정 정의**(371행)
   마스터와 트랜잭션이라 서로 대체본이 아니다.

★코드가 쓰는 컬럼 6개(실측): A_WORK_CODE · WORK_DESC · WORK_ST · SORT_SEQ · WELDING_GUBUN · PROC_GUBUN
   HOUR_PAY · WELDING_USE_QTY 도 함께 옮긴다(화면에 없지만 임률·용접량은 의미가 있다).
   감사컬럼 10개(INSERT_*/UPDATE_*)는 upd_user/upd_at 로 대체.

★안전 — 미러 읽기만. --apply 없으면 조회만.
사용: python _migration\\seed_work_assy_260909.py [--apply]
"""
import sys, os, io, datetime

BE = r"c:\Users\박근민\Desktop\NEW_ERP_1\PNC_ERP_Web\backend"
sys.path.insert(0, BE); os.chdir(BE)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
from common import _nx

S = "PARTNER_ERP_TEST3.nx"
STAMP = datetime.datetime.now().strftime("%y%m%d_%H%M")
APPLY = "--apply" in sys.argv

nx = _nx(); nx.autocommit = False
cur = nx.cursor()

COLS = [("A_WORK_CODE", "a_work_code"), ("WORK_DESC", "work_desc"), ("SORT_SEQ", "sort_seq"),
        ("HOUR_PAY", "hour_pay"), ("WORK_ST", "work_st"), ("WELDING_USE_QTY", "welding_use_qty"),
        ("WELDING_GUBUN", "welding_gubun"), ("PROC_GUBUN", "proc_gubun")]

print("=" * 96)
print(" 조립공정 클린 이관 — nx.PR_M_WORK_ASSY → nx.work_assy")
print(" 모드: {}".format("★실제 반영(--apply)" if APPLY else "조회만(dry-run)"))
print("=" * 96)

cur.execute("SELECT COUNT(*) FROM {S}.PR_M_WORK_ASSY".format(S=S)); n_m = cur.fetchone()[0]
cur.execute("""SELECT COUNT(*) FROM PARTNER_ERP_TEST3.INFORMATION_SCHEMA.TABLES
                WHERE TABLE_SCHEMA='nx' AND TABLE_NAME='work_assy'""")
ex = cur.fetchone()[0]
print("\n① 미러 {}행 · nx.work_assy {}".format(n_m, "이미 있음" if ex else "없음(신설)"))

sel = ", ".join("m.{}".format(a) for a, _ in COLS)
cur.execute("SELECT {} FROM {S}.PR_M_WORK_ASSY m ORDER BY m.SORT_SEQ, m.A_WORK_CODE".format(sel, S=S))
src = [tuple(x) for x in cur.fetchall()]
print("\n   — 샘플 —")
for r in src[:8]:
    print("   {:>4} {:<20s} 정렬={:<4} 임률={:<9,.0f} ST={:<9,.2f} 용접구분={} 공정구분={}".format(
        r[0], str(r[1] or "").strip()[:20], (r[2] if r[2] is not None else 0),
        float(r[3] or 0), float(r[4] or 0),
        (r[6] if r[6] is not None else 0), str(r[7] or "").strip() or "-"))

if not APPLY:
    print("\n   ※dry-run — 반영하려면 --apply")
    nx.rollback(); nx.close(); sys.exit(0)

# ── 테이블 신설 ────────────────────────────────────────────────
cur.execute("""IF OBJECT_ID('nx.work_assy','U') IS NULL
CREATE TABLE nx.work_assy(
    a_work_code      int           NOT NULL PRIMARY KEY,
    work_desc        nvarchar(60)  NULL,
    sort_seq         int           NULL,
    hour_pay         decimal(18,4) NULL,
    work_st          decimal(18,5) NULL,
    welding_use_qty  decimal(18,5) NULL,
    welding_gubun    int           NULL,
    proc_gubun       varchar(4)    NULL,
    use_yn           varchar(1)    NULL DEFAULT '1',
    remarks          nvarchar(200) NULL,
    upd_user         nvarchar(40)  NULL,
    upd_dt           datetime      NULL
)""")
print("\n② 테이블 확보")

# ── 씨딩(멱등) ─────────────────────────────────────────────────
n_i = n_u = 0
ccols = ", ".join(c for _, c in COLS)
ph = ", ".join("?" * len(COLS))
setc = ", ".join("{}=?".format(c) for _, c in COLS[1:])
for r in src:
    cur.execute("SELECT 1 FROM {S}.work_assy WHERE a_work_code=?".format(S=S), r[0])
    if cur.fetchone():
        cur.execute("""UPDATE {S}.work_assy SET {sc}, upd_user='SEED260909', upd_dt=GETDATE()
                        WHERE a_work_code=?""".format(S=S, sc=setc), *(list(r[1:]) + [r[0]]))
        n_u += 1
    else:
        cur.execute("""INSERT INTO {S}.work_assy({cc}, use_yn, upd_user, upd_dt)
                       VALUES({ph}, '1', 'SEED260909', GETDATE())""".format(S=S, cc=ccols, ph=ph), *r)
        n_i += 1
print("③ 씨딩 — 신규 {} · 갱신 {}".format(n_i, n_u))

# ── 호환 뷰 ────────────────────────────────────────────────────
cur.execute("IF OBJECT_ID('nx.v_work_assy','V') IS NOT NULL DROP VIEW nx.v_work_assy")
vsel = ",\n       ".join("{} AS {}".format(c, a) for a, c in COLS)
cur.execute("""CREATE VIEW nx.v_work_assy AS
SELECT {sel},
       use_yn   AS USE_YN,
       upd_user AS UPDATE_USER_ID,
       upd_dt   AS UPDATE_DATETIME
  FROM nx.work_assy""".format(sel=vsel))
print("④ 호환뷰 nx.v_work_assy 생성")

# ── 검증 ───────────────────────────────────────────────────────
cur.execute("""SELECT COUNT(*) FROM {S}.PR_M_WORK_ASSY m
                WHERE NOT EXISTS(SELECT 1 FROM {S}.v_work_assy v WHERE v.A_WORK_CODE=m.A_WORK_CODE)""".format(S=S))
miss = cur.fetchone()[0]
cur.execute("""SELECT COUNT(*) FROM {S}.PR_M_WORK_ASSY m JOIN {S}.v_work_assy v ON v.A_WORK_CODE=m.A_WORK_CODE
                WHERE ISNULL(RTRIM(CAST(m.WORK_DESC AS varchar(60))),'')<>ISNULL(RTRIM(CAST(v.WORK_DESC AS varchar(60))),'')
                   OR ABS(ISNULL(m.WORK_ST,0)-ISNULL(v.WORK_ST,0))>0.00001
                   OR ISNULL(m.SORT_SEQ,0)<>ISNULL(v.SORT_SEQ,0)
                   OR ISNULL(RTRIM(CAST(m.PROC_GUBUN AS varchar(8))),'')<>ISNULL(RTRIM(CAST(v.PROC_GUBUN AS varchar(8))),'')
                   OR ISNULL(m.WELDING_GUBUN,0)<>ISNULL(v.WELDING_GUBUN,0)""".format(S=S))
diff = cur.fetchone()[0]
cur.execute("SELECT COUNT(*) FROM {S}.v_work_assy".format(S=S)); n_v = cur.fetchone()[0]
print("\n⑤ 검증 — 미러 {}행 · 뷰 {}행 · 결손 {} · 값불일치 {}".format(n_m, n_v, miss, diff))

if miss == 0 and diff == 0:
    nx.commit(); print("   ✅ 커밋 완료")
    print("""
   다음 — 코드 2곳 전환
     prodinfo.py L151(조인) · L163(COUNT)
     nx.PR_M_WORK_ASSY → nx.v_work_assy""")
else:
    nx.rollback(); print("   ★검증 실패 — 롤백"); nx.close(); sys.exit(1)
nx.close()
