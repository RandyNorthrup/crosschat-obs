# CrossChat API

The CrossChat hub is a small web server on your PC. The chat window, the Theme Studio, the OBS widgets and the companion all use it, and so can your own overlays and tools.

- **Base address:** `http://127.0.0.1:4466` (the `"port"` in `config.json`). The demo (`crosschat --demo`) runs on `4477`.
- **Live updates:** one [Server-Sent Events](https://developer.mozilla.org/docs/Web/API/Server-sent_events) stream, `GET /events`.
- **Changes:** `POST` with a JSON body, from the hub's own pages.

## Who can use what

| Caller | Can |
|---|---|
| The CrossChat window, the Theme Studio and the widgets (`http://127.0.0.1:4466/…`) | Everything below |
| **Your own overlay pages** (`http://localhost:4466/custom/…`) | Their own files, and the public chat: `/events` (public types only), `/settings`, `/version`, `/themes`. Nothing else |
| A program on this PC (no browser `Origin`) | Every `GET`. `POST` needs `Content-Type: application/json` |
| A paired companion device (port 4467) | `/events`, and `POST` to `/send`, `/mod`, `/feature`, `/star`, `/quick`, `/test`, `/tts/say`, `/tts/skip` |
| A page from any other website, or a local file | Nothing |

Put your own overlay pages in the folder named by `"custom_overlays"` in `config.json`. The hub serves them at `http://localhost:4466/custom/<file>` (an old `http://127.0.0.1:4466/custom/…` address is sent there). That address is kept apart from the CrossChat window's by the browser, so an overlay page you downloaded can show chat but can't reply, moderate or change anything as you. Inside one, `/events` and the other public addresses work as relative URLs; `http://127.0.0.1:4466/events` works too. See [SECURITY.md](../SECURITY.md) for the rules in full.

## Quick start: a custom overlay

```html
<!doctype html>
<meta charset="utf-8">
<ul id="chat"></ul>
<script>
  const list = document.getElementById('chat');
  const feed = new EventSource('/events');
  feed.onmessage = (e) => {
    const event = JSON.parse(e.data);
    if (event.type === 'msg' && event.kind === 'chat' && !event.hidden) {
      const li = document.createElement('li');
      li.dataset.id = event.id;
      li.textContent = event.name + ': ' + event.text;     // always textContent: chat is written by viewers
      list.append(li);
    }
    if (event.type === 'delete') list.querySelector(`[data-id="${CSS.escape(event.id)}"]`)?.remove();
  };
</script>
```

Save it as `my-chat.html` in your custom overlays folder and add `http://localhost:4466/custom/my-chat.html` to OBS as a browser source.

## `GET /events`

The stream starts with the last 300 messages, then the current state (`status`, `viewers`, `feature`, `emotes` and the rest), then everything as it happens. Each event is one JSON object in a `data:` line, with a `type`.

Your own overlay pages get the chat as viewers see it: `msg`, `delete`, `purge`, `clear`, `emotes`, `feature`, `status`, `theme` and `viewers`. Messages your filters hide, and CrossChat's own notes, are left out; a message filtered after it showed arrives as a `delete`.

### `msg`: a chat message, an alert or a note

| Field | Meaning |
|---|---|
| `id` | CrossChat's id for the message |
| `t` | Time, in milliseconds since 1970 |
| `p` | Platform: `twitch`, `youtube`, `kick`, `x`, `tiktok`, `facebook`, `instagram`, `rumble` or `system` |
| `name` | The viewer's display name |
| `text` | What they wrote |
| `kind` | `chat`, `event` (a sub, gift, raid, cheer, Super Chat or membership) or `note` (a message from CrossChat itself) |
| `color` | The name colour the platform gave the viewer, or `""` |
| `badges` | For example `["moderator", "subscriber"]`. The streamer's own lines carry `broadcaster` (Twitch, Kick) or `owner` (YouTube) |
| `emotes` | Twitch only: Twitch's own `id:from-to,…` list |
| `question` | `true` when the line looks like a question |
| `first` | `"ever"` for the viewer's first message in the channel (Twitch says so), `"stream"` for their first this stream |
| `hidden` | Why your filters hide it: `bot`, `user`, `command` or `word`. Hidden messages still arrive, so a page can show them to you; don't show them on stream |
| `alert` | For `kind: "event"`: `sub`, `resub`, `gift`, `raid`, `cheer`, `superchat`, `member` or `other` |
| `amount` | For alerts: months, number of gifts, viewers, bits or the Super Chat amount, as text (`"5 subs"`, `"$5.00"`) |
| `system` | For alerts: the platform's own line, such as `nightowl_42 subscribed for 6 months!` |
| `mid` | The platform's own message id, used for moderation |
| `uid` | The platform's user id, when it gives one |
| `handle` | X only: the viewer's `@name` |
| `test` | `true` for test events from the Theme Studio or the window |

### Other events

| `type` | Fields | When |
|---|---|---|
| `delete` | `id` | A message was removed (by a moderator, or by CrossChat on your say-so) |
| `purge` | `p`, `name` | Everything a viewer wrote was removed (a timeout or ban) |
| `clear` | | The chat was cleared |
| `hide` | `id`, `why` | Your filters now hide a message that already showed. Take it off stream |
| `status` | `status` (platform → `off`, `waiting`, `on` or `retry`), `live`, `yt`, `health` | A platform's connection changed. `health[p]` has `since`, `last` (time of the last message) and `reconnects` |
| `viewers` | `counts` (platform → number or `null`), `total` | Every 10 to 30 seconds while live |
| `feature` | `msg` (a `msg` event, or `null`) | The featured message changed |
| `emotes` | `emotes` (name → picture URL) | 7TV, BetterTTV and FrankerFaceZ emotes loaded. Show a word as a picture when it matches a name exactly |
| `theme` | `theme` | The default theme changed |
| `starred` | `ids` | Messages put aside to answer later |
| `quick` | `replies` | The quick replies changed |
| `sent` | `job_id`, `answer` (platform → `{ok, why}`) | A reply or moderation finished |
| `executor` | `present` | Whether the chat window with the extension is open (it posts to YouTube and X) |
| `twitch_auth`, `kick_auth` | `state` (`off`, `pending`, `on`, `error`), `login`, `why` | Sign-in state |
| `tts`, `filters` | `settings` | Text-to-speech or filter settings changed |
| `say`, `say_stop` | `text`, `voice`, `rate`, `volume` | Sent to the CrossChat window on this PC only: read this aloud, or stop |
| `devices`, `pair` | | Sent to pages on this PC only: paired devices and pairing codes |

## Reading

| Request | Answer |
|---|---|
| `GET /version` | `{"version": "1.4.0"}` |
| `GET /settings` | The chat widget's settings from `config.json` and the default theme |
| `GET /themes` | `{"default", "themes": [...]}` |
| `GET /themes/<name>.json` | One theme |
| `GET /targets` | Where a typed reply goes: `{"twitch", "youtube_video"}` |
| `GET /x/last` | X Live's last result |
| `GET /logs` | Chat history: `{"logs": [{"name", "started", "ended", "messages", "bytes"}]}`. This PC's own pages only |
| `GET /logs/<name>.json` | One stream's messages, with deleted ones marked `"gone": true` |
| `GET /logs/<name>.csv` | The same as a spreadsheet (UTF-8, opens in Excel). Lines starting with `= + - @` get a leading `'` so they stay text |
| `GET /logs/<name>.html` | The same as a page to read or print |

## Doing

Every `POST` answers `{"ok": true}` or `{"ok": false, "why": "…"}`.

### Replies and moderation

Replies and moderation are jobs: the answer comes at once with a `job_id`, and the outcome follows on `/events` as `sent`.

`POST /send`

```json
{"to": ["twitch", "youtube", "kick", "x"], "text": "Thanks for the raid!", "reply": {"p": "twitch", "id": "…", "mid": "…"}}
```

- `text` becomes one line. Limits: Facebook 8000 characters, Twitch and Kick 500, YouTube and Rumble 200, TikTok 150, X 140.
- Twitch and Kick replies go through their APIs and need **Connect Twitch** / **Connect Kick** in Settings. YouTube, X and TikTok replies need the chat window with the extension open (and, for TikTok, your TikTok LIVE page).
- `"dry": true` checks everything and posts nothing.

`POST /mod`

```json
{"p": "twitch", "action": "timeout", "message_id": "…", "user_id": "…", "name": "spammer", "seconds": 600, "reason": "spam"}
```

| Platform | Actions |
|---|---|
| Twitch | `delete`, `timeout`, `ban`, `unban` |
| Kick | `delete`, `timeout` (rounded up to whole minutes, 1 minute to 7 days), `ban`, `unban` |
| YouTube | `delete`, `timeout`, `ban` |

### Featured message, stars, quick replies

| Request | Body |
|---|---|
| `POST /feature` | `{"id": "<message id>"}`, or `{"id": ""}` to clear. Also `GET /feature?id=…` and `GET /feature?clear=1` from this PC, for hotkeys |
| `POST /star` | `{"id": "<message id>", "on": true}` |
| `POST /quick` | `{"replies": ["…"]}`: up to 30 lines of up to 100 characters |

### Reading chat aloud

| Request | Body |
|---|---|
| `POST /tts` | The settings: `enabled`, `read` (`all`, `questions`, `events`, `command` or `featured`), `command`, `names`, `max_chars`, `skip_links`, `platforms` (`"all"` or a list), `voice`, `rate`, `volume`. This PC only |
| `POST /tts/say` | `{"id": "<message id>"}`: read that chat message now. Only messages from the chat can be read |
| `POST /tts/skip` | Stop the current line |

The CrossChat window on this PC does the speaking, with the voices Windows and the browser have.

### Filters

`POST /filters`, this PC only:

```json
{"words": ["spoiler"], "users": ["@someone"], "bots": ["nightbot"], "hide_commands": true}
```

Each list holds up to 200 entries of up to 50 characters. Words match whole words, ignoring case. Filtered messages arrive with `hidden` set; nothing is deleted on the platform.

### Test events

`POST /test` with `{"kind": "chat"}`, `"alert"`, `"featured"` or `"viewers"` sends a made-up event, marked `"test": true`.

### This PC only

These answer only the hub's own pages on this PC:

- `/pair/start`, `/devices/revoke`;
- `/twitch/connect`, `/twitch/disconnect`;
- `/kick/connect` (answers the Kick sign-in `url` to open), `/kick/disconnect`;
- `/themes/save`, `/themes/delete`, `/themes/default`;
- `/outbox/result`, used by the extension.

`POST /rumble/connect` (`{"url"}`) and `/rumble/disconnect` set or remove the Rumble Live Stream API URL, this PC only.

`GET /tiktok/feed`, `GET /facebook/feed` and `GET /instagram/feed` are how the extension passes on your TikTok LIVE chat, Facebook Live comments and Instagram Live comments. It accepts lines only for your own TikTok name, and only from the extension or a program on this PC.

`GET /show` opens the chat window. `GET /x/go` goes live on X (`?mode=private` or `?mode=dry` for a test). Both refuse other websites.
