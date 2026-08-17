# -*- coding: utf-8 -*-
"""★컷오버 델타 sync (r_bulk_copy의 델타판) — 이관량 최소화.
방식:
  · 마스터(_M_/기타)  = 전체 재복사(DROP+SELECT INTO). 행수스킵 없음 → UPDATE 반영. (BLOB도 전체)
  · 거래로그(_T_·날짜컬럼) = 최근 WINDOW_DAYS일 윈도우 재복사(nx 구간 DELETE → 라이브 구간 INSERT).
  · 제외(EXCLUDE)     = 우리 생성분(nx>라이브) — 라이브 복사 안 함(소실방지).
  · 날짜컬럼 없는 _T_  = 전체 재복사(윈도우 불가) — [full-fallback]로 표시.
DRY 기본(계획+행수만 출력, 쓰기 없음). 실행: python r_delta_sync.py --commit
읽기전용 소스=PARTNER_ERP, 쓰기 대상=PARTNER_ERP_TEST3.nx 미러."""
import sys, io, datetime, time
sys.path.insert(0, r'd:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP')
import pyodbc, db_client
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
DRY = ('--commit' not in sys.argv)
WINDOW_DAYS = 30

# 제외: 라이브 소스 없는 nx전용 테이블만(자동감지). 계획 미러는 제외 아님(순수미러=갱신대상).
EXCLUDE = set()
# 강제 전체복사: 라이브가 재생성(삭제+삽입)하는 계획테이블 — 윈도우는 삭제분 못잡음, 전체복사로 정확.
# (백엔드는 이 미러들을 읽기만 함/우리 계획데이터는 nx.plan_part_mat 등 별도이름 — 검증완료 2026-08-14)
FORCE_FULL = {'PR_T_PLAN_PART_MAT','PR_T_PLAN_PART_DTL','PR_T_PLAN_PART_COPY',
              'PR_T_PLAN_PART_DTL_FOR_CUST','PR_T_PLAN_DTL','SA_T_PLAN_DTL'}

cutoff = (datetime.date.today() - datetime.timedelta(days=WINDOW_DAYS)).strftime('%y%m%d')  # YYMMDD

cn = pyodbc.connect(f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};DATABASE=PARTNER_ERP_TEST3;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}', autocommit=False)
c = cn.cursor()

def tbl_exists(t):
    return c.execute("SELECT COUNT(*) FROM sys.tables WHERE schema_id=SCHEMA_ID('nx') AND name=?", t).fetchone()[0]

def do_full(t):
    """마스터/계획/날짜없음 = 전체 재복사. TRUNCATE+INSERT(원자적·리더안전). 스키마드리프트/부재는 DROP+SELECT INTO 폴백."""
    if tbl_exists(t):
        try:
            c.execute(f"TRUNCATE TABLE nx.{t}")
            c.execute(f"INSERT INTO nx.{t} SELECT * FROM PARTNER_ERP.dbo.{t}")
            cn.commit(); return
        except Exception:
            cn.rollback()
            c.execute(f"DROP TABLE nx.{t}")
    c.execute(f"SELECT * INTO nx.{t} FROM PARTNER_ERP.dbo.{t}")
    cn.commit()

def do_window(t, dc, live_cnt=None):
    """거래 = 최근 cutoff 구간만 DELETE+INSERT(원자적). 실패/윈도우밖 드리프트면 전체복사 자가치유."""
    try:
        c.execute(f"DELETE FROM nx.{t} WHERE {dc} >= ?", cutoff)
        c.execute(f"INSERT INTO nx.{t} SELECT * FROM PARTNER_ERP.dbo.{t} WHERE {dc} >= ?", cutoff)
        cn.commit()
        newc = c.execute(f"SELECT COUNT(*) FROM nx.{t}").fetchone()[0]; cn.commit()
        if isinstance(live_cnt, int) and newc != live_cnt:
            do_full(t)   # 윈도우 밖 백데이트 수정/삭제 드리프트 → 전체복사로 정합
    except Exception:
        cn.rollback(); do_full(t)

def cnt(sql):
    try: return c.execute(sql).fetchone()[0]
    except Exception as e: return 'ERR:'+str(e)[:24]

# nx 미러 목록(legacy형)
c.execute("""SELECT t.name FROM sys.tables t JOIN sys.schemas s ON t.schema_id=s.schema_id
 WHERE s.name='nx' AND (t.name LIKE 'PU[_]%' OR t.name LIKE 'SA[_]%' OR t.name LIKE 'PR[_]%'
   OR t.name LIKE 'CM[_]%' OR t.name LIKE 'QA[_]%' OR t.name LIKE 'CS[_]%' OR t.name LIKE 'HR[_]%')
 AND t.name NOT LIKE '%[_]bak[_]%' ORDER BY t.name""")
TABLES = [r[0] for r in c.fetchall()]

def cols(t):
    c.execute("""SELECT COLUMN_NAME, DATA_TYPE FROM PARTNER_ERP.INFORMATION_SCHEMA.COLUMNS
      WHERE TABLE_SCHEMA='dbo' AND TABLE_NAME=? ORDER BY ORDINAL_POSITION""", t)
    return [(r[0], r[1].lower()) for r in c.fetchall()]

