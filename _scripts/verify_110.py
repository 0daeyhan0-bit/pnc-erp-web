# -*- coding: utf-8 -*-
import sys,io,json; sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding='utf-8')
raw=open(r'd:\피앤씨인더스트리\100_AI_AGENT\PNC_ERP_Web\js\data.js',encoding='utf-8').read()
DB=json.loads(raw[raw.index('const DB = ')+11:raw.rindex(';')])
ps={r[0]:r for r in DB['prodItemStock']}
exp={'MJU63357501':1418,'ACJ75119301':200,'AJR30004702':232,'ACJ75119304':30,'5211A21904A':3,'MJU64433701':5058}
for it,e in exp.items():
    v=ps.get(it,[None,None,None,0])[3]
    ok='OK' if abs(v-e)<0.5 else 'XX'
    print('%-14s 내값 %10s  라이브 %8s  %s'%(it,v,e,ok))
print('재고합:', round(sum(r[3] for r in DB['prodItemStock']),1), ' (라이브 50,104)')
