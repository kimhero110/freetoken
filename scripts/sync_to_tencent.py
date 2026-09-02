# -*- coding: utf-8 -*-
"""
Tencent Cloud Sync with Permanent ICP Filing Injection (Overwrite-Proof)
------------------------------------------------------------------------
- Ensures ALL HTML files on Tencent Cloud (witkit.zone) contain:
  <a href="https://beian.miit.gov.cn/" target="_blank" rel="noopener">苏ICP备2026003689号-2</a>
- Fully visible in raw static HTML for MIIT & Tencent compliance crawlers.
"""

import os
import sys
import re
import tarfile
import tempfile
import subprocess
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST_DIR = ROOT / 'site' / 'dist'
SSH_KEY = Path.home() / '.ssh' / 'freetokenlab'
SERVER_IP = '124.221.254.56'
SERVER_USER = 'root'
REMOTE_DIR = '/var/www/freetoken-public'

# 工信部 ICP 备案号及跳转官网标准配置
ICP_NUMBER = "苏ICP备2026003689号-2"
ICP_URL = "https://beian.miit.gov.cn/"
ICP_TAG = (
    f'<span class="icp-sep" style="margin: 0 6px; opacity: 0.4;">|</span>'
    f'<a href="{ICP_URL}" target="_blank" rel="noopener" class="icp-filing-link" '
    f'style="color: inherit; text-decoration: underline;">{ICP_NUMBER}</a>'
)


def inject_icp_into_dist(target_dir: Path) -> int:
    """遍历待上传的 HTML 文件，全量注入 ICP 备案信息并确保静态 HTML 100% 显式可见"""
    injected_count = 0
    for html_path in target_dir.glob('**/*.html'):
        raw_text = html_path.read_text(encoding='utf-8')
        
        # 1. 如果已有占位 slot，直接解除隐藏
        if 'id="footer-icp-slot"' in raw_text:
            raw_text = raw_text.replace('id="footer-icp-slot" style="display: none;"', 'id="footer-icp-slot" style="display: inline;"')
            raw_text = raw_text.replace('id="footer-icp-slot" style="display:none;"', 'id="footer-icp-slot" style="display: inline;"')
            html_path.write_text(raw_text, encoding='utf-8')
            injected_count += 1
        elif ICP_NUMBER not in raw_text:
            if '© 2026 FreeTokens.info' in raw_text:
                raw_text = re.sub(
                    r'(© 2026 FreeTokens\.info[^<]*)',
                    r'\1 ' + ICP_TAG,
                    raw_text,
                    count=1
                )
            elif '</footer>' in raw_text:
                raw_text = raw_text.replace(
                    '</footer>',
                    f'<div style="text-align: center; font-size: 12px; padding: 10px 0; background: #f4f3ef; border-top: 1px solid #e7e5e0;">{ICP_TAG}</div></footer>'
                )
            else:
                raw_text = raw_text.replace('</body>', f'<div style="text-align:center;padding:10px;">{ICP_TAG}</div></body>')
            html_path.write_text(raw_text, encoding='utf-8')
            injected_count += 1

    return injected_count


def sync():
    if not DIST_DIR.exists():
        print(f"[ERROR] {DIST_DIR} not found. Please run 'npm run build' inside site/ first.")
        return 1
    if not SSH_KEY.exists():
        print(f"[ERROR] SSH key not found at {SSH_KEY}")
        return 1

    temp_deploy_dir = tempfile.mkdtemp()
    temp_tar_path = os.path.join(tempfile.gettempdir(), 'tencent_site_dist.tar.gz')

    try:
        # 1. 复制一份干净的构建产物
        shutil.copytree(str(DIST_DIR), os.path.join(temp_deploy_dir, 'dist'))
        tencent_dist = Path(temp_deploy_dir) / 'dist'

        # 2. 注入腾讯云专属 ICP 备案信息
        count = inject_icp_into_dist(tencent_dist)
        print(f"[ICP PIPELINE] Successfully injected & displayed '{ICP_NUMBER}' across {count} HTML pages.")

        # 3. 打包压缩
        with tarfile.open(temp_tar_path, 'w:gz') as tar:
            tar.add(str(tencent_dist), arcname='.')
        print(f"[SYNC] Uploading tarball to Tencent Cloud ({SERVER_IP})...")

        # 4. 上传至临时目录
        subprocess.run([
            'scp', '-i', str(SSH_KEY), '-o', 'StrictHostKeyChecking=no',
            temp_tar_path, f'{SERVER_USER}@{SERVER_IP}:/tmp/site_dist.tar.gz'
        ], check=True)

        # 5. 解压并重启 Nginx
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
        print(f"[SUCCESS] Tencent Cloud ({SERVER_IP} / witkit.zone) 100% synchronized with ICP: {ICP_NUMBER}!")
        return 0
    finally:
        shutil.rmtree(temp_deploy_dir, ignore_errors=True)
        if os.path.exists(temp_tar_path):
            os.remove(temp_tar_path)


if __name__ == '__main__':
    sys.exit(sync())
