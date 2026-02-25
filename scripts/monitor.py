# scripts/monitor.py
import os
import asyncio
import re
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
        data.add_field('caption', caption[:1024])  # Telegram 限制
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
        "text": message[:4096],  # Telegram 限制
        "parse_mode": "Markdown"
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload) as response:
            if response.status == 200:
                print("✅ Telegram 消息发送成功")
            else:
                print(f"❌ Telegram 发送失败: {await response.text()}")

async def random_delay(min_sec=0.5, max_sec=2.0):
    """随机延迟，模拟人类反应时间"""
    delay = random.uniform(min_sec, max_sec)
    await asyncio.sleep(delay)

async def human_like_click(page, selector):
    """模拟人类点击：移动鼠标、停顿、点击"""
    element = await page.wait_for_selector(selector, timeout=10000)
    
    # 获取元素位置
    box = await element.bounding_box()
    if not box:
        raise Exception(f"无法获取元素位置: {selector}")
    
    # 计算元素中心点，并添加随机偏移（模拟不精准点击）
    x = box['x'] + box['width'] / 2 + random.randint(-5, 5)
    y = box['y'] + box['height'] / 2 + random.randint(-5, 5)
    
    # 移动鼠标（贝塞尔曲线）
    await page.mouse.move(x, y, steps=random.randint(5, 10))
    await random_delay(0.2, 0.5)
    
    # 按下和释放之间也有延迟
    await page.mouse.down()
    await random_delay(0.05, 0.15)
    await page.mouse.up()
    
    print(f"🖱️ 已点击: {selector} at ({x:.0f}, {y:.0f})")
    return element

