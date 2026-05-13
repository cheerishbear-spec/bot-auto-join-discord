require('dotenv').config();

function required(name) {
  const value = process.env[name];
  if (!value || value.trim() === '') {
    throw new Error(`Missing required env var: ${name}`);
  }
  return value.trim();
}

const config = {
  telegram: {
    apiId: parseInt(required('TELEGRAM_API_ID'), 10),
    apiHash: required('TELEGRAM_API_HASH'),
    channel: required('TELEGRAM_CHANNEL'),
    session: process.env.TELEGRAM_SESSION || '',
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
