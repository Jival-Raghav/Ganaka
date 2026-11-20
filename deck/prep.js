const sharp=require('sharp');
async function round(src,dst,crop,r){
  let img=sharp(src); const md=await img.metadata();
  const c=Object.assign({left:0,top:0,width:md.width,height:md.height},crop||{});
  const buf=await sharp(src).extract(c).toBuffer();
  const mask=Buffer.from(`<svg width="${c.width}" height="${c.height}"><rect width="${c.width}" height="${c.height}" rx="${r}" ry="${r}"/></svg>`);
  await sharp(buf).composite([{input:mask,blend:'dest-in'}]).png().toFile(dst);
  const o=await sharp(dst).metadata(); console.log(dst,o.width,o.height);
}
(async()=>{
  await round('shots/home_c.png','shots/r_home.png',null,44);
  await round('shots/chat_c.png','shots/r_chat.png',null,44);
  await round('shots/ewb_c.png','shots/r_ewb.png',{left:0,top:0,width:780,height:1320},44);
  await round('shots/acc_clients.png','shots/r_acc.png',{left:0,top:46,width:1920,height:640},18);
  await round('shots/suppliers_w.png','shots/r_sup.png',{left:0,top:200,width:1240,height:1520},24);
})();