DATE_PRI = ['MAINT_YMD','SALE_YMD','PROD_YMD','RECEIVING_YMD','PLAN_YMD','REQ_YMD','CUTTING_YMD',
            'PRINT_YMD','WORK_YMD','INDI_YMD','OUTPUT_YMD','MOVE_YMD']
def pick_date(cl):
    names = [cn0 for cn0, dt in cl]
    for p in DATE_PRI:
        if p in names: return p
    # 일반 패턴: 이름에 YMD 포함 & 문자형(YYMMDD)
    for cn0, dt in cl:
        if 'YMD' in cn0.upper() and dt in ('char','varchar','nvarchar','nchar'): return cn0
    return None
def has_blob(cl):
    return any(dt in ('image','varbinary','text','ntext') for _, dt in cl)

def classify(t):
    cl = cols(t)
    if not cl: return ('nx전용(소스없음)', 'skip', None)   # 라이브에 없는 테이블=우리 전용 → 복사 안 함
    if t in EXCLUDE: return ('제외', 'exclude', None)
    if t in FORCE_FULL: return ('계획-전체재복사', 'full', None)   # 재생성형 → 전체복사로 정확 동기화
    blob = has_blob(cl)
    is_tx = '_T_' in t.upper()
    if is_tx:
        dc = pick_date(cl)
        if dc: return ('거래-윈도우', 'tx', dc)
        return ('거래-전체(날짜없음)', 'full', None)
    return ('마스터'+('·BLOB' if blob else ''), 'full', None)

print(f"=== 컷오버 델타 sync 계획 (WINDOW={WINDOW_DAYS}일, cutoff>={cutoff}) {'[DRY]' if DRY else '[COMMIT]'} ===")
print(f"미러 {len(TABLES)}개 · 소스 PARTNER_ERP → nx\n")
print('%-32s %-16s %11s %11s %11s'%('테이블','방식','nx건수','라이브건수','옮길행'))
print('-'*86)
tot_move = 0
plan = []
RESULT = []
for t in sorted(TABLES):
    label, mode, dc = classify(t)
    nxc = cnt(f'SELECT COUNT(*) FROM nx.{t}')
    lvc = cnt(f'SELECT COUNT(*) FROM PARTNER_ERP.dbo.{t}')
    if mode == 'skip':
        move = 0; note = 'nx전용-스킵'
    elif mode == 'exclude':
        move = 0; note = '복사안함'
    elif mode == 'tx':
        # 윈도우: 라이브 cutoff 이후 행 = INSERT 대상(=옮길행). nx 동구간은 DELETE.
        move = cnt(f"SELECT COUNT(*) FROM PARTNER_ERP.dbo.{t} WHERE {dc} >= '{cutoff}'")
        note = f'{dc}>={cutoff}'
    else:  # full
        move = lvc if isinstance(lvc, int) else 0
        note = '전체재복사'
    if isinstance(move, int): tot_move += move
    plan.append((t, mode, dc))
    res = ''
    if not DRY and mode in ('tx', 'full'):
        t0 = time.time()
        try:
            if mode == 'tx': do_window(t, dc, lvc if isinstance(lvc, int) else None)
            else: do_full(t)
            newc = c.execute(f"SELECT COUNT(*) FROM nx.{t}").fetchone()[0]; cn.commit()
            ok = (newc == lvc) if isinstance(lvc, int) else True
            res = f"→ nx {newc:,} {'✔' if ok else '⚠차이'} {time.time()-t0:.1f}s"
            RESULT.append((t, 'OK' if ok else 'DIFF', newc))
        except Exception as e:
            cn.rollback(); res = f"✖ {str(e)[:44]}"; RESULT.append((t, 'FAIL', str(e)[:60]))
    print('%-30s %-15s %10s %10s %9s %s'%(
        t[:30], label,
        format(nxc,',') if isinstance(nxc,int) else nxc,
        format(lvc,',') if isinstance(lvc,int) else lvc,
        format(move,',') if isinstance(move,int) else move, note if DRY else res))
print('-'*86)
print(f'옮길 행 합계 ≈ {format(tot_move,",")}행 (거래=윈도우분만, 마스터=전체, 제외=0)')
if not DRY:
    okn = sum(1 for r in RESULT if r[1]=='OK'); dfn=[r for r in RESULT if r[1]=='DIFF']; fl=[r for r in RESULT if r[1]=='FAIL']
    print(f'\n[COMMIT 결과] 성공 {okn} · 차이 {len(dfn)} · 실패 {len(fl)}')
    for r in dfn: print('  ⚠차이', r[0], '→ nx', r[2])
    for r in fl: print('  ✖실패', r[0], r[2])
print()

# 계획 미러(FORCE_FULL) 갱신 전후: 순수미러라 라이브로 맞춤(stale 해소)
print('=== 계획 미러 전체재복사 대상 (순수미러=백엔드 읽기전용, nx.plan_* 별개) ===')
for t in sorted(FORCE_FULL):
    nxc = cnt(f'SELECT COUNT(*) FROM nx.{t}'); lvc = cnt(f'SELECT COUNT(*) FROM PARTNER_ERP.dbo.{t}')
    print(f'  {t:30s} nx {nxc}(stale) → live {lvc} 로 갱신')
cn.close()
