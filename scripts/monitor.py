# scripts/monitor_drission.py
import os
import time
import asyncio
import aiohttp
from DrissionPage import ChromiumPage, ChromiumOptions

# 配置
EMAIL = os.environ['LOGIN_EMAIL']
PASSWORD = os.environ['LOGIN_PASSWORD']
TELEGRAM_BOT_TOKEN = os.environ['TELEGRAM_BOT_TOKEN']
TELEGRAM_CHAT_ID = os.environ['TELEGRAM_CHAT_ID']

def send_telegram_photo(photo_path, caption=""):
    """同步发送截图"""
    import requests
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
    with open(photo_path, 'rb') as f:
        data = {'chat_id': TELEGRAM_CHAT_ID, 'caption': caption}
        requests.post(url, data=data, files={'photo': f})

def send_telegram(message):
    """同步发送消息"""
    import requests
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"})

def handle_turnstile(page):
    """处理 CF 验证 - 完全用你的逻辑"""
    try:
        iframe = page.ele('css:iframe[src*="cloudflare"]', timeout=5)
        if iframe:
            print("✅ 发现 CF iframe")
            frame_doc = page.get_frame(iframe)
            if frame_doc:
                # 先点击 body
                frame_doc.ele('tag:body').click()
                print("🖱️ 点击 iframe body")
                time.sleep(1)
                
                # 再点击 checkbox
                cb = frame_doc.ele('@type=checkbox')
                if cb:
                    cb.click()
                    print("🖱️ 点击 checkbox")
                    time.sleep(3)
                return True
    except Exception as e:
        print(f"ℹ️ 无验证或失败: {e}")
    return False

def monitor():
    """主函数"""
    # 初始化浏览器
    co = ChromiumOptions()
    if os.getenv('GITHUB_ACTIONS'):
        co.set_browser_path('/usr/bin/google-chrome')
    
    co.set_argument('--no-sandbox')
    co.set_argument('--disable-gpu')
    co.set_argument('--window-size=1920,1080')
    
    page = ChromiumPage(co)
    page.set.timeouts(10)
    
    try:
        print("🌐 访问登录页...")
        page.get("https://betadash.lunes.host/login?next=/")
        time.sleep(3)
        
        # 截图1
        page.get_screenshot(path="step1.png", full_page=True)
        send_telegram_photo("step1.png", "📸 步骤1: 登录页")
        
        # 处理验证
        handle_turnstile(page)
        
        # 填写账号
        print("🔐 填写账号...")
        page.ele('css:input[type="email"]').input(EMAIL)
        page.ele('css:input[type="password"]').input(PASSWORD)
        time.sleep(1)
        
        page.get_screenshot(path="step2.png", full_page=True)
        send_telegram_photo("step2.png", "📸 步骤2: 已填账号")
        
        # 登录前验证
        handle_turnstile(page)
        
        # 点击登录
        print("🖱️ 点击登录...")
        page.ele('css:button[type="submit"]').click()
        time.sleep(5)
        
        page.get_screenshot(path="step3.png", full_page=True)
        send_telegram_photo("step3.png", "📸 步骤3: 登录后")
        
        # 登录后验证
        handle_turnstile(page)
        
        # 点击 Continue
        print("🖱️ 点击 Continue...")
        page.ele('text=Continue to dashboard').click()
        time.sleep(5)
        
        page.get_screenshot(path="step4.png", full_page=True)
        send_telegram_photo("step4.png", "📸 步骤4: Dashboard")
        
        # 点击 Open Panel
        print("🖱️ 点击 Open Panel...")
        page.ele('text=Open Panel').click()
        time.sleep(5)
        
        # 获取新标签页
        tabs = page.tabs
        if len(tabs) > 1:
            page = tabs[-1]
            print(f"🔗 切换到新标签: {page.url}")
            time.sleep(3)
        
        page.get_screenshot(path="step5.png", full_page=True)
        send_telegram_photo("step5.png", "📸 步骤5: 控制面板")
        
        # 抓取数据
        print("📊 抓取数据...")
        time.sleep(3)
        
        # 提取数据（正则或元素查找）
        uptime = page.ele('text=Uptime >> xpath=following-sibling::div', timeout=5).text if page.ele('text=Uptime', timeout=1) else "N/A"
        cpu = page.ele('text=CPU Load >> xpath=following-sibling::div', timeout=5).text if page.ele('text=CPU Load', timeout=1) else "N/A"
        memory = page.ele('text=Memory >> xpath=following-sibling::div', timeout=5).text if page.ele('text=Memory', timeout=1) else "N/A"
        
        # 最终截图
        page.get_screenshot(path="step6.png", full_page=True)
        
        # 发送报告
        msg = f"""🖥️ Lunes Server 监控报告

⏱️ Uptime: {uptime}
🔄 CPU: {cpu}
💾 Memory: {memory}

✅ 完成"""
        
        send_telegram(msg)
        send_telegram_photo("step6.png", "📸 完成")
        
        print("✅ 全部完成！")
        
    except Exception as e:
        print(f"❌ 错误: {e}")
        page.get_screenshot(path="error.png", full_page=True)
        send_telegram_photo("error.png", f"❌ 错误: {e}")
        send_telegram(f"❌ 监控失败: {e}")
        
    finally:
        page.quit()

if __name__ == "__main__":
    monitor()
