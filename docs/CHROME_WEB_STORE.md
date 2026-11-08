# Publishing the extension on the Chrome Web Store

For whoever publishes CrossChat's browser extension. Everything the [developer dashboard](https://chrome.google.com/webstore/devconsole) asks for is here, ready to paste.

**Listing:** item ID `bnjoldkacppoejikoiccgkblbajbenhj`, first submitted for review on 8 November 2026. Its address once approved: https://chromewebstore.google.com/detail/bnjoldkacppoejikoiccgkblbajbenhj

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

**Category:** Communication. **Language:** English.

**Description:**

```
CrossChat puts the chat of every platform you stream to in one window, and lets you answer everyone from there. This extension is the part that works in your browser. It needs the free CrossChat app on your computer: https://github.com/RandyNorthrup/crosschat-obs

What the extension does
• Posts the replies you write in CrossChat to YouTube, X, TikTok, Facebook, Instagram and Rumble, by typing them into each site's own chat box, as the account already signed in to your browser.
• Brings chat in from your own X livestream, TikTok LIVE page, Facebook Live Producer and Instagram live.
• Carries out the moderation you ask for on YouTube, Facebook and Rumble, in those sites' own menus.
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

**Host permission justification** (one box, at most 1,000 characters; the extension asks for no API permissions):

```
127.0.0.1:4466 is the CrossChat app on the user's own computer, the only place the extension sends data. studio.x.com: starts and ends the user's own X livestream when asked, reads its chat, types their replies. youtube.com/live_chat: types the user's replies and carries out their moderation through YouTube's own menus. tiktok.com: the user's own TikTok LIVE page only; TikTok changes pages without a reload, so the script must load on the site, but it asks the app which account is the user's and does nothing on any other page. facebook.com/live/producer: shows only the user's own broadcasts; reads comments, types replies, deletes a comment when asked. instagram.com, home page only, where Instagram's Live producer opens: reads the user's own live's comments and viewer count, types their replies. rumble.com/chat/popup: types the user's replies in their own live's chat and carries out their moderation there.
```

**Remote code:** No, I am not using remote code. (All JavaScript ships in the package. There is no `eval` and nothing is downloaded.)

**Data usage.** These answers are declarations you make to Google, so check they still match the code before ticking them. What the code does today:

- Tick **Personal communications** (the form's examples include chat messages) and **Website content**: chat text and viewer names on the user's own live pages are read and passed to the app on the same computer.
- Leave the rest unticked: it reads no logins, health or financial data, location, browsing history or activity.
- Tick all three certifications: not sold to third parties, not used for purposes unrelated to the single purpose, not used for creditworthiness or lending. Nothing is ever sent to the developer.

**Privacy policy URL:** https://github.com/RandyNorthrup/crosschat-obs/blob/main/PRIVACY.md

## Test instructions

The **Additional instructions** box takes at most 500 characters. Username and password stay empty.

```
Needs the free CrossChat app on the same computer. It works on the tester's own live streams, so no account is supplied. To see it connect, with made-up chat and nothing posted: install Python 3.10+, download github.com/RandyNorthrup/crosschat-obs, run pip install -r hub/requirements.txt, then python hub/hub.py --demo. Open http://127.0.0.1:4466/ in the browser with the extension and send a reply: the demo shows it as sent. The extension has no interface of its own.
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
