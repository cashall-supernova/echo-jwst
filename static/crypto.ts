export type Lock={version:1;iterations:number;salt:string;manifest:string};
export type Entry={file:string;type:string};
export type Manifest={version:1;updatedAt:string;resources:Record<string,Entry>};
const bytes=(value:string)=>Uint8Array.from(atob(value),c=>c.charCodeAt(0));
export async function deriveKey(username:string,password:string,lock:Lock){
 const material=await crypto.subtle.importKey('raw',new TextEncoder().encode(username.trim().toLowerCase()+'\n'+password),'PBKDF2',false,['deriveBits']);
 return new Uint8Array(await crypto.subtle.deriveBits({name:'PBKDF2',hash:'SHA-256',salt:bytes(lock.salt),iterations:lock.iterations},material,256));
}
export const importKey=(raw:Uint8Array)=>crypto.subtle.importKey('raw',raw as BufferSource,'AES-GCM',false,['decrypt']);
export async function decryptFile(raw:ArrayBuffer,key:CryptoKey,path:string){
 const bytes=new Uint8Array(raw);
 if(bytes.length<32||new TextDecoder().decode(bytes.slice(0,4))!=='ECHO')throw Error('Invalid encrypted archive file.');
 const compressed=await crypto.subtle.decrypt({name:'AES-GCM',iv:bytes.slice(4,16),additionalData:new TextEncoder().encode(path)},key,bytes.slice(16));
 const stream=new Blob([compressed]).stream().pipeThrough(new DecompressionStream('gzip'));
 return new Response(stream).arrayBuffer();
}
