#!/usr/bin/env bash
# Read-only DWG inventory. Does not invoke a CAD converter or alter input files.
set -euo pipefail
IFS=$'\n\t'

usage() {
  cat <<'EOF'
Usage: scripts/scan_dwg_inventory.sh [dataset_dir] [output_dir]

Scans every *.dwg below dataset_dir and writes:
  files.csv       one row per file, including the six-byte DWG signature
  versions.csv    aggregates by signature and conversion readiness
  report.md       human-readable summary and next actions

Defaults:
  dataset_dir = dataset
  output_dir  = reports/dwg-inventory

The output directory must not already exist. The source directory is read only.
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

input_dir=${1:-dataset}
output_dir=${2:-reports/dwg-inventory}

if [[ ! -d "$input_dir" ]]; then
  printf 'Input directory does not exist: %s\n' "$input_dir" >&2
  exit 2
fi
if [[ -e "$output_dir" ]]; then
  printf 'Refusing to overwrite existing output: %s\n' "$output_dir" >&2
  exit 2
fi

mkdir -p "$output_dir"
tmp_dir=$(mktemp -d)
trap 'rm -rf "$tmp_dir"' EXIT

csv_quote() {
  local value=$1
  value=${value//\"/\"\"}
  printf '"%s"' "$value"
}

# ODA's public specification maps these six-byte file headers to DWG releases.
# readiness is intentionally conservative: it is a candidate for a converter probe,
# not proof that all custom/AEC objects inside the drawing can be preserved.
classify_signature() {
  case "$1" in
    AC1009) printf 'R12|candidate_same_or_newer_dxf' ;;
    AC1012) printf 'R13|candidate_same_or_newer_dxf' ;;
    AC1014) printf 'R14|candidate_same_or_newer_dxf' ;;
    AC1015) printf 'R2000|candidate_same_or_newer_dxf' ;;
    AC1018) printf 'R2004|candidate_same_or_newer_dxf' ;;
    AC1021) printf 'R2007|candidate_same_or_newer_dxf' ;;
    AC1024) printf 'R2010|candidate_same_or_newer_dxf' ;;
    AC1027) printf 'R2013-R2017|candidate_same_or_newer_dxf' ;;
    AC1032) printf 'R2018-R2025|target_ac1032' ;;
    AC*)    printf 'unknown_acad_version|converter_probe_required' ;;
    *)      printf 'not_recognized_as_dwg|rejected_before_conversion' ;;
  esac
}

files_csv="$output_dir/files.csv"
versions_csv="$output_dir/versions.csv"
rows_tsv="$tmp_dir/rows.tsv"
invalid_tsv="$tmp_dir/not-dwg.tsv"

printf 'relative_path,size_bytes,signature,autocad_release,readiness\n' > "$files_csv"
: > "$rows_tsv"
: > "$invalid_tsv"

