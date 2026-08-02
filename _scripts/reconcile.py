# -*- coding: utf-8 -*-
import sys, io, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
raw=open(r"d:\피앤씨인더스트리\100_AI_AGENT\PNC_ERP_Web\js\data.js",encoding="utf-8").read()
DB=json.loads(raw[raw.index("const DB = ")+11:raw.rindex(";")])

# 자재 수불장(일, 260717=matLedger) 재고수량(sq) 총계
ml=DB.get('matLedger',[])
print("자재 일수불장(260717) 재고수량(sq) 총계:", round(sum((r.get('sq') or 0) for r in ml),2), " 품목:",len(ml))
# 월수불장(2606=monthLedger) 재고수량
mo=DB.get('monthLedger',[])
print("자재 월수불장(2606) 재고수량(sq) 총계:", round(sum((r.get('sq') or 0) for r in mo),2), " 품목:",len(mo))
# 060 내 계산
s060=DB.get('matStock060',[])
print("060 내계산 재고 총계:", round(sum(r['stock'] for r in s060),2)," 품목:",len(s060))

# MAF66426701 각 소스
for it in ('MAF66426701','MGZ62928801','AAA36923606'):
    a=next((r for r in ml if r['cd']==it),None)
    b=next((r for r in mo if r['cd']==it),None)
    c=next((r for r in s060 if r['mat']==it),None)
    print(f"\n{it}:")
    print("  일수불장(sq):", a['sq'] if a else '없음')
    print("  월수불장(sq):", b['sq'] if b else '없음')
    print("  060(재고):", c['stock'] if c else '없음')
