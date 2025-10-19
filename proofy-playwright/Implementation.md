# Proofy Playwright Reporter Implementation

## References
- [Current Proofy Python project](../README.md)

## Requirements
- Provide a Playwright test reporter that forwards results to Proofy using the same data model semantics as the existing pytest plugin.
- Support JavaScript and TypeScript consumers with full type definitions and dual ESM/CJS bundles.
- Share logic through a `proofy-commons-js` package covering configuration resolution, result models, serialization, and Proofy API interactions.
- Execute every Proofy API call via async functions without background worker threads or queues; rely on concurrent `Promise` handling for parallel uploads.
- Offer run modes mirroring live, lazy, and batch behaviors using async-only flows (e.g., `Promise.allSettled` for batching) and optional local JSON backups.
- Capture Playwright-specific metadata: annotations, parameters, retries, attachments (screenshots, traces, videos), stdout/stderr, and test duration data.
- Provide configuration via Playwright config files, environment variables, and optional CLI flags, keeping parity with Python options where practical.
- Include developer ergonomics: helper APIs for tagging/tests, rich logging, and clear error handling when Proofy configuration is incomplete.
- Deliver a documented release process (semantic versioning, npm publishing) and CI coverage for linting, testing, and building.

## Implementation Steps
1. **Repository Scaffold**
   - Initialize Node workspace (npm/pnpm) with separate packages for commons and Playwright reporter.
   - Configure TypeScript project references, ESLint, Prettier, Vitest (or equivalent), and build tooling (tsup/tsc) to emit ESM and CJS outputs plus `.d.ts` files.
2. **Commons Package (`proofy-commons-js`)**
   - Port `ProofyConfig` model and option resolution logic, supporting env/CLI/Playwright config sources.
   - Implement async HTTP client with retry/backoff, timeout, and diagnostics; ensure every public method returns a promise.
   - Recreate result/run models, clamps, metadata merging, and local backup writer using async `fs` APIs.
   - Provide helpers for run attribute management and artifact metadata generation.
3. **Playwright Reporter Package**
   - Implement `ProofyPlaywrightReporter` adhering to Playwright's reporter interface, wiring hooks (`onBegin`, `onTestBegin`, `onTestEnd`, `onEnd`, etc.) to commons async APIs.
   - Track in-flight promises for test/result uploads; flush them with `await Promise.allSettled(...)` at suite end.
   - Map Playwright entities to Proofy models (ids, titles, locations, retries, attachments, stdout/stderr) and enforce limits.
   - Expose configuration helpers, decorators, and documented runtime APIs for tagging and run attributes.
4. **Testing & Tooling**
   - Write unit tests with mocked HTTP client verifying config parsing, async flows, batching, and error handling.
   - Add integration tests using Playwright in CI to validate real reporter behavior against a mock Proofy server.
   - Set up GitHub Actions (or equivalent) for lint/test/build workflows and release automation (semantic-release or Changesets).
5. **Documentation & Examples**
   - Author README files for repository and each package, covering setup, configuration, and troubleshooting in both TS and JS.
   - Provide sample Playwright project demonstrating reporter usage, including artifact uploads and batch mode.
   - Generate API docs (typedoc) and maintain CHANGELOG for releases.
6. **Release Preparation**
   - Define versioning policy, publishing checklists, and contribution guidelines.
   - Verify npm package metadata, include license files, and ensure repository links and Proofy references are accurate.

## Next Steps
- Confirm tooling preferences (npm vs pnpm, build/test stack) and initialize the Node workspace accordingly.
- Establish mock Proofy service endpoints for local testing before implementing reporter logic.
