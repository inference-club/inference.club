# GitHub OAuth setup

Sign-in is GitHub-only (handled by `social-auth-app-django`). You need
*two* OAuth apps if you want both local dev and production: GitHub
binds each app to exactly one callback URL.

## Production app (for `https://inference.club/`)

1. Go to <https://github.com/settings/developers> → **New OAuth App**
2. Fill in:
   - **Application name:** `inference.club`
   - **Homepage URL:** `https://inference.club`
   - **Authorization callback URL:** `https://api.inference.club/oauth/complete/github/`
     (exact, including trailing slash — GitHub's "redirect_uri does not match"
     error is unforgiving here)
3. Click **Register application**
4. On the next page, copy the **Client ID**, then click **Generate a new
   client secret** and copy that too — GitHub only shows the secret once
5. Save these as repo secrets (see [secrets.md](secrets.md)):
   - `GH_OAUTH_CLIENT_ID`
   - `GH_OAUTH_CLIENT_SECRET`

## Dev app (for `http://localhost:3001`)

Same flow, but with:
- **Application name:** `inference.club (dev)`
- **Homepage URL:** `http://localhost:3001`
- **Authorization callback URL:** `http://localhost:8001/oauth/complete/github/`

Save the dev pair into `backend/.env` as:
```env
GITHUB_OAUTH_CLIENT_ID=...
GITHUB_OAUTH_CLIENT_SECRET=...
```

`backend/.env` is gitignored. The Django settings load it via
`python-dotenv` and fall back to whatever is in the process env, so the
prod container's env vars (rendered by Pulumi from `GH_OAUTH_*` repo
secrets) take precedence in production.

## What goes wrong

- **Wrong callback URL.** You must use `https://api.inference.club/...`
  (the API subdomain), not `https://inference.club/...`. The OAuth
  callback path lives in Django, which is reachable via `api.`
- **Missing trailing slash.** `…/oauth/complete/github/` ends with a `/`.
  Without it GitHub returns "redirect_uri does not match"
- **CSRF cookie scope.** Production sets `CSRF_COOKIE_DOMAIN=.inference.club`
  so the CSRF cookie issued by `api.inference.club` is readable by
  JavaScript on `inference.club`. Without that, the dashboard's
  POST-after-login flows (token mint, etc.) fail with 403. See the
  Django settings for both `CSRF_COOKIE_DOMAIN` and `SESSION_COOKIE_DOMAIN`
- **Reusing the dev OAuth app for prod.** Don't — GitHub allows one
  callback URL per app, and rotating the prod app's URL would break
  any open dev sessions. Two apps, two pairs of secrets

## Rotating

If a client secret leaks (e.g. ends up in a chat transcript): GitHub
OAuth app page → **Generate a new client secret** → update the
`GH_OAUTH_CLIENT_SECRET` repo secret → trigger `infra-deploy` to
re-render `backend.env` on the VPS.
