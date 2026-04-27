# Deploy the chat proxy (one-time, 5 minutes)

The dashboard is a static site on GitHub Pages, so it can't securely call the
Anthropic API directly (would expose the key). The chat feature uses a tiny
Cloudflare Worker that holds the key server-side and proxies requests.

Cloudflare Workers free tier covers 100,000 requests/day. You will not exceed it.

## What you need
- A Cloudflare account (free, no credit card)
- The same `sk-ant-...` API key already used by the daily refresh

## Steps (Cloudflare dashboard, no CLI)

1. **Sign up / log in** at https://dash.cloudflare.com
2. Left sidebar -> **Compute (Workers)** -> **Workers & Pages** -> **Create**
3. **Create Worker** -> Name it `nee-coaching-chat` -> **Deploy** (the default
   "Hello World" worker is fine for now)
4. After deploy, click **Edit code**
5. **Replace the entire file contents** with the contents of
   `worker/coaching-chat-worker.js` from this repo
6. Click **Deploy** (top right)
7. Click **Settings** -> **Variables and Secrets**
8. Add a **Secret** named exactly `ANTHROPIC_API_KEY`, value = your `sk-ant-...` key
9. (Optional) Add a Variable `ALLOWED_ORIGIN` set to `https://thomashaslam.github.io`
   to lock CORS to just the dashboard domain
10. **Copy the Worker URL** (top of the worker page, looks like
    `https://nee-coaching-chat.<your-account>.workers.dev`)

## Tell the dashboard where to find it

Two paths:

**A. (Easiest) Tell me the Worker URL** and I'll bake it into the page.

**B. (DIY)** Edit `index.html`, find `const CHAT_WORKER_URL = ""`, paste
the URL between the quotes, commit, push.

That's it. Refresh the dashboard, click the chat button on any TM card.
