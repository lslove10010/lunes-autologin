# scripts/monitor.py
import os
import asyncio
import re
import time
import random
from playwright.async_api import async_playwright
import aiohttp

# 从环境变量获取配置
LOGIN_EMAIL = os.environ['LOGIN_EMAIL']
LOGIN_PASSWORD = os.environ['LOGIN_PASSWORD']
TELEGRAM_BOT_TOKEN = os.environ['TELEGRAM_BOT_TOKEN']
TELEGRAM_CHAT_ID = os.environ['TELEGRAM_CHAT_ID']

BASE_URL = "https://betadash.lunes.host"
LOGIN_URL = f"{BASE_URL}/login?next=/"

async def send_telegram_photo(photo_path: str, caption: str = ""):
    """发送截图到 Telegram"""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
    
    with open(photo_path, 'rb') as photo:
        data = aiohttp.FormData()
        data.add_field('chat_id', TELEGRAM_CHAT_ID)
        data.add_field('caption', caption[:1024])
        data.add_field('photo', photo, filename=photo_path)
        data.add_field('parse_mode', 'Markdown')
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=data) as response:
                if response.status == 200:
                    print(f"✅ 截图已发送: {caption[:50]}...")
                else:
                    print(f"❌ 截图发送失败: {await response.text()}")

async def send_telegram(message: str):
    """发送文本消息到 Telegram"""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message[:4096],
        "parse_mode": "Markdown"
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload) as response:
            if response.status == 200:
                print("✅ Telegram 消息发送成功")
            else:
                print(f"❌ Telegram 发送失败: {await response.text()}")

async def handle_turnstile(page):
    """
    处理 Cloudflare Turnstile 验证
    参考你的 DrissionPage 代码逻辑：
    1. 找到 iframe[src*="cloudflare"]
    2. 点击 body 或 checkbox
    """
    print("🔍 检查 Cloudflare 验证...")
    
    try:
        # 等待 iframe 出现（最多5秒）
        iframe = await page.wait_for_selector(
            'iframe[src*="cloudflare"], iframe[src*="turnstile"], iframe[src*="challenges"]',
            timeout=5000
        )
        
        if iframe:
            print("✅ 发现 CF iframe，开始处理...")
            
            # 获取 iframe 的 frame
            frame = await iframe.content_frame()
            if not frame:
                print("❌ 无法进入 iframe")
                return False
            
            # 方法1: 点击 body（参考你的代码）
            try:
                body = await frame.wait_for_selector('body', timeout=3000)
                if body:
                    print("🖱️ 点击 iframe body...")
                    await body.click()
                    await asyncio.sleep(3)
            except Exception as e:
                print(f"⚠️ 点击 body 失败: {e}")
            
            # 方法2: 点击 checkbox
            try:
                checkbox = await frame.wait_for_selector('input[type="checkbox"]', timeout=3000)
                if checkbox:
                    print("🖱️ 点击 checkbox...")
                    await checkbox.click()
                    await asyncio.sleep(3)
            except Exception as e:
                print(f"⚠️ 点击 checkbox 失败: {e}")
            
            # 等待验证完成
            print("⏳ 等待验证完成...")
            for i in range(20):  # 最多等20秒
                await asyncio.sleep(1)
                
                # 检查是否还在验证页面
                content = await page.content()
                if 'security verification' not in content.lower() and 'verify you are human' not in content.lower():
                    print(f"✅ 验证通过！用时 {i+1} 秒")
                    return True
                
                # 每5秒重试点击
                if (i + 1) % 5 == 0:
                    try:
                        body = await frame.wait_for_selector('body', timeout=1000)
                        if body:
                            await body.click()
                            print(f"🖱️ 第{(i+1)//5}次重试点击...")
                    except:
                        pass
            
            print("⚠️ 验证超时，但继续执行...")
            return True  # 即使超时也继续，可能已验证
            
    except Exception as e:
        print(f"ℹ️ 未发现验证或处理失败: {e}")
        return True  # 没发现验证也算成功

