# CrossChat privacy policy

Last updated: 8 November 2026

CrossChat is an open-source program that runs on your own computer, and a browser extension that works with it. It has no server of its own, no account, and no analytics or crash reports. The developer never receives your data.

## The browser extension

**What it handles.** On the pages listed below, and only while you use CrossChat, the extension reads the chat on your own live stream (viewers' names and messages, viewer counts) and passes it to the CrossChat program on your own computer. It types the replies you write in CrossChat into those sites' own chat boxes, as the account already signed in to your browser, and carries out the moderation you ask for there.

**Where that goes.** Only to `http://127.0.0.1:4466`, the CrossChat program on your own computer. The extension sends nothing to the developer or to any other server. What it types into a site goes to that site, because you asked it to post there.

**What it does not do.** It does not read your logins, passwords, cookies or tokens. It asks for no Chrome permissions, so it has no access to your tabs, history or storage. It does not read other sites, your feed, your direct messages or other people's profiles. It does not run code from anywhere else.

**Pages it may touch.**

| Page | Why |
|---|---|
| `127.0.0.1:4466` | The CrossChat program on your computer |
| `studio.x.com` | Start and end your X livestream, read its chat, type your replies |
| `www.youtube.com/live_chat` | Type your replies, carry out your moderation |
| `www.tiktok.com` | Your own TikTok LIVE page only. It first asks CrossChat which account is yours, and reads nothing on any other page |
| `www.facebook.com/live/producer` | Read comments on your own live, type your replies, delete a comment when you ask |
| `www.instagram.com/` | The home page only, where Instagram's Live producer opens: read your own live's comments and viewer count, type your replies |
| `rumble.com/chat/popup/` | Type your replies in your own live's chat, and carry out your moderation there |

**Selling and sharing.** Your data is not sold, not transferred to anyone, not used for advertising, and not used to decide creditworthiness or for lending.

## The CrossChat program

Everything it keeps stays on your computer: its settings, your sign-ins (encrypted for your user account) and, if you leave it on, your chat history, which you can delete at any time. It connects only to the services you set up. [SECURITY.md](https://github.com/RandyNorthrup/crosschat-obs/blob/main/SECURITY.md#what-leaves-your-pc) lists every connection it makes and what it sends.

## Removing your data

Remove the extension from your browser and uninstall CrossChat. Nothing about you is held anywhere else.

## Changes and contact

Changes to this policy are made in this file, so its [history](https://github.com/RandyNorthrup/crosschat-obs/commits/main/PRIVACY.md) shows every one. Questions: [open an issue](https://github.com/RandyNorthrup/crosschat-obs/issues).
