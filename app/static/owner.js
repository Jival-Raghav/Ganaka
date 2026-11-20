const UI={en:{home:'Home',chat:'Chat',inbox:'Inbox',approvals:'Approvals',returns:'Returns',ewb:'E-way bills',suppliers:'Suppliers',calendar:'Calendar',docs:'Documents',notices:'Notices',more:'More',settings:'Settings',ask:'Ask about GST, credit, bills…'},
 hi:{home:'होम',chat:'चैट',inbox:'इनबॉक्स',approvals:'मंज़ूरी',returns:'रिटर्न',ewb:'ई-वे बिल',suppliers:'सप्लायर',calendar:'कैलेंडर',docs:'दस्तावेज़',notices:'नोटिस',more:'और',settings:'सेटिंग',ask:'GST, क्रेडिट, बिल के बारे में पूछें…'},
 kn:{home:'ಮುಖಪುಟ',chat:'ಚಾಟ್',inbox:'ಇನ್‌ಬಾಕ್ಸ್',approvals:'ಅನುಮೋದನೆ',returns:'ರಿಟರ್ನ್',ewb:'ಇ-ವೇ ಬಿಲ್',suppliers:'ಪೂರೈಕೆದಾರರು',calendar:'ಕ್ಯಾಲೆಂಡರ್',docs:'ದಾಖಲೆಗಳು',notices:'ನೋಟಿಸ್',more:'ಇನ್ನಷ್ಟು',settings:'ಸೆಟ್ಟಿಂಗ್',ask:'GST, ಕ್ರೆಡಿಟ್, ಬಿಲ್ ಬಗ್ಗೆ ಕೇಳಿ…'}};
const S={me:null,bid:null,role:null,lang:'en',tab:'home'};
const TABS=['home','chat','inbox','approvals','returns','ewb','suppliers','calendar','docs','notices','more','settings'];
const L=k=>(UI[S.lang]||UI.en)[k]||UI.en[k];
const B=p=>`/api/b/${S.bid}${p}`;
const R={};

async function boot(){
 if(!TOKEN)return login();
 try{S.me=await api('/api/me',{quiet:true})}catch(e){return login()}
 S.lang=S.me.user.preferred_language;const ms=S.me.memberships.filter(m=>m.role!=='accountant');
 if(!ms.length){return location.href='/accountant'}
 S.bid=S.bid||ms[0].business_id;S.role=ms.find(m=>m.business_id==S.bid)?.role;shell();route()}
function login(){$('#app').innerHTML=`<div class="login card stack"><h1>Ganaka</h1><p><b>Simplifying Compliance. Empowering Businesses.</b></p><p class="mute">Collects your bills, prepares returns, explains everything in your language. You decide.</p>
 <label>Phone</label><input id="ph" placeholder="98450 12345" inputmode="tel"><button data-act="otp">Send OTP</button>
 <div id="otpbox" style="display:none" class="stack"><label>OTP <span class="mute" id="demootp"></span></label><input id="otp" inputmode="numeric"><button data-act="verify">Log in</button></div>
 <h3>Demo logins</h3><div class="row"><button class="ghost small" data-act="demo" data-p="9845012345">Ramesh (trader, Kannada)</button><button class="ghost small" data-act="demo" data-p="9845098765">Lakshmi (QRMP, Hindi)</button><button class="ghost small" data-act="demo" data-p="9845077777">Suresh (services)</button></div>
 <p class="mute"><a href="#" data-act="onboard">New business? Onboard</a> · <a href="/accountant">Accountant console</a> · <a href="/sim">WhatsApp simulator</a></p></div>`}
ACT.otp=async()=>{const r=await api('/api/auth/otp',{body:{phone:$('#ph').value}});$('#otpbox').style.display='block';$('#demootp').textContent='(demo OTP '+r.demo_otp+')';$('#otp').value=r.demo_otp};
ACT.verify=async()=>{const r=await api('/api/auth/verify',{body:{phone:$('#ph').value,otp:$('#otp').value}});setToken(r.token);boot()};
ACT.demo=async d=>{$('#ph').value=d.p;await ACT.otp();await ACT.verify()};
ACT.onboard=()=>{$('#app').innerHTML=`<div class="login card stack"><h1>Onboarding</h1>
 <input id="o_name" placeholder="Your name"><input id="o_phone" placeholder="Phone"><input id="o_legal" placeholder="Legal name"><input id="o_trade" placeholder="Trade name">
 <input id="o_gstin" placeholder="GSTIN (15 chars; checksum validated)"><input id="o_pin" placeholder="Business PIN code">
 <select id="o_type"><option value="trader">Trader</option><option value="manufacturer">Small manufacturer</option><option value="transporter">Transporter</option><option value="service">Service business</option></select>
 <select id="o_scheme"><option value="regular">Regular (monthly)</option><option value="qrmp">QRMP (quarterly)</option><option value="composition">Composition</option></select>
 <select id="o_lang"><option value="en">English</option><option value="hi">हिन्दी</option><option value="kn">ಕನ್ನಡ</option></select>
 <label><input type="checkbox" id="o_udyam" style="width:auto"> Udyam registered</label><input id="o_emp" type="number" placeholder="Employees" value="0">
 <input id="o_acc" placeholder="Accountant email (optional, e.g. priya@demo.in)"><button data-act="onboard_go">Create</button><button class="ghost" onclick="location.reload()">Back</button></div>`};
