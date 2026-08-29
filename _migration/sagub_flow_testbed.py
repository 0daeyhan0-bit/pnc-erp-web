# -*- coding: utf-8 -*-
"""사급 흐름 TEST BED (no-commit·오염0) — 사용자 관점 협력사입고/피앤씨입고 → 전 원장 반영 검증.
   협력사입고 = 사급출고(/api/saleout/save)  → 매출·협력사사급재고·재고·수불장
   피앤씨입고 = 세트입고(/api/setstock/receive) → 재고(자도번 tag S)·협력사사급재고(−소진)·수불장(협력사출고)
   실제 엔드포인트 구동. 실행: python _migration/sagub_flow_testbed.py
"""
import sys, io
sys.path.insert(0, r'd:/피앤씨인더스트리/100_AI_AGENT/Projects/_wt_sagub/PNC_ERP_Web/backend')
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', line_buffering=True)
import common, pyodbc, db_client
CS=(f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};DATABASE=PARTNER_ERP_TEST3;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}')

class NC:
    def __init__(s,c): object.__setattr__(s,'_c',c)
    def cursor(s): return s._c.cursor()
    def commit(s): pass
    def close(s): pass
    def rollback(s): pass
    def __getattr__(s,n): return getattr(s._c,n)

raw=pyodbc.connect(CS, autocommit=False); sh=NC(raw)
common._nx=lambda:sh; common._nx_tx=lambda:sh; common._conn=lambda:sh
import routers.sales as SA, routers.setin as SI, routers.auth as AU, routers.sagubledger as SL
for M in (SA,SI,SL):
    M._nx=lambda:sh
    if hasattr(M,'_nx_tx'): M._nx_tx=lambda:sh
    if hasattr(M,'_conn'): M._conn=lambda:sh
SA.stock_changed=lambda *a,**k:None; SI.stock_changed=lambda *a,**k:None
_STAFF={"user_id":"tb","utype":"직원","partner_code":None,"status":"사용"}
for M in (AU,SI,SL):
    if hasattr(M,'require_user'): M.require_user=lambda req:_STAFF
    if hasattr(M,'scope_cust'): M.scope_cust=lambda u,c=None:c
if hasattr(SI,'staff_only'): SI.staff_only=lambda req,what="":_STAFF
if hasattr(SI,'_assert_open'): SI._assert_open=lambda *a,**k:None
class _Req: pass
cur=sh.cursor()

def led(cust, mat=""):
    r=SL.sagubledger_list(_Req(), cust=cust, mat=mat, fr='260701', to='261231', sign='', scope='all', limit=5000)
    return r
def led_one(cust, mat):
    for x in led(cust,mat)['rows']:
        if x['mat_code'].strip()==mat.strip(): return x
    return {"sent":0.0,"used":0.0,"bal":0.0}
def n(v): return f"{v:+,.1f}"

print("="*70); print("■ 사급 흐름 TEST BED — 협력사입고(saleout) + 피앤씨입고(setstock)"); print("="*70)

# ══ 시나리오 A: 협력사입고(사급출고) 다품목 ══
print("\n── A. 협력사입고 = 사급출고(/api/saleout/save) ──")
cur.execute("SELECT DISTINCT TOP 3 mat_code FROM nx.sagub_maint WHERE cust_code='2096' AND remarks_src='hist7' AND maint_qty>0")
partsA=[str(r[0]).strip() for r in cur.fetchall()]
for mat in partsA:
    b=led_one('2096',mat)
    res=SA.saleout_save({'out_cust':'2096','item_code':mat,'out_qty':40,'out_ymd':'260716','sagub':'1'})
    a=led_one('2096',mat)
    ok = abs((a['sent']-b['sent'])-40)<0.01
    print(f"  {'✅' if ok else '❌'} {mat:16s} 협력사입고 {n(b['sent'])}→{n(a['sent'])} (Δ+40 기대) · 매출amt {res.get('amt')}")

