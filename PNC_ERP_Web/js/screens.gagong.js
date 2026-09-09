/* ===== PNC ERP screens.gagong.js — 가공 SCREEN (app.js 분할, 순수이동) ===== */

/* ===== 생산 ⑥: 가공공정 파트별계획 (w_pr_input_510_new) — PR_T_PLAN_PART_MAT 가공/동파이프 뷰 ===== */
SCREEN.partplanproc=(c)=>{
  const API=API_BASE;
  const nf=n=>Number(n||0).toLocaleString('ko-KR',{maximumFractionDigits:0});
  const dcol=s=>(s&&(''+s).length===6)?`${(''+s).slice(2,4)}/${(''+s).slice(4,6)}`:s;
  const iso=x=>`${x.getFullYear()}-${String(x.getMonth()+1).padStart(2,'0')}-${String(x.getDate()).padStart(2,'0')}`;
  const T=new Date();
  // ★기준일 = 마지막 계획업로드의 일자축 첫날(planBaseIso, 2026-08-28 사용자 확정)
  const _pb0=planBaseIso(), _pbT=new Date(_pb0+'T00:00:00');
  let F={from:_pb0,to:iso(new Date(_pbT.getTime()+27*864e5)),wc:'',part:'',assy:'',diam:'',thick:'',pipe:'1'};
  let data={dates:[],rows:[],part_count:0,sum_qty:0}, wcs=[], loading=false, msg='';
  const loadWc=async()=>{try{const r=await fetch(`${API}/api/partplan/workcenters`);wcs=(await r.json()).rows||[];}catch(e){wcs=[];}};
  const load=async()=>{loading=true;draw();
    const qs=new URLSearchParams({from_ymd:F.from,to_ymd:F.to,wc:F.wc,part:F.part,assy:F.assy,diam:F.diam,thick:F.thick,pipe:F.pipe});
    try{const r=await fetch(`${API}/api/partplan/list?${qs}`);data=await r.json();msg='';}
    catch(e){msg='백엔드 연결 실패';data={dates:[],rows:[],part_count:0,sum_qty:0};}
    loading=false;draw();};
  const draw=()=>{
    const dates=data.dates||[];
    // 규칙17: 로드된 rows에서 자도번(값→품명표시)·지름·두께 datalist
    const gpPart=new Map(),gpDiam=new Set(),gpThick=new Set();
    (data.rows||[]).forEach(r=>{if(r.part&&!gpPart.has(r.part))gpPart.set(r.part,r.nm||'');if(r.diam)gpDiam.add(r.diam);if(r.thick)gpThick.add(r.thick);});
    const gpPartOpts=[...gpPart].map(([v,n])=>`<option value="${esc(v)}">${esc(n)}</option>`).join('');
    const gpDiamOpts=[...gpDiam].sort((a,b)=>a-b).map(v=>`<option value="${esc(v)}"></option>`).join('');
    const gpThickOpts=[...gpThick].sort((a,b)=>a-b).map(v=>`<option value="${esc(v)}"></option>`).join('');
    c.innerHTML=`
     <div class="page-title">⚙️ 가공공정 파트별계획 <span style="font-size:12px;color:var(--muted);font-weight:400">동파이프(지름·두께) 가공 파트 일자계획</span></div>
     <!-- ★배지 정정(2026-09-08) — 실제 소스는 nx(coopplan.py:37 PARTNER_ERP_TEST3.nx). 라이브 직독 아님. -->
     <div class="page-sub">협력사계획(<code>nx.PR_T_PLAN_PART_MAT</code>)을 가공 파트(동파이프) 단위로 지름·두께 포함 일자별 전개. 소스 nx</div>
     <div class="toolbar">
       <label class="tl">계획기간</label><input class="inp" type="date" id="gp-from" value="${F.from}"> ~ <input class="inp" type="date" id="gp-to" value="${F.to}">
       <label class="tl">자도번작업처</label><select class="inp" id="gp-wc" style="max-width:170px"><option value="">전체</option>${wcs.map(w=>`<option value="${esc(w.cc)}"${F.wc===w.cc?' selected':''}>${esc(w.nm||w.cc)} (${w.n})</option>`).join('')}</select>
       <label class="tl">동파이프만</label><input type="checkbox" id="gp-pipe"${F.pipe==='1'?' checked':''}>
       <button class="btn" id="gp-search">🔍 조회</button>
     </div>
     <div class="toolbar" style="margin-top:2px">
       <label class="tl">자도번</label><input class="inp" id="gp-part" list="gpp-partl" value="${esc(F.part)}" style="width:110px" placeholder="자도번/품명" autocomplete="off"><datalist id="gpp-partl">${gpPartOpts}</datalist>
       <label class="tl">지름</label><input class="inp" id="gp-diam" list="gpp-diaml" value="${esc(F.diam)}" style="width:60px" placeholder="지름" autocomplete="off"><datalist id="gpp-diaml">${gpDiamOpts}</datalist>
       <label class="tl">두께</label><input class="inp" id="gp-thick" list="gpp-thickl" value="${esc(F.thick)}" style="width:60px" placeholder="두께" autocomplete="off"><datalist id="gpp-thickl">${gpThickOpts}</datalist>
       <div class="spacer"></div><span class="rowcount">파트 <b>${nf(data.part_count)}</b> · 계획수량합 <b>${nf(data.sum_qty)}</b> · 일자 ${dates.length}개</span>
     </div>
     ${msg?`<div class="page-sub" style="color:#c0392b">⚠ ${esc(msg)}</div>`:''}
     <div class="grid-wrap" style="max-height:calc(100vh - 330px);overflow:auto;background:#fff;border:1px solid var(--line-2,#c9d3e0);border-radius:8px">
      <table class="tbl" style="font-size:11px"><thead><tr>
       <th>Assy도번</th><th>자도번</th><th>품명</th><th class="num">지름</th><th class="num">두께</th><th class="num">길이</th><th>작업처</th><th class="num">계</th>${dates.map(d=>`<th class="num">${dcol(d)}</th>`).join('')}</tr></thead>
      <tbody>${loading?spinRow(8+dates.length):((data.rows&&data.rows.length)?data.rows.map(r=>`<tr>
        <td>${esc(r.assy)}</td><td><b>${esc(r.part)}</b></td>
        <td class="bcap" title="${esc(r.nm)}" style="max-width:130px;overflow:hidden;text-overflow:ellipsis">${esc(r.nm)}</td>
        <td class="num">${r.diam?nf(r.diam):'·'}</td><td class="num">${r.thick||'·'}</td><td class="num">${r.length?nf(r.length):'·'}</td>
        <td class="center">${esc(r.wcnm||r.wc)}</td><td class="num"><b>${nf(r.tot)}</b></td>
        ${dates.map(d=>{const v=(r.days&&r.days[d])||0;return `<td class="num"${v?'':' style="color:#dfe6ef"'}>${v?nf(v):'·'}</td>`;}).join('')}</tr>`).join(''):`<tr><td colspan="${8+dates.length}" class="empty">조회 결과 없음</td></tr>`)}</tbody></table></div>`;
    const g=id=>c.querySelector(id);
    g('#gp-search').onclick=()=>{F.from=g('#gp-from').value;F.to=g('#gp-to').value;F.wc=g('#gp-wc').value;F.pipe=g('#gp-pipe').checked?'1':'';F.part=g('#gp-part').value;F.diam=g('#gp-diam').value;F.thick=g('#gp-thick').value;load();};
    ['#gp-part','#gp-diam','#gp-thick'].forEach(id=>g(id).onkeyup=e=>{if(e.key==='Enter')g('#gp-search').click();});
  };
  // ★계획 기준일 반영 후 조회 — 2026-08-28
  planBase().then(b=>{if(b&&b.iso){F.from=b.iso;
      F.to=iso(new Date(new Date(b.iso+'T00:00:00').getTime()+27*864e5));}}).catch(()=>{})
    .then(()=>loadWc()).then(load);
};

/* ===== 생산: 4주간 가공계획현황 (w_pr_outside_410_work) — 도번×라인×작업처, 자도번LIST 묶기 ===== */
SCREEN.gagongplan4w=(c)=>{
  const API=API_BASE;
  const nf=n=>Number(n||0).toLocaleString('ko-KR',{maximumFractionDigits:0});
  const dcol=s=>(s&&(''+s).length===6)?`${(''+s).slice(2,4)}/${(''+s).slice(4,6)}`:s;
  const iso=x=>`${x.getFullYear()}-${String(x.getMonth()+1).padStart(2,'0')}-${String(x.getDate()).padStart(2,'0')}`;
  // 배경이 어두우면 흰 글자(키팅완료 #669900 이 그 경우). 임계값 150 = 420·580 과 동일.
  const fgOn4=bg=>{const m=/^#([0-9a-f]{6})$/i.exec(bg||'');if(!m)return 'color:#222';
    const n=parseInt(m[1],16), L=(((n>>16)&255)*0.299+((n>>8)&255)*0.587+(n&255)*0.114);
    return L<150?'color:#fff':'color:#222';};
  const T=new Date();
  // ★기준일 = 마지막 계획업로드의 일자축 첫날(planBaseIso, 2026-08-28 사용자 확정).
  //   당일 기준이면 업로드 전날이 잡혀 미출하 재편성분과 재고 충당이 어긋난다.
  const _b0=planBaseIso(), _bT=new Date(_b0+'T00:00:00');
  const st={from:_b0,to:iso(new Date(_bT.getTime()+30*864e5)),wc:'P2',item:'',part:'',gigan:31,
            dates:[],rows:[],cnt:0,plan_sum:0,done_sum:0,note:'',loading:false,msg:'',exp:new Set()};
  /* ★컬럼 정의 — 항목보기(숨김·순서)를 쓰려면 <th>·<td> 를 하드코딩하지 않고
       정의에서 만들어야 한다(2026-09-06, 420·580 과 같은 구조).
       이 화면은 일자칸이 **맨 뒤**라 그룹이 하나뿐이다(앞그룹만). */
  const P4DEF={
    seq:{t:'SEQ',cls:'num', h:(r,i)=>`<td class="num">${i+1}</td>`, x:{w:40,al:'center',v:(r,i)=>i+1}},
    awc:{t:'자도번작업처',   h:r=>`<td class="center">${esc(r.awcnm||r.awc)}</td>`, x:{w:86,al:'center',v:r=>r.awcnm||r.awc||''}},
    line:{t:'라인',          h:r=>`<td class="center">${esc(r.line)}</td>`,        x:{w:48,al:'center',v:r=>r.line||''}},
    mwc:{t:'작업처',         h:r=>`<td>${esc(r.mwcnm)}</td>`,                       x:{w:96,al:'left',  v:r=>r.mwcnm||''}},
    assy:{t:'도번',          h:r=>`<td><b>${esc(r.assy)}</b></td>`,                 x:{w:118,al:'center',v:r=>r.assy||''}},
    jado:{t:'자도번LIST',    h:(r,i)=>{const js=(r.jado||'').length>44?(r.jado.slice(0,44)+'…'):(r.jado||'');
      return `<td class="jado-cell" data-i="${i}" title="${esc(r.jado)}&#10;클릭=자도번 펼치기" style="max-width:230px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;cursor:pointer;color:#1c66c9">${esc(js)} <span style="color:#8aa">(${r.matcnt})</span></td>`;},
      x:{w:230,al:'left',v:r=>r.jado||''}},
    lot:{t:'LOT수량',cls:'num',  h:r=>`<td class="num">${nf(r.lot)}</td>`,          x:{w:62,al:'right',v:r=>+r.lot||0}},
    matq:{t:'자재수량',cls:'num', h:r=>`<td class="num">${nf(r.matq)}</td>`,        x:{w:62,al:'right',v:r=>+r.matq||0}},
    finish:{t:'완료수량',cls:'num',h:r=>`<td class="num"${r.finish?'':' style="color:#dfe6ef"'}>${r.finish?nf(r.finish):'·'}</td>`,
      x:{w:62,al:'right',v:r=>(+r.finish||0)||''}},
    plan_qty:{t:'요청수량',cls:'num',h:r=>`<td class="num">${nf(r.plan_qty)}</td>`, x:{w:62,al:'right',v:r=>+r.plan_qty||0}},
    nm:{t:'품목정보',        h:r=>`<td class="bcap" title="${esc(r.nm)}" style="max-width:150px;overflow:hidden;text-overflow:ellipsis">${esc(r.nm)}</td>`,
      x:{w:150,al:'left',v:r=>r.nm||''}},
  };
  const P4_DEF=['seq','awc','line','mwc','assy','jado','lot','matq','finish','plan_qty','nm'];
  const P4_LS='p4w_colorder', P4_HIDE='p4w_hidecols';
  /* ★가변 배열로 둔다 — 항목보기 적용 시 제자리에서 고쳐야 draw() 한 번으로 새 순서가 보인다. */
  const P4_ORD=(()=>{try{const v=JSON.parse(localStorage.getItem(P4_LS)||'null');
    if(Array.isArray(v)&&v.length){const o=v.filter(k=>P4DEF[k]);
      P4_DEF.forEach(k=>{if(!o.includes(k))o.push(k);});return o;}}catch(_){}
    return P4_DEF.slice();})();
  const p4LoadHide=()=>{try{const v=JSON.parse(localStorage.getItem(P4_HIDE)||'[]');
    return new Set(Array.isArray(v)?v:[]);}catch(_){return new Set();}};
  let p4Hid=p4LoadHide();
  const p4Vis=()=>P4_ORD.filter(k=>!p4Hid.has(k));
  const p4Th=()=>p4Vis().map(k=>`<th class="${P4DEF[k].cls||''}" data-tk="${k}" title="우클릭 = 항목보기(순서·숨김)">${P4DEF[k].t}</th>`).join('');
  const p4Td=(r,i)=>p4Vis().map(k=>P4DEF[k].h(r,i)).join('');
  const load=async()=>{st.loading=true;draw();
    const qs=new URLSearchParams({from_ymd:st.from,to_ymd:st.to,wc:st.wc,item:st.item,part:st.part,limit:2500});
    try{const r=await fetch(`${API}/api/gagong/plan4w?${qs}`);const d=await r.json();
      st.dates=d.dates||[];st.rows=d.rows||[];st.cnt=d.cnt||0;st.plan_sum=d.plan_sum||0;st.done_sum=d.done_sum||0;st.note=d.note||'';st.msg='';st.exp.clear();}
    catch(e){st.msg='백엔드 연결 실패';st.dates=[];st.rows=[];st.cnt=0;}
    st.loading=false;draw();};
  const draw=()=>{
    const dates=st.dates;
    // UI규칙17: 자도번작업처·도번·자도번(자도번LIST에서 추출) autocomplete
    const wcS=new Map(),itS=new Map(),ptS=new Set();
    st.rows.forEach(r=>{if(r.awc&&!wcS.has(r.awc))wcS.set(r.awc,r.awcnm||r.awc);if(r.assy&&!itS.has(r.assy))itS.set(r.assy,r.nm||'');
      (r.jado||'').split(',').forEach(x=>{const m=x.split('{')[0];if(m)ptS.add(m);});});
    const wcOpts=[...wcS].map(([v,n])=>`<option value="${esc(v)}">${esc(n)}</option>`).join('');
    const itOpts=[...itS].map(([v,n])=>`<option value="${esc(v)}">${esc(n)}</option>`).join('');
    const ptOpts=[...ptS].sort().slice(0,400).map(v=>`<option value="${esc(v)}"></option>`).join('');
    // 합계
    let tLot=0,tMat=0,tFin=0,tReq=0;const dSum={};dates.forEach(d=>dSum[d]={dn:0,pl:0});
    st.rows.forEach(r=>{tLot+=+r.lot||0;tMat+=+r.matq||0;tFin+=+r.finish||0;tReq+=+r.plan_qty||0;
      dates.forEach(d=>{dSum[d].dn+=(r.done&&r.done[d])||0;dSum[d].pl+=(r.days&&r.days[d])||0;});});
    // ★colspan 은 실제 보이는 컬럼 수로 — 고정값(8)을 쓰면 항목 숨김 시 어긋난다(420·580 과 동일).
    const NC=p4Vis().length;
    const frac=(dn,pl,bg)=>{if(!pl&&!dn)return '<td class="num" style="color:#dfe6ef">·</td>';
      return `<td class="num" style="white-space:nowrap${bg?';background:'+bg+';'+fgOn4(bg):''}">${nf(dn)}/${nf(pl)}</td>`;};   // 날짜셀 색=완료상태(서버)
    c.innerHTML=`
     <div class="page-title">📋 4주간 가공계획현황 <span style="font-size:12px;color:var(--muted);font-weight:400">도번×라인×작업처 · 자도번LIST 묶음</span></div>
     <!-- ★배지 정정(2026-09-08) — 종전 '🔴 라이브' 는 사실이 아니었다.
          컷오버 커밋(5a9941d·03b06c0)이 백엔드를 nx 로 바꿨는데 부제만 그대로 남아
          "레거시 원본이라 믿을 수 있다" 는 오판을 부를 수 있었다.
          실제 소스 = PARTNER_ERP_TEST3.nx (gagong.py:523). 라이브 직독 아님. -->
     <div class="page-sub">계획원천 <code>nx.PR_T_PLAN_PART_DTL_FOR_CUST</code>(레거시 배치가 만드는 당일생성 스냅샷의 nx 사본). <b>도번=부품</b>·<b>자도번LIST=이 부품을 쓰는 부모 자도번들</b>. 첫 일자컬럼=당일이전 누적. 소스 nx
       <span style="margin-left:8px;font-size:11px">날짜셀 색(완료≥계획): <span style="background:#ffff00;padding:0 5px;border-radius:3px">생산완료</span> <span style="background:#fac090;padding:0 5px;border-radius:3px">출하완료</span> <span style="background:#669900;color:#fff;padding:0 5px;border-radius:3px">키팅완료</span></span></div>
     <div class="toolbar">
       <label class="tl">기준일자</label><input class="inp" type="date" id="p4-from" value="${st.from}">
       <label class="tl">기간</label><select class="inp" id="p4-gigan" style="max-width:78px">${[7,14,21,31,42,60].map(d=>`<option value="${d}"${st.gigan===d?' selected':''}>${d}일</option>`).join('')}</select>
       <label class="tl">자도번작업처</label><select class="inp" id="p4-wc" style="max-width:110px"><option value="P2"${st.wc==='P2'?' selected':''}>P2 가공</option><option value="P1"${st.wc==='P1'?' selected':''}>P1 용접</option></select>
       <button class="btn" id="p4-search">🔍 조회</button>
       <button class="btn" id="p4-col" title="컬럼 숨김·순서 (헤더 우클릭으로도 열림)">항목보기</button>
       <button class="btn xls" id="p4-xls" title="조회 결과를 화면과 같은 색상으로 엑셀 저장">엑셀</button>
     </div>
     <div class="toolbar" style="margin-top:2px">
       <label class="tl">도번</label><input class="inp" id="p4-item" list="p4-iteml" value="${esc(st.item)}" style="width:130px" placeholder="도번/품명" autocomplete="off"><datalist id="p4-iteml">${itOpts}</datalist>
       <label class="tl">자도번</label><input class="inp" id="p4-part" list="p4-partl" value="${esc(st.part)}" style="width:130px" placeholder="자도번" autocomplete="off"><datalist id="p4-partl">${ptOpts}</datalist>
       <div class="spacer"></div><span class="rowcount" id="p4-cnt">행 <b>${nf(st.cnt)}</b> · 계획합 <b>${nf(st.plan_sum)}</b> · 완료합 <b>${nf(st.done_sum)}</b> · 일자 ${dates.length}개</span>
     </div>
     ${st.note?`<div class="page-sub" style="color:#c0392b">${esc(st.note)}</div>`:''}
     ${st.msg?`<div class="page-sub" style="color:#c0392b">⚠ ${esc(st.msg)}</div>`:''}
     <div class="grid-wrap" style="max-height:calc(100vh - 340px);overflow:auto;background:#fff;border:1px solid var(--line-2,#c9d3e0);border-radius:8px">
      <table class="tbl fit p4tbl" style="font-size:11px;user-select:none"><thead><tr>
       ${p4Th()}
       ${dates.map(d=>`<th class="num">${dcol(d)}</th>`).join('')}</tr></thead>
      <tbody>${st.loading?spinRow(NC+dates.length):(st.rows.length?st.rows.map((r,i)=>{
        const ex=st.exp.has(i);
        return `<tr>
        ${p4Td(r,i)}
        ${dates.map(d=>frac((r.done&&r.done[d])||0,(r.days&&r.days[d])||0,(r.colors&&r.colors[d])||'')).join('')}</tr>
        ${ex?`<tr class="jado-exp"><td></td><td colspan="${NC-1+dates.length}" style="background:#f2f7ff;white-space:normal;padding:4px 8px;font-size:11px;color:#334">📦 자도번 ${r.matcnt}종: ${esc(r.jado).replace(/,/g,'&nbsp;· ')}</td></tr>`:''}`;
      }).join(''):`<tr><td colspan="${NC+dates.length}" class="empty">조회 결과 없음</td></tr>`)}</tbody>
      ${(()=>{if(!st.rows.length)return '';
        /* ★합계행도 정의 기반으로 — 종전엔 colspan="6" + 위치 하드코딩이라
             컬럼을 숨기거나 옮기면 합계가 엉뚱한 칸에 붙었다(580 과 같은 교정). */
        const TOT={lot:tLot,matq:tMat,finish:tFin,plan_qty:tReq};
        const vs=p4Vis();
        let lead=0; while(lead<vs.length && TOT[vs[lead]]===undefined) lead++;
        return `<tfoot><tr class="grandtot">${lead?`<td colspan="${lead}">합계 (${nf(st.cnt)}행)</td>`:''}
        ${vs.slice(lead).map(k=>`<td class="num">${TOT[k]===undefined?'':nf(TOT[k])}</td>`).join('')}
        ${dates.map(d=>`<td class="num" style="white-space:nowrap">${nf(dSum[d].dn)}/${nf(dSum[d].pl)}</td>`).join('')}</tr></tfoot>`;})()}
      </table></div>`;
    const g=id=>c.querySelector(id);
    g('#p4-search').onclick=()=>{st.from=g('#p4-from').value;st.gigan=+g('#p4-gigan').value;st.to=iso(new Date(new Date(st.from).getTime()+st.gigan*864e5));st.wc=g('#p4-wc').value.trim();st.item=g('#p4-item').value.trim();st.part=g('#p4-part').value.trim();load();};
    g('#p4-gigan').onchange=()=>{st.gigan=+g('#p4-gigan').value;st.to=iso(new Date(new Date(st.from).getTime()+st.gigan*864e5));g('#p4-search').click();};
    ['#p4-wc','#p4-item','#p4-part'].forEach(id=>g(id).onkeyup=e=>{if(e.key==='Enter')g('#p4-search').click();});
    c.querySelectorAll('.jado-cell').forEach(el=>el.onclick=()=>{const i=+el.dataset.i;st.exp.has(i)?st.exp.delete(i):st.exp.add(i);draw();});
    {const cb=g('#p4-col');
     if(cb)cb.onclick=e=>{e.preventDefault();e.stopPropagation();
       try{openColPick();}
       catch(err){console.error('[4주 항목보기]',err);
                  alert('항목보기를 열지 못했습니다: '+(err&&err.message||err));}};}
    {const xb=g('#p4-xls'); if(xb)xb.onclick=exportXls;}

    /* == 드래그 복사 (2026-09-06 — 410·420·580 과 같은 동작) ==================
         표를 끌어 사각영역을 고르고 Ctrl+C 로 클립보드에 넣는다(엑셀에 TSV 로 붙는다).
         ★이 화면은 전표발행 같은 셀 선택 로직이 없어 **모든 셀**이 복사 대상이다.
         ★HTML5 텍스트 선택과 부딪히므로 mousedown 에서 preventDefault +
           표에 user-select:none — 안 그러면 파란 블록만 생기고 영역이 안 잡힌다. */
    const tbl=c.querySelector('.p4tbl');
    const tb=tbl&&tbl.tBodies[0];
    if(tb&&!c.dataset.p4cp){
      c.dataset.p4cp='1';
      if(!document.getElementById('p4cp-css')){
        const stl=document.createElement('style'); stl.id='p4cp-css';
        stl.textContent='.p4tbl td.p4cp{outline:1px solid #93b4e6;outline-offset:-1px;'
          +'background-image:linear-gradient(rgba(219,234,254,.55),rgba(219,234,254,.55))}';
        document.head.appendChild(stl);
      }
    }
    if(tb){
      const rcOf=td=>({r:td.parentElement.rowIndex, c:td.cellIndex});
      let cdrag=false,_ca=null,_cells=null,_clast=null;
      const cpClear=()=>tb.querySelectorAll('td.p4cp').forEach(td=>td.classList.remove('p4cp'));
      const cpSnap=()=>{_cells=[...tb.querySelectorAll('td')].map(x=>{const q=rcOf(x);return {td:x,r:q.r,c:q.c};});};
      const cpRect=td=>{if(!_ca||!_cells)return;
        const b=rcOf(td);
        const r1=Math.min(_ca.r,b.r),r2=Math.max(_ca.r,b.r);
        const c1=Math.min(_ca.c,b.c),c2=Math.max(_ca.c,b.c);
        for(const it of _cells) it.td.classList.toggle('p4cp', it.r>=r1&&it.r<=r2&&it.c>=c1&&it.c<=c2);
        const n=tb.querySelectorAll('td.p4cp').length;
        const el=c.querySelector('#p4-cnt');
        if(el&&n&&!el.dataset.o){el.dataset.o=el.innerHTML;}
        if(el&&n)el.innerHTML=`복사선택 <b>${nf(n)}</b>칸 <span style="color:#7b8aa0">(Ctrl+C)</span>`;};
      tb.addEventListener('mousedown',e=>{
        if(e.button!==0)return;
        if(e.target.closest('.jado-cell'))return;        // 자도번 펼치기 클릭은 살린다
        const start=e.target.closest('td'); if(!start||!start.closest('tr'))return;
        e.preventDefault();
        if(!e.ctrlKey&&!e.metaKey)cpClear();
        cdrag=true;cpSnap();_ca=rcOf(start);_clast=start;cpRect(start);});
      tb.addEventListener('mousemove',e=>{if(!cdrag)return;
        if(!(e.buttons&1)){cdrag=false;_ca=null;_cells=null;_clast=null;return;}
        const el=document.elementFromPoint(e.clientX,e.clientY);
        const td=(el&&el.closest('td'))||_clast;
        if(td){_clast=td;cpRect(td);}});
      document.addEventListener('mouseup',()=>{cdrag=false;_ca=null;_cells=null;_clast=null;});
    }
    const selText=()=>{
      const map=new Map();
      c.querySelectorAll('td.p4cp').forEach(td=>{
        const tr=td.parentElement; if(!tr)return;
        if(!map.has(tr.rowIndex))map.set(tr.rowIndex,[]);
        map.get(tr.rowIndex).push([td.cellIndex,(td.innerText||'').trim()]);});
      return [...map.keys()].sort((x,y)=>x-y)
        .map(r=>map.get(r).sort((x,y)=>x[0]-y[0]).map(x=>x[1]).join('\t')).join('\n');
    };
    const toClip=(txt,what)=>{
      if(!txt){alert('복사할 영역을 먼저 끌어서 선택하세요.');return;}
      const done=()=>{const el=c.querySelector('#p4-cnt');
        if(el){const o=el.innerHTML;el.innerHTML=`<b style="color:#1c7c3a">${what} 복사됨</b>`;
               setTimeout(()=>{el.innerHTML=o;},1400);}};
      // ★비보안(http 운영 184)은 clipboard API 가 막히고 그 거부는 **비동기** —
      //   제스처(Ctrl+C) 밖에서 fb 가 돌면 execCommand 도 막혀 조용히 실패한다.
      //   ⟹ isSecureContext 가 아니면 처음부터 동기 fb()(2026-09-08).
      if(window.isSecureContext&&navigator.clipboard&&navigator.clipboard.writeText)
        navigator.clipboard.writeText(txt).then(done,()=>fb()); else fb();
      function fb(){   // 비보안 컨텍스트(http)는 clipboard API 가 막힌다
        const ta=document.createElement('textarea'); ta.value=txt;
        ta.style.cssText='position:fixed;left:-9999px;top:0';
        document.body.appendChild(ta); ta.focus(); ta.select();
        let ok=false; try{ok=document.execCommand('copy');}catch(_){}
        ta.remove();
        if(ok)done(); else alert('복사에 실패했습니다.');}
    };
    const copySel=()=>toClip(selText(),'선택영역');
    const copyAll=()=>{
      if(!tbl)return; const out=[];
      const hr=tbl.tHead&&tbl.tHead.rows[0];
      if(hr)out.push([...hr.cells].map(th=>(th.innerText||'').trim()).join('\t'));
      [...tbl.tBodies].forEach(b=>{for(const tr of b.rows)
        out.push([...tr.cells].map(td=>(td.innerText||'').trim()).join('\t'));});
      toClip(out.join('\n'),`전체 ${nf(out.length-1)}행`);
    };
    // ★Ctrl+C 는 document 에서 받는다 — 범위선택 mousedown 의 preventDefault 때문에
    //   c 에 포커스가 오지 않아 c.onkeydown 은 아예 안 불린다(2026-09-08, 420 과 동일 수정).
    c._p4CopySel=copySel;
    if(!c.dataset.cpkey){
      c.dataset.cpkey='1';
      c.setAttribute('tabindex','-1'); c.style.outline='none';
      document.addEventListener('keydown',ev=>{
        if(!((ev.ctrlKey||ev.metaKey)&&(ev.key==='c'||ev.key==='C')))return;
        if(!c.isConnected||!c.offsetParent)return;
        const t=ev.target;
        if(t&&(t.tagName==='INPUT'||t.tagName==='TEXTAREA'||t.tagName==='SELECT'||t.isContentEditable))return;
        if(!c.querySelector('td.p4cp'))return;
        ev.preventDefault(); if(c._p4CopySel)c._p4CopySel();});
    }
    /* 우클릭 메뉴 — ★실행도 mousedown 에서(410·420·580 과 같은 함정 회피:
       바깥클릭 닫기가 mousedown 이라 click 은 죽은 노드에 떨어진다). */
    c.querySelectorAll('.p4tbl thead th,.p4tbl tbody').forEach(el=>{
      el.oncontextmenu=e=>{
        e.preventDefault();
        const old2=document.getElementById('p4-ctx'); if(old2)old2.remove();
        const m=document.createElement('div'); m.id='p4-ctx';
        m.style.cssText=`position:fixed;left:${Math.min(e.clientX,innerWidth-170)}px;
          top:${Math.min(e.clientY,innerHeight-110)}px;z-index:1400;background:#fff;
          border:1px solid #cfd8e6;border-radius:6px;box-shadow:0 6px 20px rgba(20,40,80,.22);
          font-size:12.5px;min-width:150px;overflow:hidden`;
        m.innerHTML=['항목보기','선택영역 복사','전체 복사']
          .map((t,i)=>`<div data-i="${i}" style="padding:7px 12px;cursor:pointer">${t}</div>`).join('');
        document.body.appendChild(m);
        m.querySelectorAll('div[data-i]').forEach(d=>{
          d.onmouseenter=()=>d.style.background='#eef4ff';
          d.onmouseleave=()=>d.style.background='';});
        const kill=()=>{m.remove();document.removeEventListener('mousedown',outside,true);};
        const outside=ev2=>{if(!m.contains(ev2.target))kill();};
        setTimeout(()=>document.addEventListener('mousedown',outside,true),0);
        m.addEventListener('mousedown',ev2=>{
          ev2.preventDefault(); ev2.stopPropagation();
          const t=ev2.target.closest&&ev2.target.closest('[data-i]'); if(!t)return;
          const i=+t.dataset.i; kill();
          try{ if(i===0)openColPick(); else if(i===1)copySel(); else copyAll(); }
          catch(err){console.error('[4주 메뉴]',err);alert('실행 실패: '+(err&&err.message||err));}});
      };
    });
  };
  /* == 항목보기 (2026-09-06 — 420·580 과 같은 방식) ========================
       체크 해제 = 그 컬럼 숨김 · 행을 끌거나 ▲▼ 로 순서 변경.
       ★이 화면은 일자칸이 맨 뒤라 그룹이 하나다(앞쪽 컬럼만 다룬다). */
  const openColPick=()=>{
    const old=document.getElementById('p4-colpick'); if(old)old.remove();
    const hid=p4LoadHide();
    const ov=document.createElement('div');
    ov.id='p4-colpick';
    ov.style.cssText='position:fixed;inset:0;z-index:1300;background:rgba(20,32,54,.34);'
                    +'display:flex;align-items:center;justify-content:center';
    const item=k=>`<div class="p4cp-r" data-k="${k}"
         style="display:flex;align-items:center;gap:7px;padding:4px 8px;border-bottom:1px solid #eef1f6;
                cursor:grab;user-select:none;-webkit-user-select:none">
        <span style="color:#b6c2d4;font-size:11px" title="끌어서 순서 변경">⠿</span>
        <input type="checkbox" ${hid.has(k)?'':'checked'} data-ck="${k}">
        <span style="flex:1;font-size:12.5px">${P4DEF[k].t}</span>
        <button class="btn ghost p4cp-up" data-k="${k}" style="padding:0 6px;font-size:11px">▲</button>
        <button class="btn ghost p4cp-dn" data-k="${k}" style="padding:0 6px;font-size:11px">▼</button>
      </div>`;
    ov.innerHTML=`<div style="background:#fff;border-radius:10px;width:420px;max-height:78vh;
           display:flex;flex-direction:column;box-shadow:0 8px 30px rgba(20,40,80,.28)">
        <div style="padding:10px 12px;border-bottom:1px solid #e3e9f2;font-weight:700;color:#16305c">
          항목보기 <span style="font-weight:400;font-size:11px;color:#7b8aa0">체크 해제 = 숨김 · 행을 끌거나 ▲▼ 로 순서 변경</span></div>
        <div style="flex:1;overflow:auto;padding:4px 0">
          <div id="p4cp-l">${P4_ORD.map(item).join('')}</div>
          <div style="padding:6px 10px;font-size:11px;color:#7b8aa0">일자 컬럼은 항상 맨 뒤에 붙습니다.</div>
        </div>
        <div style="padding:9px 12px;border-top:1px solid #e3e9f2;display:flex;gap:6px;justify-content:flex-end">
          <button class="btn ghost" id="p4cp-reset">초기화</button>
          <div style="flex:1"></div>
          <button class="btn ghost" id="p4cp-x">닫기</button>
          <button class="btn" id="p4cp-ok" style="background:#1c47a0;color:#fff">적용</button>
        </div></div>`;
    document.body.appendChild(ov);
    const q=sel=>ov.querySelector(sel);
    /* ★모달 mousedown 은 **버블 단계에서만** 막는다(캡처 아님) — 캡처로 끊으면
         아래 행 드래그 핸들러까지 못 받는다(420 에서 실측한 원인). */
    ov.addEventListener('mousedown',e=>e.stopPropagation());
    ov.onclick=e=>{if(e.target===ov)ov.remove();};
    q('#p4cp-x').onclick=()=>ov.remove();
    const move=(k,dir)=>{const row=ov.querySelector(`.p4cp-r[data-k="${k}"]`); if(!row)return;
      const box=row.parentElement;
      const sib=dir<0?row.previousElementSibling:row.nextElementSibling;
      if(!sib)return;
      if(dir<0)box.insertBefore(row,sib); else box.insertBefore(sib,row);};
    ov.querySelectorAll('.p4cp-up').forEach(b=>b.onclick=()=>move(b.dataset.k,-1));
    ov.querySelectorAll('.p4cp-dn').forEach(b=>b.onclick=()=>move(b.dataset.k, 1));
    /* 행 끌어서 순서 변경 — ★HTML5 draggable 은 쓰지 않는다(텍스트 선택이 먼저 잡혀
         파란 블록만 생기고 드래그가 시작되지 않는다). 5px 이상 움직여야 '이동'이라
         같은 행에서 "클릭=체크토글 / 끌면=이동"이 공존한다. */
    let dK=null,dY=0,dMoved=false;
    const rowsOf=()=>[...ov.querySelectorAll('.p4cp-r')];
    const rowAtY=y=>{const rs=rowsOf(); if(!rs.length)return null;
      let best=rs[0],bd=1e9;
      for(const r of rs){const b=r.getBoundingClientRect();
        const d=(y<b.top)?(b.top-y):((y>b.bottom)?(y-b.bottom):0);
        if(d<bd){bd=d;best=r;}}
      return best;};
    ov.addEventListener('mousedown',e=>{
      const row=e.target.closest&&e.target.closest('.p4cp-r'); if(!row)return;
      if(e.target.tagName==='INPUT')return;
      if(e.target.closest('.p4cp-up,.p4cp-dn'))return;
      e.preventDefault();
      dK=row.dataset.k; dY=e.clientY; dMoved=false;
      row.style.opacity='.55';});
    const onMove=e=>{
      if(!dK)return;
      if(!ov.isConnected){dK=null;document.removeEventListener('mousemove',onMove);return;}
      if(!dMoved&&Math.abs(e.clientY-dY)<5)return;
      dMoved=true;
      const over=rowAtY(e.clientY);
      rowsOf().forEach(x=>{if(x!==over)x.style.borderTop='';});
      if(over&&over.dataset.k!==dK)over.style.borderTop='2px solid #2563eb';};
    const onUp=e=>{
      if(!dK)return;
      if(!ov.isConnected){dK=null;document.removeEventListener('mouseup',onUp);return;}
      const k=dK; dK=null;
      rowsOf().forEach(x=>{x.style.opacity='';x.style.borderTop='';});
      if(!dMoved)return;
      const over=rowAtY(e.clientY);
      if(!over||over.dataset.k===k)return;
      const src=rowsOf().find(r=>r.dataset.k===k); if(!src)return;
      const box=over.parentElement, sb=over.getBoundingClientRect();
      if(e.clientY < sb.top+sb.height/2) box.insertBefore(src,over);
      else box.insertBefore(src,over.nextSibling);};
    document.addEventListener('mousemove',onMove);
    document.addEventListener('mouseup',onUp);
    q('#p4cp-reset').onclick=()=>{
      try{localStorage.removeItem(P4_LS);localStorage.removeItem(P4_HIDE);}catch(_){}
      P4_ORD.length=0; P4_DEF.forEach(k=>P4_ORD.push(k));
      p4Hid=new Set();
      ov.remove(); draw();};
    q('#p4cp-ok').onclick=()=>{
      const no=[...ov.querySelectorAll('#p4cp-l .p4cp-r')].map(r=>r.dataset.k);
      const nhid=[...ov.querySelectorAll('input[data-ck]')].filter(x=>!x.checked).map(x=>x.dataset.ck);
      try{localStorage.setItem(P4_LS,JSON.stringify(no));
          localStorage.setItem(P4_HIDE,JSON.stringify(nhid));}catch(_){}
      P4_ORD.length=0; no.forEach(k=>P4_ORD.push(k));
      p4Hid=new Set(nhid);
      ov.remove(); draw();};
  };
  /* == 엑셀 (화면 색상 그대로) ============================================
       ★진짜 xlsx 로 내보낸다(core.js downloadXLS). HTML→.xls 는 엑셀이 서식(색)을 버린다.
       ★항목보기의 숨김·순서를 그대로 따른다 — "보이는 대로" 받는 것이 기대 동작이다.
       ★'10/10' 이 날짜로 바뀌던 문제는 downloadXLS 의 x:str 로 차단(core.js). */
  const _fgx=bg=>{const m=/^#([0-9a-f]{6})$/i.exec(bg||'');if(!m)return '';
    const n=parseInt(m[1],16), L=(((n>>16)&255)*0.299+((n>>8)&255)*0.587+(n&255)*0.114);
    return L<150?'#ffffff':'#222222';};
  const exportXls=()=>{
    if(!st.rows.length)return alert('조회 결과가 없습니다.');
    const dates=st.dates, vs=p4Vis(), HB='#ffffff';
    const cols=vs.map(k=>({h:P4DEF[k].t,w:P4DEF[k].x.w,bg:HB}))
      .concat(dates.map(d=>({h:dcol(d),w:56,bg:HB})));
    const rows=st.rows.map((r,i)=>{
      const out=vs.map(k=>({v:P4DEF[k].x.v(r,i), al:P4DEF[k].x.al}));
      dates.forEach(d=>{
        const pl=(r.days&&r.days[d])||0, dn=(r.done&&r.done[d])||0;
        if(!pl&&!dn){out.push({v:'',al:'center'});return;}
        const bg=(r.colors&&r.colors[d])||'';
        out.push({v:`${dn}/${pl}`,al:'center',bg,fg:_fgx(bg)});});
      return out;});
    const T2=new Date(), p2=n=>String(n).padStart(2,'0');
    const stamp=`${String(T2.getFullYear()).slice(2)}${p2(T2.getMonth()+1)}${p2(T2.getDate())}`
      +`${p2(T2.getHours())}${p2(T2.getMinutes())}${p2(T2.getSeconds())}`;
    downloadXLS(`4주간가공계획현황_${stamp}`, cols, rows, {sheet:`4주간가공계획_${st.wc||'전체'}`});
  };
  // ★계획 기준일 반영 후 조회(첫 진입 시 캐시 미로드 대비) — 2026-08-28
  planBase().then(b=>{if(b&&b.iso){st.from=b.iso;
      st.to=iso(new Date(new Date(b.iso+'T00:00:00').getTime()+30*864e5));}}).catch(()=>{}).then(load);
};

