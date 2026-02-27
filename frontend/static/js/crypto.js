/**
 * SecureVote — Client-side RSA Blind Signature operations
 *
 * Implements the voter-side blinding / unblinding in pure JavaScript using
 * the BigInt primitive (available in all modern browsers).
 *
 * Protocol summary:
 *  1. generate_token()      → random 32-byte token (Uint8Array)
 *  2. blind_token()         → { blindedB64, blindingFactor } using issuer pub key
 *  3. [server signs blinded token → blindSigB64]
 *  4. unblind_signature()   → final signature (BigInt) using blinding factor
 *  5. serialize_credential()→ { token_hex, signature_b64 } ready for /api/vote
 */

// ---------------------------------------------------------------------------
// Utility helpers
// ---------------------------------------------------------------------------

function bytesToBigInt(bytes) {
  let hex = Array.from(bytes).map(b => b.toString(16).padStart(2, '0')).join('');
  return hex.length === 0 ? 0n : BigInt('0x' + hex);
}

function bigIntToBytes(n, byteLength) {
  let hex = n.toString(16);
  if (hex.length % 2 !== 0) hex = '0' + hex;
  // Pad to requested byte length
  while (hex.length < byteLength * 2) hex = '00' + hex;
  const bytes = new Uint8Array(hex.length / 2);
  for (let i = 0; i < bytes.length; i++) {
    bytes[i] = parseInt(hex.slice(i * 2, i * 2 + 2), 16);
  }
  return bytes;
}

function base64ToBytes(b64) {
  const bin = atob(b64);
  return Uint8Array.from(bin, c => c.charCodeAt(0));
}

function bytesToBase64(bytes) {
  let bin = '';
  for (const b of bytes) bin += String.fromCharCode(b);
  return btoa(bin);
}

function bigIntToBase64(n) {
  const byteLen = Math.ceil(n.toString(16).length / 2);
  return bytesToBase64(bigIntToBytes(n, byteLen));
}

function base64ToBigInt(b64) {
  return bytesToBigInt(base64ToBytes(b64));
}

function bytesToHex(bytes) {
  return Array.from(bytes).map(b => b.toString(16).padStart(2, '0')).join('');
}

function hexToBytes(hex) {
  const bytes = new Uint8Array(hex.length / 2);
  for (let i = 0; i < bytes.length; i++) {
    bytes[i] = parseInt(hex.slice(i * 2, i * 2 + 2), 16);
  }
  return bytes;
}

// ---------------------------------------------------------------------------
// Modular arithmetic (BigInt)
// ---------------------------------------------------------------------------

function modPow(base, exp, mod) {
  if (mod === 1n) return 0n;
  let result = 1n;
  base = base % mod;
  while (exp > 0n) {
    if (exp % 2n === 1n) result = (result * base) % mod;
    exp = exp >> 1n;
    base = (base * base) % mod;
  }
  return result;
}

function modInverse(a, m) {
  // Extended Euclidean Algorithm
  let [old_r, r] = [a, m];
  let [old_s, s] = [1n, 0n];
  while (r !== 0n) {
    const q = old_r / r;
    [old_r, r] = [r, old_r - q * r];
    [old_s, s] = [s, old_s - q * s];
  }
  if (old_r !== 1n) throw new Error('No modular inverse');
  return ((old_s % m) + m) % m;
}

// ---------------------------------------------------------------------------
// SHA-256 helper (returns BigInt of the digest)
// ---------------------------------------------------------------------------

async function sha256BigInt(bytes) {
  const digest = await crypto.subtle.digest('SHA-256', bytes);
  return bytesToBigInt(new Uint8Array(digest));
}

// ---------------------------------------------------------------------------
// Parse RSA public key from PEM
// Returns { n: BigInt, e: BigInt }
// ---------------------------------------------------------------------------

