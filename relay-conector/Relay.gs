// ============================================================
// GARMIN/HUAWEI/COROS SELF-SERVICE CONNECTOR — RELAY
// ------------------------------------------------------------
// Standalone Apps Script Web App (separate project from the
// triatlon-atleta Sheet script). Its ONLY job: take an athlete's
// wearable-brand email/password from a web form, encrypt it with
// GitHub's public key (crypto_box_seal, see vendored_crypto.gs.txt),
// and write it directly as a GitHub Actions secret on wearables-hub.
//
// It never stores, logs, or returns the plaintext credentials
// anywhere — not in a Sheet, not in Logger, not in the HTTP response.
// Once written, GitHub Secrets are write-only: nobody, including the
// repo owner (Carlos), can read them back via the UI or API. That's
// the property this whole design leans on.
//
// SETUP (one-time, done by Carlos in the Apps Script editor):
//   1. Project Settings → Script properties → add:
//        GITHUB_PAT   = <fine-grained PAT for wearables-hub, scoped to
//                        Secrets: write, Variables: write, Actions: read>
//        GITHUB_OWNER = carlosgranderodriguez-a11y
//        GITHUB_REPO  = wearables-hub
//   2. Deploy as Web App: Execute as "Me", Access "Anyone".
//   3. Run createInviteLink_('nacho', 'garmin') ONCE from the editor
//      (View > Execution log shows the resulting URL) to generate
//      Nacho's one-time connect link, and send him that link — never
//      the raw Web App URL. See createInviteLink_ below.
// ============================================================

// ── Brand registry ──────────────────────────────────────────
// Adding a new email/password-style brand (Huawei, Coros, ...) is
// just adding an entry here — nothing else in this file changes.
var BRAND_CONFIG = {
  garmin: {
    label: 'Garmin Connect',
    secretNames: function (atletaKey) {
      return {
        email: 'GARMIN_EMAIL_' + atletaKey,
        password: 'GARMIN_PASSWORD_' + atletaKey
      };
    },
    athleteListVar: 'GARMIN_ATLETAS'
  },
  huawei: {
    label: 'Huawei Health',
    secretNames: function (atletaKey) {
      return {
        email: 'HUAWEI_EMAIL_' + atletaKey,
        password: 'HUAWEI_PASSWORD_' + atletaKey
      };
    },
    athleteListVar: 'HUAWEI_ATLETAS'
  },
  coros: {
    label: 'COROS',
    secretNames: function (atletaKey) {
      return {
        email: 'COROS_EMAIL_' + atletaKey,
        password: 'COROS_PASSWORD_' + atletaKey
      };
    },
    athleteListVar: 'COROS_ATLETAS'
  }
};

// ── Config helpers ──────────────────────────────────────────
function cfg_() {
  var p = PropertiesService.getScriptProperties();
  var pat = p.getProperty('GITHUB_PAT');
  var owner = p.getProperty('GITHUB_OWNER');
  var repo = p.getProperty('GITHUB_REPO');
  if (!pat || !owner || !repo) {
    throw new Error('Faltan Script Properties: GITHUB_PAT, GITHUB_OWNER, GITHUB_REPO. Configúralas en Project Settings > Script properties.');
  }
  return { pat: pat, owner: owner, repo: repo };
}

// ── Athlete key validation ──────────────────────────────────
// Only lowercase letters, digits and underscores — this value gets
// interpolated directly into GitHub secret/variable names, so it must
// be constrained to characters GitHub allows there anyway.
function validAtletaKey_(k) {
  return typeof k === 'string' && /^[a-z][a-z0-9_]{1,30}$/.test(k);
}

// ============================================================
// INVITE TOKENS — single-use, so the public Web App URL alone
// isn't enough for a stranger to write secrets into Carlos's repo.
// Stored in Script Properties as INVITE_<token> = "atleta|brand|used".
// ============================================================
function createInviteLink_(atletaKey, brand) {
  if (!validAtletaKey_(atletaKey)) throw new Error('Clave de atleta inválida: ' + atletaKey);
  if (!BRAND_CONFIG[brand]) throw new Error('Marca desconocida: ' + brand);
  var token = Utilities.getUuid().replace(/-/g, '');
  PropertiesService.getScriptProperties().setProperty(
    'INVITE_' + token,
    JSON.stringify({ atleta: atletaKey, brand: brand, used: false, created: new Date().toISOString() })
  );
  var url = ScriptApp.getService().getUrl() + '?t=' + token;
  Logger.log('Enlace para ' + atletaKey + ' (' + brand + '): ' + url);
  return url;
}

function consumeInvite_(token) {
  var props = PropertiesService.getScriptProperties();
  var key = 'INVITE_' + token;
  var raw = props.getProperty(key);
  if (!raw) return null;
  var invite = JSON.parse(raw);
  if (invite.used) return null;
  invite.used = true;
  invite.usedAt = new Date().toISOString();
  props.setProperty(key, JSON.stringify(invite));
  return invite; // {atleta, brand}
}

