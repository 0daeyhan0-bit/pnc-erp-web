# -*- coding: utf-8 -*-
"""클린 BOM 수량 동기화 — 라이브 PR_M_ITEM_BOM 기준 (2026-09-09)

★무엇을 — 라이브에서 최근(2026-09-04) 등록·수정된 BOM 수량이 클린에 안 넘어왔다.
   실측: 라이브 유효 35,380쌍 중 수량 불일치 **9쌍**(2도번), 클린 결손 0.
   옛 데이터(적용일 빈칸/260801 이전) 35,214쌍은 100% 일치 — 최근분만 어긋났다.

     AJR30133610 (적용일 260904)  3건 : 1MPC0502018 1→2 · 3H01582A 1→8 · MJX30152802 1→2
     AJR30133611 (적용일 260904)  6건

   AJR30133610 은 계획에 ASSY 로 120행 물려 있고, 3H01582A 소요가 8 인데 1 로 계산되고 있다.

★어떻게 — 근거키(부모품번+자품번) 스코프 UPDATE 만. 태그기반·대량 DELETE 없음(§1-3).
   · 백업 = nx.bk_bomline_qty_<stamp> (바꾸는 행의 before 값)
   · 대상 = 라이브와 수량이 다른 쌍만. 라이브에 없는 쌍은 건드리지 않는다
   · except_flag/파트/적용일은 손대지 않는다 — **수량만**
   · --apply 없으면 조회만(dry-run)

사용:
    python _migration\\sync_bom_qty_260909.py            # dry-run
    python _migration\\sync_bom_qty_260909.py --apply    # 실제 반영
"""
import sys, os, io, datetime

BE = r"c:\Users\박근민\Desktop\NEW_ERP_1\PNC_ERP_Web\backend"
sys.path.insert(0, BE); os.chdir(BE)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
from common import _nx

S = "PARTNER_ERP_TEST3.nx"
L = "PARTNER_ERP.dbo"
D6 = datetime.datetime.now().strftime("%y%m%d")
STAMP = datetime.datetime.now().strftime("%y%m%d_%H%M")
APPLY = "--apply" in sys.argv

V = """ISNULL(NULLIF(LTRIM(RTRIM({f})),''),'{d}')"""
PR = """
SELECT LTRIM(RTRIM(a.ITEM_CODE)) p, LTRIM(RTRIM(a.MAT_CODE)) c,
       CAST(ISNULL(a.USE_QTY,0) AS float) q, ISNULL(a.FROM_APPLY_YMD,'') fa
  FROM {L}.PR_M_ITEM_BOM a WITH(NOLOCK)
 WHERE ISNULL(a.EXCEPT_FLAG,'0')<>'1' AND CAST(ISNULL(a.USE_QTY,0) AS float)>0
   AND {f}<='{D}' AND {t}>='{D}'""".format(
    L=L, D=D6, f=V.format(f="a.FROM_APPLY_YMD", d="000000"), t=V.format(f="a.TO_APPLY_YMD", d="991231"))
NX = """
SELECT h.item_code p0, LTRIM(RTRIM(h.item_code)) p, LTRIM(RTRIM(l.child_item)) c,
       CAST(ISNULL(l.qty,0) AS float) q, l.bom_id, l.seq
  FROM {S}.bom_line l WITH(NOLOCK) JOIN {S}.bom_header h WITH(NOLOCK) ON h.bom_id=l.bom_id
 WHERE ISNULL(l.except_flag,0)=0 AND CAST(ISNULL(l.qty,0) AS float)>0
   AND {f}<='{D}' AND {t}>='{D}'""".format(
    S=S, D=D6, f=V.format(f="l.from_ymd", d="000000"), t=V.format(f="l.to_ymd", d="991231"))

nx = _nx(); nx.autocommit = False
cur = nx.cursor()

print("=" * 100)
print(" 클린 BOM 수량 동기화 — 라이브 기준 (기준일 {})".format(D6))
print(" 모드: {}".format("★실제 반영(--apply)" if APPLY else "조회만(dry-run)"))
print("=" * 100)

