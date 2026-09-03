# -*- coding: utf-8 -*-
"""★partplandtl.py 가 -53% 미러를 토글없이 읽는다 → 화면이 실제로 반토막인가 확인"""
import sys, io, os, traceback, inspect
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
B = r'c:\Users\박근민\Desktop\NEW_ERP_1\PNC_ERP_Web\backend'
sys.path.insert(0, B); sys.path.insert(0, os.path.join(B, 'routers'))
sys.path.insert(0, r'c:\Users\박근민\Desktop\New_ERP')
os.chdir(B)
import pyodbc, db_client
nx = pyodbc.connect(f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};'
                    f'DATABASE=PARTNER_ERP_TEST3;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}').cursor()
F, T = '260902', '260907'

print('■ partplandtl 이 읽는 미러 vs 라이브 vs 웹정본')
nx.execute(f"""SELECT
   (SELECT SUM(CAST(PART_PLAN_QTY AS float)) FROM PARTNER_ERP.dbo.PR_T_PLAN_PART_MAT WITH(NOLOCK)
     WHERE PART_PLAN_YMD BETWEEN '{F}' AND '{T}') 라이브,
   (SELECT SUM(CAST(PART_PLAN_QTY AS float)) FROM nx.PR_T_PLAN_PART_MAT WITH(NOLOCK)
     WHERE PART_PLAN_YMD BETWEEN '{F}' AND '{T}') nx미러,
   (SELECT SUM(CAST(part_plan_qty AS float)) FROM nx.plan_part_mat WITH(NOLOCK)
     WHERE part_plan_ymd BETWEEN '{F}' AND '{T}') 웹정본""")
r = nx.fetchone()
print(f'   라이브   {float(r[0] or 0):>14,.0f}')
print(f'   nx미러   {float(r[1] or 0):>14,.0f}   ({(float(r[1] or 0)-float(r[0] or 0))/float(r[0] or 1)*100:+.1f}%)  ← partplandtl 이 읽음')
print(f'   웹정본   {float(r[2] or 0):>14,.0f}   ({(float(r[2] or 0)-float(r[0] or 0))/float(r[0] or 1)*100:+.1f}%)')

print('\n■ 실제 화면 API 호출')
try:
    from routers import partplandtl
    sig = inspect.signature(partplandtl.__dict__.get('partplan_list') or list(
        v for k, v in partplandtl.__dict__.items() if callable(v) and k.startswith('partplan'))[0])
    print(f'   시그니처: {sig}')
except Exception as e:
    print('   ', str(e)[:150])
    import routers.partplandtl as pp
    fns = [k for k, v in pp.__dict__.items() if callable(v) and not k.startswith('_')]
    print('   함수들:', fns[:10])

try:
    from routers import partplandtl as pp
    for k, v in pp.__dict__.items():
        if callable(v) and k.startswith('partplan'):
            print(f'\n   ▶ {k}{inspect.signature(v)}')
            kw = {}
            for n, p in inspect.signature(v).parameters.items():
                d = p.default
                kw[n] = getattr(d, 'default', d)
            for cand in ('from_ymd', 'base_ymd', 'ymd'):
                if cand in kw: kw[cand] = F
            try:
                res = v(**kw)
                rows = res.get('rows') if isinstance(res, dict) else res
                print(f'      → {len(rows or [])}행')
                if rows:
                    print(f'      키: {sorted(rows[0].keys())[:14]}')
                    for c in ('qty', 'plan_qty', 'part_plan_qty', 'q'):
                        if c in rows[0]:
                            print(f'      {c} 합 = {sum(float(x.get(c) or 0) for x in rows):,.0f}')
            except Exception as e2:
                print(f'      호출 ERR {str(e2)[:120]}')
except Exception as e:
    traceback.print_exc()
