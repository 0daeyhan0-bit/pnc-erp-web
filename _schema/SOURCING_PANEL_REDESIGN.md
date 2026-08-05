# 조달후보 SUB 재구성·공정 배치 패널 — 전면 재설계 (durable)

> 화면: `SCREEN.subvariant`(js/screens.dev.js) — "조달경로 통합검토"의 후보 상세 편집 안 패널.
> 백엔드: `backend/routers/sourcing.py`. 쓰기=nx(PARTNER_ERP_TEST3). 원가 diff0·용접봉(RAC) 항상 제외.
> 작성: 2026-08-05. 앵커 품목=AJR75563402 (base_gongsu=43 = 절삭27+조립16, 부품10종(RAC제외)).

---

## 1. 재설계 목적 / 이전과의 차이

| 구분 | 이전(드롭다운 배치) | 재설계(좌풀/우트리 + 노드팝업) |
|---|---|---|
| 부품 편집 | detailModal 안 "구성 라인" 표 + [라인추가] | **제거**. 좌측 부품 풀의 [✎]·[➕부품추가](lineModal 재사용) |
| SUB 묶기 | 부품 위에 부품 드롭 | 좌 풀 → 우 트리 **새 SUB존/기존 SUB** 드롭 |
| 공정 배치 | 조립공정별 "배치 노드" 드롭다운 + [공정배치 저장](proc/save, BASE게이트) | **제거**. 노드별 [수정] → 공정 팝업(노드 스코프) |
| 용접 | 별도 weldModal(공정셀 주입) | 노드 팝업 안 관경별 용접 매트릭스 통합 |
| 저장 | proc/save 1콜(BASE게이트) | 노드별 증분(proc/node_save·weld/save) + [전체 저장] 검증 3종 |

핵심 수정: **신규 SUB 팝업이 레벨0(ASSY) 공정값을 보여주던 버그 제거** — 노드 스코프로 신규 SUB는 빈값.

---

## 2. 레이아웃 (subPanel)

```
🧩 SUB 재구성·공정 배치   공수합 T/BASE = 절삭+조립 ✔/✖   [💾 전체 저장(검증)]
┌── 부품 풀(좌) ────────────┐  ┌── ASSY 계층 트리(우) ───────────────┐
│ [➕부품추가]                │  │ ▣ ASSY (레벨0)  노드공수 N  [수정]   │ ← 드롭타겟(data-sub=0)
│ ⠿ 품번 품명 ⚙절삭  [배지][✎]│  │   • 배치된 부품…                     │
│ …전 구성부품(RAC 제외)…    │  │ ▸ SUB _Snn (레벨1) 노드공수 N [수정] │ ← 드롭타겟(data-sub=line_id)
│                            │  │   • 배치된 부품…                     │
│  배지 = 레벨0·ASSY / SUB명 │  │ ➕ 새 SUB로 묶기 — 부품 드롭         │ ← sub/create
└────────────────────────────┘  └──────────────────────────────────────┘
```

- **좌 부품 풀**: 전 구성부품(RAC 용접봉 제외) 나열. 각 행에 현재 배치노드 **배지**(레벨0=ASSY / SUB코드 / 미배치), 절삭공정 배지(⚙, part_cut), 드래그 소스, [✎]=lineModal(부품 라인 직접수정).
- **우 ASSY 트리**: 레벨0(ASSY=routeTarget) 노드 + 레벨1 SUB 노드들. 각 노드 [수정]=공정팝업, 그 아래 배치된 부품 목록. 노드 박스 전체가 드롭 타겟.
- **기본 상태**: 열면 전 부품이 레벨0(parent_line=NULL)=ASSY 배치(flat=BASE와 동일).

### 드래그 규칙
| 동작 | 엔드포인트 |
|---|---|
| 좌 부품 → 우 SUB 노드(data-sub=line_id) | `part/assign` sub_line=line_id |
| 좌 부품 → 우 레벨0(ASSY, data-sub=0) | `part/assign` sub_line=0 (평면 복귀) |
| 좌 부품 → "➕ 새 SUB로 묶기" 존 | `sub/create` line_ids=[lid] (자동 _S{nn}) |
| 빈 SUB(부품 0) | `sub/dissolve` 자동소멸(reloadPanel) |