async def monitor_server():
    """主监控逻辑"""
    async with async_playwright() as p:
        # 启动浏览器
        browser = await p.chromium.launch(
            headless=True,
            args=[
                '--no-sandbox',
                '--disable-gpu',
                '--window-size=1920,1080',
                '--start-maximized',
                '--disable-blink-features=AutomationControlled',
            ]
        )
        
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            locale='en-US',
        )
        
        page = await context.new_page()
        page.set_default_timeout(30000)
        
        try:
            # ========== 步骤 1: 访问登录页 ==========
            print("🌐 访问登录页...")
            await page.goto(LOGIN_URL, wait_until='networkidle')
            await asyncio.sleep(3)
            
            await page.screenshot(path='step1_login.png', full_page=True)
            await send_telegram_photo('step1_login.png', '📸 步骤1: 登录页')
            
            # ========== 步骤 2: 处理 CF 验证 ==========
            await handle_turnstile(page)
            
            # ========== 步骤 3: 填写账号 ==========
            print("🔐 填写账号...")
            
            # 等待并填写邮箱
            await page.wait_for_selector('input[type="email"]', state='visible')
            await page.fill('input[type="email"]', LOGIN_EMAIL)
            await asyncio.sleep(0.5)
            
            # 填写密码
            await page.fill('input[type="password"]', LOGIN_PASSWORD)
            await asyncio.sleep(0.5)
            
            await page.screenshot(path='step2_filled.png', full_page=True)
            await send_telegram_photo('step2_filled.png', '📸 步骤2: 已填账号')
            
            # ========== 步骤 4: 点击登录 ==========
            print("🖱️ 点击登录...")
            
            # 再次处理验证（登录前）
            await handle_turnstile(page)
            
            # 点击登录按钮
            await page.click('button[type="submit"]')
            await asyncio.sleep(5)
            
            await page.screenshot(path='step3_after_login.png', full_page=True)
            await send_telegram_photo('step3_after_login.png', '📸 步骤3: 点击登录后')
            
            # ========== 步骤 5: 处理登录后的验证 ==========
            await handle_turnstile(page)
            
            # ========== 步骤 6: 点击 Continue to dashboard ==========
            print("🖱️ 点击 Continue...")
            
            # 等待按钮出现
            await page.wait_for_selector('text=Continue to dashboard', timeout=15000)
            await page.click('button:has-text("Continue to dashboard")')
            await asyncio.sleep(5)
            
            await page.screenshot(path='step4_dashboard.png', full_page=True)
            await send_telegram_photo('step4_dashboard.png', '📸 步骤4: Dashboard')
            
            # ========== 步骤 7: 点击 Open Panel ==========
            print("🖱️ 点击 Open Panel...")
            
            await page.wait_for_selector('text=Open Panel', timeout=15000)
            await page.click('button:has-text("Open Panel")')
            await asyncio.sleep(5)
            
            # 检查新标签页
            pages = context.pages
            if len(pages) > 1:
                page = pages[-1]
                print(f"🔗 切换到新页面: {page.url}")
                await asyncio.sleep(3)
            
            await page.screenshot(path='step5_panel.png', full_page=True)
            await send_telegram_photo('step5_panel.png', '📸 步骤5: 控制面板')
            
            # ========== 步骤 8: 抓取数据 ==========
            print("📊 抓取数据...")
            
            # 等待数据加载
            await page.wait_for_selector('text=Uptime', timeout=15000)
            await asyncio.sleep(2)
            
            data = await extract_server_data(page)
            
            await page.screenshot(path='step6_final.png', full_page=True)
            
            # 发送报告
            msg = format_telegram_message(data)
            await send_telegram(msg)
            await send_telegram_photo('step6_final.png', '📸 完成')
            
            print("✅ 全部完成！")
            
        except Exception as e:
            error_msg = f"❌ 错误: {str(e)}"
            print(error_msg)
            try:
                await page.screenshot(path='error.png', full_page=True)
                await send_telegram_photo('error.png', f'❌ 错误: {str(e)}')
            except:
                pass
            await send_telegram(error_msg)
            
        finally:
            await browser.close()

async def extract_server_data(page):
    """提取服务器数据"""
    data = {
        'server_name': 'webapphost',
        'uptime': 'N/A',
        'cpu_load': 'N/A',
        'memory': 'N/A',
        'disk': 'N/A',
        'address': 'N/A'
    }
    
    try:
        text = await page.inner_text('body')
        
        patterns = {
            'uptime': r'(\d+d?\s*\d+h\s+\d+m\s+\d+s|\d+h\s+\d+m\s+\d+s)',
            'cpu_load': r'([\d.]+%?\s*/\s*[\d.]+%?)',
            'memory': r'([\d.]+\s*MiB?\s*/\s*[\d.]+\s*MiB?)',
            'disk': r'Disk\s+([\d.]+\s*MiB?\s*/\s*[\d.]+\s*MiB?)',
            'address': r'(node\d+\.lunes\.host:\d+)'
        }
        
        for key, pattern in patterns.items():
            matches = re.findall(pattern, text)
            if matches:
                data[key] = matches[0]
                print(f"✅ 提取到 {key}: {data[key]}")
                
    except Exception as e:
        print(f"⚠️ 提取警告: {e}")
    
    return data

def format_telegram_message(data):
    """格式化消息"""
    from datetime import datetime
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    return f"""🖥️ *Lunes Server 监控报告*

📅 `{now}`

📌 *服务器*
• 名称: `{data.get('server_name', 'N/A')}`
• 地址: `{data.get('address', 'N/A')}`

📊 *资源*
⏱️ Uptime: `{data.get('uptime', 'N/A')}`
🔄 CPU: `{data.get('cpu_load', 'N/A')}`
💾 Memory: `{data.get('memory', 'N/A')}`
💿 Disk: `{data.get('disk', 'N/A')}`

✅ 自动检查完成
"""

if __name__ == "__main__":
    asyncio.run(monitor_server())