ACT.onboard_go=async()=>{const r=await api('/api/onboard',{body:{name:$('#o_name').value,phone:$('#o_phone').value,legal_name:$('#o_legal').value,trade_name:$('#o_trade').value,gstin:$('#o_gstin').value.toUpperCase(),business_type:$('#o_type').value,gst_scheme:$('#o_scheme').value,language:$('#o_lang').value,udyam_registered:$('#o_udyam').checked,employee_count:+$('#o_emp').value,address_pin:$('#o_pin').value,accountant_email:$('#o_acc').value||null}});toast(r.message,7000);setTimeout(()=>location.reload(),1500)};

function shell(){const ms=S.me.memberships.filter(m=>m.role!=='accountant');
 $('#app').innerHTML=`<div class="top"><span class="brand">Ganaka</span><select id="bsel" style="width:auto;max-width:200px">${ms.map(m=>`<option value="${m.business_id}" ${m.business_id==S.bid?'selected':''}>${esc(m.trade_name)}</option>`).join('')}</select><span class="sp"></span>
 <select id="lsel" style="width:auto">${Object.entries(S.me.languages).map(([k,v])=>`<option value="${k}" ${k==S.lang?'selected':''}>${v}</option>`).join('')}</select><button class="ghost small" data-act="logout">Log out</button></div>
 <div class="nav" id="nav"></div><div class="wrap" id="main"></div>`;
 $('#bsel').onchange=e=>{S.bid=+e.target.value;S.role=ms.find(m=>m.business_id==S.bid).role;route()};
 $('#lsel').onchange=async e=>{S.lang=e.target.value;await api('/api/me/lang',{method:'PUT',body:{lang:S.lang}});shell();route()};}
ACT.logout=()=>logout();
window.addEventListener('hashchange',()=>{if(S.me)route()});
async function route(){const [t,id]=(location.hash.slice(1)||'home').split('/');S.tab=t;
 const bar=$('#nav');if(bar)bar.innerHTML=TABS.map(k=>`<a href="#${k}" class="${k===t||(t==='return'&&k==='returns')?'on':''}">${esc(L(k))}</a>`).join('');
 const m=$('#main');if(!m)return;m.innerHTML='<p class="mute">Loading…</p>';
 try{m.innerHTML=await (R[t]||R.home)(id)}catch(e){m.innerHTML=`<div class="card"><b>Error:</b> ${esc(e.message)}</div>`}
 if(t==='chat')chatInit()}

R.home=async()=>{const h=await api(B('/home'));const l=h.liability;
 return `<h1>${esc(h.business.trade_name)}</h1><p class="mute">${esc(h.business.gstin)} · ${h.business.business_type} · ${h.business.gst_scheme} · period ${h.period}</p>
 ${h.questions.length?`<div class="card"><h3>${h.questions.length} question(s) for you</h3>${h.questions.slice(0,3).map(qHtml).join('')}</div>`:''}
 <div class="grid"><div class="card"><div class="mute">GST to pay (${h.period})</div><div class="kpi">${money(l.cash)}</div><div class="mute">due ${l.due}</div><a href="#returns">Open return</a></div>
 <div class="card"><div class="mute">Input credit used</div><div class="kpi">${money(l.itc)}</div><div class="mute">stuck / at risk: <b>${money(h.itc_at_risk)}</b></div><a href="#suppliers">Review suppliers</a></div>
 <div class="card"><div class="mute">Waiting for you</div><div class="kpi">${h.approvals_waiting}</div><a href="#approvals">Approvals</a> · ${h.open_notices} open notice(s)</div></div>
 <div class="grid"><div class="card"><h3>Next deadlines</h3>${h.deadlines.map(d=>`<div class="row"><span>${esc(d.label)}</span><span class="sp"></span>${statusPill(d.status)} <span class="mute">${d.due_date}</span></div>`).join('')||'<span class="mute">None</span>'}</div>
 <div class="card"><h3>Dispatches needing e-way bill</h3>${h.pending_dispatches.map(p=>`<div class="row"><span>${esc(p.invoice_no)} · ${money(p.value)}</span><span class="sp"></span>${statusPill(p.ewb_status||'not prepared')}</div>`).join('')||'<span class="mute">None</span>'}<a href="#ewb">Open</a></div>
 <div class="card"><h3>Notifications</h3>${h.notifications.map(n=>`<div class="mute"><b>${esc(n.title)}</b> ${esc(n.body)}</div>`).join('')||'<span class="mute">None</span>'}${h.expiring_docs.map(d=>`<div class="mute">⚠ ${esc(d.doc_type)} ${d.state} (${d.days_left} days)</div>`).join('')}</div></div>`};

