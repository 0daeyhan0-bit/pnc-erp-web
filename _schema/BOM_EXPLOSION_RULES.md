# BOM 전개(자재소요) 규칙 + 구동 필드 — 조달 프로파일 적용 정본

> 목적: 생산계획UPLOAD 자재소요(레거시 STEP5→6→7) 검증에서 규명한 **BOM 전개 규칙**과 그 규칙을 결정하는 **필드**를 전부 기록.
> **조달 프로파일(nx.sourcing_profile) 설계 시 이 규칙/필드를 받아서 적용**해야 함. 즉 "이 부품을 어떻게 전개하고, 자재소요/키팅/발주에 어떻게 넣을지"를 필드로 판정.
> 검증: 설계2건(용접봉·체결SUB) 제외 시 웹 vs 레거시 PR_T_PLAN_PART_MAT 수량 100%·총량 1.00000x. 세션 02b63e35(2026-07-24). [[newerp-plan-soyo-verify]] [[newerp-sourcing-profile]]

---

## A. 구동 필드 사전 (어느 테이블·컬럼이 무슨 규칙을 결정하나)

### PR_M_ITEM (품목 마스터) — 품목 자체의 성격
| 필드 | 값 | 전개/조달 규칙 | 조달프로파일 적용 |
|---|---|---|---|
| **MAKE_TYPE** | 1자체생산·2외주가공·3매입·4사급가공·5외주완성 | 생산 vs 조달 판별의 1차 기준 | 1=사내생산(부품전개)·3매입(구매)·2/4/5외주(가공처+사급) |
| **IN_CUST_CODE** | 가공처 코드(예 대원산업) | 어디서 가공/완성되나(사급 목적지) | 외주/사급의 공급처 = 프로파일 vendor |
| **WORK_CODE** | 내부작업장 | mat_work_center = work_code>''? work_code : in_cust | 내부공정 라우팅 |
| **ITEM_SGROUP** | 910=용접봉/잡자재 | **★sgroup=910(용접봉)은 자재소요 BOM에서 제외=공정처리**(CS_T_ITEM_WELD로 별도 산출) | 용접봉은 조달아님·용접엔진 |
| **PROD_RATE** | 수율% | plan_qty = CEILING(plan×use×prod_rate/100) | 소요량 보정 |

### PR_M_ITEM_BOM (BOM 라인) — 부모-자식 관계·전개 제어
| 필드 | 값 | 전개 규칙 | 조달프로파일 적용 |
|---|---|---|---|
| **USE_QTY** | 소요량 | cum_use_qty = 누적 × use_qty | 소요 배수 |
| **EXCEPT_FLAG** | 1=제외 | 1이면 이 BOM 라인 전개 안함 | 전개 제외 |
| **KITTING_FLAG (KIT)** | 0/1 | **★KIT=0=생산품(자재/키팅 대상 아님, 관통)·KIT=1=자재/키팅 대상**. 예 "체결-SUB"(KIT=0)는 우리가 생산→그 부품(KIT=1)만 자재소요 | 조달/키팅 대상 여부의 핵심 마커 |
| **SAGUB_FLAG** | 0/1 | 사급 여부(유상사급 부품 표시) | 사급 판정 |
| **VIR_ITEM_FLAG** | 0/1 | 1=가상도번(p_item_code 승계, 가공공정 산출서 제외) | 가상노드 처리 |
| **GAGONG_PROC_CODE / WH/IN_GAGONG_PROC_CODE** | 공정코드 | 파트별 가공공정 | 공정 라우팅 |

### PR_M_ITEM_PROC_GAGONG + PR_M_WORK_SINGLE + PR_M_PROC_GAGONG (가공공정)
| 필드 | 전개 규칙 |
|---|---|
| **PROC_SEQ / S_WORK_CODE / GAGONG_PROC_CODE** | 부품이 **가공공정을 보유하면 PART_DTL 진입**(공정전이지점만). ★PART_DTL 진입 = STEP7 재귀 **사급중단점** |
| **GC_GUBUN** | 'P'면 anchor(proc_seq=1, cust_flag=0)를 최종필터 `NOT(cust=0 AND gc=P)`로 제외 |
| **in_cust in ('','2228')** | 내부가공(공백 또는 제이에스2228)만 GAGONG_TEMP 포함. 외주/사급 가공처는 제외 |

