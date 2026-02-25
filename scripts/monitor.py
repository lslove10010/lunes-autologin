# scripts/monitor.py
import os
import asyncio
import re
from playwright.async_api import async_playwright
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

async def monitor_server():
    """主监控逻辑"""
    async with async_playwright() as p:
        # 启动浏览器
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.0'
        )
        
        page = await context.new_page()
        
        # 设置更长的默认超时
        page.set_default_timeout(60000)
        
        try:
            # ========== 步骤 1: 访问登录页面 ==========
            print("🌐 正在访问登录页面...")
            await page.goto(LOGIN_URL, wait_until='networkidle')
            await asyncio.sleep(2)
            
            # 截图: 登录页面
            await page.screenshot(path='step1_login_page.png', full_page=True)
            await send_telegram_photo('step1_login_page.png', '📸 步骤 1: 登录页面已加载')
            
            # ========== 步骤 2: 填写登录表单 ==========
            print("🔐 正在填写登录表单...")
            
            # 等待并填写邮箱
            await page.wait_for_selector('input[type="email"]', state='visible')
            await page.fill('input[type="email"]', LOGIN_EMAIL)
            await asyncio.sleep(1)
            
            # 截图: 填写邮箱后
            await page.screenshot(path='step2_email_filled.png', full_page=True)
            await send_telegram_photo('step2_email_filled.png', '📸 步骤 2: 邮箱已填写')
            
            # 填写密码
            await page.fill('input[type="password"]', LOGIN_PASSWORD)
            await asyncio.sleep(1)
            
            # 截图: 填写密码后（密码会显示为圆点）
            await page.screenshot(path='step3_password_filled.png', full_page=True)
            await send_telegram_photo('step3_password_filled.png', '📸 步骤 3: 密码已填写')
            
            # ========== 步骤 3: 点击登录按钮 ==========
            print("🖱️ 正在点击登录按钮...")
            
            # 查找登录按钮（多种可能的选择器）
            login_btn_selectors = [
                'button[type="submit"]',
                'button:has-text("Sign in")',
                'button:has-text("Continue")',
                '.btn-primary',
                'button.w-full',
                'form button'
            ]
            
            login_btn = None
            for selector in login_btn_selectors:
                try:
                    login_btn = await page.wait_for_selector(selector, timeout=5000)
                    if login_btn:
                        print(f"✅ 找到登录按钮: {selector}")
                        break
                except:
                    continue
            
            if not login_btn:
                raise Exception("未找到登录按钮")
            
            # 截图: 点击登录前
            await page.screenshot(path='step4_before_login_click.png', full_page=True)
            await send_telegram_photo('step4_before_login_click.png', '📸 步骤 4: 准备点击登录按钮')
            
            # 点击登录
            await login_btn.click()
            
            # 等待页面响应
            await asyncio.sleep(3)
            
            # 截图: 点击登录后
            await page.screenshot(path='step5_after_login_click.png', full_page=True)
            await send_telegram_photo('step5_after_login_click.png', '📸 步骤 5: 已点击登录按钮')
            
            # ========== 步骤 4: 等待 Cloudflare 验证 ==========
            print("⏳ 等待 Cloudflare 验证...")
            await asyncio.sleep(5)
            
            # 截图: Cloudflare 验证后
            await page.screenshot(path='step6_after_cloudflare.png', full_page=True)
            await send_telegram_photo('step6_after_cloudflare.png', '📸 步骤 6: Cloudflare 验证后状态')
            
            # 检查当前 URL
            current_url = page.url
            print(f"🔗 当前 URL: {current_url}")
            await send_telegram(f"🔗 当前 URL: {current_url}")
            
            # ========== 步骤 5: 查找并点击 "Continue to dashboard" ==========
            print("🖱️ 查找 'Continue to dashboard' 按钮...")
            
            # 截图: 查找按钮前
            await page.screenshot(path='step7_looking_for_continue.png', full_page=True)
            await send_telegram_photo('step7_looking_for_continue.png', '📸 步骤 7: 查找 Continue 按钮')
            
            continue_selectors = [
                'button:has-text("Continue to dashboard")',
                'a:has-text("Continue to dashboard")',
                'button:has-text("Continue")',
                'a:has-text("Continue")',
                '.btn:has-text("Continue")',
                'button.w-full.bg-blue-600',
                'button[type="submit"]'
            ]
            
            continue_btn = None
            for selector in continue_selectors:
                try:
                    continue_btn = await page.wait_for_selector(selector, timeout=5000)
                    if continue_btn:
                        print(f"✅ 找到 Continue 按钮: {selector}")
                        break
                except:
                    continue
            
            if not continue_btn:
                # 如果没有找到特定按钮，检查页面内容
                page_content = await page.content()
                if 'dashboard' in current_url or 'servers' in current_url:
                    print("✅ 似乎已经在 dashboard 页面了")
                    await send_telegram("✅ 检测到已在 dashboard 页面，跳过 Continue 按钮")
                else:
                    raise Exception("未找到 'Continue to dashboard' 按钮")
            else:
                # 截图: 点击 Continue 前
                await page.screenshot(path='step8_before_continue.png', full_page=True)
                await send_telegram_photo('step8_before_continue.png', '📸 步骤 8: 准备点击 Continue')
                
                await continue_btn.click()
                await asyncio.sleep(3)
                
                # 截图: 点击 Continue 后
                await page.screenshot(path='step9_after_continue.png', full_page=True)
                await send_telegram_photo('step9_after_continue.png', '📸 步骤 9: 已点击 Continue')
            
            # ========== 步骤 6: 查找并点击 "Open Panel" ==========
            print("🖱️ 查找 'Open Panel' 按钮...")
            
            # 截图: 查找 Open Panel 前
            await page.screenshot(path='step10_looking_for_open_panel.png', full_page=True)
            await send_telegram_photo('step10_looking_for_open_panel.png', '📸 步骤 10: 查找 Open Panel 按钮')
            
            open_panel_selectors = [
                'button:has-text("Open Panel")',
                'a:has-text("Open Panel")',
                '.btn:has-text("Open Panel")',
                'button.bg-blue-600',
                'button:has-text("Panel")',
                'a[href*="ctrl.lunes"]',
                'button[onclick*="panel"]'
            ]
            
            open_panel_btn = None
            for selector in open_panel_selectors:
                try:
                    open_panel_btn = await page.wait_for_selector(selector, timeout=5000)
                    if open_panel_btn:
                        print(f"✅ 找到 Open Panel 按钮: {selector}")
                        break
                except:
                    continue
            
            if not open_panel_btn:
                # 检查是否已经有直接链接到控制面板的链接
                panel_links = await page.query_selector_all('a[href*="ctrl.lunes.host"]')
                if panel_links:
                    print(f"✅ 找到 {len(panel_links)} 个控制面板链接")
                    open_panel_btn = panel_links[0]
                else:
                    raise Exception("未找到 'Open Panel' 按钮")
            
            # 截图: 点击 Open Panel 前
            await page.screenshot(path='step11_before_open_panel.png', full_page=True)
            await send_telegram_photo('step11_before_open_panel.png', '📸 步骤 11: 准备点击 Open Panel')
            
            # 获取按钮信息
            btn_text = await open_panel_btn.inner_text()
            print(f"🖱️ 点击按钮: {btn_text}")
            
            # 点击 Open Panel
            await open_panel_btn.click()
            
            # 等待新页面或跳转
            await asyncio.sleep(5)
            
            # 截图: 点击 Open Panel 后
            await page.screenshot(path='step12_after_open_panel.png', full_page=True)
            await send_telegram_photo('step12_after_open_panel.png', '📸 步骤 12: 已点击 Open Panel')
            
            # 检查是否有新页面打开
            pages = context.pages
            print(f"📑 当前有 {len(pages)} 个页面")
            
            # 切换到最新的页面（如果是新标签页打开）
            if len(pages) > 1:
                page = pages[-1]
                print(f"🔗 切换到新页面: {page.url}")
                await asyncio.sleep(3)
                
                # 截图: 新页面
                await page.screenshot(path='step13_new_page.png', full_page=True)
                await send_telegram_photo('step13_new_page.png', '📸 步骤 13: 新页面已加载')
            
            # ========== 步骤 7: 等待控制面板加载并抓取数据 ==========
            print("⏳ 等待控制面板加载...")
            
            # 等待关键元素
            try:
                await page.wait_for_selector('text=Uptime', timeout=15000)
                print("✅ 找到 Uptime 元素")
            except:
                print("⚠️ 未找到 Uptime 文本，继续尝试其他方法")
            
            await asyncio.sleep(3)
            
            # 截图: 控制面板
            await page.screenshot(path='step14_control_panel.png', full_page=True)
            await send_telegram_photo('step14_control_panel.png', '📸 步骤 14: 控制面板')
            
            # 抓取数据
            print("📊 正在抓取服务器数据...")
            data = await extract_server_data(page)
            
            # 截图: 最终状态
            await page.screenshot(path='step15_final.png', full_page=True)
            
            # 发送最终报告
            message = format_telegram_message(data)
            await send_telegram(message)
            await send_telegram_photo('step15_final.png', '📸 最终状态截图')
            
            print("✅ 监控完成！")
            
        except Exception as e:
            error_msg = f"❌ 监控失败: {str(e)}"
            print(error_msg)
            
            # 错误截图
            try:
                await page.screenshot(path='error_screenshot.png', full_page=True)
                await send_telegram_photo('error_screenshot.png', f'❌ 错误发生时的页面状态: {str(e)}')
            except:
                pass
            
            await send_telegram(error_msg)
            
        finally:
            await browser.close()

