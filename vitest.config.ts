// Suppress the per-run `results.json` cache under node_modules/.vite/vitest/.
// We run the integration matrix one-shot via `vitest run`, so the cache
// (used by watch mode + "rerun failed" UI) adds no value and clutters the
// workspace with files named by an empty-string SHA1.
//
// Plain object instead of `defineConfig` from `vitest/config`: vitest is
// run via `npx` so it isn't a local dep, and importing `vitest/config`
// here would fail to resolve.
export default {
  test: {
    cache: false,
  },
};
