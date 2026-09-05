import {build} from 'esbuild';
const test = process.argv.includes('--test');
await build({entryPoints:[test?'src/core.ts':'src/main.ts'],outfile:test?'.test-build/core.cjs':'main.js',bundle:true,platform:'browser',format:'cjs',target:'es2020',external:['obsidian'],sourcemap:false,logLevel:'info'});
