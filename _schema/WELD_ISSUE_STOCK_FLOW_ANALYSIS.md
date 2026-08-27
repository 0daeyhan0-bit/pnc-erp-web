# 용접봉 출고 & 생산 재고흐름 정밀분석 (검증기록)

작성 2026-08-27. 목적: "생산실적 잡으면 용접봉 −출고 / 실적 해제하면 +복원 / 재고없으면 실적차단"이 실제 도는지 검증. 결과=**반쪽결선(실질 미작동)**. 배경: 용접봉을 BOM→공정(proc_weld) 이전.

관련: [[newerp-stock-ledger-engine]] [[newerp-kitting-redesign]] [[newerp-weld-cost-split]] [[newerp-stock-gating-close-lock]] · 설계정본 `NX_STOCK_LEDGER_DESIGN.md`

---

## 0. 핵심 결론 (먼저)

**두 재고 시스템이 병존하고, 용접봉 백플러시 결선이 이력적으로 유실됐다.**

| 시스템 | 실체 | 용접봉 |
|---|---|---|
| **A. 레거시충실 미러** (procbc_save, 2026-08-19 이식) = **현재 배포·병행운영본** | nx 미러테이블만 씀: `nx.PR_T_STOCK_MAINT_MAT`(tag4 자재차감)·`PU_T_READY_STOCK_MAINT`(tagA 준비차감)·`SA_T_STOCK_MAINT`(tagP 완성입고) | **통째 제외**(Q1000/Q2000 "운영방침변경으로 처리안함") |
| **B. nx 단일원장** (backflush.py + stock_ledger Phase0~5, 2026-07-30) = **178 dev만·미배포** | `nx.stock_ledger`(STOCK_POINT MAT/RDY/PRD/ASY + tag W 용접봉)·백플러시엔진 | **엔진에 있음**(role='용접봉' RAC, tag W) 하지만 **procbc_save 자동트리거 배선 유실** |

**증거(실측 2026-08-27)**: `nx.stock_ledger`의 `tag='W'` = **0건**(백플러시 용접봉소비가 실제로 한 번도 안 돔). `_backflush_core`는 코드 전체에서 **수기 `/api/backflush/post` 1곳에서만** 호출. procbc_save(prodsheet.py:1045)는 `_backflush_core`를 **import만 하고 미호출(dead)**.

---

## 1. 현행 생산실적 저장 = procbc_save (레거시충실)

`/api/procbc/save` (prodsheet.py:1045, 레거시 w_pr_input_520.ue_save_after_sub 이식, 실측 UPDATE_WINDOW 3,351건). 8단계:
- ①~④ 항상: 스티커·용접시트detail·헤더·prod_dtl_proc
- ⑤~⑧ 마지막공정만: ⑤PR_T_PROD_DTL ⑥입고(제품+: 자재창고P/파트창고/ASSY 영업창고 SA_T_STOCK_MAINT tagP) **⑦BOM전개→파트별 자재차감(PR_T_STOCK_MAINT_MAT tag4)** ⑧준비재고차감(PU_T_READY_STOCK_MAINT tagA)
- **취소 = 수량 음수로 재호출 → 전부 반대적용 원복** (이미 구현됨, 레거시경로)
- **★⑦에서 Q1000/Q2000(용접봉창고) 명시제외** (prodsheet.py:1342·1361·1393). → 용접봉은 자재차감에서 빠짐.

∴ **현재 배포본**: 생산실적 저장/취소 시 용접봉 재고이동 **전무**. 게이팅도 레거시BOM게이트(prodsheet.py:1329~)만이고 용접봉 제외.

## 2. nx 백플러시 엔진 = backflush.py (엔진은 완비, 배선만 없음)

`_backflush_core`(backflush.py:114-193)는 3기능 완비:
- **−출고**: 완성공정 1회 전체BOM×생산량. 자재 −P4(RDY우선→MAT), **용접봉 −W**(tag W, STOCK_POINT MAT, base RAC, 투입공정 gpc), 생산품 +P7(ASY/PRD). (backflush.py:166-181)
- **용접봉 식별 = `nx.bom.role='용접봉'` + child RAC prefix** (sgroup 아님! backflush.py:30,48-50). base RAC로 집계(-접미사 제거). 사내한정 `_sanae`(외주는 사급출고tag5로 이미−, 이중차감방지).
- **게이팅**(mode=post, backflush.py:134-153): comps+**용접봉** 부족검사 → 부족시 `{ok:false, "자재부족으로 생산실적 불가"}` 반환. 가용정본=`_mat_avail`=nx.mat_stock_daily 최신(common.py:205). 커버리지=`_tracked`(mat_stock_daily 등록품목만).
- **reverse**(mode=reverse, f=-1.0): 부호반대 복원 + backflush_log state='reversed'.
- **멱등** ref_key + backflush_log. **INNER_PROD=1 사내만**.
- **★유일 호출자 = 수기 `/api/backflush/post`** (backflush.py:208). procbc_save·prodwrite 어디서도 미호출.

