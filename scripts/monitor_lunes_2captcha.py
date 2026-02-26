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

# ==================== 2Captcha HTTP API模块（Cloudflare Challenge版） ====================
class TwoCaptchaHTTP:
    def __init__(self, api_key):
        self.api_key = api_key
        self.base_url = "http://2captcha.com"
    
    def solve_turnstile_challenge(self, sitekey, pageurl, action, data, pagedata, useragent):
        """
        解决Cloudflare Challenge页面的Turnstile
        需要额外参数：action, data(cData), pagedata(chlPageData)
        """
        print(f"🤖 请求2captcha解决Turnstile Challenge...")
        print(f"   Site Key: {sitekey}")
        print(f"   URL: {pageurl}")
        print(f"   Action: {action}")
        print(f"   Data: {data[:20] if data else 'N/A'}...")
        print(f"   PageData: {pagedata[:20] if pagedata else 'N/A'}...")
        
        # 提交任务 - 使用Cloudflare Challenge所需的所有参数
        submit_url = f"{self.base_url}/in.php"
        payload = {
            'key': self.api_key,
            'method': 'turnstile',
            'sitekey': sitekey,
            'pageurl': pageurl,
            'action': action,
            'data': data,
            'pagedata': pagedata,
            'userAgent': useragent,
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
        self.cf_params = None  # 存储拦截到的CF参数
    
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
    
    def inject_intercept_script(self):
        """
        注入JavaScript拦截turnstile.render调用
        这是解决Cloudflare Challenge的关键！
        """
        intercept_script = """
        (function() {
            console.log('🔧 注入拦截脚本...');
            
            const i = setInterval(() => {
                if (window.turnstile) {
                    console.log('✅ 检测到window.turnstile，开始拦截...');
                    clearInterval(i);
                    
                    // 保存原始render方法
                    const originalRender = window.turnstile.render;
                    
                    // 重写render方法
                    window.turnstile.render = function(a, b) {
                        console.log('🎯 拦截到turnstile.render调用');
                        
                        // 提取参数
                        const params = {
                            sitekey: b.sitekey,
                            pageurl: window.location.href,
                            data: b.cData || '',
                            pagedata: b.chlPageData || '',
                            action: b.action || '',
                            userAgent: navigator.userAgent
                        };
                        
                        // 保存到全局变量
                        window.cfParams = params;
                        window.cfCallback = b.callback;
                        
                        console.log('📦 拦截到的参数:', JSON.stringify(params));
                        
                        // 调用原始方法（让widget正常渲染）
                        return originalRender ? originalRender.apply(this, arguments) : null;
                    };
                    
                    console.log('✅ 拦截脚本注入完成');
                }
            }, 50);
        })();
        """
        
        try:
            self.page.run_js(intercept_script)
            print("✅ 拦截脚本已注入")
            time.sleep(2)  # 等待脚本生效
            return True
        except Exception as e:
            print(f"❌ 注入拦截脚本失败: {e}")
            return False
    
    def get_intercepted_params(self):
        """获取拦截到的CF参数"""
        try:
            # 从页面读取拦截到的参数
            result = self.page.run_js('() => { return window.cfParams || null; }')
            if result:
                self.cf_params = result
                print(f"✅ 获取到拦截参数: {result}")
                return result
            return None
        except Exception as e:
            print(f"⚠️ 获取拦截参数失败: {e}")
            return None
    
    def execute_cf_callback(self, token):
        """
        执行CF回调函数 - 这是通过验证的关键！
        调用 window.cfCallback(token) 让页面知道验证已完成
        """
        try:
            print("🚀 执行CF回调函数...")
            
            # 方法1: 直接调用cfCallback
            result = self.page.run_js(f"""
                (function() {{
                    if (window.cfCallback) {{
                        window.cfCallback('{token}');
                        return 'cfCallback executed';
                    }}
                    return 'cfCallback not found';
                }})()
            """)
            print(f"   方法1结果: {result}")
            
            if 'executed' in result:
                return True
            
            # 方法2: 调用turnstileCallback
            result = self.page.run_js(f"""
                (function() {{
                    if (window.turnstileCallback) {{
                        window.turnstileCallback('{token}');
                        return 'turnstileCallback executed';
                    }}
                    return 'turnstileCallback not found';
                }})()
            """)
            print(f"   方法2结果: {result}")
            
            if 'executed' in result:
                return True
            
            # 方法3: 填充表单字段并触发表单提交
            result = self.page.run_js(f"""
                (function() {{
                    // 查找并填充隐藏的response字段
                    const inputs = document.querySelectorAll('input[name="cf-turnstile-response"], textarea[name="cf-turnstile-response"]');
                    inputs.forEach(input => {{
                        input.value = '{token}';
                        input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                        input.dispatchEvent(new Event('change', {{ bubbles: true }}));
                    }});
                    
                    // 触发验证完成事件
                    window.dispatchEvent(new CustomEvent('turnstileSolved', {{ detail: {{ token: '{token}' }} }}));
                    
                    return 'form fields filled: ' + inputs.length;
                }})()
            """)
            print(f"   方法3结果: {result}")
            
            return True
            
        except Exception as e:
            print(f"❌ 执行回调失败: {e}")
            return False
    
    def handle_cloudflare_challenge(self):
        """
        处理Cloudflare Challenge验证 - 完整流程
        1. 注入拦截脚本
        2. 刷新页面让脚本生效
        3. 获取拦截的参数
        4. 使用2captcha解决
        5. 执行回调函数
        """
        print("🛡️ 开始处理Cloudflare Challenge...")
        
        # 步骤1: 注入拦截脚本
        self.inject_intercept_script()
        
        # 步骤2: 刷新页面以触发拦截
        print("🔄 刷新页面以捕获参数...")
        self.page.refresh()
        time.sleep(5)
        
        self.screenshot("01_cf_detected")
        
        # 步骤3: 获取拦截的参数
        params = None
        for i in range(10):  # 最多等待10次
            params = self.get_intercepted_params()
            if params:
                break
            time.sleep(1)
        
        if not params:
            raise Exception("未能拦截到CF参数")
        
        # 步骤4: 使用2captcha解决（使用完整参数）
        token = self.cf_solver.solve_turnstile_challenge(
            sitekey=params['sitekey'],
            pageurl=params['pageurl'],
            action=params['action'],
            data=params['data'],
            pagedata=params['pagedata'],
            useragent=params['userAgent']
        )
        
        # 步骤5: 执行回调函数（关键！）
        self.execute_cf_callback(token)
        
        # 等待验证生效
        time.sleep(3)
        
        print("✅ Cloudflare Challenge处理完成")
        self.screenshot("02_cf_solved")
        return True
    
    def login(self):
        """
        正确登录流程：
        1. 访问登录页
        2. 处理CF Challenge（拦截参数->解决->回调）
        3. 填写邮箱和密码
        4. 点击 Continue to dashboard
        """
        print("\n🔐 开始登录流程...")
        
        # 步骤1: 访问登录页
        print(f"🌐 访问: {LUNES_LOGIN_URL}")
        self.page.get(LUNES_LOGIN_URL)
        time.sleep(3)
        
        # 步骤2: 处理CF Challenge（在填表前完成！）
        print("🛡️ 处理Cloudflare Challenge...")
        self.handle_cloudflare_challenge()
        
        # 截图：验证通过后
        self.screenshot("03_after_cf")
        self.wx_bot.send_image(self.screenshots[-1])
        
        # 步骤3: 填写表单
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
        
        self.screenshot("04_form_filled")
        
        # 步骤4: 点击 Continue to dashboard
        print("🖱️ 点击 Continue to dashboard...")
        try:
            continue_btn = self.page.ele('text=Continue to dashboard', timeout=10)
            continue_btn.click()
            print("   ✅ 已点击 Continue")
        except Exception as e:
            # 备用：尝试submit按钮
            try:
                submit_btn = self.page.ele('css:button[type="submit"]', timeout=5)
                submit_btn.click()
                print("   ⚠️ 点击了submit按钮（备用）")
            except:
                raise Exception(f"点击按钮失败: {e}")
        
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
        
        self.screenshot("05_dashboard")
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
        
        final_shot = self.screenshot("06_final")
        if final_shot:
            self.wx_bot.send_image(final_shot)
        
        self.wx_bot.send_text(f"✅ Lunes监控完成\n时间: {now}")

# ==================== 主程序 ====================
def main():
    print(f"\n{'='*50}")
    print(f"🚀 Lunes Server Monitor - Cloudflare Challenge版")
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
        
        # 登录（先过CF Challenge，再填表）
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
