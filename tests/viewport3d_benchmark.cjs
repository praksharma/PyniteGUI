/* Optional desktop lattice benchmark. Timings are observations, not hardware-independent gates. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

function lattice(base, bays, storeys) {
  const nodes=[],members=[],lookup=new Map();
  for(let y=0;y<=storeys;y++)for(let z=0;z<=bays;z++)for(let x=0;x<=bays;x++){
    const name=`N${nodes.length+1}`;
    nodes.push({name,position:[x*240,y*144,z*180],restraints:Array(6).fill(false),springs:Array(6).fill(0)});
    lookup.set(`${x},${y},${z}`,name);
  }
  for(let y=0;y<=storeys;y++)for(let z=0;z<=bays;z++)for(let x=0;x<=bays;x++){
    for(const [dx,dy,dz,axes] of [[1,0,0,[[1,0,0],[0,1,0],[0,0,1]]],
      [0,1,0,[[0,1,0],[-1,0,0],[0,0,1]]],[0,0,1,[[0,0,1],[0,1,0],[-1,0,0]]]]){
      const end=lookup.get(`${x+dx},${y+dy},${z+dz}`);
      if(end)members.push({name:`M${members.length+1}`,start:lookup.get(`${x},${y},${z}`),end,kind:'frame',axes});
    }
  }
  return {...base,nodes,members,loads:[],selection:[],diagram:null,deformed:false,localAxes:false,
    supports:false,mode:'select',moveNodes:false,boxSelect:false,labels:false,plane:'XY',offset:0};
}

module.exports=async function benchmark(page,base,output){
  const models=[];
  for(const [bays,storeys] of [[3,3],[6,4],[9,5]]){
    const model=lattice(base,bays,storeys);
    for(const labels of [false,true]){
      const data={...model,labels};
      const measure=async()=>page.evaluate(async data=>{
        const start=performance.now();window.pyniteViewer.update(data);
        const updateMilliseconds=performance.now()-start;window.pyniteViewer.orient(0);
        await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
        const frames=[];let last=performance.now();
        for(let i=0;i<12;i++){
          await new Promise(resolve=>requestAnimationFrame(resolve));
          const now=performance.now();frames.push(now-last);last=now;
        }
        const canvas=document.querySelector('canvas'),gl=canvas.getContext('webgl2');
        const rgba=new Uint8Array(canvas.width*canvas.height*4);
        gl.readPixels(0,0,canvas.width,canvas.height,gl.RGBA,gl.UNSIGNED_BYTE,rgba);
        let engineering=0;
        // Exclude the gizmo and pale grid: count actual dark frame pixels in the model region.
        for(let y=80;y<canvas.height-80;y++)for(let x=80;x<canvas.width-170;x++){
          const i=4*(y*canvas.width+x);
          if(Math.max(rgba[i],rgba[i+1],rgba[i+2])<180)engineering++;
        }
        return {updateMilliseconds,frameMilliseconds:frames,pixels:engineering/(canvas.width*canvas.height),...window.pyniteViewer.state()};
      },data);
      const first=await measure();
      assert(first.pixels>.0005,'Blank large-model canvas');
      assert(first.drawCalls>model.members.length,'Large-model geometry not rendered');
      for(const node of [model.nodes[0],model.nodes.at(-1)]){
        const [x,y]=await page.evaluate(position=>window.pyniteViewer.project(position),node.position);
        assert(x>10&&x<1270&&y>10&&y<710,'Large model clipped');
      }
      await page.screenshot({path:path.join(output,`desktop-benchmark-${model.members.length}-${labels?'labels':'geometry'}.png`)});
      const before=first.camera;
      await page.mouse.move(1200,80);await page.mouse.down();await page.mouse.move(1150,140,{steps:5});await page.mouse.up();
      await page.waitForTimeout(150);
      const after=await page.evaluate(()=>window.pyniteViewer.state().camera);
      assert(Math.hypot(...after.map((value,i)=>value-before[i]))>1,'Large-model orbit did not respond');
      await page.evaluate(base=>window.pyniteViewer.update({...base,labels:false}),base);
      const repeated=await measure();
      assert.deepEqual(repeated.resources,first.resources,'Resources accumulated after model replacement');
      models.push({members:model.members.length,nodes:model.nodes.length,labels,
        updateMilliseconds:first.updateMilliseconds,rebuildMilliseconds:repeated.updateMilliseconds,
        frameMilliseconds:repeated.frameMilliseconds,drawCalls:repeated.drawCalls,resources:repeated.resources,pixels:repeated.pixels});
    }
  }
  const report={viewport:{width:1280,height:720},chromium:page.context().browser().version(),
    driver:await page.evaluate(()=>window.pyniteViewer.diagnostics()),models};
  fs.writeFileSync(path.join(output,'desktop-benchmark.json'),JSON.stringify(report,null,2));
  console.log('BENCHMARK',JSON.stringify(report));
};
