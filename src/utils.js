// Match discord.gg/xxx, discord.com/invite/xxx, discordapp.com/invite/xxx
const INVITE_REGEX =
  /(?:https?:\/\/)?(?:www\.)?(?:discord\.gg|discord(?:app)?\.com\/invite)\/([a-zA-Z0-9-]+)/gi;

function extractInviteCodes(text) {
  if (!text) return [];
  const codes = new Set();
  let match;
  while ((match = INVITE_REGEX.exec(text)) !== null) {
    codes.add(match[1]);
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
