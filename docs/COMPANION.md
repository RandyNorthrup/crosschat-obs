# The companion: chat on your phone or another PC

The CrossChat window on your streaming PC can also be opened on a **phone, tablet or second PC** on your home network. You get the same live chat with viewer counts. From there you can:

- reply to everyone, to one platform or to one person;
- send quick replies;
- show a message on stream;
- star messages to answer later;
- moderate.

Nothing is installed on the other device: it's a web page, and you can add it to the home screen like an app.

<p align="center">
  <img src="../assets/screenshots/companion-phone.png" alt="CrossChat on a phone: live chat from Twitch, YouTube, Kick and X with quick replies" width="300">
  <img src="../assets/screenshots/companion-phone-mod.png" alt="The actions for one message on a phone: moderation and quick replies" width="300">
</p>

## Pair a device

1. On the streaming PC, open the CrossChat window and press the **gear** (Settings) → **Pair a device**.
2. A QR code, a 6-digit code and an address appear. The code works for **5 minutes**.
3. On the phone, scan the QR code with the camera. On another PC, type the address into its browser. Either way the device is paired and opens the chat.
4. The first time, Windows asks whether CrossChat may use the network. Choose **Allow** for **private networks**.

<p align="center"><img src="../assets/screenshots/companion-pair.png" alt="Settings on the streaming PC: paired devices and the pairing QR code" width="360"></p>

**Add it to the home screen**, so it opens like an app:
- iPhone and iPad: Safari → **Share** → **Add to Home Screen**.
- Android: Chrome menu → **Add to Home screen** (or **Install app**).

Each paired device is listed under **Settings → Paired devices** on the streaming PC, with the day it was paired and when it was last seen. **Remove** takes its access away at once; pair it again to bring it back.

## What works when

The companion talks to the CrossChat hub on the streaming PC, so that PC must be on, with OBS (and so the hub) running.

| | Needs |
|---|---|
| Reading chat, viewer counts, live status | The hub running (it starts with OBS) |
| Show on stream, Answer later, quick-reply editing, test events | The hub running |
| Replies and moderation on **Twitch** | **Twitch connected** in Settings on the streaming PC; otherwise the CrossChat window open on the streaming PC |
| Replies and moderation on **YouTube**, replies on **X** | The **CrossChat window open on the streaming PC**, in Chrome or Edge with the CrossChat extension. It opens by itself when you go live. |
| **Kick** | Read only: Kick chat can't be answered or moderated from CrossChat yet |

When something isn't available, the companion says why: in the bar under the header, next to the action (greyed out with a reason), or in the chat list after you try.

## Using it

- **Tap a message** (or click **⋯**, right-click, or select it and press Enter) to see what you can do with it:
  - **Reply**: answers that person on their own platform. On Twitch it's a threaded reply.
  - **Show on stream / Hide from stream**: puts it in the featured-message widget.
  - **Answer later**: stars it.
  - **Copy text**.
  - **Moderate**: see below.
  - **Quick reply to *name***: one of your quick replies, sent to that person.
- **Mouse:** hovering a message shows **reply**, **show**, **☆** and **⋯**.
- **Keyboard:**
  - **↑ ↓** move between messages, and **Enter** opens the actions;
  - **r** replies, and **s** stars;
  - **Esc** cancels a reply.
- **The box** sends to every live chat that takes replies. Use **only:** to send to one platform. The counter warns when a message is too long for a platform: X takes 140 characters, YouTube 200, Twitch 500.

### Quick replies

The row above the box holds your quick replies.
- **Tap** one to send it to every live chat at once.
- **Hold** it (or right-click it) to put it in the box first, to add to it.
- **✎** opens the editor: add, reorder or remove replies. You can have up to 30, each up to 100 characters.

The list is kept by the hub, so every device and the streaming PC share it.

### Questions and Answer later

- **Questions** shows only messages that ask something. CrossChat spots them by itself, and they're marked **Q** in the list.
- **Answer later** shows the messages you starred. Starred messages stay in the list even when chat moves fast. Stars are shared between all your devices, so you can star on the phone and answer from the PC.

### Moderation

| | Delete a message | Timeout | Ban |
|---|---|---|---|
| **Twitch** (Twitch connected) | ✓ | 10 minutes, 1 hour, or any length up to 14 days | ✓ (and unban) |
| **YouTube** (CrossChat window open on the streaming PC) | ✓ (remove) | 5 minutes (YouTube's fixed length) | Hide user on this channel |
| **X**, **Kick** | — | — | — |

- A ban always asks first.
- On YouTube, CrossChat uses YouTube's own chat menu in the CrossChat window on the streaming PC. The YouTube account signed in there must own the channel or be a moderator.
- **Connect Twitch:**
  1. On the streaming PC: Settings → **Connect Twitch**.
  2. Go to **twitch.tv/activate** and enter the code shown, signed in as the streamer or a moderator.
  3. After that, Twitch replies and moderation work without the browser extension, from every device.

## Settings

| | |
|---|---|
| **Look and sound** | Auto (follows the device), Light or Dark; a ding when a message arrives. Each device remembers its own. |
| **Twitch** | Connect or disconnect (on the streaming PC). |
| **Paired devices** | The list, **Remove**, and **Pair a device** (on the streaming PC). |
| **Check the stream** | Test chat, alert, featured message or viewer count on the widgets in OBS, without going live. |
| **About** | The version, and on the streaming PC the address other devices use. |

## Keeping it private

- **Paired devices only.**
  - Each paired device has its own key, kept by its browser.
  - Without one, the companion address shows only the pairing page.
  - Pairing codes are random, 6 digits, and last 5 minutes.
- **Home network only.**
  - The companion uses plain `http` on your local network, like a printer's or router's own page.
  - Use it on a network you trust, not public or hotel Wi-Fi.
  - **Don't forward its port** on your router.
- **From away from home**, the safe way is [Tailscale](https://tailscale.com): a private network between your own devices, free for personal use. Install it on the streaming PC and the phone, then open the companion address with the PC's Tailscale name or address. Pairing works the same.
- Removing a device in Settings takes effect immediately. The device then says it is no longer paired.

## Troubleshooting

| Problem | Try |
|---|---|
| The address doesn't load on the phone | Same Wi-Fi as the PC (not a guest network, which often keeps devices apart)? Did Windows ask about the network and get **Allow** for private networks? If not, open Windows Security → Firewall → *Allow an app through firewall* and tick **Private** for Python. |
| It worked yesterday, not today | The PC may have a new address on your network. Pair again; the new address is in the QR code and under Settings → About. |
| "This device is no longer paired" | It was removed, or its key was cleared with the browser's data. Pair it again. |
| "Needs the CrossChat window open on the streaming PC" | Open it there: Start menu → CrossChat → **Open chat** (Chrome or Edge with the extension), or go live and it opens by itself. For Twitch, connecting Twitch removes the need. |
| Twitch says "This CrossChat has no Twitch app Client ID" | This build can't connect to Twitch's API. Twitch replies still go out through the CrossChat window on the streaming PC. |