async def handle_turnstile_challenge(page):
    """处理 Cloudflare Turnstile 验证 - 最强反检测版本"""
    print("🔍 检查 Cloudflare 验证...")
    
    await page.screenshot(path='cf_check.png', full_page=True)
    
    # 检查是否存在验证
    challenge_text = await page.inner_text('body')
    if 'Verify you are human' not in challenge_text and 'security verification' not in challenge_text:
        print("✅ 无需验证")
        return True
    
    await send_telegram_photo('cf_check.png', '⚠️ 发现 CF 验证，开始处理...')
    print("⚠️ 发现验证页面，尝试绕过...")
    
    # 方法 1: 直接点击 checkbox（带随机延迟和移动）
    try:
        print("🎯 方法1: 模拟人类点击 checkbox...")
        
        # 先滚动到验证框位置
        await page.evaluate('window.scrollTo(0, 200)')
        await random_delay(0.5, 1.0)
        
        # 查找 checkbox（可能在 iframe 中）
        checkbox_selectors = [
            'input[type="checkbox"]',
            '.cf-turnstile input',
            'input[name="cf-turnstile-response"]',
            'iframe[src*="challenges.cloudflare"]',
            'iframe[src*="turnstile"]'
        ]
        
        # 检查是否在 iframe 中
        iframe = None
        for selector in ['iframe[src*="challenges.cloudflare"]', 'iframe[src*="turnstile"]']:
            try:
                iframe = await page.wait_for_selector(selector, timeout=3000)
                if iframe:
                    print(f"✅ 找到 iframe: {selector}")
                    break
            except:
                continue
        
        if iframe:
            # 处理 iframe 内的 checkbox
            frame = await iframe.content_frame()
            if frame:
                print("🔄 进入 iframe...")
                await random_delay(1.0, 2.0)
                
                # 在 iframe 内查找 checkbox
                try:
                    checkbox = await frame.wait_for_selector('input[type="checkbox"]', timeout=5000)
                    box = await checkbox.bounding_box()
                    
                    if box:
                        # 模拟真实点击 iframe 内的元素
                        # 注意：iframe 内的坐标是相对于 iframe 的
                        x = box['x'] + box['width'] / 2 + random.randint(-3, 3)
                        y = box['y'] + box['height'] / 2 + random.randint(-3, 3)
                        
                        print(f"🖱️ 点击 iframe 内 checkbox at ({x:.0f}, {y:.0f})")
                        await checkbox.click()
                        # 或者使用更真实的点击
                        # await frame.evaluate(f'document.querySelector("input[type=checkbox]").click()')
                        
                except Exception as e:
                    print(f"⚠️ iframe 内点击失败: {e}")
                    # 尝试 JavaScript 点击
                    await frame.evaluate('document.querySelector("input[type=checkbox]").click()')
        else:
            # 直接点击页面上的 checkbox
            try:
                checkbox = await page.wait_for_selector('input[type="checkbox"]', timeout=5000)
                await human_like_click(page, 'input[type="checkbox"]')
            except:
                # 尝试通过 label 点击
                await human_like_click(page, 'label:has-text("Verify you are human")')
        
        # 等待验证完成
        print("⏳ 等待验证完成（最长60秒）...")
        for i in range(60):
            await asyncio.sleep(1)
            
            # 检查页面是否变化
            current_url = page.url
            content = await page.content()
            
            # 如果不在验证页面了
            if 'security verification' not in content.lower() and 'verify you are human' not in content.lower():
                print(f"✅ 验证通过！用时 {i+1} 秒")
                await page.screenshot(path='cf_success.png', full_page=True)
                await send_telegram_photo('cf_success.png', f'✅ 验证通过！用时 {i+1} 秒')
                return True
            
            # 每10秒发送进度
            if (i + 1) % 10 == 0:
                await page.screenshot(path=f'cf_wait_{i+1}.png', full_page=True)
                await send_telegram_photo(f'cf_wait_{i+1}.png', f'⏳ 验证中... {i+1}秒')
                print(f"⏳ 已等待 {i+1} 秒...")
        
        # 超时
        await page.screenshot(path='cf_timeout.png', full_page=True)
        await send_telegram_photo('cf_timeout.png', '❌ 验证超时（60秒）')
        return False
        
    except Exception as e:
        print(f"❌ 方法1失败: {e}")
        await send_telegram(f"⚠️ 方法1失败: {str(e)}")
    
    # 方法 2: 使用 JavaScript 强制触发（最后手段）
    try:
        print("🎯 方法2: JavaScript 强制点击...")
        await page.evaluate('''
            () => {
                // 尝试多种方式找到并点击 checkbox
                const checkbox = document.querySelector('input[type="checkbox"]');
                if (checkbox) {
                    checkbox.click();
                    checkbox.checked = true;
                    checkbox.dispatchEvent(new Event('change', { bubbles: true }));
                    return 'Checkbox clicked via JS';
                }
                
                // 尝试点击 label
                const label = document.querySelector('label');
                if (label) {
                    label.click();
                    return 'Label clicked via JS';
                }
                
                return 'No checkbox found';
            }
        ''')
        
        await asyncio.sleep(5)
        
        content = await page.content()
        if 'security verification' not in content.lower():
            print("✅ 方法2成功！")
            return True
            
    except Exception as e:
        print(f"❌ 方法2失败: {e}")
    
    return False

