# 레거시 원가 산식 분석 (품목별 원가분석 / 견적원가손익 정본)

> 목적: 레거시 원가 SP를 원본 소스로 완전 분석해, **차세대 nx 원가엔진 재현**과 **최종 이관**의 근거로 재사용.
> 근거 원본(이 폴더): `SP_CS_견적서_실원가용_250910.sql`(987줄, 정본) · `SP_CS_견적서_내부용_250704.sql` · `SP_CS_견적서_BOM_250613.sql` · `SP_CS_견적리스트_실원가용.sql`.
> 화면: w_cs_esti_010(견적원가조회) · w_cs_esti_020(견적원가손익금액) → 웹 `SCREEN.costanalysis`(품목별 원가분석).
> 호출: `EXEC [SP_CS_견적서(실원가용)_250910] @ITEM_CODE, @YMD(YYMMDD)`. 분석일 2026-07-22. 관련 [MIGRATION_ISSUES.md] §D.

---

## 0. 실원가 정의
**실원가(TOT_AMT) = 재료비(JAI) + 가공비(GAGONG) + 일반관리비(ILBAN) + 운반비(UNBAN) + 이윤(PROFIT)**
**손익 = LG_COST − TOT_AMT**. (실원가용=업체가 해온 실제공정만, 내부용=전공정 우리가 한다고 가정 → 가공비 내부≫실원가)

## 1. BOM 전개 (재귀 CTE_BOM)
- 앵커=대상품목(level 0). 재귀: `CS_M_ITEM_BOM b JOIN pr_m_item` where `ISNULL(CS_CALC_EXCEPT_FLAG,'0')<>'1'` AND 부모 `cost_gubun<>'5'`(직납이면 하위 안품).
- `cum_use_qty` = 상위누적 × 자기 use_qty (레벨 곱).
- `cum_mat_code` = 경로 문자열(레벨·bom_seq·mat_code 30자) — 롤업 LIKE 매칭 키.
- **INNER_PROD_FLAG(사내생산)**: `MAKE_TYPE='1'→1` / `MAKE_TYPE=''&(IN_CUST_CODE=''또는 PR_M_ITEM_PROC_GAGONG 존재)→1` / else `0`.
- **LME_CALC_FLAG**: 부모 사내(INNER_PROD=1)면 자식 LME대상(사급 소급차액).

## 2. 원소재 중량·단가
- **ITEM_WEIGHT** = `ROUND((ITEM_DIAM−ITEM_THICK)×ITEM_THICK×π×ITEM_LENGTH×GRAVITY/1,000,000, 4)` (DIAM>0). π=3.141592.
  - **GRAVITY(비중)** = `CM_M_MASTER_DETAIL[KIND_CODE='PR019', DETAIL_CODE=metal_gubun].OTHER_CHAR1` (예 CU=8.96).
  - ★중량은 **계산값**(마스터 저장값 아님). nx.item.net_weight와 반드시 대조.
- **WON_MAT_COST(원소재단가)** = `CS_M_METERIAL_COST.TOT_COST` by (metal_gubun, item_diam, item_thick, apply_yyyymm 최신 < '20'+YMD), WHERE weight>0.
- **WON_MAT_COST_SUB(사급차액단가)** = `TOT_COST − TOT_COST_SUB` (LG 절단재료비 − 협력사 절단재료비).

## 3. 매입/구매단가 (INNER_PROD=0 = 구매·외주완성)
- COST_GUBUN 조정: 구매품 → `'2'`. LEVEL0 & LME자식 다수 → `''`(하위전개).
- **MAT_COST** = `PR_M_ITEM_COST[item_code, cust_code=지정매입처, COST_TAG='1', COST_APPLY_YMD≤YMD 최신].ITEM_COST × 환율`.
  - 환율 = `FI_M_EXCHANGE.BAS` (USD/EUR/YEN, EXCH_YMD≤YMD 최신). KRW=1.
  - 지정매입처 = MAT_IN_CUST_CODE (원 주석엔 3개월 입고 최종업체 로직 있으나 **현재 주석처리**, in_cust 사용).
- 이 MAT_COST가 WON_MAT_COST를 대체.

