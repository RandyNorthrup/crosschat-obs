# Publishing the extension on the Chrome Web Store

For whoever publishes CrossChat's browser extension. Everything the [developer dashboard](https://chrome.google.com/webstore/devconsole) asks for is here, ready to paste. Chrome doesn't let tools script the dashboard, so this is done by hand.

## Build the upload

```
python scripts/package_extension.py
```

It writes `dist/CrossChat-extension-<version>.zip` and refuses anything the store would refuse at upload. Every later upload needs a higher `version` in `extension/manifest.json`.

`PRIVACY.md` must be on GitHub's `main` branch before you submit, because the listing links to it.

## Steps

1. **Account:** dashboard → *Account*. Set a publisher name, verify the contact email, and answer the trader / non-trader question for the EU.
2. **Upload:** *Items → New item* → the zip.
3. **Store listing:** paste from [Store listing](#store-listing), and upload the pictures from `assets/webstore/`.
4. **Privacy:** paste from [Privacy tab](#privacy-tab).
5. **Distribution:** Free, all regions, Public.
6. **Test instructions:** paste from [Test instructions](#test-instructions).
7. **Submit for review.** Leave "publish automatically" on, or turn it off to choose the moment.

## Store listing

**Title** (from the manifest): CrossChat

**Summary** (from the manifest): Companion to the CrossChat app: reads your own live chats and posts your replies. Talks only to the app on this PC. Reads no logins.

**Category:** Social & Communication. **Language:** English.

**Description:**

```
CrossChat puts the chat of every platform you stream to in one window, and lets you answer everyone from there. This extension is the part that works in your browser. It needs the free CrossChat app on your computer: https://github.com/RandyNorthrup/crosschat-obs

What the extension does
• Posts the replies you write in CrossChat to YouTube, X, TikTok, Facebook, Instagram and Rumble, by typing them into each site's own chat box, as the account already signed in to your browser.
• Brings chat in from your own X livestream, TikTok LIVE page, Facebook Live Producer and Instagram live.
• Carries out the moderation you ask for on YouTube and Facebook, in those sites' own menus.
• Starts and ends your X livestream when you ask, or together with your stream.
• Places and closes the windows CrossChat opens. Your own browser windows are never touched.

Private by design
• Talks only to the CrossChat app on your own computer (127.0.0.1). There is no CrossChat server.
• Asks for no Chrome permissions: no cookies, no tabs, no history, no storage.
• Reads no logins, passwords or tokens.
• Open source: every line is on GitHub.

CrossChat is an independent project, and is not made by or affiliated with X, YouTube, TikTok, Meta, Rumble, Twitch or Kick.
```

**Pictures** (`assets/webstore/`): store icon `extension/icons/icon-128.png`; screenshots `screenshot-1-reply.png` to `screenshot-4-studio.png` (1280 × 800); small promo tile `promo-small-440x280.png`.

**Homepage URL:** https://github.com/RandyNorthrup/crosschat-obs

**Support URL:** https://github.com/RandyNorthrup/crosschat-obs/issues

## Privacy tab

**Single purpose:**

```
Connects the streamer's own live-stream pages to the CrossChat app on their computer, so they can read and answer the chat of every platform they stream to from one window.
```

**Permissions:** the extension asks for no API permissions, only these host permissions.

| Host permission | Justification to paste |
|---|---|
| `http://127.0.0.1:4466/*` | The CrossChat app on the user's own computer. The extension exchanges chat lines and reply jobs with it, and nothing else. |
| `https://studio.x.com/*` | X Live Studio: starts and ends the user's own X livestream when they ask, reads its chat, and types their replies. |
| `https://www.youtube.com/live_chat*` | YouTube's chat box: types the user's replies and carries out their moderation through YouTube's own menus. |
| `https://www.tiktok.com/*` | The user's own TikTok LIVE page: reads its chat and types their replies. TikTok moves between pages without a reload, so the script must be present on the site; it asks the app which account is the user's and does nothing on any other page. |
| `https://www.facebook.com/live/producer*` | Facebook Live Producer, which shows only the user's own broadcasts: reads comments, types replies, and deletes a comment when asked. |
| `https://www.instagram.com/` | The home page only, where Instagram's Live producer opens: reads the user's own live's comments and viewer count, and types their replies. |
| `https://rumble.com/chat/popup/*` | Rumble's chat pop-out: types the user's replies in their own live's chat. |

**Remote code:** No, I am not using remote code. (All JavaScript ships in the package. There is no `eval` and nothing is downloaded.)

**Data usage.** These answers are declarations you make to Google, so check they still match the code before ticking them. What the code does today:

- Tick **Website content**: chat text and viewer names on the user's own live pages are read and passed to the app on the same computer.
- Leave the rest unticked: it reads no logins, health or financial data, location, browsing history or activity.
- Tick all three certifications: not sold to third parties, not used for purposes unrelated to the single purpose, not used for creditworthiness or lending. Nothing is ever sent to the developer.

**Privacy policy URL:** https://github.com/RandyNorthrup/crosschat-obs/blob/main/PRIVACY.md

## Test instructions

```
The extension needs the CrossChat app on the same computer, and works on the tester's own live streams, so no account is supplied.

To see it connect, with made-up chat and nothing posted anywhere:
1. Install Python 3.10 or newer, then download the source from https://github.com/RandyNorthrup/crosschat-obs and run: pip install -r hub/requirements.txt
2. Run: python hub/hub.py --demo
3. Open http://127.0.0.1:4466/ in the browser with the extension. The chat window opens with sample chat. Type a reply and send it: the demo shows it as sent and nothing leaves the computer.

The extension reads nothing on other sites and shows no interface of its own.
```

## Once it is approved

1. Copy the listing's address, `https://chromewebstore.google.com/detail/<id>`.
2. Replace the **Load unpacked** steps with that link in `README.md` (Install, Mac, Linux), `installer/first-steps.html` and `scripts/install.ps1`, and the matching lines in `scripts/install.sh`.
3. Edge users can install from the Chrome Web Store too, after allowing extensions from other stores.

## Things a reviewer may question

- **`www.tiktok.com/*`** is the broadest host permission. The justification above explains why.
- **The icon** is CrossChat's own mark, but it looks like X's logo. Reviewers can turn down an icon that suggests another company's product, so have a different one ready if they object.
- **`rumble-confirm.js`** runs in the page's own world, which reviewers look at closely. It is short, and it only answers Rumble's confirmation box when the extension deletes a message the streamer asked it to.
- A store-installed extension **updates on its own**, separately from the app. Keep the extension compatible with the previous app version.
