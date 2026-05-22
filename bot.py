import json
import os
import re
from typing import Any, Awaitable, Callable
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, BaseMiddleware
from aiogram.types import Message
from aiogram.filters import CommandStart, Command
import asyncio

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не задан в .env")


def _parse_player_ids():
    raw = os.getenv("PLAYERS", "")
    result = {}
    for entry in raw.split(","):
        entry = entry.strip()
        if ":" in entry:
            uid_str, name = entry.split(":", 1)
            result[int(uid_str.strip())] = name.strip()
    return result


PLAYER_IDS = _parse_player_ids()
PLAYERS = list(PLAYER_IDS.values())
PLAYER_IDS_BY_NAME = {v: k for k, v in PLAYER_IDS.items()}

_chat_id_raw = os.getenv("CHAT_ID", "").strip()
ALLOWED_CHAT_ID = int(_chat_id_raw) if _chat_id_raw else None


class ChatFilterMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Message, dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: dict[str, Any],
    ) -> Any:
        if ALLOWED_CHAT_ID and event.chat.id != ALLOWED_CHAT_ID:
            return None
        return await handler(event, data)


bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
dp.message.middleware(ChatFilterMiddleware())

DATA_FILE = "data.json"


def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE) as f:
            return json.load(f)
    return {"episodes": [], "scores": {p: 0 for p in PLAYERS}}


def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def find_player(user_id):
    return PLAYER_IDS.get(user_id)


def fuzzy_match(bet_name, result_name):
    a = bet_name.lower().strip()
    b = result_name.lower().strip()
    return a[:3] == b[:3] or a in b or b in a


def slot_positions(slot_label, slot_index=None):
    """Извлекает номера мест из метки слота: '1 место' → [1], '2–3 место' → [2, 3].
    Если цифр нет — использует порядковый номер слота как позицию."""
    nums = [int(n) for n in re.findall(r'\d+', slot_label)]
    if not nums and slot_index is not None:
        return [slot_index + 1]
    return nums


def get_current_episode(data):
    if data["episodes"]:
        return data["episodes"][-1]
    return None


@dp.message(Command("chatid"))
async def cmd_chatid(message: Message):
    await message.answer(f"Chat ID: <code>{message.chat.id}</code>", parse_mode="HTML")


@dp.message(CommandStart())
async def cmd_start(message: Message):
    await message.answer(
        "Привет! Это бот для игры «Ставка на любовь».\n\n"
        "Используй /help для списка команд."
    )


@dp.message(Command("help"))
async def cmd_help(message: Message):
    help_text = (
        "<b>🎬 Ведущий</b>\n"
        "/newbet — открыть раунд\n"
        "  <code>/newbet 1 место, 2–3 место, 4–5 место</code>\n"
        "  <code>/newbet Серия 5: 1 место, 2–3 место</code>\n"
        "  <code>/newbet Испытание: выживший</code>  ← 1 слот = испытание\n\n"
        "/stopbet — закрыть приём ставок\n\n"
        "/result — ввести результаты\n"
        "  <code>/result хилькевич, ершов, башаров, олимпиец, стогниенко</code>\n\n"
        "/cancel — отменить текущий раунд\n\n"
        "<b>🎯 Игроки</b>\n"
        "/bet — сделать ставку (ровно 300 очков)\n"
        "  <code>/bet хилькевич 100, олимпийцы 150, ершов 50</code>\n"
        "  При испытании: <code>/bet хилькевич 300</code>\n\n"
        "/mybets — мои ставки в текущем раунде\n"
        "/myresult — мои итоги по всем раундам\n\n"
        "<b>📊 Просмотр</b>\n"
        "/scores — таблица очков\n"
        "/status — статус текущего раунда\n"
        "/history — история раундов"
    )
    await message.answer(help_text, parse_mode="HTML")


