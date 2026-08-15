# ★실제 ASSY가 SUB코드로 가려지던 문제 — 규명·수정·정리 (필독)

> 작성: 2026-08-15 (세션 634b8f52). 담당이 지목(AJR30125501)한 "실제 ASSY를 SUB로 바꾼" 문제의 전체 규명.
> 관련: [[BOM_MIRROR_DEBT_AND_DIFF0_PRINCIPLE]] · [[SUB_RECOMPOSE_DESIGN]] · [[BOM_STRUCTURE_CANON]] · 메모리 [[newerp-sub-name-registry]]

---

## 0. 한 줄 결론

**BOM 트리 표시 로직이 "하위를 가진 자식"을 무조건 `{부모}_S{nn}` SUB코드로 개명해서, 자기 품번·도면이 있는 실제 제품(예 AJR30125501)까지 가려버렸다.** 데이터(nx.bom_line)엔 실제코드가 그대로 있었고 **표시만의 문제**. → 실제 제품코드는 개명하지 않도록 수정(2026-08-15).

**원칙: 자기 품번·도면이 있는 실제 ASSY에는 SUB코드(`_S{nn}`·전역 S#####)가 붙으면 안 된다.** SUB코드는 우리가 만든 합성/변형 SUB(`base-N-N`·`_S`)에만.

---

## 1. 증상 (담당 지목)

- 품목BOM관리 **라우팅 탭** 트리에서 `AJR30125601`(Tube Assembly,Expansion) 아래 자식이 `AJR30125601_S08`, `_S10` 등으로 표시됨.
- 실제로 그 자리는 **AJR30125501 / AJR30125502**(Tube Assembly,Solenoide) — **자기 품번과 도면이 있는 실제 제품**.
- 담당은 **도면(품번 AJR30125501)을 보고** 대조해야 하는데, 화면이 `AJR30125601_S08`로 가려서 대조 불가.

## 2. 규명 (데이터는 정상, 표시가 문제)

- `nx.bom_line`의 AJR30125601 직접자식: seq3=**AJR30125501**, seq4=**AJR30125502** (실제코드 그대로 저장, node_type=서브ASSY).
- `AJR30125601_S08`은 **어디에도 저장 안 됨**(bom_line·sub_variant_map·sub_registry 전부 0) → **트리 렌더링이 실시간 생성**.
- 원인 코드 = `backend/routers/bom.py` `_bom_tree_nx()` 의 `subdisp()`:
  ```python
  def subdisp(child):
      if child in edges:                 # 하위 보유 = SUB로 간주(무조건)
          sub_map[child] = f"{item}_S{sub_seq:02d}"   # ← 실제 제품도 개명
          return sub_map[child]
      return disp(child)
  ```
  "자식이 하위를 가지면 무조건 `{부모}_S{nn}`" → 실제 제품(자기 BOM 보유)도 싸잡음. (2026-08-13 "SUB표시=ASSY품번+순번" 확정 규칙의 부작용)
- 추가: 이 실제 제품들이 **전역 S코드**도 받음 (AJR30125501→S00683, AJR30125502→S00685; sub_registry/sub_code_map).

## 3. 수정 (2026-08-15, 적용·검증 완료)

`bom.py` `subdisp()` — **깨끗한 실제 제품코드(접미사 `-`/`_` 없음)는 개명 금지, 합성/변형 SUB만 `_S{nn}`**:
```python
def subdisp(child):
    if child in edges:
        if ('-' not in child) and ('_' not in child):   # 실제 제품코드 → 도면과 동일하게 그대로
            return disp(child)
        if child not in sub_map:                          # 합성/변형 SUB만 _S{nn}
            sub_seq[0]+=1; sub_map[child]=f"{item}_S{sub_seq[0]:02d}"
        return sub_map[child]
    return disp(child)
```
**검증(AJR30125601 트리):** AJR30125501·AJR30125502 = 실제코드 그대로 표시 / `AJR30125601-3-1`(이젠터 SUB)·`AJR30125501-20-1`(썬텍 sub) = `_S01`·`_S07` 유지. `raw` 필드엔 원래 실제코드 항상 보존(네비/편집 무영향).

## 4. 스코프 (검토·정리 대상)

- **깨끗한 코드인데 item_type=서브ASSY = 1,344종** (실제 ASSY가 SUB로 분류된 의심군)
  - 그중 sub_code_map S코드 부여 1,063종 · sub_registry 대표 880종.
- **상위(부모)가 25/01~ LG 출고 제품인 것 = 623종** ← ★우선 검토 (상위 품번 기준 매출로 롤업)
  - 산출 CSV: `_schema/real_assy_as_sub_LG.csv` (ASSY품번·품명·상위LG제품·상위LG매출수량·상위최근출고)
  - 판별: 깨끗한코드(접미사 `-`/`_` 없음) + item_type=서브ASSY + 조상이 LG제품(BFS 롤업). ★"자식 자체 LG출고"로 잡으면 내부조립품(AJR30125501)을 놓침 → **반드시 상위 품번 매출 기준**.

## 5. 남은 정리 (데이터, 승인 후)

1. **item_type 재분류**: 이들 실제 제품 = 서브ASSY → **완제품/제품**으로 교정.
2. **S코드 레지스트리 제외**: sub_code_map/sub_registry에서 실제 제품코드 제거(합성 SUB만 남김).
3. **판별 정밀화**: "접미사 `-`/`_` 없음" 휴리스틱 → 도면/독립생산/독립매출 등 근거로 보강(정당한 SUB 오검출 방지).

## 6. 원칙 (정본)

- **실제 제품(자기 품번·도면) = 실제 코드 유지.** SUB코드 부여·개명 금지.
- **SUB코드(`_S{nn}`·S#####) = 우리가 만든 합성/변형 SUB 전용**(base-N-N 변형, 도면 없는 그룹핑).
- 클린 모델(3축)에선 "SUB 역할"은 라우팅/구조에서 표현하고, 제품 정체성(품번)은 보존.
