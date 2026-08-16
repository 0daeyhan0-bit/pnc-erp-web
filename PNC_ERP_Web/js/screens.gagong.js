/* ===== PNC ERP screens.gagong.js — 가공 SCREEN (app.js 분할, 순수이동) ===== */

/* ===== 생산 ⑥: 가공공정 파트별계획 (w_pr_input_510_new) — PR_T_PLAN_PART_MAT 가공/동파이프 뷰 ===== */
SCREEN.partplanproc=(c)=>{
  const API=API_BASE;
  const nf=n=>Number(n||0).toLocaleString('ko-KR',{maximumFractionDigits:0});
  const dcol=s=>(s&&(''+s).length===6)?`${(''+s).slice(2,4)}/${(''+s).slice(4,6)}`:s;
  const iso=x=>`${x.getFullYear()}-${String(x.getMonth()+1).padStart(2,'0')}-${String(x.getDate()).padStart(2,'0')}`;
  const T=new Date();
  let F={from:iso(T),to:iso(new Date(T.getTime()+27*864e5)),wc:'',part:'',assy:'',diam:'',thick:'',pipe:'1'};
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
     <div class="page-sub">협력사계획(<code>PR_T_PLAN_PART_MAT</code>)을 가공 파트(동파이프) 단위로 지름·두께 포함 일자별 전개. 🔴 라이브</div>
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
  loadWc().then(load);
};

