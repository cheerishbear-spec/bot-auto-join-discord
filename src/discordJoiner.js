const { Client } = require('discord.js-selfbot-v13');
const { log } = require('./utils');

class DiscordJoiner {
  constructor(token) {
    this.token = token;
    this.client = new Client();
    this.ready = false;
  }

  async start() {
    return new Promise((resolve, reject) => {
      this.client.once('ready', () => {
        this.ready = true;
        log(`Discord logged in as ${this.client.user.tag}`);
        resolve();
      });
      this.client.login(this.token).catch(reject);
    });
  }

  async joinInvite(code) {
    if (!this.ready) {
      throw new Error('Discord client not ready yet');
    }

    // Best-effort pre-check: if we can fetch invite and we're already in that
    // guild, skip. If fetchInvite itself blows up (library bugs like
    // "Invalid bitfield flag: GUEST"), ignore it and try to accept anyway.
    try {
      const invite = await this.client.fetchInvite(code);
      if (invite?.guild && this.client.guilds.cache.has(invite.guild.id)) {
        log(`Already in guild for invite ${code} (${invite.guild.name}), skip`);
        return { ok: true, skipped: true };
      }
    } catch (err) {
      log(`(pre-check skipped for ${code}: ${err.message})`);
    }

    try {
      const accepted = await this.client.acceptInvite(code);
      const guildName = accepted?.name ?? 'unknown guild';
      log(`Joined invite ${code} -> ${guildName}`);
      return { ok: true, skipped: false };
    } catch (err) {
      // Treat "already in guild" errors as success (code 50007 / message match)
      if (err?.code === 50007 || /already/i.test(err?.message || '')) {
        log(`Already in guild for invite ${code}, skip`);
        return { ok: true, skipped: true };
      }
      log(`Failed to join invite ${code}: ${err.message}`);
      return { ok: false, error: err.message };
    }
  }
}

module.exports = DiscordJoiner;
