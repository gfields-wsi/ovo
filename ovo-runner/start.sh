#!/bin/sh
# Start command for a host. Change only the store address.
# The store address must come from the merchant. Do not set a
# default store here, and do not set a check interval here.
# No scheduled check is set by this file.
#
# Usage:
#   STORE_URL=https://example.com/shop sh start.sh
#   STORE_URL=https://example.com/shop sh start.sh --skip-spark
#   STORE_URL=https://example.com/shop RUN_KEY=my-run-1 sh start.sh
#
# The runner pauses at Merchant Approval by default.
# It does not publish, and it does not start the plugin stage
# until a merchant decision file is given.
set -e
cd "$(dirname "$0")"
if [ -z "$STORE_URL" ]; then
  echo "Set STORE_URL first. Example: STORE_URL=https://example.com/shop sh start.sh" >&2
  exit 2
fi
if [ -n "$RUN_KEY" ]; then
  exec python3 runner.py --store-url "$STORE_URL" --run-key "$RUN_KEY" "$@"
fi
exec python3 runner.py --store-url "$STORE_URL" "$@"
