import importlib.util
import json
import os
from datetime import datetime, timezone
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from aiogram.types import Chat, Message, Update, User


# Import the real handlers without loading production credentials or polling.
with patch.dict(os.environ, {
    "BOT_TOKEN": "123456:TEST_ONLY",
    "PLAYERS": "1:Alice,2:Bob", "CHAT_ID": "-100123", "ADMIN_IDS": "",
}), patch("dotenv.load_dotenv"):
    spec = importlib.util.spec_from_file_location("tested_bot", Path(__file__).parents[1] / "bot.py")
    bot = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bot)


class ChatMessage:
    def __init__(self, user_id=1):
        self.from_user = SimpleNamespace(id=user_id)
        self.chat = SimpleNamespace(id=-100123)
        self.answers = []

    async def answer(self, text, **kwargs):
        self.answers.append(text)

    async def delete(self):
        pass


def command(args=None):
    return SimpleNamespace(args=args)


def episode(closed=False):
    return {
        "id": 1, "name": "Round 1", "slots": ["1 место"], "bet_total": 100,
        "bets": {"Alice": [{"slot": "1 место", "pair": "Winner", "amount": 100}], "Bob": []},
        "bets_locked": closed, "closed": closed, "results": ["Winner"] if closed else [],
    }


class BotTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.state_path = Path(self.tmp.name) / "data.json"
        patcher = patch.object(bot, "DATA_FILE", str(self.state_path))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.write({"episodes": [], "scores": {"Alice": 0, "Bob": 0}})

    def write(self, state):
        self.state_path.write_text(json.dumps(state))

    def read(self):
        return json.loads(self.state_path.read_text())

    def special(self, kind, locked=False):
        d = self.read()
        d[kind] = {"amount": 500 if kind == "final" else 300,
                   "bets": {"Alice": "Winner", "Bob": "Other"}, "locked": locked}
        if kind == "final":
            d[kind].update(winner=None, resolved=False)
        self.write(d)

    async def test_winning_personal_history_renders_without_parsing_display_text(self):
        self.write({"episodes": [episode(True)], "scores": {"Alice": 100, "Bob": 0}})
        m = ChatMessage()
        await bot.cmd_myresult(m)
        self.assertIn("✅", "\n".join(m.answers))
        self.assertIn("+100", "\n".join(m.answers))

    async def test_winning_round_history_renders(self):
        self.write({"episodes": [episode(True)], "scores": {"Alice": 100, "Bob": 0}})
        m = ChatMessage()
        await bot.cmd_history(m, command("1"))
        self.assertIn("✅", "\n".join(m.answers))

    async def test_open_history_does_not_expose_any_player_pick(self):
        self.write({"episodes": [episode()], "scores": {"Alice": 0, "Bob": 0}})
        m = ChatMessage(user_id=2)
        await bot.cmd_history(m, command("1"))
        self.assertNotIn("Winner", "\n".join(m.answers))
        self.assertEqual(self.read()["scores"], {"Alice": 0, "Bob": 0})

    async def test_frozen_history_can_reveal_picks(self):
        d = self.read(); e = episode(); e["bets_locked"] = True
        d["episodes"] = [e]; self.write(d)
        m = ChatMessage()
        await bot.cmd_history(m, command("1"))
        self.assertIn("Winner", "\n".join(m.answers))

    async def test_empty_result_never_changes_state(self):
        self.write({"episodes": [episode()], "scores": {"Alice": 0, "Bob": 0}})
        before = self.state_path.read_bytes()
        await bot.cmd_result(ChatMessage(), command())
        self.assertEqual(self.state_path.read_bytes(), before)

    async def test_blank_result_never_changes_state(self):
        self.write({"episodes": [episode()], "scores": {"Alice": 0, "Bob": 0}})
        before = self.state_path.read_bytes()
        await bot.cmd_result(ChatMessage(), command("   "))
        self.assertEqual(self.state_path.read_bytes(), before)

    async def test_generic_stop_closes_final(self):
        self.special("final")
        await bot.cmd_stopbet(ChatMessage())
        self.assertTrue(self.read()["final"]["locked"])

    async def test_generic_stop_closes_elimination(self):
        self.special("elim")
        await bot.cmd_stopbet(ChatMessage())
        self.assertTrue(self.read()["elim"]["locked"])

    async def test_stop_warns_once_before_closing_when_player_is_missing(self):
        self.write({"episodes": [episode()], "scores": {"Alice": 0, "Bob": 0}})
        await bot.cmd_stopbet(ChatMessage())
        self.assertFalse(self.read()["episodes"][0]["bets_locked"])
        await bot.cmd_stopbet(ChatMessage())
        self.assertTrue(self.read()["episodes"][0]["bets_locked"])

    async def test_generic_result_settles_final_only_once(self):
        self.special("final", locked=True)
        await bot.cmd_result(ChatMessage(), command("Winner"))
        d = self.read()
        self.assertEqual(d["scores"], {"Alice": 500, "Bob": 0})
        self.assertTrue(d["final"]["resolved"])
        await bot.cmd_result(ChatMessage(), command("Winner"))
        self.assertEqual(self.read(), d)

    async def test_elimination_history_survives_next_bet_and_duplicate_result(self):
        self.special("elim", locked=True)
        await bot.cmd_result(ChatMessage(), command("Winner, Other"))
        first = self.read()
        self.assertEqual(first["scores"], {"Alice": 300, "Bob": 300})
        self.assertEqual(first["elim_history"][0]["bets"], {"Alice": "Winner", "Bob": "Other"})
        self.assertEqual(first["elim_history"][0]["results"], ["Winner", "Other"])
        await bot.cmd_result(ChatMessage(), command("Winner, Other"))
        self.assertEqual(self.read(), first)
        await bot.cmd_elim(ChatMessage(), command("Next"))
        self.assertEqual(self.read()["elim_history"], first["elim_history"])

    async def test_new_round_cannot_overlap_elimination(self):
        self.special("elim")
        before = self.read()
        await bot.cmd_newbet(ChatMessage(), command("1 место"))
        self.assertEqual(self.read(), before)

    async def test_final_cannot_overlap_round(self):
        d = self.read(); d["episodes"] = [episode()]; self.write(d)
        before = self.read()
        await bot.cmd_final(ChatMessage(), command("Winner"))
        self.assertEqual(self.read(), before)

    async def test_elimination_cannot_overlap_final(self):
        self.special("final")
        before = self.read()
        await bot.cmd_elim(ChatMessage(), command("Winner"))
        self.assertEqual(self.read(), before)

    async def test_legacy_parallel_state_is_never_settled_by_guessing(self):
        d = self.read(); d["episodes"] = [episode()]; self.write(d)
        self.special("final")
        before = self.read()
        await bot.cmd_result(ChatMessage(), command("Winner"))
        self.assertEqual(self.read(), before)

    async def test_me_shows_own_special_pick_and_never_another_players_pick(self):
        self.special("elim")
        m = ChatMessage()
        await bot.cmd_mybets(m)
        output = "\n".join(m.answers)
        self.assertIn("Winner", output)
        self.assertNotIn("Other", output)

    async def test_cancel_handles_special_bet_without_erasing_its_history(self):
        self.special("elim")
        d = self.read(); d["elim_history"] = [{"id": 1, "bets": {"Alice": "Old"}}]; self.write(d)
        await bot.cmd_cancel(ChatMessage())
        d = self.read()
        self.assertFalse(d.get("elim", {}).get("bets"))
        self.assertEqual(d["elim_history"], [{"id": 1, "bets": {"Alice": "Old"}}])

    async def test_complete_game_round_elimination_final_has_hand_checked_scores(self):
        await bot.cmd_newbet(ChatMessage(), command("Trial: 1 место"))
        await bot.cmd_bet(ChatMessage(), command("Winner 100"))
        await bot.cmd_bet(ChatMessage(2), command("Other 100"))
        await bot.cmd_stopbet(ChatMessage())
        await bot.cmd_result(ChatMessage(), command("Winner"))
        self.assertEqual(self.read()["scores"], {"Alice": 100, "Bob": 0})
        await bot.cmd_elim(ChatMessage(), command("Winner"))
        await bot.cmd_elim(ChatMessage(2), command("Other"))
        await bot.cmd_stopbet(ChatMessage())
        await bot.cmd_result(ChatMessage(), command("Winner, Other"))
        self.assertEqual(self.read()["scores"], {"Alice": 400, "Bob": 300})
        await bot.cmd_final(ChatMessage(), command("Winner"))
        await bot.cmd_final(ChatMessage(2), command("Other"))
        await bot.cmd_stopbet(ChatMessage())
        await bot.cmd_result(ChatMessage(), command("Winner"))
        self.assertEqual(self.read()["scores"], {"Alice": 900, "Bob": 300})
        m = ChatMessage()
        await bot.cmd_myresult(m)
        output = "\n".join(m.answers)
        self.assertIn("900", output)
        self.assertIn("Вылет #1", output)
        self.assertIn("Финал", output)

    async def test_grouped_result_with_empty_slots_preserves_existing_rules(self):
        await bot.cmd_newbet(ChatMessage(), command("1 место, 2–3 место, 4–5 место"))
        await bot.cmd_bet(ChatMessage(), command("First 100, Second 150, Third 50"))
        await bot.cmd_result(ChatMessage(), command("; ; Third, Fourth"))
        self.assertEqual(self.read()["scores"], {"Alice": 50, "Bob": 0})

    async def test_malformed_grouped_result_does_not_freeze_or_score(self):
        d = self.read(); d["episodes"] = [episode()]; self.write(d)
        before = self.state_path.read_bytes()
        await bot.cmd_result(ChatMessage(), command("Winner; Other"))
        self.assertEqual(self.state_path.read_bytes(), before)

    async def test_elimination_details_are_accessible_in_both_histories(self):
        self.special("elim")
        await bot.cmd_result(ChatMessage(), command("Winner"))
        for handler, args in ((bot.cmd_history, (command("e1"),)), (bot.cmd_myresult, ())):
            m = ChatMessage()
            await handler(m, *args)
            output = "\n".join(m.answers)
            self.assertIn("Winner", output)
            self.assertIn("+300", output)

    async def test_special_lookup_without_name_is_read_only_and_personal(self):
        self.special("final")
        before = self.state_path.read_bytes()
        m = ChatMessage()
        await bot.cmd_final(m, command())
        self.assertEqual(self.state_path.read_bytes(), before)
        self.assertIn("Winner", "\n".join(m.answers))
        self.assertNotIn("Other", "\n".join(m.answers))

    async def test_status_reveals_special_picks_only_after_locking(self):
        self.special("elim")
        m = ChatMessage()
        await bot.cmd_status(m)
        self.assertNotIn("Winner", "\n".join(m.answers))
        await bot.cmd_stopbet(ChatMessage())
        m = ChatMessage()
        await bot.cmd_status(m)
        self.assertIn("Winner", "\n".join(m.answers))

    async def test_personal_history_is_split_before_telegram_message_limit(self):
        d = self.read()
        for number in range(100):
            e = episode(True); e.update(id=number + 1, name=f"Round {number + 1}")
            d["episodes"].append(e)
        self.write(d)
        m = ChatMessage()
        await bot.cmd_myresult(m)
        self.assertGreater(len(m.answers), 1)
        self.assertTrue(all(len(text) <= 3500 for text in m.answers))
        self.assertIn("Round 100", "\n".join(m.answers))

    async def test_short_commands_dispatch_and_retired_commands_do_not(self):
        async def send(text, number):
            update = Update(update_id=number, message=Message(
                message_id=number, date=datetime(2026, 10, 16, tzinfo=timezone.utc),
                chat=Chat(id=-100123, type="group"),
                from_user=User(id=1, first_name="Alice", is_bot=False), text=text,
            ))
            await bot.dp.feed_update(bot.bot, update)

        with patch.object(Message, "answer", new_callable=AsyncMock) as reply, \
                patch.object(Message, "delete", new_callable=AsyncMock):
            for n, text in enumerate(("/newbet 1 место", "/bet Winner 100", "/stopbet",
                                      "/stopbet", "/result Winner", "/me", "/mehistory"), 1):
                await send(text, n)
            self.assertEqual(self.read()["scores"], {"Alice": 100, "Bob": 0})
            self.assertIn("+100", reply.await_args.args[0])
            replies_before = reply.await_count
            for n, name in enumerate(("finalstop", "elimstop", "finalresult", "elimresult",
                                      "finalstatus", "elimstatus", "mybets", "myresult", "stats"), 20):
                await send(f"/{name}", n)
            self.assertEqual(reply.await_count, replies_before)

    async def test_chat_restriction_still_ignores_other_chats(self):
        update = Update(update_id=99, message=Message(
            message_id=99, date=datetime(2026, 10, 16, tzinfo=timezone.utc),
            chat=Chat(id=-999, type="group"),
            from_user=User(id=1, first_name="Alice", is_bot=False), text="/newbet 1 место",
        ))
        before = self.state_path.read_bytes()
        with patch.object(Message, "answer", new_callable=AsyncMock) as reply:
            await bot.dp.feed_update(bot.bot, update)
            self.assertEqual(self.state_path.read_bytes(), before)
            self.assertEqual(reply.await_count, 0)


if __name__ == "__main__":
    unittest.main()
