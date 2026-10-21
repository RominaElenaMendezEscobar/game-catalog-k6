// Minimal AWS Signature Version 4 for k6 (no external dependencies).
// Signs requests to API Gateway endpoints protected with IAM authorization.

import crypto from 'k6/crypto';

function hmac(key, data) {
  return crypto.hmac('sha256', key, data, 'binary');
}

function toAmzDate(date) {
  return date.toISOString().replace(/[:-]|\.\d{3}/g, '');
}

function encodePath(path) {
  return path.split('/').map((s) => encodeURIComponent(s)).join('/');
}

/**
 * Returns the headers needed to send a signed request.
 * @param {object} opts
 *   method, url, body, region, service ('execute-api'),
 *   accessKeyId, secretAccessKey, sessionToken (optional), headers (optional), date (optional)
 */
export function signRequest(opts) {
  // k6 has no global URL class: parse the URL with a regular expression
  const m = /^https?:\/\/([^/?#]+)([^?#]*)(?:\?([^#]*))?/.exec(opts.url);
  if (!m) {
    throw new Error(`Invalid URL: ${opts.url}`);
  }
  const host = m[1];
  const path = encodePath(m[2] || '/');
  const query = m[3] ? m[3].split('&').sort().join('&') : '';
  const body = opts.body || '';
  const date = opts.date || new Date();
  const amzDate = toAmzDate(date);
  const dateStamp = amzDate.substring(0, 8);

  const payloadHash = crypto.sha256(body, 'hex');

  const headers = { ...(opts.headers || {}) };
  headers['host'] = host;
  headers['x-amz-date'] = amzDate;
  headers['x-amz-content-sha256'] = payloadHash;
  if (opts.sessionToken) {
    headers['x-amz-security-token'] = opts.sessionToken;
  }

  const lower = {};
  Object.keys(headers).forEach((k) => {
    lower[k.toLowerCase()] = String(headers[k]).trim().replace(/\s+/g, ' ');
  });
  const signedHeaderNames = Object.keys(lower).sort();
  const canonicalHeaders = signedHeaderNames.map((k) => `${k}:${lower[k]}\n`).join('');
  const signedHeaders = signedHeaderNames.join(';');

  const canonicalRequest = [
    opts.method.toUpperCase(),
    path,
    query,
    canonicalHeaders,
    signedHeaders,
    payloadHash,
  ].join('\n');

  const scope = `${dateStamp}/${opts.region}/${opts.service}/aws4_request`;
  const stringToSign = [
    'AWS4-HMAC-SHA256',
    amzDate,
    scope,
    crypto.sha256(canonicalRequest, 'hex'),
  ].join('\n');

  const kDate = hmac(`AWS4${opts.secretAccessKey}`, dateStamp);
  const kRegion = hmac(kDate, opts.region);
  const kService = hmac(kRegion, opts.service);
  const kSigning = hmac(kService, 'aws4_request');
  const signature = crypto.hmac('sha256', kSigning, stringToSign, 'hex');

  headers['Authorization'] =
    `AWS4-HMAC-SHA256 Credential=${opts.accessKeyId}/${scope}, ` +
    `SignedHeaders=${signedHeaders}, Signature=${signature}`;
  delete headers['host'];
  return headers;
}
