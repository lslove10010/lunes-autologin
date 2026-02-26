#!/usr/bin/env python3
"""
Lunes Host 自动登录并获取服务器状态
使用 Playwright + 企业微信机器人
"""
import os
import time
import base64
import requests
from datetime import datetime, timezone, timedelta
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

# 北京时间（UTC+8）
BEIJING_TZ = timezone(timedelta(hours=8))

def get_beijing_time():
    return datetime.now(BEIJING_TZ).strftime('%Y-%m-%d %H:%M:%S')

def send_wecom_message(webhook_key, message):
    """
    发送企业微信消息 - 改用 text 类型，避免 markdown 在普通微信显示问题
    """
    if not webhook_key:
        print("警告: 未设置企业微信 Webhook Key")
        return False
   
    webhook_url = f"https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={webhook_key}"
   
    try:
        data = {
            "msgtype": "text",
            "text": {
                "content": message,
                "mentioned_list": [],           # 可选：@某人
                "mentioned_mobile_list": []     # 可选：@手机号
            }
        }
        response = requests.post(webhook_url, json=data, timeout=10)
        result = response.json()
       
        if result.get("errcode") == 0:
            print("企业微信文字通知发送成功")
            return True
        else:
            print(f"企业微信发送失败: {result}")
            return False
           
    except Exception as e:
        print(f"企业微信通知失败: {e}")
        return False

def send_wecom_image(webhook_key, image_path):
    """发送图片到企业微信（通过 base64 + md5）"""
    if not webhook_key or not os.path.exists(image_path):
        return False
   
    webhook_url = f"https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={webhook_key}"
   
    try:
        with open(image_path, "rb") as f:
            image_data = f.read()
       
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
            print(f"图片发送成功: {os.path.basename(image_path)}")
            return True
        else:
            print(f"图片发送失败: {result}")
            return False
           
    except Exception as e:
        print(f"发送图片失败: {e}")
        return False

def take_screenshot(page, filename):
    """截图并保存（不打印路径到日志，避免 GitHub 显示）"""
    screenshot_path = f"/tmp/{filename}"
    page.screenshot(path=screenshot_path, full_page=True)
    # 注释掉打印，避免 GitHub Actions 日志显示路径
    # print(f"截图已保存: {screenshot_path}")
    return screenshot_path

def extract_server_stats(page):
    """提取服务器详情页的统计信息 - 加强版"""
    stats = {}
    
    try:
        # 等待 Uptime 出现（核心指标）
        page.wait_for_selector("text=Uptime", state="visible", timeout=20000)
        print("找到 'Uptime' 元素，页面已加载")
        
        # 尝试提取 Address（可能有端口或 IP）
        try:
            address_text = page.locator("text=node22.lunes.host, text=Address").inner_text(timeout=5000).strip()
            if address_text:
                stats["address"] = address_text
                print(f"提取到 address: {address_text}")
        except:
            pass
        
        # 卡片提取 - 放宽选择器
        cards = page.locator("div.grid > div, div[class*='card'], div[class*='stat'], div[class*='bg-'], section, article").all()
        print(f"找到 {len(cards)} 个潜在统计卡片")
        
        for card in cards:
            try:
                text = card.inner_text().strip()
                if not text:
                    continue
                lower_text = text.lower()
                
                if "uptime" in lower_text:
                    # 去掉标题，保留值（支持 "Uptime: 5 days" 或 "Uptime 5d"）
                    value = text.replace("Uptime", "", 1).replace(":", "", 1).strip()
                    stats["uptime"] = value or text.split("Uptime")[-1].strip()
                elif "cpu load" in lower_text or "cpu" in lower_text:
                    stats["cpu_load"] = text.replace("CPU Load", "", 1).replace(":", "", 1).strip()
                elif "memory" in lower_text and "network" not in lower_text:
                    stats["memory"] = text.replace("Memory", "", 1).replace(":", "", 1).strip()
                elif "disk" in lower_text:
                    stats["disk"] = text.replace("Disk", "", 1).replace(":", "", 1).strip()
                elif "inbound" in lower_text or "network (inbound)" in lower_text:
                    stats["network_in"] = text.replace("Network (Inbound)", "", 1).replace("Inbound", "", 1).strip()
                elif "outbound" in lower_text or "network (outbound)" in lower_text:
                    stats["network_out"] = text.replace("Network (Outbound)", "", 1).replace("Outbound", "", 1).strip()
            except:
                continue
        
        # 最强保底：整个可见文本逐行匹配（旧代码核心，可靠）
        if len(stats) < 4:  # 如果卡片没抓够，再用 body
            print("卡片提取不完整，使用 body 文本保底")
            body_text = page.inner_text("body", timeout=5000)
            lines = [line.strip() for line in body_text.splitlines() if line.strip()]
            
            for i in range(len(lines)):
                line = lines[i].lower()
                if "uptime" in line and i+1 < len(lines):
                    stats["uptime"] = lines[i+1].strip()
                if "cpu load" in line or "cpu" in line and "load" in line and i+1 < len(lines):
                    stats["cpu_load"] = lines[i+1].strip()
                if "memory" in line and "network" not in line and i+1 < len(lines):
                    stats["memory"] = lines[i+1].strip()
                if "disk" in line and i+1 < len(lines):
                    stats["disk"] = lines[i+1].strip()
                if ("inbound" in line or "network in" in line) and i+1 < len(lines):
                    stats["network_in"] = lines[i+1].strip()
                if ("outbound" in line or "network out" in line) and i+1 < len(lines):
                    stats["network_out"] = lines[i+1].strip()
        
        if not stats:
            stats["error"] = "未能提取到任何统计数据，请检查页面结构或选择器"
        else:
            print(f"提取成功: {stats}")
    
    except Exception as e:
        print(f"提取统计信息失败: {str(e)}")
        stats["error"] = str(e)
    
    return stats

