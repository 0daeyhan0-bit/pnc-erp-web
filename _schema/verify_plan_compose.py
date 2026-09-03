# -*- coding: utf-8 -*-
"""생산계획 편성 검증 — 웹 산출물 ↔ 레거시 대사 (2026-09-02 신설)

무엇을 보는가
  편성 4단계 산출물을 레거시와 **같은 그레인**으로 대사한다.

    ④품목별  nx.plan_item_dtl   ↔ PR_T_PLAN_ITEM_DTL
    ④파트별  nx.plan_part_dtl   ↔ PR_T_PLAN_PART_DTL
    ⑤자재소요 nx.plan_part_mat   ↔ PR_T_PLAN_PART_MAT
    ⑤조달    nx.plan_mat_source  (웹 전용 — 레거시 대응 없음, 총량만)

★판정 원칙 (실측으로 얻은 것 — 어기면 오판한다)
  1. **최소 그레인에서 본다.** (작업처,자재) 합산은 +/− 가 상쇄돼 문제를 숨긴다.
     실측: 합산 11쌍 → 제번 그레인 83건·최대 +300.
  2. **레거시 대비**로 본다. 절대값 0 을 요구하면 정상 구조를 결함으로 오판한다
     (파트별을 안 거치는 수주·직납품 계열은 레거시에도 있다).
  3. **BOM 재현으로 판정하지 않는다.** 엣지 개수·ad-hoc 전개 비교는 전부 틀린다 —
     v_pr_bom 은 except 행까지 담고, 엔진은 용접봉(RAC*)을 설계상 제외한다.
     판정은 **편성 산출물끼리** 한다.
     ★`nx_soyo_engine.prod_soyo` 로 대조하는 것도 틀린다(2026-09-02 실측 오판).
       그건 **최하위 leaf 만** 집계하는 원가용 walker라 중간 조립품(AJR76462726 등)을
       관통해 0 으로 만든다. 계획 STEP7 은 **가공공정 전이 그레인**이라 그 중간품을
       그대로 계상한다 — 실제 plan_part_mat 에서는 웹·레거 모두 18.0 으로 일치했다.
       ⟹ 소요 판정은 반드시 `nx.plan_part_mat` ↔ `PR_T_PLAN_PART_MAT` 로.
  4. 한 방향 쏠림(웹만 과다/부족)이면 **축 오류**를 먼저 의심한다.

사용
    python _schema/verify_plan_compose.py                 # 전체
    python _schema/verify_plan_compose.py --from 260901   # 기준일 지정
    python _schema/verify_plan_compose.py --top 30        # 차이 상세 건수
"""
import sys, os, io, argparse

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8',
                              errors='replace', line_buffering=True)
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, '..', '..', 'New_ERP'))

AP = argparse.ArgumentParser()
AP.add_argument('--from', dest='dfrom', default='', help='기준일 YYMMDD(기본=계획 최소일)')
AP.add_argument('--to', dest='dto', default='', help='종료일 YYMMDD(기본=웹 계획 최대일)')
AP.add_argument('--top', type=int, default=15, help='차이 상세 출력 건수')
ARG = AP.parse_args()

import pyodbc, db_client

CS = (f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};'
      f'DATABASE=PARTNER_ERP_TEST3;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}')
cn = pyodbc.connect(CS, autocommit=True)
cur = cn.cursor()

BAR = '=' * 78


def n1(q, *a):
    cur.execute(q, *a)
    r = cur.fetchone()
    return int(r[0] or 0) if r and r[0] is not None else 0


def f1(q, *a):
    cur.execute(q, *a)
    r = cur.fetchone()
    return float(r[0] or 0) if r and r[0] is not None else 0.0


# ── 기준일 ─────────────────────────────────────────────────────────
DF = ARG.dfrom.strip()
DT = ARG.dto.strip()
if not DF or not DT:
    # ★기본 = **웹 계획 기간**(이상치 제외). 레거시 PR_T_PLAN_* 는 1년 넘게 누적돼 있어
    #   상한을 안 걸면 "레거시에만 N키"가 수천 건 나온다 — 비교축 오류다(2026-09-03 실측:
    #   레거 일자 349개 vs 웹 25개). 같은 창으로 잘라야 편성 차이가 보인다.
    cur.execute("""SELECT MIN(RTRIM(ISNULL(PLAN_YMD,''))), MAX(RTRIM(ISNULL(PLAN_YMD,'')))
                     FROM nx.plan_dtl WITH(NOLOCK)
                    WHERE PLAN_YMD BETWEEN '200101' AND '991231'""")
    r = cur.fetchone()
    DF = DF or (str(r[0]).strip() if r and r[0] else '260901')
    DT = DT or (str(r[1]).strip() if r and r[1] else '991231')