**line 208 주석 "재고부족 차단 안함"은 stale**(구버전 잔재) — 실제 코드 134-153은 차단함(2026-08-19 게이팅 확정, [[newerp-stock-gating-close-lock]]).

## 3. 용접봉 240 재분류는 이 흐름과 무관

backflush는 **role(nx.bom)만 읽고 sgroup을 안 읽음**(backflush.py sgroup 참조 0건). 240 소분류는 코드마스터/원가 material_split(240→부자재)에만 영향. **재고차감축(role)과 분리** → 240 재분류로 인한 백플러시 회귀 없음.

## 4. 용접봉 재고 위치 실측 (−출고 대상)

- **레거시 자재원장 `PU_T_STOCK_MAINT`**: 용접봉(RAC305993%) tag9 매입입고(+64,738)·tag5 사급출고(−20,192)·tag2·tagB 등. → 용접봉 재고는 레거시 자재수불에서 관리됨.
- **nx.mat_stock_daily**: RAC 용접봉 **14개만** 추적(=품목마스터 "사용중 14"와 일치). 게이트 커버리지 = 이 14개뿐(나머지 50 미추적 → 게이트 통과).
- **nx.stock_ledger tag W = 0건**: 백플러시 −출고 실적 전무.

## 5. 재고흐름 설계모델 (NX_STOCK_LEDGER_DESIGN, 2026-07-30 설계·178구현)

사장님 질문 "자재→생산 이동이 맞나 / 키팅 어떻게"에 대한 **이미 확정된 설계**:
- **3단 재고**: 자재(MAT) → 준비(RDY, 키팅) → 생산소비→ 완성(PRD/ASY).
- **키팅 = flag-only(자재 무차감·예약만)** [[newerp-kitting-redesign]]. 키팅확인=+RDY 예약, 자재는 안 깜.
- **자재차감 = 생산실적 백플러시 1곳** (−MAT/−RDY, +ASY/PRD). 키팅재고는 백플러시가 −RDY로 상쇄(현장 "재고조사때 키팅재고0" 일치).
- **용접봉 = 공정종속, 완성공정 1회 −W**. 회수율 미개입(소비는 use_qty×생산량).
- 이 전체가 2026-07-30 e2e PASS(자재입고→키팅→바코드완성실적 자동−RDY/−MAT/+ASY→출하−ASY). **단 localhost 178, 184 미배포. 그리고 2026-08-19 procbc_save 레거시재작성이 자동트리거 배선을 덮음.**

---

## 6. 갭 정리

1. **[치명] 자동트리거 배선 유실**: 2026-07-30 결선(procbc_save→_backflush_core)이 2026-08-19 레거시충실 재작성으로 사라짐. 현재 용접봉 −출고/복원/게이팅 실질 0.
2. **두 시스템 병존 미결**: 레거시미러(배포·병행운영) vs nx단일원장(dev). 어느 것이 재고정본인지 컷오버 결정 필요.
3. **게이트 커버리지 14개**: mat_stock_daily 추적 용접봉만. 나머지 미추적.
4. **mat_stock_daily 일스냅샷**: 당일입고/연속차감 미반영 → 실시간 자재정본 승격 선행(컷오버).
5. **소스 통일 미결**: 백플러시 용접봉소요=nx.bom qty. 로드맵은 proc_weld(용접ST×원단위) 전환([[newerp-weld-settlement-roadmap]]). 원가엔진은 이미 proc_weld 이관.
6. **협력사 용접봉 무게정산 연계 TODO** (backflush.py:190).

## 7. 설계 옵션 (결정 필요)

- **옵션1 (재배선)**: 현재 레거시충실 procbc_save에 nx 백플러시(용접봉 −W)만 얹기. 레거시미러는 그대로(용접봉 제외 유지) + nx.stock_ledger에 용접봉만 −W 결선. 용접봉은 레거시가 아예 안 다루니 이중차감 없음. **최소·안전**.
- **옵션2 (단일원장 활성화)**: nx 단일원장(자재·준비·용접봉 전부)을 생산실적 정본으로 승격. 2026-07-30 설계 전체 배포. 큰 결정(컷오버급).
- 공통 선결: 게이트 커버리지(용접봉 mat_stock_daily 적재)·실시간 자재정본·소스(bom vs proc_weld).

