/* Optional desktop documentation QA against the built GitHub Pages subpath. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const http = require('node:http');
const path = require('node:path');
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const root = path.resolve(__dirname, '../site');
const output = process.env.DOCS_QA_OUTPUT || '/tmp/pynite-docs-qa';
const prefix = '/PyniteGUI/';
fs.mkdirSync(output, {recursive:true});
const mime = {'.html':'text/html', '.js':'text/javascript', '.css':'text/css', '.json':'application/json',
  '.wasm':'application/wasm', '.svg':'image/svg+xml', '.png':'image/png'};
const server = http.createServer((request,response)=>{
  const pathname = decodeURIComponent(new URL(request.url,'http://localhost').pathname);
  if(!pathname.startsWith(prefix)){response.writeHead(404).end();return;}
  let filename = path.resolve(root,pathname.slice(prefix.length));
  if(filename!==root&&!filename.startsWith(root+path.sep)){response.writeHead(403).end();return;}
  try{
    if(fs.statSync(filename).isDirectory())filename=path.join(filename,'index.html');
    response.setHeader('Content-Type',mime[path.extname(filename)]||'application/octet-stream');
    response.end(fs.readFileSync(filename));
  }catch{response.writeHead(404).end();}
});

(async()=>{
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  const browser = await chromium.launch({headless:true});
  try{
    const page = await browser.newPage({viewport:{width:1440,height:1000}});
    const origin=`http://127.0.0.1:${server.address().port}`;
    const errors=[],missing=[],requests=[];
    page.on('pageerror',error=>errors.push(error.message));
    page.on('response',response=>{if(response.url().startsWith(origin)&&response.status()>=400)missing.push(response.url());});
    page.on('request',request=>requests.push(request.url()));
    await page.goto(origin+prefix);
    await page.locator('article h1').filter({hasText:'Brecon'}).waitFor();
    const images=await page.locator('article img').evaluateAll(nodes=>nodes.map(node=>({src:node.src,ok:node.complete&&node.naturalWidth>0})));
    assert(images.length>=3&&images.every(image=>image.ok),'Missing logo/screenshots');
    await page.screenshot({path:path.join(output,'home-light.png')});
    await page.getByPlaceholder('Search',{exact:true}).waitFor({state:'attached'});
    await page.keyboard.press('Control+k');
    await page.getByPlaceholder('Search',{exact:true}).fill('slab');
    const result=page.locator('a').filter({hasText:'Slab Placement and Main-Model Surfaces'}).first();
    await result.waitFor({state:'visible'});
    await page.screenshot({path:path.join(output,'search.png')});
    await result.click();
    await page.locator('article h1').filter({hasText:'Slab Placement and Main-Model Surfaces'}).waitFor();
    assert(page.url().includes('/PyniteGUI/surfaces/main-model/'),'Search lost the GitHub Pages base path');
    assert((await page.locator('article').innerText()).includes('Coupled rectangular slabs (experimental)'));
    const slabFigures=await page.locator('article img').evaluateAll(nodes=>nodes.map(node=>({src:node.src,ok:node.complete&&node.naturalWidth>0})));
    assert(slabFigures.some(image=>image.src.endsWith('coupled-slab-results.png'))&&
      slabFigures.some(image=>image.src.endsWith('slab-edge-supports.png'))&&slabFigures.every(image=>image.ok),'Missing slab inspection/support screenshots');
    await page.locator('label[for="__palette_1"]').click();
    await page.waitForFunction(()=>document.body.dataset.mdColorScheme==='slate');
    await page.screenshot({path:path.join(output,'surfaces-dark.png')});
    for(const [url,title] of [['features/','Feature Index'],['start/first-model/','Your First Model'],
      ['analysis/loads/','Point, Angled and Distributed Loads'],['analysis/pushover/','Steel Pushover'],['automation/mcp/','Optional MCP Server'],
      ['reference/units/','Units and Conversions'],['project/roadmap/','Brecon Roadmap'],
      ['modeling/3d/','3D Frames and Trusses'],
      ['modeling/supports/','Supports and Springs'],
      ['modeling/joint-springs/','Joint Springs'],
      ['surfaces/plates/','Rectangular Plate Analysis']]){
      await page.goto(origin+prefix+url);
      await page.locator('article h1').filter({hasText:title}).waitFor();
      assert((await page.locator('article').innerText()).length>250,`Empty ${url}`);
      if(url==='analysis/pushover/'){
        const figures=await page.locator('article img').evaluateAll(nodes=>nodes.map(node=>({src:node.src,ok:node.complete&&node.naturalWidth>0})));
        assert(figures.some(image=>image.src.endsWith('steel-pushover.png'))&&figures.every(image=>image.ok),'Missing steel pushover screenshot');
        assert((await page.locator('article').innerText()).includes('Partial'),'Missing partial-history contract');
        assert(figures.some(image=>image.src.endsWith('combined-pushover-prerequisite.png')),'Missing combined pushover prerequisite figure');
        assert((await page.locator('article').innerText()).includes('elastic_prerequisite_passed: false'),'Missing elastic rejection gate');
        assert((await page.locator('article').innerText()).includes('combined_plastic_validated: false'),'Missing combined-plastic scope');
        assert(figures.some(image=>image.src.endsWith('equilibrated-column.png')),'Missing corrected elastic comparison figure');
        assert((await page.locator('article').innerText()).includes('bounded_elastic_checks_passed: true'),'Missing bounded elastic readiness');
        assert((await page.locator('article').innerText()).includes('plastic_validated: false'),'Missing retained material-plastic gate');
        assert(figures.some(image=>image.src.endsWith('section-return.png')),'Missing local section-return figure');
        assert((await page.locator('article').innerText()).includes('bounded_local_section_checks_passed: true'),'Missing bounded local-section readiness');
        assert((await page.locator('article').innerText()).includes('global_yield_domain_convex: false'),'Missing nonconvex-domain scope');
        assert((await page.locator('article').innerText()).includes('frame_plastic_validated: false'),'Missing frame-plastic gate');
      }
      if(url==='modeling/joint-springs/'){
        const figures=await page.locator('article img').evaluateAll(nodes=>nodes.map(node=>({src:node.src,ok:node.complete&&node.naturalWidth>0})));
        assert(figures.some(image=>image.src.endsWith('joint-springs-editor.png'))&&figures.some(image=>image.src.endsWith('joint-springs-results.png'))&&figures.every(image=>image.ok),'Missing joint spring workflow screenshots');
        assert((await page.locator('article').innerText()).includes('tension positive'),'Missing spring force convention');
      }
      if(url==='modeling/supports/'){
        const figures=await page.locator('article img').evaluateAll(nodes=>nodes.map(node=>({src:node.src,ok:node.complete&&node.naturalWidth>0})));
        assert(figures.some(image=>image.src.endsWith('inclined-roller.png'))&&figures.every(image=>image.ok),'Missing inclined roller screenshot');
        assert(figures.some(image=>image.src.endsWith('spatial-inclined-properties.png')),'Missing spatial support normal controls');
        assert(figures.some(image=>image.src.endsWith('support-settlement.png')),'Missing imposed support movement example');
        assert(figures.some(image=>image.src.endsWith('pdelta-support-motion.png')),'Missing imposed-motion P-Delta example');
      }
      if(url==='modeling/3d/'){
        const figures=await page.locator('article img').evaluateAll(nodes=>nodes.map(node=>({src:node.src,ok:node.complete&&node.naturalWidth>0})));
        assert(figures.some(image=>image.src.endsWith('spatial-rotational-releases.png'))&&figures.every(image=>image.ok),'Missing spatial release screenshot');
        assert((await page.locator('article').innerText()).includes('Member-end bending') ||
          (await page.locator('article').innerText()).includes('member-end slopes'),'Missing released-end motion explanation');
      }
      if(url==='surfaces/plates/'){
        const figures=await page.locator('article img').evaluateAll(nodes=>nodes.map(node=>({src:node.src,ok:node.complete&&node.naturalWidth>0})));
        assert(figures.some(image=>image.src.endsWith('hydrostatic-wall.png'))&&figures.some(image=>image.src.endsWith('hydrostatic-wall-pressure.png'))&&figures.some(image=>image.src.endsWith('hydrostatic-wall-loading.png')),'Missing hydrostatic wall workflow screenshots');
        assert(figures.some(image=>image.src.endsWith('plate-recovery-benchmarks.png'))&&figures.every(image=>image.ok),'Missing plate benchmark figure');
        assert(figures.some(image=>image.src.endsWith('quad-shear-benchmarks.png')),'Missing Quad shear feasibility figure');
        assert(figures.some(image=>image.src.endsWith('quad-shear-boundaries.png')),'Missing boundary/interface shear figure');
        assert(figures.some(image=>image.src.endsWith('opening-shear-reference.png')),'Missing independent opening reference figure');
        assert(figures.some(image=>image.src.endsWith('equilibrated-quad-shear.png')),'Missing compatible-recovery comparison figure');
        assert((await page.locator('article').innerText()).includes('bounded_free_rim_recovery_ready'),'Missing bounded recovery versus production distinction');
        assert((await page.locator('article').innerText()).includes('bounded_reference_observables_ready'),'Missing independent reference-versus-recovery distinction');
        assert((await page.locator('article').innerText()).includes('production_ready: false'),'Missing preserved research checkpoint');
        assert((await page.locator('article').innerText()).includes('Guarded recovered centre shear'),'Missing current standalone workflow');
        assert((await page.locator('article').innerText()).includes('Finite frame-interface rejection'),'Missing rejected coupling scope');
        assert(figures.some(image=>image.src.endsWith('plate-recovered-shear.png'))&&figures.some(image=>image.src.endsWith('plate-recovered-shear-masks.png')),'Missing production recovery screenshots');
        assert(figures.some(image=>image.src.endsWith('plate-load-combinations.png'))&&
          figures.some(image=>image.src.endsWith('plate-load-program.png')),'Missing plate loading workflow screenshots');
      }
    }
    await page.setViewportSize({width:1280,height:900});
    await page.goto(origin+prefix+'features/');
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'Desktop horizontal overflow');
    await page.screenshot({path:path.join(output,'features-desktop.png')});
    assert(!requests.some(url=>/fonts\.(googleapis|gstatic)\.com/.test(url)),'Unexpected Google Fonts request');
    assert.deepEqual(missing,[],'Missing local documentation resources');
    assert.deepEqual(errors,[],'Documentation JavaScript errors');
    console.log('PASS: documentation pages, images, full-text search, GitHub Pages subpath, dark mode and desktop layout');
  }finally{await browser.close();server.close();}
})().catch(error=>{console.error(error);server.close();process.exitCode=1;});
