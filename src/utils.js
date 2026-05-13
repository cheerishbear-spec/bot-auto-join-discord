// Match discord.gg/xxx, discord.com/invite/xxx, discordapp.com/invite/xxx
const INVITE_URL_REGEX =
  /(?:https?:\/\/)?(?:www\.)?(?:discord\.gg|discord(?:app)?\.com\/invite)\/([a-zA-Z0-9-]+)/gi;

// Match a standalone invite code: a single word, 2-16 chars, alphanumeric + dash/underscore.
// Anchored to whitespace boundaries so we don't greedily grab random substrings.
const STANDALONE_CODE_REGEX = /(?:^|\s)([a-zA-Z0-9_-]{2,16})(?=\s|$)/g;

// Common false-positive words to skip when scanning standalone codes.
const CODE_BLACKLIST = new Set([
  'http', 'https', 'www', 'com', 'org', 'net',
  'the', 'and', 'for', 'not', 'you', 'are', 'this', 'that',
  'join', 'link', 'invite', 'server', 'click', 'here', 'new',
]);

function extractInviteCodes(text) {
  if (!text) return [];
  const codes = new Set();

  // 1) URL-based invites (discord.gg/xxx, discord.com/invite/xxx, etc.)
  let m;
  INVITE_URL_REGEX.lastIndex = 0;
  while ((m = INVITE_URL_REGEX.exec(text)) !== null) {
    codes.add(m[1]);
  }

  // If we found URL invites, return them only (safer, avoids false positives).
  if (codes.size > 0) return [...codes];

  // 2) Otherwise, scan for standalone codes. Only when the message is short-ish
  // and looks like someone pasting a raw code ("TG5mYpebU"), not a long
  // sentence.
  const trimmed = text.trim();
  if (trimmed.length === 0 || trimmed.length > 200) return [];

  STANDALONE_CODE_REGEX.lastIndex = 0;
  while ((m = STANDALONE_CODE_REGEX.exec(` ${trimmed} `)) !== null) {
    const candidate = m[1];
    const lower = candidate.toLowerCase();
    if (CODE_BLACKLIST.has(lower)) continue;
    // Filter out plain English words: require a digit or mixed case.
    const hasDigit = /\d/.test(candidate);
    const hasMixedCase = /[a-z]/.test(candidate) && /[A-Z]/.test(candidate);
    if (!hasDigit && !hasMixedCase) continue;
    codes.add(candidate);
  }

  return [...codes];
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function randomDelay(minMs, maxMs) {
  const min = Math.min(minMs, maxMs);
  const max = Math.max(minMs, maxMs);
  return Math.floor(Math.random() * (max - min + 1)) + min;
}

function log(...args) {
  console.log(`[${new Date().toISOString()}]`, ...args);
}

module.exports = { extractInviteCodes, sleep, randomDelay, log };
