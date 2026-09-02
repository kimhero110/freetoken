import os
import sys
import tarfile
import tempfile
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST_DIR = ROOT / 'site' / 'dist'
SSH_KEY = Path.home() / '.ssh' / 'freetokenlab'
SERVER_IP = '124.221.254.56'
SERVER_USER = 'root'
REMOTE_DIR = '/var/www/freetoken-public'

def sync():
    if not DIST_DIR.exists():
        print(f'Error: {DIST_DIR} not found. Please build site first.')
        return 1
    if not SSH_KEY.exists():
        print(f'Error: SSH key not found at {SSH_KEY}')
        return 1

    temp_tar = tempfile.NamedTemporaryFile(suffix='.tar.gz', delete=False)
    temp_tar_path = temp_tar.name
    temp_tar.close()

    try:
        with tarfile.open(temp_tar_path, 'w:gz') as tar:
            tar.add(str(DIST_DIR), arcname='.')
        print('Created tarball. Uploading to Tencent Cloud 124.221.254.56...')

        subprocess.run([
            'scp', '-i', str(SSH_KEY), '-o', 'StrictHostKeyChecking=no',
            temp_tar_path, f'{SERVER_USER}@{SERVER_IP}:/tmp/site_dist.tar.gz'
        ], check=True)

        remote_cmds = (
            f'mkdir -p {REMOTE_DIR} && '
            f'tar -xzf /tmp/site_dist.tar.gz -C {REMOTE_DIR} && '
            f'rm -f /tmp/site_dist.tar.gz && '
            f'docker restart freetoken-nginx'
        )
        subprocess.run([
            'ssh', '-i', str(SSH_KEY), '-o', 'StrictHostKeyChecking=no',
            f'{SERVER_USER}@{SERVER_IP}', remote_cmds
        ], check=True)
        print('Successfully synchronized with Tencent Cloud server (witkit.zone)!')
        return 0
    finally:
        if os.path.exists(temp_tar_path):
            os.remove(temp_tar_path)

if __name__ == '__main__':
    sys.exit(sync())
