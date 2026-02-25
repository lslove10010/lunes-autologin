# scripts/monitor_drission.py
import os
import time
import re
import requests
import tempfile
from datetime import datetime
from DrissionPage import ChromiumPage, ChromiumOptions

# 配置
EMAIL = os.environ['LOGIN_EMAIL']
PASSWORD = os.environ['LOGIN_PASSWORD']
TELEGRAM_BOT_TOKEN = os.environ['TELEGRAM_BOT_TOKEN']
TELEGRAM_CHAT_ID = os.environ['TELEGRAM_CHAT_ID']

def send_telegram_photo(photo_path, caption=""):
    """同步发送截图"""
    if not os.path.exists(photo_path):
        return
    
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
    try:
        with open(photo_path, 'rb') as f:
            data = {'chat_id': TELEGRAM_CHAT_ID, 'caption': caption}
            requests.post(url, data=data, files={'photo': f}, timeout=30)
            print(f"✅ 截图已发送: {caption[:50]}...")
    except Exception as e:
        print(f"❌ 发送截图异常: {e}")

def send_telegram(message):
    """同步发送消息"""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        requests.post(url, json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message[:4096],
            "parse_mode": "Markdown"
        }, timeout=30)
        print("✅ Telegram 消息发送成功")
    except Exception as e:
        print(f"❌ 发送消息异常: {e}")

def handle_turnstile(page):
    """
    完全按照你参考代码的逻辑处理 CF 验证
    关键点：快速尝试，不等待，失败就跳过
    """
    try:
        # 快速查找 iframe，5秒超时
        iframe = page.ele('css:iframe[src*="cloudflare"]', timeout=5)
        if iframe:
            print("✅ 发现 CF iframe")
            frame_doc = page.get_frame(iframe)
            if frame_doc:
                # 先点击 body
                frame_doc.ele('tag:body').click()
                print("🖱️ 点击 iframe body")
                
                # 再点击 checkbox
                cb = frame_doc.ele('@type=checkbox')
                if cb:
                    cb.click()
                    print("🖱️ 点击 checkbox")
                
                time.sleep(3)  # 等待验证完成
                return True
    except Exception as e:
        # 你的代码这里直接 pass，不处理异常
        print(f"ℹ️ CF处理: {e}")
        pass
    
    return False

def take_screenshot(page, name):
    """截图"""
    try:
        filename = f"{name}.png"
        page.get_screenshot(path=filename, full_page=True)
        print(f"📸 已截图: {filename}")
        return filename
    except Exception as e:
        print(f"❌ 截图失败: {e}")
        return None

def extract_data(page):
    """提取数据"""
    data = {
        'uptime': 'N/A',
        'cpu_load': 'N/A',
        'memory': 'N/A',
        'disk': 'N/A',
        'address': 'N/A'
    }
    
    try:
        page_text = page.html
        patterns = {
            'uptime': r'(\d+d?\s*\d+h\s+\d+m\s+\d+s|\d+h\s+\d+m\s+\d+s)',
            'cpu_load': r'CPU\s*Load\s*[\n\r\s]*([\d.]+%?\s*/\s*[\d.]+%?)',
            'memory': r'Memory\s*[\n\r\s]*([\d.]+\s*MiB?\s*/\s*[\d.]+\s*MiB?)',
            'disk': r'Disk\s*[\n\r\s]*([\d.]+\s*MiB?\s*/\s*[\d.]+\s*MiB?)',
            'address': r'(node\d+\.lunes\.host:\d+)'
        }
        
        for key, pattern in patterns.items():
            matches = re.findall(pattern, page_text)
            if matches:
                data[key] = matches[0]
                print(f"✅ 提取到 {key}: {data[key]}")
    except Exception as e:
        print(f"⚠️ 提取警告: {e}")
    
    return data

