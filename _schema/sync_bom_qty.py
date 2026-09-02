# -*- coding: utf-8 -*-
"""BOM 소요량(qty) 동기화 + 중복링크 정리 — nx.bom_line ← 라이브 PR_M_ITEM_BOM
   (2026-09-02 신설)

왜 필요한가
  레거시 품목BOM관리에서 **소요량을 고치면** 클린 BOM 이 따라가지 않아 웹만 옛 값으로 남는다.
  소요엔진이 그 값을 곱하므로 **자재소요가 그대로 틀어진다.**

  실측 2026-09-02 : qty 불일치 45행(계획 영향 7종) → 자재소요 −388.
    예) AJR30133606 → MEV39836107 : 클린 1.0 / 라이브 2.0  ⟹ 웹이 정확히 절반.

두 가지를 처리한다
  (A) **값 차이** — 같은 (상위,자재)가 양쪽 1행씩인데 qty 가 다름 → 라이브 값으로 UPDATE.
  (B) **중복 링크** — 클린에만 같은 (상위,자재)가 2행. 실측 13쌍 전부 같은 패턴이다:

        seq 낮음  qty=옛값  from_ymd 있음(250502·260319…)   ← 원본
        seq 높음  qty=새값  from_ymd **빈 값**              ← 나중에 INSERT 된 행

      과거 동기화가 UPDATE 대신 INSERT 를 해서 생긴 것으로 보인다.
      뷰(v_pr_bom)는 빈 from_ymd 를 '000000' 으로 바꾸므로 **두 행 다 유효기간을 통과**해
      엔진이 잘못된 쪽을 잡거나 이중계상한다.
      ⟹ 라이브에 1행뿐이면 **클린도 1행으로** 남긴다(라이브 값과 같은 행을 살리고 나머지 삭제).

★안전 원칙
  · 라이브는 **읽기만**(CLAUDE.md §1-1). 쓰기는 nx 뿐.
  · `--apply` 없이는 **조회만**(기본 dry-run).
  · 삭제는 **근거키 스코프**로만(§1-3) — (bom_id, seq) 를 하나씩 지목한다. 태그 대량삭제 없음.
  · 적용 전 **백업 테이블** 생성.
  · ⚠ 반영 후 **편성(④파트별 → ⑤자재소요)을 다시 돌려야** 계획에 반영된다.

사용
    python _schema/sync_bom_qty.py            # 조회만(기본)
    python _schema/sync_bom_qty.py --apply    # 실제 반영
    python _schema/sync_bom_qty.py --qty-only # 값 차이만(중복 정리 제외)
"""
import sys, os, io, argparse, datetime as _dt

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8',
                              errors='replace', line_buffering=True)
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, '..', '..', 'New_ERP'))

AP = argparse.ArgumentParser()
AP.add_argument('--apply', action='store_true', help='실제 반영(없으면 조회만)')
AP.add_argument('--qty-only', action='store_true', help='값 차이만 처리(중복 정리 제외)')
AP.add_argument('--top', type=int, default=50, help='상세 출력 건수')
ARG = AP.parse_args()

import pyodbc, db_client

CS = (f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};'
      f'DATABASE=PARTNER_ERP_TEST3;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}')
cn = pyodbc.connect(CS, autocommit=False)
cur = cn.cursor()

print('=' * 78)
print(' BOM 소요량 동기화 + 중복링크 정리  ' + ('[APPLY]' if ARG.apply else '[DRY-RUN — 조회만]'))
print('=' * 78)

# ── (B) 중복 링크 목록 ────────────────────────────────────────────
#     클린에 2행 이상 & 라이브엔 1행 → 라이브 값과 같은 행만 남긴다.
cur.execute("""
SELECT RTRIM(h.item_code) it, RTRIM(c.child_item) mat, c.bom_id, c.seq,
       CAST(c.qty AS float) q, RTRIM(ISNULL(c.from_ymd,'')) fy
  FROM nx.bom_header h WITH(NOLOCK)
  JOIN nx.bom_line c ON c.bom_id = h.bom_id
 WHERE EXISTS(SELECT 1 FROM nx.bom_header h2 WITH(NOLOCK)
                JOIN nx.bom_line c2 ON c2.bom_id = h2.bom_id
               WHERE RTRIM(h2.item_code) = RTRIM(h.item_code)
                 AND RTRIM(c2.child_item) = RTRIM(c.child_item)
               GROUP BY RTRIM(h2.item_code), RTRIM(c2.child_item)
              HAVING COUNT(*) > 1)
 ORDER BY 1, 2, 4""")
