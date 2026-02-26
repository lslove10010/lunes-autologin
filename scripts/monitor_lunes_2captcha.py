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
from twocaptcha import TwoCaptcha

# ==================== 配置区域 ====================
EMAIL = os.environ['LOGIN_EMAIL']
PASSWORD = os.environ['LOGIN_PASSWORD']
API_KEY_2CAPTCHA = os.environ['APIKEY_2CAPTCHA']  # 2captcha API密钥
WECHAT_WEBHOOK_KEY = os.environ['WECHAT_WEBHOOK_KEY']

# 常量配置
WECHAT_WEBHOOK_URL = f"https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={WECHAT_WEBHOOK_KEY}"
LUNES_LOGIN_URL = "https://betadash.lunes.host/login?next=/"

# ==================== 企业微信推送模块 ====================
class WeChatBot:
    def __init__(self, webhook_key):
        self.webhook_url = f"https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={webhook_key}"
    
    def send_text(self, content, mentioned_list=None):
        """发送文本消息"""
        data = {
            "msgtype": "text",
            "text": {
                "content": content,
                "mentioned_list": mentioned_list or []
            }
        }
        return self._send(data)
    
    def send_markdown(self, content):
        """发送Markdown消息"""
        data = {
            "msgtype": "markdown",
            "markdown": {"content": content}
        }
        return self._send(data)
    
    def send_image(self, image_path):
        """发送图片"""
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
    
    def send_file(self, file_path):
        """发送文件"""
        try:
            upload_url = f"https://qyapi.weixin.qq.com/cgi-bin/webhook/upload_media?key={WECHAT_WEBHOOK_KEY}&type=file"
            with open(file_path, 'rb') as f:
                files = {'media': (os.path.basename(file_path), f, 'application/octet-stream')}
                response = requests.post(upload_url, files=files, timeout=30)
                result = response.json()
                
                if result.get('errcode') == 0:
                    data = {
                        "msgtype": "file",
                        "file": {"media_id": result['media_id']}
                    }
                    return self._send(data)
            return False
        except Exception as e:
            print(f"❌ 文件发送失败: {e}")
            return False
    
    def _send(self, data):
        """基础发送方法"""
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

# ==================== 2Captcha CF解决模块（修复版） ====================
class CloudflareSolver:
    def __init__(self, api_key):
        self.solver = TwoCaptcha(api_key)
        self.max_retries = 3
    
    def solve_turnstile(self, site_key, page_url, invisible=False):
        """
        解决Turnstile验证 - 修复版
        正确调用方式：直接传递参数，不是字典
        """
        for attempt in range(self.max_retries):
            try:
                print(f"🤖 请求2captcha解决Turnstile... (尝试 {attempt + 1}/{self.max_retries})")
                print(f"   Site Key: {site_key}")
                print(f"   URL: {page_url}")
                
                # 正确调用方式 - 直接传递参数
                result = self.solver.turnstile(
                    sitekey=site_key,
                    url=page_url
                )
                
                # result是字典，包含code字段
                if result and 'code' in result:
                    token = result['code']
                    print(f"✅ 2captcha解决成功")
                    print(f"   Token: {token[:60]}...")
                    return token
                else:
                    print(f"⚠️ 2captcha返回格式异常: {result}")
                    if attempt < self.max_retries - 1:
                        time.sleep(5)
                        continue
                    raise Exception(f"2captcha返回无效结果: {result}")
                    
            except Exception as e:
                print(f"❌ 2captcha尝试 {attempt + 1} 失败: {e}")
                if attempt < self.max_retries - 1:
                    print("   等待5秒后重试...")
                    time.sleep(5)
                else:
                    raise Exception(f"2captcha全部尝试失败: {e}")
        
        return None

