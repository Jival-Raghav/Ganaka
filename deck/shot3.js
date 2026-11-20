const puppeteer=require('puppeteer-core');
(async()=>{const br=await puppeteer.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:'new'});
const a=await br.newPage();await a.setViewport({width:1280,height:760,deviceScaleFactor:1.5});
await a.goto('http://localhost:8000/accountant',{waitUntil:'domcontentloaded'});
const tok=await a.evaluate(async()=>{const r=await fetch('/api/auth/verify',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email:'priya@demo.in',password:'demo123',otp:'123456'})});return (await r.json()).token});
await a.evaluate(t=>localStorage.setItem('munshi_token_/accountant',t),tok);
await a.goto('http://localhost:8000/accountant#clients',{waitUntil:'networkidle0'});await a.reload({waitUntil:'networkidle0'});await new Promise(r=>setTimeout(r,1200));
await a.screenshot({path:'shots/acc_clients.png'});await br.close()})();
