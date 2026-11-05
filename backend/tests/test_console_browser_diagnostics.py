"""Test-only browser metadata trace must never record frames/credentials/terminal."""

from pathlib import Path
import subprocess


def test_lifecycle_trace_is_bounded_and_metadata_only():
    source = Path(__file__).parents[2] / "tests/console_mock/browser_lifecycle.js"
    script = """
const fs=require('fs'),vm=require('vm'),assert=require('assert');
global.window={WebSocket:class extends EventTarget{}};
global.document={addEventListener:()=>{}};
vm.runInThisContext(fs.readFileSync(process.argv[1],'utf8'));
const ws=new window.WebSocket();
for(let i=0;i<600;i++){
 ws.dispatchEvent(new MessageEvent('message',{data:JSON.stringify({type:'participants',unique_user_count:2,users:[{display_name:'PRIVATE_CANARY'}],password:'PRIVATE_CANARY',ticket:'PRIVATE_CANARY',data:'PRIVATE_CANARY'})}));
 ws.dispatchEvent(new MessageEvent('message',{data:new Uint8Array([65,66,67])}));
 ws.dispatchEvent(new MessageEvent('message',{data:JSON.stringify({type:'auth_required',username:'PRIVATE_CANARY'})}));
}
const trace=window.__r1Trace;
assert.equal(trace.length,512);
assert(!JSON.stringify(trace).includes('PRIVATE_CANARY'));
const allowed=new Set(['ms','socket','event','code','generation','state','count']);
for(const item of trace)assert(Object.keys(item).every(k=>allowed.has(k)));
assert.equal(trace.at(-1).count,2);
"""
    subprocess.run(["node", "-e", script, str(source)], check=True, capture_output=True, text=True)