function qHtml(q){const opts=q.options||(q.options_json?JSON.parse(q.options_json):null);let inp='';
 if(q.kind==='candidates')inp=(opts||[]).map(o=>`<button class="small" data-act="ans" data-q="${q.id}" data-a="${o}">${money(o,true)}</button>`).join(' ');
 else if(q.kind==='manual_entry')inp=`<textarea id="qa${q.id}" rows="7">${esc(opts&&opts[0]||'')}</textarea><button class="small" data-act="ansbox" data-q="${q.id}">Submit bill details</button>`;
 else if(q.kind==='low_conf')inp=`<button class="small" data-act="ans" data-q="${q.id}" data-a="yes">Yes, correct</button> <input id="qa${q.id}" placeholder="Or type the right value" style="max-width:220px"><button class="small ghost" data-act="ansbox" data-q="${q.id}">Fix</button>`;
 else if(q.kind==='invalid'||q.kind==='missing'||q.kind==='ewb_transporter'||q.kind==='ask_owner')inp=`<input id="qa${q.id}" placeholder="Your answer" style="max-width:240px"><button class="small" data-act="ansbox" data-q="${q.id}">Send</button>`;
 else if(q.kind==='total_mismatch')inp=`<button class="small" data-act="ans" data-q="${q.id}" data-a="use_calculated">Use calculated total</button> <button class="small ghost" data-act="ans" data-q="${q.id}" data-a="manual">No, I'll fix it</button>`;
 else if(opts)inp=opts.map(o=>`<button class="small ghost" data-act="ans" data-q="${q.id}" data-a="${esc(o)}">${esc(String(o).replace(/_/g,' '))}</button>`).join(' ');
 else inp=`<input id="qa${q.id}" placeholder="Your answer"><button class="small" data-act="ansbox" data-q="${q.id}">Send</button>`;
 return `<div class="q"><div>${esc(q.question)}</div><div class="row" style="margin-top:6px">${inp}</div></div>`}
ACT.ans=async d=>{const r=await api(B(`/questions/${d.q}/answer`),{body:{answer:d.a}});toast(r.message||r.status||'Thanks');route()};
ACT.ansbox=async d=>{const v=$('#qa'+d.q).value;if(!v)return;const r=await api(B(`/questions/${d.q}/answer`),{body:{answer:v}});toast(r.message||r.status||'Thanks');route()};

// ---------- chat ----------
const CHAT={mic:null};
R.chat=async()=>`<h1>${esc(L('chat'))}</h1><div class="card"><div class="chat" id="chat"></div>
 <div class="row" style="margin-top:8px"><button class="mic ghost" id="micb" title="Hold to talk">🎤</button><input id="cin" placeholder="${esc(L('ask'))}" style="flex:1"><button data-act="send">Send</button><label class="btn ghost small">📎<input type="file" id="cfile" style="display:none"></label></div>
 <div class="row mute" style="margin-top:6px">Try: <a href="#" data-act="try" data-t="How much tax do I pay this month?">tax this month</a> · <a href="#" data-act="try" data-t="ee month GST eshtu?">ee month GST eshtu?</a> · <a href="#" data-act="try" data-t="Which ITC is stuck?">credit stuck</a> · <a href="#" data-act="try" data-t="Any dispatch needing e-way bill?">e-way bills</a> · <a href="#" data-act="try" data-t="deadlines">deadlines</a></div></div>`;
async function chatInit(){const h=await api(B('/chat'));const box=$('#chat');h.forEach(m=>addMsg(m.role==='user'?'u':'a',m.text,m.cards));if(!h.length)addMsg('a','Hello! Ask me anything about your GST, bills or e-way bills.');box.scrollTop=1e9;
 const mic=$('#micb');const start=()=>{CHAT.mic=listen(S.lang,t=>{$('#cin').value=t;ACT.send()});mic.classList.add('rec')};const stop=()=>{mic.classList.remove('rec');try{CHAT.mic&&CHAT.mic.stop()}catch(e){}};
 mic.onmousedown=mic.ontouchstart=e=>{e.preventDefault();start()};mic.onmouseup=mic.ontouchend=stop;
 $('#cin').onkeydown=e=>{if(e.key==='Enter')ACT.send()};
 $('#cfile').onchange=async e=>{const f=e.target.files[0];if(!f)return;const fd=new FormData();fd.append('file',f);fd.append('note','');addMsg('u','📎 '+f.name);const r=await api(B('/upload'),{body:fd});addMsg('a',r.message+(r.status==='needs_review'?' → see Inbox to answer.':''))}}
function addMsg(who,text,cards){const box=$('#chat');if(!box)return;const d=document.createElement('div');d.className='msg '+who;d.innerHTML=esc(text)+(who==='a'?` <a href="#" data-act="read" data-t="${esc(text)}" title="Read aloud">🔊</a>`:'')+(cards||[]).map(c=>`<div class="card" style="margin:8px 0 0;color:var(--ink)"><b>${esc(c.title)}</b>${c.rows.length?`<table>${c.rows.map(r=>`<tr><td>${esc(r[0])}</td><td class="r">${esc(r[1])}</td></tr>`).join('')}</table>`:''}<div class="row" style="margin-top:6px">${c.actions.map(a=>a.href?`<a class="btn small" target="_blank" href="${a.href}?token=${TOKEN}">${esc(a.label)}</a>`:`<a class="btn small ghost" href="#${a.nav}">${esc(a.label)}</a>`).join('')}</div></div>`).join('');box.appendChild(d);box.scrollTop=1e9}
ACT.send=async()=>{const i=$('#cin'),t=i.value.trim();if(!t)return;i.value='';addMsg('u',t);const r=await api(B('/chat'),{body:{text:t}});addMsg('a',r.text,r.cards);sarvamSpeak(r.text,r.lang)};
ACT.try=d=>{$('#cin').value=d.t;ACT.send()};ACT.read=d=>speak(d.t,S.lang);

