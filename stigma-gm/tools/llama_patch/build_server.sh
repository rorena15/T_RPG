#!/usr/bin/env bash
# Build the decrypting llama-server as ONE binary on macOS (Metal + CPU) or Linux (CPU).
# Same idea as build_server.bat: backends statically linked, no dynamic backend loading, no web UI, no subprocess tools.
# Needs: cmake, a C++17 compiler, stigma.patch applied, ggml/src/stigma-key.inc
#   (release key: python tools/model_crypt.py emit --tag models-v1 / CI: from a repository secret
#    test key:    python tools/llama_patch/smoke_test.py genkey --src SRC)
#   tools/llama_patch/build_server.sh [source dir]
set -euo pipefail
SRC="${1:-llama.cpp-stigma}"
if [ ! -f "$SRC/ggml/src/stigma-key.inc" ]; then
  echo "missing $SRC/ggml/src/stigma-key.inc" >&2
  exit 1
fi

EXTRA=()
if [ "$(uname)" = "Darwin" ]; then
  # Metal shaders embedded in the binary (no default.metallib next to it), minimum macOS 12
  EXTRA+=(-DGGML_METAL=ON -DGGML_METAL_EMBED_LIBRARY=ON -DCMAKE_OSX_DEPLOYMENT_TARGET=12.0)
fi

cmake -S "$SRC" -B "$SRC/build-stigma" \
  -DCMAKE_BUILD_TYPE=Release \
  -DBUILD_SHARED_LIBS=OFF \
  -DGGML_BACKEND_DL=OFF \
  -DGGML_NATIVE=OFF \
  -DGGML_OPENMP=OFF \
  -DLLAMA_OPENSSL=OFF \
  -DLLAMA_SUBPROCESS=OFF \
  -DLLAMA_USE_PREBUILT_UI=OFF -DLLAMA_BUILD_UI=OFF \
  -DLLAMA_BUILD_TESTS=OFF -DLLAMA_BUILD_EXAMPLES=OFF -DLLAMA_BUILD_APP=OFF \
  "${EXTRA[@]}"
cmake --build "$SRC/build-stigma" --target llama-server -j
echo "built: $SRC/build-stigma/bin/llama-server"
