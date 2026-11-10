#!/usr/bin/env bash
# Build the xyang-ts CLI as a QuickJS-ng executable.
#
# Prerequisites:
#   - bash, curl, tar, sha256sum
#   - Node.js >= 24 and `npm ci` in ts/ (provides esbuild)
#   - Zig 0.14.x. Either `zig` on PATH, or:
#       python3 -m pip install --user 'ziglang==0.14.1'
#     and then `python3 -m ziglang` (used automatically when `zig` is absent)
#
# Usage:
#   ./build.sh                  # linux-x64
#   ./build.sh linux-x64 linux-arm64 macos-arm64 macos-x64 windows-x64
#   ./build.sh all
#
# Linux binaries are static musl executables. macOS binaries link libSystem.
# Windows binaries link the system libraries and do not need a MinGW runtime DLL.
#
# QuickJS-ng 0.18.0 is downloaded from GitHub and checked against the SHA-256
# pinned below. Bytecode is produced once by a host qjsc, then linked for each
# target with `zig cc`.

set -euo pipefail

QJS_VERSION="${QJS_VERSION:-0.18.0}"
QJS_SHA256="${QJS_SHA256:-28bcd89aa3683fd2a946537e5ce3f11cc46b5cbf3383c7561aaef3df5ff9f1dd}"
QJS_URL="${QJS_URL:-https://github.com/quickjs-ng/quickjs/archive/refs/tags/v${QJS_VERSION}.tar.gz}"

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HERE="$(cd "$(dirname "$0")" && pwd)"
CACHE="${QJS_CACHE:-$HERE/.cache}"
DIST="${QJS_DIST:-$HERE/dist}"
SRC="$CACHE/quickjs-$QJS_VERSION"
ESBUILD="${ESBUILD:-$ROOT/ts/node_modules/esbuild/bin/esbuild}"

ALL_TARGETS=(linux-x64 linux-arm64 macos-arm64 macos-x64 windows-x64)

if [[ "${1:-linux-x64}" == "all" ]]; then
  TARGETS=("${ALL_TARGETS[@]}")
elif [[ $# -eq 0 ]]; then
  TARGETS=(linux-x64)
else
  TARGETS=("$@")
fi

if [[ ! -x "$ESBUILD" ]]; then
  echo "esbuild not found at $ESBUILD" >&2
  echo "Install the TypeScript package first: (cd \"$ROOT/ts\" && npm ci)" >&2
  exit 1
fi

if [[ -n "${ZIG:-}" ]]; then
  # shellcheck disable=SC2206
  ZIG_CMD=($ZIG)
elif command -v zig >/dev/null 2>&1; then
  ZIG_CMD=(zig)
elif python3 -c 'import ziglang' >/dev/null 2>&1; then
  ZIG_CMD=(python3 -m ziglang)
else
  echo "Zig is required. Install zig 0.14.1 or: python3 -m pip install --user 'ziglang==0.14.1'" >&2
  exit 1
fi

echo "Using zig $("${ZIG_CMD[@]}" version)"

mkdir -p "$CACHE" "$DIST"

tarball="$CACHE/quickjs-$QJS_VERSION.tar.gz"
if [[ ! -f "$tarball" ]]; then
  echo "Downloading QuickJS-ng $QJS_VERSION"
  curl -fsSL -o "$tarball.partial" "$QJS_URL"
  mv "$tarball.partial" "$tarball"
fi
echo "$QJS_SHA256  $tarball" | sha256sum -c -

if [[ ! -f "$SRC/quickjs.c" ]]; then
  tar -xzf "$tarball" -C "$CACHE"
fi

QJS_SOURCES=(dtoa.c libregexp.c libunicode.c quickjs.c quickjs-libc.c)

DEFINES=(-DQUICKJS_NG_BUILD -D_GNU_SOURCE -DQJS_BUILD_LIBC)
OPT=(-Os -ffunction-sections -fdata-sections)

zig_target() {
  case "$1" in
    linux-x64) echo x86_64-linux-musl ;;
    linux-arm64) echo aarch64-linux-musl ;;
    macos-x64) echo x86_64-macos-none ;;
    macos-arm64) echo aarch64-macos-none ;;
    windows-x64) echo x86_64-windows-gnu ;;
    *)
      echo "Unknown target: $1" >&2
      echo "Known targets: ${ALL_TARGETS[*]}" >&2
      return 1
      ;;
  esac
}

output_name() {
  case "$1" in
    windows-x64) echo xyang-ts-windows-x64.exe ;;
    *) echo "xyang-ts-$1" ;;
  esac
}

