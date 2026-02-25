# scripts/monitor_drission.py
import os
import time
import re
import requests
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
        print(f"⚠️ 截图不存在: {photo_path}")
        return
    
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
    try:
        with open(photo_path, 'rb') as f:
            data = {'chat_id': TELEGRAM_CHAT_ID, 'caption': caption}
            response = requests.post(url, data=data, files={'photo': f}, timeout=30)
            if response.status_code == 200:
                print(f"✅ 截图已发送: {caption[:50]}...")
            else:
                print(f"❌ 截图发送失败: {response.text}")
    except Exception as e:
        print(f"❌ 发送截图异常: {e}")

def send_telegram(message):
    """同步发送消息"""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message[:4096],
            "parse_mode": "Markdown"
        }
        response = requests.post(url, json=payload, timeout=30)
        if response.status_code == 200:
            print("✅ Telegram 消息发送成功")
        else:
            print(f"❌ Telegram 发送失败: {response.text}")
    except Exception as e:
        print(f"❌ 发送消息异常: {e}")

def handle_turnstile(page):
    """处理 CF 验证"""
    try:
        print("🔍 检查 Cloudflare 验证...")
        iframe = page.ele('css:iframe[src*="cloudflare"], iframe[src*="turnstile"], iframe[src*="challenges"]', timeout=5)
        
        if iframe:
            print("✅ 发现 CF iframe，开始处理...")
            frame_doc = page.get_frame(iframe)
            
            if frame_doc:
                # 方法1: 点击 body
                try:
                    body = frame_doc.ele('tag:body', timeout=3)
                    if body:
                        body.click()
                        print("🖱️ 点击 iframe body")
                        time.sleep(1)
                except Exception as e:
                    print(f"⚠️ 点击 body 失败: {e}")
                
                # 方法2: 点击 checkbox
                try:
                    cb = frame_doc.ele('@type=checkbox', timeout=3)
                    if cb:
                        cb.click()
                        print("🖱️ 点击 checkbox")
                        time.sleep(3)
                except Exception as e:
                    print(f"⚠️ 点击 checkbox 失败: {e}")
                
                return True
            else:
                print("❌ 无法进入 iframe")
        else:
            print("ℹ️ 未发现 CF 验证")
            
    except Exception as e:
        print(f"ℹ️ 无验证或处理失败: {e}")
    
    return False

def take_screenshot(page, name):
    """截图辅助函数"""
    try:
        filename = f"{name}.png"
        page.get_screenshot(path=filename, full_page=True)
        print(f"📸 已截图: {filename}")
        return filename
    except Exception as e:
        print(f"❌ 截图失败: {e}")
        return None

def extract_data(page):
    """提取服务器数据"""
    data = {
        'uptime': 'N/A',
        'cpu_load': 'N/A',
        'memory': 'N/A',
        'disk': 'N/A',
        'address': 'N/A'
    }
    
    try:
        # 方法1: 通过文本查找（DrissionPage 语法）
        try:
            uptime_ele = page.ele('text=Uptime', timeout=2)
            if uptime_ele:
                # 找父元素的下一个兄弟或子元素
                parent = uptime_ele.parent()
                if parent:
                    # 尝试找同级 div
                    siblings = parent.eles('tag:div')
                    for sib in siblings:
                        text = sib.text
                        if 'h' in text and 'm' in text:
                            data['uptime'] = text.strip()
                            break
        except:
            pass
        
        # 方法2: 正则提取整个页面文本
        page_text = page.html  # 或 page.text
        
        patterns = {
            'uptime': r'(\d+d?\s*\d+h\s+\d+m\s+\d+s|\d+h\s+\d+m\s+\d+s)',
            'cpu_load': r'CPU\s*Load\s*[\n\r\s]*([\d.]+%?\s*/\s*[\d.]+%?)',
            'memory': r'Memory\s*[\n\r\s]*([\d.]+\s*MiB?\s*/\s*[\d.]+\s*MiB?)',
            'disk': r'Disk\s*[\n\r\s]*([\d.]+\s*MiB?\s*/\s*[\d.]+\s*MiB?)',
            'address': r'(node\d+\.lunes\.host:\d+)'
        }
        
        for key, pattern in patterns.items():
            if data[key] == 'N/A':
                matches = re.findall(pattern, page_text)
                if matches:
                    data[key] = matches[0]
                    print(f"✅ 提取到 {key}: {data[key]}")
                    
    except Exception as e:
        print(f"⚠️ 提取数据警告: {e}")
    
    return data