# ══ 시나리오 B: 피앤씨입고(세트입고) — barcode 700003(미래정밀) ══
print("\n── B. 피앤씨입고 = 세트입고(/api/setstock/receive) barcode 700003 ──")
# 이 바코드가 소진시킬 사급부품(예상) = 완제품들 소요
cur.execute("SELECT item_code,ISNULL(deliver_qty,input_req_qty) FROM nx.set_input_req WHERE barcode_no='700003' AND status IN('10','30')")
comp=[(str(r[0]).strip(),float(r[1] or 0)) for r in cur.fetchall()]
import nx_soyo_engine as soyo
eng=SI._sag_eng(); memo={}
exp={}  # part -> 예상 소진
for it,q in comp:
    for p,per in soyo.sagub_parts_soyo(eng,it,SI._SAG_STOP,memo).items():
        if p in SI._SAG_WELD: continue
        exp[p]=exp.get(p,0.0)+per*q
print(f"  세트입고 완제품 {len(comp)}종 → 예상 소진 사급부품 {len(exp)}종")
before={p:led_one('2096',p) for p in exp}
tot_out_b = led('2096')['tot']['used']
res=SI.setstock_receive(_Req(), {'barcode':'700003','tag':'2'})
print(f"  setstock_receive 결과: received={res.get('received')} · 재고파생(tag S)={res.get('ledger_posted')}")
tot_out_a = led('2096')['tot']['used']
print(f"  수불장 협력사출고 총합 {tot_out_b:,.1f}→{tot_out_a:,.1f} (Δ{tot_out_a-tot_out_b:+,.1f})")
okc=0
for p in list(exp)[:6]:
    b=before[p]; a=led_one('2096',p); d=a['used']-b['used']
    ok=abs(d-exp[p])<0.5
    okc+=ok
    print(f"  {'✅' if ok else '❌'} {p:16s} 협력사출고 Δ{d:+.1f} (기대 {exp[p]:+.1f}) · 잔량 {a['bal']:+.1f}")
# 재고(자도번 tag S) 반영 확인
cur.execute("SELECT COUNT(*),SUM(CAST(MAINT_QTY AS float)) FROM nx.stock_ledger WHERE MAINT_TAG='S' AND CUST_CODE='2096' AND INSERT_USER_ID='web' AND MAINT_YMD=RIGHT(CONVERT(varchar(8),GETDATE(),112),6)")
r=cur.fetchone(); print(f"  재고 자도번파생(stock_ledger tag S) 신규: {r[0]}행 Σ{float(r[1] or 0):+,.0f}")
# 사급소진(sagub_maint tag S) 확인
cur.execute("SELECT COUNT(*),SUM(CAST(maint_qty AS float)) FROM nx.sagub_maint WHERE maint_tag='S' AND remarks_src LIKE 'setstock:%'")
r=cur.fetchone(); print(f"  협력사출고(sagub_maint setstock) 신규: {r[0]}행 Σ{float(r[1] or 0):+,.0f}")

# ══ 시나리오 C: 입고취소(cancel) → 협력사출고 역posting ══
print("\n── C. 입고취소(/api/setstock/cancel) → 협력사출고 되돌림 ──")
cres=SI.setstock_cancel(_Req(), {'barcode':'700003','user':'tb'})
cur.execute("SELECT COUNT(*) FROM nx.sagub_maint WHERE maint_tag='S' AND remarks_src LIKE 'setstock:%'")
left=cur.fetchone()[0]
cancel_after = led('2096')['tot']['used']
okC = (left==0) and abs(cancel_after - tot_out_b) < 0.5
print(f"  cancel 결과: 협력사출고 되돌림 {cres.get('sagub_deleted')}행 · 재고파생 {cres.get('ledger_deleted')}행")
print(f"  {'✅' if okC else '❌'} setstock posting 잔여 {left}행(0 기대) · 수불장 협력사출고 {cancel_after:,.1f}→원복 {tot_out_b:,.1f} 기대")

raw.rollback()
cur.execute("SELECT COUNT(*) FROM nx.sagub_maint WHERE remarks_src LIKE 'setstock:%' OR remarks_src LIKE 'saleout:%'")
print(f"\n롤백 후 신규 posting(오염0): {cur.fetchone()[0]}행")
raw.rollback(); raw.close()
print("(전부 롤백·production 무변경)")
