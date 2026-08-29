# 견적원가손익 (w_cs_esti_020) 레거시 완전분석

> 원본: `w_cs_esti_020`(견적원가손익금액) · DW `dw_cs_cost_020_*` · SP `SP_CS_견적서(실원가용/내부용)`
> 우리 대응: 웹 `품목별 원가분석`(SCREEN.costanalysis) · `/api/esti` · `nx_cost_engine.py`
> 분석일 2026-08-03. **레거시는 버그가능 — 원가규칙만 100% 정합 목표**([[feedback-verify-legacy-bugs]]).

## 1. 프로그램 구조
- **화면**: 좌=품번리스트(`dw_cs_cost_020_t1`, 클라이언트 DW: select_flag·item_code·in_qty), 우=손익분석현황(`dw_cs_cost_020_c1`).
- **조회구분**: 1=품번 직접입력 / (벌크=리시빙실적). **단가기준일자**(@AS_COST_APPLY_YMD, 6자리).
- 프로그램이 **내부용 SP + 실원가 SP 두 개를 각 품번마다 호출**해 나란히 표시. DW는 SP 출력컬럼을 매핑 + 원가·재료비율만 compute.
  - 웹 `/api/esti`는 nx엔진으로 대체(내부용 SP엔진 부재 → nae=sil 동일값 반환, WON/BU/SA 분해 미구현).

## 2. SP_CS_견적서(실원가용)_250910 — 10단계 (정본)
입력 `@AS_ITEM_CODE`, `@AS_COST_APPLY_YMD`(YYMMDD).

1. **환율**(#TEMP_EXCHANGE): `FI_M_EXCHANGE` USD/YEN/EUR, EXCH_YMD ≤ ymd 최신.
2. **BOM 재귀전개**(CTE_BOM→#TEMP_BOM): `CS_M_ITEM_BOM` 재귀. `CS_CALC_EXCEPT_FLAG='1'` 제외, `cost_gubun='5'`(직납) 전개중단. `INNER_PROD_FLAG`=사내생산(MAKE_TYPE='1' or 가공공정 보유). `gravity`=CM_M_MASTER_DETAIL(PR019).OTHER_CHAR1(비중).
3. **중량**: `ITEM_WEIGHT = (외경−T)×T×π×길이×비중÷1,000,000` (외경>0). ★**동정산 엑셀 공식과 100% 동일**(구리 비중 8.94).
4. **★원소재 소재단가**(WON_MAT_COST): `CS_M_METERIAL_COST.tot_cost` by (metal_gubun,item_diam,item_thick, **apply_yyyymm < '20'+ymd** 최신). 사급차액 base `WON_MAT_COST_SUB = tot_cost − tot_cost_sub`.
5. **★구매품 매입단가**: #TEMP_MAT(cost_gubun∉('3','4') AND **INNER_PROD='0'**)에 `PR_M_ITEM_COST.ITEM_COST × 환율` by (품번, **입고거래처 cust_code**, cost_tag='1', cost_apply_ymd ≤ ymd 최신). *3개월 입고 최종거래처 자동선택 로직은 주석처리*.
6. **재료비**(JAI_COST): 소재(cg='3')=단가×중량×qty / 구매=단가×qty. **+ LME차액 포함**(25/06/30 변경). 최말단(BOTTOM_FLAG='1')에만 발생, 상위는 SUM 롤업.
7. **가공비**(GAGONG_AMT): `CS_T_ITEM_PROC × 임율`. 사내(INNER_PROD='1')만. calc_gubun **3=임율**(LABOR_COST/UPH×WORK_QTY)·**7=세척(0)**·**8=중량**(중량×UPH×WORK_QTY)·**9=적용율**. 임율=`CS_M_LABOR_COST_RATE` ★**GETDATE 최신(ymd 무관)**.
8. **간접비**: 일반관리비(91)=`ILBAN_RATE×(재료−LME+가공)` · 이윤(93)=`PROFIT_RATE×(가공+일반)` · 운반비(92). 사내만, 상위 롤업.
9. **LG판가**(LG_COST): `PR_M_ITEM_COST` vendor∈('1010','1020','1030'), cost_apply_ymd ≤ ymd 최신. (LEVEL=0)
10. **원/부/사급 분해**(최종 SELECT, ITEM_SGROUP 기준): **원자재=110/120/130/220** · **부자재=230/910** · **사급=310**. `WON_JAI_AMT/BU_JAI_AMT/SA_JAI_AMT = Σ(BOTTOM JAI_COST × UPPER_USE_QTY)`.

**TOT_AMT(실원가) = 재료비 + 가공비 + 일반관리 + 운반비 + 이윤.  손익 = LG판가 − 실원가.**

## 3. 내부용 SP(SP_CS_견적서(내부용)_250704)와의 차이
단가 소스(CS_M_METERIAL_COST 소재 + PR_M_ITEM_COST 구매)는 **동일**. 차이는 **조달 반영 여부**:
- **실원가**: #TEMP_MAT에 `AND INNER_PROD='0'` + `SET COST_GUBUN='2' WHERE INNER_PROD='0'` → **사내생산 아닌 부품은 실제 매입단가로 대체(매입중단, 실제 조달)**. LME는 구매 동부품(INNER_PROD=0)만.
- **내부용**: INNER_PROD 조건 없음 → **전공정 자체생산 가정**(전 노드 소재단가×중량 + 우리 가공비 전개).
- 그래서 스크린샷처럼 **원자재비/부자재비 분해값이 내부용≠실원가**(어느 노드가 최말단이 되고 소재단가/매입단가 중 무엇을 쓰는지가 달라짐).

## 4. ★단가 소스 요약 (실구매가 vs LG인증가)
| 구성 | 소스 테이블 | 성격 | 우리 nx 대응 |
|---|---|---|---|
| 원소재(cg='3', 사내가공 동관) | **CS_M_METERIAL_COST**(tot_cost) | **LG 인증 소재단가**(=동정산 Cost Table, tot_cost−tot_cost_sub=LME차액) | **nx.price_metal**(std_price/partner_price) |
| 구매품(INNER_PROD='0') | **PR_M_ITEM_COST**(입고거래처, cost_tag='1') | **실 구매가격** | nx.price_item(매입) |
| LG판가 | PR_M_ITEM_COST(1010/1020/1030) | 판가 | nx.dtrade / price_item |
| 임율 | CS_M_LABOR_COST_RATE | 가공 임율 | nx.labor_rate |

→ **원소재 소재단가(price_metal)에 채울 값 = LG 인증 소재단가(동정산 Cost Table)**. 실구매가는 구매품용(price_item)이며 이미 7월 입력됨.

## 5. 우리 nx엔진과의 갭
- **원/부/사급 재료비 분해(WON/BU/SA) 미구현**(nx=0) — 레거시는 ITEM_SGROUP로 분해(화면 원자재비/부자재비).
- 소재단가 as-of: 레거시 **`<`(미만)** vs nx `<=`(이하) — 경계월 미세차이.
- 7월 갭: **price_metal(소재단가) 5월 최신·CU만·고강도관 없음**([[newerp-lg-price-settlement-files]]). LG판가·매입가·LME인정가는 7월 입력됨.

[[newerp-legacy-cost-algorithm]] [[newerp-cost-verify-harness]] [[newerp-internal-cost-tab]] [[feedback-material-price-close-only]]