compile_objects() {
  local triple="$1"
  local objdir="$2"
  shift 2
  local -a extra=("$@")
  mkdir -p "$objdir"
  local pids=()
  local src obj
  for src in "${QJS_SOURCES[@]}"; do
    obj="$objdir/${src%.c}.o"
    if [[ -f "$obj" && "$obj" -nt "$SRC/$src" ]]; then
      continue
    fi
    echo "  cc $src -> ${obj#"$CACHE/"}"
    "${ZIG_CMD[@]}" cc -target "$triple" "${OPT[@]}" "${DEFINES[@]}" "${extra[@]}" \
      -I"$SRC" -c -o "$obj" "$SRC/$src" &
    pids+=("$!")
  done
  local pid fail=0
  for pid in "${pids[@]+"${pids[@]}"}"; do
    wait "$pid" || fail=1
  done
  if [[ "$fail" -ne 0 ]]; then
    echo "Compiling QuickJS objects for $triple failed" >&2
    exit 1
  fi
}

build_host_qjsc() {
  local host_obj qjsc
  host_obj="$CACHE/obj/host"
  qjsc="$CACHE/qjsc"
  if [[ -x "$qjsc" && "$qjsc" -nt "$SRC/qjsc.c" && "$qjsc" -nt "$SRC/quickjs.c" ]]; then
    echo "Host qjsc is up to date"
    return
  fi
  echo "Building host qjsc"
  mkdir -p "$host_obj"
  local pids=() src obj
  for src in "${QJS_SOURCES[@]}" qjsc.c; do
    obj="$host_obj/${src%.c}.o"
    echo "  cc $src"
    "${ZIG_CMD[@]}" cc -O2 "${DEFINES[@]}" -I"$SRC" -c -o "$obj" "$SRC/$src" &
    pids+=("$!")
  done
  local pid fail=0
  for pid in "${pids[@]}"; do
    wait "$pid" || fail=1
  done
  if [[ "$fail" -ne 0 ]]; then
    echo "Host qjsc compile failed" >&2
    exit 1
  fi
  "${ZIG_CMD[@]}" cc -O2 -o "$qjsc" "$host_obj"/*.o -lm -pthread
}

bundle_cli() {
  local bundle="$CACHE/xyang.qjs.mjs"
  echo "Bundling TypeScript CLI"
  "$ESBUILD" "$ROOT/ts/src/cli.ts" \
    --bundle \
    --format=esm \
    --target=es2020 \
    --minify \
    --platform=neutral \
    --alias:node:fs="$HERE/shims/fs.js" \
    --alias:node:path="$HERE/shims/path.js" \
    --alias:node:process="$HERE/shims/process.js" \
    --inject:"$HERE/shims/globals.js" \
    --external:qjs:std \
    --external:qjs:os \
    --outfile="$bundle" \
    --log-level=info
  local gen="$CACHE/xyang_gen.c"
  echo "Compiling bytecode with qjsc"
  "$CACHE/qjsc" -e -m -s -s -S 8388608 -n xyang-ts -o "$gen" "$bundle"
}

link_target() {
  local name="$1"
  local triple objdir out tmp
  triple="$(zig_target "$name")"
  objdir="$CACHE/obj/$name"
  out="$DIST/$(output_name "$name")"
  tmp="${out}.tmp"
  echo "Linking $name ($triple)"
  local -a extra=()
  local -a libs=(-lm -pthread)
  local -a link=(-static -Wl,--gc-sections -s)
  if [[ "$name" == windows-* ]]; then
    # Zig's mingw target already defines _WIN32_WINNT. Don't pass it again.
    extra+=(-DWIN32_LEAN_AND_MEAN)
    libs=()
  fi
  if [[ "$name" == macos-* ]]; then
    # Mach-O cannot statically link libSystem. -dead_strip drops unused objects.
    link=(-Wl,-dead_strip -s)
  fi
  compile_objects "$triple" "$objdir" "${extra[@]+"${extra[@]}"}"
  "${ZIG_CMD[@]}" cc -target "$triple" "${OPT[@]}" "${DEFINES[@]}" "${extra[@]+"${extra[@]}"}" \
    "${link[@]}" -I"$SRC" -o "$tmp" "$CACHE/xyang_gen.c" "$objdir"/*.o "${libs[@]+"${libs[@]}"}"
  mv "$tmp" "$out"
  if [[ "$name" == linux-* ]]; then
    if ! file "$out" | grep -q "statically linked"; then
      echo "Expected a statically linked binary: $out" >&2
      file "$out" >&2 || true
      exit 1
    fi
  fi
  local bytes
  bytes="$(wc -c < "$out" | tr -d ' ')"
  echo "Built $out ($bytes bytes)"
}

build_host_qjsc
bundle_cli
for target in "${TARGETS[@]}"; do
  link_target "$target"
done

echo "Binaries:"
ls -l "$DIST"