- **절삭 가공품(part_cut)을 SUB로 옮기면 절삭 ST가 그 SUB로 자동 귀속**: part_cut은 부품(child_item) 키이므로 저장 불필요 — 부품 배치 위치로 표시가 따라감. 공수합 게이트는 절삭 총합(BASE)을 항상 계상하므로 배치 위치와 무관.

---

## 3. 노드별 [수정] → 공정 등록/수정 팝업 (nodeProcModal · 노드 스코프)

- **노드 스코프 시드**:
  - 레벨0(ASSY)에 저장 공정 없음 → **BASE 조립 pool(asm_procs) 시드**(전체 조립부하 표시 → SUB로 옮긴 만큼 여기서 차감).
  - 저장 공정 있음 / 신규 SUB → **저장값(신규 SUB=빈값)**.
- **관경별 용접**(내부원가 팝업 재사용): 용접봉 종류 1개 선택 + 관경별 점수 입력.
  - 소요량(재료) = Σ(std_use_qty[관경]×점수)×loss(기본1.5, 수정가능).  ← nx.weld_diam 표준(MIN='01')
  - 용접ST(가공비) = Σ(std_st[관경]×점수).  → 용접공정(group='용접', 보통 51) work_qty로 반영(readonly).
- **공정별 작업ST**: 조립 공정 카탈로그(asm_procs) 2단(band) 배치. 용접=관경별 자동, 나머지 직접입력. 단가/UPH/임율은 읽기전용(마감때만). 절삭공정은 부품 자동귀속(읽기전용 참조).
- **워크플로우 지원**: 팝업 상단에 "이 노드 공수 / 전체 공수합 N / BASE (±차이)" 항상 표시 → SUB에 입력 후 레벨0 팝업에서 그만큼 차감(총합 유지).
- **저장**: `weld/save`(용접봉 소요량=재료·node 스코프 전체교체) + `proc/node_save`(조립ST=가공비, 용접ST 포함, node 스코프 전체교체). 승인 리셋. **BASE 게이트 없음**(전체저장에서 검증).

---

## 4. 전체 저장 검증 3종 (순서·게이트)

프론트 `finalizeRoute(rid)`:
1. **신규 SUB 중복검사** — `GET sub/match?route_id` → 이 후보 각 SUB(부품셋+공정공수)가 기존 SUB(다른 후보/이 후보 포함)와 동일(부품 child_item 셋 RAC제외 일치 AND {proc_code:round(wq,2)} 일치)한지. 코드가 다른 동일 SUB만 반환. 각 매치마다 `confirm("동일한 서브가 존재합니다(코드). 그 서브를 사용하시겠습니까?")` → 예 → reuse_map[sub_line]=기존코드.
2. **공수합 = BASE(diff0)** — `POST route/finalize`: Σ(part_cut BASE 절삭) + Σ(sourcing_route_proc 전노드 조립) vs `_base_gongsu`(내부원가 proc_grid). |차|<0.5.
3. **부품수 = BASE** — route 라인 부품(node_kind≠SUB, RAC제외) child_item 셋 == `_base_flat_lines` 부품 셋. missing/extra 목록화.

- finalize(commit=1): reuse_map 적용(라인 child_item/sub_item + sourcing_route_proc/weld node_item 교체) → 게이트 2·3 검사 → **통과 시 commit, 실패 시 rollback(변경 취소)+errors**.
- 라인/공정은 증분 저장돼 있으므로 finalize=reuse 반영 + 게이트 통과 확정.

### SUB 채번 규칙
- 신규 SUB = `_S{nn}`(언더스코어·제로패딩2). `sub/create`가 nx.item+라이브 PR_M_ITEM의 `base_child_S\d` 최대번호+1(충돌 회피). 후보=`_R{nn}`(불변).

---

## 5. 엔드포인트 (신규 3 · 재사용 기존)

