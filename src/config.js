require('dotenv').config();
const fs = require('fs');
const path = require('path');

function required(name) {
  const value = process.env[name];
  if (!value || value.trim() === '') {
    throw new Error(`Missing required env var: ${name}`);
  }
  return value.trim();
}

// Read session from .session.txt file (safer than .env for long strings
// with special chars like + / =).
function loadSession() {
  const sessionPath = path.resolve(process.cwd(), '.session.txt');
  if (!fs.existsSync(sessionPath)) return '';
  const raw = fs.readFileSync(sessionPath, 'utf8');
  return raw.trim().replace(/\s+/g, '');
}

function saveSession(sessionString) {
  const sessionPath = path.resolve(process.cwd(), '.session.txt');
  fs.writeFileSync(sessionPath, sessionString, 'utf8');
  return sessionPath;
}

const config = {
  telegram: {
    apiId: parseInt(required('TELEGRAM_API_ID'), 10),
    apiHash: required('TELEGRAM_API_HASH'),
    channel: required('TELEGRAM_CHANNEL'),
    session: loadSession(),
  },
  discord: {
    token: required('DISCORD_TOKEN'),
  },
  sniper: {
    delayMinMs: parseInt(process.env.JOIN_DELAY_MIN_MS || '2000', 10),
    delayMaxMs: parseInt(process.env.JOIN_DELAY_MAX_MS || '3000', 10),
  },
  saveSession,
};

module.exports = config;