async def extract_server_data(page):
    """从页面提取服务器数据"""
    data = {
        'server_name': 'webapphost',
        'uptime': 'N/A',
        'cpu_load': 'N/A',
        'memory': 'N/A',
        'disk': 'N/A',
        'address': 'N/A'
    }
    
    try:
        # 获取页面文本内容
        page_text = await page.inner_text('body')
        
        # 获取服务器名称
        try:
            name_elem = await page.query_selector('h1')
            if name_elem:
                data['server_name'] = await name_elem.inner_text()
        except:
            pass
        
        # 使用正则表达式提取数据
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
                print(f"✅ 提取到 {key}: {data[key]}")
        
        # 备用：尝试通过 HTML 结构提取
        if data['uptime'] == 'N/A':
            # 查找包含 Uptime 的 div 的下一个兄弟元素
            uptime_divs = await page.query_selector_all('div')
            for div in uptime_divs:
                text = await div.inner_text()
                if 'Uptime' in text and len(text) < 20:
                    # 获取父元素的下一个子元素
                    parent = await div.evaluate('el => el.parentElement')
                    if parent:
                        siblings = await parent.query_selector_all(':scope > div')
                        for sibling in siblings:
                            sib_text = await sibling.inner_text()
                            if 'h' in sib_text and 'm' in sib_text:
                                data['uptime'] = sib_text.strip()
                                break
        
    except Exception as e:
        print(f"⚠️ 数据提取警告: {e}")
    
    return data

def format_telegram_message(data):
    """格式化 Telegram 消息"""
    from datetime import datetime
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    message = f"""🖥️ *Lunes Server 监控报告*

📅 检查时间: `{now}`

📌 *服务器信息*
• 名称: `{data.get('server_name', 'N/A')}`
• 地址: `{data.get('address', 'N/A')}`

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