print(BAR)
print(f' 생산계획 편성 검증 — 웹 ↔ 레거시 대사   (계획기간 {DF} ~ {DT})')
print(BAR)

# ── 0. 편성 시점 확인 ★가장 먼저 볼 것 ─────────────────────────────
#    "차이가 갑자기 커졌다"의 태반은 **편성 시점이 다른 것**이다.
print('\n[0] 편성 시점 — 언제 돈 결과를 보고 있나')
#    ★plan_part_mat/PART_MAT 에는 시각 컬럼이 없다 — 편성 로그와 조달(compose_dt)로 본다.
for lbl, q in (
    ('웹  계획업로드 nx.plan_dtl.UPLOAD_DT ',
     "SELECT MAX(UPLOAD_DT) FROM nx.plan_dtl WITH(NOLOCK)"),
    ('웹  조달편성  nx.plan_mat_source     ',
     "SELECT MAX(COMPOSE_DT) FROM nx.plan_mat_source WITH(NOLOCK)"),
    ('웹  편성로그  nx.plan_job_log(⑤自材) ',
     "SELECT MAX(ins_dt) FROM nx.plan_job_log WITH(NOLOCK) WHERE job_code='T'"),
    ('레거 계획원본  PR_T_PLAN_DTL          ',
     "SELECT MAX(INSERT_DATETIME) FROM PARTNER_ERP.dbo.PR_T_PLAN_DTL WITH(NOLOCK)")):
    try:
        cur.execute(q)
        r = cur.fetchone()
        print(f'    {lbl} : {str(r[0])[:19] if r and r[0] else "(없음)"}')
    except Exception as e:
        print(f'    {lbl} : (조회불가 {str(e)[:36]})')

# ── 1. 계획 원본 ───────────────────────────────────────────────────
print('\n[1] 계획 원본 (①의 입구)')
w = n1("SELECT COUNT(*) FROM nx.plan_dtl WITH(NOLOCK) WHERE PLAN_YMD BETWEEN ? AND ?", DF, DT)
l = n1("SELECT COUNT(*) FROM PARTNER_ERP.dbo.PR_T_PLAN_DTL WITH(NOLOCK) WHERE PLAN_YMD BETWEEN ? AND ?", DF, DT)
wq = f1("SELECT SUM(CAST(PLAN_QTY AS float)) FROM nx.plan_dtl WITH(NOLOCK) WHERE PLAN_YMD BETWEEN ? AND ?", DF, DT)
lq = f1("SELECT SUM(CAST(PLAN_QTY AS float)) FROM PARTNER_ERP.dbo.PR_T_PLAN_DTL WITH(NOLOCK) WHERE PLAN_YMD BETWEEN ? AND ?", DF, DT)
print(f'    행수  웹 {w:,} / 레거 {l:,}   ({w-l:+,})')
print(f'    수량  웹 {wq:,.0f} / 레거 {lq:,.0f}   ({wq-lq:+,.0f})')

# ── 2. 추가계획(A/S) ───────────────────────────────────────────────
print('\n[2] 추가계획 — 동기화 상태')
w = n1("SELECT COUNT(*) FROM nx.prod_plan_input WITH(NOLOCK)")
l = n1("SELECT COUNT(*) FROM PARTNER_ERP.dbo.PR_T_PLAN_INPUT WITH(NOLOCK)")
d = n1("""SELECT COUNT(*) FROM nx.prod_plan_input w
           JOIN PARTNER_ERP.dbo.PR_T_PLAN_INPUT l WITH(NOLOCK)
             ON RTRIM(l.WORK_ORDER)=RTRIM(w.work_order)
          WHERE ISNULL(RTRIM(w.plan_ymd),'')<>ISNULL(RTRIM(l.PLAN_YMD),'')""")
mark = 'OK' if (w == l and d == 0) else '★차이 — sync_prod_plan_input_refresh.py --apply 필요'
print(f'    웹 {w:,} / 레거 {l:,} · 일자다름 {d:,}행   {mark}')


