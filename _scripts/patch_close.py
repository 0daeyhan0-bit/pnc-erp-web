# -*- coding: utf-8 -*-
import sys, io, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
cj=json.loads(open(r"C:\Users\admin\AppData\Local\Temp\claude\d-----------100-AI-AGENT\02b63e35-1303-4eb0-8eb4-29df63d29c62\scratchpad\_close.json",encoding="utf-8").read())
# 친절한 라벨 매핑
label={'자재(월마감)':'자재재고','자재(일마감)':'자재재고','생산파트(월마감)':'생산 파트재고','영업제품(월마감)':'영업 제품재고','세트(월마감)':'세트재고'}
for r in cj['closeStatus']:
    r['name']=label.get(r['domain'],r['domain'])
path=r"d:\피앤씨인더스트리\100_AI_AGENT\PNC_ERP_Web\js\data.js"
raw=open(path,encoding="utf-8").read()
head=raw[:raw.index("const DB = ")+len("const DB = ")]
DB=json.loads(raw[raw.index("const DB = ")+len("const DB = "):raw.rindex(";")])
DB['closeStatus']=cj['closeStatus']; DB['closeAsof']=cj['closeAsof']; DB['curYm']=cj['curYm']
open(path,"w",encoding="utf-8").write(head+json.dumps(DB,ensure_ascii=False,indent=0)+";\n")
print("data.js 패치완료: closeStatus",len(DB['closeStatus']))
