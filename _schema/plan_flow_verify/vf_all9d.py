# -*- coding: utf-8 -*-
"""③ 키팅 재시도(전 인자 명시) + ⑤420·⑧050·⑨040 차이 상세"""
import sys, io, os, collections, traceback, inspect
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
B = r'c:\Users\박근민\Desktop\NEW_ERP_1\PNC_ERP_Web\backend'
sys.path.insert(0, B); sys.path.insert(0, os.path.join(B, 'routers'))
sys.path.insert(0, r'c:\Users\박근민\Desktop\New_ERP')
os.chdir(B)
YMD = '260902'

def hdr(t): print('\n' + '═' * 96); print(t); print('═' * 96)
def days_of(rows, kf):
    d = collections.Counter()
    for x in rows:
        for y, v in (kf(x) or {}).items(): d[str(y)] += float(v or 0)
    return d
def cmp2(nA, dA, nB, dB):
    ks = sorted(set(dA) | set(dB)); ok = ng = 0
    print(f'   {"일자":>8s} {nA:>14s} {nB:>14s} {"차":>12s}')
    for k in ks:
        a, b = dA.get(k, 0), dB.get(k, 0)
        m = '✅' if abs(a-b) < 0.5 else '❌'; ok += (m == '✅'); ng += (m == '❌')
        print(f'   {k:>8s} {a:>14,.0f} {b:>14,.0f} {b-a:>+12,.0f} {m}')
    ta, tb = sum(dA.values()), sum(dB.values())
    print(f'   {"합계":>8s} {ta:>14,.0f} {tb:>14,.0f} {tb-ta:>+12,.0f} {"✅" if abs(ta-tb)<0.5 else "❌"}')
    return ok, ng

# ③ 키팅 — 시그니처 기본값을 전부 채운다
hdr('③ 생산준비/준비실적처리 (키팅)')
try:
    from routers import kitting
    sig = inspect.signature(kitting.kitting_grid)
    kw = {}
    for n, p in sig.parameters.items():
        d = p.default
        v = getattr(d, 'default', d)          # Query 객체면 .default
        kw[n] = v
    kw.update(from_ymd=YMD, gigan=4)
    print(f'   인자: {kw}')
    kn = dict(kw); kn['src'] = 'new'
    kl = dict(kw); kl['src'] = 'live'
    rn = kitting.kitting_grid(**kn)
    rl = kitting.kitting_grid(**kl)
    print(f'   new {len(rn.get("rows") or [])}행 / live {len(rl.get("rows") or [])}행')
    rr = rn.get('rows') or []
    if rr: print(f'   키: {sorted(rr[0].keys())[:20]}')
    kf = lambda x: x.get('days') or x.get('day') or {}
    cmp2('레거시', days_of(rl.get('rows') or [], kf), '웹', days_of(rn.get('rows') or [], kf))
except Exception as e:
    traceback.print_exc()

# ⑤ 420 차이 상세
hdr('⑤ 420 가공진척 — 행 차이(736 vs 777) 어디서')
try:
    from routers import gagong
    an = gagong.gagong_prog420nx(from_ymd=YMD, gigan=4, wc='P2', item='', jado='',
                                 unfin='전체', plansrc='new', limit=20000)
    al = gagong.gagong_prog420nx(from_ymd=YMD, gigan=4, wc='P2', item='', jado='',
                                 unfin='전체', plansrc='nx', limit=20000)
    def idx(rows):
        d = {}
        for x in rows:
            k = (str(x.get('assy') or '').strip(), str(x.get('jado') or '').strip())
            d[k] = d.get(k, 0) + sum(float(v or 0) for v in (x.get('days') or {}).values())
        return d
    IA, IB = idx(al.get('rows') or []), idx(an.get('rows') or [])
    onlyA = sorted(set(IA) - set(IB)); onlyB = sorted(set(IB) - set(IA))
    print(f'   nx에만 {len(onlyA)}조합 (합 {sum(IA[k] for k in onlyA):,.0f})')
    for k in onlyA[:8]: print(f'      {k[0]:20s} {k[1]:20s} {IA[k]:>9,.0f}')
    print(f'   new에만 {len(onlyB)}조합 (합 {sum(IB[k] for k in onlyB):,.0f})')
    for k in onlyB[:8]: print(f'      {k[0]:20s} {k[1]:20s} {IB[k]:>9,.0f}')
    both = [(abs(IB[k]-IA[k]), k, IA[k], IB[k]) for k in set(IA) & set(IB) if abs(IB[k]-IA[k]) > 0.5]
    both.sort(reverse=True)
    print(f'   공통인데 수량差 {len(both)}조합')
    for _, k, a, b in both[:10]:
        print(f'      {k[0]:20s} {k[1]:20s} nx={a:>8,.0f} new={b:>8,.0f} {b-a:>+8,.0f}')
