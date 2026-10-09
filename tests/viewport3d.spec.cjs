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
  const browser = await chromium.launch({headless:true,args:['--use-gl=angle','--use-angle=swiftshader']});
  try{
    const page = await browser.newPage();
    const errors=[];
    page.on('pageerror',error=>errors.push(error.message));
    await page.goto(`http://127.0.0.1:${server.address().port}/`);
    await page.waitForFunction(()=>window.pyniteViewer);
    for(const [name,size] of [['desktop',{width:1280,height:720}]]){
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
      await page.evaluate(()=>{window.pyniteViewer.orient(0);window.viewEvent=-1;addEventListener('viewOriented',event=>window.viewEvent=event.detail);});
      const axis=await page.evaluate(()=>window.pyniteViewer.gizmoAxes().find(axis=>axis.type==='posZ'));
      await page.mouse.click(axis.x,axis.y);
      await page.waitForFunction(()=>window.viewEvent===1);
      await page.getByRole('button',{name:'Isometric view'}).click();
      await page.waitForFunction(()=>window.viewEvent===0);
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
    for(const [type,index,direction] of [['posX',3,[1,0,0]],['posY',2,[0,1,0]],['posZ',1,[0,0,1]],['negX',6,[-1,0,0]],['negY',5,[0,-1,0]],['negZ',4,[0,0,-1]]]){
      await page.evaluate(()=>{window.pyniteViewer.orient(0);window.viewEvent=-1;});
      const before=await page.evaluate(()=>window.pyniteViewer.state());
      const axis=await page.evaluate(type=>window.pyniteViewer.gizmoAxes().find(axis=>axis.type===type),type);
      await page.mouse.click(axis.x,axis.y);
      await page.waitForFunction(index=>window.viewEvent===index,index,{timeout:2000}).catch(async error=>{
        console.error(type,index,await page.evaluate(()=>({event:window.viewEvent,state:window.pyniteViewer.state(),axes:window.pyniteViewer.gizmoAxes()})));throw error;
      });
      const after=await page.evaluate(()=>window.pyniteViewer.state());
      const delta=after.camera.map((v,i)=>v-after.target[i]),distance=Math.hypot(...delta);
      assert(delta.every((v,i)=>Math.abs(v/distance-direction[i])<.001),`${type} did not align the camera`);
      assert(after.target.every((v,i)=>Math.abs(v-before.target[i])<1e-6),'Gizmo changed the orbit target');
      assert.deepEqual(after.selection,before.selection,'Gizmo changed the selection');
      assert(Math.abs(distance-Math.hypot(...before.camera.map((v,i)=>v-before.target[i])))<.01,'Gizmo changed zoom');
    }
    await page.getByRole('group',{name:'View orientation'}).focus();
    await page.keyboard.press('Home');
    await page.waitForFunction(()=>window.viewEvent===0);
    await page.keyboard.press('Shift+X');
    await page.waitForFunction(()=>window.viewEvent===6);
    assert.deepEqual(errors,[]);
    await page.evaluate(()=>{
      window.bridgeFailures=[];
      window.pyniteBridge={failed:message=>window.bridgeFailures.push(message)};
      document.querySelector('canvas').getContext('webgl2').getExtension('WEBGL_lose_context').loseContext();
    });
    await page.waitForFunction(()=>window.pyniteFailure);
    const failure=await page.evaluate(()=>({message:window.pyniteFailure,bridge:window.bridgeFailures,error:document.querySelector('#error').textContent}));
    assert.match(failure.message,/graphics context was lost/i);
    assert.deepEqual(failure.bridge,[failure.message],'Context loss did not reach the native bridge');
    assert(failure.error.includes(failure.message),'Context loss did not show browser fallback text');
    console.log('PASS: rendered geometry/deformation, desktop framing and gizmo, six signed views, keyboard reset, orbit, node picking, XY/XZ/YZ snapped drawing, dark theme, context-loss recovery.');
  }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;}).finally(()=>server.close());
