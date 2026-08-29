# -*- coding: utf-8 -*-
"""원가 라이브 diff0(B, 데이터): nx.price_item '매입'을 레거시 실사용단가로 재구성.
레거시 SP(실원가용 line247·297-309): 매입단가 = PR_M_ITEM_COST WHERE cust_code=**BOM엣지 MAT_IN_CUST_CODE**
(CS_M_ITEM_BOM.CUST_CODE) AND cost_tag='1', cost_apply_ymd<=ymd 최신. 품목마스터 IN_CUST가 아님.
★교정(2026-08-13): 기존은 i.IN_CUST_CODE=c.CUST_CODE 강제조인 → 등록거래처≠원가거래처 구매품 16128행 탈락(엔진 폴백조차 불가).
→ 전vendor cost_tag='1'(≠0) 전부 적재. 엔진 pur_price(vendor 우선, 없으면 전vendor 최신 폴백)가 BOM엣지 거래처(nx.bom_line.cust_code, r_bomedge_cust.py)로 정확히 잡음.
백업 nx.price_item_bak_costlive. --commit 없으면 계획만."""
import sys, io
sys.path.insert(0, r'd:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP')
import pyodbc, db_client
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
# ══════════════════════════════════════════════════════════════════════════════
# ★★★ 2026-08-29 폐기 — 실행 금지. nx.price_item 이 **단가 마스터로 승격**됐다.
#
# 이 스크립트는 아래에서 `DELETE FROM nx.price_item WHERE price_type='매입'` 을 한 뒤
# 라이브에서 통째로 다시 채운다. 파생 조회본일 때는 맞는 동작이었지만,
# 지금 nx.price_item 은 **웹 단가관리 화면이 직접 쓰는 마스터**다.
# 지금 실행하면 **웹에서 입력·수정한 단가가 전부 사라진다.**
#
# 승격 근거·검증 = `_schema/CUTOVER_CHECKLIST.md` "(A)안 검증"
#   · PK(품번·구분·거래처·적용일) = 미러 PK 와 1:1 · 중복 0 · 참조 FK 없음
#   · main_flag 등 7컬럼을 라이브에서 백필(99.23%) → sourcing 값차이 163 → 1
#   · 백업 = nx.price_item_bak_promote (132,148행, 2026-08-29)
#
# 그래도 돌려야 한다면(복구 등) `--i-know-this-deletes-the-master` 를 함께 준다.
# ══════════════════════════════════════════════════════════════════════════════
if '--i-know-this-deletes-the-master' not in sys.argv:
    print("★실행 거부 — nx.price_item 은 단가 마스터다. 이 스크립트는 매입 단가를 전부 지운다.")
    print("  근거: _schema/CUTOVER_CHECKLIST.md '(A)안 검증' · 백업 nx.price_item_bak_promote")
    print("  정말 필요하면 --i-know-this-deletes-the-master 를 붙일 것.")
    sys.exit(1)

DRY=('--commit' not in sys.argv)
cn=pyodbc.connect(f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};DATABASE=PARTNER_ERP_TEST3;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}', autocommit=True)
c=cn.cursor()
cur_mai=c.execute("SELECT COUNT(*) FROM nx.price_item WHERE price_type='매입'").fetchone()[0]
# 재구성 후보 = 전vendor cost_tag='1'(≠0). vendor_code=cust_code로 그대로 보존(엔진이 BOM엣지 거래처로 선택).
newq="""SELECT COUNT(*) FROM PARTNER_ERP.dbo.PR_M_ITEM_COST c
   WHERE c.COST_TAG='1'"""
newc=c.execute(newq).fetchone()[0]
print(f"현재 nx.price_item 매입 {cur_mai} → 재구성(전vendor tag=1, 0원 포함) {newc}건")
if DRY:
    print("DRY (--commit 실행)"); cn.close(); sys.exit()
# 백업(원본 보존 — 이미 있으면 유지)
if c.execute("SELECT OBJECT_ID('nx.price_item_bak_costlive','U')").fetchone()[0] is None:
    c.execute("SELECT * INTO nx.price_item_bak_costlive FROM nx.price_item")
    print("백업 생성 nx.price_item_bak_costlive:", c.execute("SELECT COUNT(*) FROM nx.price_item_bak_costlive").fetchone()[0])
else:
    print("백업 유지(기존):", c.execute("SELECT COUNT(*) FROM nx.price_item_bak_costlive").fetchone()[0])
# 매입 재구성(전vendor)
c.execute("DELETE FROM nx.price_item WHERE price_type='매입'")
c.execute("""INSERT INTO nx.price_item(item_code, price_type, vendor_code, currency, apply_ymd, price)
   SELECT item_code,'매입',cust_code,currency,apply_ymd,price FROM (
     SELECT LTRIM(RTRIM(c.ITEM_CODE)) AS item_code, LTRIM(RTRIM(c.CUST_CODE)) AS cust_code,
            ISNULL(NULLIF(LTRIM(RTRIM(c.CURRENCY)),''),'KRW') AS currency,
            RIGHT('000000'+LTRIM(RTRIM(c.COST_APPLY_YMD)),6) AS apply_ymd, ISNULL(c.ITEM_COST,0) AS price,
            ROW_NUMBER() OVER (PARTITION BY LTRIM(RTRIM(c.ITEM_CODE)),LTRIM(RTRIM(c.CUST_CODE)),RIGHT('000000'+LTRIM(RTRIM(c.COST_APPLY_YMD)),6)
                               ORDER BY c.MAIN_FLAG DESC, ISNULL(c.ITEM_COST,0) DESC) AS rn
       FROM PARTNER_ERP.dbo.PR_M_ITEM_COST c
      WHERE c.COST_TAG='1'
        AND EXISTS(SELECT 1 FROM nx.item ni WHERE ni.item_code=LTRIM(RTRIM(c.ITEM_CODE)))
   ) q WHERE q.rn=1""")
print("재구성 매입:", c.execute("SELECT COUNT(*) FROM nx.price_item WHERE price_type='매입'").fetchone()[0])
print("완료 (되돌리기: nx.price_item_bak_costlive 복원)")
cn.close()