/* ===== 생산: 4주간 가공계획현황 (w_pr_outside_410_work) — 도번×라인×작업처, 자도번LIST 묶기 ===== */
SCREEN.gagongplan4w=(c)=>{
  const API=API_BASE;
  const nf=n=>Number(n||0).toLocaleString('ko-KR',{maximumFractionDigits:0});
  const dcol=s=>(s&&(''+s).length===6)?`${(''+s).slice(2,4)}/${(''+s).slice(4,6)}`:s;
  const iso=x=>`${x.getFullYear()}-${String(x.getMonth()+1).padStart(2,'0')}-${String(x.getDate()).padStart(2,'0')}`;
  const T=new Date();
  const st={from:iso(T),to:iso(new Date(T.getTime()+30*864e5)),wc:'P2',item:'',part:'',gigan:31,
            dates:[],rows:[],cnt:0,plan_sum:0,done_sum:0,note:'',loading:false,msg:'',exp:new Set()};
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
    const NC=12; // 고정컬럼수(SEQ~품목정보)
    const frac=(dn,pl,bg)=>{if(!pl&&!dn)return '<td class="num" style="color:#dfe6ef">·</td>';
      return `<td class="num" style="white-space:nowrap${bg?';background:'+bg:''}">${nf(dn)}/${nf(pl)}</td>`;};   // 날짜셀 색=완료상태(서버)
    c.innerHTML=`
     <div class="page-title">📋 4주간 가공계획현황 <span style="font-size:12px;color:var(--muted);font-weight:400">도번×라인×작업처 · 자도번LIST 묶음</span></div>
     <div class="page-sub">레거시 4주간 원천(<code>PR_T_PLAN_PART_DTL_FOR_CUST</code>·당일생성 스냅샷) 직독. <b>도번=부품</b>·<b>자도번LIST=이 부품을 쓰는 부모 자도번들</b>. 첫 일자컬럼=당일이전 누적. 🔴 라이브
       <span style="margin-left:8px;font-size:11px">날짜셀 색(완료≥계획): <span style="background:#ffff00;padding:0 5px;border-radius:3px">생산완료</span> <span style="background:#fac090;padding:0 5px;border-radius:3px">출하완료</span> <span style="background:#669900;color:#fff;padding:0 5px;border-radius:3px">키팅완료</span></span></div>
     <div class="toolbar">
       <label class="tl">기준일자</label><input class="inp" type="date" id="p4-from" value="${st.from}">
       <label class="tl">기간</label><select class="inp" id="p4-gigan" style="max-width:78px">${[7,14,21,31,42,60].map(d=>`<option value="${d}"${st.gigan===d?' selected':''}>${d}일</option>`).join('')}</select>
       <label class="tl">자도번작업처</label><select class="inp" id="p4-wc" style="max-width:110px"><option value="P2"${st.wc==='P2'?' selected':''}>P2 가공</option><option value="P1"${st.wc==='P1'?' selected':''}>P1 용접</option></select>
       <button class="btn" id="p4-search">🔍 조회</button>
     </div>
     <div class="toolbar" style="margin-top:2px">
       <label class="tl">도번</label><input class="inp" id="p4-item" list="p4-iteml" value="${esc(st.item)}" style="width:130px" placeholder="도번/품명" autocomplete="off"><datalist id="p4-iteml">${itOpts}</datalist>
       <label class="tl">자도번</label><input class="inp" id="p4-part" list="p4-partl" value="${esc(st.part)}" style="width:130px" placeholder="자도번" autocomplete="off"><datalist id="p4-partl">${ptOpts}</datalist>
       <div class="spacer"></div><span class="rowcount">행 <b>${nf(st.cnt)}</b> · 계획합 <b>${nf(st.plan_sum)}</b> · 완료합 <b>${nf(st.done_sum)}</b> · 일자 ${dates.length}개</span>
     </div>
     ${st.note?`<div class="page-sub" style="color:#c0392b">${esc(st.note)}</div>`:''}
     ${st.msg?`<div class="page-sub" style="color:#c0392b">⚠ ${esc(st.msg)}</div>`:''}
     <div class="grid-wrap" style="max-height:calc(100vh - 340px);overflow:auto;background:#fff;border:1px solid var(--line-2,#c9d3e0);border-radius:8px">
      <table class="tbl fit" style="font-size:11px"><thead><tr>
       <th>SEQ</th><th>자도번작업처</th><th>라인</th><th>작업처</th><th>도번</th><th>자도번LIST</th>
       <th class="num">LOT수량</th><th class="num">자재수량</th><th class="num">완료수량</th><th class="num">요청수량</th><th>품목정보</th>
       ${dates.map(d=>`<th class="num">${dcol(d)}</th>`).join('')}</tr></thead>
      <tbody>${st.loading?spinRow(NC+dates.length):(st.rows.length?st.rows.map((r,i)=>{
        const jshort=(r.jado||'').length>44?(r.jado.slice(0,44)+'…'):(r.jado||'');
        const ex=st.exp.has(i);
        return `<tr>
        <td class="num">${i+1}</td><td class="center">${esc(r.awcnm||r.awc)}</td><td class="center">${esc(r.line)}</td>
        <td>${esc(r.mwcnm)}</td><td><b>${esc(r.assy)}</b></td>
        <td class="jado-cell" data-i="${i}" title="${esc(r.jado)}" style="max-width:230px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;cursor:pointer;color:#1c66c9">${esc(jshort)} <span style="color:#8aa">(${r.matcnt})</span></td>
        <td class="num">${nf(r.lot)}</td><td class="num">${nf(r.matq)}</td><td class="num"${r.finish?'':' style="color:#dfe6ef"'}>${r.finish?nf(r.finish):'·'}</td><td class="num">${nf(r.plan_qty)}</td>
        <td class="bcap" title="${esc(r.nm)}" style="max-width:150px;overflow:hidden;text-overflow:ellipsis">${esc(r.nm)}</td>
        ${dates.map(d=>frac((r.done&&r.done[d])||0,(r.days&&r.days[d])||0,(r.colors&&r.colors[d])||'')).join('')}</tr>
        ${ex?`<tr class="jado-exp"><td></td><td colspan="${NC-1+dates.length}" style="background:#f2f7ff;white-space:normal;padding:4px 8px;font-size:11px;color:#334">📦 자도번 ${r.matcnt}종: ${esc(r.jado).replace(/,/g,'&nbsp;· ')}</td></tr>`:''}`;
      }).join(''):`<tr><td colspan="${NC+dates.length}" class="empty">조회 결과 없음</td></tr>`)}</tbody>
      ${st.rows.length?`<tfoot><tr class="grandtot"><td colspan="6">합계 (${nf(st.cnt)}행)</td>
        <td class="num">${nf(tLot)}</td><td class="num">${nf(tMat)}</td><td class="num">${nf(tFin)}</td><td class="num">${nf(tReq)}</td><td></td>
        ${dates.map(d=>`<td class="num" style="white-space:nowrap">${nf(dSum[d].dn)}/${nf(dSum[d].pl)}</td>`).join('')}</tr></tfoot>`:''}
      </table></div>`;
    const g=id=>c.querySelector(id);
    g('#p4-search').onclick=()=>{st.from=g('#p4-from').value;st.gigan=+g('#p4-gigan').value;st.to=iso(new Date(new Date(st.from).getTime()+st.gigan*864e5));st.wc=g('#p4-wc').value.trim();st.item=g('#p4-item').value.trim();st.part=g('#p4-part').value.trim();load();};
    g('#p4-gigan').onchange=()=>{st.gigan=+g('#p4-gigan').value;st.to=iso(new Date(new Date(st.from).getTime()+st.gigan*864e5));g('#p4-search').click();};
    ['#p4-wc','#p4-item','#p4-part'].forEach(id=>g(id).onkeyup=e=>{if(e.key==='Enter')g('#p4-search').click();});
    c.querySelectorAll('.jado-cell').forEach(el=>el.onclick=()=>{const i=+el.dataset.i;st.exp.has(i)?st.exp.delete(i):st.exp.add(i);draw();});
  };
  load();
};

