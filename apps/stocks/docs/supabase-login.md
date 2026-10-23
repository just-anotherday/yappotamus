# Private Supabase login

The frontend signs in with email/password. The backend asks Supabase Auth to
validate the session on every protected HTTP request and WebSocket handshake,
then permits only the configured owner UUID. It never trusts a user ID supplied
by the browser. Old app tokens cannot bypass this check in Supabase mode.
Supabase outages fail closed with HTTP 503.

## Supabase dashboard

Use the existing `yapvibes-stock` project. Under Authentication, ensure the owner
account has a password and can sign in. Disable **Allow new users to sign up**
and **Allow anonymous sign-ins**. There is no signup form in the application.
Dashboard signup settings must be applied separately; this code does not change
your Supabase project settings. No database migration is needed for login.

## Production backend environment

```dotenv
AUTH_PROVIDER=supabase
SUPABASE_URL=https://rqztvqwrcmspzwlghtln.supabase.co
SUPABASE_PUBLISHABLE_KEY=sb_publishable_ZHdIGwzaDBc2t2d27H-8Lw_HB9KmpE1
SUPABASE_ALLOWED_USER_ID=ecd5917f-ab88-4981-9ded-d8df188b2156
```

Keep `DATABASE_URL`, AI and market-data settings as configured. Keep
`INTERNAL_JOB_TOKEN` on the backend and the same value in GitHub Actions as
`STOCKS_INTERNAL_JOB_TOKEN`. These machine credentials are separate from login.
Do not use the Supabase service-role key for user authentication.

## Frontend build environment

```dotenv
NEXT_PUBLIC_AUTH_PROVIDER=supabase
NEXT_PUBLIC_SUPABASE_URL=https://rqztvqwrcmspzwlghtln.supabase.co
NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY=sb_publishable_ZHdIGwzaDBc2t2d27H-8Lw_HB9KmpE1
```

Set these alongside the existing `NEXT_PUBLIC_API_BASE` in the frontend hosting
provider's build environment. Next.js embeds these public values during build;
rebuild and redeploy the frontend after changing them. The URL, publishable key
and owner UUID above are configuration, not secret credentials.

## Rollout and verification

1. Deploy the backend with `AUTH_PROVIDER=supabase` and the settings above, then
   deploy the rebuilt frontend. The old frontend will be locked out during this
   brief transition. Coordinate the deployments.
2. Sign in using the owner's Supabase email/password. Check watchlist, news and
   live prices. Refresh the page to check session restoration, then sign out.
3. Confirm unauthenticated API requests and old app tokens get HTTP 401, and a
   valid Supabase account other than the owner gets HTTP 403.
4. Check the next scheduled ingestion run. It should still use the internal-job
   token without requiring a user session.
5. Remove `APP_ACCESS_TOKEN` and `APP_ACCESS_TOKENS` from production after the
   successful switch. They are ignored while Supabase mode is active.

Legacy token mode remains available for local development: set backend
`AUTH_PROVIDER=token` and frontend `NEXT_PUBLIC_AUTH_PROVIDER=token` and configure
a private `APP_ACCESS_TOKEN`. Never switch production back to a previously
exposed token.

## Sessions

The browser SDK stores and refreshes the user's session; logout removes the
session on that browser. The API validates the session with Supabase Auth, rather
than trusting browser storage. A user's password and refresh token are never
sent to this backend. Existing WebSockets authenticate when connecting; sign-out
unmounts the protected application and closes its sockets.

References: [Supabase Auth configuration](https://supabase.com/docs/guides/auth/general-configuration),
[password login](https://supabase.com/docs/reference/javascript/auth-signinwithpassword),
[API keys](https://supabase.com/docs/guides/getting-started/api-keys).