## 8. 검증 테스트 계획 (승인 후)

수기 `/api/backflush/post`로 엔진 3케이스 먼저 실증(공유 nx 오염방지=post후 즉시 reverse 또는 하네스 읽기전용):
- ① post: 사내 용접봉품목×수량 → nx.stock_ledger tag W −행 + backflush_log posted 확인
- ② reverse: +W 복원 + state=reversed, net0
- ③ gate: 가용<소요 → ok:false·행 0(rollback), 충분하면 통과. mat_stock_daily 미추적품은 게이트 통과(커버리지 한계 재현)
- 대상선정: `nx.bom role='용접봉' RAC` × `make_type='1'` 사내제작품, base RAC가 mat_stock_daily 추적.

## 9. ★엔진 검증 결과 (2026-08-27, 전부 롤백·nx무변경)

대상 `5211A21789C`(용접봉 RAC30599303 base, bom_qty 0.0028, 가용 180). `_backflush_core` 직접호출, cro=`_nx()`(★실엔드포인트도 _nx()를 cro로 넘김, backflush.py:204 — _conn 라이브 아님).

- **① POST(prod_qty=100)**: ok=True. nx.stock_ledger 5행 생성 = 자재 3×tag P4(−100) + **용접봉 tag W(MAT=RAC30599303, −0.28, gpc=Q1000)** + 생산품 tag P7(+100). backflush_log=posted. ✅
- **② REVERSE**: ok=True. 용접봉 W 순합=0.0(−0.28+0.28), log state=reversed. ✅
- **③ GATE**: qty=1e6 → ok=False "자재부족으로 생산실적 불가 — 용접봉 RAC30599303(가용 180 < 소요 2800)", 생성행 0(rollback). qty=10 충분 → 통과(−0.028). ✅

**결론: 엔진 3기능(−출고·복원·부족차단) 정확 작동. 유일 문제=procbc_save 미배선.** 옵션1(재배선) 안전성 실증.

## 10. ★검증이 드러낸 정합 이슈 (옵션1 필수 반영)

- **INNER_PROD 게이트**: `_is_inner_prod`(backflush.py:12)= make_type='1' **또는** PR_M_ITEM_PROC_GAGONG 보유. make_type='1'만으론 부족(사급회수·매입·직납 제외). cro는 `_nx()`여야 nx.item 조회 성공.
- **★재고 소스 분리(핵심 갭)**: 게이트 가용=`nx.mat_stock_daily`(레거시 일스냅샷) ≠ −출고 대상=`nx.stock_ledger`(tag W). → −W 소비가 mat_stock_daily에 반영 안 됨(같은날 반복생산시 소진 미감지). **옵션1 정확성 조건 = 용접봉 재고 단일소스**: (a) 게이트가 nx.stock_ledger 용접봉잔량(기초+ΣW) 읽기 or (b) 용접봉 기초재고 nx.stock_ledger 적재 + 실시간정본. 갭4와 동일 뿌리.
- **커버리지**: mat_stock_daily 추적 용접봉 14개만 게이트 적용, 나머지 통과.

## 11. ★1단계 구현·검증 (2026-08-27) — `_weld_backflush` 신규함수

옵션1(용접봉 −W만) 착수. 옆 세션 인계문서 `STOCK_CLOSE_HANDOFF.md` §2 규칙 준수 확인 후 진행.
- **신규 `backflush.py:_weld_backflush(cro,nx,item,qty,wo,mode,user,ref_key)`**: 용접봉 −W만(자재/생산품 미접촉·이중차감 없음). 게이트=`_mat_avail`(mat_stock_daily)·음수차단, 쓰기=stock_ledger tag W(base RAC·투입공정·사내한정 _sanae). 멱등=backflush_log ref_key(용접봉 네임스페이스). INNER_PROD=1만.
- **검증 3케이스 PASS**(전부 롤백·nx무변경, 대상 5211A21789C×100):
  - POST: 생성행 1개=**tag W만**(RAC30599303 −0.28 Q1000), 자재P4·생산품P7 **없음** ✓
  - REVERSE: W순합 0.0, log reversed ✓
  - GATE: qty=1e6 차단(가용180<소요2800)·행0, qty=10 통과 ✓
- **차단 헬퍼 정렬 후속**: `_neg_stock_msg`(옆 세션 feat/close-mgmt·main 미병합) 병합 시 게이트를 그걸로 교체. 현재는 `_mat_avail` 직접 비교(동일 정본·§2 부합).
- **남음(2단계)**: procbc_save 완성공정 훅(수량+ post / 수량− reverse). 생산실적 핵심경로라 결선 전 재확인.
