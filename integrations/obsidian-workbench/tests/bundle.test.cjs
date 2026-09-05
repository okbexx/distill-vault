const {test}=require('node:test');
const assert=require('node:assert/strict');
const Module=require('node:module');

// A host-contract smoke test of the real bundled entry point, NOT a GUI test.
test('built plugin registers only capture/workbench and whitelists saved settings', async()=>{
  const commands=[]; const views=[]; const ribbons=[];
  class Plugin {
    async loadData(){return {inbox:'收件箱',agentUrl:'https://example.com/obsolete',password:'dummy-not-a-credential'};}
    registerView(id,factory){views.push({id,factory});}
    addCommand(c){commands.push(c);}
    addRibbonIcon(icon,label,callback){ribbons.push({icon,label,callback});}
    addSettingTab(){}
  }
  const host={Plugin,ItemView:class{},Modal:class{},Notice:class{},PluginSettingTab:class{},Setting:class{},TFolder:class{}};
  const load=Module._load;
  let Workbench;
  try {
    Module._load=function(id,...args){return id==='obsidian'?host:load.call(this,id,...args);};
    Workbench=require('../main.js').default;
  } finally {Module._load=load;}
  const plugin=new Workbench();
  await plugin.onload();
  assert.deepEqual(plugin.settings,{inbox:'收件箱'});
  assert.deepEqual(commands.map(c=>c.id).sort(),['open-workbench','quick-capture']);
  assert.equal(views[0].id,'distill-workbench');
  assert.ok(ribbons.every(r=>typeof r.callback==='function'));
});
