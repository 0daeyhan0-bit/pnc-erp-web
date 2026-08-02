# -*- coding: utf-8 -*-
# 060(자재입출고현황)을 자재수불장(260) 정본 07/17에 정렬. LEFT=matLedger sq/bq, 이력<=260717
import sys,io,json; sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding='utf-8')
path=r"d:\피앤씨인더스트리\100_AI_AGENT\PNC_ERP_Web\js\data.js"
raw=open(path,encoding='utf-8').read()
DB=json.loads(raw[raw.index("const DB = ")+len("const DB = "):raw.rindex(";")])
ml={r['cd']:r for r in DB['matLedger']}   # 정본 260 (07/17)
# 이력 07/17 컷 (matMoves060 = 리스트, 각 레코드 .mat)
mv=DB.get('matMoves060',[]); mv2=[x for x in mv if str(x.get('ymd',''))<='260717']
import collections
bymat=collections.defaultdict(list)
for x in mv2: bymat[x.get('mat')].append(x)
# LEFT = 자재수불장 정본 (sq<>0), bf=bq
new=[]
for cd,r in ml.items():
    sq=float(r.get('sq',0) or 0)
    if abs(sq)<0.0001: continue
    new.append({'mat':cd,'nm':r.get('nm',''),'stock':round(sq,3),'bf':round(float(r.get('bq',0) or 0),3),'lastin':r.get('lastin','')})
# 우측 재현 검증(bf+net(<=0717) vs sq) 샘플
def net(cd):
    s=0
    for x in bymat.get(cd,[]): s+=(float(x.get('i',0)or 0))-(float(x.get('o',0)or 0))+(float(x.get('e',0)or 0))+(float(x.get('mv',0)or 0))
    return s
bad=0; chk=[]
for r in new:
    calc=r['bf']+net(r['mat']); d=r['stock']-calc
    if abs(d)>0.5: bad+=1;
    if abs(d)>0.5 and len(chk)<8: chk.append((r['mat'],r['stock'],round(calc,1),round(d,1)))
new.sort(key=lambda x:(''+x['mat']))
DB['matStock060']=new; DB['matMoves060']=mv2
head=raw[:raw.index("const DB = ")+len("const DB = ")]
open(path,'w',encoding='utf-8').write(head+json.dumps(DB,ensure_ascii=False,indent=0)+";\n")
print("matStock060 재정렬:",len(new),"품목(0제외), 재고합",round(sum(x['stock'] for x in new),1),"(자재수불장 8,053,853)")
print("우측(bf+이력<=0717) vs LEFT(sq) 불일치>0.5:",bad,"/",len(new))
for c in chk: print("  ",c)
