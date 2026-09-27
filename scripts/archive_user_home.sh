#!/usr/bin/env bash
# Create a complete, file-level archive of one local user's home directory.
# Unlike an ext4 image, this stores no free filesystem blocks.
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: sudo scripts/archive_user_home.sh FULL_TARGET_DIRECTORY [USERNAME]

Creates:
  FULL_TARGET_DIRECTORY/USERNAME-home-YYYYMMDD-HHMMSS.tar
  FULL_TARGET_DIRECTORY/USERNAME-home-YYYYMMDD-HHMMSS.tar.sha256

The archive contains all readable files below /home/USERNAME on its current
filesystem, including ACLs, extended attributes, numeric ownership and sparse
files. It does not include unused filesystem space. Unix sockets are skipped
because they are live IPC endpoints, not persistent data.
EOF
}

if [[ ${1:-} == '-h' || ${1:-} == '--help' ]]; then
  usage
  exit 0
fi

target_dir=${1:?Full target directory is required}
username=${2:-sol}
source_dir="/home/$username"

if [[ ${EUID} -ne 0 ]]; then
  printf 'Run through sudo: sudo %s FULL_TARGET_DIRECTORY [USERNAME]\n' "$0" >&2
  exit 2
fi
if [[ ! "$username" =~ ^[a-z_][a-z0-9_-]*$ ]]; then
  printf 'Invalid local username: %s\n' "$username" >&2
  exit 2
fi
if [[ ! -d "$source_dir" ]]; then
  printf 'Source directory does not exist: %s\n' "$source_dir" >&2
  exit 2
fi

target_dir=$(realpath -m "$target_dir")
mount_dir=$(findmnt -nro TARGET -T "$target_dir" || true)
if [[ -z "$mount_dir" ]]; then
  printf 'Cannot determine mount for target: %s\n' "$target_dir" >&2
  exit 2
fi
mount_dir=$(realpath -m "$mount_dir")
if [[ "$target_dir" == "$mount_dir" || "$target_dir" != "$mount_dir"/* ]]; then
  printf 'Target must be a subdirectory of its mount, not the mount root: %s\n' "$target_dir" >&2
  exit 2
fi
if [[ $(findmnt -nro TARGET -T "$mount_dir") == '/home' ]]; then
  printf 'Refusing to archive onto /home: %s\n' "$mount_dir" >&2
  exit 2
fi

filesystem=$(findmnt -nro FSTYPE -T "$mount_dir")
if [[ "$filesystem" == 'vfat' ]]; then
  printf 'FAT32/vfat cannot hold the expected >4 GiB tar archive.\n' >&2
  exit 2
fi

source_bytes=$(du -sxB1 "$source_dir" | awk '{print $1}')
available_bytes=$(df -PB1 "$mount_dir" | awk 'NR==2 {print $4}')
reserve_bytes=$((1024 * 1024 * 1024))
if (( available_bytes < source_bytes + reserve_bytes )); then
  printf 'Not enough free space: need at least %s bytes including reserve, have %s bytes.\n' \
    "$((source_bytes + reserve_bytes))" "$available_bytes" >&2
  exit 2
fi

mkdir -p "$target_dir"
stamp=$(date +%Y%m%d-%H%M%S)
archive="$target_dir/$username-home-$stamp.tar"

printf 'Source: %s (%s bytes)\nTarget: %s\nFilesystem: %s\n' \
  "$source_dir" "$source_bytes" "$archive" "$filesystem"

tar --create --file="$archive" --xattrs --acls --numeric-owner --sparse --one-file-system \
  --directory=/home "$username"
tar --list --file="$archive" >/dev/null
sha256sum "$archive" | tee "$archive.sha256"
printf 'Archive verified. Source has NOT been deleted.\n'