function peekInvite_(token) {
  // Read-only lookup for doGet (to pre-fill/label the form) — does NOT
  // consume the token. Only submitConnect's consumeInvite_ call marks
  // it used.
  var raw = PropertiesService.getScriptProperties().getProperty('INVITE_' + token);
  if (!raw) return null;
  var invite = JSON.parse(raw);
  if (invite.used) return null;
  return invite;
}

// ============================================================
// doGet — serves the connect.html form, pre-filled/labeled from the
// invite token so Nacho never has to type his own athlete key.
// ============================================================
function doGet(e) {
  var token = e.parameter.t || '';
  var invite = token ? peekInvite_(token) : null;
  var tpl = HtmlService.createTemplateFromFile('connect');
  tpl.token = token;
  tpl.valid = !!invite;
  tpl.brandLabel = invite ? BRAND_CONFIG[invite.brand].label : '';
  return tpl.evaluate()
    .setTitle('Conectar dispositivo')
    .addMetaTag('viewport', 'width=device-width, initial-scale=1');
}

// ============================================================
// submitConnect — the actual credential handoff, called from
// connect.html via google.script.run (client-side Apps Script RPC —
// runs server-side inside this same Web App, no separate HTTP POST/
// CORS hop needed). atleta + brand come from the invite token, never
// from the client, so a tampered call can't redirect credentials into
// a different athlete's or brand's secret names.
// ============================================================
function submitConnect(token, email, password) {
  var result = { ok: false, error: '' };
  try {
    if (!token) throw new Error('Falta el enlace de invitación.');
    var invite = consumeInvite_(token);
    if (!invite) throw new Error('Este enlace ya se usó o no es válido. Pide uno nuevo a tu entrenador.');
    if (!email || !password) throw new Error('Faltan el email o la contraseña.');

    var brand = BRAND_CONFIG[invite.brand];
    if (!brand) throw new Error('Marca no soportada: ' + invite.brand);

    var names = brand.secretNames(invite.atleta);
    var c = cfg_();
    var pubKey = getSecretsPublicKey_(c);

    putSecret_(c, pubKey, names.email, email);
    putSecret_(c, pubKey, names.password, password);
    // email/password go out of scope here; nothing keeps them beyond
    // this point (no assignment to a var that outlives this call, no
    // Logger.log of either value, ever).

    addAthleteToListVar_(c, brand.athleteListVar, invite.atleta);

    result.ok = true;
    result.message = 'Cuenta de ' + brand.label + ' conectada para ' + invite.atleta + '. A partir de mañana se sincronizará automáticamente.';
  } catch (err) {
    result.error = err.message || String(err);
    // Deliberately: never include email/password in the error payload
    // or in any Logger.log call — only the error message text.
  }
  return result;
}

// ============================================================
// GitHub REST API helpers
// ============================================================
function githubRequest_(c, method, path, payload) {
  var options = {
    method: method,
    headers: {
      Authorization: 'Bearer ' + c.pat,
      Accept: 'application/vnd.github+json',
      'X-GitHub-Api-Version': '2022-11-28'
    },
    muteHttpExceptions: true
  };
  if (payload !== undefined) {
    options.contentType = 'application/json';
    options.payload = JSON.stringify(payload);
  }
  var resp = UrlFetchApp.fetch('https://api.github.com' + path, options);
  var code = resp.getResponseCode();
  var text = resp.getContentText();
  if (code >= 200 && code < 300) {
    return text ? JSON.parse(text) : null;
  }
  if (code === 404) return { __notFound: true };
  throw new Error('GitHub API ' + method + ' ' + path + ' → ' + code + ': ' + text);
}

function getSecretsPublicKey_(c) {
  return githubRequest_(c, 'get', '/repos/' + c.owner + '/' + c.repo + '/actions/secrets/public-key');
}

function putSecret_(c, pubKey, secretName, plaintextValue) {
  var encrypted = sealedBoxEncrypt_(plaintextValue, pubKey.key);
  githubRequest_(c, 'put', '/repos/' + c.owner + '/' + c.repo + '/actions/secrets/' + secretName, {
    encrypted_value: encrypted,
    key_id: pubKey.key_id
  });
}

function addAthleteToListVar_(c, varName, atletaKey) {
  var path = '/repos/' + c.owner + '/' + c.repo + '/actions/variables/' + varName;
  var existing = githubRequest_(c, 'get', path);
  if (existing && existing.__notFound) {
    githubRequest_(c, 'post', '/repos/' + c.owner + '/' + c.repo + '/actions/variables', {
      name: varName,
      value: atletaKey
    });
    return;
  }
  var current = (existing.value || '').split(',').map(function (s) { return s.trim(); }).filter(Boolean);
  if (current.indexOf(atletaKey) === -1) {
    current.push(atletaKey);
    githubRequest_(c, 'patch', path, { name: varName, value: current.join(',') });
  }
}
