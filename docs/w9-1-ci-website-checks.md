# W9.1 — Website checks in CI (MANUAL FOLLOW-UP, NOT APPLIED)

## Status

NOT APPLIED. This change is documented here only. It was
deliberately NOT pushed with this PR: pushing
`.github/workflows/*` through the GitHub App API fails
with `403 Resource not accessible by integration`
(proven repeatedly on this repository). Apply it by
hand after this PR merges — see "How to apply" below —
and never claim CI runs the website checks until a real
CI run shows the new job.

## Why

`.github/workflows/ci.yml` currently runs only two
jobs: `backend` (pytest, Ruff, Mypy, pip-audit) and
`docker` (image build + health smoke test). The website
has never had CI coverage: its unit tests, TypeScript
check, lint, production build, and Playwright specs run
only locally. W9.1 adds frontend behaviour (the
reservation-key lifecycle) that deserves the same gate
as the backend, so this document proposes the exact
`website` job to add.

## Exact change

Append the following job to `.github/workflows/ci.yml`,
after the `docker` job. Nothing else in the file
changes: the triggers (pull requests targeting main,
pushes to main) already cover this job.

```yaml
  website:
    name: Website (tests, typecheck, lint, build, e2e)
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: apps/web
    steps:
      - name: Check out
        uses: actions/checkout@v4

      - name: Set up Node 24
        uses: actions/setup-node@v4
        with:
          node-version: "24"
          cache: npm
          cache-dependency-path: package-lock.json

      # Workspaces hoist modules to the repo root, so
      # install from the root, then run the workspace
      # scripts from apps/web.
      - name: Install dependencies
        run: npm ci
        working-directory: .

      - name: Run frontend unit tests
        run: npm run test --workspace=apps/web
        working-directory: .

      - name: Run api-client tests
        run: npm run test --workspace=packages/api-client
        working-directory: .

      - name: Run TypeScript check
        run: npm run typecheck --workspace=apps/web
        working-directory: .

      - name: Run ESLint
        run: npm run lint --workspace=apps/web
        working-directory: .

      # The production build bakes NEXT_PUBLIC_* values
      # in. These are placeholder test values, never
      # real credentials; the build must succeed with
      # them (W8 fail-loud SITE_URL is satisfied).
      - name: Run production build
        run: npm run build --workspace=apps/web
        working-directory: .
        env:
          NEXT_PUBLIC_SUPABASE_URL: https://example.supabase.co
          NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY: ci-publishable-key
          NEXT_PUBLIC_API_BASE_URL: http://localhost:8000
          NEXT_PUBLIC_SITE_URL: http://localhost:3000

      # Playwright browsers are NOT installed by npm
      # (see apps/web/playwright.config.ts). The specs
      # run against the e2e stub API plus the Next dev
      # server, both started by the config's webServer
      # entries; no real backend is required. Two
      # workers: the full suite shares one stub server,
      # and this is the worker count the suite was
      # verified with locally in W9.1.
      - name: Install Playwright chromium
        run: npx playwright install chromium

      - name: Run Playwright specs
        run: npx playwright test --workers=2
```

## How to apply

Option A (web UI): open `.github/workflows/ci.yml`
on GitHub, paste the job above after the `docker`
job, commit directly to main with a message like
`CI: add website checks (W9.1 follow-up)`.

Option B (local git): pull main, apply the same edit,
push from a local checkout (local git push is NOT
subject to the API 403).

Then verify: the next pull request targeting main
must show a `website` job in its checks. Until that
run exists, report CI website coverage as "documented,
not yet live".

## Out of scope for this change

No trigger changes, no backend/docker job changes, no
secrets, no deployment step. The Playwright step is
mocked end-to-end (stub API + mocked Razorpay); it is
never presented as live payment verification. If the
e2e step proves flaky in CI, split it into its own
job rather than deleting website coverage.
