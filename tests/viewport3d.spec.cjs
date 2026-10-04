/* Optional visual QA: uses installed Playwright, not a runtime app dependency. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const {execFileSync} = require('node:child_process');
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');

const root = path.resolve(__dirname, '..');
const assets = path.join(root, 'src/pynitegui/qt/viewport3d');
const output = process.env.VIEWPORT_QA_OUTPUT || '/tmp/pynite-3d-qa';
fs.mkdirSync(output, {recursive:true});
const payload = JSON.parse(execFileSync(path.join(root,'.venv/bin/python'),['-B',path.join(__dirname,'viewport3d_payload.py')],{
  cwd:root,env:{...process.env,QT_QPA_PLATFORM:'offscreen',PYNITEGUI_NO_WEBENGINE:'1',MPLCONFIGDIR:'/tmp/pynite-mpl'},encoding:'utf8'
}));
const server = http.createServer((request,response)=>{
  const filename = path.resolve(assets, '.'+decodeURIComponent(request.url==='/'?'/index.html':request.url.split('?')[0]));
  if(!filename.startsWith(assets+path.sep)){response.writeHead(403).end();return;}
  try{response.setHeader('Content-Type',filename.endsWith('.js')?'text/javascript':filename.endsWith('.html')?'text/html':'text/plain');response.end(fs.readFileSync(filename));}
  catch{response.writeHead(404).end();}
});

(async()=>{
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  const browser = await chromium.launch({headless:true,args:['--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
  try{
    const page = await browser.newPage();
    const errors=[];
    page.on('pageerror',error=>errors.push(error.message));
    await page.goto(`http://127.0.0.1:${server.address().port}/`);
    await page.waitForFunction(()=>window.pyniteViewer);
    for(const [name,size] of [['desktop',{width:1280,height:720}],['mobile',{width:390,height:844}]]){
      await page.setViewportSize(size);
      await page.evaluate(payload=>{window.pyniteViewer.update(payload);window.pyniteViewer.fit();},payload);
      await page.waitForTimeout(300);
      const state=await page.evaluate(()=>window.pyniteViewer.state());
      assert(state.objects>50 && state.drawCalls>10,`Empty ${name} scene`);
      const pixels=await page.evaluate(()=>{
        const canvas=document.querySelector('canvas'),gl=canvas.getContext('webgl2'),rgba=new Uint8Array(canvas.width*canvas.height*4);
        gl.readPixels(0,0,canvas.width,canvas.height,gl.RGBA,gl.UNSIGNED_BYTE,rgba);
        let engineering=0;
        for(let i=0;i<rgba.length;i+=4)if(Math.max(rgba[i],rgba[i+1],rgba[i+2])-Math.min(rgba[i],rgba[i+1],rgba[i+2])>35)engineering++;
        return engineering/(canvas.width*canvas.height);
      });
      assert(pixels>.0005,`Blank ${name} canvas`);
      const positions=await page.evaluate(nodes=>nodes.map(node=>window.pyniteViewer.project(node.position)),payload.nodes);
      for(const [x,y] of positions)assert(x>15&&x<size.width-15&&y>15&&y<size.height-15,`${name} model clipped: ${x}, ${y}`);
      await page.screenshot({path:path.join(output,`${name}-light.png`)});
      console.log(name,JSON.stringify({pixels,drawCalls:state.drawCalls}));
    }
    await page.setViewportSize({width:1280,height:720});
    await page.evaluate(payload=>{window.pyniteViewer.update(payload);window.pyniteViewer.fit();},payload);
    const before=await page.evaluate(()=>window.pyniteViewer.state().camera);
    await page.mouse.move(1100,300);await page.mouse.down();await page.mouse.move(1170,360,{steps:12});await page.mouse.up();
    await page.waitForTimeout(300);
    const after=await page.evaluate(()=>window.pyniteViewer.state().camera);
    assert(Math.hypot(...after.map((x,i)=>x-before[i]))>1,'Orbit did not move camera');
    await page.evaluate(()=>{window.pyniteViewer.orient(0);window.selectedEvent=null;addEventListener('modelSelected',event=>window.selectedEvent=event.detail);});
    await page.waitForTimeout(200);
    const node=payload.nodes.find(n=>n.name==='N2');
    const point=await page.evaluate(p=>window.pyniteViewer.project(p),node.position);
    await page.mouse.click(...point);
    const selection=await page.evaluate(()=>window.selectedEvent);
    assert.deepEqual(selection,['nodes','N2'],'Node picking failed');
    for(const [plane,orientation,points] of [['XY',1,[[72,60,0],[168,96,0]]],['XZ',2,[[72,0,60],[168,0,96]]],['YZ',3,[[0,60,60],[0,96,96]]]]){
      await page.evaluate(({payload,plane,orientation})=>{window.pyniteViewer.update({...payload,mode:'draw',plane,labels:false});window.pyniteViewer.orient(orientation);window.drawEvent=null;}, {payload,plane,orientation});
      await page.evaluate(()=>{window.addEventListener('memberDrawn',event=>window.drawEvent=event.detail,{once:true});});
      await page.waitForTimeout(150);
      for(const position of points){const p=await page.evaluate(p=>window.pyniteViewer.project(p),position);await page.mouse.click(...p);}
      const drawn=await page.evaluate(()=>window.drawEvent);
      assert(drawn,`${plane} work plane did not draw`);
      drawn.forEach((point,i)=>point.forEach((value,j)=>assert(Math.abs(value-points[i][j])<1e-6,`${plane} snap mismatch`)));
    }
    const dark={...payload,colors:{...payload.colors,canvas:'#191c1f',grid:'#30373b',member:'#d1dbe0',label:'#c4cdd3',accent:'#4cc9c0',support:'#73d89c',load:'#ff7b8a'}};
    await page.evaluate(payload=>{window.pyniteViewer.update(payload);window.pyniteViewer.orient(0);},dark);
    await page.waitForTimeout(300);await page.screenshot({path:path.join(output,'desktop-dark.png')});
    assert.deepEqual(errors,[]);
    console.log('PASS: rendered geometry/deformation, desktop/mobile framing, orbit, node picking, XY/XZ/YZ snapped drawing, dark theme.');
  }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;}).finally(()=>server.close());
