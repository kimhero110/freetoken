#!/usr/bin/env bash
set -euo pipefail

DEPLOY_USER=freetoken-deploy
PUBLIC_KEY_FILE=/tmp/freetoken-deploy.pub
DEPLOY_SCRIPT_FILE=/tmp/deploy-freetoken.new

bash -n "$DEPLOY_SCRIPT_FILE"
id "$DEPLOY_USER" >/dev/null 2>&1 || useradd --create-home --shell /bin/bash "$DEPLOY_USER"
ssh_stage=$(mktemp -d)
sed 's/^/restrict /' "$PUBLIC_KEY_FILE" > "$ssh_stage/authorized_keys"
chown -R "$DEPLOY_USER:$DEPLOY_USER" "$ssh_stage"
chmod 700 "$ssh_stage"
chmod 600 "$ssh_stage/authorized_keys"
rm -rf -- "/home/$DEPLOY_USER/.ssh"
mv "$ssh_stage" "/home/$DEPLOY_USER/.ssh"

install -o root -g root -m 755 "$DEPLOY_SCRIPT_FILE" /usr/local/sbin/deploy-freetoken
printf '%s\n' 'freetoken-deploy ALL=(root) NOPASSWD: /usr/local/sbin/deploy-freetoken' > /tmp/freetoken-deploy.sudoers
chmod 440 /tmp/freetoken-deploy.sudoers
visudo -cf /tmp/freetoken-deploy.sudoers
install -o root -g root -m 440 /tmp/freetoken-deploy.sudoers /etc/sudoers.d/freetoken-deploy

rm -f "$PUBLIC_KEY_FILE" "$DEPLOY_SCRIPT_FILE" /tmp/freetoken-deploy.sudoers
id "$DEPLOY_USER"
sudo -l -U "$DEPLOY_USER"
