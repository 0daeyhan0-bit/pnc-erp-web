# -*- coding: utf-8 -*-
"""드래그 실적 → PR_T_PROD_DTL_PROC 백필 (2026-09-07)

  왜 — 「파트별 생산실적현황」(prod.py:154)은 PR_T_PROD_DTL_PROC 를 읽는다.
       레거시 520(바코드)은 PROD_DTL 과 _PROC 두 곳에 다 쓰는데,
       웹 드래그 실적(dragprod.py)은 PROD_DTL 에만 써서 **실적을 잡아도 실적현황이 0건**이었다.
       코드는 고쳤지만(dragprod.py ①-b) 그 전에 잡힌 실적은 _PROC 에 없다 → 이 스크립트로 채운다.

  규칙
    · 대상 = UPDATE_WINDOW='w_pr_input_410_drag' 이면서 _PROC 에 짝이 없는 건
    · PROC_CODE = PART_CODE (드래그 실적은 파트 단위 — dragprod.py ①-b 와 동일)
    · ★같은 (도번·일자·시각·파트)가 여러 행이면 **합산해서 1행**으로 넣는다.
      _PROC PK = WO+SWO+ITEM+YMD+HMS+WORK_CODE+PROC_CODE+S_WORK_CODE 라
      행마다 넣으면 PK 충돌이 난다(실측: 101639 초에 14행).
    · WORK_ORDER 는 그 그룹의 대표값(MAX) — 같은 초·같은 파트면 보통 같은 제번이다.

  실행
    python _migration/dragprod_proc_backfill.py            # DRY-RUN(대상만)
    python _migration/dragprod_proc_backfill.py --commit   # 실제 반영
"""
import sys, os, io

BE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "PNC_ERP_Web", "backend")
sys.path.insert(0, BE); os.chdir(BE)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
import common, db_client            # noqa: E402

COMMIT = "--commit" in sys.argv
WIN = "w_pr_input_410_drag"

cn = db_client.get_connection()
cur = cn.cursor()

print("=" * 78)
print(f"  드래그 실적 → _PROC 백필 — {'★실제 반영(--commit)' if COMMIT else 'DRY-RUN (반영 안 함)'}")
print("=" * 78)

# 대상 = 드래그 실적 중 _PROC 에 짝이 없는 것 → (도번·일자·시각·파트) 로 합산
cur.execute(f"""
    SELECT MAX(RTRIM(ISNULL(d.WORK_ORDER,''))) wo, RTRIM(d.ITEM_CODE) item,
           d.PROD_YMD ymd, d.PROD_HMS hms, RTRIM(ISNULL(d.PART_CODE,'')) part,
           MAX(RTRIM(ISNULL(d.LINE_NO,''))) line, SUM(d.PROD_QTY) qty,
           MAX(RTRIM(ISNULL(d.PROD_USER_ID,''))) usr, COUNT(*) n
      FROM nx.PR_T_PROD_DTL d WITH(NOLOCK)
     WHERE ISNULL(d.UPDATE_WINDOW,'')=?
       AND ISNULL(d.PART_CODE,'')<>''
       AND NOT EXISTS(SELECT 1 FROM nx.PR_T_PROD_DTL_PROC p WITH(NOLOCK)
                       WHERE p.ITEM_CODE=d.ITEM_CODE AND p.PROD_YMD=d.PROD_YMD
                         AND p.PROD_HMS=d.PROD_HMS
                         AND ISNULL(p.PROC_CODE,'')=ISNULL(d.PART_CODE,''))
     GROUP BY RTRIM(d.ITEM_CODE), d.PROD_YMD, d.PROD_HMS, RTRIM(ISNULL(d.PART_CODE,''))
     ORDER BY d.PROD_YMD, d.PROD_HMS""", WIN)
rows = cur.fetchall()

print(f"\n대상 {len(rows)}그룹 · 원본 {sum(int(r[8]) for r in rows)}행 · 수량 {sum(float(r[6] or 0) for r in rows):,.0f}\n")
print(f"  {'일자':<8}{'시각':<8}{'도번':<26}{'파트':<6}{'라인':<6}{'수량':>6}{'원본행':>7}")
for r in rows:
    print(f"  {r[2]:<8}{r[3]:<8}{str(r[1])[:25]:<26}{str(r[4]):<6}{str(r[5]):<6}{float(r[6]):>6,.0f}{r[8]:>7}")

if not rows:
    print("\n채울 대상이 없습니다.")
    sys.exit(0)

if not COMMIT:
    print(f"\n※ DRY-RUN 입니다. 위 {len(rows)}그룹이 맞는지 확인한 뒤")
    print("   python _migration/dragprod_proc_backfill.py --commit  으로 반영하세요.")
    sys.exit(0)

n = 0
try:
    for r in rows:
        wo, item, ymd, hms, part, line, qty, usr = (
            str(r[0] or ""), str(r[1]), str(r[2]), str(r[3]), str(r[4]),
            str(r[5] or ""), int(r[6] or 0), str(r[7] or ""))
        cur.execute("""INSERT INTO nx.PR_T_PROD_DTL_PROC
                         (WORK_ORDER,SPLIT_WORK_ORDER,ITEM_CODE,PROD_YMD,PROD_HMS,
                          WORK_CODE,PROC_CODE,S_WORK_CODE,LINE_NO,PROD_QTY,PROD_USER_ID,
                          PROD_TAG,FINISH_FLAG,UPDATE_USER_ID,UPDATE_DATETIME,UPDATE_WINDOW)
                       VALUES(?,'',?,?,?,'',?,0,?,?,?,'','0',?,GETDATE(),?)""",
                    wo, item, ymd, hms, part, line, qty, usr, "backfill", WIN)
        n += 1
    cn.commit()
    print(f"\n✅ 반영 완료 — {n}그룹 삽입")
    cur.execute("""SELECT COUNT(*), ISNULL(SUM(PROD_QTY),0) FROM nx.PR_T_PROD_DTL_PROC
                    WHERE ISNULL(UPDATE_WINDOW,'')=?""", WIN)
    c2, q2 = cur.fetchone()
    print(f"   _PROC 의 드래그분: {c2}행 / 수량 {float(q2):,.0f}")
except Exception as e:
    cn.rollback()
    print("\n★실패 — 롤백했습니다:", str(e)[:200])
    raise
finally:
    cn.close()
