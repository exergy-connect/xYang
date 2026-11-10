# Build the QuickJS-ng xyang-ts executable. See README.md for prerequisites.

.PHONY: all all-targets smoke linux-x64 linux-arm64 macos-x64 macos-arm64 windows-x64

all: linux-x64

all-targets:
	./build.sh all

linux-x64 linux-arm64 macos-x64 macos-arm64 windows-x64:
	./build.sh $@

smoke: linux-x64
	./smoke.sh dist/xyang-ts-linux-x64