def cmp_grain(title, wtbl, ltbl, wcols, lcols, qty_w, qty_l, where_w='', where_l=''):
    """같은 그레인으로 양쪽을 접어 대사한다. wcols/lcols = 그레인 컬럼(순서 동일).

    ★키는 **한 컬럼으로 합쳐서** 만든다(구분자 '|').
      다중 컬럼을 그대로 나열하면 CTE 에서 '열 이름이 지정되지 않았습니다'(8155) 가 난다.
      합친 키는 차이 상세 출력에도 그대로 쓸 수 있어 읽기도 편하다."""
    print(f'\n{title}')
    wsel = " + '|' + ".join(f"RTRIM(ISNULL({c},''))" for c in wcols)
    lsel = " + '|' + ".join(f"RTRIM(ISNULL({c},''))" for c in lcols)
    ww = f'WHERE {where_w}' if where_w else ''
    wl = f'WHERE {where_l}' if where_l else ''
    try:
        cur.execute(f"""
        WITH w AS (SELECT {wsel} k, SUM(CAST(ISNULL({qty_w},0) AS float)) q
                     FROM {wtbl} WITH(NOLOCK) {ww} GROUP BY {wsel}),
             l AS (SELECT {lsel} k, SUM(CAST(ISNULL({qty_l},0) AS float)) q
                     FROM {ltbl} WITH(NOLOCK) {wl} GROUP BY {lsel})
        SELECT (SELECT COUNT(*) FROM w), (SELECT COUNT(*) FROM l),
               (SELECT ISNULL(SUM(q),0) FROM w), (SELECT ISNULL(SUM(q),0) FROM l),
               (SELECT COUNT(*) FROM w LEFT JOIN l ON l.k=w.k WHERE l.k IS NULL),
               (SELECT COUNT(*) FROM l LEFT JOIN w ON w.k=l.k WHERE w.k IS NULL),
               (SELECT COUNT(*) FROM w JOIN l ON l.k=w.k WHERE ABS(w.q-l.q)>0.001)""")
        r = cur.fetchone()
        wn, ln, wq, lq, wonly, lonly, qdiff = (
            int(r[0]), int(r[1]), float(r[2]), float(r[3]),
            int(r[4]), int(r[5]), int(r[6]))
    except Exception as e:
        print(f'    ★조회 실패 — {str(e)[:110]}')
        return
    print(f'    키    웹 {wn:,} / 레거 {ln:,}   웹만 {wonly:,} · 레거만 {lonly:,}')
    print(f'    수량  웹 {wq:,.0f} / 레거 {lq:,.0f}   ({wq-lq:+,.0f})')
    print(f'    양쪽 있으나 수량 다름 {qdiff:,}건')
    tot = wonly + lonly + qdiff
    if tot == 0:
        print('    ✅ 완전 일치')
        return
    # ★한 방향 쏠림이면 축 오류를 의심한다
    if wonly and not lonly:
        print('    ⚠ 웹에만 있는 키가 한 방향으로 쏠렸다 — 축(일자/제번) 오류를 먼저 의심')
    if lonly and not wonly:
        print('    ⚠ 레거시에만 있는 키가 한 방향 — 웹 편성이 빠뜨렸거나 마스터가 낡았다')
    # 상세
    try:
        cur.execute(f"""
        WITH w AS (SELECT {wsel} k, SUM(CAST(ISNULL({qty_w},0) AS float)) q
                     FROM {wtbl} WITH(NOLOCK) {ww} GROUP BY {wsel}),
             l AS (SELECT {lsel} k, SUM(CAST(ISNULL({qty_l},0) AS float)) q
                     FROM {ltbl} WITH(NOLOCK) {wl} GROUP BY {lsel})
        SELECT TOP {ARG.top} ISNULL(w.k,l.k), ISNULL(l.q,0), ISNULL(w.q,0),
               ISNULL(w.q,0)-ISNULL(l.q,0) d
          FROM w FULL OUTER JOIN l ON l.k=w.k
         WHERE w.k IS NULL OR l.k IS NULL OR ABS(w.q-l.q)>0.001
         ORDER BY ABS(ISNULL(w.q,0)-ISNULL(l.q,0)) DESC""")
        print(f'    차이 상위 {ARG.top} (키 · 레거 · 웹 · 차)')
        for x in cur.fetchall():
            print('      %-34s %12s %12s %+12s' % (
                str(x[0])[:34], format(float(x[1]), ',.0f'),
                format(float(x[2]), ',.0f'), format(float(x[3]), ',.0f')))
    except Exception as e:
        print(f'    (상세 조회 실패 {str(e)[:60]})')


