# -*- coding: utf-8 -*-
"""계획원본 교체 — nx.plan_dtl ← 레거시 PR_T_PLAN_DTL 의 **엑셀 원본(ORG_*)** (2026-09-02 신설)

왜 필요한가
  웹 편성이 레거시와 같은지 보려면 **출발점(업로드 원본)이 같아야** 한다.
  지금은 웹이 엑셀을 직접 파싱하고 레거시도 따로 파싱해, 원본 단계에서 이미 차이가 난다.
    · 웹 4,622행 / 제번 4,425   ← 389개 제번이 일자별로 분할 저장
    · 레거시 4,425행 / 제번 4,425 ← 제번당 1행, LOT 통째
  이 상태로 편성 결과를 비교하면 "편성 로직 차이"와 "원본 차이"가 섞여 판정이 안 된다.
  ⟹ 레거시 원본을 그대로 복사해 넣고 웹 편성을 돌린다. 그러면 남는 차이 = 편성 로직 차이.

★무엇을 복사하나 — **당김 전 엑셀 원본**
  레거시 PR_T_PLAN_DTL 은 PLAN_YMD 를 당김값으로 덮고 원본을 ORG_* 에 백업한다.
  웹 nx.plan_dtl 은 반대로 PLAN_YMD 가 원본이고 당김은 nx.plan_line_pull 에 따로 있다.
  ⟹ 레거시 ORG_PLAN_YMD / ORG_OUTPUT_HM (= 엑셀 Start Time) 을 웹 PLAN_YMD / START_HM 에 넣는다.
     ORG_ 가 비어 있으면(당김 안 된 건) PLAN_YMD / OUTPUT_HM 이 곧 원본이다.

★컬럼 대응 — 실측으로 확정(2026-09-02, 분할 없는 4,233 제번 기준)
    REMAIN_QTY ← LOT_QTY    4,233/4,233 (100.0%)   ★편성 STEP5 가 LOT 수량으로 쓰는 값
    TOTAL_QTY  ← LOT_QTY    4,208/4,233 ( 99.4%)   (planrev.py:510 주석과 일치)
    PLAN_QTY   ← PLAN_QTY   4,232/4,233
    TOOL       ← TOOLS_DESC
  레거시에 없는 웹 전용 컬럼 3개:
    BUYER_MODEL  → MODEL_NO 로 채운다(4,146/4,622 가 이미 동일. 편성 미사용 = 영향 없음)
    SCHED_GROUP  → 'A' (현재 4,622행 전부 'A' 상수)
  ※BUYER_MODEL·SCHED_GROUP 은 편성 코드(planrev/soyo/partplan/coopplan)에서 참조 0건 —
    grep 으로 확인했다. 화면 표시용이라 교체해도 편성 결과에 영향이 없다.

★안전
  · 라이브 PARTNER_ERP 는 **읽기만** 한다(CLAUDE.md §1-1). 쓰기는 nx 뿐.
  · 실행 전 nx.bk_plandtl_<stamp> 로 **전량 백업**한다. 되돌리기는 --restore.
  · --apply 없이는 조회만(기본 dry-run).

사용
    python _schema/replace_plan_dtl_from_legacy.py             # 조회만
    python _schema/replace_plan_dtl_from_legacy.py --apply     # 교체
    python _schema/replace_plan_dtl_from_legacy.py --restore nx.bk_plandtl_260902_1712
"""
import sys, os, io, argparse, datetime

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8',
                              errors='replace', line_buffering=True)
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, '..', '..', 'New_ERP'))

AP = argparse.ArgumentParser()
AP.add_argument('--apply', action='store_true', help='실제 교체(없으면 조회만)')
AP.add_argument('--restore', default='', help='백업 테이블명으로 원상복구')
ARG = AP.parse_args()

import pyodbc, db_client

CS = (f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};'
      f'DATABASE=PARTNER_ERP_TEST3;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}')
LIVE = 'PARTNER_ERP.dbo.PR_T_PLAN_DTL'
ORG_Y = "RTRIM(ISNULL(NULLIF(l.ORG_PLAN_YMD,''), l.PLAN_YMD))"
ORG_H = "RTRIM(ISNULL(NULLIF(l.ORG_OUTPUT_HM,''), ISNULL(l.OUTPUT_HM,'0800')))"

cn = pyodbc.connect(CS, autocommit=False)
cur = cn.cursor()


