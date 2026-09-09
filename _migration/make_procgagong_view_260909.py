# -*- coding: utf-8 -*-
"""품목별 공정순서 호환뷰 — nx.v_item_proc (2026-09-09)

★무엇을 — 미러 nx.PR_M_ITEM_PROC_GAGONG(9,899행)을 클린 nx.prodinfo_proc(9,903행) 로
   바꾸기 위한 호환뷰를 만든다. SP·코드는 테이블명만 치환하면 된다.

★왜 쉬운가 — 컬럼 24개 중 19개가 **이름 그대로 일치**하고, 차이는 감사컬럼 5개
   (UPDATE_USER_ID/DATETIME/IP/COMPUTER/WINDOW)뿐이다. 클린은 upd_user/upd_at 로 대체.

★배경 — 2026-09-08 에 미러 9,901행을 클린으로 씨딩했고(웹 편집 3건 보존),
   prodinfo.py 는 이미 클린을 읽는다. 남은 건 **SP 17곳 + 코드 22곳**의 직독.

★안전 — 뷰 생성만(테이블 무변경). --apply 없으면 점검만.
사용: python _migration\\make_procgagong_view_260909.py [--apply]
"""
import sys, os, io

BE = r"c:\Users\박근민\Desktop\NEW_ERP_1\PNC_ERP_Web\backend"
sys.path.insert(0, BE); os.chdir(BE)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
from common import _nx

S = "PARTNER_ERP_TEST3.nx"
APPLY = "--apply" in sys.argv
nx = _nx(); nx.autocommit = False
cur = nx.cursor()


def cols(t):
    cur.execute("""SELECT COLUMN_NAME, DATA_TYPE FROM PARTNER_ERP_TEST3.INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_SCHEMA='nx' AND TABLE_NAME=? ORDER BY ORDINAL_POSITION""", t)
    return [(str(r[0]), str(r[1])) for r in cur.fetchall()]


print("=" * 96)
print(" 품목별 공정순서 호환뷰 — nx.v_item_proc")
print(" 모드: {}".format("★생성(--apply)" if APPLY else "점검만(dry-run)"))
print("=" * 96)

mc = cols("PR_M_ITEM_PROC_GAGONG")
cc = cols("prodinfo_proc")
mu = {a.upper(): a for a, _ in mc}
cu = {a.upper(): a for a, _ in cc}
print("\n① 컬럼 — 미러 {}개 · 클린 {}개".format(len(mc), len(cc)))
same = sorted(set(mu) & set(cu))
onlym = sorted(set(mu) - set(cu))
onlyc = sorted(set(cu) - set(mu))
print("   이름 일치 {}개".format(len(same)))
print("   미러에만 {}개: {}".format(len(onlym), ", ".join(onlym)))
print("   클린에만 {}개: {}".format(len(onlyc), ", ".join(onlyc)))

# ── 행수·값 대조 ───────────────────────────────────────────────
cur.execute("SELECT COUNT(*) FROM {S}.PR_M_ITEM_PROC_GAGONG".format(S=S)); n_m = cur.fetchone()[0]
cur.execute("SELECT COUNT(*) FROM {S}.prodinfo_proc".format(S=S)); n_c = cur.fetchone()[0]
print("\n② 행수 — 미러 {:,} · 클린 {:,}".format(n_m, n_c))
KEY = "item_code, proc_seq"
cur.execute("""SELECT COUNT(*) FROM {S}.PR_M_ITEM_PROC_GAGONG m
                WHERE NOT EXISTS(SELECT 1 FROM {S}.prodinfo_proc c
                                  WHERE LTRIM(RTRIM(c.item_code))=LTRIM(RTRIM(m.ITEM_CODE))
                                    AND c.proc_seq=m.PROC_SEQ)""".format(S=S))
miss = cur.fetchone()[0]
cur.execute("""SELECT COUNT(*) FROM {S}.prodinfo_proc c
                WHERE NOT EXISTS(SELECT 1 FROM {S}.PR_M_ITEM_PROC_GAGONG m
                                  WHERE LTRIM(RTRIM(c.item_code))=LTRIM(RTRIM(m.ITEM_CODE))
                                    AND c.proc_seq=m.PROC_SEQ)""".format(S=S))
extra = cur.fetchone()[0]
print("   미러에만 {}행 (클린 결손) · 클린에만 {}행 (웹 추가)".format(miss, extra))

