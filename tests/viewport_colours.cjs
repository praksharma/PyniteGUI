/* Signed geometry, native-inspection bridge messages and bounded rebuilds. */
const assert=require('node:assert/strict');
module.exports=async(page,payload,screenshot)=>{
  const semantics=await page.evaluate(async()=>{
    const THREE=await import('three'),{drawColourMap,signedColor,signedSpans,legendLines}=await import('./diagrams.js');
    const diagram={style:'colour',colourBound:2,signedColors:['#2469ad','#69777e','#c35d0a'],displayFactor:1,minimum:-2,maximum:2,label:'Mz',unit:'kip-in',combination:'Test',kind:'moment_z'};
    const group=new THREE.Group();
    drawColourMap({points:[[0,0,0],[10,0,0]],diagramValues:[2,-2]},diagram,group);
    const rows=group.children.map(mesh=>{
      const matrix=new THREE.Matrix4();mesh.getMatrixAt(0,matrix);
      return {pattern:mesh.userData.signedPattern,count:mesh.count,centre:new THREE.Vector3().setFromMatrixPosition(matrix).toArray()};
    });
    const jumps=signedSpans([[0,0,0],[5,0,0],[5,0,0],[10,0,0]],[2,2,-2,-2]).length;
    const colours=[-2,0,2].map(v=>signedColor(v,diagram).getHexString());
    for(const line of group.children){line.geometry.dispose();line.material.dispose();line.dispose();}
    return {rows,jumps,colours,legend:legendLines(diagram)};
  });
  assert.equal(semantics.jumps,2,'Colour map joined opposite sides of a load jump');
  assert.deepEqual(semantics.colours,['2469ad','69777e','c35d0a']);
  assert.deepEqual(semantics.rows,[{pattern:'dashed',count:1,centre:[7.5,0,0]},{pattern:'solid',count:1,centre:[2.5,0,0]}]);
  assert(semantics.legend.some(line=>line.includes('Negative blue/dashed')));
  assert(payload.probe && payload.diagram.colourBound>0);
  await page.evaluate(data=>{window.pyniteViewer.update(data);window.pyniteViewer.fit();window.pyniteViewer.exportImage();},payload);
  const first=await page.evaluate(()=>window.pyniteViewer.state());
  await page.screenshot({path:screenshot});
  for(let i=0;i<4;i++){
    await page.evaluate(data=>{window.pyniteViewer.update({...data,diagram:{...data.diagram,style:'offset'}});window.pyniteViewer.exportImage();},payload);
    await page.evaluate(data=>{window.pyniteViewer.update(data);window.pyniteViewer.exportImage();},payload);
  }
  const final=await page.evaluate(()=>window.pyniteViewer.state());
  assert.deepEqual(final.camera,first.camera,'Style switch changed camera');
  assert(final.resources.geometries<=first.resources.geometries+2,'Colour/probe rebuilds leaked geometry');
  assert(final.resources.textures<=first.resources.textures+3,'Colour/probe rebuilds leaked textures');
  // Picking stays attached to reference geometry; only ordinary Select clicks inspect.
  await page.evaluate(()=>{window.probeRequest=null;window.pyniteBridge=new Proxy({select(){},inspect(name,data){window.probeRequest={name,...JSON.parse(data)};}},{get:(target,key)=>target[key]||(()=>{})});});
  const member=payload.members.find(m=>m.name==='M1');
  const a=payload.nodes.find(n=>n.name===member.start).position,b=payload.nodes.find(n=>n.name===member.end).position;
  const point=a.map((v,i)=>(v+b[i])/2);
  const xy=await page.evaluate(p=>window.pyniteViewer.project(p),point);
  await page.mouse.click(...xy);
  const request=await page.evaluate(()=>window.probeRequest);
  assert(request && request.name==='M1','Member click did not request station inspection');
  assert.equal(request.revision,payload.revision);
  assert.equal(request.position.length,3);
  await page.evaluate(()=>{delete window.pyniteBridge;});
};
