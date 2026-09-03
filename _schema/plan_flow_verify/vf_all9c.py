# -*- coding: utf-8 -*-
"""9단계 대사 ③(재시도) + ⑥~⑨ (읽기 전용)"""
import sys, io, os, collections, traceback, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
B = r'c:\Users\박근민\Desktop\NEW_ERP_1\PNC_ERP_Web\backend'
sys.path.insert(0, B); sys.path.insert(0, os.path.join(B, 'routers'))
sys.path.insert(0, r'c:\Users\박근민\Desktop\New_ERP')
os.chdir(B)
YMD, YMD_D = '260902', '2026-09-02'

def hdr(t):
    print('\n' + '═' * 96); print(t); print('═' * 96)
def days_of(rows, keyf):
    d = collections.Counter()
    for x in rows:
        for y, v in (keyf(x) or {}).items(): d[str(y)] += float(v or 0)
    return d
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
    print(f'   {"합계":>8s} {ta:>14,.0f} {tb:>14,.0f} {tb-ta:>+12,.0f} '
          f'{"✅" if abs(ta-tb)<0.5 else "❌"}')
    return ok, ng
R = []
def rec(s, n, v, note=''): R.append((s, n, v, note))

# ③ 키팅 재시도 (wh_part 명시)
hdr('③ 생산준비/준비실적처리 (키팅)')
try:
    from routers import kitting
    kw = dict(from_ymd=YMD, to_ymd='', wc='', part='', pgroup='', line='',
              assy='', jado='', gigan=4, wh_part='IS0001', limit=30000)
    kn = kitting.kitting_grid(src='new', **kw)
    kl = kitting.kitting_grid(src='live', **kw)
    print(f'   new {len(kn.get("rows") or [])}행 / live {len(kl.get("rows") or [])}행')
    rr = kn.get('rows') or []
    if rr: print(f'   키: {sorted(rr[0].keys())[:18]}')
    kf = lambda x: x.get('days') or x.get('day') or {}
    ok, ng = cmp2('레거시', days_of(kl.get('rows') or [], kf), '웹', days_of(kn.get('rows') or [], kf))
    rec('③', '준비/키팅', 'FAIL' if ng else 'PASS', f'{ok}/{ok+ng}')
except Exception as e:
    traceback.print_exc(); rec('③', '준비/키팅', 'ERR', str(e)[:80])

# ⑥ 자재세트입고 130 — 3개 업체
hdr('⑥ 자재세트입고현황 130 — 대원산업/미래정밀/케이비')
try:
    from routers import setinstat
    CUSTS = [('2148', '대원산업'), ('2096', '미래정밀'), ('2266', '케이비')]
    for cc, cn_ in CUSTS:
        r = setinstat.setinstat_list(base_ymd=YMD, days=4, jcust=cc, dcust='',
                                     line='', wo='', doban='', jadoban='')
        rows = r.get('rows') or []
        d = days_of(rows, lambda x: x.get('day') or {})
        print(f'   [{cn_}] {len(rows)}행 · 계획합 {sum(d.values()):,.0f}')
        print('      ' + ' '.join(f'{k[-4:]}={d[k]:,.0f}' for k in sorted(d)))
    rec('⑥', '세트입고130', 'INFO', '레거시 대사는 화면 캡처 필요')
except Exception as e:
    traceback.print_exc(); rec('⑥', '세트입고130', 'ERR', str(e)[:80])

# ⑦ 자재입고 010 — 그린산업 2곳
hdr('⑦ 자재입고진행현황 010 — 그린산업 김해(2345) / 그린산업')
try:
    from routers import matinput
    for cc in ('2345', ''):
        r = matinput.matinput_list(base_ymd=YMD_D, days=4, gubun='sum', cust=cc,
                                   line='', wo='', doban='', jadoban='', limit=20000)
        rows = r.get('rows') or []
        td = r.get('tot_day') or {}
        print(f'   [cust={cc or "전체"}] {len(rows)}행 · 자재수량 {r.get("tot_qty"):,.0f} · LOT {r.get("tot_lot"):,.0f}')
        print('      ' + ' '.join(f'{k[-4:]}={v:,.0f}' for k, v in sorted(td.items())))
    rec('⑦', '자재입고010', 'INFO', 'LOT 차이 별건')
except Exception as e:
    traceback.print_exc(); rec('⑦', '자재입고010', 'ERR', str(e)[:80])

# ⑧ 영업계획 050
hdr('⑧ 영업계획현황 050 — src=nx(웹정본) vs live(레거시)')
try:
    from routers import salesplan
    sn = salesplan.salesplan(from_ymd=YMD, days=7, gubun='2', cust='', line='',
                             model='', wo='', item='', src='nx')
    sl = salesplan.salesplan(from_ymd=YMD, days=7, gubun='2', cust='', line='',
                             model='', wo='', item='', src='live')
    print(f'   nx {len(sn.get("rows") or [])}행 / live {len(sl.get("rows") or [])}행')
    rr = sn.get('rows') or []
    if rr: print(f'   키: {sorted(rr[0].keys())[:18]}')
    kf = lambda x: x.get('days') or x.get('day') or {}
    ok, ng = cmp2('레거시', days_of(sl.get('rows') or [], kf), '웹', days_of(sn.get('rows') or [], kf))
    rec('⑧', '영업계획050', 'FAIL' if ng else 'PASS', f'{ok}/{ok+ng}')
except Exception as e:
    traceback.print_exc(); rec('⑧', '영업계획050', 'ERR', str(e)[:80])

# ⑨ 출하실적 040
hdr('⑨ 출하실적등록 040 — src=new vs live')
try:
    from routers import sales
    an = sales.sale040_grid(from_ymd=YMD, gigan=4, line='', wo='', item='', src='new', limit=20000)
    al = sales.sale040_grid(from_ymd=YMD, gigan=4, line='', wo='', item='', src='live', limit=20000)
    print(f'   new {len(an.get("rows") or [])}행 / live {len(al.get("rows") or [])}행')
    rr = an.get('rows') or []
    if rr: print(f'   키: {sorted(rr[0].keys())[:18]}')
    kf = lambda x: x.get('days') or x.get('day') or {}
    dN, dL = days_of(an.get('rows') or [], kf), days_of(al.get('rows') or [], kf)
    if not dN and not dL:
        # days 가 없으면 수량컬럼 합으로
        for k in ('plan_qty', 'plan', 'qty', 'lot'):
            if rr and k in rr[0]:
                a = sum(float(x.get(k) or 0) for x in (al.get('rows') or []))
                b = sum(float(x.get(k) or 0) for x in (an.get('rows') or []))
                print(f'   {k}: 레거시 {a:,.0f} / 웹 {b:,.0f} 차 {b-a:+,.0f}')
        rec('⑨', '출하040', 'INFO', 'days 없음 — 컬럼합 비교')
    else:
        ok, ng = cmp2('레거시', dL, '웹', dN)
        rec('⑨', '출하040', 'FAIL' if ng else 'PASS', f'{ok}/{ok+ng}')
except Exception as e:
    traceback.print_exc(); rec('⑨', '출하040', 'ERR', str(e)[:80])

print('\n\n■ 요약')
for s, n, v, note in R:
    print(f'   {s} {n:20s} {v:5s} {note}')
