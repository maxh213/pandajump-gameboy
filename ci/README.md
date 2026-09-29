# GitHub Actions workflows

These are ready-to-use workflows. Claude's GitHub App can't create files in
`.github/workflows/`, so they live here; copy them in to turn them on:

```sh
mkdir -p .github/workflows
cp ci/build.yml ci/pages.yml .github/workflows/
```

- `build.yml` builds the ROM, checks the committed `web/pandajump.gb` is
  current, runs the tests, and uploads the ROM as a build artifact.
- `pages.yml` publishes `web/` (the browser player and the ROM) to GitHub
  Pages on every push to `main`. Turn Pages on first: Settings > Pages >
  Source: GitHub Actions.
