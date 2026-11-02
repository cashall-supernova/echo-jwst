import {defineConfig} from 'vite';
import react from '@vitejs/plugin-react';
import {resolve} from 'node:path';
import {homedir,platform} from 'node:os';
const publicationRoot=process.env.ECHO_GITHUB_WORK_DIR||(platform()==='darwin'
 ?resolve(homedir(),'Library/Caches/edu.hawaii.echo')
 :resolve(process.env.XDG_CACHE_HOME||resolve(homedir(),'.cache'),'echo'));
export default defineConfig({
 root:resolve('static'),base:process.env.ECHO_PAGES_BASE||'/echo-jwst/',publicDir:false,
 plugins:[react()],
 resolve:{alias:[{find:'@/lib/archive-client',replacement:resolve('static/archive-client.ts')},{find:'@',replacement:resolve('.')}]},
 build:{outDir:resolve(publicationRoot,'github-site'),emptyOutDir:true,sourcemap:false,rolldownOptions:{input:{main:resolve('static/index.html'),spectra:resolve('static/spectra/index.html')}}},
});
