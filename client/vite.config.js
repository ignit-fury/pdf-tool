import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import {cpSync,createReadStream,existsSync} from 'node:fs';
import {resolve} from 'node:path';

// pdf.js fetches named CMaps, standard fonts and decoder WASM at runtime.
// Keep those requests on this origin in both development and the production bundle.
function pdfAssets(){
  const source=resolve('node_modules/pdfjs-dist');
  return {
    name:'local-pdfjs-assets',
    configureServer(server){
      server.middlewares.use('/assets/pdfjs/',(req,res,next)=>{
        const parts=(req.url||'').split('?')[0].split('/').filter(Boolean);
        if(parts.length!==2||!['cmaps','standard_fonts','wasm'].includes(parts[0])||!/^[-\w.]+$/.test(parts[1]))return next();
        const path=resolve(source,parts[0],parts[1]);
        if(!existsSync(path))return next();
        res.setHeader('Content-Type',path.endsWith('.wasm')?'application/wasm':'application/octet-stream');
        createReadStream(path).pipe(res);
      });
    },
    closeBundle(){for(const directory of ['cmaps','standard_fonts','wasm'])cpSync(resolve(source,directory),resolve('dist/assets/pdfjs',directory),{recursive:true});},
  };
}

export default defineConfig({
  plugins: [react(),pdfAssets()],
  server: {
    port: 5173,
    host: '127.0.0.1',
    proxy: {
      '/upload': 'http://127.0.0.1:8000',
      '/jobs': 'http://127.0.0.1:8000',
      '/fonts': 'http://127.0.0.1:8000',
      '/health': 'http://127.0.0.1:8000',
      '/ocr-notify': 'http://127.0.0.1:8000',
    },
  },
  build: {
    outDir: 'dist',
  },
});