// ---------- inbox ----------
R.inbox=async()=>{const docs=await api(B('/inbox'));
 return `<h1>${esc(L('inbox'))}</h1><div class="card"><h3>Add bills</h3><p class="mute">Forward to our WhatsApp bot (see the <a href="/sim" target="_blank">simulator</a>), connect Gmail, or upload here (text bills, CSV bank statements, notices, licences; photos ask you to key in details in this demo build).</p>
 <div class="row"><input type="file" id="upf" style="flex:1"><button data-act="upload">Upload</button><button class="ghost" data-act="gmail">Sync Gmail</button><button class="ghost" data-act="bankup">Bank statement…</button><input type="file" id="bankf" style="display:none"></div></div>
 <div class="card">${table([{h:'Received',f:d=>d.received_at.slice(0,16).replace('T',' ')},{h:'Source',f:d=>esc(d.channel)},{h:'File',f:d=>`<a href="#" data-act="viewdoc" data-d="${d.id}">${esc(d.filename)}</a>`},{h:'Type',f:d=>esc(d.doc_type||'')},{h:'Status',f:d=>statusPill(d.status)+(d.note?`<div class="mute">${esc(d.note)}</div>`:'')+d.questions.map(qHtml).join('')}],docs)}</div>`};
ACT.upload=async()=>{const f=$('#upf').files[0];if(!f)return toast('Choose a file');const fd=new FormData();fd.append('file',f);const r=await api(B('/upload'),{body:fd});toast(r.message,5000);route()};
ACT.bankup=()=>$('#bankf').click();
document.addEventListener('change',async e=>{if(e.target.id==='bankf'){const fd=new FormData();fd.append('file',e.target.files[0]);const r=await api(B('/bank-statement'),{body:fd});toast(r.message,6000);route()}});
ACT.gmail=async()=>{const r=await api(B('/gmail/sync'),{method:'POST'});toast(r.error||`Gmail: ${r.processed.length} email(s) processed`);route()};
ACT.viewdoc=async d=>{const x=await api(B('/documents/'+d.d));await modal(`<h3>${esc(x.filename)}</h3><pre>${esc(x.content||'(binary file)')}</pre><button data-v="ok">Close</button>`)};

// ---------- approvals ----------
R.approvals=async()=>{const a=await api(B('/approvals'));const pend=a.filter(x=>x.status==='pending'&&x.requested_from==='owner'),acc=a.filter(x=>x.status==='pending'&&x.requested_from==='accountant'),done=a.filter(x=>x.status!=='pending');
 return `<h1>${esc(L('approvals'))}</h1><p class="mute">Nothing leaves the system without a human decision.</p>${pend.length?'':'<div class="card mute">Nothing waiting for you.</div>'}
 ${pend.map(x=>`<div class="card"><div class="row"><b>${esc(x.summary)}</b><span class="sp"></span>${pill(x.item_type)}</div><div class="mute">requested by ${esc(x.requested_by)} · ${x.created_at.slice(0,16).replace('T',' ')}</div>${x.item_type==='message'?`<pre>${esc(JSON.stringify(x.payload.vars))}</pre>`:''}<div class="row" style="margin-top:8px"><button data-act="decide" data-id="${x.id}" data-d="approved" data-s="${esc(x.summary)}">Approve</button><button class="ghost" data-act="decide" data-id="${x.id}" data-d="rejected">Reject</button>${x.item_type==='return'?`<button class="ghost" data-act="toacc" data-id="${x.id}">Send to accountant</button><a class="btn ghost" href="#return/${x.item_id}">Open</a>`:''}</div></div>`).join('')}
 ${acc.length?`<h2>With your accountant</h2>${acc.map(x=>`<div class="card">${esc(x.summary)} ${pill('awaiting accountant','info')}</div>`).join('')}`:''}
 <h2>History</h2><div class="card">${table([{h:'Item',f:x=>esc(x.summary)},{h:'Status',f:x=>statusPill(x.status)},{h:'Comment',f:x=>esc(x.comment||'')},{h:'When',f:x=>(x.decided_at||x.created_at).slice(0,16).replace('T',' ')}],done.slice(0,20))}</div>`};
ACT.decide=async d=>{if(d.d==='approved'&&!(await confirmBox(`Approve: ${d.s}?`)))return;const r=await api(`/api/approvals/${d.id}/decide`,{body:{decision:d.d}});toast(r.error?('Failed: '+r.error):'Done');route()};
ACT.toacc=async d=>{await api(`/api/approvals/${d.id}/route-accountant`,{method:'POST'});toast('Sent to your accountant with the full proof pack');route()};

// ---------- returns ----------
R.returns=async()=>{const rs=await api(B('/returns'));const per=(await api(B('/home'))).period;
 return `<h1>${esc(L('returns'))}</h1><div class="row"><button data-act="prep" data-t="GSTR3B" data-p="${per}">Prepare GSTR-1 + 3B for ${per}</button></div>
 <div class="card">${table([{h:'Return',f:r=>`<a href="#return/${r.id}">${r.return_type} ${r.period}</a>`},{h:'Status',f:r=>statusPill(r.status)},{h:'Cash payable',r:1,f:r=>r.net_cash!=null?money(r.net_cash):''},{h:'Due',f:r=>r.due_date||''},{h:'Ack',f:r=>esc(r.ack_number||'')}],rs)}</div>`};