/* ===== 생산: 가공생산진척관리(전표발행) (w_pr_input_420_new) — PR_T_PLAN_PART_DTL 스냅샷 직독 ===== */
SCREEN.gagongprog420=(c)=>{
  const API=API_BASE;
  const nf=n=>Number(n||0).toLocaleString('ko-KR',{maximumFractionDigits:0});
  const nf2=n=>Number(n||0).toLocaleString('ko-KR',{minimumFractionDigits:2,maximumFractionDigits:2});
  const _DW=['일','월','화','수','목','금','토'];
  // ★일자헤더 = '20(목)' (준비실적처리와 동일 표기)
  const dcol=s=>{s=''+(s||'');if(s.length!==6)return s;
    const d=new Date(2000+ +s.slice(0,2), +s.slice(2,4)-1, +s.slice(4,6));
    return `${+s.slice(4,6)}(${_DW[d.getDay()]})`;};
  // ★주말 판정(2026-08-20) — 토=파랑, 일=빨강 헤더(레거시 420 동일)
  const dow=s=>{s=''+(s||'');if(s.length!==6)return -1;
    return new Date(2000+ +s.slice(0,2), +s.slice(2,4)-1, +s.slice(4,6)).getDay();};
  const dcls=s=>{const w=dow(s);return w===0?' g4sun':(w===6?' g4sat':'');};
  const iso=x=>`${x.getFullYear()}-${String(x.getMonth()+1).padStart(2,'0')}-${String(x.getDate()).padStart(2,'0')}`;
  const T=new Date();
  // ★기본 소스 = 신규DB(웹계획). 레거시 대조는 소스를 nx/sp 로 바꿔서 본다(2026-08-26).
  // ★기준일 = 마지막 계획업로드의 일자축 첫날(planBaseIso, 2026-08-28 사용자 확정)
  const _gb0=planBaseIso(), _gbT=new Date(_gb0+'T00:00:00');
  const st={from:_gb0,to:iso(new Date(_gbT.getTime()+1*864e5)),wc:'P2',part:'',item:'',jado:'',unfin:'미생산',view:'상세',gigan:2,src:'new',
            dates:[],allrows:[],parts:[],note:'',loading:false,msg:'',sel:new Set()};
  const load=async()=>{st.loading=true;draw();
    // ★nx 재현(prog420nx) 기본 · sp=레거시 암호화SP 비교용. 전체 1회 조회·캐시 → 미생산/미키팅 토글은 클라 즉시필터.
    const ep=st.src==='sp'?'prog420':'prog420nx';
    // ★도번·자도번은 서버에 안 보냄 — 전체 1회 조회 후 클라 즉시필터(2026-08-20 사용자요청)
    // ★new = nx재현 엔진 그대로, 계획원천만 웹편성(plansrc=new)으로 교체.
    const qs=st.src==='sp'
      ? new URLSearchParams({from_ymd:st.from,to_ymd:st.to,wc:st.wc,item:'',jado:'',unfin:'전체',limit:8000})
      : new URLSearchParams({from_ymd:st.from,gigan:st.gigan,wc:st.wc,item:'',jado:'',unfin:'전체',
                             plansrc:(st.src==='new'?'new':'nx'),limit:8000});
    try{const r=await fetch(`${API}/api/gagong/${ep}?${qs}`);const d=await r.json();
      st.dates=d.dates||[];st.allrows=d.rows||[];st.parts=d.parts||st.parts;st.note=d.note||'';st.msg='';}
    catch(e){st.msg='백엔드 연결 실패';st.dates=[];st.allrows=[];}
    st.loading=false;st.loaded=true;draw();};   // loaded=한 번이라도 조회했나(빈 표 문구 구분)
  const draw=()=>{
    const dates=st.dates;
    // ★미생산/미키팅 토글 = 캐시(allrows)에서 클라 즉시필터(재조회 없음)
    const rows0 = st.unfin==='미생산' ? st.allrows.filter(r=>(+r.finish||0)<(+r.plan_qty||0))
                : st.allrows;
      // ★출고처(파트) 드롭다운 = 캐시 즉시필터(2026-08-20). gpc 코드 기준.
      const rows1 = st.part ? rows0.filter(r=>(r.wcd||'')===st.part) : rows0;
      // ★도번(Assy)·자도번도 캐시 즉시필터(2026-08-20 사용자요청) — 서버 재조회 없이 부분일치.
      const _q=s=>(s||'').trim().toUpperCase();
      const qi=_q(st.item), qj=_q(st.jado);
      const rowsP = (qi||qj) ? rows1.filter(r=>
            (!qi||((r.assy||'').toUpperCase().includes(qi)||(r.upper||'').toUpperCase().includes(qi)))
         && (!qj||(r.jado||'').toUpperCase().includes(qj))) : rows1;
    const wcS=new Map(),itS=new Map(),gpS=new Map();
    rowsP.forEach(r=>{if(r.wcd&&!wcS.has(r.wcd))wcS.set(r.wcd,r.wcd);if(r.assy&&!itS.has(r.assy))itS.set(r.assy,'');if(r.gpcnm)gpS.set(r.gpcnm,r.gpcnm);});
    const itOpts=[...itS].map(([v])=>`<option value="${esc(v)}"></option>`).join('');
    const gpOpts=[...gpS].map(([v])=>`<option value="${esc(v)}"></option>`).join('');
    let tPlan=0,tFin=0,tSale=0,tPrs=0,tPFn=0,tPPl=0;const dSum={};dates.forEach(d=>dSum[d]={dn:0,pl:0});
    rowsP.forEach(r=>{tPlan+=+r.plan_qty||0;tFin+=+r.finish||0;tSale+=+r.sale||0;tPrs+=+r.prs||0;tPFn+=+r.prior_fn||0;tPPl+=+r.prior_pl||0;
      dates.forEach(d=>{dSum[d].dn+=(r.done&&r.done[d])||0;dSum[d].pl+=(r.days&&r.days[d])||0;});});
    const NC=23;  // 고정컬럼(Assy..당일이전 7 + 완료·출하·가공전표발행·가공창고·자재재고·도번고정·ASSY재고·자재사용량·자도번작업처·WO 11)
    /* ★정렬(2026-09-04 교정) — 레거시 순서에 맞춘다.
         [종전] assy → jado 만 봐서 **도번(upper)이 정렬키에 없었다**.
                그래서 같은 ASSY 안에서 AJR30012009 와 AJR30012009-20-1 이 자도번 순으로
                뒤섞였다(65966706·65966711·65966716…). 백엔드에 정렬을 넣어도
                여기서 다시 정렬해 **덮어써 버려** 화면이 그대로였다.
         [현재] assy → upper(도번) → 시간 → jado.
                · upper = 부모 도번. 이게 있어야 -20-1 하위가 부모 밑에 묶인다.
                · 시간  = 레거시 커서순서(plan_ymd→part_output_hm→output_hm→wo,
                          backend gagong.py:255 참조). 같은 도번 안은 INPUT 시간 순.
         ※assy 그룹별 청록 소계행(레거시 group trailer)은 assy 경계에서 그리므로 영향 없음. */
    const _s=v=>(v==null?'':String(v));
    const disp=rowsP.slice().sort((a,b)=>
        _s(a.assy).localeCompare(_s(b.assy))
     || _s(a.upper).localeCompare(_s(b.upper))
     || _s(a.plan_ymd).localeCompare(_s(b.plan_ymd))
     || _s(a.phm).localeCompare(_s(b.phm))
     || _s(a.ohm).localeCompare(_s(b.ohm))
     || _s(a.jado).localeCompare(_s(b.jado)));
    const dcap=(v)=>v?nf(v):'';
    // ★행 선택(드래그) — 레거시 420: 계획셀 드래그로 여러건 고른 뒤 [전표발행] (2026-08-20)
    const rkey=(r)=>`${r.assy}|${r.jado}`;
    // ★일자셀·당일이전셀 = 선택단위. 미생산분(계획−완료)이 0인 셀만 잠금.
    //   ※재고보유는 잠그지 않는다(레거시도 재고 있는 셀이 선택됨).
    //   d='P' = 당일이전 칸(계획이 과거일자에 몰린 건이 많아 이 칸이 주 선택대상).
    const ckey=(r,d)=>`${r.assy}|${r.jado}|${d}`;
    const frac=(dn,pl,bg,r,d)=>{
      const wk=(d&&d!=='P'&&!bg)?dcls(d).replace(/g4s(at|un)/,'g4wk'):'';   // 주말 연회색(계획색 있으면 유지)
      if(!pl&&!dn)return `<td class="num${wk}"></td>`;
      const rem=Math.max(0,(+pl||0)-(+dn||0));
      const lock=!r||rem<=0;
      const k=r?ckey(r,d):'';
      return `<td class="num g4c${wk}${lock?' g4lock':''}${st.sel.has(k)?' g4sel':''}"${lock?'':` data-k="${esc(k)}" data-rem="${rem}"`}
        style="white-space:nowrap${bg?';'+bg:''}"${lock?' title="미생산분 없음(계획=완료) — 선택불가"':''}>${nf(dn)}/${nf(pl)}</td>`;};   // 셀색=레거시SP color_NN
    // ★컬럼 이동(2026-08-20) — 머리(H)/꼬리(T) 그룹 안에서 드래그 재배치, localStorage 저장.
    //   일자컬럼이 두 그룹 사이에 있어 그룹을 넘나드는 이동은 불가(410과 동일 방식).
    const HDEF={
      assy:{t:'Assy도번', h:r=>`<td class="center"><b>${esc(r.assy)}</b></td>`},
      upper:{t:'도번',    h:r=>`<td class="bcap" style="max-width:110px;overflow:hidden;text-overflow:ellipsis" title="${esc(r.upper)}">${esc(r.upper)}</td>`},
      jado:{t:'자도번',   h:r=>`<td class="center">${esc(r.jado)}</td>`},
      wcd:{t:'출고처',    h:r=>`<td class="center">${esc(r.wcd)}</td>`},
      st:{t:'생산ST',     h:r=>`<td class="num">${nf2(r.st)}</td>`, cls:'num'},
      plan_qty:{t:'생산계획', h:r=>`<td class="num">${nf(r.plan_qty)}</td>`, cls:'num'},
      prior:{t:'당일이전', h:r=>frac(+r.prior_fn||0,+r.prior_pl||0,r.prior_bg||'',r,'P'), cls:'num'},
    };
    const TDEF={
      finish:{t:'완료',   h:r=>`<td class="num">${dcap(r.finish)}</td>`, cls:'num'},
      sale:{t:'출하',     h:r=>`<td class="num">${dcap(r.sale)}</td>`, cls:'num'},
      ing:{t:'가공전표발행', h:r=>`<td class="num">${dcap(r.ing)}</td>`, cls:'num'},
      proc:{t:'가공창고재고', h:r=>`<td class="num">${dcap(r.proc)}</td>`, cls:'num'},
      jae_m:{t:'자재재고', h:r=>`<td class="num">${dcap(r.jae_m)}</td>`, cls:'num'},
      jae_p:{t:'생산재고', h:r=>`<td class="num">${dcap(r.jae_p)}</td>`, cls:'num'},
      jae_s:{t:'사급재고', h:r=>`<td class="num">${dcap(r.jae_s)}</td>`, cls:'num'},
      fixst:{t:'도번고정', h:r=>`<td class="num">${dcap(r.fixst)}</td>`, cls:'num'},
      assyst:{t:'ASSY재고', h:r=>`<td class="num">${dcap(r.assyst)}</td>`, cls:'num'},
      use:{t:'자재사용량', h:r=>`<td class="num">${nf2(r.use)}</td>`, cls:'num'},
      diam:{t:'지름',     h:r=>`<td class="num">${dcap(r.diam)}</td>`, cls:'num'},
      thick:{t:'두께',    h:r=>`<td class="num">${dcap(r.thick)}</td>`, cls:'num'},
      length:{t:'길이',   h:r=>`<td class="num">${dcap(r.length)}</td>`, cls:'num'},
      lgout:{t:'LG OUTPUT시간', h:r=>`<td class="center mut">${esc(r.lgout||"")}</td>`, cls:'center'},
      line_no:{t:'Line No', h:r=>`<td class="center">${esc(r.line_no||"")}</td>`, cls:'center'},
      bl:{t:'Bom Level', h:r=>`<td class="num">${r.bl||0}</td>`, cls:'num'},
      wo:{t:'WO',        h:r=>`<td class="bcap" style="max-width:90px;overflow:hidden;text-overflow:ellipsis" title="${esc(r.wo)}">${esc(r.wo)}</td>`},
    };
    const H_DEF=['assy','upper','jado','wcd','st','plan_qty','prior'];
    const T_DEF=['finish','sale','ing','proc','jae_m','jae_p','jae_s','fixst','assyst','use',
                 'diam','thick','length','lgout','line_no','bl','wo'];
    const H_LS='g420_headorder', T_LS='g420_tailorder';
    /* ★ALLDEF = 앞·뒤 정의를 합친 것. 항목보기는 그룹 경계를 넘는 이동을 허용하므로
         저장된 순서에는 **반대 그룹의 키**가 섞여 있다(예: 뒤 컬럼 '생산재고'를 앞으로 옮김).
         종전엔 loadOrd 가 그룹별 정의(HDEF/TDEF)로 걸러서 그 키가 **탈락**했고,
         곧이어 def(T_DEF) 보충 루프가 되살려 **맨 뒤**에 붙였다 —
         "앞으로 옮겼는데 저장하면 맨 뒤로 간다"의 정체(2026-09-09 사용자 신고).
         ⟹ 필터는 ALLDEF 로 한다(410 파트별계획과 동일 처방). */
    const ALLDEF=Object.assign({},HDEF,TDEF);
    const loadOrd=(key,def,defs)=>{try{const s=JSON.parse(localStorage.getItem(key)||'null');
      if(Array.isArray(s)&&s.length){const v=s.filter(k=>defs[k]);def.forEach(k=>{if(!v.includes(k))v.push(k);});return v;}
      }catch(e){}
      return def.slice();};
    const hOrd=loadOrd(H_LS,H_DEF,ALLDEF);
    let tOrd=loadOrd(T_LS,T_DEF,ALLDEF);
    /* ★한 컬럼이 양쪽 그룹에 동시에 있으면 표에 두 번 나온다.
         loadOrd 는 "저장에 없는 기본컬럼을 뒤에 보충"하는데, 앞으로 옮긴 컬럼은
         tail 저장목록에서 빠졌으므로 T_DEF 보충 때 되살아난다 → head 가 가진 키는 tail 에서 뺀다. */
    tOrd=tOrd.filter(k=>!hOrd.includes(k));
    /* ★헤더 드래그 제거(2026-09-06 사용자 요청 "버벅거린다") — 410 과 같은 방식으로 전환.
         표를 직접 끌면 매 이동마다 레이아웃이 무효화돼 저사양 PC 에서 멈춘다.
         순서·숨김은 **항목보기**(버튼 또는 헤더 우클릭)에서 한다 — 목록 행만 움직이므로 가볍다. */
    /* ★숨김 컬럼(항목보기에서 체크 해제한 것) — 헤더·본문·소계에서 **함께** 빠져야
         열 수가 어긋나지 않는다. 그리기 직전에 한 번 읽어 vis() 로 거른다. */
    const _hid=(()=>{try{const s=JSON.parse(localStorage.getItem('g420_hidecols')||'[]');
      return new Set(Array.isArray(s)?s:[]);}catch(_){return new Set();}})();
    const vis=ks=>ks.filter(k=>!_hid.has(k));
    /* ★defs 는 항상 ALLDEF 로 찾는다 — 그룹을 넘어온 키는 그 그룹 정의에 없다.
         (HDEF/TDEF 로 찾으면 defs[k] 가 undefined 라 렌더가 그 자리에서 죽는다.) */
    const mkTh=(ks,defs,grp)=>vis(ks).map(k=>{const d=ALLDEF[k]; if(!d)return '';
      return `<th class="${d.cls||'center'}" data-tk="${k}" data-grp="${grp}" title="우클릭 = 항목보기(순서·숨김)">${d.t}</th>`;}).join('');
    const mkTd=(ks,defs,r)=>vis(ks).map(k=>{const d=ALLDEF[k]; return d?d.h(r):'';}).join('');
    const rowHtml=(r)=>`<tr class="g4row">
        ${mkTd(hOrd,HDEF,r)}
        ${dates.map(d=>frac((r.done&&r.done[d])||0,(r.days&&r.days[d])||0,(r.colors&&r.colors[d])||'',r,d)).join('')}
        ${mkTd(tOrd,TDEF,r)}</tr>`;
    // ★소계행 셀색 롤업(2026-08-20) — 레거시는 소계단에도 색이 들어간다.
    //   블록 안 명세행들의 색 중 우선순위가 높은 것 하나를 대표색으로 사용.
    //   순위 = 화면 범례순: 90주황출하 > 70·30노랑 > 20민트 > 10녹(연두) > 진녹.
    //   ※계획>0 인 행만 대상(빈 셀 색은 무시).
    const _rk={'#fac090':1,'#ffff00':2,'#99ffcc':3,'#66ff99':4,'#669900':5};
    const _bgc=bg=>{const m=/background:(#[0-9a-f]{6})/i.exec(bg||'');return m?m[1].toLowerCase():'';};
    const rollBg=(bgs)=>{const v=bgs.map(_bgc).filter(Boolean);
      if(!v.length)return '';
      v.sort((a,b)=>(_rk[a]||9)-(_rk[b]||9));
      return 'background:'+v[0];};
    const subHtml=(blk)=>{const r0=blk[0];
      const sPl=blk.reduce((s,r)=>s+(+r.plan_qty||0),0), sFn=blk.reduce((s,r)=>s+(+r.finish||0),0);
      const sPrP=blk.reduce((s,r)=>s+(+r.prior_pl||0),0), sPrF=blk.reduce((s,r)=>s+(+r.prior_fn||0),0);
      const sST=blk.reduce((s,r)=>s+(+r.st||0),0);
      const sPrBg=rollBg(blk.filter(r=>(+r.prior_pl||0)>0).map(r=>r.prior_bg||''));
      // 소계행도 컬럼 순서(hOrd/tOrd)를 따라야 드래그 이동시 어긋나지 않는다.
      const SH={assy:`<td class="center"><b>${esc(r0.assy)}</b></td>`,
                upper:'<td></td>', jado:'<td></td>', wcd:'<td></td>',
                st:`<td class="num">${nf2(sST)}</td>`,
                plan_qty:`<td class="num"><b>${nf(sPl)}</b></td>`,
                prior:`<td class="num"${sPrBg?` style="${sPrBg}"`:''}>${sPrP?nf(sPrF)+'/'+nf(sPrP):''}</td>`};
      const ST={finish:`<td class="num">${nf(sFn)}</td>`};
      /* ★소계 셀도 그룹을 합쳐 찾는다 — 컬럼이 앞↔뒤로 옮겨져도 값이 따라간다. */
      const SA=Object.assign({},SH,ST);
      return `<tr style="background:#cdeef7;font-weight:600;border-bottom:1px solid #9fb3c8">
        ${vis(hOrd).map(k=>SA[k]||'<td></td>').join('')}
        ${dates.map(d=>{const pl=blk.reduce((s,r)=>s+((r.days&&r.days[d])||0),0),dn=blk.reduce((s,r)=>s+((r.done&&r.done[d])||0),0);
          const bg=rollBg(blk.filter(r=>((r.days&&r.days[d])||0)>0).map(r=>(r.colors&&r.colors[d])||''));
          return `<td class="num"${bg?` style="${bg}"`:''}>${pl?nf(dn)+'/'+nf(pl):''}</td>`;}).join('')}
        ${vis(tOrd).map(k=>SA[k]||'<td></td>').join('')}</tr>`;};
    // ★colspan 은 실제 보이는 컬럼 수로 — NC 고정값(23)을 쓰면 숨김 시 어긋난다.
    const NCV=()=>vis(hOrd).length+vis(tOrd).length;
    const bodyHtml=()=>{if(!disp.length)return `<tr><td colspan="${NCV()+dates.length}" class="empty">${
      st.loaded?'조회 결과 없음':'조건을 지정하고 <b>조회</b>를 누르세요.'}</td></tr>`;
      let h='',i=0;
      while(i<disp.length){const a=disp[i].assy;let j=i;const blk=[];while(j<disp.length&&disp[j].assy===a){blk.push(disp[j]);j++;}
        // 구분: 상세=명세행+소계행 / 제번=명세행만 / 집계=소계행만(레거시 w_pr_input_420_new 구분토글)
        if(st.view!=='집계') blk.forEach(r=>{h+=rowHtml(r);});
        if(st.view!=='제번') h+=subHtml(blk);
        i=j;}
      return h;};
    c.innerHTML=`
     <style>.g4tbl td,.g4tbl th{text-align:center !important}.g4tbl td.bcap{text-align:center !important}
       .g4tbl tbody{user-select:none}
       .g4c[data-k]{cursor:cell}
       /* ★선택표시 완화(2026-08-20) — 키팅과 동일 톤. 셀색(녹/노랑)은 살리고 연파랑 막만 덧씌움 */
       .g4c.g4sel{background-image:linear-gradient(rgba(219,234,254,.72),rgba(219,234,254,.72));
                  outline:2px solid #4a86e8;outline-offset:-2px;font-weight:700}
       .g4c.g4lock{cursor:default}
       /* ★복사 전용 선택(2026-09-06) — 일자칸 선택(.g4sel 파랑)과 **다른 색**이어야
            무엇이 전표발행 대상이고 무엇이 복사 대상인지 구분된다. */
       .g4tbl td.g4cp{background-image:linear-gradient(rgba(255,236,179,.55),rgba(255,236,179,.55));
                      outline:1px solid #e0b84c;outline-offset:-1px}
       /* ★주말 헤더(2026-08-20): 토=파랑, 일=빨강 */
       .g4tbl th.g4sat{color:#1558d6}
       .g4tbl th.g4sun{color:#c0392b}
       .g4tbl td.g4wk{background:#f4f6f9}</style>
     <div class="page-title">🏭 가공생산진척관리(전표발행) <span style="font-size:12px;color:var(--muted);font-weight:400">Assy도번·자도번별 생산진척</span></div>
     <div class="page-sub"><b>nx 재현</b> + <b>계획=웹편성</b>(nx.plan_part_dtl) · 그레인=(도번,가공컴포넌트) · 셀색 90주황출하/70·30노랑재고/20민트가공창고/10녹전표 · 당일이전=기준일 이전</div>
     <div class="toolbar">
      <label class="tl">기준일자</label><input class="inp" type="date" id="g4-from" value="${st.from}">
      <!-- ★자도번작업처 = P2 가공 고정이므로 숨김(2026-08-20). st.wc 값·핸들러는 그대로 유지 -->
      <span style="display:none"><label class="tl">자도번작업처</label><select class="inp" id="g4-wc" style="width:110px"><option value="P2"${st.wc==='P2'?' selected':''}>P2 가공</option><option value="P1"${st.wc==='P1'?' selected':''}>P1 용접</option></select></span>
      <label class="tl">출고처</label><select class="inp" id="g4-part" style="width:150px"><option value="">전체</option>${(st.parts||[]).map(o=>`<option value="${esc(o.code)}"${st.part===o.code?' selected':''}>${esc(o.nm||o.code)}</option>`).join('')}</select>
      <label class="tl">미생산</label>
      <label class="rl"><input type="radio" name="g4-uf" value="전체"${st.unfin==='전체'?' checked':''}> 전체</label>
      <label class="rl"><input type="radio" name="g4-uf" value="미생산"${st.unfin==='미생산'?' checked':''}> 미생산</label>
      <!-- ★소스 드롭다운 제거(2026-09-08 사용자 확정) — 신규DB(웹계획) 고정.
           웹 기준(웹편성 계획)으로 운영하므로, 대사용이던 '우리(nx)'·'레거시 대사'를
           실무 화면에 노출할 필요가 없다(410 파트별계획·460 준비실적처리와 동일 조치).
           st.src 는 'new' 로 고정(초기값). API 는 plansrc 를 그대로 받으므로 백엔드 변경 없음. -->
      <button class="btn" id="g4-search">🔍 조회</button>
      <div class="spacer"></div>
      <span class="rowcount" id="g4-selinfo" style="margin-right:8px"></span>
      <!-- ★항목보기·엑셀(2026-09-06) — 파트별 생산계획 410 과 같은 기능 -->
      <button class="btn" id="g4-col" title="컬럼 숨김·순서 (헤더 우클릭으로도 열림)">항목보기</button>
      <button class="btn" id="g4-xls" style="background:#1c7c3a;color:#fff"
              title="화면과 같은 색상으로 엑셀 저장">엑셀</button>
      <button class="btn" id="g4-issue" style="background:#1c47a0;color:#fff">🧾 전표발행</button>
      <button class="btn" id="g4-bc" style="background:#1c7c3a;color:#fff">📷 가공바코드실적처리</button>
    </div>
    <div class="toolbar" style="margin-top:2px">
      <label class="tl">도번</label><input class="inp" id="g4-item" list="g4-iteml" value="${esc(st.item)}" style="width:120px" placeholder="Assy도번" autocomplete="off"><datalist id="g4-iteml">${itOpts}</datalist>
      <label class="tl">자도번</label><input class="inp" id="g4-jado" value="${esc(st.jado)}" style="width:120px" placeholder="자도번" autocomplete="off">
      <label class="tl">구분</label>
      <label class="rl"><input type="radio" name="g4-vw" value="상세"${st.view==='상세'?' checked':''}> 상세</label>
      <label class="rl"><input type="radio" name="g4-vw" value="집계"${st.view==='집계'?' checked':''}> 집계</label>
      <label class="rl"><input type="radio" name="g4-vw" value="제번"${st.view==='제번'?' checked':''}> 제번</label>
      <label class="tl">기간</label><select class="inp" id="g4-gigan" style="max-width:70px">${[1,2,3,4,5,6,7,8].map(d=>`<option value="${d}"${st.gigan===d?' selected':''}>${d}일</option>`).join('')}</select>
      <div class="spacer"></div><span class="rowcount">행 <b>${nf(disp.length)}</b> · 생산계획합 <b>${nf(tPlan)}</b> · 완료합 <b>${nf(tFin)}</b></span>
    </div>
     ${st.note?`<div class="page-sub" style="color:#c0392b">${esc(st.note)}</div>`:''}
     ${st.msg?`<div class="page-sub" style="color:#c0392b">⚠ ${esc(st.msg)}</div>`:''}
     <div class="grid-wrap" style="max-height:calc(100vh - 340px);overflow:auto;background:#fff;border:1px solid var(--line-2,#c9d3e0);border-radius:8px">
      <table class="tbl fit g4tbl" style="font-size:11px"><thead><tr>
       ${mkTh(hOrd,HDEF,'head')}
       ${dates.map(d=>`<th class="num${dcls(d)}">${dcol(d)}</th>`).join('')}
       ${mkTh(tOrd,TDEF,'tail')}</tr></thead>
      <tbody>${st.loading?spinRow(NCV()+dates.length):bodyHtml()}</tbody>
      ${disp.length?(()=>{   // 합계행도 컬럼순서를 따른다(드래그 이동시 어긋남 방지)
        const FH={assy:`<td>합계 (${nf(disp.length)}행)</td>`,
                  st:`<td class="num">${nf2(disp.reduce((s,r)=>s+(+r.st||0),0))}</td>`,
                  plan_qty:`<td class="num">${nf(tPlan)}</td>`,
                  prior:`<td class="num">${nf(tPFn)}/${nf(tPPl)}</td>`};
        const FT={finish:`<td class="num">${nf(tFin)}</td>`, sale:`<td class="num">${nf(tSale)}</td>`};
        /* ★합계행도 vis() 로 거르고 그룹을 합쳐 찾는다 —
             종전엔 hOrd/tOrd 를 그대로 써서 **숨긴 컬럼만큼 칸이 남아돌아** 어긋났다. */
        const FA=Object.assign({},FH,FT);
        return `<tfoot><tr class="grandtot">
        ${vis(hOrd).map(k=>FA[k]||'<td></td>').join('')}
        ${dates.map(d=>`<td class="num" style="white-space:nowrap">${nf(dSum[d].dn)}/${nf(dSum[d].pl)}</td>`).join('')}
        ${vis(tOrd).map(k=>FA[k]||'<td></td>').join('')}</tr></tfoot>`;})():''}
      </table></div>`;
    const g=id=>c.querySelector(id);
    g('#g4-search').onclick=()=>{st.from=g('#g4-from').value;st.to=iso(new Date(new Date(st.from).getTime()+(st.gigan-1)*864e5));st.wc=g('#g4-wc').value.trim();
      st.item=g('#g4-item').value.trim();st.jado=g('#g4-jado').value.trim();st.part=g('#g4-part').value;load();};
    // ★도번·자도번 = 캐시 즉시필터(입력 즉시, 재조회 없음). 커서/스크롤 유지되게 값 복원.
    ['#g4-item','#g4-jado'].forEach(id=>{const el=g(id);if(!el)return;
      el.oninput=()=>{const v=el.value,ss=el.selectionStart;
        if(id==='#g4-item')st.item=v.trim(); else st.jado=v.trim();
        draw();
        const n=c.querySelector(id);if(n){n.value=v;n.focus();try{n.setSelectionRange(ss,ss);}catch(e){}}};});
    g('#g4-gigan').onchange=()=>{st.gigan=+g('#g4-gigan').value;st.to=iso(new Date(new Date(st.from).getTime()+(st.gigan-1)*864e5));g('#g4-search').click();};
    c.querySelectorAll('input[name=g4-uf]').forEach(rd=>rd.onchange=()=>{st.unfin=rd.value;draw();});  // ★캐시 즉시필터(재조회 없음)
    c.querySelectorAll('input[name=g4-vw]').forEach(rd=>rd.onchange=()=>{st.view=rd.value;draw();});  // 구분: 상세/집계/제번 즉시전환
    // ★소스는 'new'(신규DB=웹계획) 고정 — 드롭다운 제거(2026-09-08)
    g('#g4-part').onchange=()=>{st.part=g('#g4-part').value;draw();};   // 출고처 = 캐시 즉시필터
    g('#g4-wc').onchange=()=>g('#g4-search').click();
    g('#g4-part').onkeyup=e=>{if(e.key==='Enter')g('#g4-search').click();};   // 도번·자도번은 즉시필터(위)
    g('#g4-bc').onclick=openBcModal;
    // ★드래그 선택(레거시 420 방식): 행 위에서 눌러 끌면 그 구간이 선택된다.
    //   부분갱신만(재렌더 X) — CLAUDE.md §3 스크롤 리셋 방지.
    const tb=c.querySelector('.g4tbl tbody');
    // ★선택 = 일자셀 단위(레거시 420). 선택수량 = 그 셀의 미생산분(계획−완료) 합.
    //   레거시 표기: "조회내역 - 선택건수=N 선택수량=M"
    const selCells=()=>{const out=[];
      disp.forEach(r=>['P'].concat(dates).forEach(d=>{const k=ckey(r,d);
        if(!st.sel.has(k))return;
        const pl=d==='P'?(+r.prior_pl||0):((r.days&&r.days[d])||0);
        const dn=d==='P'?(+r.prior_fn||0):((r.done&&r.done[d])||0);
        const rem=Math.max(0,pl-dn);
        if(rem>0)out.push({r:r,d:d,rem:rem});}));
      return out;};
    const selInfo=()=>{const e=g('#g4-selinfo');if(!e)return;
      const pk=selCells(),q=pk.reduce((s,x)=>s+x.rem,0);
      e.innerHTML=pk.length?`선택건수 <b>${nf(pk.length)}</b> · 선택수량 <b>${nf(q)}</b>`:'';};
    const paint=(td)=>{td.classList.toggle('g4sel',st.sel.has(td.getAttribute('data-k')));};
    // ★사각영역 드래그(2026-08-20) — 키팅(screens.prod.js)과 동일 방식.
    //   기존 mouseover 누적방식은 빠르게 끌면 이벤트가 유실돼 중간 셀이 빠졌음.
    //   → 시작셀~현재셀의 (행,열) 사각범위를 매 move 마다 통째로 계산(엑셀 감각).
    const gw=c.querySelector('.grid-wrap');
    if(tb&&gw){
      gw.style.userSelect='none'; gw.style.webkitUserSelect='none';
      gw.onselectstart=()=>false;                    // 브라우저 기본 텍스트선택 차단
      const rcOf=td=>{const tr=td.parentElement;return {r:tr?tr.rowIndex:-1,c:td.cellIndex};};
      const cellAt=(x,y)=>{const e=document.elementFromPoint(x,y);if(!e)return null;
        const td=e.closest('td.g4c[data-k]');if(td)return td;
        const tr=e.closest('tr');                    // 같은 행에서 x 에 가장 가까운 선택가능 셀
        if(tr){let best=null,bd=1e9;
          tr.querySelectorAll('td.g4c[data-k]').forEach(z=>{const r=z.getBoundingClientRect();
            const d=(x<r.left)?(r.left-x):((x>r.right)?(x-r.right):0);
            if(d<bd){bd=d;best=z;}});
          if(best)return best;}
        return e.closest('td');};                    // 빈칸 위에서도 좌표 유지
      let drag=false,_a=null,_cells=null,_own=null,_last=null;
      const snap=()=>{_cells=[...tb.querySelectorAll('td.g4c[data-k]')]
        .map(x=>{const p=rcOf(x);return {td:x,r:p.r,c:p.c,k:x.getAttribute('data-k')};});};
      const clearAll=()=>{tb.querySelectorAll('td.g4c.g4sel').forEach(td=>{
        st.sel.delete(td.getAttribute('data-k'));td.classList.remove('g4sel');});};
      const applyRect=(td)=>{if(!_a||!_cells)return;
        const b=rcOf(td);
        const r1=Math.min(_a.r,b.r),r2=Math.max(_a.r,b.r);
        const c1=Math.min(_a.c,b.c),c2=Math.max(_a.c,b.c);
        for(const it of _cells){
          const inR=it.r>=r1&&it.r<=r2&&it.c>=c1&&it.c<=c2, has=st.sel.has(it.k);
          if(inR&&!has){st.sel.add(it.k);it.td.classList.add('g4sel');_own.add(it.k);}
          else if(!inR&&has&&_own.has(it.k)){st.sel.delete(it.k);it.td.classList.remove('g4sel');}}
        selInfo();};
      tb.addEventListener('mousedown',e=>{if(e.button!==0)return;
        const start=e.target.closest('td');if(!start||!start.closest('tr'))return;
        const hit=e.target.closest('td.g4c[data-k]');
        e.preventDefault();
        // 재클릭=해제(키팅 동일): 이미 선택된 칸을 Ctrl 없이 다시 누르면 그 칸만 끔
        if(hit&&!e.ctrlKey&&!e.metaKey&&st.sel.has(hit.getAttribute('data-k'))&&st.sel.size===1){
          st.sel.delete(hit.getAttribute('data-k'));hit.classList.remove('g4sel');selInfo();return;}
        if(!e.ctrlKey&&!e.metaKey)clearAll();
        drag=true;_own=new Set();snap();_a=rcOf(start);_last=start;
        if(hit)applyRect(hit); else selInfo();});
      tb.addEventListener('mousemove',e=>{if(!drag)return;
        if(!(e.buttons&1)){drag=false;_a=null;_cells=null;_last=null;return;}
        const td=cellAt(e.clientX,e.clientY)||_last;
        if(td){_last=td;applyRect(td);}});
      document.addEventListener('mouseup',()=>{drag=false;_a=null;_cells=null;_last=null;});

      /* ══ 복사 전용 드래그 (2026-09-06 사용자 요청 "도번 등 여러 항목도 드래그해서 복사")
           위의 선택(.g4sel)은 **일자칸 전용**이다 — 전표발행 대상을 고르는 기능이라
           도번·자도번 같은 텍스트칸까지 넣으면 발행 로직이 깨진다.
           그래서 **모든 셀을 덮는 복사 전용 레이어**를 따로 둔다:
             · 표식 = .g4cp (연회색) — 전표발행과 무관, Ctrl+C 대상
             · 시작 조건 = 일자칸이 **아닌** 곳에서 mousedown (일자칸은 기존 로직이 가져간다)
           두 선택은 서로를 지운다 — 화면에 두 색이 동시에 뜨면 무엇이 복사될지 헷갈린다. */
      let cdrag=false,_ca=null,_ccells=null,_clast=null;
      const cpClear=()=>tb.querySelectorAll('td.g4cp').forEach(td=>td.classList.remove('g4cp'));
      const cpSnap=()=>{_ccells=[...tb.querySelectorAll('td')]
        .map(x=>{const p=rcOf(x);return {td:x,r:p.r,c:p.c};});};
      const cpRect=(td)=>{if(!_ca||!_ccells)return;
        const b=rcOf(td);
        const r1=Math.min(_ca.r,b.r),r2=Math.max(_ca.r,b.r);
        const c1=Math.min(_ca.c,b.c),c2=Math.max(_ca.c,b.c);
        for(const it of _ccells){
          const inR=it.r>=r1&&it.r<=r2&&it.c>=c1&&it.c<=c2;
          it.td.classList.toggle('g4cp',inR);}
        const n=tb.querySelectorAll('td.g4cp').length;
        const el=g('#g4-selinfo');
        if(el&&n)el.innerHTML=`복사선택 <b>${nf(n)}</b>칸 <span style="color:#7b8aa0">(Ctrl+C)</span>`;};
      tb.addEventListener('mousedown',e=>{
        if(e.button!==0)return;
        if(e.target.closest('td.g4c[data-k]'))return;    // 일자칸 = 위 선택이 처리
        const start=e.target.closest('td'); if(!start||!start.closest('tr'))return;
        e.preventDefault();
        clearAll();                                      // 일자칸 선택은 지운다(혼동 방지)
        if(!e.ctrlKey&&!e.metaKey)cpClear();
        cdrag=true;cpSnap();_ca=rcOf(start);_clast=start;cpRect(start);});
      tb.addEventListener('mousemove',e=>{if(!cdrag)return;
        if(!(e.buttons&1)){cdrag=false;_ca=null;_ccells=null;_clast=null;return;}
        const el=document.elementFromPoint(e.clientX,e.clientY);
        const td=(el&&el.closest('td'))||_clast;
        if(td){_clast=td;cpRect(td);}});
      document.addEventListener('mouseup',()=>{cdrag=false;_ca=null;_ccells=null;_clast=null;});
      // 일자칸 드래그가 시작되면 복사선택은 지운다(반대 방향도 위에서 처리)
      tb.addEventListener('mousedown',e=>{
        if(e.button===0&&e.target.closest('td.g4c[data-k]'))cpClear();});
    }
    selInfo();
    /* ★헤더 드래그 이동은 제거했다(2026-09-06 사용자 요청 "버벅거린다").
         표를 직접 끌면 이동마다 레이아웃이 무효화돼 저사양 PC 에서 멈춘다.
         순서·숨김은 아래 openColPick(항목보기)에서 처리한다 — 목록 행만 움직이므로 가볍고,
         적용은 draw() 한 번으로 끝난다(410 과 같은 방식). */

    /* ══ 선택영역 복사 (2026-09-06 — 파트별 생산계획 410 과 같은 동작) ══════════
         드래그로 고른 칸을 Ctrl+C 로 클립보드에 넣는다. 엑셀에 그대로 붙는다(TSV).
         ★DOM 에서 읽는다 — 화면에 보이는 그대로가 사용자가 기대하는 복사 결과다.
         ★선택은 .g4sel 클래스로 판정(이 화면의 선택 표시). 410 은 .pp-sel 이다. */
    const _selText=()=>{
      const map=new Map();
      // ★복사선택(.g4cp)이 있으면 그것을, 없으면 일자칸 선택(.g4sel)을 복사한다.
      const pick=c.querySelector('td.g4cp')?'td.g4cp':'td.g4sel';
      c.querySelectorAll(pick).forEach(td=>{
        const tr=td.parentElement; if(!tr)return;
        const r=tr.rowIndex;
        if(!map.has(r))map.set(r,[]);
        map.get(r).push([td.cellIndex,(td.innerText||'').trim()]);});
      return [...map.keys()].sort((x,y)=>x-y)
        .map(r=>map.get(r).sort((x,y)=>x[0]-y[0]).map(x=>x[1]).join('\t')).join('\n');
    };
    const _toClip=(txt,what)=>{
      if(!txt){alert('복사할 영역을 먼저 끌어서 선택하세요.');return;}
      const done=()=>{const el=c.querySelector('#g4-selinfo');
        if(el){const o=el.innerHTML;el.innerHTML=`<b style="color:#1c7c3a">${what} 복사됨</b>`;
               setTimeout(()=>{el.innerHTML=o;},1400);}};
      /* ★보안컨텍스트일 때만 clipboard API 를 쓴다(2026-09-08).
           운영 184 는 http://200.200.200.184:8010 = **비보안** 이라 navigator.clipboard 가
           막힌다. 종전엔 그래도 writeText 를 먼저 부르고 실패하면 fb() 로 넘어갔는데,
           그 거부(reject)는 **비동기**라 사용자 제스처(Ctrl+C) 밖에서 fb 가 돈다
           → execCommand('copy') 가 브라우저에 막혀 조용히 아무것도 복사가 안 된다.
           ⟹ isSecureContext 가 아니면 처음부터 동기 fb() 로 간다(제스처 안에서 실행). */
      if(window.isSecureContext&&navigator.clipboard&&navigator.clipboard.writeText){
        navigator.clipboard.writeText(txt).then(done,()=>fb());
      }else fb();
      function fb(){   // 비보안 컨텍스트(http)는 clipboard API 가 막힌다
        const ta=document.createElement('textarea'); ta.value=txt;
        ta.style.cssText='position:fixed;left:-9999px;top:0';
        document.body.appendChild(ta); ta.focus(); ta.select();
        let ok=false; try{ok=document.execCommand('copy');}catch(_){}
        ta.remove();
        if(ok)done(); else alert('복사에 실패했습니다.');}
    };
    const _copySel=()=>_toClip(_selText(),'선택영역');
    const _copyAll=()=>{
      const tbl=c.querySelector('.g4tbl'); if(!tbl)return;
      const out=[];
      const hr=tbl.tHead&&tbl.tHead.rows[0];
      if(hr)out.push([...hr.cells].map(th=>(th.innerText||'').trim()).join('\t'));
      [...tbl.tBodies].forEach(tb=>{const rs=tb.rows;
        for(let i=0;i<rs.length;i++)out.push([...rs[i].cells].map(td=>(td.innerText||'').trim()).join('\t'));});
      _toClip(out.join('\n'),`전체 ${nf(out.length-1)}행`);
    };
    /* Ctrl+C — 선택영역이 있을 때만 가로챈다(없으면 브라우저 기본 동작).
       ★2026-09-08 document 로 옮김(사용자 "컨트롤+C 하면 복사를 하게 해줘, 왜 안되지").
         종전엔 c(tabindex=-1)에 keydown 을 걸었는데, 복사드래그 mousedown 이
         e.preventDefault() 를 부른다 → **포커스가 표로 오지 않는다**. 그래서 칸을
         칠해놓고("복사선택 N칸" 까지 떠도) Ctrl+C 를 누르면 c 는 keydown 을 아예
         못 받았다 — 무반응의 정체. 460 키팅에서 2026-09-04 에 같은 증상·같은 원인으로
         이미 고쳤던 것(screens.prod.js §kt cpkey)을 여기에도 똑같이 적용한다.
       ⟹ document 에서 받고, ①이 화면이 화면에 붙어있고 ②칠해진 칸이 있고
          ③입력칸에서 누른 게 아닐 때만 가로챈다(입력칸 텍스트 복사는 그대로 살린다).
       ★최신 핸들러는 c._g4CopySel 로 부른다 — 이 리스너는 화면당 1회만 달리므로
         옛 클로저를 붙잡고 있으면 다시 그린 뒤 옛 표를 복사한다. */
    c._g4CopySel=_copySel;
    if(!c.dataset.cpkey){
      c.dataset.cpkey='1';
      c.setAttribute('tabindex','-1'); c.style.outline='none';
      const onKey=ev=>{
        if(!((ev.ctrlKey||ev.metaKey)&&(ev.key==='c'||ev.key==='C')))return;
        if(!c.isConnected||!c.offsetParent)return;          // 다른 탭이 떠 있으면 무시
        const t=ev.target;
        if(t&&(t.tagName==='INPUT'||t.tagName==='TEXTAREA'||t.tagName==='SELECT'||t.isContentEditable))return;
        if(!c.querySelector('td.g4cp,td.g4sel'))return;     // 칠해진 범위가 없으면 기본 동작
        ev.preventDefault(); if(c._g4CopySel)c._g4CopySel();};
      // document 하나만 — c 에도 걸면 keydown 이 버블링돼 두 번 복사된다.
      document.addEventListener('keydown',onKey);
    }


    /* ══ 항목보기 (2026-09-06 — 410 과 같은 방식) ═══════════════════════════
         체크 해제 = 그 컬럼 숨김 · ▲▼ 로 순서 변경. 앞(head)/뒤(tail) 그룹은 서로 안 섞인다
         (일자칸이 가운데 있어 그룹을 넘나들면 표가 깨진다).
         저장 = localStorage(H_LS/T_LS) — 헤더 드래그가 쓰던 키를 그대로 쓴다. */
    const HIDE_LS='g420_hidecols';
    const loadHide=()=>{try{const s=JSON.parse(localStorage.getItem(HIDE_LS)||'[]');
      return new Set(Array.isArray(s)?s:[]);}catch(_){return new Set();}};
    const openColPick=()=>{
      const old=document.getElementById('g4-colpick'); if(old)old.remove();
      const hid=loadHide();
      const ov=document.createElement('div');
      ov.id='g4-colpick';
      ov.style.cssText='position:fixed;inset:0;z-index:1300;background:rgba(20,32,54,.34);'
                      +'display:flex;align-items:center;justify-content:center';
      const item=(k,defs,grp)=>`<div class="g4cp-r" data-k="${k}" data-grp="${grp}"
           style="display:flex;align-items:center;gap:7px;padding:4px 8px;border-bottom:1px solid #eef1f6;
                  cursor:grab;user-select:none;-webkit-user-select:none">
          <span style="color:#b6c2d4;font-size:11px" title="끌어서 순서 변경">⠿</span>
          <input type="checkbox" ${hid.has(k)?'':'checked'} data-ck="${k}">
          <span style="flex:1;font-size:12.5px">${defs[k].t}</span>
          <button class="btn ghost g4cp-up" data-k="${k}" style="padding:0 6px;font-size:11px">▲</button>
          <button class="btn ghost g4cp-dn" data-k="${k}" style="padding:0 6px;font-size:11px">▼</button>
        </div>`;
      ov.innerHTML=`<div style="background:#fff;border-radius:10px;width:420px;max-height:78vh;
             display:flex;flex-direction:column;box-shadow:0 8px 30px rgba(20,40,80,.28)">
          <div style="padding:10px 12px;border-bottom:1px solid #e3e9f2;font-weight:700;color:#16305c">
            항목보기 <span style="font-weight:400;font-size:11px;color:#7b8aa0">체크 해제 = 숨김 · 행을 끌거나 ▲▼ 로 순서 변경</span></div>
          <div style="flex:1;overflow:auto;padding:4px 0">
            <div style="padding:4px 10px;font-size:11px;color:#7b8aa0;font-weight:700">앞쪽 컬럼</div>
            <div id="g4cp-h">${hOrd.map(k=>item(k,ALLDEF,'head')).join('')}</div>
            <div style="padding:6px 10px 4px;font-size:11px;color:#7b8aa0;font-weight:700">일자칸 뒤 컬럼</div>
            <div id="g4cp-t">${tOrd.map(k=>item(k,ALLDEF,'tail')).join('')}</div>
          </div>
          <div style="padding:9px 12px;border-top:1px solid #e3e9f2;display:flex;gap:6px;justify-content:flex-end">
            <button class="btn ghost" id="g4cp-reset">초기화</button>
            <div style="flex:1"></div>
            <button class="btn ghost" id="g4cp-x">닫기</button>
            <button class="btn" id="g4cp-ok" style="background:#1c47a0;color:#fff">적용</button>
          </div></div>`;
      document.body.appendChild(ov);
      const q=s=>ov.querySelector(s);
      /* ★모달 mousedown 은 **버블 단계에서만** 막는다(캡처 아님).
           캡처로 stopPropagation 하면 아래에 붙인 행 드래그 핸들러까지 못 받는다
           (2026-09-06 실측 — 드래그가 안 먹던 원인). 표는 모달 바깥이라
           버블만 끊어도 범위선택으로 새지 않는다. */
      ov.addEventListener('mousedown',e=>e.stopPropagation());
      ov.onclick=e=>{if(e.target===ov)ov.remove();};
      q('#g4cp-x').onclick=()=>ov.remove();
      /* ★▲▼ 도 그룹 경계를 넘는다(2026-09-07 교정).
           종전엔 `if(!sib)return` 으로 그룹 첫/끝에서 **아무 일도 안 일어났다**.
           앞/뒤 컬럼이 서로 다른 <div>(#g4cp-h / #g4cp-t)라 형제가 아니기 때문.
           사용자는 올렸다고 여기고 [적용]을 누르는데 순서가 그대로여서
           "위로 올리면 제일 끝으로 저장된다"로 보였다(실사용 신고).
           드래그는 이미 경계를 넘으므로(아래 onUp), ▲▼ 도 같은 규칙으로 맞춘다. */
      const move=(k,dir)=>{const row=ov.querySelector(`.g4cp-r[data-k="${k}"]`); if(!row)return;
        const box=row.parentElement;
        const sib=dir<0?row.previousElementSibling:row.nextElementSibling;
        if(sib){
          if(dir<0)box.insertBefore(row,sib); else box.insertBefore(sib,row);
          return;
        }
        const other=(box.id==='g4cp-h')?ov.querySelector('#g4cp-t'):ov.querySelector('#g4cp-h');
        if(!other)return;                      // 단일 그룹이면 경계에서 멈춘다
        if(dir<0)other.appendChild(row);       // 뒤 그룹 첫줄 ▲ → 앞 그룹 맨 끝
        else     other.insertBefore(row,other.firstElementChild);  // 앞 그룹 끝줄 ▼ → 뒤 그룹 첫줄
        row.dataset.grp=(other.id==='g4cp-h')?'head':'tail';};
      ov.querySelectorAll('.g4cp-up').forEach(b=>b.onclick=()=>move(b.dataset.k,-1));
      ov.querySelectorAll('.g4cp-dn').forEach(b=>b.onclick=()=>move(b.dataset.k, 1));

      /* ══ 행 끌어서 순서 변경 (2026-09-06) ═══════════════════════════════
           ★HTML5 draggable 은 쓰지 않는다 — 텍스트 선택이 먼저 잡혀 드래그가 시작되지
             않고 파란 블록만 생긴다(410 에서 밟은 함정). mousedown/mousemove/mouseup +
             preventDefault + user-select:none 으로 직접 구현한다.
           ★5px 이상 움직여야 '이동'으로 판정 → 같은 행에서 "클릭=체크토글 / 끌면=이동"이
             공존한다. 체크박스·▲▼ 버튼 위에서는 시작하지 않는다.
           ★그룹(앞/뒤) 경계를 넘으면 놓은 자리의 그룹을 물려받는다 — 일자칸 기준
             어느 편에 설지가 그렇게 정해진다. */
      let dK=null,dY=0,dMoved=false;
      const rowsOf=()=>[...ov.querySelectorAll('.g4cp-r')];
      const rowAtY=(y)=>{const rs=rowsOf(); if(!rs.length)return null;
        let best=rs[0],bd=1e9;
        for(const r of rs){const b=r.getBoundingClientRect();
          const d=(y<b.top)?(b.top-y):((y>b.bottom)?(y-b.bottom):0);
          if(d<bd){bd=d;best=r;}}
        return best;};
      ov.addEventListener('mousedown',e=>{
        const row=e.target.closest&&e.target.closest('.g4cp-r'); if(!row)return;
        if(e.target.tagName==='INPUT')return;              // 체크박스는 브라우저가 처리
        if(e.target.closest('.g4cp-up,.g4cp-dn'))return;   // ▲▼ 는 클릭으로
        e.preventDefault();                                 // 텍스트 선택 차단(파란 블록 방지)
        dK=row.dataset.k; dY=e.clientY; dMoved=false;
        row.style.opacity='.55';
      });
      const onMove=e=>{
        if(!dK)return;
        if(!ov.isConnected){dK=null;document.removeEventListener('mousemove',onMove);return;}
        if(!dMoved&&Math.abs(e.clientY-dY)<5)return;        // 5px 미만 = 아직 클릭
        dMoved=true;
        const over=rowAtY(e.clientY);
        rowsOf().forEach(x=>{if(x!==over)x.style.borderTop='';});
        if(over&&over.dataset.k!==dK)over.style.borderTop='2px solid #2563eb';
      };
      const onUp=e=>{
        if(!dK)return;
        if(!ov.isConnected){dK=null;document.removeEventListener('mouseup',onUp);return;}
        const k=dK; dK=null;
        rowsOf().forEach(x=>{x.style.opacity='';x.style.borderTop='';});
        if(!dMoved)return;                                  // 안 움직였으면 클릭 = 체크 토글(기본동작)
        const over=rowAtY(e.clientY);
        if(!over||over.dataset.k===k)return;
        const src=rowsOf().find(r=>r.dataset.k===k); if(!src)return;
        const box=over.parentElement;                       // 놓은 자리의 그룹을 물려받는다
        const sb=over.getBoundingClientRect();
        if(e.clientY < sb.top+sb.height/2) box.insertBefore(src,over);
        else box.insertBefore(src,over.nextSibling);
        src.dataset.grp = box.id==='g4cp-h' ? 'head' : 'tail';
      };
      document.addEventListener('mousemove',onMove);
      document.addEventListener('mouseup',onUp);
      q('#g4cp-reset').onclick=()=>{
        try{localStorage.removeItem(H_LS);localStorage.removeItem(T_LS);
            localStorage.removeItem(HIDE_LS);}catch(_){}
        ov.remove(); draw();};
      q('#g4cp-ok').onclick=()=>{
        const ord=(sel)=>[...ov.querySelectorAll(sel+' .g4cp-r')].map(r=>r.dataset.k);
        const nh=ord('#g4cp-h'), nt=ord('#g4cp-t');
        const nhid=[...ov.querySelectorAll('input[data-ck]')]
          .filter(x=>!x.checked).map(x=>x.dataset.ck);
        try{localStorage.setItem(H_LS,JSON.stringify(nh));
            localStorage.setItem(T_LS,JSON.stringify(nt));
            localStorage.setItem(HIDE_LS,JSON.stringify(nhid));}catch(_){}
        hOrd.length=0; nh.forEach(k=>hOrd.push(k));
        tOrd.length=0; nt.forEach(k=>tOrd.push(k));
        ov.remove(); draw();
      };
    };
    /* ★버튼 배선 — 실패를 삼키지 않는다(2026-09-06).
         종전엔 openColPick 안에서 예외가 나면 창이 조용히 안 뜨고 원인을 알 수 없었다.
         오류를 콘솔+알림으로 드러내야 무엇이 문제인지 바로 보인다. */
    {const cb=g('#g4-col');
     if(cb)cb.onclick=(e)=>{
       e.preventDefault(); e.stopPropagation();
       try{openColPick();}
       catch(err){console.error('[420 항목보기]',err);
                  alert('항목보기를 열지 못했습니다: '+(err&&err.message||err));}
     };}
    // 헤더 우클릭 = 항목보기 + 복사 메뉴(410 과 같은 진입)
    c.querySelectorAll('.g4tbl thead th,.g4tbl tbody').forEach(el=>{
      el.oncontextmenu=e=>{
        e.preventDefault();
        const old=document.getElementById('g4-ctx'); if(old)old.remove();
        const m=document.createElement('div'); m.id='g4-ctx';
        m.style.cssText=`position:fixed;left:${e.clientX}px;top:${e.clientY}px;z-index:1400;
          background:#fff;border:1px solid #cfd8e6;border-radius:6px;box-shadow:0 6px 20px rgba(20,40,80,.22);
          font-size:12.5px;min-width:150px;overflow:hidden`;
        m.innerHTML=['항목보기','선택영역 복사','전체 복사']
          .map((t,i)=>`<div data-i="${i}" style="padding:7px 12px;cursor:pointer">${t}</div>`).join('');
        document.body.appendChild(m);
        m.querySelectorAll('div[data-i]').forEach(d=>{
          d.onmouseenter=()=>d.style.background='#eef4ff';
          d.onmouseleave=()=>d.style.background='';});
        /* ★바깥클릭 닫기와 항목실행의 순서 문제 — 410 에서 이미 겪은 그대로다
             (screens.prod.js:1762 주석). mousedown 이 click 보다 **먼저** 오므로
             바깥클릭 핸들러가 메뉴를 remove 한 뒤 click 이 죽은 노드에서 발생 →
             "항목보기를 눌러도 아무 일도 안 일어난다".
           ⟹ 메뉴 실행도 mousedown 에서 처리하고, 바깥클릭 닫기는 메뉴 안을 제외한다. */
        const kill=()=>{m.remove();document.removeEventListener('mousedown',outside,true);};
        const outside=ev2=>{if(!m.contains(ev2.target))kill();};
        setTimeout(()=>document.addEventListener('mousedown',outside,true),0);
        m.addEventListener('mousedown',ev2=>{
          ev2.preventDefault(); ev2.stopPropagation();   // 표의 범위선택으로 새지 않게
          const t=ev2.target.closest&&ev2.target.closest('[data-i]'); if(!t)return;
          const i=+t.dataset.i; kill();
          try{ if(i===0)openColPick(); else if(i===1)_copySel(); else _copyAll(); }
          catch(err){console.error('[420 메뉴]',err);alert('실행 실패: '+(err&&err.message||err));}
        });
      };
    });

    /* ══ 엑셀 (화면 색상 그대로) ══════════════════════════════════════════
         ★DOM 에서 읽는다 — 항목보기(숨김·순서)·집계/상세 전환이 화면에 이미 반영돼 있어
           "보이는 대로" 받는 것이 사용자가 기대하는 동작이다.
         ★진짜 xlsx 로 내보낸다(core.js downloadXLS). HTML→.xls 는 엑셀이 서식(색)을 버린다. */
    {const xb=g('#g4-xls'); if(xb)xb.onclick=()=>{
      const tbl=c.querySelector('.g4tbl');
      if(!tbl||!tbl.tBodies.length||!tbl.tBodies[0].rows.length){alert('조회 결과가 없습니다.');return;}
      const hr=tbl.tHead&&tbl.tHead.rows[0];
      const cols=hr?[...hr.cells].map(th=>({t:(th.innerText||'').trim(),
                                            w:Math.max(6,Math.min(28,(th.innerText||'').trim().length*2+4))})):[];
      const bgOf=td=>{const m=/background:\s*(#[0-9a-fA-F]{6})/.exec(td.getAttribute('style')||'');
        return m?m[1]:'';};
      const rows=[];
      [...tbl.tBodies].forEach(tb=>{
        for(const tr of tb.rows){
          if(tr.cells.length!==cols.length)continue;       // 소계·합계(colspan) 행은 건너뜀
          rows.push([...tr.cells].map(td=>{
            const v=(td.innerText||'').trim(), bg=bgOf(td)||bgOf(tr);
            const o={v:v};
            if(bg)o.bg=bg;
            if(/^-?[\d,]+(\.\d+)?$/.test(v)&&v!=='')o.v=v;   // '10/10' 등은 문자로 남긴다
            return o;}));
        }});
      const stamp=(st.from||'').replace(/-/g,'').slice(2);
      downloadXLS(`가공생산진척_${stamp}`, cols, rows, {sheet:'가공생산진척'});
    };}

    // 선택 없이 눌러도 열린다 → 빈 50행 수기입력(레거시 동일)
    //   선택셀은 (자도번)별로 합산 — 같은 자도번의 여러 일자를 고르면 수량이 더해진다.
    g('#g4-issue').onclick=()=>{
      const cs=selCells();
      if(!cs.length){openIssueModal([]);return;}
      const agg=new Map();
      cs.forEach(x=>{const k=rkey(x.r);
        const cur=agg.get(k);
        if(cur)cur.qty+=x.rem; else agg.set(k,{r:x.r,qty:x.rem});});
      openIssueModal(Array.from(agg.values()).map(v=>Object.assign({},v.r,{_qty:v.qty})));
    };
  };
  /* 컷팅간판 출력(전표발행) — 레거시 w_pr_input_017: MAX(box_no)+1 채번 후 PR_T_INDI_CUTTING 등록
     · 드래그 선택 → 그 행들이 채워진 채로 열림(출력수량=생산계획−완료, 수정 가능)
     · 선택 없이 열면 빈 50행 → 자도번 직접 입력 시 규격·공정순서 자동조회 */
  const BLANK=50;
  const openIssueModal=(picked)=>{
    const mk=(r)=>({assy:(r&&r.assy)||'',upper:(r&&r.upper)||'',jado:(r&&r.jado)||'',
      wcd:(r&&r.wcd)||'',diam:(r&&r.diam)||0,thick:(r&&r.thick)||0,length:(r&&r.length)||0,
      procstr:'',seqno:0,
      qty:r?(+r._qty||Math.max(0,(+r.plan_qty||0)-(+r.finish||0))||(+r.plan_qty||0)):0});
    const rows=picked.length?picked.map(mk):Array.from({length:BLANK},()=>mk(null));
    const ov=document.createElement('div');
    ov.style.cssText='position:fixed;inset:0;background:rgba(0,0,0,.35);z-index:9999;display:flex;align-items:center;justify-content:center';
    const draw=()=>{
      const tot=rows.reduce((s,r)=>s+(+r.qty||0),0);
      ov.innerHTML=`<div style="background:#fff;border-radius:10px;width:1100px;max-width:96vw;max-height:88vh;display:flex;flex-direction:column;box-shadow:0 10px 40px rgba(0,0,0,.3);font-size:13px">
        <div style="flex:0 0 auto;display:flex;justify-content:space-between;align-items:center;padding:12px 16px;border-bottom:1px solid #e5e9f0">
          <b style="font-size:15px">🧾 컷팅간판 출력 (전표발행)</b><span id="is-x" style="cursor:pointer;font-size:18px;color:#888">✕</span></div>
        <div style="flex:1;min-height:0;overflow:auto;padding:0 16px">
          <table class="tbl fit" style="font-size:11px;white-space:nowrap"><thead><tr>
            <th class="num">SEQ</th><th>Assy도번</th><th>Assy도번작업처</th><th>도번</th><th>상위도번작업처</th>
            <th>자도번</th><th>공정순서</th><th class="num">작업순서</th>
            <th class="num">지름</th><th class="num">두께</th><th class="num">길이</th><th class="num">출력수량</th></tr></thead>
          <tbody>${rows.map((r,i)=>`<tr>
            <td class="num">${i+1}</td><td class="center">${esc(r.assy)}</td><td class="center">${esc(r.wcd)}</td>
            <td class="center">${esc(r.upper)}</td><td class="center">${esc(r.wcd)}</td>
            <td><input class="inp is-j" data-i="${i}" value="${esc(r.jado)}" placeholder="자도번" autocomplete="off" style="width:130px"></td>
            <td class="bcap" style="max-width:280px;overflow:hidden;text-overflow:ellipsis" title="${esc(r.procstr)}">${esc(r.procstr)}</td>
            <td class="num">${r.seqno||0}</td>
            <td class="num">${r.diam?(+r.diam).toFixed(2):'0.00'}</td><td class="num">${r.thick?(+r.thick).toFixed(2):'0.00'}</td>
            <td class="num">${r.length?(+r.length).toFixed(2):'0.00'}</td>
            <td class="num"><input class="inp is-q" data-i="${i}" type="number" min="0" value="${r.qty}" style="width:80px;text-align:right;background:#ffffcc"></td>
          </tr>`).join('')}</tbody>
          <tfoot><tr class="grandtot"><td colspan="11">${nf(rows.filter(r=>r.jado&&+r.qty>0).length)}건</td><td class="num"><b id="is-tot">${nf(tot)}</b></td></tr></tfoot></table></div>
        <div id="is-msg" style="flex:0 0 auto;padding:6px 16px;min-height:18px;font-size:12px"></div>
        <div style="flex:0 0 auto;display:flex;gap:8px;justify-content:flex-end;padding:10px 16px;border-top:1px solid #e5e9f0">
          <button class="btn" id="is-go" style="background:#1c47a0;color:#fff">🖨 출력(전표발행)</button>
          <button class="btn" id="is-close">닫기</button></div></div>`;
      const q=s=>ov.querySelector(s);
      const msg=(t,ok)=>{q('#is-msg').innerHTML=`<span style="color:${ok?'#1c7c3a':'#c0392b'}">${esc(t)}</span>`;};
      const retot=()=>{q('#is-tot').textContent=nf(rows.reduce((s,r)=>s+(+r.qty||0),0));};
      ov.querySelectorAll('.is-q').forEach(inp=>inp.onchange=()=>{
        rows[+inp.dataset.i].qty=Math.max(0,+inp.value||0);retot();});
      // 자도번 수기입력 → 규격·공정순서 자동조회(레거시: 자도번 치면 나머지가 채워짐)
      ov.querySelectorAll('.is-j').forEach(inp=>{
        const fill=async()=>{const i=+inp.dataset.i,v=inp.value.trim();
          if(!v){Object.assign(rows[i],{jado:'',upper:'',wcd:'',diam:0,thick:0,length:0,procstr:''});draw();return;}
          if(rows[i].jado===v&&rows[i].procstr)return;
          try{const d=await(await fetch(`${API_BASE}/api/gagong/sheet/lookup?jado=${encodeURIComponent(v)}`)).json();
            if(!d.ok){msg(d.msg||`자도번 ${v} 없음`,false);return;}
            Object.assign(rows[i],{jado:d.jado,upper:d.upper||'',wcd:d.wcd||'',
              diam:d.diam,thick:d.thick,length:d.length,procstr:d.procstr||'',procs:d.procs||[]});
            if(!rows[i].assy)rows[i].assy=d.upper||'';
            msg('',true);draw();
            const nx=ov.querySelector(`.is-q[data-i="${i}"]`);if(nx){nx.focus();nx.select();}
          }catch(e){msg('자도번 조회 실패',false);}};
        inp.onchange=fill;
        inp.onkeyup=e=>{if(e.key==='Enter')fill();};});
      q('#is-x').onclick=q('#is-close').onclick=()=>ov.remove();
      q('#is-go').onclick=async()=>{
        const send=rows.filter(r=>(+r.qty||0)>0);
        if(!send.length){msg('출력수량이 0보다 큰 행이 없습니다.',false);return;}
        q('#is-go').disabled=true;
        try{
          const d=await(await fetch(`${API_BASE}/api/gagong/sheet/issue`,{method:'POST',
            headers:{'Content-Type':'application/json'},
            body:JSON.stringify({rows:send,user:'웹',ymd:st.from})})).json();
          if(!d.ok){msg(d.msg||'발행 실패',false);q('#is-go').disabled=false;return;}
          msg(`✔ ${d.msg}`,true);
          printSheets(d.sheets||[]);
          setTimeout(()=>{ov.remove();st.sel.clear();load();},600);
        }catch(e){msg('발행 실패',false);q('#is-go').disabled=false;}
      };
    };
    draw(); document.body.appendChild(ov);
  };
  /* 가공이동전표(작업지시서 및 공정이동표) 인쇄 — 발행된 바코드별 1장 */
  const printSheets=(sheets)=>{
    if(!sheets.length)return;
    const pg=s=>`<div class="pg">
      <div class="ttl"><span class="cat">${esc(s.cat||'')}</span>작업지시서 및 공정이동표 (Processing)</div>
      <table class="hd">
        <tr><td class="lbl" style="width:13%">Part/No</td><td class="big" style="width:27%">${esc(s.assy||'')}</td>
          <td class="lbl" style="width:7%">SPEC</td>
          <td style="padding:0" colspan="4"><table class="sp">
            <!-- ★2026-08-24 바코드 위 빈칸에 현장 생산일자(PLAN_YMD) 표시 — 현장 요청 -->
            <tr><th style="width:13%">외경(Ø)</th><th style="width:13%">두께(T)</th><th style="width:13%">길이(L)</th><th style="width:15%">중량(kg)</th><th style="width:11%">LOT</th>
                <th style="width:35%" class="pymd">${(()=>{const y=(''+(s.ymd||'')).trim();
                  return y.length>=6?`생산일자 ${y.slice(0,2)}/${y.slice(2,4)}/${y.slice(4,6)}`:'&nbsp;';})()}</th></tr>
            <tr><td>${s.diam?(+s.diam).toFixed(2):''}</td><td>${s.thick?(+s.thick).toFixed(2):''}</td>
                <td>${s.length?Math.round(s.length):''}</td><td>${s.weight||''}</td>
                <td class="lot">${nf(s.qty||0)}</td>
                <td class="bcw"><img src="${API_BASE}/api/barcode/code128?text=${encodeURIComponent(s.barcode||'')}&h=90&scale=2&quiet=4">
                  <div class="bcn">${esc(s.barcode||'')}</div></td></tr></table></td></tr>
        <tr><td class="lbl">Sub number</td><td class="big">${esc(s.mat||'')}</td>
          <td class="lbl">창고</td><td style="width:16%">${esc(s.whnm||s.wh||'')}</td>
          <td style="width:8%">${esc(s.lineno||'')}</td>
          <td class="lbl" style="width:10%">신규도면</td><td class="lbl" style="width:12%">총중량(kg)</td></tr></table>
      <table class="bd"><tr>
        <td class="dw">${s.draw?`<div class="dwbox"><img src="${esc(s.draw)}"></div>`:''}</td>
        <td style="padding:0;vertical-align:top"><table class="pr">
          <tr><th style="width:8%">순서</th><th style="width:18%">공정명</th><th>SPEC</th><th style="width:9%">완료<br>수량</th><th style="width:9%">불량<br>수량</th></tr>
          ${Array.from({length:10},(_,i)=>{const p=(s.procs||[])[i]||{};
            return `<tr><td>${i+1}</td><td>${esc(p.nm||'')}</td><td style="text-align:left;padding-left:6px">${esc(p.spec||'')}</td><td></td><td></td></tr>`;}).join('')}
          <tr><td colspan="5" style="height:120px;border-left:0;border-right:0;border-bottom:0"></td></tr>
        </table></td></tr></table></div>`;
    const w=window.open('','_blank');
    if(!w){alert('팝업이 차단되었습니다. 허용 후 다시 시도하세요.');return;}
    w.document.write(`<html><head><title>가공이동전표</title><meta charset="utf-8"><style>
      @page{size:A4 landscape;margin:6mm}
      /* A4 가로 = 297x210mm, 여백 6mm → 실제 인쇄영역 285x198mm.
         ★vh 는 인쇄시 화면높이를 따라 부정확 → mm 고정(2026-08-20 잘림·빈페이지 수정) */
      html,body{height:auto}
      body{font-family:'맑은 고딕',Malgun Gothic,sans-serif;font-size:12px;margin:0;
           -webkit-print-color-adjust:exact;print-color-adjust:exact}
      .pg{border:2px solid #000;height:196mm;box-sizing:border-box;
          display:flex;flex-direction:column;overflow:hidden;page-break-inside:avoid}
      .pg+.pg{page-break-before:always}
      table{border-collapse:collapse;width:100%;table-layout:fixed}
      .ttl{position:relative;text-align:center;font-size:21px;font-weight:700;
           padding:8px 0;border-bottom:2px solid #000}
      .cat{position:absolute;left:8px;top:8px;font-size:13px;font-weight:400}
      .hd td,.sp th,.sp td,.pr th,.pr td{border:1px solid #000;padding:3px;text-align:center;
           overflow:hidden;text-overflow:ellipsis}
      .hd>tbody>tr>td{border-top:0}
      .lbl{font-weight:700}
      .big{font-size:21px;font-weight:700}
      .sp{table-layout:auto}                /* 바코드 폭 확보(fixed 상속 해제) */
      .sp th{font-weight:700;font-size:12px}
      .sp td{height:9mm}
      .lot{font-size:19px;font-weight:700;white-space:nowrap}
      .pymd{font-size:13px;font-weight:700;white-space:nowrap}   /* 현장 생산일자 */
      /* 바코드 칸: 폭에 맞춰 축소되도록 max-width 100%(잘림 방지, 2026-08-20) */
      .bcw{padding:1px !important;overflow:visible}
      .bcw img{height:auto;width:52mm;max-width:100%;display:block;margin:0 auto}
      .bcn{font-size:9px;letter-spacing:.5px;white-space:nowrap}
      .ttl,.hd{flex:0 0 auto}
      /* ★2026-08-24 도면 하단 잘림 수정.
         .pg(196mm, overflow:hidden) 안에서 .bd 가 남는 높이를 차지하는데, 도면 img 에
         max-height:150mm 고정이 걸려 있어 제목+헤더(≈50mm)와 합치면 196mm 를 넘겨
         잘려 나갔다(공정행이 많은 전표일수록 심함).
         → .bd 를 높이 0 기준 flex 로 잡고(min-height:0), 도면은 셀 높이(100%)에만 맞춘다. */
      .bd{flex:1 1 auto;min-height:0;height:0}
      .bd>tbody>tr>td{vertical-align:top}
      .dw{border:1px solid #000;width:45%;vertical-align:middle !important;text-align:center;padding:4px;
          overflow:hidden}
      /* ★도면 이미지 — td 안에서 남는 높이에만 맞춘다(2026-08-28 보강).
         td 는 높이가 내용에 따라 늘어나므로 max-height:100% 만으로는 기준이 안 잡힐 수 있다.
         → 이미지를 감싼 블록에 100% 를 주고 img 는 그 안에서 contain 시킨다. */
      .dw>.dwbox{height:100%;display:flex;align-items:center;justify-content:center;overflow:hidden}
      .dw img{max-width:100%;max-height:100%;width:auto;height:auto;object-fit:contain;display:block;margin:0 auto}
      .pr th{font-weight:700}.pr td{height:8mm}
      </style></head><body>${sheets.map(pg).join('')}
      <script>
      /* ★도면 이미지 로드를 기다렸다가 인쇄한다(2026-08-28).
         종전엔 setTimeout 350ms 고정이라 도면이 큰 전표는 이미지가 덜 그려진 채로
         인쇄창이 떠서 **아래가 회색 박스로 덮여** 나왔다(어떤 건 되고 어떤 건 안 되는 이유).
         .dw td 의 max-height:100% 도 이미지 크기가 확정돼야 계산되므로 로드 완료가 전제. */
      (function(){
        var imgs=[].slice.call(document.images), left=imgs.length;
        function go(){ setTimeout(function(){ window.print(); }, 250); }
        if(!left) return go();
        var fired=false;
        function done(){ if(--left<=0 && !fired){ fired=true; go(); } }
        imgs.forEach(function(im){
          if(im.complete && im.naturalWidth>0) done();
          else { im.addEventListener('load',done); im.addEventListener('error',done); }
        });
        /* 안전망: 이미지가 끝내 안 오면 3초 뒤 그냥 인쇄 */
        setTimeout(function(){ if(!fired){ fired=true; window.print(); } }, 3000);
      })();
      <\/script>
      </body></html>`);
    w.document.close(); w.focus();
  };
  /* 가공바코드실적처리 팝업 (레거시 w_pr_input_018) — 스캔→정보조회→양품/불량→처리바코드 재스캔→등록/취소 */
  const openBcModal=()=>{
    let bc={box:null,info:null};
    const bcNum=v=>{const m=String(v||'').trim().match(/(\d+)\s*$/);return m?+m[1]:null;};
    const ov=document.createElement('div');
    ov.style.cssText='position:fixed;inset:0;background:rgba(0,0,0,.35);z-index:9999;display:flex;align-items:center;justify-content:center';
    const today=iso(new Date());
    const render=()=>{
      const i=bc.info;
      ov.innerHTML=`<div style="background:#fff;border-radius:10px;width:640px;max-width:94vw;box-shadow:0 10px 40px rgba(0,0,0,.3);font-size:13px">
        <div style="display:flex;justify-content:space-between;align-items:center;padding:12px 16px;border-bottom:1px solid #e5e9f0">
          <b style="font-size:15px">📷 바코드실적처리 (가공지시)</b><span id="bc-x" style="cursor:pointer;font-size:18px;color:#888">✕</span></div>
        <div style="padding:16px">
          <div style="display:grid;grid-template-columns:auto 1fr auto 1fr;gap:8px 10px;align-items:center;background:#f2f7ff;padding:12px;border-radius:8px">
            <label class="tl">기준일자</label><input class="inp" type="date" id="bc-ymd" value="${today}">
            <label class="tl">바코드</label><input class="inp" id="bc-scan1" placeholder="${i?(i.done?'재스캔=실적취소':'재스캔=실적등록'):'바코드 스캔(Enter)'}" autocomplete="off" style="font-size:15px;${i?(i.done?'background:#fdecea':'background:#eaf6ec'):''}">
            <label class="tl">양품수량</label><input class="inp" id="bc-good" type="number" value="${i?(i.default_qty||0):''}" style="text-align:right"${i&&i.done?' readonly':''}>
            <label class="tl">불량수량</label><input class="inp" id="bc-bad" type="number" value="0" style="text-align:right"${i&&i.done?' readonly':''}>
          </div>
          <div style="display:grid;grid-template-columns:auto 1fr auto 1fr;gap:6px 10px;align-items:center;margin-top:12px;padding:12px;border:1px solid #e5e9f0;border-radius:8px">
            <label class="tl">대표도번</label><b>${i?esc(i.assy):''}</b><label class="tl">간판수량</label><b>${i?nf(i.plan_qty):''}</b>
            <label class="tl">자도번</label><b>${i?esc(i.mat)+' <span style="color:#888;font-weight:400">'+esc(i.matnm||'')+'</span>':''}</b><label class="tl">가공완료</label><b>${i?nf(i.prod_qty):''}</b>
            <label class="tl">불량이력</label><span>${i?(i.err_cnt+'건 / '+nf(i.err_qty)+'개'):''}</span><label class="tl">입고창고</label><b>${i?esc(i.wh):''}</b>
            <label class="tl">원소재</label><span>${i?(i.won?esc(i.won)+' <span style="color:#888">단중 '+i.weight+'</span>':'<span style="color:#888">없음</span>'):''}</span>
            <label class="tl">하위자재</label><span>${i?(i.bom_cnt?i.bom_cnt+'품목 차감':'<span style="color:#888">없음</span>'):''}</span>
          </div>
          ${i?`<div style="margin-top:8px;padding:8px 10px;border-radius:6px;font-size:12px;background:${i.done?'#fdecea':'#eaf6ec'};color:${i.done?'#a5281b':'#1c7c3a'}">
            ${i.done?'● 실적완료 상태입니다. 바코드를 <b>한번 더 스캔</b>하면 취소 확인창이 뜹니다.':'○ 미실적입니다. 수량 확인 후 바코드를 <b>한번 더 스캔</b>하면 실적이 등록됩니다.'}</div>`:''}
          <div id="bc-msg" style="margin-top:8px;min-height:18px;font-size:12px"></div>
          <div style="display:flex;gap:8px;justify-content:flex-end;margin-top:6px">
            ${i&&i.done?`<button class="btn" id="bc-cancel" style="background:#c0392b;color:#fff">🗑 실적취소</button>`:''}
            <button class="btn" id="bc-reg" style="background:#1c47a0;color:#fff"${i&&!i.done?'':' disabled'}>✔ 실적등록</button>
            <button class="btn" id="bc-close2">닫기</button></div>
        </div></div>`;
      const q=s=>ov.querySelector(s);
      const msg=(t,ok)=>{q('#bc-msg').innerHTML=`<span style="color:${ok?'#1c7c3a':'#c0392b'}">${esc(t)}</span>`;};
      const focusBc=()=>{const el=ov.querySelector('#bc-scan1');
        if(el){el.value='';el.focus();el.select();}};   // 항상 바코드칸으로 복귀(연속스캔)
      const reload=async(m,ok)=>{const s=await(await fetch(`${API_BASE}/api/gagong/barcode/scan?barcode=${bc.box}`)).json();
        bc.info=s.ok?s:null;render();if(m)msg(m,ok);focusBc();requestAnimationFrame(focusBc);};
      // ★등록/취소 완료 후 초기화(2026-08-20) — 다음 품번을 바로 스캔할 수 있게 화면을 비운다.
      //   결과 메시지는 남겨 무엇이 처리됐는지 확인 가능.
      const resetAfter=(m,ok)=>{bc.box=null;bc.info=null;render();msg(m,ok);
        focusBc();requestAnimationFrame(focusBc);setTimeout(focusBc,60);};
      // ★1회=조회 / 2회(동일바코드 재스캔)=미실적이면 등록·완료면 취소확인 (레거시 018 + 사용자 요청)
      const doScan=async()=>{const el=q('#bc-scan1'),v=el.value.trim();if(!v)return;
        if(bc.info&&bc.box===bcNum(v)){el.value='';return bc.info.done?doCancel():doReg();}
        try{const d=await(await fetch(`${API_BASE}/api/gagong/barcode/scan?barcode=${encodeURIComponent(v)}`)).json();
          if(!d.ok){bc.info=null;bc.box=null;render();q('#bc-scan1').value=v;q('#bc-scan1').select();msg(d.msg,false);return;}
          bc.box=d.box_no;bc.info=d;render();q('#bc-scan1').focus();
          msg(d.done?`실적완료된 전표입니다(가공완료 ${nf(d.prod_qty)}). 재스캔 시 취소.`
                    :`조회 완료 — 수량 확인 후 재스캔하면 등록됩니다.`,!d.done);
        }catch(e){msg('조회 실패',false);}};
      const doReg=async()=>{if(!bc.info||bc.info.done)return;
        try{const d=await(await fetch(`${API_BASE}/api/gagong/barcode/register`,{method:'POST',headers:{'Content-Type':'application/json'},
          body:JSON.stringify({box_no:bc.box,good_qty:+q('#bc-good').value||0,bad_qty:+q('#bc-bad').value||0,user:'웹',ymd:q('#bc-ymd').value})})).json();
          if(d.ok){const mv=(d.moved||[]).map(x=>`${x.kind} ${x.code} ${x.qty>0?'+':''}${x.qty}`).join(' / ');
            resetAfter(`✔ [${d.box_no}] ${d.msg}${mv?' — '+mv:''} · 다음 바코드를 스캔하세요`,true);}
          else msg(d.msg,false);
        }catch(e){msg('등록 실패',false);}};
      const doCancel=async()=>{if(!bc.info)return;
        if(!confirm(`[실적취소]\n\n자도번 ${bc.info.mat}\n가공완료 ${nf(bc.info.prod_qty)}개\n\n이 전표의 실적을 취소할까요?\n(가공창고 재고와 자재 차감분이 되돌아갑니다)`)){q('#bc-scan1').focus();return;}
        try{const d=await(await fetch(`${API_BASE}/api/gagong/barcode/cancel`,{method:'POST',headers:{'Content-Type':'application/json'},
          body:JSON.stringify({box_no:bc.box,user:'웹',ymd:q('#bc-ymd').value})})).json();
          if(d.ok)resetAfter(`✔ [${d.box_no}] ${d.msg} · 다음 바코드를 스캔하세요`,true); else msg(d.msg,false);
        }catch(e){msg('취소 실패',false);}};
      q('#bc-x').onclick=q('#bc-close2').onclick=()=>ov.remove();
      q('#bc-scan1').onkeyup=e=>{if(e.key==='Enter')doScan();};
      if(q('#bc-reg'))q('#bc-reg').onclick=doReg;
      if(q('#bc-cancel'))q('#bc-cancel').onclick=doCancel;
      // ★기본커서 = 바코드칸(2026-08-20). DOM 부착 후에 잡아야 먹으므로 다음 프레임에 실행.
      const _f=()=>{const el=ov.querySelector('#bc-scan1');if(el){el.focus();el.select();}};
      _f(); requestAnimationFrame(_f); setTimeout(_f,60);
    };
    render(); document.body.appendChild(ov); requestAnimationFrame(()=>{
      const el=ov.querySelector('#bc-scan1');if(el){el.focus();el.select();}});
  };
  /* ★계획 기준일(마지막 업로드 일자축 첫날)만 반영하고 **조회는 하지 않는다**
       (2026-09-06 사용자 요청 "메뉴 오니 바로 조회된다").
       이 화면은 응답이 5~6초라 진입할 때마다 기다리게 된다.
       조건을 정한 뒤 [조회]를 누르면 그때 가져온다. 종전엔 .then(load) 로 자동 실행했다. */
  planBase().then(b=>{if(b&&b.iso){st.from=b.iso;
      st.to=iso(new Date(new Date(b.iso+'T00:00:00').getTime()+(st.gigan-1)*864e5));}})
    .catch(()=>{}).then(()=>{st.rows=[];st.loading=false;draw();});
};

/* ===== 생산: 가공창고 이동계획 (w_pr_input_580) — 도번×라인, 자도번LIST + 이동필요/완료 =====
   ★레거시 실측(2026-08-22, w_pr_input_586 소스 확보): "이동" = 실물재고 이동이 아니라
   세트재고 발행(PU_T_STOCK_MAINT_GAGONG_MOVE INSERT, IN_CONFIRM_FLAG='0')이 "어디까지 진행됐는지" 추적하는 상태값.
   확정('1')은 자재종류별로 트리거가 다름: 가공(P2)=바코드실적처리, 사급=자재입고확인, 직납품=출하.
   화면 셀 색상: 초록=확정완료(done), 검정=발행미확정(print), 노랑/주황=부분(part). */
SCREEN.gagongmove580=(c)=>{
  const API=API_BASE;
  const nf=n=>Number(n||0).toLocaleString('ko-KR',{maximumFractionDigits:0});
  const dcol=s=>(s&&(''+s).length===6)?`${(''+s).slice(2,4)}/${(''+s).slice(4,6)}`:s;
  // 레거시 일자헤더 = 일자+요일(예 "22토"), 토=파랑·일=빨강 (생산계획추가입력 wlab/wke와 동일)
  const wlab=y=>{if(!y||y.length<6)return dcol(y);const dt=new Date(2000+ +y.slice(0,2),+y.slice(2,4)-1,+y.slice(4,6));return `${y.slice(4,6)}${'일월화수목금토'[dt.getDay()]}`;};
  const wdow=y=>{if(!y||y.length<6)return -1;return new Date(2000+ +y.slice(0,2),+y.slice(2,4)-1,+y.slice(4,6)).getDay();};
  const wke=y=>{const d=wdow(y);return d===6?'color:#1b6ec2':(d===0?'color:#c0392b':'');};        // 토 파랑 / 일 빨강
  const wkbg=y=>{const d=wdow(y);return d===6?'background:#eef4fc':(d===0?'background:#fdeeee':'');};
  // 배경색 위 글자색 — 어두운 배경(레거시 초록 #669900 등)에서 검은 숫자가 안 보여 흰색으로 뒤집는다.
  const fgOn=bg=>{const m=/^#([0-9a-f]{6})$/i.exec(bg||'');if(!m)return 'color:#222';
    const n=parseInt(m[1],16), r=(n>>16)&255, g=(n>>8)&255, b=n&255;
    return (r*0.299+g*0.587+b*0.114)<150?'color:#fff':'color:#222';};
  const iso=x=>`${x.getFullYear()}-${String(x.getMonth()+1).padStart(2,'0')}-${String(x.getDate()).padStart(2,'0')}`;
  const T=new Date();
  // ★조회엔진 = 레거시 SP(SP_PR_가공창고_이동계획_260213) 직접호출. 기본 인자도 레거시와 동일(P2/IS0001/%).
  // puPart(레거시 as_pu_part_code) = 입고 자재창고. 항상 IS0001 이라 조건칸에서 뺐다(2026-08-23) — SP 인자로만 사용.
  // ★2026-08-24 기간 드롭다운 1~14일 선택 가능. 기본 2일(기준일 포함) → to = from + 1일.
  // ★소스 = 신규DB(웹계획) **고정**(2026-09-08 사용자 확정, 드롭다운 제거).
  //   종전 '우리(nx)' 옵션은 이름과 달리 레거시 dbo SP 직접호출이라 컷오버에 죽는 경로였다.
  // ★기준일 = 마지막 계획업로드의 일자축 첫날(planBaseIso, 2026-08-28 사용자 확정)
  const _mb0=planBaseIso(), _mbT=new Date(_mb0+'T00:00:00');
  const st={from:_mb0,to:iso(new Date(_mbT.getTime()+1*864e5)),wc:'P2',dest:'',puPart:'IS0001',item:'',part:'',mv:'이동필요',gigan:2,src:'new',
            gubun:'이동계획',confirm:'전체',   // gubun: 이동계획(매트릭스) / 이동전표(발행목록)
            dates:[],rows:[],cnt:0,plan_sum:0,need_sum:0,moved_sum:0,note:'',loading:false,loaded:false,msg:'',exp:new Set(),
            sel:new Set(),itemSel:null,optDests:[],sheetRows:[],sheetAll:[],sheetCnt:0,
            all:[],allDates:[]};   // all = 서버에서 받은 원본(필터 전). sel = 선택한 셀 키("행i:날짜")
  // ★서버조회는 기간/가공창고가 바뀔 때만. 납품처·도번·자도번·이동필요는 받아둔 데이터로 즉시 필터
  //   (레거시도 조회 1회 후 필터는 즉답 — 2026-08-22 사용자요청).
  const applyFilter=()=>{
    const it=st.item.trim().toUpperCase(), pt=st.part.trim().toUpperCase();
    let rows=st.all;
    if(it) rows=rows.filter(r=>(r.assy||'').toUpperCase().includes(it));
    if(pt) rows=rows.filter(r=>(r.jado||'').toUpperCase().includes(pt));
    // ★납품처(생산라인+사급업체 통합)도 클라이언트 필터 — SP가 해당 인자를 무시하므로 결과에서 거른다.
    if(st.dest) rows=rows.filter(r=>r.dest_key===st.dest);
    if(st.mv==='이동필요') rows=rows.filter(r=>r.need>0);
    else if(st.mv==='이동완료') rows=rows.filter(r=>r.need<=0);
    st.rows=rows; st.cnt=rows.length;
    st.need_sum=rows.reduce((s,r)=>s+(+r.need||0),0);
    st.moved_sum=rows.reduce((s,r)=>s+(+r.moved||0),0);
    st.dates=st.allDates;   // 일자컬럼은 SP 기준(from~to 고정) — 행 필터로 줄이지 않는다
    st.exp.clear(); st.sel.clear(); st.itemSel=null;   // 행 순서가 바뀌므로 선택상태 초기화
  };
  const load=async()=>{
    if(st.gubun==='이동전표')return loadSheets();
    st.loading=true;draw();
    // mv(이동필요)는 서버에 안 넘긴다 — 클라이언트 필터로 즉시 전환하기 위해 항상 '전체'로 받아둔다.
    // 납품처·이동필요는 넘기지 않는다(클라이언트 즉시필터). 서버는 기간/가공창고/자재파트만.
    // ★src(2026-08-26): nx=레거시 SP / new=복제 SP(계획만 웹편성)
    const qs=new URLSearchParams({from_ymd:st.from,to_ymd:st.to,wc:st.wc,pr_part:'%',pu_part:st.puPart,sagub:'',mv:'전체',src:(st.src||'nx'),limit:2500});
    try{const r=await fetch(`${API}/api/gagong/move580?${qs}`);const d=await r.json();
      st.all=d.rows||[];st.allDates=d.dates||[];st.optDests=d.dests||[];st.plan_sum=d.plan_sum||0;st.note=d.note||'';st.msg='';st.loaded=true;
      if(st.dest&&!st.optDests.some(o=>o.key===st.dest))st.dest='';   // 새 조회에 없는 납품처면 해제
      applyFilter();}
    catch(e){st.msg='백엔드 연결 실패';st.all=[];st.allDates=[];st.dates=[];st.rows=[];st.cnt=0;}
    st.loading=false;draw();};
  const applySheetFilter=()=>{
    const it=st.item.trim().toUpperCase(), pt=st.part.trim().toUpperCase();
    let rows=st.sheetAll;
    if(it) rows=rows.filter(r=>(r.assy||'').toUpperCase().includes(it));
    if(pt) rows=rows.filter(r=>(r.mat||'').toUpperCase().includes(pt));
    if(st.confirm==='미확정') rows=rows.filter(r=>!r.confirmed);
    else if(st.confirm==='확정') rows=rows.filter(r=>r.confirmed);
    st.sheetRows=rows; st.sheetCnt=rows.length;
  };
  const loadSheets=async()=>{st.loading=true;draw();
    const qs=new URLSearchParams({from_ymd:st.from,to_ymd:st.to,confirm:'전체',limit:2500});
    try{const r=await fetch(`${API}/api/gagong/move580/sheets?${qs}`);const d=await r.json();
      st.sheetAll=d.rows||[];st.msg='';applySheetFilter();}
    catch(e){st.msg='백엔드 연결 실패';st.sheetAll=[];st.sheetRows=[];st.sheetCnt=0;}
    st.loading=false;draw();};
  const CLR={done:'#66bb6a',print:'#333',part:'#ffd54f'};   // 초록/검정/노랑
  /* ★엑셀 다운로드 — **레거시 엑셀과 동일**하게 (2026-08-31 사용자 확정: "똑같이 나오게").
       레거시 실물(가공창고이동계획_260831142118.xls) 대조로 맞춘 것:
         ① 헤더 1행부터 시작(제목·부제 없음) · 헤더는 흰 배경 + 굵게 + 가운데
         ② 컬럼명 = SEQ·최종납품처·도번·자도번LIST·PART일자·PART INPUT·Line No·
                    이동전표발·이동필요수·출하·ASSY재고·당일이전·(일자들)
            → 화면에만 있는 자재재고·생산재고·도번고정은 레거시에 없다(제외).
         ③ PART일자 = **260821 6자리 원본**(화면의 '08월 21일' 변환 아님)
         ④ 빈 셀은 완전 공백(화면의 '·' 아님) · 합계행 없음
         ⑤ 주말 헤더는 주황(#fac090) — 레거시 05토/06일이 그 색
         ⑥ 셀 배경 = SP 색상 그대로(#ffff00 노랑·#669900 초록·#fac090 주황)
       ★'10/10' 이 날짜로 바뀌던 문제는 downloadXLS 의 x:str 로 차단(core.js). */
  const _hex=s=>{const m=/background:(#[0-9a-f]{6})/i.exec(s||'');return m?m[1]:'';};
  // ★글자색 판정은 화면 fgOn(767행)과 **같은 임계값 150** 을 쓴다 — 다르면 엑셀 색이 화면과 어긋난다.
  const _fg=bg=>{const m=/^#([0-9a-f]{6})$/i.exec(bg||'');if(!m)return '';
    const n=parseInt(m[1],16), L=(((n>>16)&255)*0.299+((n>>8)&255)*0.587+(n&255)*0.114);
    return L<150?'#ffffff':'#222222';};
  const exportXls=()=>{
    if(!st.rows.length)return alert('조회 결과가 없습니다.');
    const dates=st.dates;
    const HB='#ffffff';                                  // 레거시 헤더 = 흰 배경
    const cols=[{h:'SEQ',w:40,bg:HB},{h:'최종납품처',w:110,bg:HB},{h:'도번',w:120,bg:HB},
      {h:'자도번LIST',w:230,bg:HB},{h:'PART일자',w:60,bg:HB},{h:'PART INPUT',w:70,bg:HB},
      {h:'Line No',w:52,bg:HB},{h:'이동전표발',w:66,bg:HB},{h:'이동필요수',w:66,bg:HB},
      {h:'출하',w:52,bg:HB},{h:'ASSY재고',w:64,bg:HB},{h:'당일이전',w:64,bg:HB}]
      // 주말 헤더는 레거시처럼 주황 계열, 평일은 흰색
      .concat(dates.map(d=>({h:wlab(d),w:56,bg:(wdow(d)===0||wdow(d)===6)?'#fac090':HB})));
    const n0=v=>(+v||0)?(+v):'';                         // ★레거시는 빈칸(화면의 '·' 아님)
    const rows=st.rows.map((r,i)=>{
      const base=[{v:i+1,al:'center'},{v:r.dest,al:'center'},{v:r.item||r.assy,al:'center'},
        {v:r.jado,al:'left'},
        {v:String(r.part_ymd||''),al:'center'},          // ★260821 원본 6자리
        {v:String(r.hm||''),al:'center'},{v:r.line,al:'center'},
        {v:n0(r.jp_print),al:'center'},{v:n0(r.need),al:'center'},
        {v:n0(r.sale),al:'center'},{v:n0(r.assy_stock),al:'center'}];
      // 당일이전 — '완료/계획' + 충당색(레거시 L열과 동일)
      const pb=r.prior?(r.prior_color||''):'';
      base.push(r.prior?{v:`${+r.prior_done||0}/${+r.prior}`,al:'center',bg:pb,fg:_fg(pb)}
                       :{v:'',al:'center'});
      dates.forEach(d=>{
        const plan=(r.days&&r.days[d])||0, done=(r.doneday&&r.doneday[d])||0;
        if(!plan){ base.push({v:'',al:'center'}); return; }   // 계획 없는 날 = 완전 공백
        const bg=(r.colorday&&r.colorday[d])||'';
        base.push({v:`${done}/${plan}`,al:'center',bg,fg:_fg(bg)});
      });
      return base;
    });
    const wcnm=(st.wc||'전체');
    // 파일명도 레거시 형식(가공창고이동계획_YYMMDDHHMMSS)
    const T2=new Date(), p2=n=>String(n).padStart(2,'0');
    const stamp=`${String(T2.getFullYear()).slice(2)}${p2(T2.getMonth()+1)}${p2(T2.getDate())}`
      +`${p2(T2.getHours())}${p2(T2.getMinutes())}${p2(T2.getSeconds())}`;
    // ★파일은 진짜 xlsx 로 나간다(확장자는 downloadXLS 가 .xlsx 로 붙인다).
    //   HTML→.xls 방식은 엑셀이 "형식·확장명 불일치" 경고를 띄우고 **서식(색)을 버려서** 폐기.
    downloadXLS(`가공창고이동계획_${stamp}`, cols, rows, {sheet:`가공창고이동계획_${wcnm}`});
  };
  /* ★컬럼 정의 — 항목보기(숨김·순서)를 쓰려면 <th>·<td> 를 하드코딩하지 않고
       정의에서 만들어야 한다(2026-09-06, 420 과 같은 구조).
       앞그룹(head) 11 · 일자칸 · 뒷그룹(tail) 5. */
  const rowsel=(i,extra)=>`class="center mv-rowsel" data-i="${i}" style="cursor:pointer${extra||''}"`;
  const dim=v=>v?'':';color:#dfe6ef';
  const MHDEF={
    seq:{t:'SEQ',      h:(r,i)=>`<td ${rowsel(i)}>${i+1}</td>`},
    dest:{t:'최종납품처', h:(r,i)=>`<td ${rowsel(i)}>${esc(r.dest)}</td>`},
    assy:{t:'ASSY도번', h:(r,i)=>`<td ${rowsel(i)} title="${esc(r.assy)}">${esc(r.assy)}</td>`},
    item:{t:'도번',     h:(r,i)=>{const on=st.itemSel===i;
      const sty=on?'background:#dbeafe;color:#123a6b;font-weight:700;outline:2px solid #4a86e8;outline-offset:-2px':'';
      const dno=r.item||r.assy;
      return `<td class="center mv-item" data-i="${i}" style="cursor:pointer;${sty}" title="${esc(dno)}&#10;ASSY: ${esc(r.assy)}&#10;클릭=이 도번 선택/해제 · Ctrl+클릭=여러 행 추가선택"><b>${esc(dno)}</b></td>`;}},
    jado:{t:'자도번LIST', h:(r,i)=>{const js=(r.jado||'').length>40?(r.jado.slice(0,40)+'…'):(r.jado||'');
      return `<td class="center jado-cell" data-i="${i}" title="${esc(r.jado)}&#10;더블클릭=자도번 펼치기" style="max-width:220px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;cursor:pointer;color:#1c66c9">${esc(js)} <span style="color:#8aa">(${r.matcnt})</span></td>`;}},
    part_ymd:{t:'PART일자', h:(r,i)=>`<td ${rowsel(i)}>${dcol(r.part_ymd)}</td>`},
    hm:{t:'INPUT',    h:(r,i)=>`<td ${rowsel(i)}>${esc(r.hm)}</td>`},
    line:{t:'Line',    h:(r,i)=>`<td ${rowsel(i)}>${esc(r.line)}</td>`},
    jp_print:{t:'이동전표발행', h:(r,i)=>`<td ${rowsel(i,dim(r.jp_print))}>${r.jp_print?nf(r.jp_print):'·'}</td>`},
    need:{t:'이동필요', h:(r,i)=>`<td ${rowsel(i,r.need>0?';color:#c0392b;font-weight:600':';color:#dfe6ef')}>${r.need>0?nf(r.need):'·'}</td>`},
    prior:{t:'당일이전', h:(r,i)=>{const on=st.sel.has(`${i}:P`);
      if(!r.prior)return `<td class="center" style="color:#dfe6ef">·</td>`;
      const bg=r.prior_color||'';
      return `<td class="center mv-cell" data-i="${i}" data-d="P" data-key="${i}:P" style="cursor:pointer;background:${bg};${fgOn(bg)};font-weight:700${on?';outline:2px solid #4a86e8;outline-offset:-2px;background-image:linear-gradient(rgba(219,234,254,.72),rgba(219,234,254,.72))':''}">${nf(r.prior_done||0)}/${nf(r.prior)}</td>`;}},
  };
  const MTDEF={
    sale:{t:'출하',        h:(r,i)=>`<td ${rowsel(i,dim(r.sale))}>${r.sale?nf(r.sale):'·'}</td>`},
    assy_stock:{t:'ASSY재고', h:(r,i)=>`<td ${rowsel(i,dim(r.assy_stock))}>${r.assy_stock?nf(r.assy_stock):'·'}</td>`},
    stock:{t:'자재재고',    h:(r,i)=>`<td ${rowsel(i,dim(r.stock))}>${r.stock?nf(r.stock):'·'}</td>`},
    pr_stock:{t:'생산재고',  h:(r,i)=>`<td ${rowsel(i,dim(r.pr_stock))}>${r.pr_stock?nf(r.pr_stock):'·'}</td>`},
    fix_stock:{t:'도번고정', h:(r,i)=>`<td ${rowsel(i,dim(r.fix_stock))}>${r.fix_stock?nf(r.fix_stock):'·'}</td>`},
  };
  const MH_DEF=['seq','dest','assy','item','jado','part_ymd','hm','line','jp_print','need','prior'];
  const MT_DEF=['sale','assy_stock','stock','pr_stock','fix_stock'];
  const MH_LS='mv580_headorder', MT_LS='mv580_tailorder', MV_HIDE='mv580_hidecols';
  /* ★MVALL = 앞·뒤 정의를 합친 것(420·410 과 동일 처방, 2026-09-09).
       항목보기가 그룹 경계를 넘는 이동을 허용하므로 저장순서에 반대 그룹 키가 섞인다.
       그룹별 정의로 거르면 그 키가 탈락 → 기본목록 보충 때 **맨 뒤**로 되살아난다
       ("앞으로 옮겼는데 저장하면 맨 뒤로 간다"). */
  const MVALL=Object.assign({},MHDEF,MTDEF);
  const mvOrd=(key,def,defs)=>{try{const s=JSON.parse(localStorage.getItem(key)||'null');
    if(Array.isArray(s)&&s.length){const v=s.filter(k=>defs[k]);def.forEach(k=>{if(!v.includes(k))v.push(k);});return v;}
    }catch(e){} return def.slice();};
  /* ★hOrd/tOrd 처럼 **가변 배열**로 둔다 — 항목보기 적용 시 제자리에서 고쳐야
       화면 재렌더가 새 순서를 바로 본다(다시 진입하지 않아도 된다). */
  const MH_ORD=mvOrd(MH_LS,MH_DEF,MVALL), MT_ORD=mvOrd(MT_LS,MT_DEF,MVALL);
  /* head 가 이미 가진 키는 tail 에서 뺀다(양쪽 등재 = 표에 두 번 나옴). ★in-place — 배열 참조가 유지돼야 한다. */
  for(let _i=MT_ORD.length-1;_i>=0;_i--) if(MH_ORD.includes(MT_ORD[_i])) MT_ORD.splice(_i,1);
  const mvLoadHide=()=>{try{const s=JSON.parse(localStorage.getItem(MV_HIDE)||'[]');
    return new Set(Array.isArray(s)?s:[]);}catch(_){return new Set();}};
  let mvHid=mvLoadHide();
  const mvVis=ks=>ks.filter(k=>!mvHid.has(k));
  /* ★defs 는 항상 MVALL 로 찾는다 — 그룹을 넘어온 키는 그 그룹 정의에 없다(undefined → 렌더 사망). */
  const mvTh=(ks,defs,grp)=>mvVis(ks).map(k=>{const d=MVALL[k]; if(!d)return '';
    return `<th data-tk="${k}" data-grp="${grp}" title="우클릭 = 항목보기(순서·숨김)">${d.t}</th>`;}).join('');
  const mvTd=(ks,defs,r,i)=>mvVis(ks).map(k=>{const d=MVALL[k]; return d?d.h(r,i):'';}).join('');

  /* == 항목보기 (2026-09-06 — 420·410 과 같은 방식) ========================
       체크 해제 = 그 컬럼 숨김 · 행을 끌거나 ▲▼ 로 순서 변경.
       앞(head)/뒤(tail) 그룹은 일자칸을 사이에 두고 나뉜다 — 놓은 자리의 그룹을 물려받는다. */
  const openColPick=()=>{
    const old=document.getElementById('mv-colpick'); if(old)old.remove();
    const hid=mvLoadHide();
    const ov=document.createElement('div');
    ov.id='mv-colpick';
    ov.style.cssText='position:fixed;inset:0;z-index:1300;background:rgba(20,32,54,.34);'
                    +'display:flex;align-items:center;justify-content:center';
    const item=(k,defs,grp)=>`<div class="mvcp-r" data-k="${k}" data-grp="${grp}"
         style="display:flex;align-items:center;gap:7px;padding:4px 8px;border-bottom:1px solid #eef1f6;
                cursor:grab;user-select:none;-webkit-user-select:none">
        <span style="color:#b6c2d4;font-size:11px" title="끌어서 순서 변경">⠿</span>
        <input type="checkbox" ${hid.has(k)?'':'checked'} data-ck="${k}">
        <span style="flex:1;font-size:12.5px">${defs[k].t}</span>
        <button class="btn ghost mvcp-up" data-k="${k}" style="padding:0 6px;font-size:11px">▲</button>
        <button class="btn ghost mvcp-dn" data-k="${k}" style="padding:0 6px;font-size:11px">▼</button>
      </div>`;
    ov.innerHTML=`<div style="background:#fff;border-radius:10px;width:420px;max-height:78vh;
           display:flex;flex-direction:column;box-shadow:0 8px 30px rgba(20,40,80,.28)">
        <div style="padding:10px 12px;border-bottom:1px solid #e3e9f2;font-weight:700;color:#16305c">
          항목보기 <span style="font-weight:400;font-size:11px;color:#7b8aa0">체크 해제 = 숨김 · 행을 끌거나 ▲▼ 로 순서 변경</span></div>
        <div style="flex:1;overflow:auto;padding:4px 0">
          <div style="padding:4px 10px;font-size:11px;color:#7b8aa0;font-weight:700">앞쪽 컬럼</div>
          <div id="mvcp-h">${MH_ORD.map(k=>item(k,MVALL,'head')).join('')}</div>
          <div style="padding:6px 10px 4px;font-size:11px;color:#7b8aa0;font-weight:700">일자칸 뒤 컬럼</div>
          <div id="mvcp-t">${MT_ORD.map(k=>item(k,MVALL,'tail')).join('')}</div>
        </div>
        <div style="padding:9px 12px;border-top:1px solid #e3e9f2;display:flex;gap:6px;justify-content:flex-end">
          <button class="btn ghost" id="mvcp-reset">초기화</button>
          <div style="flex:1"></div>
          <button class="btn ghost" id="mvcp-x">닫기</button>
          <button class="btn" id="mvcp-ok" style="background:#1c47a0;color:#fff">적용</button>
        </div></div>`;
    document.body.appendChild(ov);
    const q=sel=>ov.querySelector(sel);
    /* ★모달 mousedown 은 **버블 단계에서만** 막는다(캡처 아님).
         캡처로 stopPropagation 하면 아래 행 드래그 핸들러까지 못 받는다(420 실측). */
    ov.addEventListener('mousedown',e=>e.stopPropagation());
    ov.onclick=e=>{if(e.target===ov)ov.remove();};
    q('#mvcp-x').onclick=()=>ov.remove();
    /* ★▲▼ 도 그룹 경계를 넘는다(2026-09-07 교정 — 420 항목보기와 동일 버그·동일 처방). */
    const move=(k,dir)=>{const row=ov.querySelector(`.mvcp-r[data-k="${k}"]`); if(!row)return;
      const box=row.parentElement;
      const sib=dir<0?row.previousElementSibling:row.nextElementSibling;
      if(sib){
        if(dir<0)box.insertBefore(row,sib); else box.insertBefore(sib,row);
        return;
      }
      const other=(box.id==='mvcp-h')?ov.querySelector('#mvcp-t'):ov.querySelector('#mvcp-h');
      if(!other)return;
      if(dir<0)other.appendChild(row);
      else     other.insertBefore(row,other.firstElementChild);
      row.dataset.grp=(other.id==='mvcp-h')?'head':'tail';};
    ov.querySelectorAll('.mvcp-up').forEach(b=>b.onclick=()=>move(b.dataset.k,-1));
    ov.querySelectorAll('.mvcp-dn').forEach(b=>b.onclick=()=>move(b.dataset.k, 1));
    /* 행 끌어서 순서 변경 — ★HTML5 draggable 은 쓰지 않는다(텍스트 선택이 먼저 잡혀
         파란 블록만 생기고 드래그가 시작되지 않는다). 5px 이상 움직여야 '이동'이라
         같은 행에서 "클릭=체크토글 / 끌면=이동"이 공존한다. */
    let dK=null,dY=0,dMoved=false;
    const rowsOf=()=>[...ov.querySelectorAll('.mvcp-r')];
    const rowAtY=y=>{const rs=rowsOf(); if(!rs.length)return null;
      let best=rs[0],bd=1e9;
      for(const r of rs){const b=r.getBoundingClientRect();
        const d=(y<b.top)?(b.top-y):((y>b.bottom)?(y-b.bottom):0);
        if(d<bd){bd=d;best=r;}}
      return best;};
    ov.addEventListener('mousedown',e=>{
      const row=e.target.closest&&e.target.closest('.mvcp-r'); if(!row)return;
      if(e.target.tagName==='INPUT')return;                // 체크박스는 브라우저가 처리
      if(e.target.closest('.mvcp-up,.mvcp-dn'))return;     // ▲▼ 는 클릭으로
      e.preventDefault();                                   // 텍스트 선택 차단
      dK=row.dataset.k; dY=e.clientY; dMoved=false;
      row.style.opacity='.55';
    });
    const onMove=e=>{
      if(!dK)return;
      if(!ov.isConnected){dK=null;document.removeEventListener('mousemove',onMove);return;}
      if(!dMoved&&Math.abs(e.clientY-dY)<5)return;
      dMoved=true;
      const over=rowAtY(e.clientY);
      rowsOf().forEach(x=>{if(x!==over)x.style.borderTop='';});
      if(over&&over.dataset.k!==dK)over.style.borderTop='2px solid #2563eb';
    };
    const onUp=e=>{
      if(!dK)return;
      if(!ov.isConnected){dK=null;document.removeEventListener('mouseup',onUp);return;}
      const k=dK; dK=null;
      rowsOf().forEach(x=>{x.style.opacity='';x.style.borderTop='';});
      if(!dMoved)return;                                    // 안 움직였으면 클릭 = 체크 토글
      const over=rowAtY(e.clientY);
      if(!over||over.dataset.k===k)return;
      const src=rowsOf().find(r=>r.dataset.k===k); if(!src)return;
      const box=over.parentElement;                         // 놓은 자리의 그룹을 물려받는다
      const sb=over.getBoundingClientRect();
      if(e.clientY < sb.top+sb.height/2) box.insertBefore(src,over);
      else box.insertBefore(src,over.nextSibling);
      src.dataset.grp = box.id==='mvcp-h' ? 'head' : 'tail';
    };
    document.addEventListener('mousemove',onMove);
    document.addEventListener('mouseup',onUp);
    q('#mvcp-reset').onclick=()=>{
      try{localStorage.removeItem(MH_LS);localStorage.removeItem(MT_LS);
          localStorage.removeItem(MV_HIDE);}catch(_){}
      MH_ORD.length=0; MH_DEF.forEach(k=>MH_ORD.push(k));
      MT_ORD.length=0; MT_DEF.forEach(k=>MT_ORD.push(k));
      mvHid=new Set();
      ov.remove(); draw();};
    q('#mvcp-ok').onclick=()=>{
      const ord=sel=>[...ov.querySelectorAll(sel+' .mvcp-r')].map(r=>r.dataset.k);
      const nh=ord('#mvcp-h'), nt=ord('#mvcp-t');
      const nhid=[...ov.querySelectorAll('input[data-ck]')]
        .filter(x=>!x.checked).map(x=>x.dataset.ck);
      try{localStorage.setItem(MH_LS,JSON.stringify(nh));
          localStorage.setItem(MT_LS,JSON.stringify(nt));
          localStorage.setItem(MV_HIDE,JSON.stringify(nhid));}catch(_){}
      MH_ORD.length=0; nh.forEach(k=>MH_ORD.push(k));
      MT_ORD.length=0; nt.forEach(k=>MT_ORD.push(k));
      mvHid=new Set(nhid);
      ov.remove(); draw();
    };
  };
  const planGridHtml=()=>{
    const dates=st.dates;
    let tNeed=0,tMoved=0,tSale=0,tAssy=0,tPrint=0,tPrior=0;const dSum={};dates.forEach(d=>dSum[d]=0);
    st.rows.forEach(r=>{tNeed+=+r.need||0;tMoved+=+r.moved||0;tSale+=+r.sale||0;tAssy+=+r.assy_stock||0;tPrint+=+r.jp_print||0;tPrior+=+r.prior||0;
      dates.forEach(d=>{dSum[d]+=(r.days&&r.days[d])||0;});});
    // 고정컬럼수 = 앞 8(SEQ·최종납품처·ASSY도번·도번·자도번LIST·PART일자·INPUT·Line)
    //            + 3(이동전표발행·이동필요·당일이전) + 뒤 5(출하·ASSY재고·자재재고·생산재고·도번고정)
    // ★colspan 은 실제 보이는 컬럼 수로 — 고정값(16)을 쓰면 항목 숨김 시 어긋난다(420 과 동일).
    const NC=mvVis(MH_ORD).length+mvVis(MT_ORD).length;
    return `<div class="grid-wrap" style="max-height:calc(100vh - 340px);overflow:auto;background:#fff;border:1px solid var(--line-2,#c9d3e0);border-radius:8px">
      <table class="tbl fit mv-tbl" style="font-size:11px;user-select:none;text-align:center"><thead><tr>
       <!-- ★ASSY도번 추가(2026-09-01 요청) — 레거시 580 에 있는 컬럼.
            '도번'은 가공품번(예 AJR74942626-고압)이라 ASSY 원본과 다르다. 둘 다 보여야 추적된다. -->
       ${mvTh(MH_ORD,MHDEF,'head')}
       ${dates.map(d=>`<th style="${wke(d)};${wkbg(d)}">${wlab(d)}</th>`).join('')}
       <!-- ★재고류 5종을 일자 뒤로(2026-09-01 요청) — 계획·일자를 먼저 보고 재고는 참고로 -->
       ${mvTh(MT_ORD,MTDEF,'tail')}</tr></thead>
      <tbody>${st.loading?spinRow(NC+dates.length):(st.rows.length?st.rows.map((r,i)=>{
        const jshort=(r.jado||'').length>40?(r.jado.slice(0,40)+'…'):(r.jado||'');const ex=st.exp.has(i);
        return `<tr>
        ${mvTd(MH_ORD,MHDEF,r,i)}
        ${dates.map(d=>{const plan=(r.days&&r.days[d])||0,done=(r.doneday&&r.doneday[d])||0,bg=(r.colorday&&r.colorday[d])||'';
          if(!plan)return `<td class="center mv-cell" data-i="${i}" data-d="${d}" style="color:#dfe6ef;${wkbg(d)}">·</td>`;
          const key=`${i}:${d}`, on=st.sel.has(key);
          return `<td class="center mv-cell" data-i="${i}" data-d="${d}" data-key="${key}" style="cursor:pointer;${bg?`background:${bg};${fgOn(bg)}`:wkbg(d)};font-weight:700${on?';outline:2px solid #4a86e8;outline-offset:-2px;background-image:linear-gradient(rgba(219,234,254,.72),rgba(219,234,254,.72))':''}">${nf(done)}/${nf(plan)}</td>`;}).join('')}
        <!-- ★재고류 5종 — 일자 뒤(2026-09-01 요청) -->
        ${mvTd(MT_ORD,MTDEF,r,i)}</tr>
        ${ex?`<tr class="jado-exp"><td></td><td colspan="${NC-1+dates.length}" style="background:#f2f7ff;white-space:normal;padding:4px 8px;font-size:11px;color:#334;text-align:left">📦 자도번 ${r.matcnt}종: ${esc(r.jado).replace(/,/g,'&nbsp;· ')}</td></tr>`:''}`;
      }).join(''):`<tr><td colspan="${NC+dates.length}" class="empty">${st.loaded?'조회 결과 없음':'조건을 지정한 뒤 <b>🔍 조회</b> 버튼을 누르세요.'}</td></tr>`)}</tbody>
      ${(()=>{if(!st.rows.length)return '';
        // ★재고류를 일자 뒤로 옮겼으므로 합계행도 같은 순서로(2026-09-01).
        let tStock=0,tPr=0,tFix=0;
        st.rows.forEach(r=>{tStock+=+r.stock||0;tPr+=+r.pr_stock||0;tFix+=+r.fix_stock||0;});
        // ★합계행도 정의 기반으로 — 컬럼을 숨기거나 순서를 바꿔도 값이 제 칸에 붙는다.
        const TOT={jp_print:tPrint, need:`<span style="color:#c0392b">${nf(tNeed)}</span>`, prior:nf(tPrior),
                   sale:tSale, assy_stock:tAssy, stock:tStock, pr_stock:tPr, fix_stock:tFix};
        const tcell=k=>{const v=TOT[k];
          return `<td class="center">${v===undefined?'':(typeof v==='number'?nf(v):v)}</td>`;};
        const hv=mvVis(MH_ORD);
        let lead=0; while(lead<hv.length && TOT[hv[lead]]===undefined) lead++;   // 합계 라벨이 먹을 앞칸 수
        return `<tfoot><tr class="grandtot">${lead?`<td colspan="${lead}">합계 (${nf(st.cnt)}행)</td>`:''}
        ${hv.slice(lead).map(tcell).join('')}
        ${dates.map(d=>`<td class="center">${nf(dSum[d])}</td>`).join('')}
        ${mvVis(MT_ORD).map(tcell).join('')}</tr></tfoot>`;})()}
      </table></div>`;
  };
  // ★"이동전표" 모드 — MAINT_GROUP_SEQ(전표) 단위 발행목록. 확정여부(입고확인)와 각 전표 재출력 버튼.
  const sheetGridHtml=()=>{
    const rows=st.sheetRows;
    return `<div class="grid-wrap" style="max-height:calc(100vh - 300px);overflow:auto;background:#fff;border:1px solid var(--line-2,#c9d3e0);border-radius:8px">
      <table class="tbl fit mvs-tbl" style="font-size:11px;text-align:center"><thead><tr>
       <th style="width:34px"><input type="checkbox" id="mvs-all" title="전체선택"></th>
       <th>이동일자</th><th>이동전표번호</th><th>CHECK-LIST SEQ</th><th>출고처</th><th>ASSY품번</th><th>품번</th><th>품명</th><th>보관장소</th>
       <th>입고수량</th><th>입고확인</th><th>확인일시</th><th>작업자</th><th>인쇄</th>
       <!-- ★2026-08-24 체크=전표 전체 품번 출력 / 미체크=이 행 품번만 출력 -->
       <th style="width:60px" title="체크: 그 전표의 전 품번 출력 / 해제: 이 행 품번만 출력">출력범위</th></tr></thead>
      <tbody>${st.loading?spinRow(15):(rows.length?rows.map(r=>`<tr>
        <td class="center">${r.confirmed?'<span title="입고확인된 전표는 삭제할 수 없습니다" style="color:#c9d3e0">🔒</span>'
          :`<input type="checkbox" class="mvs-chk" data-ymd="${esc(r.ymd)}" data-seq="${r.seq}">`}</td>
        <td class="center">${dcol(r.ymd)}</td><td class="center"><b>${nf(r.group_seq)}</b></td><td class="center">${nf(r.check_seq)}</td>
        <td class="center">${esc(r.dest)}</td><td class="center"><b>${esc(r.assy)}</b></td><td class="center">${esc(r.mat)}</td><td class="center">${esc(r.nm)}</td><td class="center">${esc(r.rack)}</td>
        <td class="center">${nf(r.qty)}</td>
        <td class="center">${r.confirmed?'<span style="color:#1c7c3a">✔입고확인</span>':'<span style="color:#c0392b">미확정</span>'}</td>
        <td class="center">${r.confirmed?esc((r.confirm_dt||'').slice(0,16)):'·'}</td><td class="center">${esc(r.confirm_user)||'·'}</td>
        <td class="center" style="white-space:nowrap">
          <button class="btn sm sheet-print" data-g="${r.group_seq}" data-k="card" data-mat="${esc(r.mat||'')}" title="부품납품표(개별카드)" style="padding:2px 6px;font-size:11px">🖨납품표</button>
          <button class="btn sm sheet-print" data-g="${r.group_seq}" data-k="list" data-mat="${esc(r.mat||'')}" title="부품확인/납품표(묶음)" style="padding:2px 6px;font-size:11px">🖨확인표</button></td>
        <td class="center"><input type="checkbox" class="mvs-allmat" data-g="${r.group_seq}" title="체크: 이 전표의 전 품번 출력 / 해제: 이 행 품번만"></td></tr>`).join('')
        :`<tr><td colspan="15" class="empty">${st.loaded?'조회 결과 없음':'조건을 지정한 뒤 <b>🔍 조회</b> 버튼을 누르세요.'}</td></tr>`)}</tbody></table></div>`;
  };
  const draw=()=>{
    const dates=st.dates;
    const itS=new Map(),ptS=new Set();
    (st.gubun==='이동전표'?st.sheetRows:st.rows).forEach(r=>{if(r.assy&&!itS.has(r.assy))itS.set(r.assy,'');
      (r.jado||'').split(',').forEach(x=>{const m=x.split('{')[0];if(m)ptS.add(m);});});
    const itOpts=[...itS].map(([v])=>`<option value="${esc(v)}"></option>`).join('');
    const ptOpts=[...ptS].sort().slice(0,400).map(v=>`<option value="${esc(v)}"></option>`).join('');
    const isSheet=st.gubun==='이동전표';
    c.innerHTML=`
     <style>
       /* ★.tbl th 가 전역 text-align:left 라 헤더가 좌측정렬됨 → 이 화면 표는 전부 가운데 */
       .mv-tbl th,.mv-tbl td,.mvs-tbl th,.mvs-tbl td{text-align:center!important}
       .mv-tbl tr.jado-exp td{text-align:left!important}
       /* ★복사 전용 선택(2026-09-06) — 이동처리 선택(파랑)과 **다른 색**이어야
            무엇이 이동 대상이고 무엇이 복사 대상인지 구분된다.
          ★셀에 인라인 background 가 걸려 있어(SP 색상) outline 으로 표시한다 —
            background-image 는 인라인 background 에 덮인다. */
       .mv-tbl td.mvcp{outline:2px solid #e0a800;outline-offset:-2px;
                       box-shadow:inset 0 0 0 999px rgba(255,236,179,.38)}
     </style>
     <div class="page-title">🚚 가공창고 이동계획 <span style="font-size:12px;color:var(--muted);font-weight:400">가공창고→자재창고 이동필요 · 자도번LIST 묶음</span></div>
     <div class="page-sub">조회엔진 = <b>복제 SP</b> <code>SP_PR_가공창고_이동계획_WEBPLAN</code> — <b>계획원천만 웹편성</b>(<code>nx.plan_part_dtl</code>)으로 치환, 색상·자도번LIST·재고충당 로직은 레거시 그대로. 셀 <b>드래그 선택</b>(<b>Ctrl+클릭/드래그</b>=여러 곳 추가선택 · 도번칸 클릭=그 행 전체) 후 "가공자재 이동처리"로 이동전표 발행. 선택하면 <b>계획·미이동 수량</b>이 우측에 합산됩니다. 재고(ASSY·자재·생산)는 실시간 잔액. 발행은 nx</div>
     <div class="toolbar" style="flex-wrap:wrap;gap:6px;align-items:center">
       <label class="tl">기준일자</label><input class="inp" type="date" id="mv-from" value="${st.from}"> ~ <input class="inp" type="date" id="mv-to" value="${st.to}">
       <label class="tl">가공창고</label><select class="inp" id="mv-wc" style="width:100px"${isSheet?' disabled':''}><option value="">% 전체</option><option value="P1"${st.wc==='P1'?' selected':''}>P1 가공</option><option value="P2"${st.wc==='P2'?' selected':''}>P2 가공</option></select>
       <label class="tl" title="생산(라인)과 사급업체는 같은 축 — 조회결과의 실제 납품처를 중복제거해 생산 먼저, 그 뒤 업체 순으로">납품처</label><select class="inp" id="mv-dest" style="width:180px"${isSheet?' disabled':''}><option value="">% 전체</option>${st.optDests.map(o=>`<option value="${esc(o.key)}"${st.dest===o.key?' selected':''}>${o.kind==='C'?'· ':''}${esc(o.nm)}</option>`).join('')}</select>
       <div class="spacer"></div>
       ${isSheet?'<button class="btn" id="mvs-del" style="background:#c0392b;color:#fff">🗑 선택 전표삭제</button>'
                :'<button class="btn" id="mv-move" style="background:#1c47a0;color:#fff">🚚 가공자재 이동처리</button>'}
     </div>
     <div class="toolbar" style="flex-wrap:wrap;gap:6px;align-items:center;margin-top:4px">
       <label class="tl">도번</label><input class="inp" id="mv-item" list="mv-iteml" value="${esc(st.item)}" style="width:130px" placeholder="도번" autocomplete="off"><datalist id="mv-iteml">${itOpts}</datalist>
       <label class="tl">자도번</label><input class="inp" id="mv-part" list="mv-partl" value="${esc(st.part)}" style="width:130px" placeholder="자도번" autocomplete="off"><datalist id="mv-partl">${ptOpts}</datalist>
       ${isSheet?`<label class="tl">입고확인</label>
         <label class="rl"><input type="radio" name="mv-cf" value="전체"${st.confirm==='전체'?' checked':''}> 전체</label>
         <label class="rl"><input type="radio" name="mv-cf" value="미확정"${st.confirm==='미확정'?' checked':''}> 미확정</label>
         <label class="rl"><input type="radio" name="mv-cf" value="확정"${st.confirm==='확정'?' checked':''}> 확정</label>`
        :`<label class="tl">이동필요</label>
       <label class="rl"><input type="radio" name="mv-f" value="전체"${st.mv==='전체'?' checked':''}> 전체</label>
       <label class="rl"><input type="radio" name="mv-f" value="이동필요"${st.mv==='이동필요'?' checked':''}> 이동필요</label>
       <label class="rl"><input type="radio" name="mv-f" value="이동완료"${st.mv==='이동완료'?' checked':''}> 이동완료</label>`}
       <!-- ★2026-08-24 기간 1~14일 전부 선택 가능(기본 2일) · 2026-08-31 31일까지 확장(사용자 요청) -->
       <label class="tl">기간</label><select class="inp" id="mv-gigan" style="max-width:78px">${Array.from({length:31},(_,k)=>k+1).map(d=>`<option value="${d}"${st.gigan===d?' selected':''}>${d}일</option>`).join('')}</select>
       <label class="tl">구분</label>
       <label class="rl"><input type="radio" name="mv-gubun" value="이동계획"${st.gubun==='이동계획'?' checked':''}> 이동계획</label>
       <label class="rl"><input type="radio" name="mv-gubun" value="이동전표"${st.gubun==='이동전표'?' checked':''}> 이동전표</label>
       <!-- ★소스 드롭다운 제거(2026-09-08 사용자 확정) — 신규DB(웹계획) 고정.
            웹 기준(웹편성 계획 nx.plan_part_dtl)으로 운영하므로, 대사용이던 '우리(nx)'를
            실무 화면에 노출할 필요가 없다(410 파트별계획·420 가공진척과 동일 조치).
            ※'우리(nx)' 는 이름과 달리 **레거시 dbo SP 직접호출**이라 컷오버에 죽는 경로였다.
            st.src 는 'new' 로 고정(초기값). API 는 src 를 그대로 받으므로 백엔드 변경 없음. -->
       <button class="btn" id="mv-search">🔍 조회</button>
       ${isSheet?'':'<button class="btn" id="mv-col" title="컬럼 숨김·순서 (헤더 우클릭으로도 열림)">항목보기</button>'}
       ${isSheet?'':'<button class="btn xls" id="mv-xls" title="조회 결과를 화면과 같은 색상으로 엑셀 저장">엑셀</button>'}
       <div class="spacer"></div><span class="rowcount" id="mv-cnt">${isSheet?`전표 <b>${nf(st.sheetCnt)}</b>건`:`행 <b>${nf(st.cnt)}</b> · 선택 <b id="mv-selcnt">${st.sel.size}</b>셀 <span id="mv-selqty" style="color:#1c47a0"></span> · 이동필요합 <b style="color:#c0392b">${nf(st.need_sum)}</b> · 이동완료합 <b>${nf(st.moved_sum)}</b>`}</span>
     </div>
     ${st.note?`<div class="page-sub" style="color:#c0392b">${esc(st.note)}</div>`:''}
     ${st.msg?`<div class="page-sub" style="color:#c0392b">⚠ ${esc(st.msg)}</div>`:''}
     ${isSheet?sheetGridHtml():planGridHtml()}`;
    const g=id=>c.querySelector(id);
    // 서버 재조회 = 기간·가공창고·생산파트·사급업체 변경 시에만. 그 외(도번/자도번/이동필요/입고확인)는 즉시 클라이언트 필터.
    const refilter=()=>{isSheet?applySheetFilter():applyFilter();draw();};
    g('#mv-search').onclick=()=>{st.from=g('#mv-from').value;st.to=g('#mv-to').value;
      if(!isSheet){st.wc=g('#mv-wc').value.trim();st.dest=g('#mv-dest').value.trim();}
      st.item=g('#mv-item').value.trim();st.part=g('#mv-part').value.trim();load();};
    {const xb=g('#mv-xls');if(xb)xb.onclick=exportXls;}   // ★엑셀(색상 유지)
    /* ★항목보기 버튼 — 실패를 삼키지 않는다(420 과 같은 이유:
         예외가 나면 창이 조용히 안 떠서 원인을 알 수 없다). */
    {const cb=g('#mv-col');
     if(cb)cb.onclick=e=>{e.preventDefault();e.stopPropagation();
       try{openColPick();}
       catch(err){console.error('[580 항목보기]',err);
                  alert('항목보기를 열지 못했습니다: '+(err&&err.message||err));}};}
    // ★기간 N일 = 기준일 포함 N일치 → to = from + (N-1). (기존 +N 이라 11·15일치가 나왔음)
    //   ★2026-08-25 st.to 만 고치고 조회를 누르면 #mv-search 핸들러가 첫 줄에서
    //     st.to = 입력칸값 으로 되돌려버려(입력칸은 아직 옛 날짜) 항상 2일치만 나왔다.
    //     → 종료일 입력칸도 같이 갱신한 뒤 조회한다. 기준일 변경 시에도 기간을 따라가게 함.
    const syncTo=()=>{const f=g('#mv-from');if(f)st.from=f.value;
      st.to=iso(new Date(new Date(st.from).getTime()+(st.gigan-1)*864e5));
      const t=g('#mv-to');if(t)t.value=st.to;};
    g('#mv-gigan').onchange=()=>{st.gigan=+g('#mv-gigan').value;syncTo();g('#mv-search').click();};
    { const fr=g('#mv-from'); if(fr) fr.onchange=()=>{syncTo();}; }
    c.querySelectorAll('input[name=mv-gubun]').forEach(rd=>rd.onchange=()=>{st.gubun=rd.value;draw();});   // 전환만, 조회는 버튼으로
    ['#mv-item','#mv-part'].forEach(id=>{const el=g(id);
      el.oninput=()=>{st.item=g('#mv-item').value;st.part=g('#mv-part').value;refilter();
        const f=c.querySelector(id);if(f){f.focus();try{f.setSelectionRange(f.value.length,f.value.length);}catch(e){}}};
      el.onkeyup=e=>{if(e.key==='Enter')g('#mv-search').click();};});
    if(isSheet){
      c.querySelectorAll('input[name=mv-cf]').forEach(rd=>rd.onchange=()=>{st.confirm=rd.value;refilter();});
      // ★같은 행의 '전체' 체크 여부로 범위 결정 — 체크=전표 전 품번 / 미체크=이 행 품번만
      c.querySelectorAll('.sheet-print').forEach(btn=>btn.onclick=()=>{
        const k=btn.dataset.k, g0=+btn.dataset.g;
        const tr=btn.closest('tr'), ck=tr&&tr.querySelector('.mvs-allmat');
        const all=!!(ck&&ck.checked);
        printMoveSheets(g0,g0,{card:k==='card',list:k==='list',onlyMat:all?'':(btn.dataset.mat||'')});});
      // 전체선택 체크박스
      const all=g('#mvs-all');
      if(all)all.onclick=()=>c.querySelectorAll('.mvs-chk').forEach(ch=>ch.checked=all.checked);
      // ★선택 전표삭제 — nx 에 웹이 발행한 미확정 전표만. 입고확인된 건 체크박스 자체가 없다(🔒).
      const del=g('#mvs-del');
      if(del)del.onclick=async()=>{
        const keys=[...c.querySelectorAll('.mvs-chk:checked')].map(ch=>({ymd:ch.dataset.ymd,seq:+ch.dataset.seq}));
        if(!keys.length){alert('삭제할 전표를 선택하세요(체크박스).');return;}
        if(!confirm(`선택한 이동전표 ${keys.length}건을 삭제할까요?\n\n※발행이 취소되며, 입고확인된 전표는 삭제되지 않습니다.\n※레거시(라이브)에서 발행된 전표는 웹에서 지울 수 없습니다.`))return;
        del.disabled=true;
        try{
          const res=await fetch(`${API}/api/gagong/move580/delete`,{method:'POST',headers:{'Content-Type':'application/json'},
            body:JSON.stringify({keys})});
          if(!res.ok){let t='';try{t=(await res.json()).detail||'';}catch(e){t=await res.text();}
            alert('삭제 실패: '+(t||res.status));return;}
          const d=await res.json();
          alert(d.msg||(d.ok?'삭제 완료':'삭제 실패'));
          if(d.deleted)load();
        }catch(e){alert('삭제 실패: '+(e&&e.message||e));}
        finally{const b=c.querySelector('#mvs-del');if(b)b.disabled=false;}
      };
      return;
    }
    c.querySelectorAll('input[name=mv-f]').forEach(rd=>rd.onchange=()=>{st.mv=rd.value;refilter();});
    // 가공창고·자재파트 = SP 인자라 재조회 / 생산파트·사급업체 = 결과필터라 즉시반영
    g('#mv-wc').onchange=()=>g('#mv-search').click();   // 가공창고 = SP 인자라 재조회
    g('#mv-dest').onchange=()=>{st.dest=g('#mv-dest').value.trim();refilter();};   // 납품처 = 결과필터(즉시)
    c.querySelectorAll('.jado-cell').forEach(el=>el.ondblclick=e=>{e.stopPropagation();const i=+el.dataset.i;st.exp.has(i)?st.exp.delete(i):st.exp.add(i);draw();});
    // ★셀 드래그선택 — 준비실적처리(키팅)와 동일 방식.
    //   선택표시 = 연파랑 오버레이(background-image) + 파란 테두리. 배경색(초록/노랑)은 살려둔다.
    //   재렌더(draw)하면 DOM이 새로 생겨 mouseover가 끊기므로 드래그 중엔 style만 갱신한다.
    const SELBG='linear-gradient(rgba(219,234,254,.72),rgba(219,234,254,.72))';
    let dragging=false,startCell=null;
    const paintOne=(el,on)=>{const s=el.style;
      s.outline=on?'2px solid #4a86e8':''; s.outlineOffset=on?'-2px':'';
      s.backgroundImage=on?SELBG:'';};
    // ★선택 셀의 **계획수량 합계**를 즉시 계산해 보여준다(2026-08-28 사용자요청).
    //   계획 = 그 셀의 계획수량 · 미이동 = 계획−이동완료(전표발행 시 채워질 수량).
    const selSum=()=>{let pl=0,rem=0;
      st.sel.forEach(k=>{const p=k.indexOf(':'),ri=+k.slice(0,p),ax=k.slice(p+1),r=st.rows[ri];if(!r)return;
        const q=ax==='P'?(+r.prior||0):(+((r.days||{})[ax])||0);
        const dn=ax==='P'?(+r.prior_done||0):(+((r.doneday||{})[ax])||0);
        pl+=q; rem+=Math.max(0,q-dn);});
      return {pl,rem};};
    const paint=()=>{c.querySelectorAll('.mv-cell[data-key]').forEach(el=>paintOne(el,st.sel.has(el.dataset.key)));
      const b=c.querySelector('#mv-selcnt'); if(b)b.textContent=st.sel.size;
      const q=c.querySelector('#mv-selqty');
      if(q){const s=selSum();
        q.innerHTML=st.sel.size?`(계획 <b>${nf(s.pl)}</b> · 미이동 <b>${nf(s.rem)}</b>)`:'';}};
    // 날짜축 = 당일이전('P') + 실제 일자들. 사각범위 선택에 당일이전도 포함된다.
    const AX=['P'].concat(dates);
    const cellQty=(ri,ax)=>ax==='P'?((st.rows[ri]||{}).prior||0):(((st.rows[ri]||{}).days||{})[ax]||0);
    // ★Ctrl(⌘)+드래그 = 기존 선택에 **추가**(2026-08-28 사용자요청). keep 이면 지우지 않는다.
    const applySel=(r1,r2,a1,a2,keep)=>{const i1=AX.indexOf(a1),i2=AX.indexOf(a2);
      const rlo=Math.min(r1,r2),rhi=Math.max(r1,r2),alo=Math.min(i1,i2),ahi=Math.max(i1,i2);
      if(!keep)st.sel.clear();
      for(let ri=rlo;ri<=rhi;ri++)for(let ai=alo;ai<=ahi;ai++){const ax=AX[ai];if(cellQty(ri,ax))st.sel.add(`${ri}:${ax}`);}};
    // ★도번칸 = 행 전체선택. 클릭=그 행 날짜셀 전체선택(재클릭 해제) / **Ctrl+클릭=여러 행 누적**.
    c.querySelectorAll('.mv-item').forEach(el=>el.onclick=(e)=>{
      const i=+el.dataset.i, add=(e.ctrlKey||e.metaKey);
      const rowKeys=AX.filter(ax=>cellQty(i,ax)).map(ax=>`${i}:${ax}`);
      const on=rowKeys.length&&rowKeys.every(k=>st.sel.has(k));
      if(add){                                   // 누적: 이 행만 토글, 나머지 선택 유지
        if(on)rowKeys.forEach(k=>st.sel.delete(k));
        else  rowKeys.forEach(k=>st.sel.add(k));
        st.itemSel=on?null:i;
      }else if(st.itemSel===i&&on){st.itemSel=null;st.sel.clear();}
      else{st.itemSel=i;st.sel.clear();rowKeys.forEach(k=>st.sel.add(k));}
      draw();});
    c.querySelectorAll('.mv-cell[data-key]').forEach(el=>{
      // ★왼쪽 버튼(e.button===0)일 때만 드래그. 우클릭/휠클릭은 무시(브라우저 기본동작 유지).
      el.addEventListener('mousedown',e=>{
        if(e.button!==0)return;
        const key=el.dataset.key, add=(e.ctrlKey||e.metaKey);
        // ★Ctrl 없이 이미 선택된 단일 셀을 다시 누르면 해제(420 g4 그리드와 동일 동작)
        if(!add&&st.sel.has(key)&&st.sel.size===1){st.sel.delete(key);paint();e.preventDefault();return;}
        dragging=true;startCell={i:+el.dataset.i,d:el.dataset.d,add:add};
        st.itemSel=null;                        // 셀 드래그 시작 = 도번선택 해제(둘이 동시에 남지 않게)
        c.querySelectorAll('.mv-item').forEach(t=>{t.style.background='';t.style.color='';t.style.fontWeight='';t.style.outline='';});
        // Ctrl+드래그면 기존 선택 유지(누적), 아니면 새로 시작
        applySel(startCell.i,startCell.i,startCell.d,startCell.d,add);paint();e.preventDefault();});
      el.addEventListener('mouseover',e=>{
        if(dragging&&startCell&&(e.buttons&1)){
          applySel(startCell.i,+el.dataset.i,startCell.d,el.dataset.d,startCell.add);paint();}});
    });
    if(!c._mvUp){c._mvUp=true;document.addEventListener('mouseup',()=>{dragging=false;});}

    /* ══ 복사 (2026-09-06 — 420·410 과 같은 동작) ═══════════════════════════
         위의 셀 선택(.mv-cell)은 **이동처리 대상**을 고르는 기능이라 건드리지 않는다.
         도번·자도번LIST 같은 텍스트칸까지 넣으면 이동처리 로직이 깨진다.
         ⟹ 전 셀을 덮는 **복사 전용 레이어**(.mvcp, 노랑)를 따로 둔다. */
    {
      const tbl=c.querySelector('.mv-tbl');
      const tb=tbl&&tbl.tBodies[0];
      if(tb&&!tb.dataset.cpsel){
        tb.dataset.cpsel='1';
        const rcOf=td=>{const tr=td.parentElement;return {r:tr?tr.rowIndex:-1,c:td.cellIndex};};
        let cdrag=false,_ca=null,_cc=null,_cl=null;
        const cpClear=()=>tbl.querySelectorAll('td.mvcp').forEach(td=>td.classList.remove('mvcp'));
        const cpSnap=()=>{_cc=[...tb.querySelectorAll('td')]
          .map(x=>{const p=rcOf(x);return {td:x,r:p.r,c:p.c};});};
        const cpRect=(td)=>{if(!_ca||!_cc)return;
          const b=rcOf(td);
          const r1=Math.min(_ca.r,b.r),r2=Math.max(_ca.r,b.r);
          const c1=Math.min(_ca.c,b.c),c2=Math.max(_ca.c,b.c);
          for(const it of _cc)it.td.classList.toggle('mvcp',
            it.r>=r1&&it.r<=r2&&it.c>=c1&&it.c<=c2);};
        tb.addEventListener('mousedown',e=>{
          if(e.button!==0)return;
          if(e.target.closest('.mv-cell[data-key],.mv-item'))return;  // 일자칸·도번칸은 기존 선택이 처리
          const start=e.target.closest('td'); if(!start||!start.closest('tr'))return;
          e.preventDefault();
          if(!e.ctrlKey&&!e.metaKey)cpClear();
          cdrag=true;cpSnap();_ca=rcOf(start);_cl=start;cpRect(start);});
        tb.addEventListener('mousemove',e=>{if(!cdrag)return;
          if(!(e.buttons&1)){cdrag=false;_ca=null;_cc=null;_cl=null;return;}
          const el=document.elementFromPoint(e.clientX,e.clientY);
          const td=(el&&el.closest('td'))||_cl;
          if(td){_cl=td;cpRect(td);}});
        document.addEventListener('mouseup',()=>{cdrag=false;_ca=null;_cc=null;_cl=null;});
        tb.addEventListener('mousedown',e=>{   // 일자칸 드래그 시작 = 복사선택 해제
          if(e.button===0&&e.target.closest('.mv-cell[data-key]'))cpClear();});
      }
      const selText=()=>{
        const map=new Map();
        const pick=c.querySelector('td.mvcp')?'td.mvcp':'td.mv-cell.sel';
        c.querySelectorAll(pick).forEach(td=>{
          const tr=td.parentElement; if(!tr)return;
          if(!map.has(tr.rowIndex))map.set(tr.rowIndex,[]);
          map.get(tr.rowIndex).push([td.cellIndex,(td.innerText||'').trim()]);});
        return [...map.keys()].sort((x,y)=>x-y)
          .map(r=>map.get(r).sort((x,y)=>x[0]-y[0]).map(x=>x[1]).join('\t')).join('\n');
      };
      const toClip=(txt,what)=>{
        if(!txt){alert('복사할 영역을 먼저 끌어서 선택하세요.');return;}
        const done=()=>{const el=c.querySelector('#mv-cnt');
          if(el){const o=el.innerHTML;el.innerHTML=`<b style="color:#1c7c3a">${what} 복사됨</b>`;
                 setTimeout(()=>{el.innerHTML=o;},1400);}};
        // ★비보안(http 운영 184)은 clipboard API 가 막히고 그 거부는 비동기 —
        //   제스처 밖에서 fb 가 돌면 execCommand 도 막힌다. 처음부터 동기 fb(2026-09-08).
        if(window.isSecureContext&&navigator.clipboard&&navigator.clipboard.writeText)
          navigator.clipboard.writeText(txt).then(done,()=>fb()); else fb();
        function fb(){const ta=document.createElement('textarea'); ta.value=txt;
          ta.style.cssText='position:fixed;left:-9999px;top:0';
          document.body.appendChild(ta); ta.focus(); ta.select();
          let ok=false; try{ok=document.execCommand('copy');}catch(_){}
          ta.remove();
          if(ok)done(); else alert('복사에 실패했습니다.');}
      };
      const copySel=()=>toClip(selText(),'선택영역');
      const copyAll=()=>{
        if(!tbl)return; const out=[];
        const hr=tbl.tHead&&tbl.tHead.rows[0];
        if(hr)out.push([...hr.cells].map(th=>(th.innerText||'').trim()).join('\t'));
        [...tbl.tBodies].forEach(b=>{for(const tr of b.rows)
          out.push([...tr.cells].map(td=>(td.innerText||'').trim()).join('\t'));});
        toClip(out.join('\n'),`전체 ${out.length-1}행`);
      };
      // ★Ctrl+C 는 document 에서 받는다 — 범위선택 mousedown 의 preventDefault 때문에
      //   c 에 포커스가 오지 않아 c.onkeydown 은 아예 안 불린다(2026-09-08, 420 과 동일 수정).
      c._mvCopySel=copySel;
      if(!c.dataset.cpkey){
        c.dataset.cpkey='1';
        c.setAttribute('tabindex','-1'); c.style.outline='none';
        document.addEventListener('keydown',ev=>{
          if(!((ev.ctrlKey||ev.metaKey)&&(ev.key==='c'||ev.key==='C')))return;
          if(!c.isConnected||!c.offsetParent)return;
          const t=ev.target;
          if(t&&(t.tagName==='INPUT'||t.tagName==='TEXTAREA'||t.tagName==='SELECT'||t.isContentEditable))return;
          if(!c.querySelector('td.mvcp,td.mv-cell.sel'))return;
          ev.preventDefault(); if(c._mvCopySel)c._mvCopySel();});
      }
      /* 우클릭 메뉴 — ★실행도 mousedown 에서(410·420 과 같은 함정 회피:
         바깥클릭 닫기가 mousedown 이라 click 은 죽은 노드에 떨어진다). */
      c.querySelectorAll('.mv-tbl thead th,.mv-tbl tbody').forEach(el=>{
        el.oncontextmenu=e=>{
          e.preventDefault();
          const old=document.getElementById('mv-ctx'); if(old)old.remove();
          const m=document.createElement('div'); m.id='mv-ctx';
          m.style.cssText=`position:fixed;left:${Math.min(e.clientX,innerWidth-170)}px;
            top:${Math.min(e.clientY,innerHeight-90)}px;z-index:1400;background:#fff;
            border:1px solid #cfd8e6;border-radius:6px;box-shadow:0 6px 20px rgba(20,40,80,.22);
            font-size:12.5px;min-width:150px;overflow:hidden`;
          m.innerHTML=['항목보기','선택영역 복사','전체 복사']
            .map((t,i)=>`<div data-i="${i}" style="padding:7px 12px;cursor:pointer">${t}</div>`).join('');
          document.body.appendChild(m);
          m.querySelectorAll('div[data-i]').forEach(d=>{
            d.onmouseenter=()=>d.style.background='#eef4ff';
            d.onmouseleave=()=>d.style.background='';});
          const kill=()=>{m.remove();document.removeEventListener('mousedown',outside,true);};
          const outside=ev2=>{if(!m.contains(ev2.target))kill();};
          setTimeout(()=>document.addEventListener('mousedown',outside,true),0);
          m.addEventListener('mousedown',ev2=>{
            ev2.preventDefault(); ev2.stopPropagation();
            const t=ev2.target.closest&&ev2.target.closest('[data-i]'); if(!t)return;
            const i=+t.dataset.i; kill();
            try{ if(i===0)openColPick(); else if(i===1)copySel(); else copyAll(); }
            catch(err){console.error('[580 메뉴]',err);alert('실행 실패: '+(err&&err.message||err));}});
        };
      });
    }
    paint();   // ★재렌더 후 선택표시·선택수량 복원(도번칸 Ctrl+클릭 누적분 포함)
    // ★발행 직후 화면 반영 — 서버 재조회 없이 st.all 의 해당 셀을 직접 올린다(사용자요청 2026-08-23).
    //   applied = [{assy, ymd('P'=당일이전), qty}] — 발행한 수량만큼 분자(완료)를 올리고 색을 칠한다.
    const applyIssued=(applied)=>{
      const WEBPR='#66bb6a';
      (applied||[]).forEach(a=>{
        st.all.forEach(r=>{
          if(r.assy!==a.assy)return;
          if(a.ymd==='P'){
            if(!(r.prior>0))return;
            r.prior_webpr=(+r.prior_webpr||0)+a.qty;
            r.prior_done=Math.min((+r.prior_done||0)+a.qty, r.prior);
            if(!r.prior_color&&r.prior_done>=r.prior-1e-9)r.prior_color=WEBPR;
          }else{
            const plan=(r.days&&r.days[a.ymd])||0; if(!plan)return;
            r.webpr=r.webpr||{}; r.webpr[a.ymd]=(+r.webpr[a.ymd]||0)+a.qty;
            r.doneday=r.doneday||{}; r.doneday[a.ymd]=Math.min((+r.doneday[a.ymd]||0)+a.qty, plan);
            r.colorday=r.colorday||{};
            if(!r.colorday[a.ymd]&&r.doneday[a.ymd]>=plan-1e-9)r.colorday[a.ymd]=WEBPR;
          }
          r.jp_print=(+r.jp_print||0)+a.qty;
          r.need=Math.max(0,(+r.need||0)-a.qty);
        });
      });
      applyFilter(); draw();
    };
    g('#mv-move').onclick=()=>openMoveModal(st,dates,applyIssued);
  };
  // ★화면 진입 시 자동조회 안 함(조건 잡고 조회 버튼을 눌렀을 때만) — 2026-08-22 사용자요청.
  // ★계획 기준일 반영 후 그린다(조회는 여전히 사용자가) — 2026-08-28
  planBase().then(b=>{if(b&&b.iso){st.from=b.iso;
      st.to=iso(new Date(new Date(b.iso+'T00:00:00').getTime()+(st.gigan-1)*864e5));}}).catch(()=>{}).then(draw);
};

/* 가공자재 이동처리 팝업 (w_pr_input_586 "자재개별일괄출고") — 선택셀 자동채움 or 수동 행추가.
   레거시: work_code='P2'→자기자신 등록, gole_in_cust_code 있음→사급(BOM전개), 그 외→사내생산(BOM전개).
   저장 = nx.PU_T_STOCK_MAINT_GAGONG_MOVE INSERT(MAINT_TAG='B', IN_CONFIRM_FLAG='0') — "발행"이지 확정 아님. */
function openMoveModal(st,dates,onIssued){
  const API=API_BASE;
  const nf=n=>Number(n||0).toLocaleString('ko-KR',{maximumFractionDigits:0});
  const iso=x=>`${x.getFullYear()}-${String(x.getMonth()+1).padStart(2,'0')}-${String(x.getDate()).padStart(2,'0')}`;
  const ov=document.createElement('div');
  ov.style.cssText='position:fixed;inset:0;background:rgba(0,0,0,.35);z-index:9999;display:flex;align-items:center;justify-content:center';
  const rows=[];   // {seq,item_code(생산품번/도번),mat_code(자도번),item_desc,set_qty,use_qty,maint_qty,remarks}
  // 선택셀 → 자동채움: ceiling(plan-done) 수량으로 (도번,자도번) 1행씩. BOM전개는 저장시 백엔드가 work_code로 판정.
  if(st.sel.size){
    // key=(assy|mat) → 수량 누적. 레거시 586: 출고수량 = ceiling(plan - finish), 자도번마다 그 수량이 각각 적용.
    const acc=new Map();
    for(const key of st.sel){
      const ri=key.slice(0,key.indexOf(':')), d=key.slice(key.indexOf(':')+1);
      const r=st.rows[+ri]; if(!r)continue;
      // d==='P' = 당일이전 칸(plan_qty_00/finish_qty_00)
      const plan=d==='P'?(r.prior||0):((r.days&&r.days[d])||0);
      const done=d==='P'?(r.prior_done||0):((r.doneday&&r.doneday[d])||0);
      const outQty=Math.ceil(plan-done); if(outQty<=0)continue;
      // ★SP의 mat_list 형식 = "MJU63612402" 또는 "MJU66510812,MJU66510813" (수량 {n} 없음).
      //   예전 파서는 "MAT{수량}"만 인식해 전부 버려졌다 → 콤마분리 + 선택적 {수량} 처리(2026-08-22 수정).
      const mats=(r.jado||'').split(',').map(x=>x.trim()).filter(Boolean)
        .map(x=>{const m=x.match(/^(.+?)\{(\d+)\}$/);return m?{mat:m[1].trim(),q:+m[2]}:{mat:x,q:null};});
      const list=mats.length?mats:[{mat:(r.assy||''),q:null}];
      list.forEach(p=>{
        if(!p.mat)return;
        // ★계획일자(plan_ymd)까지 키에 포함 — 어느 날짜셀에서 발행했는지 보존해야 그 셀에 색이 칠해진다.
        //   당일이전(P)은 실제 계획일이 조회범위 이전이므로 'P' 마커를 그대로 저장한다(조회 때 당일이전 칸에 합산).
        const pymd=(d==='P')?'P':d;
        const k=r.assy+' '+p.mat+' '+pymd;
        const prev=acc.get(k)||{assy:r.assy,mat:p.mat,qty:0,plan_ymd:pymd,gole_proc:r.gole_proc||'',gole_cust:r.gole_cust||'',nm:r.nm||''};
        prev.qty+=outQty;                       // 자도번별로 각각 출고수량 적용(레거시 동일)
        acc.set(k,prev);
      });
    }
    for(const v of acc.values())rows.push({item_code:v.assy,mat_code:v.mat,item_desc:v.nm,set_qty:v.qty,use_qty:1,maint_qty:v.qty,remarks:'',
                                            plan_ymd:v.plan_ymd,gole_proc:v.gole_proc,gole_cust:v.gole_cust});
  }
  // 빈 행은 5줄만(레거시는 50줄이지만 화면을 넘겨 스크롤 유발 — 필요하면 행추가로).
  while(rows.length<5)rows.push({item_code:'',mat_code:'',item_desc:'',set_qty:0,use_qty:0,maint_qty:0,remarks:''});
  const state={ymd:iso(new Date()),out_wh:'P0001',in_wh:'IS0001',dest:'',rows};
  const render=()=>{
    ov.innerHTML=`<div style="background:#fff;border-radius:10px;width:900px;max-width:96vw;max-height:86vh;display:flex;flex-direction:column;box-shadow:0 10px 40px rgba(0,0,0,.3);font-size:12px">
      <style>
        /* ★.inp 전역 min-width:200px 이 표 안에서 칸을 밀어내 출고수량이 잘렸다 → 팝업 안에서만 해제 */
        .mm-tbl .inp{min-width:0!important;width:100%!important;height:26px;padding:0 4px;font-size:12px}
        .mm-tbl td,.mm-tbl th{padding:2px 3px;text-align:center!important}
      </style>
      <div style="display:flex;justify-content:space-between;align-items:center;padding:8px 12px;border-bottom:1px solid #e5e9f0">
        <b style="font-size:14px">🚚 자재개별일괄출고 (가공자재 이동처리)</b><span id="mm-x" style="cursor:pointer;font-size:18px;color:#888">✕</span></div>
      <div style="padding:8px 12px;display:flex;flex-wrap:wrap;gap:6px;align-items:center;background:#f2f7ff">
        <label class="tl">이동일자</label><input class="inp" type="date" id="mm-ymd" value="${state.ymd}" style="width:132px;min-width:0">
        <label class="tl">출고가공창고</label><input class="inp" id="mm-outwh" value="${esc(state.out_wh)}" style="width:70px;min-width:0">
        <label class="tl">입고자재창고</label><input class="inp" id="mm-inwh" value="${esc(state.in_wh)}" style="width:70px;min-width:0">
        <label class="tl">출고처</label><input class="inp" id="mm-dest" value="${esc(state.dest)}" style="width:110px;min-width:0" placeholder="최종납품처">
        <div class="spacer"></div>
        <button class="btn" id="mm-delrow" style="padding:3px 10px">➖ 빈행삭제</button>
        <button class="btn" id="mm-addrow" style="padding:3px 10px">➕ 행추가</button>
      </div>
      <div id="mm-msg" style="padding:0 12px;min-height:15px;font-size:12px"></div>
      <div style="flex:1;min-height:0;overflow-y:auto;overflow-x:hidden;padding:0 12px">
        <table class="tbl fit mm-tbl" style="font-size:12px;text-align:center;width:100%;table-layout:fixed"><thead><tr>
          <th style="width:32px">SEQ</th><th style="width:150px">생산품번</th><th style="width:150px">가공품번</th><th>품명</th>
          <!-- ★재고수량 = 출고가공창고(P0001 등) 재고. 레거시 586 그리드와 동일(2026-09-01) -->
          <th style="width:74px">재고수량</th>
          <th style="width:58px">SET</th><th style="width:52px">사용</th><th style="width:78px">출고수량</th><th style="width:110px">비고</th></tr></thead>
        <tbody>${state.rows.map((r,i)=>`<tr>
          <td class="center">${i+1}</td>
          <td><input class="inp mm-f" data-i="${i}" data-k="item_code" value="${esc(r.item_code)}" style="text-align:center" placeholder="도번"></td>
          <td><input class="inp mm-f" data-i="${i}" data-k="mat_code" value="${esc(r.mat_code)}" style="text-align:center" placeholder="자도번"></td>
          <td style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${esc(r.item_desc)}">${esc(r.item_desc)}</td>
          <!-- ★재고수량(가공창고) — 출고수량보다 적으면 빨강으로 경고 -->
          <td class="center" style="${(r.stock!=null&&(+r.maint_qty||0)>(+r.stock||0))?'color:#c0392b;font-weight:700':'color:#333'}"
              title="${esc(state.out_wh)} 창고 재고">${r.stock==null?'':nf(r.stock)}</td>
          <td><input class="inp mm-f" data-i="${i}" data-k="set_qty" type="number" value="${r.set_qty||''}" style="text-align:center"></td>
          <td><input class="inp mm-f" data-i="${i}" data-k="use_qty" type="number" value="${r.use_qty||''}" style="text-align:center"></td>
          <td><input class="inp mm-f" data-i="${i}" data-k="maint_qty" type="number" value="${r.maint_qty||''}" style="text-align:center;font-weight:700;background:#fffbe6" title="직접 수정 가능(SET×사용 자동계산값을 덮어씀)"></td>
          <td><input class="inp mm-f" data-i="${i}" data-k="remarks" value="${esc(r.remarks||'')}"></td></tr>`).join('')}</tbody></table>
      </div>
      <div style="display:flex;gap:8px;justify-content:flex-end;align-items:center;padding:8px 12px;border-top:1px solid #e5e9f0;flex-wrap:wrap">
        <span style="margin-right:auto;display:flex;gap:12px;align-items:center">
          <!-- ★2026-08-24 기본 해제 — 저장할 때마다 인쇄창이 뜨지 않게. 필요할 때만 체크해서 출력. -->
          <b style="font-size:12px;color:#555">저장 시 인쇄</b>
          <label class="rl"><input type="checkbox" id="mm-pr-card"> 부품납품표(개별)</label>
          <label class="rl"><input type="checkbox" id="mm-pr-list"> 부품확인/납품표(묶음)</label>
        </span>
        <button class="btn" id="mm-save" style="background:#1c47a0;color:#fff">✔ 저장(이동전표 발행)</button>
        <button class="btn" id="mm-close2">닫기</button></div>
    </div>`;
    const q=s=>ov.querySelector(s);
    const msg=(t,ok)=>{q('#mm-msg').innerHTML=t?`<span style="color:${ok?'#1c7c3a':'#c0392b'}">${esc(t)}</span>`:'';};
    q('#mm-x').onclick=q('#mm-close2').onclick=()=>ov.remove();
    q('#mm-ymd').onchange=e=>state.ymd=e.target.value;
    q('#mm-outwh').onchange=e=>state.out_wh=e.target.value.trim();
    q('#mm-inwh').onchange=e=>state.in_wh=e.target.value.trim();
    q('#mm-dest').onchange=e=>state.dest=e.target.value.trim();
    q('#mm-addrow').onclick=()=>{for(let k=0;k<5;k++)state.rows.push({item_code:'',mat_code:'',item_desc:'',set_qty:0,use_qty:0,maint_qty:0,remarks:''});render();};
    // ★빈행삭제(2026-09-01 요청) — 도번·자도번이 모두 빈 행만 지운다.
    //   입력된 행은 실수로 사라지면 안 되므로 절대 건드리지 않는다.
    //   전부 지워지면 입력할 칸이 없어지므로 최소 1행은 남긴다.
    q('#mm-delrow').onclick=()=>{
      const isEmpty=r=>!String(r.item_code||'').trim()&&!String(r.mat_code||'').trim();
      const keep=state.rows.filter(r=>!isEmpty(r));
      const removed=state.rows.length-keep.length;
      if(!removed){q('#mm-msg').innerHTML='<span style="color:#c0392b">지울 빈 행이 없습니다.</span>';return;}
      state.rows=keep.length?keep:[{item_code:'',mat_code:'',item_desc:'',set_qty:0,use_qty:0,maint_qty:0,remarks:''}];
      render();
      q('#mm-msg').innerHTML=`<span style="color:#1f7a3d">빈 행 ${removed}개를 삭제했습니다.</span>`;
    };
    // ★출고수량(maint_qty)은 직접 입력 가능. SET/사용 수정 시에만 자동계산으로 덮어쓴다.
    //   재렌더하면 입력 중 포커스가 날아가므로 state만 갱신(품명 등 표시는 다음 렌더에 반영).
    ov.querySelectorAll('.mm-f').forEach(el=>el.onchange=()=>{
      const i=+el.dataset.i,k=el.dataset.k,r=state.rows[i];
      r[k]=(k==='set_qty'||k==='use_qty'||k==='maint_qty')?(+el.value||0):el.value;
      if(k==='set_qty'||k==='use_qty'){
        r.maint_qty=(r.set_qty||0)*(r.use_qty||0);
        const t=ov.querySelector(`.mm-f[data-i="${i}"][data-k="maint_qty"]`); if(t)t.value=r.maint_qty||'';
      }
      // ★자도번을 넣으면 품명 + 가공창고 재고를 조회해 채운다(2026-09-01).
      //   재렌더하면 입력 포커스가 날아가므로 해당 셀만 직접 갱신한다.
      if(k==='mat_code')loadMatInfo(i);
    });
    // 자도번 → 품명·재고 조회. 출고가공창고(state.out_wh) 기준.
    const loadMatInfo=async(i)=>{
      const r=state.rows[i], m=String(r.mat_code||'').trim();
      if(!m){r.item_desc='';r.stock=null;paintRow(i);return;}
      try{
        const d=await(await fetch(`${API}/api/gagong/move580/matinfo?mat=${encodeURIComponent(m)}`
                                  +`&wh=${encodeURIComponent(state.out_wh||'P0001')}`)).json();
        r.item_desc=d.nm||''; r.stock=(d.stock==null?null:+d.stock);
        if(!d.found)r.item_desc='(품목마스터에 없음)';
      }catch(e){ r.stock=null; }
      paintRow(i);
    };
    // 그 행의 품명·재고 칸만 다시 그린다(전체 재렌더 금지 — 입력 중 포커스 보존).
    const paintRow=(i)=>{
      const tr=ov.querySelectorAll('.mm-tbl tbody tr')[i]; if(!tr)return;
      const r=state.rows[i], tds=tr.children;
      if(tds[3]){tds[3].textContent=r.item_desc||'';tds[3].title=r.item_desc||'';}
      if(tds[4]){
        tds[4].textContent=(r.stock==null?'':nf(r.stock));
        const over=(r.stock!=null&&(+r.maint_qty||0)>(+r.stock||0));
        tds[4].style.color=over?'#c0392b':'#333';
        tds[4].style.fontWeight=over?'700':'400';
      }
    };
    q('#mm-save').onclick=async()=>{
      const valid=state.rows.filter(r=>r.mat_code&&r.item_code&&(r.maint_qty>0));
      if(!valid.length){msg('출고수량이 있는 행이 없습니다(자도번·수량 확인).',false);return;}
      const wantCard=q('#mm-pr-card').checked, wantList=q('#mm-pr-list').checked;
      q('#mm-save').disabled=true;
      try{
        const res=await fetch(`${API}/api/gagong/move580/issue`,{method:'POST',headers:{'Content-Type':'application/json'},
          body:JSON.stringify({ymd:state.ymd,out_wh:state.out_wh,in_wh:state.in_wh,dest:state.dest,rows:valid,user:'웹'})});
        if(!res.ok){let t='';try{t=(await res.json()).detail||'';}catch(e){t=await res.text();}
          msg('등록 실패: '+(t||res.status),false);return;}
        const d=await res.json();
        if(d.ok){
          msg(`✔ 이동전표 ${d.cnt}건 발행됨(전표번호 MV${String(d.group_seq_from||0).padStart(8,'0')}~MV${String(d.group_seq_to||0).padStart(8,'0')})`,true);
          // ★재조회 없이 화면에 즉시 반영 — (도번,계획일자)별 발행수량을 그리드로 넘긴다.
          if(typeof onIssued==='function'){
            const agg=new Map();
            valid.forEach(r=>{
              const key=(r.item_code||'')+'|'+(r.plan_ymd||'P');
              const p=agg.get(key)||{assy:r.item_code||'',ymd:r.plan_ymd||'P',qty:0};
              p.qty+=(+r.maint_qty||0); agg.set(key,p);
            });
            try{onIssued([...agg.values()]);}catch(e){}
          }
          if((wantCard||wantList)&&d.group_seq_from!=null)await printMoveSheets(d.group_seq_from,d.group_seq_to,{card:wantCard,list:wantList});
          setTimeout(()=>{ov.remove();},900);
        }
        else msg(d.msg||'등록 실패',false);
      }catch(e){msg('등록 실패: '+(e&&e.message||e),false);}
      finally{const b=q('#mm-save');if(b)b.disabled=false;}
    };
  };
  render(); document.body.appendChild(ov);
  // ★자동채움된 행(선택셀에서 넘어온 것)들의 가공창고 재고를 처음 한 번 채운다(2026-09-01).
  //   순차 호출 — 행이 많아야 수십 개라 부담 없고, 동시요청으로 커넥션을 물지 않는다.
  (async()=>{
    for(let i=0;i<state.rows.length;i++){
      const m=String(state.rows[i].mat_code||'').trim(); if(!m)continue;
      try{
        const d=await(await fetch(`${API}/api/gagong/move580/matinfo?mat=${encodeURIComponent(m)}`
                                  +`&wh=${encodeURIComponent(state.out_wh||'P0001')}`)).json();
        state.rows[i].stock=(d.stock==null?null:+d.stock);
        if(!state.rows[i].item_desc)state.rows[i].item_desc=d.nm||'';
      }catch(e){}
    }
    if(document.body.contains(ov))render();
  })();
}

/* 부품납품표(개별카드)+부품확인/납품표(그룹묶음 8행/페이지) 인쇄 — dw_pr_input_586_p1/p2 재현.
   group_from~group_to = MAINT_GROUP_SEQ 범위(단건이면 동일값). 바코드 = "MV"+8자리0패딩.
   opt={card:bool,list:bool} — 두 전표를 각각 낼지 선택(미지정=둘 다).
   opt.onlyMat — 지정하면 그 자도번(품번)만 출력. 전표목록에서 '전체' 미체크 시 사용.
                 (체크=전표 전체 품번 / 미체크=클릭한 행의 품번만. 2026-08-24) */
async function printMoveSheets(groupFrom,groupTo,opt){
  const want={card:true,list:true,...(opt||{})};
  if(!want.card&&!want.list)return;
  const onlyMat=(opt&&opt.onlyMat)?String(opt.onlyMat).trim():'';
  const API=API_BASE;
  const nf=n=>Number(n||0).toLocaleString('ko-KR',{maximumFractionDigits:0});
  let data;
  try{data=await(await fetch(`${API}/api/gagong/move580/print?group_from=${groupFrom}&group_to=${groupTo}`)).json();}
  catch(e){alert('인쇄 데이터 조회 실패');return;}
  let groups=data.groups||[];
  // ★onlyMat 지정 시 그 품번만 남긴다(전표 전체 대신 해당 1건만 출력).
  if(onlyMat){
    groups=groups.map(g=>({...g,items:(g.items||[]).filter(it=>String(it.mat||'').trim()===onlyMat)}))
                 .filter(g=>g.items.length);
  }
  if(!groups.length){alert('인쇄할 전표 내역이 없습니다.');return;}
  const ymdw=s=>{s=(''+(s||'')).trim();if(s.length<6)return s;return `${s.slice(0,2)}/${s.slice(2,4)}/${s.slice(4,6)}`;};
  /* ★바코드 확대(2026-09-04) — 제목을 키운 만큼 바코드도 같이 커져야 균형이 맞고,
       스캐너 판독에도 유리하다. 생성 scale 2→3(인쇄 해상도), 표시 높이 22→34px. */
  const bc=(txt)=>`<div style="text-align:center;line-height:1">
      <img src="${API}/api/barcode/code128?text=${encodeURIComponent(txt)}&h=60&scale=3"
           style="height:34px;max-width:100%;image-rendering:pixelated" alt="${esc(txt)}">
      </div>`;
  // 카드1장 = 그룹 내 1개 item(자도번) — 레거시 p1: 그룹의 각 행이 개별 카드.
  const cards=[];
  groups.forEach(g=>g.items.forEach(it=>cards.push({...it,sheet_no:g.sheet_no,ymd:g.ymd,line:g.line})));
  const cardHtml=c=>`<div class="mvc">
    <div class="mvc-title">부 품 납 품 표<span class="mvc-no">${esc(c.sheet_no)}</span></div>
    <table>
      <tr><td class="lb">날짜</td><td class="big">${esc(ymdw(c.ymd))}</td><td class="lb">수량</td><td class="big">${nf(c.qty)} EA</td></tr>
      <tr><td class="lb">Assy품번</td><td class="big" colspan="1">${esc(c.assy)}</td><td class="lb">라인</td><td>${esc(c.line)}</td></tr>
      <tr><td class="lb">부품 품번</td><td class="big" colspan="1">${esc(c.mat)}</td><td class="lb">보관장소</td><td class="big">${esc(c.rack)}</td></tr>
      <tr><td class="lb">비고</td><td colspan="3"></td></tr>
    </table>
    <div class="mvc-ft">(주)피앤씨인더스트리</div>
  </div>`;
  // 부품확인/납품표 = 그룹별 헤더 + 최대 8행/페이지(레거시 mod(cnt,8) 패딩 재현)
  const listPages=[];
  groups.forEach(g=>{
    const rows=g.items.map((it,i)=>({...it,no:i+1}));
    while(rows.length%8!==0)rows.push(null);
    // ★2026-08-24 전표번호·쪽수(n/N) 표시용 — 그룹 내 총 페이지수를 함께 담는다.
    const tot=Math.max(1,Math.ceil(rows.length/8));
    for(let p=0;p<rows.length;p+=8)listPages.push({g,rows:rows.slice(p,p+8),pno:(p/8)+1,ptot:tot});
  });
  const listHtml=({g,rows,pno,ptot})=>`<div class="mvl">
    <div class="mvl-title">부품확인/납품표<span class="mvl-bc">${bc(g.sheet_no)}
      <div class="mvl-sn"><span>${esc(g.sheet_no)}</span><span>${pno} / ${ptot}</span></div></span></div>
    <div class="mvl-hd"><span>날짜 <b>${esc(ymdw(g.ymd))}</b></span><span>라인 <b>${esc(g.line)}</b></span></div>
    <table><thead><tr><th>Assy품번</th><th>No</th><th>품번</th><th>수량</th><th>보관장소</th><th>확인</th></tr></thead>
    <tbody>${rows.map(r=>r?`<tr><td>${esc(r.assy)}</td><td class="num">${r.no}</td><td>${esc(r.mat)}</td><td class="num">${nf(r.qty)}</td><td>${esc(r.rack)}</td><td class="chk"><span></span></td></tr>`
      :`<tr><td></td><td></td><td></td><td></td><td></td><td class="chk"><span></span></td></tr>`).join('')}</tbody></table>
    <div class="mvl-ft">(주)피앤씨인더스트리</div>
  </div>`;
  // ★두 전표 모두 A4 세로(2026-08-24 카드도 A4 3매/장으로 통일) — 다만 별도 창으로 열어
  //   프린터·매수를 각각 기억시킨다(카드만/확인표만 뽑는 경우가 많음).
  // ★두 장을 함께 낼 때: window.print() 는 모달이라 첫 창에서 스크립트가 멈춘다.
  //   그러면 두번째 창을 여는 코드가 실행되지 못해 "하나만 출력"된다(2026-08-23 실측).
  //   → 창을 먼저 둘 다 열어 내용을 채우고, 인쇄는 각 창이 delay 를 달리해 스스로 띄우게 한다.
  const AUTOPRINT=(delay)=>`<script>
    (function(){var imgs=[].slice.call(document.images),left=imgs.length;
      function go(){setTimeout(function(){window.print();},${delay});}
      if(!left)return go();
      imgs.forEach(function(im){if(im.complete)done();else{im.addEventListener('load',done);im.addEventListener('error',done);}});
      function done(){if(--left<=0)go();}})();
  <\/script>`;
  const TOOLBAR=t=>`<div class="noprint" style="margin-bottom:6px">
    <button onclick="window.print()" style="padding:6px 16px;font-size:13px">🖨 인쇄</button>
    <button onclick="window.close()" style="padding:6px 16px;font-size:13px">닫기</button>
    <span style="font-size:12px;color:#555;margin-left:8px">${t}</span></div>`;
  const both=want.card&&cards.length&&want.list&&listPages.length;
  // ★창 2개는 반드시 "동시에" 연다. await 로 하나씩 열면 그 사이 사용자 제스처가 만료돼
  //   두번째 window.open 이 팝업차단된다(2026-08-23 실측). Promise 를 먼저 만들고 나중에 await.
  const pCard=(want.card&&cards.length)?openPrintWin('mvcard','pncPrnMvCard','width=900,height=700'):Promise.resolve(null);
  const pList=(want.list&&listPages.length)?openPrintWin('mvlist','pncPrnMvList','width=900,height=700'):Promise.resolve(null);
  const [wCard,wList]=await Promise.all([pCard,pList]);
  if(want.card&&cards.length){
    const w=wCard;
    if(!w)alert('팝업이 차단되었습니다. 브라우저 팝업 허용 후 다시 시도하세요.');
    else{
      w.document.write(`<!doctype html><html><head><meta charset="utf-8"><title>부품납품표 (${cards.length}장)</title>
      <style>
        /* ★2026-08-24 용지변경: 100×60mm 전용지 → A4 세로(부품확인/납품표와 동일), 1장에 3카드.
           A4 인쇄영역 = 210-16 × 297-16 = 194×281mm → 카드 90mm × 3 = 270mm + 간격 여유.
           page-break-inside:avoid 로 카드가 페이지 경계에서 쪼개지지 않게 하고,
           카드마다 page-break 를 걸던 기존 규칙은 제거(그래야 한 장에 3개가 앉는다). */
        @page{size:A4 portrait;margin:8mm}
        *{box-sizing:border-box}
        body{margin:0;font-family:'맑은 고딕',Malgun Gothic,sans-serif;font-size:10px;color:#000}
        .mvc{border:2px solid #000;page-break-inside:avoid;break-inside:avoid;overflow:hidden;
             height:90mm;display:flex;flex-direction:column;margin-bottom:4mm}
        .mvc:last-child{margin-bottom:0}
        /* ★전체 확대(2026-09-04 사용자 요청) — 레거시 실물 대비 작았다.
             카드 높이(90mm)·1장 3매 구성은 그대로 두고 글자만 키운다.
             제목 20→32px · 값 19→28px · 라벨 12→17px · 일반셀 14→20px.
             ※부품 품번은 최장 MJU66526302(11자) 정도라 28px 로도 셀을 넘지 않는다. */
        .mvc-title{text-align:center;font-size:32px;font-weight:800;padding:6px;border-bottom:2px solid #000;position:relative;flex:0 0 auto;letter-spacing:3px}
        .mvc-no{position:absolute;right:6px;top:12px;font-size:12px;color:#666;font-weight:400;letter-spacing:0}
        .mvc table{border-collapse:collapse;width:100%;flex:1 1 auto}
        .mvc td{border:1px solid #000;padding:6px 8px;font-size:20px;font-weight:700}
        .mvc .lb{font-weight:700;background:#f5f5f5;width:20%;font-size:17px}
        .mvc .big{font-size:28px;font-weight:800}
        .mvc-ft{text-align:center;font-size:11px;padding:4px;border-top:1px solid #000;flex:0 0 auto}
        @media print{.noprint{display:none}}
      </style></head><body>
      ${TOOLBAR(`부품납품표 ${cards.length}장 · A4 세로(1장에 3매) · ${Math.ceil(cards.length/3)}쪽`)}
      ${cards.map(cardHtml).join('')}
      ${AUTOPRINT(250)}</body></html>`);
      w.document.close();
    }
  }
  if(want.list&&listPages.length){
    const w2=wList;
    if(!w2)alert('팝업이 차단되었습니다. 브라우저 팝업 허용 후 다시 시도하세요.');
    else{
      w2.document.write(`<!doctype html><html><head><meta charset="utf-8"><title>부품확인/납품표 (${listPages.length}쪽)</title>
      <style>
        @page{size:A4 portrait;margin:8mm}
        *{box-sizing:border-box}
        /* ★전체 확대(2026-09-04 사용자 요청 "레거시 대비 크기가 작다").
             레거시 실물은 제목이 페이지 폭을 가득 채우고 표 글자도 굵고 크다.
             A4 한 장에 8행뿐이라 세로 여유가 많다 — 행 높이를 키워 그 공간을 쓴다.
             제목 26→44px · 표 12→19px · 헤더행 14→20px · 확인칸 14→20px.
             ※행수(8)·페이지 구성은 레거시 mod(cnt,8) 그대로 — 크기만 키운다. */
        body{margin:0;font-family:'맑은 고딕',Malgun Gothic,sans-serif;font-size:11px;color:#000}
        .mvl{page-break-inside:avoid}
        .mvl+.mvl{page-break-before:always}     /* 마지막 쪽 뒤에 빈 페이지가 안 생기게 */
        .mvl-title{font-size:44px;font-weight:800;display:flex;justify-content:space-between;align-items:center;border-bottom:3px solid #000;padding-bottom:4px;letter-spacing:2px}
        /* ★2026-08-24 바코드 아래 전표번호 + 쪽수(n/N) 표시 */
        .mvl-bc{display:block;text-align:right}
        .mvl-sn{display:flex;justify-content:space-between;gap:14px;font-size:13px;font-weight:400;
                letter-spacing:.5px;margin-top:1px;padding:0 2px}
        .mvl-hd{display:flex;gap:20px;font-size:22px;font-weight:700;padding:7px 0;border-bottom:1px solid #000}
        .mvl table{border-collapse:collapse;width:100%;margin-top:3px}
        .mvl th,.mvl td{border:1px solid #000;padding:9px 6px;font-size:19px;font-weight:700;text-align:center}
        .mvl thead th{font-size:20px}
        .mvl .chk span{display:inline-block;width:20px;height:20px;border:1px solid #000}
        .mvl-ft{text-align:center;font-size:11px;padding:5px;border-top:1px solid #000;margin-top:3px}
        @media print{.noprint{display:none}}
      </style></head><body>
      ${TOOLBAR(`부품확인/납품표 ${listPages.length}쪽 · A4`)}
      ${listPages.map(listHtml).join('')}
      ${AUTOPRINT(both?1800:250)}</body></html>`);
      w2.document.close();
    }
  }
}

/* ===== 생산: 가공전표이력현황 (w_pr_processing_010) — BOX_NO 마스터-디테일 ===== */
SCREEN.gagongjeohist=(c)=>{
  const API=API_BASE;
  const nf=n=>Number(n||0).toLocaleString('ko-KR',{maximumFractionDigits:0});
  const dcol=s=>(s&&(''+s).length===6)?`${(''+s).slice(2,4)}/${(''+s).slice(4,6)}`:s;
  const iso=x=>`${x.getFullYear()}-${String(x.getMonth()+1).padStart(2,'0')}-${String(x.getDate()).padStart(2,'0')}`;
  const T=new Date();
  const DAM='<span style="color:#c0392b;font-size:10px" title="원천 미확정 — 담당확인 필요">담당확인</span>';   // 공백/추정 금지
  const st={from:iso(T),to:iso(T),item:'',jado:'',wc:'',   // ★기본 전표출력기간 = 당일~당일(대표지시)
            rows:[],cnt:0,sel:'',detail:[],loading:false,dloading:false,msg:''};
  const load=async()=>{st.loading=true;draw();
    const qs=new URLSearchParams({from_ymd:st.from,to_ymd:st.to,wc:st.wc,item:st.item,jado:st.jado,limit:500});
    try{const r=await fetch(`${API}/api/gagong/jeohist?${qs}`);const d=await r.json();st.rows=d.rows||[];st.cnt=d.cnt||0;st.msg='';}
    catch(e){st.msg='백엔드 연결 실패';st.rows=[];st.cnt=0;}
    st.loading=false;st.sel='';st.detail=[];draw();};
  const detailHTML=()=>st.dloading?spinRow(9):(st.sel?(st.detail.length?st.detail.map((r,i)=>`<tr>
         <td class="num">${i+1}</td><td>${esc(st.sel)}</td><td class="num">${r.PROC_SEQ}</td><td class="center">${esc(r.partnm)}</td>
         <td><b>${esc(r.swork)}</b> ${esc(r.sworknm||'')}</td><td class="center">${esc(r.mach)?`<b>${esc(r.mach)}</b> ${esc(r.machnm||'')}`:'·'}</td>
         <td class="num"${r.doneq?'':' style="color:#dfe6ef"'}>${r.doneq?nf(r.doneq):'·'}</td><td class="num">${r.proc_cnt==null?DAM:nf(r.proc_cnt)}</td>
         <td>${r.std==null?DAM:(esc(r.std)||'·')}</td></tr>`).join(''):`<tr><td colspan="9" class="empty">공정 없음</td></tr>`):`<tr><td colspan="9" class="empty">← 좌측 전표(바코드)를 선택하세요</td></tr>`);
  const renderDetail=()=>{const b=c.querySelector('#jh-dtl-body');if(b)b.innerHTML=detailHTML();};
  const loadDetail=async(box)=>{st.sel=box;
    c.querySelectorAll('.jh-row').forEach(el=>el.style.background=(el.dataset.box===box)?'#dcebff':'');  // 하이라이트만(전체 재렌더X→스크롤유지)
    st.dloading=true;renderDetail();
    try{const r=await fetch(`${API}/api/gagong/jeohist?box_no=${encodeURIComponent(box)}`);const d=await r.json();st.detail=d.detail||[];}
    catch(e){st.detail=[];}
    st.dloading=false;renderDetail();};
  const draw=()=>{
    const itS=new Map();st.rows.forEach(r=>{if(r.assy&&!itS.has(r.assy))itS.set(r.assy,'');});
    const itOpts=[...itS].map(([v])=>`<option value="${esc(v)}"></option>`).join('');
    c.innerHTML=`
     <div class="page-title">🧾 가공전표이력현황 <span style="font-size:12px;color:var(--muted);font-weight:400">전표(바코드)별 가공공정 이력</span></div>
     <div class="page-sub">전표=<code>PR_T_INDI_CUTTING</code>(바코드) · 공정실적=<code>PR_T_PROD_DTL_GAGONG</code>(레거시정본) + 명칭 <code>PR_M_WORK_SINGLE</code>·<code>QA_M_MACHINE</code>. 🟢 nx(웹 발행분 포함) · <span style="color:#c0392b">※=원천 미확정(담당확인)</span></div>
     <div class="toolbar">
       <label class="tl">전표출력기간</label><input class="inp" type="date" id="jh-from" value="${st.from}"> ~ <input class="inp" type="date" id="jh-to" value="${st.to}">
       <label class="tl">도번</label><input class="inp" id="jh-item" list="jh-iteml" value="${esc(st.item)}" style="width:120px" placeholder="상위도번" autocomplete="off"><datalist id="jh-iteml">${itOpts}</datalist>
       <label class="tl">자도번</label><input class="inp" id="jh-jado" value="${esc(st.jado)}" style="width:120px" placeholder="자도번" autocomplete="off">
       <label class="tl">작업처</label><input class="inp" id="jh-wc" value="${esc(st.wc)}" style="width:110px" placeholder="작업처 코드/명" autocomplete="off">
       <button class="btn" id="jh-search">🔍 조회</button>
       <div class="spacer"></div>
       <button class="btn" id="jh-del" style="background:#c0392b;color:#fff">🗑 삭제(발행취소)</button>
       <span class="rowcount">전표 <b>${nf(st.cnt)}</b>건</span>
     </div>
     <div id="jh-msg" class="page-sub" style="min-height:16px"></div>
     ${st.msg?`<div class="page-sub" style="color:#c0392b">⚠ ${esc(st.msg)}</div>`:''}
     <div style="display:flex;gap:8px;align-items:stretch">
      <div class="grid-wrap" style="flex:0 0 60%;max-height:calc(100vh - 300px);overflow:auto;background:#fff;border:1px solid var(--line-2,#c9d3e0);border-radius:8px">
       <table class="tbl fit" style="font-size:11px"><thead><tr><th>선택</th><th>번호</th><th>바코드번호</th><th>상위도번</th><th>자도번</th><th class="num">계획수량</th><th class="num">실적수량</th><th class="center">실적</th><th>작업처</th><th>작업처명</th><th class="num">지름</th><th class="num">두께</th><th title="원천 미확정 — 담당확인">검사완료시간※</th><th class="center">컷팅완료</th><th>컷팅작업자</th><th>컷팅작업일시</th><th>ASSY도번</th><th>ASSY작업처</th><th>상위도번작업처</th><th>입고창고</th><th class="center">발행일시</th><th>발행자</th></tr></thead>
       <tbody>${st.loading?spinRow(20):(st.rows.length?st.rows.map((r,i)=>{
         const locked=(+r.prod_qty||0)>0||String(r.prod_flag)==='1';   // 실적있음 = 삭제불가
         return `<tr class="jh-row" data-box="${esc(r.BOX_NO)}" style="cursor:pointer${st.sel===r.BOX_NO?';background:#dcebff':''}">
         <td class="center"><input type="checkbox" class="jh-chk" data-box="${esc(r.BOX_NO)}"${locked?' disabled title="실적이 잡혀 삭제할 수 없습니다"':''}></td>
         <td class="num">${i+1}</td><td><b>${esc(r.BOX_NO)}</b></td><td>${esc(r.doban)}</td><td>${esc(r.jado)}</td>
         <td class="num">${nf(+r.plan_qty||0)}</td>
         <td class="num"${locked?' style="color:#c0392b;font-weight:700"':''}>${nf(+r.prod_qty||0)}</td>
         <td class="center">${locked?'<span style="color:#c0392b">완료</span>':''}</td>
         <td class="center">${esc(r.wcen)||''}</td><td class="center">${esc(r.wcennm)||''}</td>
         <td class="num">${esc(r.diam)||''}</td><td class="num">${esc(r.thick)||''}</td>
         <td class="center">${esc(r.inspdt)||DAM}</td><td class="center">${esc(r.cutflag)}</td><td class="center">${esc(r.cutuser)||''}</td><td class="center">${esc(r.cutdt)||''}</td>
         <td>${esc(r.assy)}</td><td class="center">${esc(r.assywc)||''}</td><td class="center">${esc(r.dobanwc)||''}</td><td class="center">${esc(r.inwh)||''}</td>
         <!-- ★발행일시(전표 출력일시)·발행자 — 2026-08-28 사용자요청. 백엔드가 prt/prtuser 로 이미 내려준다 -->
         <td class="center" style="white-space:nowrap">${esc(r.prt)||''}</td><td class="center">${esc(r.prtuser)||''}</td></tr>`;}).join(''):`<tr><td colspan="22" class="empty">조회 결과 없음</td></tr>`)}</tbody></table></div>
      <div class="grid-wrap" style="flex:1;max-height:calc(100vh - 300px);overflow:auto;background:#fff;border:1px solid var(--line-2,#c9d3e0);border-radius:8px">
       <table class="tbl fit" style="font-size:11px"><thead><tr><th>번호</th><th>바코드</th><th class="num">공정순서</th><th>파트</th><th>가공공정</th><th>가공설비</th><th class="num">생산완료</th><th class="num" title="INDI_CUTTING_PROC_GAGONG 보충·부재시 담당확인">공정횟수※</th><th title="INDI_CUTTING_PROC_GAGONG 보충·부재시 담당확인">작업표준※</th></tr></thead>
       <tbody id="jh-dtl-body">${detailHTML()}</tbody></table></div>
     </div>`;
    const g=id=>c.querySelector(id);
    g('#jh-search').onclick=()=>{st.from=g('#jh-from').value;st.to=g('#jh-to').value;st.item=g('#jh-item').value.trim();st.jado=g('#jh-jado').value.trim();st.wc=g('#jh-wc').value.trim();load();};
    ['#jh-item','#jh-jado','#jh-wc'].forEach(id=>g(id).onkeyup=e=>{if(e.key==='Enter')g('#jh-search').click();});
    c.querySelectorAll('.jh-row').forEach(el=>el.onclick=()=>loadDetail(el.dataset.box));
    c.querySelectorAll('.jh-chk').forEach(cb=>cb.onclick=e=>e.stopPropagation());   // 체크박스는 상세로드 안 함
    // ★삭제(발행취소) — 레거시 w_pr_processing_010: 실적 잡힌 전표는 삭제불가(체크박스 자체가 disabled)
    g('#jh-del').onclick=async()=>{
      const boxes=[...c.querySelectorAll('.jh-chk:checked')].map(cb=>cb.dataset.box);
      const m=g('#jh-msg');
      if(!boxes.length){m.innerHTML='<span style="color:#c0392b">삭제할 전표를 선택하세요.</span>';return;}
      if(!confirm(`선택한 전표 ${boxes.length}건을 삭제할까요?\n\n바코드: ${boxes.slice(0,10).join(', ')}${boxes.length>10?' …':''}\n\n※발행정보가 사라지며, 실적이 잡힌 전표는 삭제되지 않습니다.`))return;
      g('#jh-del').disabled=true;
      try{
        const d=await(await fetch(`${API}/api/gagong/sheet/delete`,{method:'POST',
          headers:{'Content-Type':'application/json'},body:JSON.stringify({boxes:boxes})})).json();
        m.innerHTML=`<span style="color:${d.ok?'#1c7c3a':'#c0392b'}">${esc(d.msg||'')}</span>`;
        if(d.ok)load();
      }catch(e){m.innerHTML='<span style="color:#c0392b">삭제 실패</span>';}
      finally{const b=c.querySelector('#jh-del');if(b)b.disabled=false;}};
  };
  load();
};

/* ===== 가공: 가공세트재고관리 (w_pu_stock_280 + 조정팝업 w_pu_stock_285) =====
   ★원천(2026-08-23 레거시 소스/실측 확인)
     현재고   = PU_T_SET_MAT_STOCK (ITEM_CODE+IN_CUST_CODE) — 레거시 f_pu_get_set_mat_stock 과 동일
     조정이력 = PU_T_SET_STOCK_MAINT_GAGONG
   ★조회 = 라이브 + nx(웹 조정분) 합산 / 쓰기 = nx 만 (가공창고 이동계획 580 과 동일 패턴) */
SCREEN.gagongset280=(c)=>{
  const API=API_BASE;
  const nf=n=>Number(n||0).toLocaleString('ko-KR',{maximumFractionDigits:2});
  const dcol=s=>(s&&(''+s).length===6)?`${(''+s).slice(0,2)}/${(''+s).slice(2,4)}/${(''+s).slice(4,6)}`:s;
  const iso=x=>`${x.getFullYear()}-${String(x.getMonth()+1).padStart(2,'0')}-${String(x.getDate()).padStart(2,'0')}`;
  const T=new Date();
  const st={cust:'',item:'',gubun:'%',zero:'전체',
            rows:[],all:[],cnt:0,qty_sum:0,loading:false,loaded:false,msg:'',
            optCusts:[],optTags:[],sel:null,hist:[],histLoading:false};
  const loadOpts=async()=>{try{const d=await(await fetch(`${API}/api/gagongset/opts`)).json();
    st.optCusts=d.custs||[];st.optTags=d.tags||[];}catch(e){}};
  // 도번/구분/0재고는 받아둔 결과로 즉시 필터(서버 재조회는 세트거래처 바뀔 때만) — 580 과 동일 감각
  const applyFilter=()=>{
    const it=st.item.trim().toUpperCase();
    let rows=st.all;
    if(it) rows=rows.filter(r=>(r.item||'').toUpperCase().includes(it));
    if(st.gubun==='1') rows=rows.filter(r=>r.qty<0);
    else if(st.gubun==='0') rows=rows.filter(r=>r.qty>0);
    if(st.zero==='숨김') rows=rows.filter(r=>r.qty!==0);
    st.rows=rows; st.cnt=rows.length; st.qty_sum=rows.reduce((a,r)=>a+(+r.qty||0),0);
  };
  const load=async()=>{st.loading=true;draw();
    const qs=new URLSearchParams({cust:st.cust,item:'',gubun:'%',zero:'전체',limit:20000});
    try{const r=await fetch(`${API}/api/gagongset/list?${qs}`);const d=await r.json();
      st.all=d.rows||[];st.msg='';st.loaded=true;st.sel=null;st.hist=[];applyFilter();}
    catch(e){st.msg='백엔드 연결 실패';st.all=[];st.rows=[];st.cnt=0;}
    st.loading=false;draw();};
  // 행 클릭 = 그 품목의 조정이력(우측). 부분갱신(좌측 재렌더 X — 스크롤 유지)
  const histBody=()=>st.histLoading?spinRow(7):(st.hist.length?st.hist.map((h,i)=>`<tr>
      <td class="center">${i+1}</td><td class="center">${dcol(h.ymd)}</td><td class="center">${h.seq}</td>
      <td class="center">${esc(h.tag)}</td>
      <td class="center" style="font-weight:700;color:${h.qty<0?'#c0392b':'#1c7c3a'}">${nf(h.qty)}</td>
      <td class="center">${esc(h.user)}</td>
      <td class="center"><span style="font-size:10px;color:${h.src==='nx'?'#1c7c3a':'#888'}">${esc(h.src)}</span></td>
      </tr>`).join('')
    :`<tr><td colspan="7" class="empty">${st.sel?'조정이력 없음':'← 좌측에서 품목을 선택하세요'}</td></tr>`);
  const renderHist=()=>{const b=c.querySelector('#gs-hist-body');if(b)b.innerHTML=histBody();};
  const loadHist=async(r)=>{
    st.sel=r;
    c.querySelectorAll('.gs-row').forEach(el=>el.style.background=(el.dataset.k===r.cust+'|'+r.item)?'#dcebff':'');
    const t=c.querySelector('#gs-hist-title');
    if(t)t.innerHTML=`조정이력 — <b>${esc(r.item)}</b> <span style="color:var(--muted)">${esc(r.cust_nm)}</span>`;
    st.histLoading=true;renderHist();
    try{const d=await(await fetch(`${API}/api/gagongset/hist?item=${encodeURIComponent(r.item)}&cust=${encodeURIComponent(r.cust)}&limit=300`)).json();
      st.hist=d.rows||[];}catch(e){st.hist=[];}
    st.histLoading=false;renderHist();};
  const draw=()=>{
    const itOpts=[...new Set(st.all.map(r=>r.item))].slice(0,500).map(v=>`<option value="${esc(v)}"></option>`).join('');
    c.innerHTML=`
     <style>.gs-tbl th,.gs-tbl td{text-align:center!important}</style>
     <div class="page-title">📦 가공세트재고관리 <span style="font-size:12px;color:var(--muted);font-weight:400">거래처별 세트재고 현황 · 조정</span></div>
     <!-- ★배지 정정(2026-09-08) — 조회도 nx 다(백엔드 라이브 직독 0곳). 종전 '🔴 라이브 조회' 는 오표기. -->
     <div class="page-sub">현재고 <code>nx.PU_T_SET_GAGONG_STOCK</code>(레거시 <code>dw_pu_stock_280</code> 동일) + 웹 조정분 합산 · 조정이력 <code>nx.PU_T_SET_STOCK_MAINT_GAGONG</code>. 조회·조정등록 모두 nx</div>
     <div class="toolbar" style="flex-wrap:wrap;gap:6px;align-items:center">
       <label class="tl">세트거래처</label><select class="inp" id="gs-cust" style="width:200px"><option value="">전체 거래처</option>${st.optCusts.map(o=>`<option value="${esc(o.code)}"${st.cust===o.code?' selected':''}>${esc(o.nm)}(${esc(o.code)})</option>`).join('')}</select>
       <label class="tl">도번</label><input class="inp" id="gs-item" list="gs-iteml" value="${esc(st.item)}" style="width:150px" placeholder="도번" autocomplete="off"><datalist id="gs-iteml">${itOpts}</datalist>
       <label class="tl">구분</label>
       <label class="rl"><input type="radio" name="gs-gb" value="1"${st.gubun==='1'?' checked':''}> (-)재고</label>
       <label class="rl"><input type="radio" name="gs-gb" value="0"${st.gubun==='0'?' checked':''}> (+)재고</label>
       <label class="rl"><input type="radio" name="gs-gb" value="%"${st.gubun==='%'?' checked':''}> 전체</label>
       <label class="rl" title="재고 0 인 품목 숨김"><input type="checkbox" id="gs-zero"${st.zero==='숨김'?' checked':''}> 0재고 숨김</label>
       <button class="btn" id="gs-search">🔍 조회</button>
       <div class="spacer"></div>
       <button class="btn" id="gs-adj" style="background:#1c47a0;color:#fff">🔧 재고조정</button>
       <span class="rowcount">품목 <b>${nf(st.cnt)}</b> · 재고합 <b style="color:${st.qty_sum<0?'#c0392b':'#1c7c3a'}">${nf(st.qty_sum)}</b></span>
     </div>
     ${st.msg?`<div class="page-sub" style="color:#c0392b">⚠ ${esc(st.msg)}</div>`:''}
     <div style="display:flex;gap:8px;align-items:stretch">
      <div class="grid-wrap" style="flex:1 1 62%;max-height:calc(100vh - 260px);overflow:auto;background:#fff;border:1px solid var(--line-2,#c9d3e0);border-radius:8px">
       <table class="tbl fit gs-tbl" style="font-size:11px"><thead><tr>
         <th>SEQ</th><th>거래처코드</th><th>거래처명</th><th>업체담당자</th><th>세트도번</th><th>품명</th>
         <th>재고수량</th><th>최종작업자</th><th>최종작업일시</th></tr></thead>
       <tbody>${st.loading?spinRow(9):(st.rows.length?st.rows.map((r,i)=>`<tr class="gs-row" data-k="${esc(r.cust+'|'+r.item)}" style="cursor:pointer${st.sel&&st.sel.cust===r.cust&&st.sel.item===r.item?';background:#dcebff':''}">
         <td class="center">${i+1}</td><td class="center">${esc(r.cust)}</td><td class="center">${esc(r.cust_nm)}</td>
         <td class="center">${esc(r.charge)}</td><td class="center"><b>${esc(r.item)}</b></td>
         <td class="center" style="max-width:150px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${esc(r.item_nm)}">${esc(r.item_nm)}</td>
         <td class="center" style="font-weight:700;color:${r.qty<0?'#c0392b':(r.qty>0?'#1c7c3a':'#999')}">${nf(r.qty)}${r.nx_adj?`<span style="font-size:10px;color:#1c7c3a" title="웹 조정분 ${nf(r.nx_adj)} 포함"> ●</span>`:''}</td>
         <td class="center">${esc(r.upd_user)}</td><td class="center">${esc(r.upd_dt)}</td></tr>`).join('')
         :`<tr><td colspan="9" class="empty">${st.loaded?'조회 결과 없음':'조건을 지정한 뒤 <b>🔍 조회</b> 버튼을 누르세요.'}</td></tr>`)}</tbody>
       ${st.rows.length?`<tfoot><tr class="grandtot"><td colspan="6">합계 (${nf(st.cnt)}품목)</td>
         <td class="center" style="color:${st.qty_sum<0?'#c0392b':'#1c7c3a'}">${nf(st.qty_sum)}</td><td colspan="2"></td></tr></tfoot>`:''}
       </table></div>
      <div class="grid-wrap" style="flex:1 1 38%;max-height:calc(100vh - 260px);overflow:auto;background:#fff;border:1px solid var(--line-2,#c9d3e0);border-radius:8px">
       <div id="gs-hist-title" style="padding:6px 8px;font-size:12px;border-bottom:1px solid var(--line-2,#c9d3e0);background:#f7f9fc">조정이력 <span style="color:var(--muted)">— 좌측 품목을 선택하세요</span></div>
       <table class="tbl fit gs-tbl" style="font-size:11px"><thead><tr>
         <th>번호</th><th>조정일자</th><th>SEQ</th><th>구분</th><th>수량</th><th>등록자</th><th>출처</th></tr></thead>
       <tbody id="gs-hist-body">${histBody()}</tbody></table></div>
     </div>`;
    const g=id=>c.querySelector(id);
    const refilter=()=>{applyFilter();draw();};
    g('#gs-search').onclick=()=>{st.cust=g('#gs-cust').value;st.item=g('#gs-item').value.trim();load();};
    g('#gs-cust').onchange=()=>g('#gs-search').click();      // 거래처 = 서버 재조회
    g('#gs-item').oninput=()=>{st.item=g('#gs-item').value;refilter();
      const f=c.querySelector('#gs-item');if(f){f.focus();try{f.setSelectionRange(f.value.length,f.value.length);}catch(e){}}};
    g('#gs-item').onkeyup=e=>{if(e.key==='Enter')g('#gs-search').click();};
    c.querySelectorAll('input[name=gs-gb]').forEach(rd=>rd.onchange=()=>{st.gubun=rd.value;refilter();});
    g('#gs-zero').onchange=()=>{st.zero=g('#gs-zero').checked?'숨김':'전체';refilter();};
    c.querySelectorAll('.gs-row').forEach((el,i)=>el.onclick=()=>loadHist(st.rows[i]));
    g('#gs-adj').onclick=()=>openSetAdjModal(st,()=>load());
  };
  draw();
  loadOpts().then(draw);
};

/* 세트재고 조정 팝업 (w_pu_stock_285) — 가공세트재고조정
   ★레거시 규칙: 조정구분 3(장부수정) + 재설정 체크 → 등록수량 = 입력수량 − 현재고 (결과가 입력값이 되도록)
     그 외에는 입력수량을 그대로 가감. */
function openSetAdjModal(st,onSaved){
  const API=API_BASE;
  const nf=n=>Number(n||0).toLocaleString('ko-KR',{maximumFractionDigits:2});
  const iso=x=>`${x.getFullYear()}-${String(x.getMonth()+1).padStart(2,'0')}-${String(x.getDate()).padStart(2,'0')}`;
  const ov=document.createElement('div');
  ov.style.cssText='position:fixed;inset:0;background:rgba(0,0,0,.35);z-index:9999;display:flex;align-items:center;justify-content:center';
  const rows=[];
  if(st.sel)rows.push({item:st.sel.item,qty:'',remarks:'',cur:st.sel.qty});   // 선택행이 있으면 첫 줄 채움
  while(rows.length<6)rows.push({item:'',qty:'',remarks:'',cur:null});
  const state={ymd:iso(new Date()),cust:st.cust||(st.sel?st.sel.cust:''),tag:'3',reset:true,rows};
  const render=()=>{
    ov.innerHTML=`<div style="background:#fff;border-radius:10px;width:820px;max-width:96vw;max-height:86vh;display:flex;flex-direction:column;box-shadow:0 10px 40px rgba(0,0,0,.3);font-size:12px">
      <style>
        .gsa-tbl .inp{min-width:0!important;width:100%!important;height:26px;padding:0 4px;font-size:12px}
        .gsa-tbl td,.gsa-tbl th{padding:2px 3px;text-align:center!important}
      </style>
      <div style="display:flex;justify-content:space-between;align-items:center;padding:8px 12px;border-bottom:1px solid #e5e9f0">
        <b style="font-size:14px">🔧 가공세트재고조정</b><span id="gsa-x" style="cursor:pointer;font-size:18px;color:#888">✕</span></div>
      <div style="padding:8px 12px;display:flex;flex-wrap:wrap;gap:6px;align-items:center;background:#f2f7ff">
        <label class="tl">조정일자</label><input class="inp" type="date" id="gsa-ymd" value="${state.ymd}" style="width:132px;min-width:0">
        <label class="tl">세트거래처</label><select class="inp" id="gsa-cust" style="width:190px;min-width:0"><option value="">선택</option>${st.optCusts.map(o=>`<option value="${esc(o.code)}"${state.cust===o.code?' selected':''}>${esc(o.nm)}(${esc(o.code)})</option>`).join('')}</select>
        <label class="tl">조정구분</label><select class="inp" id="gsa-tag" style="width:110px;min-width:0">${(st.optTags||[]).map(o=>`<option value="${esc(o.code)}"${state.tag===o.code?' selected':''}>${esc(o.nm)}</option>`).join('')}</select>
        <label class="rl" title="체크: 입력수량이 '조정 후 재고'가 되도록 차액만 등록(장부수정)&#10;해제: 입력수량을 그대로 가감"><input type="checkbox" id="gsa-reset"${state.reset?' checked':''}> 입력한 수량으로 맞춤</label>
        <div class="spacer"></div><button class="btn" id="gsa-add" style="padding:3px 10px">➕ 행추가</button>
      </div>
      <div id="gsa-msg" style="padding:0 12px;min-height:15px;font-size:12px"></div>
      <div style="flex:1;min-height:0;overflow-y:auto;overflow-x:hidden;padding:0 12px">
        <table class="tbl fit gsa-tbl" style="font-size:12px;width:100%;table-layout:fixed"><thead><tr>
          <th style="width:34px">SEQ</th><th style="width:170px">세트도번</th><th style="width:90px">현재고</th>
          <th style="width:90px">${state.reset?'조정 후 재고':'가감수량'}</th><th style="width:80px">변동</th><th>비고</th></tr></thead>
        <tbody>${state.rows.map((r,i)=>{
          const cur=(r.cur==null)?null:+r.cur;
          const inq=(r.qty===''||r.qty==null)?null:+r.qty;
          const diff=(inq==null)?null:(state.reset?(inq-(cur||0)):inq);
          return `<tr>
          <td class="center">${i+1}</td>
          <td><input class="inp gsa-f" data-i="${i}" data-k="item" value="${esc(r.item)}" style="text-align:center" placeholder="세트도번"></td>
          <td class="center" style="color:${cur==null?'#bbb':(cur<0?'#c0392b':'#1c7c3a')}">${cur==null?'·':nf(cur)}</td>
          <td><input class="inp gsa-f" data-i="${i}" data-k="qty" type="number" step="any" value="${r.qty}" style="text-align:center;background:#fffbe6;font-weight:700"></td>
          <td class="center" style="font-weight:700;color:${diff==null?'#bbb':(diff<0?'#c0392b':(diff>0?'#1c7c3a':'#999'))}">${diff==null?'·':(diff>0?'+':'')+nf(diff)}</td>
          <td><input class="inp gsa-f" data-i="${i}" data-k="remarks" value="${esc(r.remarks||'')}"></td></tr>`;}).join('')}</tbody></table>
      </div>
      <div style="display:flex;gap:8px;justify-content:flex-end;align-items:center;padding:8px 12px;border-top:1px solid #e5e9f0">
        <span style="margin-right:auto;font-size:11px;color:#666">※ 조정분은 nx 에 기록됩니다(라이브 재고는 레거시가 갱신).</span>
        <button class="btn" id="gsa-save" style="background:#1c47a0;color:#fff">✔ 저장(재고조정)</button>
        <button class="btn" id="gsa-close">닫기</button></div>
    </div>`;
    const q=s=>ov.querySelector(s);
    const msg=(t,ok)=>{q('#gsa-msg').innerHTML=t?`<span style="color:${ok?'#1c7c3a':'#c0392b'}">${esc(t)}</span>`:'';};
    q('#gsa-x').onclick=q('#gsa-close').onclick=()=>ov.remove();
    q('#gsa-ymd').onchange=e=>state.ymd=e.target.value;
    q('#gsa-cust').onchange=e=>{state.cust=e.target.value;state.rows.forEach(r=>r.cur=null);render();refreshCur();};
    q('#gsa-tag').onchange=e=>{state.tag=e.target.value;render();};
    q('#gsa-reset').onchange=e=>{state.reset=e.target.checked;render();};
    q('#gsa-add').onclick=()=>{for(let k=0;k<5;k++)state.rows.push({item:'',qty:'',remarks:'',cur:null});render();};
    ov.querySelectorAll('.gsa-f').forEach(el=>{
      el.onchange=()=>{const i=+el.dataset.i,k=el.dataset.k;state.rows[i][k]=el.value;
        if(k==='item'){state.rows[i].cur=null;render();refreshCur();}else render();};
    });
    q('#gsa-save').onclick=async()=>{
      if(!state.cust){msg('세트거래처를 선택하세요.',false);return;}
      const valid=state.rows.filter(r=>String(r.item||'').trim()&&r.qty!==''&&r.qty!=null);
      if(!valid.length){msg('세트도번과 수량을 입력하세요.',false);return;}
      q('#gsa-save').disabled=true;
      try{
        const res=await fetch(`${API}/api/gagongset/adjust`,{method:'POST',headers:{'Content-Type':'application/json'},
          body:JSON.stringify({ymd:state.ymd,cust:state.cust,maint_tag:state.tag,
            reset_flag:state.reset?'1':'0',user:'웹',
            rows:valid.map(r=>({item:String(r.item).trim(),qty:+r.qty,remarks:r.remarks||''}))})});
        if(!res.ok){let t='';try{t=(await res.json()).detail||'';}catch(e){t=await res.text();}
          msg('저장 실패: '+(t||res.status),false);return;}
        const d=await res.json();
        if(d.ok){msg(`✔ ${d.msg}`,true);setTimeout(()=>{ov.remove();if(typeof onSaved==='function')onSaved();},800);}
        else msg(d.msg||'저장 실패',false);
      }catch(e){msg('저장 실패: '+(e&&e.message||e),false);}
      finally{const b=q('#gsa-save');if(b)b.disabled=false;}
    };
  };
  // 입력한 세트도번의 현재고를 조회해 표시(레거시 ue_itemchanged 의 f_pu_get_set_mat_stock 대응)
  const refreshCur=async()=>{
    if(!state.cust)return;
    const items=[...new Set(state.rows.map(r=>String(r.item||'').trim()).filter(Boolean))];
    if(!items.length)return;
    try{
      const d=await(await fetch(`${API}/api/gagongset/list?cust=${encodeURIComponent(state.cust)}&zero=전체&limit=20000`)).json();
      const m=new Map((d.rows||[]).map(r=>[r.item,r.qty]));
      let hit=false;
      state.rows.forEach(r=>{const k=String(r.item||'').trim();
        if(k&&m.has(k)){r.cur=m.get(k);hit=true;}else if(k){r.cur=0;hit=true;}});
      if(hit)render();
    }catch(e){}
  };
  render(); document.body.appendChild(ov);
  if(state.cust)refreshCur();
}


/* ===== 가공: 4주간 가공계획현황(제번) (w_pr_outside_070 「가공자재계획현황」) =====
   ★2026-09-01 신설. 레거시는 산식 참고, 데이터는 nx 웹 정본(계획원본 → 모델BOM → 소요엔진).
   집계 = 제번·라인·ASM도번 그레인 / 상세 = 거기에 자도번(P2 자재) 한 단 더.
   일자칸 01~31 = 기준일 + 0~30. 백엔드 /api/gagong/matplan070. */
SCREEN.gagongmatplan070=(c)=>{
  const API=API_BASE;
  const nf=n=>Number(n||0).toLocaleString('ko-KR',{maximumFractionDigits:0});
  const nf3=n=>Number(n||0).toLocaleString('ko-KR',{maximumFractionDigits:3});
  const _DW=['일','월','화','수','목','금','토'];
  const dcol=s=>{s=''+(s||'');if(s.length!==6)return s;
    const d=new Date(2000+ +s.slice(0,2), +s.slice(2,4)-1, +s.slice(4,6));
    return `${+s.slice(4,6)}(${_DW[d.getDay()]})`;};
  const dow=s=>{s=''+(s||'');if(s.length!==6)return -1;
    return new Date(2000+ +s.slice(0,2), +s.slice(2,4)-1, +s.slice(4,6)).getDay();};
  const ymd2date=s=>(s&&(''+s).length===6)?`20${(''+s).slice(0,2)}-${(''+s).slice(2,4)}-${(''+s).slice(4,6)}`:'';
  const date2ymd=s=>(s||'').replace(/-/g,'').slice(2);

  const st={ymd:date2ymd(planBaseIso()),mode:'sum',wc:'P2',line:'',wo:'',asm:'',item:'',
            dates:[],rows:[],cnt:0,qty:0,loading:false,msg:''};

  /* ★컬럼 정의 — 항목보기(숨김·순서)를 쓰려면 <th>·<td> 를 하드코딩하지 않고
       정의에서 만들어야 한다(2026-09-06, 410·420·580 과 같은 구조).
       ★이 화면은 보기(집계/상세)에 따라 컬럼이 달라진다 —
         집계 = LOT수량 / 상세 = 자도번·사용수. 그래서 정의에 only 를 둬서
         현재 모드에 없는 컬럼은 아예 후보에서 뺀다(순서 저장에는 남겨둔다). */
  const M7DEF={
    seq:{t:'SEQ',cls:'num', h:(r,i)=>`<td class="num">${i+1}</td>`, x:{w:40,al:'center',v:(r,i)=>i+1}},
    wcnm:{t:'작업처',       h:r=>`<td class="center">${esc(r.wcnm||r.wc)}</td>`, x:{w:62,al:'center',v:r=>r.wcnm||r.wc||''}},
    line:{t:'라인',         h:r=>`<td class="center">${esc(r.line)}</td>`,       x:{w:48,al:'center',v:r=>r.line||''}},
    wo:{t:'제번',           h:r=>`<td>${esc(r.wo)}</td>`,                        x:{w:88,al:'center',v:r=>r.wo||''}},
    model:{t:'모델',        h:r=>`<td class="bcap" title="${esc(r.model)}" style="max-width:170px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(r.model)}</td>`,
      x:{w:170,al:'left',v:r=>r.model||''}},
    asm:{t:'ASM도번',       h:r=>`<td><b>${esc(r.asm)}</b></td>`,                x:{w:110,al:'center',v:r=>r.asm||''}},
    mat:{t:'자도번',only:'dtl', h:r=>`<td>${esc(r.mat)}</td>`,                   x:{w:110,al:'center',v:r=>r.mat||''}},
    use:{t:'사용수',cls:'num',only:'dtl', h:r=>`<td class="num">${nf3(r.use)}</td>`, x:{w:62,al:'right',v:r=>+r.use||0}},
    lot:{t:'LOT수량',cls:'num',only:'sum', h:r=>`<td class="num">${nf(r.lot)}</td>`, x:{w:62,al:'right',v:r=>+r.lot||0}},
    qty:{t:'계획수량',cls:'num', h:r=>`<td class="num"><b>${nf(r.qty)}</b></td>`, x:{w:66,al:'right',v:r=>+r.qty||0}},
  };
  const M7_DEF=['seq','wcnm','line','wo','model','asm','mat','use','lot','qty'];
  const M7_LS='m7_colorder', M7_HIDE='m7_hidecols';
  /* ★가변 배열 — 항목보기 적용 시 제자리에서 고쳐야 draw() 한 번으로 새 순서가 보인다. */
  const M7_ORD=(()=>{try{const v=JSON.parse(localStorage.getItem(M7_LS)||'null');
    if(Array.isArray(v)&&v.length){const o=v.filter(k=>M7DEF[k]);
      M7_DEF.forEach(k=>{if(!o.includes(k))o.push(k);});return o;}}catch(_){}
    return M7_DEF.slice();})();
  const m7LoadHide=()=>{try{const v=JSON.parse(localStorage.getItem(M7_HIDE)||'[]');
    return new Set(Array.isArray(v)?v:[]);}catch(_){return new Set();}};
  let m7Hid=m7LoadHide();
  // 현재 보기(집계/상세)에 해당하는 컬럼만 — only 가 다른 모드면 제외
  const m7Avail=()=>M7_ORD.filter(k=>!M7DEF[k].only||M7DEF[k].only===st.mode);
  const m7Vis=()=>m7Avail().filter(k=>!m7Hid.has(k));
  const m7Th=()=>m7Vis().map(k=>`<th class="${M7DEF[k].cls||''}" data-tk="${k}" title="우클릭 = 항목보기(순서·숨김)">${M7DEF[k].t}</th>`).join('');
  const m7Td=(r,i)=>m7Vis().map(k=>M7DEF[k].h(r,i)).join('');
  /* ══ 점진 렌더 상태 ═══════════════════════════════════════════════════════
       m7Rest = {from, mk} — 아직 안 붙인 행의 시작 인덱스와 행 생성 함수.
       ★HTML 문자열을 미리 다 만들어 두지 않는다 — 3,240행분 문자열 생성 자체가
         무거워서 "미리 만들고 나눠 붙이기"는 최초 렌더 지연을 못 줄인다. */
  const M7_PAGE=300;
  let m7Rest=null;
  const m7Append=()=>{
    if(!m7Rest)return;
    const tb=c.querySelector('.m7tbl tbody'); if(!tb){m7Rest=null;return;}
    const to=Math.min(m7Rest.from+M7_PAGE, st.rows.length);
    const buf=[]; for(let i=m7Rest.from;i<to;i++)buf.push(m7Rest.mk(st.rows[i],i));
    tb.insertAdjacentHTML('beforeend',buf.join(''));
    m7Rest = (to<st.rows.length) ? {from:to, mk:m7Rest.mk} : null;
    const el=c.querySelector('#m7-cnt');
    if(el&&!el.dataset.busy)el.innerHTML=`행 <b>${nf(st.cnt)}</b>`
      +(m7Rest?` <span style="color:#7b8aa0">(${nf(to)}행 표시 · 스크롤하면 더)</span>`:'')
      +` · 수량합 <b>${nf(st.qty)}</b> · 일자 ${st.dates.length}개`;};
  const m7WireLazy=()=>{
    const w=c.querySelector('.mp7-grid');
    if(!w||w.dataset.lazy)return;
    w.dataset.lazy='1';
    w.addEventListener('scroll',()=>{
      if(m7Rest&&w.scrollTop+w.clientHeight>=w.scrollHeight-400)m7Append();
    },{passive:true});};

  const load=async()=>{st.loading=true;draw();
    const qs=new URLSearchParams({ymd:st.ymd,mode:st.mode,wc:st.wc,line:st.line,
                                 wo:st.wo,asm:st.asm,item:st.item,limit:20000});
    try{const d=await(await fetch(`${API}/api/gagong/matplan070?${qs}`)).json();
      st.dates=d.dates||[];st.rows=d.rows||[];st.cnt=d.cnt||0;st.qty=d.qty||0;st.msg='';}
    catch(e){st.msg='백엔드 연결 실패';st.dates=[];st.rows=[];st.cnt=0;st.qty=0;}
    st.loading=false;draw();};

  const draw=()=>{
    const dates=st.dates, DTL=(st.mode==='dtl');
    // 오토컴플리트 후보(조회결과에서 추출)
    const lnS=new Set(),woS=new Set(),asS=new Set(),mtS=new Set();
    st.rows.forEach(r=>{if(r.line)lnS.add(r.line);if(r.wo)woS.add(r.wo);
      if(r.asm)asS.add(r.asm);if(r.mat)mtS.add(r.mat);});
    const opt=s=>[...s].sort().slice(0,500).map(v=>`<option value="${esc(v)}"></option>`).join('');
    // 합계
    let tLot=0,tQty=0;const dSum=dates.map(()=>0);
    st.rows.forEach(r=>{tLot+=+r.lot||0;tQty+=+r.qty||0;
      (r.d||[]).forEach((v,i)=>{dSum[i]+=+v||0;});});
    // ★colspan 은 실제 보이는 컬럼 수로 — 고정값을 쓰면 항목 숨김 시 어긋난다.
    const NC=m7Vis().length;
    const hbg=i=>{const w=dow(dates[i]);return w===0?'background:#ffe3e3':(w===6?'background:#e3ecff':'');};
    const cell=(v,i)=>v?`<td class="num"${dow(dates[i])===0?' style="background:#fff5f5"':(dow(dates[i])===6?' style="background:#f5f8ff"':'')}>${nf(v)}</td>`
                       :`<td class="num" style="color:#dfe6ef${dow(dates[i])===0?';background:#fff5f5':(dow(dates[i])===6?';background:#f5f8ff':'')}">·</td>`;
    /* ══ 점진 렌더 (2026-09-06 — "계획 조회하니 버벅거린다") ══════════════════
         3,240행 × 40컬럼 = 약 13만 셀. 한 번에 그리면 최초 렌더·스크롤이 다 멈춘다.
         처음 M7_PAGE 행만 DOM 에 올리고 스크롤 끝에서 이어붙인다(410·키팅과 같은 방식).
         ★일자칸 셀 문자열은 미리 만들지 않는다 — 그 자체가 무거워 의미가 없다.
           대신 행 HTML 생성을 **필요한 만큼만** 하도록 함수로 미룬다. */
    const mkRow=(r,i)=>`<tr>${m7Td(r,i)}${(r.d||[]).map((v,j)=>cell(v,j)).join('')}</tr>`;
    const _head=[]; for(let i=0;i<Math.min(st.rows.length,M7_PAGE);i++)_head.push(mkRow(st.rows[i],i));
    m7Rest=(st.rows.length>M7_PAGE)?{from:M7_PAGE,mk:mkRow}:null;

    c.innerHTML=`
     <style>
      /* §3 페이지 본문 세로스크롤 금지 — 루트 flex, 표만 내부 스크롤 */
      .mp7-root{display:flex;flex-direction:column;height:100%}
      .mp7-root .toolbar{flex-wrap:nowrap;overflow-x:auto}
      .mp7-grid{flex:0 1 auto;max-height:100%;min-height:0;overflow:auto;background:#fff;
                border:1px solid var(--line-2,#c9d3e0);border-radius:8px}
      .mp7-grid thead th{position:sticky;top:0;z-index:2;background:#eef3fa;text-align:center}
      .mp7-grid tfoot td{position:sticky;bottom:0;z-index:2;background:#f4f7fb;font-weight:600}
     </style>
     <div class="mp7-root">
      <div class="page-title" style="flex:0 0 auto">4주간 가공계획현황(제번)
        <span style="font-size:12px;color:var(--muted);font-weight:400">제번×라인×ASM도번 · 기준일부터 31일</span></div>
      <div class="page-sub" style="flex:0 0 auto">생산계획(<code>nx.plan_dtl</code>) → 모델BOM → <b>통일 소요엔진</b> 전개로 가공(${esc(st.wc)}) 자재 소요를 낸다.
        수량 = ceiling(계획수량 × 모델BOM사용수 × 생산율) × BOM누적사용수. 모델BOM 유효기간·BOM 전개제외(except) 반영 = 웹 편성(파트별계획)과 같은 기준.</div>
      <!-- ★조건이 한 줄에 다 안 들어가 잘리므로 2줄로 나눈다(2026-09-06 요청).
             §3 "툴바는 한 줄 유지"는 각 줄에 적용 — 줄마다 nowrap 이다. -->
      <div class="toolbar" style="flex:0 0 auto">
        <label class="tl">기준일자</label><input class="inp" type="date" id="m7-ymd" value="${ymd2date(st.ymd)}" style="width:140px">
        <label class="tl">작업처</label><select class="inp" id="m7-wc" style="width:96px">
          <option value="P2"${st.wc==='P2'?' selected':''}>P2 가공</option>
          <option value="P1"${st.wc==='P1'?' selected':''}>P1 용접</option></select>
        <label class="tl">보기</label><select class="inp" id="m7-mode" style="width:88px">
          <option value="sum"${!DTL?' selected':''}>집계</option>
          <option value="dtl"${DTL?' selected':''}>상세</option></select>
        <label class="tl">라인</label><input class="inp" id="m7-line" list="m7-linel" value="${esc(st.line)}" style="width:70px" autocomplete="off"><datalist id="m7-linel">${opt(lnS)}</datalist>
        <button class="btn" id="m7-search">조회</button>
        <div class="spacer"></div>
        <span class="rowcount" id="m7-cnt">행 <b>${nf(st.cnt)}</b>${st.rows.length>M7_PAGE?` <span style="color:#7b8aa0">(${nf(M7_PAGE)}행 표시 · 스크롤하면 더)</span>`:''} · 수량합 <b>${nf(st.qty)}</b> · 일자 ${dates.length}개</span>
      </div>
      <div class="toolbar" style="flex:0 0 auto;margin-top:2px">
        <label class="tl">제번</label><input class="inp" id="m7-wo" list="m7-wol" value="${esc(st.wo)}" style="width:110px" autocomplete="off"><datalist id="m7-wol">${opt(woS)}</datalist>
        <label class="tl">ASM도번</label><input class="inp" id="m7-asm" list="m7-asml" value="${esc(st.asm)}" style="width:130px" autocomplete="off"><datalist id="m7-asml">${opt(asS)}</datalist>
        <label class="tl">자도번</label><input class="inp" id="m7-item" list="m7-iteml" value="${esc(st.item)}" style="width:130px" autocomplete="off"><datalist id="m7-iteml">${opt(mtS)}</datalist>
        <!-- ★보기설정 버튼은 조회조건과 섞이지 않게 오른쪽 끝에(2026-09-06 요청 "여기에는 왜 있지").
               조회조건 = 왼쪽 / 결과에 대한 조작(항목보기·엑셀) = 오른쪽. -->
        <div class="spacer"></div>
        <button class="btn" id="m7-col" title="컬럼 숨김·순서 (헤더 우클릭으로도 열림)">항목보기</button>
        <button class="btn xls" id="m7-xls" title="조회 결과를 화면과 같은 서식으로 엑셀 저장">엑셀</button>
      </div>
      ${st.msg?`<div class="page-sub" style="color:#c0392b;flex:0 0 auto">${esc(st.msg)}</div>`:''}
      <div class="mp7-grid">
       <table class="tbl fit m7tbl" style="font-size:11px;user-select:none"><thead><tr>
        ${m7Th()}
        ${dates.map((d,i)=>`<th class="num" style="${hbg(i)}">${dcol(d)}</th>`).join('')}</tr></thead>
       <tbody>${st.loading?spinRow(NC+dates.length):(st.rows.length?_head.join('')
        :`<tr><td colspan="${NC+dates.length}" class="empty">조회 결과 없음</td></tr>`)}</tbody>
       ${(()=>{if(!st.rows.length)return '';
         /* ★합계행도 정의 기반으로 — 종전엔 colspan="6" + 위치 하드코딩이라
              컬럼을 숨기거나 옮기면 합계가 엉뚱한 칸에 붙었다. */
         const TOT={lot:tLot,qty:tQty}, vs=m7Vis();
         let lead=0; while(lead<vs.length && TOT[vs[lead]]===undefined) lead++;
         return `<tfoot><tr class="grandtot">${lead?`<td colspan="${lead}">합계 (${nf(st.cnt)}행)</td>`:''}
         ${vs.slice(lead).map(k=>`<td class="num">${TOT[k]===undefined?'':nf(TOT[k])}</td>`).join('')}
         ${dSum.map(v=>`<td class="num">${nf(v)}</td>`).join('')}</tr></tfoot>`;})()}
       </table></div>
     </div>`;

    m7WireLazy();   // ★점진 렌더 — 스크롤 끝에서 이어붙이기
    const g=id=>c.querySelector(id);
    const apply=()=>{st.ymd=date2ymd(g('#m7-ymd').value)||st.ymd;st.wc=g('#m7-wc').value;
      st.mode=g('#m7-mode').value;st.line=g('#m7-line').value.trim();st.wo=g('#m7-wo').value.trim();
      st.asm=g('#m7-asm').value.trim();st.item=g('#m7-item').value.trim();load();};
    g('#m7-search').onclick=apply;
    ['#m7-wc','#m7-mode'].forEach(id=>g(id).onchange=apply);
    ['#m7-line','#m7-wo','#m7-asm','#m7-item'].forEach(id=>g(id).onkeyup=e=>{if(e.key==='Enter')apply();});
    /* ══ 엑셀 (화면 서식 그대로) ══════════════════════════════════════════
         ★진짜 xlsx 로 내보낸다(core.js downloadXLS). HTML→.xls 는 엑셀이 서식을 버린다.
         ★항목보기의 숨김·순서를 그대로 따른다 — "보이는 대로" 받는 것이 기대 동작이다.
         ★주말 일자칸은 화면처럼 음영(일=#ffe3e3 / 토=#e3ecff, 본문은 연하게). */
    const exportXls=()=>{
      if(!st.rows.length){alert('조회 결과가 없습니다.');return;}
      const vs=m7Vis(), HB='#ffffff';
      const hb=i=>{const w=dow(dates[i]);return w===0?'#ffe3e3':(w===6?'#e3ecff':HB);};
      const cbg=i=>{const w=dow(dates[i]);return w===0?'#fff5f5':(w===6?'#f5f8ff':'');};
      const cols=vs.map(k=>({h:M7DEF[k].t,w:M7DEF[k].x.w,bg:HB}))
        .concat(dates.map((d,i)=>({h:dcol(d),w:52,bg:hb(i)})));
      const rows=st.rows.map((r,i)=>{
        const out=vs.map(k=>({v:M7DEF[k].x.v(r,i), al:M7DEF[k].x.al}));
        (r.d||[]).forEach((v,j)=>{out.push({v:(+v||0)||'', al:'right', bg:cbg(j)});});
        return out;});
      downloadXLS(`가공계획현황_${st.ymd}_${DTL?'상세':'집계'}`, cols, rows,
                  {sheet:`가공계획_${st.wc||''}_${DTL?'상세':'집계'}`});};
    g('#m7-xls').onclick=exportXls;
    {const cbn=g('#m7-col');
     if(cbn)cbn.onclick=e=>{e.preventDefault();e.stopPropagation();
       try{openColPick();}
       catch(err){console.error('[070 항목보기]',err);
                  alert('항목보기를 열지 못했습니다: '+(err&&err.message||err));}};}

    /* ══ 드래그 복사 (410·420·580 과 같은 동작) ═══════════════════════════
         표를 끌어 사각영역을 고르고 Ctrl+C 로 클립보드에 넣는다(엑셀에 TSV 로 붙는다).
         ★HTML 텍스트 선택과 부딪히므로 mousedown 에서 preventDefault +
           표에 user-select:none — 안 그러면 파란 블록만 생기고 영역이 안 잡힌다. */
    const tbl=c.querySelector('.m7tbl');
    const tb=tbl&&tbl.tBodies[0];
    if(!document.getElementById('m7cp-css')){
      const stl=document.createElement('style'); stl.id='m7cp-css';
      stl.textContent='.m7tbl td.m7cp{outline:1px solid #93b4e6;outline-offset:-1px;'
        +'background-image:linear-gradient(rgba(219,234,254,.55),rgba(219,234,254,.55))}';
      document.head.appendChild(stl);
    }
    if(tb){
      const rcOf=td=>({r:td.parentElement.rowIndex, c:td.cellIndex});
      let cdrag=false,_ca=null,_cells=null,_clast=null;
      const cpClear=()=>tb.querySelectorAll('td.m7cp').forEach(td=>td.classList.remove('m7cp'));
      const cpSnap=()=>{_cells=[...tb.querySelectorAll('td')].map(x=>{const q=rcOf(x);return {td:x,r:q.r,c:q.c};});};
      const cpRect=td=>{if(!_ca||!_cells)return;
        const b=rcOf(td);
        const r1=Math.min(_ca.r,b.r),r2=Math.max(_ca.r,b.r);
        const c1=Math.min(_ca.c,b.c),c2=Math.max(_ca.c,b.c);
        for(const it of _cells) it.td.classList.toggle('m7cp', it.r>=r1&&it.r<=r2&&it.c>=c1&&it.c<=c2);
        const n=tb.querySelectorAll('td.m7cp').length;
        const el=c.querySelector('#m7-cnt');
        // ★busy — 점진렌더의 스크롤 append 가 이 메시지를 덮어쓰지 않게
        if(el&&n){el.dataset.busy='1';
          el.innerHTML=`복사선택 <b>${nf(n)}</b>칸 <span style="color:#7b8aa0">(Ctrl+C)</span>`;}
        else if(el)delete el.dataset.busy;};
      tb.addEventListener('mousedown',e=>{
        if(e.button!==0)return;
        const start=e.target.closest('td'); if(!start||!start.closest('tr'))return;
        e.preventDefault();
        if(!e.ctrlKey&&!e.metaKey)cpClear();
        cdrag=true;cpSnap();_ca=rcOf(start);_clast=start;cpRect(start);});
      tb.addEventListener('mousemove',e=>{if(!cdrag)return;
        if(!(e.buttons&1)){cdrag=false;_ca=null;_cells=null;_clast=null;return;}
        const el=document.elementFromPoint(e.clientX,e.clientY);
        const td=(el&&el.closest('td'))||_clast;
        if(td){_clast=td;cpRect(td);}});
      document.addEventListener('mouseup',()=>{cdrag=false;_ca=null;_cells=null;_clast=null;});
    }
    const selText=()=>{
      const map=new Map();
      c.querySelectorAll('td.m7cp').forEach(td=>{
        const tr=td.parentElement; if(!tr)return;
        if(!map.has(tr.rowIndex))map.set(tr.rowIndex,[]);
        map.get(tr.rowIndex).push([td.cellIndex,(td.innerText||'').trim()]);});
      return [...map.keys()].sort((x,y)=>x-y)
        .map(r=>map.get(r).sort((x,y)=>x[0]-y[0]).map(x=>x[1]).join('\t')).join('\n');
    };
    const toClip=(txt,what)=>{
      if(!txt){alert('복사할 영역을 먼저 끌어서 선택하세요.');return;}
      const done=()=>{const el=c.querySelector('#m7-cnt');
        if(el){const o=el.innerHTML;el.dataset.busy='1';
               el.innerHTML=`<b style="color:#1c7c3a">${what} 복사됨</b>`;
               setTimeout(()=>{el.innerHTML=o;delete el.dataset.busy;},1400);}};
      // ★비보안(http 운영 184)은 clipboard API 가 막히고 그 거부는 **비동기** —
      //   제스처(Ctrl+C) 밖에서 fb 가 돌면 execCommand 도 막혀 조용히 실패한다.
      //   ⟹ isSecureContext 가 아니면 처음부터 동기 fb()(2026-09-08).
      if(window.isSecureContext&&navigator.clipboard&&navigator.clipboard.writeText)
        navigator.clipboard.writeText(txt).then(done,()=>fb()); else fb();
      function fb(){   // 비보안 컨텍스트(http)는 clipboard API 가 막힌다
        const ta=document.createElement('textarea'); ta.value=txt;
        ta.style.cssText='position:fixed;left:-9999px;top:0';
        document.body.appendChild(ta); ta.focus(); ta.select();
        let ok=false; try{ok=document.execCommand('copy');}catch(_){}
        ta.remove();
        if(ok)done(); else alert('복사에 실패했습니다.');}
    };
    const copySel=()=>toClip(selText(),'선택영역');
    /* ★전체 복사는 DOM 이 아니라 st.rows 에서 만든다 — 점진 렌더 때문에 화면에는
         일부 행만 붙어 있어 DOM 을 훑으면 "보이는 데까지만" 복사된다(410 과 같은 이유). */
    const copyAll=()=>{
      if(!st.rows.length){alert('조회 결과가 없습니다.');return;}
      const vs=m7Vis(), out=[];
      out.push(vs.map(k=>M7DEF[k].t).concat(dates.map(d=>dcol(d))).join('\t'));
      st.rows.forEach((r,i)=>{
        const line=vs.map(k=>{const v=M7DEF[k].x.v(r,i);return (v===''||v==null)?'':String(v);});
        (r.d||[]).forEach(v=>line.push((+v||0)?String(+v):''));
        out.push(line.join('\t'));});
      toClip(out.join('\n'),`전체 ${nf(st.rows.length)}행`);
    };
    // ★Ctrl+C 는 document 에서 받는다 — 범위선택 mousedown 의 preventDefault 때문에
    //   c 에 포커스가 오지 않아 c.onkeydown 은 아예 안 불린다(2026-09-08, 420 과 동일 수정).
    c._m7CopySel=copySel;
    if(!c.dataset.cpkey){
      c.dataset.cpkey='1';
      c.setAttribute('tabindex','-1'); c.style.outline='none';
      document.addEventListener('keydown',ev=>{
        if(!((ev.ctrlKey||ev.metaKey)&&(ev.key==='c'||ev.key==='C')))return;
        if(!c.isConnected||!c.offsetParent)return;
        const t=ev.target;
        if(t&&(t.tagName==='INPUT'||t.tagName==='TEXTAREA'||t.tagName==='SELECT'||t.isContentEditable))return;
        if(!c.querySelector('td.m7cp'))return;
        ev.preventDefault(); if(c._m7CopySel)c._m7CopySel();});
    }
    /* 우클릭 메뉴 — ★실행도 mousedown 에서(410·420·580 과 같은 함정 회피:
       바깥클릭 닫기가 mousedown 이라 click 은 죽은 노드에 떨어진다). */
    c.querySelectorAll('.m7tbl thead th,.m7tbl tbody').forEach(el=>{
      el.oncontextmenu=e=>{
        e.preventDefault();
        const o2=document.getElementById('m7-ctx'); if(o2)o2.remove();
        const m=document.createElement('div'); m.id='m7-ctx';
        m.style.cssText=`position:fixed;left:${Math.min(e.clientX,innerWidth-170)}px;
          top:${Math.min(e.clientY,innerHeight-110)}px;z-index:1400;background:#fff;
          border:1px solid #cfd8e6;border-radius:6px;box-shadow:0 6px 20px rgba(20,40,80,.22);
          font-size:12.5px;min-width:150px;overflow:hidden`;
        m.innerHTML=['항목보기','선택영역 복사','전체 복사']
          .map((t,i)=>`<div data-i="${i}" style="padding:7px 12px;cursor:pointer">${t}</div>`).join('');
        document.body.appendChild(m);
        m.querySelectorAll('div[data-i]').forEach(d=>{
          d.onmouseenter=()=>d.style.background='#eef4ff';
          d.onmouseleave=()=>d.style.background='';});
        const kill=()=>{m.remove();document.removeEventListener('mousedown',outside,true);};
        const outside=ev2=>{if(!m.contains(ev2.target))kill();};
        setTimeout(()=>document.addEventListener('mousedown',outside,true),0);
        m.addEventListener('mousedown',ev2=>{
          ev2.preventDefault(); ev2.stopPropagation();
          const t=ev2.target.closest&&ev2.target.closest('[data-i]'); if(!t)return;
          const i=+t.dataset.i; kill();
          try{ if(i===0)openColPick(); else if(i===1)copySel(); else copyAll(); }
          catch(err){console.error('[070 메뉴]',err);alert('실행 실패: '+(err&&err.message||err));}});
      };
    });

    /* 헤더 더블클릭 정렬 — ★보이는 컬럼 순서를 따른다(항목보기로 순서가 바뀌므로
       고정 배열을 쓰면 엉뚱한 컬럼으로 정렬된다). SEQ 는 정렬 대상 아님. */
    const keys=m7Vis().map(k=>k==='seq'?'':k);
    enableSort(c,keys,()=>st.rows,()=>draw());
  };

  /* == 항목보기 (2026-09-06 — 410·420·580 과 같은 방식) ====================
       체크 해제 = 그 컬럼 숨김 · 행을 끌거나 ▲▼ 로 순서 변경.
       ★이 화면은 일자칸이 맨 뒤라 그룹이 하나다(앞쪽 컬럼만 다룬다).
       ★보기(집계/상세)에 없는 컬럼은 목록에 안 띄운다 — 순서 저장에는 그대로 남는다. */
  const openColPick=()=>{
    const old=document.getElementById('m7-colpick'); if(old)old.remove();
    const hid=m7LoadHide(), avail=m7Avail();
    const ov=document.createElement('div');
    ov.id='m7-colpick';
    ov.style.cssText='position:fixed;inset:0;z-index:1300;background:rgba(20,32,54,.34);'
                    +'display:flex;align-items:center;justify-content:center';
    const item=k=>`<div class="m7cp-r" data-k="${k}"
         style="display:flex;align-items:center;gap:7px;padding:4px 8px;border-bottom:1px solid #eef1f6;
                cursor:grab;user-select:none;-webkit-user-select:none">
        <span style="color:#b6c2d4;font-size:11px" title="끌어서 순서 변경">⠿</span>
        <input type="checkbox" ${hid.has(k)?'':'checked'} data-ck="${k}">
        <span style="flex:1;font-size:12.5px">${M7DEF[k].t}</span>
        <button class="btn ghost m7cp-up" data-k="${k}" style="padding:0 6px;font-size:11px">▲</button>
        <button class="btn ghost m7cp-dn" data-k="${k}" style="padding:0 6px;font-size:11px">▼</button>
      </div>`;
    ov.innerHTML=`<div style="background:#fff;border-radius:10px;width:420px;max-height:78vh;
           display:flex;flex-direction:column;box-shadow:0 8px 30px rgba(20,40,80,.28)">
        <div style="padding:10px 12px;border-bottom:1px solid #e3e9f2;font-weight:700;color:#16305c">
          항목보기 <span style="font-weight:400;font-size:11px;color:#7b8aa0">체크 해제 = 숨김 · 행을 끌거나 ▲▼ 로 순서 변경</span></div>
        <div style="flex:1;overflow:auto;padding:4px 0">
          <div id="m7cp-l">${avail.map(item).join('')}</div>
          <div style="padding:6px 10px;font-size:11px;color:#7b8aa0">
            일자 컬럼은 항상 맨 뒤에 붙습니다. 목록은 현재 보기(${st.mode==='dtl'?'상세':'집계'}) 기준입니다.</div>
        </div>
        <div style="padding:9px 12px;border-top:1px solid #e3e9f2;display:flex;gap:6px;justify-content:flex-end">
          <button class="btn ghost" id="m7cp-reset">초기화</button>
          <div style="flex:1"></div>
          <button class="btn ghost" id="m7cp-x">닫기</button>
          <button class="btn" id="m7cp-ok" style="background:#1c47a0;color:#fff">적용</button>
        </div></div>`;
    document.body.appendChild(ov);
    const q=sel=>ov.querySelector(sel);
    /* ★모달 mousedown 은 **버블 단계에서만** 막는다(캡처 아님) — 캡처로 끊으면
         아래 행 드래그 핸들러까지 못 받는다(420 에서 실측한 원인). */
    ov.addEventListener('mousedown',e=>e.stopPropagation());
    ov.onclick=e=>{if(e.target===ov)ov.remove();};
    q('#m7cp-x').onclick=()=>ov.remove();
    const move=(k,dir)=>{const row=ov.querySelector(`.m7cp-r[data-k="${k}"]`); if(!row)return;
      const box=row.parentElement;
      const sib=dir<0?row.previousElementSibling:row.nextElementSibling;
      if(!sib)return;
      if(dir<0)box.insertBefore(row,sib); else box.insertBefore(sib,row);};
    ov.querySelectorAll('.m7cp-up').forEach(b=>b.onclick=()=>move(b.dataset.k,-1));
    ov.querySelectorAll('.m7cp-dn').forEach(b=>b.onclick=()=>move(b.dataset.k, 1));
    /* 행 끌어서 순서 변경 — ★HTML5 draggable 은 쓰지 않는다(텍스트 선택이 먼저 잡혀
         파란 블록만 생기고 드래그가 시작되지 않는다). 5px 이상 움직여야 '이동'이라
         같은 행에서 "클릭=체크토글 / 끌면=이동"이 공존한다. */
    let dK=null,dY=0,dMoved=false;
    const rowsOf=()=>[...ov.querySelectorAll('.m7cp-r')];
    const rowAtY=y=>{const rs=rowsOf(); if(!rs.length)return null;
      let best=rs[0],bd=1e9;
      for(const r of rs){const b=r.getBoundingClientRect();
        const d=(y<b.top)?(b.top-y):((y>b.bottom)?(y-b.bottom):0);
        if(d<bd){bd=d;best=r;}}
      return best;};
    ov.addEventListener('mousedown',e=>{
      const row=e.target.closest&&e.target.closest('.m7cp-r'); if(!row)return;
      if(e.target.tagName==='INPUT')return;
      if(e.target.closest('.m7cp-up,.m7cp-dn'))return;
      e.preventDefault();
      dK=row.dataset.k; dY=e.clientY; dMoved=false;
      row.style.opacity='.55';});
    const onMove=e=>{
      if(!dK)return;
      if(!ov.isConnected){dK=null;document.removeEventListener('mousemove',onMove);return;}
      if(!dMoved&&Math.abs(e.clientY-dY)<5)return;
      dMoved=true;
      const over=rowAtY(e.clientY);
      rowsOf().forEach(x=>{if(x!==over)x.style.borderTop='';});
      if(over&&over.dataset.k!==dK)over.style.borderTop='2px solid #2563eb';};
    const onUp=e=>{
      if(!dK)return;
      if(!ov.isConnected){dK=null;document.removeEventListener('mouseup',onUp);return;}
      const k=dK; dK=null;
      rowsOf().forEach(x=>{x.style.opacity='';x.style.borderTop='';});
      if(!dMoved)return;
      const over=rowAtY(e.clientY);
      if(!over||over.dataset.k===k)return;
      const src=rowsOf().find(r=>r.dataset.k===k); if(!src)return;
      const box=over.parentElement, sb=over.getBoundingClientRect();
      if(e.clientY < sb.top+sb.height/2) box.insertBefore(src,over);
      else box.insertBefore(src,over.nextSibling);};
    document.addEventListener('mousemove',onMove);
    document.addEventListener('mouseup',onUp);
    q('#m7cp-reset').onclick=()=>{
      try{localStorage.removeItem(M7_LS);localStorage.removeItem(M7_HIDE);}catch(_){}
      M7_ORD.length=0; M7_DEF.forEach(k=>M7_ORD.push(k));
      m7Hid=new Set();
      ov.remove(); draw();};
    q('#m7cp-ok').onclick=()=>{
      /* ★현재 보기에 없는 컬럼(예: 집계일 때 자도번·사용수)은 목록에 없다 —
           그대로 두면 순서에서 사라지므로, 보이던 것만 새 순서로 갈아끼우고
           나머지는 원래 자리(상대순서)를 지킨다. */
      const shown=[...ov.querySelectorAll('#m7cp-l .m7cp-r')].map(r=>r.dataset.k);
      const inSet=new Set(shown);
      let si=0;
      const no=M7_ORD.map(k=>inSet.has(k)?shown[si++]:k);
      shown.slice(si).forEach(k=>{if(!no.includes(k))no.push(k);});
      M7_DEF.forEach(k=>{if(!no.includes(k))no.push(k);});
      // 숨김 = 이번에 보인 것 중 체크 해제분 + 이번에 안 보인 기존 숨김분
      const off=[...ov.querySelectorAll('input[data-ck]')].filter(x=>!x.checked).map(x=>x.dataset.ck);
      const nhid=[...new Set(off.concat([...m7Hid].filter(k=>!inSet.has(k))))];
      try{localStorage.setItem(M7_LS,JSON.stringify(no));
          localStorage.setItem(M7_HIDE,JSON.stringify(nhid));}catch(_){}
      M7_ORD.length=0; no.forEach(k=>M7_ORD.push(k));
      m7Hid=new Set(nhid);
      ov.remove(); draw();};
  };

  // 기준일 = 마지막 계획업로드 일자축 첫날(planBase 캐시 반영 후 조회)
  planBase().then(b=>{if(b&&b.iso)st.ymd=date2ymd(b.iso);}).catch(()=>{}).then(load);
};
