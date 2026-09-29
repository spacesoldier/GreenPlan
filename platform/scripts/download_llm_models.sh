#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PLATFORM_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
MODEL_ROOT="${1:-${PLATFORM_DIR}/data/llm-models}"

QWEN_REV="bc640142c66e1fdd12af0bd68f40445458f3869b"
GEMMA_REV="d0976223747697cb51e056d85c532013931fe52e"
YANDEX_REV="9fe287d2f512503046bb008aed350f2b4bbb903d"

command -v aria2c >/dev/null || {
  echo "aria2c is required" >&2
  exit 1
}
command -v curl >/dev/null || {
  echo "curl is required" >&2
  exit 1
}

download_weight() {
  local repo="$1"
  local revision="$2"
  local filename="$3"
  local destination="$4"

  mkdir -p "$destination"
  aria2c \
    --continue=true \
    --file-allocation=none \
    --max-connection-per-server=4 \
    --min-split-size=16M \
    --split=4 \
    --dir="$destination" \
    --out="$filename" \
    "https://huggingface.co/${repo}/resolve/${revision}/${filename}"
}

download_text() {
  local repo="$1"
  local revision="$2"
  local filename="$3"
  local destination="$4"

  mkdir -p "$destination"
  curl -fL --retry 3 \
    -o "${destination}/${filename}" \
    "https://huggingface.co/${repo}/resolve/${revision}/${filename}"
}

assert_gguf() {
  local path="$1"
  if [[ ! -s "$path" || "$(head -c 4 "$path")" != "GGUF" ]]; then
    echo "Invalid or incomplete GGUF: $path" >&2
    exit 1
  fi
}

QWEN_DIR="${MODEL_ROOT}/qwen3-4b"
GEMMA_DIR="${MODEL_ROOT}/gemma-3-4b-it"
YANDEX_DIR="${MODEL_ROOT}/yandexgpt-5-lite-8b"

download_weight "Qwen/Qwen3-4B-GGUF" "$QWEN_REV" \
  "Qwen3-4B-Q4_K_M.gguf" "$QWEN_DIR"
download_text "Qwen/Qwen3-4B-GGUF" "$QWEN_REV" "README.md" "$QWEN_DIR"
download_text "Qwen/Qwen3-4B-GGUF" "$QWEN_REV" "LICENSE" "$QWEN_DIR"

download_weight "ggml-org/gemma-3-4b-it-GGUF" "$GEMMA_REV" \
  "gemma-3-4b-it-Q4_K_M.gguf" "$GEMMA_DIR"
download_weight "ggml-org/gemma-3-4b-it-GGUF" "$GEMMA_REV" \
  "mmproj-model-f16.gguf" "$GEMMA_DIR"
download_text "ggml-org/gemma-3-4b-it-GGUF" "$GEMMA_REV" "README.md" "$GEMMA_DIR"

download_weight "yandex/YandexGPT-5-Lite-8B-instruct-GGUF" "$YANDEX_REV" \
  "YandexGPT-5-Lite-8B-instruct-Q4_K_M.gguf" "$YANDEX_DIR"
download_text "yandex/YandexGPT-5-Lite-8B-instruct-GGUF" "$YANDEX_REV" \
  "README.md" "$YANDEX_DIR"
download_text "yandex/YandexGPT-5-Lite-8B-instruct-GGUF" "$YANDEX_REV" \
  "LICENSE" "$YANDEX_DIR"

for file in \
  "${QWEN_DIR}/Qwen3-4B-Q4_K_M.gguf" \
  "${GEMMA_DIR}/gemma-3-4b-it-Q4_K_M.gguf" \
  "${GEMMA_DIR}/mmproj-model-f16.gguf" \
  "${YANDEX_DIR}/YandexGPT-5-Lite-8B-instruct-Q4_K_M.gguf"; do
  assert_gguf "$file"
done

(
  cd "$MODEL_ROOT"
  sha256sum \
    qwen3-4b/Qwen3-4B-Q4_K_M.gguf \
    gemma-3-4b-it/gemma-3-4b-it-Q4_K_M.gguf \
    gemma-3-4b-it/mmproj-model-f16.gguf \
    yandexgpt-5-lite-8b/YandexGPT-5-Lite-8B-instruct-Q4_K_M.gguf \
    > SHA256SUMS
)

echo "Models downloaded and verified in: ${MODEL_ROOT}"
