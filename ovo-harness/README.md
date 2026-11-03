# OvO Harness — cPanel version (wired, Codex files + fixes)

Files in this folder:
- index.html — single three-pane layout: left nav, middle actions, right Info / Trace / Timeline / Diff / Logs. Locked task: City Chelsea Rain Boots, black, size 10, $1 CAD, product 23, variation 29, store https://wsiventures.com/solemates
- meta.php — Meta-only proxy, Muse Spark 1.3. Key only from host settings (META_API_KEY / META_MODEL_API_KEY) or a private file outside public_html. Accepts both: ~/ovo-meta-key and /home/wsiventuresoutbo/.ovoharness_meta_key (one line, key only). Never put a key in index.html, meta.php, or any file in ovoharness. If no key is set, Meta calls fail plainly (503) and deterministic stages are kept. No call is simulated.
- assets/ovo_green.png, ovo_white.png, ovo_black.png — same icons, unchanged.

Stages, in order: Before (store only, stop reason stated, funnel Searched), During (Audit deterministic, Enrichment proposals only, Approval by group, Publish dry-run only with blocker stated), After (store plus OVO fields, $1.00 CAD total re-checked, test order recorded from merchant checkout confirmation only).

Payment: pass-through only, test mode only. Agent-only payment bridge is blocked. Never mark paid without a judge-entered test order number from a merchant Stripe test checkout.

Hosting: upload the zip to public_html/ovoharness and Extract there. Open https://wsiventures.com/ovoharness/index.html?v=5 directly — the plain directory URL and plain index.html URL can serve a stale server-cached copy even after a correct upload. Browser cache clearing does not fix server cache. Verify with curl: size, Last-Modified, and that "What should the agent do" is present, for the directory URL, index.html, and a query URL. Purge NGINX / server cache in cPanel if the plain URL stays stale.

Run logs: browser localStorage only in this version. A shared link on another device will not show that run's logs. Export run JSON from Logs for another device.

GitHub: source of truth is repo gfields-wsi/ovo, branch ovo-harness, folder ovo-harness/ — push only with Greg's exact approval for that branch and folder. Do not merge to main.
