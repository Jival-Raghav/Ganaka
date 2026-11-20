const puppeteer=require('puppeteer-core');const sharp=require('sharp');
(async()=>{
 const br=await puppeteer.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:'new'});
 const m=await br.newPage();await m.setViewport({width:620,height:900,deviceScaleFactor:2,isMobile:true});
 await m.goto('http://localhost:8000/',{waitUntil:'domcontentloaded'});
 const tok=await m.evaluate(async()=>{const r=await fetch('/api/auth/verify',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({phone:'9845012345',otp:'123456'})});return (await r.json()).token});
 await m.evaluate(t=>localStorage.setItem('munshi_token_/',t),tok);
 await m.goto('http://localhost:8000/#suppliers',{waitUntil:'networkidle0'});await m.reload({waitUntil:'networkidle0'});await new Promise(r=>setTimeout(r,1500));
 await m.screenshot({path:'shots/suppliers_w.png'});await br.close();
 for(const n of ['home','chat','ewb']){const i=sharp('shots/'+n+'.png');const md=await i.metadata();await sharp('shots/'+n+'.png').extract({left:0,top:200,width:md.width,height:md.height-200}).toFile('shots/'+n+'_c.png')}
 const md=await sharp('shots/suppliers_w.png').metadata();await sharp('shots/suppliers_w.png').extract({left:0,top:200,width:md.width,height:md.height-200}).toFile('shots/suppliers_c.png');
})();
