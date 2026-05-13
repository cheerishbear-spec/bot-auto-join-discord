const config = require('./config');
const DiscordJoiner = require('./discordJoiner');
const { startTelegramListener } = require('./telegramListener');
const { extractInviteCodes, sleep, randomDelay, log } = require('./utils');

async function main() {
  const joiner = new DiscordJoiner(config.discord.token);
  await joiner.start();

  await startTelegramListener(config.telegram, async (text) => {
    const codes = extractInviteCodes(text);
    if (codes.length === 0) return;

    log(`Detected ${codes.length} invite(s): ${codes.join(', ')}`);

    for (const code of codes) {
      const delay = randomDelay(config.sniper.delayMinMs, config.sniper.delayMaxMs);
      log(`Waiting ${delay}ms before joining ${code}...`);
      await sleep(delay);
      await joiner.joinInvite(code);
    }
  });

  log('Sniper is running. Press Ctrl+C to stop.');
}

main().catch((err) => {
  console.error('Fatal error:', err);
  process.exit(1);
});
