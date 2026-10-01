from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse

from wa_platform.core.config import Settings, get_settings

router = APIRouter(tags=["dev-tools"])

_PAGE = """<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Embedded Signup test harness</title>
<style>
  body { font-family: -apple-system, sans-serif; max-width: 640px; margin: 40px auto; padding: 0 16px; }
  body { color: #1b1d21; }
  h1 { font-size: 1.3rem; }
  section { border: 1px solid #ddd; border-radius: 8px; padding: 16px 20px; margin-bottom: 20px; }
  label { display: block; font-size: 0.85rem; margin: 10px 0 4px; color: #555; }
  input[type=text] { width: 100%; padding: 6px 8px; font-size: 0.9rem; box-sizing: border-box; }
  button { margin-top: 12px; padding: 8px 14px; cursor: pointer; }
  pre { background: #f4f4f4; padding: 10px; border-radius: 6px; font-size: 0.8rem; overflow-x: auto; }
  pre { white-space: pre-wrap; }
  .note { font-size: 0.82rem; color: #666; }
  .ok { color: #1a7a3c; }
  .err { color: #b3261e; }
</style>
</head>
<body>
<h1>Embedded Signup test harness — dev only</h1>
<p class="note">
  Needs a Test WABA under your Meta App (Business Portfolio → WhatsApp → API Setup) and a
  <code>config_id</code> from your app's Embedded Signup configuration. Add <code>localhost</code>
  to the app's App Domains so the JS SDK popup is allowed to run here.
</p>

<section>
  <h2>1. Get an API key</h2>
  <label>Email</label>
  <input type="text" id="email" value="">
  <label>Password (min 8 chars)</label>
  <input type="text" id="password" value="hunter22">
  <button onclick="registerUser()">Register test user</button>
  <button onclick="loginUser()">Log in instead</button>
  <label>API key (bearer token used below)</label>
  <input type="text" id="apiKey" value="">
  <pre id="authLog"></pre>
</section>

<section>
  <h2>2. Launch WhatsApp Embedded Signup</h2>
  <label>Meta App ID</label>
  <input type="text" id="appId" value="__META_APP_ID__">
  <label>Config ID</label>
  <input type="text" id="configId" value="">
  <button onclick="launchSignup()">Launch WhatsApp Signup</button>
  <pre id="signupLog"></pre>
</section>

<section>
  <h2>3. Complete onboarding</h2>
  <label>code</label>
  <input type="text" id="code" value="">
  <label>waba_id</label>
  <input type="text" id="wabaId" value="">
  <label>phone_number_id</label>
  <input type="text" id="phoneNumberId" value="">
  <button onclick="completeOnboarding()">POST /onboarding/complete</button>
  <pre id="onboardLog"></pre>
</section>

<script>
  const PERSISTED_FIELDS = ['email', 'apiKey', 'configId'];
  function persist(id, value) {
    try { localStorage.setItem('embedded-signup:' + id, value); } catch { /* ignore */ }
  }
  for (const id of PERSISTED_FIELDS) {
    try {
      const saved = localStorage.getItem('embedded-signup:' + id);
      if (saved) document.getElementById(id).value = saved;
    } catch { /* ignore */ }
    document.getElementById(id).addEventListener('input', (e) => persist(id, e.target.value));
  }

  function log(elId, label, data, isErr) {
    const el = document.getElementById(elId);
    const line = `[${new Date().toLocaleTimeString()}] ${label}\\n${JSON.stringify(data, null, 2)}\\n\\n`;
    el.textContent = line + el.textContent;
    el.className = isErr ? 'err' : 'ok';
  }

  async function registerUser() {
    let email = document.getElementById('email').value;
    if (!email) {
      email = `test+${Date.now()}@example.com`;
      document.getElementById('email').value = email;
      persist('email', email);
    }
    const password = document.getElementById('password').value;
    const r = await fetch('/auth/register', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    });
    const body = await r.json();
    if (r.ok) {
      document.getElementById('apiKey').value = body.api_key;
      persist('apiKey', body.api_key);
    }
    log('authLog', `POST /auth/register -> ${r.status}`, body, !r.ok);
  }

  async function loginUser() {
    const email = document.getElementById('email').value;
    const password = document.getElementById('password').value;
    const r = await fetch('/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    });
    const body = await r.json();
    log('authLog', `POST /auth/login -> ${r.status}`, body, !r.ok);
    if (!r.ok) return;
    log('authLog', 'note', 'login does not return an api_key — register or rotate to get one', false);
  }

  let fbReady = false;
  function loadFacebookSdk(appId) {
    const opts = { appId, cookie: false, xfbml: false, version: '__GRAPH_VERSION__' };
    if (window.FB) { window.FB.init(opts); fbReady = true; return; }
    window.fbAsyncInit = function () {
      window.FB.init(opts);
      fbReady = true;
    };
    const s = document.createElement('script');
    s.src = 'https://connect.facebook.net/en_US/sdk.js';
    s.async = true;
    s.defer = true;
    document.body.appendChild(s);
  }

  window.addEventListener('message', (event) => {
    if (!event.origin.endsWith('facebook.com')) return;
    let data;
    try { data = JSON.parse(event.data); } catch { return; }
    if (data.type !== 'WA_EMBEDDED_SIGNUP') return;
    log('signupLog', 'postMessage WA_EMBEDDED_SIGNUP', data, false);
    if (data.event === 'FINISH' && data.data) {
      const d = data.data;
      if (d.waba_id) document.getElementById('wabaId').value = d.waba_id;
      if (d.phone_number_id) document.getElementById('phoneNumberId').value = d.phone_number_id;
    }
  });

  function launchSignup() {
    const appId = document.getElementById('appId').value;
    const configId = document.getElementById('configId').value;
    if (!appId || !configId) { log('signupLog', 'error', 'appId and configId are required', true); return; }
    loadFacebookSdk(appId);
    const waitAndLaunch = () => {
      if (!fbReady) { setTimeout(waitAndLaunch, 200); return; }
      FB.login(
        (response) => {
          log('signupLog', 'FB.login response', response, !response.authResponse);
          const code = response.authResponse && response.authResponse.code;
          if (code) document.getElementById('code').value = code;
        },
        {
          config_id: configId,
          response_type: 'code',
          override_default_response_type: true,
          extras: { setup: {} },
        }
      );
    };
    waitAndLaunch();
  }

  async function completeOnboarding() {
    const apiKey = document.getElementById('apiKey').value;
    const code = document.getElementById('code').value;
    const waba_id = document.getElementById('wabaId').value;
    const phone_number_id = document.getElementById('phoneNumberId').value;
    // Must be the exact URL of this page — Meta ties the code to it as the implicit
    // redirect_uri of the FB.login call, and the exchange 403s (OAuthException 36008)
    // if the one sent here doesn't match.
    const redirect_uri = window.location.href;
    const r = await fetch('/onboarding/complete', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${apiKey}`,
      },
      body: JSON.stringify({ code, waba_id, phone_number_id, redirect_uri }),
    });
    const body = await r.json();
    log('onboardLog', `POST /onboarding/complete -> ${r.status} (redirect_uri=${redirect_uri})`, body, !r.ok);
  }
</script>
</body>
</html>
"""


@router.get("/dev/embedded-signup", response_class=HTMLResponse)
def embedded_signup_test_page(settings: Settings = Depends(get_settings)) -> str:
    return _PAGE.replace("__META_APP_ID__", settings.meta_app_id).replace(
        "__GRAPH_VERSION__", settings.graph_version
    )