dup_rows = cur.fetchall()

dups = {}
for it, mat, bid, seq, q, fy in dup_rows:
    dups.setdefault((str(it).strip(), str(mat).strip()), []).append(
        (int(bid), int(seq), float(q), str(fy).strip()))

# 라이브 값 조회
del_targets = []      # (bom_id, seq, 사유)
keep_note = []
for (it, mat), rows in sorted(dups.items()):
    cur.execute("""SELECT CAST(USE_QTY AS float) FROM PARTNER_ERP.dbo.PR_M_ITEM_BOM WITH(NOLOCK)
                    WHERE RTRIM(ITEM_CODE)=? AND RTRIM(MAT_CODE)=?""", it, mat)
    lv = [float(r[0]) for r in cur.fetchall()]
    if len(lv) != 1:
        keep_note.append((it, mat, f'라이브 {len(lv)}행 — 자동정리 대상 아님'))
        continue
    target = lv[0]
    same = [r for r in rows if abs(r[2] - target) < 1e-6]
    if not same:
        keep_note.append((it, mat, f'라이브 {target} 와 같은 행이 없음 — 수동확인'))
        continue
    keep = same[0]                       # 라이브와 같은 값 중 seq 가장 작은 행을 남긴다
    for r in rows:
        if (r[0], r[1]) != (keep[0], keep[1]):
            del_targets.append((r[0], r[1], f'{it}|{mat} qty={r[2]} (라이브 {target} 아님)'))

print(f'\n[B] 중복 링크  {len(dups)}쌍 · 삭제대상 {len(del_targets)}행'
      + (f' · 수동확인 {len(keep_note)}쌍' if keep_note else ''))
for (it, mat), rows in sorted(dups.items())[:ARG.top]:
    cur.execute("""SELECT CAST(USE_QTY AS float) FROM PARTNER_ERP.dbo.PR_M_ITEM_BOM WITH(NOLOCK)
                    WHERE RTRIM(ITEM_CODE)=? AND RTRIM(MAT_CODE)=?""", it, mat)
    lv = [float(r[0]) for r in cur.fetchall()]
    detail = ' · '.join(f'seq{r[1]}={r[2]:g}{"(fy없음)" if not r[3] else ""}' for r in rows)
    print(f'   {it:<24}{mat:<26} 클린[{detail}] → 라이브 {lv}')
for it, mat, why in keep_note:
    print(f'   ⚠ {it:<24}{mat:<26} {why}')

# ── (A) 값 차이 (중복 아닌 것) ─────────────────────────────────────
dup_keys = set(dups.keys())
cur.execute("""
SELECT RTRIM(h.item_code), RTRIM(c.child_item), c.bom_id, c.seq,
       CAST(c.qty AS float), CAST(l.USE_QTY AS float)
  FROM nx.bom_header h WITH(NOLOCK)
  JOIN nx.bom_line c ON c.bom_id = h.bom_id
  JOIN PARTNER_ERP.dbo.PR_M_ITEM_BOM l WITH(NOLOCK)
    ON RTRIM(l.ITEM_CODE) = RTRIM(h.item_code)
   AND RTRIM(l.MAT_CODE)  = RTRIM(c.child_item)
 WHERE ABS(ISNULL(CAST(c.qty AS float),0) - ISNULL(CAST(l.USE_QTY AS float),0)) > 0.000001
 ORDER BY 1, 2""")
qty_all = [(str(a).strip(), str(b).strip(), int(c), int(d), float(e), float(f))
           for a, b, c, d, e, f in cur.fetchall()]
qty_rows = [r for r in qty_all if (r[0], r[1]) not in dup_keys]

print(f'\n[A] 소요량 차이  {len(qty_rows)}행  (중복쌍 {len(qty_all)-len(qty_rows)}행은 [B]에서 처리)')
for r in qty_rows[:ARG.top]:
    print(f'   {r[0]:<24}{r[1]:<26} {r[4]:>9.4f} → {r[5]:>9.4f}')

# 영향범위
if qty_rows or del_targets:
    its = sorted({r[0] for r in qty_rows} | {k[0] for k in dups})
    ph = ','.join('?' * len(its))
    cur.execute(f"""SELECT COUNT(DISTINCT RTRIM(assy_item_code)) FROM nx.plan_part_mat WITH(NOLOCK)
                     WHERE plan_ymd>='260902' AND RTRIM(assy_item_code) IN ({ph})""", *its)
    print(f'\n[C] 영향범위 — 자재소요에 등장하는 상위품목 {int(cur.fetchone()[0] or 0):,}종')

