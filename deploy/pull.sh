#!/usr/bin/env bash
# 服务器端拉取脚本：从 GitHub 的 deploy 分支拉取构建产物到 Nginx web 根目录
#
# 首次部署：
#   git clone --branch deploy --single-branch https://github.com/kimhero110/freetoken.git /var/www/freetoken
#
# 定时任务（crontab -e），每 10 分钟检查一次更新：
#   */10 * * * * /opt/freetoken/pull.sh >> /var/log/freetoken-pull.log 2>&1

set -euo pipefail

WEB_ROOT="/var/www/freetoken"

cd "$WEB_ROOT"

# 获取远端最新提交哈希；无变化则直接退出
git fetch origin deploy
LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse origin/deploy)

if [ "$LOCAL" = "$REMOTE" ]; then
  echo "[$(date '+%F %T')] 无更新 ($LOCAL)"
  exit 0
fi

git reset --hard origin/deploy
echo "[$(date '+%F %T')] 已更新 $LOCAL -> $REMOTE"
