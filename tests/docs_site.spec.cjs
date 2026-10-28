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
    await page.locator('label[for="__palette_1"]').click();
    await page.waitForFunction(()=>document.body.dataset.mdColorScheme==='slate');
    await page.screenshot({path:path.join(output,'surfaces-dark.png')});
    for(const [url,title] of [['features/','Feature Index'],['start/first-model/','Your First Model'],
      ['analysis/loads/','Point, Angled and Distributed Loads'],['automation/mcp/','Optional MCP Server'],
      ['reference/units/','Units and Conversions'],['project/roadmap/','Brecon Roadmap']]){
      await page.goto(origin+prefix+url);
      await page.locator('article h1').filter({hasText:title}).waitFor();
      assert((await page.locator('article').innerText()).length>250,`Empty ${url}`);
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