except Exception as e:
    traceback.print_exc()

# ⑨ 040 차이 상세
hdr('⑨ 040 — 차이 -66 어디서 (제번 나눔 때문?)')
try:
    from routers import sales
    an = sales.sale040_grid(from_ymd=YMD, gigan=4, line='', wo='', item='', src='new', limit=20000)
    al = sales.sale040_grid(from_ymd=YMD, gigan=4, line='', wo='', item='', src='live', limit=20000)
    def idx4(rows):
        d = {}
        for x in rows:
            k = (str(x.get('wo') or '').strip(), str(x.get('item') or '').strip())
            d[k] = d.get(k, 0) + sum(float(v or 0) for v in (x.get('days') or {}).values())
        return d
    IA, IB = idx4(al.get('rows') or []), idx4(an.get('rows') or [])
    onlyA = sorted(set(IA)-set(IB)); onlyB = sorted(set(IB)-set(IA))
    print(f'   레거시에만 {len(onlyA)} (합 {sum(IA[k] for k in onlyA):,.0f})')
    for k in onlyA[:10]: print(f'      {k[0]:16s} {k[1]:20s} {IA[k]:>9,.0f}')
    print(f'   웹에만 {len(onlyB)} (합 {sum(IB[k] for k in onlyB):,.0f})')
    for k in onlyB[:10]: print(f'      {k[0]:16s} {k[1]:20s} {IB[k]:>9,.0f}')
    both = [(abs(IB[k]-IA[k]), k, IA[k], IB[k]) for k in set(IA)&set(IB) if abs(IB[k]-IA[k]) > 0.5]
    both.sort(reverse=True)
    print(f'   공통 수량差 {len(both)}')
    for _, k, a, b in both[:10]:
        print(f'      {k[0]:16s} {k[1]:20s} 레거시={a:>8,.0f} 웹={b:>8,.0f} {b-a:>+8,.0f}')
    # data_gubun 별
    for nm, rows in (('레거시', al.get('rows') or []), ('웹', an.get('rows') or [])):
        c = collections.Counter()
        for x in rows:
            c[str(x.get('data_gubun') or '')] += sum(float(v or 0) for v in (x.get('days') or {}).values())
        print(f'   {nm} data_gubun별: ' + ' '.join(f'{k}={v:,.0f}' for k, v in sorted(c.items())))
except Exception as e:
    traceback.print_exc()

# ⑧ 050 행 차이
hdr('⑧ 050 — 행수 1270 vs 1274')
try:
    from routers import salesplan
    sn = salesplan.salesplan(from_ymd=YMD, days=7, gubun='2', cust='', line='',
                             model='', wo='', item='', src='nx')
    sl = salesplan.salesplan(from_ymd=YMD, days=7, gubun='2', cust='', line='',
                             model='', wo='', item='', src='live')
    def idx5(rows):
        d = {}
        for x in rows:
            k = (str(x.get('wo') or '').strip(), str(x.get('item') or '').strip())
            d[k] = d.get(k, 0) + float(x.get('total') or 0)
        return d
    IA, IB = idx5(sl.get('rows') or []), idx5(sn.get('rows') or [])
    print(f'   레거시 total합 {sum(IA.values()):,.0f} / 웹 {sum(IB.values()):,.0f}')
    onlyA = sorted(set(IA)-set(IB)); onlyB = sorted(set(IB)-set(IA))
    print(f'   레거시에만 {len(onlyA)}: ' + ', '.join(f'{k[0]}/{k[1]}' for k in onlyA[:6]))
    print(f'   웹에만 {len(onlyB)}: ' + ', '.join(f'{k[0]}/{k[1]}' for k in onlyB[:6]))
    both = [(abs(IB[k]-IA[k]), k, IA[k], IB[k]) for k in set(IA)&set(IB) if abs(IB[k]-IA[k]) > 0.5]
    both.sort(reverse=True)
    print(f'   공통 수량差 {len(both)}')
    for _, k, a, b in both[:8]:
        print(f'      {k[0]:16s} {k[1]:20s} 레거시={a:>8,.0f} 웹={b:>8,.0f} {b-a:>+8,.0f}')
except Exception as e:
    traceback.print_exc()
