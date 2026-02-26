# scripts/monitor_lunes_2captcha.py
import os
import time
import re
import json
import base64
import hashlib
import tempfile
import requests
from datetime import datetime
from DrissionPage import ChromiumPage, ChromiumOptions

# ==================== 配置区域 ====================
EMAIL = os.environ['LOGIN_EMAIL']
PASSWORD = os.environ['LOGIN_PASSWORD']
API_KEY_2CAPTCHA = os.environ['APIKEY_2CAPTCHA']
WECHAT_WEBHOOK_KEY = os.environ['WECHAT_WEBHOOK_KEY']

WECHAT_WEBHOOK_URL = f"https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={WECHAT_WEBHOOK_KEY}"
LUNES_LOGIN_URL = "https://betadash.lunes.host/login?next=/"

# ==================== 企业微信推送模块 ====================
class WeChatBot:
    def __init__(self, webhook_key):
        self.webhook_url = f"https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={webhook_key}"
    
    def send_text(self, content, mentioned_list=None):
        data = {
            "msgtype": "text",
            "text": {
                "content": content,
                "mentioned_list": mentioned_list or []
            }
        }
        return self._send(data)
    
    def send_markdown(self, content):
        data = {
            "msgtype": "markdown",
            "markdown": {"content": content}
        }
        return self._send(data)
    
    def send_image(self, image_path):
        try:
            with open(image_path, 'rb') as f:
                image_data = f.read()
            
            base64_data = base64.b64encode(image_data).decode('utf-8')
            md5 = hashlib.md5(image_data).hexdigest()
            
            data = {
                "msgtype": "image",
                "image": {
                    "base64": base64_data,
                    "md5": md5
                }
            }
            return self._send(data)
        except Exception as e:
            print(f"❌ 图片发送失败: {e}")
            return False
    
    def _send(self, data):
        try:
            response = requests.post(
                self.webhook_url,
                json=data,
                timeout=30,
                headers={'Content-Type': 'application/json'}
            )
            result = response.json()
            if result.get('errcode') == 0:
                print(f"✅ 企业微信发送成功: {data.get('msgtype', 'unknown')}")
                return True
            else:
                print(f"❌ 企业微信错误: {result}")
                return False
        except Exception as e:
            print(f"❌ 发送异常: {e}")
            return False

# ==================== 2Captcha HTTP API模块 ====================
class TwoCaptchaHTTP:
    def __init__(self, api_key):
        self.api_key = api_key
        self.base_url = "http://2captcha.com"
    
    def solve_turnstile(self, sitekey, pageurl):
        """使用HTTP API解决Turnstile - 标准版本"""
        print(f"🤖 请求2captcha解决Turnstile...")
        print(f"   Site Key: {sitekey}")
        print(f"   URL: {pageurl}")
        
        # 提交任务
        submit_url = f"{self.base_url}/in.php"
        payload = {
            'key': self.api_key,
            'method': 'turnstile',
            'sitekey': sitekey,
            'pageurl': pageurl,
            'json': 1
        }
        
        print("   提交任务中...")
        response = requests.post(submit_url, data=payload, timeout=30)
        result = response.json()
        
        if result.get('status') != 1:
            raise Exception(f"提交任务失败: {result.get('request')}")
        
        task_id = result['request']
        print(f"   任务ID: {task_id}")
        
        # 轮询结果
        result_url = f"{self.base_url}/res.php"
        token = None
        
        for i in range(24):
            time.sleep(5)
            print(f"   轮询结果... ({i+1}/24)")
            
            params = {
                'key': self.api_key,
                'action': 'get',
                'id': task_id,
                'json': 1
            }
            
            response = requests.get(result_url, params=params, timeout=30)
            result = response.json()
            
            if result.get('status') == 1:
                token = result['request']
                print(f"✅ 获取到Token: {token[:60]}...")
                break
            
            if result.get('request') == 'CAPCHA_NOT_READY':
                continue
            
            raise Exception(f"获取结果失败: {result.get('request')}")
        
        if not token:
            raise Exception("Turnstile解决超时")
        
        return token