## 4. ★재료비 JAI_COST (최말단 leaf만, BOTTOM_FLAG=1)
```
JAI_COST = ( COST_GUBUN='3' ? WON_MAT_COST × ITEM_WEIGHT × USE_QTY    -- 원소재(소재단가×중량)
                            : WON_MAT_COST × USE_QTY )                -- 구매품(단가×수량)
           + LME_CHA_AMT                                             -- LME차액 포함(25/06/30 이여지 요청)
```
- 조건: `COST_GUBUN>''` AND 자식없음(최말단). 상위레벨은 자식 SUM 롤업(×USE_QTY if UNIT='EA').
- **LME_CHA_AMT** = `WON_MAT_COST_SUB × ITEM_WEIGHT × USE_QTY` (weight>0, cust>'', LME_EXCEPT≠1). 상위 롤업. = 유상사급 LME 소급정산 차액.

## 5. 가공비 GAGONG_AMT (사내생산 INNER_PROD=1만)
- 공정별(`CS_T_ITEM_PROC`, PROC_CODE≠91/92/93) PROD_AMT:
```
PROD_AMT = CASE 공정 COST_GUBUN
  '3' → ROUND(LABOR_COST / PROD_UPH × WORK_QTY, 0)   -- 임율기반(시간)
  '7' → 0                                            -- 세척
  '8' → ITEM_WEIGHT × PROD_UPH × WORK_QTY            -- 중량기반
  '9' → PROD_UPH × WORK_QTY                          -- 적용율
```
  - LABOR_COST = `CS_M_LABOR_COST_RATE` 최신(≤오늘). 공정정렬 = `CS_M_PROC` (ITEM_LGROUP IN 대상그룹,'J').
- **GAGONG_AMT** = Σ(sort1~50 PROD_AMT) × (UNIT='EA'?USE_QTY:1). 상위 롤업.

## 6. 일반관리·운반·이윤 (공정 91/92/93)
- ILBAN_RATE=proc'91' PROD_AMT · UNBAN_AMT=proc'92' PROD_AMT(운반) · PROFIT_RATE=proc'93' PROD_AMT.
- **ILBAN_AMT** = `ROUND(ILBAN_RATE × (JAI_COST − LME_CHA_AMT + GAGONG_AMT), 0)`.
- **PROFIT_AMT** = `ROUND(PROFIT_RATE × (GAGONG_AMT + ILBAN_AMT), 0)`.

## 7. 집계·결과
- **TOT_AMT** = JAI + GAGONG + ILBAN + UNBAN + PROFIT (레벨 롤업 후 level 0).
- **LG_COST** = `PR_M_ITEM_COST[item, CUST_CODE IN ('1010','1020','1030'), as-of]` (LG 3사).
- **WON_JAI_AMT**(원자재)=Σ(leaf JAI, ITEM_SGROUP∈110/120/130/220)×UPPER_USE_QTY · **BU_JAI_AMT**(부자재)=SGROUP 230/910 · **SA_JAI_AMT**(사급)=SGROUP 310.

## 8. 레거시 테이블 → nx 이관 매핑 (엔진 소비)
| 레거시 | 용도 | nx | 비고 |
|---|---|---|---|
| CS_M_ITEM_BOM | BOM 전개 | bom_line | ✓(이관 클린) |
| PR_M_ITEM | 품목·MAKE_TYPE·SGROUP·spec | item | ✓ |
| CS_T_ITEM_PROC | 공정 WORK_QTY/UPH/COST_GUBUN | routing | ✓(갭 수정완료) |
| CS_M_METERIAL_COST | 원소재 소재단가 TOT_COST/SUB | price_metal | ✓ 행수, TOT_COST/SUB 컬럼 확인필요 |
| CS_M_LABOR_COST_RATE | 임율 | labor_rate | ✓ |
| CS_M_PROC | 공정정렬·그룹 | process_master | ✓ |
| FI_M_EXCHANGE | 환율 | fx_rate | ✓ |
| **PR_M_ITEM_COST** | **매입가·LG단가**(cost_tag/cust/시계열) | price_item? | ⚠ 커버리지 검증필요 |
| **CM_M_MASTER_DETAIL PR019** | **비중 GRAVITY** | ? | ⚠ 미이관 의심 |
| **PR_M_ITEM_PROC_GAGONG** | INNER_PROD 판정 | ? | ⚠ 미이관 의심 |
| PR_M_ITEM_SUB | PIPE_KIND | - | 참고 |

## 9. 검증 상태 (nx 엔진 재현)
- v1(nx_cost_engine.py): 매입서브 경로 정확(AJR75563503 재료 21,226.7=오라클). **원소재(§4 COST_GUBUN='3' 중량기반) 미구현 → 표본 10%**.
- v2 TODO: §2~4 원소재·LME 반영, §3 매입가 PR_M_ITEM_COST/price_item 정합, §5~7 가공·overhead. 게이트=오라클(cost_oracle.py) diff0.
