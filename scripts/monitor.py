# scripts/monitor.py
import os
import asyncio
import re
from playwright.async_api import async_playwright
import aiohttp

# 从环境变量获取配置
LOGIN_EMAIL = os.environ['LOGIN_EMAIL']
LOGIN_PASSWORD = os.environ['LOGIN_PASSWORD']
TELEGRAM_BOT_TOKEN = os.environ['TELEGRAM_BOT_TOKEN']
TELEGRAM_CHAT_ID = os.environ['TELEGRAM_CHAT_ID']

BASE_URL = "https://betadash.lunes.host"
LOGIN_URL = f"{BASE_URL}/login?next=/"

async def send_telegram(message: str):
    """发送消息到 Telegram"""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload) as response:
            if response.status == 200:
                print("✅ Telegram 消息发送成功")
            else:
                print(f"❌ Telegram 发送失败: {await response.text()}")

async def monitor_server():
    """主监控逻辑"""
    async with async_playwright() as p:
        # 启动浏览器
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.0'
        )
        
        page = await context.new_page()
        
        try:
            print("🌐 正在访问登录页面...")
            await page.goto(LOGIN_URL, wait_until='networkidle')
            await page.wait_for_timeout(2000)
            
            # 填写登录表单
            print("🔐 正在登录...")
            await page.fill('input[type="email"], input[name="email"], #email', LOGIN_EMAIL)
            await page.fill('input[type="password"], input[name="password"], #password', LOGIN_PASSWORD)
            
            # 点击登录按钮（根据第一张图，登录按钮在表单下方）
            await page.click('button[type="submit"], .btn-primary, button:has-text("Sign in")')
            
            # 等待 Cloudflare 验证和登录成功
            print("⏳ 等待验证...")
            await page.wait_for_timeout(5000)
            
            # 等待 "Continue to dashboard" 按钮出现（第二张图）
            print("🖱️ 点击 'Continue to dashboard'...")
            continue_btn = await page.wait_for_selector(
                'button:has-text("Continue to dashboard"), '
                'a:has-text("Continue to dashboard"), '
                '.btn:has-text("Continue")',
                timeout=10000
            )
            await continue_btn.click()
            
            # 等待跳转到服务器列表页面
            await page.wait_for_timeout(3000)
            
            # 点击 "Open Panel" 按钮（第三张图）
            print("🖱️ 点击 'Open Panel'...")
            open_panel_btn = await page.wait_for_selector(
                'button:has-text("Open Panel"), '
                '.btn:has-text("Open Panel"), '
                'a:has-text("Open Panel")',
                timeout=10000
            )
            await open_panel_btn.click()
            
            # 等待控制面板加载（第四张图）
            print("⏳ 等待控制面板加载...")
            await page.wait_for_timeout(5000)
            
            # 等待关键元素出现
            await page.wait_for_selector('text=Uptime', timeout=15000)
            
            # 抓取数据
            print("📊 正在抓取服务器数据...")
            data = await extract_server_data(page)
            
            # 发送 Telegram 通知
            message = format_telegram_message(data)
            await send_telegram(message)
            
            print("✅ 监控完成！")
            
        except Exception as e:
            error_msg = f"❌ 监控失败: {str(e)}"
            print(error_msg)
            await send_telegram(error_msg)
            # 截图保存用于调试
            await page.screenshot(path='error_screenshot.png')
            
        finally:
            await browser.close()