@dp.message(Command("newbet"))
async def cmd_newbet(message: Message):
    data = load_data()

    ep = get_current_episode(data)
    if ep and not ep["closed"]:
        await message.answer("❌ Есть незакрытый раунд! Сначала /result или /cancel.")
        return

    text = message.text.replace("/newbet", "").strip()
    if not text:
        await message.answer(
            "Формат: /newbet 1 место, 2 место, 5 место\n"
            "Или с названием: /newbet Серия 5: 1 место, 2 место, 5 место"
        )
        return

    if ":" in text:
        ep_name, slots_text = text.split(":", 1)
        ep_name = ep_name.strip()
    else:
        ep_name = f"Раунд {len(data['episodes']) + 1}"
        slots_text = text

    slots = [s.strip() for s in slots_text.split(",") if s.strip()]
    if not slots:
        await message.answer("❌ Не указаны слоты для ставок!")
        return

    episode = {
        "id": len(data["episodes"]) + 1,
        "name": ep_name,
        "slots": slots,
        "bets": {p: [] for p in PLAYERS},
        "bets_locked": False,
        "results": [],
        "closed": False
    }

    data["episodes"].append(episode)
    save_data(data)

    slots_display = ", ".join(slots)
    await message.answer(
        f"✅ {ep_name} открыт!\n\n"
        f"Ставки на: {slots_display}\n\n"
        f"Формат: /bet пара1 сумма1, пара2 сумма2, ...\n"
        f"Всего нужно поставить ровно 300 очков."
    )


@dp.message(Command("bet"))
async def cmd_bet(message: Message):
    data = load_data()
    ep = get_current_episode(data)

    if not ep:
        await message.answer("❌ Нет активного раунда!")
        return

    if ep["closed"]:
        await message.answer("❌ Раунд уже закрыт!")
        return

    if ep.get("bets_locked"):
        await message.answer("🔒 Приём ставок закрыт!")
        return

    player = find_player(message.from_user.id)
    if not player:
        await message.answer("❌ Ты не в списке игроков!")
        return

    bets_text = message.text.replace("/bet", "").strip()
    if not bets_text:
        await message.answer("Формат: /bet пара1 сумма1, пара2 сумма2, ...")
        return

    # Принимаем запятую, | и перенос строки как разделитель
    normalized = re.sub(r'[|\n]+', ',', bets_text)
    bet_entries = [b.strip() for b in normalized.split(",") if b.strip()]
    slots = ep["slots"]

    if len(bet_entries) != len(slots):
        await message.answer(
            f"❌ Нужно ровно {len(slots)} ставок ({', '.join(slots)}), "
            f"а у тебя {len(bet_entries)}."
        )
        return

    total_amount = 0
    new_bets = []

    for slot_idx, entry in enumerate(bet_entries):
        parts = entry.rsplit(" ", 1)
        if len(parts) != 2:
            await message.answer(f"❌ Неверный формат: '{entry}'\nОжидается: название сумма")
            return

        pair_name, amount_str = parts

        try:
            amount = int(amount_str)
        except ValueError:
            await message.answer(f"❌ '{amount_str}' не число!")
            return

        if amount <= 0:
            await message.answer("❌ Сумма ставки должна быть больше 0!")
            return

        if amount > 200 and len(slots) > 1:
            await message.answer("❌ Ставка не может быть больше 200 очков!")
            return

        total_amount += amount
        new_bets.append({
            "slot": slots[slot_idx],
            "pair": pair_name.strip(),
            "amount": amount
        })

    if total_amount != 300:
        diff = 300 - total_amount
        hint = f"не хватает {diff}" if diff > 0 else f"лишних {-diff}"
        await message.answer(
            f"❌ Сумма должна быть ровно 300! У тебя {total_amount} ({hint} очков)."
        )
        return

    used_pairs = [b["pair"].lower() for b in new_bets]
    if len(used_pairs) != len(set(used_pairs)):
        await message.answer("❌ Нельзя ставить на одну пару в нескольких слотах!")
        return

    ep["bets"][player] = new_bets
    save_data(data)

    bets_display = "\n".join([f"  {b['slot']}: {b['pair']} ({b['amount']})" for b in new_bets])
    await message.answer(f"✅ {player}, ставка принята!\n{bets_display}")


