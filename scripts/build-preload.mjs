import { build } from 'esbuild'

await build({
  entryPoints: ['src/preload/index.ts'],
  outfile: 'out/preload/index.js',
  bundle: true,
  platform: 'node',
  format: 'cjs',
  target: 'node20',
  external: ['electron'],
  sourcemap: true,
})
