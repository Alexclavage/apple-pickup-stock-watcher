const {JSDOM, VirtualConsole}=require('jsdom');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const payload=JSON.parse(fs.readFileSync(0,'utf8'));
let assertions=0;
const check=(value,message)=>{assert.ok(value,message);assertions++};
const tick=()=>new Promise(resolve=>setImmediate(resolve));
const response=data=>({ok:true,json:async()=>structuredClone(data)});
async function create(){
  const calls=[],errors=[];
  let delayedModel=null,delayedDirectory=null,delayedCatalog=null;
  const console=new VirtualConsole();console.on('jsdomError',error=>errors.push(error));
  const dom=new JSDOM(payload.html,{runScripts:'dangerously',url:'http://localhost',virtualConsole:console,
    beforeParse(w){
      w.HTMLElement.prototype.scrollIntoView=function(){};
      w.fetch=async(url,options={})=>{
        const body=options.body?JSON.parse(options.body):null;calls.push({url,body});
        if(url==='/api/regions')return response(payload.regions);
        if(url==='/api/config')return response({config:body||payload.config,exists:true});
        if(url.startsWith('/api/stores?')){
          if(delayedDirectory)return new Promise(resolve=>{delayedDirectory.resolve=resolve});
          return response(payload.stores[url.split('=')[1]]||{stores:[],observed_at:'2026-10-30'});
        }
        if(url==='/api/catalog/model'){
          if(delayedModel)return new Promise(resolve=>{delayedModel.resolve=resolve});
          return response(model(body.market,body.model_id));
        }
        if(url==='/api/catalog/discover'){
          if(delayedCatalog)return new Promise(resolve=>{delayedCatalog.resolve=resolve});
          return response({items:model(body.market).products});
        }
        throw Error('Unexpected request: '+url);
      };
    }});
  const w=dom.window,d=w.document,$=id=>d.getElementById(id);
  const change=(id,value)=>{ $(id).value=value;$(id).dispatchEvent(new w.Event('change',{bubbles:true})); };
  const input=(id,value)=>{ $(id).value=value;$(id).dispatchEvent(new w.Event('input',{bubbles:true})); };
  await tick();await tick();
  return {dom,w,d,$,calls,errors,change,input,
    delayModel(){delayedModel={};return delayedModel},
    delayDirectory(){delayedDirectory={};return delayedDirectory},
    delayCatalog(){delayedCatalog={};return delayedCatalog}};
}
function model(market,id='iphone-18-pro'){
  return {market,model_id:id,count:2,cached:true,products:[0,1].map(i=>({
    market,currency:payload.regions[market].currency,part:market+'-FAKE'+i+'/A',
    name:'Example regional variant '+i,price:null,color:['Silver','Black'][i],storage:'256 GB'}))};
}
(async()=>{
  const t=await create(),{$,d,w,change,input}=t;
  const areas=()=>[...d.querySelectorAll('.region-entry')];
  check(areas().length===2,'load existing US/CA areas');
  check(d.querySelector('.product-entry .market').disabled,'SKU market cannot be silently reassigned');
  change('directoryMarket','MO');await tick();
  check($('addDirectoryStore').disabled,'directory-only market blocked');
  check($('directoryStatus').textContent.includes('Directory only'),'directory-only explained');
  change('directoryMarket','FR');await tick();
  $('addDirectoryStore').click();
  check(areas().length===2,'experimental opt-in required');
  check($('message').textContent.includes('experimental'),'explicit opt-in guidance');
  $('experimentalRegions').checked=true;$('experimentalRegions').dispatchEvent(new w.Event('change',{bubbles:true}));
  $('addDirectoryStore').click();
  check(areas().length===2,'store preparation never adds invalid FR area');
  check(!$('storeSetup').hidden,'store preparation visible');
  check($('modelMarket').value==='FR','selecting French store selects French catalog');
  check($('storeSetupTitle').textContent.includes('EUR'),'regional currency shown');
  check($('commitStore').disabled,'cannot commit without FR products/postcode');
  input('storeLocation','75001');
  check($('commitStore').disabled,'US/CA products do not satisfy French store');
  $('addProduct').click();
  check($('commitStore').disabled,'blank manual product cannot satisfy French store');
  check($('configurationIssues').textContent.includes('FR product is incomplete'),'manual product problem immediately visible');
  d.querySelectorAll('.product-entry')[2].querySelector('.remove').click();
  $('watchModel').click();await tick();await tick();
  check(!$('modelOptions').hidden,'real response preview available');
  check(d.querySelectorAll('.product-entry').length===2,'preview does not add products');
  $('applyModelFilters').click();
  check(d.querySelectorAll('.product-entry').length===4,'two regional variants selected');
  check(areas().length===2,'products still do not silently add area');
  check(!$('commitStore').disabled,'completed store ready');
  input('storeLocation','123');check($('commitStore').disabled,'incomplete French postcode blocked before area creation');input('storeLocation','75001');
  $('commitStore').click();
  check(areas().length===3,'one complete French area added');
  check($('storeSetup').hidden,'preparation completed');
  const fr=areas()[2];
  check(fr.querySelector('.country').value==='FR','area matches products country');
  check(fr.querySelector('.location').value==='75001','postcode retained');
  check(fr.querySelector('.areaReadiness').textContent.includes('2 associated regional products'),'association count visible');
  check(fr.querySelector('.areaReadiness').textContent.includes('checked by the watcher'),'configuration not called live coverage');
  // A second store near the same location shares one request area.
  $('directoryStore').selectedIndex=1;$('directoryStore').dispatchEvent(new w.Event('change'));
  $('addDirectoryStore').click();input('storeLocation','75001');$('commitStore').click();
  check(areas().length===3,'same location reuses an area');
  check(fr.querySelector('.areaStores').value.split(',').length===2,'precise two-store filter retained');
  $('save').click();await tick();await tick();
  const saved=t.calls.filter(c=>c.url==='/api/config'&&c.body).at(-1).body;
  check($('message').textContent.includes('Saved locally'),'completed configuration saved');
  check(saved.products.us.market==='US'&&saved.products.ca.market==='CA','legacy variants preserved');
  const group=[...d.querySelectorAll('.watch-group')].find(row=>row.textContent.includes('· FR'));
  group.querySelector('button').click();
  check($('configurationIssues').textContent.includes('FR store/area needs regional products'),'removal exposes actionable missing association');
  const saves=t.calls.filter(c=>c.url==='/api/config'&&c.body).length;
  $('save').click();await tick();
  check(t.calls.filter(c=>c.url==='/api/config'&&c.body).length===saves,'invalid area never posted');
  check($('modelMarket').value==='FR','save guidance selects corrective regional catalog');
  const currentFR=areas()[2];currentFR.querySelector('.remove').click();
  check(!$('configurationIssues').textContent.includes('FR store/area'),'removing incomplete area resolves issue');
  check(d.querySelectorAll('.product-entry').length===2,'US/CA variants survive removals');
  change('directoryMarket','FR');await tick();$('addDirectoryStore').click();$('cancelStore').click();
  check($('storeSetup').hidden&&areas().length===2,'cancel leaves existing areas intact');
  // Late model results must not recreate a preview after switching countries.
  const late=t.delayModel();change('modelMarket','US');$('watchModel').click();await tick();
  change('modelMarket','CA');late.resolve(response(model('US',$('modelPicker').value)));await tick();await tick();
  check($('modelOptions').hidden,'late wrong-country model result ignored');
  // The advanced catalog has the same protection.
  const catalog=t.delayCatalog();change('catalogMarket','US');$('findCatalog').click();await tick();
  change('catalogMarket','CA');catalog.resolve(response({items:model('US').products}));await tick();
  check(!$('catalogResults').children.length,'late advanced catalog ignored');
  // Editing area country clears old store filters; does not migrate SKUs.
  const area=areas()[0];area.querySelector('.areaStores').value=payload.stores.US.stores[0].id;
  area.querySelector('.country').value='CA';area.querySelector('.country').dispatchEvent(new w.Event('change',{bubbles:true}));
  check(area.querySelector('.areaStores').value==='','country edit clears foreign store IDs');
  check($('configurationIssues').textContent.includes('US products have no store/search area'),'orphan products explained');
  check(!t.errors.length,'no unhandled DOM errors: '+t.errors.join(';'));
  // Late directory data cannot replace a newer country choice.
  const lateDirectory=t.delayDirectory();change('directoryMarket','FR');await tick();
  const firstResolve=lateDirectory.resolve;change('directoryMarket','DE');await tick();
  lateDirectory.resolve(response(payload.stores.DE));await tick();
  firstResolve(response(payload.stores.FR));await tick();
  check($('directoryStore').value===payload.stores.DE.stores[0].id,'late directory response ignored');
  check(!t.errors.length,'directory callbacks have no DOM errors');
  t.dom.window.close();
  const budget=await create();
  for(let i=0;i<6;i++)budget.w.eval('regionRow('+JSON.stringify({id:'extra'+i,market:'US',location:String(10000+i),store_ids:[]})+')');
  check(budget.d.querySelectorAll('.region-entry').length===8,'eight-area fixture');
  budget.$('experimentalRegions').checked=true;budget.change('directoryMarket','FR');await tick();
  budget.$('addDirectoryStore').click();budget.input('storeLocation','75001');
  budget.$('watchModel').click();await tick();budget.$('applyModelFilters').click();
  check(budget.$('commitStore').disabled,'ninth-area commit prevented');
  check(budget.$('storeSetupStatus').textContent.includes('8-area / 24-request'),'budget restriction explained');
  budget.$('cancelStore').click();budget.change('modelMarket','US');
  const delayed=budget.delayModel();budget.$('watchModel').click();await tick();
  const many=model('US',budget.$('modelPicker').value);
  many.products=Array.from({length:37},(_,i)=>({...many.products[0],part:'US-EXAMPLE'+i+'/A'}));many.count=37;
  delayed.resolve(response(many));await tick();budget.$('applyModelFilters').click();
  check(budget.$('modelCount').textContent.includes('exceeds the safe limit'),'projected SKU request budget prevents oversized selection');
  check(budget.d.querySelectorAll('.product-entry').length===4,'rejected selection preserves existing variants');
  check(!budget.errors.length,'budget paths have no DOM errors');
  budget.dom.window.close();process.stdout.write(JSON.stringify({assertions,saved}));
})().catch(error=>{console.error(error.stack);process.exitCode=1});
