const pptxgen=require('pptxgenjs');
const React=require('react');const RDS=require('react-dom/server');
const sharp=require('sharp');
const fa=require('react-icons/fa');
const {applyTheme}=require('C:/Users/jival/.claude/skills/synced/3a7ee9be-4599-454e-98e1-0e650b3cee92_8953c25d-25db-44fa-aa8d-0641b2696c00/pptx/scripts/apply_theme.js');

const THEME={name:'Ganaka',headFontFace:'Cambria',bodyFontFace:'Calibri',colors:{
 dk1:'0B2B26',lt1:'FFFFFF',dk2:'14463D',lt2:'EEF5F2',
 accent1:'1B9A78',accent2:'F5A623',accent3:'D64545',accent4:'3B7F8C',accent5:'A9DCCB',accent6:'5E716B',hlink:'1B9A78',folHlink:'5E716B'}};
const HEX={dk1:'0B2B26',lt1:'FFFFFF',dk2:'14463D',lt2:'EEF5F2',a1:'1B9A78',a2:'F5A623',a3:'D64545',a5:'A9DCCB',a6:'5E716B'};

const pres=new pptxgen();pres.layout='LAYOUT_16x9';pres.theme={headFontFace:'Cambria',bodyFontFace:'Calibri'};
pres.title='Ganaka - Simplifying Compliance. Empowering Businesses.';pres.author='Ganaka';
const C=pres.SchemeColor;
const SHOTS='shots/';

async function icon(name,hex,size=256){
  const svg=RDS.renderToStaticMarkup(React.createElement(fa[name],{color:'#'+hex,size:String(size)}));
  const b=await sharp(Buffer.from(svg)).resize(size,size,{fit:'contain',background:{r:0,g:0,b:0,alpha:0}}).png().toBuffer();
  return 'image/png;base64,'+b.toString('base64');
}

// ---- layouts
pres.defineSlideMaster({title:'TITLE_DARK',background:{color:C.text1},objects:[],
 slideNumber:undefined});
pres.defineSlideMaster({title:'CONTENT_DARK',background:{color:C.text1},objects:[
 {placeholder:{options:{name:'title',type:'title',x:0.5,y:0.35,w:9,h:0.8,fontSize:32,bold:true,color:C.background1,align:'left',valign:'middle',margin:0},text:''}}],
 slideNumber:{x:9.0,y:5.28,w:0.5,h:0.25,fontSize:10,color:C.accent5,align:'right'}});
pres.defineSlideMaster({title:'CONTENT',background:{color:C.background1},objects:[
 {placeholder:{options:{name:'title',type:'title',x:0.5,y:0.35,w:9,h:0.8,fontSize:32,bold:true,color:C.text1,align:'left',valign:'middle',margin:0},text:''}}],
 slideNumber:{x:9.0,y:5.28,w:0.5,h:0.25,fontSize:10,color:C.accent6,align:'right'}});

// ---- helpers
const tb=(s,text,o)=>s.addText(text,Object.assign({isTextBox:true,margin:0,valign:'top'},o));
const rr=(s,x,y,w,h,fill,o={})=>s.addShape(pres.ShapeType.roundRect,Object.assign({x,y,w,h,fill:{color:fill},line:{color:fill,width:0},rectRadius:0.12},o));
async function circ(s,ic,x,y,d,bg,fg,name){
  s.addShape(pres.ShapeType.ellipse,{x,y,w:d,h:d,fill:{color:bg},line:{color:bg,width:0},objectName:name||'icon-bg'});
  const p=d*0.5;s.addImage({data:await icon(ic,fg),x:x+(d-p)/2,y:y+(d-p)/2,w:p,h:p,altText:'icon',objectName:'icon'});
}
const arrow=(s,x1,y1,x2,y2,color)=>s.addShape(pres.ShapeType.line,{x:Math.min(x1,x2),y:Math.min(y1,y2),w:Math.abs(x2-x1),h:Math.abs(y2-y1),line:{color,width:2,endArrowType:'triangle'},flipV:y2<y1,flipH:x2<x1});
const chip=(s,text,x,y,w,fill,fg,fs=10)=>{rr(s,x,y,w,0.26,fill,{rectRadius:0.13});tb(s,text,{x,y,w,h:0.26,fontSize:fs,bold:true,color:fg,align:'center',valign:'middle'});};