async def monitor_server():
    """主监控逻辑"""
    async with async_playwright() as p:
        # 启动浏览器 - 最强反检测配置
        browser = await p.chromium.launch(
            headless=True,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--disable-web-security',
                '--disable-features=IsolateOrigins,site-per-process,AutomationControlled',
                '--disable-dev-shm-usage',
                '--disable-setuid-sandbox',
                '--no-sandbox',
                '--window-size=1920,1080',
                '--start-maximized',
                '--disable-infobars',
                '--disable-extensions',
                '--disable-notifications',
                '--disable-popup-blocking',
                '--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            ]
        )
        
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            locale='en-US',
            timezone_id='America/New_York',
            permissions=['geolocation'],
            color_scheme='light',
            java_script_enabled=True,
        )
        
        # 注入反检测脚本
        await context.add_init_script("""
            // 覆盖 webdriver 检测
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
            
            // 覆盖 plugins
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5]
            });
            
            // 覆盖 languages
            Object.defineProperty(navigator, 'languages', {
                get: () => ['en-US', 'en']
            });
            
            // 伪造 chrome 对象
            window.chrome = {
                runtime: {
                    OnInstalledReason: {CHROME_UPDATE: "chrome_update"},
                    OnRestartRequiredReason: {APP_UPDATE: "app_update"},
                    PlatformArch: {X86_64: "x86-64"},
                    PlatformNaclArch: {X86_64: "x86-64"},
                    PlatformOs: {WIN: "win"},
                    RequestUpdateCheckStatus: {NO_UPDATE: "no_update"}
                }
            };
            
            // 覆盖 notification 权限
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications' ?
                    Promise.resolve({ state: Notification.permission }) :
                    originalQuery(parameters)
            );
            
            // 覆盖 canvas 指纹（简单的噪声）
            const originalToDataURL = HTMLCanvasElement.prototype.toDataURL;
            HTMLCanvasElement.prototype.toDataURL = function(type) {
                if (this.width > 16 && this.height > 16) {
                    const ctx = this.getContext('2d');
                    ctx.fillStyle = '#f0f0f0';
                    ctx.fillRect(0, 0, 1, 1);
                }
                return originalToDataURL.apply(this, arguments);
            };
        """)
        
        page = await context.new_page()
        page.set_default_timeout(60000)
        
        try:
            # ========== 步骤 1: 访问登录页面 ==========
            print("🌐 正在访问登录页面...")
            await page.goto(LOGIN_URL, wait_until='networkidle')
            await random_delay(2.0, 3.0)
            
            await page.screenshot(path='step1.png', full_page=True)
            await send_telegram_photo('step1.png', '📸 步骤1: 页面加载')
            
            # ========== 步骤 2: 处理 CF 验证 ==========
            cf_result = await handle_turnstile_challenge(page)
            if not cf_result:
                raise Exception("CF 验证失败")
            
            await random_delay(1.0, 2.0)
            
            # ========== 步骤 3: 填写表单 ==========
            print("🔐 填写登录信息...")
            
            # 邮箱
            email_sel = 'input[type="email"]'
            await page.wait_for_selector(email_sel, state='visible')
            await human_like_click(page, email_sel)
            await page.keyboard.type(LOGIN_EMAIL, delay=random.randint(50, 150))
            await random_delay(0.5, 1.0)
            
            await page.screenshot(path='step2.png', full_page=True)
            await send_telegram_photo('step2.png', '📸 步骤2: 填写邮箱')
            
            # 密码
            pwd_sel = 'input[type="password"]'
            await human_like_click(page, pwd_sel)
            await page.keyboard.type(LOGIN_PASSWORD, delay=random.randint(50, 150))
            await random_delay(0.5, 1.0)
            
            await page.screenshot(path='step3.png', full_page=True)
            await send_telegram_photo('step3.png', '📸 步骤3: 填写密码')
            
            # ========== 步骤 4: 点击登录 ==========
            print("🖱️ 点击登录...")
            await human_like_click(page, 'button[type="submit"]')
            await random_delay(3.0, 5.0)
            
            await page.screenshot(path='step4.png', full_page=True)
            await send_telegram_photo('step4.png', '📸 步骤4: 点击登录后')
            
            # 检查是否再次出现 CF 验证
            cf_result2 = await handle_turnstile_challenge(page)
            if not cf_result2:
                raise Exception("登录后验证失败")
            
            # ========== 步骤 5: Continue to dashboard ==========
            print("🖱️ 查找 Continue...")
            await page.wait_for_selector('text=Continue to dashboard', timeout=15000)
            await human_like_click(page, 'button:has-text("Continue to dashboard")')
            await random_delay(3.0, 4.0)
            
            await page.screenshot(path='step5.png', full_page=True)
            await send_telegram_photo('step5.png', '📸 步骤5: Continue后')
            
            # ========== 步骤 6: Open Panel ==========
            print("🖱️ 查找 Open Panel...")
            await page.wait_for_selector('text=Open Panel', timeout=15000)
            await human_like_click(page, 'button:has-text("Open Panel")')
            await random_delay(5.0, 7.0)
            
            # 检查新标签页
            pages = context.pages
            if len(pages) > 1:
                page = pages[-1]
                print(f"🔗 切换到新页面: {page.url}")
                await random_delay(3.0, 5.0)
            
            await page.screenshot(path='step6.png', full_page=True)
            await send_telegram_photo('step6.png', '📸 步骤6: 控制面板')
            
            # ========== 步骤 7: 抓取数据 ==========
            print("📊 抓取数据...")
            await page.wait_for_selector('text=Uptime', timeout=15000)
            
            data = await extract_server_data(page)
            
            await page.screenshot(path='step7.png', full_page=True)
            
            msg = format_telegram_message(data)
            await send_telegram(msg)
            await send_telegram_photo('step7.png', '📸 完成')
            
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
    """提取数据"""
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
