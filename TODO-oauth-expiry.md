# Expired-login follow-ups (from comment review vs origin/main @ 411c264)

Context: Google ends logins after 7 days for apps in "Testing" status (external user type).
`yt_studio.py` already catches `RefreshError` and tells the user to run `/yt-setup`,
but `/yt-setup` itself answers "Already connected" because it only checks the token
file's scopes (`hooks/register.tsx:35-45`, `:133-136`).

## 1. Fix `/yt-setup` on an expired login (the real bug)

Success check: after a failed refresh, `/yt-setup` starts sign-in instead of "Already connected", and the status hint shows "not connected".

- [ ] **Failing test first** in `hooks/register.test.ts`: token file with all needed scopes + `.tokens/expired` marker present -> `/yt-setup` must NOT return "Already connected".
- [ ] `yt_studio.py` (`get_oauth_credentials`, the `except RefreshError` branch, ~line 296): write marker `.tokens/expired` before raising. Add a test in `tests/test_yt_auth.py` asserting the marker exists after a failed refresh.
- [ ] `yt_studio.py`: delete the marker on any successful refresh and after a successful `setup`.
- [ ] `hooks/register.tsx` `loginState`: add an `'expired'` state when the marker exists. Treat it like `'none'` in the `command.run` handler (go through the sign-in flow, don't short-circuit) and in the status hint at line ~125.
- [ ] Make sure the sign-in path forces re-auth rather than reusing the dead refresh token (`force_reauth=True`).
- [ ] Risk to check: a stale marker must never trap a user. Test: marker + successful setup -> marker gone.
- [ ] Run: `python -m unittest discover tests` and the hook tests (see `.github/workflows/ci.yml` for exact commands).

## 2. README wording (`README.md:166`, `:175`)

- [ ] Add one trade-off note: moving your own OAuth app out of "Testing" may stop the 7-day expiry, but you then get Google's unverified-app warning at sign-in. Keep the existing `[unconfirmed]` flag on the "publish avoids it" claim until verified; do not state it as fact.
- [ ] Optionally verify it first with your own throwaway Cloud project (set to "In production", wait 8+ days, see if refresh survives).
- [ ] Line 175 says "no Google app verification is required"; reconcile with the note above so the two don't contradict.

## 3. Tester feedback template (not found on main)

- [ ] Check `.github/ISSUE_TEMPLATE/` first. I did not look; if it is missing, add `bug_report.yml` with required fields: client (Claude Code / Claude Desktop / Antigravity), OS + version, plugin version, exact error text.
- [ ] Note in README that `/yt-setup`'s auto-open of Google pages is macOS-only (`README.md:252-254`); Windows/Linux testers need the manual wizard. This is where breakage will differ.

## 4. Housekeeping

- [ ] The ThreadFox comment is an ad. Report/delete it on GitHub.
- [ ] Delete this file before committing, or move it into an issue.
