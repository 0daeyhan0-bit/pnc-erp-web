# -*- coding: utf-8 -*-
"""품목마스터·BOM 미러 델타 동기화 — nx ← 라이브 (2026-09-01 신설)

왜 필요한가
  편성(STEP5/6/7)과 소요엔진은 **미러**(`nx.PR_M_ITEM` · `nx.PR_M_ITEM_BOM`)를 읽는다.
  라이브에 품목·BOM 이 새로 등록되면 미러가 따라가야 하는데, 당일 등록분은
  `r_delta_sync` 가 돌기 전까지 **비어 있다.** 그러면 편성이 그 코드를 못 찾아
  **상위에서 하위로 그냥 내려가 버린다**(전개가 한 단계 깊어짐).

    실측 2026-09-01 — `AJR30100102-19-1`('명진 SUB', in_cust 2306, 08:40 손진욱 등록)
      라이브 PR_M_ITEM 1 / 미러 0 / 클린 nx.item 0   ← 딱 1건
      라이브 BOM  AJR30100102 → AJR30100102-19-1 (260901~) + 그 아래 자식 10
      미러엔 그 링크가 없어 웹은 `-19-1` 을 건너뛰고 `MJU3907432x` 7종으로 전개했다.
      ⟹ 명진(2306) 자재소요가 제번당 7배로 부풀었다
         (6I2M03K2 +240 · 6I2M03VG +300 · 6J2M01UA +168 … 13제번, 총 +590)
      레거시는 마스터를 안 보고 `-19-1` 을 그대로 써서 정상이었다.

  ★`-19-1` 은 유령코드가 아니라 **명진 사급 SUB 발주단위**다(14종, 13종은 정상 등재).
    이걸 "레거시가 남긴 쓰레기" 로 오판하면 웹 버그를 정당화하게 된다.

★안전 원칙
  · 라이브는 **읽기만** 한다(CLAUDE.md §1-1). 쓰기는 nx 뿐.
  · `--apply` 없이는 조회만 한다(기본 dry-run).
  · 실행 전 백업 테이블에 원본을 남긴다.
  · **INSERT(신규분)만 한다.** UPDATE/DELETE 는 하지 않는다 —
    미러에 사람이 손댄 값이 있을 수 있고, 이 스크립트의 목적은 "당일 신규분이 빠져서
    편성이 틀리는 것" 을 막는 것이다. 값 정정은 `r_delta_sync` 의 몫.

사용
    python _schema/sync_item_bom_delta.py            # 조회만
    python _schema/sync_item_bom_delta.py --apply    # 실제 동기화
"""
import sys, os, io, argparse, datetime

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8',
                              errors='replace', line_buffering=True)
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, '..', 'PNC_ERP_Web', 'backend'))
sys.path.insert(0, os.path.join(_HERE, '..', '..', 'New_ERP'))

AP = argparse.ArgumentParser()
AP.add_argument('--apply', action='store_true', help='실제 동기화(없으면 조회만)')
ARG = AP.parse_args()

import pyodbc, db_client

CS = (f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};'
      f'DATABASE=PARTNER_ERP_TEST3;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}')
STAMP = datetime.datetime.now().strftime('%y%m%d_%H%M')

cn = pyodbc.connect(CS, autocommit=False)
cur = cn.cursor()

print('=' * 74)
print(' 품목·BOM 미러 델타 동기화  ' + ('[APPLY]' if ARG.apply else '[DRY-RUN — 조회만]'))
print('=' * 74)


def n1(q, *a):
    cur.execute(q, *a)
    r = cur.fetchone()
    return int(r[0] or 0) if r else 0


def cols_of(db, sch, tb):
    cur.execute(f"""SELECT COLUMN_NAME FROM {db}.INFORMATION_SCHEMA.COLUMNS
                     WHERE TABLE_SCHEMA=? AND TABLE_NAME=? ORDER BY ORDINAL_POSITION""", sch, tb)
    return [r[0] for r in cur.fetchall()]


# ── 대상 3개: (미러, 라이브, 키조건, 라벨) ──
JOBS = [
    ('nx.PR_M_ITEM', 'PARTNER_ERP.dbo.PR_M_ITEM',
     "RTRIM(m.ITEM_CODE)=RTRIM(l.ITEM_CODE)", '품목마스터', ('PR_M_ITEM',)),
    ('nx.PR_M_ITEM_BOM', 'PARTNER_ERP.dbo.PR_M_ITEM_BOM',
     "RTRIM(m.ITEM_CODE)=RTRIM(l.ITEM_CODE) AND RTRIM(m.MAT_CODE)=RTRIM(l.MAT_CODE)"
     " AND ISNULL(m.BOM_SEQ,0)=ISNULL(l.BOM_SEQ,0)", 'BOM', ('PR_M_ITEM_BOM',)),
]

