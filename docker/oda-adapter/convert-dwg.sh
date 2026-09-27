#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: convert-dwg INPUT_DIR OUTPUT_DIR [RECURSE] [AUDIT] [FILTER]

Required runtime mount:
  -v /path/to/locally-obtained-oda-app:/opt/oda:ro

Environment:
  ODA_BIN      executable path inside the container
               (default: /opt/oda/ODAFileConverter)
  ODA_VERSION  output version accepted by ODA (default: ACAD2018)
  ODA_TIMEOUT  maximum conversion time in seconds (default: 900)
EOF
}

if [[ ${1:-} == '-h' || ${1:-} == '--help' ]]; then
  usage
  exit 0
fi

input_dir=${1:?Input directory is required}
output_dir=${2:?Output directory is required}
recurse=${3:-0}
audit=${4:-1}
filter=${5:-'*.dwg'}
oda_bin=${ODA_BIN:-/opt/oda/ODAFileConverter}
oda_version=${ODA_VERSION:-ACAD2018}
oda_timeout=${ODA_TIMEOUT:-900}

if [[ ! -x "$oda_bin" ]]; then
  printf 'ODA executable is unavailable: %s\n' "$oda_bin" >&2
  printf 'Mount a locally obtained ODA application directory at /opt/oda and set ODA_BIN if needed.\n' >&2
  exit 2
fi
if [[ ! -d "$input_dir" ]]; then
  printf 'Input directory does not exist: %s\n' "$input_dir" >&2
  exit 2
fi
if [[ "$input_dir" == "$output_dir" ]]; then
  printf 'Output directory must differ from input directory.\n' >&2
  exit 2
fi
mkdir -p "$output_dir"

if ! [[ "$oda_timeout" =~ ^[1-9][0-9]*$ ]]; then
  printf 'ODA_TIMEOUT must be a positive integer, got: %s\n' "$oda_timeout" >&2
  exit 2
fi

printf 'ODA conversion: version=%s type=DXF recurse=%s audit=%s filter=%s timeout=%ss\n' \
  "$oda_version" "$recurse" "$audit" "$filter" "$oda_timeout" >&2

exec timeout --signal=TERM --kill-after=15s "${oda_timeout}s" \
  xvfb-run -a --server-args='-screen 0 1280x1024x24' \
  "$oda_bin" "$input_dir" "$output_dir" "$oda_version" DXF "$recurse" "$audit" "$filter"
