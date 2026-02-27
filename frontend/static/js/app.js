/**
 * SecureVote — shared UI utilities and API client
 */

const API_BASE = '';  // same origin

// ---------------------------------------------------------------------------
// API helpers
// ---------------------------------------------------------------------------

async function apiFetch(path, opts = {}) {
  const res = await fetch(API_BASE + path, {
    headers: { 'Content-Type': 'application/json', ...(opts.headers || {}) },
    ...opts,
  });
  const json = await res.json();
  if (!res.ok && !json.hasOwnProperty('success')) {
    throw new Error(json.error || `HTTP ${res.status}`);
  }
  return json;
}

async function getPublicKey() {
  const data = await apiFetch('/api/public-key');
  return data.public_key;
}

async function registerVoter(voterId, blindedB64) {
  return apiFetch('/api/register', {
    method: 'POST',
    body: JSON.stringify({ voter_id: voterId, blinded_token_b64: blindedB64 }),
  });
}

async function castVote(tokenHex, signatureB64, candidate) {
  return apiFetch('/api/vote', {
    method: 'POST',
    body: JSON.stringify({ token_hex: tokenHex, signature_b64: signatureB64, candidate }),
  });
}

async function getResults() {
  return apiFetch('/api/results');
}

async function getChain() {
  return apiFetch('/api/blockchain');
}

async function verifyChain() {
  return apiFetch('/api/blockchain/verify');
}

async function getVoterStatus(voterId) {
  return apiFetch(`/api/voter/${encodeURIComponent(voterId)}/status`);
}

async function verifyToken(tokenHex, signatureB64) {
  return apiFetch('/api/verify-token', {
    method: 'POST',
    body: JSON.stringify({ token_hex: tokenHex, signature_b64: signatureB64 }),
  });
}

// ---------------------------------------------------------------------------
// DOM helpers
// ---------------------------------------------------------------------------

function showAlert(container, message, type = 'info') {
  // type: success | error | info | warning
  const div = document.createElement('div');
  div.className = `alert alert-${type}`;
  div.textContent = message;
  container.innerHTML = '';
  container.appendChild(div);
  container.classList.remove('hidden');
}

function showElement(el)  { el.classList.remove('hidden'); }
function hideElement(el)  { el.classList.add('hidden'); }

function setLoading(btn, loading, originalText) {
  if (loading) {
    btn.disabled = true;
    btn.innerHTML = `<span class="spinner"></span> Processing…`;
  } else {
    btn.disabled = false;
    btn.textContent = originalText;
  }
}

function setStep(steps, activeIndex) {
  steps.forEach((s, i) => {
    s.classList.remove('active', 'done');
    if (i < activeIndex)  s.classList.add('done');
    if (i === activeIndex) s.classList.add('active');
  });
}