# 값 비교 — 편성이 쓰는 핵심 컬럼
cur.execute("""SELECT COUNT(*) FROM {S}.PR_M_ITEM_PROC_GAGONG m
                 JOIN {S}.prodinfo_proc c ON LTRIM(RTRIM(c.item_code))=LTRIM(RTRIM(m.ITEM_CODE))
                                          AND c.proc_seq=m.PROC_SEQ
                WHERE ISNULL(RTRIM(CAST(m.GAGONG_PROC_CODE AS varchar(20))),'')
                      <> ISNULL(RTRIM(CAST(c.gagong_proc_code AS varchar(20))),'')
                   OR ISNULL(m.S_WORK_CODE,0) <> ISNULL(c.s_work_code,0)
                   OR ISNULL(RTRIM(CAST(m.WORK_CODE AS varchar(20))),'')
                      <> ISNULL(RTRIM(CAST(c.work_code AS varchar(20))),'')""".format(S=S))
diff = cur.fetchone()[0]
print("   ★핵심 컬럼(가공공정·단품공정·작업처) 불일치 {}행".format(diff))

if miss or diff:
    print("\n   ★중단 — 결손 {}행 · 불일치 {}행. 씨딩부터 다시 해야 한다.".format(miss, diff))
    if not APPLY:
        print("   (dry-run 이므로 뷰는 만들지 않았다)")
    nx.rollback(); nx.close(); sys.exit(1)
print("   ✔ 클린이 미러를 온전히 담고 있다")

if not APPLY:
    print("\n   ※dry-run — 뷰를 만들려면 --apply")
    nx.rollback(); nx.close(); sys.exit(0)

# ── 뷰 생성 ────────────────────────────────────────────────────
# 미러 컬럼 순서·이름 그대로 노출한다. 클린에 없는 감사컬럼은 upd_* 로 채우거나 NULL.
AUD = {"UPDATE_USER_ID": "upd_user", "UPDATE_DATETIME": "upd_at"}
sel = []
for a, _t in mc:
    up = a.upper()
    if up in cu:
        sel.append("{} AS {}".format(cu[up], a))
    elif up in AUD:
        sel.append("{} AS {}".format(AUD[up], a))
    else:
        sel.append("CAST(NULL AS varchar(50)) AS {}".format(a))
cur.execute("IF OBJECT_ID('nx.v_item_proc','V') IS NOT NULL DROP VIEW nx.v_item_proc")
cur.execute("CREATE VIEW nx.v_item_proc AS\nSELECT " + ",\n       ".join(sel) + "\n  FROM nx.prodinfo_proc")
print("\n③ 뷰 nx.v_item_proc 생성 ({}컬럼)".format(len(sel)))

# ── 검증 ───────────────────────────────────────────────────────
cur.execute("SELECT COUNT(*) FROM {S}.v_item_proc".format(S=S)); n_v = cur.fetchone()[0]
cur.execute("""SELECT COUNT(*) FROM {S}.PR_M_ITEM_PROC_GAGONG m
                 JOIN {S}.v_item_proc v ON LTRIM(RTRIM(v.ITEM_CODE))=LTRIM(RTRIM(m.ITEM_CODE))
                                        AND v.PROC_SEQ=m.PROC_SEQ
                WHERE ISNULL(RTRIM(CAST(m.GAGONG_PROC_CODE AS varchar(20))),'')
                      <> ISNULL(RTRIM(CAST(v.GAGONG_PROC_CODE AS varchar(20))),'')
                   OR ISNULL(m.S_WORK_CODE,0) <> ISNULL(v.S_WORK_CODE,0)
                   OR ABS(ISNULL(m.LT_HR,0)-ISNULL(v.LT_HR,0)) > 0.0001
                   OR ABS(ISNULL(m.TOT_ST,0)-ISNULL(v.TOT_ST,0)) > 0.0001""".format(S=S))
vd = cur.fetchone()[0]
print("\n④ 검증 — 미러 {:,} · 뷰 {:,} · 값불일치 {}".format(n_m, n_v, vd))

if vd == 0:
    nx.commit(); print("   ✅ 커밋 완료")
    print("""
   다음 — 치환 대상
     SP  17곳  (가공창고이동 5·5 · 편성 4 · 420 2 · 4주간 1)
     코드 22곳
     nx.PR_M_ITEM_PROC_GAGONG → nx.v_item_proc""")
else:
    nx.rollback(); print("   ★검증 실패 — 롤백"); nx.close(); sys.exit(1)
nx.close()
