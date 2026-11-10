#!/usr/bin/env bash
# Compare a QuickJS xyang-ts binary with the Node CLI on repository examples.
#
# Usage (from anywhere):
#   qjs/smoke.sh qjs/dist/xyang-ts-linux-x64
#
# Requires ts/dist/cli.js (`cd ts && npm run build`) and Node.js.
# Linux arm64 binaries are run under qemu-aarch64-static when that interpreter
# is on PATH and the host is not arm64.

set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "usage: $0 path/to/xyang-ts-binary" >&2
  exit 2
fi

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BIN="$(cd "$(dirname "$1")" && pwd)/$(basename "$1")"
NODE_CLI="$ROOT/ts/dist/cli.js"

if [[ ! -f "$BIN" ]]; then
  echo "binary not found: $BIN" >&2
  exit 1
fi
if [[ ! -f "$NODE_CLI" ]]; then
  echo "Node CLI not found at $NODE_CLI" >&2
  echo "Build it with: (cd \"$ROOT/ts\" && npm ci && npm run build)" >&2
  exit 1
fi

RUN=("$BIN")
if file "$BIN" | grep -q "ARM aarch64"; then
  host="$(uname -m)"
  if [[ "$host" != "aarch64" && "$host" != "arm64" ]]; then
    if command -v qemu-aarch64-static >/dev/null 2>&1; then
      RUN=(qemu-aarch64-static "$BIN")
    elif command -v qemu-aarch64 >/dev/null 2>&1; then
      RUN=(qemu-aarch64 "$BIN")
    else
      echo "arm64 binary requires qemu-aarch64-static on this host" >&2
      exit 1
    fi
  fi
fi

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
fail=0
n=0

compare() {
  local label="$1"
  shift
  n=$((n + 1))
  local nd="$work/case-$n"
  mkdir -p "$nd"
  set +e
  if [[ -n "${SMOKE_STDIN:-}" ]]; then
    node "$NODE_CLI" "$@" <"$SMOKE_STDIN" >"$nd/node.out" 2>"$nd/node.err"
  else
    node "$NODE_CLI" "$@" >"$nd/node.out" 2>"$nd/node.err"
  fi
  echo $? >"$nd/node.code"
  if [[ -n "${SMOKE_STDIN:-}" ]]; then
    "${RUN[@]}" "$@" <"$SMOKE_STDIN" >"$nd/qjs.out" 2>"$nd/qjs.err"
  else
    "${RUN[@]}" "$@" >"$nd/qjs.out" 2>"$nd/qjs.err"
  fi
  echo $? >"$nd/qjs.code"
  set -e
  local ok=1
  local why=""
  if ! cmp -s "$nd/node.out" "$nd/qjs.out"; then
    ok=0
    why="stdout"
  fi
  if ! cmp -s "$nd/node.err" "$nd/qjs.err"; then
    ok=0
    why="${why:+$why+}stderr"
  fi
  if [[ "$(cat "$nd/node.code")" != "$(cat "$nd/qjs.code")" ]]; then
    ok=0
    why="${why:+$why+}exit"
  fi
  if [[ "$label" == "convert meta-model" ]]; then
    cp "$nd/node.out" "$work/meta-model.out"
  fi
  if [[ "$ok" -eq 1 ]]; then
    printf 'ok   %s\n' "$label"
  else
    fail=1
    printf 'FAIL %s (%s)\n' "$label" "$why"
    echo "  node exit $(cat "$nd/node.code") qjs exit $(cat "$nd/qjs.code")"
    echo "  stdout bytes node=$(wc -c < "$nd/node.out") qjs=$(wc -c < "$nd/qjs.out")"
    echo "  stderr bytes node=$(wc -c < "$nd/node.err") qjs=$(wc -c < "$nd/qjs.err")"
    diff -u "$nd/node.out" "$nd/qjs.out" | head -n 40 || true
    diff -u "$nd/node.err" "$nd/qjs.err" | head -n 40 || true
  fi
}

cd "$ROOT"

