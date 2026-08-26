
const INACTIVITY_TIMEOUT_MS = 5 * 60 * 1000; // 5 minutes
const LOGOUT_DELAY_MS = 10000; // 10 seconds

let inactivityTimer;
let logoutTimer;
let warningModal = null;
let warningActive = false;
let logoutWhenInactive = false;

function resetInactivityTimer() {
    // Any activity cancels logout warning
    if (warningActive) {
        clearTimeout(logoutTimer);
        if (warningModal != null) {
          closeModal(warningModal);
          warningModal = null
        } 
        warningActive = false;
    }

    clearTimeout(inactivityTimer);

    inactivityTimer = setTimeout(showInactivityWarning, INACTIVITY_TIMEOUT_MS);
}
function showInactivityWarning() {
    warningActive = true;
    warningModal = modalPopUp(
        '',
        null,
        '<div>Logging out due to inactivity...</div>'
    );

    logoutTimer = setTimeout(() => {
        console.log("Sensitive data cleared due to inactivity.");
        logout();
    }, LOGOUT_DELAY_MS);
}
if (logoutWhenInactive === true) {
    ['mousemove', 'mousedown', 'keydown', 'touchstart']
        .forEach(evt =>
            document.addEventListener(evt, resetInactivityTimer, true)
        );

    resetInactivityTimer(); // start logout timer
}


async function connect_to_node(url, payload = null) {
  console.log('-Connecting to node:', url, 'payload',payload);
  const addr = await myVar('last_accessed_url');
  try {
    var url = format_url(url, addr)
    const options = {};

    if (payload) {
      options.method = 'POST';
      options.headers = { 'Content-Type': 'application/json' };
      options.body = JSON.stringify(payload);
    }

    const response = await fetch(url, options);
    if (!response.ok) throw new Error(`Server error: ${response.status}`);

    const contentType = response.headers.get('content-type') || '';

    const body = contentType.includes('application/json')
      ? await response.json()
      : await response.text();

    return body;

  } catch (err) {
    console.error('Request failed:', err);
    throw err;
  }
}
function format_url(url, addr = null) {
  if (addr) {
    url = addr + url
  }
  if (!url.includes('http')) {
    url = 'https://' + url;
  }
  if (url.includes('127.0.0.1')) {
    url = url.replace('https','http')
  }
  return url
}
async function direct_to(url) {
  // console.log('-direct_to',url)
  user_id = await myVar('user_id');

  if (url.includes('?')){
    addition = '&user=' + user_id;
  } else {
    addition = '?user=' + user_id;
  };
  url = url + addition
  const addr = await myVar('last_accessed_url');
  var url = format_url(url, addr);
  console.log('direct_to url',url)
  window.location.href = url;

}


function getItem(key) {
  // console.log("-getItem", key);
  return openDatabase().then((db) => {
    return new Promise((resolve, reject) => {
      const tx = db.transaction('keys', 'readonly');
      const getReq = tx.objectStore('keys').get(key);
      getReq.onsuccess = () => resolve(getReq.result);
      getReq.onerror = () => reject(getReq.error);
    });
  });
}
function storeItem(item, key) {
  console.log('-storeItem', key);
  return openDatabase().then((db) => {
    return new Promise((resolve, reject) => {
      const tx = db.transaction('keys', 'readwrite');
      tx.objectStore('keys').put(item, key);
      tx.oncomplete = resolve;
      tx.onerror = () => reject(tx.error);
    });
  });
}
function openDatabase() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open('KeyDB', 1);

    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains('keys')) {
        db.createObjectStore('keys');
      }
    };

    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}
window.myVars = window.myVars || {};
async function myVar(key, obj=null) {
  // console.log('-get myVar',key)
  if (obj) {
    storeItem(obj, key);
    window.myVars[key] = obj;
  }
  if (key in window.myVars && window.myVars[key]) {
    return window.myVars[key];
  } else {
    var obj = await getItem(key);
    if (obj) {
      window.myVars[key] = obj;
      return window.myVars[key];
    }
  }
  window.myVars[key] = null;
  return null;
}


async function generateMnemonic() {
  console.log('-generateMnemonic')
  // Load BIP-39 English wordlist
  const res = await fetch("https://raw.githubusercontent.com/bitcoin/bips/master/bip-0039/english.txt");
  if (!res.ok) throw new Error("Failed to load wordlist");
  const text = await res.text();
  const wordlist = text.trim().split('\n');

  // Generate 256-bit entropy
  const entropyBytes = new Uint8Array(32); // 32 bytes = 256 bits
  crypto.getRandomValues(entropyBytes);

  // Calculate SHA-256 hash of entropy
  const hashBuffer = await crypto.subtle.digest('SHA-256', entropyBytes);
  const hashBytes = new Uint8Array(hashBuffer);

  // Convert entropy to binary string
  const entropyBits = [...entropyBytes].map(b => b.toString(2).padStart(8, '0')).join('');
  const checksumBits = [...hashBytes].map(b => b.toString(2).padStart(8, '0')).join('').slice(0, 8); // 256 / 32 = 8 bits

  const fullBits = entropyBits + checksumBits;

  // Split into 24 chunks of 11 bits
  const words = [];
  for (let i = 0; i < 24; i++) {
    const chunk = fullBits.slice(i * 11, (i + 1) * 11);
    const index = parseInt(chunk, 2);
    words.push(wordlist[index]);
  }

  return words.join(' ');
}
async function generateId(data = null, upk=false, length = 14) {
  // max length 32
  if (upk == true){
    length = 14
  }
  let truncated;
  if (data !== null) {
    const input = typeof data === "string" ? new TextEncoder().encode(data) : data;
    const digest = await crypto.subtle.digest("SHA-256", input);
    truncated = new Uint8Array(digest).slice(0, length);
  } else {
    truncated = crypto.getRandomValues(new Uint8Array(length));
  }
  if (upk == true){
    return 'upkSo' + toBase62(truncated);
  }
  return toBase62(truncated);
}