def monitor():
    """主函数 - 完全按照你参考代码的逻辑"""
    print("🚀 开始监控...")
    
    # 初始化浏览器 - 参考你的代码配置
    co = ChromiumOptions()
    
    if os.getenv('GITHUB_ACTIONS') == 'true':
        print("🔧 GitHub Actions 环境")
        co.set_browser_path('/usr/bin/google-chrome')
        co.set_argument('--no-sandbox')
        co.set_argument('--disable-gpu')
        co.set_argument('--window-size=1920,1080')
        co.set_argument('--start-maximized')
        co.set_argument('--lang=zh-CN')
        
        # 无界面模式（关键）
        co.set_argument('--headless=new')
        co.set_argument('--disable-dev-shm-usage')
        co.set_argument('--disable-setuid-sandbox')
        co.set_argument('--remote-debugging-port=9222')
        
        # 用户数据目录
        user_data_dir = tempfile.mkdtemp()
        co.set_user_data_path(user_data_dir)
    else:
        co.set_argument('--no-sandbox')
        co.set_argument('--window-size=1920,1080')
    
    page = ChromiumPage(co)
    page.set.timeouts(10)
    
    try:
        # ========== 步骤 1: 访问登录页 ==========
        print("1. 访问登录页...")
        page.get("https://betadash.lunes.host/login?next=/")
        time.sleep(3)  # 等待页面和验证加载
        
        # ========== 步骤 2: 立即处理 CF 验证（关键！在填表前） ==========
        print("2. 处理 CF 验证...")
        handle_turnstile(page)
        
        # ========== 步骤 3: 填写账号 ==========
        print("3. 填写账号...")
        page.ele('css:input[type="email"]').input(EMAIL)
        page.ele('css:input[type="password"]').input(PASSWORD)
        
        # 截图1: 登录前
        shot = take_screenshot(page, "step1_login")
        if shot:
            send_telegram_photo(shot, "📸 登录前")
        
        # ========== 步骤 4: 登录前再次处理 CF，然后点击登录 ==========
        print("4. 点击登录...")
        handle_turnstile(page)  # 再次处理，防止新出现的验证
        page.ele('css:button[type="submit"]').click()
        
        print("5. 等待跳转...")
        time.sleep(5)
        
        # ========== 步骤 5: 检查是否需要二次点击（参考你的代码逻辑） ==========
        login_success = False
        
        # 检查是否在 dashboard 或 servers 页面
        if "dashboard" in page.url or "servers" in page.url:
            login_success = True
            print("✅ 登录成功（已在 dashboard）")
        elif "login" in page.url:
            print("⚠️ 仍在登录页，尝试二次处理...")
            handle_turnstile(page)
            time.sleep(2)
            
            # 再次点击登录
            try:
                page.ele('css:button[type="submit"]').click()
                time.sleep(5)
                
                if "dashboard" in page.url or "servers" in page.url:
                    login_success = True
                    print("✅ 二次登录成功")
            except:
                pass
        
        if not login_success:
            # 检查是否有 Continue 按钮（说明已登录但需确认）
            try:
                page.ele('text=Continue to dashboard', timeout=3)
                login_success = True
                print("✅ 发现 Continue 按钮，登录成功")
            except:
                pass
        
        if not login_success:
            raise Exception("登录失败")
        
        # 截图2: 登录成功
        shot = take_screenshot(page, "step2_logged_in")
        if shot:
            send_telegram_photo(shot, "📸 登录成功")
        
        # ========== 步骤 6: 点击 Continue to dashboard ==========
        print("6. 点击 Continue...")
        
        try:
            continue_btn = page.ele('text=Continue to dashboard', timeout=5)
            continue_btn.click()
            time.sleep(3)
        except:
            print("ℹ️ 无需点击 Continue，继续...")
        
        # 截图3: Dashboard
        shot = take_screenshot(page, "step3_dashboard")
        if shot:
            send_telegram_photo(shot, "📸 Dashboard")
        
        # ========== 步骤 7: 点击 Open Panel ==========
        print("7. 点击 Open Panel...")
        
        # 查找服务器卡片（参考第二张图的结构）
        # 可能需要先找到 webapphost 卡片
        try:
            # 尝试直接点击 Open Panel
            open_panel = page.ele('text=Open Panel', timeout=10)
            open_panel.click()
            time.sleep(5)
        except:
            # 如果找不到，可能需要先点击服务器卡片
            print("🔄 尝试查找服务器卡片...")
            try:
                # 根据第二张图，点击 webapphost 卡片进入
                webapphost = page.ele('text=webapphost', timeout=5)
                webapphost.click()
                time.sleep(3)
                
                # 然后再找 Open Panel
                open_panel = page.ele('text=Open Panel', timeout=5)
                open_panel.click()
                time.sleep(5)
            except Exception as e:
                print(f"⚠️ 查找 Open Panel 失败: {e}")
                raise
        
        # ========== 步骤 8: 切换到新标签页 ==========
        print("8. 检查新标签页...")
        tabs = page.tabs
        print(f"📑 当前有 {len(tabs)} 个标签页")
        
        if len(tabs) > 1:
            page = tabs[-1]
            print(f"🔗 切换到新标签: {page.url}")
            time.sleep(3)
        
        # 截图4: 控制面板
        shot = take_screenshot(page, "step4_panel")
        if shot:
            send_telegram_photo(shot, "📸 控制面板")
        
        # ========== 步骤 9: 抓取数据 ==========
        print("9. 抓取数据...")
        time.sleep(3)
        
        data = extract_data(page)
        
        # 最终截图
        shot = take_screenshot(page, "step5_final")
        
        # ========== 步骤 10: 发送报告 ==========
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        msg = f"""🖥️ *Lunes Server 监控报告*

📅 `{now}`

📌 *服务器*
• 地址: `{data.get('address', 'N/A')}`

📊 *资源使用*
⏱️ Uptime: `{data.get('uptime', 'N/A')}`
🔄 CPU Load: `{data.get('cpu_load', 'N/A')}`
💾 Memory: `{data.get('memory', 'N/A')}`
💿 Disk: `{data.get('disk', 'N/A')}`

✅ 完成
"""
        send_telegram(msg)
        
        if shot:
            send_telegram_photo(shot, "📸 最终状态")
        
        print("✅ 全部完成！")
        return True
        
    except Exception as e:
        error_msg = f"❌ 监控失败: {str(e)}"
        print(error_msg)
        
        try:
            error_shot = take_screenshot(page, "error")
            if error_shot:
                send_telegram_photo(error_shot, f"❌ 错误: {str(e)}")
        except:
            pass
        
        send_telegram(error_msg)
        return False
        
    finally:
        print("🧹 清理浏览器...")
        page.quit()

if __name__ == "__main__":
    success = monitor()
    exit(0 if success else 1)