@dp.message(Command("stopbet"))
async def cmd_stopbet(message: Message):
    data = load_data()
    ep = get_current_episode(data)

    if not ep:
        await message.answer("❌ Нет активного раунда!")
        return

    if ep["closed"]:
        await message.answer("❌ Раунд уже закрыт!")
        return

    if ep.get("bets_locked"):
        await message.answer("⚠️ Ставки уже заморожены!")
        return

    not_bet = [p for p in PLAYERS if not ep["bets"][p]]

    if not_bet and not ep.get("stopbet_warned"):
        ep["stopbet_warned"] = True
        save_data(data)
        tags = " ".join(
            f'<a href="tg://user?id={PLAYER_IDS_BY_NAME[p]}">{p}</a>'
            for p in not_bet
        )
        await message.answer(
            f"⚠️ Не все сделали ставки: {tags}\n\n"
            f"Введи /stopbet ещё раз чтобы всё равно закрыть приём ставок.",
            parse_mode="HTML"
        )
        return

    ep["bets_locked"] = True
    save_data(data)

    if not_bet:
        tags = " ".join(
            f'<a href="tg://user?id={PLAYER_IDS_BY_NAME[p]}">{p}</a>'
            for p in not_bet
        )
        await message.answer(
            f"🔒 Приём ставок закрыт!\n\n⚠️ Без ставок: {tags}",
            parse_mode="HTML"
        )
    else:
        await message.answer("🔒 Приём ставок закрыт! ✅ Все поставили.")


@dp.message(Command("result"))
async def cmd_result(message: Message):
    data = load_data()
    ep = get_current_episode(data)

    if not ep:
        await message.answer("❌ Нет активного раунда!")
        return

    if ep["closed"]:
        await message.answer("❌ Раунд уже закрыт!")
        return

    result_text = message.text.replace("/result", "").strip()
    if not result_text:
        await message.answer(
            "Формат: /result 1й, 2й, 3й, 4й, 5й\n"
            "(перечисли всех в порядке мест — бот сам посчитает ставки)"
        )
        return

    results = [r.strip() for r in result_text.split(",")]

    round_scores = {p: 0 for p in PLAYERS}
    win_details = {p: [] for p in PLAYERS}

    for player in PLAYERS:
        for bet in ep["bets"][player]:
            slot_idx = ep["slots"].index(bet["slot"]) if bet["slot"] in ep["slots"] else None
            positions = slot_positions(bet["slot"], slot_idx)
            for pos in positions:
                if 1 <= pos <= len(results):
                    if fuzzy_match(bet["pair"], results[pos - 1]):
                        round_scores[player] += bet["amount"]
                        win_details[player].append(f"{results[pos-1]} ({bet['slot']}) +{bet['amount']}")
                        break
        data["scores"][player] += round_scores[player]

    ep["results"] = results
    ep["closed"] = True
    save_data(data)

    results_display = "\n".join([f"  {i+1}. {r}" for i, r in enumerate(results)])

    player_lines = []
    for p in PLAYERS:
        wins = ", ".join(win_details[p]) if win_details[p] else "—"
        player_lines.append(f"  {p}: +{round_scores[p]}  ({wins})")
    players_display = "\n".join(player_lines)

    scores_sorted = sorted(
        [(p, data["scores"][p]) for p in PLAYERS],
        key=lambda x: x[1], reverse=True
    )
    scores_display = "\n".join([f"  {i+1}. {p}: {s}" for i, (p, s) in enumerate(scores_sorted)])

    await message.answer(
        f"✅ Результаты {ep['name']}:\n{results_display}\n\n"
        f"Очки за раунд:\n{players_display}\n\n"
        f"🏆 Общий счёт:\n{scores_display}"
    )


