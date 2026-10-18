# MongoDB Atlas setup

ClipCart uses MongoDB Atlas when `MONGODB_URI` is set. Without it, the API uses an in-process store reported as `local_memory`, which is never presented as Atlas.

## Status (2026-10-17)

| Item | State |
| --- | --- |
| Code path | `services/api/app/storage/db.py`: one `MongoClient` (8 s server selection, `appname=clipcart`). Indexes are created at startup. `mongodb+srv` works through dnspython 2.9.0, and TLS uses certifi's CA bundle on python.org macOS builds. |
| Real MongoDB | The full backend suite passes against MongoDB 8.0.4, the version Atlas runs: 282 passed, 1 skipped. Run `CLIPCART_TEST_MONGODB_URI=mongodb://127.0.0.1:27027 pytest services/api/tests`. Restore after a server restart was verified in the browser earlier, see `docs/verification/style-memory-e2e/`. |
| Atlas itself | **Not verified yet.** `MONGODB_URI` is empty in `.env`. |
| Secrets | `Settings.mongodb_uri` is excluded from `repr`, and `--only atlas` prints only the host. The URI belongs only in the untracked root `.env`. |

## Owner steps (in the Atlas web UI)

These steps need your Atlas account, so they are yours to do. Claude doesn't create accounts or handle database passwords.

1. **Cluster.** Create or choose a project, then create a cluster. Free M0 is enough for the demo. Pick a region near you.
2. **Database user.** Go to Database Access, then Add user, with password authentication.
   - **Privileges:** grant **readWrite on the `clipcart` database only**, rather than "Atlas admin" or "read and write to any database".
   - **Name:** use a dedicated user name, for example `clipcart-app`.
3. **Network access.** Go to Network Access and add your current IP address. Avoid `0.0.0.0/0`.
4. **Connection string.** Go to Connect, then Drivers, then Python, and copy the `mongodb+srv://…` string. Insert the user's password. If the password has `@ : / ? # [ ]` or `%`, percent-encode it.
5. **Root `.env`.** Edit it yourself. It's untracked, so never commit it.
   ```
   MONGODB_URI=mongodb+srv://clipcart-app:<password>@<cluster>.mongodb.net/?retryWrites=true&w=majority&appName=clipcart
   MONGODB_DB=clipcart
   ```

## Verify (Claude can run these once the URI is set)

1. **Connectivity, without printing secrets:**
   ```
   services/api/.venv/bin/python scripts/live_checks.py --only atlas
   ```
   Expect `status: ok`, `dbMode: atlas`, `tls: true` and a server version. It also lists `indexesPerCollection`. The check writes and deletes one marker document in `_healthcheck`, and creates the app's indexes if they're missing.
2. **App on Atlas:** restart the server on port 8000. `GET /api/health` should report `database.mode = "atlas"`, `ok: true` and no "not MongoDB Atlas" note.
3. **Persistence (SRS AT16):** run the restart flow in `scripts/e2e/style-memory/` against a separate verification server that uses Atlas with fixture providers. No paid calls are made, and `FEATURE_STYLE_MEMORY=1` is set only in that process, so `.env` flags stay as they are:
   - save an item and a preference
   - restart the server
   - confirm the same records come back
   - correct and delete the preference
   - restart again

   Each step also runs owner-isolation checks.

## Troubleshooting

| Symptom | Likely cause |
| --- | --- |
| Startup fails after about 8 s with `ServerSelectionTimeoutError` | Your IP isn't on the access list, or the cluster is paused |
| `SSL: CERTIFICATE_VERIFY_FAILED` | `SSL_CERT_FILE` points to a bad bundle. Unset it, and the app uses certifi's. |
| `Authentication failed` | Wrong password or user, or the password isn't percent-encoded |
| `not authorized on <db>` | `MONGODB_DB` differs from the database the user may write to |
| `DNS ... SRV` errors | The network blocks SRV lookups. Use the non-SRV "standard connection string" from Atlas. |

The app fails fast at startup if Atlas is unreachable, because it creates indexes on connect. `GET /api/health` reports `database.ok` from a ping after that.
