#!/usr/bin/env python3
"""
Lunes Host 自动登录并获取服务器状态
使用 Playwright + 企业微信机器人
"""
import os
import time
import base64
import requests
from datetime import datetime
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

def send_wecom_message(webhook_key, message, image_base64=None):
    """
    发送企业微信消息
    支持 markdown 文本和可选的图片
    """
    if not webhook_key:
        print("警告: 未设置企业微信 Webhook Key")
        return False
   
    webhook_url = f"https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={webhook_key}"
   
    try:
        # 先发送文字消息
        data = {
            "msgtype": "markdown",
            "markdown": {
                "content": message
            }
        }
        response = requests.post(webhook_url, json=data, timeout=10)
        result = response.json()
       
        if result.get("errcode") != 0:
            print(f"企业微信发送失败: {result}")
            return False
       
        # 如果有图片，再发送图片
        if image_base64:
            # 企业微信图片需要先上传获取 media_id，这里简化使用图片链接或 base64
            # 实际上传限制较多，建议先保存文件再发送，或直接使用 markdown 中的图片链接
            pass
           
        print(f"企业微信通知发送成功")
        return True
       
    except Exception as e:
        print(f"企业微信通知失败: {e}")
        return False

def send_wecom_image(webhook_key, image_path):
    """发送图片到企业微信（通过上传临时素材）"""
    if not webhook_key or not os.path.exists(image_path):
        return False
   
    webhook_url = f"https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={webhook_key}"
   
    try:
        with open(image_path, "rb") as f:
            image_data = f.read()
       
        # 企业微信机器人发送图片需要用 base64 + md5
        import hashlib
        image_base64 = base64.b64encode(image_data).decode('utf-8')
        image_md5 = hashlib.md5(image_data).hexdigest()
       
        data = {
            "msgtype": "image",
            "image": {
                "base64": image_base64,
                "md5": image_md5
            }
        }
       
        response = requests.post(webhook_url, json=data, timeout=10)
        result = response.json()
       
        if result.get("errcode") == 0:
            print(f"图片发送成功: {image_path}")
            return True
        else:
            print(f"图片发送失败: {result}")
            return False
           
    except Exception as e:
        print(f"发送图片失败: {e}")
        return False

def take_screenshot(page, filename):
    """截图并保存"""
    screenshot_path = f"/tmp/{filename}"
    page.screenshot(path=screenshot_path, full_page=True)
    print(f"截图已保存: {screenshot_path}")
    return screenshot_path

def extract_server_stats(page):
    """提取服务器详情页的统计信息"""
    stats = {}
   
    try:
        # 等待页面加载完成
        page.wait_for_selector("text=Uptime", timeout=10000)
       
        # 提取各项数据
        selectors = {
            "address": "text=node22.lunes.host:3098",
            "uptime": "text=Uptime >> .. >> div[class*='text']",
            "cpu_load": "text=CPU Load >> .. >> div[class*='text']",
            "memory": "text=Memory >> .. >> div[class*='text']",
            "disk": "text=Disk >> .. >> div[class*='text']",
            "network_in": "text=Network (Inbound) >> .. >> div[class*='text']",
            "network_out": "text=Network (Outbound) >> .. >> div[class*='text']"
        }
       
        # 使用更可靠的方式提取
        # Address
        address_el = page.locator("div:has-text('Address') + div, div:has-text('Address') ~ div").first
        if address_el.is_visible():
            stats["address"] = address_el.inner_text().strip()
       
        # 提取所有统计卡片
        cards = page.locator("div.grid > div, .stats-card, [class*='bg-gray-800']").all()
       
        for card in cards:
            text = card.inner_text()
            if "Uptime" in text:
                stats["uptime"] = text.replace("Uptime", "").strip()
            elif "CPU Load" in text:
                stats["cpu_load"] = text.replace("CPU Load", "").strip()
            elif "Memory" in text and "Network" not in text:
                stats["memory"] = text.replace("Memory", "").strip()
            elif "Disk" in text:
                stats["disk"] = text.replace("Disk", "").strip()
            elif "Network (Inbound)" in text:
                stats["network_in"] = text.replace("Network (Inbound)", "").strip()
            elif "Network (Outbound)" in text:
                stats["network_out"] = text.replace("Network (Outbound)", "").strip()
       
        # 备用方案：直接解析 HTML 文本
        if not stats:
            page_text = page.inner_text("body")
            lines = [l.strip() for l in page_text.split("\n") if l.strip()]
           
            for i, line in enumerate(lines):
                if "node22.lunes.host" in line:
                    stats["address"] = line
                elif line == "Uptime" and i + 1 < len(lines):
                    stats["uptime"] = lines[i + 1]
                elif line == "CPU Load" and i + 1 < len(lines):
                    stats["cpu_load"] = lines[i + 1]
                elif line == "Memory" and i + 1 < len(lines):
                    stats["memory"] = lines[i + 1]
                elif line == "Disk" and i + 1 < len(lines):
                    stats["disk"] = lines[i + 1]
                elif "Network (Inbound)" in line and i + 1 < len(lines):
                    stats["network_in"] = lines[i + 1]
                elif "Network (Outbound)" in line and i + 1 < len(lines):
                    stats["network_out"] = lines[i + 1]
       
    except Exception as e:
        print(f"提取统计信息失败: {e}")
        stats["error"] = str(e)
   
    return stats

