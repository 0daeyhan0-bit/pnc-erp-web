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

## 3. 노드별 [수정] → 공정 등록/수정 팝업 = 품목BOM관리 '내부원가' 팝업과 **완전 동일 창**

> ★2026-08-05 재작업: 이전 축약 팝업(`nodeProcModal` 자체 렌더 — 관경 일부·조립공정만·+관경 행추가식)을 **제거**하고,
> 품목BOM관리(SCREEN.unifybom)의 `naeProcModal`과 **같은 모듈레벨 공유 렌더러**를 쓰도록 통합. 두 화면 팝업이 코드·픽셀 동일.

### 공유 렌더러 (js/screens.dev.js 모듈레벨, 양 SCREEN 클로저 밖)
- `PROC_MODAL_HTML(pd)` — 팝업 본문 HTML. pd 캐노니컬:
  `{node,title?,subtitle?,isAssy,weldDiams:[{pipe_diam,std_use_qty,std_st}],weldItem,weldTypes,weldCounts:{diam2dp:count},cols:[{name,code,sec,idx,uph,cg,wq}],infoBar?,footNote?}`.
  헬퍼는 `esc`(전역)만 의존, `M2/CALCG/fmtU` 자체 내장. DOM/클래스/컬럼구성 = naeProcModal과 100% 동일.
  - (상) **관경별 용접 매트릭스**: 전체 관경 컬럼(weld_diam **14**개: 4.76~38.10) 가로 나열. 행 5개 = 표준소요량/표준공수/**용접횟수(input .wm-q)**/소요량/내부ST. 용접봉종류 `#wm-type` select. 소요량=Σ(표준소요량×횟수)(표시, BOM반영 ×1.5), 내부ST=Σ(표준공수×횟수).
  - (하) **공정별 (작업 ST 입력)**: 전체 공정 2단(band) 가로 그리드. cols=`own`(가공)+`assy`(조립). 행 = 구분/작업ST(input .pq data-sec/data-i)/내부UPH(ro)/임율·구분(ro).
- `PROC_MODAL_BIND(c,{onClose,onSave,onProcInput,onProcCommit,onWeldCount,onWeldType})` — 이벤트 바인딩(콜백으로 각 화면이 자기 상태에 write-back).
- `PROC_MODAL_CSS` — `.wm` 매트릭스 CSS(naeCss와 동일 규칙). subvariant draw에 주입(unifybom은 naeCss가 이미 포함).

### 품목BOM관리(unifybom) 측
- `naeProcModal()` = naeProcD → pd(cols=`own` 가공 + `carriers[0].rows` 조립, sec='own'/'c0') → `PROC_MODAL_HTML(pd)`.
- `wireProcModal()` = `PROC_MODAL_BIND`(onProcInput→work_qty 세팅, onWeldCount→weldCounts+draw, onWeldType→weldPoints 재매핑) + 레거시 .pu/.pl(현재 no-op) 보존. **저장(cost/proc·weld/save) 동작 불변**.

### 조달후보(subvariant) 측 — 데이터 어댑터
- 전체 공정 카탈로그: **`GET /api/cost/proc/get?node=<ASSY>` 재사용**(ASSY 기준 1회 캐시 `st.procCat`). catalog→own(is_assy=false 24)+assy(is_assy=true 24). uph/cg는 ASSY 라우팅 참조(own_procs·carriers[0].procs).
- **프리필**: 그 노드의 저장값(route/detail `procs` where node_item=node)을 proc_code로 own/assy에 매핑.
  - 레벨0(ASSY)·미저장 → **BASE 조립 시드**(route/detail `asm_procs`).
  - 신규 SUB → **빈값**.
- 관경: `weldCounts` = 그 노드 저장 용접점(route/detail `welds` where node_item=node, pipe_diam→count). weldDiams=`st.weldDiams`(/api/weld/diam, 14).
- 상단 **infoBar**(추가): "이 노드 공수(절삭 자동귀속+조립 라이브) / 전체 공수합 / BASE ±차이" + 절삭 부품자동귀속 목록 + 용접ST. **레이아웃 본체는 동일**, info만 스크롤영역 최상단에 삽입.
- **저장**(그 노드만 교체): `weld/save`(weldCounts→행, loss 1.5) + `proc/node_save`(own+assy work_qty>0). BASE 게이트 없음(전체저장 finalize에서 검증). 승인 리셋. 저장 후 `loadRD`.
- 용접ST(가공비)는 용접공정 컬럼의 작업ST(시드/입력값)로 공수합에 1회 반영(내부원가 팝업과 동일 모델). 용접봉 소요량(재료)은 weld/save 별도(공수합 미포함).

