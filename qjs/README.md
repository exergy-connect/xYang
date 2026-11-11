# xyang-ts QuickJS binary

A self-contained executable of the TypeScript CLI (`parse`, `validate`, `convert`), built with [QuickJS-ng](https://github.com/quickjs-ng/quickjs) 0.18.0. It sits beside the Python package and the npm package. Those remain the library APIs.

The linux-x64 binary is about 1 MB, starts in a few milliseconds, and speaks the same commands as `xyang-ts`. That is a practical thing for an agent or a CI image to shell out to: one file, no Node or Python install, same stdout as the Node CLI.

## Prerequisites

- bash, curl, tar, `sha256sum`
- Node.js 24 or newer, and the TypeScript dependencies (`cd ts && npm ci`). The build uses that tree's esbuild.
- Zig 0.14.1. Install either the `zig` binary, or:

```bash
python3 -m pip install --user 'ziglang==0.14.1'
```

`build.sh` uses `zig` when it is on `PATH`, and otherwise `python3 -m ziglang`.

The script downloads QuickJS-ng 0.18.0 from GitHub and checks the tarball against a pinned SHA-256. Sources are cached under `qjs/.cache/` (gitignored). Binaries are written to `qjs/dist/` (gitignored).

## Build

From the repository root, after `cd ts && npm ci`:

```bash
cd qjs
./build.sh              # linux-x64 only
./build.sh all          # linux-x64, linux-arm64, macos-arm64, macos-x64, windows-x64
make smoke              # build linux-x64 and compare it with the Node CLI
```

`make linux-arm64`, `make macos-arm64`, `make macos-x64`, and `make windows-x64` build one target.

How the build works:

1. Bundle `ts/src/cli.ts` with esbuild (`--format=esm --target=es2020 --minify --platform=neutral`). `node:fs`, `node:path`, and `node:process` are aliased to the shims in `shims/`, which call `qjs:std` and `qjs:os`. A globals shim provides `Buffer.from` for base64 and sends `console.warn` / `console.error` to stderr.
2. Compile that bundle to C bytecode with QuickJS-ng's `qjsc` (`-e -m`, source and debug stripped, 8 MiB JS stack).
3. Link the bytecode with the QuickJS-ng sources using `zig cc`.

Linux targets are `x86_64-linux-musl` and `aarch64-linux-musl` with `-static`. macOS targets link libSystem (Apple does not support a fully static executable). The Windows target is `x86_64-windows-gnu` and does not need a MinGW runtime DLL.

Output names:

| File | Target |
| --- | --- |
| `dist/xyang-ts-linux-x64` | Linux x64, static |
| `dist/xyang-ts-linux-arm64` | Linux arm64, static |
| `dist/xyang-ts-macos-arm64` | macOS Apple silicon |
| `dist/xyang-ts-macos-x64` | macOS Intel |
| `dist/xyang-ts-windows-x64.exe` | Windows x64 |

## Smoke test

Build the Node CLI, then compare stdout, stderr, and the exit code on the repository examples (including `convert` of `examples/meta-model.yang`, whose JSON Schema is larger than Node's 64 KiB pipe buffer):

```bash
cd ts && npm run build
cd ../qjs && ./smoke.sh dist/xyang-ts-linux-x64
```

On a non-arm64 host, `./smoke.sh dist/xyang-ts-linux-arm64` runs the binary with `qemu-aarch64-static` when that interpreter is installed.

## Release

Pull requests do not build these binaries. [`.github/workflows/qjs-release.yml`](../.github/workflows/qjs-release.yml) runs when a GitHub Release is published, and when someone starts it by hand. It builds all five targets, smoke-tests linux-x64 natively and linux-arm64 under QEMU against the Node CLI, and attaches the five files to that release. A manual run uploads the binaries as a workflow artifact and does not attach them to a release. macOS and Windows binaries are cross-compiled on the Linux runner and are not executed there.

## Usage

```bash
./dist/xyang-ts-linux-x64 parse examples/meta-model.yang
./dist/xyang-ts-linux-x64 validate examples/openconfig/openconfig-interfaces-subset.yang \
  examples/openconfig/sample_interfaces.json
./dist/xyang-ts-linux-x64 convert examples/meta-model.yang
```

Flags match `xyang-ts`: repeatable `--include-path`, and on `validate`, `--format text|json`, `--native-json`, `--features`, `--anydata-validation`, and `--anydata-module`.

Piped stdout is flushed before the process exits. A schema larger than Node's 64 KiB pipe buffer is not truncated.

## Not in this binary

An MCP server is a follow-up. This build does not add one.

## License

xYang is MIT. The executable also contains QuickJS-ng, which is MIT. See [QUICKJS-LICENSE](QUICKJS-LICENSE).
