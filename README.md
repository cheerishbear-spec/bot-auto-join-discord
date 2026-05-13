# bot-auto-join-discord

Auto-join Discord server dari invite link yang di-snipe dari sebuah **public channel Telegram**.

> ⚠️ **Warning**: Pakai user token Discord untuk automation melanggar [Discord ToS](https://discord.com/terms) (self-bot). Akun lo bisa kena ban permanen. **Pakai akun alt/throwaway**, jangan akun utama.

## Cara Kerja

```
Telegram channel kirim pesan
        ↓
Bot baca isi pesan (GramJS event handler)
        ↓
Regex extract: discord.gg/xxx atau discord.com/invite/xxx
        ↓
Delay random 2-3 detik
        ↓
Accept invite via discord.js-selfbot-v13
```

## Requirements

- Node.js >= 18
- Akun Telegram (buat login sekali pake OTP)
- Akun Discord (yang mau dipake buat auto-join)

## Setup

### 1. Install dependencies

```bash
npm install
```

### 2. Ambil credentials

**Telegram `api_id` & `api_hash`:**
1. Login ke https://my.telegram.org/apps
2. Bikin application baru, copy `api_id` & `api_hash`

**Discord user token:**
1. Buka Discord di browser, login
2. Buka DevTools (F12) → tab **Network**
3. Kirim pesan / klik apapun biar ada request ke `discord.com/api`
4. Klik salah satu request → **Headers** → cari `authorization`
5. Copy valuenya (format: `Mxxxxx.xxxxx.xxxxx`)

### 3. Konfigurasi `.env`

Copy template-nya:

```bash
cp .env.example .env
```

Isi:

```
TELEGRAM_API_ID=123456
TELEGRAM_API_HASH=abcdef...
TELEGRAM_CHANNEL=namachannel       # tanpa @
TELEGRAM_SESSION=                  # kosongkan dulu, diisi setelah login pertama
DISCORD_TOKEN=Mxxxxx.xxxxx.xxxxx
JOIN_DELAY_MIN_MS=2000
JOIN_DELAY_MAX_MS=3000
```

### 4. Jalankan

```bash
npm start
```

Pertama kali jalan, lo bakal diminta:
- Phone number (format internasional, misal `+6281234567890`)
- Kode OTP dari Telegram
- Password 2FA (kalau akun lo pake)

Setelah sukses login, script bakal **print session string** ke console. Copy string itu ke `TELEGRAM_SESSION` di `.env` biar run berikutnya ga login ulang.

## Output

```
[2026-05-13T...] Discord logged in as username#0
[2026-05-13T...] Telegram connected
[2026-05-13T...] Listening to channel: NamaChannel
[2026-05-13T...] Detected 1 invite(s): aBcDeF
[2026-05-13T...] Waiting 2473ms before joining aBcDeF...
[2026-05-13T...] Joined invite aBcDeF -> Nama Server
```

## Struktur Project

```
src/
├── config.js            # Load & validate env vars
├── utils.js             # Regex invite extractor, delay helper, logger
├── discordJoiner.js     # Selfbot client + join logic
├── telegramListener.js  # GramJS client + channel listener
└── index.js             # Entry point, gabungin semua
```

## Disclaimer

Project ini untuk tujuan edukasi. Penggunaan bertanggung jawab ada di tangan lo sendiri.
