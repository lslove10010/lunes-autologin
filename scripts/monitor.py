# scripts/monitor.py
import os
import asyncio
import re
from playwright.async_api import async_playwright, expect
import aiohttp
import base64

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
        data.add_field('caption', caption)
        data.add_field('photo', photo, filename=photo_path)
        data.add_field('parse_mode', 'Markdown')
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=data) as response:
                if response.status == 200:
                    print(f"✅ 截图已发送: {caption}")
                else:
                    print(f"❌ 截图发送失败: {await response.text()}")

async def send_telegram(message: str):
    """发送文本消息到 Telegram"""
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

async def handle_cloudflare_challenge(page):
    """处理 Cloudflare Turnstile 验证"""
    print("🔍 检查是否需要人机验证...")
    
    # 截图当前状态
    await page.screenshot(path='cf_check.png', full_page=True)
    
    # 检查是否存在验证框
    challenge_selectors = [
        'input[type="checkbox"]',  # 复选框
        '.cf-turnstile',  # Turnstile 容器
        'iframe[src*="challenges.cloudflare"]',  # Cloudflare iframe
        'iframe[src*="turnstile"]',
        'text=Verify you are human',
        'text=Performing security verification',
        '.cf-browser-verification',
        '#cf-turnstile'
    ]
    
    challenge_found = False
    for selector in challenge_selectors:
        try:
            element = await page.wait_for_selector(selector, timeout=3000)
            if element:
                print(f"⚠️ 发现验证元素: {selector}")
                challenge_found = True
                break
        except:
            continue
    
    if not challenge_found:
        print("✅ 未发现验证挑战")
        return True
    
    # 发送验证页面截图
    await send_telegram_photo('cf_check.png', '⚠️ 发现 Cloudflare 验证页面')
    
    # 尝试点击验证复选框
    try:
        print("🖱️ 尝试点击验证复选框...")
        
        # 方法1: 直接点击 checkbox
        checkbox = await page.query_selector('input[type="checkbox"]')
        if checkbox:
            # 模拟真实用户行为：先滚动到元素，再点击
            await checkbox.scroll_into_view_if_needed()
            await asyncio.sleep(0.5)
            await checkbox.click()
            print("✅ 已点击复选框")
        
        # 方法2: 如果 checkbox 在 iframe 中
        iframe = await page.query_selector('iframe[src*="challenges.cloudflare"], iframe[src*="turnstile"]')
        if iframe:
            print("🔄 检测到 iframe 验证框")
            frame = await iframe.content_frame()
            if frame:
                checkbox_in_frame = await frame.wait_for_selector('input[type="checkbox"]', timeout=5000)
                if checkbox_in_frame:
                    await checkbox_in_frame.click()
                    print("✅ 已点击 iframe 内的复选框")
        
        # 等待验证完成（最多30秒）
        print("⏳ 等待验证完成...")
        for i in range(30):
            await asyncio.sleep(1)
            
            # 检查是否还在验证页面
            current_url = page.url
            page_title = await page.title()
            content = await page.content()
            
            # 如果 URL 变了或标题变了，说明验证通过
            if 'login' in current_url and 'security verification' not in content.lower():
                print(f"✅ 验证似乎已通过 (URL: {current_url})")
                await page.screenshot(path='cf_success.png', full_page=True)
                await send_telegram_photo('cf_success.png', '✅ 验证通过')
                return True
            
            # 每5秒发送一次进度
            if i % 5 == 0:
                await page.screenshot(path=f'cf_progress_{i}.png', full_page=True)
                await send_telegram_photo(f'cf_progress_{i}.png', f'⏳ 验证中... {i}秒')
        
        # 检查最终状态
        final_content = await page.content()
        if 'security verification' in final_content.lower() or 'verify you are human' in final_content.lower():
            print("❌ 验证似乎未通过")
            await page.screenshot(path='cf_failed.png', full_page=True)
            await send_telegram_photo('cf_failed.png', '❌ 验证未通过')
            return False
            
        return True
        
    except Exception as e:
        print(f"❌ 验证处理失败: {e}")
        await page.screenshot(path='cf_error.png', full_page=True)
        await send_telegram_photo('cf_error.png', f'❌ 验证处理错误: {e}')
        return False

