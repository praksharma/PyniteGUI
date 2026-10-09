/* Texture lifetime/budget and display-only refresh contracts in a real browser. */
const assert=require('node:assert/strict');

module.exports=async function checkCache(page,payload){
  const cache=await page.evaluate(async()=>{
    const {LabelTextures}=await import('./label_textures.js');
    const cache=new LabelTextures(65536,2),disposed=[];
    const acquire=(name,color='#000000')=>{
      const entry=cache.acquire(name,color);
      entry.texture.addEventListener('dispose',()=>disposed.push(name));return entry;
    };
    const a=acquire('A'),again=cache.acquire('A','#000000');
    const same=a===again;cache.release(a);cache.release(again);
    const b=acquire('B'),c=acquire('C'); // Evicts idle A, never live B.
    const afterEviction=[...disposed];
    const transient=acquire('D'); // Both cached entries are live.
    const transientCached=transient.cached;cache.release(transient);
    cache.clearUnused();const liveEntries=cache.state().entries;
    cache.release(b);cache.release(c);cache.clearUnused();
    const empty=cache.state();
    const red=acquire('A','#ff0000'),black=acquire('A','#000000');
    const differentColor=red.texture!==black.texture;
    cache.release(red);cache.release(black);cache.clearUnused();
    const tiny=new LabelTextures(1,1),huge=tiny.acquire('oversized','#000');
    const oversizedCached=huge.cached;tiny.release(huge);
    return {same,afterEviction,transientCached,liveEntries,empty,differentColor,oversizedCached,disposed};
  });
  assert(cache.same,'Repeated labels did not share a texture');
  assert.deepEqual(cache.afterEviction,['A'],'Cache evicted a live entry or did not evict idle LRU');
  assert.equal(cache.transientCached,false);
  assert.equal(cache.liveEntries,2,'Clearing idle textures disposed live labels');
  assert.equal(cache.empty.entries,0);assert.equal(cache.empty.bytes,0);
  assert(cache.differentColor,'Theme colors incorrectly shared a label texture');
  assert.equal(cache.oversizedCached,false);
  assert.deepEqual(cache.disposed.slice(0,4),['A','D','B','C'],'Texture lifetimes were not independent');

  const scene=await page.evaluate(async payload=>{
    const viewer=window.pyniteViewer;
    const base={...payload,localAxes:false,labels:true};
    const frame=()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
    viewer.update(base);viewer.fit();await frame();const first=viewer.state();
    const selected={...base,selection:[['nodes',base.nodes[0].name]],boxSelect:true};
    viewer.update(selected);await frame();const selection=viewer.state();
    viewer.update({...selected,mode:'pan'});await frame();const mode=viewer.state();
    viewer.update({...base,supports:false});await frame();const hidden=viewer.state();
    viewer.update(base);await frame();const rebuilt=viewer.state();
    const moved={...base,nodes:base.nodes.map((node,i)=>i===0?{...node,position:node.position.map((x,k)=>x+(k===0?12:0))}:node)};
    viewer.update(moved);await frame();const geometry=viewer.state();
    viewer.update({...base,labels:false,diagram:null});await frame();const cleared=viewer.state();
    viewer.update({...base,localAxes:true});await frame();const axes=viewer.state();
    viewer.update({...base,localAxes:true,selection:selected.selection});await frame();const axesSelection=viewer.state();
    viewer.update(payload);
    return {first,selection,mode,hidden,rebuilt,geometry,cleared,axes,axesSelection};
  },payload);
  assert.equal(scene.selection.rebuilds,scene.first.rebuilds,'Selection rebuilt overlays');
  assert.equal(scene.mode.rebuilds,scene.first.rebuilds,'Mode changes rebuilt overlays');
  assert.equal(scene.mode.incrementalUpdates,scene.first.incrementalUpdates+2);
  assert.deepEqual(scene.selection.resources,scene.first.resources,'Selection allocated new graphics resources');
  assert.deepEqual(scene.selection.selection,[['nodes',payload.nodes[0].name]]);
  assert(scene.hidden.rebuilds>scene.mode.rebuilds,'Support visibility did not rebuild');
  assert(scene.rebuilt.labelCache.hits>scene.first.labelCache.hits,'Labels were not reused across rebuilds');
  assert(scene.geometry.rebuilds>scene.rebuilt.rebuilds,'Geometry edit was treated as display-only');
  assert.equal(scene.cleared.labelCache.entries,0,'Hiding labels retained unused textures');
  assert(scene.axesSelection.rebuilds>scene.axes.rebuilds,'Selected local axes did not rebuild');
  for(const state of Object.values(scene)){
    assert(state.labelCache.entries<=state.labelCache.maxEntries,'Texture count budget exceeded');
    assert(state.labelCache.bytes<=state.labelCache.maxBytes,'Texture memory budget exceeded');
  }

  const overlays=await page.evaluate(async payload=>{
    const viewer=window.pyniteViewer,results=[];
    const frame=()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
    for(const [kind,definition] of Object.entries(payload.qaDiagrams)){
      const base={...definition,localAxes:false};
      viewer.update(base);await frame();const before=viewer.state(),points=viewer.diagramPoints(),supports=viewer.supportSymbols();
      viewer.update({...base,selection:[['members',base.members[0].name]]});await frame();
      results.push({kind,before,after:viewer.state(),points,afterPoints:viewer.diagramPoints(),supports,afterSupports:viewer.supportSymbols()});
    }
    const before=viewer.state();
    viewer.update({...payload,colors:{...payload.colors,label:'#bbccdd',canvas:'#101010'}});await frame();
    const theme=viewer.state();viewer.update(payload);
    const THREE=await import('three'),{drawFrame,recolorFrame}=await import('./frame_meshes.js');
    const group=new THREE.Group(),picks=[];
    drawFrame({...payload,selection:[]},1,group,picks);
    recolorFrame({...payload,selection:[['nodes',payload.nodes[0].name],['members',payload.members[0].name]]},group);
    const colors=picks.map(mesh=>{const color=new THREE.Color();mesh.getColorAt(0,color);return color.getHexString();});
    const expectedColor=new THREE.Color(payload.colors.accent).getHexString();
    group.traverse(object=>{if(object.isInstancedMesh)object.dispose();object.geometry?.dispose();object.material?.dispose();});
    return {results,before,theme,colors,expectedColor};
  },payload);
  assert.equal(overlays.results.length,6);
  for(const row of overlays.results){
    assert.equal(row.after.rebuilds,row.before.rebuilds,`${row.kind} selection rebuilt result overlays`);
    assert.deepEqual(row.after.resources,row.before.resources);
    assert.deepEqual(row.afterPoints,row.points,`${row.kind} display refresh moved force diagrams`);
    assert.deepEqual(row.afterSupports,row.supports,'Selection changed support picking anchors');
  }
  assert(overlays.theme.rebuilds>overlays.before.rebuilds,'Theme changes did not rebuild');
  assert.deepEqual(overlays.colors,[overlays.expectedColor,overlays.expectedColor],'Incremental refresh lost selected instance colors');
};