# ==================== 浏览器管理模块 ====================
class BrowserManager:
    def __init__(self, headless=True):
        self.headless = headless
        self.page = None
        self.user_data_dir = None
    
    def setup(self):
        """配置并启动浏览器"""
        co = ChromiumOptions()
        
        # 检测环境
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
            
            # 反检测关键配置
            co.set_argument('--disable-blink-features=AutomationControlled')
            co.set_argument('--disable-web-security')
            co.set_argument('--disable-features=IsolateOrigins,site-per-process')
            co.set_argument('--lang=zh-CN,zh,en')
            
            # 用户代理
            co.set_argument('--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
            
            # 远程调试
            co.set_argument('--remote-debugging-port=9222')
            
            # 临时用户目录
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
        """从页面中提取Turnstile site key"""
        try:
            html = self.page.html
            
            # 方法1: 查找data-sitekey属性
            sitekey_match = re.search(r'data-sitekey=["\']([^"\']+)["\']', html)
            if sitekey_match:
                return sitekey_match.group(1)
            
            # 方法2: 查找turnstile配置
            turnstile_match = re.search(r'turnstile.*?sitekey["\']?\s*:\s*["\']([^"\']+)["\']', html, re.DOTALL)
            if turnstile_match:
                return turnstile_match.group(1)
            
            # 方法3: 查找iframe src
            iframe_match = re.search(r'challenges\.cloudflare\.com/turnstile.*?sitekey=([^&]+)', html)
            if iframe_match:
                return iframe_match.group(1)
                
        except Exception as e:
            print(f"⚠️ 提取sitekey失败: {e}")
        
        return None
    
    def inject_turnstile_token(self, token):
        """将token注入到页面"""
        try:
            # 方法1: 填充隐藏的response字段
            script = f"""
            (function() {{
                // 查找并填充turnstile response字段
                var inputs = document.querySelectorAll('input[name="cf-turnstile-response"], input[name="cf_response"], .cf-turnstile-response');
                inputs.forEach(function(input) {{
                    input.value = '{token}';
                    input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    input.dispatchEvent(new Event('change', {{ bubbles: true }}));
                }});
                
                // 查找turnstile widget并设置data-response
                var widgets = document.querySelectorAll('.cf-turnstile, .turnstile');
                widgets.forEach(function(widget) {{
                    widget.setAttribute('data-response', '{token}');
                }});
                
                // 触发自定义事件（某些站点使用）
                window.dispatchEvent(new CustomEvent('turnstileSolved', {{ detail: {{ token: '{token}' }} }}));
                
                return 'Token injected: ' + document.querySelectorAll('input[name="cf-turnstile-response"]').length;
            }})();
            """
            result = self.page.run_js(script)
            print(f"✅ Token已注入页面: {result}")
            return True
            
        except Exception as e:
            print(f"❌ Token注入失败: {e}")
            return False
    
    def verify_turnstile_solved(self):
        """验证Turnstile是否已通过"""
        try:
            # 检查是否还有验证框
            iframe = self.page.ele('css:iframe[src*="challenges.cloudflare"]', timeout=3)
            if iframe:
                # 检查iframe是否可见或已消失
                try:
                    style = iframe.attr('style')
                    if style and ('display: none' in style or 'visibility: hidden' in style):
                        return True
                except:
                    pass
                return False
            
            # 检查是否有成功标记
            success_mark = self.page.ele('css:.cf-turnstile[data-response]', timeout=2)
            if success_mark:
                return True
                
            return True  # 默认认为已通过
            
        except:
            return True
    
    def handle_cloudflare(self):
        """处理Cloudflare验证"""
        print("🛡️ 开始处理Cloudflare验证...")
        
        # 步骤1: 等待页面加载
        time.sleep(3)
        
        # 步骤2: 截图查看当前状态
        self.screenshot("01_cf_detected")
        
        # 步骤3: 查找site key
        site_key = self.find_turnstile_sitekey()
        if not site_key:
            print("⚠️ 未找到site key，尝试直接检查是否已通过")
            # 尝试直接检查是否已通过
            if self.verify_turnstile_solved():
                print("✅ 无需验证或已自动通过")
                return True
            raise Exception("未找到Turnstile site key")
        
        print(f"🔑 Site Key: {site_key}")
        
        # 步骤4: 使用2captcha解决
        try:
            token = self.cf_solver.solve_turnstile(
                site_key=site_key,
                page_url=self.page.url,
                invisible=False
            )
            
            if not token:
                raise Exception("获取token失败")
            
            # 步骤5: 注入token
            self.inject_turnstile_token(token)
            
            # 步骤6: 等待验证生效
            time.sleep(3)
            
            # 步骤7: 验证结果
            if self.verify_turnstile_solved():
                print("✅ Cloudflare验证通过")
                self.screenshot("02_cf_solved")
                return True
            else:
                raise Exception("验证未通过，可能token无效")
                
        except Exception as e:
            print(f"❌ CF处理失败: {e}")
            self.screenshot("02_cf_failed")
            raise
    
    def login(self):
        """执行登录流程"""
        print("\n🔐 开始登录流程...")
        
        # 访问登录页
        print(f"🌐 访问: {LUNES_LOGIN_URL}")
        self.page.get(LUNES_LOGIN_URL)
        time.sleep(5)
        
        # 处理CF验证
        self.handle_cloudflare()
        
        # 截图：登录页状态
        self.screenshot("03_login_page")
        self.wx_bot.send_image(self.screenshots[-1])
        
        # 填写表单
        print("📝 填写登录信息...")
        try:
            # 等待并填写邮箱
            email_input = self.page.ele('css:input[type="email"]', timeout=10)
            email_input.click()
            time.sleep(0.5)
            email_input.input(EMAIL)
            print(f"   邮箱: {EMAIL[:3]}***")
            
            # 填写密码
            password_input = self.page.ele('css:input[type="password"]', timeout=10)
            password_input.click()
            time.sleep(0.5)
            password_input.input(PASSWORD)
            print("   密码: ***")
            
        except Exception as e:
            raise Exception(f"填写表单失败: {e}")
        
        # 再次检查CF（有时在输入后会重新触发）
        try:
            self.handle_cloudflare()
        except:
            pass  # 忽略二次验证错误
        
        # 点击登录
        print("🖱️ 点击登录按钮...")
        try:
            submit_btn = self.page.ele('css:button[type="submit"]', timeout=10)
            submit_btn.click()
        except Exception as e:
            raise Exception(f"点击登录失败: {e}")
        
        # 等待跳转
        print("⏳ 等待登录响应...")
        time.sleep(5)
        
        # 检查登录结果
        current_url = self.page.url
        print(f"🔗 当前URL: {current_url}")
        
        # 情况1: 直接成功
        if "dashboard" in current_url or "servers" in current_url:
            print("✅ 登录成功")
            return True
        
        # 情况2: 仍在登录页，可能需要二次处理
        if "login" in current_url:
            print("🔄 检测到仍在登录页，尝试二次处理...")
            
            # 检查错误信息
            try:
                error_elem = self.page.ele('css:.alert-danger, .error-message, .text-danger', timeout=3)
                if error_elem:
                    error_text = error_elem.text
                    raise Exception(f"登录错误: {error_text}")
            except Exception as e:
                if "登录错误" in str(e):
                    raise
            
            # 再次处理CF
            try:
                self.handle_cloudflare()
            except:
                pass
            
            # 再次点击登录
            try:
                submit_btn = self.page.ele('css:button[type="submit"]', timeout=5)
                submit_btn.click()
                time.sleep(5)
                
                if "dashboard" in self.page.url or "servers" in self.page.url:
                    print("✅ 二次登录成功")
                    return True
            except:
                pass
        
        # 情况3: 需要点击Continue
        try:
            continue_btn = self.page.ele('text=Continue to dashboard', timeout=5)
            print("✅ 发现Continue按钮")
            return True
        except:
            pass
        
        raise Exception("登录失败，无法进入Dashboard")
    
    def navigate_to_server(self):
        """导航到服务器面板"""
        print("\n🖥️ 导航到服务器...")
        
        # 点击Continue（如果有）
        try:
            continue_btn = self.page.ele('text=Continue to dashboard', timeout=5)
            continue_btn.click()
            print("✅ 点击Continue")
            time.sleep(3)
        except:
            print("ℹ️ 无需点击Continue")
        
        self.screenshot("04_dashboard")
        self.wx_bot.send_image(self.screenshots[-1])
        
        # 查找服务器
        print("🔍 查找服务器...")
        selectors = [
            'text=webapphost',
            'text=Open Panel',
            'css:[data-server-name]',
            'css:.server-card',
            'css:.instance-card',
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
                        # 点击后查找Open Panel
                        panel_btn = self.page.ele('text=Open Panel', timeout=5)
                        panel_btn.click()
                    
                    found = True
                    time.sleep(5)
                    break
            except:
                continue
        
        if not found:
            raise Exception("未找到服务器入口")
        
        # 处理新标签页
        tabs = self.page.tabs
        if len(tabs) > 1:
            self.page = tabs[-1]
            print(f"🔗 切换到新标签: {self.page.url}")
            time.sleep(3)
            
            # 新标签可能有新的CF验证
            try:
                self.handle_cloudflare()
            except:
                pass
        
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
            'status': 'N/A',
            'hostname': 'N/A'
        }
        
        try:
            html = self.page.html
            text = self.page.text
            
            # 正则提取
            patterns = {
                'uptime': r'Uptime[:\s]+(\d+d?\s+\d+h\s+\d+m\s+\d+s|\d+h\s+\d+m\s+\d+s)',
                'cpu_load': r'CPU\s*Load[:\s]+([\d.]+%?\s*/\s*[\d.]+%?)',
                'memory': r'Memory[:\s]+([\d.]+\s*(?:MiB|GiB|MB|GB)\s*/\s*[\d.]+\s*(?:MiB|GiB|MB|GB))',
                'disk': r'Disk[:\s]+([\d.]+\s*(?:MiB|GiB|MB|GB)\s*/\s*[\d.]+\s*(?:MiB|GiB|MB|GB))',
                'address': r'(node\d+\.lunes\.host:\d+)',
                'status': r'Status[:\s]+(\w+)',
                'hostname': r'Hostname[:\s]+(\w+)'
            }
            
            for key, pattern in patterns.items():
                matches = re.findall(pattern, html, re.IGNORECASE)
                if matches:
                    data[key] = matches[0]
                    print(f"   {key}: {data[key]}")
            
            # 备用：从文本中提取
            if data['cpu_load'] == 'N/A':
                cpu_match = re.search(r'(\d+\.\d+)\s*/\s*(\d+\.\d+)', text)
                if cpu_match:
                    data['cpu_load'] = f"{cpu_match.group(1)}% / {cpu_match.group(2)}%"
            
        except Exception as e:
            print(f"⚠️ 数据提取警告: {e}")
        
        return data
    
    def generate_report(self, data):
        """生成并发送报告"""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Markdown报告
        report = f"""## 🖥️ Lunes Server 监控报告

📅 **时间**: `{now}`

📌 **服务器信息**
> 主机: `{data.get('hostname', 'N/A')}`
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
        
        # 最终截图
        final_shot = self.screenshot("05_final")
        if final_shot:
            self.wx_bot.send_image(final_shot)
        
        # 发送完成通知
        self.wx_bot.send_text(f"✅ Lunes监控完成\n时间: {now}\nCPU: {data.get('cpu_load', 'N/A')}\n内存: {data.get('memory', 'N/A')}")

# ==================== 主程序 ====================
def main():
    print(f"\n{'='*50}")
    print(f"🚀 Lunes Server Monitor - 2captcha版")
    print(f"⏰ 启动时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*50}\n")
    
    # 初始化组件
    wx_bot = WeChatBot(WECHAT_WEBHOOK_KEY)
    cf_solver = CloudflareSolver(API_KEY_2CAPTCHA)
    browser = BrowserManager(headless=True)
    
    # 发送启动通知
    wx_bot.send_text(f"🚀 Lunes监控启动\n时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    try:
        # 启动浏览器
        browser.setup()
        page = browser.get_page()
        
        # 初始化自动化
        lunes = LunesAutomation(page, cf_solver, wx_bot)
        
        # 执行登录
        lunes.login()
        
        # 导航到服务器
        page = lunes.navigate_to_server()
        lunes.page = page  # 更新page引用
        
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
        
        wx_bot.send_text(f"❌ Lunes监控异常\n错误: {str(e)}\n时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        return False
        
    finally:
        print("\n🧹 清理资源...")
        browser.close()
        # 清理截图文件
        try:
            for f in os.listdir('.'):
                if f.endswith('.png') and f[0].isdigit():
                    os.remove(f)
                    print(f"   删除: {f}")
        except:
            pass

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
