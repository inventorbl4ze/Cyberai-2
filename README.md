# CYBERAI 2.0

CYBERAI 2.0 is a browser-based assistant with a local knowledge library and an optional live AI backend.

## Project files

- `index.html` — existing CYBERAI 2.0 interface.
- `knowledge.json` — local knowledge library.
- `ai-client.js` — connects the website to the secure AI backend.
- `worker.js` — Cloudflare Worker that calls the OpenAI Responses API without exposing the API key in the website.
- `wrangler.toml` — Cloudflare Worker configuration.

## Connect the live AI

1. Deploy `worker.js` as a Cloudflare Worker using the included `wrangler.toml`.
2. In the Worker settings, add a secret named `OPENAI_API_KEY`. Enter the key only in Cloudflare's secret field. Never put it in `index.html`, `ai-client.js`, GitHub, or a public message.
3. Optionally add a Worker variable named `ALLOWED_ORIGIN` and set it to the exact HTTPS address of the CYBERAI website.
4. After deployment, copy the Worker URL and add `/api/chat` to its end.
5. Open CYBERAI 2.0 and use **Connect AI backend** to save that URL in the browser.

The Worker uses the Responses API and defaults to model `gpt-5.5`. You can override this with a Worker variable named `AI_MODEL`.

## Security notes

- The OpenAI key is read only from the Worker secret `OPENAI_API_KEY`.
- The browser sends chat text to the Worker; it never receives the API key.
- Requests are limited and request history is bounded.
- API response storage is disabled in the request.
- API usage may incur charges. Check the current API pricing and account billing before enabling it.