# ==================== 浏览器管理模块 ====================
class BrowserManager:
    def __init__(self, headless=True):
        self.headless = headless
        self.page = None
        self.user_data_dir = None
    
    def setup(self):
        """配置并启动浏览器"""
        co = ChromiumOptions()
        
        is_github_actions = os.getenv('GITHUB_ACTIONS') == 'true'
        
        if is_github_actions or self.headless:
            print("🔧 配置无头浏览器...")
            co.set_browser_path('/usr/bin/google-chrome')
            co.set_argument('--no-sandbox')
            co.set_argument('--disable-setuid-sandbox')
            co.set_argument('--disable-dev-shm-usage')
            co.set_argument('--disable-gpu')
            co.set_argument('--headless=new')
            co.set_argument('--window-size=1920,1080')
            co.set_argument('--disable-blink-features=AutomationControlled')
            co.set_argument('--disable-web-security')
            co.set_argument('--disable-features=IsolateOrigins,site-per-process')
            co.set_argument('--lang=zh-CN,zh,en')
            co.set_argument('--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
            co.set_argument('--remote-debugging-port=9222')
            
            self.user_data_dir = tempfile.mkdtemp()
            co.set_user_data_path(self.user_data_dir)
        else:
            co.set_argument('--window-size=1920,1080')
            co.set_argument('--disable-blink-features=AutomationControlled')
        
        self.page = ChromiumPage(co)
        self.page.set.timeouts(15)
        return self
    
    def get_page(self):
        return self.page
    
    def close(self):
        if self.page:
            try:
                self.page.quit()
            except:
                pass

# ==================== Lunes自动化模块 ====================
class LunesAutomation:
    def __init__(self, page, cf_solver, wx_bot):
        self.page = page
        self.cf_solver = cf_solver
        self.wx_bot = wx_bot
        self.screenshots = []
    
    def screenshot(self, name):
        """截图并保存"""
        try:
            filename = f"{name}_{datetime.now().strftime('%H%M%S')}.png"
            self.page.get_screenshot(path=filename, full_page=True)
            self.screenshots.append(filename)
            print(f"📸 截图: {filename}")
            return filename
        except Exception as e:
            print(f"❌ 截图失败: {e}")
            return None
    
    def find_turnstile_sitekey(self):
        """从页面中提取Turnstile sitekey"""
        try:
            # 方法1: 查找.cf-turnstile的data-sitekey
            sitekey = self.page.run_js('''
                () => {
                    const el = document.querySelector('.cf-turnstile');
                    return el ? el.dataset.sitekey : null;
                }
            ''')
            if sitekey:
                return sitekey
            
            # 方法2: 从HTML中正则提取
            html = self.page.html
            match = re.search(r'data-sitekey=["\']([^"\']+)["\']', html)
            if match:
                return match.group(1)
            
            # 方法3: 查找iframe
            iframe_match = re.search(r'challenges\.cloudflare\.com.*sitekey=([^&]+)', html)
            if iframe_match:
                return iframe_match.group(1)
                
        except Exception as e:
            print(f"⚠️ 提取sitekey失败: {e}")
        
        return None
    
    def inject_turnstile_token(self, token):
        """
        注入Token并触发验证完成
        参考能工作的JS代码逻辑
        """
        try:
            print("📝 注入Token到页面...")
            
            # 执行JS注入token - 参考能工作的代码
            result = self.page.run_js(f'''
                (function() {{
                    // 方法1: 填充textarea
                    const textarea = document.querySelector('textarea[name="cf-turnstile-response"]');
                    if (textarea) {{
                        textarea.value = '{token}';
                        textarea.dispatchEvent(new Event('input', {{ bubbles: true }}));
                        textarea.dispatchEvent(new Event('change', {{ bubbles: true }}));
                        return 'textarea filled';
                    }}
                    
                    // 方法2: 填充input
                    const input = document.querySelector('input[name="cf-turnstile-response"]');
                    if (input) {{
                        input.value = '{token}';
                        input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                        input.dispatchEvent(new Event('change', {{ bubbles: true }}));
                        return 'input filled';
                    }}
                    
                    // 方法3: 查找任何包含cf-turnstile的元素
                    const cfElements = document.querySelectorAll('[class*="cf-turnstile"], [id*="cf-turnstile"]');
                    for (let el of cfElements) {{
                        if (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA') {{
                            el.value = '{token}';
                            el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                            return 'cf element filled';
                        }}
                    }}
                    
                    // 方法4: 创建隐藏的input字段
                    const hiddenInput = document.createElement('input');
                    hiddenInput.type = 'hidden';
                    hiddenInput.name = 'cf-turnstile-response';
                    hiddenInput.value = '{token}';
                    document.body.appendChild(hiddenInput);
                    
                    return 'hidden input created';
                }})()
            ''')
            
            print(f"✅ Token注入结果: {result}")
            
            # 触发验证完成事件
            self.page.run_js(f'''
                window.dispatchEvent(new CustomEvent('turnstileSolved', {{ detail: {{ token: '{token}' }} }}));
            ''')
            
            return True
            
        except Exception as e:
            print(f"❌ Token注入失败: {e}")
            return False
    
    def click_cf_checkbox(self):
        """
        实际点击CF验证框的checkbox
        这是让验证显示"成功"的关键
        """
        try:
            print("🖱️ 尝试点击CF验证框...")
            
            # 查找iframe
            iframe = self.page.ele('css:iframe[src*="challenges.cloudflare"]', timeout=5)
            if iframe:
                print("   找到CF iframe，尝试点击...")
                
                # 切换到iframe
                frame_doc = self.page.get_frame(iframe)
                if frame_doc:
                    # 点击checkbox
                    checkbox = frame_doc.ele('css:input[type="checkbox"], .cb-c', timeout=3)
                    if checkbox:
                        checkbox.click()
                        print("   ✅ 点击了checkbox")
                        time.sleep(3)
                        return True
                    else:
                        # 尝试点击body
                        body = frame_doc.ele('tag:body', timeout=3)
                        if body:
                            body.click()
                            print("   ✅ 点击了iframe body")
                            time.sleep(3)
                            return True
            
            # 备用：直接点击.cf-turnstile元素
            turnstile = self.page.ele('css:.cf-turnstile', timeout=3)
            if turnstile:
                turnstile.click()
                print("   ✅ 点击了.cf-turnstile")
                time.sleep(3)
                return True
                
        except Exception as e:
            print(f"   ⚠️ 点击失败: {e}")
        
        return False
    
    def solve_and_inject_captcha(self):
        """解决验证码并注入 - 在填表后调用"""
        print("🛡️ 开始处理Cloudflare验证...")
        
        # 查找sitekey
        sitekey = self.find_turnstile_sitekey()
        if not sitekey:
            print("⚠️ 未找到sitekey，尝试直接点击验证框...")
            # 尝试直接点击
            if self.click_cf_checkbox():
                print("✅ 已通过点击完成验证")
                return True
            raise Exception("未找到Turnstile sitekey且点击失败")
        
        print(f"🔑 Site Key: {sitekey}")
        
        # 使用2captcha解决
        token = self.cf_solver.solve_turnstile(
            sitekey=sitekey,
            pageurl=self.page.url
        )
        
        if not token:
            raise Exception("获取token失败")
        
        # 注入token
        self.inject_turnstile_token(token)
        
        # 尝试点击验证框（让UI显示成功）
        self.click_cf_checkbox()
        
        # 等待验证生效
        time.sleep(3)
        
        print("✅ Cloudflare验证处理完成")
        return True
    
    def login(self):
        """
        正确登录流程（参考能工作的JS代码）：
        1. 访问登录页
        2. 填写邮箱和密码
        3. 解决CF验证（获取token并注入）
        4. 点击 Continue to dashboard
        """
        print("\n🔐 开始登录流程...")
        
        # 步骤1: 访问登录页
        print(f"🌐 访问: {LUNES_LOGIN_URL}")
        self.page.get(LUNES_LOGIN_URL)
        time.sleep(5)  # 等待页面完全加载
        
        self.screenshot("01_page_loaded")
        
        # 步骤2: 填写表单（先填表！）
        print("📝 填写登录信息...")
        try:
            # 填写邮箱
            email_input = self.page.ele('css:input[type="email"]', timeout=10)
            email_input.click()
            time.sleep(0.3)
            email_input.input(EMAIL)
            print(f"   ✅ 邮箱已填写")
            
            # 填写密码
            password_input = self.page.ele('css:input[type="password"]', timeout=10)
            password_input.click()
            time.sleep(0.3)
            password_input.input(PASSWORD)
            print(f"   ✅ 密码已填写")
            
        except Exception as e:
            raise Exception(f"填写表单失败: {e}")
        
        self.screenshot("02_form_filled")
        self.wx_bot.send_image(self.screenshots[-1])
        
        # 步骤3: 解决CF验证（填表后，点击按钮前！）
        print("🛡️ 处理CF人机验证...")
        self.solve_and_inject_captcha()
        
        self.screenshot("03_captcha_solved")
        self.wx_bot.send_image(self.screenshots[-1])
        
        # 步骤4: 点击 Continue to dashboard
        print("🖱️ 点击 Continue to dashboard...")
        try:
            # 主方法：通过文本查找
            continue_btn = self.page.ele('text=Continue to dashboard', timeout=10)
            continue_btn.click()
            print("   ✅ 已点击 Continue")
        except Exception as e:
            # 备用：查找按钮元素
            try:
                # 查找包含该文本的button或a标签
                btn = self.page.ele('css:button, css:a', timeout=5)
                if btn and 'dashboard' in btn.text.lower():
                    btn.click()
                    print("   ✅ 点击了dashboard按钮（备用）")
                else:
                    raise Exception("未找到Continue按钮")
            except Exception as e2:
                raise Exception(f"点击Continue失败: {e}, {e2}")
        
        # 等待跳转
        print("⏳ 等待页面跳转...")
        time.sleep(5)
        
        # 检查登录结果
        current_url = self.page.url
        title = self.page.title
        print(f"🔗 当前URL: {current_url}")
        print(f"📄 页面标题: {title}")
        
        # 判断成功
        if "login" not in current_url.lower():
            print("✅ 登录成功")
            return True
        
        if "dashboard" in current_url or "servers" in current_url:
            print("✅ 登录成功（在dashboard）")
            return True
        
        raise Exception(f"登录失败。URL: {current_url}, 标题: {title}")
    
    def navigate_to_server(self):
        """导航到服务器面板"""
        print("\n🖥️ 导航到服务器...")
        
        self.screenshot("04_after_login")
        self.wx_bot.send_image(self.screenshots[-1])
        
        # 查找服务器
        print("🔍 查找服务器...")
        selectors = [
            'text=webapphost',
            'text=Open Panel',
            'css:[data-server]',
            'css:.server-card',
            'css:[href*="panel"]'
        ]
        
        found = False
        for selector in selectors:
            try:
                elem = self.page.ele(selector, timeout=3)
                if elem:
                    print(f"✅ 找到元素: {selector}")
                    
                    if "Open Panel" in selector:
                        elem.click()
                    else:
                        elem.click()
                        time.sleep(2)
                        panel_btn = self.page.ele('text=Open Panel', timeout=5)
                        panel_btn.click()
                    
                    found = True
                    time.sleep(5)
                    break
            except:
                continue
        
        if not found:
            print("⚠️ 未找到服务器入口，可能已在目标页面")
        
        # 处理新标签页
        tabs = self.page.tabs
        if len(tabs) > 1:
            self.page = tabs[-1]
            print(f"🔗 切换到新标签: {self.page.url}")
            time.sleep(3)
        
        return self.page
    
    def extract_server_data(self):
        """提取服务器数据"""
        print("\n📊 提取数据...")
        time.sleep(3)
        
        data = {
            'uptime': 'N/A',
            'cpu_load': 'N/A',
            'memory': 'N/A',
            'disk': 'N/A',
            'address': 'N/A',
            'status': 'N/A'
        }
        
        try:
            html = self.page.html
            text = self.page.text
            
            patterns = {
                'uptime': r'Uptime[:\s]+(\d+d?\s+\d+h\s+\d+m\s+\d+s|\d+h\s+\d+m\s+\d+s)',
                'cpu_load': r'CPU\s*Load[:\s]+([\d.]+%?\s*/\s*[\d.]+%?)',
                'memory': r'Memory[:\s]+([\d.]+\s*(?:MiB|GiB|MB|GB)\s*/\s*[\d.]+\s*(?:MiB|GiB|MB|GB))',
                'disk': r'Disk[:\s]+([\d.]+\s*(?:MiB|GiB|MB|GB)\s*/\s*[\d.]+\s*(?:MiB|GiB|MB|GB))',
                'address': r'(node\d+\.lunes\.host:\d+)'
            }
            
            for key, pattern in patterns.items():
                matches = re.findall(pattern, html, re.IGNORECASE)
                if matches:
                    data[key] = matches[0]
                    print(f"   {key}: {data[key]}")
            
        except Exception as e:
            print(f"⚠️ 数据提取警告: {e}")
        
        return data
    
    def generate_report(self, data):
        """生成并发送报告"""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        report = f"""## 🖥️ Lunes Server 监控报告

📅 **时间**: `{now}`

📌 **服务器信息**
> 地址: `{data.get('address', 'N/A')}`
> 状态: `{data.get('status', 'Running')}`

📊 **资源使用**
> ⏱️ 运行时间: `{data.get('uptime', 'N/A')}`
> 🔄 CPU负载: `{data.get('cpu_load', 'N/A')}`
> 💾 内存使用: `{data.get('memory', 'N/A')}`
> 💿 磁盘使用: `{data.get('disk', 'N/A')}`

✅ **监控完成**
"""
        
        self.wx_bot.send_markdown(report)
        
        final_shot = self.screenshot("05_final")
        if final_shot:
            self.wx_bot.send_image(final_shot)
        
        self.wx_bot.send_text(f"✅ Lunes监控完成\n时间: {now}")

# ==================== 主程序 ====================
def main():
    print(f"\n{'='*50}")
    print(f"🚀 Lunes Server Monitor - 修复版")
    print(f"⏰ 启动时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*50}\n")
    
    # 初始化
    wx_bot = WeChatBot(WECHAT_WEBHOOK_KEY)
    cf_solver = TwoCaptchaHTTP(API_KEY_2CAPTCHA)
    browser = BrowserManager(headless=True)
    
    # 发送启动通知
    wx_bot.send_text(f"🚀 Lunes监控启动\n时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    try:
        # 启动浏览器
        browser.setup()
        page = browser.get_page()
        
        # 执行自动化
        lunes = LunesAutomation(page, cf_solver, wx_bot)
        
        # 登录（正确顺序：填表 -> 过CF -> 点击Continue）
        lunes.login()
        
        # 导航到服务器
        page = lunes.navigate_to_server()
        lunes.page = page
        
        # 提取数据
        data = lunes.extract_server_data()
        
        # 生成报告
        lunes.generate_report(data)
        
        print("\n✅ 监控流程完成")
        return True
        
    except Exception as e:
        error_msg = f"❌ 监控失败: {str(e)}"
        print(f"\n{error_msg}")
        
        # 错误截图
        try:
            if 'lunes' in locals():
                error_shot = lunes.screenshot("error")
                if error_shot:
                    wx_bot.send_image(error_shot)
        except:
            pass
        
        wx_bot.send_text(f"❌ Lunes监控异常\n错误: {str(e)}")
        return False
        
    finally:
        print("\n🧹 清理资源...")
        browser.close()
        # 清理截图
        try:
            for f in os.listdir('.'):
                if f.endswith('.png') and f[0].isdigit():
                    os.remove(f)
        except:
            pass

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
