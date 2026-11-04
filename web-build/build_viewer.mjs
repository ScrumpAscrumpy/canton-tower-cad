import * as esbuild from 'esbuild';
import { createRequire } from 'module';
import { fileURLToPath } from 'url';

const require = createRequire(import.meta.url);
const threeWebGPU = require.resolve('three/webgpu');
const entry = process.argv[2] || '../web/app.js';
const outfile = process.argv[3] || '../web/bundle.js';

// Alias only the bare `three` specifier.  `three/addons/*` and `three/tsl`
// must keep their package subpaths, otherwise esbuild would remap them to
// three/webgpu/addons/... which does not exist.
const exactThree = {
  name: 'three-exact-alias',
  setup(build) {
    build.onResolve({ filter: /^three$/ }, () => ({ path: threeWebGPU }));
  },
};

await esbuild.build({
  entryPoints: [entry],
  outfile,
  bundle: true,
  minify: true,
  format: 'iife',
  target: 'es2020',
  plugins: [exactThree],
  logLevel: 'info',
});