ACT.prep=async d=>{const r=await api(B('/returns/prepare'),{body:{return_type:d.t,period:d.p}});toast('Draft prepared');location.hash='#return/'+r.return_id};
R.return=async id=>{const r=await api('/api/returns/'+id);const c=r.computed,p=r.proof,ex=r.explanation||{};const ap=r.approval;
 let body=`<h1>${r.return_type} ${r.period} ${statusPill(r.status)}</h1>`;let act='';
 if(r.status==='filed_simulated')act=`<div class="card"><b>Filed (simulated)</b> — acknowledgement <code>${esc(r.ack_number)}</code> on ${esc((r.filed_at||'').slice(0,10))}</div>`;
 else if(r.status==='approved')act=`<div class="card"><h3>Ready to file (simulated)</h3><p class="mute">A human files it on the mock portal with an OTP. The agent cannot do this.</p><button data-act="file" data-id="${id}">File now…</button></div>`;
 else if(r.status==='awaiting_accountant')act=`<div class="card">${pill('With your accountant','info')} They will approve it in their console.</div>`;
 else act=`<div class="card"><h3>Your decision</h3><div class="row">${ap&&ap.status==='pending'?`<button data-act="decide" data-id="${ap.id}" data-d="approved" data-s="${r.return_type} ${r.period}${c.net_cash!=null?': amount payable '+money(c.net_cash):''}">Approve</button><button class="ghost" data-act="toacc" data-id="${ap.id}">Send to accountant</button>`:''}<button class="ghost" data-act="wrong" data-id="${id}">Something is wrong</button><a class="btn ghost" href="#chat">Ask a question</a><button class="ghost" data-act="recompute" data-t="${r.return_type}" data-p="${r.period}">Recompute</button></div></div>`;
 const txt=ex[S.lang]||ex.en||'';
 body+=act+`<div class="card"><h3>In plain words</h3><p>${esc(txt)}</p><a href="#" data-act="read" data-t="${esc(txt)}">🔊 Read aloud</a></div>`;
 if(r.return_type==='GSTR3B')body+=`<div class="grid"><div class="card"><div class="mute">Cash to pay</div><div class="kpi">${money(c.net_cash)}</div><div class="mute">due ${c.due_date}${c.late&&c.late.days_late?` · late fee ${money(c.late.late_fee)}, interest ${money(c.late.interest)}`:''}</div></div>
  <div class="card"><div class="mute">Output tax</div><div class="kpi">${money(c.outward.tax)}</div><div class="mute">ITC used ${money(c.itc.total)}${c.prev_net_cash!=null?` · last period paid ${money(c.prev_net_cash)}`:''}</div></div>
  <div class="card"><div class="mute">Credit stuck</div><div class="kpi">${money(c.itc.stuck||0)}</div><a href="#suppliers">See why</a></div></div>`;
 else if(r.return_type==='GSTR1'){const t=c.totals;body+=`<div class="grid"><div class="card"><div class="mute">Sales taxable</div><div class="kpi">${money(t.taxable)}</div></div><div class="card"><div class="mute">GST collected</div><div class="kpi">${money(t.tax)}</div></div><div class="card"><div class="mute">Invoices</div><div class="kpi">${t.invoices}</div></div></div>`}
 body+=`<div class="card"><h3>Proof</h3><div class="row"><a class="btn small" target="_blank" href="/api/returns/${id}/proof?token=${TOKEN}">Open full proof pack</a></div>
 <h3 style="margin-top:12px">Calculation trace</h3>${table([{h:'Step',f:t=>esc(t.step)},{h:'Amount',r:1,f:t=>typeof t.value==='number'?money(t.value):''},{h:'Rule',f:t=>esc(t.rule||'')}],p.trace)}
 ${p.exclusions.length?`<h3 style="margin-top:12px">Not claimed</h3>${table([{h:'Record',f:e=>esc(e.label||'')},{h:'Why',f:e=>esc(e.reason)},{h:'Amount',r:1,f:e=>money(e.amount)}],p.exclusions)}`:''}
 <h3 style="margin-top:12px">Checks</h3>${p.checks.map(k=>`<div>${k.ok?'✅':'⚠️'} ${esc(k.check)}: ${esc(k.detail)}</div>`).join('')}</div>`;
 return body};
ACT.recompute=async d=>{await api(B('/returns/prepare'),{body:{return_type:d.t,period:d.p}});toast('Recomputed');route()};
ACT.wrong=async d=>{const t=await promptBox('Which line looks wrong? Tell me and I will reopen the record.');if(!t)return;location.hash='#chat';setTimeout(()=>{$('#cin').value='Something is wrong in my return: '+t;ACT.send()},500)};
ACT.file=async d=>{const o=await api(`/api/returns/${d.id}/file/otp`,{method:'POST'});const otp=await promptBox(`Mock portal OTP sent (demo OTP: ${o.demo_otp}). Enter it to file:`,o.demo_otp);if(!otp)return;const r=await api(`/api/returns/${d.id}/file`,{body:{otp}});toast('Filed (simulated). Ack '+r.ack_number,6000);route()};