def format_stats_message(stats):
    """格式化统计信息为 markdown"""
    msg = "**🖥️ 服务器状态监控**\n\n"
    msg += f"> **📍 地址**: {stats.get('address', 'N/A')}\n"
    msg += f"> **⏱️ 运行时间**: {stats.get('uptime', 'N/A')}\n"
    msg += f"> **💻 CPU 负载**: {stats.get('cpu_load', 'N/A')}\n"
    msg += f"> **🧠 内存使用**: {stats.get('memory', 'N/A')}\n"
    msg += f"> **💾 磁盘使用**: {stats.get('disk', 'N/A')}\n"
    msg += f"> **📥 网络入站**: {stats.get('network_in', 'N/A')}\n"
    msg += f"> **📤 网络出站**: {stats.get('network_out', 'N/A')}\n"
    msg += f"\n⏰ 更新时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    return msg

def run_automation():
    """主自动化流程"""
    # 从环境变量读取配置
    config = {
        "website_url": os.getenv("WEBSITE_URL", "https://ctrl.lunes.host/auth/login"),
        "username": os.getenv("LOGIN_EMAIL") or os.getenv("USERNAME"),
        "password": os.getenv("LOGIN_PASSWORD") or os.getenv("PASSWORD"),
        "wecom_key": os.getenv("WECHAT_WEBHOOK_KEY") or os.getenv("WECOM_WEBHOOK_KEY"),
    }
   
    if not all([config["username"], config["password"], config["wecom_key"]]):
        raise Exception("缺少必要的环境变量: LOGIN_EMAIL, LOGIN_PASSWORD, WECHAT_WEBHOOK_KEY")
   
    print(f"开始自动化任务: {config['website_url']}")
    print(f"用户名: {config['username']}")
   
    with sync_playwright() as p:
        # 启动浏览器
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--window-size=1920,1080"
            ]
        )
       
        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
       
        page = context.new_page()
       
        try:
            # ========== 第 1 步: 访问登录页 ==========
            print("正在访问登录页面...")
            page.goto(config["website_url"], wait_until="networkidle", timeout=30000)
           
            # 等待登录表单加载
            page.wait_for_selector("input[name='username']", timeout=10000)
           
            # ========== 第 2 步: 填写表单 ==========
            print("填写登录信息...")
            page.fill("input[name='username']", config["username"])
            page.fill("input[name='password']", config["password"])
           
            # 截图：填写完成
            login_filled_screenshot = take_screenshot(page, "login_filled.png")
           
            # ========== 第 3 步: 点击登录 ==========
            print("尝试点击登录按钮（使用文本匹配）...")
            try:
                page.get_by_role("button", name="Login", exact=False).click(timeout=10000)
                print("成功点击 'Login' 按钮")
            except Exception as e:
                print(f"使用 get_by_role 失败: {e}")
                # 降级方案
                page.locator("button:has-text('Login')").click(timeout=10000)
           
            # 点击后立即截图（看是否有错误提示）
            time.sleep(1)
            click_after_screenshot = take_screenshot(page, "after_click_login.png")
            send_wecom_image(config["wecom_key"], click_after_screenshot)
           
            # 等待登录完成（通过 URL 变化或特定元素判断）
            page.wait_for_load_state("networkidle", timeout=20000)
            time.sleep(2.5)
           
            # 验证登录成功（改进判断）
            if "/auth/login" not in page.url.lower() and "/login" not in page.url.lower():
                print(f"URL 已跳转: {page.url} → 判定登录成功")
            else:
                # 判断方式2：看是否出现 dashboard 特征（比如有 "webapphost" 文字）
                if page.locator("text=webapphost").count() > 0:
                    print("找到 'webapphost' 文字 → 判定已登录")
                else:
                    # 失败，截图
                    error_screenshot = take_screenshot(page, "login_failed_detailed.png")
                    send_wecom_image(config["wecom_key"], error_screenshot)
                    raise Exception(f"登录疑似失败，当前URL仍含login且无dashboard特征: {page.url}")
           
            print(f"登录成功，当前 URL: {page.url}")
           
            # 截图：登录成功首页
            dashboard_screenshot = take_screenshot(page, "dashboard.png")
            send_wecom_image(config["wecom_key"], dashboard_screenshot)
           
            # 发送登录成功通知
            success_msg = f"""**✅ 登录成功！**
> 时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
> 用户: {config['username']}
> 页面: {page.url}"""
            send_wecom_message(config["wecom_key"], success_msg)
           
            # ========== 第 4 步: 点击 webapphost ==========
            print("查找 webapphost...")
           
            # 等待服务器列表加载
            page.wait_for_selector("text=webapphost", timeout=10000)
           
            # 点击 webapphost（使用更精确的选择器）
            webapphost_link = page.locator("text=webapphost").first
            if not webapphost_link.is_visible():
                raise Exception("未找到 webapphost 链接")
           
            print("点击进入 webapphost...")
            webapphost_link.click()
           
            # 等待页面导航完成
            page.wait_for_load_state("networkidle")
            time.sleep(3) # 等待数据加载
           
            current_url = page.url
            print(f"进入服务器详情页: {current_url}")
           
            # ========== 第 5 步: 截图并提取信息 ==========
            # 截图：服务器详情页
            detail_screenshot = take_screenshot(page, "server_detail.png")
            send_wecom_image(config["wecom_key"], detail_screenshot)
           
            # 提取统计信息
            print("提取服务器统计信息...")
            stats = extract_server_stats(page)
            print(f"提取到的数据: {stats}")
           
            # 发送统计信息
            stats_message = format_stats_message(stats)
            send_wecom_message(config["wecom_key"], stats_message)
           
            print("任务完成！")
           
        except PlaywrightTimeout as e:
            error_screenshot = take_screenshot(page, "error_timeout.png")
            send_wecom_image(config["wecom_key"], error_screenshot)
            send_wecom_message(
                config["wecom_key"],
                f"**❌ 操作超时**\n> 错误: {str(e)}\n> 时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )
            raise
           
        except Exception as e:
            error_screenshot = take_screenshot(page, "error.png")
            send_wecom_image(config["wecom_key"], error_screenshot)
            send_wecom_message(
                config["wecom_key"],
                f"**❌ 任务失败**\n> 错误: {str(e)}\n> 时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )
            raise
           
        finally:
            browser.close()

if __name__ == "__main__":
    run_automation()
