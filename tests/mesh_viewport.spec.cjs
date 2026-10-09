/* Optional offline Three.js mesh preview QA, using real PyNite generators. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const http = require('node:http');
const path = require('node:path');
const {execFileSync} = require('node:child_process');
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const root = path.resolve(__dirname, '..');
const assets = path.join(root, 'src/pynitegui/qt/viewport3d');
const output = process.env.MESH_QA_OUTPUT || '/tmp/pynite-mesh-qa';
fs.mkdirSync(output, {recursive:true});
const payloads = JSON.parse(execFileSync(path.join(root,'.venv/bin/python'), ['-B',path.join(__dirname,'mesh_payload.py')], {
  cwd:root, encoding:'utf8', env:{...process.env,QT_QPA_PLATFORM:'offscreen',PYNITEGUI_NO_WEBENGINE:'1'},
}));
const server = http.createServer((request,response) => {
  const filename = path.resolve(assets, '.'+decodeURIComponent(request.url==='/'?'/index.html':request.url.split('?')[0]));
  if (!filename.startsWith(assets+path.sep)) {response.writeHead(403).end();return;}
  try {response.setHeader('Content-Type',filename.endsWith('.js')?'text/javascript':filename.endsWith('.html')?'text/html':'text/plain');response.end(fs.readFileSync(filename));}
  catch {response.writeHead(404).end();}
});
(async()=>{
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  const browser = await chromium.launch({headless:true,args:['--use-gl=angle','--use-angle=swiftshader']});
  try {
    const page = await browser.newPage({viewport:{width:1280,height:800}});
    const errors=[];page.on('pageerror',error=>errors.push(error.message));
    await page.goto(`http://127.0.0.1:${server.address().port}/`);
    await page.waitForFunction(()=>window.pyniteViewer);
    for (const [kind,payload] of Object.entries(payloads)) {
      await page.evaluate(payload=>{window.pyniteViewer.update(payload);window.pyniteViewer.orient(0);},payload);
      await page.waitForTimeout(150);
      const pixels = await page.evaluate(()=>{
        const canvas=document.querySelector('canvas'),gl=canvas.getContext('webgl2');
        const values=new Uint8Array(canvas.width*canvas.height*4);
        gl.readPixels(0,0,canvas.width,canvas.height,gl.RGBA,gl.UNSIGNED_BYTE,values);
        let colored=0;
        for(let i=0;i<values.length;i+=4)if(Math.max(...values.subarray(i,i+3))-Math.min(...values.subarray(i,i+3))>35)colored++;
        return colored/(canvas.width*canvas.height);
      });
      assert(pixels>.005, `Blank ${kind} mesh`);
      const positions=await page.evaluate(points=>points.map(point=>window.pyniteViewer.project(point)),payload.nodes.map(node=>node.position));
      assert(positions.every(([x,y])=>x>10&&x<1270&&y>10&&y<790),`Clipped ${kind}`);
      await page.screenshot({path:path.join(output,`${kind}.png`)});
      const before=await page.evaluate(()=>window.pyniteViewer.state().camera);
      await page.mouse.move(450,330);await page.mouse.down();await page.mouse.move(620,390,{steps:8});await page.mouse.up();
      await page.waitForTimeout(200);
      const after=await page.evaluate(()=>window.pyniteViewer.state().camera);
      assert(Math.hypot(...after.map((value,i)=>value-before[i]))>1,`Orbit inactive for ${kind}`);
    }
    await page.evaluate(payload=>{window.pyniteViewer.update({...payload,surfaceFill:false,showNodes:true});window.pyniteViewer.fit();},payloads.rectangle);
    await page.waitForTimeout(100);
    const resources=await page.evaluate(()=>window.pyniteViewer.state().resources.geometries);
    for(let i=0;i<10;i++)await page.evaluate(payload=>window.pyniteViewer.update(payload),payloads.cylinder);
    await page.waitForTimeout(100);
    assert((await page.evaluate(()=>window.pyniteViewer.state().resources.geometries))<=resources+2,'Surface rebuild leaks');
    assert.deepEqual(errors,[]);
    console.log('PASS: all seven real PyNite meshes, desktop pixels/framing, orbit, face/node toggles and bounded rebuild resources');
  } finally {await browser.close();server.close();}
})().catch(error=>{console.error(error);server.close();process.exitCode=1;});
