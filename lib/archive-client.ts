// The GitHub Pages build replaces this module with its encrypted-file adapter.
export const archiveFetch=(url:string,init?:RequestInit)=>fetch(url,init);
export const archiveAssetUrl=async(url:string,_signal?:AbortSignal)=>url;
export const releaseAssetUrl=(_url:string)=>{};
export const sitePath=(path:string)=>path;
export async function archiveSignOut(){const r=await fetch('/api/access/logout',{method:'POST'});if(r.ok)window.location.reload()}
export async function archiveSignIn(username:string,password:string){
 const response=await fetch('/api/access/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username,password})});
 const result=await response.json() as {error?:string};
 if(!response.ok)throw Error(result.error||'Could not sign in.');
 window.location.reload();
}
