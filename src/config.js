require('dotenv').config();

function required(name) {
  const value = process.env[name];
  if (!value || value.trim() === '') {
    throw new Error(`Missing required env var: ${name}`);
  }
  return value.trim();
}

function sanitizeSession(name) {
  const value = process.env[name];
  if (!value) return '';
  // Strip wrapping quotes + any whitespace/newlines pasted by accident
  return value.trim().replace(/^["']|["']$/g, '').replace(/\s+/g, '');
}

const config = {
  telegram: {
    apiId: parseInt(required('TELEGRAM_API_ID'), 10),
    apiHash: required('TELEGRAM_API_HASH'),
    channel: required('TELEGRAM_CHANNEL'),
    session: sanitizeSession('TELEGRAM_SESSION'),
  },
  discord: {
    token: required('DISCORD_TOKEN'),
  },
  sniper: {
    delayMinMs: parseInt(process.env.JOIN_DELAY_MIN_MS || '2000', 10),
    delayMaxMs: parseInt(process.env.JOIN_DELAY_MAX_MS || '3000', 10),
  },
};

module.exports = config;
