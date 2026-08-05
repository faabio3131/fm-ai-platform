# Playwright MCP testing setup

This repository includes the minimum configuration needed to run browser smoke tests against the local Streamlit application without changing application business rules.

## Files

- `package.json` and `package-lock.json`: development-only Node dependencies for `@playwright/test` and the official Microsoft `@playwright/mcp` package.
- `playwright.config.ts`: Playwright Test configuration for tests under `tests/e2e`, using `http://localhost:8501` as the base URL.
- `tests/e2e/app-smoke.spec.ts`: smoke test that opens the application, checks that a document title exists, and fails on fatal page JavaScript errors during load.
- `.vscode/mcp.json`: VS Code MCP server configuration that starts the locally installed Playwright MCP server with `npx playwright-mcp`.

## Local usage

Install dependencies and Playwright browsers before running the end-to-end tests:

```bash
npm install
npx playwright install
```

Start the application separately on port `8501`, then run:

```bash
npx playwright test
```
