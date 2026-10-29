/* Camera-only framing: no geometry/result rebuild or selection changes. */
const assert=require('node:assert/strict');
module.exports=async(page,payload,points,screenshot)=>{
  await page.evaluate(payload=>{window.pyniteViewer.update(payload);window.pyniteViewer.fit();},payload);
  await page.waitForTimeout(100);
  // Flush lazy sprite texture uploads before measuring retained GPU resources.
  const flush=()=>page.evaluate(()=>{window.pyniteViewer.exportImage();window.pyniteViewer.exportImage();});
  await flush();
  const before=await page.evaluate(()=>window.pyniteViewer.state());
  const low=[0,1,2].map(axis=>Math.min(...points.map(point=>point[axis])));
  const high=[0,1,2].map(axis=>Math.max(...points.map(point=>point[axis])));
  const margin=Math.max(payload.grid*2,...high.map((value,axis)=>(value-low[axis])*.12),1);
  const bounds=[low.map(value=>value-margin),high.map(value=>value+margin)];
  assert.equal(await page.evaluate(bounds=>window.pyniteViewer.focus(bounds),bounds),true);
  await page.waitForTimeout(100);
  await flush();
  const after=await page.evaluate(()=>window.pyniteViewer.state());
  const centre=low.map((value,axis)=>(value+high[axis])/2);
  centre.forEach((value,axis)=>assert(Math.abs(after.target[axis]-value)<1e-7,'Focus target is not the requested geometry centre'));
  const direction=state=>{
    const vector=state.camera.map((value,axis)=>value-state.target[axis]),length=Math.hypot(...vector);
    return vector.map(value=>value/length);
  };
  const a=direction(before),b=direction(after);
  assert(a.reduce((sum,value,axis)=>sum+value*b[axis],0)>1-1e-9,'Focus changed camera orientation');
  assert.equal(after.rebuilds,before.rebuilds,'Focus rebuilt the model');
  assert.deepEqual(after.selection,before.selection,'Focus changed model selection');
  assert.equal(after.resources.geometries,before.resources.geometries,'Focus allocated geometry');
  assert.deepEqual(after.labelCache,before.labelCache,'Focus created new labels');
  // Moving the camera can lazily upload a previously hidden label texture.
  // Its cached definition already exists; repeated focus must then stay flat.
  for(let repeat=0;repeat<3;repeat++){
    await page.evaluate(bounds=>window.pyniteViewer.focus(bounds),bounds);
    await page.waitForTimeout(30);
    await flush();
    const current=await page.evaluate(()=>window.pyniteViewer.state());
    assert.deepEqual(current.resources,after.resources,'Repeated focus leaked graphics resources');
  }
  const viewport=page.viewportSize();
  const projected=await page.evaluate(points=>points.map(point=>window.pyniteViewer.project(point)),points);
  assert(projected.every(([x,y])=>x>10&&x<viewport.width-10&&y>10&&y<viewport.height-10),'Focused geometry is clipped');
  for(const invalid of [null,[],[[0,0],[1,1]],[[1,0,0],[0,0,0]],[['bad',0,0],[1,1,1]]]){
    const rejected=await page.evaluate(value=>{
      const before=window.pyniteViewer.state().camera;
      const accepted=window.pyniteViewer.focus(value);
      return {accepted,before,after:window.pyniteViewer.state().camera};
    },invalid);
    assert.equal(rejected.accepted,false);
    assert.deepEqual(rejected.after,rejected.before,'Invalid focus moved the camera');
  }
  if(screenshot)await page.screenshot({path:screenshot});
  await page.evaluate(()=>window.pyniteViewer.fit());
  const restored=await page.evaluate(()=>window.pyniteViewer.state());
  restored.target.forEach((value,axis)=>assert(Math.abs(value-before.target[axis])<1e-7,'Full-model Fit did not recover'));
};
