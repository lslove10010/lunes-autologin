addEventListener('scheduled', event => {
  event.waitUntil(handleScheduled(event));
});

async function handleScheduled(event) {
  try {
    const loginUrl = 'https://betadash-lunes.host/login?next=/';
    
    const loginPayload = {
      email: EMAIL,
      password: PASSWORD,
    };

    const response = await fetch(loginUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
        'User-Agent': 'Cloudflare-Worker/1.0',
      },
      body: new URLSearchParams(loginPayload).toString(),
    });

    if (response.ok) {
      console.log('登录成功', new Date().toISOString());
      return new Response('登录成功', { status: 200 });
    } else {
      console.error('登录失败:', response.status, await response.text());
      return new Response('登录失败', { status: response.status });
    }
  } catch (error) {
    console.error('登录出错:', error);
    return new Response('登录出错', { status: 500 });
  }
}
