const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const html=fs.readFileSync(path.join(__dirname,'../docs/index.html'),'utf8');
const script=html.split('<script>')[1].split('</script>')[0];
const tick=()=>new Promise(resolve=>setImmediate(resolve));

function harness(fetcher){
  const values={mode:'source',project:'.',directory:'SEGGER_RTT',format:'github-zip',origin:'official',archive:'',sha256:'','custom-version':'','git-custom-version':''};
  const selects=new Set(['mode','format','origin','version','git-version']);
  const elements=new Map(),requests=[];
  class Element{
    constructor(id){this.id=id;this._value=values[id]||'';this.options=[];this.events={};this.disabled=false;this.hidden=false;this.textContent='';}
    get value(){return this._value;}
    set value(value){this._value=String(value);}
    replaceChildren(...options){this.options=options;this._value=options.length?options[0].value:'';}
    addEventListener(name,callback){this.events[name]=callback;}
    setAttribute(){}
  }
  const get=id=>{if(!elements.has(id))elements.set(id,new Element(id));return elements.get(id);};
  const context=vm.createContext({document:{getElementById:get,querySelector:()=>get('copy'),querySelectorAll:()=>[]},Option:function(text,value){this.text=text;this.value=value;},AbortController,setTimeout,clearTimeout,fetch:async url=>{requests.push(url);return fetcher(url,requests.length);}});
  vm.runInContext(script,context);
  const change=(id,value)=>{get(id).value=value;const event=selects.has(id)?'change':'input';get(id).events[event]();};
  return {get,change,requests,context};
}
const ok=data=>({ok:true,json:async()=>data});
const tags=()=>ok([{name:'V8.58'},{name:'V7.54'},{name:'V8.58.0'}]);

test('version is a native select placed after source, without datalist',()=>{
  assert.match(html,/<select id="version"/);
  assert(!html.includes('<datalist'));
  const group=html.slice(html.indexOf('id="source-fields"'),html.indexOf('id="git-version-fields"'));
  assert(group.indexOf('id="format"')<group.indexOf('id="origin"'));
  assert(group.indexOf('id="origin"')<group.indexOf('id="version"'));
});

test('loads actual tags, selects a pinned tag and updates PowerShell/Shell commands',async()=>{
  const h=harness(tags);
  assert(h.get('version').disabled);
  assert(h.get('copy').disabled);
  await tick();
  assert(!h.get('version').disabled);
  assert.equal(h.get('version').value,'V8.58.0');
  assert.equal(h.requests.length,1);
  h.change('version','V7.54');
  assert.match(h.get('generated').textContent,/-Version 'V7.54'/);
  h.get('sh').events.click();
  assert.match(h.get('generated').textContent,/--version 'V7.54'/);
});

test('pack only offers published releases with exactly one pack asset',async()=>{
  const releases=[{tag_name:'V8.58.0',assets:[{name:'RTT.pack'}]}, {tag_name:'V8.58',assets:[]}, {tag_name:'V9.0',prerelease:true,assets:[{name:'RTT.pack'}]}, {tag_name:'draft',draft:true,assets:[{name:'RTT.pack'}]}];
  const h=harness(url=>url.includes('/releases?')?ok(releases):tags());
  await tick();h.change('format','pack');await tick();
  const options=h.get('version').options.map(o=>o.value);
  assert.deepEqual(options,['V8.58.0','latest','custom']);
  assert.match(h.get('version-status').textContent,/Release/);
});

test('local and explicit URL keep version grey and omit version from generated command',async()=>{
  const h=harness(tags);await tick();
  h.change('origin','local');h.change('archive','C:\\downloads\\RTT.zip');
  assert(h.get('version').disabled);
  assert(h.get('custom-version').disabled);
  assert(!h.get('generated').textContent.includes('-Version'));
  assert(!h.get('copy').disabled);
  h.change('origin','url');h.change('archive','https://example.com/RTT.zip');
  assert(h.get('version').disabled);
  assert(!h.get('generated').textContent.includes('-Version'));
  h.change('origin','official');
  assert(!h.get('version').disabled);
  assert.equal(h.requests.length,1,'reuse cached tags');
});

test('switching inactive format does not request versions until official source is selected',async()=>{
  const h=harness(url=>url.includes('/releases?')?ok([{tag_name:'V8.58.0',assets:[{name:'RTT.pack'}]}]):tags());
  await tick();h.change('origin','local');h.change('format','pack');
  assert.equal(h.requests.length,1);
  assert(h.get('version').disabled);
  assert.equal(h.get('version').options[0].text,'不适用（由文件决定）');
  h.change('origin','official');await tick();
  assert.equal(h.requests.length,2);
  assert(!h.get('version').disabled);
});

test('failed request exposes retry and usable manual input',async()=>{
  let fail=true;
  const h=harness(()=>fail?{ok:false,status:403}:tags());
  await tick();
  assert.match(h.get('version-status').textContent,/加载失败/);
  assert(!h.get('version-retry').hidden);
  assert(!h.get('custom-version-field').hidden);
  h.change('custom-version','a'.repeat(40));
  assert(!h.get('copy').disabled);
  assert(h.get('generated').textContent.includes('a'.repeat(40)));
  fail=false;h.get('version-retry').events.click();await tick();
  assert(h.get('version-retry').hidden);
  assert.match(h.get('version-status').textContent,/加载 3 个/);
});

test('manual commit for submodule is independent of file source and hidden online picker',async()=>{
  const h=harness(tags);await tick();
  h.change('origin','local');h.change('mode','submodule');
  assert(h.get('source-fields').hidden);
  assert(!h.get('git-version-fields').hidden);
  assert(h.get('version').disabled);
  assert(!h.get('git-version').disabled);
  h.change('git-version','custom');h.change('git-custom-version','b'.repeat(40));
  assert.match(h.get('generated').textContent,/-Mode 'submodule'/);
  assert(!h.get('generated').textContent.includes('-Archive'));
  assert(h.get('generated').textContent.includes('b'.repeat(40)));
});

test('late tag response cannot replace pack release options',async()=>{
  let resolveTags;
  const h=harness(url=>url.includes('/tags?')?new Promise(resolve=>{resolveTags=resolve;}):ok([{tag_name:'pack-only',assets:[{name:'RTT.pack'}]}]));
  h.change('format','pack');await tick();
  assert.equal(h.get('version').value,'pack-only');
  resolveTags(tags());await tick();
  assert.equal(h.get('version').value,'pack-only');
  assert(!h.get('version').options.some(o=>o.value==='V7.54'));
});

test('GitHub tags pagination is respected',async()=>{
  const first=Array.from({length:100},(_,n)=>({name:'V1.'+n}));
  const h=harness(url=>ok(url.endsWith('page=1')?first:[{name:'V2.0'}]));await tick();
  assert.equal(h.requests.length,2);
  assert(h.get('version').options.some(o=>o.value==='V2.0'));
  assert.equal(h.get('version').value,'V2.0');
});

test('Middlewares remains blocked after version loading',async()=>{
  const h=harness(tags);await tick();h.change('directory','Middlewares');
  assert(h.get('copy').disabled);
  assert.match(h.get('validation').textContent,/Middlewares/);
});
