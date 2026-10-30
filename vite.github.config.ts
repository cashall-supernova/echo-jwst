import {defineConfig} from 'vite';
import react from '@vitejs/plugin-react';
import {resolve} from 'node:path';
export default defineConfig({
 root:resolve('static'),base:process.env.ECHO_PAGES_BASE||'/echo-jwst/',publicDir:false,
 plugins:[react()],
 resolve:{alias:[{find:'@/lib/archive-client',replacement:resolve('static/archive-client.ts')},{find:'@',replacement:resolve('.')}]},
 build:{outDir:resolve('local/github-site'),emptyOutDir:true,sourcemap:false,rolldownOptions:{input:{main:resolve('static/index.html'),spectra:resolve('static/spectra/index.html')}}},
});
