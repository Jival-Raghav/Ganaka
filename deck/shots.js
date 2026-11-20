const puppeteer=require('puppeteer-core');
const B='http://localhost:8000';
async function login(page,path,body){
  await page.goto(B+path,{waitUntil:'domcontentloaded'});
  const tok=await page.evaluate(async(b)=>{const r=await fetch('/api/auth/verify',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b)});return (await r.json()).token},body);
  await page.evaluate((p,t)=>localStorage.setItem('munshi_token_'+p,t),path,tok);
}
(async()=>{
  const br=await puppeteer.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:'new'});
  const m=await br.newPage(); await m.setViewport({width:390,height:760,deviceScaleFactor:2,isMobile:true});
  await login(m,'/',{phone:'9845012345',otp:'123456'});
  const go=async(h,name,wait=1500)=>{await m.goto(B+'/#'+h,{waitUntil:'networkidle0'});await m.reload({waitUntil:'networkidle0'});await new Promise(r=>setTimeout(r,wait));await m.screenshot({path:'shots/'+name+'.png'});console.log(name)};
  await go('home','home');
  await go('suppliers','suppliers');
  await go('ewb','ewb');
  await go('returns','returns');
  // chat
  await m.goto(B+'/#chat',{waitUntil:'networkidle0'});await m.reload({waitUntil:'networkidle0'});await new Promise(r=>setTimeout(r,1000));
  await m.type('#cin','ee month GST eshtu?');await m.keyboard.press('Enter');await new Promise(r=>setTimeout(r,2500));
  await m.screenshot({path:'shots/chat.png'});console.log('chat');
  // accountant
  const a=await br.newPage(); await a.setViewport({width:1280,height:760,deviceScaleFactor:1.5});
  await login(a,'/accountant',{email:'priya@demo.in',password:'demo123',otp:'123456'});
  for(const [h,n] of [['clients','acc_clients'],['queue','acc_queue'],['capacity','acc_capacity']]){await a.goto(B+'/accountant#'+h,{waitUntil:'networkidle0'});await a.reload({waitUntil:'networkidle0'});await new Promise(r=>setTimeout(r,1200));await a.screenshot({path:'shots/'+n+'.png'});console.log(n)}
  // sim
  const s=await br.newPage(); await s.setViewport({width:1280,height:760,deviceScaleFactor:1.5});
  await s.goto(B+'/sim',{waitUntil:'networkidle0'});await new Promise(r=>setTimeout(r,1500));await s.screenshot({path:'shots/sim.png'});console.log('sim');
  await br.close();
})().catch(e=>{console.error(e);process.exit(1)});
