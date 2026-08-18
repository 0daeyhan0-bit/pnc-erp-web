/* ===== PNC ERP screens.dev.js — 개발 SCREEN (app.js 분할) · 재구성 20260802 ===== */

SCREEN.price=(c)=>{
  let mode='item';
  const paint=()=>{
    c.innerHTML=`
     <div class="page-title">💰 품목단가 조회 <span style="font-size:12px;color:var(--muted);font-weight:400">조회 · 전사 변동내역 · 특이 단가목록 (읽기전용) · 편집은 [품목단가 관리]</span></div>
     <div style="display:flex;gap:6px;margin:6px 0 2px">
       <button class="btn ${mode==='item'?'':'ghost'}" id="pm-item" style="${mode==='item'?'background:#1c47a0;color:#fff':''}">📇 품목별 단가조회</button>
       <button class="btn ${mode==='hist'?'':'ghost'}" id="pm-hist" style="${mode==='hist'?'background:#1c47a0;color:#fff':''}">📊 전사 단가변동내역</button>
       <button class="btn ${mode==='inv'?'':'ghost'}" id="pm-inv" style="${mode==='inv'?'background:#b12a2a;color:#fff':''}">⚠️ 특이 단가목록</button>
     </div>
     <div id="pr-host"></div>`;
    c.querySelector('#pm-item').onclick=()=>{if(mode!=='item'){mode='item';paint();}};
    c.querySelector('#pm-hist').onclick=()=>{if(mode!=='hist'){mode='hist';paint();}};
    c.querySelector('#pm-inv').onclick=()=>{if(mode!=='inv'){mode='inv';paint();}};
    const host=c.querySelector('#pr-host');
    if(mode==='item') priceItemView(host); else if(mode==='hist') priceHistView(host); else priceInvView(host);
  };
  paint();
};

/* ===== 품목단가 관리 (레거시 w_tc_master_090) — 매출처별 판매/매입 단가 마스터 CRUD. 권한자만 편집. nx.PR_M_ITEM_COST ===== */
SCREEN.pricemgmt=(c)=>{
  let mode='mgr';
  const paint=()=>{
    c.innerHTML=`
     <div class="page-title" style="margin-bottom:2px">🛠️ 품목단가 관리 <span style="font-size:12px;color:var(--muted);font-weight:400">매출처별 판매/매입 단가 · 사급가 업로드 · 권한자 편집</span></div>
     <div style="display:flex;gap:6px;margin:4px 0">
       <button class="btn ${mode==='mgr'?'':'ghost'}" id="pm2-mgr" style="${mode==='mgr'?'background:#1c47a0;color:#fff':''}">📇 품목별 단가관리</button>
       <button class="btn ${mode==='sagub'?'':'ghost'}" id="pm2-sagub" style="${mode==='sagub'?'background:#1c7c3a;color:#fff':''}">📤 사급가 업로드</button>
     </div>
     <div id="pr2-host" style="height:calc(100% - 66px)"></div>`;
    c.querySelector('#pm2-mgr').onclick=()=>{if(mode!=='mgr'){mode='mgr';paint();}};
    c.querySelector('#pm2-sagub').onclick=()=>{if(mode!=='sagub'){mode='sagub';paint();}};
    const host=c.querySelector('#pr2-host');
    if(mode==='mgr') priceMgmtView(host); else priceSagubView(host);
  };
  paint();
};

const priceMgmtView=(host)=>{
  const API=API_BASE;
  const SG=DB.sgroupNames||{}, LG=DB.lgroupNames||{};
  const sgN=s=>SG[(''+s).trim()]||(''+s).trim()||'';
  const TAGNM={'1':'매입','E':'수출판매','S':'내수판매'};
  const CUROPT=['KRW','USD','JPY','EUR','CNY','RMB'];
  const nD=(v,n)=>(v==null||v==='')?'':Number(v).toLocaleString('en-US',{minimumFractionDigits:n||0,maximumFractionDigits:n||0});
  const fmtY=y=>{y=(''+(y||'')).trim();return y.length>=6?`${y.slice(0,2)}/${y.slice(2,4)}/${y.slice(4,6)}`:y;};
  const dIn=d=>{d=(''+(d||'')).trim();return d.length>=6?`20${d.slice(0,2)}-${d.slice(2,4)}-${d.slice(4,6)}`:'';};
  const inD=v=>(''+(v||'')).slice(2).replace(/-/g,'');
  const canEdit=(typeof PERM!=='undefined')&&(PERM.isAdmin()||(((PERM.perms||{})[PERM.userId]||{})['pricemgmt']||{}).edit===true);
  let items=[], sel='', selNm='', detail=[], q='', lg='', sg='', loadingI=false, loadingD=false, form=null, dsel=null, modalEl=null, acCust={};
  // 거래처 커스텀 오토컴플리트
  const acAttach=(inp,onPick)=>{let box=null,t=null,its=[],idx=-1;
    const close=()=>{if(box){box.remove();box=null;}idx=-1;};
    const open=(list)=>{close();its=list;if(!list||!list.length)return;box=document.createElement('div');const r=inp.getBoundingClientRect();
      box.style.cssText='position:fixed;left:'+r.left+'px;top:'+(r.bottom+2)+'px;width:'+Math.max(r.width,220)+'px;max-height:240px;overflow:auto;background:#fff;border:1px solid #b9c6dd;border-radius:6px;box-shadow:0 10px 28px rgba(0,0,0,.2);z-index:1300;font-size:13px';
      list.forEach(it=>{const o=document.createElement('div');o.className='ac-op';o.style.cssText='padding:6px 10px;cursor:pointer;white-space:nowrap;overflow:hidden;text-overflow:ellipsis';o.innerHTML=it.label;o.onmousedown=e=>{e.preventDefault();onPick(it);close();};box.appendChild(o);});
      document.body.appendChild(box);};
    inp.addEventListener('input',()=>{const s=inp.value.trim();clearTimeout(t);if(!s){close();return;}t=setTimeout(async()=>{try{const r=await fetch(`${API}/api/item/vendorsearch?q=${encodeURIComponent(s)}`);open(((await r.json()).rows||[]).map(x=>({name:x.name,code:x.code,label:`${esc(x.name)} <span style="color:#8896ab">${esc(x.code)}</span>`})));}catch(e){close();}},200);});
    inp.addEventListener('blur',()=>setTimeout(close,150));
    inp.addEventListener('keydown',e=>{if(!box)return;const ops=box.querySelectorAll('.ac-op');if(e.key==='ArrowDown'){e.preventDefault();idx=Math.min(idx+1,ops.length-1);}else if(e.key==='ArrowUp'){e.preventDefault();idx=Math.max(idx-1,0);}else if(e.key==='Enter'&&idx>=0){e.preventDefault();onPick(its[idx]);close();return;}else if(e.key==='Escape'){close();return;}else return;ops.forEach((o,i)=>o.style.background=i===idx?'#eaf2fd':'');if(ops[idx])ops[idx].scrollIntoView({block:'nearest'});});};
  const loadItems=async()=>{loadingI=true;draw();
    try{let u=`${API}/api/pricemgmt/items?limit=1000`;if(q)u+=`&q=${encodeURIComponent(q)}`;if(lg)u+=`&lg=${encodeURIComponent(lg)}`;if(sg)u+=`&sg=${encodeURIComponent(sg)}`;
      items=(await(await fetch(u)).json()).rows||[];}catch(e){items=[];}loadingI=false;draw();};
  // ★행 클릭시 full draw 금지(좌측 스크롤 리셋 버그) — 상세 tbody만 부분갱신. [feedback-ui-rules 마스터-디테일 규칙]
  const detailBody=()=>{
    if(!sel)return `<tr><td colspan="13" class="empty">좌측에서 품목을 선택하세요</td></tr>`;
    if(loadingD)return `<tr><td colspan="13" class="empty">단가 조회 중…</td></tr>`;
    if(!detail.length)return `<tr><td colspan="13" class="empty">단가 없음 — ${canEdit?'추가 버튼으로 등록':'등록된 단가 없음'}</td></tr>`;
    return detail.map(r=>{const on=dsel&&dsel.tag===r.tag&&dsel.cust===r.cust&&dsel.ymd===r.ymd;
      return `<tr class="pm-drow${on?' sel':''}" data-t="${esc(r.tag)}" data-c="${esc(r.cust)}" data-y="${esc(r.ymd)}" style="cursor:${canEdit?'pointer':'default'}${on?';background:#dce9ff':''}">
        <td class="center">${esc(r.tag_nm)}</td><td class="bcap" title="${esc(r.cust_nm)}" style="max-width:130px;overflow:hidden;text-overflow:ellipsis">${esc(r.cust_nm)}</td>
        <td class="center">${r.main==='1'?'★':''}</td><td class="center">${fmtY(r.ymd)}</td><td class="center">${esc(r.cur)}</td>
        <td class="num"><b>${nD(r.cost,r.cost%1?4:0)}</b></td><td class="num">${r.mat?nD(r.mat,0):''}</td><td class="num">${r.proc?nD(r.proc,0):''}</td><td class="num">${r.other?nD(r.other,0):''}</td>
        <td>${esc(r.matunit)}</td><td class="bcap" title="${esc(r.remarks)}" style="max-width:120px;overflow:hidden;text-overflow:ellipsis">${esc(r.remarks)}</td><td>${esc(r.usr)}</td><td class="center" style="color:#8aa0bd">${esc(r.dt)}</td></tr>`;}).join('');};
  const wireDetail=()=>{ if(!canEdit)return;
    host.querySelectorAll('.pm-drow').forEach(tr=>{
      tr.onclick=()=>{dsel={tag:tr.dataset.t,cust:tr.dataset.c,ymd:tr.dataset.y,cust_nm:(detail.find(x=>x.tag===tr.dataset.t&&x.cust===tr.dataset.c&&x.ymd===tr.dataset.y)||{}).cust_nm};
        host.querySelectorAll('.pm-drow').forEach(x=>{x.classList.remove('sel');x.style.background='';});tr.classList.add('sel');tr.style.background='#dce9ff';};
      tr.ondblclick=()=>{const r=detail.find(x=>x.tag===tr.dataset.t&&x.cust===tr.dataset.c&&x.ymd===tr.dataset.y);if(r){dsel=r;openEdit();}};});};
  const renderDetail=()=>{const tb=host.querySelector('#pm-dbody');if(tb){tb.innerHTML=detailBody();wireDetail();}};
  const loadDetail=async()=>{if(!sel){detail=[];renderDetail();return;}loadingD=true;renderDetail();
    try{detail=(await(await fetch(`${API}/api/pricemgmt/detail?item=${encodeURIComponent(sel)}`)).json()).rows||[];}catch(e){detail=[];}loadingD=false;renderDetail();};
  // 편집 모달
  const removeModal=()=>{if(modalEl){modalEl.remove();modalEl=null;}};
  const mq=k=>{const x=modalEl&&modalEl.querySelector('.pmf[data-k="'+k+'"]');return x?(x.type==='checkbox'?(x.checked?'1':'0'):x.value.trim()):'';};
  const modalHtml=()=>{const f=form.data;const L=t=>`<label style="text-align:right;color:#4a5563;font-size:13px">${t}</label>`;
    const N=k=>`<input class="pmf inp" data-k="${k}" value="${esc(f[k]!=null&&f[k]!==''?f[k]:'')}" style="width:130px;text-align:right">`;
    const T=k=>`<input class="pmf inp" data-k="${k}" value="${esc(f[k]!=null&&f[k]!==''?f[k]:'')}" style="width:100%">`;
    return `<div class="wr-modal" style="position:fixed;inset:0;z-index:1200;background:rgba(20,30,50,.44);display:flex;align-items:flex-start;justify-content:center;overflow:auto;padding:48px 12px">
     <div style="background:#fff;border-radius:12px;padding:20px 24px;width:680px;max-width:94vw;box-shadow:0 14px 50px rgba(0,0,0,.34)">
      <div style="font-weight:700;font-size:15px;margin-bottom:16px">${form.mode==='new'?'➕ 단가 추가':'✏️ 단가 수정'} <span style="color:#888;font-weight:400;font-size:13px">${esc(sel)} · ${esc(selNm)}</span></div>
      <div style="display:grid;grid-template-columns:82px 1fr 82px 1fr;gap:11px 12px;align-items:center">
       ${L('단가구분')}<select class="pmf inp" data-k="tag" style="width:130px">${Object.entries(TAGNM).map(([k,v])=>`<option value="${k}" ${f.tag===k?'selected':''}>${v}</option>`).join('')}</select>
       ${L('거래처')}<input class="pmf inp" data-k="cust_nm" autocomplete="off" value="${esc(f.cust_nm||'')}" placeholder="거래처명/코드" style="width:100%">
       ${L('적용일')}<input class="pmf inp" data-k="ymd" type="date" value="${esc(dIn(f.ymd))}" style="width:150px">
       ${L('화폐')}<select class="pmf inp" data-k="cur" style="width:120px">${CUROPT.map(x=>`<option value="${x}" ${(''+f.cur)===x?'selected':''}>${x}</option>`).join('')}</select>
       ${L('현재단가')}${N('cost')}${L('주거래')}<label style="font-size:13px"><input class="pmf" data-k="main" type="checkbox" ${f.main==='1'?'checked':''}> 주거래처</label>
       ${L('부품비')}${N('mat')}${L('가공비')}${N('proc')}
       ${L('기타')}${N('other')}${L('소재단위')}<input class="pmf inp" data-k="matunit" value="${esc(f.matunit||'')}" style="width:130px">
       ${L('비고')}<span style="grid-column:span 3">${T('remarks')}</span>
      </div>
      <div style="margin-top:18px;text-align:right"><button class="btn ghost" id="pm-cancel">취소</button> <button class="btn" id="pm-save" style="background:#1c47a0;color:#fff">💾 저장</button></div>
     </div></div>`;};
  const showModal=()=>{removeModal();modalEl=document.createElement('div');modalEl.innerHTML=modalHtml();document.body.appendChild(modalEl);
    modalEl.querySelector('#pm-cancel').onclick=()=>{removeModal();form=null;};
    modalEl.querySelector('#pm-save').onclick=doSave;
    const cel=modalEl.querySelector('.pmf[data-k="cust_nm"]');if(cel)acAttach(cel,it=>{cel.value=it.name;acCust[it.name]=it.code;});
    const fi=modalEl.querySelector('.pmf');if(fi)fi.focus();};
  const openAdd=()=>{if(!sel){alert('먼저 좌측에서 품목을 선택하세요');return;}form={mode:'new',data:{tag:'S',cust:'',cust_nm:'',ymd:inD((new Date()).toISOString().slice(0,10)),cur:'KRW',main:'0',cost:0,mat:0,proc:0,other:0,matunit:'',remarks:''}};showModal();};
  const openEdit=()=>{if(!dsel){alert('수정 또는 삭제할 행을 선택해 주세요');return;}form={mode:'edit',data:Object.assign({},dsel)};showModal();};
  const doSave=async()=>{const f=form.data;const custNm=mq('cust_nm');let cust=acCust[custNm]||'';
    if(!cust){if(custNm===(f.cust_nm||''))cust=f.cust||'';else if(/^\d+$/.test(custNm))cust=custNm;}
    const body={item:sel,tag:mq('tag'),cust:cust,ymd:inD(mq('ymd')),cur:mq('cur'),main:mq('main'),cost:mq('cost'),mat:mq('mat'),proc:mq('proc'),other:mq('other'),matunit:mq('matunit'),remarks:mq('remarks'),by:(PERM&&PERM.userId)||'web'};
    if(form.mode==='edit')body.old={cust:f.cust,tag:f.tag,ymd:f.ymd};
    if(!body.cust||!body.ymd){alert('거래처·적용일 필수 (거래처는 목록에서 선택)');return;}
    try{const r=await fetch(`${API}/api/pricemgmt/save`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
      const j=await r.json();if(!r.ok){alert('저장 실패: '+(j.detail||r.status));return;}removeModal();form=null;dsel=null;loadDetail();}
    catch(e){alert('저장 오류: '+e.message);}};
  const doDelete=async()=>{if(!dsel){alert('수정 또는 삭제할 행을 선택해 주세요');return;}
    if(!confirm(`${TAGNM[dsel.tag]||dsel.tag} · ${dsel.cust_nm} · ${dsel.ymd} 단가행을 삭제할까요?`))return;
    try{const r=await fetch(`${API}/api/pricemgmt/delete`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({item:sel,tag:dsel.tag,cust:dsel.cust,ymd:dsel.ymd})});
      const j=await r.json();if(!r.ok){alert('삭제 실패: '+(j.detail||r.status));return;}dsel=null;loadDetail();}
    catch(e){alert('삭제 오류: '+e.message);}};
  const draw=()=>{
    const lgs=Object.entries(LG).map(([k,v])=>`<option value="${esc(k)}" ${lg===k?'selected':''}>${esc(v)}</option>`).join('');
    const sgs=Object.entries(SG).map(([k,v])=>`<option value="${esc(k)}" ${sg===k?'selected':''}>${esc(v)}</option>`).join('');
    host.innerHTML=`<div style="display:flex;flex-direction:column;height:100%">
     ${!canEdit?`<div class="page-sub" style="color:#b8860b;margin:0 0 4px">🔒 조회만 가능 — 편집 권한이 없습니다(관리자에게 [품목단가 관리] 편집권한 요청). 단가는 권한자만 수정.</div>`:''}
     <div class="toolbar" style="gap:5px;flex:0 0 auto">
       <input class="inp" id="pmq" placeholder="품번/품명" value="${esc(q)}" style="width:150px">
       <select class="inp" id="pmlg" style="max-width:120px"><option value="">대분류</option>${lgs}</select>
       <select class="inp" id="pmsg" style="max-width:120px"><option value="">소분류</option>${sgs}</select>
       <button class="btn" id="pmgo">🔍조회</button>
       <div class="spacer"></div>
       ${canEdit?`<button class="btn" id="pmadd" style="background:#1c7c3a;color:#fff">➕추가</button><button class="btn" id="pmedit">✏️수정</button><button class="btn" id="pmdel" style="color:#c0392b">🗑삭제</button>`:''}
     </div>
     <div style="display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1.5fr);gap:10px;flex:1;min-height:0">
      <div class="grid-wrap" style="min-height:0;overflow:auto;border:1px solid var(--line);border-radius:8px">
       <table class="tbl fit"><thead><tr><th>품번</th><th style="text-align:left">품명</th><th>소분류</th><th class="num">단가건</th></tr></thead>
       <tbody>${loadingI?`<tr><td colspan="4" class="empty">조회 중…</td></tr>`:(items.length?items.map(r=>`<tr class="pm-irow${sel===r.item?' sel':''}" data-i="${esc(r.item)}" style="cursor:pointer${sel===r.item?';background:#dce9ff':''}"><td><b>${esc(r.item)}</b></td><td class="bcap" title="${esc(r.nm)}" style="max-width:180px;overflow:hidden;text-overflow:ellipsis">${esc(r.nm)}</td><td class="center">${esc(sgN(r.sg))}</td><td class="num">${r.cnt||''}</td></tr>`).join(''):`<tr><td colspan="4" class="empty">검색어/분류로 조회하세요</td></tr>`)}</tbody></table>
      </div>
      <div class="grid-wrap" style="min-height:0;overflow:auto;border:1px solid var(--line);border-radius:8px">
       <table class="tbl fit"><thead><tr><th>구분</th><th>거래처</th><th class="center">주거래</th><th class="center">적용일</th><th>화폐</th><th class="num">현재단가</th><th class="num">부품비</th><th class="num">가공비</th><th class="num">기타</th><th>소재단위</th><th>비고</th><th>수정자</th><th>수정일시</th></tr></thead>
       <tbody id="pm-dbody">${detailBody()}</tbody></table>
      </div>
     </div></div>`;
    const g=id=>host.querySelector(id);
    const go=()=>{q=g('#pmq').value.trim();lg=g('#pmlg').value;sg=g('#pmsg').value;sel='';selNm='';detail=[];dsel=null;loadItems();};
    g('#pmgo').onclick=go;g('#pmq').onkeyup=e=>{if(e.key==='Enter')go();};
    g('#pmlg').onchange=go;g('#pmsg').onchange=go;
    // 품목 클릭 = 좌측 하이라이트만 부분갱신(스크롤 유지) + 상세 부분로드(full draw 금지)
    host.querySelectorAll('.pm-irow').forEach(tr=>tr.onclick=()=>{sel=tr.dataset.i;const it=items.find(x=>x.item===sel);selNm=it?it.nm:'';dsel=null;
      host.querySelectorAll('.pm-irow').forEach(x=>{x.classList.remove('sel');x.style.background='';});tr.classList.add('sel');tr.style.background='#dce9ff';
      loadDetail();});
    wireDetail();
    if(canEdit){const a=g('#pmadd'),e=g('#pmedit'),d=g('#pmdel');if(a)a.onclick=openAdd;if(e)e.onclick=openEdit;if(d)d.onclick=doDelete;}
    if(typeof attachResizers!=='undefined')attachResizers(host);
  };
  draw();
};

/* 사급가(COSP Sales Price) 업로드 — LG 사급 부품가를 nx.price_item에 Start Date 반영 */
const priceSagubView=(host)=>{
  const API=API_BASE;
  const won=v=>(v==null||v==='')?'':Number(v).toLocaleString('ko-KR',{maximumFractionDigits:0});
  let st={busy:false,msg:'',rows:[],q:''};
  const load=async()=>{try{const r=await fetch(`${API}/api/price/sagub_list?q=${encodeURIComponent(st.q)}`);st.rows=(await r.json()).rows||[];}catch(e){st.rows=[];}draw();};
  const doUpload=async(f)=>{
    if(!f)return;
    if(!/\.(xlsx|xls)$/i.test(f.name||'')){st.msg='❌ 엑셀(.xlsx/.xls) 파일만 업로드할 수 있습니다';draw();return;}
    st.busy=true;st.msg='';draw();
    try{const fd=new FormData();fd.append('file',f);
      const r=await fetch(`${API}/api/price/sagub_upload`,{method:'POST',body:fd});
      let j={};try{j=await r.json();}catch(e){}
      if(r.ok&&j.ok){st.msg=`✅ 업로드 완료 — ${won(j.rows)}행 적재 · 품목 ${j.items}개${j.skipped?` · 스킵 ${j.skipped}건(nx 미등록 품번)`:''}`;st.busy=false;await load();return;}
      else st.msg='❌ 실패: '+(j.detail||('HTTP '+r.status));
    }catch(e){st.msg='❌ 오류: '+e.message;}
    st.busy=false;draw();};
  const draw=()=>{
    host.innerHTML=`
     <div class="page-sub">LG <b>COSP Sales Price</b>(사급 부품가) 엑셀 업로드 → 각 행의 <b>Start Date를 적용일</b>로 <code>nx.price_item</code>(vendor=LG)에 반영. 최신가는 적용일 기준 자동 적용. 헤더: <code>Material·Sales Price·Start Date</code></div>
     <div id="sg-drop" style="border:2px dashed #8fb4d6;border-radius:9px;padding:16px 18px;background:#f4f9fe;display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin:8px 0">
       <span style="font-size:20px">📤</span> <b>COSP Sales Price 엑셀</b>을 여기로 <b>드래그&드롭</b> 하거나
       <button class="btn" id="sg-pick" style="background:#1c7c3a;color:#fff"${st.busy?' disabled':''}>${st.busy?'⏳ 처리중…':'📁 파일 선택'}</button>
       <input type="file" id="sg-file" accept=".xlsx,.xls" style="display:none">
       <span style="margin-left:auto;color:#8aa0bd;font-size:11px">사업부별 파일 각각 올리면 됩니다</span>
     </div>
     ${st.msg?`<div class="page-sub" style="color:${st.msg.startsWith('✅')?'#1c7c3a':'#c0392b'};font-weight:600">${esc(st.msg)}</div>`:''}
     <div class="toolbar"><label class="tl">검색</label><input class="inp" id="sg-q" value="${esc(st.q)}" placeholder="품번/품명" style="width:200px"><button class="btn" id="sg-go">🔍 조회</button><div class="spacer"></div><span class="rowcount">업로드 사급가 ${st.rows.length}건</span></div>
     <div class="grid-wrap" style="max-height:calc(100vh - 360px);overflow:auto"><table class="tbl"><thead><tr><th>품번</th><th>품명</th><th class="center">적용일(Start)</th><th class="num">사급가</th><th class="center">통화</th></tr></thead>
     <tbody>${st.rows.map(r=>`<tr><td><b>${esc(r.item)}</b></td><td class="cap" style="max-width:280px;overflow:hidden;text-overflow:ellipsis" title="${esc(r.name)}">${esc(r.name)}</td><td class="center">${esc(r.apply_ymd)}</td><td class="num">${won(r.price)}</td><td class="center">${esc(r.currency)}</td></tr>`).join('')||`<tr><td colspan="5" class="empty">업로드된 사급가 없음 — COSP 엑셀을 올려주세요</td></tr>`}</tbody></table></div>`;
    const g=id=>host.querySelector(id);
    const fe=g('#sg-file'),drop=g('#sg-drop');
    g('#sg-pick').onclick=()=>fe.click();
    fe.onchange=()=>{doUpload(fe.files&&fe.files[0]);fe.value='';};
    drop.ondragover=e=>{e.preventDefault();drop.style.background='#e3f0ff';drop.style.borderColor='#1c7c3a';};
    drop.ondragleave=()=>{drop.style.background='#f4f9fe';drop.style.borderColor='#8fb4d6';};
    drop.ondrop=e=>{e.preventDefault();drop.style.background='#f4f9fe';drop.style.borderColor='#8fb4d6';const f=e.dataTransfer.files&&e.dataTransfer.files[0];if(f)doUpload(f);};
    const q=g('#sg-q');q.oninput=x=>st.q=x.target.value;q.onkeydown=x=>{if(x.key==='Enter')load();};g('#sg-go').onclick=load;
  };
  draw();load();
};

/* 특이 단가목록 — 해당월 실 입고가 > 실 유상사급 출고가(비싸게 사서 싸게 사급) 품목. 입고/출고 둘다 있는 품목만 · 원소재·용접봉·소모품 제외 · 상위 Assy(BOM) */
const priceInvView=(host)=>{
  const API=API_BASE;
  const won=v=>(v==null||v==='')?'':Number(v).toLocaleString('ko-KR',{maximumFractionDigits:0});
  const curYm=()=>{const d=new Date();return `20${String(d.getFullYear()).slice(2)}-${String(d.getMonth()+1).padStart(2,'0')}`;};
  const toYm4=v=>{v=(''+(v||'')).trim();return v.length>=7?v.slice(2,4)+v.slice(5,7):'';};
  let st={busy:true,rows:[],q:'',ym:curYm(),retYm:''};
  const load=async()=>{
    st.busy=true;draw();
    try{const r=await fetch(`${API}/api/price/inversion?ym=${toYm4(st.ym)}&q=${encodeURIComponent(st.q)}`);
      const j=await r.json();st.rows=j.rows||[];st.retYm=j.ym||'';}catch(e){st.rows=[];}
    st.busy=false;draw();};
  const draw=()=>{
    const rows=st.rows;
    host.innerHTML=`
     <div class="page-sub">해당월에 <b>입고</b>되고 <b>유상사급 출고</b>된 품목 중 <b style="color:#c0392b">실 입고가 &gt; 실 출고가</b>(비싸게 사서 싸게 사급 = 역전). 원소재·용접봉·소모품 제외(용접링 유지). <code>입고=자재입고명세서 / 출고=자재불출명세서(tag5) · nx</code></div>
     <div class="toolbar"><label class="tl">적용월</label><input type="month" class="inp" id="iv-ym" value="${esc(st.ym)}" style="width:130px">
       <label class="tl">품목</label><input class="inp" id="iv-q" value="${esc(st.q)}" placeholder="품번/품명" style="width:160px">
       <button class="btn" id="iv-go">🔍 조회</button><div class="spacer"></div>
       <span class="rowcount">${st.busy?'조회중…':`역전 <b style="color:#c0392b">${rows.length}</b>건 · 20${esc(st.retYm.slice(0,2))}년 ${esc(st.retYm.slice(2,4))}월`}</span></div>
     <div class="grid-wrap" style="max-height:calc(100vh - 320px);overflow:auto"><table class="tbl">
       <thead><tr><th>품번</th><th>품명</th><th class="center">분류</th><th>매입처</th><th class="num">입고가</th><th class="num">입고량</th><th>사급처</th><th class="num">출고가</th><th class="num">출고량</th><th class="num">역전액</th><th class="num">총역전액</th><th>상위 Assy(완제품)</th></tr></thead>
       <tbody>${st.busy?`<tr><td colspan="12" class="empty">조회중…</td></tr>`:(rows.map(r=>`
         <tr><td class="cap" style="max-width:118px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${esc(r.item)}"><b>${esc(r.item)}</b></td>
           <td class="cap" style="max-width:110px;overflow:hidden;text-overflow:ellipsis" title="${esc(r.nm)}">${esc(r.nm)}</td>
           <td class="center" style="font-size:11px;color:#667">${esc(r.sg_nm||r.sg)}</td>
           <td class="cap" style="max-width:78px;overflow:hidden;text-overflow:ellipsis" title="${esc(r.pur_cust_nm)}">${esc(r.pur_cust_nm)}</td>
           <td class="num">${won(r.pur)}</td>
           <td class="num" style="color:#889">${won(r.inq)}</td>
           <td class="cap" style="max-width:78px;overflow:hidden;text-overflow:ellipsis" title="${esc(r.sag_cust_nm)}">${esc(r.sag_cust_nm)}</td>
           <td class="num">${won(r.sag)}</td>
           <td class="num" style="color:#889">${won(r.outq)}</td>
           <td class="num" style="color:#c0392b;font-weight:700">${won(r.diff)}</td>
           <td class="num" style="color:#8a1f1f;font-weight:800;background:#fbeeee">${won((r.diff||0)*(r.outq||0))}</td>
           <td class="cap" style="max-width:230px;overflow:hidden;text-overflow:ellipsis" title="${esc((r.assy||[]).join(', '))}">${(r.assy&&r.assy.length)?esc(r.assy.join(', ')):'<span style=\"color:#aaa\">(직접)</span>'}</td></tr>`).join('')||`<tr><td colspan="12" class="empty">해당월 입고+출고 역전 품목 없음</td></tr>`)}</tbody></table></div>`;
    const g=id=>host.querySelector(id);
    const ym=g('#iv-ym');ym.onchange=e=>{st.ym=e.target.value;load();};
    const q=g('#iv-q');q.oninput=e=>st.q=e.target.value;q.onkeydown=e=>{if(e.key==='Enter')load();};
    g('#iv-go').onclick=load;
  };
  load();
};

SCREEN.devmaster=(c)=>{
  const LG=DB.lgroupNames||{};
  const MS={
    assem:{t:'체결공정', key:'assemProc', cols:[{f:'code',h:'공정코드'},{f:'nm',h:'공정명'},{f:'st',h:'표준공수',n:1},{f:'seq',h:'표시순서',n:1},{f:'use',h:'사용',yn:1}]},
    proc:{t:'원가공정', key:'costProc', cols:[{f:'code',h:'공정코드'},{f:'nm',h:'공정명'},{f:'lg',h:'대분류',sel:LG},{f:'seq',h:'표시순서',n:1},{f:'uph',h:'표준UPH',n:1},{f:'use',h:'사용',yn:1}]},
    weld:{t:'용접공정', key:'weldDiam', cols:[{f:'diam',h:'외경',n:1},{f:'solder',h:'은납(%)'},{f:'qty',h:'소요량',n:1},{f:'st',h:'공수',n:1}]},
    labor:{t:'표준임율', key:'laborRate', cols:[{f:'ym',h:'적용년월'},{f:'tag',h:'임율구분'},{f:'cost',h:'적용임율',n:1}]},
    matcost:{t:'절삭재료비', key:'matCost', filt:1, cols:[{f:'diam',h:'외경',n:1},{f:'thick',h:'두께',n:1},{f:'matcost',h:'재료비',n:1},{f:'proccost',h:'가공비',n:1},{f:'exrate',h:'적용환율',n:1},{f:'totcost',h:'원재료비',n:1},{f:'totcust',h:'원재료비(고객)',n:1},{f:'totsub',h:'원재료비(협력)',n:1},{f:'market',h:'현물기준',n:1},{f:'remarks',h:'비고'}]},
    matspec:{t:'소재SPEC별ST', special:1},
  };
  const ORDER=['assem','proc','weld','labor','matcost','matspec'];
  const metalNM={CU:'구리',STS:'STS',AL:'알루미늄',FE:'철','고강도':'고강도관'};
  let tab='assem', data=[], fm='CU', fy='', editMode=false, msMetal='CU', msShow=null, msSeq=null;
  const lsk=k=>'dm_'+k;
  const load=k=>{try{const s=localStorage.getItem(lsk(k));if(s)return JSON.parse(s);}catch(e){} return JSON.parse(JSON.stringify(DB[k]||[]));};
  const draw=()=>{
    const m=MS[tab];
    c.innerHTML=`
     <div class="page-title">🛠️ 원가/BOM 기준정보</div>
     <div class="page-sub">원가·BOM 산정용 기준마스터 편집 · 원본 <code>CS_M_*</code> · ✎추가/수정/삭제 후 <b>저장</b>(브라우저 임시저장, 실 반영은 신규 백엔드 연결 후)</div>
     <div class="toolbar" style="gap:4px">${ORDER.map(k=>`<button class="btn ${tab===k?'':'ghost'}" data-tab="${k}">${MS[k].t}</button>`).join('')}</div>
     <div id="pane"></div>`;
    c.querySelectorAll('[data-tab]').forEach(b=>b.onclick=()=>{tab=b.dataset.tab;editMode=false;draw();});
    const pane=c.querySelector('#pane');
    if(m.special){
      const specs=load('resSpec'), procD=load('resProc'); const procNM={}; (DB.costProc||[]).forEach(p=>procNM[(''+p.code).trim()]=(p.nm||'').trim());
      const metals=[...new Set(specs.map(s=>s.mat))].filter(Boolean).sort();
      if(!metals.includes(msMetal)) msMetal=metals.includes('고강도')?'고강도':(metals[0]||'');
      pane.innerHTML=`
        <div class="page-sub" style="margin:2px 0 8px">소재SPEC별 공정 표준 UPH · 좌:<b>소재SPEC</b>(<code>CS_M_RES_PROC_RAW1</code>) + 우:<b>공정 UPH</b>(<code>CS_M_RES_PROC_RAW2</code>) · <b>소재SPEC 클릭 → 공정 UPH</b> · ✔라이브 100% 일치 · (품목별 매트릭스는 「품목별 ST관리」)</div>
        <div class="toolbar"><label class="tl">소재</label><select class="sel" id="smat">${metals.map(x=>`<option value="${esc(x)}" ${x===msMetal?'selected':''}>${esc(x)} ${esc(metalNM[x]||'')}</option>`).join('')}</select>
          ${editMode?`<button class="btn" id="ssave">💾 저장</button><button class="btn ghost" id="scancel">✖ 취소</button><button class="btn ghost" id="srevert">↩ 원본복원</button>`:(PERM.canEdit('devmaster')?`<button class="btn" id="sedit">✎ 수정</button>`:`<span style="color:#c0392b;font-size:12px">🔒 수정권한 없음 (${esc(PERM.label())})</span>`)}
          <div class="spacer"></div><span class="rowcount" id="scnt"></span></div>
        <div style="display:flex;gap:10px;align-items:flex-start">
          <div style="flex:0 0 48%;min-width:0"><div class="summary-bar"><div class="s-item"><b>소재SPEC</b> · 순번·from/to 외경·두께·길이</div></div>
            <div class="grid-wrap" style="max-height:440px;overflow:auto"><table class="tbl fit"><thead><tr><th class="num">순번</th><th class="num">from외경</th><th class="num">to외경</th><th class="num">from두께</th><th class="num">to두께</th><th class="num">from길이</th><th class="num">to길이</th></tr></thead><tbody id="sbody"></tbody></table></div></div>
          <div style="flex:1;min-width:0"><div class="summary-bar" id="rhead"><div class="s-item">← 좌측 소재SPEC 클릭</div></div>
            <div class="grid-wrap" style="max-height:440px;overflow:auto"><table class="tbl fit"><thead><tr><th>공정</th><th class="num">내부UPH</th><th class="num">고객사UPH</th><th class="num">협력사UPH</th><th class="center">임율구분</th></tr></thead><tbody id="rbody"></tbody></table></div></div>
        </div>`;
      const nn=v=>v==null?'':won(v);
      const renderProc=()=>{
        const rows=procD.map((x,pi)=>({x,pi})).filter(({x})=>x.mat===msMetal&&x.seq===msSeq).sort((a,b)=>(''+a.x.pc).localeCompare(''+b.x.pc,'ko'));
        c.querySelector('#rhead').innerHTML=`<div class="s-item">소재 <b>${esc(msMetal)}</b> · 순번 <b>${msSeq==null?'-':msSeq}</b> · ${rows.length}공정</div>`;
        const cell=(pi,f)=>editMode?`<input type="number" step="any" class="num" data-p="${pi}" data-f="${f}" value="${procD[pi][f]==null?'':procD[pi][f]}" style="width:74px">`:won(procD[pi][f]);
        c.querySelector('#rbody').innerHTML=rows.map(({x,pi})=>`<tr><td>${esc(x.pc)} ${esc(procNM[x.pc]||'')}</td><td class="num">${cell(pi,'uh')}</td><td class="num">${cell(pi,'uhc')}</td><td class="num">${cell(pi,'uhs')}</td><td class="center">${esc(x.lt)}:임율</td></tr>`).join('')||`<tr><td colspan="5" class="empty">공정 없음</td></tr>`;
        if(editMode) c.querySelectorAll('#rbody input').forEach(el=>el.onchange=()=>{procD[+el.dataset.p][el.dataset.f]=+el.value||0;});
      };
      const renderSpec=()=>{
        const list=specs.map((s,si)=>({s,si})).filter(({s})=>s.mat===msMetal).sort((a,b)=>a.s.seq-b.s.seq);
        const cell=(si,f)=>editMode?`<input type="number" step="any" class="num" data-s="${si}" data-f="${f}" value="${specs[si][f]==null?'':specs[si][f]}" style="width:66px">`:nn(specs[si][f]);
        c.querySelector('#sbody').innerHTML=list.map(({s,si})=>`<tr data-seq="${s.seq}" class="${msSeq===s.seq?'sel':''}" style="cursor:pointer"><td class="num"><b>${s.seq}</b></td><td class="num">${cell(si,'bd')}</td><td class="num">${cell(si,'ed')}</td><td class="num">${cell(si,'bt')}</td><td class="num">${cell(si,'et')}</td><td class="num">${cell(si,'bl')}</td><td class="num">${cell(si,'el')}</td></tr>`).join('')||`<tr><td colspan="7" class="empty">없음</td></tr>`;
        if(editMode) c.querySelectorAll('#sbody input').forEach(el=>{el.onclick=e=>e.stopPropagation();el.onchange=()=>{specs[+el.dataset.s][el.dataset.f]=el.value===''?null:(+el.value);};});
        c.querySelectorAll('#sbody tr[data-seq]').forEach(tr=>tr.onclick=()=>{msSeq=+tr.dataset.seq;c.querySelectorAll('#sbody tr').forEach(x=>x.classList.remove('sel'));tr.classList.add('sel');renderProc();});
        c.querySelector('#scnt').textContent=`${list.length} SPEC (순번 1~${list.length?Math.max(...list.map(o=>o.s.seq)):0})${editMode?' · ✎수정중':''}`;
      };
      c.querySelector('#smat').onchange=e=>{msMetal=e.target.value;msSeq=null;renderSpec();c.querySelector('#rbody').innerHTML='';c.querySelector('#rhead').innerHTML='<div class="s-item">← 좌측 소재SPEC 클릭</div>';};
      if(editMode){
        c.querySelector('#ssave').onclick=()=>{localStorage.setItem(lsk('resSpec'),JSON.stringify(specs));localStorage.setItem(lsk('resProc'),JSON.stringify(procD));editMode=false;draw();alert('저장되었습니다(브라우저 임시저장).\n실제 DB 반영은 신규 백엔드 연결 후.');};
        c.querySelector('#scancel').onclick=()=>{editMode=false;draw();};
        c.querySelector('#srevert').onclick=()=>{if(confirm('원본(CS_M_RES_PROC_RAW1/2)으로 되돌립니다.')){localStorage.removeItem(lsk('resSpec'));localStorage.removeItem(lsk('resProc'));editMode=false;draw();}};
      } else if(c.querySelector('#sedit')){ c.querySelector('#sedit').onclick=()=>{editMode=true;draw();}; }
      renderSpec(); if(msSeq!=null) renderProc();
      return;
    }
    data=load(m.key);
    const cols=m.cols;
    let metalOpts='',ymOpts='';
    if(m.filt){
      const metals=[...new Set(data.map(r=>r.metal))].filter(Boolean).sort();
      if(!metals.includes(fm)) fm=metals[0]||'CU';
      const ymsFor=x=>[...new Set(data.filter(r=>r.metal===x).map(r=>r.ym))].filter(Boolean).sort().reverse();
      if(!ymsFor(fm).includes(fy)) fy=ymsFor(fm)[0]||'';
      metalOpts=metals.map(x=>`<option value="${esc(x)}" ${x===fm?'selected':''}>${esc(x)} ${esc(metalNM[x]||'')}</option>`).join('');
      ymOpts=ymsFor(fm).map(y=>`<option value="${esc(y)}" ${y===fy?'selected':''}>${esc(y.slice(0,4))}/${esc(y.slice(4,6))}</option>`).join('');
    }
    const latestYm=x=>{const ys=[...new Set(data.filter(r=>r.metal===x).map(r=>r.ym))].filter(Boolean).sort();return ys[ys.length-1]||'';};
    const disp=(cc,r)=>{const v=r[cc.f];if(v==null||v==='')return '';if(cc.sel)return esc(''+v)+' '+esc(cc.sel[v]||'');if(cc.n)return won(v);return esc(''+v);};
    const inp=(cc,r,i)=>{
      const v=r[cc.f]!==undefined&&r[cc.f]!==null?r[cc.f]:'';
      if(cc.yn) return `<select data-i="${i}" data-f="${cc.f}"><option value="Y" ${v==='Y'?'selected':''}>Y</option><option value="N" ${v==='N'?'selected':''}>N</option></select>`;
      if(cc.sel) return `<select data-i="${i}" data-f="${cc.f}"><option value=""></option>${Object.entries(cc.sel).map(([k,nm])=>`<option value="${esc(k)}" ${v===k?'selected':''}>${esc(k)} ${esc(nm)}</option>`).join('')}</select>`;
      return `<input data-i="${i}" data-f="${cc.f}" class="cell ${cc.n?'num':''}" value="${esc(''+v)}" ${cc.n?'type="number" step="any"':''}>`;
    };
    const th=cols.map(cc=>`<th class="${cc.n?'num':''}">${cc.h}</th>`).join('')+(editMode?'<th class="center">삭제</th>':'');
    pane.innerHTML=`
     <div class="toolbar">
       ${m.filt?`<label class="tl">소재</label><select class="sel" id="fm">${metalOpts}</select><label class="tl">적용년월</label><select class="sel" id="fy">${ymOpts}</select>
         <span style="width:1px;height:20px;background:var(--line);margin:0 2px"></span><input class="inp" id="genym" placeholder="생성 YYYYMM" style="width:120px"><button class="btn" id="copyme" title="최신 년월 자료를 생성 년월로 복사">📋 LME단가 월복사</button>`:''}
       ${editMode
         ?`<button class="btn" id="save">💾 저장</button><button class="btn ghost" id="cancel">✖ 취소</button><button class="btn" id="add">➕ 추가</button><button class="btn ghost" id="revert">↩ 원본복원</button>`
         :(PERM.canEdit('devmaster')?`<button class="btn" id="edit">✎ 수정</button>`:`<span style="color:#c0392b;font-size:12px">🔒 수정권한 없음 (${esc(PERM.label())})</span>`)}
       <input class="inp" id="q" placeholder="검색"><div class="spacer"></div><span class="rowcount" id="cnt"></span></div>
     <div class="grid-wrap" style="max-height:540px;overflow:auto"><table class="tbl fit"><thead><tr>${th}</tr></thead><tbody id="tb"></tbody></table></div>`;
    const rend=()=>{
      const q=(c.querySelector('#q').value||'').trim().toLowerCase(), tb=c.querySelector('#tb');
      const vis=data.map((r,i)=>({r,i})).filter(({r})=>(!m.filt||(r.metal===fm&&r.ym===fy))&&(!q||cols.some(cc=>(''+(r[cc.f]!=null?r[cc.f]:'')).toLowerCase().includes(q))));
      tb.innerHTML=vis.map(({r,i})=>`<tr>${cols.map(cc=>`<td class="${cc.n?'num':''}">${editMode?inp(cc,r,i):disp(cc,r)}</td>`).join('')}${editMode?`<td class="center"><button class="btn xs ghost" data-del="${i}">✕</button></td>`:''}</tr>`).join('')||`<tr><td colspan="${cols.length+(editMode?1:0)}" class="empty">데이터 없음${editMode?' — ➕추가':''}</td></tr>`;
      if(editMode){
        tb.querySelectorAll('input,select').forEach(el=>el.onchange=()=>{const cc=cols.find(x=>x.f===el.dataset.f);data[+el.dataset.i][el.dataset.f]=cc&&cc.n?(+el.value||0):el.value;});
        tb.querySelectorAll('[data-del]').forEach(b=>b.onclick=()=>{data.splice(+b.dataset.del,1);rend();});
      }
      c.querySelector('#cnt').textContent=`${vis.length}건${m.filt?` / 전체 ${data.length}`:''} · ${editMode?'✎수정중':'읽기전용'}${localStorage.getItem(lsk(m.key))?' (임시저장분 반영)':''}`;
    };
    if(m.filt){ c.querySelector('#fm').onchange=e=>{fm=e.target.value;draw();}; c.querySelector('#fy').onchange=e=>{fy=e.target.value;rend();};
      c.querySelector('#copyme').onclick=()=>{
        const ny=(c.querySelector('#genym').value||'').replace(/\D/g,'');
        if(ny.length!==6){alert('생성할 년월을 YYYYMM 6자리로 입력하세요 (예: 202607)');return;}
        const sy=latestYm(fm);
        const src=data.filter(r=>r.metal===fm&&r.ym===sy);
        if(!src.length){alert('복사할 최신 자료가 없습니다.');return;}
        if(sy===ny){alert('최신 자료가 이미 '+ny+' 입니다.');return;}
        if(data.some(r=>r.metal===fm&&r.ym===ny)&&!confirm(`${metalNM[fm]||fm} ${ny} 데이터가 이미 있습니다.\n그래도 복사(추가)하시겠습니까?`))return;
        src.forEach(r=>data.push({...r,ym:ny}));
        localStorage.setItem(lsk(m.key),JSON.stringify(data)); fy=ny; draw();
        alert(`최신 ${sy} → ${ny} 로 ${src.length}건 단순복사 완료(임시저장).`);
      };
    }
    if(editMode){
      c.querySelector('#save').onclick=()=>{localStorage.setItem(lsk(m.key),JSON.stringify(data));editMode=false;draw();alert('저장되었습니다(브라우저 임시저장). 읽기전용으로 전환합니다.\n실제 DB 반영은 신규 백엔드 연결 후.');};
      c.querySelector('#cancel').onclick=()=>{editMode=false;draw();};
      c.querySelector('#add').onclick=()=>{const o={};cols.forEach(cc=>o[cc.f]=cc.yn?'Y':(cc.n?0:''));if(m.filt){o.metal=fm;o.ym=fy;}data.push(o);rend();};
      c.querySelector('#revert').onclick=()=>{if(confirm('원본(CS_M) 데이터로 되돌립니다. 임시저장분이 삭제됩니다.')){localStorage.removeItem(lsk(m.key));data=load(m.key);rend();}};
    } else if(c.querySelector('#edit')){
      c.querySelector('#edit').onclick=()=>{editMode=true;draw();};
    }
    c.querySelector('#q').onkeyup=rend;
    rend();
  };
  draw();
};

SCREEN.itembom=(c)=>{
  const metalNM={CU:'구리',STS:'STS',AL:'알루미늄',FE:'철','고강도':'고강도관'};
  const procs=DB.matSpecProcs||[], lsm='dm_matSpecItems';
  const loadMS=()=>{try{const s=localStorage.getItem(lsm);if(s)return JSON.parse(s);}catch(e){}return JSON.parse(JSON.stringify(DB.matSpecItems||[]));};
  let items=loadMS();
  const metals=[...new Set(items.map(r=>r.metal))].filter(Boolean).sort();
  let msMetal=metals.includes('CU')?'CU':(metals[0]||''); const msShow=new Set(procs.map(p=>p.code)); let editMode=false;
  const fixed=[['item','P/N'],['nm','품명'],['sg','소분류'],['diam','외경'],['thick','두께'],['metal','재질'],['unit','단위']];
  const API=API_BASE;
  let itab='gagong', assyD=null, assyLoad=false, assyQ='';   // ★탭: 가공품 공정ST / ASSY 조립공정
  const TAB=()=>{const t=(k,l)=>`<div class="it-tab" data-it="${k}" style="border:1px solid #d3ddec;border-bottom:none;background:${itab===k?'#fff':'#f1f5fb'};color:${itab===k?'#1c47a0':'#5a6b82'};padding:7px 16px;font-size:13px;font-weight:700;cursor:pointer;border-radius:8px 8px 0 0">${l}</div>`;
    return `<div style="display:flex;gap:2px;margin:6px 0 2px;border-bottom:2px solid #d3ddec">${t('gagong','가공품 공정 ST')}${t('assy','ASSY 조립공정')}</div>`;};
  const bindTab=()=>c.querySelectorAll('.it-tab').forEach(el=>el.onclick=()=>{itab=el.dataset.it;draw();});
  const startEdit=(td)=>{
    if(td.querySelector('input'))return;
    const ri=+td.dataset.ri, pc=td.dataset.pc, cur=(items[ri].wq&&items[ri].wq[pc])||0;
    td.innerHTML=`<input type="number" step="any" value="${cur}" style="width:66px">`;
    const el=td.querySelector('input'); el.focus(); el.select();
    const done=s=>{ if(s){const nv=+el.value||0; items[ri].wq=items[ri].wq||{}; if(nv)items[ri].wq[pc]=nv; else delete items[ri].wq[pc]; td.innerHTML=nv?won(nv):'<span style="color:#cfd6e0">·</span>'; td.style.background='#fff7d6';} else td.innerHTML=cur?won(cur):'<span style="color:#cfd6e0">·</span>'; };
    el.onblur=()=>done(1); el.onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();el.blur();}else if(e.key==='Escape'){el.onblur=null;done(0);}};
  };
  const drawGagong=()=>{
    c.innerHTML=`
     <div class="page-title">📋 품목별 공정관리 <span style="font-size:12px;color:var(--muted);font-weight:400">가공품 공정 ST</span></div>
     ${TAB()}
     <div class="page-sub"><b>품목별 공정 ST(WORK_QTY)</b> 매트릭스 · 원본 <code>CS_T_ITEM_PROC</code> · ✔라이브 견적원가(w_cs_esti_010) WORK_QTY 일치검증 · ✎수정 시 숫자 클릭 편집</div>
     <div class="toolbar">
       <label class="tl">소재</label><select class="sel" id="msmetal">${metals.map(x=>`<option value="${esc(x)}" ${x===msMetal?'selected':''}>${esc(x)} ${esc(metalNM[x]||'')}</option>`).join('')}</select>
       <input class="inp" id="msq" placeholder="P/N·품명·규격">
       ${editMode?`<button class="btn" id="mssave">💾 저장</button><button class="btn ghost" id="mscancel">✖ 취소</button><button class="btn ghost" id="msrevert">↩ 원본복원</button>`:(PERM.canEdit('itembom')?`<button class="btn" id="msedit">✎ 수정</button>`:`<span style="color:#c0392b;font-size:12px">🔒 수정권한 없음 (${esc(PERM.label())})</span>`)}
       <div class="spacer"></div><span class="rowcount" id="mscnt"></span></div>
     <div class="grid-wrap" style="max-height:540px;overflow:auto"><table class="tbl fit"><thead id="msth"></thead><tbody id="mstb"></tbody></table></div>`;
    const renderMS=()=>{
      const q=(c.querySelector('#msq').value||'').trim().toLowerCase();
      const pcs=procs;
      const allv=items.map((r,ri)=>({r,ri})).filter(({r})=>r.metal===msMetal&&(!q||(''+r.item+r.nm+(r.spec||'')).toLowerCase().includes(q)));
      const CAP=300, vis=allv.slice(0,CAP);
      c.querySelector('#msth').innerHTML=`<tr>${fixed.map(([f,h])=>`<th class="${['diam','thick'].includes(f)?'num':''}">${h}</th>`).join('')}${pcs.map(p=>`<th class="num" title="${esc(p.nm)}">${esc(p.nm)}</th>`).join('')}<th class="num" style="background:#eef4ff" title="공정 ST 합산">합계</th></tr>`;
      c.querySelector('#mstb').innerHTML=vis.map(({r,ri})=>`<tr>${fixed.map(([f])=>`<td class="${['diam','thick'].includes(f)?'num':'cap'}" title="${esc(''+(r[f]!=null?r[f]:''))}">${esc(''+(r[f]!=null?r[f]:''))}</td>`).join('')}${pcs.map(p=>{const v=(r.wq&&r.wq[p.code])||0;return `<td class="num ${editMode?'wqc':''}" ${editMode?`data-ri="${ri}" data-pc="${p.code}" style="cursor:pointer"`:''}>${v?won(v):'<span style="color:#cfd6e0">·</span>'}</td>`;}).join('')}${(t=>`<td class="num" style="font-weight:700;background:#f6f9ff">${t?won(t):'<span style="color:#cfd6e0">·</span>'}</td>`)(pcs.reduce((s,p)=>s+((r.wq&&r.wq[p.code])||0),0))}</tr>`).join('')||`<tr><td colspan="${fixed.length+pcs.length+1}" class="empty">결과 없음</td></tr>`;
      c.querySelector('#mscnt').textContent=`${allv.length}품목${allv.length>vis.length?` (상위 ${vis.length} 표시 — 검색으로 좁히세요)`:''} · ${pcs.length}공정 · ${editMode?'✎수정중(숫자클릭)':'읽기전용'}${localStorage.getItem(lsm)?' (임시저장 반영)':''}`;
    };
    if(editMode) c.querySelector('#mstb').addEventListener('click',e=>{const td=e.target.closest('.wqc');if(td)startEdit(td);});
    c.querySelector('#msmetal').onchange=e=>{msMetal=e.target.value;renderMS();};
    c.querySelector('#msq').onkeyup=renderMS;
    if(editMode){
      c.querySelector('#mssave').onclick=()=>{localStorage.setItem(lsm,JSON.stringify(items));editMode=false;draw();alert('저장되었습니다(브라우저 임시저장). 읽기전용 전환.\n실제 DB 반영은 신규 백엔드 연결 후.');};
      c.querySelector('#mscancel').onclick=()=>{items=loadMS();editMode=false;draw();};
      c.querySelector('#msrevert').onclick=()=>{if(confirm('원본(CS_T_ITEM_PROC)으로 되돌립니다. 임시저장분 삭제.')){localStorage.removeItem(lsm);items=loadMS();renderMS();}};
    } else if(c.querySelector('#msedit')){ c.querySelector('#msedit').onclick=()=>{editMode=true;draw();}; }
    renderMS();
    bindTab();
  };
  // ===== ASSY 조립공정 탭 — 제품(행) × 조립공정(열) · 소스 nx.routing(p_item=제품) = 내부원가 조립공정 팝업과 동일 =====
  const loadAssy=async()=>{assyLoad=true;renderAssy();
    try{const r=await fetch(`${API}/api/itemproc/assy?q=${encodeURIComponent(assyQ)}`);assyD=await r.json();}catch(e){assyD={error:e.message};}
    assyLoad=false;renderAssy();};
  const renderAssy=()=>{
    const b=c.querySelector('#asbody');if(!b)return;
    if(assyLoad){b.innerHTML='<div class="empty">조회 중…</div>';return;}
    if(!assyD){b.innerHTML='<div class="empty">제품 P/N·품명으로 조회하세요 (조립공정 보유 제품).</div>';return;}
    if(assyD.error){b.innerHTML=`<div class="page-sub" style="color:#c0392b">⚠ ${esc(assyD.error)}</div>`;return;}
    const cols=assyD.cols||[],rows=assyD.rows||[];
    const cnt=c.querySelector('#ascnt');if(cnt)cnt.textContent=`${rows.length}제품 · ${cols.length}조립공정${assyD.total_items>rows.length?` (전체 ${assyD.total_items} 중 상위 표시)`:''}`;
    b.innerHTML=`<div class="grid-wrap" style="max-height:560px;overflow:auto"><table class="tbl fit">
      <thead><tr><th style="text-align:left">P/N</th><th style="text-align:left">품명</th>${cols.map(cc=>`<th class="num" title="${esc(cc.name)} (${esc(cc.code)}·${esc(cc.group)})">${esc(cc.name)}</th>`).join('')}<th class="num" style="background:#eef4ff">합계</th></tr></thead>
      <tbody>${rows.map(r=>`<tr><td style="white-space:nowrap"><b>${esc(r.item)}</b></td><td class="cap" title="${esc(r.name)}" style="max-width:200px;overflow:hidden;text-overflow:ellipsis">${esc(r.name)}</td>${cols.map(cc=>{const v=r.wq[cc.code]||0;return `<td class="num">${v?won(v):'<span style="color:#cfd6e0">·</span>'}</td>`;}).join('')}<td class="num" style="font-weight:700;background:#f6f9ff">${won(r.total)}</td></tr>`).join('')||`<tr><td colspan="${cols.length+3}" class="empty">조립공정 보유 제품 없음</td></tr>`}</tbody></table></div>`;};
  const drawAssy=()=>{
    c.innerHTML=`
     <div class="page-title">📋 품목별 공정관리 <span style="font-size:12px;color:var(--muted);font-weight:400">ASSY 조립공정 (nx.routing · 내부원가 조립공정 팝업과 동일 소스)</span></div>
     ${TAB()}
     <div class="page-sub">제품(ASSY) × 조립공정(용접·은납·체결·포장) ST(work_qty) 매트릭스 · 소스 <code>nx.routing</code>(p_item=제품) · 편집은 [품목 BOM관리 › 내부원가 › 제품 조립공정 팝업]</div>
     <div class="toolbar"><input class="inp" id="asq" placeholder="제품 P/N·품명 검색" value="${esc(assyQ)}" style="width:260px"><button class="btn" id="asgo">🔍 조회</button>
       <div class="spacer"></div><span class="rowcount" id="ascnt"></span></div>
     <div id="asbody"></div>`;
    bindTab();
    const go=()=>{assyQ=(c.querySelector('#asq').value||'').trim();assyD=null;loadAssy();};
    c.querySelector('#asgo').onclick=go;
    c.querySelector('#asq').onkeyup=e=>{if(e.key==='Enter')go();};
    renderAssy();
    if(!assyD&&!assyLoad)loadAssy();
  };
  const draw=()=>{ if(itab==='gagong')drawGagong(); else drawAssy(); };
  draw();
};

SCREEN.costverify=(c)=>{
  const API=API_BASE;
  let item='AJR75563503', ymd='260630', data=null, loading=false, msg='';
  const ROWS=[['jae','재료비'],['gagong','가공비'],['ilban','일반관리비'],['unban','운반비'],['profit','이윤'],
              ['silwon','실원가',1],['lg','LG판가'],['sonik','손익',1]];
  const load=async()=>{
    if(!item.trim()){msg='품번을 입력하세요';draw();return;}
    loading=true;msg='';draw();
    try{
      const r=await fetch(`${API}/api/cost/compare?item=${encodeURIComponent(item.trim())}&ymd=${encodeURIComponent(ymd)}`);
      if(!r.ok)throw new Error('HTTP '+r.status);
      data=await r.json();
    }catch(e){msg='백엔드 연결 실패 — uvicorn app:app --port 8010 실행 필요';data=null;}
    loading=false;draw();
  };
  const draw=()=>{
    const sp=data&&data.sp||{}, nx=data&&data.nx||{}, df=data&&data.diff||{};
    const allZero=data&&data.diff&&ROWS.every(([k])=>Math.abs(df[k]||0)<1);
    const spErr=sp.error, nxErr=nx.error;
    c.innerHTML=`
     <div class="page-title">🔬 원가엔진 검증 (라이브)</div>
     <div class="page-sub">레거시 <code>SP_CS_견적서(실원가용)</code> vs <b>nx 원가엔진</b>(nx테이블 재계산) 성분별 대조 · durable 엔진 <code>nx_cost_engine.py</code> · 기준일 ${esc(ymd)}</div>
     <div class="toolbar">
       <label class="tl">품번</label><input class="inp" id="cv-item" value="${esc(item)}" placeholder="PART-NO" style="width:220px">
       <label class="tl" style="margin-left:8px">기준일(YYMMDD)</label><input class="inp" id="cv-ymd" value="${esc(ymd)}" style="width:110px">
       <button class="btn" id="cv-go">🔍 대조</button>
       ${loading?'<span style="color:var(--muted)">계산중…</span>':''}
       ${msg?`<span style="color:#c0392b">${esc(msg)}</span>`:''}
     </div>
     ${data?`
     <div class="ca-cards" style="margin:10px 0">
       <div class="ca-card ${allZero?'pos':'neg'}"><span>일치 여부</span><b>${allZero?'✔ 완전일치':'⚠ 차이있음'}</b></div>
       <div class="ca-card"><span>실원가(nx)</span><b>${nxErr?'-':won(nx.silwon||0)}</b></div>
       <div class="ca-card ${(nx.sonik||0)<0?'neg':'pos'}"><span>손익(nx)</span><b>${nxErr?'-':won(nx.sonik||0)}</b></div>
     </div>
     ${(spErr||nxErr)?`<div style="color:#c0392b;padding:8px">SP: ${esc(spErr||'ok')} / nx: ${esc(nxErr||'ok')}</div>`:`
     <table class="grid" style="max-width:560px"><thead><tr>
       <th>성분</th><th class="num">레거시 SP</th><th class="num">nx 엔진</th><th class="num">차이</th></tr></thead><tbody>
       ${ROWS.map(([k,nm,b])=>{const d=df[k]||0;return `<tr${b?' style="font-weight:700;background:var(--th,#f4f6fa)"':''}>
         <td>${esc(nm)}</td><td class="num">${won(sp[k]||0)}</td><td class="num">${won(nx[k]||0)}</td>
         <td class="num" style="color:${Math.abs(d)<1?'#27ae60':'#c0392b'}">${d===0?'0':won(d)}</td></tr>`;}).join('')}
     </tbody></table>`}`:'<div style="color:var(--muted);padding:16px">품번을 입력하고 대조를 누르세요. 예: AJR75563503(용접), AJR30064601(용접봉), PQ060903E30.AKOR(설치)</div>'}`;
    const gi=c.querySelector('#cv-item'); if(gi)gi.oninput=e=>item=e.target.value;
    const gy=c.querySelector('#cv-ymd'); if(gy)gy.oninput=e=>ymd=e.target.value;
    const gb=c.querySelector('#cv-go'); if(gb)gb.onclick=load;
    const onEnter=e=>{if(e.key==='Enter')load();};
    if(gi)gi.onkeydown=onEnter; if(gy)gy.onkeydown=onEnter;
  };
  draw();
};

SCREEN.delivery=(c)=>{
  const API=API_BASE;
  let item='', rows=[], msg='', calc=null, ordq=50, edit=null;
  const BASIS=['개당','박스당','파렛트당','발주당'];
  const LEVELS=['','박스','파렛트','앵글','비닐','기타'];
  const load=async()=>{
    if(!item.trim()){rows=[];draw();return;}
    try{const r=await fetch(`${API}/api/delivery/list?item=${encodeURIComponent(item.trim())}`);
      rows=(await r.json()).rows||[];}
    catch(e){msg='백엔드 연결 실패';rows=[];}
    draw();
  };
  const save=async(row)=>{
    try{const r=await fetch(`${API}/api/delivery/save`,{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({...row,item_code:item.trim()})});
      if(!(await r.json()).ok)throw 0; msg='저장됨'; edit=null; await load();}
    catch(e){msg='저장 실패';draw();}
  };
  const del=async(id)=>{ if(!confirm('삭제할까요?'))return;
    try{await fetch(`${API}/api/delivery/delete`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id})}); msg='삭제됨'; await load();}
    catch(e){msg='삭제 실패';draw();}
  };
  const runCalc=async()=>{
    try{const r=await fetch(`${API}/api/delivery/calc?item=${encodeURIComponent(item.trim())}&order_qty=${ordq}`);
      calc=(await r.json()).packs||[];}catch(e){calc=null;}
    draw();
  };
  const blank=()=>({id:null,seq:(rows.length+1),pack_item:'',pack_name:'',pack_level:'',use_basis:'개당',qty_per:1,units_per:'',ceiling:false,is_bom:false,remarks:''});
  const draw=()=>{
    const E=edit;
    const canW=(typeof PERM!=='undefined')?PERM.canEdit('delivery'):true;   // 수정권한 게이트(규칙#16)
    c.innerHTML=`
     <div class="page-title">📦 납품 포장/적재</div>
     <div class="page-sub">완제품별 포장자재 위계 · <code>nx.delivery_pack</code> · 개당/박스당/파렛트당/발주당 + 적재수량(units_per) + <b>CEILING(발주÷적재수량)</b> · 설치박스=BOM관리(is_bom)</div>
     <div class="toolbar">
       <label class="tl">완제품 품번</label><input class="inp" id="dv-item" value="${esc(item)}" placeholder="PART-NO" style="width:220px">
       <button class="btn" id="dv-go">🔍 조회</button>
       ${canW?`<button class="btn" id="dv-add" ${item.trim()?'':'disabled'}>＋ 행추가</button>`:`<span style="color:#c0392b;font-size:12px">🔒 수정권한 없음 (${esc((typeof PERM!=='undefined')?PERM.label():'')})</span>`}
       ${msg?`<span style="color:#2c7">${esc(msg)}</span>`:''}
     </div>
     <table class="grid"><thead><tr>
       <th>순번</th><th>포장자재코드</th><th>포장자재명</th><th>위계</th><th>소요기준</th><th class="num">기준당수량</th>
       <th class="num">적재수량</th><th>CEILING</th><th>BOM</th><th>비고</th><th></th></tr></thead><tbody>
       ${rows.map(r=>`<tr>
         <td>${r.seq}</td><td>${esc(r.pack_item)}</td><td>${esc(r.pack_name)}</td><td>${esc(r.pack_level)}</td>
         <td>${esc(r.use_basis)}</td><td class="num">${r.qty_per}</td><td class="num">${r.units_per||''}</td>
         <td>${r.ceiling?'✔':''}</td><td>${r.is_bom?'✔':''}</td><td>${esc(r.remarks)}</td>
         <td>${canW?`<button class="btn sm" data-ed="${r.id}">✎</button> <button class="btn sm" data-del="${r.id}">🗑</button>`:''}</td></tr>`).join('')
       ||`<tr><td colspan="11" class="empty">${item.trim()?'포장 구성이 없습니다. ＋행추가로 등록하세요.':'완제품 품번을 조회하세요'}</td></tr>`}
     </tbody></table>
     ${E?`<div class="card" style="margin-top:12px;padding:12px;border:1px solid var(--bd,#ddd);border-radius:8px;max-width:900px">
       <b>${E.id?'수정':'신규'} 포장행</b>
       <div class="toolbar" style="flex-wrap:wrap;gap:6px;margin-top:8px">
         <input class="inp" id="e-seq" value="${E.seq}" style="width:55px" title="순번">
         <input class="inp" id="e-pi" value="${esc(E.pack_item)}" placeholder="포장자재코드" style="width:130px">
         <input class="inp" id="e-pn" value="${esc(E.pack_name)}" placeholder="포장자재명" style="width:150px">
         <select class="inp" id="e-lv">${LEVELS.map(l=>`<option ${E.pack_level===l?'selected':''}>${l}</option>`).join('')}</select>
         <select class="inp" id="e-ub">${BASIS.map(b=>`<option ${E.use_basis===b?'selected':''}>${b}</option>`).join('')}</select>
         <input class="inp" id="e-qp" value="${E.qty_per}" placeholder="기준당" style="width:70px" title="기준당 소요수량">
         <input class="inp" id="e-up" value="${E.units_per||''}" placeholder="적재수량" style="width:80px" title="이 포장1개에 담는 제품수(LG지정)">
         <label class="chk"><input type="checkbox" id="e-ce" ${E.ceiling?'checked':''}> CEILING</label>
         <label class="chk"><input type="checkbox" id="e-bm" ${E.is_bom?'checked':''}> BOM관리</label>
         <input class="inp" id="e-rm" value="${esc(E.remarks)}" placeholder="비고" style="width:140px">
         <button class="btn" id="e-save">💾 저장</button><button class="btn" id="e-cancel">취소</button>
       </div></div>`:''}
     <div class="card" style="margin-top:14px;padding:12px;border:1px dashed var(--bd,#ccc);border-radius:8px;max-width:640px">
       <b>🧮 발주수량 → 포장 소요 계산</b>
       <div class="toolbar" style="margin-top:6px">
         <label class="tl">발주수량</label><input class="inp" id="dv-oq" value="${ordq}" style="width:90px">
         <button class="btn" id="dv-calc" ${item.trim()?'':'disabled'}>계산</button>
       </div>
       ${calc?`<table class="grid" style="max-width:560px"><thead><tr><th>포장</th><th>기준</th><th class="num">적재수량</th><th class="num">소요</th></tr></thead>
         <tbody>${calc.map(x=>`<tr><td>${esc(x.pack)}</td><td>${esc(x.basis)}</td><td class="num">${x.units_per||''}</td><td class="num"><b>${x.need}</b></td></tr>`).join('')||'<tr><td colspan="4" class="empty">포장구성 없음</td></tr>'}</tbody></table>`:''}
     </div>`;
    const q=(id)=>c.querySelector(id);
    if(q('#dv-item'))q('#dv-item').oninput=e=>item=e.target.value;
    if(q('#dv-go'))q('#dv-go').onclick=load;
    if(q('#dv-add'))q('#dv-add').onclick=()=>{edit=blank();draw();};
    if(q('#dv-oq'))q('#dv-oq').oninput=e=>ordq=parseFloat(e.target.value)||0;
    if(q('#dv-calc'))q('#dv-calc').onclick=runCalc;
    c.querySelectorAll('[data-ed]').forEach(b=>b.onclick=()=>{edit={...rows.find(r=>r.id==b.dataset.ed)};draw();});
    c.querySelectorAll('[data-del]').forEach(b=>b.onclick=()=>del(parseInt(b.dataset.del)));
    if(q('#e-cancel'))q('#e-cancel').onclick=()=>{edit=null;draw();};
    if(q('#e-save'))q('#e-save').onclick=()=>save({
      id:E.id,seq:parseInt(q('#e-seq').value)||1,pack_item:q('#e-pi').value,pack_name:q('#e-pn').value,
      pack_level:q('#e-lv').value,use_basis:q('#e-ub').value,qty_per:parseFloat(q('#e-qp').value)||0,
      units_per:q('#e-up').value,ceiling:q('#e-ce').checked,is_bom:q('#e-bm').checked,remarks:q('#e-rm').value});
  };
  draw();
};

SCREEN.costanalysis=(c)=>{
  let D=window.COSTDATA||{rows:[],agg:{},ym:'',base:''};
  // ★UI 날짜 규칙: 날짜범위=당월1일~당일 · 월=당월 · 일자=당일 (동적)
  const _t=new Date(), _p=n=>String(n).padStart(2,'0');
  const _TODAY=`${_t.getFullYear()}-${_p(_t.getMonth()+1)}-${_p(_t.getDate())}`;
  const _MFIRST=`${_t.getFullYear()}-${_p(_t.getMonth()+1)}-01`;
  const _CURYM=`${String(_t.getFullYear()).slice(2)}${_p(_t.getMonth()+1)}`;         // YYMM(당월)
  const _CURDYMD=_TODAY.slice(2).replace(/-/g,'');                                    // YYMMDD(당일)
  let R=D.rows||[], A=D.agg||{};   // ★실시간(nx): loadRecv가 재구성. 초기값=기존 스냅샷(있으면)
  const eok=v=>(v/1e8).toFixed(1);
  const pct=v=>(v*100).toFixed(1)+'%';
  // [rowIdx, header, group, opts]
  const NUM=[[1,'입고수량','',{}],
    [2,'원자재비','내부용',{}],[3,'부자재비','내부용',{}],[4,'LG사급비','내부용',{}],[23,'실사급금액','내부용',{}],[5,'재료비합계','내부용',{}],[6,'원가','내부용',{b:1}],[7,'재료비율','내부용',{pct:1}],
    [8,'원자재비','실원가',{}],[9,'부자재비','실원가',{}],[10,'LG사급비','실원가',{}],[24,'실사급금액','실원가',{}],[11,'재료비합계','실원가',{}],[12,'실원가','실원가',{b:1}],[13,'가공비','실원가',{}],[14,'일반관리','실원가',{}],[15,'운반비','실원가',{}],[16,'이윤','실원가',{}],[17,'사급차액','실원가',{sk:1}],[18,'재료비율','실원가',{pct:1}],
    [19,'LG단가','LG단가·손익',{}],[20,'LG총금액','LG단가·손익',{}],[21,'손익','LG단가·손익',{sk:1}],[22,'Impact','LG단가·손익',{sk:1,b:1}]];
  let mode='recv', q='', lossOnly=false, sortI=20, dir=-1, dItem='';   // 기본정렬=LG총금액(20) 내림차순
  const API=API_BASE;
  let dLive=null, dLoading=false, dErr='';   // 직접입력=라이브 조회 결과(단품)
  let dYmd=_CURDYMD;               // 단가 적용일자(YYMMDD) — 당일(사용자 지정: 일자=당일)
  const ymd2date=(y)=>y&&y.length===6?`20${y.slice(0,2)}-${y.slice(2,4)}-${y.slice(4,6)}`:'';   // YYMMDD→date
  const date2ymd=(d)=>d?d.slice(2).replace(/-/g,''):'';                                          // date→YYMMDD
  // 리시빙실적(벌크) 단가 적용일자 — 변경 시 nx엔진 전체 재계산(백그라운드)
  let rvYmd=_CURDYMD, regenMsg='', regenPoll=null;   // ★단가 적용일자=당일(사용자 지정: 일자=당일)
  const setRegenMsg=(m)=>{regenMsg=m;const el=c.querySelector('#ca-regen-msg');if(el)el.textContent=m;};
  const doRegen=async()=>{
    if(!confirm(`단가 적용일자 ${ymd2date(rvYmd)} 기준으로 589품목을 재계산합니다.\n수 분 소요되며 완료 후 자동 새로고침됩니다. 진행할까요?`))return;
    try{
      const r=await fetch(`${API}/api/cost/regen`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({ymd:rvYmd})});
      if(r.status===409){setRegenMsg('이미 재계산 중…');}
      else if(!r.ok)throw new Error('HTTP '+r.status);
      if(regenPoll)clearInterval(regenPoll);
      regenPoll=setInterval(async()=>{
        try{const s=await(await fetch(`${API}/api/cost/regen/status`)).json();
          if(s.running){setRegenMsg(`재계산 중… ${s.done}/${s.total||'?'}`);}
          else{clearInterval(regenPoll);
            if(s.error){setRegenMsg('오류: '+s.error);}
            else{setRegenMsg(`완료 (${s.sec}s) — 새로고침…`);setTimeout(()=>location.reload(),900);}}
        }catch(e){clearInterval(regenPoll);setRegenMsg('상태 조회 실패');}
      },2000);
    }catch(e){setRegenMsg('재계산 시작 실패 — 백엔드 확인');}
  };
  // /api/esti 응답 → 23컬럼 행배열 (내부용+실원가+LG+손익, 수량1 단품)
  const estiToRow=(part,j)=>{
    const s=(j.sil&&j.sil.agg)||{}, n=(j.nae&&j.nae.agg)||{};
    const r=new Array(23).fill(0); r[0]=part; r[1]=1;
    r[2]=n.WON_JAI_AMT||0; r[3]=n.BU_JAI_AMT||0; r[4]=n.SA_JAI_AMT||0; r[5]=n.JAI_COST||0; r[6]=n.TOT_AMT||0; r[7]=(n.TOT_AMT&&s.LG_COST)?n.JAI_COST/s.LG_COST:0;
    r[8]=s.WON_JAI_AMT||0; r[9]=s.BU_JAI_AMT||0; r[10]=s.SA_JAI_AMT||0; r[11]=s.JAI_COST||0; r[12]=s.TOT_AMT||0;
    r[13]=s.GAGONG_AMT||0; r[14]=s.ILBAN_AMT||0; r[15]=s.UNBAN_AMT||0; r[16]=s.PROFIT_AMT||0; r[17]=s.LME_CHA_AMT||0;
    r[18]=s.LG_COST?(s.JAI_COST/s.LG_COST):0; r[19]=s.LG_COST||0; r[20]=s.LG_COST||0; r[21]=(s.LG_COST||0)-(s.TOT_AMT||0); r[22]=r[21];
    return r;
  };
  const dLoad=async()=>{
    const it=dItem.trim(); if(!it){dLive=null;renderBody();return;}
    dLoading=true;dErr='';renderBody();
    try{const r=await fetch(`${API}/api/esti?item=${encodeURIComponent(it)}&ymd=${encodeURIComponent(dYmd)}`);
      if(!r.ok)throw new Error('HTTP '+r.status); const j=await r.json();
      dLive=estiToRow(it,j);}
    catch(e){dErr='백엔드 연결 실패 — uvicorn app:app --port 8010 실행 필요';dLive=null;}
    dLoading=false;renderBody();
  };
  // ★리시빙실적 실시간(nx): 목록(SA_T_LG_RECEIVING_DTL)+행별 배치 원가(/api/cost/nx/bulk). 스냅샷 파일 대체·세션캐시.
  const ym2str=(y)=>(y&&y.length===6)?`20${y.slice(0,2)}-${y.slice(2,4)}-${y.slice(4,6)}`:(y||'');
  const buildRow=(part,qty,cst)=>{const r=new Array(25).fill(0);r[0]=part;r[1]=qty;
    if(cst&&!cst.error){const jae=cst.jae||0,lg=cst.lg||0,sil=cst.silwon||0,son=cst.sonik||0,sagub=cst.sagub||0;
      const won=(cst.won!=null?cst.won:jae),bu=cst.bu||0,sa=cst.sa||0,matb=won+bu+sa;   // 원자재/부자재/LG사급 분리(sgroup)
      const son2=son+sagub;   // 손익 = (LG−실원가) + 사급차액(실출고가−실입고가, 음수=손해)
      r[2]=won;r[3]=bu;r[4]=sa;r[5]=matb;r[6]=sil;r[7]=lg?matb/lg:0;
      r[8]=won;r[9]=bu;r[10]=sa;r[11]=matb;r[12]=sil;r[13]=cst.gagong||0;r[14]=cst.ilban||0;r[15]=cst.unban||0;r[16]=cst.profit||0;r[17]=sagub;r[18]=lg?matb/lg:0;
      r[19]=lg;r[20]=lg*qty;r[21]=son2;r[22]=son2*qty;
      r[23]=cst.silsagub||0;r[24]=cst.silsagub||0;}   // ★실사급금액(통째,기준일사급가) — 나란히 표시(원가/손익 무영향)
    return r;};
  const cardsHTML=()=>`<div class="ca-card"><span>LG 매출</span><b>${eok(A.sales||0)}억</b></div>
       <div class="ca-card"><span>실원가 총금액</span><b>${eok(A.silamt||0)}억</b></div>
       <div class="ca-card ${(A.impact||0)>=0?'pos':'neg'}"><span>손익 Impact</span><b>${(A.impact||0)>=0?'+':''}${eok(A.impact||0)}억</b></div>
       <div class="ca-card neg"><span>적자 품번</span><b>${won(A.loss||0)}<small>/${won(A.cnt||0)}</small></b></div>`;
  const recomputeAgg=()=>{let sales=0,silamt=0,impact=0,loss=0,qt=0;D.rows.forEach(r=>{sales+=r[20];silamt+=r[12]*r[1];impact+=r[22];qt+=r[1];if(r[21]<0)loss++;});
    D.agg={cnt:D.rows.length,qty:Math.round(qt),sales:Math.round(sales),silamt:Math.round(silamt),impact:Math.round(impact),loss};A=D.agg;
    const cd=c.querySelector('.ca-cards');if(cd)cd.innerHTML=cardsHTML();};
  let rvBusy=false;
  const loadRecv=async(ym,ymd,force)=>{
    if(rvBusy)return;rvBusy=true;ymd=ymd||rvYmd;const tok=ymd+'|'+(ym||'');loadRecv._tok=tok;setRegenMsg('목록 로드…');
    try{
      // ★서버 결과캐시 우선(첫 로드 즉시화). force(재계산)면 스킵.
      if(!force){
        try{const cg=await(await fetch(`${API}/api/cost/analysis/cache/get?ym=${encodeURIComponent(ym||'')}&ymd=${encodeURIComponent(ymd)}`)).json();
          if(cg&&cg.cached&&cg.rows&&cg.rows.length&&loadRecv._tok===tok){
            D.ym=cg.ym||ym||'';D.base=ymd;dYmd=ymd;rvYmd=ymd;
            D.rows=cg.rows.map(x=>buildRow(x.part,x.qty,x));R=D.rows;recomputeAgg();
            window.__CA_LIVE={ymd,ym:D.ym,rows:D.rows,agg:D.agg};
            setRegenMsg(`캐시 ${cg.upd||''} · 최신화=재계산 버튼`);
            rvBusy=false;renderBody();return;
          }
        }catch(e){}
      }
      const lr=await(await fetch(`${API}/api/cost/analysis/list?ym=${encodeURIComponent(ym||'')}`)).json();
      const list=lr.rows||[];D.ym=lr.ym||ym||'';D.base=ymd;dYmd=ymd;rvYmd=ymd;
      D.rows=list.map(x=>buildRow(x.part,x.qty,null));R=D.rows;recomputeAgg();renderBody();
      // ★속도: 청크 35 + 6개 동시(병렬) — 무거운 품목(복합SUB)을 여러 워커로 분산. + 남은시간(ETA) 표시.
      const CH=35, PAR=6; let done=0; const t0=Date.now(); const liveCC={};
      const chunks=[]; for(let i=0;i<list.length;i+=CH)chunks.push({start:i,items:list.slice(i,i+CH)});
      for(let b=0;b<chunks.length;b+=PAR){
        if(loadRecv._tok!==tok)break;
        await Promise.all(chunks.slice(b,b+PAR).map(async(ck)=>{
          let cc={};
          try{cc=(await(await fetch(`${API}/api/cost/nx/bulk`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({parts:ck.items.map(x=>x.part),ymd,ym:(ym||D.ym||'')})})).json()).costs||{};}catch(e){}
          ck.items.forEach((x,j)=>{liveCC[x.part]=cc[x.part]||{};D.rows[ck.start+j]=buildRow(x.part,x.qty,cc[x.part]);});
          done+=ck.items.length;
          // ★청크 완료마다 진행표시 갱신(라운드 끝까지 안 기다림 = 멈춘 듯 안 보임)
          if(loadRecv._tok===tok){const el=(Date.now()-t0)/1000,eta=done?Math.ceil((list.length-done)*el/done):0;setRegenMsg(`실시간 계산 ${done}/${list.length} · 약 ${eta}초 남음`);renderBody();}
        }));
        if(loadRecv._tok!==tok)break;
        const el=(Date.now()-t0)/1000, eta=done?Math.ceil((list.length-done)*el/done):0;
        setRegenMsg(`실시간 계산 ${done}/${list.length} · 약 ${eta}초 남음`);renderBody();
      }
      recomputeAgg();
      if(loadRecv._tok===tok){window.__CA_LIVE={ymd,ym:D.ym,rows:D.rows,agg:D.agg};
        // ★계산결과 서버캐시 저장 → 다음 진입·타 사용자 즉시(엔진 재계산 불요)
        try{const saveRows=list.map(x=>Object.assign({part:x.part,qty:x.qty},liveCC[x.part]||{}));
          fetch(`${API}/api/cost/analysis/cache/save`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({ym:D.ym,ymd,rows:saveRows})});}catch(e){}
        setRegenMsg('완료 · 캐시 저장됨');
      }
    }catch(e){setRegenMsg('로드 실패 — 백엔드 확인');}
    finally{rvBusy=false;renderBody();}
  };
  // 표시 컬럼: 직접입력은 입고수량(1)·LG총금액(20)·Impact(22) 제외 (수량 1 단품 관점)
  const colsOf=()=> mode==='direct'? NUM.filter(([i])=>![1,20,22].includes(i)) : NUM;
  const filt=()=>{
    if(mode==='direct'){ return dLive?[dLive]:[]; }   // 직접입력=라이브 단품
    let a=R.slice();
    if(q){const ql=q.toLowerCase();a=a.filter(r=>r[0].toLowerCase().includes(ql));} if(lossOnly)a=a.filter(r=>r[21]<0);
    a.sort((x,y)=>sortI<0?x[0].localeCompare(y[0])*dir:(x[sortI]-y[sortI])*dir);
    return a;
  };
  const renderBody=()=>{
    const a=filt(), cols=colsOf();
    // ★로딩 중(리시빙): 값이 계속 바뀌어 착각하므로 값 대신 "조회 중" 전체 표시(완료 후 1회 렌더)
    if(mode!=='direct' && rvBusy){
      const cb=c.querySelector('#ca-body'); if(cb)cb.innerHTML=`<tr><td colspan="${cols.length+1}" class="empty" style="padding:44px 0"><span style="display:inline-flex;align-items:center;gap:10px;color:#2f5aa8;font-weight:700;font-size:15px"><span class="ca-spin"></span> 조회 중… <span style="color:#8595ad;font-weight:500;font-size:13px">${esc(regenMsg||'')}</span></span></td></tr>`;
      const ft=c.querySelector('#ca-foot'); if(ft)ft.innerHTML='';
      const cn=c.querySelector('#ca-cnt'); if(cn)cn.textContent='조회 중…';
      return;
    }
    c.querySelector('#ca-body').innerHTML = a.map(r=>{const neg=r[21]<0;
      return `<tr class="${neg?'lossrow':''}"><td class="pcode" title="${esc(r[0])}"><b>${esc(r[0])}</b></td>`+
        cols.map(([i,,,op])=>{let cls='num';if(op.b)cls+=' bcol';if(op.sk&&r[i]<0)cls+=' negv';if(op.sk&&r[i]>0)cls+=' posv';
          return `<td class="${cls}">${op.pct?pct(r[i]):wonI(r[i])}</td>`;}).join('')+`</tr>`;}).join('')
      || `<tr><td colspan="${cols.length+1}" class="empty">${mode==='direct'?(dLoading?'라이브 계산중…':(dErr||'품번을 입력하고 조회 (라이브 · 아무 품번, 예: AJR75563503)')):(rvBusy?'<span style="display:inline-flex;align-items:center;gap:8px;color:#2f5aa8;font-weight:600"><span class="ca-spin"></span> 조회 중…</span>':'결과 없음')}</td></tr>`;
    if(mode!=='direct'){
      // 합계 = Σ(수량 × 단위금액). LG총금액(20)·Impact(22)는 이미 행별 총액이라 그대로 합산. 재료비율=Σ재료비/LG총매출.
      const T={}; NUM.forEach(([i,,,o])=>{if(!o.pct)T[i]=0;});
      a.forEach(r=>{const q2=r[1];NUM.forEach(([i,,,op])=>{if(op.pct)return;T[i]+=(i===1)?q2:(i===20||i===22)?r[i]:r[i]*q2;});});
      const lgTot=T[20]||0, rN=lgTot?T[5]/lgTot:0, rS=lgTot?T[11]/lgTot:0;
      c.querySelector('#ca-foot').innerHTML=`<tr class="sumrow"><td>합계 ${won(a.length)}건</td>`+
        NUM.map(([i,,,op])=>{const v=(i===7)?pct(rN):(i===18)?pct(rS):(op.pct?'':won(Math.round(T[i])));
          let cls='num';if(op.b)cls+=' bcol';if(op.sk&&T[i]<0)cls+=' negv';if(op.sk&&T[i]>0)cls+=' posv';
          return `<td class="${cls}">${v}</td>`;}).join('')+`</tr>`;
    }else c.querySelector('#ca-foot').innerHTML='';
    const cnt=c.querySelector('#ca-cnt'); if(cnt)cnt.textContent=`${a.length}품번${mode==='direct'?' (부분일치)':(lossOnly?' · 적자만':'')}`;
  };
  const caExport=()=>{
    const a=filt(), cols=colsOf();
    const header=['PART-NO', ...cols.map(x=>x[1])];
    const rows=a.map(r=>[r[0], ...cols.map(([i,,,op])=>op.pct?(r[i]*100).toFixed(1)+'%':r[i])]);
    dlCSV(`품목별원가분석_${mode==='recv'?'리시빙실적':'직접입력'}_${(D.base||'')}.csv`, header, rows);
  };
  // 헤더(그룹+컬럼) — 모드별. 직접입력은 입고수량 제외, LG그룹 2컬럼(LG단가·손익).
  const headHTML=()=>{
    const lgSpan=mode==='direct'?2:4;
    let g1='<th rowspan="2">PART-NO</th>'+(mode!=='direct'?'<th rowspan="2" class="num">입고수량</th>':'');
    g1+=`<th colspan="7" class="ghead">내부용</th><th colspan="12" class="ghead">실원가</th><th colspan="${lgSpan}" class="ghead">LG단가·손익</th>`;
    const h2=colsOf().filter(([i])=>i!==1).map(([i,h])=>`<th class="num sortable ${sortI===i?'sorted':''}" data-si="${i}">${h}${sortI===i?(dir<0?' ▼':' ▲'):''}</th>`).join('');
    return `<thead><tr>${g1}</tr><tr>${h2}</tr></thead>`;
  };
  const directBar=()=>`
     <div class="toolbar">
       <label class="tl">품번</label>
       <input class="inp" id="di-q" value="${esc(dItem)}" placeholder="PART-NO 입력 (예: AJR75563503)" style="width:220px">
       <label class="tl" style="margin-left:8px">단가 적용일자</label>
       <input class="inp" type="date" id="di-ymd" value="${ymd2date(dYmd)}" style="width:150px" title="이 날짜 기준 LG인정가(TAGE)·LME시세·매입가·임율 적용">
       <button class="btn" id="di-go">🔍 라이브 조회</button>
       <span style="color:var(--muted);font-size:12px">그 날짜 기준 단가 적용 · 아무 품번 · 수량1 단위원가·손익</span>
       <button class="btn" id="ca-xls" title="현재 목록 엑셀(CSV) 다운로드">⬇ 엑셀</button>
       <div class="spacer"></div><span class="rowcount" id="ca-cnt"></span>
     </div>`;
  const recvBar=()=>`
     <div class="ca-cards">
       <div class="ca-card"><span>LG 매출</span><b>${eok(A.sales||0)}억</b></div>
       <div class="ca-card"><span>실원가 총금액</span><b>${eok(A.silamt||0)}억</b></div>
       <div class="ca-card pos"><span>손익 Impact</span><b>+${eok(A.impact||0)}억</b></div>
       <div class="ca-card neg"><span>적자 품번</span><b>${won(A.loss||0)}<small>/${won(A.cnt||0)}</small></b></div>
     </div>
     <div class="toolbar">
       <label class="tl">리시빙 기간</label>
       <input class="inp" type="date" id="ca-from" value="${_MFIRST}" style="width:140px"><span style="color:var(--muted)">~</span>
       <input class="inp" type="date" id="ca-to" value="${_TODAY}" style="width:140px">
       <span class="badge" title="최대 조회기간 1개월">최대 1개월</span>
       <button class="btn" id="ca-go">🔍 조회</button>
       <div class="spacer" style="max-width:20px"></div>
       ${(typeof PERM==='undefined'||PERM.canEdit('costanalysis'))?`<label class="tl" title="이 날짜 기준 LG인정가(TAGE)·LME시세·매입가·임율로 전체 재계산">💲 단가 적용일자</label>
       <input class="inp" type="date" id="ca-ymd" value="${ymd2date(rvYmd)}" style="width:150px">
       <button class="btn" id="ca-regen" title="지정 단가일자로 nx엔진 재계산">🔄 재계산</button>`:`<span style="color:#c0392b;font-size:12px">🔒 재계산 권한 없음 (${esc((typeof PERM!=='undefined')?PERM.label():'')})</span>`}
       <label class="tl" style="margin-left:8px">품번</label><input class="inp" id="ca-q" value="${esc(q)}" placeholder="PART-NO 검색(타이핑하면 필터)" style="width:180px" autocomplete="off">
       <label class="chk"><input type="checkbox" id="ca-loss" ${lossOnly?'checked':''}> 적자만</label>
       <button class="btn" id="ca-xls" title="현재 목록 엑셀(CSV) 다운로드">⬇ 엑셀</button>
       <div class="spacer"></div><span class="rowcount" id="ca-cnt"></span>
     </div>`;
  const draw=()=>{
    c.innerHTML=`
     <div class="page-title">💹 품목별 원가분석</div>
     <div class="page-sub">품목별 <b>내부원가·실원가·손익</b> · 원본 <code>w_cs_esti_020</code> · <b>nx 엔진 재계산</b>(실원가·LME·손익, <code>nx_cost_engine.py</code> 검증완료) · 라이브검증=개발›원가엔진 검증 · 기준일 ${esc(D.base||'')}</div>
     ${recvBar()}
     <div class="grid-wrap ca-wrap"><table class="tbl ca-tbl">${headHTML()}<tbody id="ca-body"></tbody><tfoot id="ca-foot"></tfoot></table></div>
     <style>
       .ca-modes{display:flex;margin:10px 0 2px;border:1px solid var(--line);border-radius:8px;overflow:hidden;width:fit-content}
       .ca-mode{padding:7px 18px;border:none;background:#fff;cursor:pointer;font-size:13px;font-weight:600;color:var(--muted)}
       .ca-mode.on{background:#2f5aa8;color:#fff}
       .ca-cards{display:flex;gap:12px;margin:10px 0 4px;flex-wrap:wrap}
       .ca-card{flex:1;min-width:130px;background:#fff;border:1px solid var(--line);border-radius:10px;padding:11px 14px}
       .ca-card span{display:block;font-size:12px;color:var(--muted)}.ca-card b{font-size:22px;font-weight:800}
       .ca-card.pos b{color:#1f8a5a}.ca-card.neg b{color:#c0392b}.ca-card small{font-size:13px;color:var(--muted);font-weight:600}
       .ca-wrap{max-height:calc(100vh - 310px);overflow:auto;max-width:100%;width:100%;box-sizing:border-box}
       .ca-tbl{font-size:13px;table-layout:auto}
       .ca-tbl th,.ca-tbl td{padding:4px 6px}
       .ca-tbl td.num,.ca-tbl th.num{font-variant-numeric:tabular-nums}
       .ca-tbl th.ghead{background:#eef4ff;text-align:center;color:#2f5aa8;font-weight:700}
       .ca-tbl th.sortable{cursor:pointer;white-space:nowrap}.ca-tbl th.sorted{background:#dfe9ff;color:#1c47a0}
       .ca-tbl thead th{height:26px;box-sizing:border-box;white-space:nowrap;background:#f4f7fc}
       .ca-tbl thead tr:first-child th{position:sticky;top:0;z-index:4}
       .ca-tbl thead tr:nth-child(2) th{position:sticky;top:26px;z-index:4}
       .ca-tbl td.bcol{background:#f6f9ff;font-weight:700}
       .ca-tbl td.pcode{max-width:92px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
       .ca-tbl thead tr:first-child th:first-child{max-width:92px}
       .ca-tbl tr.lossrow td.pcode{color:#c0392b;font-weight:600}
       .ca-tbl td.negv{color:#c0392b;font-weight:700}.ca-tbl td.posv{color:#1f8a5a}
       .ca-tbl tfoot td{position:sticky;bottom:0;background:#f0f4fb;font-weight:700;border-top:2px solid #cdd9ef}
       .chk{display:inline-flex;align-items:center;gap:4px;font-size:13px;color:var(--muted);margin:0 4px}
       .ca-spin{width:16px;height:16px;border:3px solid #cdd9ef;border-top-color:#2f5aa8;border-radius:50%;display:inline-block;animation:caspin .7s linear infinite}
       @keyframes caspin{to{transform:rotate(360deg)}}
     </style>`;
    renderBody();
    {const xls=c.querySelector('#ca-xls'); if(xls)xls.onclick=caExport;}
    c.querySelectorAll('.ca-mode').forEach(b=>b.onclick=()=>{mode=b.dataset.mode; if(mode==='recv')sortI=20; else if([1,20,22].includes(sortI))sortI=21; dir=-1; draw();});
    // ★정렬 = 클라이언트만(draw 전체재렌더/재조회 금지). 헤더(정렬표시)만 교체+재바인딩 후 body만 갱신.
    const bindSort=()=>c.querySelectorAll('th.sortable').forEach(th=>th.onclick=()=>{
      const si=+th.dataset.si; if(sortI===si)dir=-dir; else{sortI=si;dir=-1;}
      const th0=c.querySelector('.ca-tbl thead'); if(th0){th0.outerHTML=headHTML();bindSort();}
      renderBody();
    });
    bindSort();
    if(mode==='recv'){
      c.querySelector('#ca-go').onclick=()=>{
        const f=c.querySelector('#ca-from').value;
        const ym=f?f.slice(2,7).replace('-',''):'';   // YYYY-MM-DD → YYMM(리시빙 월)
        loadRecv._tok=null; loadRecv(ym, rvYmd);       // 실시간 재로드(목록+원가)
      };
      c.querySelector('#ca-q').oninput=e=>{q=e.target.value.trim();renderBody();};
      c.querySelector('#ca-loss').onchange=e=>{lossOnly=e.target.checked;renderBody();};
      const cy=c.querySelector('#ca-ymd'); if(cy)cy.onchange=e=>{rvYmd=date2ymd(e.target.value);};
      const cr=c.querySelector('#ca-regen'); if(cr)cr.onclick=()=>{loadRecv._tok=null; loadRecv(D.ym||'', rvYmd, true);};   // 재계산=캐시무시 강제 재계산+재저장
      // ★자동 초기로드/세션캐시: 진입 시 실시간 계산(캐시 있으면 즉시 복원)
      if(!rvBusy && !loadRecv._tok){
        if(window.__CA_LIVE&&window.__CA_LIVE.ymd===rvYmd){D.rows=window.__CA_LIVE.rows;D.agg=window.__CA_LIVE.agg;D.ym=window.__CA_LIVE.ym;D.base=window.__CA_LIVE.ymd;R=D.rows;A=D.agg;loadRecv._tok='cache';recomputeAgg();renderBody();}
        else loadRecv(_CURYM, rvYmd);   // ★기본 당월 리시빙
      }
    }else{
      const dq=c.querySelector('#di-q'), dyv=c.querySelector('#di-ymd');
      const goLive=()=>{dItem=dq.value||'';if(dyv&&dyv.value)dYmd=date2ymd(dyv.value);dLoad();};
      c.querySelector('#di-go').onclick=goLive;
      dq.oninput=e=>{dItem=e.target.value;};
      dq.onkeydown=e=>{if(e.key==='Enter')goLive();};
      if(dyv)dyv.onchange=e=>{dYmd=date2ymd(e.target.value);if(dItem.trim())goLive();};
    }
  };
  draw();
};

SCREEN.esticost=(c)=>{
  const API=API_BASE;
  const canW=(typeof PERM!=='undefined')?PERM.canEdit('esticost'):true;
  const ymd2date=y=>(y&&y.length===6)?`20${y.slice(0,2)}-${y.slice(2,4)}-${y.slice(4,6)}`:'';
  const date2ymd=d=>d?d.slice(2).replace(/-/g,''):'';
  const nfq=v=>{v=Number(v||0);return v%1===0?v.toLocaleString('ko-KR'):v.toFixed(4).replace(/0+$/,'').replace(/\.$/,'');};
  const STC={'작성':'#8a6d1e','승인':'#1c7c3a','반려':'#c0392b'};
  let q='', slist=[], searching=false, msg='';
  let head={esti_no:'',item_code:'',item_name:'',base_ymd:'260630',cost_gubun:'실원가',status:'',model:''};
  let bom=[], gongsu=[], cost=null, srch=[], acT=null, busy=false;

  const loadList=async()=>{try{const r=await fetch(`${API}/api/esticost/list?q=${encodeURIComponent(q)}`);slist=(await r.json()).rows||[];}catch(e){slist=[];}};
  const reset=()=>{head={esti_no:'',item_code:'',item_name:'',base_ymd:head.base_ymd,cost_gubun:head.cost_gubun,status:'',model:''};bom=[];gongsu=[];cost=null;msg='';};

  // LG BOM 전개(nx.lg_bom) → 편집용 초기 BOM
  const expand=async(item)=>{item=(item||'').trim();if(!item)return;busy=true;draw();
    try{const r=await fetch(`${API}/api/esticost/expand?item=${encodeURIComponent(item)}`);const j=await r.json();
      if(!j.rows||!j.rows.length){msg='⚠ LG BOM(nx.lg_bom) 전개 결과 없음 — 상위품번 확인';busy=false;draw();return;}
      bom=j.rows.map(x=>({...x,mat_cost:null,raw_cost:null,proc_in:''}));
      head.item_code=item;head.item_name=j.name||'';head.model=item;head.esti_no='';head.status='';gongsu=[];cost=null;
      msg=`✅ LG BOM 전개 ${j.count}행 (source: ${j.source}${j.has_nxbom?' · nx.bom 보유':''})`;
    }catch(e){msg='전개 실패: '+e;}
    busy=false;draw();};

  const openEsti=async(no)=>{busy=true;draw();
    try{const r=await fetch(`${API}/api/esticost/load?esti_no=${encodeURIComponent(no)}`);const j=await r.json();
      head={esti_no:j.head.esti_no,item_code:j.head.item_code,item_name:j.head.item_name,base_ymd:j.head.base_ymd,
        cost_gubun:j.head.cost_gubun,status:j.head.status,model:j.head.model};
      bom=j.bom||[];gongsu=j.gongsu||[];
      cost={jae:j.head.jae_amt,gagong:j.head.gagong_amt,lme:j.head.lme_amt,ilban:j.head.ilban_amt,
        unban:j.head.unban_amt,profit:j.head.profit_amt,silwon:j.head.silwon_amt,lg:j.head.lg_cost,sonik:j.head.sonik_amt};
      msg=`📂 견적 ${no} 로드`;
    }catch(e){msg='로드 실패: '+e;}
    busy=false;draw();};

  // DOM → bom/gongsu 수집(편집값 반영)
  const collect=()=>{
    c.querySelectorAll('#ec-bom tbody tr[data-seq]').forEach(tr=>{
      const s=+tr.dataset.seq, row=bom.find(x=>x.seq===s);if(!row)return;
      const g=sel=>tr.querySelector(sel);
      const gv=sel=>{const el=g(sel);return el?el.value:undefined;};
      if(gv('.e-diam')!==undefined)row.diam=+gv('.e-diam')||0;
      if(gv('.e-thick')!==undefined)row.thick=+gv('.e-thick')||0;
      if(gv('.e-length')!==undefined)row.length=+gv('.e-length')||0;
      if(gv('.e-metal')!==undefined)row.metal_gubun=gv('.e-metal')||'';
      if(gv('.e-uweight')!==undefined)row.unit_weight=+gv('.e-uweight')||0;
      if(gv('.e-uqty')!==undefined)row.unit_qty=+gv('.e-uqty')||0;
      if(gv('.e-tqty')!==undefined)row.total_qty=+gv('.e-tqty')||0;
      const sag=g('.e-sag'),nw=g('.e-new');if(sag)row.sagub_flag=sag.checked?1:0;if(nw)row.new_flag=nw.checked?1:0;
    });
    c.querySelectorAll('#ec-gs tbody tr[data-i]').forEach(tr=>{
      const i=+tr.dataset.i, row=gongsu[i];if(!row)return;
      const gv=s=>{const el=tr.querySelector(s);return el?el.value:undefined;};
      row.work_qty=+gv('.g-wq')||0;row.uph=+gv('.g-uph')||0;row.rate=+gv('.g-rate')||0;
      row.proc_code=gv('.g-code')||row.proc_code;row.proc_name=gv('.g-name')||row.proc_name;
    });
  };

  const save=async()=>{if(!head.item_code){alert('대상 품번을 전개하거나 견적을 여세요.');return;}collect();busy=true;draw();
    try{const r=await fetch(`${API}/api/esticost/save`,{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({esti_no:head.esti_no||'',item_code:head.item_code,item_name:head.item_name,
          base_ymd:head.base_ymd,cost_gubun:head.cost_gubun,model:head.model,by:(typeof PERM!=='undefined'?PERM.userId:'')||'웹사용자',
          bom,gongsu})});
      const j=await r.json();if(!r.ok){alert('저장 실패: '+(j.detail||''));busy=false;draw();return;}
      head.esti_no=j.esti_no;head.status='작성';cost=j.cost||cost;msg=`💾 저장 완료 — ${j.esti_no}`;
      await loadList();
    }catch(e){alert('저장 오류: '+e);}
    busy=false;draw();};

  const calcCost=async()=>{if(!head.item_code){alert('대상 품번 필요');return;}busy=true;draw();
    try{const url=head.esti_no?`${API}/api/esticost/cost?esti_no=${encodeURIComponent(head.esti_no)}`
        :`${API}/api/esticost/cost?item=${encodeURIComponent(head.item_code)}&ymd=${head.base_ymd}`;
      const r=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});
      const j=await r.json();if(!r.ok){alert('산출 실패: '+(j.detail||''));busy=false;draw();return;}
      cost=j.cost;msg='🧮 원가 산출 완료 (NxCostEngine · nx.bom 기준)';
    }catch(e){alert('산출 오류: '+e);}
    busy=false;draw();};

  const approve=async(action)=>{if(!head.esti_no){alert('저장 후 승인/반려하세요.');return;}
    if(!confirm(`견적 ${head.esti_no} 을(를) ${action==='reject'?'반려':'승인'}하시겠습니까?`))return;
    try{const r=await fetch(`${API}/api/esticost/approve`,{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({esti_no:head.esti_no,action,by:(typeof PERM!=='undefined'?PERM.userId:'')||'웹사용자'})});
      const j=await r.json();if(!j.ok){alert('처리 실패');return;}
      head.status=j.status;msg=`${j.status==='승인'?'✅ 승인':'⛔ 반려'} — ${head.esti_no}`;await loadList();draw();
    }catch(e){alert('오류: '+e);}};

  const del=async()=>{if(!head.esti_no){reset();draw();return;}
    if(!confirm(`견적 ${head.esti_no} 을(를) 삭제하시겠습니까?`))return;
    try{await fetch(`${API}/api/esticost/delete`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({esti_no:head.esti_no})});
      msg=`🗑 삭제 — ${head.esti_no}`;reset();await loadList();draw();}catch(e){alert('삭제 오류: '+e);}};

  // 행추가(품목검색) — /api/bom/search
  const acAdd=t=>{clearTimeout(acT);acT=setTimeout(async()=>{try{const r=await fetch(`${API}/api/bom/search?q=${encodeURIComponent(t)}`);srch=(await r.json()).rows||[];const dl=c.querySelector('#ec-adddl');if(dl)dl.innerHTML=srch.slice(0,50).map(s=>`<option value="${esc(s.item)}">${esc((s.name||'').replace(/"/g,''))}</option>`).join('');}catch(e){}},180);};
  const addSearchRow=async(code)=>{code=(code||'').trim();if(!code)return;collect();
    const hit=srch.find(s=>s.item===code)||{};const seq=(bom.reduce((m,x)=>Math.max(m,x.seq),0)||0)+1;
    bom.push({seq,level:1,parent:head.item_code,item_code:code,item_name:hit.name||'',diam:0,thick:0,length:0,
      metal_gubun:'',shape:'',unit_weight:0,unit_qty:1,total_qty:1,cost_gubun:'',in_cust:'',make_type:'',
      sagub_flag:0,new_flag:0,mat_cost:null,raw_cost:null,proc_in:''});
    msg=`➕ 행추가 ${code}`;draw();};

  // 신규 SUB 자동채번 생성
  const newItem=async()=>{const name=(prompt('신규 품목(외주SUB) 품명을 입력하세요.','')||'').trim();if(!name)return;
    const prefix=(prompt('접두어(품번 prefix)를 입력하세요. 예: NXS','NXS')||'NXS').trim().toUpperCase();
    collect();
    try{const r=await fetch(`${API}/api/esticost/newitem`,{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({item_name:name,prefix,item_type:'S_ASSY',unit:'EA',make_type:'1'})});
      const j=await r.json();if(!j.ok){alert('생성 실패: '+(j.detail||''));return;}
      const seq=(bom.reduce((m,x)=>Math.max(m,x.seq),0)||0)+1;
      bom.push({seq,level:1,parent:head.item_code,item_code:j.item_code,item_name:j.item_name,diam:j.diam,thick:j.thick,
        length:j.length,metal_gubun:j.metal_gubun,shape:'',unit_weight:0,unit_qty:1,total_qty:1,cost_gubun:j.cost_gubun,
        in_cust:j.in_cust,make_type:j.make_type,sagub_flag:0,new_flag:1,mat_cost:null,raw_cost:null,proc_in:''});
      msg=`🆕 신규품목 채번 ${j.item_code} (nx.item 등록 · nx.bom 승격=승인시 phase2)`;draw();
    }catch(e){alert('생성 오류: '+e);}};
  const delRow=s=>{collect();bom=bom.filter(x=>x.seq!==s);draw();};
  const addGs=()=>{collect();gongsu.push({seq:(gongsu.length+1),item_code:head.item_code,proc_code:'',proc_name:'',work_qty:0,uph:0,rate:20776,calc_gubun:'3',amt:0});draw();};
  const delGs=i=>{collect();gongsu.splice(i,1);draw();};

  const gsAmt=g=>{const cg=g.calc_gubun||'3';const wq=+g.work_qty||0,uph=+g.uph||0,rate=+g.rate||0;
    if(cg==='3')return uph?Math.round(rate/uph*wq):0;if(cg==='8')return rate*uph*wq;if(cg==='9')return uph*wq;return 0;};

  // ===== BOM 편집 테이블 =====
  const bomTbl=()=>{
    if(!bom.length)return `<div class="empty" style="margin-top:14px">상단에서 품번을 <b>[LG BOM 전개]</b> 하거나 좌측 저장견적을 선택하세요.</div>`;
    const ro=head.status==='승인';   // 승인건은 잠금(재저장시 작성회귀)
    const cell=(cls,v,w)=>ro?`<span>${nfq(v)}</span>`:`<input class="${cls}" type="number" step="any" value="${v||v===0?v:''}" style="width:${w||58}px;min-width:0;padding:1px 3px">`;
    return `<table class="tbl" id="ec-bom" style="font-size:12px"><thead><tr>
      <th data-key="level" style="min-width:230px">레벨 · 품번</th><th data-key="item_name">품명</th>
      <th data-key="diam" class="num">외경</th><th data-key="thick" class="num">두께</th><th data-key="length" class="num">길이</th>
      <th data-key="metal_gubun">재질</th><th data-key="unit_weight" class="num">단위중량</th>
      <th data-key="unit_qty" class="num">단위소요</th><th data-key="total_qty" class="num">총소요</th>
      <th data-key="cost_gubun">단가구분</th><th>매입처</th>
      <th class="num">원소재비</th><th class="num">재료비</th>
      <th class="center">사급</th><th class="center">신규</th><th class="center"></th></tr></thead>
      <tbody>${bom.map(n=>{const root=n.level===0;
        return `<tr data-seq="${n.seq}" style="${root?'background:#eef5ff;font-weight:700':(n.new_flag?'background:#f0fff4':'')}">
          <td style="white-space:nowrap"><span style="display:inline-block;width:${n.level*16}px"></span>${n.level?'└ ':''}<b>${esc(n.item_code)}</b></td>
          <td class="cap" style="max-width:170px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${esc(n.item_name)}">${esc(n.item_name)}</td>
          <td class="num">${root?'':cell('e-diam',n.diam,52)}</td>
          <td class="num">${root?'':cell('e-thick',n.thick,48)}</td>
          <td class="num">${root?'':cell('e-length',n.length,52)}</td>
          <td>${root||ro?esc(n.metal_gubun||''):`<input class="e-metal" value="${esc(n.metal_gubun||'')}" style="width:56px;min-width:0;padding:1px 3px">`}</td>
          <td class="num">${root?'':cell('e-uweight',n.unit_weight,64)}</td>
          <td class="num">${root?'':cell('e-uqty',n.unit_qty,58)}</td>
          <td class="num">${root?'':cell('e-tqty',n.total_qty,58)}</td>
          <td>${esc(n.cost_gubun||'')}</td>
          <td class="cap" style="max-width:70px;overflow:hidden;text-overflow:ellipsis" title="${esc(n.in_cust||'')}">${esc(n.in_cust||'')}</td>
          <td class="num" style="color:#8aa0bd" title="자재단가=읽기전용(마감때만 수정)">${n.raw_cost!=null?wonI(n.raw_cost):'-'}</td>
          <td class="num" style="color:#8aa0bd" title="자재단가=읽기전용(마감때만 수정)">${n.mat_cost!=null?wonI(n.mat_cost):'-'}</td>
          <td class="center">${root?'':`<input class="e-sag" type="checkbox" ${n.sagub_flag?'checked':''} ${ro?'disabled':''}>`}</td>
          <td class="center">${root?'':(n.new_flag?'<span style="color:#1c7c3a;font-weight:700">신규</span>':`<input class="e-new" type="checkbox" ${ro?'disabled':''}>`)}</td>
          <td class="center">${root||ro?'':`<button class="btn ghost ec-del" data-s="${n.seq}" style="padding:0 6px;color:#c0392b">✖</button>`}</td>
        </tr>`;}).join('')}</tbody></table>`;
  };

  // ===== 작업공수 테이블 =====
  const gsTbl=()=>{
    const ro=head.status==='승인';
    return `<table class="tbl" id="ec-gs" style="font-size:12px"><thead><tr>
      <th>공정코드</th><th>공정명</th><th class="num">작업량</th><th class="num">내부UPH</th><th class="num">임율</th>
      <th class="num">가공비(미리보기)</th><th class="center"></th></tr></thead>
      <tbody>${gongsu.length?gongsu.map((g,i)=>`<tr data-i="${i}">
        <td>${ro?esc(g.proc_code):`<input class="g-code" value="${esc(g.proc_code||'')}" style="width:56px;min-width:0;padding:1px 3px">`}</td>
        <td>${ro?esc(g.proc_name):`<input class="g-name" value="${esc(g.proc_name||'')}" style="width:110px;min-width:0;padding:1px 3px">`}</td>
        <td class="num">${ro?nfq(g.work_qty):`<input class="g-wq" type="number" step="any" value="${g.work_qty||''}" style="width:64px;min-width:0;padding:1px 3px">`}</td>
        <td class="num">${ro?nfq(g.uph):`<input class="g-uph" type="number" step="any" value="${g.uph||''}" style="width:64px;min-width:0;padding:1px 3px">`}</td>
        <td class="num">${ro?won(g.rate):`<input class="g-rate" type="number" step="any" value="${g.rate||''}" style="width:74px;min-width:0;padding:1px 3px">`}</td>
        <td class="num">${wonI(gsAmt(g))}</td>
        <td class="center">${ro?'':`<button class="btn ghost ec-gsdel" data-i="${i}" style="padding:0 6px;color:#c0392b">✖</button>`}</td>
      </tr>`).join(''):`<tr><td colspan="7" class="empty">작업공수 없음 — <b>공정추가</b>로 용접·체결·가공 공수를 입력하세요.</td></tr>`}
      ${gongsu.length?`<tr class="grandtot"><td colspan="5" class="right">가공비 합계(미리보기)</td><td class="num">${wonI(gongsu.reduce((a,g)=>a+gsAmt(g),0))}</td><td></td></tr>`:''}</tbody></table>`;
  };

  const costBar=()=>{
    if(!cost)return `<div class="botsum" style="margin-top:10px;color:#8aa0bd">원가 미산출 — <b>🧮 원가산출</b> 또는 <b>💾 저장</b> 시 NxCostEngine으로 재료비·가공비·LME·손익을 산출합니다.</div>`;
    const K=(l,v,col)=>`<span style="display:inline-flex;flex-direction:column;min-width:96px"><small style="color:#8aa0bd">${l}</small><b style="font-size:15px;color:${col||'#243b5e'}">${wonI(v)}</b></span>`;
    const sonik=cost.sonik||0;
    return `<div class="botsum" style="margin-top:10px;display:flex;gap:18px;flex-wrap:wrap;align-items:center">
      ${K('재료비',cost.jae)}${K('가공비',cost.gagong)}${K('LME차액',cost.lme,'#8e44ad')}${K('일반',cost.ilban)}${K('운반',cost.unban)}${K('이윤',cost.profit)}
      <span style="width:1px;align-self:stretch;background:#cfe0ff"></span>
      ${K('실원가',cost.silwon,'#1c47a0')}${K('LG판가',cost.lg,'#1c7c3a')}${K('손익',sonik,sonik<0?'#c0392b':'#1c7c3a')}
      <span style="font-size:11px;color:#8aa0bd">NxCostEngine · nx.bom 기준(편집본 반영은 확정 승격 phase2)</span></div>`;
  };

  const draw=()=>{
    const st=head.status, stBadge=st?`<span style="background:${STC[st]||'#888'};color:#fff;border-radius:8px;padding:1px 9px;font-size:11px;font-weight:700">${esc(st)}</span>`:'';
    c.innerHTML=`
     <div class="page-title">💹 견적원가관리 <span style="font-size:12px;color:var(--muted);font-weight:400">LG BOM 전개 → 치수/공수 편집 → 원가·손익(NxCostEngine) → 저장·승인</span></div>
     <div class="page-sub">상위품번을 전개하면 <b>nx.lg_bom(LG BOM Explosion)</b> 전 레벨이 편집용으로 로딩됩니다. 저장=견적 스냅샷(nx.esti_*), 원가=nx 엔진. <b>승인</b> 시에만 조달후보 등록(phase2). <code>nx.esti_head/bom/gongsu</code></div>
     <div class="toolbar" style="flex-wrap:wrap;gap:6px">
       <input class="inp" id="ec-item" list="ec-itemdl" autocomplete="off" value="${esc(head.item_code)}" placeholder="상위품번 (예: AJR30089609)" style="width:200px;min-width:0">
       <datalist id="ec-itemdl"></datalist>
       <button class="btn" id="ec-expand" ${canW?'':'disabled'}>🔀 LG BOM 전개</button>
       <span style="margin-left:8px">단가기준일 <input class="inp" id="ec-ymd" type="date" value="${ymd2date(head.base_ymd)}" style="width:150px"></span>
       <span>원가구분 <select class="inp" id="ec-gubun" style="width:100px"><option value="실원가"${head.cost_gubun==='실원가'?' selected':''}>실원가</option><option value="내부용"${head.cost_gubun==='내부용'?' selected':''}>내부용</option></select></span>
       <span style="flex:1"></span>
       <button class="btn" id="ec-calc">🧮 원가산출</button>
       ${canW?`<button class="btn" id="ec-save" style="background:#1c7c3a;color:#fff">💾 저장</button>
       <button class="btn" id="ec-approve" style="background:#1c47a0;color:#fff">✅ 승인</button>
       <button class="btn ghost" id="ec-reject" style="color:#c0392b">⛔ 반려</button>
       <button class="btn ghost" id="ec-new">🆕 초기화</button>`:''}
     </div>
     <div style="display:flex;gap:12px;align-items:flex-start">
      <div style="flex:0 0 290px">
       <div class="toolbar"><input class="inp" id="ec-q" value="${esc(q)}" placeholder="견적/품번/품명 검색" style="width:180px;min-width:0"><button class="btn" id="ec-qbtn">🔍</button></div>
       <div class="grid-wrap" style="max-height:calc(100vh - 250px);overflow:auto;background:#fff;border:1px solid var(--line-2,#c9d3e0);border-radius:8px">
        <table class="tbl" id="ec-list" style="font-size:11.5px"><thead><tr><th data-key="esti_no">견적번호</th><th data-key="item_code">품번</th><th data-key="status" class="center">상태</th><th data-key="sonik" class="num">손익</th></tr></thead>
        <tbody>${searching?spinRow(4):(slist.length?slist.map(s=>`<tr class="ec-row${head.esti_no===s.esti_no?' sel':''}" data-no="${esc(s.esti_no)}" style="cursor:pointer">
          <td><b>${esc(s.esti_no)}</b><div style="color:#8aa0bd;font-size:10px">${esc(s.created_at||'')}</div></td>
          <td class="cap" style="max-width:90px;overflow:hidden;text-overflow:ellipsis" title="${esc(s.item_name)}"><b>${esc(s.item_code)}</b><div style="color:#8aa0bd;font-size:10px;overflow:hidden;text-overflow:ellipsis">${esc(s.item_name||'')}</div></td>
          <td class="center"><span style="color:${STC[s.status]||'#888'};font-weight:700">${esc(s.status)}</span></td>
          <td class="num" style="color:${(s.sonik||0)<0?'#c0392b':'#1c7c3a'}">${wonI(s.sonik)}</td></tr>`).join(''):`<tr><td colspan="4" class="empty">저장견적 없음</td></tr>`)}</tbody></table>
       </div>
      </div>
      <div style="flex:1;min-width:0">
       <div class="toolbar" style="flex-wrap:wrap">
         <span style="font-weight:700;color:#1c47a0;font-size:15px">${esc(head.item_code||'—')}</span>
         <span style="color:var(--muted)">${esc(head.item_name||'')}</span>
         ${head.esti_no?`<span class="rowcount">${esc(head.esti_no)}</span>`:'<span class="rowcount" style="background:#fff3d6;color:#8a6d1e">미저장</span>'} ${stBadge}
       </div>
       ${busy?`<div class="grid-wrap" style="padding:22px">${spinRow(1)}</div>`:`
       <div style="overflow:auto;max-height:calc(100vh - 430px);min-height:120px">
         <div style="font-weight:700;color:#334;margin:2px 0 4px">📦 BOM 전개 · 편집 <span style="font-size:11px;color:#8aa0bd;font-weight:400">(치수·소요량 편집 · 자재단가=읽기전용)</span></div>
         <div style="overflow-x:auto">${bomTbl()}</div>
       </div>
       ${canW&&bom.length&&head.status!=='승인'?`<div class="toolbar" style="margin-top:4px">
         <input class="inp" id="ec-add" list="ec-adddl" placeholder="행추가: 품목검색(품번/품명)" style="width:220px;min-width:0"><datalist id="ec-adddl"></datalist>
         <button class="btn ghost" id="ec-addbtn">➕ 행추가</button>
         <button class="btn ghost" id="ec-newitem">🆕 신규 SUB 생성(채번)</button></div>`:''}
       <div style="margin-top:8px;overflow:auto;max-height:230px">
         <div style="font-weight:700;color:#334;margin:2px 0 4px">⏱️ 작업공수 <span style="font-size:11px;color:#8aa0bd;font-weight:400">(용접·체결·가공: 작업량·UPH·임율 → 가공비)</span>
           ${canW&&head.status!=='승인'&&head.item_code?`<button class="btn ghost" id="ec-gsadd" style="margin-left:8px">➕ 공정추가</button>`:''}</div>
         <div style="overflow-x:auto">${gsTbl()}</div>
       </div>
       ${costBar()}`}
      </div>
     </div>
     ${msg?`<div class="page-sub" style="color:#1c7c3a">${esc(msg)}</div>`:''}
     <style>.ec-row.sel{background:#e8f0ff}.ec-row:hover{background:#eef4ff}#ec-bom th,#ec-gs th{position:sticky;top:0;z-index:1}</style>`;
    const g=id=>c.querySelector(id);
    // 헤더 입력
    if(g('#ec-ymd'))g('#ec-ymd').onchange=e=>{head.base_ymd=date2ymd(e.target.value)||head.base_ymd;};
    if(g('#ec-gubun'))g('#ec-gubun').onchange=e=>{head.cost_gubun=e.target.value;};
    if(g('#ec-item')){g('#ec-item').oninput=e=>{const t=e.target.value;clearTimeout(acT);acT=setTimeout(async()=>{try{const r=await fetch(`${API}/api/lgbom/search?q=${encodeURIComponent(t)}`);const rows=(await r.json()).rows||[];const dl=g('#ec-itemdl');if(dl)dl.innerHTML=rows.slice(0,40).map(x=>`<option value="${esc(x.model)}">${esc((x.modelnm||'').replace(/"/g,''))}</option>`).join('');}catch(e){}},180);};
      g('#ec-item').onkeydown=e=>{if(e.key==='Enter')expand(e.target.value);};}
    if(g('#ec-expand'))g('#ec-expand').onclick=()=>expand(g('#ec-item').value);
    if(g('#ec-calc'))g('#ec-calc').onclick=calcCost;
    if(g('#ec-save'))g('#ec-save').onclick=save;
    if(g('#ec-approve'))g('#ec-approve').onclick=()=>approve('approve');
    if(g('#ec-reject'))g('#ec-reject').onclick=()=>approve('reject');
    if(g('#ec-new'))g('#ec-new').onclick=()=>{reset();draw();};
    // 좌측 목록
    g('#ec-qbtn').onclick=async()=>{q=g('#ec-q').value;searching=true;draw();await loadList();searching=false;draw();};
    g('#ec-q').onkeydown=async e=>{if(e.key==='Enter'){q=e.target.value;searching=true;draw();await loadList();searching=false;draw();}};
    c.querySelectorAll('.ec-row').forEach(el=>el.onclick=()=>openEsti(el.dataset.no));
    // BOM 편집
    c.querySelectorAll('.ec-del').forEach(b=>b.onclick=()=>delRow(+b.dataset.s));
    if(g('#ec-add')){g('#ec-add').oninput=e=>acAdd(e.target.value);g('#ec-add').onkeydown=e=>{if(e.key==='Enter')addSearchRow(e.target.value);};}
    if(g('#ec-addbtn'))g('#ec-addbtn').onclick=()=>addSearchRow(g('#ec-add').value);
    if(g('#ec-newitem'))g('#ec-newitem').onclick=newItem;
    // 공수
    if(g('#ec-gsadd'))g('#ec-gsadd').onclick=addGs;
    c.querySelectorAll('.ec-gsdel').forEach(b=>b.onclick=()=>delGs(+b.dataset.i));
    c.querySelectorAll('#ec-gs input').forEach(el=>el.onchange=()=>{collect();
      // 가공비 미리보기만 갱신(전체 재draw 없이)
      c.querySelectorAll('#ec-gs tbody tr[data-i]').forEach(tr=>{const gg=gongsu[+tr.dataset.i];const cell=tr.children[5];if(gg&&cell)cell.textContent=wonI(gsAmt(gg));});
    });
    attachResizers(c);
  };
  const init=async()=>{await loadList();draw();};
  init();
};

/* ===== 공유 공정 팝업 렌더러(품목BOM관리 '내부원가' ↔ 조달후보 노드팝업 = 완전 동일 창) =====
   ★두 화면이 같은 DOM/클래스/컬럼구성(관경 전체표 + 공정 2단 전체 그리드)을 쓰도록 모듈레벨 공유.
   pd 캐노니컬 구조: {node, title?, subtitle?, isAssy, weldDiams:[{pipe_diam,std_use_qty,std_st}],
                     weldItem, weldTypes:[], weldCounts:{diam2dp:count}, cols:[{name,code,sec,idx,uph,cg,wq}],
                     infoBar?(상단 추가정보 HTML), footNote?}. 헬퍼는 esc(전역)만 의존(M2/CALCG/fmtU 자체내장). */
const PROC_MODAL_HTML=(pd)=>{
  if(!pd) return `<div id="pm-backdrop" style="position:fixed;inset:0;background:rgba(20,30,50,.35);z-index:9996;display:flex;align-items:center;justify-content:center"><div style="background:#fff;border-radius:10px;padding:20px" class="empty">공정 로딩…</div></div>`;
  const CALCG={'3':'임율기반','8':'중량기반','9':'적용율','7':'세척'};
  const M2=v=>(v==null||v==='')?'':Number(v).toLocaleString('ko-KR',{maximumFractionDigits:2});
  const isAssy=pd.isAssy, node=pd.node;
  const lvl=pd.subtitle||(isAssy?'제품/조립 — 관경별 용접 + 조립공정(용접·포장·체결)':'부품 — 가공공정');
  const wd=pd.weldDiams||[];
  const DIAMS=wd.map(d=>d.pipe_diam);
  const STU={},STS={};wd.forEach(d=>{STU[d.pipe_diam.toFixed(2)]=d.std_use_qty;STS[d.pipe_diam.toFixed(2)]=d.std_st;});
  const cnt=pd.weldCounts||{};
  let sUse=0,sSt=0,sCnt=0;DIAMS.forEach(d=>{const k=d.toFixed(2),q=+cnt[k]||0;if(q){sUse+=(STU[k]||0)*q;sSt+=(STS[k]||0)*q;sCnt+=q;}});
  const wTypes=[...new Set([...(pd.weldTypes||[]),'RAC30599301-1','RAC30599327','RAC30599328','RAC30599303'])];
  const wLabel=w=>({'RAC30599301-1':'1% 용접봉','RAC30599327':'3% 용접봉','RAC30599328':'30% BAG','RAC30599303':'BCUP'}[w]||w);
  const fmtU=v=>{if(!v)return '';const s=(+v).toFixed(5);return s.replace(/0+$/,'').replace(/\.$/,'');};
  const weldMatrix=!isAssy?'':`
      <div style="display:flex;align-items:center;gap:8px;padding:4px 6px;flex-wrap:wrap">
        <b style="color:#8e44ad">🔧 관경별 용접</b>
        <span style="color:#8a94a6;font-size:11px">용접봉 종류(노드당 1개)</span>
        <select id="wm-type" style="font-size:12px">${wTypes.map(w=>`<option value="${esc(w)}" ${w===pd.weldItem?'selected':''}>${esc(w)} · ${esc(wLabel(w))}</option>`).join('')}</select>
        <span style="color:#8a94a6;font-size:11px">관경 아래 <b>용접횟수</b> 입력 → 소요량·내부ST 자동 (BOM반영 소요량=표시×1.5)</span></div>
      <div style="overflow-x:auto"><table class="tbl wm wmw" style="font-size:11px">
        <thead><tr><th style="text-align:left;min-width:56px">용접</th><th class="num" style="min-width:48px">합계</th>${DIAMS.map(d=>`<th class="num">${d.toFixed(2)}</th>`).join('')}</tr></thead>
        <tbody>
          <tr><td style="text-align:left;color:#5a6b82">표준소요량</td><td></td>${DIAMS.map(d=>`<td class="num" style="color:#8a94a6">${fmtU(STU[d.toFixed(2)]||0)}</td>`).join('')}</tr>
          <tr><td style="text-align:left;color:#5a6b82">표준공수</td><td></td>${DIAMS.map(d=>`<td class="num" style="color:#8a94a6">${(STS[d.toFixed(2)]||0)}</td>`).join('')}</tr>
          <tr style="background:#faf5ff"><td style="text-align:left;font-weight:700;color:#8e44ad">용접횟수</td><td class="num"><b>${sCnt}</b></td>${DIAMS.map(d=>{const k=d.toFixed(2);return `<td class="num"><input class="wm-q" data-diam="${k}" type="number" min="0" step="1" value="${cnt[k]||''}" style="width:32px;text-align:center"></td>`;}).join('')}</tr>
          <tr style="background:#eef4ff"><td style="text-align:left;font-weight:700;color:#1c6b3a">소요량</td><td class="num" style="color:#1c6b3a"><b>${fmtU(sUse)}</b></td>${DIAMS.map(d=>{const k=d.toFixed(2),q=+cnt[k]||0;return `<td class="num" style="color:#1c6b3a">${q?fmtU((STU[k]||0)*q):''}</td>`;}).join('')}</tr>
          <tr><td style="text-align:left;font-weight:700;color:#8a5a1a">내부ST</td><td class="num" style="color:#8a5a1a"><b>${sSt}</b></td>${DIAMS.map(d=>{const k=d.toFixed(2),q=+cnt[k]||0;return `<td class="num" style="color:#8a5a1a">${q?((STS[k]||0)*q):''}</td>`;}).join('')}</tr>
        </tbody></table></div>`;
  const cols=pd.cols||[];
  let sWq=0;cols.forEach(cc=>sWq+=(+cc.wq||0));
  const band=(sub)=>{if(!sub.length)return '';const bsum=sub.reduce((s,cc)=>s+(+cc.wq||0),0);
    return `<table class="tbl wm" style="font-size:11px;table-layout:fixed;width:100%;margin-bottom:6px">
        <thead><tr><th style="text-align:left;width:58px">구분</th>${sub.map(cc=>`<th class="num" style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:10px" title="${esc(cc.name)} · ${esc(cc.code)}">${esc(cc.name)}</th>`).join('')}<th class="num" style="width:48px;background:#eef4ff">합계</th></tr></thead>
        <tbody>
          <tr style="background:#f5f9ff"><td style="text-align:left;font-weight:700;color:#1c47a0">작업ST</td>${sub.map(cc=>`<td class="num"><input class="pq" data-sec="${cc.sec}" data-i="${cc.idx}" type="number" min="0" step="any" value="${cc.wq||''}" style="width:38px;text-align:center"></td>`).join('')}<td class="num" style="font-weight:700;background:#f6f9ff;color:#1c47a0">${bsum?M2(bsum):''}</td></tr>
          <tr><td style="text-align:left;color:#5a6b82">내부UPH</td>${sub.map(cc=>`<td class="num"><input class="puph" data-sec="${cc.sec}" data-i="${cc.idx}" type="number" min="0" step="any" value="${cc.uph||''}" title="표준UPH 자동조회 · 수정가능(마감無관)" style="width:52px;text-align:center;color:#33507d;font-variant-numeric:tabular-nums"></td>`).join('')}<td style="background:#f6f9ff"></td></tr>
          <tr><td style="text-align:left;color:#5a6b82">임율/구분</td>${sub.map(cc=>`<td class="center" style="color:#8a94a6;font-size:10px">${esc(CALCG[cc.cg]||cc.cg||'임율')}</td>`).join('')}<td style="background:#f6f9ff"></td></tr>
        </tbody></table>`;};
  const _half=Math.ceil(cols.length/2);
  const procMatrix=`
      <div style="padding:4px 6px"><b style="color:#1c47a0">⚙ 공정별 (작업 ST 입력)</b> <span style="color:#8a94a6;font-size:11px">공정 2단 배치 · 작업ST 입력 / 내부UPH·임율 참조(읽기전용) · 작업ST 합계 <b style="color:#1c47a0">${M2(sWq)}</b></span></div>
      <div style="padding:0 4px">${band(cols.slice(0,_half))}${band(cols.slice(_half))}</div>`;
  const title=pd.title!=null?pd.title:`✎ 공정 등록/수정 — ${esc(node)}`;
  const foot=pd.footNote!=null?pd.footNote:'관경별 용접횟수→소요량(Σ표준소요량×횟수×1.5)·내부ST 자동 · 공정 작업ST 입력 · 단가 읽기전용(마감때만) · 저장시 재계산';
  return `<div id="pm-backdrop" style="position:fixed;inset:0;background:rgba(20,30,50,.4);z-index:9996;display:flex;align-items:center;justify-content:center;padding:12px">
      <div style="background:#fff;border-radius:10px;box-shadow:0 10px 40px rgba(0,0,0,.3);width:98vw;max-width:1700px;max-height:94vh;display:flex;flex-direction:column">
        <div style="padding:9px 14px;display:flex;align-items:center;gap:10px;border-bottom:1px solid #dce4ee;flex:0 0 auto">
          <b style="color:#1c47a0;font-size:15px">${title}</b><span style="color:#8a94a6;font-size:12px">${esc(lvl)}</span>
          <div style="flex:1"></div><button class="btn" id="pm-save" style="background:#1c7c3a;color:#fff">💾 저장</button><button class="btn ghost" id="pm-close">✖ 닫기</button></div>
        <div style="flex:1 1 auto;min-height:0;overflow-y:auto;overflow-x:hidden;padding:8px 10px">
          ${pd.infoBar||''}
          ${isAssy?`<div style="border:1px solid #d6c3ea;border-radius:8px;background:#faf7ff;margin-bottom:10px">${weldMatrix}</div>`:''}
          <div style="border:1px solid #cfe0ff;border-radius:8px;background:#f7faff">${procMatrix}</div>
          ${isAssy&&pd.fastenHtml?`<div style="border:1px solid #d6c3ea;border-radius:8px;background:#faf7ff;margin-top:10px">${pd.fastenHtml}</div>`:''}
        </div>
        <div style="padding:6px 14px;border-top:1px solid #dce4ee;color:#8aa0bd;font-size:11px;flex:0 0 auto">${esc(foot)}</div>
      </div></div>`;};
// 공유 공정 팝업 이벤트 바인딩 — 콜백으로 각 화면이 자기 상태에 write-back(닫기/저장/공정입력/용접횟수/용접봉종류).
const PROC_MODAL_BIND=(c,cbs)=>{const g=id=>c.querySelector(id);
  {const x=g('#pm-close');if(x)x.onclick=()=>cbs.onClose&&cbs.onClose();}
  {const bg=g('#pm-backdrop');if(bg)bg.onclick=e=>{if(e.target===bg&&cbs.onClose)cbs.onClose();};}
  {const s=g('#pm-save');if(s)s.onclick=()=>cbs.onSave&&cbs.onSave();}
  c.querySelectorAll('.pq').forEach(el=>{el.oninput=()=>cbs.onProcInput&&cbs.onProcInput(el.dataset.sec,+el.dataset.i,el.value,el);
    el.onchange=()=>cbs.onProcCommit&&cbs.onProcCommit(el.dataset.sec,+el.dataset.i,el.value,el);});
  c.querySelectorAll('.puph').forEach(el=>{el.oninput=()=>cbs.onProcUph&&cbs.onProcUph(el.dataset.sec,+el.dataset.i,el.value,el);
    el.onchange=()=>cbs.onProcCommit&&cbs.onProcCommit(el.dataset.sec,+el.dataset.i,el.value,el);});  // ★UPH 편집(표준 자동조회+수정)
  c.querySelectorAll('.wm-q').forEach(el=>el.oninput=()=>cbs.onWeldCount&&cbs.onWeldCount(el.dataset.diam,el.value,el));
  {const ts=g('#wm-type');if(ts)ts.onchange=()=>cbs.onWeldType&&cbs.onWeldType(ts.value);}};
// 공유 공정 팝업 CSS(관경/공정 매트릭스 .wm) — naeCss와 동일 규칙(subvariant 화면에 주입용).
const PROC_MODAL_CSS=`<style>
  .wm{border-collapse:collapse;table-layout:auto}
  .wm th,.wm td{border:1px solid #dde6f0;padding:1px 2px}
  .wm th.wm-vh{height:66px;width:26px;min-width:26px;max-width:26px;vertical-align:bottom;background:#eef3fb;padding:2px 0}
  .wm th.wm-vh span{writing-mode:vertical-rl;text-orientation:upright;white-space:nowrap;font-size:10px;font-weight:600;color:#40567a;display:inline-block;max-height:62px;overflow:hidden;letter-spacing:-1px}
  .wm td input{border:1px solid #cfd9e6;border-radius:3px;padding:1px}
  .wm tbody td:first-child,.wm thead th:first-child{position:sticky;left:0;background:#f4f7fc;z-index:2}
</style>`;

/* ===== 품목 BOM관리 (SCREEN.unifybom) — 3탭: BOM구성 | 내부원가 | 실원가. nx · 백엔드 편집·저장 ===== */
/* 내부원가=/api/cost/nae(naewon_nodes+proc_grid) · 실원가=/api/cost/sil(silwon_nodes) · 단가기준일(naeYmd). 단가는 마감때만(수정제외). */
SCREEN.unifybom=(c,ro)=>{
  const API=API_BASE;
  const RO=(ro===true);
  let item='', name='', lines=[], results=[], loading=false, msg='', editMode=false, query='', procs=[], procMap={}, itemNames={}, includePast=false, itemCut='';  // itemCut=절삭/설치 구분(nx.item.cut_gubun)
  let tree=[], treeMax=0, viewTree=true, showWeld=false, navStack=[];
  let wuData=null, wuBusy=false;   // 역전개(where-used) 모달 상태
  const wuFmt=n=>(n==null||n==='')?'':Number(n).toLocaleString('ko-KR',{maximumFractionDigits:5});
  const openWhereUsed=async()=>{
    if(!item)return; wuBusy=true; wuData=null; draw();
    try{const r=await fetch(`${API}/api/bom/whereused?item=${encodeURIComponent(item)}`); wuData=await r.json();}
    catch(e){wuData={rows:[],error:e.message,item:item,name:name};}
    wuBusy=false; draw();
  };
  function wuModalHtml(){
    const d=wuData||{}, rows=d.rows||[];
    const body = wuBusy ? '<div class="empty" style="padding:24px">역전개 조회 중…</div>'
      : d.error ? `<div class="empty" style="color:#c0392b;padding:24px">오류: ${esc(d.error)}</div>`
      : (rows.length<=1) ? '<div class="empty" style="padding:24px">이 품번을 하위구성으로 쓰는 상위 품번이 없습니다 (최상위이거나 아직 미사용).</div>'
      : `<table class="tbl" style="font-size:12px"><thead><tr><th style="width:54px">레벨</th><th>품번</th><th>품명</th><th>대표매입처</th><th class="num" style="width:72px">소요량</th><th style="width:160px">구분</th><th>규격</th></tr></thead><tbody>${rows.map(r=>{
        const ind=8+(r.level||0)*16;
        const flags = r.level===0 ? '<span class="badge">대상</span>'
          : `${r.ce==='1'?'<span style="color:#c0392b;font-size:10px">원가제외</span> ':''}${r.sag==='1'?'<span style="color:#8a6d1c;font-size:10px">사급</span> ':''}${r.se==='1'?'<span style="color:#888;font-size:10px">세트제외</span>':''}`;
        const sz = r.spec || ((r.diam?('Φ'+r.diam):'')+(r.thick?('×'+r.thick):''));
        const clk = (r.level>0 && r.raw) ? ` class="wu-row" data-raw="${esc(r.raw)}" style="cursor:pointer"` : '';
        return `<tr${clk}><td class="center" style="color:#8598b5">${r.level===0?'0':'▲'+r.level}</td><td style="padding-left:${ind}px"><b>${esc(r.code||'')}</b></td><td>${esc(r.nm||'')}</td><td>${esc(r.custnm||'')}</td><td class="num">${wuFmt(r.qty)}</td><td>${flags}</td><td>${esc(sz||'')}</td></tr>`;
      }).join('')}</tbody></table>`;
    return `<div id="wu-backdrop" style="position:fixed;inset:0;background:rgba(15,25,45,.38);z-index:1200;display:flex;align-items:center;justify-content:center">
      <div style="background:#fff;border-radius:12px;width:min(900px,93vw);max-height:86vh;display:flex;flex-direction:column;box-shadow:0 14px 44px rgba(0,0,0,.32)">
        <div style="display:flex;align-items:center;gap:8px;padding:12px 16px;border-bottom:1px solid var(--line)">
          <b style="font-size:15px">🔺 역전개 <span style="font-size:12px;color:var(--muted);font-weight:400">where-used</span></b>
          <span style="color:#33507d;font-size:12px;font-weight:600">${esc(d.item||item||'')} ${esc((d.name||name)||'')}</span>
          ${(!wuBusy&&!d.error)?`<span class="badge">${Math.max(0,rows.length-1)}건</span>`:''}
          <div style="flex:1"></div><button class="btn ghost" id="wu-close">✖ 닫기</button>
        </div>
        <div style="overflow:auto;padding:6px 12px 12px">${body}</div>
        <div style="padding:7px 16px;border-top:1px solid var(--line);color:var(--muted);font-size:11px">▲N = N단계 상위 · <b>상위 품번 클릭 → 그 품번으로 이동</b> · 소스 = 재설계 단일BOM(nx.bom_line)</div>
      </div></div>`;
  }
  let codes={}, vlist=[];
  const _naeToday=(()=>{const d=new Date();return `${String(d.getFullYear()).slice(2)}${String(d.getMonth()+1).padStart(2,'0')}${String(d.getDate()).padStart(2,'0')}`;})();  // YYMMDD 당일(단가기준일 기본)
  let tab='bom', naeD=null, naeFor='', naeYmd=_naeToday, naeLoad=false, naeSel='', naeProcs=[], naeProcD=null, naeEdit=false, naeView='proc', naeEditM=false, naeEdits={};
  let fastenD=null, fastenFor='';   // 체결 매트릭스(품목별 체결 공정횟수 입력→가공비). /api/assywork
  let naeProcLoading=false;         // 조립공정 팝업 로딩(사외망 DB 지연 대비 즉시 표시)
  const loadFasten=async(node)=>{ node=(node||item||'').trim(); if(!node)return;
    try{const r=await fetch(`${API}/api/assywork/get?item=${encodeURIComponent(node)}`);fastenD=await r.json();fastenFor=node;}catch(e){fastenD={rows:[],error:e.message};} };
  const saveFasten=async()=>{ if(!fastenD)return; const it=fastenFor||item;
    const rows=(fastenD.rows||[]).filter(x=>(+x.qty)>0).map(x=>({fcode:x.fcode,qty:+x.qty}));
    try{const r=await fetch(`${API}/api/assywork/save`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({item:it,rows,user:'웹'})});
      const j=await r.json(); if(!j.ok){alert('체결 저장 실패');return;}
      await loadFasten(it); if(tab==='nae')await loadNae(true);   // 가공비 재계산 반영
      alert(`체결 저장 완료 — ${j.count}공정 · 가공비 재계산`);
    }catch(e){alert('체결 저장 오류: '+e.message);} };
  // 체결 매트릭스 렌더(레거시 견적원가조회 체결보기: 표준공수 고정·공정횟수 입력·내부ST 자동)
  const fastenMatrix=(embedded)=>{
    if(!fastenD)return `<div class="empty">체결 매트릭스 로딩…</div>`;
    const rows=fastenD.rows||[]; const RW=(!RO&&(typeof PERM==='undefined'||PERM.canEdit('unifybom')));
    const tSt=rows.reduce((s,r)=>s+(+r.qty||0)*(+r.std_st||0),0);
    const gag=Math.round(tSt/3600*(fastenD.labor_rate||20776));
    const cell=(r,i)=>`<td class="num"><input class="fq" data-i="${i}" type="number" min="0" step="1" value="${r.qty||''}" ${RW?'':'disabled'} style="width:46px;text-align:center"></td>`;
    return `<div style="${embedded?'':'flex:1 1 auto;min-height:0;overflow:auto'}">
      <div style="display:flex;align-items:center;gap:10px;padding:6px 4px">
        <b style="color:#8e44ad">🔩 체결 공정 (품목별 횟수 입력)</b>
        <span style="font-size:11px;color:var(--muted)">표준공수×횟수=내부ST · 가공비=Σ내부ST÷3600×임율(${won(fastenD.labor_rate||0)})</span>
        <span style="margin-left:auto;font-weight:700;color:#1c47a0">체결 내부ST ${won(Math.round(tSt))} · 가공비 ${won(gag)}원</span>
        ${(RW&&!embedded)?`<button class="btn" id="ft-save" style="background:#1c7c3a;color:#fff">💾 저장</button>`:''}${embedded?'<span style="font-size:11px;color:#8a5a1a">(아래 [저장] 시 함께 저장)</span>':''}</div>
      <div class="grid-wrap" style="overflow:auto"><table class="tbl fit" style="font-size:12px"><thead><tr>
        <th>체결공정</th>${rows.map(r=>`<th class="num" title="${esc(r.fname)}" style="max-width:70px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(r.fname)}</th>`).join('')}<th class="num" style="background:#eef4ff">합계</th></tr></thead>
        <tbody>
          <tr><td style="text-align:left;color:#5a6b82">표준공수</td>${rows.map(r=>`<td class="num" style="color:#8a94a6">${r.std_st}</td>`).join('')}<td></td></tr>
          <tr style="background:#faf5ff"><td style="text-align:left;font-weight:700;color:#8e44ad">공정횟수</td>${rows.map((r,i)=>cell(r,i)).join('')}<td class="num"><b>${won(rows.reduce((s,r)=>s+(+r.qty||0),0))}</b></td></tr>
          <tr><td style="text-align:left;font-weight:700;color:#8a5a1a">내부ST</td>${rows.map(r=>`<td class="num" style="color:#8a5a1a">${(+r.qty||0)?won(Math.round((+r.qty||0)*(+r.std_st||0))):''}</td>`).join('')}<td class="num" style="color:#8a5a1a"><b>${won(Math.round(tSt))}</b></td></tr>
        </tbody></table></div></div>`;
  };
  let naeModal=false;   // 공정 수정 팝업(모달) 표시
  const _prevYm=(()=>{const d=new Date();d.setDate(1);d.setMonth(d.getMonth()-1);return `${String(d.getFullYear()).slice(2)}${String(d.getMonth()+1).padStart(2,'0')}`;})();  // 직전 완성월 YYMM(사급 리시빙월 기본)
  let silD=null, silFor='', silLoad=false, silView='company', silSagYm=_prevYm;
  // ★조달경로 후보 연동(현행 R01 + 승인 후보 R02..) — BOM구성·실원가 탭 공용 선택기. routeSel=0=현행(마스터), >0=후보 route_id.
  let routes=[], routesFor='', routeSel=0, routeTree=null, routeTreeFor=-1, routeCost=null, routeCostFor=-1, routeBusy=false;
  const loadRoutes=async()=>{if(!item)return;
    try{const r=await fetch(`${API}/api/sourcing/routes?item=${encodeURIComponent(item)}&for_profile=1&show_unapproved=0`);
      const j=await r.json();routes=(j.routes||[]);routesFor=item;}catch(e){routes=[];routesFor=item;}};
  // 후보 선택기(현행+승인후보) — 두 탭 공용
  const candSelector=(tabn)=>{
    if(!routes.length) return '';
    const opts=routes.map(rt=>{const lbl=rt.baseline?'현행 (실사용 BOM · R01)':`R${String(rt.route_no).padStart(2,'0')} ${rt.route_name||'대안'}${rt.approve_flag?'':' ·미승인'}`;
      return `<option value="${rt.route_id}" ${rt.route_id===routeSel?'selected':''}>${esc(lbl)}</option>`;}).join('');
    const cur=routes.find(rt=>rt.route_id===routeSel);
    const desc=routeSel>0?`후보 R${cur?String(cur.route_no).padStart(2,'0'):''} 구조·실원가 보기 — 조달 업체는 <b>조달프로파일</b> 계층`:'현행(마스터 실사용 BOM) 보기';
    return `<div class="cand-bar" style="display:flex;align-items:center;gap:8px;margin:6px 0;padding:5px 10px;background:#f6f2fb;border:1px solid #d6c3ea;border-radius:8px;flex-wrap:wrap"><b style="color:#8e44ad;font-size:12px">🔀 조달경로</b>
       <select class="cand-sel" data-tab="${tabn}" style="min-width:230px;border:1px solid #cbb6e2;border-radius:5px;padding:3px 6px;font-size:12px;background:#fff">${opts}</select>
       <span style="color:#7a6a92;font-size:11px">${desc}</span>${routeSel>0?'<span class="nae-tg" style="color:#8e44ad;border-color:#d6c3ea">후보</span>':'<span class="nae-tg" style="color:#1c47a0;border-color:#bcd">현행</span>'}</div>`;};
  const loadRouteTree=async()=>{if(routeSel<=0){routeTree=null;return;}routeBusy=true;draw();
    try{const r=await fetch(`${API}/api/bom/tree?item=${encodeURIComponent(item)}&route_id=${routeSel}`);routeTree=await r.json();routeTreeFor=routeSel;}
    catch(e){routeTree={error:e.message};routeTreeFor=routeSel;}routeBusy=false;draw();};
  const loadRouteCost=async()=>{if(routeSel<=0){routeCost=null;return;}routeBusy=true;draw();
    try{const r=await fetch(`${API}/api/sourcing/route/cost?route_id=${routeSel}&ymd=${encodeURIComponent(naeYmd)}`);routeCost=await r.json();routeCostFor=routeSel;}
    catch(e){routeCost={error:e.message};routeCostFor=routeSel;}routeBusy=false;draw();};
  const bindCandSel=()=>{c.querySelectorAll('.cand-sel').forEach(el=>el.onchange=()=>{routeSel=+el.value;routeTreeFor=-1;routeCostFor=-1;draw();});};
  // 후보 구조 트리(BOM구성 탭, routeSel>0) — bom/tree route_id 동일스키마
  const routeTreeTable=()=>{
    if(routeBusy||routeTreeFor!==routeSel) return `<div class="empty">후보 구조 로딩…</div>`;
    if(!routeTree||routeTree.error) return `<div class="empty" style="color:#c0392b">⚠ ${esc((routeTree&&routeTree.error)||'후보 구조 로드 실패')}</div>`;
    const rows=routeTree.rows||[];
    const body=rows.map(r=>{const sp=r.diam?('Ø'+r.diam+(r.thick?'×'+r.thick:'')):(r.spec||'');
      const bg=['#fff','#f6f2fb','#efe7f8','#e7dcf4','#dfd2f0'][Math.min(r.level,4)];
      const tag=r.level===0?'<span class="nae-tg" style="color:#1c47a0;border-color:#bcd">제품</span>':(r.haskids?'<span class="nae-tg" style="color:#8e44ad;border-color:#d6c3ea">SUB</span>':(r.gubun?`<span class="nae-tg" style="color:#556;border-color:#ccc">${esc(r.gubun)}</span>`:''));
      return `<tr style="background:${bg}"><td class="center">${r.level}</td>
        <td style="padding-left:${8+r.level*18}px;white-space:nowrap">${r.level?'<span style="color:#a9b8cc">└ </span>':''}<b>${esc(r.code)}</b> ${tag}</td>
        <td class="bcap" title="${esc(r.nm)}" style="max-width:210px;text-align:left">${esc(r.nm)}</td>
        <td class="center" style="color:#5a6b82">${esc(sp)}</td>
        <td class="center">${r.sag==='1'?'<span class="nae-tg" style="color:#c0392b;border-color:#e6bcbc">사급</span>':''}</td>
        <td class="bcap" title="${esc(r.custnm||r.cust||'')}" style="max-width:130px;text-align:left;color:#5a6b82">${esc(r.custnm||r.cust||'')}</td>
        <td class="num">${q4(r.qty)}</td></tr>`;}).join('')||'<tr><td colspan=7 class="empty">후보 구성 없음</td></tr>';
    return `<div class="summary-bar" style="flex-wrap:wrap"><div class="s-item"><b style="color:#8e44ad">후보 R${String(routeTree.route_no).padStart(2,'0')}</b> ${esc(routeTree.route_name||'')} · 조달경로 구조(SUB 포함) · <span style="color:#8a94a6">공급처=조달프로파일</span></div></div>
      <div class="grid-wrap" style="max-height:calc(100vh - 340px);overflow:auto"><table class="tbl bm-tbl">
      <thead><tr><th>레벨</th><th style="text-align:left">품번</th><th style="text-align:left">품명</th><th>규격</th><th class="center">사급</th><th style="text-align:left">공급처</th><th class="num">소요량</th></tr></thead>
      <tbody>${body}</tbody></table></div>`;};
  // 후보 실원가(실원가 탭, routeSel>0) — route/cost. 현행 대비 손익 diff.
  const routeCostContent=()=>{
    if(routeBusy||routeCostFor!==routeSel) return `<div class="empty">후보 실원가 계산 중…</div>`;
    if(!routeCost||routeCost.error) return `<div class="page-sub" style="color:#c0392b">⚠ ${esc((routeCost&&routeCost.error)||'후보 원가 로드 실패')}</div>`;
    const cc=routeCost.cost||{}, cur=routeCost.current||{}, rows=routeCost.rows||[], prc=routeCost.procs||[];
    const cline=(lb,a,b)=>{const d=Math.round(((+a||0)-(+b||0))*100)/100;return `<tr><td style="text-align:left">${lb}</td><td class="num">${M(b)}</td><td class="num"><b>${M(a)}</b></td><td class="num" style="color:${d===0?'#8a94a6':(d<0?'#1c7c3a':'#c0392b')}">${d===0?'0':((d>0?'+':'')+M(d))}</td></tr>`;};
    const cmp=`<div class="grid-wrap" style="max-height:30vh;overflow:auto;margin-top:6px"><table class="tbl bm-tbl">
      <thead><tr><th style="text-align:left">성분</th><th class="num">현행(R01)</th><th class="num">후보 R${String(routeCost.route_no).padStart(2,'0')}</th><th class="num">차이(후보−현행)</th></tr></thead>
      <tbody>${cline('재료비',cc.jae,cur.jae)}${cline('가공비',cc.gagong,cur.gagong)}${cline('LME차액',cc.lme,cur.lme)}${cline('일반관리',cc.ilban,cur.ilban)}${cline('운반비',cc.unban,cur.unban)}${cline('이윤',cc.profit,cur.profit)}
        <tr class="nae-foot">${cline('실원가',cc.silwon,cur.silwon).replace(/<td/,'<td')}</tr>${cline('LG판가',cc.lg,cur.lg)}${cline('손익',cc.sonik,cur.sonik)}</tbody></table></div>`;
    const rowsTbl=`<div class="grid-wrap" style="max-height:34vh;overflow:auto;margin-top:6px"><table class="tbl bm-tbl">
      <thead><tr><th>레벨</th><th style="text-align:left">품번</th><th style="text-align:left">품명</th><th>구분</th><th class="num">단위단가</th><th class="num">재료비</th><th class="num">LME</th><th class="num">가공비</th></tr></thead>
      <tbody>${rows.map(r=>{const k=silKind(r);return `<tr style="background:${['#fff','#f6f9ff','#edf3ff','#e4edff','#dbe7ff'][Math.min(r.level,4)]}">
        <td class="center">${r.level}</td><td style="padding-left:${8+r.level*16}px;white-space:nowrap">${r.level?'└ ':''}<b>${esc(r.code)}</b></td>
        <td class="bcap" title="${esc(r.name)}" style="max-width:170px">${esc(r.name)}</td>
        <td class="center"><span style="color:${k.c};font-weight:600;font-size:11px">${k.t}</span></td>
        <td class="num">${r.won?M2(r.won):''}</td><td class="num" style="color:#1c6b3a">${M(r.mat)}</td>
        <td class="num" style="color:#a8442a">${r.lme?M(r.lme):''}</td><td class="num" style="color:#8a5a1a">${M(r.gag)}</td></tr>`;}).join('')||'<tr><td colspan=8 class="empty">구성 없음</td></tr>'}</tbody></table></div>`;
    return `${sumbar(cc,'silwon','실원가')}
      <div class="page-sub" style="margin-top:2px;color:#7a6a92">후보 <b>R${String(routeCost.route_no).padStart(2,'0')} ${esc(routeCost.route_name||'')}</b> · 실원가(NxCostEngine, 마스터와 동일 산식) ${routeCost.diff0?'<span class="nae-tg" style="color:#1c7c3a;border-color:#a9d9b9">현행과 diff0</span>':''}</div>
      <div style="font-weight:700;color:#8e44ad;font-size:12px;margin-top:6px">현행 대비 비교</div>${cmp}
      <div style="font-weight:700;color:#243244;font-size:12px;margin-top:6px">노드별 실원가</div>${rowsTbl}
      <div class="page-sub" style="color:#8aa0bd;margin-top:4px">${esc(routeCost.note||'')}</div>`;};
  // ★신규 BOM 등록 상태(방식①LG업로드 ②복사 ③새로) + 용접공정(관경별 횟수) 직원입력
  let newReg=null;              // {method} 모달 표시
  let isNew=false;             // 신규등록 편집 세션(저장시 마스터 생성)
  let newMaster={lgroup:'',sgroup:'',make_type:'3',cost_gubun:''};  // ★신규등록 제품(top) 마스터속성. 대분류=가공비 필터핵심(미설정시 부품공정 누락)
  let weldRows=[];             // [{weld_item,pipe_diam,weld_qty}] 관경별 용접점
  // ★관경 마스터 상수 fallback(weld_diam 정본 14관경) — API 미로드/지연에도 매트릭스 항상 채워지게(빈칸 방지)
  const WELD_DIAMS_DEFAULT=[{pipe_diam:4.76,std_use_qty:0.0007,std_st:10},{pipe_diam:5.00,std_use_qty:0.0007,std_st:10},{pipe_diam:6.35,std_use_qty:0.0008,std_st:10},{pipe_diam:7.94,std_use_qty:0.0008,std_st:10},{pipe_diam:9.52,std_use_qty:0.0008,std_st:10},{pipe_diam:12.70,std_use_qty:0.0010,std_st:15},{pipe_diam:15.88,std_use_qty:0.0012,std_st:15},{pipe_diam:19.05,std_use_qty:0.0022,std_st:23},{pipe_diam:22.00,std_use_qty:0.0028,std_st:23},{pipe_diam:25.40,std_use_qty:0.0038,std_st:29},{pipe_diam:28.00,std_use_qty:0.0047,std_st:29},{pipe_diam:31.75,std_use_qty:0.0057,std_st:29},{pipe_diam:34.90,std_use_qty:0.0066,std_st:29},{pipe_diam:38.10,std_use_qty:0.0076,std_st:29}];
  let weldDiams=WELD_DIAMS_DEFAULT.slice();   // 기본값으로 시작(빈배열 방지)
  const loadWeldDiams=async()=>{try{const r=await fetch(`${API}/api/weld/diam`);const rows=(await r.json()).rows||[];if(rows.length)weldDiams=rows;}catch(e){/* 실패시 기본값 유지 */}};
  const loadCodes=async()=>{try{const r=await fetch(`${API}/api/codes`);codes=await r.json();}catch(e){codes={};}};
  const COLS=[['child_item','품번','item'],['item_name','품명','text'],
    ['diam','외경','num'],['thick','두께','num'],['length','길이','num'],['metal_gubun','재질','sel:metal'],['net_weight','중량','num'],
    ['qty','소요량','num'],['unit','단위','sel:unit'],
    ['lgroup','대분류','sel:lgroup'],['sgroup','소분류','sel:sgroup'],['make_type','생산구분','sel:make_type'],['cost_gubun','단가구분','sel:cost_gubun'],
    ['in_cust','매입처','vendor'],['gagong_proc','투입공정','proc'],
    ['sagub_default','사급','chk'],['kitting','키팅','chk'],['set_except','세트제외','chk'],['remarks','비고','text']];
  const codeName=(grp,v)=>{const a=codes[grp]||[];const f=a.find(x=>x.code==v);return f?f.name:(v||'');};
  const specOf=l=>[l.metal_gubun,(l.diam?('Ø'+l.diam):''),(l.thick?('×'+l.thick):'')].filter(Boolean).join(' ')||(l.item_spec||'');
  // ★동관(구리) 중량 자동계산: π/4×(OD²−ID²)×L×ρ/1e6 (ID=OD−2t, ρ=8.94 기존품목 역산확정). 치수·재질 입력 시 net_weight 자동.
  const CU_RHO=8.94;
  const isCu=m=>['CU','동','고강도'].includes((''+(m||'')).trim());
  const calcWeight=l=>{const d=+l.diam||0,t=+l.thick||0,ln=+l.length||0;
    if(!isCu(l.metal_gubun)||!(d>0&&t>0&&ln>0))return null;
    const id=d-2*t; if(id<=0)return null;
    return Math.round((Math.PI/4*(d*d-id*id)*ln)*CU_RHO/1e6*1e6)/1e6;};
  const CALCG={'3':'임율기반','8':'중량기반','9':'적용율','7':'세척'};
  const M=v=>(v==null||v==='')?'':Number(v).toLocaleString('ko-KR',{maximumFractionDigits:0});
  const M2=v=>(v==null||v==='')?'':Number(v).toLocaleString('ko-KR',{maximumFractionDigits:2});
  const q4=v=>Number(v||0).toLocaleString('ko-KR',{maximumFractionDigits:4});
  const ymd2date=y=>(y&&y.length===6)?`20${y.slice(0,2)}-${y.slice(2,4)}-${y.slice(4,6)}`:'';  // YYMMDD→date(달력)
  const date2ymd=d=>d?d.slice(2).replace(/-/g,''):'';                                            // date→YYMMDD(백엔드 파라미터)
  const doSearch=async q=>{q=(q||'').trim();query=q;item='';name='';lines=[];editMode=false;naeD=null;naeFor='';silD=null;silFor='';
    if(!q){results=[];draw();return;}
    try{const r=await fetch(`${API}/api/bom/search?q=${encodeURIComponent(q)}&include_past=${includePast?1:0}`);results=(await r.json()).rows||[];msg='';}
    catch(e){msg='백엔드 연결 실패 — 백엔드(uvicorn app:app --port 8010) 실행 필요';results=[];}draw();};
  const load=async (it, enterEdit)=>{it=(it||'').trim().toUpperCase();if(!it)return;loading=true;msg='';editMode=false;naeFor='';silFor='';draw();
    if(!codes.metal)await loadCodes();
    const [gp,tp]=await Promise.allSettled([   // ★get·tree 병렬(순차 대비 tree 시간만큼 단축)
      fetch(`${API}/api/bom/get?item=${encodeURIComponent(it)}`).then(r=>{if(!r.ok)throw new Error('HTTP '+r.status);return r.json();}),
      fetch(`${API}/api/bom/tree?item=${encodeURIComponent(it)}`).then(r=>r.json())]);
    if(gp.status==='fulfilled'){const j=gp.value;item=j.item;name=j.name||'';itemCut=j.cut_gubun||'';procs=j.procs||[];procMap={};procs.forEach(p=>procMap[p.code]=p.name);lines=(j.lines||[]).map(l=>({...l,spec:specOf(l)}));}
    else{msg='조회 실패: '+((gp.reason&&gp.reason.message)||gp.reason);lines=[];}
    if(tp.status==='fulfilled'){const tj=tp.value;tree=tj.rows||[];treeMax=tj.maxlevel||0;} else{tree=[];treeMax=0;}
    routeSel=0;routes=[];routesFor='';routeTree=null;routeTreeFor=-1;routeCost=null;routeCostFor=-1;   // ★품번 전환 → 후보선택 현행으로 리셋
    loadRoutes();   // 조달경로 후보 목록(현행+승인후보) 비동기 로드
    if(enterEdit && !RO && (typeof PERM==='undefined'||PERM.canEdit('unifybom'))){editMode=true;viewTree=false;}
    loading=false;results=[];draw();};
  const save=async()=>{const seen={},errs=[];
    lines.forEach((l,i)=>{const ch=(l.child_item||'').trim();if(!ch)errs.push(`${i+1}행: 품번 필요`);
      if(ch&&ch===item)errs.push(`${i+1}행: 자기참조`);if(ch&&seen[ch])errs.push(`${i+1}행: 중복 ${ch}`);if(ch)seen[ch]=1;});
    if(errs.length){alert('저장 불가:\n'+errs.join('\n'));return;}
    const mrows=lines.filter(l=>(l.child_item||'').trim()).map(l=>({item_code:l.child_item,item_name:l.item_name,
      item_spec:l.spec,metal_gubun:l.metal_gubun,diam:l.diam,thick:l.thick,length:l.length,net_weight:l.net_weight,
      unit:l.unit,in_cust:l.in_cust,sgroup:l.sgroup,lgroup:l.lgroup,make_type:l.make_type,cost_gubun:l.cost_gubun,status:l.status}));
    try{await fetch(`${API}/api/item/save`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({rows:mrows})});}
    catch(e){alert('품목 마스터 저장 실패: '+e.message);return;}
    try{const r=await fetch(`${API}/api/bom/save`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({item,lines})});
      const j=await r.json();if(!j.ok){alert('BOM 저장 거부 (백엔드 가드):\n'+(j.errors||[]).join('\n'));return;}
      alert(`저장 완료 — 마스터 ${mrows.length}건 · BOM ${j.count}구성`);load(item);}catch(e){alert('BOM 저장 실패: '+e.message);}};
  let _lastAdd=0;
  const addRow=()=>{const t=Date.now();if(t-_lastAdd<600)return;_lastAdd=t;  // ★rapid-click 가드(렌더 지연에 연타→중복행 방지)
    lines.push({child_item:'',item_name:'(저장 후 표시)',spec:'',qty:1,node_type:'부품',cs_calc_except:false,sagub_default:false,
    kitting:false,set_except:false,vir_item:false,lme_except:false,gagong_proc:'',cust_name:'',remarks:''});draw();};
  const doCopy=async()=>{
    const tgt=(prompt(`「${item}」의 BOM을 복사할 새 품번을 입력하세요.\n(유사공정 협력사 변형 등 — 신규 품번은 nx에만 저장)`,'')||'').trim().toUpperCase();
    if(!tgt)return; if(tgt===item){alert('원본과 다른 품번을 입력하세요.');return;}
    try{const r=await fetch(`${API}/api/bom/copy`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({source:item,target:tgt})});
      const j=await r.json(); if(!j.ok){alert('복사 실패: '+(j.error||(j.errors||[]).join('\n')));return;}
      alert(`복사 완료 — ${tgt} 에 ${j.count}구성 저장.${j.warn?'\n\n⚠ '+j.warn:''}`); load(tgt);
    }catch(e){alert('복사 오류: '+e.message);}};
  // ============ 신규 BOM 등록 (방식 ①LG업로드 ②복사 ③새로) ============
  const openNew=()=>{newReg={method:''};draw();};
  const closeNew=()=>{newReg=null;draw();};
  // 공통: 신규 편집 세션 진입(품번·구성·용접후보 세팅)
  const enterNew=async(topItem,topName,newLines,weldCand)=>{
    if(!codes.metal)await loadCodes(); await loadWeldDiams();
    item=(topItem||'').trim().toUpperCase(); name=topName||''; isNew=true; editMode=true; viewTree=false; newReg=null;
    newMaster={lgroup:'',sgroup:'',make_type:'3',cost_gubun:''};   // 제품 마스터속성 초기화(사용자 입력)
    results=[]; tree=[]; treeMax=0; naeFor=''; silFor='';
    lines=(newLines||[]).map(l=>({child_item:(l.child_item||'').toUpperCase(),item_name:l.item_name||'',spec:l.item_spec||'',
      qty:(l.qty!=null?+l.qty:1),unit:l.unit||'EA',node_type:'부품',cs_calc_except:false,sagub_default:false,kitting:false,
      set_except:false,vir_item:false,lme_except:false,gagong_proc:'',in_cust:'',cust_name:'',remarks:(l.supply_type?('LG:'+l.supply_type):'')}));
    // 용접봉 후보 → 용접공정 행(관경·점수는 직원입력, 기본 빈행)
    weldRows=[];
    (weldCand||[]).forEach(w=>{weldRows.push({weld_item:(w.child_item||w.weld_item||'').toUpperCase(),pipe_diam:'',weld_qty:''});});
    if(!weldRows.length) weldRows.push({weld_item:'RAC30599301-1',pipe_diam:'',weld_qty:''});
    fastenD=null; fastenFor='';   // 체결은 조립공정 팝업(loadNaeProc)에서 로드
    tab='bom'; draw();
  };
  // ①LG BOM 불러오기 — [기준정보›LG BOM관리]에 적재된 nx.lg_bom에서 모델 선택→tree 전개→구성 초안(파일 업로드 아님)
  let lgAcT=null;
  const lgAuto=(inp)=>{const q=inp.value.trim();clearTimeout(lgAcT);if(q.length<1)return;
    lgAcT=setTimeout(async()=>{try{const wk=(c.querySelector('#nw-lgwk')||{}).value||'';
      const r=await fetch(`${API}/api/lgbom/search?q=${encodeURIComponent(q)}&werks=${encodeURIComponent(wk)}`);
      const rows=(await r.json()).rows||[];const dl=c.querySelector('#nw-lgdl');
      if(dl)dl.innerHTML=rows.slice(0,40).map(x=>`<option value="${esc(x.model)}">${esc((x.modelnm||'').replace(/"/g,''))} · ${esc(x.werks)} · 구성${x.child_cnt}</option>`).join('');
    }catch(e){}},220);};
  const lgLoad=async(model,werks)=>{model=(model||'').trim().toUpperCase();if(!model){alert('LG 모델(상위품번)을 선택/입력하세요');return;}
    try{const r=await fetch(`${API}/api/lgbom/tree?model=${encodeURIComponent(model)}&werks=${encodeURIComponent(werks||'')}`);
      const j=await r.json();const rows=j.rows||[];
      if(!rows.length){alert(`nx.lg_bom에 ${model} 없음 — [기준정보 › LG BOM관리]에서 먼저 업로드하세요.`);return;}
      // 직속자식(parent_code==model, 없으면 stufe=1). RAC 용접봉 분리
      let direct=rows.filter(x=>String(x.parent_code||'').trim()===model);
      if(!direct.length) direct=rows.filter(x=>(+x.stufe===1));
      const seen={},lines=[],weld=[];
      direct.forEach(x=>{const ch=String(x.child_code||'').trim();if(!ch||seen[ch])return;seen[ch]=1;
        const rec={child_item:ch,item_name:x.child_desc||x.nx_desc||'',item_spec:x.child_spec||'',qty:(x.qty!=null?+x.qty:1),unit:x.unit||'EA',supply_type:x.supply_type||''};
        (ch.toUpperCase().startsWith('RAC')?weld:lines).push(rec);});
      alert(`LG BOM 불러오기 — 상위 ${model} · 구성 ${lines.length} · 용접봉 ${weld.length} (전개 ${rows.length}행, nx.lg_bom)`);
      enterNew(model, j.modelnm||'', lines, weld);
    }catch(e){alert('LG BOM 불러오기 오류: '+e.message);}
  };
  // ②기존 복사
  const copyNew=async()=>{const src=(prompt('복사할 기존 품번(원본)을 입력','')||'').trim().toUpperCase();if(!src)return;
    const tgt=(prompt(`「${src}」→ 새 품번(대상)을 입력`,'')||'').trim().toUpperCase();if(!tgt||tgt===src){alert('원본과 다른 새 품번 필요');return;}
    try{const r=await fetch(`${API}/api/bom/copy`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({source:src,target:tgt})});
      const j=await r.json();if(!j.ok){alert('복사 실패: '+(j.error||(j.errors||[]).join('\n')));return;}
      alert(`복사 완료 — ${tgt} 에 ${j.count}구성.${j.warn?'\n⚠ '+j.warn:''}`);newReg=null;isNew=false;load(tgt);
    }catch(e){alert('복사 오류: '+e.message);}};
  // ③완전 새로
  const blankNew=async()=>{const it=(prompt('신규 품번을 입력(nx에만 저장)','')||'').trim().toUpperCase();if(!it)return;
    const nm=(prompt('품명을 입력(선택)','')||'').trim();
    enterNew(it,nm,[],[]);};
  // 용접공정 패널(관경별 횟수, 실시간 미리보기)
  const weldPreview=(w)=>{const d=weldDiams.find(x=>Math.abs(x.pipe_diam-(+w.pipe_diam||0))<0.01);
    if(!d||!(+w.weld_qty>0))return {use:0,st:0};
    return {use:d.std_use_qty*(+w.weld_qty)*1.5, st:d.std_st*(+w.weld_qty)};};
  const weldPanel=()=>{
    const byRod={}; weldRows.forEach(w=>{const k=w.weld_item||'(용접봉)';(byRod[k]=byRod[k]||[]).push(w);});
    const opts=weldDiams.map(d=>`<option value="${d.pipe_diam}">${d.pipe_diam}φ (원단위 ${d.std_use_qty})</option>`).join('');
    let totUse=0; weldRows.forEach(w=>{totUse+=weldPreview(w).use;});
    return `<div style="border:1px solid #d6c3ea;border-radius:8px;margin-top:8px;background:#faf7ff">
      <div style="padding:6px 10px;display:flex;align-items:center;gap:8px;flex-wrap:wrap">
        <b style="color:#8e44ad">🔧 용접 공정 (관경별 용접점수 — 직원 입력)</b>
        <span style="color:#8a94a6;font-size:11px">용접봉 소요량 = Σ(표준소요량×점수)×1.5 · 저장시 nx.item_weld+proc_weld+routing 파생</span>
        <div style="flex:1"></div><b style="color:#8e44ad">Σ소요량 ${totUse.toFixed(5)}</b>
        <button class="btn ghost" id="wl-add" style="padding:1px 8px">＋ 용접점</button></div>
      <datalist id="wl-roddl"><option value="RAC30599301-1">1% 용접봉</option><option value="RAC30599327">3% 용접봉</option><option value="RAC30599303">BCUP</option></datalist>
      <div class="grid-wrap" style="max-height:24vh;overflow:auto"><table class="tbl" style="font-size:11px">
        <thead><tr><th>용접봉</th><th>관경</th><th class="num">점수</th><th class="num">소요량(미리보기)</th><th class="num">내부ST</th><th></th></tr></thead>
        <tbody>${weldRows.map((w,i)=>{const pv=weldPreview(w);return `<tr>
          <td><input class="wl-rod" data-i="${i}" list="wl-roddl" value="${esc(w.weld_item||'')}" style="width:120px" placeholder="RAC…"></td>
          <td><select class="wl-d" data-i="${i}" style="width:130px"><option value="">-관경-</option>${opts.replace(`value="${w.pipe_diam}"`,`value="${w.pipe_diam}" selected`)}</select></td>
          <td class="num"><input class="wl-q" data-i="${i}" type="number" step="1" min="0" value="${w.weld_qty}" style="width:52px"></td>
          <td class="num">${pv.use?pv.use.toFixed(5):''}</td><td class="num">${pv.st||''}</td>
          <td class="center"><span class="wl-del" data-i="${i}" style="cursor:pointer;color:#c0392b">✖</span></td></tr>`;}).join('')||'<tr><td colspan=6 class="empty">＋용접점으로 추가</td></tr>'}</tbody></table></div></div>`;
  };
  const bindWeld=()=>{
    const a=c.querySelector('#wl-add');if(a)a.onclick=()=>{weldRows.push({weld_item:(weldRows[weldRows.length-1]||{}).weld_item||'RAC30599301-1',pipe_diam:'',weld_qty:''});draw();};
    c.querySelectorAll('.wl-rod').forEach(el=>el.oninput=()=>{weldRows[+el.dataset.i].weld_item=el.value.trim().toUpperCase();});
    c.querySelectorAll('.wl-d').forEach(el=>el.onchange=()=>{weldRows[+el.dataset.i].pipe_diam=el.value;draw();});
    c.querySelectorAll('.wl-q').forEach(el=>el.oninput=()=>{weldRows[+el.dataset.i].weld_qty=el.value;const t=el.closest('tr');if(t){const pv=weldPreview(weldRows[+el.dataset.i]);const tds=t.querySelectorAll('td');tds[3].textContent=pv.use?pv.use.toFixed(5):'';tds[4].textContent=pv.st||'';}});
    c.querySelectorAll('.wl-del').forEach(el=>el.onclick=()=>{weldRows.splice(+el.dataset.i,1);draw();});
  };
  // 신규 저장: 마스터 + BOM(RAC자동라우팅) + 용접공정(관경별→파생)
  const saveNew=async()=>{
    if(!item){alert('품번 필요');return;}
    if(!newMaster.lgroup){alert('제품 대분류를 선택하세요.\n(대분류 미설정 시 부품 가공비가 원가에서 누락됩니다 — 공정 필터가 대분류 기준)');return;}
    const seen={},errs=[];
    lines.forEach((l,i)=>{const ch=(l.child_item||'').trim();if(ch&&ch===item)errs.push(`${i+1}행 자기참조`);if(ch&&seen[ch])errs.push(`${i+1}행 중복 ${ch}`);if(ch)seen[ch]=1;});
    if(errs.length){alert('저장 불가:\n'+errs.join('\n'));return;}
    // 1) 마스터 — ★제품(top) 자신 + 신규품번 포함 자식들. 제품 대분류/소분류/생산구분/단가구분 저장(가공비 필터 정상화)
    const mrows=[{item_code:item,item_name:name||item,lgroup:newMaster.lgroup,sgroup:newMaster.sgroup,
      make_type:newMaster.make_type,cost_gubun:newMaster.cost_gubun,status:'사용'}];
    lines.filter(l=>(l.child_item||'').trim()).forEach(l=>mrows.push({item_code:l.child_item,item_name:l.item_name,item_spec:l.spec,
      metal_gubun:l.metal_gubun,diam:l.diam,thick:l.thick,length:l.length,net_weight:l.net_weight,unit:l.unit,in_cust:l.in_cust,
      sgroup:l.sgroup,lgroup:l.lgroup,make_type:l.make_type,cost_gubun:l.cost_gubun,status:l.status}));
    try{if(mrows.length)await fetch(`${API}/api/item/save`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({rows:mrows})});}catch(e){alert('마스터 저장 실패: '+e.message);return;}
    // 2) BOM 구성(RAC는 백엔드가 proc_weld로 라우팅) — 신규품번 헤더 자동생성(target_name)
    try{const r=await fetch(`${API}/api/bom/save`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({item,target_name:name||item,lines})});
      const j=await r.json();if(!j.ok){alert('BOM 저장 거부:\n'+(j.errors||[]).join('\n'));return;}}catch(e){alert('BOM 저장 실패: '+e.message);return;}
    // 3) 용접공정(관경별 횟수) → item_weld+proc_weld+routing 파생 (용접봉별 그룹)
    const grp={}; weldRows.forEach(w=>{if((+w.weld_qty>0)&&w.pipe_diam&&w.weld_item){(grp[w.weld_item]=grp[w.weld_item]||[]).push({pipe_diam:+w.pipe_diam,weld_qty:+w.weld_qty});}});
    let wsum=0;
    try{for(const wi in grp){const r=await fetch(`${API}/api/weld/save`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({node:item,weld_item:wi,rows:grp[wi]})});
      const j=await r.json();if(j.ok)wsum+=j.use_qty;}}catch(e){alert('용접공정 저장 실패: '+e.message);return;}
    // ★체결 매트릭스 저장(신규등록 시 함께) — nx.item_fasten
    let fcnt=0;
    try{const frows=((fastenD&&fastenD.rows)||[]).filter(x=>(+x.qty)>0).map(x=>({fcode:x.fcode,qty:+x.qty}));
      const r=await fetch(`${API}/api/assywork/save`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({item,rows:frows,user:'웹'})});
      const j=await r.json();if(j.ok)fcnt=j.count;}catch(e){}
    alert(`신규 BOM 등록 완료\n품번 ${item} · 구성 ${lines.filter(l=>(l.child_item||'').trim()).length}\n용접봉 ${Object.keys(grp).length}종 · Σ소요량 ${wsum.toFixed(5)} · 체결 ${fcnt}공정`);
    isNew=false; load(item);
  };
  // ============ 탭바 ============
  // ★내부원가·실원가 탭은 개발 전용 — 품목 BOM 조회(RO)에서는 숨김(BOM구성만 노출)
  const tabbar=(act)=>`<div class="bm-tabs">
    <div class="bm-tab bm-tab-c ${act==='bom'?'on':''}" data-t="bom">🔀 BOM구성</div>
    <div class="bm-tab bm-tab-c ${act==='route'?'on':''}" data-t="route">🧭 라우팅</div>
    ${RO?'':`<div class="bm-tab bm-tab-c ${act==='nae'?'on':''}" data-t="nae">🧮 내부원가</div>
    <div class="bm-tab bm-tab-c ${act==='sil'?'on':''}" data-t="sil">💠 실원가</div>`}</div>`;
  const bindTabs=()=>{c.querySelectorAll('.bm-tab-c').forEach(el=>el.onclick=()=>{const t=el.dataset.t;if(t===tab)return;tab=t;
    if(t==='nae'&&item&&naeFor!==item&&!naeLoad){loadNae();return;}
    if(t==='sil'&&item&&silFor!==item&&!silLoad){loadSil();return;}
    draw();});};
  const naeToolbar=(rw)=>`<div class="toolbar" style="flex-wrap:wrap;gap:4px">
     <span class="rowcount"><b>${esc(item)}</b> · ${esc(name)}</span>
     <label class="tl" style="margin-left:8px">단가기준일</label><input class="inp" id="nae-ymd" type="date" value="${ymd2date(naeYmd)}" style="width:150px">
     <button class="btn" id="nae-go">🔍 조회</button><button class="btn ghost" id="nae-regen">🔄 재계산</button>
     ${rw}
     <div class="spacer"></div></div>`;
  const sumbar=(a,tot,totlb)=>{const chip=(lb,v,cl)=>`<span class="nae-chip"><em>${lb}</em><b style="color:${cl||'#243244'}">${M(v)}</b></span>`;
    const son2=(a.sagub!=null)?((+a.sonik||0)+(+a.sagub||0)):null;
    const sagChip=`<span class="nae-chip"><em>LG사급비</em><b style="color:#b8860b">${M((+a.sa_mat||0))}</b>${a.silsagub!=null?`<small style="display:block;font-size:10px;color:#8a5a1a">(실사급가: ${M(a.silsagub)}원)</small>`:''}</span>`;
    return `<div class="nae-sum">${chip('재료비',(+a.jae||0)-(+a.sa_mat||0),'#1c6b3a')}${sagChip}${chip('가공비',a.gagong,'#8a5a1a')}${chip('일반관리',a.ilban)}${chip('운반비',a.unban)}${chip('이윤',a.profit)}${chip(totlb,a[tot],'#1c47a0')}${chip('LG판가',a.lg,'#1c47a0')}${chip('손익',a.sonik,(a.sonik<0?'#c0392b':'#1c7c3a'))}${a.sagub!=null?chip('사급차액',a.sagub,(a.sagub<0?'#c0392b':'#1c7c3a'))+chip('손익(사급반영)',son2,(son2<0?'#c0392b':'#1c7c3a')):''}</div>`;};
  const naeViewBar=()=>{const V=[['proc','공정'],['weld','용접'],['fasten','체결'],['company','업체']];
    return `<div class="nae-vbar">${V.map(([k,l])=>`<span class="nae-vb ${naeView===k?'on':''}" data-v="${k}">${l}</span>`).join('')}</div>`;};
  // 역전개 재료(재료비만, 용접봉=종류별 합산)
  const flatMat=(rows)=>{const normal=[],weld={};
    rows.filter(r=>r.level>0 && (+r.mat||0)>0).forEach(r=>{
      if(String(r.code).toUpperCase().startsWith('RAC')){const b=String(r.code).split('-')[0];
        const w=weld[b]||(weld[b]={code:b,name:r.name,metal:r.metal,diam:r.diam,thick:r.thick,won:r.won,qty:0,mat:0});
        w.qty+=(+r.qty||0);w.mat+=(+r.mat||0);}
      else if(!isSub(r.code,r.haskids)) normal.push(r);});   // ★임의 SUB(SOCKET·20-1 등) 제외 — leaf 재료만
    return {normal:normal.sort((x,y)=>(+y.mat||0)-(+x.mat||0)),weldArr:Object.values(weld).sort((x,y)=>x.code<y.code?-1:1)};};
  const matTable=(a,rows,editable)=>{const fm=flatMat(rows);const jae=(+a.jae||0);
    const row=(r,weld)=>{const sp=r.diam?('Ø'+r.diam+(r.thick?'×'+r.thick:'')):(r.spec||'');const sel=naeSel===r.code;
      const canEd=!weld && (r.make_type==='1'||r.nproc||r.silver);
      return `<tr class="nae-mrow${sel?' sel':''}${weld?' weld':''}" ${weld?`data-weld="${esc(weld)}"`:`data-node="${esc(r.code)}"`} style="cursor:pointer">
        <td style="white-space:nowrap"><b>${esc(r.code)}</b>${weld?' <span class="nae-tg" style="color:#a8442a;border-color:#e6c0b3">용접봉→용접탭</span>':(r.silver?' <span class="nae-tg" style="color:#8e44ad;border-color:#d6c3ea">은납</span>':'')}${canEd?' <span class="nae-tg" style="color:#2f6db3;border-color:#bcd">✎공정</span>':''}</td>
        <td class="bcap" title="${esc(r.name)}" style="max-width:200px">${esc(r.name)}</td>
        <td title="${esc(sp)}" style="max-width:120px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#5a6b82">${esc(sp)}</td>
        <td class="center" style="color:#5a6b82">${esc(r.metal||'')}</td>
        <td class="num ${editable&&!weld?'nae-eq':''}" ${editable&&!weld?`data-node="${esc(r.code)}" data-parent="${esc(r.parent||'')}"`:''}>${editable&&!weld?`<input class="nae-qi" data-node="${esc(r.code)}" type="number" step="any" value="${r.eqty!=null?r.eqty:r.qty}" style="width:70px;text-align:right">`:q4(r.qty)}</td>
        <td class="num">${r.won?M2(r.won):''}</td>
        <td class="num" style="color:#1c6b3a"><b>${M(r.mat)}</b></td>
        <td class="num" style="color:#7a8aa0">${jae?((+r.mat||0)/jae*100).toFixed(1):'0.0'}%</td></tr>`;};
    return `<div class="grid-wrap" style="max-height:${naeSel?'26vh':'40vh'};overflow:auto"><table class="tbl bm-tbl">
       <thead><tr><th style="text-align:left">품번</th><th style="text-align:left">품명</th><th>규격</th><th>소재</th><th class="num">소요량</th><th class="num">단위단가</th><th class="num">재료비</th><th class="num">비율</th></tr></thead>
       <tbody>${fm.normal.map(r=>row(r)).join('')}${fm.weldArr.map(r=>row(r,r.code)).join('')}</tbody>
       <tfoot><tr class="nae-foot"><td colspan="6" style="text-align:right">재료비 합계</td><td class="num" style="color:#1c6b3a">${M(a.jae)}</td><td class="num">100%</td></tr></tfoot></table></div>`;};
  // ★내부원가 좌측 = LG BOM 수준 평면 재료표(SUB 해체·역전개평면, 트리 아님 — 대표 확정 [[newerp-sourcing-profile]])
  // 편집모델: 절삭부품(가공품)=행 [✎]→가공공정 팝업 · 제품(맨위)=[✎ 조립공정]→용접(관경별)·포장·체결 팝업 · 구매/부자재/사급=재료만(편집X)
  const naeFlatMat=(a,rows,prc)=>{
    const RW=(!RO&&(typeof PERM==='undefined'||PERM.canEdit('unifybom')));
    const fm=flatMat(rows); const jae=(+a.jae||0);
    const prodBtn=RW?`<button class="nae-edit-btn" data-node="${esc(item)}" title="제품 조립공정(용접 관경별·포장·체결)" style="padding:2px 9px;font-size:11px;background:#8e44ad;color:#fff;border:none;border-radius:4px;cursor:pointer">✎ 조립공정(용접·포장·체결)</button>`:'';
    const matRow=(r)=>{const sp=r.diam?('Ø'+r.diam+(r.thick?'×'+r.thick:'')):(r.spec||'');const sel=naeSel===r.code;
      const canEd=RW && (r.make_type==='1'||r.nproc||r.silver);
      const tag=canEd?'<span class="nae-tg" style="color:#2f6db3;border-color:#bcd">가공품</span>':'<span class="nae-tg" style="color:#8a97a8;border-color:#d5dde7">구매/부자재</span>';
      return `<tr class="nae-trow nae-mrow${sel?' sel':''}" data-node="${esc(r.code)}" style="cursor:pointer">
        <td style="white-space:nowrap;text-align:left"><span style="color:#7a8aa0">1</span> <span style="color:#a9b8cc">└</span> <b>${esc(r.code)}</b>${r.silver?' <span class="nae-tg" style="color:#8e44ad;border-color:#d6c3ea">은납</span>':''} ${tag}</td>
        <td class="bcap" title="${esc(r.name)}" style="max-width:200px;text-align:left">${esc(r.name)}</td>
        <td title="${esc(sp)}" style="max-width:120px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#5a6b82">${esc(sp)}</td>
        <td class="center" style="color:#5a6b82">${esc(r.metal||'')}</td>
        <td class="center">${r.sag?'<span class="nae-tg" style="color:#c0392b;border-color:#e6bcbc">사급</span>':''}</td>
        <td class="bcap" title="${esc(r.cust||'')}" style="max-width:140px;text-align:left;color:#5a6b82">${esc(r.cust||'')}</td>
        <td class="num">${q4(r.qty)}</td><td class="num">${r.won?M2(r.won):''}</td>
        <td class="num" style="color:#1c6b3a"><b>${M(r.mat)}</b></td>
        <td class="num" style="color:#7a8aa0">${jae?((+r.mat||0)/jae*100).toFixed(1):'0.0'}%</td>
        <td class="center">${canEd?`<button class="nae-edit-btn" data-node="${esc(r.code)}" style="padding:1px 6px;font-size:11px;background:#8e44ad;color:#fff;border:none;border-radius:3px;cursor:pointer;line-height:1.3">✎</button>`:''}</td></tr>`;};
    const weldRow=(r)=>`<tr class="nae-mrow" style="background:#fdf6f0">
        <td style="white-space:nowrap;text-align:left"><span style="color:#7a8aa0">1</span> <b>${esc(r.code)}</b> <span class="nae-tg" style="color:#a8442a;border-color:#e6c0b3">용접봉(제품조립)</span></td>
        <td class="bcap" title="${esc(r.name)}" style="max-width:200px;text-align:left">${esc(r.name)}</td>
        <td style="color:#5a6b82">${r.diam?('Ø'+r.diam):''}</td><td class="center" style="color:#5a6b82">${esc(r.metal||'')}</td>
        <td class="center"></td><td></td>
        <td class="num">${q4(r.qty)}</td><td class="num">${r.won?M2(r.won):''}</td>
        <td class="num" style="color:#1c6b3a"><b>${M(r.mat)}</b></td>
        <td class="num" style="color:#7a8aa0">${jae?((+r.mat||0)/jae*100).toFixed(1):'0.0'}%</td><td></td></tr>`;
    // ★레벨0 제품 행 — 조립공정(용접 관경별·포장·체결) 입력 지점. [✎]=조립공정 팝업(node===item→isAssy)
    const prodRow=`<tr class="nae-trow nae-mrow" data-node="${esc(item)}" style="background:#eef3fb;font-weight:700;cursor:pointer">
        <td style="white-space:nowrap;text-align:left"><span style="color:#1c47a0">0</span> <b style="color:#1c47a0">${esc(item)}</b> <span class="nae-tg" style="color:#1c47a0;border-color:#bcd">제품</span></td>
        <td class="bcap" title="${esc(name)}" style="max-width:200px;text-align:left">${esc(name)}</td>
        <td></td><td></td><td></td><td></td><td class="num">1</td><td></td>
        <td class="num" style="color:#1c6b3a"><b>${M(a.jae)}</b></td><td class="num" style="color:#7a8aa0">100%</td>
        <td class="center">${prodBtn}</td></tr>`;
    const weldBody=showWeld?fm.weldArr.map(weldRow).join(''):'';
    const body=(prodRow+fm.normal.map(matRow).join('')+weldBody);
    const weldBtn=`<button class="btn ghost" id="nae-weld" style="padding:2px 9px;font-size:11px">${showWeld?'🔧 용접봉 숨기기':`🔧 용접봉 표시${fm.weldArr.length?' ('+fm.weldArr.length+')':''}`}</button>`;
    return `<div style="display:flex;flex-direction:column;min-height:0;height:100%">
      <div class="summary-bar" style="flex:0 0 auto"><div class="s-item" style="white-space:nowrap;overflow:hidden;text-overflow:ellipsis"><b>${esc(item)}</b> ${esc(name)} <span class="nae-tg" style="color:#1c47a0;border-color:#bcd">제품</span> · <span style="color:#8a94a6">평면 재료표 · [✎]=공정편집</span></div><div style="flex:1"></div>${weldBtn}</div>
      <div class="grid-wrap" style="flex:1 1 auto;min-height:0;max-height:none;overflow:auto"><table class="tbl bm-tbl nae-tree">
        <thead><tr><th style="text-align:left">품번(레벨)</th><th style="text-align:left">품명</th><th>규격</th><th>소재</th><th class="center">사급</th><th style="text-align:left">매입처</th><th class="num">소요량</th><th class="num">단위단가</th><th class="num">재료비</th><th class="num">비율</th><th class="center">등록/수정</th></tr></thead>
        <tbody>${body}</tbody>
        <tfoot><tr class="nae-foot"><td colspan="8" style="text-align:right">재료비 합계</td><td class="num" style="color:#1c6b3a">${M(a.jae)}</td><td class="num">100%</td><td></td></tr></tfoot></table></div></div>`;};
  const procTable=(procList)=>{const sub=procList.reduce((s,p)=>s+(+p.amt||0),0);
    return `<div class="grid-wrap" style="max-height:${naeSel?'16vh':'34vh'};overflow:auto"><table class="tbl bm-tbl">
       <thead><tr><th style="text-align:left">공정</th><th class="num">작업량</th><th class="num">내부UPH</th><th class="num">임율</th><th>계산구분</th><th class="num">가공비</th></tr></thead>
       <tbody>${procList.map(p=>`<tr><td style="text-align:left;white-space:nowrap"><b>${esc(p.name)}</b> <span style="color:#aab;font-size:10px">${esc(p.code)}</span>${p.group&&p.group!=='가공'?` <span class="nae-tg" style="color:#a8442a;border-color:#e6c0b3">${esc(p.group)}</span>`:''}</td>
         <td class="num">${M2(p.wq)}</td><td class="num">${M2(p.uph)}</td><td class="num">${p.cg==='3'?M(p.labor):'<span style=color:#c8d0dc>-</span>'}</td>
         <td class="center" style="color:#5a6b82">${CALCG[p.cg]||p.cg||'임율'}</td><td class="num" style="color:#8a5a1a"><b>${M(p.amt)}</b></td></tr>`).join('')||'<tr><td colspan="6" class="empty">공정 없음 — 재료표에서 부품 클릭해 공정 입력</td></tr>'}</tbody>
       <tfoot><tr class="nae-foot"><td colspan="5" style="text-align:right">가공비 소계</td><td class="num" style="color:#8a5a1a">${M(sub)}</td></tr></tfoot></table></div>`;};
  const companyTable=(rows)=>`<div class="grid-wrap" style="max-height:44vh;overflow:auto"><table class="tbl bm-tbl">
     <thead><tr><th>레벨</th><th style="text-align:left">품번</th><th style="text-align:left">품명</th><th>단가구분</th><th class="num">소요량</th><th class="num">단위단가</th><th class="num">재료비</th><th class="num">가공비</th></tr></thead>
     <tbody>${rows.map(r=>`<tr style="background:${['#fff','#f6f9ff','#edf3ff','#e4edff','#dbe7ff'][Math.min(r.level,4)]}">
       <td class="center">${r.level}</td><td style="padding-left:${8+r.level*18}px;white-space:nowrap">${r.level?'└ ':''}<b>${esc(r.code)}</b></td>
       <td class="bcap" title="${esc(r.name)}" style="max-width:200px">${esc(r.name)}</td><td class="center" style="color:#5a6b82">${esc(r.cost_gubun||'')}</td>
       <td class="num">${q4(r.qty)}</td><td class="num">${r.won?M2(r.won):''}</td><td class="num" style="color:#1c6b3a">${M(r.mat)}</td><td class="num" style="color:#8a5a1a">${M(r.gag)}</td></tr>`).join('')||'<tr><td colspan="8" class="empty">구성 없음</td></tr>'}</tbody></table></div>`;
  // ============ 내부원가 로드/그리기 ============
  const loadNae=async(fresh)=>{if(!item)return;naeLoad=true;naeSel='';naeProcD=null;draw();
    try{const r=await fetch(`${API}/api/cost/nae?item=${encodeURIComponent(item)}&ymd=${encodeURIComponent(naeYmd)}&bom=nx${fresh?'&fresh=1':''}`);
      if(!r.ok)throw new Error('HTTP '+r.status);naeD=await r.json();naeFor=item;}
    catch(e){naeD={error:e.message};}naeLoad=false;draw();};
  // ★carrier-aware 공정입력: /api/cost/proc/get → 가공(own) + 용접봉 carrier별 조립공정(용접/체결/포장). carrier별 in-place(통합/이동 금지).
  const loadNaeProc=async(node,openModal)=>{naeSel=node;naeProcD=null;naeProcLoading=true;if(openModal)naeModal=true;draw();  // ★즉시 로딩모달 표시(사외망 지연 대비)
    const enc=encodeURIComponent(node);
    // ★4개 fetch 순차(≈9초)→병렬(≈3초). 사외망 DB 지연시 체감 크게 개선
    const [,,wj,j]=await Promise.all([
      loadWeldDiams(),
      loadFasten(node),   // ★체결 매트릭스도 팝업에 로드(노드별)
      fetch(`${API}/api/weld/get?node=${enc}`).then(r=>r.json()).catch(()=>({})),
      fetch(`${API}/api/cost/proc/get?node=${enc}`).then(r=>r.json()).catch(e=>({error:e.message}))
    ]);
    naeProcLoading=false;
    // 조립 용접(관경별) — 제품/SUB 레벨에서 용접점 편집용
    let weldPoints=[], weldCarriers=[];
    (wj.welds||[]).forEach(w=>{(w.rows||[]).forEach(x=>weldPoints.push({weld_item:w.weld_item,pipe_diam:x.pipe_diam,weld_qty:x.weld_qty}));});
    weldCarriers=wj.carriers||[];
    try{if(j.error)throw new Error(j.error);
      const cat=j.catalog||[]; const own0={}; (j.own_procs||[]).forEach(p=>own0[p.proc_code]=p);
      // 가공 own = 조립외 카탈로그 전체(기존값 병합)
      const own=cat.filter(p=>!p.is_assy).map(p=>({proc_code:p.proc_code,name:p.name,group:p.group,std_uph:p.std_uph||0,
        work_qty:(own0[p.proc_code]||{}).work_qty||0,prod_uph:(own0[p.proc_code]||{}).prod_uph||p.std_uph||0,calc_gubun:(own0[p.proc_code]||{}).calc_gubun||'3'}));
      // 용접봉 carrier별 = 조립 카탈로그 전체(해당 carrier 기존값 병합)
      const carriers=(j.carriers||[]).map(cr=>{const cur={};(cr.procs||[]).forEach(p=>cur[p.proc_code]=p);
        // 조립공정군(추가용) + ★carrier에 실재하는 비-assy 공정(예:53 가공)도 포함해 표시·보존(유실 방지)
        const assy=cat.filter(p=>p.is_assy); const ac=new Set(assy.map(p=>p.proc_code));
        const extra=(cr.procs||[]).filter(p=>!ac.has(p.proc_code));
        return {weld_item:cr.weld_item,use_qty:cr.use_qty,pipe_diam:cr.pipe_diam,unit_qty:cr.unit_qty,loss_factor:(cr.loss_factor==null?1.5:cr.loss_factor),meta_ok:cr.meta_ok,
          rows:assy.concat(extra).map(p=>({proc_code:p.proc_code,name:p.name,group:p.group,std_uph:p.std_uph||0,
          work_qty:(cur[p.proc_code]||{}).work_qty||0,prod_uph:(cur[p.proc_code]||{}).prod_uph||p.std_uph||0,calc_gubun:(cur[p.proc_code]||{}).calc_gubun||'3'}))};});
      // 제품/SUB(=조립 노드) 판정: 용접봉 carrier 존재 or 최상위 품번(item)
      const isAssy=(carriers.length>0)||(weldCarriers.length>0)||(node===item);
      // ★용접봉 종류=노드당 1개(상단 드롭다운). 기존 종류들 목록 + 기본선택
      const weldTypes=[...new Set([...weldCarriers, ...weldPoints.map(w=>w.weld_item)].filter(Boolean))];
      const weldItem=weldTypes[0]||'RAC30599301-1';
      // 선택 종류의 관경별 횟수 맵
      const weldCounts={};
      weldPoints.forEach(w=>{if(w.weld_item===weldItem && w.pipe_diam)weldCounts[(+w.pipe_diam).toFixed(2)]=(+w.weld_qty||0);});
      naeProcD={node,pipe_diam:j.pipe_diam,own,carriers,isAssy,weldPoints,catalog:cat,weldTypes,weldItem,weldCounts};
      if(openModal)naeModal=true;
    }catch(e){naeProcD={node,own:[],carriers:[],isAssy:false,weldPoints:[],error:e.message};}draw();};
  const saveNaeProc=async()=>{if(!naeSel||!naeProcD)return;
    const pick=arr=>arr.filter(p=>(+p.work_qty)>0).map(p=>({proc_code:p.proc_code,work_qty:+p.work_qty,prod_uph:+p.prod_uph,calc_gubun:p.calc_gubun||'3'}));
    const payload={node:naeSel,own_procs:pick(naeProcD.own||[]),carriers:(naeProcD.carriers||[]).map(cr=>({weld_item:cr.weld_item,loss_factor:+cr.loss_factor||1.5,procs:pick(cr.rows||[])}))};
    try{const r=await fetch(`${API}/api/cost/proc/save`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
      const j=await r.json();if(!j.ok){alert('공정 저장 실패');return;}
      // ★체결 매트릭스 → nx.routing(FS행) 저장(node별)
      try{const frows=((fastenD&&fastenD.rows)||[]).filter(x=>(+x.qty)>0).map(x=>({fcode:x.fcode,qty:+x.qty}));
        await fetch(`${API}/api/assywork/save`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({item:naeSel,rows:frows,user:'웹'})});}catch(e){}
      // ★관경별 용접 매트릭스 → /api/weld/save (선택 용접봉종류 1개, node). 관경별 횟수 입력분만(weld_qty>0)
      let wmsg='';
      if(naeProcD.isAssy){
        const wi=naeProcD.weldItem, cnt=naeProcD.weldCounts||{};
        const rows=Object.keys(cnt).filter(d=>(+cnt[d])>0).map(d=>({pipe_diam:+d,weld_qty:+cnt[d]}));
        if(wi && rows.length){try{const wr=await fetch(`${API}/api/weld/save`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({node:naeSel,weld_item:wi,rows})});
          const wj=await wr.json();if(wj.ok)wmsg+=`\n용접 ${wi}: 소요량 ${wj.use_qty} · 내부ST ${wj.inner_st} (${wj.total_points}점)`;}catch(e){}}
      }
      const rc=(j.weld_recalc||[]).map(x=>`${x.carrier} 소요 ${x.use_qty}`).join(', ');
      naeModal=false;naeSel='';naeProcD=null;alert(`공정 저장(가공 ${j.own} · 용접봉 ${j.carriers}건) · 재계산${rc?'\n용접봉 소요량(ST): '+rc:''}${wmsg}`);
      naeFor='';if(isNew){naeModal=false;draw();}else if(tab==='bom'){await load(item);}else{await loadNae(true);}}catch(e){alert('저장 오류: '+e.message);}};
  // 공정입력 팝업(모달) 이벤트 바인딩 — 내부원가/BOM구성 탭 공유(close=draw()로 현재 탭 재렌더)
  const wireProcModal=()=>{
    const rowsOf=sec=>sec==='own'?(naeProcD&&naeProcD.own):((naeProcD&&naeProcD.carriers[+sec.slice(1)])||{}).rows;
    PROC_MODAL_BIND(c,{
      onClose:()=>{naeModal=false;draw();},
      onSave:saveNaeProc,
      onProcInput:(sec,i,v)=>{const a=rowsOf(sec);if(a&&a[i])a[i].work_qty=+v||0;},   // 입력중 값만(재draw 없음=포커스 유지, 기존 동작 동일)
      onProcUph:(sec,i,v)=>{const a=rowsOf(sec);if(a&&a[i])a[i].prod_uph=+v||0;},     // ★UPH 편집 write-back(표준 자동조회+수정)
      onWeldCount:(d,v)=>{if(!naeProcD)return;const val=+v||0;if(val>0)naeProcD.weldCounts[d]=val;else delete naeProcD.weldCounts[d];draw();},
      onWeldType:(v)=>{if(!naeProcD)return;naeProcD.weldItem=v;const cnt={};(naeProcD.weldPoints||[]).forEach(w=>{if(w.weld_item===v&&w.pipe_diam)cnt[(+w.pipe_diam).toFixed(2)]=(+w.weld_qty||0);});naeProcD.weldCounts=cnt;draw();},
    });
    // 레거시 procEditPanel 잔여(.pu/.pl) — 현재 모달엔 없어 no-op이나 보존(회귀 방지)
    const rowsOf2=sec=>sec==='own'?(naeProcD&&naeProcD.own):((naeProcD&&naeProcD.carriers[+sec.slice(1)])||{}).rows;
    c.querySelectorAll('.pu').forEach(el=>el.oninput=()=>{const a=rowsOf2(el.dataset.sec);if(a&&a[+el.dataset.i])a[+el.dataset.i].prod_uph=+el.value||0;});
    c.querySelectorAll('.pl').forEach(el=>el.oninput=()=>{const cr=naeProcD&&naeProcD.carriers[+el.dataset.c];if(cr)cr.loss_factor=+el.value||1.5;});
    c.querySelectorAll('.fq').forEach(el=>el.oninput=()=>{const i=+el.dataset.i;if(fastenD&&fastenD.rows[i])fastenD.rows[i].qty=+el.value||0;});  // ★팝업 내 체결 횟수 입력
  };
  const saveNaeMaster=async()=>{const rows=(naeD&&naeD.rows)||[];const qtyC=[];const specM={};const num=v=>{const n=parseFloat(v);return isNaN(n)?null:n;};
    rows.forEach(r=>{const e=naeEdits[r.code];if(!e)return;
      if(e.eqty!==undefined && r.parent && num(e.eqty)!==null && num(e.eqty)!==+r.qty) qtyC.push({parent:r.parent,child:r.code,qty:num(e.eqty)});
      const sp={};let sc=false;
      if(e.diam!==undefined && num(e.diam)!==null && num(e.diam)!==+r.diam){sp.diam=num(e.diam);sc=true;}
      if(e.thick!==undefined && num(e.thick)!==null && num(e.thick)!==+r.thick){sp.thick=num(e.thick);sc=true;}
      if(e.metal!==undefined && String(e.metal).trim().toUpperCase()!==(r.metal||'').toUpperCase()){sp.metal_gubun=String(e.metal).trim().toUpperCase();sc=true;}
      if(sc){sp.item_code=r.code;specM[r.code]=Object.assign(specM[r.code]||{},sp);}});
    const nQ=qtyC.length,nS=Object.keys(specM).length;
    if(!nQ&&!nS){alert('변경된 값이 없습니다.');return;}
    if(!confirm(`소요량 ${nQ}건 · 원소재 스펙 ${nS}건 저장하시겠습니까?\n(단가는 마감때만 수정 가능 — 제외)`))return;
    try{for(const q of qtyC){const r=await fetch(`${API}/api/bom/qty`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(q)});if(!(await r.json()).ok)throw new Error('소요량 '+q.child);}
      for(const s of Object.values(specM)){const r=await fetch(`${API}/api/item/spec`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(s)});if(!(await r.json()).ok)throw new Error('스펙 '+s.item_code);}
      naeEditM=false;naeEdits={};alert(`저장 완료 — 소요량 ${nQ} · 스펙 ${nS} · 재계산`);await loadNae(true);}catch(e){alert('저장 오류: '+e.message);}};
  const drawNae=()=>{
    const RW=(!RO&&(typeof PERM==='undefined'||PERM.canEdit('unifybom')));
    const a=(naeD&&naeD.agg)||{},rows=(naeD&&naeD.rows)||[],prc=(naeD&&naeD.procs)||[];
    const procBtn='';  // ★공정입력은 좌측 트리 [등록/수정]→팝업으로 이동(인라인 matTable 편집 제거). 소요량 편집은 BOM구성 탭.
    let content='';
    if(naeLoad) content=`<div class="empty">계산 중…</div>`;
    else if(naeD&&naeD.error) content=`<div class="page-sub" style="color:#c0392b">⚠ ${esc(naeD.error)}</div>`;
    else if(!naeFor) content=`<div class="empty">품번을 조회하세요.</div>`;
    else{
      const view=naeView;
      let mid='';
      if(view==='proc') mid=`<div class="nae-2col" style="flex:1 1 auto;min-height:0;height:100%;grid-template-rows:minmax(0,1fr);align-items:stretch">${naeFlatMat(a,rows,prc)}${naeRightPanel(a,rows,prc)}</div>`;
      else if(view==='weld'){const wp=prc.filter(p=>p.group==='용접');mid=`<div style="flex:1 1 auto;min-height:0;overflow:auto">${matTable(a,rows.filter(r=>String(r.code).toUpperCase().startsWith('RAC')||r.silver),false)}${procTable(wp)}</div>`;}
      else if(view==='fasten'){mid=fastenMatrix();}
      else mid=`<div style="flex:1 1 auto;min-height:0;overflow:auto">${companyTable(rows)}</div>`;
      content=`<div style="flex:0 0 auto">${sumbar(a,'naewon','내부원가')}${naeViewBar()}</div>${mid}${naeModal?naeProcModal():''}`;
    }
    // ★.content{overflow:hidden} 이므로 여기서 flex컬럼 height:100% + 본문 flex:1 min-height:0 overflow:auto 로 자체 스크롤 확보(클립 방지)
    c.innerHTML=`
     <div style="display:flex;flex-direction:column;height:100%;min-height:0">
       <div style="flex:0 0 auto">
         <div class="page-title">🔀 품목 BOM관리 <span style="font-size:12px;color:var(--muted);font-weight:400">내부원가(전공정 자체 가정, nx.bom)</span></div>
         ${tabbar('nae')}
         ${naeToolbar(procBtn)}
       </div>
       <div style="flex:1 1 auto;min-height:0;display:flex;flex-direction:column">${content}</div>
     </div>
     ${naeCss()}`;
    bindTabs();
    const g=id=>c.querySelector(id);
    g('#nae-go').onclick=()=>{naeYmd=date2ymd(g('#nae-ymd').value)||naeYmd;loadNae();};
    g('#nae-regen').onclick=()=>loadNae(true);
    {const w=g('#nae-weld');if(w)w.onclick=()=>{showWeld=!showWeld;drawNae();};}
    // [조립공정] 툴바 버튼 제거 — 레벨0(제품) 행의 [등록/수정]이 동일 팝업(용접·포장·체결) 담당(중복 제거)
    c.querySelectorAll('.nae-vb').forEach(el=>el.onclick=async()=>{naeView=el.dataset.v;if(naeView==='fasten')await loadFasten(item);drawNae();});
    c.querySelectorAll('.fq').forEach(el=>el.oninput=()=>{const i=+el.dataset.i;if(fastenD&&fastenD.rows[i])fastenD.rows[i].qty=+el.value||0;});
    {const fs=c.querySelector('#ft-save');if(fs)fs.onclick=saveFasten;}
    // 좌측 레벨트리: 행 클릭=우측 조회 / [등록/수정] 버튼=팝업
    c.querySelectorAll('.nae-trow[data-node]').forEach(el=>el.onclick=e=>{if(e.target.closest('.nae-edit-btn'))return;loadNaeProc(el.dataset.node,false);});
    c.querySelectorAll('.nae-edit-btn').forEach(el=>el.onclick=e=>{e.stopPropagation();loadNaeProc(el.dataset.node,true);});
    // 우측 조회 헤더의 [등록/수정]
    {const re=g('#nae-right-edit');if(re)re.onclick=()=>{if(naeProcD&&naeProcD.node===naeSel){naeModal=true;drawNae();}else loadNaeProc(naeSel,true);};}
    // 팝업(모달) — 공유 바인딩
    wireProcModal();
  };
  // ===== 좌측 BOM 레벨트리(BOM구성 탭 형태 재사용: /api/bom/tree=tree). 레벨0=제품·레벨1+=부품 =====
  const naeLevelTree=(a,rows)=>{
    const rowsT=(tree||[]).filter(r=>!isW(r.nm));   // 용접봉(RAC)은 공정처리 → 트리 제외
    const body=rowsT.map(r=>{const sp=r.diam?('Ø'+r.diam+(r.thick?'×'+r.thick:'')):(r.spec||'');const sel=naeSel===r.code;
      const bg=['#fff','#f6f9ff','#edf3ff','#e4edff','#dbe7ff','#d3e2ff'][Math.min(r.level,5)];
      return `<tr class="nae-trow" data-node="${esc(r.code)}" data-level="${r.level}" style="cursor:pointer;background:${sel?'#e8f0ff':bg}">
        <td class="center" style="font-weight:${r.level?400:700};color:${r.level?'#7a8aa0':'#1c47a0'}">${r.level}</td>
        <td style="padding-left:${8+r.level*20}px;text-align:left;white-space:nowrap">${r.level?'<span style="color:#a9b8cc">└ </span>':''}<b style="color:${r.level?'#243244':'#1c47a0'}">${esc(r.code)}</b>${r.level===0?' <span class="nae-tg" style="color:#1c47a0;border-color:#bcd">제품</span>':(r.haskids?' <span class="nae-tg" style="color:#2f6db3;border-color:#bcd">SUB</span>':'')}</td>
        <td class="bcap" title="${esc(r.nm)}" style="max-width:190px;overflow:hidden;text-overflow:ellipsis;text-align:left">${esc(r.nm)}</td>
        <td class="center" style="color:#5a6b82">${esc(sp)}</td>
        <td class="num">${q4(r.qty)}</td>
        <td class="center"><button class="nae-edit-btn" data-node="${esc(r.code)}" data-level="${r.level}" style="padding:1px 6px;font-size:11px;background:#8e44ad;color:#fff;border:none;border-radius:3px;cursor:pointer;line-height:1.3">✎</button></td></tr>`;}).join('')||'<tr><td colspan=6 class="empty">구성 없음 — 조회하세요</td></tr>';
    return `<div style="display:flex;flex-direction:column;min-height:0;height:100%">
      <div class="summary-bar" style="flex:0 0 auto"><div class="s-item"><b>BOM 레벨트리</b> · 레벨0=제품 / 레벨1+=부품 · 행클릭=우측조회 · <b>[✎]</b>=공정입력 팝업</div></div>
      <div class="grid-wrap" style="flex:1 1 auto;min-height:0;max-height:none;overflow:auto"><table class="tbl bm-tbl nae-tree">
        <thead><tr><th>레벨</th><th style="text-align:left">품번</th><th style="text-align:left">품명</th><th>규격</th><th class="num">소요량</th><th class="center">등록/수정</th></tr></thead>
        <tbody>${body}</tbody></table></div></div>`;};
  // 공정 롤업 테이블(내부 max-height cap 없음 — 우측 flex 그리드가 높이 담당)
  const naeProcRoll=(procList)=>{const sub=(procList||[]).reduce((s,p)=>s+(+p.amt||0),0);
    return `<table class="tbl bm-tbl"><thead><tr><th style="text-align:left">공정</th><th class="num">작업량</th><th class="num">내부UPH</th><th class="num">임율</th><th>계산구분</th><th class="num">가공비</th></tr></thead>
      <tbody>${(procList||[]).map(p=>`<tr><td style="text-align:left;white-space:nowrap"><b>${esc(p.name)}</b> <span style="color:#aab;font-size:10px">${esc(p.code)}</span>${p.group&&p.group!=='가공'?` <span class="nae-tg" style="color:#a8442a;border-color:#e6c0b3">${esc(p.group)}</span>`:''}</td>
        <td class="num">${M2(p.wq)}</td><td class="num">${M2(p.uph)}</td><td class="num">${p.cg==='3'?M(p.labor):'<span style=color:#c8d0dc>-</span>'}</td>
        <td class="center" style="color:#5a6b82">${CALCG[p.cg]||p.cg||'임율'}</td><td class="num" style="color:#8a5a1a"><b>${M(p.amt)}</b></td></tr>`).join('')||'<tr><td colspan="6" class="empty">공정 없음</td></tr>'}</tbody>
      <tfoot><tr class="nae-foot"><td colspan="5" style="text-align:right">가공비 소계</td><td class="num" style="color:#8a5a1a">${M(sub)}</td></tr></tfoot></table>`;};
  // ===== 우측 조회(선택 노드) — 레벨0=제품 롤업 / 레벨1=부품 =====
  const naeRightPanel=(a,rows,prc)=>{
    if(!naeSel) return `<div style="display:flex;flex-direction:column;min-height:0;height:100%"><div class="summary-bar" style="flex:0 0 auto"><div class="s-item">← 좌측 <b>레벨 행</b>을 선택하세요 (레벨0 제품=전체 롤업 · 레벨1 부품)</div></div><div class="grid-wrap" style="flex:1 1 auto;min-height:0;max-height:none;overflow:auto">${naeProcRoll(prc)}</div></div>`;
    const isProd=(naeSel===item);
    const nrow=(rows||[]).find(r=>r.code===naeSel)||{};
    const mat=isProd?(+a.jae||0):(+nrow.mat||0), gag=isProd?(+a.gagong||0):(+nrow.gag||0);
    const nm=isProd?name:(nrow.name||'');
    let midT;
    if(isProd){ midT=naeProcRoll(prc); }   // 제품 = 전체 공정 롤업(가공비 포함, cap 없음)
    else{ // 부품 = 그 노드 공정(naeProcD 로드시 ST 표시)
      const pd=(naeProcD&&naeProcD.node===naeSel)?naeProcD:null;
      if(!pd) midT=`<div class="empty" style="padding:10px">행을 클릭하면 공정을 불러옵니다…</div>`;
      else{const list=(pd.own||[]).filter(p=>p.work_qty>0);
        midT=`<table class="tbl bm-tbl"><thead><tr><th style="text-align:left">가공공정</th><th class="num">작업ST</th><th class="num">내부UPH</th></tr></thead>
          <tbody>${list.map(p=>`<tr><td style="text-align:left"><b>${esc(p.name)}</b> <span style="color:#aab;font-size:10px">${esc(p.proc_code)}</span></td><td class="num">${M2(p.work_qty)}</td><td class="num">${M2(p.prod_uph)}</td></tr>`).join('')||'<tr><td colspan=3 class="empty">등록된 공정 없음 — [등록/수정]으로 입력</td></tr>'}</tbody></table>`;}
    }
    return `<div style="display:flex;flex-direction:column;min-height:0;height:100%">
      <div class="summary-bar" style="flex:0 0 auto;flex-wrap:wrap"><div class="s-item"><b>${esc(naeSel)}</b> ${esc(nm)} ${isProd?'<span class="nae-tg" style="color:#1c47a0;border-color:#bcd">제품 롤업</span>':'<span class="nae-tg" style="color:#7a8aa0">부품</span>'}</div>
        <div class="s-item">재료비 <b style="color:#1c6b3a">${M(mat)}</b></div><div class="s-item">가공비 <b style="color:#8a5a1a">${M(gag)}</b></div>
        <div style="flex:1"></div><button class="btn" id="nae-right-edit" style="background:#8e44ad;color:#fff">✎ 등록/수정</button></div>
      <div class="grid-wrap" style="flex:1 1 auto;min-height:0;max-height:none;overflow:auto">${midT}</div></div>`;};
  // ===== 등록/수정 팝업(모달) — 레거시형 가로 매트릭스 2단(관경 컬럼 / 공정 컬럼, 세로헤더) =====
  // ★공정 팝업 = 공유 렌더러(PROC_MODAL_HTML) 사용. naeProcD → 캐노니컬 pd(cols=own 가공 + carriers[0] 조립).
  const naeProcModal=()=>{
    if(!naeProcD) return PROC_MODAL_HTML(null);
    const isAssy=naeProcD.isAssy, node=naeProcD.node;
    const lvl=isAssy?'제품/조립 — 관경별 용접 + 조립공정(용접·포장·체결)':'부품 — 가공공정';
    const cols=[];
    (naeProcD.own||[]).forEach((p,i)=>cols.push({name:p.name,code:p.proc_code,sec:'own',idx:i,uph:p.prod_uph,cg:p.calc_gubun,wq:p.work_qty}));
    if(naeProcD.carriers&&naeProcD.carriers[0]) naeProcD.carriers[0].rows.forEach((p,i)=>cols.push({name:p.name,code:p.proc_code,sec:'c0',idx:i,uph:p.prod_uph,cg:p.calc_gubun,wq:p.work_qty}));
    return PROC_MODAL_HTML({node,subtitle:lvl,isAssy,weldDiams,weldItem:naeProcD.weldItem,weldTypes:naeProcD.weldTypes,weldCounts:naeProcD.weldCounts,cols,fastenHtml:fastenMatrix(true)});};  // ★fastenMatrix는 클로저 로컬 → 여기서 만들어 pd로 전달(전역 PROC_MODAL_HTML은 접근불가)
  const procSecTable=(rows,sec,title,titleColor)=>`<div style="padding:4px 8px 2px;font-weight:600;color:${titleColor};font-size:11px">${title}</div>
     <table class="tbl" style="font-size:11px"><thead><tr><th>공정</th><th class="num">작업 ST</th><th class="num">내부UPH</th></tr></thead>
       <tbody>${(rows||[]).map((p,i)=>`<tr${p.work_qty>0?' style="background:#f0f7f0"':''}><td>${esc(p.name)} <span style="color:#c3c9d4;font-size:10px">${esc(p.proc_code)}</span></td>
         <td class="num"><input class="pq" data-sec="${sec}" data-i="${i}" type="number" step="any" value="${p.work_qty||''}" style="width:66px"></td>
         <td class="num"><input class="pu" data-sec="${sec}" data-i="${i}" type="number" step="any" value="${p.prod_uph||''}" style="width:66px"></td></tr>`).join('')||'<tr><td colspan=3 class="empty">공정 없음</td></tr>'}</tbody></table>`;
  const procEditPanel=()=>{
     if(!naeProcD) return `<div style="border:1px solid #cfe0ff;border-radius:8px;margin-top:6px;background:#f7faff;padding:10px" class="empty">공정 로딩…</div>`;
     const carSecs=(naeProcD.carriers||[]).map((cr,k)=>{
        const mok=(+cr.meta_ok===1);
        const badge=mok?`<span title="용접ST·배수 변경 시 소요량 자동재계산" style="color:#1c7c3a;font-size:10px">● 재계산 가능</span>`
                       :`<span title="관경 정본(item_weld) 미매칭 — 소요량 정본 보존, 자동재계산 비활성(배수만 저장)" style="color:#b8860b;font-size:10px">▲ 소요량 정본보존</span>`;
        const lfBox=`<span style="color:#8a94a6;font-size:10px">배수(로스)</span><input class="pl" data-c="${k}" type="number" step="0.1" min="0" value="${(+cr.loss_factor||1.5)}" style="width:52px" title="용접봉 소요량 = 용접ST × 원단위 × 배수. 레거시 기본 1.5">`;
        return `<div style="border-top:1px dashed #cfe0ff;margin-top:4px">`+
        procSecTable(cr.rows,'c'+k,`🔗 용접봉 ${esc(cr.weld_item)} <span style="color:#8a94a6;font-weight:400">(조립: 용접·은납·체결·포장 · 소요량 ${(+cr.use_qty||0).toFixed(4)} · 원단위 ${(+cr.unit_qty||0).toFixed(6)})</span> ${badge} ${lfBox}`,'#8e44ad')+`</div>`;}).join('');
     const assy=naeProcD.isAssy;
     return `<div style="border:1px solid #cfe0ff;border-radius:8px;margin-top:6px;background:#f7faff">
     <div style="padding:6px 10px;display:flex;align-items:center;gap:8px;flex-wrap:wrap;position:sticky;top:0;z-index:3;background:#eef4ff;border-radius:8px 8px 0 0;border-bottom:1px solid #cfe0ff"><b style="color:#1c47a0">✎ 공정 지정 ${esc(naeSel)}</b>
       <span style="color:#8a94a6;font-size:10px">${assy?'제품/조립 레벨 — 가공+조립(용접·체결·포장) 입력':'부품 레벨 — 가공공정만'}</span>
       <div style="flex:1"></div><button class="btn" id="pm-save" style="background:#1c7c3a;color:#fff;padding:1px 8px">💾 등록</button><button class="btn ghost" id="pm-close" style="padding:1px 8px">✖</button></div>
     <div style="padding:0 2px 6px">
       ${procSecTable(naeProcD.own,'own','⚙ 가공공정 (자체)','#1c47a0')}
       ${assy?naeWeldSection():''}
       ${carSecs||''}
     </div></div>`;};
  // 조립 용접(관경별 점수 → 용접봉 소요량 자동파생, /api/weld/save) — 제품/SUB 레벨만
  const naeWeldPrev=(w)=>{const d=weldDiams.find(x=>Math.abs(x.pipe_diam-(+w.pipe_diam||0))<0.01);
    if(!d||!(+w.weld_qty>0))return{use:0,st:0};return{use:d.std_use_qty*(+w.weld_qty)*1.5,st:d.std_st*(+w.weld_qty)};};
  const naeWeldSection=()=>{
    const wp=naeProcD.weldPoints||[];const opts=weldDiams.map(d=>`<option value="${d.pipe_diam}">${d.pipe_diam}φ (${d.std_use_qty})</option>`).join('');
    let tu=0;wp.forEach(w=>{tu+=naeWeldPrev(w).use;});
    return `<div style="border-top:2px solid #d6c3ea;margin-top:4px;background:#faf7ff">
      <div style="padding:4px 8px;display:flex;align-items:center;gap:6px;flex-wrap:wrap"><b style="color:#8e44ad;font-size:11px">🔧 조립 공정 — 용접 (관경별 점수 → 용접봉 소요량 자동)</b>
        <span style="color:#8a94a6;font-size:10px">소요량=Σ(표준소요량×점수)×1.5 · 제품 귀속</span><div style="flex:1"></div>
        <b style="color:#8e44ad;font-size:11px">Σ소요량 ${tu.toFixed(5)}</b><button class="btn ghost" id="nw-wadd" style="padding:0 6px">＋점</button></div>
      <datalist id="nw-wrod"><option value="RAC30599301-1">1% 용접봉</option><option value="RAC30599327">3% 용접봉</option><option value="RAC30599303">BCUP</option></datalist>
      <table class="tbl" style="font-size:11px"><thead><tr><th>용접봉</th><th>관경</th><th class="num">점수</th><th class="num">소요량</th><th class="num">ST</th><th></th></tr></thead>
      <tbody>${wp.map((w,i)=>{const pv=naeWeldPrev(w);return `<tr>
        <td><input class="nwr-rod" data-i="${i}" list="nw-wrod" value="${esc(w.weld_item||'')}" style="width:118px"></td>
        <td><select class="nwr-d" data-i="${i}" style="width:120px"><option value="">-관경-</option>${opts.replace(`value="${w.pipe_diam}"`,`value="${w.pipe_diam}" selected`)}</select></td>
        <td class="num"><input class="nwr-q" data-i="${i}" type="number" step="1" min="0" value="${w.weld_qty}" style="width:50px"></td>
        <td class="num">${pv.use?pv.use.toFixed(5):''}</td><td class="num">${pv.st||''}</td>
        <td class="center"><span class="nwr-del" data-i="${i}" style="cursor:pointer;color:#c0392b">✖</span></td></tr>`;}).join('')||'<tr><td colspan=6 class="empty">＋점 으로 용접점 추가</td></tr>'}</tbody></table></div>`;};
  // ============ 실원가 로드/그리기 ============
  const loadSil=async(fresh)=>{if(!item)return;silLoad=true;draw();
    try{const r=await fetch(`${API}/api/cost/sil?item=${encodeURIComponent(item)}&ymd=${encodeURIComponent(naeYmd)}&ym=${encodeURIComponent(silSagYm)}${fresh?'&fresh=1':''}`);
      if(!r.ok)throw new Error('HTTP '+r.status);silD=await r.json();silFor=item;}
    catch(e){silD={error:e.message};}silLoad=false;draw();};
  const silKind=r=>{if(r.silver)return{t:'은납',c:'#8e44ad'};if(r.haskids)return{t:'제작',c:'#1c7c3a'};if(String(r.kind||'').indexOf('사급')>=0||String(r.cost_gubun)==='2')return{t:'사급',c:'#b8860b'};if(r.metal&&(+r.weight>0))return{t:'원소재',c:'#1c47a0'};return{t:'매입',c:'#556'};};
  const drawSil=()=>{
    const a=(silD&&silD.agg)||{},rows=(silD&&silD.rows)||[],prc=(silD&&silD.procs)||[];
    const V=[['company','업체'],['proc','공정'],['weld','용접'],['fasten','체결']];
    let content='';
    if(routeSel>0){ content=routeCostContent(); }
    else if(silLoad) content=`<div class="empty">계산 중…</div>`;
    else if(silD&&silD.error) content=`<div class="page-sub" style="color:#c0392b">⚠ ${esc(silD.error)}</div>`;
    else if(!silFor) content=`<div class="empty">품번을 조회하세요.</div>`;
    else{
      let mid='';
      if(silView==='proc') mid=procTable(prc);
      else if(silView==='weld') mid=procTable(prc.filter(p=>p.group==='용접'));
      else if(silView==='fasten') mid=procTable(prc.filter(p=>p.group==='체결'));
      else mid=`<div class="grid-wrap" style="max-height:52vh;overflow:auto"><table class="tbl bm-tbl">
        <thead><tr><th>레벨</th><th style="text-align:left">품번</th><th style="text-align:left">품명</th><th>구분</th><th>거래처</th><th class="num">단위단가</th><th class="num">재료비</th><th class="num">LME차액</th><th class="num">가공비</th><th class="num" title="실출고가−실입고가(개당). 매입 SUB에 묻힌 사급부품만 손익 반영">사급차액<br>(개당)</th></tr></thead>
        <tbody>${rows.map(r=>{const k=silKind(r);return `<tr style="background:${['#fff','#f6f9ff','#edf3ff','#e4edff','#dbe7ff'][Math.min(r.level,4)]}">
          <td class="center">${r.level}</td><td style="padding-left:${8+r.level*18}px;white-space:nowrap">${r.level?'└ ':''}<b>${esc(r.code)}</b></td>
          <td class="bcap" title="${esc(r.name)}" style="max-width:180px">${esc(r.name)}</td>
          <td class="center"><span style="color:${k.c};font-weight:600;font-size:11px">${k.t}</span></td>
          <td class="bcap" title="${esc(r.cust_name||r.in_cust||'')}" style="max-width:120px;color:#5a6b82">${esc(r.cust_name||r.in_cust||'')}</td>
          <td class="num">${r.won?M2(r.won):''}</td><td class="num" style="color:#1c6b3a">${M(r.mat)}</td>
          <td class="num" style="color:#a8442a">${r.lme?M(r.lme):''}</td><td class="num" style="color:#8a5a1a">${M(r.gag)}</td>
          <td class="num" style="color:#b8860b;font-weight:600" title="${(r.sagub!=null&&r.sagub!=='')?('개당 '+M(r.sagub)+(r.sagub_amt!=null?' × 소요 → 기여 '+M(r.sagub_amt):'')):''}">${(r.sagub!=null&&r.sagub!=='')?M(r.sagub):''}</td></tr>`;}).join('')||'<tr><td colspan="10" class="empty">구성 없음</td></tr>'}</tbody></table></div>`;
      content=`${sumbar(a,'silwon','실원가')}<div class="nae-vbar">${V.map(([k,l])=>`<span class="nae-vb sil-vb ${silView===k?'on':''}" data-v="${k}">${l}</span>`).join('')}</div>${mid}
        <div class="page-sub" style="color:#8aa0bd;margin-top:4px">실원가=실제 조달 기준(매입 중단·구매완제=매입단가). 읽기전용 · LME차액=전서브트리 합산 · <b>사급차액</b>=리시빙월 실출고가−실입고가(개당, 매입 SUB에 <b>묻힌</b> 사급부품만·이중계상 방지). <b>손익(사급반영)</b>=손익+사급차액합.</div>`;
    }
    c.innerHTML=`
     <div class="page-title">🔀 품목 BOM관리 <span style="font-size:12px;color:var(--muted);font-weight:400">실원가(실제 조달·매입중단, 읽기전용)</span></div>
     ${tabbar('sil')}
     <div class="toolbar"><span class="rowcount"><b>${esc(item)}</b> · ${esc(name)}</span>
       <label class="tl" style="margin-left:8px">단가기준일</label><input class="inp" id="sil-ymd" type="date" value="${ymd2date(naeYmd)}" style="width:150px">
       <label class="tl" style="margin-left:8px" title="유상사급 실출고−실입고 차액을 집계할 리시빙월(당월은 월초라 희소 → 기본=직전 완성월)">사급 리시빙월</label><input class="inp" id="sil-sagym" type="month" value="20${silSagYm.slice(0,2)}-${silSagYm.slice(2,4)}" style="width:130px">
       <button class="btn" id="sil-go">🔍 조회</button><button class="btn ghost" id="sil-regen">🔄 재계산</button><div class="spacer"></div></div>
     ${candSelector('sil')}
     ${content}${naeCss()}`;
    bindTabs();bindCandSel();
    const g=id=>c.querySelector(id);
    const _rdSag=()=>{const v=g('#sil-sagym')&&g('#sil-sagym').value;if(v)silSagYm=v.slice(2).replace('-','');};
    g('#sil-go').onclick=()=>{naeYmd=date2ymd(g('#sil-ymd').value)||naeYmd;_rdSag();routeCostFor=-1;if(routeSel>0)loadRouteCost();else loadSil();};
    g('#sil-regen').onclick=()=>{_rdSag();if(routeSel>0){routeCostFor=-1;loadRouteCost();}else loadSil(true);};
    c.querySelectorAll('.sil-vb').forEach(el=>el.onclick=()=>{silView=el.dataset.v;drawSil();});
  };
  const naeCss=()=>`<style>
     .bm-tabs{display:flex;gap:2px;margin:6px 0 2px;border-bottom:2px solid #d3ddec}
     .bm-tab{border:1px solid #d3ddec;border-bottom:none;background:#f1f5fb;color:#5a6b82;padding:7px 18px;font-size:13px;font-weight:700;cursor:pointer;border-radius:8px 8px 0 0}
     .bm-tab.on{background:#fff;color:#1c47a0;border-color:#bcd;position:relative;top:2px}
     .nae-sum{display:flex;flex-wrap:wrap;gap:6px;margin:6px 0}
     .nae-chip{display:inline-flex;flex-direction:column;align-items:center;border:1px solid #dce4ee;border-radius:8px;padding:4px 12px;background:#fff;min-width:78px}
     .nae-chip em{font-style:normal;font-size:10px;color:#8aa0bd}.nae-chip b{font-size:14px}
     .nae-vbar{display:flex;gap:4px;margin:4px 0}
     .nae-vb{border:1px solid #d3ddec;border-radius:14px;padding:2px 14px;font-size:12px;color:#5a6b82;cursor:pointer;background:#fff}
     .nae-vb.on{background:#1c47a0;color:#fff;font-weight:700;border-color:#1c47a0}
     .nae-2col{display:grid;grid-template-columns:1fr 1fr;gap:8px}
     .nae-tg{font-size:9px;border:1px solid #ccc;border-radius:3px;padding:0 3px}
     .nae-mrow:hover{background:#eef4ff}.nae-mrow.sel{background:#e8f0ff}
     .nae-foot td{font-weight:700;background:#f6f9ff;border-top:2px solid #d3ddec}
     .bm-tbl{font-size:11.5px}.bm-tbl th,.bm-tbl td{padding:3px 6px;white-space:nowrap}.bm-tbl td.bcap{overflow:hidden;text-overflow:ellipsis}
     .bm-tbl thead th{position:sticky;top:0;background:#f4f7fc;z-index:2}
     .nae-2col .bm-tbl td:first-child{max-width:150px;overflow:hidden;text-overflow:ellipsis}
     /* 레거시형 가로 매트릭스: 세로 컬럼헤더로 전 컬럼 한 화면 */
     .wm{border-collapse:collapse;table-layout:auto}
     .wm th,.wm td{border:1px solid #dde6f0;padding:1px 2px}
     .wm th.wm-vh{height:66px;width:26px;min-width:26px;max-width:26px;vertical-align:bottom;background:#eef3fb;padding:2px 0}
     .wm th.wm-vh span{writing-mode:vertical-rl;text-orientation:upright;white-space:nowrap;font-size:10px;font-weight:600;color:#40567a;display:inline-block;max-height:62px;overflow:hidden;letter-spacing:-1px}
     .wm td input{border:1px solid #cfd9e6;border-radius:3px;padding:1px}
     .wm tbody td:first-child,.wm thead th:first-child{position:sticky;left:0;background:#f4f7fc;z-index:2}
     /* 레벨트리 컴팩트: 행높이 축소로 화면당 품번 최대 */
     .nae-tree td,.nae-tree th{padding:2px 6px;line-height:1.3;font-size:12.5px}
     .nae-tree .nae-edit-btn:hover{background:#7a379a}
     .cand-bar{display:flex;align-items:center;gap:8px;margin:6px 0;padding:5px 10px;background:#f6f2fb;border:1px solid #d6c3ea;border-radius:8px;flex-wrap:wrap}
     .cand-bar select{border:1px solid #cbb6e2;border-radius:5px;padding:3px 6px;font-size:12px;background:#fff}
   </style>`;
  const isW=nm=>(nm||'').indexOf('용접봉')>=0;
  // ★임의 SUB(중간 조립노드) 식별 — 평면 BOM(bmFlat·naeFlatMat)에서 행 제외(leaf 재료만). 용접봉(RAC)은 isW로 별도처리(호출부에서 먼저 걸러짐).
  // 규칙: haskids(자식보유) OR 품번 접미사(-SOCKET·-SUB·-은납·-AL·-숫자류[-20-1·-12-1·-S1-1 등]). 소분류120/자체제작SUB도 접미사로 포착.
  const isSub=(code,haskids)=>!!haskids || /-(SOCKET|SUB|은납|AL|S?\d)/i.test(String(code||''));
  // ============ BOM구성 그리기 ============
  // ★BOM구성 평면 = 내부원가(naeFlatMat)와 완전 동일 렌더. 같은 데이터소스(naeD)·같은 분류(가공품/구매·부자재/은납)·SUB제외·레벨0/1·조립공정 팝업 공유.
  // (이전 tree기반 자체분류는 gp/sw 오분류·SUB잔존 버그 → naeD 공유로 교체. 원가컬럼 포함 동일.)
  const bmFlat=()=>{
    if(naeFor!==item||!naeD||naeD.error) return `<div class="empty">${naeD&&naeD.error?('⚠ '+esc(naeD.error)):'계산 중… (BOM구성 평면 = 내부원가와 동일 데이터 로딩)'}</div>`;
    return naeFlatMat(naeD.agg||{}, naeD.rows||[], naeD.procs||[])+(naeModal?naeProcModal():'');};
  const drawBom=()=>{
    const cell=(l,i,col)=>{const[k,,t]=col,v=l[k];const isSel=t.indexOf('sel:')===0,grp=isSel?t.slice(4):'';
      if(!editMode||t==='ro'){
        if(t==='chk')return `<td class="center">${v?'<span style="color:#2f6db3;font-weight:700">✔</span>':''}</td>`;
        if(t==='proc')return `<td class="bcap" title="${esc(procMap[v]||v||'')}">${esc(procMap[v]||v||'')}</td>`;
        if(isSel)return `<td class="center">${esc(codeName(grp,v))}</td>`;
        if(t==='vendor')return `<td class="bcap" title="${esc(l.cust_name||'')}">${esc(l.cust_name||v||'')}</td>`;
        return `<td class="bcap" title="${esc(''+(v==null?'':v))}">${esc(''+(v==null?'':v))}</td>`;}
      if(t==='chk')return `<td class="center"><input type="checkbox" data-i="${i}" data-k="${k}" ${v?'checked':''}></td>`;
      if(t==='num')return `<td><input class="ce" type="number" step="any" data-i="${i}" data-k="${k}" value="${v==null?'':v}" style="width:54px"></td>`;
      if(isSel)return `<td><select class="ce cesel" data-i="${i}" data-k="${k}" style="width:78px" title="${esc(codeName(grp,v))}"><option value="">-</option>${(codes[grp]||[]).map(o=>`<option value="${esc(o.code)}" ${o.code==v?'selected':''}>${esc(o.name)}</option>`).join('')}</select></td>`;
      if(t==='vendor')return `<td><input class="ce cevendor" list="bm-vendordl" data-i="${i}" data-k="${k}" value="${esc(''+(v==null?'':v))}" placeholder="${esc(l.cust_name||'코드/명')}" style="width:88px" title="${esc(l.cust_name||'')}"></td>`;
      if(t==='proc')return `<td><select class="ce cesel" data-i="${i}" data-k="${k}" style="width:58px" title="${esc(procMap[v]||v||'')}"><option value="">-</option>${procs.map(p=>`<option value="${esc(p.code)}" ${p.code===v?'selected':''}>${esc(p.name)}</option>`).join('')}</select></td>`;
      if(t==='item')return `<td><input class="ce ceitem" list="bm-itemdl" data-i="${i}" data-k="${k}" value="${esc(''+(v==null?'':v))}" placeholder="검색·선택" style="width:120px"></td>`;
      return `<td><input class="ce" data-i="${i}" data-k="${k}" value="${esc(''+(v==null?'':v))}" style="width:90px"></td>`;};
    c.innerHTML=`
     <div class="page-title">🔀 품목 BOM${RO?' 조회':'관리'} <span style="font-size:12px;color:var(--muted);font-weight:400">${RO?'조회 전용':'nx · 백엔드 편집·저장'}</span></div>
     <div class="page-sub">품번 검색 → BOM 구성(다단계 전개)·내부원가·실원가. 원천 단일BOM(nx.bom_line). 기본은 현행만, "과거포함" 체크 시 휴면 품번·BOM도 표시.</div>
     ${item?tabbar('bom'):''}
     <div class="toolbar">
       <label class="tl">품번</label><input class="inp" id="bm-q" value="${esc(query)}" placeholder="품번/품명 검색" style="width:220px">
       <button class="btn" id="bm-search">🔍 검색</button>
       <label class="tl" title="체크 시 휴면(과거) 품번·BOM도 검색결과에 표시" style="margin-left:2px;font-weight:400;color:var(--muted)"><input type="checkbox" id="bm-past" ${includePast?'checked':''} style="vertical-align:middle"> 과거포함</label>
       ${(!RO&&(typeof PERM==='undefined'||PERM.canEdit('unifybom')))?`<button class="btn" id="bm-new" style="background:#1c7c3a;color:#fff">＋ 신규 BOM 등록</button>`:''}
       ${item&&navStack.length?`<button class="btn ghost" id="bm-back" title="상위 레벨로 돌아가기">◀ 상위로 (${esc(navStack[navStack.length-1])})</button>`:''}
       ${item?(editMode
         ?`<button class="btn" id="bm-add">＋ 행추가</button><button class="btn ghost" id="bm-weld">${showWeld?'🔧 용접봉 숨기기':'🔧 용접봉 표시'}</button><button class="btn" id="bm-save">💾 저장</button><button class="btn ghost" id="bm-cancel">✖ 취소</button><button class="btn" id="bm-xls">⬇ 엑셀</button>`
         :`<button class="btn ghost" id="bm-tree">${viewTree?'📄 단일레벨':'🌲 다단계 전개'}</button><button class="btn ghost" id="bm-wu" title="이 품번을 하위구성으로 쓰는 상위 품번(역전개·where-used)">🔺 역전개</button><button class="btn ghost" id="bm-weld">${showWeld?'🔧 용접봉 숨기기':'🔧 용접봉 표시'}</button>${PERM.canEdit('unifybom')?`${!RO?`<button class="btn" id="bm-edit">✎ 수정</button><button class="btn ghost" id="bm-copy" title="이 BOM을 다른 품번으로 복사">📋 복사</button><button class="btn ghost" id="bm-del" style="color:#c0392b;border-color:#e2b4b4" title="이 품번 삭제 — 구성(자식관계) 제거 후 품번을 마스터에서 삭제. 자식으로 사용중이면 불가">🗑 품번삭제</button>`:''}`:(RO?'':`<span style="color:#c0392b;font-size:12px">🔒 수정권한 없음 (${esc(PERM.label())})</span>`)}<button class="btn" id="bm-xls">⬇ 엑셀</button>`
       ):''}
       ${item&&!RO&&(typeof PERM==='undefined'||PERM.canEdit('unifybom'))?`<label class="tl" style="margin-left:6px" title="경영 대시보드·영업예상 절삭/설치 분류(품목마스터 nx.item.cut_gubun). 즉시 저장.">구분</label><select class="sel" id="bm-cut" style="width:96px">${['','절삭','설치','분지관','이지링크'].map(g=>`<option value="${g}" ${itemCut===g?'selected':''}>${g||'미분류'}</option>`).join('')}</select>`:''}
       <div class="spacer"></div>${item?`<span class="rowcount"><b>${esc(item)}</b> · ${esc(name)} · ${lines.length}구성${itemCut?` · <b style="color:#1c47a0">${esc(itemCut)}</b>`:''}</span>`:''}
     </div>
     <datalist id="bm-itemdl"></datalist><datalist id="bm-vendordl"></datalist>
     ${newReg?`<div style="border:2px solid #1c7c3a;border-radius:10px;background:#f4fbf6;padding:12px;margin:8px 0">
        <div style="display:flex;align-items:center;gap:8px"><b style="color:#1c7c3a;font-size:14px">＋ 신규 BOM 등록 — 방식 선택</b><div style="flex:1"></div><button class="btn ghost" id="nw-close">✖</button></div>
        <div style="display:flex;gap:10px;flex-wrap:wrap;margin-top:10px">
          <div style="flex:1;min-width:240px;border:1px solid #cfe0ff;border-radius:8px;padding:10px;background:#fff">
            <b style="color:#1c47a0">① LG BOM 불러오기</b><div style="font-size:11px;color:#5a6b82;margin:4px 0">[기준정보 › LG BOM관리]에 적재된 LG BOM(nx.lg_bom)에서 <b>모델 선택 → 전개 → 구성 초안</b>. 품번=LG 상위품번. 용접봉은 용접공정으로 분리.</div>
            <div style="display:flex;gap:4px;flex-wrap:wrap;align-items:center">
              <select id="nw-lgwk" class="inp" style="width:auto"><option value="">전체</option><option value="DMZ">DMZ(SAC)</option><option value="DGZ">DGZ(RAC)</option></select>
              <input id="nw-lgq" class="inp" list="nw-lgdl" autocomplete="off" placeholder="LG 모델/상위품번" style="width:150px"><datalist id="nw-lgdl"></datalist>
              <button class="btn" id="nw-lgload" style="background:#1c47a0;color:#fff">불러오기</button></div></div>
          <div style="flex:1;min-width:200px;border:1px solid #cfe0ff;border-radius:8px;padding:10px;background:#fff">
            <b style="color:#1c47a0">② 기존 BOM 복사</b><div style="font-size:11px;color:#5a6b82;margin:4px 0">유사 품번 복사 → 새 품번으로. proc_weld·routing 포함 복사 후 편집.</div>
            <button class="btn" id="nw-copy">복사로 시작</button></div>
          <div style="flex:1;min-width:200px;border:1px solid #cfe0ff;border-radius:8px;padding:10px;background:#fff">
            <b style="color:#1c47a0">③ 완전 새로</b><div style="font-size:11px;color:#5a6b82;margin:4px 0">빈 폼. 품번 직접입력 후 구성·용접공정 등록.</div>
            <button class="btn" id="nw-blank">빈 폼으로 시작</button></div>
        </div></div>`:''}
     ${(editMode&&isNew)?`<div class="page-sub" style="color:#1c7c3a;font-weight:700">＋ 신규 등록 편집: 품번 <b>${esc(item)}</b> · ${esc(name||'(품명 미입력)')} — 구성 그리드 + 아래 용접공정 입력 후 [저장]</div>
     <div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap;padding:6px 8px;margin:2px 0 4px;background:#f2fbf4;border:1px solid #bfe6c8;border-radius:8px;font-size:12px">
       <b style="color:#1c7c3a">📋 제품 마스터</b>
       <label class="tl">대분류<span style="color:#c0392b">*</span></label><select class="nm-fld" data-k="lgroup" style="width:130px"><option value="">-</option>${(codes.lgroup||[]).map(o=>`<option value="${esc(o.code)}" ${o.code==newMaster.lgroup?'selected':''}>${esc(o.name)}</option>`).join('')}</select>
       <label class="tl">소분류</label><select class="nm-fld" data-k="sgroup" style="width:130px"><option value="">-</option>${(codes.sgroup||[]).map(o=>`<option value="${esc(o.code)}" ${o.code==newMaster.sgroup?'selected':''}>${esc(o.name)}</option>`).join('')}</select>
       <label class="tl">생산구분</label><select class="nm-fld" data-k="make_type" style="width:110px"><option value="">-</option>${(codes.make_type||[]).map(o=>`<option value="${esc(o.code)}" ${o.code==newMaster.make_type?'selected':''}>${esc(o.name)}</option>`).join('')}</select>
       <label class="tl">단가구분</label><select class="nm-fld" data-k="cost_gubun" style="width:110px"><option value="">-</option>${(codes.cost_gubun||[]).map(o=>`<option value="${esc(o.code)}" ${o.code==newMaster.cost_gubun?'selected':''}>${esc(o.name)}</option>`).join('')}</select>
       <span style="color:#8a5a1a;font-size:11px">※ 대분류 미설정 시 부품 가공비가 누락됩니다(공정 필터).</span>
     </div>`:''}
     ${msg?`<div class="page-sub" style="color:#c0392b">⚠ ${esc(msg)}</div>`:''}
     ${results.length?`<div class="bm-results">${results.map(r=>`<div class="bm-r" data-it="${esc(r.item)}"><b>${esc(r.item)}</b> ${esc(r.name||'')} ${r.has_bom?'<span class="badge">BOM</span>':'<span style="color:#bbb">구성없음</span>'}${r.status==='휴면'?' <span style="color:#c0392b;font-size:11px">휴면</span>':''}</div>`).join('')}</div>`:''}
     ${loading?`<div class="empty">조회 중…</div>`:''}
     ${item&&!loading&&viewTree&&!editMode?candSelector('bom'):''}
     ${item&&!loading?((viewTree&&!editMode)?`
       ${routeSel>0?routeTreeTable():bmFlat()}`
     :`<div class="grid-wrap" style="max-height:calc(100vh - 300px);overflow:auto"><table class="tbl bm-tbl"><thead><tr><th>#</th>${COLS.map(cc=>`<th>${cc[1]}</th>`).join('')}${editMode?'<th>삭제</th>':''}</tr></thead>
       <tbody>${lines.map((l,i)=>(isW(l.item_name)&&!showWeld)?'':`<tr${isW(l.item_name)?' style="background:#f3eefa"':''}><td class="center mut">${i+1}</td>${COLS.map(col=>cell(l,i,col)).join('')}${editMode?`<td class="center"><span class="bm-del" data-i="${i}" style="cursor:pointer;color:#c0392b">✖</span></td>`:''}</tr>`).join('')||`<tr><td colspan="${COLS.length+(editMode?2:1)}" class="empty">구성 없음${editMode?' — ＋행추가로 등록':''}</td></tr>`}</tbody></table></div>${(editMode&&isNew)?`<div style="margin-top:10px;padding:9px;border:1px dashed #8e44ad;border-radius:8px;background:#faf7ff"><button class="btn" id="bm-assyproc" style="background:#8e44ad;color:#fff">✎ 조립공정 입력 (관경별 용접 · 공정 · 체결)</button> <span style="font-size:11px;color:var(--muted)">내부원가와 동일한 매트릭스 팝업에서 입력·저장 (한 표=nx.routing)</span></div>`:''}`):''}
     ${naeModal?naeProcModal():''}
     ${(wuBusy||wuData)?wuModalHtml():''}
     ${bomCss()}`;
    const qi=c.querySelector('#bm-q');
    c.querySelector('#bm-search').onclick=()=>doSearch(qi.value);
    qi.onkeyup=e=>{if(e.key==='Enter')doSearch(qi.value);};
    {const pc=c.querySelector('#bm-past');if(pc)pc.onchange=()=>{includePast=pc.checked;doSearch(qi.value);};}
    if(item)bindTabs();
    bindCandSel();
    c.querySelectorAll('.bm-r').forEach(el=>el.onclick=()=>{navStack=[];load(el.dataset.it);});
    const tg=c.querySelector('#bm-tree');if(tg)tg.onclick=()=>{viewTree=!viewTree;draw();};
    const wl=c.querySelector('#bm-weld');if(wl)wl.onclick=()=>{showWeld=!showWeld;draw();};
    {const w2=c.querySelector('#nae-weld');if(w2)w2.onclick=()=>{showWeld=!showWeld;draw();};}  // 평면표(=내부원가) 용접봉 토글
    // 평면표 [✎] = 공정입력 팝업(제품=조립공정 용접/포장/체결 · 절삭부품=가공공정) — 내부원가와 공유
    c.querySelectorAll('.nae-edit-btn').forEach(el=>el.onclick=e=>{e.stopPropagation();loadNaeProc(el.dataset.node,true);});
    {const ap=c.querySelector('#bm-assyproc');if(ap)ap.onclick=()=>{ap.disabled=true;ap.textContent='⏳ 조립공정 여는 중…';loadNaeProc(item,true);};}  // ★신규등록 조립공정 = 내부원가와 동일 팝업(클릭 즉시 피드백)
    if(naeModal)wireProcModal();
    const cp=c.querySelector('#bm-copy');if(cp)cp.onclick=doCopy;
    // 품번삭제 — 레거시 방식(구성 제거 후 품번 삭제). 자식으로 사용중이면 백엔드가 차단.
    const dbtn=c.querySelector('#bm-del');if(dbtn)dbtn.onclick=async()=>{
      if(!item)return;
      if(!confirm(`품번 [${item}] ${name||''} 삭제할까요?\n\n· 구성(자식 ${lines.length}건) 관계 제거\n· 품번을 품목마스터에서 삭제\n· 다른 BOM이 이 품번을 자식으로 쓰면 삭제 안 됨\n\n되돌릴 수 없습니다.`))return;
      try{const r=await fetch(`${API}/api/bom/delete`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({item})});
        const j=await r.json();
        if(!j.ok){alert('삭제 불가:\n'+(j.errors||['오류']).join('\n'));return;}
        alert(`삭제 완료 — 품번 ${j.item} (구성 ${j.lines_removed||0}건 제거)`);
        item='';name='';lines=[];editMode=false;naeD=null;naeFor='';silD=null;silFor='';results=[];query='';draw();
      }catch(e){alert('삭제 실패: '+e.message);}};
    // 역전개(where-used) 버튼·모달
    {const wu=c.querySelector('#bm-wu');if(wu)wu.onclick=openWhereUsed;}
    {const wx=c.querySelector('#wu-close');if(wx)wx.onclick=()=>{wuData=null;wuBusy=false;draw();};}
    {const wb=c.querySelector('#wu-backdrop');if(wb)wb.onclick=e=>{if(e.target===wb){wuData=null;wuBusy=false;draw();}};}
    c.querySelectorAll('.wu-row[data-raw]').forEach(el=>el.onclick=()=>{const raw=el.dataset.raw;if(raw){wuData=null;wuBusy=false;if(item)navStack.push(item);load(raw);}});
    // 신규등록 진입·모달·용접패널
    {const nb=c.querySelector('#bm-new');if(nb)nb.onclick=openNew;}
    {const x=c.querySelector('#nw-close');if(x)x.onclick=closeNew;}
    {const lq=c.querySelector('#nw-lgq');if(lq){lq.oninput=()=>lgAuto(lq);lq.onkeyup=e=>{if(e.key==='Enter')lgLoad(lq.value,(c.querySelector('#nw-lgwk')||{}).value);};}}
    {const lb=c.querySelector('#nw-lgload');if(lb)lb.onclick=()=>lgLoad((c.querySelector('#nw-lgq')||{}).value,(c.querySelector('#nw-lgwk')||{}).value);}
    {const cy=c.querySelector('#nw-copy');if(cy)cy.onclick=copyNew;}
    {const bl=c.querySelector('#nw-blank');if(bl)bl.onclick=blankNew;}
    if(editMode&&isNew)bindWeld();
    c.querySelectorAll('.fq').forEach(el=>el.oninput=()=>{const i=+el.dataset.i;if(fastenD&&fastenD.rows[i])fastenD.rows[i].qty=+el.value||0;});  // 신규등록 체결 횟수 입력
    c.querySelectorAll('.nm-fld').forEach(el=>el.onchange=()=>{newMaster[el.dataset.k]=el.value;});  // 제품 마스터속성 write-back
    const bk=c.querySelector('#bm-back');if(bk)bk.onclick=()=>{const p=navStack.pop();if(p)load(p);};
    c.querySelectorAll('.bm-trow').forEach(el=>el.onclick=()=>{if(item)navStack.push(item);load(el.dataset.sub);});
    const ed=c.querySelector('#bm-edit');if(ed)ed.onclick=()=>{editMode=true;viewTree=false;draw();};
    {const bc=c.querySelector('#bm-cut');if(bc)bc.onchange=async()=>{const v=bc.value;   // 절삭/설치 구분 즉시저장(nx.item.cut_gubun)
      try{const r=await fetch(`${API}/api/item/cutgubun`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({item_code:item,cut_gubun:v})});const j=await r.json();
        if(j&&(j.ok||j.updated>=0)){itemCut=v;const rc=c.querySelector('.rowcount');if(rc&&item)rc.innerHTML=`<b>${esc(item)}</b> · ${esc(name)} · ${lines.length}구성${itemCut?` · <b style="color:#1c47a0">${esc(itemCut)}</b>`:''}`;}
        else alert('구분 저장 실패');}catch(e){alert('구분 저장 오류: '+e.message);}};}
    const cx=c.querySelector('#bm-cancel');if(cx)cx.onclick=()=>{if(isNew){isNew=false;item='';name='';lines=[];weldRows=[];editMode=false;draw();}else load(item);};
    const add=c.querySelector('#bm-add');if(add)add.onclick=addRow;
    const sv=c.querySelector('#bm-save');if(sv)sv.onclick=(isNew?saveNew:save);
    const xls=c.querySelector('#bm-xls');if(xls)xls.onclick=()=>dlCSV(`BOM_${item}.csv`,['#',...COLS.map(x=>x[1])],lines.map((l,i)=>[i+1,...COLS.map(([k])=>l[k])]));
    c.querySelectorAll('.bm-del').forEach(el=>el.onclick=()=>{lines.splice(+el.dataset.i,1);draw();});
    const recalcWt=(i,tr)=>{const w=calcWeight(lines[i]);if(w!=null){lines[i].net_weight=w;const wc=tr&&tr.querySelector('input[data-k="net_weight"]');if(wc&&document.activeElement!==wc)wc.value=w;}};
    c.querySelectorAll('.ce').forEach(el=>el.oninput=()=>{const i=+el.dataset.i,k=el.dataset.k;lines[i][k]=(el.type==='number')?(el.value===''?null:+el.value):el.value;
      if(['diam','thick','length'].includes(k))recalcWt(i,el.closest('tr'));});   // ★동관 치수 입력 시 중량 자동
    c.querySelectorAll('.cesel').forEach(el=>el.onchange=()=>{const i=+el.dataset.i;lines[i][el.dataset.k]=el.value;
      if(el.dataset.k==='metal_gubun')recalcWt(i,el.closest('tr'));});   // ★재질=동 선택 시 중량 자동
    let itT=null;
    c.querySelectorAll('.ceitem').forEach(el=>{
      el.oninput=()=>{const i=+el.dataset.i;lines[i].child_item=el.value.trim().toUpperCase();
        const q=el.value.trim();clearTimeout(itT);if(q.length<2)return;
        itT=setTimeout(async()=>{try{const r=await fetch(`${API}/api/bom/search?q=${encodeURIComponent(q)}&include_past=1`);const rows=(await r.json()).rows||[];  // ★부품등록=휴면·orphan 포함 전체검색
          const dl=c.querySelector('#bm-itemdl');if(dl)dl.innerHTML=rows.map(x=>{itemNames[x.item]=x.name;return `<option value="${esc(x.item)}">${esc(x.name||'')}${x.status&&x.status!=='사용'?' ('+esc(x.status)+')':''}</option>`;}).join('');}catch(e){}},250);};
      el.onchange=async()=>{const i=+el.dataset.i,code=el.value.trim().toUpperCase();const L=lines[i];L.child_item=code;
        // ★버그수정: 품번 변경 시 마스터 파생필드는 "항상" 새 품번 기준으로 갱신. 새 품번 값이 비어있으면 이전 품번 잔류값을 클리어(예 Tube→Supporter 시 외경/두께/길이/중량이 남던 문제).
        const MK=['diam','thick','length','metal_gubun','net_weight','unit','lgroup','sgroup','make_type','cost_gubun'];
        if(!code){L.item_name='';L.spec='';MK.forEach(k=>L[k]='');L.in_cust='';L.cust_name='';draw();return;}
        try{const r=await fetch(`${API}/api/bom/iteminfo?item=${encodeURIComponent(code)}`);const d=await r.json();
          if(d&&d.found){
            L.item_name=d.item_name||itemNames[code]||'';
            L.spec=d.item_spec||'';
            MK.forEach(k=>{L[k]=(d[k]==null?'':d[k]);});                 // 있으면 값·없으면 '' (잔류 방지)
            if(d.in_cust){L.in_cust=d.in_cust;L.cust_name=d.cust_name||'';}else{L.in_cust='';L.cust_name='';}
            if(L.net_weight===''||L.net_weight==null){const w=calcWeight(L);if(w!=null)L.net_weight=w;}  // 마스터 중량 없고 동관 치수 있으면 자동계산
          }else{  // 마스터 미등록 신규 품번 → 스펙 초기화(이전 품번 값 잔류 방지)
            L.item_name=itemNames[code]||'';L.spec='';MK.forEach(k=>L[k]='');L.in_cust='';L.cust_name='';
          }
          draw();
        }catch(e){}};
    });
    let vT=null;
    c.querySelectorAll('.cevendor').forEach(el=>{
      el.oninput=()=>{const i=+el.dataset.i;lines[i].in_cust=el.value.trim();
        const q=el.value.trim();clearTimeout(vT);if(q.length<1)return;
        vT=setTimeout(async()=>{try{const r=await fetch(`${API}/api/item/vendorsearch?q=${encodeURIComponent(q)}`);vlist=(await r.json()).rows||[];
          const dl=c.querySelector('#bm-vendordl');if(dl)dl.innerHTML=vlist.map(x=>`<option value="${esc(x.code)}">${esc(x.name)}</option>`).join('');}catch(e){}},250);};
      el.onchange=()=>{const i=+el.dataset.i,code=el.value.trim();lines[i].in_cust=code;const v=vlist.find(x=>x.code===code);if(v)lines[i].cust_name=v.name;};
    });
    c.querySelectorAll('.bm-tbl input[type=checkbox]').forEach(el=>el.onchange=()=>{lines[+el.dataset.i][el.dataset.k]=el.checked;});
  };
  const bomCss=()=>`<style>
     .bm-tabs{display:flex;gap:2px;margin:6px 0 2px;border-bottom:2px solid #d3ddec}
     .bm-tab{border:1px solid #d3ddec;border-bottom:none;background:#f1f5fb;color:#5a6b82;padding:7px 18px;font-size:13px;font-weight:700;cursor:pointer;border-radius:8px 8px 0 0}
     .bm-tab.on{background:#fff;color:#1c47a0;border-color:#bcd;position:relative;top:2px}
     .bm-results{border:1px solid var(--line-2,#c9d3e0);border-radius:8px;margin:6px 0 0;max-height:calc(100vh - 250px);overflow:auto;background:#fff;box-shadow:0 3px 12px rgba(30,45,70,.10)}
     .bm-r{padding:7px 12px;border-bottom:1px solid var(--line);cursor:pointer;font-size:13px}
     .bm-r:last-child{border-bottom:none}.bm-r:hover{background:#eef4ff}
     .bm-tbl{font-size:12px}.bm-tbl th,.bm-tbl td{padding:3px 6px;white-space:nowrap}
     .bm-tbl td.bcap{max-width:150px;overflow:hidden;text-overflow:ellipsis}
     .bm-tbl td.mut{color:var(--muted)}.bm-tbl thead th{position:sticky;top:0;background:#f4f7fc;z-index:2}
     .ce{border:1px solid var(--line);border-radius:4px;padding:2px 5px;font-size:12px}
   </style>`;
  // ===== 라우팅 탭: 실사용(매입중단) BOM 구조만 — 원가 미표시. 현행=tree(default bom/tree, 이미 로드), 후보=routeTreeTable =====
  // 라우팅 탭 현행 전체전개(expandbuy=1 = 현행 cs_except=0 유지 + 매입SUB 하위전개, 비현행 변형 제외)
  let routeFull=null, routeFullFor='';
  const loadRouteFull=async()=>{ if(!item){routeFull=[];return;} routeBusy=true; draw();
    try{const r=await fetch(`${API}/api/bom/tree?item=${encodeURIComponent(item)}&real=1&expandbuy=1`); const j=await r.json(); routeFull=j.rows||[]; routeFullFor=item;}
    catch(e){routeFull=[]; routeFullFor=item;}
    routeBusy=false; draw(); };
  const routeRowsTbl=(rows,head)=>`${head}<div class="grid-wrap" style="max-height:calc(100vh - 320px);overflow:auto"><table class="tbl bm-tbl">
    <thead><tr><th>레벨</th><th style="text-align:left">품번</th><th style="text-align:left">품명</th><th>규격</th><th class="center">사급</th><th style="text-align:left">매입처</th><th class="num">소요량</th></tr></thead>
    <tbody>${rows.map(r=>{const sp=r.diam?('Ø'+r.diam+(r.thick?'×'+r.thick:'')):(r.spec||'');
      const bg=['#fff','#f6f2fb','#efe7f8','#e7dcf4','#dfd2f0'][Math.min(r.level,4)];
      const tag=r.level===0?'<span class="nae-tg" style="color:#1c47a0;border-color:#bcd">제품</span>':(r.haskids?'<span class="nae-tg" style="color:#8e44ad;border-color:#d6c3ea">SUB</span>':'');
      return `<tr style="background:${bg}"><td class="center">${r.level}</td>
        <td style="padding-left:${8+r.level*18}px;white-space:nowrap">${r.level?'<span style="color:#a9b8cc">└ </span>':''}<b>${esc(r.code)}</b> ${tag}</td>
        <td class="bcap" title="${esc(r.nm)}" style="max-width:210px;text-align:left">${esc(r.nm)}</td>
        <td class="center" style="color:#5a6b82">${esc(sp)}</td>
        <td class="center">${r.sag==='1'?'<span class="nae-tg" style="color:#c0392b;border-color:#e6bcbc">사급</span>':''}</td>
        <td class="bcap" title="${esc(r.custnm||r.cust||'')}" style="max-width:150px;text-align:left;color:#5a6b82">${esc(r.custnm||r.cust||'')}</td>
        <td class="num">${r.qty!=null?q4(r.qty):''}</td></tr>`;}).join('')||'<tr><td colspan=7 class="empty">구성 없음</td></tr>'}</tbody></table></div>`;
  const drawRoute=()=>{
    let content;
    if(routeSel>0){ content=routeTreeTable(); }
    else if(!item){ content=`<div class="empty">품번을 조회하세요.</div>`; }
    else{ const head=`<div class="summary-bar" style="flex-wrap:wrap"><div class="s-item"><b style="color:#1c47a0">현행 실사용 BOM</b> · ROUTING(실제 조달·매입중단) 구성 · <span style="color:#8a94a6">원가 미표시</span></div></div>`;
      content = routeRowsTbl(routeFull||[], head); }
    c.innerHTML=`
     <div class="page-title">🔀 품목 BOM${RO?' 조회':'관리'} <span style="font-size:12px;color:var(--muted);font-weight:400">라우팅(조달경로 구성 BOM · 원가 미표시)</span></div>
     ${tabbar('route')}
     <div class="toolbar"><span class="rowcount"><b>${esc(item)}</b> · ${esc(name)}</span><div class="spacer"></div></div>
     ${candSelector('route')}
     ${content}${naeCss()}`;
    bindTabs();bindCandSel();
  };
  const draw=()=>{
    if(tab==='route'){ if(routeSel>0){ if(routeTreeFor!==routeSel&&!routeBusy){ loadRouteTree(); return; } } else if(routeFullFor!==item&&!routeBusy){ loadRouteFull(); return; } drawRoute(); return; }
    if(tab==='nae'){ if(item&&naeFor!==item&&!naeLoad){loadNae();return;} drawNae(); return; }
    if(tab==='sil'){ if(item&&silFor!==item&&!silLoad){loadSil();return;}
      if(routeSel>0&&routeCostFor!==routeSel&&!routeBusy){ loadRouteCost(); return; } drawSil(); return; }
    // 후보 선택 시 BOM구성 = 후보 구조 트리(route/tree) 로드
    if(tab==='bom'&&routeSel>0&&viewTree&&!editMode&&routeTreeFor!==routeSel&&!routeBusy){ loadRouteTree(); return; }
    // BOM구성 평면(viewTree, 현행)=내부원가(naeD) 공유 렌더 → naeD 없으면 로드(단일레벨/편집 그리드는 tree/lines 사용)
    if(item&&viewTree&&!editMode&&routeSel===0&&naeFor!==item&&!naeLoad){ loadNae(); return; }
    drawBom();
  };
  draw();
};

/* ===== 개발: 조달경로 통합검토 (재설계) — 상단=품목 BOM관리 '내부원가' 탭 재료표 + 하단=조달경로 후보(요약카드) ===== */
/* ★상단 = /api/cost/nae 재료 역전개 평면(품번·품명·규격·소재·소요량, 용접봉 종류별). 재료행 클릭=조달대상 선택. */
/* ★하단 = 조달대상별 후보 요약카드(현행1+대안N). [➕ 신규 조달프로파일 등록](품목BOM 신규등록 패턴: 대상+후보명+3방법 현행복사/기존복사/빈수동, BOM미등록시 LG seed). */
/* ★현행 더블클릭=상세 보기모달(+새 후보 만들기), 대안 더블클릭=상세 편집모달(헤더+라인 CRUD·채번·승인토글). 저장=route/save·line/save(approve_flag=0 리셋), 승인=route/approve(개발). */
SCREEN.subvariant=(c)=>{
  const API=API_BASE;
  const canW=(typeof PERM!=='undefined')?PERM.canEdit('subvariant'):true;
  const nfq=v=>{v=Number(v||0);return v%1===0?v.toLocaleString('ko-KR'):v.toFixed(4).replace(/0+$/,'').replace(/\.$/,'');};
  const q4=v=>Number(v||0).toLocaleString('ko-KR',{maximumFractionDigits:4});
  const REQ='<span style="color:#c0392b">*</span>';
  const HINT='* 필수항목 제외품목들을 사용해보고 전산담당에게 알려주세요.';
  const st={q:'',slist:[],sel:null,selNm:'',searching:false,acT:null,ymd:'260630',
    mat:null,matErr:'',routeTarget:null,routeTargetNm:'',
    routes:[],gopts:[],lgopts:[],loading:false,rload:false,msg:'',
    newForm:null,detail:null,lineForm:null,vopts:[],
    weldDiams:[],weldEdit:null,np:null,procCat:null,procCatFor:''};   // #3 관경별 용접 팝업 재사용 · np=노드 스코프 공정팝업 · procCat=전체 공정 카탈로그 캐시
  const loadWeldDiams=async()=>{if(st.weldDiams.length)return;try{const r=await fetch(`${API}/api/weld/diam`);st.weldDiams=(await r.json()).rows||[];}catch(e){}};
  // ---------- 좌측 검색 ----------
  const search=async(auto)=>{st.searching=true;draw();
    try{const r=await fetch(`${API}/api/bom/search?q=${encodeURIComponent(st.q)}`);st.slist=(await r.json()).rows||[];}
    catch(e){st.msg='검색 실패';st.slist=[];}
    st.searching=false;draw();if(auto&&st.slist.length&&!st.sel)open(st.slist[0].item);};
  const fillDL=()=>{const dl=c.querySelector('#sv-dl');if(dl)dl.innerHTML=st.slist.slice(0,60).map(s=>`<option value="${esc(s.item)}">${esc((s.name||'').replace(/"/g,''))}</option>`).join('');};
  const ac=t=>{clearTimeout(st.acT);st.acT=setTimeout(async()=>{try{const r=await fetch(`${API}/api/bom/search?q=${encodeURIComponent(t)}`);st.slist=(await r.json()).rows||[];fillDL();}catch(e){}},180);};
  const nameOf=code=>{const m=(st.mat||[]).find(r=>String(r.code)===String(code));if(m)return m.name;const s=st.slist.find(x=>x.item===code);return s?s.name:'';};
  const open=async(item)=>{await discardFreshSilent();st.sel=item;st.selNm=(st.slist.find(s=>s.item===item)||{}).name||'';st.mat=null;st.matErr='';st.routes=[];st.loading=true;st.newForm=st.detail=st.lineForm=null;draw();
    try{const r=await fetch(`${API}/api/cost/nae?item=${encodeURIComponent(item)}&ymd=${encodeURIComponent(st.ymd)}`);const j=await r.json();
      if(j.error){st.matErr=j.error;st.mat=[];}else{st.mat=j.rows||[];if(!st.selNm)st.selNm=j.item||'';}}catch(e){st.matErr='내부원가 조회 실패';st.mat=[];}
    st.routeTarget=item;st.routeTargetNm=st.selNm;await loadRoutes();st.loading=false;draw();};
  const loadRoutes=async()=>{try{const r=await fetch(`${API}/api/sourcing/routes?item=${encodeURIComponent(st.routeTarget)}&show_unapproved=1&for_profile=0`);
      const j=await r.json();st.routes=j.routes||[];st.gopts=j.gubun_opts||[];st.lgopts=j.line_gubun_opts||[];st.nextNo=j.next_route_no||null;}catch(e){st.routes=[];}};
  const vSearch=t=>{clearTimeout(st.acT);st.acT=setTimeout(async()=>{try{const r=await fetch(`${API}/api/item/vendorsearch?q=${encodeURIComponent(t)}`);
      st.vopts=(await r.json()).rows||[];const dl=c.querySelector('#sv-vdl');if(dl)dl.innerHTML=st.vopts.map(v=>`<option value="${esc(v.code)}">${esc(v.code)} · ${esc(v.name)}</option>`).join('');}catch(e){}},180);};
  const routeById=id=>st.routes.find(r=>r.route_id===id)||(id===0?st.routes.find(r=>r.baseline):null);
  const altRoutes=()=>st.routes.filter(r=>!r.baseline);
  // ---------- 상단: 내부원가 재료 역전개 평면 ----------
  const flatMat=()=>{const normal=[],weld={};
    (st.mat||[]).filter(r=>r.level>0 && (+r.mat||0)>0).forEach(r=>{
      if(String(r.code).toUpperCase().startsWith('RAC')){const base=String(r.code).split('-')[0];
        const w=weld[base]||(weld[base]={code:base,name:r.name,metal:r.metal,diam:r.diam,thick:r.thick,qty:0});w.qty+=(+r.qty||0);}
      else normal.push(r);});
    return {normal:normal.sort((x,y)=>(+y.mat||0)-(+x.mat||0)),weldArr:Object.values(weld).sort((x,y)=>x.code<y.code?-1:1)};};
  const matTbl=()=>{
    if(st.matErr)return `<div class="empty" style="margin-top:14px;color:#c0392b">내부원가 조회 실패: ${esc(st.matErr)}</div>`;
    if(!st.mat)return '';
    const fm=flatMat(); if(!fm.normal.length&&!fm.weldArr.length)return `<div class="empty" style="margin-top:14px">재료 구성 없음</div>`;
    const row=(r,weld)=>{const sp=r.diam?('Ø'+r.diam+(r.thick?'×'+r.thick:'')):(r.spec||'');const on=(String(r.code)===String(st.routeTarget));const pick=!weld;
      return `<tr class="${pick?'sv-mrow':''}${on?' sel':''}" ${pick?`data-code="${esc(r.code)}"`:''} style="${pick?'cursor:pointer':'background:#f3eefa'}" ${pick?'title="클릭: 이 대상의 조달경로 후보를 아래에 표시"':''}>
        <td style="white-space:nowrap"><b style="color:#243244">${esc(r.code)}</b>${weld?' <span style="font-size:9px;color:#a8442a;border:1px solid #e6c0b3;border-radius:3px;padding:0 3px">용접봉→용접팀</span>':''}</td>
        <td class="bcap" title="${esc(r.name)}" style="max-width:230px;overflow:hidden;text-overflow:ellipsis">${esc(r.name)}</td>
        <td title="${esc(sp)}" style="max-width:130px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#5a6b82">${esc(sp)}</td>
        <td class="center" style="color:#5a6b82">${esc(r.metal||'')}</td>
        <td class="num">${q4(r.qty)}</td></tr>`;};
    return `<table class="tbl" style="font-size:12px"><thead><tr><th style="text-align:left">품번</th><th style="text-align:left">품명</th><th>규격</th><th>소재</th><th class="num">소요량</th></tr></thead>
      <tbody>${fm.normal.map(r=>row(r,false)).join('')}${fm.weldArr.map(r=>row(r,true)).join('')}</tbody></table>`;};
  // ---------- 하단: 후보 요약 카드 ----------
  const apBadge=r=>r.approve_flag?'<span style="background:#1c7c3a;color:#fff;border-radius:8px;padding:0 7px;font-size:10px">승인</span>':'<span style="background:#c0392b;color:#fff;border-radius:8px;padding:0 7px;font-size:10px">개발 미승인</span>';
  const card=r=>{const cur=r.current_flag||r.baseline||r.route_no===1;   // ★route_no=1=현행(current_flag 리셋돼도 방어)
    return `<div class="sv-card" data-rid="${r.route_id}" style="border:1px solid ${cur?'#bfe6cd':'#c9d3e0'};border-radius:8px;padding:8px 12px;margin-bottom:8px;background:${cur?'#eafaef':'#fff'};cursor:pointer;display:flex;flex-wrap:wrap;gap:6px;align-items:center" title="더블클릭: 상세${cur?' 보기':' 편집'}">
      <span style="background:${cur?'#1c7c3a':'#1c47a0'};color:#fff;border-radius:8px;padding:1px 8px;font-size:11px;font-weight:700" title="후보 라벨(base 품번은 불변)">${esc(st.routeTarget)}_R${String(r.baseline?1:r.route_no).padStart(2,'0')}${cur?' · 현행':''}</span>
      <b style="color:#1c3a6e">${esc(r.route_name||(r.baseline?'현행(실사용 BOM)':''))}</b>
      <span style="color:#5a6b82;font-size:12px">구분 <b>${esc(r.gubun||'-')}</b>${r.vendor_code?` · 공급처 <b>${esc(r.vendor_name||r.vendor_code)}</b>`:''}${r.apply_from?` · 적용 ${esc(r.apply_from)}`:''} · 라인 ${(r.lines||[]).length}</span>
      ${r.baseline?'<span style="color:#8aa0bd;font-size:10px">기준선</span>':(cur?'<span style="background:#1c7c3a;color:#fff;border-radius:8px;padding:0 7px;font-size:10px">현행</span>':apBadge(r))}
      <div style="flex:1"></div>
      ${cur
        ? `<button class="btn sv-open" data-rid="${r.route_id}" data-mode="view" style="padding:1px 8px;font-size:11px">상세</button>${canW?` <button class="btn sv-editcur" style="padding:1px 8px;font-size:11px;background:#1c47a0;color:#fff">수정</button>`:''}`
        : `<button class="btn sv-open" data-rid="${r.route_id}" data-mode="${canW?'edit':'view'}" style="padding:1px 8px;font-size:11px">${canW?'수정':'상세'}</button>${canW?` <button class="btn sv-appr" data-rid="${r.route_id}" data-on="${r.approve_flag?0:1}" style="padding:1px 8px;font-size:11px;${r.approve_flag?'':'background:#1c7c3a;color:#fff'}">${r.approve_flag?'승인취소':'승인'}</button> <button class="btn sv-rdel" data-rid="${r.route_id}" style="padding:1px 8px;font-size:11px;color:#c0392b">삭제</button>`:''}`}
    </div>`;};
  const routesPanel=()=>{
    const isRoot=st.routeTarget===st.sel;
    const tgt=`<div style="margin:2px 0 6px;padding:6px 11px;background:#eef5ff;border:1px solid #cfe0ff;border-radius:7px;font-size:12px;display:flex;flex-wrap:wrap;align-items:center;gap:8px">
      <span>조달대상: <b style="color:#1c47a0">${esc(st.routeTarget||'')}</b> <span style="color:#5a6b82">${esc(st.routeTargetNm||'')}</span> <span style="color:#8aa0bd">${isRoot?'(완제품·루트)':'(SUB/부품 — 상단 재료행 클릭 시 전환)'}</span></span>
      ${isRoot?'':`<button class="btn ghost sv-root" style="padding:1px 8px;font-size:11px">↩ 완제품(루트)로</button>`}
      <div style="flex:1"></div>
      ${canW?`<button class="btn sv-new" style="background:#1c7c3a;color:#fff">➕ 신규 조달프로파일(후보) 등록</button>`:''}</div>`;
    const note=altRoutes().length?'':`<div class="page-sub" style="color:#8aa0bd;margin:2px 0 8px">이 대상의 대안 후보가 없습니다 — <b>➕ 신규 조달프로파일 등록</b> 또는 현행 카드 더블클릭→[새 후보 만들기].</div>`;
    return `<div style="font-weight:700;color:#334;margin:2px 0 4px">② 조달경로 후보 <span style="font-size:11px;color:#8aa0bd;font-weight:400">SUB/조달대상 단위 · 후보1=현행(더블클릭 보기) · 대안(더블클릭 편집) · 승인해야 조달프로파일 노출</span></div>${tgt}${note}${st.rload?spinRow(1):st.routes.map(card).join('')}`;};
  // ---------- 신규 등록 모달 ----------
  const newModal=()=>{const f=st.newForm;if(!f)return '';
    const M=(v,lb,hint)=>`<label class="nb-m${f.method===v?' on':''}" style="display:flex;gap:8px;align-items:center;padding:8px 10px;border:1px solid ${f.method===v?'#1c7c3a':'#d3ddec'};border-radius:8px;background:${f.method===v?'#eafaf0':'#fff'};cursor:pointer;font-size:13px"><input type="radio" name="nrm" value="${v}" ${f.method===v?'checked':''}> <b>${lb}</b> <span style="color:#8aa0bd;font-size:11px;font-weight:400">${hint}</span></label>`;
    const alts=altRoutes();
    return `<div class="pmodal-bg" style="position:fixed;inset:0;background:rgba(20,40,80,.42);z-index:9990;display:flex;align-items:flex-start;justify-content:center;overflow:auto;padding:24px 10px">
      <div style="background:#fff;border-radius:12px;width:520px;max-width:95vw;box-shadow:0 20px 60px rgba(10,25,55,.4)">
        <div style="display:flex;justify-content:space-between;align-items:center;padding:12px 18px;background:#1c7c3a;color:#fff;border-radius:12px 12px 0 0"><b>➕ 신규 조달프로파일(후보) 등록</b><span id="nr-x" style="cursor:pointer;font-size:17px">✕</span></div>
        <div style="padding:16px 18px;font-size:12.5px">
          <label style="font-weight:700;color:#33507d">대상 품번</label>
          <div style="margin:3px 0 10px"><b style="font-size:14px;color:#1c47a0">${esc(f.target)}</b> <span style="color:#5a6b82">${esc(nameOf(f.target)||st.routeTargetNm)}</span> <span style="color:#8aa0bd;font-size:11px">(현재 조달대상)</span></div>
          <label style="font-weight:700;color:#33507d">후보명 <span style="color:#8aa0bd;font-weight:400">(자동 생성)</span></label>
          <div style="margin:3px 0 12px;padding:8px 10px;border:1px solid #cfe0d0;border-radius:8px;background:#f3faf5;font-size:14px">생성될 후보: <b style="color:#1c7c3a">${esc(f.autoLabel||'')}</b> <span style="color:#8aa0bd;font-size:11px">현행 R01 다음으로 자동 채번 · base 품번은 불변(라벨만)</span></div>
          <label style="font-weight:700;color:#33507d">시작 방법</label>
          <div style="display:flex;flex-direction:column;gap:6px;margin:4px 0 6px">
            ${M('cur','현행 복사','실사용 BOM(현행)을 복제해 대안 시작')}
            ${M('base','BASE BOM 가져오기','평면 BASE(실사용) 가져와 SUB 재구성 시작')}
            ${alts.length?M('copy','기존 후보 복사','다른 대안 후보를 복제'):''}
            ${M('blank','빈 상태(수동)','헤더만 만들고 라인은 상세에서 추가')}
            ${f.lgAvail?M('lg','LG BOM 불러오기','BOM 미등록 신규품목 — LG BOM(nx.lg_bom) 직하위 시딩'):''}
          </div>
          ${f.method==='copy'&&alts.length?`<label style="font-weight:700;color:#33507d">복사할 원본 후보</label>
            <select class="inp nf" data-k="source_route_id" style="width:100%;box-sizing:border-box;margin:3px 0 8px">${alts.map(r=>`<option value="${r.route_id}" ${+f.source_route_id===r.route_id?'selected':''}>후보 ${r.route_no} · ${esc(r.route_name||'')}</option>`).join('')}</select>`:''}
          ${f.method==='blank'?`<div style="margin-top:8px;padding:10px;border:1px solid #e2e8f2;border-radius:8px;background:#fafbfd">
            <div style="font-weight:700;color:#33507d;margin-bottom:6px">헤더(빈 후보 필수값)</div>
            <div style="display:grid;grid-template-columns:auto 1fr auto 1fr;gap:7px 9px;align-items:center">
              <label style="text-align:right;color:#33507d">구분${REQ}</label><select class="inp nf" data-k="gubun">${['',...st.gopts].map(o=>`<option value="${esc(o)}" ${String(o)===String(f.gubun||'')?'selected':''}>${o?esc(o):'(선택)'}</option>`).join('')}</select>
              <label style="text-align:right;color:#33507d">공급처${REQ}</label><input class="inp nf" list="sv-vdl" data-k="vendor_code" value="${esc(f.vendor_code||'')}" placeholder="거래처 검색">
              <label style="text-align:right;color:#33507d">유효일자${REQ}</label><input class="inp nf" type="date" data-k="apply_from" value="${esc(f.apply_from||'')}">
              <label style="text-align:right;color:#33507d">현행여부</label><label style="font-size:12px"><input type="checkbox" class="nf" data-k="current_flag" ${f.current_flag?'checked':''}> 현행</label>
            </div></div>`:''}
          <div style="color:#8aa0bd;font-size:11px;margin-top:10px">생성 시 <b style="color:#c0392b">개발 미승인</b> 상태이며, 곧바로 상세 편집 모달이 열립니다. 승인해야 조달프로파일에 노출됩니다.</div>
        </div>
        <div style="padding:12px 18px;border-top:1px solid #e2e8f2;text-align:right"><button class="btn ghost" id="nr-cancel">취소</button> <button class="btn" id="nr-create" style="background:#1c7c3a;color:#fff">생성 →</button></div>
      </div><datalist id="sv-vdl"></datalist></div>`;};
  // ---------- 상세 모달(보기/편집) ----------
  const lineRow=(l,ed)=>`<tr>
    <td><b>${esc(l.child_item)}</b></td><td class="bcap" style="max-width:160px;overflow:hidden;text-overflow:ellipsis" title="${esc(l.child_name)}">${esc(l.child_name)}</td>
    <td class="num">${nfq(l.qty)}</td><td>${esc(l.gubun)}</td><td title="${esc(l.vendor_code)}">${esc(l.vendor_name||l.vendor_code||'')}</td>
    <td>${l.is_rawmat?`Ø${nfq(l.diam)}×${nfq(l.thick)}×${nfq(l.len_val)} · ${esc(l.material)}`:'<span style="color:#c3c9d4">-</span>'}</td>
    ${ed?`<td class="center"><button class="btn dl-e" data-lid="${l.line_id}" style="padding:1px 5px;font-size:10px">수정</button><button class="btn dl-d" data-lid="${l.line_id}" style="padding:1px 5px;font-size:10px">삭제</button></td>`:''}</tr>`;
  // ===== STEP3: 후보 SUB 재구성·공정배치 패널 (drag=체크선택→SUB, 공정 배치, 공수합=BASE 게이트) =====
  const loadRD=async(rid)=>{try{const r=await fetch(`${API}/api/sourcing/route/detail?route_id=${rid}`);st.rd=await r.json();st.rd.route_id=rid;st.rdProc=null;}catch(e){st.rd={route_id:rid,error:e.message};}draw();};
  // 빈 SUB 자동 소멸(하위부품 0개 SUB 삭제) — 드래그로 부품 다 빠지면 SUB 안 남김
  const dissolveEmptySubs=async(rid)=>{const rd=st.rd;if(!rd||rd.route_id!==rid||!rd.lines)return;
    const subs=rd.lines.filter(l=>l.node_kind==='SUB');
    const empties=subs.filter(s=>!rd.lines.some(l=>l.parent_line===s.line_id));
    if(!empties.length)return;
    for(const s of empties){try{await fetch(`${API}/api/sourcing/sub/dissolve`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({route_id:rid,sub_line:s.line_id})});}catch(e){}}
    st.rdProc=null;await loadRD(rid);};
  const loadRP=async(rid)=>{try{const r=await fetch(`${API}/api/sourcing/profile/list?route_id=${rid}`);const j=await r.json();st.rp={route_id:rid,rows:(j.rows||[]),header:j.header||{}};}catch(e){st.rp={route_id:rid,error:e.message};}draw();};
  const vSearch2=t=>{clearTimeout(st.acT2);st.acT2=setTimeout(async()=>{try{const r=await fetch(`${API}/api/sourcing/vendors?q=${encodeURIComponent(t)}`);
    const dl=c.querySelector('#sv-vdl2');if(dl)dl.innerHTML=((await r.json()).rows||[]).map(v=>`<option value="${esc(v.code)}">${esc(v.code)} · ${esc(v.name)}${v.role?' ('+esc(v.role)+')':''}</option>`).join('');}catch(e){}},180);};
  const _pmap={'28':'은납','51':'용접','52':'지그','53':'교정','54':'수몰','55':'부품부착','56':'에어','61':'포장','69':'너트','83':'포장'};
  // ===== ★재설계: 좌=부품풀(배지·드래그) / 우=ASSY계층트리(레벨0+SUB, 노드[수정]=공정팝업, 드롭=배치) =====
  const subPanel=(R)=>{
    const rd=(st.rd&&st.rd.route_id===R.route_id)?st.rd:null;
    if(!rd) return `<div style="margin-top:10px;border-top:2px solid #e2e8f2;padding-top:8px"><button class="btn" id="sp-open" style="background:#8e44ad;color:#fff;padding:3px 12px">🧩 SUB 재구성 · 공정 배치 열기</button> <span style="color:#8aa0bd;font-size:11px">좌 부품풀→우 계층트리 드래그로 SUB 묶기 · 절삭공정 부품따라감 · 노드[수정]=공정팝업 · 공수합=BASE</span></div>`;
    if(rd.error) return `<div style="margin-top:10px;color:#c0392b">SUB패널 오류: ${esc(rd.error)}</div>`;
    const RACX=l=>String(l.child_item||'').toUpperCase().startsWith('RAC')&&!String(l.child_name||'').includes('용접링');   // 용접봉(RAC) 제외·용접링은 유지(사급부품)
    const lines=(rd.lines||[]).filter(l=>!RACX(l)), subs=lines.filter(l=>l.node_kind==='SUB'), parts=lines.filter(l=>l.node_kind!=='SUB');
    const flat=parts.filter(p=>!p.parent_line), memb=sid=>parts.filter(p=>p.parent_line===sid);
    const ASSY=st.routeTarget, partCut=rd.part_cut||{};
    const subOf=sid=>{const s=subs.find(x=>x.line_id===sid);return s?(s.sub_item||s.child_item):null;};
    const badgeOf=p=>{if(!p.parent_line)return {t:'레벨0·ASSY',c:'#1c47a0'};const sc=subOf(p.parent_line);return sc?{t:'SUB '+sc,c:'#8e44ad'}:{t:'미배치',c:'#c0392b'};};
    const procByNode={};(rd.procs||[]).forEach(p=>{procByNode[p.node_item]=(procByNode[p.node_item]||0)+(+p.work_qty||0);});
    const cutOfPart=code=>{const arr=partCut[code];return arr?arr.reduce((a,x)=>a+(+x.wq||0),0):0;};
    const cutOfNode=np2=>np2.reduce((a,p)=>a+cutOfPart(p.child_item),0);
    let cutSum=0;Object.values(partCut).forEach(arr=>arr.forEach(x=>cutSum+=+x.wq||0));cutSum=Math.round(cutSum*100)/100;
    let procSum=0;(rd.procs||[]).forEach(p=>procSum+=+p.work_qty||0);procSum=Math.round(procSum*100)/100;
    const total=Math.round((cutSum+procSum)*100)/100, base=rd.base_gongsu||0, ok=Math.abs(total-base)<0.5;
    const cutBadge=code=>{const arr=partCut[code];if(!arr||!arr.length)return '';const s=arr.reduce((a,x)=>a+(+x.wq||0),0);
      return ` <span title="절삭공정 자동귀속(부품 위치 따라감): ${esc(arr.map(x=>x.name+' '+nfq(x.wq)).join(', '))}" style="color:#b5651d;font-size:10px;border:1px solid #e6cfae;border-radius:3px;padding:0 4px">⚙${nfq(s)}</span>`;};
    const poolRow=p=>{const b=badgeOf(p);return `<div draggable="true" class="sp-drag" data-lid="${p.line_id}" style="display:flex;align-items:center;gap:5px;font-size:12px;cursor:grab;padding:2px 0;border-bottom:1px solid #f0eef6">
      <span>⠿</span><b>${esc(p.child_item)}</b><span style="color:#8a94a6;max-width:110px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(p.child_name||'')}</span>${cutBadge(p.child_item)}
      <span style="margin-left:auto;color:${b.c};font-size:10px;border:1px solid ${b.c}55;border-radius:8px;padding:0 6px;white-space:nowrap">${esc(b.t)}</span>
      <button class="btn sp-ledit" draggable="false" data-lid="${p.line_id}" title="부품 라인 직접수정(BOM 구성과 동일 폼)" style="padding:0 5px;font-size:10px;color:#1c47a0">✎</button></div>`;};
    const nodeBox=(node,label,color,dsub,np2,depth)=>{const ng=Math.round((cutOfNode(np2)+(procByNode[node]||0))*100)/100;
      const kids=subs.filter(s=>dsub>0?s.parent_line===dsub:!s.parent_line);   // ★이 노드의 자식 SUB(중첩=서브안의서브)
      return `<div class="sp-drop" data-sub="${dsub}" style="border:1px dashed ${color}66;border-radius:7px;padding:5px 7px;margin:0 0 6px ${(depth||0)*16}px;background:#fff">
        <div style="display:flex;align-items:center;gap:6px;font-size:12px"><b style="color:${color}">${esc(label)}</b><span style="color:#8a94a6;font-size:10px">노드공수 ${nfq(ng)}</span><div style="flex:1"></div>
          ${dsub>0?`<button class="btn sp-ndissolve" data-sub="${dsub}" title="이 SUB 해체 — 하위부품 ASSY(레벨0) 복귀 · 비종속 공정/용접은 ASSY 이관(공수합 보존)" style="padding:0 8px;font-size:10px;background:#c0392b;color:#fff">🧩 해체</button>`:''}
          <button class="btn sp-nedit" data-node="${esc(node)}" data-sub="${dsub}" title="${dsub>0?'SUB':'ASSY'} 노드 공정편집 — 관경별 용접 + 공정별 작업ST 팝업(노드 스코프)" style="padding:1px 9px;font-size:10px;background:${color};color:#fff">⚙ ${dsub>0?'SUB':'ASSY'} 공정수정</button></div>
        ${np2.map(p=>`<div style="font-size:11.5px;padding:1px 0 1px 14px;color:#33507d">• ${esc(p.child_item)} <span style="color:#8a94a6">${esc(p.child_name||'')}</span>${cutBadge(p.child_item)}</div>`).join('')||(kids.length?'':'<div style="color:#8a94a6;font-size:10.5px;padding-left:14px">부품 없음 — 왼쪽 풀에서 드래그</div>')}
        ${kids.map(s=>nodeBox((s.sub_item||s.child_item),'▸ SUB '+(s.sub_item||s.child_item),'#8e44ad',s.line_id,memb(s.line_id),(depth||0)+1)).join('')}
        <div class="sp-newsub" data-parentsub="${dsub}" style="border:${dsub>0?'1px':'2px'} dashed #a678d0;border-radius:${dsub>0?'5px':'8px'};padding:${dsub>0?'4px 8px':'14px 8px'};text-align:center;color:#8e44ad;font-size:${dsub>0?'10px':'12.5px'};font-weight:600;background:#f6f0fc;cursor:copy;margin-top:6px;${dsub>0?'':'min-height:44px;display:flex;align-items:center;justify-content:center'}">${dsub>0?'➕ 서브 안에 중첩 SUB로 묶기':'➕ 부품을 여기로 드래그 → 새 SUB로 묶기 (레벨1)'}</div>
      </div>`;};
    return `<div style="margin-top:10px;border-top:2px solid #d6c3ea;padding-top:8px">
      <style>.sp-drop.dz-hi{box-shadow:0 0 0 2px #1c47a0 inset;background:#eef4ff!important}.sp-newsub.dz-hi{background:#e3c8f5!important;border-color:#8e44ad!important;color:#6c2f96!important;transform:scale(1.01)}</style>
      <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
        <div style="font-weight:700;color:#8e44ad">🧩 SUB 재구성 · 공정 배치</div>
        <span id="sp-gate" style="font-size:11px;color:${ok?'#1c7c3a':'#c0392b'}">공수합 ${nfq(total)} / BASE ${base} = 절삭 ${nfq(cutSum)} + 조립 ${nfq(procSum)} ${ok?'✔':'✖ 불일치'}</span>
        <button class="btn" id="sp-validate" style="margin-left:auto;background:#1c47a0;color:#fff;padding:2px 12px" title="공수합=BASE · 부품수=BASE · 구성 검증만 수행(저장하지 않음). 저장은 하단 [저장] 버튼.">🔍 BOM 검증</button></div>
      <div style="display:flex;gap:10px;flex-wrap:wrap;margin-top:6px">
        <div style="flex:1;min-width:250px;min-height:420px;border:1px solid #d6c3ea;border-radius:8px;padding:8px;background:#faf7ff">
          <div style="display:flex;align-items:center;font-size:12px;font-weight:600;margin-bottom:4px">부품 풀 <span style="color:#8a94a6;font-weight:400;margin-left:5px">(전 구성부품·배지=배치노드·오른쪽 SUB/새SUB존으로 드래그)</span></div>
          ${flat.map(poolRow).join('')||'<div class="empty" style="font-size:11px">미배치 부품 없음 — 모두 SUB에 배치됨 (RAC 용접봉 제외)</div>'}
        </div>
        <div style="flex:1.3;min-width:300px;min-height:420px;border:1px solid #cfe0ff;border-radius:8px;padding:8px;background:#f7faff">
          <div style="font-size:12px;font-weight:600;margin-bottom:4px">ASSY 계층 트리 <span style="color:#8a94a6;font-weight:400">(SUB 노드 위=하이라이트+추가 · "새 SUB로 묶기"=SUB 생성 · 레벨1 바닥=무반응)</span></div>
          ${nodeBox(ASSY,'▣ '+ASSY+' (레벨0·ASSY)','#1c47a0',0,flat,0)}
        </div>
      </div></div>`;};
  // ===== ★노드 스코프 공정 팝업 = 품목BOM관리 '내부원가' 팝업과 완전 동일 창(PROC_MODAL_HTML 공유) =====
  //   레벨0=ASSY값(없으면 BASE 조립 시드) / 신규SUB=빈값. cols=전체 공정(가공 own + 조립 assy) · 관경=전체.
  //   상단 info(이 노드 공수/전체 공수합/BASE ±차이)만 추가(레이아웃 본체는 naeProcModal과 100% 동일).
  const nodeProcModal=()=>{const np=st.np;if(!np)return '';
    // 관경별 용접 소요량/ST(표시) — weldCounts × 표준(st.weldDiams)
    const STS={},STU={};(st.weldDiams||[]).forEach(d=>{STS[d.pipe_diam.toFixed(2)]=d.std_st;STU[d.pipe_diam.toFixed(2)]=d.std_use_qty;});
    let wSt=0;Object.keys(np.weldCounts||{}).forEach(k=>{const q=+np.weldCounts[k]||0;if(q>0)wSt+=(STS[k]||0)*q;});wSt=Math.round(wSt*100)/100;
    // cols = own(가공) + assy(조립). naeProcModal과 동일 구성(sec='own'/'c0').
    const cols=[];
    (np.own||[]).forEach((p,i)=>cols.push({name:p.name,code:p.proc_code,sec:'own',idx:i,uph:p.prod_uph,cg:p.calc_gubun,wq:p.work_qty}));
    (np.assy||[]).forEach((p,i)=>cols.push({name:p.name,code:p.proc_code,sec:'c0',idx:i,uph:p.prod_uph,cg:p.calc_gubun,wq:p.work_qty}));
    // 상단 info(추가): 이 노드 공수(절삭 자동귀속 + 조립 라이브) / 전체 공수합 / BASE ±차이
    const cutSum=np.cutSum||0;
    let nodeAsm=0;cols.forEach(cc=>nodeAsm+=+cc.wq||0);nodeAsm=Math.round(nodeAsm*100)/100;
    const nodeG=Math.round((cutSum+nodeAsm)*100)/100;
    const globalTotal=Math.round((np.otherTotal+cutSum+nodeAsm)*100)/100, gdiff=Math.round((globalTotal-np.base)*100)/100, gok=Math.abs(gdiff)<0.5;
    const infoBar=`<div style="font-size:11.5px;padding:5px 8px;background:#f4f7fc;border-radius:6px;margin-bottom:8px">이 노드 공수 <b style="color:#1c47a0">${nfq(nodeG)}</b> (절삭 ${nfq(cutSum)}+조립 ${nfq(nodeAsm)}) · 전체 공수합 <b style="color:${gok?'#1c7c3a':'#c0392b'}">${nfq(globalTotal)}</b> / BASE ${np.base} <span style="color:${gok?'#1c7c3a':'#c0392b'}">(${gdiff>0?'+':''}${nfq(gdiff)}${gok?' ✔':' ✖ 차감/추가 필요'})</span>`
      +(cutSum?` · <span style="color:#b5651d">⚙ 절삭(부품 자동귀속·읽기전용): ${(np.cutRows||[]).map(x=>esc(x.name)+' '+nfq(x.wq)).join(', ')} = ${nfq(cutSum)}</span>`:'')
      +` · 🔧 용접ST(가공비) <b style="color:#8e44ad">${nfq(wSt)}</b> (용접공정 컬럼에 입력/시드된 값이 공수합에 반영)</div>`;
    return PROC_MODAL_HTML({node:np.node,title:`✎ 공정 등록/수정 — ${esc(np.label)}`,subtitle:(np.isAssy?'제품/조립 — 관경별 용접 + 조립공정(용접·포장·체결)':'부품 — 가공공정'),
      isAssy:np.isAssy,weldDiams:st.weldDiams,weldItem:np.weldItem,weldTypes:np.weldTypes,weldCounts:np.weldCounts,cols,infoBar});};
  // ---------- #4 업체 매핑(조달프로파일) — 승인 후보(구조)에 업체·배분%·유효기간 (2계층) ----------
  const profPanel=(R)=>{
    const rp=(st.rp&&st.rp.route_id===R.route_id)?st.rp:null;
    if(!rp) return `<div style="margin-top:10px;border-top:2px solid #cfe0d0;padding-top:8px"><button class="btn" id="rp-open" style="background:#1c7c3a;color:#fff;padding:3px 12px">🏭 업체 매핑(조달프로파일) 열기</button> <span style="color:#8aa0bd;font-size:11px">승인 후보(구조)에 <b>업체·배분%·유효기간</b> 지정 · 활성 배분합=100% 강제</span></div>`;
    if(rp.error) return `<div style="margin-top:10px;color:#c0392b">업체매핑 오류: ${esc(rp.error)}</div>`;
    const rows=rp.rows||[];
    const act=rows.filter(r=>!r._delete&&r.is_active&&r.alloc_ratio!=null&&r.alloc_ratio!==''&&!r.is_internal);
    const sum=Math.round(act.reduce((a,r)=>a+(+r.alloc_ratio||0),0)*100)/100;
    const ok=act.length===0||Math.abs(sum-100)<0.01;
    return `<div style="margin-top:10px;border-top:2px solid #b9dcc4;padding-top:8px">
      <div style="font-weight:700;color:#1c7c3a">🏭 업체 매핑(조달프로파일) <span id="rp-gate" style="font-size:11px;font-weight:400;color:${ok?'#1c7c3a':'#c0392b'}">활성 배분합 ${nfq(sum)}% ${ok?'✔':'✖ 100% 아님(저장거부)'}</span> <span style="color:#8a94a6;font-size:11px;font-weight:400">이 후보(구조)를 실제로 제작·조달하는 업체와 배분비율</span></div>
      <div style="overflow:auto;margin-top:6px"><table class="tbl" style="font-size:11.5px"><thead><tr>
        <th>업체</th><th class="num">배분%</th><th>유효 시작</th><th>유효 종료</th><th class="center">활성</th><th class="center">LME</th><th style="width:40px"></th></tr></thead>
        <tbody>${rows.map((r,i)=>r._delete?'':`<tr>
          <td><input class="rp-f" data-i="${i}" data-k="vendor_code" list="sv-vdl2" value="${esc(r.vendor_code||'')}" style="width:120px" placeholder="업체코드">${r.vendor_name?` <span style="color:#8a94a6;font-size:10px">${esc(r.vendor_name)}</span>`:''}</td>
          <td class="num"><input class="rp-f" data-i="${i}" data-k="alloc_ratio" type="number" step="any" min="0" max="100" value="${r.alloc_ratio!=null?r.alloc_ratio:''}" style="width:56px;text-align:right"></td>
          <td><input class="rp-f" data-i="${i}" data-k="apply_from" type="date" value="${esc(r.apply_from||'')}"></td>
          <td><input class="rp-f" data-i="${i}" data-k="apply_to" type="date" value="${esc(r.apply_to||'')}"></td>
          <td class="center"><input class="rp-f" data-i="${i}" data-k="is_active" type="checkbox" ${r.is_active?'checked':''}></td>
          <td class="center"><input class="rp-f" data-i="${i}" data-k="lme_flag" type="checkbox" ${r.lme_flag?'checked':''}></td>
          <td class="center"><button class="btn rp-del" data-i="${i}" style="padding:0 6px;font-size:10px;color:#c0392b">✕</button></td></tr>`).join('')||'<tr><td colspan="7" class="empty">업체 매핑 없음 (➕ 업체추가)</td></tr>'}</tbody></table></div>
      <button class="btn" id="rp-add" style="margin-top:6px;padding:2px 10px">➕ 업체추가</button>
      <button class="btn" id="rp-save" style="margin-top:6px;background:#1c7c3a;color:#fff;padding:2px 10px">💾 업체 매핑 저장</button>
      <datalist id="sv-vdl2"></datalist></div>`;};
  // ---------- #3 관경별 용접 팝업(내부원가 재사용) — 노드별 용접점→용접ST(가공비)·용접봉 소요량(재료) ----------
  const weldPrev=r=>{const d=st.weldDiams.find(x=>Math.abs(x.pipe_diam-(+r.pipe_diam||0))<0.01);if(!d||!(+r.weld_qty>0))return {use:0,st:0};return {use:d.std_use_qty*(+r.weld_qty)*1.5,st:d.std_st*(+r.weld_qty)};};
  const weldModal=()=>{const w=st.weldEdit;if(!w)return '';
    const opts=st.weldDiams.map(d=>`<option value="${d.pipe_diam}">${d.pipe_diam}φ (원단위 ${nfq(d.std_use_qty)} · ST ${nfq(d.std_st)})</option>`).join('');
    let tUse=0,tSt=0;w.rows.forEach(r=>{const p=weldPrev(r);tUse+=p.use;tSt+=p.st;});tUse=Math.round(tUse*10000)/10000;tSt=Math.round(tSt*100)/100;
    return `<div class="pmodal-bg" style="position:fixed;inset:0;background:rgba(30,20,50,.45);z-index:9995;display:flex;align-items:flex-start;justify-content:center;overflow:auto;padding:30px 10px">
      <div style="background:#fff;border-radius:11px;width:640px;max-width:96vw;box-shadow:0 20px 60px rgba(30,10,55,.4)">
        <div style="display:flex;justify-content:space-between;align-items:center;padding:11px 16px;background:#8e44ad;color:#fff;border-radius:11px 11px 0 0"><b>🔧 관경별 용접점 — ${esc(w.label)}</b><span id="wm-x" style="cursor:pointer;font-size:17px">✕</span></div>
        <div style="padding:12px 16px">
          <div style="color:#8a94a6;font-size:11px;margin-bottom:6px">용접봉 소요량 = Σ(원단위×점수)×1.5 <b>(재료)</b> · 용접ST = Σ(표준ST×점수) <b>(가공비)</b> — 내부원가 관경별 용접 팝업과 동일 표준(nx.weld_diam)</div>
          <datalist id="wm-roddl"><option value="RAC30599301-1">1% 용접봉</option><option value="RAC30599327">3% 용접봉</option><option value="RAC30599303">BCUP</option></datalist>
          <table class="tbl" style="font-size:11.5px"><thead><tr><th>용접봉</th><th>관경</th><th class="num">점수</th><th class="num">소요량</th><th class="num">ST</th><th style="width:34px"></th></tr></thead>
          <tbody>${w.rows.map((r,i)=>{const pv=weldPrev(r);return `<tr>
            <td><input class="wm-f" data-i="${i}" data-k="weld_item" list="wm-roddl" value="${esc(r.weld_item||'')}" style="width:120px" placeholder="RAC…"></td>
            <td><select class="wm-f" data-i="${i}" data-k="pipe_diam" style="width:150px"><option value="">-관경-</option>${opts.replace(`value="${r.pipe_diam}"`,`value="${r.pipe_diam}" selected`)}</select></td>
            <td class="num"><input class="wm-f" data-i="${i}" data-k="weld_qty" type="number" step="1" min="0" value="${r.weld_qty!=null&&r.weld_qty!==''?r.weld_qty:''}" style="width:52px;text-align:right"></td>
            <td class="num">${q4(pv.use)}</td><td class="num">${nfq(pv.st)}</td>
            <td class="center"><span class="wm-del" data-i="${i}" style="cursor:pointer;color:#c0392b">✖</span></td></tr>`;}).join('')||'<tr><td colspan="6" class="empty">＋용접점으로 추가</td></tr>'}</tbody>
          <tfoot><tr><td colspan="3" style="text-align:right;color:#8a94a6">합계</td><td class="num"><b>${q4(tUse)}</b></td><td class="num"><b>${nfq(tSt)}</b></td><td></td></tr></tfoot></table>
          <button class="btn" id="wm-add" style="margin-top:6px;padding:1px 10px">＋ 용접점</button>
        </div>
        <div style="padding:11px 16px;border-top:1px solid #e2e8f2;display:flex;justify-content:space-between;align-items:center">
          <span style="color:#8a94a6;font-size:11px">저장 시 용접봉 소요량(재료)·용접ST 기록 · 후보 미승인 리셋</span>
          <span><button class="btn" id="wm-apply" style="background:#8e44ad;color:#fff">💾 저장 + ST ${nfq(tSt)} → [${esc(_pmap[w.wproc]||w.wproc)}]공정 적용</button> <button class="btn" id="wm-cancel">닫기</button></span></div>
      </div></div>`;};
  const detailModal=()=>{const d=st.detail;if(!d)return '';const R=routeById(d.route_id);if(!R)return '';
    const ed=d.mode==='edit'&&canW&&!R.baseline, h=d.hdr||{};
    const hdrView=`<div style="color:#5a6b82;font-size:12.5px">구분 <b>${esc(R.gubun||'-')}</b>${R.vendor_code?` · 공급처 <b>${esc(R.vendor_name||R.vendor_code)}</b>`:''}${R.apply_from?` · 적용 ${esc(R.apply_from)}`:''}${R.note?` · ${esc(R.note)}`:''}</div>`;
    const hdrEdit=`<div style="display:grid;grid-template-columns:auto 1fr auto 1fr;gap:8px 10px;align-items:center;font-size:12px;padding:10px 0;border-bottom:1px dashed #e2e8f2">
        <label style="text-align:right;color:#33507d;font-weight:600">경로명</label><input class="inp df" data-k="route_name" value="${esc(h.route_name||'')}">
        <label style="text-align:right;color:#33507d;font-weight:600">구분${REQ}</label><select class="inp df" data-k="gubun">${['',...st.gopts].map(o=>`<option value="${esc(o)}" ${String(o)===String(h.gubun||'')?'selected':''}>${o?esc(o):'(선택)'}</option>`).join('')}</select>
        <label style="text-align:right;color:#33507d;font-weight:600">유효일자${REQ}</label><input class="inp df" type="date" data-k="apply_from" value="${esc(h.apply_from||'')}">
        <label style="text-align:right;color:#33507d;font-weight:600">비고</label><input class="inp df" data-k="note" value="${esc(h.note||'')}">
        <div style="grid-column:1/-1;color:#8aa0bd;font-size:10.5px">업체(공급처)는 승인 후 <b>업체 매핑(조달프로파일)</b>에서 배분% 지정합니다 — 후보 헤더엔 지정하지 않습니다.</div>
      </div>`;
    const fresh=ed&&!!d.fresh;   // 신규 미커밋 드래프트(가져오기로 방금 생성, [등록] 전) — 닫기=등록취소(롤백)
    const isCur=!R.baseline&&(R.current_flag||R.route_no===1);
    const footL=R.baseline
      ? (canW?`<button class="btn" id="dt-editcur" style="background:#1c47a0;color:#fff">현행 수정</button> <button class="btn" id="dt-newfromcur" style="background:#1c7c3a;color:#fff">이 현행으로 새 후보 만들기</button>`:'')
      : (fresh
          ? '<span style="color:#8aa0bd;font-size:11px">[등록]해야 후보가 확정됩니다 · 닫기/취소 = 등록 취소</span>'
          : (canW?(isCur
              ? `<button class="btn" id="dt-resetcur" style="background:#e67e22;color:#fff" title="실사용 BOM에서 라인을 다시 불러와 편집 초기화">🔄 BOM 다시 불러오기</button>`   // ★현행: BOM리셋만(승인 없음 — 실사용 BOM 자체라 승인대상 아님)
              : `<button class="btn sv-appr" data-rid="${R.route_id}" data-on="${R.approve_flag?0:1}" style="${R.approve_flag?'':'background:#1c7c3a;color:#fff'}">${R.approve_flag?'승인취소':'✔ 승인(개발)'}</button>`   // 대안: 승인
            ):''));
    const footR=R.baseline
      ? `<button class="btn" id="dt-close">닫기</button>`
      : (fresh
          ? `<button class="btn" id="dt-cancel" style="color:#c0392b">✖ 취소</button> <button class="btn" id="dt-register" style="background:#1c7c3a;color:#fff">✔ 등록</button>`
          : `${(canW&&ed)?`<button class="btn" id="dt-hsave2" style="background:#1b6ec2;color:#fff">💾 저장</button> `:''}<button class="btn" id="dt-close">닫기</button>`);
    return `<div class="pmodal-bg" style="position:fixed;inset:0;background:rgba(20,40,80,.42);z-index:9990;display:flex;align-items:flex-start;justify-content:center;overflow:auto;padding:20px 10px">
      <div style="background:#fff;border-radius:12px;width:1080px;max-width:97vw;max-height:94vh;display:flex;flex-direction:column;box-shadow:0 20px 60px rgba(10,25,55,.4)">
        <div style="flex:0 0 auto;display:flex;justify-content:space-between;align-items:center;padding:12px 18px;background:${R.baseline?'#1c7c3a':'#1c47a0'};color:#fff;border-radius:12px 12px 0 0">
          <b>${R.baseline?'현행 조달경로 상세(보기)':(fresh?'조달후보 신규 등록':'조달후보 상세 편집')} — ${esc(st.routeTarget)}_R${String(R.baseline?1:R.route_no).padStart(2,'0')}${R.baseline?' (현행·base품번 불변)':''}</b><span id="dt-x" style="cursor:pointer;font-size:17px">✕</span></div>
        <div style="flex:1 1 auto;overflow:auto;padding:14px 18px">
          <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:6px"><b style="color:#1c3a6e;font-size:14px">${esc(R.route_name||(R.baseline?'현행(실사용 BOM)':''))}</b>${R.baseline?'<span style="color:#8aa0bd;font-size:11px">기준선(읽기전용)</span>':apBadge(R)}</div>
          ${ed?hdrEdit:hdrView}
          ${!ed?`<div style="font-weight:700;color:#334;margin:10px 0 4px">구성 라인 (${(R.lines||[]).length})</div>
          <div class="grid-wrap" style="max-height:38vh;overflow:auto"><table class="tbl" style="font-size:11.5px"><thead><tr>
            <th>하위품번</th><th>품명</th><th class="num">소요량</th><th>구분</th><th>공급처</th><th>소재(외경×두께×길이·재질)</th></tr></thead>
            <tbody>${(R.lines||[]).length?R.lines.map(l=>lineRow(l,false)).join(''):`<tr><td colspan="6" class="empty">라인 없음</td></tr>`}</tbody></table></div>`:''}
          ${ed?subPanel(R):''}
          ${(canW&&!R.baseline&&R.approve_flag)?profPanel(R):(!R.baseline&&R.approve_flag?'':(!R.baseline?'<div style="margin-top:10px;color:#8aa0bd;font-size:11.5px;border-top:1px dashed #e2e8f2;padding-top:8px">🏭 업체 매핑은 <b>승인(개발)</b> 후 가능합니다 — 승인하면 이 후보(구조)에 업체·배분%를 지정할 수 있습니다.</div>':''))}
        </div>
        <div style="flex:0 0 auto;padding:12px 18px;border-top:1px solid #e2e8f2;display:flex;justify-content:space-between;align-items:center;background:#fff;border-radius:0 0 12px 12px">
          <span>${footL}</span><span>${footR}</span></div>
      </div><datalist id="sv-vdl"></datalist></div>`;};
  // ---------- 라인 편집 모달(상세 위에) ----------
  const lineModal=()=>{const f=st.lineForm;if(!f)return '';const rm=!!f.is_rawmat;
    return `<div class="pmodal-bg" style="position:fixed;inset:0;background:rgba(20,30,50,.4);z-index:9998;display:flex;align-items:flex-start;justify-content:center;overflow:auto;padding:24px 10px">
      <div style="background:#fff;border-radius:10px;width:640px;max-width:96vw;box-shadow:0 20px 60px rgba(10,25,55,.4)">
        <div style="display:flex;justify-content:space-between;align-items:center;padding:11px 16px;background:#1c47a0;color:#fff;border-radius:10px 10px 0 0"><b>구성 라인 ${f.line_id?'수정':'추가'}</b><span id="ln-x" style="cursor:pointer;font-size:17px">✕</span></div>
        <div style="padding:14px 16px;display:grid;grid-template-columns:auto 1fr auto 1fr;gap:9px 10px;align-items:center;font-size:12px">
          <label style="color:#33507d;font-weight:600;text-align:right">하위품번${REQ}</label><input class="inp lf" data-k="child_item" value="${esc(f.child_item||'')}">
          <label style="color:#33507d;font-weight:600;text-align:right">품명${REQ}</label><input class="inp lf" data-k="child_name" value="${esc(f.child_name||'')}">
          <label style="color:#33507d;font-weight:600;text-align:right">소요량${REQ}</label><input class="inp lf" type="number" step="any" data-k="qty" value="${f.qty!=null&&f.qty!==''?f.qty:''}">
          <label style="color:#33507d;font-weight:600;text-align:right">구분${REQ}</label><select class="inp lf" data-k="gubun">${['',...st.lgopts].map(o=>`<option value="${esc(o)}" ${String(o)===String(f.gubun||'')?'selected':''}>${o?esc(o):'(선택)'}</option>`).join('')}</select>
          <label style="color:#33507d;font-weight:600;text-align:right">공급처<span style="font-size:9px;color:#8aa0bd">(매입필수)</span></label><input class="inp lf" list="sv-vdl" data-k="vendor_code" value="${esc(f.vendor_code||'')}" placeholder="거래처 검색">
          <label style="color:#33507d;font-weight:600;text-align:right">소재계산</label><label style="font-size:12px"><input type="checkbox" class="lf" data-k="is_rawmat" ${rm?'checked':''}> 원소재(치수·재질 계산 대상)</label>
          <label style="color:#33507d;font-weight:600;text-align:right">외경${rm?REQ:''}</label><input class="inp lf" type="number" step="any" data-k="diam" value="${f.diam||''}" ${rm?'':'style="background:#f2f4f7"'}>
          <label style="color:#33507d;font-weight:600;text-align:right">두께${rm?REQ:''}</label><input class="inp lf" type="number" step="any" data-k="thick" value="${f.thick||''}" ${rm?'':'style="background:#f2f4f7"'}>
          <label style="color:#33507d;font-weight:600;text-align:right">길이${rm?REQ:''}</label><input class="inp lf" type="number" step="any" data-k="len_val" value="${f.len_val||''}" ${rm?'':'style="background:#f2f4f7"'}>
          <label style="color:#33507d;font-weight:600;text-align:right">재질${rm?REQ:''}</label><input class="inp lf" data-k="material" value="${esc(f.material||'')}" ${rm?'':'style="background:#f2f4f7"'}>
          <label style="color:#33507d;font-weight:600;text-align:right">규격</label><input class="inp lf" data-k="spec" value="${esc(f.spec||'')}">
          <label style="color:#33507d;font-weight:600;text-align:right">비고</label><input class="inp lf" data-k="note" value="${esc(f.note||'')}">
        </div>
        <div style="padding:11px 16px;border-top:1px solid #e2e8f2;display:flex;justify-content:space-between;align-items:center">
          <span style="color:#c0392b;font-size:11px">${HINT} 소요량은 원가/조달/재고 계산에 쓰여 필수. 저장 시 후보 <b>미승인</b> 리셋.</span>
          <span><button class="btn" id="ln-save" style="background:#1b6ec2;color:#fff">💾 저장</button> <button class="btn" id="ln-cancel">닫기</button></span></div>
      </div><datalist id="sv-vdl"></datalist></div>`;};
  // ---------- draw ----------
  const draw=()=>{
    c.innerHTML=`
     <div class="page-title">🧩 조달경로 통합검토 <span style="font-size:12px;color:var(--muted);font-weight:400">상단 내부원가 재료표 · 하단 조달경로 후보(신규등록·상세편집)</span></div>
     <div class="page-sub">상단=<b>품목 BOM관리 '내부원가' 탭 재료표</b>(재료행 클릭=조달대상). 하단=<b>조달경로 후보</b> — <b>➕신규 등록</b>(현행복사/기존복사/빈수동) · <b>현행 더블클릭=상세보기</b> · <b>대안 더블클릭=상세편집</b>. 승인해야 조달프로파일 노출. <code>/api/cost/nae · nx.sourcing_route</code></div>
     <div style="display:flex;gap:14px;align-items:flex-start">
      <div style="flex:0 0 290px">
       <div class="toolbar"><input class="inp" id="sv-q" list="sv-dl" autocomplete="off" value="${esc(st.q)}" placeholder="품번/품명" style="width:180px;min-width:0"><datalist id="sv-dl"></datalist><button class="btn" id="sv-search">🔍</button></div>
       <div class="grid-wrap" style="max-height:calc(100vh - 240px);overflow:auto;background:#fff;border:1px solid var(--line-2,#c9d3e0);border-radius:8px">
        <table class="tbl" style="font-size:12px"><thead><tr><th>품번</th><th>품명</th><th class="center">BOM</th></tr></thead>
        <tbody>${st.searching?spinRow(3):(st.slist.length?st.slist.map(s=>`<tr class="sv-row${st.sel===s.item?' sel':''}" data-i="${esc(s.item)}" style="cursor:pointer"><td><b>${esc(s.item)}</b></td><td class="bcap" style="max-width:130px;overflow:hidden;text-overflow:ellipsis" title="${esc(s.name)}">${esc(s.name||'')}</td><td class="center">${s.has_bom?'<span style="color:#1c7c3a">●</span>':'<span style="color:#ccc">–</span>'}</td></tr>`).join(''):`<tr><td colspan="3" class="empty">품번/품명 검색</td></tr>`)}</tbody></table>
       </div>
      </div>
      <div style="flex:1;min-width:0">
       ${st.sel?`
        <div class="toolbar"><span style="font-weight:700;color:#1c47a0;font-size:16px">${esc(st.sel)}</span> <span style="color:var(--muted)">${esc(st.selNm)}</span> ${st.mat?`<span class="rowcount">재료 ${flatMat().normal.length+flatMat().weldArr.length}종</span>`:''}
          ${!canW?'<span style="color:#c0392b;font-size:12px;margin-left:8px">🔒 수정권한 없음</span>':''}</div>
        ${st.loading?`<div class="grid-wrap" style="padding:20px">${spinRow(1)}</div>`:`<div id="sv-right" style="overflow:auto;max-height:calc(100vh - 205px)">
          <div style="font-weight:700;color:#334;margin:2px 0 4px">① 재료(내부원가 역전개) <span style="font-size:11px;color:#8aa0bd;font-weight:400">(품번·품명·규격·소재·소요량 · 용접봉 종류별 · 행 클릭=조달대상 선택)</span></div>
          <div id="sv-tree" style="overflow-x:auto">${matTbl()}</div>
          <div style="height:14px"></div>
          <div id="sv-routes">${routesPanel()}</div></div>`}`
       :`<div class="empty" style="margin-top:40px">좌측에서 품번을 선택하세요.</div>`}
      </div>
     </div>
     ${st.msg?`<div class="page-sub" style="color:#1c7c3a">${esc(st.msg)}</div>`:''}
     ${newModal()}${detailModal()}${lineModal()}${weldModal()}${nodeProcModal()}
     ${PROC_MODAL_CSS}
     <style>.sv-row.sel{background:#e8f0ff}.sv-row:hover{background:#eef4ff}.sv-mrow:hover{background:#f4f8ff}.sv-mrow.sel{outline:2px solid #1c7c3a;outline-offset:-2px;background:#eafaef}.sv-card:hover{filter:brightness(.985);box-shadow:0 2px 8px rgba(30,45,70,.08)}</style>`;
    const g=id=>c.querySelector(id);
    g('#sv-search').onclick=()=>{st.q=g('#sv-q').value;search();};
    g('#sv-q').oninput=e=>ac(e.target.value);
    g('#sv-q').onkeyup=e=>{if(e.key==='Enter'){st.q=e.target.value;search(true);}};
    g('#sv-q').onchange=e=>{const v=e.target.value.trim();if(v&&st.slist.some(s=>s.item===v))open(v);};
    c.querySelectorAll('.sv-row').forEach(el=>el.onclick=()=>open(el.dataset.i));
    bindTree();bindBottom();
    bindNewModal();bindDetailModal();bindLineModal();bindWeldModal();bindNodeProc();
    fillDL();
  };
  const paintTree=()=>{const box=c.querySelector('#sv-tree');if(box){box.innerHTML=matTbl();bindTree();}};
  const paintRoutes=()=>{const box=c.querySelector('#sv-routes');if(box){box.innerHTML=routesPanel();bindBottom();}};
  const bindTree=()=>{c.querySelectorAll('.sv-mrow').forEach(el=>el.onclick=()=>selectTarget(el.dataset.code,el));};
  const bindBottom=()=>{
    {const b=c.querySelector('.sv-root');if(b)b.onclick=()=>selectTarget(st.sel,null);}
    {const b=c.querySelector('.sv-new');if(b)b.onclick=openNew;}
    c.querySelectorAll('.sv-card').forEach(el=>el.ondblclick=()=>{const b=el.querySelector('.sv-open');openDetail(+el.dataset.rid,b?b.dataset.mode:'view');});
    c.querySelectorAll('.sv-open').forEach(b=>b.onclick=e=>{e.stopPropagation();openDetail(+b.dataset.rid,b.dataset.mode);});
    // ★현행 카드 '수정'(baseline) = 실체화 후 편집 바로 진입
    c.querySelectorAll('.sv-editcur').forEach(b=>b.onclick=async e=>{e.stopPropagation();
      if(!confirm('현행(실사용 BOM)을 수정합니다.\n닫기=되돌리기 · 전체 저장(검증)해야 반영됩니다. 계속?'))return;   // ★매번 확인
      try{const r=await fetch(`${API}/api/sourcing/route/edit_current`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({item_code:st.routeTarget,user:'웹사용자'})});
        const j=await r.json();if(!j.ok){alert('현행 수정 진입 실패: '+(j.detail||''));return;}
        await loadRoutes();openDetail(j.route_id,'edit',false);}catch(x){alert('오류: '+x.message);}});
    c.querySelectorAll('.sv-appr').forEach(b=>b.onclick=e=>{e.stopPropagation();approve(+b.dataset.rid,b.dataset.on==='1');});
    c.querySelectorAll('.sv-rdel').forEach(b=>b.onclick=e=>{e.stopPropagation();delRoute(+b.dataset.rid);});
  };
  const bindNewModal=()=>{if(!st.newForm)return;const g=id=>c.querySelector(id);
    g('#nr-x').onclick=g('#nr-cancel').onclick=()=>{st.newForm=null;draw();};
    g('#nr-create').onclick=doNewCreate;
    c.querySelectorAll('input[name=nrm]').forEach(rd=>rd.onchange=()=>{st.newForm.method=rd.value;draw();});
    c.querySelectorAll('.nf').forEach(el=>{el.oninput=el.onchange=()=>{st.newForm[el.dataset.k]=el.type==='checkbox'?el.checked:el.value;if(el.dataset.k==='vendor_code')vSearch(el.value);};});};
  const bindDetailModal=()=>{if(!st.detail)return;const R=routeById(st.detail.route_id);if(!R)return;const g=id=>c.querySelector(id);
    {const x=g('#dt-x');if(x)x.onclick=()=>closeDetail();}                 // ✕(항상) — fresh는 dt-close 없음(취소/등록) → 개별 널가드(체이닝 금지)
    {const b=g('#dt-close');if(b)b.onclick=()=>closeDetail();}
    {const b=g('#dt-cancel');if(b)b.onclick=()=>cancelDraft();}          // ✖ 취소 = 롤백+닫기
    {const b=g('#dt-register');if(b)b.onclick=()=>registerWithGate(st.detail.route_id);}   // ✔ 등록 = 게이트검증(공정/구성≠BOM이면 차단) + SUB중복 + 확정 + fresh해제
    {const b=g('#dt-hsave2');if(b)b.onclick=()=>saveWithGate(st.detail.route_id);}  // 💾 저장 = 저장전 재검증(공정/구성≠BOM이면 차단) + 헤더 + SUB중복 + 확정
    {const b=g('#dt-newfromcur');if(b)b.onclick=()=>{st.detail=null;openNew('cur');};}
    {const b=g('#dt-editcur');if(b)b.onclick=async()=>{   // ★현행(R01) 직접 수정 = baseline을 편집용 route로 실체화 후 대안과 동일 편집
      if(!confirm('현행(R01)을 직접 수정합니다.\n실사용 BOM을 편집용 route로 실체화합니다 — 이후 실사용 BOM이 바뀌어도 자동반영 안 됩니다([BOM 다시 불러오기]로 리셋 가능). 계속?'))return;
      try{const r=await fetch(`${API}/api/sourcing/route/edit_current`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({item_code:st.routeTarget,user:'웹사용자'})});
        const j=await r.json();if(!j.ok){alert('현행 수정 진입 실패: '+(j.detail||''));return;}
        st.detail=null;await loadRoutes();openDetail(j.route_id,'edit',false);}catch(e){alert('오류: '+e.message);}};}
    {const b=g('#dt-resetcur');if(b)b.onclick=async()=>{   // ★현행 편집 초기화 = 실사용 BOM에서 라인 재도출
      if(!confirm('실사용 BOM에서 라인을 다시 불러옵니다.\n현재 편집한 SUB 구성/공정 배치가 모두 초기화됩니다. 계속?'))return;
      try{const r=await fetch(`${API}/api/sourcing/route/edit_current`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({item_code:st.routeTarget,user:'웹사용자',reset:1})});
        const j=await r.json();if(!j.ok){alert('리셋 실패: '+(j.detail||''));return;}
        st.msg='현행 BOM에서 다시 불러옴 (라인 '+j.lines+')';await loadRoutes();openDetail(j.route_id,'edit',false);}catch(e){alert('오류: '+e.message);}};}
    {const b=g('#dt-hsave');if(b)b.onclick=()=>saveHdr(false);}
    {const b=g('#dt-ladd');if(b)b.onclick=()=>{st.lineForm={route_id:st.detail.route_id,gubun:'',is_rawmat:0};draw();};}
    c.querySelectorAll('.df').forEach(el=>{el.oninput=el.onchange=()=>{st.detail.hdr[el.dataset.k]=el.type==='checkbox'?el.checked:el.value;if(el.dataset.k==='vendor_code')vSearch(el.value);};});
    c.querySelectorAll('.dl-e').forEach(b=>b.onclick=()=>{const l=(R.lines||[]).find(y=>y.line_id==b.dataset.lid);st.lineForm=Object.assign({route_id:st.detail.route_id},l);draw();});
    c.querySelectorAll('.dl-d').forEach(b=>b.onclick=()=>delLine(+b.dataset.lid));
    {const b=c.querySelector('.pmodal-bg .sv-appr');if(b)b.onclick=()=>approve(+b.dataset.rid,b.dataset.on==='1');}
    // ---- ★재설계 SUB 재구성·공정배치 binds (좌 풀 → 우 트리 드래그·노드[수정]→공정팝업·전체저장 검증) ----
    const rid=st.detail.route_id;
    {const b=g('#sp-open');if(b)b.onclick=()=>loadRD(rid);}
    const reloadPanel=async()=>{st.rdProc=null;await loadRD(rid);await dissolveEmptySubs(rid);};
    // ★부품추가 버튼 제거 — 조달후보는 BASE BOM 부품만 재편성(BOM 외 부품 금지). 라인 직접수정만 유지.
    c.querySelectorAll('.sp-ledit').forEach(b=>b.onclick=e=>{e.stopPropagation();const l=(R.lines||[]).find(y=>y.line_id==b.dataset.lid);if(l){st.lineForm=Object.assign({route_id:rid},l);draw();}});
    // ★드래그&드롭 = 컨테이너 이벤트 위임(재렌더에도 유지·property할당=멱등 → 재드롭/반복 SUB생성 안정).
    //   드롭대상: 기존 SUB노드(부품 추가)·"새 SUB로 묶기"존(SUB 생성)만. ASSY 레벨1(data-sub=0)=무반응. 하이라이트=.dz-hi.
    const _dzClear=()=>c.querySelectorAll('.dz-hi').forEach(x=>x.classList.remove('dz-hi'));
    const _dzTarget=e=>{const z=e.target.closest&&e.target.closest('.sp-newsub,.sp-drop[data-sub]');if(!z)return null;
      if(z.classList.contains('sp-newsub'))return z;              // 새 SUB 생성 존
      return (+z.dataset.sub>0)?z:null;};                          // SUB(추가)만 / ASSY 레벨1(0)=무반응
    c.ondragstart=e=>{const el=e.target.closest&&e.target.closest('.sp-drag');if(!el)return;
      st._dragLid=el.dataset.lid;try{e.dataTransfer.setData('text/lid',el.dataset.lid);}catch(_){}e.dataTransfer.effectAllowed='move';};
    c.ondragend=()=>{st._dragLid=null;_dzClear();};
    c.ondragover=e=>{const z=_dzTarget(e);if(!z)return;e.preventDefault();e.dataTransfer.dropEffect='move';if(!z.classList.contains('dz-hi')){_dzClear();z.classList.add('dz-hi');}};
    c.ondragleave=e=>{const z=e.target.closest&&e.target.closest('.sp-newsub,.sp-drop[data-sub]');if(z)z.classList.remove('dz-hi');};
    c.ondrop=async e=>{const z=_dzTarget(e);const lid=+(st._dragLid||0);st._dragLid=null;_dzClear();if(!z)return;e.preventDefault();if(!lid)return;
      try{
        if(z.classList.contains('sp-newsub')){const psub=+z.dataset.parentsub||0;
          const r=await fetch(`${API}/api/sourcing/sub/create`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({route_id:rid,line_ids:[lid],base_child:st.routeTarget,suffix:'',name:'SUB '+st.routeTarget,gubun:'외주(유상사급)',parent_sub:psub})});
          const j=await r.json();if(j.ok){st.msg='신규 SUB '+j.sub_item+(psub>0?' (중첩)':'')+' 생성';await reloadPanel();}else alert('SUB 생성 실패: '+(j.detail||''));
        }else{
          const r=await fetch(`${API}/api/sourcing/part/assign`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({route_id:rid,sub_line:+z.dataset.sub,line_ids:[lid]})});
          if((await r.json()).ok)await reloadPanel();else alert('이동 실패');
        }
      }catch(err){alert('드롭 오류: '+err.message);}};
    // 노드 [수정] → 관경별 용접 + 공정별 작업ST 팝업(노드 스코프: 레벨0=ASSY값 / 신규SUB=빈값)
    c.querySelectorAll('.sp-nedit').forEach(b=>b.onclick=e=>{e.stopPropagation();openNodeProc(b.dataset.node,b.dataset.sub==='0');});
    // [해체] SUB 노드 → 하위부품 ASSY 복귀 · 비종속 공정/용접 ASSY 이관(공수합 보존, 백엔드 sub/dissolve). 해체 후 패널 갱신.
    c.querySelectorAll('.sp-ndissolve').forEach(b=>b.onclick=async e=>{e.stopPropagation();
      if(!confirm('이 SUB를 해체합니다.\n하위부품은 ASSY(레벨0)로 복귀하고, SUB의 비종속 공정/용접은 ASSY로 이관되어 공수합이 보존됩니다. 계속?'))return;
      try{const r=await fetch(`${API}/api/sourcing/sub/dissolve`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({route_id:rid,sub_line:+b.dataset.sub})});
        const j=await r.json();if(j.ok){st.msg=`SUB 해체 ✔ 부품 ${j.freed} 복귀 · 공정 이관 ${j.moved_proc} · 용접 이관 ${j.moved_weld}`;await reloadPanel();}
        else alert('해체 실패: '+(j.detail||JSON.stringify(j)));}catch(err){alert('해체 오류: '+err.message);}});
    // 🔍 BOM 검증 = 공수합=BASE·부품수=BASE·구성 검증만(저장 안 함). 저장은 하단 [저장](saveWithGate).
    {const b=g('#sp-validate');if(b)b.onclick=()=>validateRoute(rid);}
    // ---- #4 업체 매핑(조달프로파일) binds ----
    {const b=g('#rp-open');if(b)b.onclick=()=>loadRP(rid);}
    c.querySelectorAll('.rp-f').forEach(el=>{el.oninput=el.onchange=()=>{const i=+el.dataset.i,k=el.dataset.k,row=(st.rp&&st.rp.rows)?st.rp.rows[i]:null;if(!row)return;
      row[k]=el.type==='checkbox'?el.checked:el.value;if(k==='vendor_code')vSearch2(el.value);
      const act=st.rp.rows.filter(r=>!r._delete&&r.is_active&&r.alloc_ratio!=null&&r.alloc_ratio!==''&&!r.is_internal);
      const sum=Math.round(act.reduce((a,r)=>a+(+r.alloc_ratio||0),0)*100)/100,ok=act.length===0||Math.abs(sum-100)<0.01;
      const gt=g('#rp-gate');if(gt){gt.textContent=`활성 배분합 ${nfq(sum)}% ${ok?'✔':'✖ 100% 아님(저장거부)'}`;gt.style.color=ok?'#1c7c3a':'#c0392b';}};});
    {const b=g('#rp-add');if(b)b.onclick=()=>{st.rp.rows.push({profile_id:0,vendor_code:'',vendor_name:'',alloc_ratio:null,apply_from:'',apply_to:'',is_active:true,lme_flag:false,is_internal:false});draw();};}
    c.querySelectorAll('.rp-del').forEach(el=>el.onclick=()=>{const i=+el.dataset.i,row=st.rp.rows[i];if(!row)return;if(row.profile_id)row._delete=true;else st.rp.rows.splice(i,1);draw();});
    {const b=g('#rp-save');if(b)b.onclick=async()=>{try{const r=await fetch(`${API}/api/sourcing/profile/save`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({route_id:rid,rows:st.rp.rows})});
      const j=await r.json();if(j.ok){alert(`업체 매핑 저장 ✔ (추가 ${j.ins} · 수정 ${j.upd} · 삭제 ${j.del})`);await loadRP(rid);}
      else if(j.gate==='NOT_APPROVED')alert('승인된 후보만 업체 매핑 가능합니다. 먼저 승인하세요.');
      else if(j.gate==='ALLOC'||j.errors)alert('배분 검증 실패:\n'+((j.errors||['활성 배분합이 100%가 아닙니다']).join('\n')));
      else alert('저장 실패: '+(j.detail||JSON.stringify(j)));}catch(e){alert('오류: '+e.message);}};}};
  const bindLineModal=()=>{if(!st.lineForm)return;const g=id=>c.querySelector(id);
    g('#ln-x').onclick=g('#ln-cancel').onclick=()=>{st.lineForm=null;draw();};
    g('#ln-save').onclick=saveLine;   // ★신규채번 버튼 제거(정규화 역행 방지) — SUB 생성은 "새 SUB로 묶기" _S{nn} 정본으로 일원화
    c.querySelectorAll('.lf').forEach(el=>{el.oninput=el.onchange=()=>{const v=el.type==='checkbox'?el.checked:el.value;st.lineForm[el.dataset.k]=v;if(el.dataset.k==='is_rawmat')draw();if(el.dataset.k==='vendor_code')vSearch(el.value);};});};
  // ---------- #3 용접 팝업 binds ----------
  const bindWeldModal=()=>{if(!st.weldEdit)return;const w=st.weldEdit,g=id=>c.querySelector(id);
    g('#wm-x').onclick=g('#wm-cancel').onclick=()=>{st.weldEdit=null;draw();};
    {const b=g('#wm-add');if(b)b.onclick=()=>{w.rows.push({weld_item:'RAC30599301-1',pipe_diam:'',weld_qty:''});draw();};}
    c.querySelectorAll('.wm-f').forEach(el=>{el.oninput=el.onchange=()=>{const i=+el.dataset.i,k=el.dataset.k;if(!w.rows[i])return;w.rows[i][k]=el.value;draw();};});
    c.querySelectorAll('.wm-del').forEach(el=>el.onclick=()=>{w.rows.splice(+el.dataset.i,1);draw();});
    {const b=g('#wm-apply');if(b)b.onclick=async()=>{const rid=st.detail.route_id;
      const rows=w.rows.filter(r=>+r.pipe_diam>0&&+r.weld_qty>0);
      try{const r=await fetch(`${API}/api/sourcing/weld/save`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({route_id:rid,node_item:w.node,loss_factor:1.5,rows})});
        const j=await r.json();if(!j.ok){alert('용접점 저장 실패: '+(j.detail||JSON.stringify(j)));return;}
        st.weldEdit=null;await loadRD(rid);  // welds 배지 갱신 + rdProc 재빌드(저장 procs 기준)
        // 용접ST → 해당 노드 [용접]공정 셀 주입(재빌드 이후) · 공수합=BASE는 proc/save 게이트가 최종보증
        (st.rdProc[w.node]=st.rdProc[w.node]||{})[w.wproc]=j.total_st;draw();
        alert(`용접점 저장 ✔ 용접봉 소요량 ${q4(j.total_use_qty)} · 용접ST ${nfq(j.total_st)} → [${_pmap[w.wproc]||w.wproc}]공정 적용됨. 공수합=BASE 확인 후 '공정 배치 저장'하세요.`);
      }catch(e){alert('오류: '+e.message);}};}};
  // ---------- ★노드 스코프 공정 팝업 열기/저장 + 전체 저장(검증 3종) ----------
  // 노드 팝업 열기 = naeProcD와 동일 구조(own 가공 + assy 조립)로 로드. 전체 공정 카탈로그는 /api/cost/proc/get 재사용(ASSY 기준 1회 캐시).
  const openNodeProc=async(node,isAssy)=>{await loadWeldDiams();const rd=st.rd||{};
    // 전체 공정 카탈로그(가공 own + 조립 assy) — 내부원가 팝업과 동일 소스. uph/cg는 ASSY 라우팅 참조.
    if(!st.procCat||st.procCatFor!==st.routeTarget){
      let cat=[],ownV={},asmV={};
      try{const r=await fetch(`${API}/api/cost/proc/get?node=${encodeURIComponent(st.routeTarget)}`);const j=await r.json();
        cat=j.catalog||[];(j.own_procs||[]).forEach(p=>ownV[p.proc_code]=p);
        const cr=(j.carriers||[])[0];((cr&&cr.procs)||[]).forEach(p=>asmV[p.proc_code]=p);
      }catch(e){}
      st.procCat={cat,ownV,asmV};st.procCatFor=st.routeTarget;}
    const {cat,ownV,asmV}=st.procCat;
    const ownCat=cat.filter(p=>!p.is_assy), asmCat=cat.filter(p=>p.is_assy);
    // 프리필: 그 노드 저장값(sourcing_route_proc). 레벨0 ASSY & 미저장 → BASE 조립 시드. 신규 SUB → 빈값.
    const saved={};(rd.procs||[]).forEach(p=>{if(p.node_item===node)saved[p.proc_code]=+p.work_qty||0;});
    const hasSaved=Object.keys(saved).length>0;
    const seed={};if(isAssy&&!hasSaved){(rd.asm_procs||[]).forEach(a=>{if(+a.wq>0)seed[a.proc_code]=+a.wq;});}
    const prefill=hasSaved?saved:(isAssy?seed:{});
    // own(가공)/assy(조립) = naeProcD.own + carriers[0].rows 대응. wq=프리필, uph/cg=ASSY 라우팅 참조.
    const own=ownCat.map(p=>{const v=ownV[p.proc_code]||{};return {proc_code:p.proc_code,name:p.name,group:p.group,work_qty:+prefill[p.proc_code]||0,prod_uph:+v.prod_uph||0,calc_gubun:v.calc_gubun||'3'};});
    const assy=asmCat.map(p=>{const v=asmV[p.proc_code]||{};return {proc_code:p.proc_code,name:p.name,group:p.group,work_qty:+prefill[p.proc_code]||0,prod_uph:+v.prod_uph||0,calc_gubun:v.calc_gubun||'3'};});
    // 관경별 용접(weldCounts) = 그 노드 저장 용접점(pipe_diam→count)
    const welds=(rd.welds||[]).filter(w=>w.node_item===node);
    const weldCounts={};welds.forEach(w=>{if(w.pipe_diam)weldCounts[(+w.pipe_diam).toFixed(2)]=(+w.weld_qty||0);});
    const weldItem=(welds[0]&&welds[0].weld_item)||'RAC30599301-1';
    const weldTypes=[...new Set(welds.map(w=>w.weld_item).filter(Boolean))];
    // info(상단) 계산용: 이 노드 절삭 자동귀속 + 전역 기타합
    const RACX=l=>String(l.child_item||'').toUpperCase().startsWith('RAC')&&!String(l.child_name||'').includes('용접링');   // 용접봉 제외·용접링 유지
    const lines=(rd.lines||[]).filter(l=>!RACX(l)),parts=lines.filter(l=>l.node_kind!=='SUB'),subs=lines.filter(l=>l.node_kind==='SUB');
    let nodeParts;if(isAssy){nodeParts=parts.filter(p=>!p.parent_line);}else{const s=subs.find(x=>(x.sub_item||x.child_item)===node);nodeParts=s?parts.filter(p=>p.parent_line===s.line_id):[];}
    const partCut=rd.part_cut||{},cutAgg={};
    nodeParts.forEach(p=>{(partCut[p.child_item]||[]).forEach(x=>{const a=cutAgg[x.proc_code]||(cutAgg[x.proc_code]={name:x.name,wq:0});a.wq+=+x.wq||0;});});
    const cutRows=Object.keys(cutAgg).map(k=>({proc_code:k,name:cutAgg[k].name,wq:Math.round(cutAgg[k].wq*100)/100}));
    let cutAll=0;Object.values(partCut).forEach(arr=>arr.forEach(x=>cutAll+=+x.wq||0));
    let procOther=0;(rd.procs||[]).forEach(p=>{if(p.node_item!==node)procOther+=+p.work_qty||0;});
    const thisCut=cutRows.reduce((a,x)=>a+x.wq,0);
    const otherTotal=Math.round((cutAll-thisCut+procOther)*100)/100;   // 전역합 = otherTotal + (이 노드 절삭 + 조립 라이브)
    st.np={node,isAssy,label:(isAssy?'ASSY '+node+' (레벨0)':'SUB '+node),
      own,assy,weldCounts,weldItem,weldTypes,loss:1.5,
      cutRows,cutSum:Math.round(thisCut*100)/100,otherTotal,base:rd.base_gongsu||0};
    draw();};
  const saveNodeProc=async()=>{const np=st.np;if(!np||!st.rd)return;const rid=st.rd.route_id;
    // 관경별 용접(재료) — weldCounts → 행. loss=1.5(내부원가 팝업과 동일).
    const wrows=Object.keys(np.weldCounts||{}).filter(k=>+np.weldCounts[k]>0).map(k=>({weld_item:np.weldItem,pipe_diam:+k,weld_qty:+np.weldCounts[k]}));
    // 공정(가공비) — own + assy 전 컬럼 work_qty>0. 용접ST(가공비)는 용접공정 컬럼(작업ST)에 입력/시드된 값(내부원가 팝업과 동일 모델).
    const procs=[];
    (np.own||[]).forEach(p=>{if(+p.work_qty>0)procs.push({proc_code:p.proc_code,work_qty:+p.work_qty,prod_uph:+p.prod_uph||0,calc_gubun:p.calc_gubun||'3'});});
    (np.assy||[]).forEach(p=>{if(+p.work_qty>0)procs.push({proc_code:p.proc_code,work_qty:+p.work_qty,prod_uph:+p.prod_uph||0,calc_gubun:p.calc_gubun||'3'});});
    try{
      await fetch(`${API}/api/sourcing/weld/save`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({route_id:rid,node_item:np.node,loss_factor:+np.loss||1.5,rows:wrows})});
      const r=await fetch(`${API}/api/sourcing/proc/node_save`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({route_id:rid,node_item:np.node,procs})});
      const j=await r.json();if(!j.ok){alert('공정 저장 실패: '+(j.detail||JSON.stringify(j)));return;}
      st.np=null;st.msg=`공정 저장 ✔ ${np.label} 노드공수 ${nfq(j.node_gongsu)}`;await loadRD(rid);
    }catch(e){alert('저장 오류: '+e.message);}};
  // 노드 팝업 바인딩 = 공유 PROC_MODAL_BIND. own/assy에 write-back(sec='own'/'c0'). 용접횟수→weldCounts.
  const bindNodeProc=()=>{if(!st.np)return;const np=st.np;
    const rowsOf=sec=>sec==='own'?np.own:np.assy;
    PROC_MODAL_BIND(c,{
      onClose:()=>{st.np=null;draw();},
      onSave:saveNodeProc,
      onProcInput:(sec,i,v)=>{const a=rowsOf(sec);if(a&&a[i])a[i].work_qty=+v||0;},   // 입력중 값만(포커스 유지)
      onProcUph:(sec,i,v)=>{const a=rowsOf(sec);if(a&&a[i])a[i].prod_uph=+v||0;},     // ★UPH 편집 write-back
      onProcCommit:()=>draw(),                                                          // 확정(blur)시 상단 info 갱신
      onWeldCount:(d,v)=>{const val=+v||0;if(val>0)np.weldCounts[d]=val;else delete np.weldCounts[d];draw();},
      onWeldType:(v)=>{np.weldItem=v;},
    });};
  // 🔍 BOM 검증 = 검증만(commit:0 → 롤백, 저장 안 함). 공수합=BASE·부품수=BASE·구성 확인. SUB 중복검사/재사용은 하지 않음(저장 시에만).
  const validateRoute=async(rid)=>{const item=st.routeTarget;
    try{
      const r=await fetch(`${API}/api/sourcing/route/finalize`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({route_id:rid,item_code:item,ymd:'260630',commit:0})});
      const j=await r.json();
      if(j.ok){alert(`✅ BOM 검증 통과 (저장 안 됨 — 반영하려면 하단 [저장])\n공수합 ${nfq(j.cand_gongsu)} = BASE ${nfq(j.base_gongsu)} (절삭 ${nfq(j.cut_sum)} + 조립 ${nfq(j.proc_sum)})\n부품수 ${j.route_part_count}/${j.base_part_count} 일치 ✔`);}
      else{alert('❌ BOM 검증 실패 — 공정/구성이 BOM과 다릅니다:\n\n'+((j.errors||[]).join('\n')||`공수합 ${nfq(j.cand_gongsu)} ≠ BASE ${nfq(j.base_gongsu)}`)+'\n\n(이 상태로는 [저장]되지 않습니다.)');}
    }catch(e){alert('검증 오류: '+e.message);}};
  // 💾 저장 = ★저장 직전 재검증 → 공정/구성이 BOM과 다르면 저장 차단. 통과 시 헤더저장 + SUB중복 재사용확인 + 확정(commit:1).
  const saveWithGate=async(rid)=>{const item=st.routeTarget;
    try{
      // (1) 저장 전 재검증(commit:0=검증만)
      const v=await(await fetch(`${API}/api/sourcing/route/finalize`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({route_id:rid,item_code:item,ymd:'260630',commit:0})})).json();
      if(!v.ok){alert('❌ 저장할 수 없습니다 — 공정/구성이 BOM과 다릅니다:\n\n'+((v.errors||[]).join('\n')||`공수합 ${nfq(v.cand_gongsu)} ≠ BASE ${nfq(v.base_gongsu)}`)+'\n\n[BOM 검증]으로 확인 후 수정하세요.');return;}
      // (2) 헤더(경로명/구분/유효일자/비고) 저장
      const okh=await saveHdr(false);if(okh===false)return;
      // (3) SUB 중복 재사용 확인(선택) — 저장 시에만 물어봄
      const sm=await(await fetch(`${API}/api/sourcing/sub/match?route_id=${rid}`)).json();
      const reuse={};
      for(const m of (sm.matches||[])){
        if(confirm(`동일한 표준 SUB가 존재합니다(${m.match_code}).\n현재 SUB ${m.sub_item}(부품 ${m.member_count}종) 대신 그 표준 SUB를 사용하시겠습니까?\n(취소 = 현재 SUB 그대로 저장)`)) reuse[m.sub_line]=m.match_code;
      }
      // (4) 확정 커밋(commit:1 — 서버가 게이트 재검증 후 통과 시에만 저장)
      const r=await fetch(`${API}/api/sourcing/route/finalize`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({route_id:rid,item_code:item,ymd:'260630',reuse_map:reuse,commit:1})});
      const j=await r.json();
      if(j.ok){alert(`✅ 저장 완료\n공수합 ${nfq(j.cand_gongsu)} = BASE ${nfq(j.base_gongsu)} (절삭 ${nfq(j.cut_sum)} + 조립 ${nfq(j.proc_sum)})\n부품수 ${j.route_part_count}/${j.base_part_count}${(j.reused&&j.reused.length)?'\n재사용 SUB: '+j.reused.map(x=>x.old+'→'+x.new).join(', '):''}\n(신규 SUB 정본 채번은 승인 시 수행)`);await loadRD(rid);await loadRoutes();}
      else{alert('❌ 저장 거부(검증 실패):\n'+((j.errors||[]).join('\n')||JSON.stringify(j)));}
    }catch(e){alert('저장 오류: '+e.message);}};
  // ✔ 등록(신규 후보 확정) = 저장(saveWithGate)과 동일 작동: 재검증(공정/구성≠BOM이면 차단) + 헤더커밋(fresh해제) + SUB중복 + 확정.
  const registerWithGate=async(rid)=>{const item=st.routeTarget;
    try{
      // (1) 등록 전 재검증(commit:0)
      const v=await(await fetch(`${API}/api/sourcing/route/finalize`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({route_id:rid,item_code:item,ymd:'260630',commit:0})})).json();
      if(!v.ok){alert('❌ 등록할 수 없습니다 — 공정/구성이 BOM과 다릅니다:\n\n'+((v.errors||[]).join('\n')||`공수합 ${nfq(v.cand_gongsu)} ≠ BASE ${nfq(v.base_gongsu)}`)+'\n\n[BOM 검증]으로 확인 후 수정하세요.');return;}
      // (2) SUB 중복 재사용 확인(선택)
      const sm=await(await fetch(`${API}/api/sourcing/sub/match?route_id=${rid}`)).json();
      const reuse={};
      for(const m of (sm.matches||[])){
        if(confirm(`동일한 표준 SUB가 존재합니다(${m.match_code}).\n현재 SUB ${m.sub_item}(부품 ${m.member_count}종) 대신 그 표준 SUB를 사용하시겠습니까?\n(취소 = 현재 SUB 그대로 등록)`)) reuse[m.sub_line]=m.match_code;
      }
      // (3) 확정 커밋(commit:1 — 서버 게이트 재검증 후 통과 시에만)
      const j=await(await fetch(`${API}/api/sourcing/route/finalize`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({route_id:rid,item_code:item,ymd:'260630',reuse_map:reuse,commit:1})})).json();
      if(!j.ok){alert('❌ 등록 거부(검증 실패):\n'+((j.errors||[]).join('\n')||JSON.stringify(j)));return;}
      // (4) 헤더 커밋 + fresh 해제(닫기=삭제 방지 → 정식 후보 확정)
      const okh=await saveHdr(true);if(okh===false)return;
      alert(`✅ 등록 완료\n공수합 ${nfq(j.cand_gongsu)} = BASE ${nfq(j.base_gongsu)} (절삭 ${nfq(j.cut_sum)} + 조립 ${nfq(j.proc_sum)})\n부품수 ${j.route_part_count}/${j.base_part_count}${(j.reused&&j.reused.length)?'\n재사용 SUB: '+j.reused.map(x=>x.old+'→'+x.new).join(', '):''}\n(승인해야 조달프로파일에 노출됩니다)`);
      await loadRoutes();
    }catch(e){alert('등록 오류: '+e.message);}};
  // ---------- 대상 선택(부분갱신) ----------
  const selectTarget=async(code,el)=>{
    if(!code||code===st.routeTarget)return;
    await discardFreshSilent();   // 대상 전환 전 미커밋 드래프트 롤백(고아 방지)
    st.routeTarget=code;st.routeTargetNm=nameOf(code);st.detail=st.newForm=st.lineForm=null;
    c.querySelectorAll('.sv-mrow.sel').forEach(x=>x.classList.remove('sel'));if(el)el.classList.add('sel');
    st.rload=true;paintRoutes();await loadRoutes();st.rload=false;paintTree();paintRoutes();};
  // ---------- 신규 등록 ----------
  const nextRouteNo=()=>{if(st.nextNo)return st.nextNo;  // ★서버 단조증가 high-water(삭제해도 재사용안함) 미러
    const stored=st.routes.filter(r=>+r.route_id>0);return (stored.length?Math.max(...stored.map(r=>+r.route_no||0)):1)+1;};  // 폴백
  const openNew=(preMethod)=>{const baseline=st.routes.find(r=>r.baseline);
    const nn=nextRouteNo(),autoLabel=`${st.routeTarget}_R${String(nn).padStart(2,'0')}`;
    st.newForm={target:st.routeTarget,name:autoLabel,autoLabel,nextNo:nn,method:preMethod||'cur',source_route_id:(altRoutes()[0]||{}).route_id||0,
      gubun:'',vendor_code:'',apply_from:'',current_flag:false,
      lgAvail:!!(baseline&&(baseline.lines||[]).length===0)};draw();};
  const doNewCreate=async()=>{const f=st.newForm;
    if(!f.name)f.name=f.autoLabel||`${st.routeTarget}_R${String(nextRouteNo()).padStart(2,'0')}`;  // 후보명 자동(수동입력 제거)
    try{
      if(f.method==='cur'||f.method==='copy'||f.method==='base'){
        const body={item_code:st.routeTarget,user:'웹사용자'};
        if(f.method==='base') body.source='base';                       // BASE BOM 평면 seed
        else{ body.source_route_id=f.method==='copy'?(+f.source_route_id||0):0; body.copy_children=0; }   // ★하위품번 신규채번 제거(1품번1BOM 원칙 — 대안은 조달경로/공정만 다름, 품번 접미사 복제 금지)
        const r=await fetch(`${API}/api/sourcing/route/copy`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
        const j=await r.json();if(!j.ok){alert('생성 실패: '+(j.detail||JSON.stringify(j)));return;}
        await afterCreate(j.route_id,f.name,`${st.routeTarget}_R${String(j.route_no).padStart(2,'0')} 생성 (라인 ${j.lines})`);
      } else if(f.method==='blank'){
        const r=await fetch(`${API}/api/sourcing/route/save`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({item_code:st.routeTarget,route_name:f.name,gubun:f.gubun,vendor_code:f.vendor_code,apply_from:f.apply_from,current_flag:f.current_flag?1:0,user:'웹사용자'})});
        const j=await r.json();if(!j.ok){alert('생성 실패:\n'+(j.errors?j.errors.join('\n'):(j.detail||JSON.stringify(j))));return;}
        await afterCreate(j.route_id,null,'빈 후보 생성 — 상세에서 라인을 추가하세요');
      } else if(f.method==='lg'){
        await createFromLg(f);
      }
    }catch(e){alert('생성 오류: '+e);}};
  const afterCreate=async(rid,rename,msg)=>{
    // 복사본 채번명 대신 사용자가 입력한 후보명을 상세 편집 헤더에 프리필(저장 시 route/save로 확정)
    st.newForm=null;st.msg='📋 '+msg+' — 미커밋(드래프트). [등록]해야 확정, 닫기=등록 취소.';
    await loadRoutes();openDetail(rid,'edit',true);   // fresh=true(미커밋 드래프트)
    if(rename&&st.detail){st.detail.hdr.route_name=rename;draw();}};
  const createFromLg=async(f)=>{
    const r=await fetch(`${API}/api/esticost/expand?item=${encodeURIComponent(st.routeTarget)}`);const j=await r.json();
    const rows=(j.rows||[]).filter(x=>x.parent===st.routeTarget);
    if(!rows.length){alert('LG BOM(nx.lg_bom)에 해당 모델 직하위가 없습니다.');return;}
    const cr=await fetch(`${API}/api/sourcing/route/save`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({item_code:st.routeTarget,route_name:f.name,gubun:'자체',vendor_code:'',apply_from:(f.apply_from||''),current_flag:0,user:'웹사용자'})});
    const cj=await cr.json();if(!cj.ok){alert('생성 실패:\n'+(cj.errors?cj.errors.join('\n'):JSON.stringify(cj)));return;}
    const rid=cj.route_id;let n=0;
    for(const x of rows){const g=(x.sagub_flag?'사급':(x.make_type==='1'?'제작':'매입'));
      const lr=await fetch(`${API}/api/sourcing/line/save`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({route_id:rid,child_item:x.item_code,child_name:x.item_name||x.item_code,qty:(+x.unit_qty||1),gubun:g,vendor_code:x.in_cust||'',is_rawmat:x.metal_gubun?1:0,diam:(+x.diam||0),thick:(+x.thick||0),len_val:(+x.length||0),material:x.metal_gubun||'',user:'웹사용자'})});
      if((await lr.json()).ok)n++;}
    st.newForm=null;st.msg=`🔀 LG BOM 시딩 후보 생성 (라인 ${n}) — 미커밋. [등록]해야 확정.`;await loadRoutes();openDetail(rid,'edit',true);};
  // ---------- 상세 ----------
  const today=()=>{const d=new Date();return d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0')+'-'+String(d.getDate()).padStart(2,'0');};
  const openDetail=(rid,mode,fresh)=>{const R=routeById(rid);if(!R)return;
    st.detail={route_id:rid,mode:(R.baseline?'view':mode||'edit'),fresh:!!fresh,
      hdr:{route_name:R.route_name||'',gubun:R.gubun||'',apply_from:R.apply_from||today(),note:R.note||''}};  // 유효일자 default=오늘·공급처/현행 제거
    st.newForm=null;st.rd=null;draw();
    if(!R.baseline && st.detail.mode==='edit'){
      if(!fresh){try{fetch(`${API}/api/sourcing/route/edit_begin`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({route_id:rid})});}catch(e){}}  // ★편집 세션 시작 스냅샷(닫기=되돌리기용)
      loadRD(rid);   // 편집모드=좌/우 패널 기본 펼침(버튼 클릭 불필요)
    }
  };
  // 닫기(X/닫기): 신규 미커밋 드래프트면 "등록 취소?" · ★편집 세션이면 닫기=되돌리기(세션 스냅샷 복원). 저장했으면 스냅 없어 그대로.
  const closeDetail=async()=>{
    if(st.detail&&st.detail.fresh){
      if(confirm('등록을 취소하시겠습니까?\n확인 시 이 후보는 등록되지 않습니다(삭제·번호 재사용).')) await cancelDraft();
      return;   // 계속 = 모달 유지
    }
    if(st.detail&&st.detail.mode==='edit'&&+st.detail.route_id>0){   // ★닫기=되돌리기(저장 안 했으면 편집 전으로 복원)
      try{const r=await fetch(`${API}/api/sourcing/route/edit_cancel`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({route_id:st.detail.route_id})});
        const j=await r.json();if(j.reverted){st.detail=null;await loadRoutes();draw();return;}}catch(e){}
    }
    st.detail=null;draw();};
  // ✖ 취소 = 미커밋 드래프트 롤백(route 삭제)+닫기 → 고아 없음·다음 번호 재사용
  const cancelDraft=async()=>{const rid=st.detail?st.detail.route_id:0;
    if(rid>0){try{await fetch(`${API}/api/sourcing/route/delete`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({route_id:rid})});}catch(e){}}
    st.detail=null;st.msg='등록 취소 — 후보가 등록되지 않았습니다(번호 재사용).';await loadRoutes();draw();};
  // 드래프트 방치 방지: 대상 전환/신규열기 전에 미커밋 드래프트 조용히 롤백
  const discardFreshSilent=async()=>{if(st.detail&&st.detail.fresh){const rid=st.detail.route_id;st.detail=null;
    try{await fetch(`${API}/api/sourcing/route/delete`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({route_id:rid})});}catch(e){}}};
  // ---------- actions ----------
  const saveHdr=async(commit)=>{const h=st.detail.hdr;
    try{const r=await fetch(`${API}/api/sourcing/route/save`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(Object.assign({item_code:st.routeTarget,route_id:st.detail.route_id,user:'웹사용자'},h))});
      const j=await r.json();
      if(j.ok){if(commit&&st.detail)st.detail.fresh=false;st.msg=commit?'✅ 후보 등록 완료 — 승인하면 조달프로파일에 노출됩니다':'✅ 헤더 저장 (개발 미승인 리셋)';await loadRoutes();draw();return true;}
      alert('저장 실패:\n'+(j.errors?j.errors.join('\n'):(j.detail||JSON.stringify(j))));return false;}catch(e){alert('저장 오류: '+e);return false;}};
  const saveLine=async()=>{const f=st.lineForm;
    try{const r=await fetch(`${API}/api/sourcing/line/save`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(Object.assign({user:'웹사용자'},f))});
      const j=await r.json();if(j.ok){st.msg='✅ 라인 저장 (후보 미승인 리셋)';st.lineForm=null;await loadRoutes();if(st.rd&&st.detail&&st.rd.route_id===st.detail.route_id)await loadRD(st.rd.route_id);else draw();}
      else alert('저장 실패:\n'+(j.errors?j.errors.join('\n'):(j.detail||JSON.stringify(j))));}catch(e){alert('저장 오류: '+e);}};
  const newChild=async()=>{const f=st.lineForm;const base=(f.child_item||'').trim();
    if(!base){alert('원본 하위품번을 먼저 입력하세요');return;}
    const suffix=(prompt('신규 채번 접미사',(f.child_item||'').match(/-S\d+$/)?'-S2':'-S1')||'').trim();if(!suffix)return;
    try{const r=await fetch(`${API}/api/sourcing/child/new`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({base_child:base,suffix,name:f.child_name})});
      const j=await r.json();if(j.ok){st.lineForm.child_item=j.code;if(!f.child_name)st.lineForm.child_name=j.name;st.msg=(j.existed?'기존':'신규')+' 하위품번 채번 → '+j.code;draw();}
      else alert('채번 실패: '+(j.detail||''));}catch(e){alert('채번 오류: '+e);}};
  const approve=async(rid,on)=>{try{const r=await fetch(`${API}/api/sourcing/route/approve`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({route_id:rid,approve:on?1:0,user:'개발'})});
      const j=await r.json();if(j.ok){const mt=(j.minted&&j.minted.length)?' · 신규 SUB 채번 '+j.minted.map(x=>x.old+'→'+x.new).join(', '):'';st.msg=(on?'✔ 승인 — 조달프로파일 후보로 노출됩니다':'승인 취소 — 프로파일에서 숨김')+mt;await loadRoutes();draw();}else alert('승인 실패');}catch(e){alert('승인 오류: '+e);}};
  const delRoute=async(rid)=>{if(!confirm('이 대안 후보(헤더+라인)를 삭제하시겠습니까?'))return;
    try{const r=await fetch(`${API}/api/sourcing/route/delete`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({route_id:rid})});
      const j=await r.json();
      if(j.ok){st.msg='🗑 후보 삭제 완료';if(st.detail&&st.detail.route_id===rid)st.detail=null;await loadRoutes();draw();}
      else if(j.guard==='IN_USE'){alert('⚠ 삭제 불가 — '+(j.msg||'조달 프로파일에서 사용 중입니다. 업체 매핑을 먼저 해제하세요.'));}
      else if(j.guard==='CURRENT'){alert('⚠ '+(j.msg||'현행 후보는 삭제할 수 없습니다.'));}
      else alert('삭제 실패: '+(j.detail||j.msg||''));}catch(e){alert('삭제 오류: '+e);}};
  const delLine=async(lid)=>{if(!confirm('이 라인을 삭제하시겠습니까?'))return;
    try{const r=await fetch(`${API}/api/sourcing/line/delete`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({line_id:lid,user:'웹사용자'})});
      const j=await r.json();if(j.ok){st.msg='🗑 라인 삭제 (후보 미승인 리셋)';await loadRoutes();draw();}else alert('삭제 실패: '+(j.detail||''));}catch(e){alert('삭제 오류: '+e);}};
  const init=async()=>{st.q='';await search();if(st.slist.length)open(st.slist[0].item);};
  init();
};

SCREEN.itemmaster=(host)=>{
  const API=API_BASE;
  let opts={};
  const st={rows:[],cnt:0,q:'',status:'사용',nature:'',prod_group:'',form:null,sel:new Set(),msg:''};
  // [key,label,type,optkey] · type: req/text/num/date/sel/chk/ro
  // ★3층 원칙: 품목마스터는 "고정 속성"만. 조달·거래·운영 필드는 분리(백엔드 _IM_CORE/_IM_BIZ/_SUB와 일치).
  const F=[
    ['item_code','품번','req'],['item_name','품명','req'],
    ['item_spec','규격','text'],
    ['sgroup','품목유형 판정(소분류)','sel','sgroup'],
    ['pipe_kind','품목형태','sel','pipe_kind'],['metal_gubun','재질','sel','metal'],
    ['unit','단위','sel','unit'],['status','사용상태','sel','status'],
    ['diam','외경','num'],['thick','두께','num'],['length','길이','num'],['net_weight','중량','num'],
    ['item_pipe_id','내경(자동)','ro'],['item_status','품목상태','text'],
    // ── 서브(item_sub) ──
    ['insp_flag','검사구분','sel','insp_flag'],['rack_no','RACK(적치)','text'],
    ['prod_step_memo','공정메모','text'],['remarks','비고','text'],
  ];
  const REQ=new Set(['item_code','item_name','sgroup','unit']);   // 하드필수(전 그룹 공통). 성격별 소프트권장은 저장 후 경고.
  const softField=()=>{const nat=st.form&&st.form.nature; return (nat&&opts.nature_soft&&opts.nature_soft[nat])||[];};
  const load=async()=>{
    const qs=new URLSearchParams({q:st.q,status:st.status,nature:st.nature,prod_group:st.prod_group,limit:500});
    try{const r=await fetch(`${API}/api/itemmaster/list?${qs}`);const j=await r.json();st.rows=j.rows||[];st.cnt=j.cnt||0;
      if(j.natures)opts.nature_f=j.natures; if(j.prod_groups)opts.prod_groups=j.prod_groups;}
    catch(e){st.msg='백엔드 연결 실패';st.rows=[];}
    render();
  };
  const fld=(f)=>{
    const [k,label,type,ok]=f, v=st.form[k]??'';
    if(type==='sel'){const os=opts[ok]||[];return `<select class="inp" data-fk="${k}" style="min-width:90px;width:auto;max-width:230px"><option value="">선택</option>${os.map(o=>`<option value="${esc(o.code)}" ${String(o.code)===String(v)?'selected':''}>${esc(o.nm)}</option>`).join('')}</select>`;}
    if(type==='chk')return `<input type="checkbox" data-fk="${k}" ${(v===1||v==='1'||v===true)?'checked':''} style="width:18px;height:18px">`;
    if(type==='ro')return `<input class="inp" data-fk="${k}" value="${esc(v)}" readonly style="width:90px;background:#eef2f7" title="외경-두께×2 자동계산">`;
    return `<input class="inp" data-fk="${k}" value="${esc(v)}" ${type==='num'?'inputmode="decimal" style="width:90px"':'style="width:160px"'}>`;
  };
  const render=()=>{
    const editing=st.form!==null;
    const ed=(typeof PERM!=='undefined')?PERM.canEdit('itemmaster'):true;   // 수정권한 게이트(규칙#16)
    host.innerHTML=`
     <div class="page-title">📇 품목마스터 관리 <span style="font-size:12px;color:var(--muted);font-weight:400">nx.item(+서브·밸브) · BOM 무결성(삭제가드·품번변경 연쇄)</span></div>
     <div class="page-sub">레거시 <code>w_pr_master_010</code>/PR_M_ITEM 재설계. 코드→이름 드롭다운·내경 자동·생산구분4→LG사급 자동. <b>품번 변경 시 BOM 모/자 연쇄 갱신 + 이력</b>.</div>
     <div class="toolbar" style="flex-wrap:wrap;gap:4px">
       <label class="tl">검색</label><input class="inp" id="im-q" value="${esc(st.q)}" placeholder="품번/품명" style="width:150px">
       <label class="tl">제품군</label><select class="inp" id="im-pg" style="width:auto"><option value="">전체</option>${(opts.prod_groups||[]).map(o=>`<option value="${esc(o.code)}" ${st.prod_group===o.code?'selected':''}>${esc(o.nm)}</option>`).join('')}</select>
       <label class="tl">품목유형</label><select class="inp" id="im-nat"><option value="">전체</option>${(opts.nature_f||opts.nature||[]).map(o=>`<option value="${esc(o.code)}" ${st.nature===o.code?'selected':''}>${esc(o.nm)}</option>`).join('')}</select>
       <label class="tl">상태</label><select class="inp" id="im-st"><option value="사용" ${st.status==='사용'?'selected':''}>사용</option><option value="휴면" ${st.status==='휴면'?'selected':''}>휴면</option><option value="중지" ${st.status==='중지'?'selected':''}>중지</option><option value="" ${st.status===''?'selected':''}>전체</option></select>
       <button class="btn" id="im-search">🔍 조회</button>
       ${ed?`<button class="btn" id="im-new" style="background:#1c7c3a;color:#fff">➕ 신규</button>
       <button class="btn" id="im-del">🗑 선택삭제</button>`:`<span style="color:#c0392b;font-size:12px">🔒 수정권한 없음 (${esc((typeof PERM!=='undefined')?PERM.label():'')})</span>`}
       <div class="spacer"></div>
       <span class="rowcount">${won(st.cnt)}건${st.cnt>=500?' (상한·검색으로 좁히세요)':''}</span>
     </div>
     ${st.msg?`<div class="page-sub" style="color:${st.msg.includes('실패')?'#c0392b':'#1c7c3a'};font-weight:600">${esc(st.msg)}</div>`:''}
     ${editing?`<div class="wr-modal" style="position:fixed;inset:0;z-index:110;background:rgba(20,30,50,.38);display:flex;align-items:flex-start;justify-content:center;overflow:auto;padding:24px 10px">
       <div style="background:#fff;border-radius:10px;box-shadow:0 22px 64px rgba(0,0,0,.32);width:720px;max-width:97vw">
         <div style="display:flex;justify-content:space-between;align-items:center;padding:11px 16px;background:#1c47a0;color:#fff;border-radius:10px 10px 0 0">
           <b>품목마스터 ${st.form._edit?'— 수정 ('+esc(st.form._orig_code||'')+')':'— 신규'}</b><span id="im-x" style="cursor:pointer;font-size:17px">✕</span></div>
         <div style="padding:12px 16px;max-height:calc(100vh - 170px);overflow:auto">
           <div style="font-size:11.5px;margin-bottom:8px;padding:6px 9px;background:#f2f6fc;border-radius:6px">
             ${st.form.prod_group?`제품군: <b style="color:#1c47a0">${esc(st.form.prod_group)}</b> › <b>${esc(st.form.prod_line||'')}</b> <span style="color:var(--muted)">(품번 접두어 자동)</span>&nbsp;·&nbsp;`:''}품목유형: <b style="color:#1c47a0">${st.form.nature?esc(st.form.nature):'저장 시 자동판정'}</b>
             ${softField().length?`&nbsp;·&nbsp;<span style="color:#b8860b">권장항목(노랑 ※)</span>: ${softField().map(k=>esc((opts.field_label&&opts.field_label[k])||k)).join(', ')} — 비어도 저장되나 경고`:''}
             ${st.form.active===0?`&nbsp;·&nbsp;<span style="color:#c0392b">▲ 정리대상 후보(BOM/공정 미연결)</span>`:''}
           </div>
           ${st.form._edit?`<div style="font-size:11px;color:#b8860b;margin-bottom:8px">※ 품번을 바꾸면 <b>품번변경</b>으로 처리 — BOM 모/자코드 연쇄 갱신 + 이력 기록됩니다.</div>`:''}
           <table style="border-collapse:collapse;width:100%"><tbody>${(()=>{let h='';const SF=softField();for(let i=0;i<F.length;i+=2){const a=F[i],b=F[i+1];
             const cell=f=>f?`<td style="padding:5px 8px 5px 0;white-space:nowrap;color:#33507d;font-weight:600;font-size:12px;text-align:right;width:92px">${f[1]}${REQ.has(f[0])?'<span style="color:#c0392b">*</span>':SF.includes(f[0])?'<span style="color:#b8860b" title="권장">※</span>':''}</td><td style="padding:4px 8px 4px 0">${fld(f)}</td>`:'<td></td><td></td>';
             h+=`<tr>${cell(a)}${cell(b)}</tr>`;}return h;})()}</tbody></table>
         </div>
         <div style="padding:11px 16px;border-top:1px solid #e2e8f2;display:flex;justify-content:space-between;align-items:center">
           <span style="font-size:11px"><span style="color:#c0392b">* 하드필수(품번·품명·소분류·단위)</span> · <span style="color:#b8860b">※ 성격별 권장(비어도 저장·경고만)</span></span>
           <span><button class="btn" id="im-save" style="background:#1b6ec2;color:#fff">💾 저장</button> <button class="btn" id="im-cancel">닫기</button></span></div>
       </div></div>`:''}
     <div class="grid-wrap" style="max-height:calc(100vh - 300px);overflow:auto;background:#fff;border:1px solid var(--line-2,#c9d3e0);border-radius:8px">
      <table class="tbl fit" style="font-size:11px"><thead><tr><th style="width:26px"></th>
        <th>품번</th><th>품명</th><th>제품군</th><th>제품계열</th><th>품목유형</th><th>규격</th><th>단위</th><th>재질</th><th>검사</th><th class="center">상태</th><th style="width:46px">작업</th></tr></thead>
      <tbody>${st.rows.length?st.rows.map((r,i)=>`<tr>
        <td class="center">${ed?`<input type="checkbox" class="im-chk" data-code="${esc(r.item_code)}" ${st.sel.has(r.item_code)?'checked':''}>`:''}</td>
        <td><b>${esc(r.item_code)}</b></td><td class="cap" title="${esc(r.item_name)}" style="max-width:150px;overflow:hidden;text-overflow:ellipsis">${esc(r.item_name)}</td>
        <td style="white-space:nowrap;font-weight:600;color:#1c47a0">${esc(r.prod_group||'')}</td>
        <td style="white-space:nowrap">${esc(r.prod_line||'')}</td>
        <td style="white-space:nowrap"><span style="font-size:10px;color:#33507d">${esc((r.nature||'').replace(/^\d+\./,''))}</span>${r.active===0?' <span title="정리대상 후보(BOM/공정 미연결)" style="color:#c0392b;font-weight:700">▲</span>':''}</td>
        <td class="cap" title="${esc(r.item_spec)}" style="max-width:120px;overflow:hidden;text-overflow:ellipsis">${esc(r.item_spec)}</td>
        <td>${esc(r.unit)}</td><td>${esc(r.metal)}</td>
        <td>${esc(r.insp_flag)}</td>
        <td class="center">${(r.status==='중지')?'<span class="bdg off">중지</span>':(r.status==='휴면')?'<span class="bdg" style="background:#f0ad4e;color:#fff">휴면</span>':'<span class="bdg ok">사용</span>'}</td>
        <td class="center">${ed?`<button class="btn im-edit" data-idx="${i}" style="padding:1px 6px;font-size:10px">수정</button>`:''}</td></tr>`).join(''):`<tr><td colspan="12" class="empty">조회 결과 없음${ed?' (➕신규로 등록)':''}</td></tr>`}</tbody></table></div>`;
    const g=id=>host.querySelector(id);
    g('#im-search').onclick=()=>{st.q=g('#im-q').value;st.status=g('#im-st').value;st.nature=g('#im-nat').value;st.prod_group=g('#im-pg').value;load();};
    g('#im-q').onkeyup=e=>{if(e.key==='Enter')g('#im-search').click();};
    if(ed){
      g('#im-new').onclick=()=>{st.form={_edit:0,item_code:'',item_name:'',item_type:'제품',status:'사용',unit:'EA',make_type:'',lgroup:'',sgroup:''};render();};
      g('#im-del').onclick=()=>del([...st.sel]);
      host.querySelectorAll('.im-chk').forEach(ch=>ch.onclick=()=>{const cd=ch.dataset.code;ch.checked?st.sel.add(cd):st.sel.delete(cd);});
      host.querySelectorAll('.im-edit').forEach(b=>b.onclick=async()=>{const code=st.rows[+b.dataset.idx].item_code;
        try{const j=await(await fetch(`${API}/api/itemmaster/get?item=${encodeURIComponent(code)}`)).json();
          st.form=Object.assign({_edit:1,_orig_code:code},j.item||{},j.sub||{});}
        catch(e){alert('불러오기 실패: '+e);return;}render();});
    }
    attachResizers(host);
    if(editing){
      g('#im-cancel').onclick=g('#im-x').onclick=()=>{st.form=null;render();};
      g('#im-save').onclick=save;
      host.querySelectorAll('[data-fk]').forEach(el=>{
        const k=el.dataset.fk;
        if(el.type==='checkbox')el.onchange=()=>{st.form[k]=el.checked?1:0;};
        else el.oninput=()=>{st.form[k]=el.value;
          if(k==='diam'||k==='thick'){const d=parseFloat(st.form.diam),t=parseFloat(st.form.thick);
            if(!isNaN(d)&&!isNaN(t)){st.form.item_pipe_id=Math.round((d-t*2)*10000)/10000;const pe=host.querySelector('[data-fk="item_pipe_id"]');if(pe)pe.value=st.form.item_pipe_id;}}
        };
      });
    }
  };
  const save=async()=>{
    const f=st.form;
    for(const k of REQ){if(!String(f[k]||'').trim()){alert(({item_code:'품번',item_name:'품명',lgroup:'대분류',sgroup:'소분류',unit:'단위'})[k]+'은(는) 필수입니다');return;}}
    try{const r=await fetch(`${API}/api/itemmaster/save`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...f,user:'웹사용자'})});
      const j=await r.json();
      if(r.ok&&j.ok){st.msg=(j.renamed?'✅ 품번변경 완료 → ':(j.mode==='insert'?'✅ 등록완료 ':'✅ 수정완료 '))+j.item_code+(j.nature?' ['+j.nature+']':'')+((j.warnings&&j.warnings.length)?'  ⚠ 권장항목 미입력: '+j.warnings.join(', '):'');st.form=null;await load();}
      else alert('저장 실패: '+(j.detail||JSON.stringify(j)));}
    catch(e){alert('저장 오류: '+e);}
  };
  const del=async(codes)=>{if(!codes.length){alert('삭제할 행을 체크하세요');return;}
    if(!confirm(codes.length+'건을 삭제하시겠습니까? (BOM에 사용중이면 거부됩니다)'))return;
    try{const r=await fetch(`${API}/api/itemmaster/delete`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({codes})});
      const j=await r.json();
      if(j.ok){st.msg='🗑 '+j.deleted+'건 삭제완료';st.sel.clear();await load();}
      else alert('삭제 불가 (BOM 무결성):\n'+(j.errors||[]).join('\n'));}
    catch(e){alert('삭제 오류: '+e);}
  };
  (async()=>{try{opts=await (await fetch(`${API}/api/itemmaster/opts`)).json();}catch(e){}load();})();
};

SCREEN.rawmat=(host)=>{
  const API=API_BASE;
  const canW=(typeof PERM!=='undefined')?PERM.canEdit('rawmat'):true;
  const st={rows:[],cnt:0,q:'',material:'',materials:[],loading:false,
            sel:null,detail:null,dLoading:false,edit:{},msg:'',editMode:false,tab:'spec',
            L:{months:[],ym:'',header:null,rows:[],gagong:[],editable:false,hedit:{},gform:null,msg:'',loading:false}};
  const won=v=>(v==null||v==='')?'<span style="color:#c9d1dc">-</span>':Number(v).toLocaleString('ko-KR',{maximumFractionDigits:2});
  const nf=v=>Number(v||0).toLocaleString('ko-KR',{maximumFractionDigits:2});
  const won1=v=>(v==null||v==='')?'<span style="color:#c9d1dc">-</span>':Number(v).toLocaleString('ko-KR',{minimumFractionDigits:1,maximumFractionDigits:1});
  const r1=v=>(v==null||v==='')?'':(Math.round(Number(v)*10)/10);
  const fmtYm=y=>{y=''+(y||'');return y.length>=6?`${y.slice(0,4)}-${y.slice(4,6)}`:y;};
  // ===================== 탭1: 원소재 스펙(기존) =====================
  const load=async()=>{st.loading=true;draw();
    try{const r=await fetch(`${API}/api/rawmat/list?q=${encodeURIComponent(st.q)}&material=${encodeURIComponent(st.material)}`);
      const j=await r.json();st.rows=j.rows||[];st.cnt=j.cnt||0;if(j.materials)st.materials=j.materials;}
    catch(e){st.rows=[];}
    st.loading=false;draw();};
  const loadDetail=async(rid)=>{st.sel=rid;st.detail=null;st.dLoading=true;st.edit={};st.msg='';st.editMode=false;renderDetail();
    try{const r=await fetch(`${API}/api/rawmat/prices?raw_id=${encodeURIComponent(rid)}`);st.detail=await r.json();}
    catch(e){st.detail={rows:[]};}
    st.dLoading=false;renderDetail();};
  const sagubVal=r=>{const e=st.edit[r.ym];return (e!==undefined&&e!=='')?e:(r.lg_sagub!=null?r.lg_sagub:0);};
  const save=async()=>{
    if(!st.detail||!st.detail.rows.length){alert('저장할 월이 없습니다.');return;}
    const rows=st.detail.rows.map(r=>({ym:r.ym,price:+sagubVal(r)||0}));
    try{const r=await fetch(`${API}/api/rawmat/lg_sagub/save`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({raw_id:st.sel,rows})});
      const j=await r.json();if(!j.ok)throw new Error(j.error||'save');st.msg='✔ LG사급가 저장 완료';loadDetail(st.sel);}
    catch(e){st.msg='저장 실패: '+e.message;renderDetail();}};
  const addMonth=()=>{const el=host.querySelector('#rm-addym');const ym=(el?el.value:'').replace(/[^0-9]/g,'').slice(0,6);
    if(ym.length!==6){alert('YYYYMM 6자리로 입력하세요(예: 202607).');return;}
    if(!st.detail)st.detail={rows:[]};
    if(st.detail.rows.some(r=>r.ym===ym)){alert('이미 있는 월입니다.');return;}
    st.detail.rows.push({ym,lg_recog:null,lg_sagub:0,sise:null,partner:null});
    st.detail.rows.sort((a,b)=>b.ym.localeCompare(a.ym));st.edit[ym]=st.edit[ym]||0;renderDetail();};
  const detailPanel=()=>{
    if(!st.sel)return `<div style="padding:24px;color:#8aa0bd;font-size:13px">← 좌측에서 원소재를 선택하면 월별 단가가 표시됩니다.</div>`;
    if(st.dLoading)return `<table class="tbl"><tbody>${spinRow(5)}</tbody></table>`;
    const d=st.detail||{rows:[]}, rows=d.rows||[], ed=st.editMode;
    const head=`<div style="font-weight:700;margin:2px 0 6px;color:#1c47a0">월별 단가 <span style="font-weight:400;color:#8aa0bd;font-size:12px">${esc(d.material||'')} ${esc(d.spec||'')} ${d.part_no?'· '+esc(d.part_no):''}</span></div>
      <div class="toolbar" style="margin:0 0 6px 0">
        ${ed?`<label class="tl">월 추가</label><input class="inp" id="rm-addym" placeholder="YYYYMM" style="width:96px"><button class="btn ghost" id="rm-addm">＋ 추가</button>`:''}
        <div class="spacer"></div>${st.msg?`<span style="color:${st.msg.includes('실패')?'#c0392b':'#1c7c3a'};font-size:12px;margin-right:8px">${esc(st.msg)}</span>`:''}
        ${ed?`<button class="btn" id="rm-save" style="background:#1c7c3a;color:#fff">💾 저장</button><button class="btn ghost" id="rm-cancel">취소</button>`
            :(canW?`<button class="btn" id="rm-edit">✏ 수정</button>`:'')}</div>`;
    const body=rows.length?rows.map(r=>`<tr><td class="center"><b>${esc(fmtYm(r.ym))}</b></td>
        <td class="num">${won(r.lg_recog)}</td>
        <td class="num ${ed?'':'edcol'}">${ed?`<input class="rm-sg" data-ym="${esc(r.ym)}" type="number" step="any" value="${sagubVal(r)}" style="width:96px;text-align:right;font-weight:700;color:#1c7c3a">`:`<b style="color:#1c7c3a">${nf(sagubVal(r))}</b>`}</td>
        <td class="num">${won(r.sise)}</td><td class="num">${won(r.partner)}</td></tr>`).join('')
      :`<tr><td colspan="5" class="empty">${ed?'"월 추가"로 새 월의 LG사급가를 입력하세요.':'이 원소재의 월별 단가가 없습니다.'+(canW?' ✏ 수정으로 입력하세요.':'')}</td></tr>`;
    return head+`<div class="grid-wrap" style="max-height:calc(100vh - 330px);overflow:auto;background:#fff;border:1px solid var(--line-2,#c9d3e0);border-radius:8px">
      <table class="tbl fit" style="font-size:12px"><thead><tr><th class="center">적용월</th><th class="num">LG인증가</th><th class="num">LG사급가</th><th class="num">현물가</th><th class="num">협력사 사급가</th></tr></thead>
      <tbody>${body}</tbody></table></div>`;
  };
  const renderDetail=()=>{
    const el=host.querySelector('#rm-detail');if(!el)return;
    el.innerHTML=detailPanel();
    el.querySelectorAll('.rm-sg').forEach(inp=>inp.oninput=()=>{st.edit[inp.dataset.ym]=inp.value;});
    const sv=el.querySelector('#rm-save');if(sv)sv.onclick=save;
    const am=el.querySelector('#rm-addm');if(am)am.onclick=addMonth;
    const eb=el.querySelector('#rm-edit');if(eb)eb.onclick=()=>{st.editMode=true;st.msg='';renderDetail();};
    const cb=el.querySelector('#rm-cancel');if(cb)cb.onclick=()=>{st.editMode=false;st.edit={};st.msg='';renderDetail();};
  };
  const specBody=()=>`
     <div class="page-sub">거래처 실입고(2026) 기반 정규화 규격. 좌측 스펙 클릭 → 우측에 <b>월별 단가</b>(LG인증가·<b>LG사급가</b>·현물가·협력사 사급가). LG사급가는 이 화면에서 월별 입력(미입력=0).</div>
     <div class="toolbar" style="flex-wrap:wrap;gap:4px">
       <input class="inp" id="rm-q" value="${esc(st.q)}" placeholder="규격/파트넘버 입력" style="width:170px">
       <label class="tl">재질</label><select class="sel" id="rm-mat"><option value="">전체</option>${st.materials.map(o=>`<option value="${esc(o.code)}" ${st.material===o.code?'selected':''}>${esc(o.nm)}</option>`).join('')}</select>
       <button class="btn" id="rm-go">🔍 조회</button>
       <div class="spacer"></div><span class="rowcount">${won(st.cnt)}종</span>
     </div>
     <div style="display:flex;gap:10px;align-items:flex-start">
       <div style="flex:0 0 56%;min-width:0">
         <div class="grid-wrap" style="max-height:calc(100vh - 270px);overflow:auto;background:#fff;border:1px solid var(--line-2,#c9d3e0);border-radius:8px">
          <table class="tbl fit" id="rm-mtbl" style="font-size:11px"><thead><tr>
            <th>재질</th><th class="num">외경</th><th class="num">두께</th><th>조질</th><th>파트넘버</th><th class="num">2026입고KG</th><th class="num">품번수</th><th>공급처</th></tr></thead>
          <tbody>${st.loading?spinRow(8):(st.rows.length?st.rows.map(r=>`<tr class="rm-row ${st.sel===r.raw_id?'sel':''}" data-rid="${esc(r.raw_id)}" style="cursor:pointer">
            <td style="font-weight:600;color:#1c47a0">${esc(r.material)}</td><td class="num">${esc(r.outer_diam)}</td><td class="num">${esc(r.thickness)}</td>
            <td>${esc(r.temper)||'<span style="color:#c9d1dc">-</span>'}</td><td style="font-size:10px">${esc(r.part_no)}</td>
            <td class="num">${won(Math.round(r.y2026_kg))}</td><td class="num">${r.codes_cnt}</td>
            <td class="cap" title="${esc(r.vendors)}" style="max-width:160px;overflow:hidden;text-overflow:ellipsis;font-size:10px">${esc(r.vendors)}</td></tr>`).join(''):`<tr><td colspan="8" class="empty">조회 결과 없음</td></tr>`)}</tbody></table></div>
       </div>
       <div style="flex:1;min-width:0" id="rm-detail">${detailPanel()}</div>
     </div>`;
  // ===================== 탭2: LG전자 LME인정가 =====================
  const HF=[['cu_lme','Cu 적용 LME(선물)'],['brass_lme','황동 적용 LME(현물)'],['cable_lme','Cable 적용 LME'],
    ['fx_now','적용환율(당월)'],['fx_prev','전월환율'],['premium','직관 프리미엄'],['surcharge','직관 할증']];
  const loadLmeMonths=async()=>{
    try{const r=await fetch(`${API}/api/lglme/months`);const j=await r.json();st.L.months=j.rows||[];
      if(!st.L.ym&&st.L.months.length)st.L.ym=st.L.months[0].apply_ym;}catch(e){st.L.months=[];}};
  const loadLme=async(ym)=>{st.L.ym=ym;st.L.loading=true;st.L.gform=null;drawLme();
    try{const r=await fetch(`${API}/api/lglme/table?ym=${encodeURIComponent(ym)}`);const j=await r.json();
      st.L.header=j.header;st.L.editable=!!j.editable;st.L.rows=j.rows||[];st.L.hedit=j.header?Object.assign({},j.header):{};}
    catch(e){st.L.rows=[];st.L.header=null;}
    if(st.L.editable){try{const g=await fetch(`${API}/api/lglme/gagong?ym=${encodeURIComponent(ym)}`);st.L.gagong=(await g.json()).rows||[];}catch(e){st.L.gagong=[];}}
    st.L.loading=false;drawLme();};
  const hv=k=>{const e=st.L.hedit;return (e&&e[k]!=null&&e[k]!=='')?e[k]:(st.L.header&&st.L.header[k]!=null?st.L.header[k]:'');};
  const saveHeaderRecompute=async()=>{
    const p=Object.assign({apply_ym:st.L.ym,user:'web'},st.L.hedit);
    try{const r=await fetch(`${API}/api/lglme/header/save`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(p)});
      const j=await r.json();if(!j.ok){alert('헤더 저장 실패:\n'+(j.errors?j.errors.join('\n'):JSON.stringify(j)));return;}
      const rc=await fetch(`${API}/api/lglme/recompute`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({ym:st.L.ym})});
      const rj=await rc.json();st.L.msg=rj.ok?`✔ 저장·재계산 완료 (${rj.updated}행)`:('재계산 실패: '+(rj.errors?rj.errors.join(','):''));
      await loadLme(st.L.ym);}catch(e){alert('오류: '+e);}};
  const recompute=async()=>{try{const rc=await fetch(`${API}/api/lglme/recompute`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({ym:st.L.ym})});
    const rj=await rc.json();st.L.msg=rj.ok?`♻ 재계산 완료 (${rj.updated}행)`:('실패: '+(rj.errors?rj.errors.join(','):''));await loadLme(st.L.ym);}catch(e){alert('오류: '+e);}};
  const copyMonth=async()=>{const to=(prompt('신규 적용월(YYYYMM) — 전월('+st.L.ym+') 복사 후 LME/환율/국가단가 갱신',(''))||'').replace(/[^0-9]/g,'').slice(0,6);
    if(to.length!==6)return;
    try{const r=await fetch(`${API}/api/lglme/copy`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({from_ym:st.L.ym,to_ym:to,user:'web'})});
      const j=await r.json();if(!j.ok){alert('복사 실패: '+(j.detail||JSON.stringify(j)));return;}
      st.L.msg='📋 '+to+' 생성('+j.rows+'행) — LME/환율 갱신 후 저장·재계산';await loadLmeMonths();await loadLme(to);}catch(e){alert('복사 오류: '+e);}};
  const openGagong=(row)=>{
    const g=st.L.gagong.find(x=>x.gubun===row.gubun&&Math.abs((x.diam||0)-(row.diam||0))<1e-6&&Math.abs((x.thick||0)-(row.thick||0))<1e-6);
    st.L.gform=g?Object.assign({},g):{gubun:row.gubun,diam:row.diam,thick:row.thick,vn_gagong:0,vn_prem:0,vn_mul:0,vn_naeryuk:0,cn_gagong:0,cn_prem:0,cn_mul:0,cn_naeryuk:0,duty_vn:0,duty_cn:0.016,mix_cn:0.3,mix_vn:0.7};
    drawLme();};
  const saveGagong=async()=>{const f=st.L.gform;
    try{const r=await fetch(`${API}/api/lglme/gagong/save`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(Object.assign({apply_ym:st.L.ym},f))});
      const j=await r.json();if(!j.ok){alert('저장 실패');return;}
      st.L.gform=null;await recompute();}catch(e){alert('오류: '+e);}};
  const GF=[['vn_gagong','베트남 가공비'],['vn_prem','베트남 프리미엄'],['vn_mul','베트남 물류비'],['vn_naeryuk','베트남 내륙'],
    ['cn_gagong','중국 가공비'],['cn_prem','중국 프리미엄'],['cn_mul','중국 물류비'],['cn_naeryuk','중국 내륙'],
    ['duty_vn','베트남 관세율'],['duty_cn','중국 관세율'],['mix_cn','중국 믹스비율'],['mix_vn','베트남 믹스비율']];
  const gagongModal=()=>{const f=st.L.gform;if(!f)return '';
    return `<div class="wr-modal" style="position:fixed;inset:0;z-index:120;background:rgba(20,30,50,.4);display:flex;align-items:flex-start;justify-content:center;overflow:auto;padding:24px 10px">
      <div style="background:#fff;border-radius:10px;width:560px;max-width:96vw;box-shadow:0 22px 64px rgba(0,0,0,.32)">
        <div style="display:flex;justify-content:space-between;align-items:center;padding:11px 16px;background:#1c47a0;color:#fff;border-radius:10px 10px 0 0"><b>가공비 국가믹스 — ${esc(f.gubun)} Ø${esc(f.diam)}×${esc(f.thick)}</b><span id="lg-gx" style="cursor:pointer;font-size:17px">✕</span></div>
        <div style="padding:14px 16px;display:grid;grid-template-columns:auto 1fr auto 1fr;gap:8px 10px;align-items:center;font-size:12px">
          ${GF.map(([k,lb])=>`<label style="color:#33507d;font-weight:600;text-align:right">${lb}</label><input class="inp lgf" type="number" step="any" data-k="${k}" value="${f[k]!=null?f[k]:''}">`).join('')}
        </div>
        <div style="padding:11px 16px;border-top:1px solid #e2e8f2;display:flex;justify-content:space-between;align-items:center">
          <span style="color:#8aa0bd;font-size:11px">국가Price(USD)=가공비+프리미엄+물류+관세((LME+가공비+물류)×관세율)+내륙 · 가공비원화=(중국P×믹스+베트남P×믹스)×환율/1000. 저장 시 자동 재계산.</span>
          <span><button class="btn" id="lg-gsave" style="background:#1b6ec2;color:#fff">💾 저장·재계산</button> <button class="btn" id="lg-gcancel">닫기</button></span></div>
      </div></div>`;};
  const lmeBody=()=>{
    const L=st.L, ed=canW&&L.editable;
    const monsel=`<label class="tl">적용월</label><select class="sel" id="lg-ym">${L.months.map(m=>`<option value="${m.apply_ym}" ${L.ym===m.apply_ym?'selected':''}>${fmtYm(m.apply_ym)}${m.editable?' (편집)':''} · ${m.n_row}행</option>`).join('')}</select>`;
    const hdr=L.editable?`<div style="border:1px solid #cfe0ff;border-radius:8px;padding:10px 12px;margin:6px 0;background:#f4f8ff">
        <div style="font-weight:700;color:#1c47a0;margin-bottom:6px">적용 LME · 환율 · 직관 파라미터 <span style="font-size:11px;color:#8aa0bd;font-weight:400">(입력 후 [저장·재계산] → 재료비/가공비/원재료가 갱신)</span></div>
        <div style="display:grid;grid-template-columns:repeat(4,max-content 110px);gap:7px 14px;align-items:center;font-size:12px;justify-content:start">
          ${HF.map(([k,lb])=>`<label style="color:#33507d;font-weight:600;text-align:right;white-space:nowrap">${lb}${(k==='cu_lme'||k==='fx_now')?'<span style=color:#c0392b>*</span>':''}</label><input class="inp lgh" type="number" step="any" data-k="${k}" value="${r1(hv(k))}" ${ed?'':'readonly'} style="width:110px" title="표시=소수1자리·저장=정밀">`).join('')}
        </div>
        ${ed?`<div style="margin-top:8px;text-align:right"><button class="btn" id="lg-hsave" style="background:#1c7c3a;color:#fff">💾 저장·재계산</button> <button class="btn ghost" id="lg-recalc">♻ 재계산</button></div>`:''}
      </div>`
      :`<div class="page-sub" style="color:#8aa0bd;margin:6px 0">과거 시계열(값 조회 전용) — 편집은 현행월(header 보유)에서. 헤더 입력값이 없어 재료비/가공비는 엑셀 적재값입니다.</div>`;
    return `<div class="page-sub">LG전자 <b>Cost Table(직거래)</b> — 재료비=<b>LME×환율÷1000</b>(직관&P/C=(LME+152)×1.05×환율÷1000) · 가공비=<b>국가믹스(중국30%+베트남70%)</b> · 원재료가=재료비+가공비. 원천 <code>26.06월_동 LME 인정가.xlsx</code></div>
     <div class="toolbar" style="flex-wrap:wrap;gap:4px">${monsel}
       ${canW&&L.editable?`<button class="btn" id="lg-copy">📋 전월 복사로 신규월</button>`:''}
       <div class="spacer"></div>${L.msg?`<span style="color:${L.msg.includes('실패')?'#c0392b':'#1c7c3a'};font-size:12px">${esc(L.msg)}</span>`:''}<span class="rowcount">${won(L.rows.length)}행</span></div>
     ${hdr}
     <div class="grid-wrap" style="max-height:calc(100vh - 360px);overflow:auto;background:#fff;border:1px solid var(--line-2,#c9d3e0);border-radius:8px">
      ${L.loading?spinRow(1):`<table class="tbl fit" style="font-size:11.5px"><thead><tr>
        <th style="width:78px">구분</th><th class="num" style="width:52px">외경</th><th class="num" style="width:46px">두께</th><th style="width:96px">P/No</th><th class="num" style="width:92px">재료비</th><th class="num" style="width:88px">가공비</th><th class="num" style="width:96px">원재료가</th>${ed?'<th class="center" style="width:70px">가공비편집</th>':''}<th></th></tr></thead>
      <tbody>${L.rows.length?L.rows.map(r=>`<tr>
        <td style="font-weight:600;color:#1c47a0;white-space:nowrap">${esc(r.gubun)}</td><td class="num">${esc(r.diam)}</td><td class="num">${esc(r.thick)}</td><td style="font-size:10px;white-space:nowrap">${esc(r.p_no)}</td>
        <td class="num">${won1(r.jaeryo)}</td><td class="num" style="color:#8a5a1a">${won1(r.gagong)}</td><td class="num" style="font-weight:700;color:#1c6b3a">${won1(r.wonjae)}</td>
        ${ed?`<td class="center"><button class="btn lg-ge" data-id="${r.id}" style="padding:1px 7px;font-size:10px">국가믹스</button></td>`:''}<td></td></tr>`).join(''):`<tr><td colspan="${ed?9:8}" class="empty">이 월의 Cost Table 데이터가 없습니다</td></tr>`}</tbody></table>`}</div>`;
  };
  const drawLme=()=>{const el=host.querySelector('#rm-tabbody');if(!el)return;el.innerHTML=lmeBody()+gagongModal();
    const g=id=>host.querySelector(id);
    {const s=g('#lg-ym');if(s)s.onchange=()=>loadLme(s.value);}
    {const b=g('#lg-copy');if(b)b.onclick=copyMonth;}
    {const b=g('#lg-hsave');if(b)b.onclick=saveHeaderRecompute;}
    {const b=g('#lg-recalc');if(b)b.onclick=recompute;}
    host.querySelectorAll('.lgh').forEach(inp=>inp.oninput=()=>{st.L.hedit[inp.dataset.k]=inp.value;});
    host.querySelectorAll('.lg-ge').forEach(b=>b.onclick=()=>{const row=st.L.rows.find(x=>x.id==b.dataset.id);if(row)openGagong(row);});
    if(st.L.gform){g('#lg-gx').onclick=g('#lg-gcancel').onclick=()=>{st.L.gform=null;drawLme();};
      g('#lg-gsave').onclick=saveGagong;
      host.querySelectorAll('.lgf').forEach(inp=>inp.oninput=()=>{st.L.gform[inp.dataset.k]=inp.value;});}
  };
  // ===================== 공통 draw(탭) =====================
  const draw=()=>{
    host.innerHTML=`
     <div class="page-title">🧱 원소재 마스터 <span style="font-size:12px;color:var(--muted);font-weight:400">스펙 마스터 + 월별 단가 · LG전자 LME인정가</span></div>
     <div class="bm-tabs" style="display:flex;gap:2px;margin:6px 0 2px;border-bottom:2px solid #d3ddec">
       <div class="bm-tab rm-tab ${st.tab==='spec'?'on':''}" data-t="spec" style="border:1px solid #d3ddec;border-bottom:none;background:${st.tab==='spec'?'#fff':'#f1f5fb'};color:${st.tab==='spec'?'#1c47a0':'#5a6b82'};padding:7px 18px;font-size:13px;font-weight:700;cursor:pointer;border-radius:8px 8px 0 0">🧱 원소재 스펙</div>
       <div class="bm-tab rm-tab ${st.tab==='lme'?'on':''}" data-t="lme" style="border:1px solid #d3ddec;border-bottom:none;background:${st.tab==='lme'?'#fff':'#f1f5fb'};color:${st.tab==='lme'?'#1c47a0':'#5a6b82'};padding:7px 18px;font-size:13px;font-weight:700;cursor:pointer;border-radius:8px 8px 0 0">📈 LG전자 LME인정가</div>
       <div class="bm-tab rm-tab ${st.tab==='settle'?'on':''}" data-t="settle" style="border:1px solid #d3ddec;border-bottom:none;background:${st.tab==='settle'?'#fff':'#f1f5fb'};color:${st.tab==='settle'?'#1c47a0':'#5a6b82'};padding:7px 18px;font-size:13px;font-weight:700;cursor:pointer;border-radius:8px 8px 0 0">📋 동정산 원단위</div>
     </div>
     <div id="rm-tabbody">${st.tab==='spec'?specBody():''}</div>`;
    host.querySelectorAll('.rm-tab').forEach(t=>t.onclick=()=>{const nt=t.dataset.t;if(nt===st.tab)return;st.tab=nt;
      if(nt==='lme'){draw();(async()=>{await loadLmeMonths();await loadLme(st.L.ym);})();}else draw();});
    if(st.tab==='spec'){
      const g=id=>host.querySelector(id);
      g('#rm-go').onclick=()=>{st.q=g('#rm-q').value;st.material=g('#rm-mat').value;load();};
      g('#rm-q').onkeyup=e=>{if(e.key==='Enter')g('#rm-go').click();};
      host.querySelectorAll('.rm-row').forEach(tr=>tr.onclick=()=>{host.querySelectorAll('.rm-row').forEach(x=>x.classList.remove('sel'));tr.classList.add('sel');loadDetail(+tr.dataset.rid);});
      attachResizers(host);renderDetail();
    } else if(st.tab==='settle'){ SCREEN.dongunit(host.querySelector('#rm-tabbody')); }
    else { drawLme(); }
  };
  load();
};

/* ===== 개발: 조달후보 승인관리 — 미승인(approve_flag=0) 목록·상세·개별/일괄 승인·반려 (nx.sourcing_route) ===== */
SCREEN.routeapprove=(host)=>{
  const API=API_BASE;
  const canW=(typeof PERM!=='undefined')?PERM.canEdit('routeapprove'):true;
  const nfq=v=>{v=Number(v||0);return v%1===0?v.toLocaleString('ko-KR'):v.toFixed(4).replace(/0+$/,'').replace(/\.$/,'');};
  const st={rows:[],cnt:0,item:'',gubun:'',user:'',from:'',to:'',incRej:false,gopts:[],sel:new Set(),detail:null,rejForm:null,msg:'',loading:false};
  const load=async()=>{st.loading=true;render();
    const qs=new URLSearchParams({item:st.item,gubun:st.gubun,user:st.user,from_ymd:st.from,to_ymd:st.to,include_rejected:st.incRej?1:0});
    try{const r=await fetch(`${API}/api/sourcing/pending?${qs}`);const j=await r.json();st.rows=j.rows||[];st.cnt=j.cnt||0;st.gopts=j.gubun_opts||[];st.msg='';}
    catch(e){st.msg='백엔드 연결 실패';st.rows=[];st.cnt=0;}
    st.sel.clear();st.loading=false;render();};
  const openDetail=async(rid)=>{st.detail={route_id:rid,loading:true};render();
    try{const r=await fetch(`${API}/api/sourcing/route/detail?route_id=${rid}`);const j=await r.json();st.detail={route_id:rid,header:j.header,lines:j.lines||[]};}
    catch(e){st.detail={route_id:rid,err:'상세 조회 실패'};}
    render();};
  const detailModal=()=>{const d=st.detail;if(!d)return '';const h=d.header||{};
    return `<div class="pmodal-bg" style="position:fixed;inset:0;background:rgba(20,40,80,.42);z-index:9990;display:flex;align-items:flex-start;justify-content:center;overflow:auto;padding:20px 10px">
      <div style="background:#fff;border-radius:12px;width:800px;max-width:97vw;box-shadow:0 20px 60px rgba(10,25,55,.4)">
        <div style="display:flex;justify-content:space-between;align-items:center;padding:12px 18px;background:#1c47a0;color:#fff;border-radius:12px 12px 0 0"><b>조달후보 상세 — 후보 #${d.route_id}</b><span id="ra-dx" style="cursor:pointer;font-size:17px">✕</span></div>
        <div style="padding:14px 18px">
          ${d.loading?spinRow(1):(d.err?`<div class="empty" style="color:#c0392b">${esc(d.err)}</div>`:`
          <div style="font-size:12.5px;margin-bottom:8px">품목 <b>${esc(h.item_code)}</b> <span style="color:#5a6b82">${esc(h.item_name||'')}</span> · 후보 <b>${esc(h.route_name||'')}</b>
            · 구분 <b>${esc(h.gubun||'-')}</b>${h.vendor_code?` · 공급처 <b>${esc(h.vendor_name||h.vendor_code)}</b>`:''}${h.apply_from?` · 적용 ${esc(h.apply_from)}`:''}
            · 등록 ${esc(h.ins_user||'')} ${h.approve_flag?'<span style="background:#1c7c3a;color:#fff;border-radius:8px;padding:0 7px;font-size:10px">승인</span>':(h.reject_flag?`<span style="background:#c0392b;color:#fff;border-radius:8px;padding:0 7px;font-size:10px" title="${esc(h.reject_reason||'')}">반려</span>`:'<span style="background:#e0912a;color:#fff;border-radius:8px;padding:0 7px;font-size:10px">미승인</span>')}</div>
          ${h.reject_flag&&h.reject_reason?`<div class="page-sub" style="color:#c0392b">반려 사유: ${esc(h.reject_reason)}</div>`:''}
          <div style="font-weight:700;color:#334;margin:8px 0 4px">구성 라인 (${(d.lines||[]).length})</div>
          <div class="grid-wrap" style="max-height:46vh;overflow:auto"><table class="tbl" style="font-size:11.5px"><thead><tr>
            <th>하위품번</th><th>품명</th><th class="num">소요량</th><th>구분</th><th>공급처</th><th>소재(외경×두께×길이·재질)</th></tr></thead>
            <tbody>${(d.lines||[]).length?d.lines.map(l=>`<tr><td><b>${esc(l.child_item)}</b></td><td class="bcap" style="max-width:180px;overflow:hidden;text-overflow:ellipsis" title="${esc(l.child_name)}">${esc(l.child_name)}</td>
              <td class="num">${nfq(l.qty)}</td><td>${esc(l.gubun)}</td><td title="${esc(l.vendor_code)}">${esc(l.vendor_name||l.vendor_code||'')}</td>
              <td>${l.is_rawmat?`Ø${nfq(l.diam)}×${nfq(l.thick)}×${nfq(l.len_val)} · ${esc(l.material)}`:'<span style="color:#c3c9d4">-</span>'}</td></tr>`).join(''):`<tr><td colspan="6" class="empty">라인 없음</td></tr>`}</tbody></table></div>`)}
        </div>
        <div style="padding:12px 18px;border-top:1px solid #e2e8f2;display:flex;justify-content:space-between;align-items:center">
          <span>${(canW&&!d.loading&&!d.err&&!(h.approve_flag))?`<button class="btn ra-appr1" data-rid="${d.route_id}" style="background:#1c7c3a;color:#fff">✔ 승인</button> <button class="btn ra-rej1" data-rid="${d.route_id}" style="color:#c0392b">✖ 반려</button>`:''}</span>
          <button class="btn" id="ra-dclose">닫기</button></div>
      </div></div>`;};
  const rejModal=()=>{const f=st.rejForm;if(!f)return '';
    return `<div class="pmodal-bg" style="position:fixed;inset:0;background:rgba(20,40,80,.42);z-index:9995;display:flex;align-items:center;justify-content:center">
      <div style="background:#fff;border-radius:10px;width:440px;max-width:94vw;box-shadow:0 20px 60px rgba(10,25,55,.4)">
        <div style="display:flex;justify-content:space-between;align-items:center;padding:11px 16px;background:#c0392b;color:#fff;border-radius:10px 10px 0 0"><b>조달후보 반려 — #${f.route_id}</b><span id="ra-rx" style="cursor:pointer;font-size:17px">✕</span></div>
        <div style="padding:16px"><label style="font-weight:700;color:#33507d;font-size:12px">반려 사유<span style="color:#c0392b">*</span></label>
          <textarea id="ra-reason" class="inp" style="width:100%;min-height:70px;box-sizing:border-box;margin-top:4px" placeholder="반려 사유(필수) — 등록자에게 전달">${esc(f.reason||'')}</textarea></div>
        <div style="padding:11px 16px;border-top:1px solid #e2e8f2;text-align:right"><button class="btn" id="ra-rsave" style="background:#c0392b;color:#fff">✖ 반려 확정</button> <button class="btn" id="ra-rcancel">닫기</button></div>
      </div></div>`;};
  const render=()=>{
    host.innerHTML=`
     <div class="page-title">🛡 조달후보 승인관리 <span style="font-size:12px;color:var(--muted);font-weight:400">미승인 조달프로파일(후보) 검토·승인·반려 · nx.sourcing_route</span></div>
     <div class="page-sub">조달경로 통합검토에서 등록된 <b>미승인 후보</b>(approve_flag=0)를 개발이 검토 → <b>승인 시 조달프로파일 노출</b>. 개별·<b>일괄 승인</b>/반려(사유). 코드→이름.</div>
     <div class="toolbar" style="flex-wrap:wrap;gap:4px">
       <label class="tl">품목</label><input class="inp" id="ra-item" value="${esc(st.item)}" placeholder="품번 일부" style="width:120px">
       <label class="tl">구분</label><select class="sel" id="ra-gubun"><option value="">전체</option>${st.gopts.map(o=>`<option value="${esc(o)}" ${st.gubun===o?'selected':''}>${esc(o)}</option>`).join('')}</select>
       <label class="tl">등록자</label><input class="inp" id="ra-user" value="${esc(st.user)}" placeholder="등록자" style="width:90px">
       <label class="tl">등록기간</label><input class="inp" id="ra-from" type="date" value="${esc(st.from)}" style="width:140px"> ~ <input class="inp" id="ra-to" type="date" value="${esc(st.to)}" style="width:140px">
       <label style="font-size:12px;margin-left:4px"><input type="checkbox" id="ra-inc" ${st.incRej?'checked':''}> 반려포함</label>
       <button class="btn" id="ra-go">🔍 조회</button>
       ${canW?`<button class="btn" id="ra-appr" style="background:#1c7c3a;color:#fff">✔ 선택 일괄승인</button>`:`<span style="color:#c0392b;font-size:12px">🔒 승인권한 없음</span>`}
       <div class="spacer"></div><span class="rowcount">${won(st.cnt)}건</span>
     </div>
     ${st.msg?`<div class="page-sub" style="color:${st.msg.includes('실패')?'#c0392b':'#1c7c3a'};font-weight:600">${esc(st.msg)}</div>`:''}
     <div class="grid-wrap" style="max-height:calc(100vh - 250px);overflow:auto;background:#fff;border:1px solid var(--line-2,#c9d3e0);border-radius:8px">
      <table class="tbl fit" style="font-size:11.5px"><thead><tr>
        <th style="width:26px"></th><th>품목</th><th>후보명</th><th>구분</th><th>공급처</th><th class="num">하위품번수</th><th>등록자</th><th>등록일</th><th class="center">상태</th><th style="width:150px">작업</th></tr></thead>
      <tbody>${st.loading?spinRow(10):(st.rows.length?st.rows.map((r,i)=>`<tr class="ra-row" data-idx="${i}" style="cursor:pointer">
        <td class="center">${(canW&&!r.reject_flag)?`<input type="checkbox" class="ra-chk" data-rid="${r.route_id}" ${st.sel.has(r.route_id)?'checked':''}>`:''}</td>
        <td title="${esc(r.item_code)}"><b>${esc(r.item_code)}</b> <span style="color:#5a6b82">${esc((r.item_name||'').slice(0,16))}</span></td>
        <td class="bcap" style="max-width:150px;overflow:hidden;text-overflow:ellipsis" title="${esc(r.route_name)}">${esc(r.route_name)}</td>
        <td>${esc(r.gubun||'-')}</td><td title="${esc(r.vendor_code)}">${esc(r.vendor_name||r.vendor_code||'')}</td>
        <td class="num">${won(r.n_line)}</td><td>${esc(r.ins_user||'')}</td><td>${esc(r.ins_dt||'')}</td>
        <td class="center">${r.reject_flag?`<span style="background:#c0392b;color:#fff;border-radius:8px;padding:0 6px;font-size:10px" title="${esc(r.reject_reason||'')}">반려</span>`:'<span style="background:#e0912a;color:#fff;border-radius:8px;padding:0 6px;font-size:10px">미승인</span>'}</td>
        <td class="center"><button class="btn ra-det" data-rid="${r.route_id}" style="padding:1px 6px;font-size:10px">상세</button>${canW?`<button class="btn ra-a1" data-rid="${r.route_id}" style="padding:1px 6px;font-size:10px;background:#1c7c3a;color:#fff">승인</button><button class="btn ra-r1" data-rid="${r.route_id}" style="padding:1px 6px;font-size:10px;color:#c0392b">반려</button>`:''}</td></tr>`).join(''):`<tr><td colspan="10" class="empty">미승인 후보 없음 (조달경로 통합검토에서 등록 시 표시)</td></tr>`)}</tbody>
      <tfoot><tr style="position:sticky;bottom:0;background:#eef2f7;font-weight:700;border-top:2px solid #c9d3e0"><td></td><td class="center">합계</td><td colspan="8">미승인 ${won(st.cnt)}건${st.sel.size?` · 선택 ${st.sel.size}건`:''}</td></tr></tfoot></table></div>
     ${detailModal()}${rejModal()}`;
    const g=id=>host.querySelector(id);
    g('#ra-go').onclick=()=>{st.item=g('#ra-item').value;st.gubun=g('#ra-gubun').value;st.user=g('#ra-user').value;st.from=g('#ra-from').value;st.to=g('#ra-to').value;st.incRej=g('#ra-inc').checked;load();};
    g('#ra-item').onkeyup=e=>{if(e.key==='Enter')g('#ra-go').click();};
    host.querySelectorAll('.ra-det').forEach(b=>b.onclick=e=>{e.stopPropagation();openDetail(+b.dataset.rid);});
    host.querySelectorAll('.ra-row').forEach(el=>el.onclick=()=>openDetail(st.rows[+el.dataset.idx].route_id));
    if(canW){
      g('#ra-appr').onclick=()=>approve([...st.sel]);
      host.querySelectorAll('.ra-chk').forEach(ch=>ch.onclick=e=>{e.stopPropagation();const id=+ch.dataset.rid;ch.checked?st.sel.add(id):st.sel.delete(id);render();});
      host.querySelectorAll('.ra-a1').forEach(b=>b.onclick=e=>{e.stopPropagation();approve([+b.dataset.rid]);});
      host.querySelectorAll('.ra-r1').forEach(b=>b.onclick=e=>{e.stopPropagation();st.rejForm={route_id:+b.dataset.rid,reason:''};render();});
    }
    if(st.detail){g('#ra-dx').onclick=g('#ra-dclose').onclick=()=>{st.detail=null;render();};
      const a=host.querySelector('.ra-appr1');if(a)a.onclick=()=>approve([+a.dataset.rid]);
      const rj=host.querySelector('.ra-rej1');if(rj)rj.onclick=()=>{st.rejForm={route_id:+rj.dataset.rid,reason:''};render();};}
    if(st.rejForm){g('#ra-rx').onclick=g('#ra-rcancel').onclick=()=>{st.rejForm=null;render();};
      g('#ra-rsave').onclick=doReject;}
  };
  const approve=async(ids)=>{ids=ids.filter(x=>x);if(!ids.length){alert('승인할 후보를 체크하세요');return;}
    if(!confirm(ids.length+'건을 승인하시겠습니까? (조달프로파일에 노출됩니다)'))return;
    try{const r=await fetch(`${API}/api/sourcing/route/approve_bulk`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({route_ids:ids,user:'개발'})});
      const j=await r.json();if(j.ok){st.msg='✔ '+j.approved+'건 승인 완료 — 조달프로파일 노출';st.detail=null;await load();}else alert('승인 실패');}
    catch(e){alert('승인 오류: '+e);}};
  const doReject=async()=>{const f=st.rejForm;const reason=(host.querySelector('#ra-reason').value||'').trim();
    if(!reason){alert('반려 사유는 필수입니다');return;}
    try{const r=await fetch(`${API}/api/sourcing/route/reject`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({route_id:f.route_id,reason,user:'개발'})});
      const j=await r.json();if(j.ok){st.msg='✖ 반려 완료 (#'+f.route_id+')';st.rejForm=null;st.detail=null;await load();}else alert('반려 실패: '+(j.detail||''));}
    catch(e){alert('반려 오류: '+e);}};
  load();
};

/* ===== 개발: 직거래 LME 월연동 판가 (자동정본화, w_tc_master_165/090 자동판) — nx.dtrade_* ===== */
SCREEN.dtradeprice=(host)=>{
  const API=API_BASE;
  const canW=(typeof PERM!=='undefined')?PERM.canEdit('dtradeprice'):true;
  const won=v=>(v==null||v==='')?'<span style="color:#c9d1dc">-</span>':Number(v).toLocaleString('ko-KR',{maximumFractionDigits:1});
  const q4=v=>(v==null)?'':Number(v).toLocaleString('ko-KR',{maximumFractionDigits:4});
  const fy=y=>{y=''+(y||'');return y.length>=6?`${y.slice(0,4)}-${y.slice(4,6)}`:y;};
  const st={months:[],ym:'',batch:'260709',summary:[],rows:[],cnt:0,linkage:'직거래LME',q:'',cmp:null,msg:'',loading:false,uploading:false,upmsg:''};
  const loadInit=async()=>{
    try{const r=await fetch(`${API}/api/dtrade/lme`);st.months=(await r.json()).rows||[];if(!st.ym&&st.months.length)st.ym=st.months[0].apply_ym;}catch(e){}
    try{const s=await fetch(`${API}/api/dtrade/summary`);st.summary=(await s.json()).rows||[];}catch(e){}
    load();};
  const load=async()=>{st.loading=true;draw();
    try{const r=await fetch(`${API}/api/dtrade/list?ym=${encodeURIComponent(st.ym)}&linkage=${encodeURIComponent(st.linkage)}&q=${encodeURIComponent(st.q)}`);
      const j=await r.json();st.rows=j.rows||[];st.cnt=j.cnt||0;}catch(e){st.rows=[];}
    st.loading=false;draw();};
  const recompute=async()=>{st.msg='재계산 중…';draw();
    try{const r=await fetch(`${API}/api/dtrade/recompute`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({ym:st.ym})});
      const j=await r.json();st.msg=j.ok?`♻ 재계산 완료 — 직거래LME ${j['직거래LME']}·사급정체 ${j['사급정체']} (LME ${won(j.lme_index)})`:('실패: '+(j.errors?j.errors.join(','):''));await load();}
    catch(e){st.msg='재계산 오류: '+e;draw();}};
  const compare=async()=>{st.msg='라이브 대사 중…';st.cmp=null;draw();
    try{const r=await fetch(`${API}/api/dtrade/compare?ym=${encodeURIComponent(st.ym)}&batch_ymd=${encodeURIComponent(st.batch)}`);
      st.cmp=await r.json();st.msg='';}catch(e){st.msg='대사 오류: '+e;}
    draw();};
  const doUpload=async(f)=>{                       // LG PO Price 업로드(정본)
    if(!f)return;
    if(!/\.(xlsx|xls)$/i.test(f.name||'')){st.upmsg='❌ 엑셀(.xlsx/.xls)만 가능';draw();return;}
    st.uploading=true;st.upmsg='';draw();
    try{const fd=new FormData();fd.append('file',f);
      const r=await fetch(`${API}/api/dtrade/po_upload`,{method:'POST',body:fd});
      let j={};try{j=await r.json();}catch(e){}
      if(r.ok&&j.ok){st.upmsg=`✅ ${won(j.rows)}행 · 품목 ${won(j.items)} · 누적 ${won(j.total_items)} (최신회차 ${j.latest_created})`;st.uploading=false;await load();return;}
      else st.upmsg='❌ '+(j.detail||('HTTP '+r.status));
    }catch(e){st.upmsg='❌ '+e.message;}
    st.uploading=false;draw();};
  const draw=()=>{
    const sumMap={};st.summary.forEach(s=>sumMap[s.linkage]=s);
    const dir=sumMap['직거래LME']||{},stl=sumMap['사급정체']||{};
    const c=st.cmp;
    host.innerHTML=`
     <div class="page-title">🔁 직거래 LME 월연동 판가 <span style="font-size:12px;color:var(--muted);font-weight:400">자동정본화 · 레거시 w_tc_master_165/090 수작업 자동판 · nx.dtrade_*</span></div>
     <div class="page-sub">산식 <b>판가(월)=기준판가 + 동소요량 × (LME월 − 기준LME)</b>. 직거래LME만 매월 재계산, <b>사급정체(2월↓)</b>는 기준 고정. 라이브 <code>PR_M_ITEM_COST</code> 읽기전용 대사.</div>
     <div style="display:flex;gap:8px;margin:6px 0">
       <span style="background:#1c47a0;color:#fff;border-radius:8px;padding:3px 12px;font-size:12px">직거래LME <b>${won(dir.cnt||0)}</b> <span style="opacity:.8">(LG392 ${dir.lg392||0}·역산 ${dir.inv||0})</span></span>
       <span style="background:#8090a5;color:#fff;border-radius:8px;padding:3px 12px;font-size:12px">사급정체(제외) <b>${won(stl.cnt||0)}</b></span>
     </div>
     ${canW?`<div id="dt-drop" style="border:2px dashed #8fb4d6;border-radius:9px;padding:9px 14px;background:#f4f9fe;display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin:4px 0;font-size:12px">
       <span style="font-size:18px">📤</span><b>LG PO Price 엑셀</b>을 드래그&드롭 또는
       <button class="btn" id="dt-pick" style="background:#1c47a0;color:#fff"${st.uploading?' disabled':''}>${st.uploading?'⏳ 처리중…':'📁 파일 선택'}</button>
       <input type="file" id="dt-file" accept=".xlsx,.xls" style="display:none">
       <span style="color:#5a6b82">→ 최신 Created 회차가 <b>LG확정판가(정본)</b>. LME 계산판가는 검증용.</span>
       ${st.upmsg?`<span style="margin-left:auto;font-weight:600;color:${st.upmsg.startsWith('✅')?'#1c7c3a':'#c0392b'}">${esc(st.upmsg)}</span>`:''}
     </div>`:''}
     <div class="toolbar" style="flex-wrap:wrap;gap:4px">
       <label class="tl">적용월</label><select class="sel" id="dt-ym">${st.months.map(m=>`<option value="${m.apply_ym}" ${st.ym===m.apply_ym?'selected':''}>${fy(m.apply_ym)} · LME ${won(m.lme_index)}</option>`).join('')}</select>
       <label class="tl">구분</label><select class="sel" id="dt-lk"><option value="직거래LME" ${st.linkage==='직거래LME'?'selected':''}>직거래LME</option><option value="사급정체" ${st.linkage==='사급정체'?'selected':''}>사급정체</option><option value="" ${st.linkage===''?'selected':''}>전체</option></select>
       <input class="inp" id="dt-q" value="${esc(st.q)}" placeholder="품번/품명" style="width:130px">
       <button class="btn" id="dt-go">🔍 조회</button>
       ${canW?`<button class="btn" id="dt-recalc" style="background:#1c7c3a;color:#fff">♻ ${fy(st.ym)} 재계산</button>`:''}
       <label class="tl">라이브배치</label><input class="inp" id="dt-batch" value="${esc(st.batch)}" placeholder="YYMMDD" style="width:80px"><button class="btn" id="dt-cmp" style="background:#b12a2a;color:#fff">🔴 라이브 대사</button>
       <div class="spacer"></div><span class="rowcount">${won(st.cnt)}건</span>
     </div>
     ${st.msg?`<div class="page-sub" style="color:${st.msg.includes('실패')||st.msg.includes('오류')?'#c0392b':'#1c7c3a'};font-weight:600">${esc(st.msg)}</div>`:''}
     ${c&&c.calc_cnt!=null?`<div style="border:1px solid ${c.match_rate>=90?'#bfe6cd':'#f0dca8'};background:${c.match_rate>=90?'#eafaef':'#fff7e6'};border-radius:8px;padding:8px 12px;margin:4px 0;font-size:13px">
       <b>라이브 대사</b> (계산 ${fy(c.ym)} vs 라이브 배치 ${esc(c.batch_ymd)}, ±${c.tol}원): 매칭키 ${won(c.live_matched_keys)} · <b style="color:${c.match_rate>=90?'#1c7c3a':'#c0392b'};font-size:15px">일치율 ${c.match_rate}%</b> · 평균오차 ${c.mean_abs_diff} · 중앙 ${c.median_abs_diff}
       ${(c.mismatch_samples||[]).length?`<div style="margin-top:4px;font-size:11px;color:#8a5a1a">불일치 표본: ${c.mismatch_samples.slice(0,6).map(s=>`${esc(s.item)}(계산 ${s.calc}/라이브 ${s.live}/Δ${s.diff})`).join(', ')}</div>`:''}</div>`:''}
     <div class="grid-wrap" style="max-height:calc(100vh - 390px);overflow:auto;background:#fff;border:1px solid var(--line-2,#c9d3e0);border-radius:8px">
      <table class="tbl fit" style="font-size:11px"><thead><tr>
        <th>품번</th><th>품명</th><th>거래처</th><th class="center">구분</th><th class="center">연동</th><th class="num">동소요량</th><th class="center">src</th><th class="center">주거래</th>
        <th class="num">기준판가</th><th class="num">기준LME</th><th class="num">계산판가(${fy(st.ym)})</th><th class="num">LG확정판가</th><th class="num">차이</th><th class="center">사급자재</th></tr></thead>
      <tbody>${st.loading?spinRow(12):(st.rows.length?st.rows.map(r=>`<tr>
        <td><b>${esc(r.item_code)}</b></td><td class="bcap" title="${esc(r.item_desc)}" style="max-width:150px;overflow:hidden;text-overflow:ellipsis">${esc(r.item_desc)}</td>
        <td>${esc(r.cust_code)}</td><td class="center">${esc(r.cost_tag)}</td>
        <td class="center"><span style="color:#fff;background:${r.linkage==='직거래LME'?'#1c47a0':'#8090a5'};border-radius:7px;padding:0 6px;font-size:10px">${esc(r.linkage)}</span></td>
        <td class="num">${q4(r.dong_qty)}</td><td class="center" style="font-size:10px;color:#5a6b82">${esc(r.qty_src)}</td>
        <td class="center">${r.main_flag==='1'?'★':''}</td>
        <td class="num">${won(r.base_item_cost)}</td><td class="num" style="color:#8aa0bd">${won(r.base_lme)}</td>
        <td class="num" style="font-weight:700;color:#1c6b3a">${won(r.calc_item_cost)}</td>
        <td class="num" style="font-weight:700;color:#1c47a0">${won(r.lg_price)}</td>
        <td class="num" style="color:${r.lg_diff==null?'#c9d1dc':(Math.abs(r.lg_diff)<1?'#1c7c3a':'#c0392b')}">${r.lg_diff==null?'-':(r.lg_diff>0?'+':'')+won(r.lg_diff)}</td>
        <td class="center">${r.sagub_flag?'<span style="color:#b8860b">사급</span>':''}</td></tr>`).join(''):`<tr><td colspan="14" class="empty">대상 없음 (재계산으로 계산판가 생성)</td></tr>`)}</tbody></table></div>`;
    const g=id=>host.querySelector(id);
    g('#dt-go').onclick=()=>{st.ym=g('#dt-ym').value;st.linkage=g('#dt-lk').value;st.q=g('#dt-q').value;st.batch=g('#dt-batch').value;load();};
    g('#dt-ym').onchange=()=>{st.ym=g('#dt-ym').value;load();};
    g('#dt-q').onkeyup=e=>{if(e.key==='Enter')g('#dt-go').click();};
    {const b=g('#dt-recalc');if(b)b.onclick=()=>{st.ym=g('#dt-ym').value;recompute();};}
    g('#dt-cmp').onclick=()=>{st.ym=g('#dt-ym').value;st.batch=g('#dt-batch').value;compare();};
    {const drop=g('#dt-drop');if(drop){const fe=g('#dt-file');
      g('#dt-pick').onclick=()=>fe.click();
      fe.onchange=()=>{doUpload(fe.files&&fe.files[0]);fe.value='';};
      drop.ondragover=e=>{e.preventDefault();drop.style.background='#e3f0ff';drop.style.borderColor='#1c47a0';};
      drop.ondragleave=()=>{drop.style.background='#f4f9fe';drop.style.borderColor='#8fb4d6';};
      drop.ondrop=e=>{e.preventDefault();drop.style.background='#f4f9fe';drop.style.borderColor='#8fb4d6';const f=e.dataTransfer.files&&e.dataTransfer.files[0];if(f)doUpload(f);};}}
  };
  loadInit();
};
