// Shared cryptographic primitives; no credentials are bundled with client code.
export const SESSION_COOKIE='__Host-echo-session';
export const SESSION_SECONDS=12*60*60;
export type LoginVerifier={salt:string;hash:string};
const bytes=(text:string)=>new TextEncoder().encode(text);
const hex=(buffer:ArrayBuffer)=>Array.from(new Uint8Array(buffer),b=>b.toString(16).padStart(2,'0')).join('');
const unhex=(text:string)=>Uint8Array.from(text.match(/../g)||[],n=>parseInt(n,16));
export function equalSecret(a:string,b:string){
 if(!a||!b||a.length!==b.length)return false;
 let difference=0;for(let i=0;i<a.length;i++)difference|=a.charCodeAt(i)^b.charCodeAt(i);
 return difference===0;
}
export function parseVerifier(value?:string):LoginVerifier|null{
 try{const v=JSON.parse(value||'');return /^[a-f0-9]{32,64}$/.test(v.salt)&&/^[a-f0-9]{64}$/.test(v.hash)?v:null}catch{return null}
}
export async function verifyLogin(username:string,password:string,verifier:LoginVerifier){
 const key=await crypto.subtle.importKey('raw',bytes(username.trim().toLowerCase()+'\n'+password),'PBKDF2',false,['deriveBits']);
 const hash=await crypto.subtle.deriveBits({name:'PBKDF2',salt:unhex(verifier.salt),iterations:100000,hash:'SHA-256'},key,256);
 return equalSecret(hex(hash),verifier.hash);
}
async function sessionKey(secret:string,verifier:LoginVerifier){
 return crypto.subtle.importKey('raw',bytes(secret+'\n'+verifier.hash),{name:'HMAC',hash:'SHA-256'},false,['sign','verify']);
}
export async function makeSession(secret:string,verifier:LoginVerifier,now=Date.now()){
 const payload=`v1.${Math.floor(now/1000)+SESSION_SECONDS}.${crypto.randomUUID()}`;
 const signature=await crypto.subtle.sign('HMAC',await sessionKey(secret,verifier),bytes(payload));
 return payload+'.'+hex(signature);
}
export async function validSession(cookie:string,secret:string,verifier:LoginVerifier,now=Date.now()){
 const match=/^v1\.(\d{10})\.([a-f0-9-]{36})\.([a-f0-9]{64})$/.exec(cookie);
 if(!match||Number(match[1])<=now/1000||Number(match[1])>now/1000+SESSION_SECONDS+60)return false;
 const payload=cookie.slice(0,cookie.lastIndexOf('.'));
 return crypto.subtle.verify('HMAC',await sessionKey(secret,verifier),unhex(match[3]),bytes(payload));
}
export function sessionFromHeaders(headers:Headers){
 return headers.get('cookie')?.split(';').map(s=>s.trim()).find(s=>s.startsWith(SESSION_COOKIE+'='))?.slice(SESSION_COOKIE.length+1)||'';
}
