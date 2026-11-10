const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const html=fs.readFileSync(path.join(__dirname,'../docs/index.html'),'utf8'),script=html.split('<script>')[1].split('</script>')[0];
function harness(){
 const values={mode:'source',project:'.',directory:'SEGGER_RTT',version:'release',format:'github-zip',origin:'official',archive:'',sha256:'',target:'','custom-version':''},elements=new Map();
 const get=id=>{if(!elements.has(id))elements.set(id,{value:values[id]||'',events:{},hidden:false,disabled:false,textContent:'',addEventListener(name,fn){this.events[name]=fn;},setAttribute(){}});return elements.get(id);};
 vm.runInNewContext(script,{document:{getElementById:get,querySelector:()=>get('copy'),querySelectorAll:()=>[]},fetch(){throw Error('Page must not query GitHub');}});
 const change=(id,value)=>{get(id).value=value;get(id).events[['mode','version','format','origin'].includes(id)?'change':'input']();};
 return {get,change};
}
test('primary form only asks project, install mode and version; advanced starts closed',()=>{
 const main=html.slice(html.indexOf('<div class="builder">'),html.indexOf('<details id="advanced">'));
 assert(main.includes('id="project"'));assert(main.includes('id="mode"'));assert(main.includes('id="version"'));
 for(const id of ['format','origin','archive','sha256','directory','target'])assert(!main.includes('id="'+id+'"'));
 assert(!html.includes('<details id="advanced" open'));
});
test('default is a formal release copy and generates minimal command without API request',()=>{
 const h=harness();assert(!h.get('copy').disabled);
 assert.match(h.get('generated').textContent,/-Mode 'source' -Version 'release'/);
 assert(!h.get('generated').textContent.includes('-Format'));assert(!h.get('generated').textContent.includes('-Directory'));
});
test('main snapshot and a custom ref produce explicit distinct version arguments',()=>{
 const h=harness();h.change('version','main');assert.match(h.get('generated').textContent,/-Version 'main'/);assert.match(h.get('version-note').textContent,/尚未发布/);
 h.change('version','custom');assert(h.get('copy').disabled);h.change('custom-version','refs/heads/main');assert(!h.get('copy').disabled);assert.match(h.get('generated').textContent,/-Version 'refs\/heads\/main'/);
});
test('local and URL archives disable semantic version and never pass its stale value',()=>{
 const h=harness();h.change('origin','local');h.change('archive','C:\\downloads\\RTT.pack');assert(h.get('version').disabled);assert(!h.get('generated').textContent.includes('-Version'));assert(!h.get('generated').textContent.includes('-Format'));
 h.change('origin','url');h.change('archive','https://example.com/RTT.pack');h.change('format','pack');assert(h.get('version').disabled);assert.match(h.get('generated').textContent,/-Format 'pack'/);
 h.change('origin','official');assert(!h.get('version').disabled);
});
test('submodule ignores preserved offline source settings and uses requested main ref',()=>{
 const h=harness();h.change('origin','local');h.change('mode','submodule');h.change('version','main');assert(!h.get('version').disabled);assert(h.get('origin').disabled);assert.match(h.get('generated').textContent,/-Mode 'submodule' -Version 'main'/);assert(!h.get('generated').textContent.includes('-Archive'));
});
test('advanced pack is retained but rejects main snapshot',()=>{
 const h=harness();h.change('origin','pack');assert.match(h.get('generated').textContent,/-Format 'pack'/);h.change('version','main');assert(h.get('copy').disabled);assert.match(h.get('validation').textContent,/main 是源码快照/);
});
test('custom path, target, hash and POSIX quoting remain available',()=>{
 const h=harness();h.change('project',"/work/board's project");h.change('directory','DebugRTT');h.change('target','firmware');h.change('sha256','a'.repeat(64));h.get('sh').events.click();assert.match(h.get('generated').textContent,/--directory 'DebugRTT'/);assert.match(h.get('generated').textContent,/--target 'firmware'/);assert(h.get('generated').textContent.includes("'\"'\"'"));assert(!h.get('copy').disabled);
});
test('Middlewares protection remains enforced in advanced settings',()=>{
 const h=harness();h.change('directory','Middlewares');assert(h.get('copy').disabled);assert.match(h.get('validation').textContent,/Middlewares/);
});
