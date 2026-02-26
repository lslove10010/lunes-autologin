const puppeteer = require('puppeteer');
const axios = require('axios');

async function sendWeComMessage(webhookUrl, message) {
  // 企业微信机器人支持 markdown 格式
  const data = {
    msgtype: 'markdown',
    markdown: {
      content: message
    }
  };
  
  await axios.post(webhookUrl, data)
    .catch(error => {
      console.error('企业微信通知失败:', error.message);
    });
}

async function solveTurnstile(page, sitekey, pageUrl) {
  const apiKey = process.env.CAPTCHA_API_KEY;
  if (!apiKey) throw new Error('CAPTCHA_API_KEY 未设置');

  const submitTaskRes = await axios.post('http://2captcha.com/in.php', {
    key: apiKey,
    method: 'turnstile',
    sitekey: sitekey,
    pageurl: pageUrl,
    json: 1
  });

  if (submitTaskRes.data.status !== 1) {
    throw new Error(`提交任务失败: ${submitTaskRes.data.request}`);
  }

  const taskId = submitTaskRes.data.request;

  let result;
  for (let i = 0; i < 24; i++) {
    await page.waitForTimeout(5000);
    const getResultRes = await axios.get(`http://2captcha.com/res.php?key=${apiKey}&action=get&id=${taskId}&json=1`);
    if (getResultRes.data.status === 1) {
      result = getResultRes.data.request;
      break;
    }
    if (getResultRes.data.request === 'CAPCHA_NOT_READY') {
      continue;
    }
    throw new Error(`获取结果失败: ${getResultRes.data.request}`);
  }

  if (!result) throw new Error('Turnstile 解决超时');

  await page.evaluate((token) => {
    const textarea = document.querySelector('textarea[name="cf-turnstile-response"]');
    if (textarea) {
      textarea.value = token;
    } else {
      if (window.turnstileCallback) {
        window.turnstileCallback({ token });
      }
    }
  }, result);

  console.log('Turnstile 已解决');
}

async function login() {
  const browser = await puppeteer.launch({
    headless: true,
    args: [
      '--no-sandbox',
      '--disable-setuid-sandbox',
      '--disable-dev-shm-usage',
      '--disable-gpu'
    ]
  });
  const page = await browser.newPage();

  await page.setUserAgent('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36');

  try {
    await page.goto(process.env.WEBSITE_URL, { waitUntil: 'networkidle2' });

    await page.type('#email', process.env.USERNAME);
    await page.type('#password', process.env.PASSWORD);

    await page.waitForSelector('.g-recaptcha', { timeout: 10000 });

    const sitekey = await page.evaluate(() => {
      const el = document.querySelector('.g-recaptcha');
      return el ? el.dataset.sitekey : null;
    });
    if (!sitekey) throw new Error('未找到 sitekey');
    const currentUrl = page.url();

    await solveTurnstile(page, sitekey, currentUrl);

    await page.click('button[type="submit"]');

    await page.waitForNavigation({ waitUntil: 'networkidle2', timeout: 10000 });

    const currentUrlAfter = page.url();
    const title = await page.title();
    if (currentUrlAfter.includes('/') && !title.includes('Login')) {
      // 企业微信 markdown 格式：绿色表示成功
      const successMessage = `**登录成功！**\n> 时间: ${new Date().toISOString()}\n> 页面: ${currentUrlAfter}\n> 标题: ${title}`;
      await sendWeComMessage(process.env.WECOM_WEBHOOK_URL, successMessage);
      console.log('登录成功！当前页面：', currentUrlAfter);
    } else {
      throw new Error(`登录可能失败。当前 URL: ${currentUrlAfter}, 标题: ${title}`);
    }

    console.log('脚本执行完成。');
  } catch (error) {
    await page.screenshot({ path: 'login-failure.png', fullPage: true });
    // 企业微信 markdown 格式：红色表示失败
    const failMessage = `**登录失败！**\n> 时间: ${new Date().toISOString()}\n> 错误: ${error.message}\n> 请检查截图 login-failure.png`;
    await sendWeComMessage(process.env.WECOM_WEBHOOK_URL, failMessage);
    console.error('登录失败：', error.message);
    console.error('截屏已保存为 login-failure.png');
    throw error;
  } finally {
    await browser.close();
  }
}

login();