@dp.message(Command("myresult"))
async def cmd_myresult(message: Message):
    data = load_data()

    player = find_player(message.from_user.id)
    if not player:
        await message.answer("❌ Ты не в списке игроков!")
        return

    closed = [ep for ep in data["episodes"] if ep["closed"] and ep.get("results")]
    if not closed:
        await message.answer("❌ Нет завершённых раундов!")
        return

    lines = [f"📊 Результаты {player}:\n"]
    total = 0

    for ep in closed:
        lines.append(f"▸ {ep['name']}")
        player_bets = ep["bets"].get(player, [])
        if not player_bets:
            lines.append("  Ставок не было\n")
            continue

        ep_total = 0
        for bet in player_bets:
            slot_idx = ep["slots"].index(bet["slot"]) if bet["slot"] in ep.get("slots", []) else None
            positions = slot_positions(bet["slot"], slot_idx)
            won = False
            for pos in positions:
                if 1 <= pos <= len(ep["results"]):
                    if fuzzy_match(bet["pair"], ep["results"][pos - 1]):
                        won = True
                        break
            if won:
                lines.append(f"  ✅ {bet['slot']}: {bet['pair']} +{bet['amount']}")
                ep_total += bet["amount"]
            else:
                lines.append(f"  ❌ {bet['slot']}: {bet['pair']} 0")
        lines.append(f"  Итого: +{ep_total}\n")
        total += ep_total

    lines.append(f"🏆 Всего: {data['scores'].get(player, 0)}")
    await message.answer("\n".join(lines))


@dp.message(Command("mybets"))
async def cmd_mybets(message: Message):
    data = load_data()
    ep = get_current_episode(data)

    if not ep:
        await message.answer("❌ Нет активного раунда!")
        return

    player = find_player(message.from_user.id)
    if not player:
        await message.answer("❌ Ты не в списке игроков!")
        return

    bets = ep["bets"][player]
    if not bets:
        await message.answer(f"{player}, ты ещё не делал ставок в этом раунде.")
        return

    bets_display = "\n".join([f"  {b['slot']}: {b['pair']} ({b['amount']})" for b in bets])
    total = sum(b["amount"] for b in bets)
    await message.answer(f"Ставки {player} (всего {total}):\n{bets_display}")


@dp.message(Command("status"))
async def cmd_status(message: Message):
    data = load_data()
    ep = get_current_episode(data)

    if not ep:
        await message.answer("❌ Нет активного раунда!")
        return

    if ep["closed"]:
        status = "🔒 ЗАКРЫТ"
    elif ep.get("bets_locked"):
        status = "🟡 СТАВКИ ЗАМОРОЖЕНЫ"
    else:
        status = "🟢 ОТКРЫТ"

    slots_display = ", ".join(ep.get("slots", []))

    bets_text = "\n".join([
        f"  {p}: {'✅' if ep['bets'][p] else '⏳'}"
        for p in PLAYERS
    ])

    msg = f"📊 {ep['name']} [{status}]\n\nСлоты: {slots_display}\n\nСтавки:\n{bets_text}"

    if ep["results"]:
        results_text = "\n".join([f"  {i+1}. {r}" for i, r in enumerate(ep["results"])])
        msg += f"\n\nРезультаты:\n{results_text}"

    await message.answer(msg)


@dp.message(Command("scores"))
async def cmd_scores(message: Message):
    data = load_data()

    scores = [(p, data["scores"][p]) for p in PLAYERS]
    scores.sort(key=lambda x: x[1], reverse=True)

    scores_text = "\n".join([f"  {i+1}. {p}: {s}" for i, (p, s) in enumerate(scores)])
    await message.answer(f"🏆 Общий счёт:\n{scores_text}")


@dp.message(Command("cancel"))
async def cmd_cancel(message: Message):
    data = load_data()
    ep = get_current_episode(data)

    if not ep:
        await message.answer("❌ Нет активного раунда!")
        return

    if ep["closed"]:
        await message.answer("❌ Раунд уже закрыт!")
        return

    ep["bets"] = {p: [] for p in PLAYERS}
    ep["bets_locked"] = False
    ep["results"] = []
    ep.pop("stopbet_warned", None)
    save_data(data)

    await message.answer("✅ Раунд отменён. Все ставки очищены.")


@dp.message(Command("history"))
async def cmd_history(message: Message):
    data = load_data()

    if not data["episodes"]:
        await message.answer("❌ История пуста!")
        return

    history_lines = []
    for ep in data["episodes"]:
        status = "✅" if ep["closed"] else "🔄"
        history_lines.append(f"{status} {ep['name']} (ID: {ep['id']})")

    history_text = "\n".join(history_lines)
    await message.answer(f"📜 История раундов:\n{history_text}")


async def main():
    print("🤖 Бот запущен...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
