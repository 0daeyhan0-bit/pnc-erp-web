# -*- coding: utf-8 -*-
"""9단계 대사 ③~⑨ (읽기 전용)"""
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
def rec(s, n, v, note=''): R.append((s, n, v, note));

# ③ 준비(키팅)
hdr('③ 생산준비/준비실적처리 (키팅) — src=new vs live')
try:
    from routers import kitting
    t0 = time.time()
    kn = kitting.kitting_grid(from_ymd=YMD, to_ymd='', wc='', part='', pgroup='', line='',
                              assy='', jado='', gigan=4, src='new')
    kl = kitting.kitting_grid(from_ymd=YMD, to_ymd='', wc='', part='', pgroup='', line='',
                              assy='', jado='', gigan=4, src='live')
    print(f'   ({time.time()-t0:.0f}s)  new {len(kn.get("rows") or [])}행 / live {len(kl.get("rows") or [])}행')
    rr = (kn.get('rows') or [])
    if rr: print(f'   키: {sorted(rr[0].keys())[:16]}')
    kf = lambda x: x.get('days') or x.get('day') or {}
    ok, ng = cmp2('레거시', days_of(kl.get('rows') or [], kf), '웹', days_of(kn.get('rows') or [], kf))
    rec('③', '준비/키팅', 'FAIL' if ng else 'PASS', f'{ok}/{ok+ng}')
except Exception as e:
    traceback.print_exc(); rec('③', '준비/키팅', 'ERR', str(e)[:80])

# ④ 가공이동 580
hdr('④ 가공창고 이동계획 580 — src=new vs nx(레거시SP)')
try:
    from routers import gagongmove
    gn = gagongmove.gagong_move580(from_ymd=YMD, to_ymd='260907', wc='P2', pr_part='%',
                                   pu_part='IS0001', sagub='', item='', part='',
                                   mv='전체', src='new', limit=8000)
    gl = gagongmove.gagong_move580(from_ymd=YMD, to_ymd='260907', wc='P2', pr_part='%',
                                   pu_part='IS0001', sagub='', item='', part='',
                                   mv='전체', src='nx', limit=8000)
    print(f'   new {len(gn.get("rows") or [])}행 / nx {len(gl.get("rows") or [])}행')
    kf = lambda x: x.get('days') or {}
    ok, ng = cmp2('레거시SP', days_of(gl.get('rows') or [], kf), '웹계획', days_of(gn.get('rows') or [], kf))
    # 당일이전
    pa = sum(float(x.get('prior') or 0) for x in (gl.get('rows') or []))
    pb = sum(float(x.get('prior') or 0) for x in (gn.get('rows') or []))
    print(f'   당일이전  레거시 {pa:,.0f} / 웹 {pb:,.0f}  {"✅" if abs(pa-pb)<0.5 else "❌"}')
    rec('④', '가공이동580', 'FAIL' if ng else 'PASS', f'{ok}/{ok+ng}')
except Exception as e:
    traceback.print_exc(); rec('④', '가공이동580', 'ERR', str(e)[:80])

# ⑤ 가공생산진척 420
hdr('⑤ 가공전표/가공생산진척 420 — plansrc=new vs nx')
try:
    from routers import gagong
    an = gagong.gagong_prog420nx(from_ymd=YMD, gigan=4, wc='P2', item='', jado='',
                                 unfin='전체', plansrc='new', limit=20000)
    al = gagong.gagong_prog420nx(from_ymd=YMD, gigan=4, wc='P2', item='', jado='',
                                 unfin='전체', plansrc='nx', limit=20000)
    print(f'   new {len(an.get("rows") or [])}행 / nx {len(al.get("rows") or [])}행')
    rr = an.get('rows') or []
    if rr: print(f'   키: {sorted(rr[0].keys())[:16]}')
    kf = lambda x: x.get('days') or x.get('day') or {}
    ok, ng = cmp2('nx(미러)', days_of(al.get('rows') or [], kf), '웹계획', days_of(an.get('rows') or [], kf))
    rec('⑤', '가공진척420', 'FAIL' if ng else 'PASS', f'{ok}/{ok+ng}')
except Exception as e:
    traceback.print_exc(); rec('⑤', '가공진척420', 'ERR', str(e)[:80])

print('\n\n■ 중간 요약')
for s, n, v, note in R:
    print(f'   {s} {n:20s} {v:5s} {note}')
