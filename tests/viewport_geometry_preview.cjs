/* Candidate geometry must render without becoming editable model geometry. */
const assert=require('node:assert/strict');
module.exports=async function checkGeometryPreview(page,payload){
  await page.evaluate(data=>{window.pyniteViewer.update(data);window.pyniteViewer.orient(1);window.pyniteViewer.fit();window.pyniteViewer.exportImage();},payload);
  const before=await page.evaluate(()=>window.pyniteViewer.state());
  const xs=payload.nodes.map(node=>node.position[0]),extent=Math.max(...xs)-Math.min(...xs)||240;
  const a=[Math.max(...xs)+extent,0,0],b=[Math.max(...xs)+extent*2,extent/2,0];
  const candidate={...payload,geometryPreview:{nodes:[a,b],lines:[[a,b]]}};
  await page.evaluate(data=>{window.pyniteViewer.update(data);window.pyniteViewer.exportImage();},candidate);
  const shown=await page.evaluate(()=>window.pyniteViewer.state());
  assert.deepEqual(shown.camera,before.camera,'Candidate preview moved camera without Fit');
  assert.deepEqual(shown.nodes,before.nodes,'Ghost nodes entered the model');
  assert.deepEqual(shown.selection,before.selection,'Candidate changed selection');
  assert(shown.drawCalls>before.drawCalls,'Candidate ghost geometry did not render');
  const selected=await page.evaluate(async data=>{
    const THREE=await import('three');
    const {rectangleSelection}=await import('./selection.js');
    const camera=new THREE.PerspectiveCamera(45,innerWidth/innerHeight,.1,1e7);
    const state=window.pyniteViewer.state();camera.position.fromArray(state.camera);camera.lookAt(new THREE.Vector3(...state.target));camera.updateMatrixWorld();
    return rectangleSelection(data,camera,innerWidth,innerHeight,[0,0],[innerWidth,innerHeight]);
  },candidate);
  assert(selected.every(([kind,name])=>(kind==='nodes'?payload.nodes:kind==='members'?payload.members:payload.surfaceMeshes||[]).some(item=>item.name===name)), 'Ghost entered box selection');
  await page.evaluate(()=>{window.pyniteViewer.fit();window.pyniteViewer.exportImage();});
  const projected=await page.evaluate(points=>points.map(point=>window.pyniteViewer.project(point)),[a,b]);
  const viewport=page.viewportSize();
  assert(projected.every(([x,y])=>x>0&&x<viewport.width&&y>0&&y<viewport.height),'Fit omitted candidate geometry');
  await page.evaluate(data=>{window.pyniteViewer.update(data);window.pyniteViewer.fit();window.pyniteViewer.exportImage();},payload);
  const cleared=await page.evaluate(()=>window.pyniteViewer.state());
  for(let i=0;i<5;i++){
    await page.evaluate(data=>{window.pyniteViewer.update(data);window.pyniteViewer.exportImage();},candidate);
    await page.evaluate(data=>{window.pyniteViewer.update(data);window.pyniteViewer.exportImage();},payload);
  }
  const repeated=await page.evaluate(()=>window.pyniteViewer.state());
  assert.equal(repeated.resources.geometries,cleared.resources.geometries,'Preview/cancel leaked graphics geometry');
};
