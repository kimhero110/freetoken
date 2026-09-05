#!/usr/bin/env python3
"""微信公众号草稿箱全自动推送引擎 (WeChat Drafts Auto-Publisher)
借鉴 baoyu-skills 工作流设计：
1. 自动鉴权：获取微信官方 access_token
2. 素材管理：自动上传文章封面头图，获取 thumb_media_id
3. 正文清洗与图床：将正文中的本地/相对图片自动上传到微信图床 CDN
4. 草稿投递：调用 /cgi-bin/draft/add 将富文本推送到公众号草稿箱
"""

import json
import os
import re
import sys
from datetime import date
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT / "output"
ARTICLE_FILE = OUTPUT_DIR / "wechat_article.html"
QR_IMAGE_FILE = ROOT / "site" / "public" / "wechat-qrcode.jpg"
CACHE_DIR = ROOT / ".cache"
COVER_MEDIA_CACHE = CACHE_DIR / "wechat_cover_media_id.json"


def load_platform_count() -> int:
    """从正式编译数据读取平台数量，避免文案中的硬编码计数漂移。"""
    platforms = json.loads((ROOT / "data" / "platforms.json").read_text(encoding="utf-8"))
    return len(platforms)


def load_cached_cover_media_id() -> str:
    """复用已上传的永久封面素材，避免每次推送都消耗素材额度。"""
    try:
        data = json.loads(COVER_MEDIA_CACHE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    media_id = data.get("thumb_media_id", "")
    return media_id.strip() if isinstance(media_id, str) else ""


def save_cover_media_id(media_id: str) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    COVER_MEDIA_CACHE.write_text(
        json.dumps({"thumb_media_id": media_id}, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def get_wechat_credentials() -> tuple[str, str]:
    """从环境变量获取微信 AppID 和 AppSecret"""
    app_id = os.environ.get("WECHAT_APP_ID", "").strip()
    app_secret = os.environ.get("WECHAT_APP_SECRET", "").strip()
    return app_id, app_secret


def get_access_token(app_id: str, app_secret: str) -> str:
    """向微信 API 换取全局唯一接口调用凭据 access_token"""
    url = f"https://api.weixin.qq.com/cgi-bin/token?grant_type=client_credential&appid={app_id}&secret={app_secret}"
    resp = requests.get(url, timeout=15)
    data = resp.json()

    if "access_token" in data:
        return data["access_token"]

    err_code = data.get("errcode")
    err_msg = data.get("errmsg")
    if err_code == 40164:
        raise RuntimeError(
            f"微信接口报错: IP 不在白名单中 (40164)。\n"
            f"详细信息: {err_msg}\n"
            f"请登录微信公众平台 ->「设置与开发」->「基本配置」->「IP白名单」中添加当前机器的公网 IP！"
        )
    raise RuntimeError(f"获取微信 access_token 失败 [{err_code}]: {err_msg}")


def upload_permanent_image(access_token: str, image_path: Path) -> str:
    """上传永久图片素材，获取 thumb_media_id (用作文章封面图)"""
    url = f"https://api.weixin.qq.com/cgi-bin/material/add_material?access_token={access_token}&type=image"
    if not image_path.exists():
        raise FileNotFoundError(f"封面图文件不存在: {image_path}")

    with open(image_path, "rb") as f:
        files = {"media": (image_path.name, f, "image/jpeg")}
        resp = requests.post(url, files=files, timeout=30)
        data = resp.json()

    if "media_id" in data:
        return data["media_id"]
    raise RuntimeError(f"上传封面素材失败: {data}")


def upload_news_image(access_token: str, image_path: Path) -> str:
    """上传正文内部图片到微信 CDN，返回微信可直接引用的 cdn url"""
    url = f"https://api.weixin.qq.com/cgi-bin/media/uploadimg?access_token={access_token}"
    with open(image_path, "rb") as f:
        files = {"media": (image_path.name, f, "image/jpeg")}
        resp = requests.post(url, files=files, timeout=30)
        data = resp.json()

    if "url" in data:
        return data["url"]
    print(f"Warning: 上传正文图片失败，使用原始路径: {data}")
    return ""


def push_draft_article(
    access_token: str,
    title: str,
    author: str,
    digest: str,
    content_html: str,
    thumb_media_id: str,
    source_url: str = "https://freetokens.info",
) -> str:
    """调用微信官方草稿箱接口新增草稿"""
    url = f"https://api.weixin.qq.com/cgi-bin/draft/add?access_token={access_token}"

    article_payload = {
        "articles": [
            {
                "title": title,
                "author": author,
                "digest": digest,
                "content": content_html,
                "content_source_url": source_url,
                "thumb_media_id": thumb_media_id,
                "need_open_comment": 1,
                "only_fans_can_comment": 0,
            }
        ]
    }

    # 微信接口要求 utf-8 且不能带有未转义的 unicode 乱码
    req_data = json.dumps(article_payload, ensure_ascii=False).encode("utf-8")
    resp = requests.post(
        url,
        data=req_data,
        headers={"Content-Type": "application/json; charset=utf-8"},
        timeout=30,
    )
    data = resp.json()

    if "media_id" in data:
        return data["media_id"]
    raise RuntimeError(f"推送微信草稿箱失败: {data}")


def main() -> int:
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8")

    print("========================================")
    print("🚀 启动微信公众号草稿箱一键直推引擎")
    print("========================================")

    # 1. 检查环境变量
    app_id, app_secret = get_wechat_credentials()
    if not app_id or not app_secret:
        print("\n❌ 未检测到微信开发者凭据 WECHAT_APP_ID 或 WECHAT_APP_SECRET！")
        print("\n📖 配置教程：")
        print("1. 打开微信公众平台后台 (https://mp.weixin.qq.com/)；")
        print("2. 点击左侧「设置与开发」->「基本配置」；")
        print("3. 获取 AppID 和 AppSecret，并配置当前执行 IP 到「IP白名单」；")
        print("4. 在终端运行：")
        print('   export WECHAT_APP_ID="你的AppID"')
        print('   export WECHAT_APP_SECRET="你的AppSecret"')
        print("   python scripts/push_to_wechat.py\n")
        return 1

    # 2. 检查待推送文章 HTML
    if not ARTICLE_FILE.exists():
        print("[工坊生成] 正在重新生成最新图文排版...")
        from generate_content import load_platforms, generate_wechat_article
        platforms = load_platforms()
        html_content = generate_wechat_article(platforms)
        ARTICLE_FILE.write_text(html_content, encoding="utf-8")
    else:
        html_content = ARTICLE_FILE.read_text(encoding="utf-8")

    try:
        # 3. 获取 Access Token
        print("[1/4] 正在鉴权获取微信 Access Token...")
        token = get_access_token(app_id, app_secret)
        print("  ✓ Access Token 获取成功！")

        # 4. 上传正文图片到微信图床（替换本地 /wechat-qrcode.jpg 路径）
        if QR_IMAGE_FILE.exists():
            print("[2/4] 正在上传公众号二维码至微信 CDN 图床...")
            cdn_url = upload_news_image(token, QR_IMAGE_FILE)
            if cdn_url:
                html_content = html_content.replace('src="/wechat-qrcode.jpg"', f'src="{cdn_url}"')
                print("  ✓ 正文图片已自动替换为微信 CDN 链接！")

        # 5. 上传文章封面头图（优先复用已缓存的永久素材）
        thumb_media_id = load_cached_cover_media_id()
        if thumb_media_id:
            print(f"  ✓ 复用已上传封面素材! Media ID: {thumb_media_id}")
        else:
            print("[3/4] 正在上传文章封面头图素材...")
            thumb_media_id = upload_permanent_image(token, QR_IMAGE_FILE)
            save_cover_media_id(thumb_media_id)
            print(f"  ✓ 封面素材上传并缓存成功! Media ID: {thumb_media_id}")

        # 6. 推送至草稿箱（计数从正式数据动态生成）
        platforms_count = load_platform_count()
        today_str = date.today().strftime("%m月%d日")
        title = f"零成本玩转大模型！全网 {platforms_count} 家免费 API Token 白嫖清单 ({today_str}更新)"
        author = "免费Token情报局"
        digest = f"全网精选 {platforms_count} 家大厂与新兴 GPU 算力云免费额度，附 10 秒快速接入代码！"

        print("[4/4] 正在将文章推送到公众号草稿箱 (Drafts)...")
        draft_media_id = push_draft_article(
            access_token=token,
            title=title,
            author=author,
            digest=digest,
            content_html=html_content,
            thumb_media_id=thumb_media_id,
            source_url="https://freetokens.info",
        )

        print("\n========================================")
        print("🎉🎉🎉 恭喜！文章已成功推送到微信公众号草稿箱！")
        print(f"📄 草稿 Media ID: {draft_media_id}")
        print("📱 手机打开【订阅号助手 App】或登录电脑后台，点击「草稿箱」即可一键群发！")
        print("========================================\n")
        return 0

    except Exception as exc:
        print(f"\n❌ 推送失败: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())