# ── 대상 산출 ──────────────────────────────────────────────────
cur.execute("""
SELECT b.bom_id, b.seq, b.p, b.c, b.q AS old_q, p.q AS new_q, p.fa
  FROM ({NX}) b JOIN ({PR}) p ON p.p=b.p AND p.c=b.c
 WHERE ABS(b.q-p.q)>0.0001
 ORDER BY b.p, b.c""".format(NX=NX, PR=PR))
rows = [tuple(x) for x in cur.fetchall()]

if not rows:
    print("   대상 0건 — 이미 일치합니다.")
    nx.rollback(); nx.close(); sys.exit(0)

print("\n   대상 {}건".format(len(rows)))
print("   {:<22s} {:<22s} {:>8s} {:>8s}  {}".format("부모", "자품번", "현재", "라이브", "적용일"))
for r in rows:
    print("   {:<22s} {:<22s} {:>8g} {:>8g}  {}".format(
        str(r[2]), str(r[3]), r[4], r[5], str(r[6]).strip() or "-"))

if not APPLY:
    print("\n   ※dry-run — 반영하려면 --apply 를 붙여 다시 실행하세요.")
    nx.rollback(); nx.close(); sys.exit(0)

# ── 백업 ───────────────────────────────────────────────────────
BK = "bk_bomline_qty_{}".format(STAMP)
cur.execute("""CREATE TABLE {S}.{BK}(
    bom_id INT, seq INT, parent_item varchar(50), child_item varchar(50),
    old_qty FLOAT, new_qty FLOAT, live_from varchar(10), bk_dt DATETIME)""".format(S=S, BK=BK))
for r in rows:
    cur.execute("""INSERT INTO {S}.{BK}(bom_id,seq,parent_item,child_item,old_qty,new_qty,live_from,bk_dt)
                   VALUES(?,?,?,?,?,?,?,GETDATE())""".format(S=S, BK=BK),
                r[0], r[1], str(r[2]), str(r[3]), float(r[4]), float(r[5]), str(r[6]).strip())
print("\n   백업 생성: {}.{} ({}행)".format(S, BK, len(rows)))

# ── 반영 — 근거키(bom_id, seq) 스코프. 수량만. ────────────────
n = 0
for r in rows:
    cur.execute("UPDATE {S}.bom_line SET qty=? WHERE bom_id=? AND seq=?".format(S=S),
                float(r[5]), r[0], r[1])
    n += cur.rowcount
print("   UPDATE {}행".format(n))

# ── 검증 — 다시 재서 0 이어야 한다 ────────────────────────────
cur.execute("""SELECT COUNT(*) FROM ({NX}) b JOIN ({PR}) p ON p.p=b.p AND p.c=b.c
                WHERE ABS(b.q-p.q)>0.0001""".format(NX=NX, PR=PR))
left = cur.fetchone()[0]
cur.execute("SELECT COUNT(*) FROM ({}) z".format(NX))
tot_nx = cur.fetchone()[0]
cur.execute("SELECT COUNT(*) FROM ({}) z".format(PR))
tot_pr = cur.fetchone()[0]
print("\n   검증 — 남은 불일치 {}건 · 클린 {:,}쌍 · 라이브 {:,}쌍".format(left, tot_nx, tot_pr))

if left == 0 and tot_nx == tot_pr:
    nx.commit()
    print("   ✅ 커밋 완료 — 롤백하려면:")
    print("      UPDATE l SET l.qty=b.old_qty FROM {S}.bom_line l".format(S=S))
    print("        JOIN {S}.{BK} b ON b.bom_id=l.bom_id AND b.seq=l.seq".format(S=S, BK=BK))
else:
    nx.rollback()
    print("   ★검증 실패 — 롤백했습니다(남은 불일치 {} · 행수 {}≠{})".format(left, tot_nx, tot_pr))
    nx.close(); sys.exit(1)

# ── 영향 안내 ─────────────────────────────────────────────────
print("\n   ※원가엔진 캐시는 백엔드 재기동 또는 BOM 화면 저장 시 무효화된다.")
print("   ※자재소요(STEP7)에 반영하려면 계획 편성을 다시 돌려야 한다.")
nx.close()