// ---------- e-way bills ----------
R.ewb=async()=>{const d=await api(B('/ewb'));
 return `<h1>${esc(L('ewb'))}</h1><p class="mute">The agent catches every qualifying dispatch, prepares Part A, asks the transporter for Part B, and blocks mismatches before the truck leaves.</p>
 ${d.unprepared_invoices.map(i=>`<div class="card row">${esc(i.invoice_no)} ${money(i.total)} needs an e-way bill <span class="sp"></span><button data-act="ewbprep" data-i="${i.id}">Prepare</button></div>`).join('')}
 ${d.bills.map(e=>{const a=e.part_a;return `<div class="card"><div class="row"><b>${esc(e.invoice_no)} → ${esc(e.buyer||'')}</b> ${statusPill(e.status)}<span class="sp"></span><span class="kpi" style="font-size:18px">${money(e.total)}</span></div>
 <div class="mute">PIN ${esc(a.from_pin)} → ${esc(a.to_pin)} · ${e.distance_km||'?'} km · HSN ${esc(a.hsn)} · transporter ${esc(e.transporter?e.transporter.name:'unknown')} · vehicle ${esc(e.vehicle_no||'—')}</div>
 ${e.ewb_number?`<div>E-way bill <b>${e.ewb_number}</b> valid until ${esc(e.valid_until.slice(0,16).replace('T',' '))} ${e.hours_left!=null?pill(e.hours_left>0?Math.round(e.hours_left)+' h left':'expired',e.hours_left<12?'bad':'ok'):''}</div>`:''}
 ${e.issues.length?`<div class="q"><b>Blocked — fix before dispatch:</b>${e.issues.map(i=>`<div>${esc(i.field)}: draft <b>${esc(i.ewb)}</b> ≠ invoice <b>${esc(i.invoice)}</b></div>`).join('')}<button class="small" data-act="ewbrefresh" data-e="${e.id}">Refresh Part A from invoice</button></div>`:''}
 <div class="row" style="margin-top:8px">${!e.ewb_number?`<input id="veh${e.id}" placeholder="Vehicle e.g. ka 05 ab 1234" style="max-width:220px" value="${esc(e.vehicle_no||'')}"><button class="small ghost" data-act="ewbveh" data-e="${e.id}">Set vehicle</button><button class="small" data-act="ewbgen" data-e="${e.id}" data-n="${esc(e.invoice_no)}" data-v="${money(e.total)}" ${e.issues.length||!e.vehicle_no?'disabled':''}>Approve & generate (simulated)</button>`:`<button class="small ghost" data-act="ewbext" data-e="${e.id}">Extend validity</button><button class="small danger" data-act="ewbheld" data-e="${e.id}">Truck stopped!</button>`}</div></div>`}).join('')||'<div class="card mute">No e-way bills yet.</div>'}`};
ACT.ewbprep=async d=>{await api(B('/ewb/prepare'),{body:{invoice_id:+d.i}});route()};
ACT.ewbrefresh=async d=>{const r=await api(B(`/ewb/${d.e}/refresh`),{method:'POST'});toast(r.issues.length?'Still blocked':'Part A now matches the invoice');route()};
ACT.ewbveh=async d=>{const r=await api(B(`/ewb/${d.e}/vehicle`),{body:{text:$('#veh'+d.e).value}});toast(r.ok?'Vehicle '+r.vehicle:r.message);route()};
ACT.ewbgen=async d=>{if(!(await confirmBox(`Generate e-way bill for ${d.n} worth ${d.v}? (simulated portal)`)))return;const r=await api(B(`/ewb/${d.e}/generate?approve=true`),{method:'POST'});toast(r.result&&r.result.ewb_number?'E-way bill '+r.result.ewb_number+'. Documents sent to driver and buyer.':JSON.stringify(r.result||r),6000);route()};
ACT.ewbext=async d=>{await api(B(`/ewb/${d.e}/extend?approve=true`),{body:{}});toast('Extended (simulated)');route()};
ACT.ewbheld=async d=>{const p=await api(B(`/ewb/${d.e}/held`));await modal(`<h3>${esc(p.title)}</h3><pre>${esc(JSON.stringify(p,null,2))}</pre><p class="mute">Sent to the driver and your accountant (simulated).</p><button data-v="ok">Close</button>`)};

// ---------- suppliers / reconciliation ----------
R.suppliers=async()=>{const per=(await api(B('/home'))).period;const [rc,sp]=await Promise.all([api(B('/recon?period='+per)),api(B('/suppliers'))]);
 return `<h1>${esc(L('suppliers'))} & input credit</h1><div class="grid"><div class="card"><div class="mute">ITC at risk (${per})</div><div class="kpi">${money(rc.itc_at_risk)}</div></div><div class="card"><div class="row"><button data-act="applyrec" data-p="${per}">Approve all recommended IMS actions</button><button class="ghost" data-act="refrec" data-p="${per}">Refresh from portal</button></div><p class="mute">Applies Accept / Pending / Reject on the portal after your approval.</p></div></div>
 <div class="card">${table([{h:'Supplier',f:i=>esc(i.party_name||'')},{h:'Invoice',f:i=>esc(i.inv_no)},{h:'Books',r:1,f:i=>i.book_taxable!=null?money(i.book_taxable):'—'},{h:'Supplier filed',r:1,f:i=>i.p_taxable!=null?money(i.p_taxable):'—'},{h:'Status',f:i=>statusPill(i.match_status)},{h:'ITC at risk',r:1,f:i=>money(i.itc_at_risk)},{h:'Recommended',f:i=>`<b>${esc(String(i.recommended_action).replace('_',' '))}</b><div class="mute">${esc(i.reason)}</div>${i.decided_action?pill('applied: '+i.decided_action,'ok'):''}${i.supplier_reply?`<div class="mute">Supplier replied: “${esc(i.supplier_reply)}”</div>`:''}`},{h:'',f:i=>['missing_in_2b','value_mismatch','gstin_mismatch'].includes(i.match_status)?`<button class="small" data-act="nudge" data-i="${i.id}" data-n="${esc(i.party_name)}">Nudge on WhatsApp</button>`:(i.match_status==='missing_in_books'?`<button class="small ghost" data-act="ims" data-i="${i.id}" data-p="${per}">Apply</button>`:'')}],rc.items.filter(i=>i.match_status!=='matched'||i.itc_at_risk>0))}
 <p class="mute">${rc.items.filter(i=>i.match_status==='matched'&&!i.itc_at_risk).length} other invoices matched cleanly.</p></div>
 <h2>Supplier reliability (last 6 periods)</h2><div class="card">${table([{h:'Supplier',f:s=>esc(s.name)},{h:'Score',r:1,f:s=>s.reliability_score!=null?s.reliability_score+'%':'—'},{h:'Summary',f:s=>esc(s.summary)}],sp)}</div>`};
