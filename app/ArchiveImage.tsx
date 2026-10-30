'use client';
import {useEffect,useRef,useState} from 'react';
import type {ImgHTMLAttributes} from 'react';
import {archiveAssetUrl,releaseAssetUrl} from '@/lib/archive-client';
export default function ArchiveImage({src,...props}:Omit<ImgHTMLAttributes<HTMLImageElement>,'src'>&{src?:string}){
 const ref=useRef<HTMLImageElement>(null),[url,setUrl]=useState<string>(),[failed,setFailed]=useState(false);
 useEffect(()=>{
  setUrl(undefined);setFailed(false);if(!src)return;
  const controller=new AbortController();let resolved='',started=false;
  const load=()=>{if(started)return;started=true;archiveAssetUrl(src,controller.signal).then(value=>{if(controller.signal.aborted){releaseAssetUrl(value);return}resolved=value;setUrl(value)}).catch(()=>{if(!controller.signal.aborted)setFailed(true)})};
  const observer=new IntersectionObserver(entries=>{if(entries.some(e=>e.isIntersecting)){load();observer.disconnect()}},{rootMargin:'300px'});
  if(ref.current)observer.observe(ref.current);else load();
  return()=>{controller.abort();observer.disconnect();if(resolved)releaseAssetUrl(resolved)};
 },[src]);
 return <img {...props} ref={ref} src={url} data-load-error={failed||undefined}/>;
}
