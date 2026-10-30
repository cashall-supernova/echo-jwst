'use client';
import {archiveSignOut} from '@/lib/archive-client';
import {ExternalLink,LogOut} from 'lucide-react';
export default function TeamLinks(){return <><a className="nav-item" href="https://cashall-supernova.github.io/hiss-spectra/" title="HISS spectra and light curves"><ExternalLink size={18}/> HISS</a><button className="nav-item" onClick={archiveSignOut}><LogOut size={18}/> Sign out</button></>}
