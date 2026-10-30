'use client';
import {useState} from 'react';
import type {ReactNode} from 'react';
import {archiveAssetUrl,releaseAssetUrl} from '@/lib/archive-client';
export default function ArchiveDownload({src,children}:{src:string;children:ReactNode}){
 const [busy,setBusy]=useState(false),[error,setError]=useState('');
 return <><button className="btn" disabled={busy} onClick={async()=>{setBusy(true);setError('');try{const url=await archiveAssetUrl(src);const a=document.createElement('a');a.href=url;a.download=src.split('/').pop()||'cutout.fits';a.click();setTimeout(()=>releaseAssetUrl(url),60000)}catch{setError('Download unavailable. Please try again.')}finally{setBusy(false)}}}>{busy?'Preparing download…':children}</button>{error&&<span role="alert">{error}</span>}</>;
}
