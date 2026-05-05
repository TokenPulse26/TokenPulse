# TokenPulse Public Beta Release Checklist

Use this checklist before each public beta announcement.

## Release Identity
- [ ] `VERSION` file updated.
- [ ] `src-tauri/Cargo.toml` version matches `VERSION`.
- [ ] `CHANGELOG.md` top entry version/date matches release tag.
- [ ] Dashboard-reported version matches `VERSION`.

## Installer + Distribution
- [ ] Latest release asset (`tokenpulse-macos-arm64`) published.
- [ ] SHA256 asset published and validated by installer path.
- [ ] Install flow tested from clean macOS Apple Silicon machine.
- [ ] First-run security prompt flow documented and tested.

## Functional QA (minimum)
- [ ] Proxy health endpoint responds on `127.0.0.1:4100/health`.
- [ ] Dashboard loads on `127.0.0.1:4200`.
- [ ] OpenAI-compatible route logs tokens + model + provider.
- [ ] Anthropic route logs tokens + model + provider.
- [ ] Ollama route logs local-model traffic correctly.

## Analytics Integrity
- [ ] Time range filters validated (Today/7d/30d/All) on seeded data.
- [ ] Cost and token totals match raw request samples.
- [ ] CSV export includes all expected columns.
- [ ] Error monitoring panel shows expected failures.

## Support Readiness
- [ ] Known limitations section updated in README.
- [ ] First tester onboarding flow validated end-to-end.
- [ ] Issue template references version + route + provider info.
- [ ] Triage owner assigned for first 7 days after release.
