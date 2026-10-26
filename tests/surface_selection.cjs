/* Surface box semantics in the existing offline desktop viewport. */
const assert=require('node:assert/strict');
module.exports=async(page,payload)=>{
  const checks=await page.evaluate(async()=>{
    const THREE=await import('three'),{rectangleSelection}=await import('./selection.js');
    const camera=new THREE.OrthographicCamera(-100,100,100,-100,.1,100);
    camera.position.set(0,0,10);camera.lookAt(0,0,0);camera.updateMatrixWorld();
    const mesh={name:'Floor',nodes:[[-80,-80,0],[80,-80,0],[80,80,0],[-80,80,0]].map(position=>({position})),surfaces:[[0,1,2,3]]};
    const data={nodes:[],members:[],surfaceMeshes:[mesh]};
    const select=(from,to,input=data)=>rectangleSelection(input,camera,200,200,from,to).map(item=>item.join(':'));
    const ring={name:'Opening',nodes:[],surfaces:[]},coordinates=[-80,-20,20,80];
    for(const y of coordinates)for(const x of coordinates)ring.nodes.push({position:[x,y,0]});
    for(let y=0;y<3;y++)for(let x=0;x<3;x++)if(x!==1||y!==1){const n=y*4+x;ring.surfaces.push([n,n+1,n+5,n+4]);}
    const stacked={...mesh,name:'Upper',nodes:mesh.nodes.map(node=>({position:[node.position[0],node.position[1],-20]}))};
    const behind={...mesh,nodes:mesh.nodes.map(node=>({position:[node.position[0],node.position[1],20]}))};
    return {
      enclosed:select([10,10],[190,190]), partial:select([40,40],[50,50]),
      interiorCrossing:select([50,40],[40,50]), edgeCrossing:select([25,90],[15,110]),
      outside:select([199,0],[190,10]),
      hole:select([110,90],[90,110],{...data,surfaceMeshes:[ring]}),
      ringFace:select([50,40],[40,50],{...data,surfaceMeshes:[ring]}),
      stacked:select([10,10],[190,190],{...data,surfaceMeshes:[mesh,stacked]}),
      hidden:select([10,10],[190,190],{...data,surfaceMeshes:[]}),
      clipped:select([10,10],[190,190],{...data,surfaceMeshes:[behind]}),
    };
  });
  assert.deepEqual(checks.enclosed,['surfaces:Floor']);
  assert.deepEqual(checks.partial,[],'Window selection must enclose the complete recipe');
  assert.deepEqual(checks.interiorCrossing,['surfaces:Floor'],'Crossing rectangle inside a face was missed');
  assert.deepEqual(checks.edgeCrossing,['surfaces:Floor']);
  assert.deepEqual(checks.outside,[]);
  assert.deepEqual(checks.hole,[],'Recipe bounds incorrectly filled an opening during selection');
  assert.deepEqual(checks.ringFace,['surfaces:Opening']);
  assert.deepEqual(checks.stacked,['surfaces:Floor','surfaces:Upper']);
  assert.deepEqual(checks.hidden,[]);assert.deepEqual(checks.clipped,[]);
  await page.evaluate(payload=>{
    window.pyniteViewer.update({...payload,boxSelect:true,deformed:false});
    window.pyniteViewer.fit();window.pyniteViewer.orient(0);
    window.surfaceBox=null;
    addEventListener('modelBoxSelected',event=>window.surfaceBox=event.detail);
  },payload);
  await page.waitForTimeout(120);
  const drag=async(from,to)=>{
    await page.mouse.move(...from);await page.mouse.down();await page.mouse.move(...to,{steps:6});await page.mouse.up();
    return page.evaluate(()=>window.surfaceBox);
  };
  const camera=await page.evaluate(()=>window.pyniteViewer.state().camera);
  let selection=await drag([5,5],[1275,795]);
  assert(selection.selections.some(([kind,name])=>kind==='surfaces'&&name==='Floor'));
  assert(selection.selections.some(([kind,name])=>kind==='surfaces'&&name==='Tower'));
  assert(selection.selections.some(([kind])=>kind==='members'));
  const centre=await page.evaluate(()=>window.pyniteViewer.project([120,144,90]));
  selection=await drag([centre[0]-6,centre[1]-6],[centre[0]+6,centre[1]+6]);
  assert(!selection.selections.some(([kind])=>kind==='surfaces'),'Small enclosed box selected a whole surface');
  await page.keyboard.down('Control');
  selection=await drag([centre[0]+6,centre[1]-6],[centre[0]-6,centre[1]+6]);
  await page.keyboard.up('Control');
  assert(selection.extend);
  assert(selection.selections.some(([kind,name])=>kind==='surfaces'&&name==='Floor'));
  const after=await page.evaluate(()=>window.pyniteViewer.state().camera);
  assert(after.every((value,index)=>Math.abs(value-camera[index])<1e-6),'Surface box selection moved camera');
  await page.evaluate(()=>window.surfaceBox=null);
  await page.mouse.move(5,5);await page.mouse.down();await page.mouse.move(500,300);
  await page.keyboard.press('Escape');await page.mouse.up();
  assert.equal(await page.evaluate(()=>window.surfaceBox),null);
};
