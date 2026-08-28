# 직거래 LME 판가연동 — dong_qty(동소요량) LG BOM 정교화 (★나중에 할 일)

> 작성 2026-08-28. **상태 = 분석·설계만. 미구현(나중에).** 현 프로그램은 정상 가동 중, 정교화는 후속.
> 하드룰: 라이브 dbo=RO(PR_M_ITEM_COST 대사만) · dev 검증 후 배포 · 원가 diff0 무관(dtrade는 판가 축).

## 0. 프로그램 개요 (이미 구현·가동 중)
**직거래 LME 월연동 판가** = 레거시 `w_tc_master_165/090` 수작업 판가등록의 자동화. 코드 `routers/dtrade.py`, 화면 개발>직거래 LME 판가연동(SCREEN in screens.dev.js), 로컬 8011 확인됨.

- **산식**: `판가(월) = base_item_cost + dong_qty × (LME월 − base_lme)`. 직거래LME만 매월 재계산, **사급정체(2월↓)는 base 고정**.
- **테이블(nx.dtrade_*)**:
  - `nx.dtrade_price`(마스터): item_code·cust_code·cost_tag(E/S)·**linkage(직거래LME/사급정체)**·**dong_qty(동소요량)**·**qty_src(LG392/역산)**·base_ym·base_item_cost·base_lme·main_flag·sagub_flag·item_desc
  - `nx.dtrade_lme_index`: apply_ym·lme_index(원/kg)
  - `nx.dtrade_price_ts`: 월별 계산결과(item_cost·mat_cost_calc)
  - `nx.dtrade_lg_price`: LG PO Price(판가 정본, LG 엑셀 업로드 `po_upload`)
- **엔드포인트**: /api/dtrade/lme·summary·recompute·list·compare(라이브 PR_M_ITEM_COST 대사)·po_upload·lg_compare(LG확정판가 대사)
- **규모**(2026-07): 직거래LME 3,012(LG392 164·**역산 2,848**)·사급정체(제외) 4,726.

## 1. 핵심 문제 = dong_qty 부정확 (역산)
- dong_qty 2,848건이 **qty_src='역산'**(판가에서 역산 추정) → 부정확.
- 실측 대조(2026-08-28): **4849A10047A 역산 dong_qty=0.0072 vs 실제 동중량 ~1.9522** (270× 오차). 다수 품목 역산이 LG BOM 실제와 크게 다름.
- → **LG BOM(권위 있는 LG 원본)으로 dong_qty를 정교화**하면 판가 연동이 정확해짐.

## 2. ★dong_qty 출처가 품목 유형별로 다름 (정교화의 핵심)
직거래(우리가 소재 직접구매) 판가 연동의 dong_qty = **"우리가 사는 동(직거래분)"의 중량**. AP(LG 사급동)는 LG가 주니 제외. 그런데 품목이 2유형:

| 유형 | 예 | 특징 | dong_qty 출처 |
|---|---|---|---|
| **① Tube Assembly류** | 4849A10047A | 하위에 Tube,Raw(matkl='MJU0631') 보유 | LG BOM **Supplier Tube,Raw 중량**(직거래분). AP(사급)분 제외 |
| **② 동 부품 자체** | 3A00375A Socket·3A00213H Tube,Distributor | EA 단위 동 절단품, **자기 자신이 동**(하위 Tube,Raw 없음) | 그 품목 **자체 동중량 = nx.item.net_weight**(우리 실측) 또는 원단위 weight |

- 실측: dtrade 직거래LME 1,452품목 중 LG BOM Supplier동 있음 1,006·AP동 있음 1,070·역산정교화대상(LG BOM有) 1,178. 샘플 3A00375A류(유형②)는 LG BOM Tube,Raw 없음(자기가 동).
- 역산이 이 ①②를 뭉뚱그려 부정확.

## 3. 미결 — 구현 시 결정할 것
1. **dong_qty 정교화 출처 확정**: (a)①=LG BOM Supplier Tube,Raw 중량 + ②=net_weight 결합(가장 정확) / (b)원단위 파일 weight를 정본으로 / (c)기타. → **사용자 결정 필요.**
2. **직거래 vs 사급 분리**: 혼재 품목(4849A10047A=AP1.594+Supplier0.36)에서 직거래분(Supplier)만 dong_qty에. LG BOM supply_type로 분리.
3. **매월 자동화**: LG BOM 버전관리(nx.lg_bom_ver, ver_from)로 point-in-time 반영 → 매월 dong_qty 자동 갱신 가능.
4. **역산 유지 fallback**: LG BOM/net_weight로 못 잡는 품목은 역산 유지.
5. 검증: 정교화 후 `/compare`(라이브 판가)·`/lg_compare`(LG확정판가) 일치율↑ 확인.

## 4. 연관
- 동 원소재 판정·버전관리 = `LG_BOM_VERSION_SAGUB_SOYO_DESIGN.md`(matkl='MJU0631'=Tube,Raw 통합·supply_type=사급(AP)/직거래(Supplier)·AL제외·nx.lg_bom_ver 버전).
- 소재단가(가격인상) = 절삭재료비 CS_M_METERIAL_COST(202605 인상전/202608 인상후) — dtrade는 판가 축(LME index 기반)이라 별개.
- 원단위(nx.lg_settle_unit) = 직거래/사급 동부자재 원단위(월별 수기관리, 검증 힘듦) — 이 프로그램이 그 판가연동을 자동화한 것.
