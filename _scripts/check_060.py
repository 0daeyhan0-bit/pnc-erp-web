# -*- coding: utf-8 -*-
import sys, io, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
raw=open(r"d:\피앤씨인더스트리\100_AI_AGENT\PNC_ERP_Web\js\data.js",encoding="utf-8").read()
DB=json.loads(raw[raw.index("const DB = ")+11:raw.rindex(";")])
S={s['mat']:s for s in DB['matStock060']}
# ERP 화면값 (자도번: 재고)
erp={'AAA36923606':1,'96902009':187.055,'AAA31179501':333,'AAA31179502':602,'AAA31179503':0,
     'AAA31179504':318,'AAA31179505':0,'AAA36923607':23,'AAA36923608':197,'AAA36923611':330,
     'AAA68954002':47,'AAA72940317':197,'91427011':0,
     'AJR73965607-F&T':240,'AJR73965606-F&T':243,'AJR73965601-19-7':100,'AJR73965602-19-1':100,
     'AJR73965602-19-10':100,'AJR73965602-19-11':0,'AJR73965606-19-1':100,'AJR73965607-19-1':100,
     'AJR73965607-SUB':0,'AJR73965606-SUB':0,'AJR73968602':0,'AJR73965602-15-1':0}
print(f"{'자도번':16}{'내계산':>12}{'ERP':>12}  일치")
ok=0
for m,e in erp.items():
    s=S.get(m.upper())
    v=s['stock'] if s else None
    match = (v is not None and abs(v-e)<0.01)
    ok+=match
    print(f"{m:16}{('' if v is None else round(v,3)):>12}{e:>12}  {'O' if match else 'X'}{'' if s else ' (내목록에없음)'}")
print(f"\n일치 {ok}/{len(erp)}")
tot=sum(s['stock'] for s in DB['matStock060'])
print(f"\nmatStock060 총계: {tot:,.2f} (품목 {len(DB['matStock060'])})  ERP목표 299,913")
print("상위 재고 15품목(총계 부풀리는 후보):")
for s in sorted(DB['matStock060'],key=lambda x:-abs(x['stock']))[:15]:
    print(f"  {s['mat']:18} 재고 {s['stock']:>14,.2f}  bf {s['bf']:>14,.2f}  {s['nm'][:20]}")
