const { TelegramClient } = require('telegram');
const { StringSession } = require('telegram/sessions');
const { NewMessage } = require('telegram/events');
const input = require('input');
const { log } = require('./utils');
const config = require('./config');

async function startTelegramListener({ apiId, apiHash, session, channel }, onMessage) {
  if (session) {
    log(`Loaded session (length: ${session.length}, starts: "${session.slice(0, 8)}...")`);
  } else {
    log('No session file found (.session.txt), will login via OTP');
  }
  const stringSession = new StringSession(session || '');
  const client = new TelegramClient(stringSession, apiId, apiHash, {
    connectionRetries: 5,
  });

  await client.start({
    phoneNumber: async () => await input.text('Phone number: '),
    password: async () => await input.text('2FA password (if any): '),
    phoneCode: async () => await input.text('Code you received: '),
    onError: (err) => log('Telegram auth error:', err.message),
  });

  log('Telegram connected');

  if (!session) {
    const saved = client.session.save();
    const sessionPath = config.saveSession(saved);
    log(`Session saved to ${sessionPath} (next run will auto-login)`);
  }

  // Resolve channel entity once to log the title and get its numeric id.
  // NewMessage filter needs id/username (not an entity object).
  const entity = await client.getEntity(channel);
  const chatId = entity.id;
  log(`Listening to channel: ${entity.title || channel} (id: ${chatId})`);

  client.addEventHandler(async (event) => {
    const msg = event.message;
    if (!msg || !msg.message) return;
    try {
      await onMessage(msg.message);
    } catch (err) {
      log('onMessage handler error:', err.message);
    }
  }, new NewMessage({ chats: [chatId] }));

  return client;
}

module.exports = { startTelegramListener };