print('\n① 현황')
todo = []
for mirr, live, key, label, _ in JOBS:
    a = n1(f'SELECT COUNT(*) FROM {live} WITH(NOLOCK)')
    b = n1(f'SELECT COUNT(*) FROM {mirr} WITH(NOLOCK)')
    miss = n1(f"""SELECT COUNT(*) FROM {live} l WITH(NOLOCK)
                   WHERE NOT EXISTS(SELECT 1 FROM {mirr} m WITH(NOLOCK) WHERE {key})""")
    print(f'   {label:8s} 라이브 {a:>8,} / 미러 {b:>8,}   ★라이브에만 {miss:,}')
    todo.append(miss)

print('\n② 라이브에만 있는 것 — 무엇인가')
cur.execute("""SELECT RTRIM(l.ITEM_CODE), ISNULL(RTRIM(l.ITEM_DESC),''), ISNULL(RTRIM(l.IN_CUST_CODE),''),
                      CONVERT(varchar(19),l.INSERT_DATETIME,120), ISNULL(RTRIM(l.INSERT_USER_ID),'')
                 FROM PARTNER_ERP.dbo.PR_M_ITEM l WITH(NOLOCK)
                WHERE NOT EXISTS(SELECT 1 FROM nx.PR_M_ITEM m WITH(NOLOCK)
                                  WHERE RTRIM(m.ITEM_CODE)=RTRIM(l.ITEM_CODE))
                ORDER BY l.INSERT_DATETIME DESC""")
rows = cur.fetchall()
print(f'   품목 {len(rows)}건')
for r in rows[:20]:
    print(f"     {r[0]:22s} {r[1][:22]:24s} 매입처 {r[2]:6s} {r[3]} {r[4]}")

cur.execute("""SELECT TOP 20 RTRIM(l.ITEM_CODE), RTRIM(l.MAT_CODE), CAST(ISNULL(l.USE_QTY,0) AS float),
                      RTRIM(ISNULL(l.FROM_APPLY_YMD,'')), CONVERT(varchar(19),l.INSERT_DATETIME,120)
                 FROM PARTNER_ERP.dbo.PR_M_ITEM_BOM l WITH(NOLOCK)
                WHERE NOT EXISTS(SELECT 1 FROM nx.PR_M_ITEM_BOM m WITH(NOLOCK)
                                  WHERE RTRIM(m.ITEM_CODE)=RTRIM(l.ITEM_CODE)
                                    AND RTRIM(m.MAT_CODE)=RTRIM(l.MAT_CODE)
                                    AND ISNULL(m.BOM_SEQ,0)=ISNULL(l.BOM_SEQ,0))
                ORDER BY l.INSERT_DATETIME DESC""")
brows = cur.fetchall()
print(f'\n   BOM 링크 {todo[1]}건 (앞 20)')
for r in brows:
    print(f"     {r[0]:22s} → {r[1]:22s} x{r[2]:<8} 적용 {r[3]} {r[4]}")

if not any(todo):
    print('\n   ✅ 이미 동기 상태입니다.')
    cn.close(); sys.exit(0)

if not ARG.apply:
    print('\n※ DRY-RUN 입니다. 실제로 동기화하려면 --apply 를 붙이세요.')
    cn.close(); sys.exit(0)

print('\n③ 동기화 실행')
for mirr, live, key, label, (tb,) in JOBS:
    mcols = cols_of('PARTNER_ERP_TEST3', 'nx', tb)
    lcols = cols_of('PARTNER_ERP', 'dbo', tb)
    use = [c for c in mcols if c in lcols]          # 양쪽에 다 있는 컬럼만
    bk = f'nx.bk_{tb.lower()}_{STAMP}'
    cur.execute(f'SELECT * INTO {bk} FROM {mirr}')
    print(f'   [{label}] 백업 {bk} ({cur.rowcount:,}행) · 복사컬럼 {len(use)}/{len(mcols)}')
    cl = ",".join(f'[{c}]' for c in use)
    cur.execute(f"""INSERT INTO {mirr}({cl})
                    SELECT {",".join(f'l.[{c}]' for c in use)}
                      FROM {live} l WITH(NOLOCK)
                     WHERE NOT EXISTS(SELECT 1 FROM {mirr} m WITH(NOLOCK) WHERE {key})""")
    print(f'   [{label}] 신규 {cur.rowcount:,}행')

cn.commit()

print('\n④ 검증')
for mirr, live, key, label, _ in JOBS:
    left = n1(f"""SELECT COUNT(*) FROM {live} l WITH(NOLOCK)
                   WHERE NOT EXISTS(SELECT 1 FROM {mirr} m WITH(NOLOCK) WHERE {key})""")
    print(f'   {label:8s} 잔여 누락 {left}   ' + ('✅' if left == 0 else '★남음'))

print('\n   ⚠ 편성(④파트별 → ⑤자재소요)을 다시 돌려야 계획에 반영됩니다.')
cn.close()
