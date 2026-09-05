#!/usr/bin/env bash
set -euo pipefail
trap 'status=$?; echo "deployment failed at line ${LINENO} (status ${status})" >&2' ERR

REMOTE_DIR=/var/www/freetoken-public
COMPOSE_FILE=/root/verdaccio/docker-compose.yml
SERVICE=freetoken-nginx
WORK_DIR=/var/www/.freetoken-releases

archive=${1:-}
release_id=${2:-}
if [[ ! "$release_id" =~ ^[0-9]{14}-[a-f0-9]{12}$ ]] || [[ "$archive" != "/tmp/freetoken-${release_id}.tar.gz" ]]; then
  echo "invalid deployment arguments" >&2
  exit 2
fi
if [[ ! -f "$archive" || -L "$archive" || "$(stat -c %U "$archive")" != "freetoken-deploy" ]]; then
  echo "deployment archive must be a regular file owned by freetoken-deploy" >&2
  exit 2
fi
MAX_ARCHIVE_BYTES=$((256 * 1024 * 1024))
archive_size=$(stat -c %s "$archive")
if (( archive_size > MAX_ARCHIVE_BYTES )); then
  echo "deployment archive exceeds ${MAX_ARCHIVE_BYTES} bytes: ${archive_size}" >&2
  exit 2
fi

mkdir -p "$WORK_DIR"
exec 9>"$WORK_DIR/deploy.lock"
flock -n 9 || { echo "another deployment is running" >&2; exit 3; }

incoming="$WORK_DIR/incoming-${release_id}.tar.gz"
next_dir="$WORK_DIR/next-${release_id}"
previous_dir="$WORK_DIR/previous-${release_id}"
mv -- "$archive" "$incoming"
chown root:root "$incoming"
trap 'rm -rf -- "$incoming" "$next_dir"' EXIT

python3 - "$incoming" <<'PY'
import sys
import tarfile
from pathlib import PurePosixPath

MAX_MEMBERS = 30000
MAX_TOTAL_BYTES = 1024 ** 3
MAX_MEMBER_BYTES = 64 * 1024 * 1024

with tarfile.open(sys.argv[1], "r:gz") as archive:
    members = archive.getmembers()
    if len(members) > MAX_MEMBERS:
        raise SystemExit(f"archive member count exceeds {MAX_MEMBERS}")
    total = 0
    for member in members:
        path = PurePosixPath(member.name)
        if path.is_absolute() or ".." in path.parts or not (member.isfile() or member.isdir()):
            raise SystemExit(f"unsafe archive member: {member.name}")
        if member.isfile():
            if member.size > MAX_MEMBER_BYTES:
                raise SystemExit(f"archive member exceeds size limit: {member.name}")
            total += member.size
    if total > MAX_TOTAL_BYTES:
        raise SystemExit(f"archive expanded size exceeds {MAX_TOTAL_BYTES} bytes")
PY

mkdir "$next_dir"
tar --extract --gzip --file "$incoming" --directory "$next_dir" --no-same-owner --no-same-permissions
[[ -f "$next_dir/index.html" ]]
# Artifact downloads can preserve a private 0700 root directory. Normalize the
# static tree before nginx reads it through the bind mount.
find "$next_dir" -type d -exec chmod 755 {} +
find "$next_dir" -type f -exec chmod 644 {} +
actual_release=$(cat "$next_dir/release-id.txt" 2>/dev/null || true)
if [[ "$actual_release" != "$release_id" ]]; then
  printf 'release marker mismatch: expected %q, got %q\n' "$release_id" "$actual_release" >&2
  exit 1
fi

if [[ -d "$REMOTE_DIR" ]]; then
  mv "$REMOTE_DIR" "$previous_dir"
fi
mv "$next_dir" "$REMOTE_DIR"

rollback() {
  rm -rf -- "$REMOTE_DIR"
  if [[ -d "$previous_dir" ]]; then
    mv "$previous_dir" "$REMOTE_DIR"
  fi
  docker compose -f "$COMPOSE_FILE" up -d --force-recreate "$SERVICE" || true
}

if ! docker compose -f "$COMPOSE_FILE" up -d --force-recreate "$SERVICE"; then
  rollback
  exit 1
fi
sleep 2
if ! docker exec "$SERVICE" nginx -t \
  || [[ "$(docker inspect -f '{{.State.Running}}' "$SERVICE")" != true ]] \
  || [[ "$(docker exec "$SERVICE" wget -q -O - http://127.0.0.1/release-id.txt)" != "$release_id" ]]; then
  rollback
  exit 1
fi

# 保留最新两个回滚快照，清理更早的历史发布
ls -1dt "$WORK_DIR"/previous-* 2>/dev/null | tail -n +3 | while IFS= read -r old_release; do
  rm -rf -- "$old_release"
done
echo "deployed release $release_id"