async def extract_server_data(page):
    """从页面提取服务器数据"""
    data = {
        'server_name': '',
        'uptime': '',
        'cpu_load': '',
        'memory': '',
        'disk': '',
        'address': ''
    }
    
    try:
        # 获取服务器名称
        name_elem = await page.query_selector('h1, .server-name, [data-server-name]')
        if name_elem:
            data['server_name'] = await name_elem.inner_text()
        
        # 获取地址信息
        address_elem = await page.query_selector('text=Address >> xpath=following-sibling::*')
        if address_elem:
            data['address'] = await address_elem.inner_text()
        
        # 使用更可靠的选择器策略
        # Uptime - 通常在黄色/橙色图标旁边
        uptime_elem = await page.query_selector(
            '.fa-clock, .icon-clock, [class*="uptime"], '
            'div:has-text("Uptime") + div, '
            'div:has-text("Uptime") >> xpath=following-sibling::div'
        )
        if uptime_elem:
            data['uptime'] = await uptime_elem.inner_text()
        else:
            # 尝试通过文本内容查找
            content = await page.content()
            uptime_match = re.search(r'Uptime\s*[\n\r\s]*(\d+h\s*\d+m\s*\d+s|\d+d\s*\d+h)', content)
            if uptime_match:
                data['uptime'] = uptime_match.group(1)
        
        # CPU Load
        cpu_elem = await page.query_selector(
            '.fa-microchip, .icon-cpu, [class*="cpu"], '
            'div:has-text("CPU Load") + div'
        )
        if cpu_elem:
            data['cpu_load'] = await cpu_elem.inner_text()
        else:
            content = await page.content()
            cpu_match = re.search(r'CPU Load\s*[\n\r\s]*([\d.]+%?\s*/\s*\d+%?)', content)
            if cpu_match:
                data['cpu_load'] = cpu_match.group(1)
        
        # Memory
        memory_elem = await page.query_selector(
            '.fa-memory, .icon-memory, [class*="memory"], '
            'div:has-text("Memory") + div'
        )
        if memory_elem:
            data['memory'] = await memory_elem.inner_text()
        else:
            content = await page.content()
            mem_match = re.search(r'Memory\s*[\n\r\s]*([\d.]+\s*MiB?\s*/\s*[\d.]+\s*MiB?)', content)
            if mem_match:
                data['memory'] = mem_match.group(1)
        
        # Disk
        disk_elem = await page.query_selector(
            '.fa-hdd, .icon-disk, [class*="disk"], '
            'div:has-text("Disk") + div'
        )
        if disk_elem:
            data['disk'] = await disk_elem.inner_text()
        
        # 如果上面的方法都失败，尝试直接解析 HTML 文本
        if not all([data['uptime'], data['cpu_load'], data['memory']]):
            print("⚠️ 使用备用提取方法...")
            page_text = await page.inner_text('body')
            
            # 正则提取
            patterns = {
                'uptime': r'(\d+h\s+\d+m\s+\d+s)',
                'cpu_load': r'([\d.]+%?\s*/\s*\d+%?)',
                'memory': r'([\d.]+\s*MiB?\s*/\s*[\d.]+\s*MiB?)',
                'disk': r'Disk\s+([\d.]+\s*MiB?\s*/\s*[\d.]+\s*MiB?)'
            }
            
            for key, pattern in patterns.items():
                if not data[key]:
                    match = re.search(pattern, page_text)
                    if match:
                        data[key] = match.group(1)
        
    except Exception as e:
        print(f"⚠️ 数据提取警告: {e}")
    
    return data

def format_telegram_message(data):
    """格式化 Telegram 消息"""
    timestamp = asyncio.get_event_loop().time()
    from datetime import datetime
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    message = f"""🖥️ *Lunes Server 监控报告*

📅 检查时间: `{now}`

📌 *服务器信息*
• 名称: `{data.get('server_name', 'webapphost')}`
• 地址: `{data.get('address', 'node22.lunes.host:3098')}`

📊 *资源使用情况*
⏱️ Uptime: `{data.get('uptime', 'N/A')}`
🔄 CPU Load: `{data.get('cpu_load', 'N/A')}`
💾 Memory: `{data.get('memory', 'N/A')}`
💿 Disk: `{data.get('disk', 'N/A')}`

✅ 自动检查完成
"""
    return message

if __name__ == "__main__":
    asyncio.run(monitor_server())