async function hashMessage(message) {
  const hashHex = CryptoJS.SHA256(message).toString(CryptoJS.enc.Hex);
  return hashHex;
}
function toBase64Url(uint8array) {
  return btoa(String.fromCharCode(...uint8array))
    .replace(/\+/g, '-').replace(/\//g, '_').replace(/=/g, '');
}
function fromBase64Url(str) {
  str = str.replace(/-/g, '+').replace(/_/g, '/');
  while (str.length % 4) str += '=';
  return Uint8Array.from(atob(str), c => c.charCodeAt(0));
}
function toBase64(uint8array) {
  return btoa(String.fromCharCode(...uint8array));
}
function fromBase64(base64str) {
  return Uint8Array.from(atob(base64str), c => c.charCodeAt(0));
}
function toBase62(hashBytes) {
  const BASE62_CHARS = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ";

  let num = 0n;
  for (const byte of hashBytes) {
    num = (num << 8n) | BigInt(byte);
  }
  if (num === 0n) return "0";

  let s = "";
  const base = 62n;
  while (num > 0n) {
    s = BASE62_CHARS[Number(num % base)] + s;
    num /= base;
  }
  return s;
}
function fastHash(str, seed = 0) {
  let h1 = 0xdeadbeef ^ seed, h2 = 0x41c6ce57 ^ seed;
  for (let i = 0, ch; i < str.length; i++) {
    ch = str.charCodeAt(i);
    h1 = Math.imul(h1 ^ ch, 2654435761);
    h2 = Math.imul(h2 ^ ch, 1597334677);
  }
  h1 = Math.imul(h1 ^ (h1 >>> 16), 2246822507);
  h1 ^= Math.imul(h2 ^ (h2 >>> 13), 3266489909);
  h2 = Math.imul(h2 ^ (h2 >>> 16), 2246822507);
  h2 ^= Math.imul(h1 ^ (h1 >>> 13), 3266489909);
  return 4294967296 * (2097151 & h2) + (h1 >>> 0);

  // // usage
  // fastHash("hello world"); // returns a number (53-bit safe integer)
  // fastHash("hello world").toString(36); // compact alphanumeric string
}


const SK_SIZES = { 32: 'secp256k1', 66: 'P521', 2560: 'ML_DSA_44', 4032: 'ML_DSA_65', 4896: 'ML_DSA_87' };
const PK_SIZES = { 65: 'secp256k1', 133: 'P521', 1312: 'ML_DSA_44', 1952: 'ML_DSA_65', 2592: 'ML_DSA_87' };
const SIG_SIZES = { 132: 'P521', 2420: 'ML_DSA_44', 3309: 'ML_DSA_65', 4627: 'ML_DSA_87' };

function detectSecurityFromSK(secretKeyB64Url) {
  const byteLen = fromBase64Url(secretKeyB64Url).length;
  const level = SK_SIZES[byteLen];
  if (!level) throw new Error(`Unknown secret key size: ${byteLen} bytes`);
  return level;
}
function detectSecurityFromPK(publicKeyB64Url) {
  const bytes = fromBase64Url(publicKeyB64Url);
  if (bytes.length === 65 && bytes[0] === 0x04) return 'secp256k1';
  if (bytes.length === 133 && bytes[0] === 0x04) return 'P521';
  const level = PK_SIZES[bytes.length];
  if (!level) throw new Error(`Unknown public key size: ${bytes.length} bytes`);
  return level;
}
function detectSecurityFromSig(signatureB64Url) {
  const byteLen = fromBase64Url(signatureB64Url).length;
  const level = SIG_SIZES[byteLen];
  if (!level) throw new Error(`Unknown signature size: ${byteLen} bytes`);
  return level;
}

async function deriveKey_secp256k1(user_id, user_pass) {
  await loadLibs();
  const saltBytes = new Uint8Array(
    await crypto.subtle.digest('SHA-256', new TextEncoder().encode(`${user_id}:${user_pass}`))
  );
  const passBytes = new TextEncoder().encode(user_pass);
  if (user_pass.length > 120) {
    var n = 16384
  } else if (user_pass.length > 40) {
    var n = 65536
  } else {
    var n = 262144
  }
  // console.log('user_pass',user_pass)
  // console.log('n',n,user_pass.length)
  return await _scrypt.scrypt(passBytes, saltBytes, n, 8, 1, 32);
}
async function getKeyPair_secp256k1(user_id, user_pass) {
  console.log('-getKeyPair_secp256k1');
  await loadLibs();

  const seed = await deriveKey_secp256k1(user_id, user_pass);

  const EC = elliptic.ec;
  const ec = new EC('secp256k1');

  const order = BigInt('0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141');
  let privInt = BigInt('0x' + Array.from(seed).map(b => b.toString(16).padStart(2, '0')).join(''));
  privInt = privInt % order;
  if (privInt === 0n) privInt = 1n;

  const privHex = privInt.toString(16).padStart(64, '0');
  const keyPair = ec.keyFromPrivate(privHex, 'hex');

  const privKeyBytes = Uint8Array.from(privHex.match(/.{1,2}/g).map(b => parseInt(b, 16)));
  const pubKeyBytes = Uint8Array.from(keyPair.getPublic().encode()); // uncompressed

  // console.log("Private Key (base64url):", toBase64Url(privKeyBytes));
  // console.log("Public Key (base64url):", toBase64Url(pubKeyBytes));

  return [toBase64Url(privKeyBytes), toBase64Url(pubKeyBytes)];
}
async function simpleSign_secp256k1(privKeyB64Url, data) {
  console.log('-simpleSign_secp256k1');
  const privKeyBytes = fromBase64Url(privKeyB64Url);
  const privHex = Array.from(privKeyBytes).map(b => b.toString(16).padStart(2, '0')).join('');

  const curve = new elliptic.ec('secp256k1');
  const keyPair = curve.keyFromPrivate(privHex, 'hex');

  const msgBytes = new TextEncoder().encode(data);
  const hashBuffer = await crypto.subtle.digest('SHA-256', msgBytes);
  const hashBytes = new Uint8Array(hashBuffer);

  const signature = keyPair.sign(hashBytes, { canonical: true });
  const sigBytes = Uint8Array.from(signature.toDER());

  return toBase64Url(sigBytes);
}
async function simpleVerify_secp256k1(data, signatureB64Url, pubKeyB64Url) {
  console.log('-simpleVerify_secp256k1');
  // console.log('signatureB64Url',signatureB64Url);
  // console.log('pubKeyB64Url',pubKeyB64Url);
  const pubKeyBytes = fromBase64Url(pubKeyB64Url);
  const sigBytes = fromBase64Url(signatureB64Url);
  const pubHex = Array.from(pubKeyBytes).map(b => b.toString(16).padStart(2, '0')).join('');
  const sigHex = Array.from(sigBytes).map(b => b.toString(16).padStart(2, '0')).join('');

  const msgBytes = new TextEncoder().encode(data);
  const hashBuffer = await crypto.subtle.digest('SHA-256', msgBytes);
  const hashBytes = new Uint8Array(hashBuffer);

  const curve = new elliptic.ec('secp256k1');
  const pubKey = curve.keyFromPublic(pubHex, 'hex');

  return curve.verify(hashBytes, sigHex, pubKey);
}

let _p521 = null;
let _p521hashes = null;
const FIELD_BYTES_P521 = 66; // 521-bit curve, fixed-width scalar/point coords

async function loadP521Libs() {
  console.log('-loadP521Libs');
  if (!_p521) _p521 = (await import('https://esm.sh/@noble/curves@1.4.2/p521')).p521;
  if (!_p521hashes) {
    const { sha512 } = await import('https://esm.sh/@noble/hashes@1.4.0/sha512');
    const { hkdf } = await import('https://esm.sh/@noble/hashes@1.4.0/hkdf');
    _p521hashes = { sha512, hkdf };
  }
  if (!_scrypt) _scrypt = (await import('https://esm.sh/scrypt-js@3.0.0')).default;
  // console.log('done loadP521Libs');
}
function bytesToBigInt_p521(bytes) {
  let hex = Array.from(bytes).map(b => b.toString(16).padStart(2, '0')).join('');
  return BigInt('0x' + hex);
}
function bigIntToBytes_p521(num, length) {
  let hex = num.toString(16).padStart(length * 2, '0');
  return Uint8Array.from(hex.match(/.{1,2}/g).map(b => parseInt(b, 16)));
}
function derivePrivateScalar_p521(seedBytes) {
  const { sha512, hkdf } = _p521hashes;
  const salt = new Uint8Array(0);
  const info = new TextEncoder().encode('ecdsa-p521-key');
  const okm = hkdf(sha512, seedBytes, salt, info, FIELD_BYTES_P521 + 8);
  let scalar = bytesToBigInt_p521(okm) % _p521.CURVE.n;
  if (scalar === 0n) scalar = 1n;
  return scalar;
}
async function getKeyPair_p521(user_id, user_pass) {
  console.log('-getKeyPair_p521');
  await loadP521Libs();
  const seed = await deriveKey_ml_dsa(user_id, user_pass); // reuse existing scrypt-based 32-byte seed
  const scalar = derivePrivateScalar_p521(seed);
  const skBytes = bigIntToBytes_p521(scalar, FIELD_BYTES_P521);
  const pkBytes = _p521.getPublicKey(skBytes, false); // uncompressed, 133 bytes
  return [toBase64Url(skBytes), toBase64Url(pkBytes)];
}
async function simpleSign_p521(secretKeyB64, data) {
  console.log('-simpleSign_p521',data);
  await loadP521Libs();
  const sk = fromBase64Url(secretKeyB64);
  const message = new TextEncoder().encode(data);
  const msgHash = _p521hashes.sha512(message);
  const sig = _p521.sign(msgHash, sk);
  return toBase64Url(sig.toCompactRawBytes()); // raw r||s, 132 bytes — matches Python side
}
async function simpleVerify_p521(data, signatureB64, publicKeyB64) {
  console.log('-simpleVerify_p521');
  await loadP521Libs();
  try {
    const pk = fromBase64Url(publicKeyB64);
    const sig = fromBase64Url(signatureB64);
    const message = new TextEncoder().encode(data);
    const msgHash = _p521hashes.sha512(message);
    const valid = _p521.verify(sig, msgHash, pk);
    console.log(valid ? 'P521 Signature is *VALID*' : 'P521 Signature !!INVALID!!');
    return valid;
  } catch (e) {
    console.log('VERIFY err p521', e.message);
    return false;
  }
}

let _pq = null;
let _scrypt = null;

async function loadLibs() {
  if (!_pq) _pq = await import('https://esm.sh/@noble/post-quantum@0.2.1/ml-dsa');
  if (!_scrypt) _scrypt = (await import('https://esm.sh/scrypt-js@3.0.0')).default;
}
async function getMLDSA(security) {
  // console.log('-getMLDSA',security)
  await loadLibs();
  const { ml_dsa44, ml_dsa65, ml_dsa87 } = _pq;
  if (security === 'ML_DSA_87') return ml_dsa87;
  if (security === 'ML_DSA_44') return ml_dsa44;
  if (security === 'ML_DSA_65') return ml_dsa65;
}
async function deriveKey_ml_dsa(user_id, user_pass) {
  const scrypt = _scrypt;
  const saltBytes = new Uint8Array(
    await crypto.subtle.digest('SHA-256', new TextEncoder().encode(`${user_id}:${user_pass}`))
  );
  const passBytes = new TextEncoder().encode(user_pass);
  if (user_pass.length > 120) {
    var n = 16384
  } else if (user_pass.length > 40) {
    var n = 65536
  } else {
    var n = 262144
  }
  return await scrypt.scrypt(passBytes, saltBytes, n, 8, 1, 32);
}
async function getKeyPair_ml_dsa(user_id, user_pass, key_strength = 'ML_DSA_44') {
  console.log('-getKeyPair_ml_dsa',key_strength)
  await loadLibs();
  const { ml_dsa44, ml_dsa65, ml_dsa87 } = _pq;
  const seed = await deriveKey_ml_dsa(user_id, user_pass);
  const mldsa = await getMLDSA(key_strength);
  const { secretKey, publicKey } = mldsa.keygen(seed);
  return [toBase64Url(secretKey), toBase64Url(publicKey)];
}
async function simpleSign_ml_dsa(secretKeyB64, data, key_strength = 'ML_DSA_44') {
  console.log('-simpleSign_ml_dsa',key_strength,data)
  var key_strength = detectSecurityFromSK(secretKeyB64);
  const sk = fromBase64Url(secretKeyB64);
  const message = new TextEncoder().encode(data);
  const mldsa = await getMLDSA(key_strength);
  const signature = mldsa.sign(sk, message);
  return toBase64Url(signature);
}
async function simpleVerify_ml_dsa(data, signatureB64, publicKeyB64, key_strength = 'ML_DSA_44') {
  console.log('-simpleVerify_ml_dsa')
  if (key_strength == null) {
    var key_strength = detectSecurityFromPK(publicKeyB64);
  }
  const pk = fromBase64Url(publicKeyB64);
  const sig = fromBase64Url(signatureB64);
  const message = new TextEncoder().encode(data);
  const mldsa = await getMLDSA(key_strength);
  return mldsa.verify(pk, message, sig);
}


async function simpleSign(data_str, privKey, key_type='secp256k1') {
  data_str = data_str+'ycF3atcq61TMBvVmGwrQWZJ69fu';

  if (key_type == 'secp256k1') {
    sig = await simpleSign_secp256k1(privKey, data_str);
  } else if (key_type == 'P521') {
    sig = await simpleSign_p521(privKey, data_str);
  } else {
    sig = await simpleSign_ml_dsa(privKey, data_str, key_strength=key_type);
  };
  return sig;
}
async function simpleVerify(data_str, sig, publicKey, key_type='secp256k1') {
  var data_str = data_str + 'ycF3atcq61TMBvVmGwrQWZJ69fu';

  let isVerified;
  if (key_type == 'secp256k1') {
    isVerified = await simpleVerify_secp256k1(data_str, sig, publicKey);
  } else if (key_type == 'P521') {
    isVerified = await simpleVerify_p521(data_str, sig, publicKey);
  } else {
    isVerified = await simpleVerify_ml_dsa(data_str, sig, publicKey, key_strength=key_type);
  };
  return isVerified;
}
async function createKeyPair(user_id, user_pass, key_type, key_strength = 'secp256k1') {
  user_pass = key_type + user_pass
  if (key_strength === 'secp256k1') return await getKeyPair_secp256k1(user_id, user_pass);
  if (key_strength === 'P521') return await getKeyPair_p521(user_id, user_pass);
  return await getKeyPair_ml_dsa(user_id, user_pass, key_strength);
}

async function sign_data(data, privKey=null, pubKey=null, key_type='secp256k1', signed_dt=null, req_sigs=null, include_key=false, do_sort=true) {
  // receives parsed data
  console.log('-signing...',key_type);

  if (pubKey == null) {
    pubKey = await myVar('Sign_PubKey');
    // console.log('pubKey',pubKey);
  };
    if (privKey == null) {
    privKey = await myVar('Sign_PrivKey');
    // console.log('privKey!!',privKey);
  };
  if (privKey == null || privKey == 'null' || pubKey == null) {
    console.log('privKey or pubkey nuill');
    return null;
  };
  if (key_type == null) {
    var key_type = detectSecurityFromSK(privKey);
  };

  if (!signed_dt) {
    signed_dt = get_current_time();
  };

  pk_data = {'pk':await generateId(pubKey, upk=true)};
  var original_signed = {}
  if (!req_sigs) {
    data.signed = {};
    if ('lastUpdate' in data) {
      data.lastUpdate = signed_dt
    };
  } else { 
    
    if (req_sigs == 'current') {
      // if sigs exist avoid collisions with signed_dt bump
      if (data.signed && typeof data.signed === 'object') {
        while (signed_dt in data.signed) {
          console.log('signed_dt collision, bumping:', signed_dt);
          signed_dt = bumpDt(signed_dt);
        };
      };
      pk_data['req'] = {};
      var original_signed = JSON.parse(JSON.stringify(data.signed));
      for (const [dt, sig_data] of Object.entries(data.signed)) {
        data.signed[dt] = {'pk':sig_data['pk']};
        if (sig_data['req']) {
          data.signed[dt]['req'] = sig_data['req'];
        };
        pk_data['req'][dt] = sig_data['pk'].slice(0, 10);
      };
    } else {
      pk_data['req'] = {};
      for (const [dt, sig_data] of Object.entries(req_sigs)) {
        if (sig_data['pk'] in req_sigs) {
          if (dt == signed_dt) {
            console.log('signed_dt collision, bumping:', signed_dt);
            signed_dt = bumpDt(signed_dt);
          }
          data.signed[dt] = {'pk':sig_data['pk']};
          if (sig_data['req']) {
            data.signed[dt]['req'] = sig_data['req'];
          };
          pk_data['req'][dt] = sig_data['pk'].slice(0, 10);
        };
      };
    }
  };

  data.signed[signed_dt] = pk_data;
  if (include_key == true) {
    data.signed[signed_dt]['publicKey'] = pubKey;
  }
  // console.log('data.signed',data.signed)
  try {
    delete data.latestVer;
  } catch(err){};
  if (do_sort) {
    var sortedData = sortForSign(data);
  } else {
    var sortedData = data;
  }
  var data_str = JSON.stringify(sortedData);
  console.log('data_str',data_str)

  var sig = await simpleSign(data_str, privKey, key_type=key_type);
  // console.log('sig',sig);
  data.signed[signed_dt]['sig'] = sig;
  if (original_signed) {
    for (const [dt, sig_data] of Object.entries(original_signed)) {
      if (dt === signed_dt) continue;
      if (sig_data['sig'] !== undefined) {
        data.signed[dt]['sig'] = sig_data['sig'];
      }
      if (sig_data['publicKey'] !== undefined) {
        data.signed[dt]['publicKey'] = sig_data['publicKey'];
      }
    }
  };

  // console.log('data.signed[signed_dt]',data.signed[signed_dt]);
  return data;
}

function resolveChain(dt, entryData, signedField, snapshot) {
  if (dt in snapshot) {
    return true; // already resolved via another path, avoid redundant work / cycles
  }

  snapshot[dt] = { pk: entryData.pk };
  if (entryData.req) {
    snapshot[dt].req = entryData.req;
    for (const [key, val] of Object.entries(entryData.req)) {
      if (!(key in signedField)) {
        console.log('req unresolved - missing key', key);
        return false;
      }
      const refEntry = signedField[key];
      const refPk = refEntry.pk;
      if (!refPk || refPk.slice(0, 10) !== val) {
        console.log('req unresolved - pk mismatch', key);
        return false;
      }
      if (!resolveChain(key, refEntry, signedField, snapshot)) {
        return false;
      }
    }
  }
  return true;
}
async function verify(data, sortData=false, key_type=null) {
  console.log('-verifying...');
  const workingData = JSON.parse(JSON.stringify(data));
  try {
    delete workingData.latestVer;
  } catch(err){};

  if (!workingData.signed || Object.keys(workingData.signed).length === 0) {
    console.log('no signed data');
    return false;
  };

  const signedField = workingData.signed;

  for (const [dt, entry] of Object.entries(signedField)) {
    if (!entry.sig || !entry.publicKey) {
      console.log('missing sig or publicKey for', dt);
      return false;
    };

    const snapshot = {};
    if (!resolveChain(dt, entry, signedField, snapshot)) {
      console.log('req chain resolution failed for', dt);
      return false;
    };

    const sortedSnapshot = {};
    Object.keys(snapshot).sort().forEach(k => { sortedSnapshot[k] = snapshot[k]; }); // earliest first

    let kt = key_type;
    if (kt == null) {
      kt = detectSecurityFromPK(entry.publicKey);
    };

    const dataForHash = { ...workingData, signed: sortedSnapshot };
    const finalData = sortData ? sortForSign(dataForHash) : dataForHash;
    const data_str = JSON.stringify(finalData);

    let isVerified;
    isVerified = await simpleVerify(data_str, entry.sig, entry.publicKey, key_type=kt)

    console.log('isVerified', dt, isVerified);
    if (!isVerified) {
      return false;
    };
  };

  return true;
}



async function react(item, iden, code=null, button=null){
  console.log('-react', code)
  // navigator.vibrate(3);
  userData = get_stored_userData();
  const addr = await myVar("last_accessed_url");
  console.log('addr',addr)
  if (!addr) {
    addr = '';
  }
  if (item == 'verify') {
    modalPopUp('Verify Me', '/utils/verify_post_modal/' + iden)
    return
  } else if (item == 'modelData') {
    modalPopUp('Model Data', '/utils/generic_modal_data/modelData/' + iden)
    return
  } else if (item == 'share') {

  } else if (userData == null || userData == 'null') {
    modalPopUp('Login / Signup', '/accounts/login-signup')
  } else {
    if(item == 'follow2'){
      var navBar = document.getElementById('navBar');
      follow = item.split('-')[0]
      li = navBar.getElementsByClassName('follow')[0]
      li.classList.toggle('active');
      if (iden.includes('?follow=')||iden.includes('&follow=')){
        link = iden
      } else {
        link = '?follow=' + iden
      }
      $.get(addr + link, function(data){
          var parser = new DOMParser();
          var htmlDoc = parser.parseFromString(data, 'text/html');
        check_instructions(htmlDoc)
      });

    } else {
      const data = {'item':item, 'post_id':iden}
      var convert_to_none = false;
      var remove_depress = true;

      const el = document.querySelector(`#${iden}.reactionBar`);

      if (item == 'yea'){
        li = el.getElementsByClassName('yea')[0]
        if(String(li.classList).includes('active')){
          convert_to_none = true
        } 
        remove_depress = false;
        li.classList.toggle('glow-active');
        li.classList.add('depress');
        li2 = el.getElementsByClassName('nay')[0]
        li2.classList.remove('active');
        li2.classList.remove('glow-active');
      } else if (item == 'nay'){
        li = el.getElementsByClassName('nay')[0]
        if(String(li.classList).includes('active')){
          convert_to_none = true
        }
        remove_depress = false;
        li.classList.toggle('glow-active');
        li.classList.add('depress');
        li2 = el.getElementsByClassName('yea')[0]
        li2.classList.remove('active');
        li2.classList.remove('glow-active');
      
      } else if (item == 'follow' || item == 'unfollow') {
        console.log('is follow')
        var post_id = iden
        console.log(userData.follow_post_id_array)
      
      try{
        follow_post_id_array = JSON.parse(userData.follow_post_id_array)
      } catch(err) {
        follow_post_id_array = userData.follow_post_id_array
      }
      if (item == 'follow') {
        if (follow_post_id_array.length > 980) {
          follow_post_id_array.shift()
        }
        follow_post_id_array.push(post_id);
      } else if (item == 'unfollow') {
        var index = follow_post_id_array.indexOf(post_id);
            if (index !== -1) { 
              follow_post_id_array.splice(index, 1);
            }
      }
      userData.follow_post_id_array = JSON.stringify(follow_post_id_array)
      // console.log(JSON.stringify(userData))
      // console.log('---')
    
        li = rs[i].getElementsByClassName('follow')[0]
        li.classList.toggle('active');
        li.classList.add('depress');
      userData = await sign_userData(userData)
      return_signed_userData(userData)
      
      } else if (item == 'more') {
        li = el.getElementsByClassName('moreVert')[0]
        li.classList.add('depress');
        setTimeout(() => {
          li.classList.remove('depress');
        }, 250);
        modalPopUp('More Options', '/utils/post_more_options_modal/' + iden)
        return
      } else if (item == 'insight') {
        console.log('is insishgt')
        modalPopUp('Insights', '/utils/post_insight_modal/' + iden)
        li = el.getElementsByClassName('insight')[0]
        console.log('li:',li)
        li.classList.add('depress');
        setTimeout(() => {
          li.classList.remove('depress');
        }, 250);
        return
      } else if (item == 'spren') {
        modalPopUp("Spren",code)
        li = el.getElementsByClassName('reactionbarSpren')[0]
        li.classList.add('depress');
        setTimeout(() => {
          li.classList.remove('depress');
        }, 250);
        return
      } else {
          li = el.getElementsByClassName(item)[0]
          li.classList.toggle('active');
          li.classList.add('depress');
      }
      data['element'] = li
      
      if (convert_to_none){
        item = 'None'
      }
      if (remove_depress) {
        try {
          setTimeout(function (){
            console.log('removing depress');
            li.classList.remove('depress');
    
          }, 200);
        } catch(err) {console.log(err)}
      }
      if (item != 'share' && item != 'follow' && item != 'unfollow') {
        console.log('makerequest for interaction object')
        // console.log(data)
        user_id = await myVar('user_id')
        makeAjaxRequest({}, addr + '/accounts/reaction/' + iden + '/' + item + '?user=' + user_id, data)
          .then(signReturnInteraction)
          .catch(error => {
            console.error('There was a problem with the AJAX request:', error);
        });

      }
    }
  }

}
async function signReturnInteraction({ response, item }) {
  console.log('-signReturnInteraction',response)
  message = response['message'];
  console.log('message',message)
  if (message == 'login') {
    modalPopUp('Login / Signup', '/accounts/login-signup')
  } else if (message == 'sign-return') {
    
    data = JSON.parse(response['data']);
    li = item['element']
    var sendBack = false;
    const postData = {};
    cmd = item
    const addr = await myVar("last_accessed_url");
    // console.log('addr',addr)
    if (!addr) {
      addr = '';
    }
    user_id = await myVar('user_id');
    data.User_obj = user_id
    if (data['objType'] == 'UserAction') {
      sendBack = true;
      pubKey = await myVar('Sign_PubKey');
      privKey = await myVar('Sign_PrivKey');

      if (data.voteValue == 'yea' && cmd.item == 'yea' || data.voteValue == 'nay' && cmd.item == 'nay') {
        data.voteValue = 'none' // if all actionable fields are none, apply data.rmv = True to request object removal. if any are not none, data.rmv = false
      } else {
        data.voteValue = cmd.item
      }
      data.postId = item.post_id

      const reactionBar = document.getElementById(item.post_id);
      const pointerId = reactionBar.querySelector('.pointer_id').dataset.id;
      data.pointerId = pointerId;
      const updateId = reactionBar.querySelector('.update_id').dataset.id;
      data.updateId = updateId;
      console.log(pointerId, updateId);
      const network_id = reactionBar.querySelector('.network_id').dataset.id;
      data.networkChain = network_id;

      const card = document.getElementById(pointerId);
      if (card) {
        data.pointerHash = fetchHashable('hashable');
        data.updateHash = fetchHashable('hashableUpdate');
      };

      function fetchHashable(selector) {
        const hashableElements = card.querySelectorAll('.'+selector);
        if (hashableElements.length > 0) {
          const hashableElements = card ? [...card.querySelectorAll('.'+selector)] : [];
          const combinedText = hashableElements
            .map(el => el.textContent.trim())
            .filter(text => text.length > 0)
            .join('|');
          return fastHash(combinedText).toString(36);
        }
        return '';
      };
      function isPopulated(obj) {
        return obj && typeof obj === 'object' && Object.keys(obj).length > 0;
      }
      if (isPopulated(response['addon'])) {
        console.log("esponse['addon']",response['addon'])
        addon = JSON.parse(response['addon']);
        if (addon['objType']) {
          data.addonId = addon['id'];
          data.addonKey = addon['objType'];
          addon.created = now_utc;
          addon.User_obj = user_id;
          for (const field of response['addonFields']) {
            if (data[field]) {
              addon[field] = data[field];
            } else {
              // fetch plugin setting and fill out field
            }
          }
          delete addon.signed;
          var sorted_addon = sortForSign(addon);
          data.addonHash = fastHash(JSON.stringify(sorted_addon)).toString(36);

          addon = await sign_data(sorted_addon, privKey=privKey, pubKey=pubKey, key_type='secp256k1', do_sort=false)
          postData['addon'] = JSON.stringify(addon);
        };
      };

      
    } else if (data['objType'] == 'SavePost') {
      if (data.saved == false) {
        data.saved = true
        post_save_state = true
      } else {
        data.saved = false
        post_save_state = false
      }
    }

    if (sendBack) {
      console.log('data',data)
      data = await sign_data(data, privKey=privKey, pubKey=pubKey, key_type='secp256k1')
      if (!data) {
        modalPopUp('Login / Signup', '/accounts/login-signup')
      } else {
        postData['objData'] = JSON.stringify(data);
        // console.log('---')
        // console.log(postData)
        $.ajax({
          type:'POST',
          url: addr + '/accounts/receive_interaction_data',
          data: postData,
          success:function(response){
            console.log('response',response)
            if (response['message'] == 'Success') {
              if (item.item == 'saveButton') {
                if (post_save_state == true) {
                  li.innerHTML = 'Saved'
                } else {
                  li.innerHTML = 'Save'
                }
              } else if (data['objType'] == 'UserAction') {
                  li.classList.remove('depress');
                  li.classList.remove('glow-active'); 
                console.log("data['voteValue']",data['voteValue'])
                  if (data['voteValue'] == 'none'){
                    li.classList.remove('active');
                  } else {
                    li.classList.add('active');
                  }
              }
            } else {
              console.log('else, post-interaction', data['objType'], item)
              if (data['objType'] == 'UserAction') {
                if (item.item == 'yea'){
                  li.classList.remove('active');
                  li.classList.remove('depress');
                  li.classList.remove('glow-active'); 
                }else if (item.item == 'nay'){
                  li.classList.remove('active');
                  li.classList.remove('depress');
                  li.classList.remove('glow-active'); 
                }

              }
              if (response['message'] == 'Invalid publicKey') {
                console.log('invalid public key')
                // notify user that upk has changed and request re-authentication
              } else if (response['message'] == 'User not found') {
                console.log('User not found')
                // notify user that user not found on node and request re-authentication
              };
            };
          },
          error: function (xhr, ajaxOptions, thrownError) {
            console.log('prob2');
            var li = none;
              if (item.item == 'saveButton') {
                li = document.getElementsByClassName('saveButton, clickable')[0];
              } else if (data['objType'] == 'UserAction') {
                if (item == 'yea'){
                  li = rs[i].getElementsByClassName('yea')[0];
                }else if (item == 'nay'){
                  li = rs[i].getElementsByClassName('nay')[0];
                };
              };
            if (li) {
              li.classList.remove('depress');
              li.classList.remove('glow-active'); 
            };
          }
        });
      };
    };
  };
};


function mobileShare(iden, code=null) {
  modalPopUp('Share Post', '/utils/share_modal/' + iden)
    $.get('/utils/mobile_share/' + iden, function(data){
      setTimeout(function (){
        li.classList.remove('active');     
        li.classList.remove('depress'); 
      }, 200);
    });

};
function copyToClipboard(text) {
  if (text[0] == '/') {
  }
  try{
    navigator.clipboard.writeText(text).then(() => {
      console.log("copied " + text);
    });
  }catch(err){}

};
function readAloud(iden) {
  card = document.getElementById(iden);
  let text = $(card).find('.TextContent').text()
  let control = $(card).find('.listen').text()
  var msg = new SpeechSynthesisUtterance(text);
  if(control == 'Read Aloud'){
    $(card).find('.listen').text('Pause Player')
    window.speechSynthesis.cancel(msg);
    window.speechSynthesis.speak(msg);
  }else if (control == 'Pause Player'){
    $(card).find('.listen').text('Resume Player')
    window.speechSynthesis.cancel(msg);
  }else if (control == 'Resume Player'){
    $(card).find('.listen').text('Pause Player')
    window.speechSynthesis.resume(msg);
  } 
};
function removeNotification(iden) {
  $.get('/utils/remove_notification/' + iden, function(data){});
  n = document.getElementsByClassName('notification')
  for(i=0;i<n.length;i++){
    if(n[i].id == iden){
      n[i].remove()
    }
  }
};
function addNotification(word) {
  $.get('/utils/test_notification', function(data){});
};
function calendarWidget() {
  c = document.getElementById('calendarForm');
  c.classList.toggle('showForm');
};
function subNavWidget(value) {
  function activate(element, show, delay) {
    if (show) {
      element.classList.add('active');
    } else {
      if (delay) {
        setTimeout(function() {
            element.classList.remove('active');
        }, 200);
      } else {
        element.classList.remove('active');
      }
    }
  }

  navBar = document.getElementById('navBar')
  ul = navBar.getElementsByTagName('ul')[0]
  ul.classList.toggle('bottomBorder')
  li = navBar.getElementsByTagName('li')
  for(i=0;i<li.length;i++){
    if (li[i].classList.contains(value) || li[i].textContent.includes('Current') || li[i].textContent.includes('Upcoming')){
      if (li[i].classList.contains('active')) {
        activate(li[i], false, true)
      } else {
        activate(li[i], true, true)
      }
    } else {
      if (li[i].classList.contains('active')) { }
        activate(li[i], false, false)
    }
  }
  function activate_menu(element, show) {
    if (show) {
      element.classList.add('showFormA');
      setTimeout(function() {
          element.classList.add('showForm');
      }, 10);
    } else {
      element.classList.remove('showForm');
      setTimeout(function() {
          element.classList.remove('showFormA');
      }, 200);
    }
  }
  navOptions = document.getElementById('navOptions')
  subNavs = navOptions.getElementsByTagName('div')
  for(i=0;i<subNavs.length;i++){
    try{
      if (value == subNavs[i].id){
        if (subNavs[i].classList.contains('showForm')) {
          activate_menu(subNavs[i], false)
        } else {
          activate_menu(subNavs[i], true)
        }
      } else {
        if (subNavs[i].classList.contains('showForm')) {
          activate_menu(subNavs[i], false)
        }
      }
    }catch(err){
    }
  }
};
function sidebarSort(head) {
  var isMobile = document.getElementById('isMobile').name;

  if(head.includes('-')){
    var title = head.split('-')[0];
    var task = head.split('-')[1];
    if (isMobile == 'True'){
      var pages = document.getElementsByClassName('searchTabContent show block')[0];
      var list = pages.firstElementChild.nextElementSibling;
      a = pages;
      var items = list.childNodes;
      var itemsArr = [];
      for (var i in items) {
          if (items[i].nodeType == 1) { // remove whitespace text nodes
            itemsArr.push(items[i]);
          };
      };
      if(task == 'inst'){
        var b = title + '-alpha'
        $(a).children().first().remove()
        $(a).children().eq(1).remove()
        code = `<div><span class="sort" onclick="sidebarSort('` + b + `')">sort</span></div>`
        itemsArr.sort(function(a, b) {
          return a.innerHTML == b.innerHTML
                  ? 0
                : (parseInt(b.firstElementChild.firstElementChild.innerHTML.replace('(', '').replace(')','')) > parseInt(a.firstElementChild.firstElementChild.innerHTML.replace('(', '').replace(')','')) ? 1 : -1);
        });
      }else{
        var b = title + '-inst'
        $(a).children().first().remove()
        $(a).children().eq(1).remove()
        code = `<div><span class="sort" onclick="sidebarSort('` + b + `')">sort</span></div>`
        itemsArr.sort(function(a, b) {
          return a.innerHTML == b.innerHTML
                  ? 0
                  : (a.firstElementChild.innerHTML > b.firstElementChild.innerHTML ? 1 : -1);
        });
      };
      for (i = 0; i < itemsArr.length; ++i) {
        list.appendChild(itemsArr[i]);
      };
      $(a).prepend(code) 
    } else {
      var list = document.getElementById(title).nextElementSibling.firstElementChild;
      var items = list.childNodes;
      var itemsArr = [];
      for (var i in items) {
          if (items[i].nodeType == 1) {
            itemsArr.push(items[i]);
          };
      };
      if(task == 'inst'){
      a = document.getElementById(title);
      var b = title + '-alpha'
        $(a).children().first().next().remove()
        code = `<span class="sort" onclick="sidebarSort('` + b + `')">sort</span>`
        $(a).append(code) 
        itemsArr.sort(function(a, b) {
          return a.innerHTML == b.innerHTML
                  ? 0
                  : (parseInt(b.firstElementChild.firstElementChild.innerHTML.replace('(', '').replace(')','')) > parseInt(a.firstElementChild.firstElementChild.innerHTML.replace('(', '').replace(')','')) ? 1 : -1);
        });
      }else{
        a = document.getElementById(title);
        var b = title + '-inst'
        $(a).children().first().next().remove()
        code = `<span class="sort" onclick="sidebarSort('` + b + `')">sort</span>`
        $(a).append(code) 
        itemsArr.sort(function(x, y) {
          return x.innerHTML == y.innerHTML
                  ? 0
                  : (x.firstElementChild.innerHTML > y.firstElementChild.innerHTML ? 1 : -1);
        });
      };
      for (i = 0; i < itemsArr.length; ++i) {
        list.appendChild(itemsArr[i]);
      };
    };
  
  }else{
    // clear notificationss
  };

};
function insertEmbed(iden, link) {
  var card = document.getElementById(iden);
  var word = $(card).find('.watch').text();
  if (word == 'Watch') {
    code = '<iframe class="EmbedContent" src="' + link + '" allowfullscreen></iframe>';
    $(card).find('.Embed').prepend(code)  ;
    $(card).find('.watch').text('Close Player');
  } else {
    $(card).find('.Embed').empty();
    $(card).find('.watch').text('Watch')
  };
};
function tocNav(item) {
  console.log('-tocNav',item);
  var hs = document.getElementsByTagName('h2');
  for (i=0; i<hs.length; i++) {
    if (hs[i].outerHTML.includes(item)) {
      scrollToElement(hs[i], 10, true);
      // .scrollIntoView({ behavior: 'smooth', block: 'start' });
      break;
    };
  };
  item = item.replaceAll("'", '"');
  var hs = document.querySelectorAll("[style*='text-align:Center']");
  for (i=0; i<hs.length; i++) {
    if (hs[i].outerHTML.includes(item)) {
      scrollToElement(hs[i], 10, true);
      // hs[i].scrollIntoView({ behavior: 'smooth', block: 'start' });
      break;
    };
  };
  function searchelement(elementhtml) {
    try {
      [...document.querySelectorAll("*")].forEach((ele)=>{
        if (ele.outerHTML == elementhtml) {
          scrollToElement(ele, 10, true);
          // ele.scrollIntoView({ behavior: 'smooth', block: 'start' });
          // break
        };
      });
    } catch (err) {console.log(err)}
  };
  searchelement(item);
  var isMobile = document.getElementById('isMobile').name;
  if (isMobile == 'True') {
    mobileSwitch('drawer4');
  };
};
function continue_reading(iden, direction) {
  var card = document.getElementById(iden);
    if (direction == 'more') {
      try {
        $(card).find('.Text').addClass('showFullText');
        $(card).find('.TextContent').addClass('showFullText');
        $(card).find('.fadeOut').remove();
        $(card).find('.TextContent').next().text("Read Less");
        $(card).find('.TextContent').next().attr("onclick","continue_reading('" + iden + "', 'less')");
      } catch (err) {};
    } else if (direction == 'less') {
      try {
        $(card).find('.Text').removeClass('showFullText');
        $(card).find('.TextContent').removeClass('showFullText');
        $(card).find('.TextContent').next().text("Read More");
        $(card).find('.TextContent').next().attr("onclick","continue_reading('" + iden + "', 'more')");
        var text = card.getElementsByClassName('TextContent')[0];
        fade = "<div class='fadeOut'></div>";
        $(text).append(fade);
        scrollToElement(card);
      } catch (err) {};
    } else {
      $.get('/utils/continue_reading/' + iden + '/?topic=' + direction, function(data) {
        $(card).find('.Terms').text("");
        $(card).find('.Terms').append(data);
        $(card).find('.Terms').next().text("");
        $(card).find('.readMoreTerms').text("");
      });
    };
};
function show_all(iden, item) {
  try {
      var subscribers = document.getElementsByClassName('showAllCentered');
      for (i=0; i<subscribers.length; i++) {
          subscribers[i].outerHTML = "";
      }
  } catch (err) { alert(err) };
  if (item != 'function close() { [native code] }') {
      $.get('/utils/show_all/' + iden + '/' + item, function(data) {
          if (item == 'terms') {
            title = 'All Topics';
          } else {
            title = "All Speakers";
          };
          code = '<div class="showAllCentered"><div id="showAllClose" onclick="show_all(100, close)">Close</div><div id="title">' + title + '</div>' + data  + '</div>';
          $('#container').prepend(code);
      });
  };
};
async function loadScript(url, callback) {
  console.log('-loadScript')
  const script = document.createElement('script');
  script.src = url;
  script.async = false; // Optional: load asynchronously
  script.onload = () => {
    console.log(`Script loaded: ${url}`);
    if (callback) callback();
  };
  script.onerror = () => {
    console.error(`Failed to load script: ${url}`);
  };
  document.head.appendChild(script);
};
function showDarkenOverlay() {
  // console.log('-showDarkenOverlay')
  const overlay = document.querySelector('.darkenOverlay');
  overlay.style.display = 'block';
  requestAnimationFrame(() => {
    overlay.classList.add('darken');
  });
};
function hideDarkenOverlay() {
  // console.log('-hideDarkenOverlay')
  function activate() {
    const overlay = document.querySelector('.darkenOverlay');
    overlay.classList.remove('darken');
    overlay.addEventListener('transitionend', function handleFade() {
      overlay.style.display = 'none';
      overlay.removeEventListener('transitionend', handleFade);
    });
  };
  try {
    activate();
  } catch (err) {};
};


async function generatePassword(field="password") {
  console.log('-generatePassword')
  const mnemonic = await generateMnemonic()
  var form = document.getElementById("modalForm");
  form.elements[field].value = mnemonic;
};
function displayPassword(btn="showPassword", field="password") {
    var clicker = document.getElementById(btn);
    // console.log('-displayPassword',clicker.innerHTML, btn, field)
    if (clicker.innerHTML == 'visibility_off') {
        clicker.innerHTML = 'visibility_on';
        var x = document.getElementById(field);
        x.type = "text";
    } else if (clicker.innerHTML == 'visibility_on') {
        clicker.innerHTML = 'visibility_off';
        var x = document.getElementById(field);
        x.type = "password";
    } else if (clicker.innerHTML == 'Show Passphrase') {
        clicker.innerHTML = 'Hide Passphrase';
        var x = document.getElementById(field);
        x.type = "text";
    } else if (clicker.innerHTML == 'Hide Passphrase') {
        clicker.innerHTML = 'Show Passphrase';
        var x = document.getElementById(field);
        x.type = "password";
    } else if (clicker.innerHTML == 'Show') {
        clicker.innerHTML = 'Hide';
        var x = document.getElementById(field);
        x.type = "text";
    } else if (clicker.innerHTML == 'Hide') {
        clicker.innerHTML = 'Show';
        var x = document.getElementById(field);
        x.type = "password";
    };
};


function modalPopPointer(value){
  items = value.split(', ')
  modalPopUp(items[0].replace(/"/g, ''), items[1].replace(/"/g, ''))
}
async function modalPopUp(title, target=null, content=null) {
  console.log('-modalPopUp',target);
  mobileSwitch(null);
  var isMobile = document.getElementById('isMobile').name;
  // console.log('ismobile:',isMobile);
  showDarkenOverlay();
  m = document.getElementsByClassName('modalWidget')[0];
  modal = $('.modalWidget');
  if (target == 'so_modal') {
    content = await getItem(target);
  }
  if (content != null) {
    m.querySelector("#modalContent").innerHTML = sanitize(content);
  } else if (target != null) {
    code = '<div class="lds-dual-ring"></div>';
    console.log('code',code);
    m.querySelector("#modalContent").innerHTML = sanitize(code);
  };
  
  m.querySelector("#modalTitle").innerHTML = sanitize(title);
  modal.addClass('show');
  setTimeout(function() {
    modal.addClass('fade-in');
  }, 10);

  if (target != null) {
    if (target.includes('/')) {
      target = target
    } else {
      target = '/utils/default_modal/' + target
    }
    try {
      userData = JSON.parse(await getItem('userData'))
      if (target.includes('?')){
        target = target + '&userId=' + userData['id']
      } else {
        target = target + '?userId=' + userData['id']
      }
    } catch(err) {};

    const data = await connect_to_node(target);
    // console.log('modal response:', data);
    if (data) {
        var html = $('<html>').html(data);
        var new_title = html.find('title').text();
        m.querySelector("#modalTitle").innerHTML = sanitize(new_title);
        var instruction = html.find('#instruction').attr('value');
        content = sanitizeWithException(data, ['loginRequest','modifyKey','generatePassword','displayPassword','modalPopUp','onFormSubmit','react','mobileShare']);
        m.querySelector("#modalContent").innerHTML = content;
          if (target.includes('so_modal')) {
            storeItem(content, 'so_modal');
          }
        enact_user_instruction(instruction, {});
      const usernameInput = document.getElementById("username");
      const statusSpan = document.getElementById("username-status");
      if (!usernameInput || !statusSpan) return;

      let timeout = null;

      usernameInput.addEventListener("input", function () {
          clearTimeout(timeout);
          const username = usernameInput.value;
          if (!username.trim()) {
              statusSpan.textContent = "";
              return;
          }

          timeout = setTimeout(() => {
              fetch(`/accounts/username_avail/?username=${encodeURIComponent(username)}`)
                  .then(response => response.json())
                  .then(data => {
                      if (data.available) {
                          // statusSpan.textContent = " ✓";
                          statusSpan.textContent = "Available";
                          statusSpan.style.color = "green";
                      } else {
                          // statusSpan.textContent = " ✗";
                          statusSpan.textContent = "Not Available";
                          statusSpan.style.color = "red";
                      };
                  })
                  .catch(error => {
                      statusSpan.textContent = "Error";
                      statusSpan.style.color = "gray";
                  });
          }, 300);
      });

    } else {
      console.log('no data returned')
      m.querySelector("#modalContent").innerHTML = 'Failed to reach server';
    };
  };
  return m;
};
function closeModal(m=null, close_nav=true) {
  // console.log('-close modal');
  if (m == null) {
    m = document.getElementsByClassName('modalWidget')[0];
  };
  if (m == null) {
    return
  };
  modal = $('.modalWidget');
  modal.removeClass('fade-in');
  modal.addClass('fade-out');
  var isMobile = document.getElementById('isMobile').name;
  // console.log('isMobile',isMobile);
  if (isMobile == 'True' && close_nav) {
    mobileSwitch(null, close_modal=false);
    modal.removeClass('show');
    modal.removeClass('fade-out');
    hideDarkenOverlay();
  } else {
    function handleTransition(event) {
      modal.removeClass('show');
      modal.removeClass('fade-out');
      m.removeEventListener('transitionend', handleTransition);
    };
    try {
      m.addEventListener('transitionend', handleTransition);
      hideDarkenOverlay();
    } catch(err) {console.log('closeModal err',err)};
  };
};
function removeModalClose() {
  btn = document.getElementsByClassName('modalWidgetClose')[0];
  btn.setAttribute('onclick','');
  btn.innerHTML = '-';
};


function onFormSubmit(evt) {
  // Prevent default form submission so credentials never hit query params.
  if (!evt && typeof window !== 'undefined') {
    evt = window.event;
  };
  if (evt && evt.preventDefault) {
    evt.preventDefault();
  };
  return false;
};
function encryptMessage(publicKey, keyPair, message) {
  console.log('-encrypt_message')
  const curve = new elliptic.ec('secp256k1');
  const recipientKey = curve.keyFromPublic(publicKey, 'hex');
  const sharedSecret = keyPair.derive(recipientKey.getPublic());
  const sharedKey = CryptoJS.enc.Hex.parse(sharedSecret.toString(16).slice(0, 32));

  const iv = CryptoJS.lib.WordArray.random(16);
  const encrypted = CryptoJS.AES.encrypt(message, sharedKey, { iv: iv });
  return {
    iv: iv.toString(CryptoJS.enc.Hex),
    encrypted: encrypted.toString()
  };
};
function decryptMessage(privateKey, publicKey, encryptedData) {
    console.log('-decrypt_message')
    const curve = new elliptic.ec('secp256k1');
    const { iv, encrypted } = encryptedData;
    const recipientKey = curve.keyFromPublic(publicKey, 'hex');
    const privKey = curve.keyFromPrivate(privateKey, 'hex');
    const sharedSecret = privKey.derive(recipientKey.getPublic());
    const sharedKey = CryptoJS.enc.Hex.parse(sharedSecret.toString(16).slice(0, 32));
    const decrypted = CryptoJS.AES.decrypt(encrypted, sharedKey, {
        iv: CryptoJS.enc.Hex.parse(iv)
    });
    return decrypted.toString(CryptoJS.enc.Utf8);
};


function getSigData(received_data, first_key = true) {
    if (received_data.signed) {
        received_data = received_data.signed;
    };
    const keys = Object.keys(received_data).sort();
    if (!keys.length) return null;

    const dt = first_key
        ? keys[0]
        : keys.at(-1);
    return {
        dt: formatDateToDjango(dt),
        pk: received_data[dt].pk,
        sig: received_data[dt].sig,
        publicKey: received_data[dt].publicKey
    };
};
async function verifyUserData(userData, localData=false) {
  x = await getItem('userData');
  console.log('-verify userData...');
  try {
    userData = JSON.parse(userData);
  } catch(err) {};
  const sig_data = getSigData(userData);
  receivedPubKey = sig_data['pk'];
  if (receivedPubKey == null || receivedPubKey == 'null') {
    return false;
  };
  var localPubKey = await getItem("Sign_PubKey"); // careful of recently renewed keys here
  if (receivedPubKey != localPubKey) {
      return false;
  };
  const sig = sig_data['sig'];
  userData.signed[sig_data['dt']] = {'pk':sig_data['pk']};
  try {
    delete userData.latestVer;
  } catch (err) {};

  const sortedData = sortForSign(userData);
  is_valid = await verify(sortedData, sig, localPubKey);
  return is_valid;
};


function makeAjaxRequest(data, link, item) {
  // console.log('-makeAjax request', link)
  return new Promise((resolve, reject) => {
    $.ajax({
      type: 'POST',
      url: link,
      data: data,
      success: function(response) {
        resolve({ response, item });
      },
      error: function(xhr, status, error) {
        console.log('ajax err1', error);
        reject(error)
      }
    });
  });
};


async function loginRequest(url = '/accounts/get_user_login', csrf = null, wallet_data = null, upk_data = null) {
  const addr = await myVar("last_accessed_url");
  url = format_url(url, addr);
  console.log('l-oginRequest',url);
  var form = document.getElementById("modalForm");
  var username = form.elements["username"].value;
  var password = form.elements["password"].value;
  logoutWhenInactive = document.getElementById('logoutInactive').checked;
  console.log("Username:", username);
  var field0 = document.getElementById('field0');
  var field3 = document.getElementById('field3');
  var field4 = document.getElementById('field4');
  field0.innerHTML = ''
  field3.style.display = 'none';
  if (username == '') {
      field0.innerHTML = 'Please enter a username';
      field0.style.color = 'red';
      field0.style.display = '';
      return
  }else if (password == '') {
      field0.innerHTML = 'Please enter a passphrase';
      field0.style.color = 'red';
      field0.style.display = '';
      return
  } else {
    field4.style.color = '';
    field4.innerHTML = 'Loading...';
    var field5 = document.getElementById('field5');
    field5.style.display = 'none';

    const data = {};
    data['username'] = username;
    data['csrfmiddlewaretoken'] = csrf;
    makeAjaxRequest(data, url, {'password':password,'username':username})
      .then(loginResponse)
      .catch(error => {
        console.error('There was a problem with the AJAX request:', error);
    });  
  };
};
async function loginResponse({ response, item }) {
  console.log('-loginResponse',response);
  var password = item['password'];
  var username = item['username'];
  var field0 = document.getElementById('field0');
  var field3 = document.getElementById('field3');
  var field4 = document.getElementById('field4');
  field0.innerHTML = '';
  field4.innerHTML = '';
  message = response['message'];
  // console.log(message);
  login_btn = `<button style='color: black;' type="submit" onclick="loginRequest('/accounts/get_user_login')">Continue</button>`;
  signup_btn = `<button style='color: black;' type="submit" onclick="loginRequest('/accounts/create_user')">Continue</button>`;
  switch_to_new_btn = `<button style='color: black;' onclick="modalPopUp('Signup', '/accounts/signup')">New User</button>`;
  switch_to_restore_btn = `<button style='color: black;' type="submit" onclick="modalPopUp('Login', '/accounts/login-signup')">Restore User</button>`;
  or_text = `<span style="display: block; margin-top: 10px; margin-bottom: 12px;">or</span>`;
  const postData = {};
  if (message == 'User exists') {
    field4.innerHTML = 'Username not available';
    field4.style.color = 'red';
    field4.style.display = '';
    var field5 = document.getElementById('field5');
    field5.innerHTML = signup_btn + or_text + switch_to_restore_btn;
    field5.style.display = '';
    field3.style.display = '';
    return
  } else if (message == 'User not found' || message == 'Invalid Passphrase' || message == 'Verification failed') {
    field4.innerHTML = sanitize(message);
    field4.style.color = 'red';
    field4.style.display = '';
    var field5 = document.getElementById('field5');
    field5.innerHTML = login_btn + or_text + switch_to_new_btn;
    field5.style.display = '';
    field3.style.display = '';
    return
  } else if (message == 'Create User') {
    receivedUserData = JSON.parse(response['userData']);
    const now = get_current_time();
    field4.innerHTML = 'Please Wait,<br>Generating Quantum Safe<br>Login Keys...';
    account_keyPair = await createKeyPair(receivedUserData['id'], password, 'account', key_strength='ML_DSA_44');
    field4.innerHTML = 'Generating Signing Keys...';
    signing_keyPair = await createKeyPair(receivedUserData['id'], now+password, 'signing', key_strength='secp256k1');
    // console.log('account_keyPair', account_keyPair);
    privKey = account_keyPair[0];
    pubKey = account_keyPair[1];
    console.log('creating user');
    field4.innerHTML = 'Signing Request...';
    // walletData = JSON.parse(response['walletData']);
    // walletData['created'] = now;
    // walletData['User_obj'] = receivedUserData['id'];
    // walletData['Name'] = 'Main';
    // walletData = await sign_data(walletData, privKey=privKey, pubKey=pubKey, key_type='ML_DSA_44', null, null, true);
    // postData['walletData'] = JSON.stringify(walletData);

    upkData = JSON.parse(response['upkData']);
    upkData['id'] = await generateId(pubKey, upk=true);
    upkData['created'] = now;
    upkData['User_obj'] = receivedUserData['id'];
    upkData['commitChain'] = 'Keys';
    upkData['publicKey'] = pubKey;
    upkData['algorithm'] = 'ML_DSA_44';
    upkData['keyType'] = 'account';
    upkData = await sign_data(upkData, privKey=privKey, pubKey=pubKey, key_type='ML_DSA_44', null, null, true);
    // console.log('signed upkData accnt',upkData);
    postData['upkData_accnt'] = JSON.stringify(upkData);
    
    upkData = JSON.parse(response['upkData']);
    upkData['id'] = await generateId(signing_keyPair[1], upk=true);
    upkData['created'] = now;
    upkData['User_obj'] = receivedUserData['id'];
    upkData['commitChain'] = 'Keys';
    upkData['publicKey'] = signing_keyPair[1];
    upkData['algorithm'] = 'secp256k1';
    upkData['keyType'] = 'signing';
    upkData = await sign_data(upkData, privKey=privKey, pubKey=pubKey, key_type='ML_DSA_44', null, null, true);
    // console.log('signed upkData signing',upkData);
    postData['upkData_sign'] = JSON.stringify(upkData);

    userData = receivedUserData;
    userData['username'] = username;
    userData['created'] = now;
    userData['networkChain'] = receivedUserData['id'];
    userData['commitChain'] = 'Accounts';
    userData['UserData_obj'] = 'Val:N';
    userData['signkey_dt'] = now;
    userData = await sign_userData(userData, privKey=privKey, pubKey=pubKey, key_type='ML_DSA_44');
  } else if ((message == 'User found')) {
    receivedUserData = JSON.parse(response['userData']);
    field4.innerHTML = 'Loading Libraries...';
    await loadLibs();
    field4.innerHTML = 'Please Wait,<br>Generating Quantum Safe<br>Login Keys...';
    account_keyPair = await createKeyPair(receivedUserData['id'], password, 'account', key_strength='ML_DSA_44');
    field4.innerHTML = 'Generating Signing Keys...';
    signing_keyPair = await createKeyPair(receivedUserData['id'], receivedUserData['signkey_dt']+password, 'signing', key_strength='secp256k1');
    privKey = account_keyPair[0];
    pubKey = account_keyPair[1];
    stored_userData = get_stored_userData();
    if (stored_userData != null && stored_userData != 'null' && stored_userData['id'] == receivedUserData['id'] && stored_userData['username'] == receivedUserData['username']) {
      is_valid = await verifyUserData(response['userData']);
      console.log('userdata verify:', is_valid);
      if (Date(userData['lastUpdate']) < Date(receivedUserData['lastUpdate'])) {
        if (is_valid) {
          // userData was updated on a different server more recently than this device
          userData = receivedUserData;
          // userArrayData = receivedUserArrayData
          console.log('updated userData from server');
        } else {
          // received data is not valid
          userData = stored_userData;
        };
      } else {
        // device userData is up to date
        userData = stored_userData;
      };
      // } else {
      //   // receivedUserData does not match local userData
      // }
    } else { 
      // local userData not found
      userData = receivedUserData;
      // userArrayData = receivedUserArrayData
      console.log('updated userData from server')
    };
    // console.log('sign sign_userData', userData)
    field4.innerHTML = 'Signing Request...';
    userData = await sign_data(userData, privKey=privKey, pubKey=pubKey, key_type='ML_DSA_44', null, null, false);
  } else {
    field4.innerHTML = sanitize(message);
    field4.style.color = 'red';
    field4.style.display = '';
    var field5 = document.getElementById('field5');
    field5.innerHTML = login_btn + or_text + switch_to_new_btn;
    field5.style.display = '';
    field3.style.display = '';
    return
  };
  postData['userData'] = JSON.stringify(userData);
  field4.innerHTML = 'Submitting Request...';
  var url = '/accounts/receive_user_login';
  const resp = await connect_to_node(url, postData);
  console.log('modal response:', resp);
  if (resp) {
      if (resp['message'] == 'Invalid Passphrase' || resp['message'] == 'Verification failed') {
          field4.innerHTML = sanitize(resp['message']);
          field4.style.color = 'red';
          var field5 = document.getElementById('field5');
          field5.innerHTML = login_btn + or_text + switch_to_new_btn;
          field5.style.display = '';
          field3.style.display = '';
      } else if (resp['message'] == 'Valid Username and Password'||resp['message'] == 'User Created') {
        field4.style.color = 'green';
        field4.innerHTML = 'Accepted';
        field4.style.display = '';
        field3.innerHTML = '';
        console.log('proceed to login');
        upk_id = await generateId(signing_keyPair[1], upk=true);
        storeItem(upk_id, 'upkId');
        storeItem(signing_keyPair[0], 'Sign_PrivKey');
        storeItem(signing_keyPair[1], 'Sign_PubKey');
        storeItem(password, 'password');
        storeItem(JSON.parse(resp['userData'])['username'], 'username');
        storeItem(JSON.parse(resp['userData'])['id'], 'user_id');
        storeItem(JSON.stringify(userData), 'userData');
        login()
      } else {
        field4.innerHTML = sanitize(resp['message']);
        field4.style.color = 'red';
        field4.style.display = '';
        var field5 = document.getElementById('field5');
        field5.innerHTML = login_btn + or_text + switch_to_new_btn;
        field5.style.display = '';
        field3.style.display = '';
        try {
          username = await getItem("username");
          pass = await getItem("password");
          if (username != 'null' && username != null) {
            var str_pass = JSON.stringify(pass);
            var field4 = document.getElementById('field4');
            field4.innerHTML = `<button id="clearUser" style="color: black;" type="submit" onclick='clearLocalUserData(`+str_pass+`)'>Clear Local User Data</button>`;            
            var field5 = document.getElementById('field5');
            field5.style.display = '';
          };
        } catch(err) {}
      };
  } else {
      field4.innerHTML = 'Failed to reach server';
      field4.style.color = 'red';
      field4.style.display = '';
      var field5 = document.getElementById('field5');
      field5.style.display = '';
  };      
};
async function login() {
  console.log('-login')
  index = document.getElementById('navigation');
  if (index) {
    index.innerHTML = '<div class="lds-dual-ring"></div>';
  };
  user_id = await myVar('user_id')
  // var logoutWhenInactive = await getItem("logoutWhenInactive");
  url = '/accounts/get_index?user=' + user_id;
  const addr = await myVar("last_accessed_url");
  var url = format_url(url, addr);
  console.log('url',url);
  $.ajax({
    url:url,
    success:function(response){
      closeModal();
      displayStoredNavigation(fadeIn=true, savedNav=response);
      storeItem(null, 'navigationHtml');
      storeNavigation();
      if (logoutWhenInactive == true) {
        resetInactivityTimer(); // start logout timer
      };
    },
  });
};
async function logout(target="/accounts/logout") {
  console.log('-logout',target);
  mobileSwitch(null);
  user_id = await myVar('user_id');
  const resp = await connect_to_node(target + '?user=' + user_id);
  console.log('modal response:', resp);
  if (resp) {
      window.myVars = {};
      storeItem(null, 'Accnt_PrivKey');
      storeItem(null, 'Accnt_PubKey');
      storeItem(null, 'Sign_PrivKey');
      storeItem(null, 'Sign_PubKey');
      storeItem(null, 'username');
      storeItem(null, 'userData');
      storeItem(null, 'password');
      storeItem(null, 'user_id');
      storeItem(null, 'navigationHtml');
      location.reload();
  } else {
    alert('Failed to reach server');
  };
};

async function modifyKey(blank_upkData, keyType, keyStrength, requires, extra_data=null) {
  console.log('-modifyKey',keyType,keyStrength,requires)
  const addr = await myVar("last_accessed_url");
  const user_id = await myVar('user_id');
  const sign_upkId = await getItem("upkId");
  const sign_privKey = await getItem("Sign_PrivKey");
  const sign_pubKey = await getItem("Sign_PubKey");

  var field0 = document.getElementById('field0');
  var field3 = document.getElementById('field3');
  var field4 = document.getElementById('field4');
  var current_upkData = null;
  var userData = null;
  var additional_upks = null;
  var security_keyPair = null;
  var new_signing_keyPair = null;
  const postData = {'sig_map':{}};

  if (extra_data) {
    current_upkData = extra_data['current_upkData'];
    userData = extra_data['userData'];
    additional_upks = extra_data['additional_upks'];
    accnt_upkId = extra_data['accnt_upkId'];
    if (current_upkData) {
      current_upkData = JSON.parse(extra_data['current_upkData']);
    };
  };

  var form = document.getElementById("modalForm");
  try {
    var accountPassword = form.elements["accountPassword"].value;
  } catch (err) {
    var accountPassword = null;
  };
  try {
    var securityPassword = form.elements["securityPassword"].value;
  } catch (err) {
    console.log('sec_pass err',err);
    var securityPassword = null;
  };
  try {
    var newPassword = form.elements["newPassword"].value;
  } catch (err) {
    var newPassword = null;
  };
  
  field0.innerHTML = '';
  field3.style.display = 'none';
  if (accountPassword == '') {
      field4.innerHTML = 'Please enter your login passphrase';
      field4.style.color = 'red';
      field4.style.display = '';
      return
  }else if (requires != 'account' && securityPassword == '') {
      field4.innerHTML = 'Please enter your security passphrase';
      field4.style.color = 'red';
      field4.style.display = '';
      return
  }else if (newPassword == '') {
      field4.innerHTML = 'Please enter a passphrase';
      field4.style.color = 'red';
      field4.style.display = '';
      return

  // } else if (password.length < 20) {
  //   field0.innerHTML = 'Please enter at least 20 characters in password.'
  } else {
    if (newPassword == null && accountPassword != null) {
      newPassword = accountPassword;
    };
    field4.style.color = '';
    field4.innerHTML = 'Loading...';
    var field5 = document.getElementById('field5');
    field5.style.display = 'none';
    field4.innerHTML = 'Loading Libraries...';
    await loadLibs();
    try {
      if (accountPassword) {
        field4.innerHTML = 'Regenerating Account Keys...';
        account_keyPair = await createKeyPair(user_id, accountPassword, 'account', key_strength='ML_DSA_44');
        account_privKey = account_keyPair[0];
        account_pubKey = account_keyPair[1];
        account_upkId = await generateId(account_pubKey, upk=true);
        if (accnt_upkId) {
          if (accnt_upkId != account_upkId) {
            field4.innerHTML = 'Wrong account passphrase';
            field4.style.color = 'red';
            field4.style.display = '';
            return
          };
        };
      };
      if (securityPassword) {
        field4.innerHTML = 'Regenerating Security Keys...';
        security_keyPair = await createKeyPair(user_id, securityPassword, 'security', key_strength=requires);
        security_privKey = security_keyPair[0];
        security_pubKey = security_keyPair[1];
        security_upkId = await generateId(security_pubKey, upk=true);
        console.log('security_upkId',security_upkId);
      };

      const now = get_current_time();
      if (accountPassword) {
        field4.innerHTML = 'Generating New Key Pair...';
        signkey_dt = formatDateToDjango(now);
        if (keyType == 'signing') {
          // requires account key id and account passphrase
          // signs prev signing key with account key if req'd else with prev signing key
          // creates new signing key signed by prev signing key

          new_keyPair = await createKeyPair(user_id, signkey_dt+newPassword, keyType, key_strength='secp256k1');
          new_signing_keyPair = new_keyPair;
          // if new signing key is successful, remember to save to browser
        } else {
          // account, security and other keys require new password
          new_keyPair = await createKeyPair(user_id, newPassword, keyType, key_strength=keyStrength);
        };
        new_privKey = new_keyPair[0];
        new_pubKey = new_keyPair[1];
      };

      if (blank_upkData) {
        // may be account, security or signing
        var blank_upkData_copy = structuredClone(blank_upkData);
        blank_upkData['id'] = await generateId(new_pubKey, upk=true);
        blank_upkData['created'] = now;
        blank_upkData['User_obj'] = user_id;
        blank_upkData['publicKey'] = new_pubKey;
        blank_upkData['algorithm'] = keyStrength;
        blank_upkData['keyType'] = keyType;
        field4.innerHTML = 'Signing New Key...';

        if (requires == 'signing') {
          console.log('sign with signing');
          // if new key is signing key, sign with previous signing key, not account or security
          new_upkData = await sign_data(blank_upkData, privKey=sign_privKey, pubKey=sign_pubKey, key_type=null);
          postData['sig_map'][new_upkData['id']] = [sign_upkId];
        } else {
          console.log('sign with account');
          new_upkData = await sign_data(blank_upkData, privKey=account_privKey, pubKey=account_pubKey, key_type=null);
          postData['sig_map'][new_upkData['id']] = [account_upkId];
          if (security_keyPair) {
            console.log('sign with security');
            new_upkData = await sign_data(new_upkData, privKey=security_privKey, pubKey=security_pubKey, key_type=null, null, 'current');
            postData['sig_map'][new_upkData['id']].push(security_upkId);
          };
        };
        postData['new_upkData'] = JSON.stringify(new_upkData);
      };

      if (current_upkData) {
        const currentDate = new Date();
        const future = new Date(currentDate.getTime() + 3 * 60 * 1000); // 3 mins in future
        const isoString = future.toISOString();
        const end_life_dt = formatDateToDjango(isoString);

        field4.innerHTML = 'Updating Old Key...';
        current_upkData['end_life_dt'] = end_life_dt;
        updated_upkData = await sign_data(current_upkData, privKey=account_privKey, pubKey=account_pubKey, key_type=null, null);
        postData['sig_map'][updated_upkData['id']] = [account_upkId];
        if (security_keyPair) {
          updated_upkData = await sign_data(updated_upkData, privKey=security_privKey, pubKey=security_pubKey, key_type=null, null, 'current');
          postData['sig_map'][updated_upkData['id']].push(security_upkId);
        };
        postData['updated_upkData'] = JSON.stringify(updated_upkData);

        if (additional_upks) {
          // only used when current_upkData.keyType == 'account
          // if changing account key, also rotate signing key
          // if disabling account, disable all active keys
          additional_upks = JSON.parse(extra_data['additional_upks']);
          postData['additional_upks'] = {'new':[], 'previous':[]};
          for (const additional_upk of additional_upks) {
            console.log('additional_upk',additional_upk);
            if (additional_upk) {
              field4.innerHTML = 'Disabling Previous ' + additional_upk['keyType'][0].toUpperCase()+additional_upk['keyType'].slice(1) + ' Key...';
              additional_upk['end_life_dt'] = end_life_dt;
              updated_upk = await sign_data(additional_upk, privKey=account_privKey, pubKey=account_pubKey, key_type=null, null);
              postData['sig_map'][updated_upk['id']] = [account_upkId];
              if (security_keyPair) {
                updated_upk = await sign_data(updated_upk, privKey=security_privKey, pubKey=security_pubKey, key_type=null, null, 'current');
                postData['sig_map'][updated_upk['id']].push(security_upkId);
              };
              postData['additional_upks']['previous'].push(updated_upk);

              if (blank_upkData) {
                // would only be signing key after changing account key
                field4.innerHTML = 'Generating New ' + additional_upk['keyType'][0].toUpperCase()+additional_upk['keyType'].slice(1) + ' Key...';

                new_signing_keyPair = await createKeyPair(user_id, signkey_dt+newPassword, keyType, key_strength=additional_upk['algorithm']);
                signing_privKey = new_signing_keyPair[0];
                signing_pubKey = new_signing_keyPair[1];

                blank_upkData_copy['id'] = await generateId(signing_pubKey, upk=true);
                blank_upkData_copy['created'] = now;
                blank_upkData_copy['User_obj'] = user_id;
                blank_upkData_copy['publicKey'] = signing_pubKey;
                blank_upkData_copy['algorithm'] = 'secp256k1';
                blank_upkData_copy['keyType'] = 'signing';
                field4.innerHTML = 'Signing Key...';

                // if new key is signing key, sign with previous signing key, not account or security
                new_upkData = await sign_data(blank_upkData_copy, privKey=sign_privKey, pubKey=sign_pubKey, key_type=null);
                postData['sig_map'][new_upkData['id']] = [sign_upkId];
                postData['additional_upks']['new'].push(new_upkData);
              };
            };
          };
          postData['additional_upks'] = JSON.stringify(postData['additional_upks']);
        };
      };
      if (userData) {
        // if keyType == 'signing' or keyType == 'account'
        // if rotated signing key, also update user data
        userData = JSON.parse(extra_data['userData']);
        field4.innerHTML = 'Updating User Data...';
        userData['signkey_dt'] = signkey_dt;
        updated_userData = await sign_data(userData, privKey=account_privKey, pubKey=account_pubKey, key_type=null);
        postData['sig_map'][updated_userData['id']] = [account_upkId];
        postData['updated_userData'] = JSON.stringify(updated_userData);
      };

      field4.innerHTML = 'Uploading New Data...';

      // if modifying account key or security key, should send to multiple nodes

      var url = '/user/settings?style=popup&cmd=update_key';
      const resp = await connect_to_node(url, postData);
      console.log('modal response:', resp);
      if (resp) {
          if (resp['message'] == 'Valid') {
            field4.innerHTML = sanitize(resp['msg']);
            field4.style.color = 'green';
            field4.style.display = '';
            if (new_signing_keyPair) {
              storeItem(await generateId(new_signing_keyPair[1], upk=true), 'upkId');
              storeItem(new_signing_keyPair[0], 'Sign_PrivKey');
              storeItem(new_signing_keyPair[1], 'Sign_PubKey');
            };
            if (keyType == 'account') {
              storeItem(newPassword, 'password');
            };
            if (userData) {
              storeItem(JSON.stringify(updated_userData), 'userData');
            };
          } else if (resp['message'] == 'Invalid') {
            field4.innerHTML = sanitize(resp['message']) + ' - ' + sanitize(resp['error']);
            field4.style.color = 'red';
            field4.style.display = '';
            var field5 = document.getElementById('field5');
            field5.style.display = '';
            field3.style.display = '';
          } else if (resp['message'] == 'Fail') {
            field4.innerHTML = sanitize(resp['msg']);
            field4.style.color = 'red';
            field4.style.display = '';
            var field5 = document.getElementById('field5');
            field5.style.display = '';
            field3.style.display = '';
          };
        } else {
            field4.innerHTML = 'Failed contact';
            field4.style.color = 'red';
            field4.style.display = '';
        };
    } catch(err) {
        field4.innerHTML = 'error ' + err;
        field4.style.color = 'red';
        field4.style.display = '';
    };
  };
};


async function clearLocalUserData(pass) {
  console.log('-clearLocalUserData');
  if (pass == await getItem("password")) {
    await storeItem(null, 'Sign_PrivKey');
    await storeItem(null, 'Sign_PubKey');
    await storeItem(null, 'username');
    await storeItem(null, 'userData');
    await storeItem(null, 'password');
    await storeItem(null, 'user_id');
    var field4 = document.getElementById('field4');
    field4.innerHTML = 'Cleared';
  };
};
function storeNavigation() {
  // console.log('-storeNavigation');
  var navHtml = document.querySelector("#navigation");
  if (navHtml && navHtml.innerHTML.includes('dual-ring')) {
    return
  } else if (navHtml && navHtml.innerHTML) {
    if (!navHtml.innerHTML.includes('dual-ring')) {
      const cleaned = sanitizeWithException(navHtml.innerHTML, ["modalPopUp", "logout", "themer", "select_node", "direct_to", "mobileSwitch"]);
      storeItem(cleaned,"navigationHtml");
    };
  } else {
    var navHtml = document.querySelector(".drawer1");
    if (navHtml && navHtml.innerHTML.includes('dual-ring')) {
      return
    } else if (navHtml && navHtml.innerHTML) {
      if (!navHtml.innerHTML.includes('dual-ring')) {
        const cleaned = sanitizeWithException(navHtml.innerHTML, ["modalPopUp", "logout", "themer", "select_node", "direct_to", "mobileSwitch"]);
        // console.log('cleaned',cleaned)
        storeItem(cleaned,"navigationHtml");
      };
    };
  };
};
async function displayStoredNavigation(fadeIn=true, savedNav=null) {
  // console.log('-displayStoredNavigation', savedNav);
  if (savedNav) {
    var savedNav = sanitizeWithException(savedNav, ["modalPopUp", "logout", "themer", "select_node", "mobileSwitch"]);
  } else {
    var savedNav = await getItem("navigationHtml");
  };  
  if (savedNav.includes('dual-ring')) {
    return false;
  };
  if (savedNav) {
    const $currentNav = $("#navigation");
    if ($currentNav.length === 0) {
      if (savedNav.includes("mobileNavContent")) {
        if (savedNav.includes("drawer1")) {
            // console.log('savedNav1',savedNav);
            document.querySelector(".drawer1").outerHTML = savedNav;
        } else {
          // console.log('savedNav2',savedNav);
          document.querySelector(".drawer1").innerHTML = savedNav;
        };
      };  
    } else {
      if (fadeIn) {
        $currentNav.fadeOut(200, function () {
            $currentNav.html(savedNav).fadeIn(500);
        });
      } else {
        // console.log('savedNav3',savedNav)
        document.querySelector("#navigation").innerHTML = savedNav;
      };
    };
    return true;
  };
  return false;
};

async function renameUser() {
  var form = document.getElementById("modalForm");
  var username = form.elements["username"].value;
  var field2 = document.getElementById('field2');
  if (username == '') {
    field2.innerHTML = 'Please enter a username';
  } else {
    d = get_stored_userData();
    userData = d[0];
    userArrayData = d[1];
    userData.username = username;
    userData.must_rename = false;
    userData = get_userData_for_sign_return(userData, userArrayData);
    signedData = await sign_data(userData);
    const data = {};
    data['userData'] = JSON.stringify(signedData);
    $.ajax({
      type:'POST',
      url:'/accounts/receive_rename',
      data: postData,
      success: async function(response){
        console.log(response)
        if (response['message'] == 'Username taken') {
            field2.innerHTML = 'Username not available'
        } else if (response['message'] == 'Success') {
          await storeItem(username, 'username');
          await storeItem(JSON.stringify(signedData), 'userData');
          location.reload();
        } else {
          field2.innerHTML = sanitize(response['message']);
        };
      },
      error: function (xhr, ajaxOptions, thrownError) {
        field2.innerHTML = 'Failed to reach server';
      }
    });
  };
};
async function setRegionModal(csrf) {
  // console.log('-setRegionModal')
  code = '<div class="lds-dual-ring"></div>';
  var spinner = document.getElementsByClassName("modal-spinner")[0];
  spinner.innerHTML = code;
  var form = document.getElementById("modalForm");
  var address = form.elements["address"].value;
  var city = form.elements["city"].value;
  var state = form.elements["state"].value;
  var zip_code = form.elements["zip_code"].value;
  var field2 = document.getElementById('field2');
  field2.innerHTML = '';
  field3.innerHTML = '';
  if (address == '') {
      field2.innerHTML = 'Please enter an address';
  }else if (city == '') {
      field2.innerHTML = 'Please enter a city';
  }else if (state == '') {
      field2.innerHTML = 'Please enter a state';
  } else if (zip_code == '') {
    field2.innerHTML = 'Please enter a zip code';
  } else {
    const data = {};
    country = document.getElementById('field3');
    data['country'] = country.getAttribute("value");
    data['address'] = address;
    data['city'] = city;
    data['state'] = state;
    data['zip_code'] = zip_code;
    data['csrfmiddlewaretoken'] = csrf;
    // console.log(data);
    $.ajax({
      type: 'POST',
      data: data,
      url: '/accounts/run_region_modal',
      success: function (response) {
        if (response['message'] == 'Failed to set region') {
          field2.innerHTML = sanitize(response['error']);
          spinner.innerHTML = '';
        } else {
          string = '/region';
          resultData = response['result'];
          // console.log(resultData);
          // federal = resultData['federal']
          function build_url(string, data){
            for (let [key, value] of Object.entries(data)) {
              for (let item of value) {
                string = string + item + '_';
              };
            };
            return string;
          };
          string = string + '?roles=';
          string = build_url(string, resultData['Federal']);
          string = build_url(string, resultData['State']);
          string = build_url(string, resultData['County']);
          string = build_url(string, resultData['City']);
          window.location.href = string;
        };
      },
      error: function (xhr, ajaxOptions, thrownError) {
        m.querySelector("#modalContent").innerHTML = 'Failed to reach server';
      }
    });
  };
};
function remove_region(iden) {
  // console.log('-remove-regino',iden);
  var regions = document.getElementsByClassName("region-reps");
  for (let region of regions) {
    if (region.id == iden) {
      removeElementWithFadeOut(region);
    };
  };
};
async function save_regions_to_account(userId) {
  // console.log('-rsave_regions_to_account',userId)
  userData = get_stored_userData();
  var regions = document.getElementsByClassName("region-reps");
  var localities = [];
  for (let region of regions) {
    var level = region.dataset.level;
    var type = region.dataset.type;
    localities.push(region.id);
  };
  userData.localities = JSON.stringify(localities);
  const currentDate = new Date();
  const isoString = currentDate.toISOString();
  userData.region_set_date = formatDateToDjango(isoString);
  console.log(JSON.stringify(userData));
  signedUserData = await sign_userData(userData);
  return_signed_userData(signedUserData)
};

function removeElementWithFadeOut(element) {
  element.classList.add('fade-out');
  element.addEventListener('transitionend', () => {
    element.remove();
  });
};


window.addEventListener("scroll", function() {
  let scrolled = window.scrollY;
  let title = document.getElementById("feedTitle");
  if (title) {
    title.style.transform = `translateY(${scrolled * 0.6}px)`;
  }
})
$(window).scroll(function() { 
  var topics = $('#topics');
  var speakers = $('#speakers');
  var isMobile = document.getElementById('isMobile').name;
  if (isMobile != 'True'){
  let window = innerHeight;
  var $navbar = $('#navBar');
  var isPositionFixed = ($navbar.css('position') == 'fixed');
  if ($(this).scrollTop() > 72 && !isPositionFixed) {
    adjustNavBar($navbar);
  } else if ($(this).scrollTop() < 72 && isPositionFixed) {
    var con = document.getElementById('container');
    var rect = con.getBoundingClientRect();
    var right = rect.left;
    right = right.toString();
    right = right + 'px';
    $navbar.css({'right': '-1' });
    $navbar.removeClass('fixed');
  };
    var $el = $('#sidebar'); 
    let box = document.querySelector('#sidebar');
    var height = box.offsetHeight;
    if (height < window) {
      difference = 100;
      var isPositionFixed = ($el.css('position') == 'fixed');
      if ($(this).scrollTop() > 100 && !isPositionFixed) {
        adjustSidebar($el);
      };
    } else {
      var isPositionFixed = ($el.css('position') == 'fixed');
      if ($(this).scrollTop() > 100 && !isPositionFixed) {
        adjustSidebar($el);
      };
    };
    if ($(this).scrollTop() < 100 && isPositionFixed) {
      $el.css({'position': 'absolute', 'top': '100px', 'right': '0px'}); 
      $el.removeClass('fixed');
    };
  };
})
$('#firstPane').scroll(function() {
  sideBarExpand('firstPane');
})
$('#secondPane').scroll(function() {
  sideBarExpand('secondPane');
})
$('#thirdPane').scroll(function() {
  sideBarExpand('thirdPane');
})
$('#fourthPane').scroll(function() {
  sideBarExpand('fourthPane');
})


function sideBarExpand(item) {
  var windowPanes = $('.sideBarWindow');
  windowPanes.each(function() {
    if (this.id == item) {
        $(this).addClass('showFullText');
    } else {
      $(this).removeClass('showFullText');
    };
});
};
function adjustSidebar($el) {
  var con = document.getElementById('container');
  var rect = con.getBoundingClientRect();
  var right = rect.left;
  right = right.toString();
  right = right + 'px';
$el.css({'position': 'fixed', 'top': '-1px', 'right': right }); 
$el.addClass('fixed');
};
function adjustNavBar($navbar) {
  var con = document.getElementById('container');
    var rect = con.getBoundingClientRect();
    var right = rect.left + 206;
    right = right.toString();
    right = right + 'px';
    $navbar.css({'right': right }); 
    $navbar.addClass('fixed');
};

function isInternalUrl(value, allowedExternalDomains = [], allowDataImage = false) {
    if (!value) return true;
    if (allowDataImage && /^data:image\/(png|jpe?g|gif|webp);base64,/i.test(value)) return true;
    if (/^(\/(?!\/)|#|\.\.?\/)/.test(value)) return true;
    try {
        const url = new URL(value, window.location.origin);
        if (isSameSite(url.hostname)) return true;
        return allowedExternalDomains.includes(url.hostname);
    } catch (e) {
        return false;
    };
};

function getRootDomain(hostname) {
    const parts = hostname.split('.');
    if (parts.length <= 2) return hostname;
    return parts.slice(-2).join('.');
};

function isSameSite(hostname) {
    return getRootDomain(hostname) === getRootDomain(window.location.hostname);
};

function sanitize(html, added_attrs = null, allowedExternalDomains = []) {
    DOMPurify.addHook('uponSanitizeAttribute', (node, data) => {
        if (data.attrName === 'href' || data.attrName === 'src') {
            if (!isInternalUrl(data.attrValue, allowedExternalDomains)) {
                data.keepAttr = false;
            };
        };
    });

    const config = {
        USE_PROFILES: { html: true },
        FORBID_TAGS: ['script', 'svg', 'math'],
        FORBID_ATTR: ['on*']
    };
    if (added_attrs) {
        config.ADD_ATTR = added_attrs;
        delete config.FORBID_ATTR;
    };

    const clean = DOMPurify.sanitize(html, config);
    DOMPurify.removeAllHooks();
    return clean;
};

function sanitizeWithException(html, allowedFunctions, allowedExternalDomains = []) {
  // sanitizeWithException(html, ["react", "modalPopUp", "direct_to"], ["trusted-partner.com"]);
    if (!Array.isArray(allowedFunctions)) {
        throw new Error("allowedFunctions must be an array of function names");
    };
    const handlerRegex = new RegExp(
        `^\\s*(${allowedFunctions.join('|')})\\s*\\(.*\\)\\s*;?\\s*$`
    );

    DOMPurify.addHook('uponSanitizeAttribute', (node, data) => {
        if (data.attrName === 'onclick') {
            if (!handlerRegex.test(data.attrValue)) {
                data.keepAttr = false;
            };
        };
        // if (data.attrName === 'href' || data.attrName === 'src') {
        //     const isImgSrc = node.tagName === 'IMG' && data.attrName === 'src';
        //     if (!isInternalUrl(data.attrValue, allowedExternalDomains, isImgSrc)) {
        //         data.keepAttr = false;
        //     };
        // };
    });

    const clean = DOMPurify.sanitize(html, {
        USE_PROFILES: { html: true },
        FORBID_TAGS: ['script', 'svg', 'math'],
        ADD_TAGS: ['meta'],
        ADD_ATTR: ['onclick']
    });

    DOMPurify.removeAllHooks();
    return clean;
};

function shorten_text(cards) {
  var isMobile = document.getElementById('isMobile').name;
  try {
    for(i=0; i<cards.length; i++){
      var text = cards[i].getElementsByClassName('Text')[0];
      try {
        if (text) {
          let child = text.parentNode.querySelector('.fadeOut')
          var height = text.offsetHeight;
          if (isMobile == 'True' && height >= 300 && child == null || isMobile == 'False' && height >= 150 && child == null) {
            iden = cards[i].id;
            code = `<div class='readMore' onclick='continue_reading("` + iden + `", "more")'>Read More</div>`;
            $(text).parent().after(code);
            fade = `<div class='fadeOut' onclick='continue_reading("` + iden + `", "more")'></div>`;
            $(text).parent().append(fade);
          };
        };
      } catch(err) {};
    };
  } catch(err) {};
};

async function sign_userData(userData, privKey=null, pubKey=null, key_type='ML_DSA_44') {
  userData.lastUpdate = get_current_time();
  delete userData['signed'];
  userData = await sign_data(userData, privKey=privKey, pubKey=pubKey, key_type=key_type);
  return userData;
};
function return_signed_userData(userData) {
  // console.log('-return signed data');
  if (userData) {
    const data = {'userData': JSON.stringify(userData)};
    return new Promise((resolve, reject) => {
      $.ajax({
        type:'POST',
        url:'/accounts/set_user_data',
        data: data,
        success: async function(response){
          console.log(response)
          if (response['message'].toLowerCase() == 'success') {
            await storeItem(JSON.stringify(userData), 'userData');
            resolve(true);
          } else {
            reject(false);
          };
        },
        error: function (xhr, ajaxOptions, thrownError) {
          reject(false);
        } 
      });
    });
  } else {return false};
};
async function get_stored_userData() {
  // console.log('-get stored userdata');
var result = await getItem("userData");
var userData;
if (result != null && typeof result === "string") {
  try {
    userData = JSON.parse(result);
  } catch(e) {
    console.error("Failed to parse JSON:", e);
    userData = null;
  };
} else {
  userData = result;
};
return userData;
  var userArrayData = {};
  try {
    Object.keys(userData).forEach(field => {
      if (field.endsWith('_array')) {
        userArrayData[field] = JSON.parse(JSON.stringify(userData[field]).replace(/'/g, '"'));
      };
    });
  } catch(err) {};
  return [userData, userArrayData];
};
async function update_userData(receivedUserData) {
  console.log('-update_userData');
  var parsedReceivedUserData = JSON.parse(receivedUserData);
  var latestmodlVer = parsedReceivedUserData.latestVer;
  if (parsedReceivedUserData.must_rename == true || parsedReceivedUserData.must_rename == 'true') {
    parsedReceivedUserData.must_rename = false;
    engage_rename = true;
  } else {
    engage_rename = false;
  };
  try {
    delete parsedReceivedUserData.must_rename;
  } catch(err) {};
  var localUsermodlVer = await getItem("localUsermodlVer");
  if (latestmodlVer != localUsermodlVer) {
    modelupgrade = true;
  } else {
    modelupgrade = false;
  };
  try {
    delete parsedReceivedUserData.latestVer;
  } catch(err) {};

  async function migrate_userData(fromModel, toModel, send_to_server=true) { 
    Object.keys(toModel).forEach(key => {
      if (fromModel[key]) {
        toModel[key] = fromModel[key];
      };
    });
    toModel['modlVer'] = latestmodlVer;
    if (send_to_server) {
      var signedUserData = await sign_userData(toModel);
      var do_save_data = await return_signed_userData(signedUserData);
    } else {
      do_save_data = true;
    }
    if (do_save_data) {
      await storeItem(latestmodlVer, 'localUsermodlVer');
      await storeItem(JSON.stringify(fromModel), 'prev_userData');
      await storeItem(JSON.stringify(userData), 'userData');
    };
  };
  is_valid = await verifyUserData(receivedUserData);
  console.log('is_valid',is_valid,'modelupgrade',modelupgrade,'engage_rename',engage_rename);
  if (modelupgrade) {
    var userData = await get_stored_userData();
    if ('updated_model' in parsedReceivedUserData) {
      var newUserModel = JSON.parse(JSON.parse(parsedReceivedUserData.updated_model));
      await migrate_userData(userData, newUserModel);
    } else if (is_valid) {
      var userData = get_stored_userData();
      if (Date(userData.lastUpdate) > Date(parsedReceivedUserData.lastUpdate)) {
        await migrate_userData(userData, newUserModel);
      } else {
        await storeItem(latestmodlVer, 'localUsermodlVer');
        await storeItem(JSON.stringify(parsedReceivedUserData), 'userData');
      };
    };
  } else if (is_valid) {
    var userData = get_stored_userData();
    if (Date(userData.lastUpdate) < Date(parsedReceivedUserData.lastUpdate)) {
      await storeItem(JSON.stringify(parsedReceivedUserData), 'userData');
    } else if (Date(userData.lastUpdate) > Date(parsedReceivedUserData.lastUpdate)) {
      return_signed_userData(userData);
    };
    if (engage_rename) {
      modalPopUp('Mandatory User Rename', '/accounts/rename_setup');
    };
  };
};
async function enact_user_instruction(instruction) {
  console.log('-instruction',instruction);
  if (instruction) {
    try {
      var pattern = /^(\w+)\s+(\w+)\s+"([^"]+)"$/;
      var match = pattern.exec(instruction);
      var command = match[1];
      var direction = match[2];
      var target = match[3];
    } catch(err) {
      var command = instruction;
    }
    // if (command.includes('_array') || command.includes('_json')) {
    //     userData = edit_user_array(command, target, direction);
    //     userData = sign_userData(userData);
    //     return_signed_userData(userData);
    // } else if (command == 'get_stored_user_login_data') {
    //   try {
    //     username = await getItem("username");
    //     pass = await getItem("password");
    //     var form = document.getElementById("modalForm");
    //     if (username != 'null' && username != null) {
    //       form.elements["username"].value = username;
    //     };
    //     if (pass != 'null' && pass != null) {
    //       form.elements["password"].value = 'xxx';
    //     };
    //   } catch(err) {};
    // };
  };
};
async function check_instructions(page) {
  // console.log('-check instructions');
  try {
    var ud = page.getElementById("userData");
    if (ud) {
      var userData = ud.getAttribute("value");
      await update_userData(userData);
    };
  } catch(err) {
    console.log('checkinstructions err1',err)
  };
  try {
    var inst = page.getElementById("instruction");
    if (inst) {
      var instruction = inst.getAttribute("value");
      enact_user_instruction(instruction);
    };
  }catch(err){
  };
};

function flash_object(element) {
  // console.log('-flash',element)
  const parentWithClass = element.closest('.cardContainer');
  if (parentWithClass) {
      element = parentWithClass;
  };
  var originalElement = element.cloneNode(true);
  element.style.transition = '0.5s';;
  element.classList.add('flash');
  setTimeout(function() {
    element.classList.remove('flash');
    setTimeout(function() {
      element.style.removeProperty('transition');
      element.replaceWith(originalElement.cloneNode(true));
      }, 500);
    }, 500);
};
function scrollToElement(element, offsetPercentage=10, flash=false) {
  // console.log('-scrollto element', flash, element);
  if (typeof element === 'string') {
    var element = document.getElementsByClassName(element)[0];
  };
  const elementPosition = element.getBoundingClientRect().top + window.pageYOffset;
  const offset = window.innerHeight * (offsetPercentage / 100);
  const scrollPosition = elementPosition - offset;

  window.scrollTo({
      top: scrollPosition,
      behavior: 'smooth'
  });
  if (flash) {
    let isScrolling;
  
    window.addEventListener('scroll', function() {
        window.clearTimeout(isScrolling);
  
        isScrolling = setTimeout(function() {
            if (Math.abs(window.pageYOffset - scrollPosition) < 2) {
              flash_object(element);
            };
        }, 100);
    }, { passive: true });
  };
};

function getBaseDomain() {
  const host = window.location.hostname;
  const parts = host.split('.');

  if (parts.length > 2) {
    return parts.slice(-2).join('.');
  };
  return host;
};
function getHostIdentifier(subdomain) {
  const host = window.location.host;
  const hostname = window.location.hostname;
  const portStr = window.location.port ? `:${window.location.port}` : "";

  const isIPv4 = /^\d{1,3}(\.\d{1,3}){3}$/.test(hostname);
  const isIPv6 = hostname.includes(":");   // hostname is unbracketed for IPv6, but contains ':'
  const isLocalhost = hostname === "localhost";

  // If IP or localhost → return as-is (no subdomain)
  if (isIPv4 || isIPv6 || isLocalhost) {
    try { myVar(host, 'domain'); } catch (e) {};
    return host;
  };

  const parts = hostname.split(".");
  const baseDomain = parts.length > 2 ? parts.slice(-2).join(".") : hostname;
  const result = (subdomain ? `${subdomain}.` : "") + baseDomain + portStr;

  return result;
};

function get_current_time(return_string=true) {
  const currentDate = new Date();
  const isoString = currentDate.toISOString();
  if (return_string) {
    return formatDateToDjango(isoString);
  } else {
    return currentDate;
  };
};
function formatDateToDjango(isoString) {
  const date = isoString instanceof Date ? isoString : new Date(isoString);
  const iso = date.toISOString();
  const new_dt = iso.replace(/(\.\d{2})\d*Z$/, '$1Z');
  return new_dt;
};
function bumpDt(dtStr) {
  // dtStr format: YYYY-MM-DDTHH:mm:ss.ffZ (hundredths of a second)
  // pad hundredths (2 digits) to milliseconds (3 digits) so Date can parse it
  const msString = dtStr.replace(/\.(\d{2})Z$/, '.$10Z');
  const d = new Date(msString);
  d.setMilliseconds(d.getMilliseconds() + 10); // smallest representable increment at hundredths precision
  return formatDateToDjango(d.toISOString());
};

function handleLocalLink(href) {
    console.log('-Intercepted local link:', href);
    // alert(`You clicked a local link: ${href}`);
};


async function check_for_node_updates(document) {
  console.log('-check_for_node_updates');
  var nodeData = document.getElementById("nodeData");
  console.log('nodeData',nodeData.getAttribute("value"));
  if (nodeData.getAttribute("value")) {
    parsed_nodeData = JSON.parse(nodeData.getAttribute("value"));
    var saved_nodeData_str = await getItem("nodeData");
    if (saved_nodeData_str) {
      var saved_nodeData = JSON.parse(saved_nodeData_str);
    } else {
      var saved_nodeData = null;
    };
    console.log('saved_nodeData',saved_nodeData)
    await storeItem(JSON.stringify(parsed_nodeData), 'nodeData');
    if (!saved_nodeData) {
      await storeItem(JSON.stringify(parsed_nodeData), 'nodeData');
    } else if (formatDateToDjango(saved_nodeData['blockDatetime']) < formatDateToDjango(parsed_nodeData['blockDatetime'])) {
      await storeItem(JSON.stringify(parsed_nodeData), 'nodeData');
    } else {
      console.log('no save node data');
    };
    await storeItem(parsed_nodeData['sonetInitializedDatetime'], 'sonetInitializedDatetime');
  };
  var saved_nodeData = await getItem("nodeData");
  console.log('saved_nodeData111',saved_nodeData)
};


async function browser_shuffle_2(text_input, dt, node_ids) {
    console.log('-browser_shuffle',text_input,'dt',dt,'node_ids',node_ids);
    async function sha256Hex(input) {
      const encoder = new TextEncoder();
      const data = encoder.encode(input);
      const hashBuffer = await crypto.subtle.digest('SHA-256', data);
      return Array.from(new Uint8Array(hashBuffer))
                  .map(b => b.toString(16).padStart(2, '0'))
                  .join('');
    };
    const dt_str = formatDateToDjango(dt);
    const seed_input = `${text_input}_${dt_str}`;
    const hashes = await Promise.all(node_ids.map(async item => {
        const hash = await sha256Hex(seed_input + item);
        return { item, hash };
    }));
    hashes.sort((a, b) => a.hash.localeCompare(b.hash));
    console.log('hashes',hashes);
    return hashes.map(obj => obj.item);
};

function mulberry32(seed) {
  function stringToSeed(s) {
    let h = 0x811C9DC5; // FNV offset basis
    for (let i = 0; i < s.length; i++) {
      h ^= s.charCodeAt(i);
      h = Math.imul(h, 0x01000193) >>> 0; // FNV prime
    }
    return h;
  }
  seed = stringToSeed(seed)
  let state = seed >>> 0;
  return function rng() {
    state = (state + 0x6D2B79F5) >>> 0;
    let t = state;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function cross_language_shuffle(arr, seed) {
  const result = arr.slice();
  const rng = mulberry32(seed);
  for (let i = result.length - 1; i > 0; i--) {
    const j = Math.floor(rng() * (i + 1));
    [result[i], result[j]] = [result[j], result[i]];
  }
  return result;
}

function gcd(a, b) {
    while (b !== 0) {
        [a, b] = [b, a % b];
    };
    return a;
};
function position_sort(active_set, starting_position, pattern, max_number, number_of_matches) {
    console.log('-position_sort',starting_position,pattern,max_number,number_of_matches);
    console.log('active_set',active_set);

    let matches = [];
    let visited = new Set();

    if (max_number <= 0) return [];

    // Initial position (1-based safe wrap)
    let start = ((starting_position + pattern - 1) % max_number + max_number) % max_number + 1;
    if (!start) {start = 1};

    // Deterministic step derived from pattern
    let step = (Math.abs(pattern) % max_number);
    // if (step === 0) step = 1;

    // Force coprime step
    while (gcd(step, max_number) !== 1) {
        step = (step + 1) % max_number;
        if (step === 0) step = 1;
    };
    console.log('max_number',max_number, 'matches.length',matches.length,'number_of_matches',number_of_matches,'start',start,'step',step);
    let current_pos = start;
    for (let i = 0; i < max_number && matches.length < number_of_matches; i++) {
      // console.log('i',i);
        if (active_set.hasOwnProperty(current_pos) && !visited.has(current_pos)) {
          // console.log('push');
            matches.push(active_set[current_pos]);
            visited.add(current_pos);
        };
        current_pos = ((current_pos + step - 1) % max_number) + 1;
        // console.log('current_pos,',current_pos);
    };
    return matches;
};
async function get_assignment(obj=null, iden=null, DateTime=null, nodeIds=[], relevantNodes={}, region='All') {
  console.log('-get_assignment','obj',obj,'iden',iden,'DateTime',DateTime,'nodeIds',nodeIds);
  if (obj != null) {
    if (DateTime == null) {
      var DateTime = obj.DateTime;
    };
    if (iden == null) {
    var iden = obj.iden;
    };
  };
  if (DateTime == null) {
    DateTime = new Date();
  };
  if (iden == null) {
    var iden = await getItem("user_id");
    if (!iden) {
      var iden = await getItem('anonId');
      if (!iden) {
        const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
        let result = '';
        for (let i = 0; i < 14; i++) {
          result += chars.charAt(Math.floor(Math.random() * chars.length));
        };
        iden = 'tusrSo' + result;
        await storeItem(iden, 'anonId');
      };
    };
  };
  if (nodeIds.length === 0 || Object.keys(relevantNodes).length === 0 ) {
    var saved_nodeData = await getItem("nodeData");
    console.log('saved_nodeData22',saved_nodeData)
    var parsed_nodeData = JSON.parse(saved_nodeData);
    // console.log('parsed_nodeData',parsed_nodeData);
    var relevantNodes = parsed_nodeData.id_data.active;
    // console.log('relevantNodes1',relevantNodes);
    if (region !== 'All' && region in parsed_nodeData.id_data) {
      var nodeIds = parsed_nodeData.id_data.region;
    } else {
      var nodeIds = parsed_nodeData.id_data.active;
    };
  };
  userData = await get_stored_userData();
  const position_dict = {};
  for (const [id, data] of Object.entries(relevantNodes)) {
    console.log('id',id,'data',data)
    if (parsed_nodeData.id_data.active[id]) {
      console.log('1a')
      position_dict[parsed_nodeData.id_data.active[id]['pos']] = id;
      // console.log('position_dict1',position_dict);
    } else {
      console.log('1b')
      position_dict[1] = id;
      // console.log('position_dict2',position_dict);
    };
  };
  if (userData && userData.nodeCreatorId && parsed_nodeData.id_data.active[userData.nodeCreatorId]) {
    var nodeId = userData.nodeCreatorId;
  } else {
    const keys = Object.keys(parsed_nodeData.id_data.active);
    var nodeId = keys[Math.floor(Math.random() * keys.length)];
  };
  const startPos = parsed_nodeData.id_data.active[nodeId] || null;
  if (!startPos) {
    const data = await connect_to_node('/utils/get_object_id/'+nodeId);
    if (data) {
      startPos = data.signing_obj;
    };
  };
  var max_number = parsed_nodeData.max_pos;
  // console.log('max_number',max_number);
  if (userData && userData.pattern) {
    var pattern = userData.pattern;
  } else {
    var pattern = 6;
  };
  matches = position_sort(position_dict, startPos, pattern, max_number, 50);
  // const sorted = await browser_shuffle(iden, DateTime, nodeIds);
  console.log('matches',matches);
  return {'orderOfNodes':matches, 'addresses':relevantNodes} ;
};


async function load_queue() {
  console.log('-load_queue...',);
  try {
    isLoading = document.getElementsByClassName('lds-dual-ring')[0];
    if (isLoading) {
      var assignment = await get_assignment(obj=null, iden=null, DateTime=null, nodeIds=[], relevantNodes={});
      orderOfNodes = assignment.orderOfNodes;
      // console.log('assignment',orderOfNodes);
      current = window.location.href;
      const current_path = new URL(current).pathname;
      const current_params = new URL(current).search;
      user_id = await myVar('user_id');
      if (current_params.includes('?')) {
        addition = '&style=feed&include_nav=True&user=' + user_id;
      } else {
        addition = '?style=feed&include_nav=True&user=' + user_id;
      };
      url = current + current_path + current_params + addition;

      async function fetchWithTimeout(url, timeout = 7000) {
          console.log('-fetchWithTimeout',url);
          const controller = new AbortController();
          const signal = controller.signal;
          const timeoutId = setTimeout(() => controller.abort(), timeout);
          try {
              const response = await fetch(url, { signal });
              clearTimeout(timeoutId);
              if (!response.ok) throw new Error(`HTTP error! Status: ${response.status}`);
              return response;
          } catch (error) {
              if (error.name === "AbortError") {
                  console.log(`Request to ${url} timed out!`);
              } else {
                  console.log(`Fetch failed: ${error.message}`);
              }
              return null; // Indicate failure
          };
      };
      
      async function attempt_connection(url, newIp, user_id) {
          let result = await fetchWithTimeout(url, 7000);
          if (result) {
              myVar('last_accessed_url', newIp);
              console.log("Success! Processing data...");
              const bottomCard = document.getElementById('bottomCard');
              const bottomCardHtml = bottomCard.outerHTML;
              const has_nav = false;
              const feed = $('#feed');
              const newHtmlText = await result.text();
              const parsedElements = $.parseHTML(newHtmlText);
              const new_cards = $(parsedElements);
              var navBar = $(parsedElements).filter("#navBar")[0];
              if (navBar) {
                  const has_nav = true;
                  const $holder = $("#navBarHolder");
                  navBar = sanitizeWithException(navBar, ["subNavWidget", "scrollToElement"]);
                  const $newNav = $(navBar).clone().hide();
                  $newNav.attr("id", "navBar");
                  const $existingNav = $holder.find("#navBar");
                  if ($existingNav.length) {
                      $existingNav.fadeOut(200, function() {
                          $(this).remove();
                          $holder.append($newNav);
                          $newNav.fadeIn(240);
                      });
                  } else {
                      $holder.append($newNav);
                      $newNav.fadeIn(240);
                  }; 
              };
              const newStylesheets = $(parsedElements).filter("link[rel='stylesheet']");
              if (newStylesheets.length) {
                  const $defaultLink = $('head link[href*="default.css"]');
                  newStylesheets.each(function() {
                      const href = this.getAttribute("href");
                      if (href && !document.querySelector(`link[rel="stylesheet"][href="${href}"]`)) {
                          const $link = $(this).clone();
                          if ($defaultLink.length) {
                              $link.insertBefore($defaultLink.first());
                          } else {
                              $("head").append($link);
                          };
                      };
                  });
              };
              var feedTitle = $(parsedElements).filter("#feedTitle")[0];
              if (feedTitle) {
                  const $mainTitle = $("#mainTitle");
                  feedTitle = sanitize(feedTitle)
                  const $newTitleContent = $(feedTitle).contents().clone();
                  $mainTitle.fadeOut(100, function() {
                      $mainTitle.empty().append($newTitleContent).fadeIn(200);
                  });
              };
              var newList = [];
              for (let f = 0; f < new_cards.length; f++) {
                  var el = new_cards[f];
                  var elId = el.id;
                  el = sanitizeWithException(el, ["react", "modalPopUp", "direct_to"]);
                  // console.log('after sanitize:', el.outerHTML || el);
                  if ($(el).closest("#feedTitle").length || $(el).closest("#navBar").length) continue;
                  if (elId === 'bottomCard') {
                      const $bottom = $(el).hide();
                      feed.append($bottom);
                      $bottom.fadeIn(50);
                      continue;
                  };
                  const $card = $(el).hide();
                  feed.append($card);
                  $card.fadeIn(500);
              };
              function appendAndRevealCards(cards, index = 0, obj, feed, cover = null) {
                const newCover = $('<div class="cardCover"></div>');
                const newCard = $(cards[index]);
                if (index >= cards.length) {
                  return;
                };
                var cl = cards[index].className;
                var iden = cards[index].id;
                if (cl && cl.includes('bottomDivider') || cl && cl.includes('reactionBar') || cl && cl.includes('cardContainer')) {
                  obj.push(newCard);
                  feed.append(obj);
                  newCard.hide().fadeIn(30, function() {
                    setTimeout(function() {
                      try {
                        cover.fadeOut(30, function() {
                          cover.remove();
                          appendAndRevealCards(cards, index + 1, obj, feed, newCover);
                        });
                      }catch(err) {
                        appendAndRevealCards(cards, index + 1, obj, feed, newCover);
                      };
                    }, 60);
                  });

                } else if (iden && iden.includes('bottomCard')) {
                  feed.append(newCard);
                } else if (cl && cl.includes('card')) {
                  newCard.append(newCover);
                  obj.push(newCard);
                  appendAndRevealCards(cards, index + 1, obj, feed, newCover);
                } else {
                  obj.push(newCard);
                  appendAndRevealCards(cards, index + 1, obj, feed, cover);
                };
              };
              document.getElementById("bottomCard").outerHTML='';
              page_picker = document.getElementsByClassName('pagePicker');
              page_form = document.getElementById("pageForm");
              try {
                if (page_form) {
                  page_form.innerHTML = sanitize(page_picker[page_picker.length - 1].outerHTML);
                };
              } catch(err) {
              };
              var cards = document.getElementsByClassName('card');
              if (cards['length']) {
                shorten_text(cards);
              } else if (has_nav) {
                document.getElementById("bottomCard").outerHTML="<div id='bottomCard'><div style='margin:auto;'>None Found</div></div>";
              } else {
                document.getElementById("bottomCard").outerHTML="<div id='bottomCard'><div style='margin:auto;'></div></div>";
              };
              try {
                var rePosition = document.getElementsByClassName('moveToHere')[0];
                scrollToElement(rePosition, 10, true);
              } catch(err) {};
              
              var cards = document.getElementsByClassName('card');
              shorten_text(cards);
              
              if (current_params.includes('?')) {
                addition = '&style=index';
              } else {
                addition = '?style=index';
              };
              url = newIp + current_path + current_params + addition + '&user=' + user_id;
              // console.log('fetch index',url);
              let index_result = await fetchWithTimeout(url, 7000);
              let data = await index_result.text();
              const $response = $(data);
              const $newNav = $response.find("#navigation");
              // console.log('$newNav.length',$newNav.length)
              if ($newNav.length) {
                // console.log('$newNav.html()1',$newNav.html())
                var nav = sanitizeWithException($newNav.html(), ["modalPopUp", "logout", "themer", "select_node", "mobileSwitch"]);
                $("#navigation").html(nav);
                storeNavigation();
              } else {
                const $newMobileNav = $response.find(".mobileNavContent");
                // console.log('newMobileNav',$newMobileNav.html());
                if ($newMobileNav.length) {
                  var nav = sanitizeWithException($newMobileNav.html(), ["modalPopUp", "logout", "themer", "select_node", "mobileSwitch"]);
                  $(".mobileNavContent").html(nav);
                  // console.log('new mobile nav',nav)
                  storeNavigation();
                };
              };
              const $newSidebar = $response.find("#sidebar");
              if ($newSidebar.length) {
                const $currentSidebar = $("#sidebar");
                const $newSidebarContent = $newSidebar.contents().clone().hide();
                $currentSidebar.empty().append($newSidebarContent);
                $newSidebarContent.fadeIn(500);
              };
              const $newMobileSidebar = $response.find(".drawer4");
              if ($newMobileSidebar.length) {
                const $currentMobileSidebar = $(".drawer4");
                const $newMobileSidebarContent = $newMobileSidebar.contents().clone().hide();
                $currentMobileSidebar.empty().append($newMobileSidebarContent);
                $newMobileSidebarContent.fadeIn(500);
              };
              return true;
          } else {
            console.log('no result');
          };
        return false;
      };
      async function loopRequests(url, orderOfNodes, user_id, addresses=null) {
        for (let key of orderOfNodes) {
          const addr = getHostIdentifier(key);
          var newIp = addr;
          var newIp = format_url(addr);
          url = newIp + current_path + current_params + addition;
          console.log(`Trying: ${url}`);
          result = await attempt_connection(url, newIp, user_id);
          if (result) {
            return
          };
        };
      };
      const last_connection = await myVar('last_accessed_url');
      if (last_connection) {
        url = last_connection + current_path + current_params + addition;
        console.log(`Trying1: ${url}`);
        result = await attempt_connection(url, last_connection, user_id);
        if (result) {
          return
        };
      };
      loopRequests(url, orderOfNodes, user_id);
    };
    console.log('end load queue');
  }catch(err){console.log('load_queue eer2',err)};
};
async function initialize_page(document) {
  console.log('-initialize_page');
  masterConnection =  window.location.href;
  await check_for_node_updates(document);
  displayStoredNavigation();
  load_queue();
  check_instructions(document);
  console.log('done initialize_page');
};

$(document).ready(
    function(){
      initialize_page(document);
    console.log('document ready done');
    // key_test();
  }
);


$(document).on('submit', '#post-form',function(e){
  e.preventDefault();
  $.ajax({
      type:'POST',
      url:'/utils/calendar_widget',
      data: $('#post-form').serialize(),
      success:function(data){
        a = document.getElementById('agenda');
        a.nextElementSibling.remove();
        a.outerHTML = data;
        $('#secondPane').scroll(function(){
          sideBarExpand('secondPane');
        });
      },
      error : function(xhr,errmsg,err) {
      console.log(xhr.status + ": " + xhr.responseText);
  }
  });
});
document.body.addEventListener('click', function(e) {
    const button = e.target.closest('.navBar-btn');
    if (!button) return;

    const menus = document.querySelectorAll('.navOptionsMenu');
    const buttons = document.querySelectorAll('.navBar-btn');
    const targetMenu = document.getElementById(button.getAttribute('data-target'));
    const isOpen = targetMenu.classList.contains('open');

    menus.forEach(menu => menu.classList.remove('open'));
    buttons.forEach(btn => btn.classList.remove('selected'));

    if (!isOpen) {
        targetMenu.classList.add('open');
        button.classList.add('selected');
    };
});
document.addEventListener("click", function(event) {
    let link = event.target.closest("a");
    if (link && link.href) {
      const menus = document.querySelectorAll('.navOptionsMenu');
      const buttons = document.querySelectorAll('.navBar-btn');
      menus.forEach(menu => menu.classList.remove('open'));
      buttons.forEach(btn => btn.classList.remove('selected'));

      mobileSwitch(null);

    };
});


function mobileSwitch(screen, close_modal=true){
  // console.log('-mobileSwitch',screen);
    modal = $('.modalWidget');
    if (screen != 'so' && modal.hasClass('show') && close_modal) {
      closeModal(close_nav=false);
    }
    labels = document.getElementsByClassName('label');
    for (i=0;i<labels.length;i++) {
      if (labels[i].id == 'drawer1') {
        var menu_label = labels[i];
      } else if (labels[i].id == 'drawer3') {
        var notifications_label = labels[i];
      } else if (labels[i].id == 'drawer2') {
        var poupons_label = labels[i];
      } else if (labels[i].id == 'drawer4') {
        var search_label = labels[i];
      };
    };
    var drawer1 = $('.drawer1');
    var drawer4 = $('.drawer4');
    var drawer3 = $('.drawer3');
    var drawer2 = $('.drawer2');
    if (screen == 'drawer1') {
      if (drawer1.attr('class').includes('show_window')) {
        drawer1.removeClass('show_window');
        menu_label.classList.remove("show_label");
        hideDarkenOverlay();
      } else {
        drawer1.addClass('show_window');
        menu_label.classList.add("show_label");
        showDarkenOverlay();
        drawer4.removeClass('show_window');
        search_label.classList.remove("show_label");
        drawer3.removeClass('show_window');
        notifications_label.classList.remove("show_label");
        drawer2.removeClass('show_window');
        poupons_label.classList.remove("show_label");
      };
    } else if (screen == 'drawer4') {
      if (drawer4.attr('class').includes('show_window')) {
        drawer4.removeClass('show_window');
        search_label.classList.remove("show_label");
        hideDarkenOverlay();
      } else {
        drawer4.addClass('show_window');
        search_label.classList.add("show_label");
        showDarkenOverlay();
        drawer1.removeClass('show_window');
        menu_label.classList.remove("show_label");
        drawer3.removeClass('show_window');
        notifications_label.classList.remove("show_label");
        drawer2.removeClass('show_window');
        poupons_label.classList.remove("show_label");
      };
    } else if (screen == 'feed') {      
      if (drawer1.attr('class').includes('display') || drawer4.attr('class').includes('display') || drawer3.attr('class').includes('display')) {
        drawer1.removeClass('display');
        menu_label.classList.remove("show_label");
        drawer4.removeClass('display');
        search_label.classList.remove("show_label");
        drawer3.removeClass('display');
        notifications_label.classList.remove("show_label");
        drawer2.removeClass('display');
        poupons_label.classList.remove("show_label");
        hideDarkenOverlay();
      } else {
        window.location.href = '/';
      };
    } else if (screen == 'drawer3') {
      if (drawer3.attr('class').includes('show_window')) {
        drawer3.removeClass('show_window');
        notifications_label.classList.remove("show_label");
        hideDarkenOverlay();
      } else {
        drawer3.addClass('show_window');
        notifications_label.classList.add("show_label");
        showDarkenOverlay();
        drawer1.removeClass('show_window');
        menu_label.classList.remove("show_label");
        drawer4.removeClass('show_window');
        search_label.classList.remove("show_label");
        drawer2.removeClass('show_window');
        poupons_label.classList.remove("show_label");
      };
    } else if (screen == 'drawer2') {
      if (drawer2.attr('class').includes('show_window')) {
        drawer2.removeClass('show_window');
        poupons_label.classList.remove("show_label");
        hideDarkenOverlay();
      } else {
        drawer2.addClass('show_window');
        poupons_label.classList.add("show_label");
        showDarkenOverlay();
        drawer1.removeClass('show_window');
        menu_label.classList.remove("show_label");
        drawer4.removeClass('show_window');
        search_label.classList.remove("show_label");
        drawer3.removeClass('show_window');
        notifications_label.classList.remove("show_label");
      };
    }else if (screen == 'so') {  
      modal = $('.modalWidget');
      if (modal.hasClass('show')) {
        closeModal();
        try {
          if (drawer1.attr('class').includes('show_window') || drawer4.attr('class').includes('show_window') || drawer3.attr('class').includes('show_window')) {
            hideDarkenOverlay();
            drawer1.removeClass('show_window');
            menu_label.classList.remove("show_label");
            drawer4.removeClass('show_window');
            search_label.classList.remove("show_label");
            drawer3.removeClass('show_window');
            notifications_label.classList.remove("show_label");
            drawer2.removeClass('show_window');
            poupons_label.classList.remove("show_label");
          };
        } catch {
        };
      } else {
        try {
          if (drawer1.attr('class').includes('show_window') || drawer4.attr('class').includes('show_window') || drawer3.attr('class').includes('show_window')) {
            hideDarkenOverlay();
            drawer1.removeClass('show_window');
            menu_label.classList.remove("show_label");
            drawer4.removeClass('show_window');
            search_label.classList.remove("show_label");
            drawer3.removeClass('show_window');
            notifications_label.classList.remove("show_label");
            drawer2.removeClass('show_window');
            poupons_label.classList.remove("show_label");
          } else {
            modalPopUp('So...', 'so_modal');
          };
        } catch {
          modalPopUp('So...', 'so_modal');
        };
      };
    } else {
        try {
          if (drawer1.attr('class').includes('show_window') || drawer4.attr('class').includes('show_window') || drawer3.attr('class').includes('show_window')) {
            hideDarkenOverlay();
            drawer1.removeClass('show_window');
            menu_label.classList.remove("show_label");
            search.removeClass('show_window');
            search_label.classList.remove("show_label");
            drawer3.removeClass('show_window');
            notifications_label.classList.remove("show_label");
            drawer2.removeClass('show_window');
            poupons_label.classList.remove("show_label");
          };
        } catch {
      };
    };
};
function searchMobileSwitch(tab) {
  var tabs = document.getElementsByClassName('searchTab');
  var pages = document.getElementsByClassName('searchTabContent');
  for (i=0; i<pages.length; i++) {
    if (pages[i].classList.contains('show')) {
      pages[i].classList.remove('show');
      removePage = pages[i];
        setTimeout(function (){
        removePage.classList.remove('block');
      }, 200);
    };
    if (pages[i].id == tab) {
      pages[i].classList.add('block');
      pages[i].classList.add('show');
    };
  };
  for (i=0; i<tabs.length; i++) {
      tabs[i].classList.remove('blue');
    if (tabs[i].id == tab) {
      tabs[i].classList.add('blue');
    };
  };
};

async function select_node() {
  // console.log('-select_node');
  modalPopUp('Connect to Node');
  var assignment = await get_assignment(obj=null, iden=null, DateTime=null, nodeIds=[], relevantNodes={});
  orderOfNodes = assignment.orderOfNodes;
  console.log('assignment',orderOfNodes);
  const listElement = document.getElementById("modalContent");
    listElement.innerHTML = "";
      const inputUl = document.createElement("ul");
      listElement.appendChild(inputUl);
      const inputLi = document.createElement("li");
      const input = document.createElement("input");
      input.type = "text";
      inputLi.style.listStyle = "none";
      const button = document.createElement("button");
      button.textContent = "enter";
      button.style.color = "black";
      button.addEventListener("click", async () => {
        const value = input.value.trim();
        if (value) {
          const addr = getHostIdentifier(value);
          var newIp = addr;
          var newIp = format_url(addr);
          await myVar('last_accessed_url', newIp);
          location.reload();
        };
      });

      inputLi.appendChild(input);
      inputLi.appendChild(button);
      inputUl.appendChild(inputLi);
      const spacer = document.createElement("li");
      spacer.style.listStyle = "none";
      spacer.innerHTML = "&nbsp;";
      inputUl.appendChild(spacer);

      orderOfNodes.forEach(item => {
        const li = document.createElement("li");
        li.textContent = item;
        li.style.cursor = "pointer";
        li.style.margin = "12px 8";
        // li.style.textAlign = "left";
        li.style.listStyle = "none";
        li.className = 'clickable';

        li.addEventListener("click", async () => {
          const addr = getHostIdentifier(item);
          var newIp = addr;
          var newIp = format_url(addr);
          await myVar('last_accessed_url', newIp);
          location.reload();
        });
        inputUl.appendChild(li);
      });
};




async function my_test() {
  console.log('-running my test');
  await key_test();
  console.log('done my test');
}
async function key_test() {
  console.log('-runnign key_test');
  
  password = 'have node_rec for each plugin and each region - cross reference both records when both region and plugin inputted to get_broadcast_list/get_nodes_from_block';
  account_keyPair = await createKeyPair('1234567890', password, 'account', key_strength='ML_DSA_44');
  privKey = account_keyPair[0];
  pubKey = account_keyPair[1];
  console.log('privKey:',privKey);
  console.log('pubKey:',pubKey);

  console.log('generateId 1',await generateId(pubKey, upk=true))
  console.log('generateId 2',await generateId(pubKey, upk=false))
  console.log('generateId 20',await generateId(pubKey, upk=false, length=20))
  console.log('generateId 30',await generateId(pubKey, upk=false, length=30))
  
  console.log('done key_test');
}






// DO NOT MODIFY - VERY IMPORTANT
function sortForSign(data) {
    function stringifyValue(val) {
        if (val === true) return "True";
        if (val === false) return "False";
        if (val === null || val === undefined) return "Val:N";
        return val;
    };
    function isISODate(str) {
        return typeof str === "string" && /^\d{4}-\d{2}-\d{2}T/.test(str);
    };
    function formatDate(val) {
        try {
            return new Date(val).toISOString().replace(/\.\d{3}Z$/, 'Z');
        } catch {
            return val;
        };
    };
    function process(val) {
        if (val === null || val === undefined) return "Val:N";
        if (typeof val === "boolean") return stringifyValue(val);
        if (typeof val === "string" && isISODate(val)) return formatDateToDjango(val);
        if (Array.isArray(val)) return val.map(process);
        if (typeof val === "object") return sortForSign(val);
        return val;
    };
    if (Array.isArray(data)) {
        return data.map(process);
    };
    if (data !== null && typeof data === "object") {
        const entries = Object.entries(data).map(([k, v]) => [k, process(v)]);
        entries.sort((a, b) => a[0].toLowerCase().localeCompare(b[0].toLowerCase()));
        const indexId = entries.findIndex(([key]) => key === 'id');
        if (indexId !== -1) {
            const [idEntry] = entries.splice(indexId, 1);
            entries.unshift(idEntry);
        };
        const indexSigned = entries.findIndex(([key]) => key === 'signed');
        if (indexSigned !== -1) {
            const [signedEntry] = entries.splice(indexSigned, 1);
            entries.push(signedEntry);
        };
        return Object.fromEntries(entries);
    };
    return stringifyValue(data);
};


// not currently used
async function encryptAndStore(key, data) {
  const encryptedData = CryptoJS.AES.encrypt(JSON.stringify(data), key).toString();
  await storeItem(encryptedData, 'encryptedData');
  // localStorage.setItem('encryptedData', encryptedData);
}
async function retrieveAndDecrypt(key) {
  const encryptedData = await getItem('encryptedData');
  if (encryptedData) {
    const decryptedBytes = CryptoJS.AES.decrypt(encryptedData, key);
    const decryptedData = JSON.parse(decryptedBytes.toString(CryptoJS.enc.Utf8));
    return decryptedData;
  }
  return null;
}