ACT.applyrec=async d=>{if(!(await confirmBox('Apply all recommended IMS actions on the (simulated) portal?')))return;const r=await api(B('/recon/apply'),{body:{period:d.p}});toast(`Applied ${r.applied} action(s)`);route()};
ACT.refrec=async d=>{await api(B('/recon?refresh=true&period='+d.p));toast('Refreshed from portal');route()};
ACT.nudge=async d=>{if(!(await confirmBox(`Send a WhatsApp nudge to ${d.n}? (fixed template, identified as Ganaka on your behalf)`,'Send')))return;await api(B(`/recon/${d.i}/nudge?send=true`),{method:'POST'});toast('Nudge sent. See the WhatsApp simulator.');route()};
ACT.ims=async d=>{await api(B('/recon/apply'),{body:{period:d.p,item_ids:[+d.i]}});toast('Done');route()};

// ---------- calendar / docs / notices / more / settings ----------
R.calendar=async()=>{const c=await api(B('/calendar'));return `<h1>${esc(L('calendar'))}</h1><div class="card">${table([{h:'Due',f:o=>o.due_date},{h:'Obligation',f:o=>esc(o.label)},{h:'Status',f:o=>statusPill(o.status)},{h:'Days',r:1,f:o=>o.days_left},{h:'Late fee so far',r:1,f:o=>o.late_fee_so_far?money(o.late_fee_so_far):''}],c.filter(o=>o.days_left>-45||o.status!=='done'))}</div>`};
R.docs=async()=>{const v=await api(B('/vault'));return `<h1>${esc(L('docs'))}</h1><p class="mute">Upload a licence (text) in the Inbox to read its expiry date; reminders go out 60/30/7 days before.</p><div class="card">${table([{h:'Document',f:d=>esc(d.doc_type)},{h:'Number',f:d=>esc(d.number||'')},{h:'Expiry',f:d=>d.expiry_date},{h:'',f:d=>pill(d.state==='ok'?d.days_left+' days':d.state+' ('+d.days_left+' d)',d.state==='ok'?'ok':d.state==='expired'?'bad':'warn')}],v)}</div>`};
R.notices=async()=>{const d=await api(B('/notices'));
 return `<h1>${esc(L('notices'))} & risk</h1><div class="row"><button class="ghost" data-act="riskscan">Run risk scan now</button></div><h2>Risk warnings (before a notice arrives)</h2><div class="card">${table([{h:'Level',f:r=>statusPill(r.level)},{h:'Finding',f:r=>esc(r.detail)},{h:'Impact',r:1,f:r=>money(r.rupee_impact)},{h:'Fix',f:r=>esc(r.fix)}],d.risk)}</div>
 <h2>Notices received</h2>${d.notices.map(n=>{const e=(n.explanation||{})[S.lang]||(n.explanation||{}).en||{};const en=(n.explanation||{}).en||{};return `<div class="card"><b>${esc(n.notice_type)}</b> ${pill(n.status)} <span class="mute">ref ${esc(n.reference_no)} · reply by ${n.reply_due_date}</span><p>${esc(e.what||'')} ${esc(e.why||'')}<br>${esc(e.deadline||'')}</p>${en.documents?`<div class="mute">Documents for accountant: ${en.documents.map(esc).join(', ')}</div>`:''}</div>`}).join('')||'<div class="card mute">No notices. Forward one in the Inbox to see it explained.</div>'}`};
ACT.riskscan=async()=>{await api(B('/risk/scan'),{method:'POST'});route()};
R.more=async()=>{const [t,x,im]=await Promise.all([api(B('/tds')),api(B('/extras')),api(B('/impact'))]);
 return `<h1>${esc(L('more'))}</h1><div class="grid"><div class="card"><h3>Impact so far</h3><div class="kpi">${im.hours_saved_estimate} h</div><div class="mute">saved (estimate) · ${esc(im.assumptions)}</div><div>ITC found at risk <b>${money(im.itc_at_risk_found)}</b>, recovered <b>${money(im.itc_recovered)}</b></div><div>E-way bill errors caught before dispatch: <b>${im.ewb_errors_caught}</b></div><div>Deadlines met: <b>${im.deadlines_met}</b> (≈ ${money(im.late_fee_avoided_estimate)} late fees avoided)</div></div>
 <div class="card"><h3>TDS</h3><p>${esc(t.applicability.text)}</p>${t.deducted_from_us.length?`<button class="small" data-act="m26">Match with Form 26AS</button><div id="m26res"></div>`:''}</div></div>
 ${t.deducted_by_us.length?`<div class="card"><h3>TDS to deduct</h3>${table([{h:'Party',f:r=>esc(r.party)},{h:'Section',f:r=>r.section},{h:'TDS',r:1,f:r=>money(r.tds_amount)}],t.deducted_by_us)}</div>`:''}
 <div class="card"><h3>Overdue receivables (43B(h))</h3>${table([{h:'Buyer',f:r=>esc(r.party)},{h:'Invoice',f:r=>esc(r.invoice_no)},{h:'Outstanding',r:1,f:r=>money(r.outstanding)},{h:'Age',r:1,f:r=>r.age_days+' d'},{h:'',f:r=>`<button class="small ghost" data-act="chase" data-i="${r.invoice_id}">Draft reminder</button>`}],x.receivables)}</div>
 <div class="grid"><div class="card"><h3>Payroll (PF / ESI / PT)</h3>${table([{h:'Employee',f:e=>esc(e.name)},{h:'PF',r:1,f:e=>money(e.pf)},{h:'ESI',r:1,f:e=>money(e.esi)},{h:'PT',r:1,f:e=>money(e.pt)}],x.payroll.employees)}<div class="mute">PF applies at ≥20 employees, ESI at ≥10 (config): ${x.payroll.pf_applicable?'':'not '}applicable here.</div></div>
 <div class="card"><h3>Income tax: Section 44AD estimate</h3><div class="kpi">${money(x.presumptive.estimated_presumptive_income)}</div><div class="mute">on turnover ${money(x.presumptive.turnover_to_date)}. ${esc(x.presumptive.tip)}</div></div>
 <div class="card"><h3>Unexplained bank payments</h3>${x.unmatched_bank.map(b=>`<div>${b.date} ${money(b.amount)} ${esc(b.narration)}</div>`).join('')||'<span class="mute">None</span>'}</div></div>`};
