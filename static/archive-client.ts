import {decryptFile,deriveKey,importKey} from './crypto';
import type {Lock,Manifest} from './crypto';
const base=import.meta.env.BASE_URL;
const sessionName='echo-team-key:'+base;
let key:CryptoKey|null=null,manifest:Manifest|null=null,lock:Lock|null=null;
let activeManifest='';
let sessionUntil=0;
const objectUrls=new Set<string>();
const encode=(raw:Uint8Array)=>btoa(String.fromCharCode(...raw));
const decode=(raw:string)=>Uint8Array.from(atob(raw),c=>c.charCodeAt(0));
async function loadLock(){
 const r=await fetch(base+'lock.json',{cache:'no-store'});if(!r.ok)throw Error('The archive is temporarily unavailable. Please try again.');
 const value=await r.json() as Lock;
 if(value.version!==1||!Number.isInteger(value.iterations)||value.iterations<100000||value.iterations>2000000||!/^data\/[a-f0-9]{64}\.bin$/.test(value.manifest))throw Error('Invalid archive configuration.');
 lock=value;return value;
}
async function unlock(raw:Uint8Array,current:Lock){
 const candidate=await importKey(raw),r=await fetch(base+current.manifest,{cache:'no-cache'});if(!r.ok)throw Error('Archive files are unavailable. Please reload.');
 const data=JSON.parse(new TextDecoder().decode(await decryptFile(await r.arrayBuffer(),candidate,'manifest'))) as Manifest;
 if(data.version!==1||!data.resources?.['/api/catalog']||!data.resources?.['/api/spectra'])throw Error('Incomplete encrypted archive.');
 key=candidate;manifest=data;activeManifest=current.manifest;
}
export async function restoreSession(){
 const current=await loadLock();let saved:string|null=null;try{saved=sessionStorage.getItem(sessionName)}catch{}
 if(!saved)return false;
 try{const s=JSON.parse(saved);if(s.salt!==current.salt||Date.now()>s.until)throw Error();await unlock(decode(s.key),current);sessionUntil=s.until;return true}catch{try{sessionStorage.removeItem(sessionName)}catch{};return false}
}
export async function archiveSignIn(username:string,password:string){
 const current=lock||await loadLock();
 const raw=await deriveKey(username,password,current);
 try{await unlock(raw,current)}catch(error){if(error instanceof DOMException&&error.name==='OperationError')throw Error('Username or password not recognised.');throw error}
 sessionUntil=Date.now()+12*3600000;
 try{sessionStorage.setItem(sessionName,JSON.stringify({key:encode(raw),salt:current.salt,until:sessionUntil}))}catch{}
 window.dispatchEvent(new Event('echo-unlocked'));
}
export async function archiveSignOut(){
 key=null;manifest=null;try{sessionStorage.removeItem(sessionName)}catch{}
 for(const url of objectUrls)URL.revokeObjectURL(url);objectUrls.clear();window.location.reload();
}
export function sitePath(path:string){return base+(path==='/spectra'?'spectra/':path.replace(/^\//,''))}
function canonical(url:string){
 if(url.startsWith('/stamps/'))return '/api'+url;
 if(!/^\/api\/(catalog|cross-links|spectra(?:\/[a-f0-9]{24})?|stamps\/[a-f0-9]{24}\.(?:png|fits))$/.test(url))throw Error('Unknown archive resource.');
 return url;
}
export async function archiveFetch(url:string,init?:RequestInit){
 if(key&&Date.now()>=sessionUntil){await archiveSignOut();throw Error('Please sign in again.');}
 if(!key||!manifest)throw Error('Please sign in to open archive data.');
 if(url==='/api/catalog'||url==='/api/spectra'){
  const current=await loadLock();
  if(current.manifest!==activeManifest){
   const r=await fetch(base+current.manifest,{cache:'no-cache',signal:init?.signal});if(!r.ok)throw Error('Archive update unavailable.');
   const next=JSON.parse(new TextDecoder().decode(await decryptFile(await r.arrayBuffer(),key,'manifest'))) as Manifest;
   if(next.version!==1||!next.resources?.['/api/catalog']||!next.resources?.['/api/spectra'])throw Error('Incomplete archive update.');
   manifest=next;activeManifest=current.manifest;
  }
 }
 const path=canonical(url),entry=manifest.resources[path];
 if(!entry)return new Response('Archive file unavailable',{status:404});
 if(!/^data\/[a-f0-9]{64}\.bin$/.test(entry.file))throw Error('Invalid archive file path.');
 const r=await fetch(base+entry.file,{signal:init?.signal,cache:'force-cache'});if(!r.ok)return r;
 return new Response(await decryptFile(await r.arrayBuffer(),key,path),{headers:{'Content-Type':entry.type}});
}
export async function archiveAssetUrl(url:string,signal?:AbortSignal){
 const r=await archiveFetch(url,{signal});if(!r.ok)throw Error('Image could not be loaded.');
 const result=URL.createObjectURL(await r.blob());objectUrls.add(result);return result;
}
export function releaseAssetUrl(url:string){if(objectUrls.delete(url))URL.revokeObjectURL(url)}