### PR_M_MODEL_BOM / _EXCEPT (모델→ASSY)
| 필드 | 규칙 |
|---|---|
| MAKE_YMD ~ TO_APPLY_YMD | 유효일자(plan_ymd가 이 사이) |
| **PR_M_MODEL_BOM_EXCEPT** | **★신규모델생성(STEP M) "새 매핑 생성금지" 전용. 모델→ASSY 전개(STEP5)에는 적용 금지!** (적용하면 대원 외주완성 서포터 EXCEPT=1을 드롭→사급부품 누락) |

---

## B. 전개 알고리즘 규칙 (레거시 STEP5→6→7 정본)

1. **STEP5 LOT합산**: 계획을 **(제번, 모델) 단위로 SUM(plan_qty)** 후 전개. 일별 출하분할(예 355+145)을 **생산LOT(500) 하나로 합쳐서** CEILING. ★건별 CEILING하면 +8/+1씩 초과(용접봉·나사 잔차 원인). 레거시 STEP0 "같은제번 LOT 사전합산".
2. **모델→ASSY**: 유효일자 내 후보 중 make_ymd 최대 1건. **EXCEPT 미적용**. 없으면 주문(sa_t_recv_dtl) fallback.
3. **STEP6 10레벨 BOM전개**: PR_M_ITEM_BOM(except≠1, level<10, pr_m_mat제외[현재 빈테이블]), cum_use_qty=×use_qty. 가공공정 보유 부품만 PART_DTL(공정전이지점: gagong_proc_code≠직전proc).
4. **STEP7 사급중단**: 재귀 중 자식이 **PART_DTL에 존재(=가공공정 보유, 별도계획됨)하면 재귀중단**. 앵커=PART_DTL(proc1)∪ITEM_DTL(NOT EXISTS PART_DTL).
5. **중복 가공처 제거**: `charindex('||'+work_center+'||', 누적가공처체인)=0` (조상에 같은 가공처면 컷).
6. **최하위 집계**: 같은 자재(bom_mat_code)는 **가장 깊은 레벨만** 유지. part_plan_qty = SUM(part_plan_qty × cum_use_qty).
7. **용접봉 제외**: sgroup=910은 자재소요서 제외(공정처리). PART_PLAN_QTY는 weld엔진(CS_T_ITEM_WELD·CS_M_WELD_DIAM)으로 별도.
8. **자체생산 중간품(체결-SUB) 제외**: KIT=0·make=1 중간노드는 자재소요 아님(생산품). 그 부품(KIT=1)만. 레거시는 이걸 이중방출(버그).

---

## C. 조달 프로파일이 받아야 할 규칙 (설계 연결)

조달 프로파일(nx.sourcing_profile)은 품목/BOM라인별로 다음을 **필드에서 받아** 판정·오버레이:
- **전개 여부**: EXCEPT_FLAG, KITTING_FLAG(KIT=0 관통), sgroup910(용접봉 제외)
- **조달 방식**: MAKE_TYPE(자체/매입/외주/사급) → 공급처 후보(IN_CUST_CODE·프로파일 vendor)
- **사급 판정**: SAGUB_FLAG + 가공공정 보유(PART_DTL) → 사급중단점
- **소요 산정**: USE_QTY 누적 × PROD_RATE, LOT합산 후 CEILING
- **공급처 배분**: 프로파일의 유효기간·배분비율(현행 100% 기본)

→ 즉 조달 프로파일은 이 필드들을 **입력으로 받아 "이 부품을 어느 공급처에서·사급으로·얼마나·언제" 조달할지**를 결정. BOM 전개는 소요(얼마나 필요)를, 프로파일은 공급(어디서 어떻게)을 담당. [[newerp-proc-sourcing-weld-model]] [[newerp-install-product-consignment]]