# ── 3. ④품목별계획 ────────────────────────────────────────────────
#    ★품목 컬럼명은 양쪽 다 C_ITEM_CODE 다(ITEM_CODE 아님 — 실측 확인).
#    ★★기간 필터 필수. 레거시 PR_T_PLAN_ITEM_DTL 은 **전 기간 누적**(110,813키)이고
#      웹 nx.plan_item_dtl 은 **현재 편성분만**(8,550키) 담는다. 필터 없이 비교하면
#      "레거시만 102,592키"라는 무의미한 숫자가 나온다(2026-09-02 실측 오판).
_WPY = f"PLAN_YMD BETWEEN '{DF}' AND '{DT}'"
cmp_grain('[3] ④품목별계획 — 그레인 (제번, 품목)',
          'nx.plan_item_dtl', 'PARTNER_ERP.dbo.PR_T_PLAN_ITEM_DTL',
          ['WORK_ORDER', 'C_ITEM_CODE'], ['WORK_ORDER', 'C_ITEM_CODE'],
          'PLAN_QTY', 'PLAN_QTY', where_w=_WPY, where_l=_WPY)

# ── 4. ④파트별계획 ────────────────────────────────────────────────
#    ★수량은 양쪽 다 PART_PLAN_QTY 로 맞춘다. 레거시에 PLAN_QTY 도 있지만 그건
#      상위(제번) 수량이라 웹 part_plan_qty 와 그레인이 다르다 — 섞으면 전건 불일치가 난다.
cmp_grain('[4] ④파트별계획 — 그레인 (제번, ASSY도번, 품목)',
          'nx.plan_part_dtl', 'PARTNER_ERP.dbo.PR_T_PLAN_PART_DTL',
          ['work_order', 'assy_item_code', 'item_code'],
          ['WORK_ORDER', 'ASSY_ITEM_CODE', 'ITEM_CODE'],
          'part_plan_qty', 'PART_PLAN_QTY',
          where_w=f"PLAN_YMD BETWEEN '{DF}' AND '{DT}'", where_l=_WPY)

# ── 5. ⑤자재소요 ★최소 그레인 ─────────────────────────────────────
cmp_grain('[5] ⑤자재소요 — ★최소 그레인 (제번, ASSY도번, 자재)',
          'nx.plan_part_mat', 'PARTNER_ERP.dbo.PR_T_PLAN_PART_MAT',
          ['work_order', 'assy_item_code', 'mat_code'],
          ['WORK_ORDER', 'ASSY_ITEM_CODE', 'MAT_CODE'],
          'part_plan_qty', 'PART_PLAN_QTY',
          where_w=f"PLAN_YMD BETWEEN '{DF}' AND '{DT}'", where_l=_WPY)

# ── 6. ⑤자재소요 — 업체별(운영 관점) ──────────────────────────────
cmp_grain('[6] ⑤자재소요 — 업체×자재 (발주가 어디로 나가나)',
          'nx.plan_part_mat', 'PARTNER_ERP.dbo.PR_T_PLAN_PART_MAT',
          ['mat_work_center_code', 'mat_code'],
          ['MAT_WORK_CENTER_CODE', 'MAT_CODE'],
          'part_plan_qty', 'PART_PLAN_QTY',
          where_w=f"PLAN_YMD BETWEEN '{DF}' AND '{DT}'", where_l=_WPY)

