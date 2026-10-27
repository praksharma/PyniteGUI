/* Display-only label controls in the real offline renderer. */
const assert=require('node:assert/strict');

module.exports=async function checkReadability(page,payload,screenshot){
  const selections=await page.evaluate(async()=>{
    const {drawDiagram,diagramLabelIndices}=await import('./diagrams.js');
    const values=[1,-2,3,0],member={name:'Test',points:[[0,0,0],[1,0,0],[2,0,0],[3,0,0]],
      diagramValues:values,axes:[[1,0,0],[0,1,0],[0,0,1]]};
    const records=[];
    for(const [endValues,extrema,ids] of [[true,false,true],[false,true,false],[false,false,false],[true,true,true]]){
      const diagram={axis:1,factor:1,color:'moment',label:'Mz',unit:'kip-in',displayFactor:1,endValues,extrema,ids};
      const objects=[],labels=[],lines=[];
      drawDiagram(member,diagram,{add:o=>objects.push(o)},points=>lines.push(points.map(p=>p.toArray())),text=>labels.push(text),{moment:'#b53c5b'});
      records.push({indices:diagramLabelIndices(values,diagram),labels,lines,
        ribbon:Array.from(objects[0].geometry.attributes.position.array)});
      objects[0].geometry.dispose();objects[0].material.dispose();
    }
    return {records,legacyOn:diagramLabelIndices(values,{values:true}),legacyOff:diagramLabelIndices(values,{values:false})};
  });
  assert.deepEqual(selections.records.map(r=>r.indices),[[0,3],[1,2],[],[0,1,2,3]]);
  assert(selections.records[0].labels.every(text=>text.startsWith('Test Mz ')));
  assert(selections.records[1].labels.every(text=>text.startsWith('Mz ')&&!text.includes('Test')));
  assert.deepEqual(selections.legacyOn,[0,1,2,3]);assert.deepEqual(selections.legacyOff,[]);
  for(const record of selections.records){
    assert.deepEqual(record.lines,selections.records[0].lines,'Label visibility changed diagram paths');
    assert.deepEqual(record.ribbon,selections.records[0].ribbon,'Label visibility changed ribbon geometry');
  }
  const full={...payload,ids:true,diagram:{...payload.diagram,ids:true,endValues:true,extrema:true}};
  const namesOff={...full,ids:false,diagram:{...full.diagram,ids:false}};
  const allOff={...namesOff,diagram:{...namesOff.diagram,endValues:false,extrema:false}};
  await page.evaluate(p=>{window.pyniteViewer.update(p);window.pyniteViewer.fit();window.pyniteViewer.orient(0);},full);
  await page.waitForTimeout(150);
  const first=await page.evaluate(()=>({state:window.pyniteViewer.state(),paths:window.pyniteViewer.diagramPoints()}));
  await page.evaluate(p=>window.pyniteViewer.update(p),namesOff);
  const noNames=await page.evaluate(()=>window.pyniteViewer.state());
  assert.equal(first.state.objects-noNames.objects,payload.nodes.length+payload.members.length,'Names did not hide independently');
  await page.evaluate(p=>window.pyniteViewer.update(p),allOff);
  const hidden=await page.evaluate(()=>({state:window.pyniteViewer.state(),paths:window.pyniteViewer.diagramPoints()}));
  assert(hidden.state.objects<noNames.objects,'Numerical labels did not hide');
  assert.deepEqual(hidden.paths,first.paths,'Visibility moved rolled diagram offsets');
  assert(hidden.state.camera.every((v,i)=>Math.abs(v-first.state.camera[i])<1e-9),'Visibility moved camera');
  assert((await page.locator('#result-legend').innerText()).includes(payload.diagram.combination));
  // Warm both sets of sprites before checking bounded reuse across toggles.
  for(let i=0;i<4;i++)await page.evaluate(p=>window.pyniteViewer.update(p),i%2?allOff:full);
  await page.waitForTimeout(100);
  const warm=await page.evaluate(()=>{window.pyniteViewer.exportImage();return window.pyniteViewer.state();});
  for(let i=0;i<10;i++)await page.evaluate(p=>window.pyniteViewer.update(p),i%2?allOff:full);
  await page.waitForTimeout(100);
  const final=await page.evaluate(()=>{window.pyniteViewer.exportImage();return window.pyniteViewer.state();});
  assert.equal(final.labelCache.entries,warm.labelCache.entries,'Repeated labels accumulated textures');
  assert.equal(final.resources.geometries,warm.resources.geometries,'Visibility leaked geometry');
  await page.evaluate(p=>window.pyniteViewer.update(p),{...namesOff,diagram:{...namesOff.diagram,endValues:false,extrema:true}});
  await page.waitForTimeout(150);
  await page.screenshot({path:screenshot});
  await page.evaluate(p=>window.pyniteViewer.update(p),payload);
};