def monitor():
    """主函数"""
    print("🚀 开始监控...")
    
    # 初始化浏览器
    co = ChromiumOptions()
    
    # GitHub Actions 环境配置
    if os.getenv('GITHUB_ACTIONS') == 'true':
        print("🔧 GitHub Actions 环境 detected")
        co.set_browser_path('/usr/bin/google-chrome')
        co.set_argument('--no-sandbox')
        co.set_argument('--disable-gpu')
        co.set_argument('--disable-dev-shm-usage')
        co.set_argument('--disable-setuid-sandbox')
    else:
        # 本地环境
        co.set_argument('--no-sandbox')
    
    co.set_argument('--window-size=1920,1080')
    co.set_argument('--start-maximized')
    co.set_argument('--disable-blink-features=AutomationControlled')
    
    page = ChromiumPage(co)
    page.set.timeouts(10)
    
    screenshots = []
    
    try:
        # ========== 步骤 1: 访问登录页 ==========
        print("🌐 访问登录页...")
        page.get("https://betadash.lunes.host/login?next=/")
        time.sleep(3)
        
        shot = take_screenshot(page, "step1_login")
        if shot:
            screenshots.append(shot)
            send_telegram_photo(shot, "📸 步骤1: 登录页")
        
        # ========== 步骤 2: 处理 CF 验证 ==========
        handle_turnstile(page)
        
        # ========== 步骤 3: 填写账号 ==========
        print("🔐 填写账号...")
        
        # 等待并填写
        email_input = page.ele('css:input[type="email"]', timeout=10)
        email_input.input(EMAIL)
        time.sleep(0.5)
        
        pwd_input = page.ele('css:input[type="password"]', timeout=10)
        pwd_input.input(PASSWORD)
        time.sleep(0.5)
        
        shot = take_screenshot(page, "step2_filled")
        if shot:
            screenshots.append(shot)
            send_telegram_photo(shot, "📸 步骤2: 已填账号")
        
        # ========== 步骤 4: 登录前验证 + 点击登录 ==========
        handle_turnstile(page)
        
        print("🖱️ 点击登录...")
        login_btn = page.ele('css:button[type="submit"]', timeout=10)
        login_btn.click()
        time.sleep(5)
        
        shot = take_screenshot(page, "step3_after_login")
        if shot:
            screenshots.append(shot)
            send_telegram_photo(shot, "📸 步骤3: 点击登录后")
        
        # ========== 步骤 5: 处理登录后验证 ==========
        handle_turnstile(page)
        
        # ========== 步骤 6: 点击 Continue to dashboard ==========
        print("🖱️ 点击 Continue to dashboard...")
        
        # 等待按钮（多种选择器）
        continue_btn = None
        for selector in [
            'text=Continue to dashboard',
            'button:has-text("Continue")',
            'a:has-text("Continue to dashboard")'
        ]:
            try:
                continue_btn = page.ele(selector, timeout=5)
                if continue_btn:
                    print(f"✅ 找到 Continue 按钮: {selector}")
                    break
            except:
                continue
        
        if not continue_btn:
            raise Exception("未找到 Continue to dashboard 按钮")
        
        continue_btn.click()
        time.sleep(5)
        
        shot = take_screenshot(page, "step4_dashboard")
        if shot:
            screenshots.append(shot)
            send_telegram_photo(shot, "📸 步骤4: Dashboard")
        
        # ========== 步骤 7: 点击 Open Panel ==========
        print("🖱️ 点击 Open Panel...")
        
        open_panel_btn = None
        for selector in [
            'text=Open Panel',
            'button:has-text("Open Panel")',
            'a:has-text("Open Panel")'
        ]:
            try:
                open_panel_btn = page.ele(selector, timeout=5)
                if open_panel_btn:
                    print(f"✅ 找到 Open Panel 按钮: {selector}")
                    break
            except:
                continue
        
        if not open_panel_btn:
            raise Exception("未找到 Open Panel 按钮")
        
        open_panel_btn.click()
        time.sleep(5)
        
        # ========== 步骤 8: 切换到新标签页 ==========
        print("🔄 检查新标签页...")
        tabs = page.tabs
        print(f"📑 当前有 {len(tabs)} 个标签页")
        
        if len(tabs) > 1:
            page = tabs[-1]  # 切换到最新标签页
            print(f"🔗 切换到新标签: {page.url}")
            time.sleep(3)
        
        shot = take_screenshot(page, "step5_panel")
        if shot:
            screenshots.append(shot)
            send_telegram_photo(shot, "📸 步骤5: 控制面板")
        
        # ========== 步骤 9: 抓取数据 ==========
        print("📊 抓取数据...")
        time.sleep(3)  # 等待数据加载
        
        data = extract_data(page)
        
        # 最终截图
        shot = take_screenshot(page, "step6_final")
        if shot:
            screenshots.append(shot)
        
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

✅ 自动检查完成
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
