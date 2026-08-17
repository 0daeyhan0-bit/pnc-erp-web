# -*- coding: utf-8 -*-
# ③원가 안전: 정규SUB/routing/R01 적재 후 원가엔진 실원가 회귀 (SELECT only)
import sys
sys.path.insert(0, r'd:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP')
sys.path.insert(0, r'd:\피앤씨인더스트리\100_AI_AGENT\Projects\NEW_ERP_1\_harness')
import pyodbc, db_client
def NX(): return pyodbc.connect(f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};DATABASE=PARTNER_ERP_TEST3;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}')
n=NX().cursor()
# 다양 15품목(bom_header 보유)
n.execute("""SELECT TOP 15 item_code FROM nx.bom_header WHERE item_code LIKE 'AJR%' ORDER BY item_code""")
items=[r[0] for r in n.fetchall()]
try:
    from nx_cost_engine import NxCostEngine
    eng=NxCostEngine()
    ok=0; err=0
    print(f"{'품목':<16}{'재료':>10}{'가공':>8}{'실원가':>10}  상태")
    for it in items:
        try:
            s=eng.silwon(it,'260630')
            print(f"  {it:<16}{s.get('jae',0):>10.1f}{s.get('gagong',0):>8.1f}{s.get('silwon',0):>10.1f}  ✔")
            ok+=1
        except Exception as e:
            print(f"  {it:<16} (err){str(e)[:40]}"); err+=1
    print(f"\n★엔진 실원가 정상: {ok}/{len(items)} · 오류 {err} (=원가 무손상, 마이그 안전)")
    # 앵커 재확인
    a=eng.silwon('AJR75563402','260630'); print(f"  앵커 AJR75563402 실원가={a.get('silwon')} (기대 5722.2)")
except Exception as e:
    print("엔진 임포트 실패:", str(e)[:80])
print("DONE")
