"""Staying up: a message CrossChat can't read is skipped, and a job that fails on something unexpected starts again."""
import asyncio

import hub


class FakeReader:
    def __init__(self, lines):
        self.lines = [line.encode() + b"\r\n" for line in lines]

    async def readline(self):
        if self.lines:
            return self.lines.pop(0)
        await asyncio.sleep(3600)                  # then quiet, like a chat with nobody talking


class FakeWriter:
    def write(self, data):
        pass

    async def drain(self):
        pass

    def close(self):
        pass


def test_one_unreadable_twitch_line_is_skipped(home, monkeypatch):
    home()
    lines = [":tmi.twitch.tv 366 justinfan1 #chan :End of /NAMES list",
             "@badges=;display-name=Bad;id=b1 :bad!bad@bad.tmi.twitch.tv PRIVMSG #chan :this one breaks",
             "@badges=;display-name=Good;id=g1 :good!good@good.tmi.twitch.tv PRIVMSG #chan :still here"]

    async def connection(*args, **kwargs):
        return FakeReader(lines), FakeWriter()

    real_tags = hub.irc_tags

    def tags(raw):
        if "Bad" in raw:
            raise ValueError("a format CrossChat has never seen")
        return real_tags(raw)

    monkeypatch.setattr(hub.asyncio, "open_connection", connection)
    monkeypatch.setattr(hub, "irc_tags", tags)
    hub.skipped.seen.clear()

    async def run():
        task = asyncio.create_task(hub.twitch("chan"))
        await asyncio.sleep(0.2)
        task.cancel()
    asyncio.run(run())
    said = [m["text"] for m in hub.messages if m["p"] == "twitch"]
    assert said == ["still here"] and hub.status["twitch"] == "on"          # same connection, nothing dropped
    assert hub.health["twitch"]["reconnects"] == 0


def test_a_job_that_fails_starts_again(home, monkeypatch):
    home()
    runs = []

    async def job():
        runs.append(1)
        if len(runs) < 3:
            raise KeyError("platform changed something")
        return "done"

    async def no_wait(seconds):
        pass

    monkeypatch.setattr(hub.asyncio, "sleep", no_wait)
    assert asyncio.run(hub.keep_running("twitch", job)) == "done" and len(runs) == 3
    assert hub.status["twitch"] == "retry"