/* ===== 생산: 가공생산진척관리(전표발행) (w_pr_input_420_new) — PR_T_PLAN_PART_DTL 스냅샷 직독 ===== */
SCREEN.gagongprog420=(c)=>{
  const API=API_BASE;
  const nf=n=>Number(n||0).toLocaleString('ko-KR',{maximumFractionDigits:0});
  const nf2=n=>Number(n||0).toLocaleString('ko-KR',{minimumFractionDigits:2,maximumFractionDigits:2});
  const dcol=s=>(s&&(''+s).length===6)?`${(''+s).slice(2,4)}/${(''+s).slice(4,6)}`:s;
  const iso=x=>`${x.getFullYear()}-${String(x.getMonth()+1).padStart(2,'0')}-${String(x.getDate()).padStart(2,'0')}`;
  const T=new Date();
  const st={from:iso(T),to:iso(new Date(T.getTime()+1*864e5)),wc:'P2',part:'',item:'',jado:'',unfin:'미생산',gigan:2,src:'nx',
            dates:[],allrows:[],note:'',loading:false,msg:''};
  const load=async()=>{st.loading=true;draw();
    // ★nx 재현(prog420nx) 기본 · sp=레거시 암호화SP 비교용. 전체 1회 조회·캐시 → 미생산/미키팅 토글은 클라 즉시필터.
    const ep=st.src==='sp'?'prog420':'prog420nx';
    const qs=st.src==='sp'
      ? new URLSearchParams({from_ymd:st.from,to_ymd:st.to,wc:st.wc,item:st.item,jado:st.jado,unfin:'전체',limit:8000})
      : new URLSearchParams({from_ymd:st.from,gigan:st.gigan,wc:st.wc,item:st.item,jado:st.jado,unfin:'전체',limit:8000});
    try{const r=await fetch(`${API}/api/gagong/${ep}?${qs}`);const d=await r.json();
      st.dates=d.dates||[];st.allrows=d.rows||[];st.note=d.note||'';st.msg='';}
    catch(e){st.msg='백엔드 연결 실패';st.dates=[];st.allrows=[];}
    st.loading=false;draw();};
  const draw=()=>{
    const dates=st.dates;
    // ★미생산/미키팅 토글 = 캐시(allrows)에서 클라 즉시필터(재조회 없음)
    const rows0 = st.unfin==='미생산' ? st.allrows.filter(r=>(+r.finish||0)<(+r.plan_qty||0))
                : st.unfin==='미키팅' ? st.allrows.filter(r=>(+r.prior_fn||0)<=0) : st.allrows;
    const wcS=new Map(),itS=new Map(),gpS=new Map();
    rows0.forEach(r=>{if(r.wcd&&!wcS.has(r.wcd))wcS.set(r.wcd,r.wcd);if(r.assy&&!itS.has(r.assy))itS.set(r.assy,'');if(r.gpcnm)gpS.set(r.gpcnm,r.gpcnm);});
    const itOpts=[...itS].map(([v])=>`<option value="${esc(v)}"></option>`).join('');
    const gpOpts=[...gpS].map(([v])=>`<option value="${esc(v)}"></option>`).join('');
    let tPlan=0,tFin=0,tSale=0,tPrs=0,tPFn=0,tPPl=0;const dSum={};dates.forEach(d=>dSum[d]={dn:0,pl:0});
    rows0.forEach(r=>{tPlan+=+r.plan_qty||0;tFin+=+r.finish||0;tSale+=+r.sale||0;tPrs+=+r.prs||0;tPFn+=+r.prior_fn||0;tPPl+=+r.prior_pl||0;
      dates.forEach(d=>{dSum[d].dn+=(r.done&&r.done[d])||0;dSum[d].pl+=(r.days&&r.days[d])||0;});});
    const NC=15;
    const frac=(dn,pl,bg)=>{if(!pl&&!dn)return '<td class="num" style="color:#dfe6ef">·</td>';
      return `<td class="num" style="white-space:nowrap${bg?';'+bg:''}">${nf(dn)}/${nf(pl)}</td>`;};   // 셀색=레거시SP color_NN
    c.innerHTML=`
     <div class="page-title">🏭 가공생산진척관리(전표발행) <span style="font-size:12px;color:var(--muted);font-weight:400">Assy도번·자도번별 생산진척</span></div>
     <div class="page-sub">${st.src==='sp'?'레거시 암호화SP 직접실행(대사용)':'<b>nx 재현</b>(암호화SP 탈피)'} · 그레인=(도번,가공컴포넌트) · 셀색 90주황출하/70·30노랑재고/20민트가공창고/10녹전표 · 당일이전=기준일 이전 · ${st.src==='sp'?'🔴 라이브':'🟢 nx'}</div>
     <div class="toolbar">
       <label class="tl">기준일자</label><input class="inp" type="date" id="g4-from" value="${st.from}">
       <label class="tl">기간</label><select class="inp" id="g4-gigan" style="max-width:70px">${[1,2,3,4,5,6,7,8].map(d=>`<option value="${d}"${st.gigan===d?' selected':''}>${d}일</option>`).join('')}</select>
       <label class="tl">자도번작업처</label><select class="inp" id="g4-wc" style="width:110px"><option value="P2"${st.wc==='P2'?' selected':''}>P2 가공</option><option value="P1"${st.wc==='P1'?' selected':''}>P1 용접</option></select>
       <label class="tl">미생산</label>
       <label class="rl"><input type="radio" name="g4-uf" value="전체"${st.unfin==='전체'?' checked':''}> 전체</label>
       <label class="rl"><input type="radio" name="g4-uf" value="미생산"${st.unfin==='미생산'?' checked':''}> 미생산</label>
       <label class="rl"><input type="radio" name="g4-uf" value="미키팅"${st.unfin==='미키팅'?' checked':''}> 미키팅</label>
       <label class="tl">소스</label><select class="inp" id="g4-src" style="width:110px"><option value="nx"${st.src==='nx'?' selected':''}>우리(nx)</option><option value="sp"${st.src==='sp'?' selected':''}>레거시 대사</option></select>
       <button class="btn" id="g4-search">🔍 조회</button>
       <div class="spacer"></div><button class="btn" id="g4-bc" style="background:#1c7c3a;color:#fff">📷 가공바코드실적처리</button>
     </div>
     <div class="toolbar" style="margin-top:2px">
       <label class="tl">도번</label><input class="inp" id="g4-item" list="g4-iteml" value="${esc(st.item)}" style="width:120px" placeholder="Assy도번" autocomplete="off"><datalist id="g4-iteml">${itOpts}</datalist>
       <label class="tl">자도번</label><input class="inp" id="g4-jado" value="${esc(st.jado)}" style="width:120px" placeholder="자도번" autocomplete="off">
       <label class="tl">출고처(파트)</label><input class="inp" id="g4-part" list="g4-partl" value="${esc(st.part)}" style="width:110px" placeholder="가공파트" autocomplete="off"><datalist id="g4-partl">${gpOpts}</datalist>
       <div class="spacer"></div><span class="rowcount">행 <b>${nf(st.cnt)}</b> · 생산계획합 <b>${nf(st.plan_sum)}</b> · 완료합 <b>${nf(st.done_sum)}</b></span>
     </div>
     ${st.note?`<div class="page-sub" style="color:#c0392b">${esc(st.note)}</div>`:''}
     ${st.msg?`<div class="page-sub" style="color:#c0392b">⚠ ${esc(st.msg)}</div>`:''}
     <div class="grid-wrap" style="max-height:calc(100vh - 340px);overflow:auto;background:#fff;border:1px solid var(--line-2,#c9d3e0);border-radius:8px">
      <table class="tbl fit" style="font-size:11px"><thead><tr>
       <th>Assy도번</th><th>자도번</th><th>품명</th><th>출고처</th><th class="num">생산ST</th><th class="num">생산계획</th><th class="num">당일이전</th>
       ${dates.map(d=>`<th class="num">${dcol(d)}</th>`).join('')}
       <th class="num">완료</th><th class="num">출하</th><th class="num">생산재고</th><th class="num">ASSY재고</th><th class="num">도번고정</th><th>자도번작업처</th><th>WO</th></tr></thead>
      <tbody>${st.loading?spinRow(NC+dates.length):(st.rows.length?st.rows.map(r=>{
        return `<tr>
        <td><b>${esc(r.assy)}</b></td><td>${esc(r.jado)}</td>
        <td class="bcap" title="${esc(r.jnm)}" style="max-width:130px;overflow:hidden;text-overflow:ellipsis">${esc(r.jnm)}</td>
        <td class="center">${esc(r.gpcnm)}</td><td class="num">${nf2(r.st)}</td><td class="num">${nf(r.plan_qty)}</td>
        <td class="num" style="white-space:nowrap${r.prior_bg?';'+r.prior_bg:''}">${nf(r.prior_fn)}/${nf(r.prior_pl)}</td>
        ${dates.map(d=>frac((r.done&&r.done[d])||0,(r.days&&r.days[d])||0,(r.colors&&r.colors[d])||'')).join('')}
        <td class="num"${r.finish?'':' style="color:#dfe6ef"'}>${r.finish?nf(r.finish):'·'}</td>
        <td class="num"${r.sale?'':' style="color:#dfe6ef"'}>${r.sale?nf(r.sale):'·'}</td>
        <td class="num"${r.prs?'':' style="color:#dfe6ef"'}>${r.prs?nf(r.prs):'·'}</td>
        <td class="num"${r.assyst?'':' style="color:#dfe6ef"'}>${r.assyst?nf(r.assyst):'·'}</td>
        <td class="num"${r.fixst?'':' style="color:#dfe6ef"'}>${r.fixst?nf(r.fixst):'·'}</td>
        <td class="center">${esc(r.wcc?(r.wcc+' '+r.wcd):r.wcd)}</td><td class="bcap" style="max-width:110px;overflow:hidden;text-overflow:ellipsis" title="${esc(r.wo)}">${esc(r.wo)}</td></tr>`;
      }).join(''):`<tr><td colspan="${NC+dates.length}" class="empty">조회 결과 없음</td></tr>`)}</tbody>
      ${st.rows.length?`<tfoot><tr class="grandtot"><td colspan="5">합계 (${nf(st.cnt)}행)</td><td class="num">${nf(tPlan)}</td><td class="num">${nf(tPFn)}/${nf(tPPl)}</td>
        ${dates.map(d=>`<td class="num" style="white-space:nowrap">${nf(dSum[d].dn)}/${nf(dSum[d].pl)}</td>`).join('')}
        <td class="num">${nf(tFin)}</td><td class="num">${nf(tSale)}</td><td class="num">${nf(tPrs)}</td><td></td><td></td><td></td><td></td></tr></tfoot>`:''}
      </table></div>`;
    const g=id=>c.querySelector(id);
    g('#g4-search').onclick=()=>{st.from=g('#g4-from').value;st.to=iso(new Date(new Date(st.from).getTime()+(st.gigan-1)*864e5));st.wc=g('#g4-wc').value.trim();
      st.item=g('#g4-item').value.trim();st.jado=g('#g4-jado').value.trim();st.part=g('#g4-part').value.trim();load();};
    g('#g4-gigan').onchange=()=>{st.gigan=+g('#g4-gigan').value;st.to=iso(new Date(new Date(st.from).getTime()+(st.gigan-1)*864e5));g('#g4-search').click();};
    c.querySelectorAll('input[name=g4-uf]').forEach(rd=>rd.onchange=()=>{st.unfin=rd.value;load();});
    g('#g4-wc').onchange=()=>g('#g4-search').click();
    ['#g4-item','#g4-jado','#g4-part'].forEach(id=>g(id).onkeyup=e=>{if(e.key==='Enter')g('#g4-search').click();});
    g('#g4-bc').onclick=openBcModal;
  };
  /* 가공바코드실적처리 팝업 (레거시 w_pr_input_018) — 스캔→정보조회→양품/불량→처리바코드 재스캔→등록/취소 */
  const openBcModal=()=>{
    let bc={box:null,info:null};
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
            <label class="tl">바코드/수량</label><input class="inp" id="bc-scan1" placeholder="바코드 스캔(Enter)" autocomplete="off" style="font-size:15px">
            <label class="tl">양품수량</label><input class="inp" id="bc-good" type="number" value="${i?(i.reg_good||i.plan_qty):''}" style="text-align:right">
            <label class="tl">불량수량</label><input class="inp" id="bc-bad" type="number" value="${i?(i.reg_bad||0):0}" style="text-align:right">
            <label class="tl">처리바코드</label><input class="inp" id="bc-scan2" placeholder="확정 바코드 재스캔(Enter=등록)" autocomplete="off" style="font-size:15px;grid-column:span 3">
          </div>
          <div style="display:grid;grid-template-columns:auto 1fr auto 1fr;gap:6px 10px;align-items:center;margin-top:12px;padding:12px;border:1px solid #e5e9f0;border-radius:8px">
            <label class="tl">대표도번</label><b>${i?esc(i.assy):'·'}</b><label class="tl">간판수량</label><b>${i?nf(i.plan_qty):'·'}</b>
            <label class="tl">자도번</label><b>${i?esc(i.mat)+' <span style="color:#888;font-weight:400">'+esc(i.matnm||'')+'</span>':'·'}</b><label class="tl">가공완료</label><b>${i?nf(i.prod_qty):'·'}</b>
            <label class="tl">불량이력</label><span>${i?(i.err_cnt+'건 / '+nf(i.err_qty)+'개'):'·'}</span><label class="tl">입고창고</label><b>${i?esc(i.wh):'·'}</b>
          </div>
          <div id="bc-msg" style="margin-top:8px;min-height:18px;font-size:12px"></div>
          <div style="display:flex;gap:8px;justify-content:flex-end;margin-top:6px">
            ${i&&i.already?`<button class="btn" id="bc-cancel" style="background:#c0392b;color:#fff">🗑 실적취소</button>`:''}
            <button class="btn" id="bc-reg" style="background:#1c47a0;color:#fff"${i?'':' disabled'}>✔ 실적등록</button>
            <button class="btn" id="bc-close2">닫기</button></div>
        </div></div>`;
      const q=s=>ov.querySelector(s);
      const msg=(t,ok)=>{q('#bc-msg').innerHTML=`<span style="color:${ok?'#1c7c3a':'#c0392b'}">${esc(t)}</span>`;};
      const doScan=async()=>{const v=q('#bc-scan1').value.trim();if(!v)return;
        try{const d=await(await fetch(`${API_BASE}/api/gagong/barcode/scan?barcode=${encodeURIComponent(v)}`)).json();
          if(!d.ok){bc.info=null;render();q('#bc-scan1').value=v;q('#bc-scan1').focus();msg(d.msg,false);return;}
          bc.box=d.box_no;bc.info=d;render();q('#bc-scan1').value=v;q('#bc-scan2').focus();
          if(d.already)msg(`이미 등록됨(양품 ${d.reg_good}·불량 ${d.reg_bad}, ${d.reg_user} ${d.reg_dt}). 취소 후 재등록.`,false);
        }catch(e){msg('조회 실패',false);}};
      const doReg=async()=>{if(!bc.info)return;
        try{const d=await(await fetch(`${API_BASE}/api/gagong/barcode/register`,{method:'POST',headers:{'Content-Type':'application/json'},
          body:JSON.stringify({box_no:bc.box,scan2:q('#bc-scan2').value.trim(),good_qty:+q('#bc-good').value||0,bad_qty:+q('#bc-bad').value||0,user:'웹',ymd:q('#bc-ymd').value})})).json();
          if(d.ok){const s=await(await fetch(`${API_BASE}/api/gagong/barcode/scan?barcode=${bc.box}`)).json();bc.info=s;render();msg(`✔ 등록완료: 양품 ${d.good_qty}·불량 ${d.bad_qty}`,true);}
          else msg(d.msg,false);
        }catch(e){msg('등록 실패',false);}};
      const doCancel=async()=>{if(!confirm('이 전표의 실적을 취소할까요?'))return;
        const d=await(await fetch(`${API_BASE}/api/gagong/barcode/cancel`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({box_no:bc.box})})).json();
        if(d.ok){const s=await(await fetch(`${API_BASE}/api/gagong/barcode/scan?barcode=${bc.box}`)).json();bc.info=s;render();msg('실적 취소됨',true);}};
      q('#bc-x').onclick=q('#bc-close2').onclick=()=>ov.remove();
      q('#bc-scan1').onkeyup=e=>{if(e.key==='Enter')doScan();}; q('#bc-scan1').onblur=doScan;
      q('#bc-scan2').onkeyup=e=>{if(e.key==='Enter')doReg();};
      if(q('#bc-reg'))q('#bc-reg').onclick=doReg;
      if(q('#bc-cancel'))q('#bc-cancel').onclick=doCancel;
      if(!bc.info)q('#bc-scan1').focus();
    };
    render(); document.body.appendChild(ov);
  };
  load();
};

/* ===== 생산: 가공창고 이동계획 (w_pr_input_580) — 도번×라인, 자도번LIST + 이동필요/완료 ===== */
SCREEN.gagongmove580=(c)=>{
  const API=API_BASE;
  const nf=n=>Number(n||0).toLocaleString('ko-KR',{maximumFractionDigits:0});
  const dcol=s=>(s&&(''+s).length===6)?`${(''+s).slice(2,4)}/${(''+s).slice(4,6)}`:s;
  const iso=x=>`${x.getFullYear()}-${String(x.getMonth()+1).padStart(2,'0')}-${String(x.getDate()).padStart(2,'0')}`;
  const T=new Date();
  const st={from:iso(T),to:iso(new Date(T.getTime()+14*864e5)),wc:'',item:'',part:'',mv:'이동필요',gigan:14,
            dates:[],rows:[],cnt:0,plan_sum:0,need_sum:0,moved_sum:0,note:'',loading:false,msg:'',exp:new Set()};
  const load=async()=>{st.loading=true;draw();
    const qs=new URLSearchParams({from_ymd:st.from,to_ymd:st.to,wc:st.wc,item:st.item,part:st.part,mv:st.mv,limit:2500});
    try{const r=await fetch(`${API}/api/gagong/move580?${qs}`);const d=await r.json();
      st.dates=d.dates||[];st.rows=d.rows||[];st.cnt=d.cnt||0;st.plan_sum=d.plan_sum||0;st.need_sum=d.need_sum||0;st.moved_sum=d.moved_sum||0;st.note=d.note||'';st.msg='';st.exp.clear();}
    catch(e){st.msg='백엔드 연결 실패';st.dates=[];st.rows=[];st.cnt=0;}
    st.loading=false;draw();};
  const draw=()=>{
    const dates=st.dates;
    const itS=new Map(),ptS=new Set();
    st.rows.forEach(r=>{if(r.assy&&!itS.has(r.assy))itS.set(r.assy,'');
      (r.jado||'').split(',').forEach(x=>{const m=x.split('{')[0];if(m)ptS.add(m);});});
    const itOpts=[...itS].map(([v])=>`<option value="${esc(v)}"></option>`).join('');
    const ptOpts=[...ptS].sort().slice(0,400).map(v=>`<option value="${esc(v)}"></option>`).join('');
    let tNeed=0,tMoved=0;const dSum={};dates.forEach(d=>dSum[d]=0);
    st.rows.forEach(r=>{tNeed+=+r.need||0;tMoved+=+r.moved||0;dates.forEach(d=>{dSum[d]+=(r.days&&r.days[d])||0;});});
    const NC=9;
    c.innerHTML=`
     <div class="page-title">🚚 가공창고 이동계획 <span style="font-size:12px;color:var(--muted);font-weight:400">가공창고→자재창고 이동필요 · 자도번LIST 묶음</span></div>
     <div class="page-sub">계획(<code>PR_T_PLAN_PART_MAT</code>) − 이동완료(<code>PU_T_STOCK_MAINT_GAGONG_MOVE</code> 확정) = 이동필요수. 🔴 라이브 <span style="color:#c0392b">(레거시 SP 암호화 → 라이브 역설계)</span></div>
     <div class="toolbar">
       <label class="tl">기준일자</label><input class="inp" type="date" id="mv-from" value="${st.from}"> ~ <input class="inp" type="date" id="mv-to" value="${st.to}">
       <label class="tl">기간</label><select class="inp" id="mv-gigan" style="max-width:78px">${[7,10,14,21,31].map(d=>`<option value="${d}"${st.gigan===d?' selected':''}>${d}일</option>`).join('')}</select>
       <label class="tl">작업처</label><input class="inp" id="mv-wc" list="mv-wcl" value="${esc(st.wc)}" style="width:90px" placeholder="P2" autocomplete="off"><datalist id="mv-wcl"><option value="P1"></option><option value="P2"></option></datalist>
       <label class="tl">이동필요</label>
       <label class="rl"><input type="radio" name="mv-f" value="전체"${st.mv==='전체'?' checked':''}> 전체</label>
       <label class="rl"><input type="radio" name="mv-f" value="이동필요"${st.mv==='이동필요'?' checked':''}> 이동필요</label>
       <label class="rl"><input type="radio" name="mv-f" value="이동완료"${st.mv==='이동완료'?' checked':''}> 이동완료</label>
       <button class="btn" id="mv-search">🔍 조회</button>
     </div>
     <div class="toolbar" style="margin-top:2px">
       <label class="tl">도번</label><input class="inp" id="mv-item" list="mv-iteml" value="${esc(st.item)}" style="width:130px" placeholder="도번" autocomplete="off"><datalist id="mv-iteml">${itOpts}</datalist>
       <label class="tl">자도번</label><input class="inp" id="mv-part" list="mv-partl" value="${esc(st.part)}" style="width:130px" placeholder="자도번" autocomplete="off"><datalist id="mv-partl">${ptOpts}</datalist>
       <div class="spacer"></div><span class="rowcount">행 <b>${nf(st.cnt)}</b> · 이동필요합 <b style="color:#c0392b">${nf(st.need_sum)}</b> · 이동완료합 <b>${nf(st.moved_sum)}</b></span>
     </div>
     ${st.note?`<div class="page-sub" style="color:#c0392b">${esc(st.note)}</div>`:''}
     ${st.msg?`<div class="page-sub" style="color:#c0392b">⚠ ${esc(st.msg)}</div>`:''}
     <div class="grid-wrap" style="max-height:calc(100vh - 340px);overflow:auto;background:#fff;border:1px solid var(--line-2,#c9d3e0);border-radius:8px">
      <table class="tbl fit" style="font-size:11px"><thead><tr>
       <th>SEQ</th><th>최종납품처</th><th>도번</th><th>자도번LIST</th><th>PART일자</th><th>INPUT</th><th>Line</th><th class="num">이동필요</th><th class="num">이동완료</th>
       ${dates.map(d=>`<th class="num">${dcol(d)}</th>`).join('')}</tr></thead>
      <tbody>${st.loading?spinRow(NC+dates.length):(st.rows.length?st.rows.map((r,i)=>{
        const jshort=(r.jado||'').length>40?(r.jado.slice(0,40)+'…'):(r.jado||'');const ex=st.exp.has(i);
        return `<tr>
        <td class="num">${i+1}</td><td>${esc(r.dest)}</td><td><b>${esc(r.assy)}</b></td>
        <td class="jado-cell" data-i="${i}" title="${esc(r.jado)}" style="max-width:220px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;cursor:pointer;color:#1c66c9">${esc(jshort)} <span style="color:#8aa">(${r.matcnt})</span></td>
        <td class="center">${dcol(r.part_ymd)}</td><td class="center">${esc(r.hm)}</td><td class="center">${esc(r.line)}</td>
        <td class="num"${r.need>0?' style="color:#c0392b;font-weight:600"':' style="color:#dfe6ef"'}>${r.need>0?nf(r.need):'·'}</td>
        <td class="num"${r.moved?'':' style="color:#dfe6ef"'}>${r.moved?nf(r.moved):'·'}</td>
        ${dates.map(d=>{const v=(r.days&&r.days[d])||0;return `<td class="num"${v?'':' style="color:#dfe6ef"'}>${v?nf(v):'·'}</td>`;}).join('')}</tr>
        ${ex?`<tr class="jado-exp"><td></td><td colspan="${NC-1+dates.length}" style="background:#f2f7ff;white-space:normal;padding:4px 8px;font-size:11px;color:#334">📦 자도번 ${r.matcnt}종: ${esc(r.jado).replace(/,/g,'&nbsp;· ')}</td></tr>`:''}`;
      }).join(''):`<tr><td colspan="${NC+dates.length}" class="empty">조회 결과 없음</td></tr>`)}</tbody>
      ${st.rows.length?`<tfoot><tr class="grandtot"><td colspan="7">합계 (${nf(st.cnt)}행)</td><td class="num" style="color:#c0392b">${nf(tNeed)}</td><td class="num">${nf(tMoved)}</td>
        ${dates.map(d=>`<td class="num">${nf(dSum[d])}</td>`).join('')}</tr></tfoot>`:''}
      </table></div>`;
    const g=id=>c.querySelector(id);
    g('#mv-search').onclick=()=>{st.from=g('#mv-from').value;st.to=g('#mv-to').value;st.wc=g('#mv-wc').value.trim();st.item=g('#mv-item').value.trim();st.part=g('#mv-part').value.trim();load();};
    g('#mv-gigan').onchange=()=>{st.gigan=+g('#mv-gigan').value;st.to=iso(new Date(new Date(st.from).getTime()+st.gigan*864e5));g('#mv-search').click();};
    c.querySelectorAll('input[name=mv-f]').forEach(rd=>rd.onchange=()=>{st.mv=rd.value;load();});
    ['#mv-wc','#mv-item','#mv-part'].forEach(id=>g(id).onkeyup=e=>{if(e.key==='Enter')g('#mv-search').click();});
    c.querySelectorAll('.jado-cell').forEach(el=>el.onclick=()=>{const i=+el.dataset.i;st.exp.has(i)?st.exp.delete(i):st.exp.add(i);draw();});
  };
  load();
};

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
     <div class="page-sub">전표=<code>PR_T_INDI_CUTTING</code>(바코드) · 공정실적=<code>PR_T_PROD_DTL_GAGONG</code>(레거시정본) + 명칭 <code>PR_M_WORK_SINGLE</code>·<code>QA_M_MACHINE</code>. 🔴 라이브 · <span style="color:#c0392b">※=원천 미확정(담당확인)</span></div>
     <div class="toolbar">
       <label class="tl">전표출력기간</label><input class="inp" type="date" id="jh-from" value="${st.from}"> ~ <input class="inp" type="date" id="jh-to" value="${st.to}">
       <label class="tl">도번</label><input class="inp" id="jh-item" list="jh-iteml" value="${esc(st.item)}" style="width:120px" placeholder="상위도번" autocomplete="off"><datalist id="jh-iteml">${itOpts}</datalist>
       <label class="tl">자도번</label><input class="inp" id="jh-jado" value="${esc(st.jado)}" style="width:120px" placeholder="자도번" autocomplete="off">
       <label class="tl">작업처</label><input class="inp" id="jh-wc" value="${esc(st.wc)}" style="width:110px" placeholder="작업처 코드/명" autocomplete="off">
       <button class="btn" id="jh-search">🔍 조회</button>
       <div class="spacer"></div><span class="rowcount">전표 <b>${nf(st.cnt)}</b>건</span>
     </div>
     ${st.msg?`<div class="page-sub" style="color:#c0392b">⚠ ${esc(st.msg)}</div>`:''}
     <div style="display:flex;gap:8px;align-items:stretch">
      <div class="grid-wrap" style="flex:0 0 60%;max-height:calc(100vh - 300px);overflow:auto;background:#fff;border:1px solid var(--line-2,#c9d3e0);border-radius:8px">
       <table class="tbl fit" style="font-size:11px"><thead><tr><th>선택</th><th>번호</th><th>바코드번호</th><th>상위도번</th><th>자도번</th><th>작업처</th><th>작업처명</th><th class="num">지름</th><th class="num">두께</th><th title="원천 미확정 — 담당확인">검사완료시간※</th><th class="center">컷팅완료</th><th>컷팅작업자</th><th>컷팅작업일시</th><th>ASSY도번</th><th>ASSY작업처</th><th>상위도번작업처</th><th>입고창고</th></tr></thead>
       <tbody>${st.loading?spinRow(17):(st.rows.length?st.rows.map((r,i)=>`<tr class="jh-row" data-box="${esc(r.BOX_NO)}" style="cursor:pointer${st.sel===r.BOX_NO?';background:#dcebff':''}">
         <td class="center"><input type="checkbox" class="jh-chk" data-box="${esc(r.BOX_NO)}"></td>
         <td class="num">${i+1}</td><td><b>${esc(r.BOX_NO)}</b></td><td>${esc(r.doban)}</td><td>${esc(r.jado)}</td>
         <td class="center">${esc(r.wcen)||'·'}</td><td class="center">${esc(r.wcennm)||'·'}</td>
         <td class="num">${esc(r.diam)||'·'}</td><td class="num">${esc(r.thick)||'·'}</td>
         <td class="center">${esc(r.inspdt)||DAM}</td><td class="center">${esc(r.cutflag)}</td><td class="center">${esc(r.cutuser)||'·'}</td><td class="center">${esc(r.cutdt)||'·'}</td>
         <td>${esc(r.assy)}</td><td class="center">${esc(r.assywc)||'·'}</td><td class="center">${esc(r.dobanwc)||'·'}</td><td class="center">${esc(r.inwh)||'·'}</td></tr>`).join(''):`<tr><td colspan="17" class="empty">조회 결과 없음</td></tr>`)}</tbody></table></div>
      <div class="grid-wrap" style="flex:1;max-height:calc(100vh - 300px);overflow:auto;background:#fff;border:1px solid var(--line-2,#c9d3e0);border-radius:8px">
       <table class="tbl fit" style="font-size:11px"><thead><tr><th>번호</th><th>바코드</th><th class="num">공정순서</th><th>파트</th><th>가공공정</th><th>가공설비</th><th class="num">생산완료</th><th class="num" title="INDI_CUTTING_PROC_GAGONG 보충·부재시 담당확인">공정횟수※</th><th title="INDI_CUTTING_PROC_GAGONG 보충·부재시 담당확인">작업표준※</th></tr></thead>
       <tbody id="jh-dtl-body">${detailHTML()}</tbody></table></div>
     </div>`;
    const g=id=>c.querySelector(id);
    g('#jh-search').onclick=()=>{st.from=g('#jh-from').value;st.to=g('#jh-to').value;st.item=g('#jh-item').value.trim();st.jado=g('#jh-jado').value.trim();st.wc=g('#jh-wc').value.trim();load();};
    ['#jh-item','#jh-jado','#jh-wc'].forEach(id=>g(id).onkeyup=e=>{if(e.key==='Enter')g('#jh-search').click();});
    c.querySelectorAll('.jh-row').forEach(el=>el.onclick=()=>loadDetail(el.dataset.box));
    c.querySelectorAll('.jh-chk').forEach(cb=>cb.onclick=e=>e.stopPropagation());   // 체크박스는 상세로드 안 함
  };
  load();
};
