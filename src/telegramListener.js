const { TelegramClient } = require('telegram');
const { StringSession } = require('telegram/sessions');
const { NewMessage } = require('telegram/events');
const input = require('input');
const { log } = require('./utils');

async function startTelegramListener({ apiId, apiHash, session, channel }, onMessage) {
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
    log('>>> Save this TELEGRAM_SESSION to your .env to skip login next time:');
    log(saved);
  }

  // Resolve channel entity once so filter works with id
  const entity = await client.getEntity(channel);
  log(`Listening to channel: ${entity.title || channel}`);

  client.addEventHandler(async (event) => {
    const msg = event.message;
    if (!msg || !msg.message) return;
    try {
      await onMessage(msg.message);
    } catch (err) {
      log('onMessage handler error:', err.message);
    }
  }, new NewMessage({ chats: [entity] }));

  return client;
}

module.exports = { startTelegramListener };
