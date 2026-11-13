# CYBERAI 2.0 — CYRA

A fresh rebuild featuring CYRA, a full-body holographic AI companion.

## Features
- Animated holographic avatar and responsive mobile-first interface
- Text chat through the connected Cloudflare AI gateway
- Browser speech synthesis and speech recognition (browser support varies)
- No API key is stored in this repository or browser

## Live AI gateway
The website sends chat requests to the existing Cloudflare Worker endpoint configured in index.html. The Worker must have its server-side OPENAI_API_KEY secret configured. API usage may incur charges.

## Deploy
GitHub Pages can serve this static site directly from the main branch root.

Created by Oduyebo Abiola.
