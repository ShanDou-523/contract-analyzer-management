import { build } from 'esbuild'

await build({
  entryPoints: ['src/main/index.ts'],
  outfile: 'out/main/index.js',
  bundle: true,
  platform: 'node',
  format: 'cjs',
  target: 'node20',
  external: ['electron'],
  sourcemap: true,
})
