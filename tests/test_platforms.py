import hub


def test_irc_tags_unescape():
    assert hub.irc_tags(r"display-name=A\sB;system-msg=x\:y;emotes=") == {"display-name": "A B", "system-msg": "x;y", "emotes": ""}


def test_twitch_notices_become_alerts():
    assert hub.twitch_notice({"msg-id": "sub"}) == ("sub", "")
    assert hub.twitch_notice({"msg-id": "resub", "msg-param-cumulative-months": "6"}) == ("resub", "6")
    assert hub.twitch_notice({"msg-id": "submysterygift", "msg-param-mass-gift-count": "5"}) == ("gift", "5 subs")
    assert hub.twitch_notice({"msg-id": "subgift"}) == ("gift", "a sub")
    assert hub.twitch_notice({"msg-id": "raid", "msg-param-viewerCount": "37"}) == ("raid", "37")
    assert hub.twitch_notice({"msg-id": "announcement"}) == ("other", "")


def test_kick_events_become_alerts():
    assert hub.kick_alert(r"App\Events\GiftedSubscriptionsEvent", {"gifter_username": "a", "gifted_usernames": ["b"]}) == \
        ("a", "a gifted 1 sub", "gift", "a sub")
    assert hub.kick_alert(r"App\Events\StreamHostEvent", {"host_username": "r", "number_viewers": 12})[2:] == ("raid", "12")
    assert hub.kick_alert(r"App\Events\SubscriptionEvent", {"username": "s", "months": 3})[2:] == ("resub", "3")
    assert hub.kick_alert(r"App\Events\SubscriptionEvent", {"username": "s"})[1:] == ("s subscribed", "sub", "")


class _Reply:
    def __init__(self, body):
        self.body = body

    def json(self):
        if isinstance(self.body, Exception):
            raise self.body
        return self.body


def test_kick_feed_asks_kick_for_its_current_pusher_key(monkeypatch):
    asked = []

    def post(url, **kw):
        asked.append((url, kw["json"]))
        return _Reply({"data": {"mode": "websocket", "connections": [
            {"provider": "pusher", "credentials": {"app_key": "0123456789abcdef0123", "cluster": "eu"}}]}})
    monkeypatch.setattr(hub.requests, "post", post)
    assert hub.kick_feed(42) == "wss://ws-eu.pusher.com/app/0123456789abcdef0123?protocol=7&client=js&version=8.4.0&flash=false"
    url, body = asked[0]
    assert url == "https://web.kick.com/api/v1/realtime/channels/42/chat/connection"
    assert body["capabilities"] == {"accepted_providers": [{"provider": "pusher"}]}       # only the feed CrossChat reads
    assert body["client"]["type"] == "web" and len(body["client"]["id"]) == 36            # a random id, nothing about you


def test_kick_feed_keeps_the_last_known_key_when_kick_says_nothing_usable(monkeypatch):
    known = "wss://ws-%s.pusher.com/app/%s?protocol=7&client=js&version=8.4.0&flash=false" % (hub.KICK_PUSHER[1], hub.KICK_PUSHER[0])
    for body in ({"data": {"connections": [{"provider": "centrifugo", "credentials": {"url": "wss://elsewhere"}}]}},
                 {"data": {"connections": [{"provider": "pusher", "credentials": {"app_key": "not a key!", "cluster": "us2"}}]}},
                 {"data": {"connections": [{"provider": "pusher", "credentials": {"app_key": "0123456789abcdef0123",
                                                                                  "cluster": "us2.evil.example/x"}}]}},
                 {"message": "Not Found"}, ValueError("not json")):
        monkeypatch.setattr(hub.requests, "post", lambda url, body=body, **kw: _Reply(body))
        assert hub.kick_feed(42) == known

    def offline(url, **kw):
        raise hub.requests.ConnectionError("offline")
    monkeypatch.setattr(hub.requests, "post", offline)
    assert hub.kick_feed(42) == known
    assert hub.kick_feed(0) == known                    # no channel number: nothing is asked


def runs(text):
    return {"runs": [{"text": text}]}


def test_youtube_poll_reads_chat_and_alerts(monkeypatch):
    actions = [
        {"addChatItemAction": {"item": {"liveChatTextMessageRenderer": {"id": "1", "authorName": {"simpleText": "Ann"}, "message": runs("hi"),
                                                                        "timestampUsec": "1000000"}}}},
        {"addChatItemAction": {"item": {"liveChatPaidMessageRenderer": {"id": "2", "authorName": {"simpleText": "Bo"}, "message": runs("gg"),
                                                                        "purchaseAmountText": {"simpleText": "$5.00"}}}}},
        {"addChatItemAction": {"item": {"liveChatMembershipItemRenderer": {"id": "3", "authorName": {"simpleText": "Cy"},
                                                                           "headerSubtext": runs("Welcome to Members")}}}},
        {"addChatItemAction": {"item": {"liveChatSponsorshipsGiftPurchaseAnnouncementRenderer": {"id": "4", "header": {
            "liveChatSponsorshipsHeaderRenderer": {"authorName": {"simpleText": "Di"}, "primaryText": runs("Gifted 5 memberships")}}}}}},
        {"addChatItemAction": {"item": {"liveChatViewerEngagementMessageRenderer": {"id": "5"}}}},
        {"markChatItemAsDeletedAction": {"targetItemId": "1"}},
    ]

    class Reply:
        def json(self):
            return {"continuationContents": {"liveChatContinuation": {
                "continuations": [{"timedContinuationData": {"continuation": "next", "timeoutMs": 3000}}], "actions": actions}}}

    monkeypatch.setattr(hub.web, "post", lambda *a, **k: Reply())
    chat = {"key": "k", "version": "v", "token": "t"}
    events, wait = hub.yt_poll(chat)
    assert chat["token"] == "next" and wait == 3
    by_id = {e["id"]: e for e in events if e["type"] == "msg"}
    assert by_id["yt-1"]["kind"] == "chat" and by_id["yt-1"]["text"] == "hi" and "alert" not in by_id["yt-1"]
    assert (by_id["yt-2"]["alert"], by_id["yt-2"]["amount"], by_id["yt-2"]["text"], by_id["yt-2"]["system"]) == \
        ("superchat", "$5.00", "gg", "Super Chat $5.00")                  # text: only what the viewer said
    assert (by_id["yt-3"]["alert"], by_id["yt-3"]["text"], by_id["yt-3"]["system"]) == ("member", "", "Welcome to Members")
    assert (by_id["yt-4"]["alert"], by_id["yt-4"]["name"], by_id["yt-4"]["amount"], by_id["yt-4"]["system"]) == \
        ("gift", "Di", "5 memberships", "Gifted 5 memberships")
    assert "yt-5" not in by_id                          # kinds CrossChat doesn't show are left out
    assert {"type": "delete", "id": "yt-1"} in events


def test_page_json_and_text():
    assert hub.page_json('x = 1; var ytInitialData = {"a": {"b": 2}};</script>', "ytInitialData") == {"a": {"b": 2}}
    assert hub.page_json("nothing here", "ytInitialData") is None
    assert hub.yt_text({"runs": [{"text": "hi "}, {"emoji": {"emojiId": "😀"}}, {"emoji": {"isCustomEmoji": True, "shortcuts": [":yt:"]}}]}) \
        == "hi 😀:yt:"