if not (qty_rows or del_targets):
    print('\n   ✅ 이미 동기 상태입니다.')
    cn.close()
    sys.exit(0)

if not ARG.apply:
    print('\n※ DRY-RUN 입니다. 실제로 반영하려면 --apply 를 붙이세요.')
    cn.close()
    sys.exit(0)

# ── 백업 ───────────────────────────────────────────────────────────
bk = 'bk_bomline_qty_' + _dt.datetime.now().strftime('%y%m%d_%H%M')
cur.execute(f"""SELECT c.bom_id, c.seq, RTRIM(h.item_code) item_code,
                       c.child_item, c.qty, c.qty_pr, c.from_ymd, c.to_ymd
                  INTO nx.{bk}
                  FROM nx.bom_line c JOIN nx.bom_header h ON h.bom_id=c.bom_id
                 WHERE 1=0""")
for bid, seq, _ in del_targets:
    cur.execute(f"""INSERT INTO nx.{bk}
                    SELECT c.bom_id, c.seq, RTRIM(h.item_code), c.child_item, c.qty, c.qty_pr,
                           c.from_ymd, c.to_ymd
                      FROM nx.bom_line c JOIN nx.bom_header h ON h.bom_id=c.bom_id
                     WHERE c.bom_id=? AND c.seq=?""", bid, seq)
for it, mat, bid, seq, _, _ in qty_rows:
    cur.execute(f"""INSERT INTO nx.{bk}
                    SELECT c.bom_id, c.seq, RTRIM(h.item_code), c.child_item, c.qty, c.qty_pr,
                           c.from_ymd, c.to_ymd
                      FROM nx.bom_line c JOIN nx.bom_header h ON h.bom_id=c.bom_id
                     WHERE c.bom_id=? AND c.seq=?""", bid, seq)
print(f'\n④ 백업 — nx.{bk}')

# ── 반영 ───────────────────────────────────────────────────────────
nd = 0
if not ARG.qty_only:
    for bid, seq, why in del_targets:
        cur.execute('DELETE FROM nx.bom_line WHERE bom_id=? AND seq=?', bid, seq)
        nd += cur.rowcount
    print(f'⑤ 중복 삭제 — {nd:,}행 (근거키 (bom_id,seq) 지목)')

nu = 0
for it, mat, bid, seq, oq, lq in qty_rows:
    cur.execute("""UPDATE nx.bom_line SET qty=?, qty_pr=?
                    WHERE bom_id=? AND seq=?""", lq, lq, bid, seq)
    nu += cur.rowcount
print(f'⑥ 소요량 갱신 — {nu:,}행')
cn.commit()

# ── 검증 ───────────────────────────────────────────────────────────
cur.execute("""SELECT COUNT(*)
  FROM nx.bom_header h WITH(NOLOCK)
  JOIN nx.bom_line c ON c.bom_id=h.bom_id
  JOIN PARTNER_ERP.dbo.PR_M_ITEM_BOM l WITH(NOLOCK)
    ON RTRIM(l.ITEM_CODE)=RTRIM(h.item_code) AND RTRIM(l.MAT_CODE)=RTRIM(c.child_item)
 WHERE ABS(ISNULL(CAST(c.qty AS float),0)-ISNULL(CAST(l.USE_QTY AS float),0))>0.000001""")
left_q = int(cur.fetchone()[0] or 0)
cur.execute("""SELECT COUNT(*) FROM (
   SELECT RTRIM(h.item_code) i, RTRIM(c.child_item) m
     FROM nx.bom_header h WITH(NOLOCK) JOIN nx.bom_line c ON c.bom_id=h.bom_id
    GROUP BY RTRIM(h.item_code), RTRIM(c.child_item) HAVING COUNT(*)>1) z""")
left_d = int(cur.fetchone()[0] or 0)
print(f'\n⑦ 검증 — 잔여 qty 불일치 {left_q}행 · 중복쌍 {left_d}쌍')
print('   ' + ('✅ 동기화 완료' if left_q == 0 and left_d == 0 else '★일부 남음 — 위 수동확인 항목 참조'))
print(f'   되돌리려면: nx.{bk} 참조')
print('   ⚠ ★편성(④파트별 → ⑤자재소요)을 다시 돌려야 계획에 반영된다.')
cn.close()