def n1(q, *a):
    cur.execute(q, *a)
    r = cur.fetchone()
    return int(r[0] or 0) if r else 0


# ── 복구 모드 ──────────────────────────────────────────────────────
if ARG.restore:
    bk = ARG.restore.strip()
    if not bk.startswith('nx.'):
        bk = 'nx.' + bk
    if not n1(f"SELECT CASE WHEN OBJECT_ID('{bk}','U') IS NULL THEN 0 ELSE 1 END"):
        print(f'★백업 테이블 {bk} 이(가) 없습니다.'); sys.exit(1)
    n_bk = n1(f'SELECT COUNT(*) FROM {bk}')
    print(f'복구: {bk} ({n_bk:,}행) → nx.plan_dtl')
    cur.execute('DELETE FROM nx.plan_dtl')
    cur.execute(f'INSERT INTO nx.plan_dtl SELECT * FROM {bk}')
    print(f'   {cur.rowcount:,}행 복구')
    cn.commit()
    print(f'   현재 nx.plan_dtl = {n1("SELECT COUNT(*) FROM nx.plan_dtl"):,}행')
    cn.close(); sys.exit(0)

print('=' * 74)
print(' 계획원본 교체  nx.plan_dtl ← 레거시 ORG_*(엑셀원본)  '
      + ('[APPLY]' if ARG.apply else '[DRY-RUN — 조회만]'))
print('=' * 74)

# ── 현황 ───────────────────────────────────────────────────────────
web = n1('SELECT COUNT(*) FROM nx.plan_dtl WITH(NOLOCK)')
web_wo = n1('SELECT COUNT(DISTINCT RTRIM(WORK_ORDER)) FROM nx.plan_dtl WITH(NOLOCK)')
leg = n1(f'SELECT COUNT(*) FROM {LIVE} WITH(NOLOCK)')
leg_wo = n1(f'SELECT COUNT(DISTINCT RTRIM(WORK_ORDER)) FROM {LIVE} WITH(NOLOCK)')
web_q = n1('SELECT ISNULL(SUM(PLAN_QTY),0) FROM nx.plan_dtl WITH(NOLOCK)')
leg_q = n1(f'SELECT ISNULL(SUM(PLAN_QTY),0) FROM {LIVE} WITH(NOLOCK)')

print(f'\n① 현재      웹 {web:,}행 / 제번 {web_wo:,} / 수량 {web_q:,}')
print(f'   레거시    {leg:,}행 / 제번 {leg_wo:,} / 수량 {leg_q:,}')
print(f'   → 교체 후 {leg:,}행 (제번당 1행, LOT 통째)  {web-leg:+,}행')

cur.execute(f"""SELECT MIN({ORG_Y}), MAX({ORG_Y}) FROM {LIVE} l WITH(NOLOCK)""")
r = cur.fetchone()
print(f'\n② 복사할 일자 범위(엑셀원본) : {r[0]} ~ {r[1]}')

# 바뀌는 내용 미리보기
print('\n③ 일자가 바뀌는 제번 (웹 현재 → 레거시 엑셀원본)')
cur.execute(f"""SELECT TOP 8 RTRIM(w.WORK_ORDER), RTRIM(w.PLAN_YMD), {ORG_Y},
                       RTRIM(ISNULL(w.START_HM,'')), {ORG_H}
                  FROM nx.plan_dtl w JOIN {LIVE} l WITH(NOLOCK)
                       ON RTRIM(l.WORK_ORDER)=RTRIM(w.WORK_ORDER)
                 WHERE RTRIM(w.PLAN_YMD) <> {ORG_Y}
                 ORDER BY w.WORK_ORDER""")
for x in cur.fetchall():
    print(f'    {x[0]:14s} {x[1]} {x[3]:>4s}  →  {x[2]} {x[4]:>4s}')

if not ARG.apply:
    print('\n※ DRY-RUN 입니다. 실제로 교체하려면 --apply 를 붙이세요.')
    cn.close(); sys.exit(0)

# ── 백업 ───────────────────────────────────────────────────────────
stamp = datetime.datetime.now().strftime('%y%m%d_%H%M')
BK = f'nx.bk_plandtl_{stamp}'
print(f'\n④ 백업 → {BK}')
cur.execute(f"IF OBJECT_ID('{BK}','U') IS NOT NULL DROP TABLE {BK}")
cur.execute(f'SELECT * INTO {BK} FROM nx.plan_dtl')
print(f'   {cur.rowcount:,}행 백업 완료  (되돌리기: --restore {BK})')