compare "usage"
compare "unknown command" not-a-command
compare "missing yang" parse
compare "missing file" parse examples/no-such-module.yang
compare "parse meta-model" parse examples/meta-model.yang
compare "parse generic-field" parse examples/generic-field.yang
compare "parse identity" parse examples/identity_roundtrip.yang
compare "parse openconfig" parse examples/openconfig/openconfig-interfaces-subset.yang
compare "convert meta-model" convert examples/meta-model.yang
compare "convert generic-field" convert examples/generic-field.yang
compare "convert identity" convert examples/identity_roundtrip.yang
compare "convert openconfig" convert examples/openconfig/openconfig-interfaces-subset.yang
compare "validate openconfig" validate \
  examples/openconfig/openconfig-interfaces-subset.yang \
  examples/openconfig/sample_interfaces.json
compare "parse inet-types via include-path" parse \
  --include-path examples/ietf-yang-push/modules \
  examples/ietf-yang-push/modules/ietf-inet-types@2013-07-15.yang
compare "validate yang-push notification" validate \
  examples/ietf-yang-push/modules/ietf-yp-notification@2025-06-04.yang \
  examples/ietf-yang-push/27-push-update.json \
  --include-path examples/ietf-yang-push/modules \
  --anydata-validation complete \
  --anydata-module examples/ietf-yang-push/modules/ietf-yang-push@2019-09-09.yang \
  --anydata-module examples/ietf-yang-push/modules/ietf-distributed-notif@2024-04-21.yang \
  --anydata-module examples/ietf-yang-push/modules/ietf-yp-observation@2025-02-24.yang \
  --anydata-module examples/ietf-yang-push/modules/ietf-alarms@2019-09-11.yang \
  --anydata-module examples/ietf-yang-push/modules/ietf-alarms-x733@2019-09-11.yang

# Relative paths, so resolution is not only from the repository root.
pushd "$ROOT/examples" >/dev/null
compare "parse meta-model from examples/" parse meta-model.yang
compare "convert openconfig from examples/" convert openconfig/openconfig-interfaces-subset.yang
popd >/dev/null

# Stdin instance, binary length check, and a missing include.
stdin_dir="$(mktemp -d)"
cat >"$stdin_dir/bin.yang" <<'EOF'
module bin-test {
  yang-version 1.1;
  namespace "urn:test:bin";
  prefix b;
  container top {
    leaf data { type binary { length "0..16"; } }
    leaf name { type string; }
  }
}
EOF
printf '%s\n' '{"top":{"name":"hello","data":"aGVsbG8="}}' >"$stdin_dir/ok.json"
printf '%s\n' '{"top":{"name":"hello","data":"not!!!base64"}}' >"$stdin_dir/bad.json"
SMOKE_STDIN="$stdin_dir/ok.json" compare "validate binary from stdin" validate "$stdin_dir/bin.yang"
SMOKE_STDIN="$stdin_dir/bad.json" compare "reject bad binary from stdin" validate "$stdin_dir/bin.yang"
unset SMOKE_STDIN
compare "validate binary file" validate "$stdin_dir/bin.yang" "$stdin_dir/ok.json"
rm -rf "$stdin_dir"

meta_bytes="$(wc -c < "$work/meta-model.out" | tr -d ' ')"
if [[ "$meta_bytes" -le $((128 * 1024)) ]]; then
  echo "convert meta-model produced only $meta_bytes bytes; expected a schema larger than 128 KiB" >&2
  fail=1
fi

echo
echo "Compared $n invocations. meta-model schema is $meta_bytes bytes."
if [[ "$fail" -ne 0 ]]; then
  echo "Smoke test failed." >&2
  exit 1
fi

python3 - "$ROOT" "${RUN[@]}" <<'PY'
import subprocess, sys, time
root = sys.argv[1]
cmd = sys.argv[2:]
times = []
for _ in range(20):
    t = time.perf_counter()
    subprocess.run(cmd, cwd=root, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    times.append((time.perf_counter() - t) * 1000)
times.sort()
median = times[len(times) // 2]
print(f"startup (usage, n=20): min {times[0]:.2f} ms  median {median:.2f} ms  max {times[-1]:.2f} ms")
convert = cmd + ["convert", "examples/meta-model.yang"]
t = time.perf_counter()
subprocess.run(convert, cwd=root, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
print(f"convert examples/meta-model.yang: {(time.perf_counter() - t) * 1000:.1f} ms")
PY

echo "binary: $BIN"
file "$BIN" || true
ls -l "$BIN"
