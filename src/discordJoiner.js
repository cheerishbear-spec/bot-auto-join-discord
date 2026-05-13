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
    try {
      // Pre-check: skip if already a member of the invite's guild
      const invite = await this.client.fetchInvite(code);
      if (invite.guild && this.client.guilds.cache.has(invite.guild.id)) {
        log(`Already in guild for invite ${code} (${invite.guild.name}), skip`);
        return { ok: true, skipped: true };
      }

      // v3+ API: accept from the client, not the invite object
      const accepted = await this.client.acceptInvite(code);
      const guildName = accepted?.name ?? invite.guild?.name ?? 'unknown guild';
      log(`Joined invite ${code} -> ${guildName}`);
      return { ok: true, skipped: false };
    } catch (err) {
      log(`Failed to join invite ${code}: ${err.message}`);
      return { ok: false, error: err.message };
    }
  }
}

module.exports = DiscordJoiner;