(async()=>{
const N=(s,t)=>s.addNotes(t);

// 1 TITLE
pres.addSection({title:'Opening'});
let s=pres.addSlide({masterName:'TITLE_DARK',sectionTitle:'Opening'});
tb(s,'Ganaka',{x:0.6,y:1.35,w:6.4,h:1.2,fontSize:64,bold:true,fontFace:'Cambria',color:C.background1,valign:'middle'});
tb(s,'Simplifying Compliance.\nEmpowering Businesses.',{x:0.6,y:2.65,w:6.4,h:1.0,fontSize:24,color:C.accent2,bold:true});
tb(s,"An agentic AI compliance assistant for India's micro business owners",{x:0.6,y:3.95,w:6.0,h:0.7,fontSize:16,color:C.accent5});
const motif=[['FaFileInvoiceDollar',1.0],['FaTruck',2.35],['FaWhatsapp',3.7]];
for(const [ic,y] of motif){await circ(s,ic,7.55,y,1.15,C.accent1,'FFFFFF');}
for(const [ic,y] of [['FaLanguage',1.65],['FaRupeeSign',3.0]]){await circ(s,ic,8.45,y,0.8,C.dark2||C.accent4,'FFFFFF');}
N(s,'Opening. Ganaka is an agentic AI compliance assistant for micro business owners. Name and tagline: Simplifying Compliance. Empowering Businesses.');

// 2 PROBLEM NUMBERS
pres.addSection({title:'Problem'});
s=pres.addSlide({masterName:'CONTENT_DARK',sectionTitle:'Problem'});
s.addText('Compliance quietly drains owners',{placeholder:'title'});
tb(s,'Micro business owners are the backbone of the economy, and they carry the heaviest compliance load.',{x:0.5,y:1.1,w:9,h:0.35,fontSize:14,color:C.accent5});
const stats=[['FaHourglassHalf','15–20 hrs','every month on GST, TDS and e-way bill paperwork'],
 ['FaRupeeSign','₹1,500–3,000','paid to an accountant for every filing'],
 ['FaPercent','8–12%','of annual profit eaten up by compliance'],
 ['FaTruck','Up to 200%','of the tax as penalty when goods are held for a missing or invalid e-way bill']];
for(let i=0;i<4;i++){const x=0.5+(i%2)*4.6,y=1.6+Math.floor(i/2)*1.45;
 rr(s,x,y,4.4,1.3,C.accent6===undefined?C.text2:C.text2,{objectName:'stat-card'});
 await circ(s,stats[i][0],x+0.2,y+0.35,0.6,C.accent2,HEX.dk1);
 tb(s,stats[i][1],{x:x+1.0,y:y+0.1,w:3.3,h:0.6,fontSize:32,bold:true,fontFace:'Cambria',color:C.accent2,valign:'middle'});
 tb(s,stats[i][2],{x:x+1.0,y:y+0.72,w:3.25,h:0.5,fontSize:12,color:C.background1});}
rr(s,0.5,4.55,9,0.62,C.accent1,{objectName:'strip'});
tb(s,'On top of that: late fees and interest, input credit lost to a supplier’s bad filing, and goods stopped at checkpoints, often for mistakes they never knew they were making.',{x:0.7,y:4.55,w:8.6,h:0.62,fontSize:13,color:C.background1,valign:'middle'});
N(s,'Numbers from the brief: 15-20 hours a month, Rs 1,500-3,000 per filing, compliance can eat 8-12% of annual profit, and a missing or invalid e-way bill can cost a penalty of up to 200% of the tax. Replace with field-interview figures when available.');

// STORIES
pres.addSection({title:'Stories'});
const stories=[
 {tag:'STORY 1 · LATE FILING',title:'Lakshmi missed the due date',ic:'FaCalendarTimes',name:'Lakshmi Textiles',lines:['Jaipur · textile trader','Quarterly (QRMP) filer','Bills in WhatsApp, email and paper'],
  steps:['Bills lived in WhatsApp chats, email and a drawer. Collecting them took most of the month.','Her accountant waited on the last few invoices while juggling dozens of other clients.','The due date passed. She found out 12 days later, when the portal showed the return as pending.'],
  big:'₹600+',desc:'late fee at ₹50 a day for 12 days, plus 18% a year interest on the tax due',tail:'A mistake she never knew she was making',
  note:'Story 1, illustrative composite. Late fee of Rs 50/day (Rs 25 CGST + Rs 25 SGST) and 18% p.a. interest are standard GST rules; have a CA verify before external use.'},
 {tag:'STORY 2 · E-WAY BILL',title:'Ramesh’s truck was stopped',ic:'FaTruck',name:'Ramesh Hardware',lines:['Bengaluru · hardware trader','Ships to buyers in other states','Keys e-way bills by hand'],
  steps:['He sent ₹72,000 of fasteners (HSN 7318) to Mumbai and keyed the e-way bill by hand.','The bill said HSN 7317 and had no vehicle number. Nobody had asked the transporter.','The truck was stopped at a checkpoint and the goods were detained.'],
  big:'₹25,920',desc:'maximum penalty: 200% of ₹12,960 GST (18% on ₹72,000), plus days of truck waiting',tail:'Caught only after the truck left',
  note:'Story 2, illustrative composite, matching the demo case (HSN mismatch on a Rs 72,000 inter-state sale). Penalty shown is the upper bound at 18% GST.'},
 {tag:'STORY 3 · LOST CREDIT',title:'Anita’s credit never arrived',ic:'FaStore',name:'Anita General Stores',lines:['Hyderabad · retail and wholesale','Buys from many small suppliers','Pays GST on every purchase bill'],
  steps:['She bought ₹1,00,000 of goods from Ravi Traders and paid the GST on the invoice.','Ravi never filed his GSTR-1, so the invoice never showed up in her GSTR-2B.','Nobody told her. She found out when the credit was denied and a notice followed.'],
  big:'₹18,000',desc:'input credit lost: GST paid to the supplier, but not claimable from the government',tail:'Paid twice, noticed late',
  note:'Story 3, illustrative composite, matching the Ravi Traders INV-1043 demo case (Rs 1,00,000 at 18%).'}];
for(let i=0;i<3;i++){const st=stories[i];
 s=pres.addSlide({masterName:'CONTENT',sectionTitle:'Stories'});
 s.addText(st.title,{placeholder:'title'});
 chip(s,st.tag,7.2,0.5,2.3,HEX.a2,HEX.dk1,10.5);
 // persona
 rr(s,0.5,1.4,2.7,3.6,C.background2,{objectName:'persona-card'});
 await circ(s,st.ic,1.4,1.6,0.9,C.accent1,'FFFFFF');
 tb(s,st.name,{x:0.65,y:2.65,w:2.4,h:0.4,fontSize:17,bold:true,color:C.text1,align:'center'});
 tb(s,st.lines.join('\n'),{x:0.65,y:3.1,w:2.4,h:1.2,fontSize:12,color:C.text2,align:'center',paraSpaceAfter:4});
 tb(s,'Illustrative composite',{x:0.65,y:4.6,w:2.4,h:0.25,fontSize:10,italic:true,color:C.accent6===undefined?C.text2:C.text2,align:'center'});
 // steps
 tb(s,'WHAT HAPPENED',{x:3.5,y:1.4,w:3.3,h:0.25,fontSize:11,bold:true,color:C.accent1});
 for(let k=0;k<3;k++){const y=1.75+k*1.08;
  s.addShape(pres.ShapeType.ellipse,{x:3.5,y:y+0.05,w:0.42,h:0.42,fill:{color:C.text1},line:{color:C.text1,width:0}});
  tb(s,String(k+1),{x:3.5,y:y+0.05,w:0.42,h:0.42,fontSize:14,bold:true,color:C.background1,align:'center',valign:'middle'});
  tb(s,st.steps[k],{x:4.05,y,w:2.75,h:1.0,fontSize:13,color:C.text1});}
 // cost
 rr(s,7.1,1.4,2.4,3.6,C.text1,{objectName:'cost-card'});
 tb(s,'THE BILL',{x:7.3,y:1.6,w:2.0,h:0.25,fontSize:11,bold:true,color:C.accent5});
 tb(s,st.big,{x:7.3,y:1.95,w:2.05,h:0.75,fontSize:34,bold:true,fontFace:'Cambria',color:C.accent2,valign:'middle'});
 tb(s,st.desc,{x:7.3,y:2.8,w:2.0,h:1.3,fontSize:12,color:C.background1});
 tb(s,st.tail,{x:7.3,y:4.2,w:2.0,h:0.65,fontSize:12,italic:true,color:C.accent5});
 N(s,st.note);}

// 6 WHAT IS GANAKA
pres.addSection({title:'Solution'});
s=pres.addSlide({masterName:'CONTENT',sectionTitle:'Solution'});
s.addText('Meet Ganaka',{placeholder:'title'});
tb(s,'An agentic AI compliance assistant that lifts the compliance burden off owners.',{x:0.5,y:1.25,w:9,h:0.7,fontSize:20,color:C.text2});
const pill=[['FaInbox','Collect','Gathers bills from WhatsApp, Gmail and uploads into one trusted ledger.'],
 ['FaFileInvoiceDollar','Prepare','Drafts GST returns, recovers lost input credit, flags TDS and readies e-way bills before goods leave.'],
 ['FaLanguage','Explain','Tells the owner everything in their own language, by text and by voice.']];
for(let i=0;i<3;i++){const x=0.5+i*3.05;
 rr(s,x,2.15,2.9,2.15,C.background2,{objectName:'pillar-card'});
 await circ(s,pill[i][0],x+0.2,2.35,0.7,C.accent1,'FFFFFF');
 tb(s,pill[i][1],{x:x+1.05,y:2.35,w:1.7,h:0.7,fontSize:22,bold:true,fontFace:'Cambria',color:C.text1,valign:'middle'});
 tb(s,pill[i][2],{x:x+0.2,y:3.2,w:2.5,h:1.0,fontSize:13,color:C.text1});}
rr(s,0.5,4.5,9,0.65,C.text1,{objectName:'banner'});
tb(s,'Ganaka does the work. The owner stays in control of every decision.',{x:0.7,y:4.5,w:8.6,h:0.65,fontSize:18,bold:true,color:C.accent2,valign:'middle',align:'center'});
N(s,'Ganaka collects, prepares and explains. It never files and never decides for the owner.');

// 7 INGEST
pres.addSection({title:'Product'});
s=pres.addSlide({masterName:'CONTENT',sectionTitle:'Product'});
s.addText('From scattered bills to one ledger',{placeholder:'title'});
const src=[['FaWhatsapp','WhatsApp','Forward a photo or PDF'],['FaEnvelope','Gmail','Invoices in the inbox'],['FaCloudUploadAlt','Upload','App, camera, bank CSV'],['FaMicrophone','Voice','Say the details aloud']];
for(let i=0;i<4;i++){const y=1.4+i*0.95;
 rr(s,0.5,y,2.4,0.8,C.background2,{objectName:'source'});
 await circ(s,src[i][0],0.62,y+0.13,0.54,C.accent1,'FFFFFF');
 tb(s,src[i][1],{x:1.28,y:y+0.1,w:1.55,h:0.3,fontSize:15,bold:true,color:C.text1});
 tb(s,src[i][2],{x:1.28,y:y+0.42,w:1.6,h:0.3,fontSize:11,color:C.text2});
 arrow(s,2.9,y+0.4,3.5,y+0.4,HEX.a1);}
rr(s,3.5,1.4,2.9,3.65,C.text1,{objectName:'read-check'});
tb(s,'Read and check',{x:3.7,y:1.55,w:2.5,h:0.35,fontSize:17,bold:true,fontFace:'Cambria',color:C.accent2});
const chk=['Reads every bill and pulls out the fields','Checks GSTIN and tax maths in code','Removes duplicates across channels','Asks the owner when something is unclear'];
for(let i=0;i<4;i++){const y=2.1+i*0.72;
 s.addImage({data:await icon('FaCheckCircle',HEX.a5),x:3.7,y:y+0.03,w:0.26,h:0.26,altText:'check'});
 tb(s,chk[i],{x:4.1,y,w:2.15,h:0.65,fontSize:13,color:C.background1});}
arrow(s,6.4,3.22,7.0,3.22,HEX.a1);
rr(s,7.0,1.9,2.5,2.65,C.accent1,{objectName:'ledger'});
await circ(s,'FaBook',8.0,2.1,0.75,C.text1,HEX.a2);
tb(s,'One trusted ledger',{x:7.15,y:3.0,w:2.2,h:0.7,fontSize:19,bold:true,fontFace:'Cambria',color:C.background1,align:'center',valign:'middle'});
tb(s,'Purchases · Sales\nBank · Licences',{x:7.15,y:3.8,w:2.2,h:0.55,fontSize:12,color:C.background1,align:'center'});
N(s,'Ingestion: bills arrive by WhatsApp, Gmail and uploads; extraction and validation are deterministic checks in code; duplicates across channels are linked; unclear fields are asked back to the owner. In the prototype the extraction is a stub; a vision LLM plugs in behind the same schema.');

// 8 BRANCHES
s=pres.addSlide({masterName:'CONTENT',sectionTitle:'Product'});
s.addText('One ledger. Every obligation.',{placeholder:'title'});
const br=[['FaFileInvoiceDollar','GST returns','GSTR-1, 3B and CMP-08 drafted with a proof pack',['Owner','Accountant']],
 ['FaSearchDollar','Input credit','Matches books to GSTR-2B and nudges suppliers who have not filed',['Owner','Supplier']],
 ['FaTruck','E-way bills','Checked before dispatch; vehicle number from the transporter',['Owner','Driver']],
 ['FaPercent','TDS','Flags obligations and matches deductions with 26AS',['Owner','Accountant']],
 ['FaGavel','Notices','Explained in plain words, with a risk scan',['Owner','Accountant']],
 ['FaCalendarAlt','Calendar and rules','Due dates and rule changes, approved by a CA',['Accountant','Owner']]];
rr(s,3.8,1.25,2.4,3.76,C.accent1,{objectName:'ledger-hub'});
await circ(s,'FaBook',4.55,1.7,0.9,C.text1,HEX.a2);
tb(s,'One trusted ledger',{x:3.95,y:2.8,w:2.1,h:0.7,fontSize:19,bold:true,fontFace:'Cambria',color:C.background1,align:'center',valign:'middle'});
tb(s,'Single source of truth for every branch',{x:3.95,y:3.55,w:2.1,h:0.8,fontSize:12,color:C.background1,align:'center'});
for(let i=0;i<6;i++){const left=i<3;const row=i%3;const x=left?0.5:6.5,y=1.25+row*1.28;
 rr(s,x,y,3.0,1.2,C.background2,{objectName:'branch-card'});
 await circ(s,br[i][0],x+0.12,y+0.1,0.42,C.text1,HEX.a2);
 tb(s,br[i][1],{x:x+0.65,y:y+0.08,w:2.25,h:0.4,fontSize:14,bold:true,color:C.text1,valign:'middle'});
 tb(s,br[i][2],{x:x+0.15,y:y+0.5,w:2.75,h:0.38,fontSize:10.5,color:C.text2});
 let cx=x+0.15;for(const a of br[i][3]){const w=a.length*0.085+0.3;chip(s,a,cx,y+0.9,w,HEX.a5,HEX.dk1,10);cx+=w+0.08;}
 if(left)arrow(s,3.5,y+0.6,3.8,y+0.6,HEX.a1);else arrow(s,6.2,y+0.6,6.5,y+0.6,HEX.a1);}
N(s,'Six branches off the single ledger. Chips show which people are involved in each branch. Every output is a draft for approval: nothing is filed by the agent.');

// 9 ACTORS
s=pres.addSlide({masterName:'CONTENT',sectionTitle:'Product'});
s.addText('Ganaka works. People decide.',{placeholder:'title'});
const act=[['FaStore','Owner','Forwards bills, asks questions and approves every action.',0],
 ['FaRobot','Ganaka','Collects, calculates, drafts and explains. It has no filing tool.',1],
 ['FaUserTie','Accountant','Reviews drafts and risk flags, approves rule updates, files with OTP.',0],
 ['FaTruckMoving','Driver','Replies with the vehicle number on WhatsApp and gets the document pack.',0],
 ['FaIndustry','Supplier','Gets a polite WhatsApp nudge to file or fix an invoice.',0]];
for(let i=0;i<5;i++){const x=0.5+i*1.825,hl=act[i][3];
 rr(s,x,1.35,1.7,2.4,hl?C.accent1:C.background2,{objectName:'actor-card'});
 await circ(s,act[i][0],x+0.45,1.5,0.8,hl?C.text1:C.accent1,hl?HEX.a2:'FFFFFF');
 tb(s,act[i][1],{x:x+0.1,y:2.4,w:1.5,h:0.35,fontSize:16,bold:true,fontFace:'Cambria',color:hl?C.background1:C.text1,align:'center'});
 tb(s,act[i][2],{x:x+0.12,y:2.8,w:1.46,h:0.9,fontSize:11.5,color:hl?C.background1:C.text1,align:'center'});}
tb(s,'THE APPROVAL GATE',{x:0.5,y:3.95,w:4,h:0.25,fontSize:11,bold:true,color:C.accent1});
const flow=['Ganaka prepares','Owner approves','Accountant reviews','A human files with OTP'];
for(let i=0;i<4;i++){const x=0.5+i*2.33;
 rr(s,x,4.25,2.0,0.55,i===3?C.accent2:C.text1,{objectName:'flow-step'});
 tb(s,flow[i],{x,y:4.25,w:2.0,h:0.55,fontSize:13,bold:true,color:i===3?C.text1:C.background1,align:'center',valign:'middle'});
 if(i<3)arrow(s,x+2.0,4.525,x+2.33,4.525,HEX.a1);}
tb(s,'The agent never files. Every action is recorded in an append-only audit log.',{x:0.5,y:4.95,w:8,h:0.25,fontSize:11,italic:true,color:C.text2});
N(s,'Actors: owner, the Ganaka agent, accountant, driver or transporter, and supplier. The approval gate is enforced in code: agent modules cannot import the executor, and there is no filing tool.');

// 10 MULTILINGUAL
s=pres.addSlide({masterName:'CONTENT',sectionTitle:'Product'});
s.addText('Speaks the owner’s language',{placeholder:'title'});
const lang=[['EN','Calibri','Pay ₹18,702 by 20 November. ₹18,000 of your credit is stuck because Ravi Traders has not filed.'],
 ['हिंदी','Nirmala UI','20 नवंबर तक ₹18,702 जमा करें। ₹18,000 का क्रेडिट अटका है, क्योंकि रवि ट्रेडर्स ने फाइल नहीं किया।'],
 ['ಕನ್ನಡ','Nirmala UI','ನವೆಂಬರ್ 20 ರೊಳಗೆ ₹18,702 ಪಾವತಿಸಿ. ₹18,000 ಕ್ರೆಡಿಟ್ ಸಿಲುಕಿದೆ, ರವಿ ಟ್ರೇಡರ್ಸ್ ಫೈಲ್ ಮಾಡಿಲ್ಲ.']];
for(let i=0;i<3;i++){const y=1.4+i*1.12;
 rr(s,0.5,y,5.5,1.0,C.background2,{objectName:'bubble'});
 chip(s,lang[i][0],0.65,y+0.37,0.8,HEX.a1,'FFFFFF',11);
 tb(s,lang[i][2],{x:1.6,y:y+0.08,w:4.3,h:0.85,fontSize:13,fontFace:lang[i][1],color:C.text1,valign:'middle'});}
tb(s,'The same answer in three languages (illustrative).',{x:0.5,y:4.8,w:5.5,h:0.25,fontSize:11,italic:true,color:C.text2});
const ml=[['FaMicrophone','Voice in, answer read aloud','Owners can speak instead of typing.'],
 ['FaWhatsapp','App and WhatsApp','The same assistant on both channels.'],
 ['FaShieldAlt','Numbers are never invented','Every ₹ amount is checked against the ledger.'],
 ['FaLanguage','Built to grow','More Indian languages can be added next.']];
for(let i=0;i<4;i++){const y=1.4+i*0.92;
 await circ(s,ml[i][0],6.35,y+0.05,0.55,C.accent1,'FFFFFF');
 tb(s,ml[i][1],{x:7.05,y,w:2.45,h:0.3,fontSize:13,bold:true,color:C.text1});
 tb(s,ml[i][2],{x:7.05,y:y+0.3,w:2.45,h:0.55,fontSize:11.5,color:C.text2});}
N(s,'Languages in the prototype: English, Hindi and Kannada, by text and voice (browser speech, with Sarvam hooks ready). The Hindi and Kannada lines are illustrative translations: have a native speaker review them before presenting externally.');

// 11 UI
s=pres.addSlide({masterName:'CONTENT',sectionTitle:'Product'});
s.addText('How we are building it',{placeholder:'title'});
const ph=[['r_home.png','Home: tax due and credit at risk, shown in Kannada'],['r_chat.png','Chat: ask in any language, get a proof pack'],['r_ewb.png','E-way bill: blocked before the truck leaves']];
for(let i=0;i<3;i++){const x=0.55+i*2.0;
 rr(s,x-0.05,1.25,1.9,3.2,C.text1,{rectRadius:0.2,objectName:'phone-frame'});
 s.addImage({path:SHOTS+ph[i][0],x,y:1.3,w:1.8,h:1.8/780*1320,altText:ph[i][1]});
 tb(s,ph[i][1],{x:x-0.05,y:4.55,w:1.9,h:0.6,fontSize:11,color:C.text2});}
tb(s,'WORKING TODAY',{x:6.75,y:1.3,w:2.75,h:0.25,fontSize:11,bold:true,color:C.accent1});
const bl=[['FaMobileAlt','Owner app: chat, voice, approvals'],['FaWhatsapp','WhatsApp and Gmail intake'],['FaUserTie','Accountant console'],['FaUniversity','Mock GST, IMS and e-way bill portal'],['FaSyncAlt','Rule tracker with CA approval']];
for(let i=0;i<5;i++){const y=1.65+i*0.62;
 await circ(s,bl[i][0],6.75,y,0.42,C.accent1,'FFFFFF');
 tb(s,bl[i][1],{x:7.3,y,w:2.2,h:0.42,fontSize:12.5,color:C.text1,valign:'middle'});}
tb(s,'Screens from the working prototype, using synthetic data.',{x:6.75,y:4.85,w:2.75,h:0.4,fontSize:10.5,italic:true,color:C.text2});
N(s,'Screenshots are taken from the running prototype (FastAPI + SQLite, mobile-first web app). All data is synthetic.');

// 12 ACCOUNTANT + UNDER THE HOOD
s=pres.addSlide({masterName:'CONTENT',sectionTitle:'Product'});
s.addText('Built for the accountant, too',{placeholder:'title'});
rr(s,0.45,1.3,2.8,3.4,C.text1,{rectRadius:0.15,objectName:'img-frame'});
s.addImage({path:SHOTS+'r_sup.png',x:0.5,y:1.35,w:2.7,h:2.7/1240*1520,altText:'Supplier reconciliation screen showing Rs 18,000 stuck with Ravi Traders'});
tb(s,'Credit recovery: ₹18,000 stuck with Ravi Traders',{x:0.5,y:4.78,w:2.8,h:0.4,fontSize:11,color:C.text2});
s.addImage({path:SHOTS+'r_acc.png',x:3.55,y:1.3,w:5.95,h:5.95/1920*640,altText:'Accountant console listing clients with deadlines and ITC at risk'});
tb(s,'Accountant console: every client, deadline and credit at risk in one view',{x:3.55,y:3.4,w:5.95,h:0.3,fontSize:11,color:C.text2});
const uh=[['FaCalculator','Maths in code','Tax is calculated by deterministic code, not guessed by AI.'],['FaLock','Approval gate','No filing tool. A human files, with an OTP.'],['FaHistory','Audit trail','Append-only log of every action.']];
for(let i=0;i<3;i++){const x=3.55+i*2.0;
 rr(s,x,3.85,1.95,1.3,C.background2,{objectName:'fact-tile'});
 await circ(s,uh[i][0],x+0.12,3.95,0.38,C.accent1,'FFFFFF');
 tb(s,uh[i][1],{x:x+0.58,y:3.95,w:1.3,h:0.38,fontSize:12.5,bold:true,color:C.text1,valign:'middle'});
 tb(s,uh[i][2],{x:x+0.12,y:4.42,w:1.72,h:0.7,fontSize:11,color:C.text2});}
N(s,'Accountant console and the safeguards. 25 automated tests cover calculators, reconciliation, the approval gate, the append-only audit log and end-to-end flows.');

// 13 IMPACT
pres.addSection({title:'Impact'});
s=pres.addSlide({masterName:'CONTENT',sectionTitle:'Impact'});
s.addText('What changes with Ganaka',{placeholder:'title'});
tb(s,'TODAY',{x:3.0,y:1.2,w:2.6,h:0.25,fontSize:11,bold:true,color:C.accent3});
tb(s,'WITH GANAKA',{x:6.1,y:1.2,w:3.4,h:0.25,fontSize:11,bold:true,color:C.accent1});
const imp=[['FaClock','Paperwork time','15–20 hours every month','A short monthly review. Ganaka collects and drafts.'],
 ['FaRupeeSign','Cost per filing','₹1,500–3,000 to an accountant','The accountant reviews instead of re-keying data.'],
 ['FaSearchDollar','Input credit','Lost to supplier errors, found by notice','Flagged before filing and the supplier is nudged.'],
 ['FaTruck','E-way bills','A wrong bill means detention, up to 200% of tax','Validated and blocked before the truck leaves.'],
 ['FaBell','Deadlines, notices','Late fees and notices in jargon','Calendar alerts and notices in the owner’s language.']];
for(let i=0;i<5;i++){const y=1.5+i*0.72;
 await circ(s,imp[i][0],0.5,y+0.07,0.46,C.text1,HEX.a2);
 tb(s,imp[i][1],{x:1.05,y,w:1.8,h:0.6,fontSize:13,bold:true,color:C.text1,valign:'middle'});
 rr(s,3.0,y,2.6,0.62,C.background2,{objectName:'today-cell'});
 tb(s,imp[i][2],{x:3.1,y,w:2.4,h:0.62,fontSize:11.5,color:C.text1,valign:'middle'});
 tb(s,'→',{x:5.6,y,w:0.5,h:0.62,fontSize:20,bold:true,color:C.accent1,align:'center',valign:'middle'});
 rr(s,6.1,y,3.4,0.62,C.accent1,{objectName:'ganaka-cell'});
 tb(s,imp[i][3],{x:6.2,y,w:3.2,h:0.62,fontSize:11.5,color:C.background1,valign:'middle'});}
tb(s,'Targets to be validated in pilots with real micro businesses.',{x:0.5,y:5.15,w:6,h:0.25,fontSize:10.5,italic:true,color:C.text2});
N(s,'Today column is from the brief. The With Ganaka column describes designed behaviour demonstrated in the prototype (including the Rs 18,000 credit case and the e-way bill block). Time and cost reductions are targets to validate in pilots, not measured results.');

// 14 THANK YOU
s=pres.addSlide({masterName:'TITLE_DARK',sectionTitle:'Impact'});
tb(s,'Thank you',{x:0.6,y:1.4,w:6.4,h:1.1,fontSize:60,bold:true,fontFace:'Cambria',color:C.background1,valign:'middle'});
tb(s,'Ganaka does the work.\nThe owner stays in control.',{x:0.6,y:2.7,w:6.4,h:1.0,fontSize:24,bold:true,color:C.accent2});
tb(s,'Simplifying Compliance. Empowering Businesses.',{x:0.6,y:4.0,w:6.4,h:0.4,fontSize:16,color:C.accent5});
for(const [ic,y] of [['FaStore',1.0],['FaUserTie',2.35],['FaTruck',3.7]]){await circ(s,ic,7.55,y,1.15,C.accent1,'FFFFFF');}
N(s,'Close. Ganaka: Simplifying Compliance. Empowering Businesses.');

await pres.writeFile({fileName:'Ganaka_Pitch.pptx'});
await applyTheme('Ganaka_Pitch.pptx',THEME);
console.log('built');
})().catch(e=>{console.error(e);process.exit(1)});