async function parseRsaPublicKey(pem) {
  const b64 = pem
    .replace(/-----BEGIN PUBLIC KEY-----/, '')
    .replace(/-----END PUBLIC KEY-----/, '')
    .replace(/\s+/g, '');
  const der = base64ToBytes(b64);

  // Import via SubtleCrypto to extract n and e
  const cryptoKey = await crypto.subtle.importKey(
    'spki',
    der,
    { name: 'RSASSA-PKCS1-v1_5', hash: 'SHA-256' },
    true,
    ['verify']
  );
  const jwk = await crypto.subtle.exportKey('jwk', cryptoKey);
  const n = base64ToBigInt(jwk.n.replace(/-/g, '+').replace(/_/g, '/'));
  const e = base64ToBigInt(jwk.e.replace(/-/g, '+').replace(/_/g, '/'));
  return { n, e };
}

// ---------------------------------------------------------------------------
// Core blind signature operations
// ---------------------------------------------------------------------------

/**
 * Generate a random 32-byte token.
 * @returns {Uint8Array}
 */
function generateToken() {
  const token = new Uint8Array(32);
  crypto.getRandomValues(token);
  return token;
}

/**
 * Blind a token using the issuer's RSA public key.
 *
 * @param {Uint8Array} token        — the voter's secret random token
 * @param {string}     publicKeyPem — issuer PEM public key
 * @returns {Promise<{blindedB64: string, blindingFactor: BigInt}>}
 */
async function blindToken(token, publicKeyPem) {
  const { n, e } = await parseRsaPublicKey(publicKeyPem);
  const keyByteLen = Math.ceil(n.toString(16).length / 2);

  // m = SHA-256(token) mod n
  const m = (await sha256BigInt(token)) % n;

  // Choose random r in [2, n-2] with r != 0
  let r;
  do {
    const rBytes = new Uint8Array(keyByteLen);
    crypto.getRandomValues(rBytes);
    r = bytesToBigInt(rBytes) % n;
  } while (r <= 1n);

  // blinded = m * r^e mod n
  const r_e = modPow(r, e, n);
  const blinded = (m * r_e) % n;

  const blindedBytes = bigIntToBytes(blinded, keyByteLen);
  return {
    blindedB64: bytesToBase64(blindedBytes),
    blindingFactor: r,
  };
}

/**
 * Unblind the issuer's blind signature.
 *
 * @param {string} blindSigB64     — blind signature from server (base64)
 * @param {BigInt} blindingFactor  — r used during blinding
 * @param {string} publicKeyPem    — issuer PEM public key
 * @returns {Promise<BigInt>}      — the actual signature
 */
async function unblindSignature(blindSigB64, blindingFactor, publicKeyPem) {
  const { n } = await parseRsaPublicKey(publicKeyPem);
  const blindSig = base64ToBigInt(blindSigB64);
  const r_inv = modInverse(blindingFactor, n);
  return (blindSig * r_inv) % n;
}

/**
 * Verify a blind signature credential.
 *
 * @param {Uint8Array} token       — the original token
 * @param {BigInt}     signature   — the unblinded signature
 * @param {string}     publicKeyPem
 * @returns {Promise<boolean>}
 */
async function verifySignature(token, signature, publicKeyPem) {
  const { n, e } = await parseRsaPublicKey(publicKeyPem);
  const m = (await sha256BigInt(token)) % n;
  const recovered = modPow(signature, e, n);
  return recovered === m;
}

/**
 * Serialize a credential for submission to /api/vote.
 *
 * @param {Uint8Array} token
 * @param {BigInt}     signature
 * @returns {{token_hex: string, signature_b64: string}}
 */
function serializeCredential(token, signature) {
  return {
    token_hex: bytesToHex(token),
    signature_b64: bigIntToBase64(signature),
  };
}

// ---------------------------------------------------------------------------
// LocalStorage helpers for credential persistence
// ---------------------------------------------------------------------------

const CRED_KEY = 'securevote_credential';

function saveCredential(tokenHex, signatureB64, blindingFactorHex) {
  localStorage.setItem(CRED_KEY, JSON.stringify({
    token_hex: tokenHex,
    signature_b64: signatureB64,
    blinding_factor_hex: blindingFactorHex,
    saved_at: new Date().toISOString(),
  }));
}

function loadCredential() {
  try {
    const raw = localStorage.getItem(CRED_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch (_) {
    return null;
  }
}

function clearCredential() {
  localStorage.removeItem(CRED_KEY);
}
