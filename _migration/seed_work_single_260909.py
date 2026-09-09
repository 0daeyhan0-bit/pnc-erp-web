# -*- coding: utf-8 -*-
"""단품공정 클린 이관 — nx.prodinfo_single 씨딩 + 호환뷰 (2026-09-09)

★무엇을 — 미러 nx.PR_M_WORK_SINGLE(450행)을 클린 nx.prodinfo_single 로 옮기고,
   미러 모양 호환뷰 nx.v_work_single 을 만든다.

★왜 — STEP6 편성의 `s_work_code → gagong_proc` 매핑 원천이다.
   미러는 컷오버에 얼어붙는다(§1-9-1). 지금 옮겨야 한다.

★왜 안전한가 (실측)
   · 컬럼 — 클린 21 / 미러 29. 차이는 INSERT_*·UPDATE_* 감사컬럼 10개뿐이고
     **업무 컬럼은 전부 있다**(클린은 upd_user/upd_at 로 대체).
   · 코드가 쓰는 컬럼 9개(S_WORK_CODE·WORK_DESC·WORK_CODE·GAGONG_PROC_CODE·
     SORT_SEQ·HOUR_PAY·CUTTING_PROC_FLAG·SUB_WELD_FLAG·GAGONG_GROUP_CODE)가
     전부 클린에 있다 → 작업처 때 겪은 PROD_RATE 누락 같은 사고가 없다.
   · 안 쓰는 것 = ST_635~ST_1905(외경별 표준ST 9개)·GC_GUBUN·감사컬럼.
     ST_* 는 그래도 옮긴다(단품공정 표준ST 화면이 나중에 쓸 수 있다).

★기존 설계 존중 — prodinfo.py:174 는 이미 「미러 뼈대 + 클린 편집분 덮어쓰기」 구조다.
   클린이 0행이었던 건 아무도 수정 안 했기 때문이지 설계 결함이 아니다.
   씨딩하면 클린이 뼈대가 되고, 화면의 nx 뱃지 로직은 그대로 살아있다.

★안전 — 미러 읽기만. 클린 UPSERT(멱등). --apply 없으면 조회만.
사용: python _migration\\seed_work_single_260909.py [--apply]
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

# 미러 → 클린 컬럼 매핑 (업무 컬럼 19개)
COLS = [("S_WORK_CODE", "s_work_code"), ("WORK_DESC", "work_desc"), ("SORT_SEQ", "sort_seq"),
        ("GC_GUBUN", "gc_gubun"), ("WORK_CODE", "work_code"), ("GAGONG_PROC_CODE", "gagong_proc_code"),
        ("CUTTING_PROC_FLAG", "cutting_proc_flag"), ("HOUR_PAY", "hour_pay"),
        ("ST_635", "st_635"), ("ST_794", "st_794"), ("ST_952", "st_952"), ("ST_127", "st_127"),
        ("ST_1588", "st_1588"), ("ST_1905", "st_1905"), ("ST_22", "st_22"), ("ST_254", "st_254"),
        ("ST_28", "st_28"), ("SUB_WELD_FLAG", "sub_weld_flag"), ("GAGONG_GROUP_CODE", "gagong_group_code")]

print("=" * 96)
print(" 단품공정 클린 이관 — nx.PR_M_WORK_SINGLE → nx.prodinfo_single")
print(" 모드: {}".format("★실제 반영(--apply)" if APPLY else "조회만(dry-run)"))
print("=" * 96)

cur.execute("SELECT COUNT(*) FROM {S}.PR_M_WORK_SINGLE".format(S=S)); n_m = cur.fetchone()[0]
cur.execute("SELECT COUNT(*) FROM {S}.prodinfo_single".format(S=S)); n_c = cur.fetchone()[0]
print("\n① 현황 — 미러 {}행 · 클린 {}행".format(n_m, n_c))

msel = ", ".join("m.{}".format(a) for a, _ in COLS)
cur.execute("""SELECT {sel} FROM {S}.PR_M_WORK_SINGLE m
                WHERE NOT EXISTS(SELECT 1 FROM {S}.prodinfo_single c WHERE c.s_work_code=m.S_WORK_CODE)
                ORDER BY m.WORK_CODE, m.SORT_SEQ, m.S_WORK_CODE""".format(sel=msel, S=S))
new = [tuple(x) for x in cur.fetchall()]
cur.execute("""SELECT {sel} FROM {S}.PR_M_WORK_SINGLE m
                 JOIN {S}.prodinfo_single c ON c.s_work_code=m.S_WORK_CODE
                WHERE ISNULL(RTRIM(CAST(m.WORK_DESC AS varchar(60))),'')<>ISNULL(RTRIM(CAST(c.work_desc AS varchar(60))),'')
                   OR ISNULL(RTRIM(CAST(m.GAGONG_PROC_CODE AS varchar(20))),'')<>ISNULL(RTRIM(CAST(c.gagong_proc_code AS varchar(20))),'')
                   OR ISNULL(RTRIM(CAST(m.WORK_CODE AS varchar(20))),'')<>ISNULL(RTRIM(CAST(c.work_code AS varchar(20))),'')
             """.format(sel=msel, S=S))
upd = [tuple(x) for x in cur.fetchall()]
print("   신규 {}행 · 값갱신 {}행".format(len(new), len(upd)))
if new:
    print("\n   — 신규 샘플 —")
    for r in new[:8]:
        print("      {:<6s} {:<16s} 작업처={:<4s} 파트={:<8s} 정렬={}".format(
            str(r[0]), str(r[1] or "")[:16], str(r[4] or "").strip(), str(r[5] or "").strip(), r[2]))

if not APPLY:
    print("\n   ※dry-run — 반영하려면 --apply")
    nx.rollback(); nx.close(); sys.exit(0)

# ── 백업 ───────────────────────────────────────────────────────
BK = "bk_prodinfo_single_{}".format(STAMP)
cur.execute("SELECT * INTO {S}.{BK} FROM {S}.prodinfo_single".format(S=S, BK=BK))
print("\n② 백업 {}.{} ({}행)".format(S, BK, n_c))

# ── UPSERT ─────────────────────────────────────────────────────
ccols = ", ".join(c for _, c in COLS)
ph = ", ".join("?" * len(COLS))
n_i = n_u = 0
for r in new:
    cur.execute("""INSERT INTO {S}.prodinfo_single({cc}, upd_user, upd_at)
                   VALUES({ph}, 'SEED260909', GETDATE())""".format(S=S, cc=ccols, ph=ph), *r)
    n_i += 1
setc = ", ".join("{}=?".format(c) for _, c in COLS[1:])          # s_work_code 는 키
for r in upd:
    cur.execute("""UPDATE {S}.prodinfo_single SET {sc}, upd_user='SEED260909', upd_at=GETDATE()
                    WHERE s_work_code=?""".format(S=S, sc=setc), *(list(r[1:]) + [r[0]]))
    n_u += 1
print("③ 반영 — 신규 {} · 갱신 {}".format(n_i, n_u))

# ── 호환 뷰 ────────────────────────────────────────────────────
cur.execute("IF OBJECT_ID('nx.v_work_single','V') IS NOT NULL DROP VIEW nx.v_work_single")
sel = ",\n       ".join("{} AS {}".format(c, a) for a, c in COLS)
cur.execute("""CREATE VIEW nx.v_work_single AS
SELECT {sel},
       upd_user AS UPDATE_USER_ID,
       upd_at   AS UPDATE_DATETIME
  FROM nx.prodinfo_single""".format(sel=sel))
print("④ 호환뷰 nx.v_work_single 생성")

# ── 검증 ───────────────────────────────────────────────────────
cur.execute("""SELECT COUNT(*) FROM {S}.PR_M_WORK_SINGLE m
                WHERE NOT EXISTS(SELECT 1 FROM {S}.v_work_single v WHERE v.S_WORK_CODE=m.S_WORK_CODE)""".format(S=S))
miss = cur.fetchone()[0]
cur.execute("""SELECT COUNT(*) FROM {S}.PR_M_WORK_SINGLE m JOIN {S}.v_work_single v ON v.S_WORK_CODE=m.S_WORK_CODE
                WHERE ISNULL(RTRIM(CAST(m.WORK_DESC AS varchar(60))),'')<>ISNULL(RTRIM(CAST(v.WORK_DESC AS varchar(60))),'')
                   OR ISNULL(RTRIM(CAST(m.GAGONG_PROC_CODE AS varchar(20))),'')<>ISNULL(RTRIM(CAST(v.GAGONG_PROC_CODE AS varchar(20))),'')
                   OR ISNULL(RTRIM(CAST(m.WORK_CODE AS varchar(20))),'')<>ISNULL(RTRIM(CAST(v.WORK_CODE AS varchar(20))),'')
                   OR ISNULL(m.SORT_SEQ,0)<>ISNULL(v.SORT_SEQ,0)
                   OR ABS(ISNULL(m.HOUR_PAY,0)-ISNULL(v.HOUR_PAY,0))>0.0001""".format(S=S))
diff = cur.fetchone()[0]
cur.execute("SELECT COUNT(*) FROM {S}.v_work_single".format(S=S)); n_v = cur.fetchone()[0]
print("\n⑤ 검증 — 미러 {}행 · 뷰 {}행 · 결손 {} · 값불일치 {}".format(n_m, n_v, miss, diff))

if miss == 0 and diff == 0:
    nx.commit(); print("   ✅ 커밋 완료")
    print("""
   다음 — 코드 6곳 전환
     gagong.py   L721 · L785 · L795
     prodinfo.py L113 · L173 · L298
     nx.PR_M_WORK_SINGLE → nx.v_work_single""")
else:
    nx.rollback(); print("   ★검증 실패 — 롤백"); nx.close(); sys.exit(1)
nx.close()
