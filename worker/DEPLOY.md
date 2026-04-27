# Activate Coach Rick chat (5-10 min, free, one-time)

The dashboard is currently served from GitHub Pages, which is static. To make
real-time chat work, we move the same site to **Cloudflare Pages** (also free,
also auto-deploys from GitHub) which lets us run a tiny server-side function
that holds the Anthropic API key.

The function code is already written at `functions/api/chat.js`. You just have
to point Cloudflare Pages at this repo.

## What you'll do

1. Sign up for Cloudflare (free, no credit card)
2. Connect to GitHub
3. Pick this repo
4. Set the Anthropic API key as an environment variable
5. Deploy

That's it. Every git push from here on auto-deploys both the static site AND
the chat function.

## Step by step

### 1. Sign up for Cloudflare

Open https://dash.cloudflare.com/sign-up. Use any email. No payment info needed
for what we're doing.

### 2. Open Workers & Pages

After login, in the left sidebar click **Compute (Workers)** → **Workers & Pages**.

### 3. Create a Pages project

Click the **Create** button → **Pages** tab → **Connect to Git**.

Authorize Cloudflare to read your GitHub. Pick **only** the `nee-coaching` repo.

### 4. Build settings

On the "Set up builds and deployments" screen:

- **Project name:** `nee-coaching` (or whatever you want; this becomes part of
  the URL)
- **Production branch:** `main`
- **Framework preset:** None
- **Build command:** _(leave empty)_
- **Build output directory:** _(leave empty, or put `.` / `/`)_

Click **Save and Deploy**. The first build takes about 60-90 seconds.

### 5. Add the Anthropic API key

After the first deploy completes:

- Go to **Settings** → **Environment variables**
- Click **Add variable**
- Name: `ANTHROPIC_API_KEY` (exact, case-sensitive)
- Value: your `sk-ant-...` key (the **rotated one**, not the one shared in chat earlier)
- Environment: **Production** (and Preview, if you want it active in preview branches too)
- Click **Save**

Then trigger a redeploy: **Deployments** → top deployment → **...** menu → **Retry deployment**.

(Optional: also add `ANTHROPIC_MODEL` set to `claude-sonnet-4-6` for richer chat
at ~3x cost. Default is `claude-haiku-4-5-20251001`.)

### 6. Try it

Cloudflare gives you a URL at the top of the project page that looks like
`https://nee-coaching.pages.dev` (or `https://nee-coaching-xxx.pages.dev` if
the name was taken).

Open that URL. Click the **💬 Ask Coach Rick** button on any teammate card.
Type a question. Coach Rick replies in 2-5 seconds.

### 7. (Optional) Use a custom domain or replace GitHub Pages

You can keep both URLs alive. Or, in Cloudflare's project Settings → Custom
domains, point a domain you own at the Pages project. Or just use the
`pages.dev` URL.

## How it works

- Static HTML/CSS/JS lives in the repo root, same as before
- `functions/api/chat.js` is a Cloudflare Pages Function. Cloudflare deploys
  it automatically and exposes it at `https://your-site/api/chat`
- The browser POSTs to that endpoint; the function calls Anthropic with the
  secret key; the response comes back to the browser
- The daily refresh workflow continues to run on GitHub Actions (no change)
- Per-leader chat history is saved to that browser's localStorage, so you
  pick up where you left off when you reopen a teammate

## Cost

Cloudflare Pages Functions: 100,000 free requests per day. You will not
exceed it.

Anthropic API: about $0.005 per chat message at Claude Haiku 4.5. 100 questions
per day across all leaders is about $0.50 / day = ~$15/month.

## Troubleshooting

**Chat says "Free-form chat needs a serverless function"**
The site is being served from GitHub Pages (no functions). Open the
`pages.dev` URL Cloudflare gave you instead.

**Chat says "Server is missing ANTHROPIC_API_KEY"**
The env var wasn't saved or the deploy didn't pick it up. Re-check Settings →
Environment variables, then retry deployment.

**Chat says "Anthropic API error"**
The key is invalid, expired, or the account has no balance. Check
https://console.anthropic.com/settings/billing.