### [해체] 버튼 (SUB 노드 전용, 2026-08-05 추가)
- nodeBox 헤더에 `dsub>0`(=SUB)일 때만 `[🧩 해체]` 표시(레벨0 ASSY엔 없음).
- confirm → `POST /api/sourcing/sub/dissolve {route_id,sub_line}` → reloadPanel. **백엔드는 기존 보강분**: 하위부품 parent_line=NULL(ASSY 복귀) + SUB 노드 비종속 공정/용접(node_item=SUB코드)을 ASSY로 이관(**공수합 보존**), 절삭은 부품 따라 자동유지.

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

## 6b. 공유 팝업 통합 검증 (2026-08-05 재작업, localhost:8010, AJR75563402)

- **JS 파싱**: esprima(ES2020 연산자 `??`/`?.` 다운레벨 후) `parseScript` PARSE_OK(275,470자) — 전체 문법 유효.
- **동일성 대조(핵심)**: 두 화면 팝업이 **동일 `PROC_MODAL_HTML`** 호출.
  - 관경 컬럼 = `/api/weld/diam` = **14** (4.76,5.00,6.35,7.94,9.52,12.70,15.88,19.05,22.00,25.40,28.00,31.75,34.90,38.10) — 양쪽 동일.
  - 공정 컬럼 = `/api/cost/proc/get` catalog = **48**(own 가공 24 + assy 조립 24), 2단 band(24+24) — 양쪽 동일(unifybom=own+carriers[0].rows, subvariant=own+assy, 같은 catalog 소스).
  - 용접 매트릭스 행 = 표준소요량/표준공수/용접횟수(input)/소요량/내부ST 5행 — 공유 렌더러라 구조 동일.
- **축약본 마커 제거 확인**: 서빙 JS에 `np.catalog·np.proc·np.weldRows·npWeldPrev·np-pq·np-wf·np-wtype·np-loss·np-wadd·np-wdel·np-x` **0건**(grep). `nodeProcModal`은 얇은 어댑터로만 잔존(PROC_MODAL_HTML 호출).
- **e2e**(route/copy base→detail→node popup 어댑터→weld/save→proc/node_save→detail→sub/create→sub/dissolve→finalize→cleanup):
```
[routes] existing=1 next_no=2
[route/copy base] route_id=54 route_no=2 lines=10
[detail] base_gongsu=43.0 asm_procs=5 part_cut_parts=3 route_parts=10 saved_procs=0
[BASE split] 절삭27.0 + 조립16.0 = 43.0 (=base_gongsu)
[node popup ASSY] cols=own24+assy24=48 · 관경14 · seed조립5건
[weld/save ASSY 19.05×2] rows=1 use_qty(재료)=0.0066 st(가공비)=46.0
[proc/node_save ASSY(BASE 조립 시드)] saved=5 node_gongsu=16.0
[detail#2] saved_procs=5 welds=1 cand=16.0
[sub/create 부품2] sub_item=AJR75563402_S05 moved=2
[sub/dissolve] freed=2 moved_proc=0 moved_weld=0  (공수합 보존)
[finalize commit] ok=True gongsu_ok=True part_ok=True cand=43.0=base=43.0 (cut27+proc16) parts=10/10 errs=[]
[cleanup route/delete] {'ok':True,'deleted':54}
```
- **원가 회귀**: 내부원가 AJR75563402 jae(재료)=4014.74 · gagong=1653.59 · naewon=6068.33 · proc 공수합=43 — 앵커 불변(원가엔진/백엔드 무수정, 프론트 리팩터만).
- **index.html** ?v=260805m → **260805n**. **백엔드 무변경**(openapi=317 유지). 어댑터는 기존 엔드포인트(cost/proc/get·route/detail·weld/save·proc/node_save·sub/dissolve)만 사용.

미완/주의(재작업분):
- 브라우저 실제 픽셀 렌더(두 팝업 나란히 눈 대조)·드래그는 **사용자 확인 필요**(구조·컬럼수·마커·파싱·백엔드 왕복은 자동검증 완료).
- subvariant 팝업의 가공(own 24) 컬럼은 대개 0(절삭=부품 자동귀속). 사용자가 own에 값 입력 시 finalize 게이트(Σpart_cut+Σroute_proc=BASE)가 이중계상을 차단.

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
