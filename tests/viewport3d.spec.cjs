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
  const browser = await chromium.launch({headless:true,executablePath:process.env.PLAYWRIGHT_EXECUTABLE_PATH,
    args:['--use-gl=angle','--use-angle=swiftshader']});
  try{
    const page = await browser.newPage();
    const errors=[];
    page.on('pageerror',error=>errors.push(error.message));
    await page.goto(`http://127.0.0.1:${server.address().port}/`);
    await page.waitForFunction(()=>window.pyniteViewer);
    const driver=await page.evaluate(()=>window.pyniteViewer.diagnostics());
    assert(driver.renderer&&driver.vendor&&driver.version.includes('WebGL'),'Missing observed WebGL driver information');
    assert.equal(driver.lost,false);
    assert(['Unmasked WebGL driver','Masked WebGL information'].includes(driver.source));
    await require('./viewport3d_cache.cjs')(page,payload);
    const batches=await page.evaluate(async()=>{
      const THREE=await import('three'),{drawFrame,hitIdentity}=await import('./frame_meshes.js');
      const group=new THREE.Group(),picks=[];
      const data={nodes:[{name:'A',position:[0,0,0]},{name:'B',position:[10,0,0]},
        {name:'C',position:[20,0,0]},{name:'D',position:[20,10,0]}],
        members:[{name:'X',start:'A',end:'B',kind:'frame'},{name:'Y',start:'C',end:'D',kind:'truss'}],
        selection:[['nodes','A'],['members','Y']],colors:{accent:'#ff0000',member:'#444444',axial:'#00ff00'}};
      drawFrame(data,.2,group,picks);group.updateMatrixWorld(true);
      const cast=position=>hitIdentity(new THREE.Raycaster(new THREE.Vector3(...position),new THREE.Vector3(0,0,-1)).intersectObjects(picks)[0]);
      const matrix=new THREE.Matrix4(),member=picks[0],node=picks[1],color=new THREE.Color();
      const ends=[];
      for(let i=0;i<2;i++){
        member.getMatrixAt(i,matrix);ends.push([new THREE.Vector3(0,-.5,0).applyMatrix4(matrix).toArray(),
          new THREE.Vector3(0,.5,0).applyMatrix4(matrix).toArray()]);
      }
      member.getColorAt(1,color);const memberColor=color.getHexString();node.getColorAt(0,color);
      const value={counts:picks.map(mesh=>mesh.count),ends,hits:[[5,0,10],[20,5,10],[20,10,10]].map(cast),
        colors:[memberColor,color.getHexString()]};
      for(const mesh of picks){mesh.dispose();mesh.geometry.dispose();mesh.material.dispose();}return value;
    });
    assert.deepEqual(batches.counts,[2,4]);
    assert.deepEqual(batches.hits,[['members','X'],['members','Y'],['nodes','D']],'Instanced picking lost identities');
    assert.deepEqual(batches.colors,['ff0000','ff0000'],'Instance selection colours were lost');
    const expectedEnds=[[[0,0,0],[10,0,0]],[[20,0,0],[20,10,0]]];
    batches.ends.forEach((ends,i)=>ends.forEach((point,j)=>point.forEach((value,k)=>assert(Math.abs(value-expectedEnds[i][j][k])<1e-6,'Instance transform moved a member endpoint'))));
    for(const load of payload.loads.filter(load=>load.label.includes('| Angle'))){
      assert(Math.abs(Math.hypot(...load.vector)-1)<1e-9,'Angular load arrow is not a unit global vector');
      assert(load.label.includes('az ')&&load.label.includes('el '),'Angular arrow label lacks angle context');
    }
    const crossing=await page.evaluate(async()=>{
      const {drawDiagram}=await import('./diagrams.js');
      const objects=[];
      drawDiagram({name:'Test',points:[[0,0,0],[10,0,0]],diagramValues:[2,-2],axes:[[1,0,0],[0,1,0],[0,0,1]]},
        {axis:1,factor:1,color:'shear',values:false},{add:object=>objects.push(object)},()=>{},()=>{},{shear:'#168b8b'});
      const result=Array.from(objects[0].geometry.attributes.position.array);
      objects[0].geometry.dispose();objects[0].material.dispose();return result;
    });
    assert.deepEqual(crossing,[0,0,0,5,0,0,0,2,0,5,0,0,10,0,0,10,-2,0],'Opposite-sign ribbon did not split at zero');
    for(const [name,size] of [['desktop',{width:1280,height:720}]]){
      await page.setViewportSize(size);
      await page.evaluate(payload=>{window.pyniteViewer.update(payload);window.pyniteViewer.fit();},payload);
      await page.waitForTimeout(300);
      const state=await page.evaluate(()=>window.pyniteViewer.state());
      assert(state.objects>10 && state.drawCalls>10 && state.nodes.length===payload.nodes.length,`Empty ${name} scene`);
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
    await page.evaluate(payload=>{window.pyniteViewer.update({...payload,boxSelect:true,deformed:false});window.pyniteViewer.orient(0);window.boxEvent=null;addEventListener('modelBoxSelected',event=>window.boxEvent=event.detail);},payload);
    const boxCamera=await page.evaluate(()=>window.pyniteViewer.state().camera);
    await page.mouse.move(5,5);await page.mouse.down();await page.mouse.move(1275,715,{steps:6});await page.mouse.up();
    const allBox=await page.evaluate(()=>window.boxEvent);
    assert.equal(allBox.selections.length,payload.nodes.length+payload.members.length,'Whole-view box missed geometry');
    assert.equal(allBox.extend,false);
    const fixedCamera=await page.evaluate(()=>window.pyniteViewer.state().camera);
    assert(fixedCamera.every((value,i)=>Math.abs(value-boxCamera[i])<1e-6),'Box drag moved the camera');
    const column=payload.members.find(member=>member.name==='M1');
    const midpoint=payload.nodes.find(node=>node.name===column.start).position.map((value,i)=>(value+payload.nodes.find(node=>node.name===column.end).position[i])/2);
    const center=await page.evaluate(point=>window.pyniteViewer.project(point),midpoint);
    await page.mouse.move(center[0]-4,center[1]-4);await page.mouse.down();await page.mouse.move(center[0]+4,center[1]+4);await page.mouse.up();
    assert(!(await page.evaluate(()=>window.boxEvent)).selections.some(([kind,name])=>kind==='members'&&name==='M1'),'Contained selection picked a crossing member');
    await page.keyboard.down('Control');
    await page.mouse.move(center[0]+4,center[1]-4);await page.mouse.down();await page.mouse.move(center[0]-4,center[1]+4);await page.mouse.up();
    await page.keyboard.up('Control');
    const crossingBox=await page.evaluate(()=>window.boxEvent);
    assert(crossingBox.selections.some(([kind,name])=>kind==='members'&&name==='M1'),'Crossing box missed member');
    assert(crossingBox.extend,'Ctrl did not request additive selection');
    await page.evaluate(()=>window.boxEvent=null);
    await page.mouse.move(5,5);await page.mouse.down();await page.mouse.move(400,300);
    await page.screenshot({path:path.join(output,'desktop-box-selection.png')});
    await page.keyboard.press('Escape');await page.mouse.up();
    assert.equal(await page.evaluate(()=>window.boxEvent),null,'Cancelled box changed selection');
    assert(await page.locator('#selection-box').isHidden(),'Selection rectangle remained after cancellation');
    await page.evaluate(payload=>window.pyniteViewer.update(payload),payload);
    await page.keyboard.down('Shift');
    await page.mouse.move(5,5);await page.mouse.down();await page.mouse.move(1275,715);await page.mouse.up();
    await page.keyboard.up('Shift');
    assert.equal((await page.evaluate(()=>window.boxEvent)).selections.length,payload.nodes.length+payload.members.length,'Shift-drag did not select a box with box mode off');
    for(const [plane,orientation,points] of [['XY',1,[[72,60,0],[168,96,0]]],['XZ',2,[[72,0,60],[168,0,96]]],['YZ',3,[[0,60,60],[0,96,96]]]]){
      await page.evaluate(({payload,plane,orientation})=>{window.pyniteViewer.update({...payload,mode:'draw',plane,labels:false});window.pyniteViewer.orient(orientation);window.drawEvent=null;}, {payload,plane,orientation});
      await page.evaluate(()=>{window.addEventListener('memberDrawn',event=>window.drawEvent=event.detail,{once:true});});
      await page.waitForTimeout(150);
      for(const position of points){const p=await page.evaluate(p=>window.pyniteViewer.project(p),position);await page.mouse.click(...p);}
      const drawn=await page.evaluate(()=>window.drawEvent);
      assert(drawn,`${plane} work plane did not draw`);
      drawn.forEach((point,i)=>point.forEach((value,j)=>assert(Math.abs(value-points[i][j])<1e-6,`${plane} snap mismatch`)));
    }
    for(const [plane,orientation,target] of [['XY',1,[24,168,0]],['XZ',2,[24,144,24]],['YZ',3,[0,168,24]]]){
      await page.evaluate(({payload,plane,orientation})=>{
        window.pyniteViewer.update({...payload,mode:'select',plane,offset:999,boxSelect:false,moveNodes:true,deformed:true});
        window.pyniteViewer.orient(orientation);window.moveEvent=null;
        addEventListener('nodeMoved',event=>window.moveEvent=event.detail,{once:true});
      }, {payload:payload.qaDiagrams.moment_z,plane,orientation});
      await page.waitForTimeout(100);
      const node=payload.nodes.find(node=>node.name==='N2');
      const from=await page.evaluate(point=>window.pyniteViewer.project(point),node.position);
      const to=await page.evaluate(point=>window.pyniteViewer.project(point),target);
      const camera=await page.evaluate(()=>window.pyniteViewer.state().camera);
      await page.mouse.move(...from);await page.mouse.down();await page.mouse.move(...to,{steps:10});
      const preview=await page.evaluate(()=>window.pyniteViewer.state());
      assert(preview.dragging,`${plane} node drag did not start`);
      assert.deepEqual(preview.nodes.find(node=>node.name==='N2').position,target,`${plane} preview did not snap or preserve the frozen coordinate`);
      assert.equal(await page.evaluate(()=>window.moveEvent),null,'Preview committed an engineering edit');
      assert(await page.locator('#result-legend').isHidden(),'Old result overlay remained during geometry preview');
      assert(preview.camera.every((value,i)=>Math.abs(value-camera[i])<1e-6),'Moving a node orbited the camera');
      if(plane==='XY')await page.screenshot({path:path.join(output,'desktop-node-drag-preview.png')});
      await page.mouse.up();
      const moved=await page.evaluate(()=>window.moveEvent);
      assert.deepEqual(moved,{node:'N2',start:node.position,target,plane,revision:payload.revision},`${plane} drag emitted an invalid native request`);
      assert.deepEqual((await page.evaluate(()=>window.pyniteViewer.state())).nodes.find(node=>node.name==='N2').position,node.position,
        'Browser preview was not restored pending native validation');
    }
    await page.evaluate(payload=>{
      window.pyniteViewer.update({...payload,mode:'select',plane:'XY',boxSelect:false,moveNodes:true});window.pyniteViewer.orient(1);
      window.moveEvent=null;addEventListener('nodeMoved',event=>window.moveEvent=event.detail);
    },payload.qaDiagrams.moment_z);
    let dragFrom=await page.evaluate(()=>window.pyniteViewer.project([0,144,0]));
    let dragTo=await page.evaluate(()=>window.pyniteViewer.project([24,168,0]));
    await page.mouse.move(...dragFrom);await page.mouse.down();await page.mouse.move(...dragTo,{steps:5});
    await page.keyboard.press('Escape');await page.mouse.up();
    assert.equal(await page.evaluate(()=>window.moveEvent),null,'Cancelled node drag committed');
    assert.deepEqual((await page.evaluate(()=>window.pyniteViewer.state())).nodes.find(node=>node.name==='N2').position,[0,144,0]);
    assert(!(await page.locator('#result-legend').isHidden()),'Cancellation did not restore the analyzed overlay');
    // A native redraw/change of work plane cancels the old gesture without committing it.
    await page.mouse.move(...dragFrom);await page.mouse.down();await page.mouse.move(...dragTo,{steps:5});
    await page.evaluate(payload=>window.pyniteViewer.update({...payload,mode:'select',plane:'XZ',moveNodes:true}),payload);
    await page.mouse.up();
    assert.equal(await page.evaluate(()=>window.moveEvent),null,'Native update committed a stale gesture');
    // An edge-on work plane cannot produce a stable move intersection.
    await page.evaluate(payload=>{window.pyniteViewer.update({...payload,mode:'select',plane:'XZ',moveNodes:true});window.pyniteViewer.orient(1);window.unavailable=false;
      addEventListener('nodeMoveUnavailable',()=>window.unavailable=true,{once:true});},payload);
    dragFrom=await page.evaluate(()=>window.pyniteViewer.project([0,144,0]));
    await page.mouse.move(...dragFrom);await page.mouse.down();await page.mouse.move(dragFrom[0]+40,dragFrom[1]+40);await page.mouse.up();
    assert(await page.evaluate(()=>window.unavailable),'Edge-on move did not give feedback');
    assert.equal(await page.evaluate(()=>window.moveEvent),null,'Edge-on gesture committed geometry');
    const dark={...payload,colors:{...payload.colors,canvas:'#191c1f',grid:'#30373b',member:'#d1dbe0',label:'#c4cdd3',text:'#eef1f2',accent:'#4cc9c0',support:'#73d89c',load:'#ff7b8a',axial:'#79bdf1',shear:'#4cc9c0',moment:'#ff91ad'}};
    await page.evaluate(payload=>{window.pyniteViewer.update(payload);window.pyniteViewer.orient(0);},dark);
    await page.waitForTimeout(300);await page.screenshot({path:path.join(output,'desktop-dark.png')});
    // Every global DOF gets its own pickable symbol; spring geometry is distinct.
    await page.evaluate(payload=>{window.pyniteViewer.update(payload);window.pyniteViewer.orient(0);},payload.qaSupports);
    await page.waitForTimeout(250);
    const supportSymbols=await page.evaluate(()=>window.pyniteViewer.supportSymbols());
    assert.equal(supportSymbols.length,12,'Mixed support presets produced incorrect DOF symbols');
    const springSymbols=supportSymbols.filter(symbol=>symbol.node==='N1');
    assert.deepEqual(springSymbols.map(symbol=>symbol.dof),['DX','DY','DZ','RX','RY','RZ']);
    assert(springSymbols.every(symbol=>symbol.kind==='spring'));
    assert.equal(supportSymbols.filter(symbol=>symbol.node==='N3').length,3,'Pin restrained rotations');
    assert.deepEqual(supportSymbols.filter(symbol=>symbol.node==='N5').map(symbol=>symbol.dof),['DY'],'Roller restrained wrong global axis');
    assert.deepEqual(supportSymbols.filter(symbol=>symbol.node==='N7').map(symbol=>symbol.dof),['DX','RZ']);
    for(const symbol of springSymbols){
      const point=await page.evaluate(position=>window.pyniteViewer.project(position),symbol.center);
      await page.mouse.move(...point);
      await page.waitForFunction(()=>!document.getElementById('support-tooltip').hidden);
      const details=await page.locator('#support-tooltip').innerText();
      assert(details.includes('N1 | Global supports')&&details.includes('Bilateral spring: 10 kip/in'));
      assert.equal(await page.locator('#support-tooltip .active-dof td').first().innerText(),symbol.dof,'Symbol hover highlighted the wrong DOF');
      assert.equal(await page.locator('#support-tooltip tr').count(),6);
    }
    await page.screenshot({path:path.join(output,'desktop-support-springs-light.png')});
    const symbolShape=await page.evaluate(async()=>{
      const THREE=await import('three'),{drawSupports}=await import('./supports.js');
      const shape=(springs)=>{
        const group=new THREE.Group(),picks=[];
        drawSupports({name:'Test',position:[0,0,0],restraints:springs?Array(6).fill(false):Array(6).fill(true),springs:springs?Array(6).fill(1):Array(6).fill(0)},100,{support:'#00aa00',axial:'#0000aa'},group,picks);
        const sizes=picks.map(object=>object.geometry.attributes.position.count);
        const tags=picks.map(object=>object.userData.identity);
        group.traverse(object=>{object.geometry?.dispose();object.material?.dispose();});
        return {sizes,tags};
      };
      return {spring:shape(true),fixed:shape(false)};
    });
    assert(symbolShape.spring.sizes.includes(51),'Translational spring coil missing');
    assert(symbolShape.spring.sizes.includes(65),'Rotational spring spiral missing');
    assert(!symbolShape.fixed.sizes.includes(51)&&!symbolShape.fixed.sizes.includes(65),'Rigid supports rendered as springs');
    assert(symbolShape.spring.tags.every(tag=>tag[0]==='nodes'&&tag[1]==='Test'),'Support picks not linked to node inspector');
    await page.mouse.down();
    assert(await page.locator('#support-tooltip').isHidden(),'Tooltip remained during drag');
    await page.mouse.up();
    const hoverPoint=await page.evaluate(position=>window.pyniteViewer.project(position),springSymbols[0].center);
    await page.mouse.move(...hoverPoint);
    await page.waitForFunction(()=>!document.getElementById('support-tooltip').hidden);
    await page.keyboard.down('Shift');
    await page.mouse.down();
    assert(await page.locator('#support-tooltip').isHidden(),'Box-selection capture left a stale tooltip');
    await page.keyboard.press('Escape');await page.mouse.up();await page.keyboard.up('Shift');
    await page.evaluate(payload=>window.pyniteViewer.update({...payload,supports:false}),payload.qaSupports);
    assert.equal((await page.evaluate(()=>window.pyniteViewer.supportSymbols())).length,0,'Support visibility did not clear geometry');
    assert(await page.locator('#support-tooltip').isHidden(),'Redraw left a stale support tooltip');
    await page.evaluate(({payload,colors})=>{window.pyniteViewer.update({...payload,colors});window.pyniteViewer.orient(0);},{payload:payload.qaSupportsSI,colors:dark.colors});
    await page.waitForTimeout(250);
    const siNode=payload.qaSupportsSI.nodes.find(node=>node.name==='N1');
    const siPoint=await page.evaluate(position=>window.pyniteViewer.project(position),siNode.position);
    await page.mouse.move(...siPoint);
    await page.waitForFunction(()=>!document.getElementById('support-tooltip').hidden);
    for(const row of siNode.supportDetails)assert((await page.locator('#support-tooltip').innerText()).includes(row.state),'SI tooltip stiffness units incorrect');
    const tooltip=await page.locator('#support-tooltip').boundingBox();
    assert(tooltip.x>=8&&tooltip.y>=8&&tooltip.x+tooltip.width<=1272&&tooltip.y+tooltip.height<=712,'Support tooltip clipped');
    assert.equal(await page.locator('#support-tooltip').evaluate(element=>getComputedStyle(element).color),'rgb(238, 241, 242)');
    await page.screenshot({path:path.join(output,'desktop-support-springs-dark-si.png')});
    await page.keyboard.press('Escape');
    assert(await page.locator('#support-tooltip').isHidden(),'Escape left support tooltip open');
    await page.mouse.move(1100,40);
    assert(await page.locator('#support-tooltip').isHidden(),'Empty-space hover left tooltip open');
    await page.evaluate(payload=>{window.pyniteViewer.update(payload);window.pyniteViewer.orient(0);},dark);
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
    for(const [kind,diagramPayload] of Object.entries(payload.qaDiagrams)){
      await page.evaluate(payload=>{window.pyniteViewer.update(payload);window.pyniteViewer.orient(0);},diagramPayload);
      await page.waitForTimeout(150);
      assert((await page.locator('#result-legend').innerText()).includes(diagramPayload.diagram.combination),'Missing combination legend');
      const paths=await page.evaluate(()=>window.pyniteViewer.diagramPoints());
      for(const path of paths){
        const member=diagramPayload.members.find(member=>member.name===path.name);
        assert.equal(path.points.length,member.points.length);
        path.points.forEach((point,i)=>point.forEach((value,j)=>{
          const expected=member.points[i][j]+member.axes[diagramPayload.diagram.axis][j]*member.diagramValues[i]*diagramPayload.diagram.factor;
          assert(Math.abs(value-expected)<1e-6,`${kind} diagram not in rolled local axes`);
        }));
      }
      const projected=await page.evaluate(paths=>paths.flatMap(path=>path.points.map(point=>window.pyniteViewer.project(point))),paths);
      projected.forEach(([x,y])=>assert(x>5&&x<1275&&y>5&&y<715,`${kind} diagram clipped after fit`));
      if(kind==='moment_z')await page.screenshot({path:path.join(output,'desktop-moment-z.png')});
    }
    const png=await page.evaluate(()=>window.pyniteViewer.exportImage());
    assert(png.startsWith('data:image/png;base64,'),'PNG export failed');
    const pngBytes=Buffer.from(png.split(',')[1],'base64');
    assert.equal(pngBytes.readUInt32BE(16),1280);assert.equal(pngBytes.readUInt32BE(20),720);
    fs.writeFileSync(path.join(output,'export-moment-z.png'),pngBytes);
    await page.evaluate(({payload,colors})=>{window.pyniteViewer.update({...payload,colors});window.pyniteViewer.orient(0);},
      {payload:payload.qaDiagrams.moment_z,colors:dark.colors});
    await page.waitForTimeout(150);
    assert.equal(await page.locator('#result-legend').evaluate(element=>getComputedStyle(element).color),'rgb(238, 241, 242)','Dark legend text has insufficient contrast');
    await page.screenshot({path:path.join(output,'desktop-moment-z-dark.png')});
    await page.evaluate(payload=>window.pyniteViewer.update(payload),payload);
    assert(await page.locator('#result-legend').isHidden(),'Result legend was not cleared');
    const split=payload.qaSplit;
    assert.equal(split.nodes.length,3);assert.equal(split.members.length,2);
    assert.equal(split.members[0].end,split.members[1].start,'Split viewport segments do not share a joint');
    assert.equal(split.loads.find(load=>load.name==='L5').position,1,'Split point force lost its member-end station');
    await page.evaluate(payload=>{window.pyniteViewer.update(payload);window.pyniteViewer.orient(0);},split);
    await page.waitForTimeout(200);
    for(const node of split.nodes){
      const [x,y]=await page.evaluate(position=>window.pyniteViewer.project(position),node.position);
      assert(x>15&&x<1265&&y>15&&y<705,'Split XYZ geometry clipped');
    }
    await page.screenshot({path:path.join(output,'desktop-spatial-split.png')});
    await page.evaluate(payload=>window.pyniteViewer.update({...payload,loads:[]}),split);
    const joint=split.nodes.find(node=>node.name===split.members[0].end);
    const jointPoint=await page.evaluate(position=>window.pyniteViewer.project(position),joint.position);
    await page.mouse.click(...jointPoint);
    assert.deepEqual(await page.evaluate(()=>window.selectedEvent),['nodes',joint.name],'New split joint could not be picked');
    const truss=payload.qaTruss;
    assert(truss.members.every(member=>member.kind==='truss'),'Missing truss type in viewport');
    assert(truss.members.every(member=>member.diagramValues.every(value=>Math.abs(value-1.25)<1e-7)),'Tripod axial diagram differs from analytical force');
    await page.evaluate(payload=>{window.pyniteViewer.update(payload);window.pyniteViewer.orient(0);},truss);
    await page.waitForTimeout(200);
    assert((await page.evaluate(()=>window.pyniteViewer.state())).drawCalls>10,'Truss viewport is empty');
    for(const member of truss.members){
      assert.equal(member.displacements.length,member.points.length);
      const first=member.displacements[0],last=member.displacements.at(-1);
      for(const [i,motion] of member.displacements.entries()){
        const fraction=i/(member.displacements.length-1);
        motion.forEach((value,j)=>assert(Math.abs(value-first[j]-fraction*(last[j]-first[j]))<1e-9,'Truss deformation is not linear between joints'));
      }
    }
    await page.screenshot({path:path.join(output,'desktop-truss-tripod.png')});
    await page.evaluate(({payload,colors})=>window.pyniteViewer.update({...payload,colors}),{payload:truss,colors:dark.colors});
    await page.waitForTimeout(100);
    await page.screenshot({path:path.join(output,'desktop-truss-tripod-dark.png')});
    const converted=payload.qaConversion;
    assert(converted.nodes.every(node=>node.position[2]===24),'Converted geometry lost its Z offset');
    const angled=converted.loads.find(load=>load.name==='L2');
    assert(Math.abs(angled.vector[0]-.5)<1e-9 && Math.abs(angled.vector[1]+Math.sqrt(3)/2)<1e-9 && Math.abs(angled.vector[2])<1e-9,
      'Converted force arrow no longer lies in its original XY direction');
    for(const [name,colors] of [['light',converted.colors],['dark',dark.colors]]){
      await page.evaluate(({payload,colors})=>{window.pyniteViewer.update({...payload,colors});window.pyniteViewer.orient(0);}, {payload:converted,colors});
      await page.waitForTimeout(200);
      assert((await page.evaluate(()=>window.pyniteViewer.state())).drawCalls>10,'Converted model viewport is empty');
      for(const node of converted.nodes){
        const [x,y]=await page.evaluate(position=>window.pyniteViewer.project(position),node.position);
        assert(x>15&&x<1265&&y>15&&y<705,'Converted geometry clipped');
      }
      await page.screenshot({path:path.join(output,`desktop-converted-cantilever-${name}.png`)});
    }
    if(process.env.VIEWPORT_BENCHMARK==='1')await require('./viewport3d_benchmark.cjs')(page,payload,output);
    assert.deepEqual(errors,[]);
    await page.evaluate(payload=>{window.pyniteViewer.update({...payload,mode:'select',plane:'XY',moveNodes:true});window.pyniteViewer.orient(1);window.moveEvent=null;},payload);
    dragFrom=await page.evaluate(()=>window.pyniteViewer.project([0,144,0]));
    dragTo=await page.evaluate(()=>window.pyniteViewer.project([24,168,0]));
    await page.mouse.move(...dragFrom);await page.mouse.down();await page.mouse.move(...dragTo,{steps:5});
    assert((await page.evaluate(()=>window.pyniteViewer.state())).dragging,'Context-loss test did not start a node drag');
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
    await page.mouse.up();
    assert(!(await page.evaluate(()=>window.pyniteViewer.state())).dragging,'Graphics loss left an active node drag');
    assert.equal(await page.evaluate(()=>window.pyniteViewer.state().labelCache.entries),0,'Graphics loss retained label textures');
    assert.equal(await page.evaluate(()=>window.moveEvent),null,'Graphics loss committed a node move');
    console.log('PASS: desktop geometry, six-DOF supports/springs/hover/visibility, gizmo, orbit/picking, contained/crossing/additive/cancelled box selection, drawing, constrained node dragging/cancellation/stale updates, result overlays, PNG, diagnostics and dark/context-loss states.');
  }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;}).finally(()=>server.close());