신규(sourcing.py):
- `POST /api/sourcing/proc/node_save` {route_id,node_item,procs:[{proc_code,work_qty,prod_uph,calc_gubun}]} → (route_id,node_item)만 전체교체. BASE게이트 없음. 승인 리셋. {ok,saved,node_gongsu}.
- `GET  /api/sourcing/sub/match?route_id` → {ok,matches:[{sub_line,sub_item,member_count,match_code,match_route_id}]}.
- `POST /api/sourcing/route/finalize` {route_id,item_code,ymd?,reuse_map?{sub_line:code},commit?} → {ok,gongsu_ok,part_ok,cand_gongsu,base_gongsu,cut_sum,proc_sum,base_part_count,route_part_count,missing,extra,reused,committed,errors}.

재사용 기존: `route/copy`(source=base), `route/detail`(lines·procs·welds·part_cut·asm_procs·base_gongsu), `sub/create`, `sub/dissolve`, `part/assign`, `weld/save`(노드 스코프), `line/save`·`child/new`(부품풀), `route/delete`.

스키마: nx.sourcing_route_proc(node_item 스코프)·nx.sourcing_route_weld(node_item 스코프) **기존 그대로**(`_ensure_route_tbl` 멱등, 신규 컬럼/테이블 없음).

### 공수 회계(이중계상 방지)
- 전역 공수합 = Σ(part_cut 전부, BASE·배치무관) + Σ(sourcing_route_proc 전노드).
- 용접ST는 **sourcing_route_proc의 용접공정(51) work_qty로 1회만** 계상(관경별 용접 매트릭스 Σstd_st). 용접봉 소요량(재료)은 sourcing_route_weld에 별도(공수합 미포함).
- part_cut은 sourcing_route_proc에 저장하지 않음(BASE 자동귀속·표시전용).

---

## 6. 검증 결과 (2026-08-05, localhost:8010, AJR75563402)

py_compile OK · openapi 314→**317**(+3) · 서빙 JS 마커 확인(sp-finalize/sp-nedit/sp-newsub/openNodeProc/nodeProcModal/proc\_node\_save/sub\_match/route\_finalize 존재, sp-psave/sp-asm/asmUI/st.asmNode 제거) · index.html ?v=260805m · JS 괄호밸런스 net 0/0/0(regex 인지 스캐너).

백엔드 e2e(route/copy base → detail → node_save → sub/create → node_save → sub/match → finalize):
```
[1] copy base → route 10라인
[2] detail: 부품(RAC제외)=10 base_gongsu=43.0 | part_cut 3노드 cut_sum=27.0 | asm 5(51용접5·52지그2·53교정1·55부품부착7·61포장1)=16.0 | cut+asm=43.0
[3] node_save ASSY 시드(BASE asm) saved=5 node_gongsu=16.0
[4] finalize(flat ASSY): ok=True cand=43.0=base=43.0(cut27+proc16) part_ok=True 10/10
[5] sub/create(부품2개) → AJR75563402_S02 moved=2
[6] 신규 SUB procs=0 (빈값) ✔  ASSY procs=5(값있음) ✔
[7] 용접(51) 1.0을 SUB로 이동 + ASSY 1.0 차감
[8] sub/match: matches=0
[9] finalize: ok=True 공수합 43.0=BASE 유지 ✔ (SUB입력+ASSY차감 워크플로우)
[10] NEG(SUB +5): ok=False committed=False 공수합48≠43 거부 ✔
[11] 복원 finalize commit: committed=True 43.0=43.0 ✔
[cleanup] route 삭제 + 번호 재사용 확인
```
원가 회귀: 내부원가 AJR75563402 jae(재료)=4014.74 gagong=1653.59 naewon=6068.33 proc공수합=43 — 앵커 불변(원가엔진/파일 무수정).

미완/주의:
- 브라우저 실제 드래그(픽셀 레벨 dnd)·팝업 렌더는 사용자 확인 필요(백엔드 왕복·서빙 마커·괄호밸런스까지 자동검증).
- SP 오라클(cost_oracle.py anchors)은 EXEC 권한 거부로 실행 불가 — 엔진값(위)로 대체 확인.
