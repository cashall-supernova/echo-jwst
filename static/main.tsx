import React,{lazy,Suspense,useEffect,useState} from 'react';
import {createRoot} from 'react-dom/client';
import TeamLogin from '../app/TeamLogin';
import {restoreSession} from './archive-client';
import '../app/globals.css';
const Images=lazy(()=>import('../app/page'));
const Spectra=lazy(()=>import('../app/spectra/page'));
function App(){
 const [ready,setReady]=useState(false),[busy,setBusy]=useState(true),[error,setError]=useState('');
 useEffect(()=>{const unlocked=()=>setReady(true);window.addEventListener('echo-unlocked',unlocked);restoreSession().then(setReady).catch(()=>setError('The archive could not be opened. Check your connection and reload.')).finally(()=>setBusy(false));return()=>window.removeEventListener('echo-unlocked',unlocked)},[]);
 if(error)return <main className="team-login"><div className="login-card"><h1>ECHO</h1><p role="alert">{error}</p><button className="btn" onClick={()=>window.location.reload()}>Reload</button></div></main>;
 if(busy)return <main className="team-login"><p role="status">Opening ECHO…</p></main>;
 if(!ready)return <TeamLogin/>;
 return <Suspense fallback={<main className="team-login"><p role="status">Loading the archive…</p></main>}>{/\/spectra\/?$/.test(location.pathname)?<Spectra/>:<Images/>}</Suspense>;
}
createRoot(document.getElementById('root')!).render(<App/>);