def format_stats_message(stats):
    """格式化统计信息为纯文本（适合 text 消息）"""
    # 打码 server ID 如 564fec71
    address = stats.get('address', 'N/A')
    if '564fec71' in address:
        address = address.replace('564fec71', '***')
    stats['address'] = address
    
    lines = []
    lines.append("🖥️ 服务器状态监控")
    lines.append("")
    lines.append(f"📍 地址: {stats.get('address', 'N/A')}")
    lines.append(f"⏱️ 运行时间: {stats.get('uptime', 'N/A')}")
    lines.append(f"💻 CPU 负载: {stats.get('cpu_load', 'N/A')}")
    lines.append(f"🧠 内存使用: {stats.get('memory', 'N/A')}")
    lines.append(f"💾 磁盘使用: {stats.get('disk', 'N/A')}")
    lines.append(f"📥 网络入站: {stats.get('network_in', 'N/A')}")
    lines.append(f"📤 网络出站: {stats.get('network_out', 'N/A')}")
    lines.append("")
    lines.append(f"更新时间: {get_beijing_time()}")
    
    return "\n".join(lines)

def run_automation():
    """主自动化流程"""
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
            print("正在访问登录页面...")
            page.goto(config["website_url"], wait_until="networkidle", timeout=30000)
           
            page.wait_for_selector("input[name='username']", timeout=10000)
           
            print("填写登录信息...")
            page.fill("input[name='username']", config["username"])
            page.fill("input[name='password']", config["password"])
           
            login_filled_screenshot = take_screenshot(page, "login_filled.png")
           
            print("尝试点击登录按钮...")
            try:
                page.get_by_role("button", name="Login", exact=False).click(timeout=10000)
                print("成功点击 'Login' 按钮")
            except Exception as e:
                print(f"使用 get_by_role 失败: {e}")
                page.locator("button:has-text('Login')").click(timeout=10000)
           
            time.sleep(1)
            click_after_screenshot = take_screenshot(page, "after_click_login.png")
            send_wecom_image(config["wecom_key"], click_after_screenshot)
           
            page.wait_for_load_state("networkidle", timeout=20000)
            time.sleep(2.5)
           
            if "/auth/login" not in page.url.lower() and "/login" not in page.url.lower():
                print(f"URL 已跳转: {page.url}")
            else:
                if page.locator("text=webapphost").count() > 0:
                    print("找到 'webapphost' 文字 → 已登录")
                else:
                    error_screenshot = take_screenshot(page, "login_failed_detailed.png")
                    send_wecom_image(config["wecom_key"], error_screenshot)
                    raise Exception(f"登录疑似失败，当前URL: {page.url}")
           
            print(f"登录成功，当前 URL: {page.url}")
           
            dashboard_screenshot = take_screenshot(page, "dashboard.png")
            send_wecom_image(config["wecom_key"], dashboard_screenshot)
           
            # 登录成功通知 - 纯文本
            success_msg = f"""登录成功！
时间: {get_beijing_time()}
用户: {config['username']}
页面: {page.url}"""
            send_wecom_message(config["wecom_key"], success_msg)
           
            print("查找 webapphost...")
            page.wait_for_selector("text=webapphost", timeout=10000)
           
            webapphost_link = page.locator("text=webapphost").first
            if not webapphost_link.is_visible():
                raise Exception("未找到 webapphost 链接")
           
            print("点击进入 webapphost...")
            webapphost_link.click()
           
            page.wait_for_load_state("networkidle")
            time.sleep(3)
           
            current_url = page.url
            print(f"进入服务器详情页: {current_url}")
           
            detail_screenshot = take_screenshot(page, "server_detail.png")
            send_wecom_image(config["wecom_key"], detail_screenshot)
           
            print("提取服务器统计信息...")
            stats = extract_server_stats(page)
            print(f"提取到的数据: {stats}")
           
            stats_message = format_stats_message(stats)
            send_wecom_message(config["wecom_key"], stats_message)
           
            print("任务完成！")
           
        except PlaywrightTimeout as e:
            error_screenshot = take_screenshot(page, "error_timeout.png")
            send_wecom_image(config["wecom_key"], error_screenshot)
            send_wecom_message(
                config["wecom_key"],
                f"操作超时\n错误: {str(e)}\n时间: {get_beijing_time()}"
            )
            raise
           
        except Exception as e:
            error_screenshot = take_screenshot(page, "error.png")
            send_wecom_image(config["wecom_key"], error_screenshot)
            send_wecom_message(
                config["wecom_key"],
                f"任务失败\n错误: {str(e)}\n时间: {get_beijing_time()}"
            )
            raise
           
        finally:
            browser.close()

if __name__ == "__main__":
    run_automation()