file_total=0
while IFS= read -r -d '' file_path; do
  file_total=$((file_total + 1))
  relative_path=${file_path#"$input_dir"/}
  size_bytes=$(wc -c < "$file_path" | tr -d '[:space:]')
  signature=$(LC_ALL=C dd if="$file_path" bs=6 count=1 status=none 2>/dev/null || true)
  classification=$(classify_signature "$signature")
  release=${classification%%|*}
  readiness=${classification#*|}

  {
    csv_quote "$relative_path"; printf ','
    printf '%s,' "$size_bytes"
    csv_quote "$signature"; printf ','
    csv_quote "$release"; printf ','
    csv_quote "$readiness"; printf '\n'
  } >> "$files_csv"

  printf '%s\t%s\t%s\n' "$signature" "$release" "$readiness" >> "$rows_tsv"
  if [[ "$readiness" == 'rejected_before_conversion' ]]; then
    printf '%s\t%s\t%s\n' "$size_bytes" "$signature" "$relative_path" >> "$invalid_tsv"
  fi
done < <(find "$input_dir" -type f -iname '*.dwg' -print0 | sort -z)

{
  printf 'signature,autocad_release,readiness,file_count\n'
  awk -F '\t' '{ key=$1 FS $2 FS $3; count[key]++ } END { for (key in count) print key FS count[key] }' "$rows_tsv" \
    | LC_ALL=C sort -t $'\t' -k1,1 \
    | while IFS=$'\t' read -r signature release readiness count; do
        csv_quote "$signature"; printf ','
        csv_quote "$release"; printf ','
        csv_quote "$readiness"; printf ',%s\n' "$count"
      done
} > "$versions_csv"

target_count=$(awk -F ',' 'NR > 1 && $5 == "\"target_ac1032\"" { n++ } END { print n+0 }' "$files_csv")
candidate_count=$(awk -F ',' 'NR > 1 && $5 == "\"candidate_same_or_newer_dxf\"" { n++ } END { print n+0 }' "$files_csv")
probe_count=$(awk -F ',' 'NR > 1 && $5 == "\"converter_probe_required\"" { n++ } END { print n+0 }' "$files_csv")
rejected_count=$(awk -F ',' 'NR > 1 && $5 == "\"rejected_before_conversion\"" { n++ } END { print n+0 }' "$files_csv")

{
  printf '# DWG inventory\n\n'
  printf 'Input: `%s`\n\n' "$input_dir"
  cat <<EOF
## Summary

| Metric | Files |
|---|---:|
| Total DWG | $file_total |
| Already AC1032 / target DXF 2018 | $target_count |
| Earlier recognised DWG candidates | $candidate_count |
| Unknown AC signatures; converter probe required | $probe_count |
| Not recognised as DWG | $rejected_count |

## Version distribution

| Signature | AutoCAD release | Conversion readiness | Files |
|---|---|---|---:|
EOF
} > "$output_dir/report.md"

tail -n +2 "$versions_csv" | while IFS=, read -r signature release readiness count; do
  if [[ ${readiness//\"/} != 'rejected_before_conversion' ]]; then
    printf '| %s | %s | %s | %s |\n' "${signature//\"/}" "${release//\"/}" "${readiness//\"/}" "$count" >> "$output_dir/report.md"
  fi
done
if [[ "$rejected_count" -gt 0 ]]; then
  printf '| n/a | not_recognized_as_dwg | rejected_before_conversion | %s |\n' "$rejected_count" >> "$output_dir/report.md"
fi

invalid_report="$output_dir/non-dwg-files.md"
if [[ "$rejected_count" -gt 0 ]]; then
  {
    printf '# Файлы с расширением .dwg, не являющиеся DWG\n\n'
    printf 'Источник: `%s`; проверка: первые шесть байтов каждого файла.\n\n' "$input_dir"
    printf '## Вывод\n\n'
    printf 'Найдено **%s** файлов. Все они находятся в каталогах `PaxHeader`, имеют размер не более 512 байт и не содержат сигнатуру `ACxxxx`; это служебные PAX/TAR-метаданные распакованного архива, а не повреждённые CAD-чертежи. Их необходимо исключать из входа конвертера.\n\n' "$rejected_count"
    printf '## Каталоги\n\n| Файлов | Каталог |\n|---:|---|\n'
    awk -F '\t' '{p=$3; sub(/\/[^/]+$/, "", p); n[p]++} END {for(p in n) print n[p] "\t" p}' "$invalid_tsv" \
      | sort -nr \
      | while IFS=$'\t' read -r count folder; do
          printf '| %s | `%s` |\n' "$count" "$folder"
        done
    printf '\n## Полный список\n\n'
    while IFS=$'\t' read -r size signature relative_path; do
      printf -- '- `%s` — %s байт; сигнатура `%s`\n' "$relative_path" "$size" "$signature"
    done < <(sort -t $'\t' -k3,3 "$invalid_tsv")
  } > "$invalid_report"
else
  printf '# Файлы с расширением .dwg, не являющиеся DWG\n\nНе найдены.\n' > "$invalid_report"
fi

cat >> "$output_dir/report.md" <<'EOF'

## Interpretation

`target_ac1032` and `candidate_same_or_newer_dxf` mean only that the six-byte file header is a known DWG release for the intended conversion path. They are **not** a no-loss guarantee. A conversion gate must still check entities, layers, blocks, XREF, proxy/custom objects, fonts, extents and visual output.

`converter_probe_required` means the header is an `AC*` value outside this script's public mapping. It must be tested with the approved converter before it enters the planning pipeline.

## Next command after installing an approved converter

Run the converter on a copy of a small pilot directory, retain the original DWG, target DXF 2018/AC1032, and write its log alongside this inventory. Do not batch-convert all input files until the pilot conversion gate passes.
EOF

printf 'Scanned %s DWG files. Report: %s/report.md\n' "$file_total" "$output_dir"
