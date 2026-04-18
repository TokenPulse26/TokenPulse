# TokenPulse Launch Posts — Draft Copy

## Vibecoding Community Post

**Title:** Built a local proxy that tracks all your AI token usage in one dashboard — looking for feedback

I've been running a mix of Claude, GPT, Ollama, and OpenRouter through my OpenClaw setup and got tired of having no idea what I was actually spending across all of them. So I built TokenPulse.

**What it is:** A local Rust proxy + web dashboard that sits between your AI tools and providers. It intercepts requests, extracts token counts and costs, and gives you one dashboard for everything — cloud APIs and local models.

**How it works:**
- Point your tools at `localhost:4100` instead of the provider directly
- TokenPulse forwards everything transparently (your API keys pass through, never stored)
- Open `127.0.0.1:4200` for the dashboard
- All data stays in local SQLite — nothing leaves your machine

**What I'm tracking right now:** 30K+ requests across 7 providers (OpenAI, Anthropic, Ollama, OpenRouter, etc.), 11 models, with real cost breakdowns.

**The cool part for agent setups:** If you're running agents that make a lot of API calls, you can finally see exactly what they're doing. Budget alerts, cost projections, and a context audit that catches wasted tokens.

It's free, early access, and I'd genuinely love feedback from people who are actually running AI agent workflows. Your agent can set it up for you — there's an agent-specific setup guide in the repo.

**Repo:** https://github.com/TokenPulse26/TokenPulse
**Site:** https://tokenpulse.to
**Agent setup guide:** https://github.com/TokenPulse26/TokenPulse/blob/main/AGENT_SETUP.md

Runs on macOS (Apple Silicon verified). Linux should work but hasn't been heavily tested yet. Looking for people to try it and tell me what breaks.

---

## Reddit Post (r/LocalLLaMA version)

**Title:** I built a local proxy that tracks token usage across cloud AND local models in one dashboard — free, early access

I was running Claude, GPT-4, and Ollama side by side and had no unified view of what was happening across all of them. Built TokenPulse to fix that.

It's a Rust proxy on localhost:4100 that intercepts AI API requests and logs usage to local SQLite. Web dashboard on localhost:4200 shows spend, token counts, model breakdowns, budget alerts, and activity trends.

**Why this matters for local model users:** You can see your Ollama/local model usage alongside your cloud API usage in one place. Zero cost for local requests, obviously, but you get request counts, latency, and model breakdowns.

Supports: OpenAI, Anthropic, Google, Mistral, Groq, OpenRouter, Ollama, LM Studio

Everything stays local. No cloud account, no telemetry.

Free during early access. Repo: https://github.com/TokenPulse26/TokenPulse

Looking for feedback — especially from people running hybrid setups.

---

## Reddit Post (r/SelfHosted version)

**Title:** TokenPulse — self-hosted AI usage tracking proxy + dashboard (Rust + Python, local SQLite)

Built a local-first proxy that tracks all my AI API usage in one dashboard. Runs as two processes: a Rust proxy on port 4100 and a Python web dashboard on port 4200. Data stored in local SQLite.

- Intercepts and forwards AI API requests transparently
- Tracks tokens, costs, models, providers, latency
- Dashboard with budget alerts, cost projections, CSV export
- Supports OpenAI, Anthropic, Google, Ollama, OpenRouter, and more
- Zero external dependencies for the dashboard (Python stdlib only)
- Designed for headless servers — runs great as a systemd service

No cloud account, no telemetry, no data leaves your machine. API keys pass through in headers and are never stored.

Free, early access. Repo: https://github.com/TokenPulse26/TokenPulse

---

## Reddit Post (r/OpenAI version)

**Title:** Built a local proxy to track exactly how much I'm spending on AI APIs — open source, free

Got tired of checking three different provider dashboards to figure out my monthly AI spend. Built TokenPulse — a local Rust proxy that sits between your tools and the API, logs every request, and shows everything in one web dashboard.

Tracks: token counts, costs per request, model usage, provider breakdowns, budget alerts, spending forecasts.

Works with: OpenAI, Anthropic, Google, Mistral, Groq, OpenRouter, Ollama, LM Studio.

Everything stays on your machine in SQLite. No account required.

https://github.com/TokenPulse26/TokenPulse

Early access — looking for feedback.

---

## X/Twitter Post

Short version:
> Built TokenPulse — a local proxy that tracks all your AI token usage in one dashboard.
>
> Cloud APIs + local models. One view. All local, all private.
>
> Free during early access.
> https://tokenpulse.to

Thread version:
> 1/ I was running Claude, GPT, and Ollama through my AI agent setup and had zero visibility into what was happening across all of them. So I built @TokenPulse.
>
> 2/ It's a local Rust proxy that sits between your tools and AI providers. Every request gets logged — tokens, costs, models, latency — into local SQLite. Then a web dashboard shows you everything.
>
> 3/ The thing I'm most proud of: your AI agent can install it for you. There's an agent-optimized setup guide that any AI (Claude, GPT, Codex, local models) can follow to get it running.
>
> 4/ Tracking 30K+ requests across 7 providers right now. Free during early access. Looking for people running hybrid cloud + local AI setups to try it.
>
> https://tokenpulse.to
> https://github.com/TokenPulse26/TokenPulse

---

## Key talking points across all channels

- "I built this to solve my own problem" (authentic, not salesy)
- 30K+ real requests tracked (proof it works, not vaporware)
- Local-first, privacy-focused (resonates with self-hosted crowd)
- Your agent can install it for you (unique selling point)
- Free during early access (no friction)
- Looking for feedback (invites engagement, not just clicks)
- Honest about what's early: macOS verified, Linux should work, agent setup guide exists