# ── 6b. ★당김(part_plan_ymd) 대사 ─────────────────────────────────
#    ★2026-09-02 신설. [4] 는 plan_ymd(생산계획일) 축이라 **당김 차이를 못 잡는다** —
#      총량이 같아도 날짜 배분이 다르면 화면(410 파트별 생산계획)의 일자별 계획이 어긋난다.
#      실측: 총량 차 +20 인데 09/03 +270 · 09/04 +630 · 09/07 −531 로 벌어졌다.
#      화면이 보는 축은 **part_plan_ymd**(당김 적용된 파트 착수일)다.
print('\n[6b] ★당김 일자(part_plan_ymd) — 화면이 보는 축')
try:
    cur.execute(f"""
    SELECT w.d, ISNULL(w.q,0), ISNULL(l.q,0), ISNULL(w.q,0)-ISNULL(l.q,0)
      FROM (SELECT RTRIM(ISNULL(part_plan_ymd,'')) d, SUM(CAST(ISNULL(part_plan_qty,0) AS float)) q
              FROM nx.plan_part_dtl WITH(NOLOCK) WHERE part_PLAN_YMD BETWEEN '{DF}' AND '{DT}'
             GROUP BY RTRIM(ISNULL(part_plan_ymd,''))) w
      FULL OUTER JOIN
           (SELECT RTRIM(ISNULL(PART_PLAN_YMD,'')) d, SUM(CAST(ISNULL(PART_PLAN_QTY,0) AS float)) q
              FROM PARTNER_ERP.dbo.PR_T_PLAN_PART_DTL WITH(NOLOCK) WHERE PART_PLAN_YMD BETWEEN '{DF}' AND '{DT}'
             GROUP BY RTRIM(ISNULL(PART_PLAN_YMD,''))) l ON l.d=w.d
     ORDER BY ISNULL(w.d,l.d)""")
    rows = cur.fetchall()
    bad = [r for r in rows if abs(float(r[3] or 0)) > 0.001]
    print(f'    일자 {len(rows)}개 · 수량 다른 일자 {len(bad)}개')
    for r in rows[:12]:
        d = float(r[3] or 0)
        print('      %s  웹 %10s / 레거 %10s  %s' % (
            r[0], format(float(r[1]), ',.0f'), format(float(r[2]), ',.0f'),
            (format(d, '+,.0f') if abs(d) > 0.001 else '=')))
    # 같은 키에서 당김일이 다른 건 (원인 특정용)
    cur.execute(f"""
    SELECT COUNT(*) FROM
      (SELECT RTRIM(work_order) wo, RTRIM(assy_item_code) a, RTRIM(ISNULL(item_code,'')) i,
              MIN(RTRIM(ISNULL(part_plan_ymd,''))) d
         FROM nx.plan_part_dtl WITH(NOLOCK) WHERE PLAN_YMD BETWEEN '{DF}' AND '{DT}'
        GROUP BY RTRIM(work_order), RTRIM(assy_item_code), RTRIM(ISNULL(item_code,''))) w
      JOIN
      (SELECT RTRIM(WORK_ORDER) wo, RTRIM(ASSY_ITEM_CODE) a, RTRIM(ISNULL(ITEM_CODE,'')) i,
              MIN(RTRIM(ISNULL(PART_PLAN_YMD,''))) d
         FROM PARTNER_ERP.dbo.PR_T_PLAN_PART_DTL WITH(NOLOCK) WHERE PLAN_YMD BETWEEN '{DF}' AND '{DT}'
        GROUP BY RTRIM(WORK_ORDER), RTRIM(ASSY_ITEM_CODE), RTRIM(ISNULL(ITEM_CODE,''))) l
        ON l.wo=w.wo AND l.a=w.a AND l.i=w.i
     WHERE w.d<>l.d""")
    n = int(cur.fetchone()[0] or 0)
    print(f'    ★같은 키인데 당김일이 다른 건: {n:,}건'
          + ('  = 당김 규칙 차이(총량이 같아도 화면 일자칸이 어긋난다)' if n else '  ✅'))
except Exception as e:
    print(f'    ★조회 실패 — {str(e)[:110]}')

# ── 7. 조달 오버레이 (웹 전용) ─────────────────────────────────────
print('\n[7] ⑤조달 오버레이 (웹 전용 — 레거시 대응 없음)')
n = n1("SELECT COUNT(*) FROM nx.plan_mat_source WITH(NOLOCK)")
q = f1("SELECT SUM(CAST(ISNULL(QTY,0) AS float)) FROM nx.plan_mat_source WITH(NOLOCK)")
m = n1("SELECT COUNT(*) FROM nx.plan_part_mat WITH(NOLOCK)")
print(f'    조달 {n:,}행 · 수량 {q:,.0f}   (자재소요 {m:,}행)')
if m and abs(n - m) > max(50, m * 0.05):
    print(f'    ⚠ 자재소요와 {n-m:+,}행 차이 — 조달 오버레이가 일부 자재를 놓쳤을 수 있다')

# ── 8. 요약 ────────────────────────────────────────────────────────
print('\n' + BAR)
print(' 판정 요령')
print('   · [3][4][5] 가 0 차이면 편성 정합 완료.')
print('   · [5] 만 차이나면 STEP7(자재소요) 문제. [4] 부터 차이면 STEP5/6 문제.')
print('   · 한 방향 쏠림 = 축(일자/제번) 오류 먼저 의심. [0] 편성 시점부터 확인할 것.')
print('   · [6] 은 운영 관점(발주처) — [5] 가 맞는데 [6] 이 틀리면 routing_edge 를 본다.')
print(BAR)
cn.close()
