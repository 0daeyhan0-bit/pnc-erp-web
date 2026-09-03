# -*- coding: utf-8 -*-
"""★9단계 전 구간 계획수량 일자별 대사 (읽기 전용)
   순서: 계획업로드 → 파트별410 → 준비(키팅) → 가공이동580 → 가공전표
         → 자재세트입고130 → 자재입고010 → 영업계획050 → 출하실적040
   각 화면을 웹 API 로 부르고, 가능한 곳은 레거시 소스(src=live/nx)와 같이 부른다.
"""
import sys, io, os, collections, traceback, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
B = r'c:\Users\박근민\Desktop\NEW_ERP_1\PNC_ERP_Web\backend'
sys.path.insert(0, B); sys.path.insert(0, os.path.join(B, 'routers'))
sys.path.insert(0, r'c:\Users\박근민\Desktop\New_ERP')
os.chdir(B)

YMD = '260902'; YMD_D = '2026-09-02'
SEP = '─' * 96

def hdr(t):
    print('\n' + '═' * 96); print(t); print('═' * 96)

def days_of(rows, keyf):
    d = collections.Counter()
    for x in rows:
        for y, v in (keyf(x) or {}).items():
            d[str(y)] += float(v or 0)
    return d

def show(nm, d, tot=None):
    ks = sorted(d)
    s = ' '.join(f'{k[-4:]}={d[k]:,.0f}' for k in ks[:8])
    print(f'   {nm:22s} 합 {sum(d.values()):>12,.0f}   {s}')

def cmp2(nmA, dA, nmB, dB):
    ks = sorted(set(dA) | set(dB))
    print(f'   {"일자":>8s} {nmA:>14s} {nmB:>14s} {"차":>12s}')
    ok = ng = 0
    for k in ks:
        a, b = dA.get(k, 0), dB.get(k, 0)
        m = '✅' if abs(a-b) < 0.5 else '❌'
        ok += (m == '✅'); ng += (m == '❌')
        print(f'   {k:>8s} {a:>14,.0f} {b:>14,.0f} {b-a:>+12,.0f} {m}')
    ta, tb = sum(dA.values()), sum(dB.values())
    m = '✅' if abs(ta-tb) < 0.5 else '❌'
    print(f'   {"합계":>8s} {ta:>14,.0f} {tb:>14,.0f} {tb-ta:>+12,.0f} {m}')
    return ok, ng

RESULT = []
def rec(step, nm, verdict, note=''):
    RESULT.append((step, nm, verdict, note))

# ════════════════════════════════════════════════════════════
hdr('① 계획업로드 원본 — nx.plan_dtl vs 라이브 PR_T_PLAN_DTL')
import pyodbc, db_client
def C(db):
    return pyodbc.connect(f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};'
                          f'DATABASE={db};UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}')
live = C('PARTNER_ERP').cursor(); nxc = C('PARTNER_ERP_TEST3').cursor()
F, T = '260902', '260907'
try:
    live.execute(f"""SELECT PLAN_YMD, SUM(CAST(PLAN_QTY AS float)) FROM PR_T_PLAN_DTL WITH(NOLOCK)
                      WHERE PLAN_YMD BETWEEN '{F}' AND '{T}' GROUP BY PLAN_YMD""")
    dL = {str(r[0]): float(r[1] or 0) for r in live.fetchall()}
    nxc.execute(f"""SELECT PLAN_YMD, SUM(CAST(PLAN_QTY AS float)) FROM nx.plan_dtl WITH(NOLOCK)
                     WHERE PLAN_YMD BETWEEN '{F}' AND '{T}' GROUP BY PLAN_YMD""")
    dW = {str(r[0]): float(r[1] or 0) for r in nxc.fetchall()}
    ok, ng = cmp2('레거시', dL, '웹', dW)
    rec('①', '계획업로드 원본', 'FAIL' if ng else 'PASS', f'일자 {ok}일치/{ng}불일치')
    print('\n   ※레거시는 PLAN_YMD=당김후. ORG 기준으로도 비교:')
    live.execute(f"""SELECT ISNULL(NULLIF(ORG_PLAN_YMD,''),PLAN_YMD) y, SUM(CAST(PLAN_QTY AS float))
                       FROM PR_T_PLAN_DTL WITH(NOLOCK)
                      WHERE ISNULL(NULLIF(ORG_PLAN_YMD,''),PLAN_YMD) BETWEEN '{F}' AND '{T}'
                      GROUP BY ISNULL(NULLIF(ORG_PLAN_YMD,''),PLAN_YMD)""")
    dO = {str(r[0]): float(r[1] or 0) for r in live.fetchall()}
    cmp2('레거시ORG', dO, '웹', dW)
except Exception as e:
    print('   ERR', str(e)[:200]); rec('①', '계획업로드 원본', 'ERR', str(e)[:80])

# ════════════════════════════════════════════════════════════
hdr('② 파트별 생산계획현황 410 — src=new vs src=live')
try:
    from routers import kitting
    t0 = time.time()
    rn = kitting.plan_part410(from_ymd=YMD, gigan=4, wc='', part='', line='', assy='',
                              jado='', wo='', view='전체', unfin='전체', src='new',
                              wh_part='IS0001', limit=30000)
    rl = kitting.plan_part410(from_ymd=YMD, gigan=4, wc='', part='', line='', assy='',
                              jado='', wo='', view='전체', unfin='전체', src='live',
                              wh_part='IS0001', limit=30000)
    print(f'   ({time.time()-t0:.0f}s)')
    for nm, r in (('new', rn), ('live', rl)):
        rows = r.get('rows') or []
        print(f'   {nm}: {len(rows)}행 · 키 {sorted(rows[0].keys())[:14] if rows else "?"}')
    kf = lambda x: x.get('days') or x.get('day') or {}
    dN, dL2 = days_of(rn.get('rows') or [], kf), days_of(rl.get('rows') or [], kf)
    ok, ng = cmp2('레거시(live)', dL2, '웹(new)', dN)
    rec('②', '파트별410', 'FAIL' if ng else 'PASS', f'{ok}/{ok+ng}')
except Exception as e:
    traceback.print_exc(); rec('②', '파트별410', 'ERR', str(e)[:80])