# ── 교체 ───────────────────────────────────────────────────────────
print('\n⑤ 교체 실행')
cur.execute('DELETE FROM nx.plan_dtl')
print(f'   기존 {cur.rowcount:,}행 삭제')

cur.execute(f"""INSERT INTO nx.plan_dtl
      (PLAN_YMD, WORK_ORDER, MODEL_NO, BUYER_MODEL, LINE_NO, SCHED_GROUP,
       PLAN_QTY, TOTAL_QTY, REMAIN_QTY, START_HM, TOOL, FROM_SEQ, TO_SEQ, CR_FLAG,
       UPLOAD_DT, ORG_PLAN_YMD, ORG_OUTPUT_HM)
    SELECT {ORG_Y},                                   -- ★엑셀 원본일자
           RTRIM(l.WORK_ORDER),
           RTRIM(ISNULL(l.MODEL_NO,'')),
           RTRIM(ISNULL(l.MODEL_NO,'')),              -- BUYER_MODEL: 레거시 미보유 → MODEL_NO
           RTRIM(ISNULL(l.LINE_NO,'')),
           'A',                                       -- SCHED_GROUP: 현재 전건 'A' 상수
           ISNULL(l.PLAN_QTY,0),
           ISNULL(l.LOT_QTY,0),
           ISNULL(l.LOT_QTY,0),                       -- ★REMAIN_QTY = LOT_QTY (편성 LOT 수량)
           {ORG_H},                                   -- ★엑셀 원본시각
           LEFT(RTRIM(ISNULL(l.TOOLS_DESC,'')),40),
           LEFT(RTRIM(ISNULL(CAST(l.FROM_SEQ AS varchar(20)),'')),20),
           LEFT(RTRIM(ISNULL(CAST(l.TO_SEQ   AS varchar(20)),'')),20),
           RTRIM(ISNULL(l.CR_FLAG,'')),
           GETDATE(),
           {ORG_Y}, {ORG_H}                           -- ORG_* 도 같은 값(원본=원본)
      FROM {LIVE} l WITH(NOLOCK)""")
n_ins = cur.rowcount
print(f'   신규 {n_ins:,}행 적재')
cn.commit()

# ── 검증 ───────────────────────────────────────────────────────────
print('\n⑥ 검증')
w2 = n1('SELECT COUNT(*) FROM nx.plan_dtl')
w2_wo = n1('SELECT COUNT(DISTINCT RTRIM(WORK_ORDER)) FROM nx.plan_dtl')
w2_q = n1('SELECT ISNULL(SUM(PLAN_QTY),0) FROM nx.plan_dtl')
print(f'   행수   웹 {w2:,} / 레거시 {leg:,}   {"✅" if w2==leg else "★불일치"}')
print(f'   제번   웹 {w2_wo:,} / 레거시 {leg_wo:,}   {"✅" if w2_wo==leg_wo else "★불일치"}')
print(f'   수량   웹 {w2_q:,} / 레거시 {leg_q:,}   {"✅" if w2_q==leg_q else "★불일치"}')

bad = n1(f"""SELECT COUNT(*) FROM nx.plan_dtl w JOIN {LIVE} l WITH(NOLOCK)
                    ON RTRIM(l.WORK_ORDER)=RTRIM(w.WORK_ORDER)
              WHERE RTRIM(w.PLAN_YMD) <> {ORG_Y}
                 OR RTRIM(ISNULL(w.START_HM,'')) <> {ORG_H}""")
print(f'   일자·시각 불일치 {bad}건   {"✅" if bad==0 else "★확인 필요"}')

lot = n1(f"""SELECT COUNT(*) FROM nx.plan_dtl w JOIN {LIVE} l WITH(NOLOCK)
                    ON RTRIM(l.WORK_ORDER)=RTRIM(w.WORK_ORDER)
              WHERE ISNULL(w.REMAIN_QTY,0) <> ISNULL(l.LOT_QTY,0)""")
print(f'   LOT(REMAIN_QTY) 불일치 {lot}건   {"✅" if lot==0 else "★확인 필요"}')

print(f'\n   백업 = {BK}  (되돌리기: python _schema/replace_plan_dtl_from_legacy.py --restore {BK})')
print('   ★다음 단계: 웹 화면에서 계획 편성(일괄작업)을 돌린 뒤 레거시와 대사한다.')
cn.close()