ACT.m26=async()=>{const r=await api(B('/tds/match-26as'),{method:'POST'});$('#m26res').innerHTML=`<p>TDS credit available: <b>${money(r.tds_credit_available)}</b></p>`+r.flags.map(f=>`<div class="q">${esc(f.kind.replace(/_/g,' '))}: ${esc(f.party||'')} ${f.invoice?esc(f.invoice):''} ${f.ours?'ours '+money(f.ours):''} ${f['26as']?'26AS '+money(f['26as']):''}</div>`).join('')+'<p class="mute">Draft messages to customers are in Approvals.</p>'};
ACT.chase=async d=>{await api(B(`/receivables/${d.i}/chase`),{method:'POST'});toast('Reminder drafted. Approve it in Approvals.')};
R.settings=async()=>{const s=await api(B('/settings'));const T={m_transporter_partb:'Ask transporter for vehicle number',m_doc_pack:'Send document pack to driver',m_buyer_copy:'Send invoice + e-way bill to buyer',m_ewb_expiry:'Warn transporter about expiry',ewb_generate:'Auto-generate valid e-way bills (up to a value, ₹)'};
 const pre=Object.fromEntries(s.preapprovals.map(p=>[p.template_id,p]));
 return `<h1>${esc(L('settings'))}</h1><div class="card"><h3>Standing pre-approvals (low-risk only, revocable)</h3>${Object.entries(T).map(([k,v])=>`<div class="row"><label style="flex:1"><input type="checkbox" style="width:auto" ${pre[k]&&pre[k].active?'checked':''} data-pre="${k}"> ${esc(v)}</label>${k==='ewb_generate'?`<input style="max-width:120px" placeholder="max ₹" id="premax" value="${pre[k]&&pre[k].max_value?pre[k].max_value/100:''}">`:''}</div>`).join('')}<p class="mute">Returns, IMS actions, and messages to suppliers always need your approval.</p></div>
 <div class="card"><h3>Consents (DPDP)</h3>${['gmail_read','whatsapp','bank_upload'].map(sc=>{const on=s.consents.some(c=>c.scope===sc&&!c.revoked_at);return `<div class="row"><span style="flex:1">${sc.replace('_',' ')}</span>${on?pill('granted','ok'):pill('off')}<button class="small ghost" data-act="consent" data-s="${sc}" data-g="${on?0:1}">${on?'Revoke':'Grant'}</button></div>`}).join('')}</div>
 <div class="card"><h3>Who has access</h3>${table([{h:'Name',f:m=>esc(m.name)},{h:'Role',f:m=>m.role},{h:'',f:m=>m.revoked_at?pill('revoked','bad'):(m.role==='accountant'&&S.role==='owner'?`<button class="small danger" data-act="revoke" data-m="${m.id}">Revoke</button>`:pill('active','ok'))}],s.members)}</div>
 <div class="card"><h3>Audit trail</h3><a href="#" data-act="audit">View recent actions</a></div>`};
document.addEventListener('change',async e=>{const k=e.target.dataset&&e.target.dataset.pre;if(!k)return;const mx=k==='ewb_generate'?(Math.round((+($('#premax')?.value||0))*100)||null):null;await api(B('/preapprovals'),{method:'PUT',body:{template_id:k,active:e.target.checked,max_value:mx}});toast('Saved')});
ACT.consent=async d=>{await api(B('/consents'),{method:'PUT',body:{scope:d.s,granted:d.g==='1'}});route()};
ACT.revoke=async d=>{if(!(await confirmBox('Revoke this accountant\'s access?','Revoke')))return;await api(B(`/members/${d.m}/revoke`),{method:'POST'});route()};
ACT.audit=async()=>{const a=await api(B('/audit'));await modal(`<h3>Audit trail (append-only)</h3><div style="max-height:50vh;overflow:auto">${table([{h:'When',f:x=>x.at.slice(0,16).replace('T',' ')},{h:'Actor',f:x=>x.actor_type},{h:'Action',f:x=>esc(x.action)}],a)}</div><button data-v="ok">Close</button>`)};
boot();