async def monitor_server():
    """主监控逻辑"""
    async with async_playwright() as p:
        # 启动浏览器 - 使用更真实的配置
        browser = await p.chromium.launch(
            headless=True,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--disable-web-security',
                '--disable-features=IsolateOrigins,site-per-process',
            ]
        )
        
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            locale='en-US',
            timezone_id='America/New_York',
            permissions=['geolocation'],
            color_scheme='light',
        )
        
        # 注入脚本隐藏自动化特征
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5]
            });
            window.chrome = { runtime: {} };
        """)
        
        page = await context.new_page()
        page.set_default_timeout(60000)
        
        try:
            # ========== 步骤 1: 访问登录页面 ==========
            print("🌐 正在访问登录页面...")
            await page.goto(LOGIN_URL, wait_until='networkidle')
            await asyncio.sleep(3)
            
            await page.screenshot(path='step1_login_page.png', full_page=True)
            await send_telegram_photo('step1_login_page.png', '📸 步骤 1: 登录页面')
            
            # ========== 步骤 2: 处理可能的 CF 验证 ==========
            cf_result = await handle_cloudflare_challenge(page)
            if not cf_result:
                raise Exception("Cloudflare 验证失败")
            
            # 验证后等待页面稳定
            await asyncio.sleep(2)
            
            # ========== 步骤 3: 填写登录表单 ==========
            print("🔐 正在填写登录表单...")
            
            # 等待登录表单出现
            await page.wait_for_selector('input[type="email"]', state='visible', timeout=10000)
            
            # 模拟真实输入：先点击，再输入，有延迟
            email_input = await page.query_selector('input[type="email"]')
            await email_input.click()
            await asyncio.sleep(0.3)
            await email_input.fill(LOGIN_EMAIL)
            await asyncio.sleep(0.5)
            
            await page.screenshot(path='step2_email.png', full_page=True)
            await send_telegram_photo('step2_email.png', '📸 步骤 2: 已填邮箱')
            
            # 密码
            password_input = await page.query_selector('input[type="password"]')
            await password_input.click()
            await asyncio.sleep(0.3)
            await password_input.fill(LOGIN_PASSWORD)
            await asyncio.sleep(0.5)
            
            await page.screenshot(path='step3_password.png', full_page=True)
            await send_telegram_photo('step3_password.png', '📸 步骤 3: 已填密码')
            
            # ========== 步骤 4: 点击登录 ==========
            print("🖱️ 点击登录按钮...")
            
            # 查找登录按钮
            login_btn = await page.wait_for_selector('button[type="submit"]', timeout=5000)
            
            # 模拟真实点击
            await login_btn.hover()
            await asyncio.sleep(0.3)
            await login_btn.click()
            
            await asyncio.sleep(3)
            await page.screenshot(path='step4_after_login.png', full_page=True)
            await send_telegram_photo('step4_after_login.png', '📸 步骤 4: 已点击登录')
            
            # ========== 步骤 5: 再次检查 CF 验证（登录后可能出现） ==========
            cf_result2 = await handle_cloudflare_challenge(page)
            if not cf_result2:
                raise Exception("登录后验证失败")
            
            # ========== 步骤 6: 点击 Continue to dashboard ==========
            print("🖱️ 查找 Continue to dashboard...")
            
            # 等待按钮出现
            continue_btn = await page.wait_for_selector(
                'button:has-text("Continue to dashboard"), a:has-text("Continue to dashboard")',
                timeout=15000
            )
            
            await continue_btn.click()
            await asyncio.sleep(3)
            
            await page.screenshot(path='step5_after_continue.png', full_page=True)
            await send_telegram_photo('step5_after_continue.png', '📸 步骤 5: 已点击 Continue')
            
            # ========== 步骤 7: 点击 Open Panel ==========
            print("🖱️ 查找 Open Panel...")
            
            open_panel = await page.wait_for_selector('button:has-text("Open Panel")', timeout=15000)
            await open_panel.click()
            
            # 等待新页面
            await asyncio.sleep(5)
            
            # 检查是否有新标签页
            pages = context.pages
            if len(pages) > 1:
                page = pages[-1]  # 切换到新页面
                print(f"🔗 切换到新页面: {page.url}")
            
            await page.screenshot(path='step6_panel.png', full_page=True)
            await send_telegram_photo('step6_panel.png', '📸 步骤 6: 控制面板')
            
            # ========== 步骤 8: 抓取数据 ==========
            print("📊 抓取数据...")
            await page.wait_for_selector('text=Uptime', timeout=15000)
            
            data = await extract_server_data(page)
            
            # 最终截图和报告
            await page.screenshot(path='step7_final.png', full_page=True)
            
            message = format_telegram_message(data)
            await send_telegram(message)
            await send_telegram_photo('step7_final.png', '📸 最终状态')
            
            print("✅ 完成！")
            
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
        page_text = await page.inner_text('body')
        
        # 正则提取
        patterns = {
            'uptime': r'(\d+d?\s*\d+h\s+\d+m\s+\d+s|\d+h\s+\d+m\s+\d+s)',
            'cpu_load': r'([\d.]+%?\s*/\s*[\d.]+%?)',
            'memory': r'([\d.]+\s*MiB?\s*/\s*[\d.]+\s*MiB?)',
            'disk': r'Disk\s+([\d.]+\s*MiB?\s*/\s*[\d.]+\s*MiB?)',
            'address': r'(node\d+\.lunes\.host:\d+)'
        }
        
        for key, pattern in patterns.items():
            matches = re.findall(pattern, page_text)
            if matches:
                data[key] = matches[0]
                
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

✅ 完成
"""

if __name__ == "__main__":
    asyncio.run(monitor_server())
