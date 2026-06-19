import json
import os
import re
from typing import Any, Awaitable, Callable
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, BaseMiddleware
from aiogram.types import Message
from aiogram.filters import CommandStart, Command
from aiogram.filters.command import CommandObject
import asyncio

load_dotenv(override=True)

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

ADMIN_IDS = {
    int(x.strip())
    for x in os.getenv("ADMIN_IDS", "").split(",")
    if x.strip().isdigit()
}


def is_admin(user_id: int) -> bool:
    return not ADMIN_IDS or user_id in ADMIN_IDS


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

DATA_FILE = os.path.join(os.path.dirname(__file__), "data.json")


def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            print(f"⚠️ Не удалось загрузить {DATA_FILE}: {e}. Начинаем с чистого состояния.")
    return {"episodes": [], "scores": {p: 0 for p in PLAYERS}}


def save_data(data):
    tmp = DATA_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    if os.path.exists(DATA_FILE):
        os.replace(DATA_FILE, DATA_FILE + ".bak")
    os.replace(tmp, DATA_FILE)


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


def is_grouped(results):
    return bool(results) and isinstance(results[0], list)


def score_bets(player_bets, results, slots):
    """Возвращает (total_score, [win_descriptions])."""
    total = 0
    wins = []
    if is_grouped(results):
        for bet in player_bets:
            slot_idx = slots.index(bet["slot"]) if bet["slot"] in slots else None
            if slot_idx is None or slot_idx >= len(results):
                continue
            group = results[slot_idx]
            if any(fuzzy_match(bet["pair"], member) for member in group):
                total += bet["amount"]
                wins.append(f"{', '.join(group)} ({bet['slot']}) +{bet['amount']}")
    else:
        for bet in player_bets:
            slot_idx = slots.index(bet["slot"]) if bet["slot"] in slots else None
            positions = slot_positions(bet["slot"], slot_idx)
            for pos in positions:
                if 1 <= pos <= len(results):
                    if fuzzy_match(bet["pair"], results[pos - 1]):
                        total += bet["amount"]
                        wins.append(f"{results[pos-1]} ({bet['slot']}) +{bet['amount']}")
                        break
    return total, wins


def format_results(results, slots=None):
    if is_grouped(results):
        if slots and len(slots) == len(results):
            return "\n".join([f"  {slots[i]}: {', '.join(g) if g else '—'}" for i, g in enumerate(results)])
        return "\n".join([f"  Группа {i+1}: {', '.join(g) if g else '—'}" for i, g in enumerate(results)])
    return "\n".join([f"  {i+1}. {r}" for i, r in enumerate(results)])


def get_current_episode(data):
    if data["episodes"]:
        return data["episodes"][-1]
    return None


@dp.message(Command("chatid"))
async def cmd_chatid(message: Message):
    if not is_admin(message.from_user.id):
        return
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
        "  <code>/result хилькевич, ершов, башаров, олимпиец, стогниенко</code>\n"
        "  Групповой: <code>/result победитель; прошли1, прошли2; не прошли</code>\n"
        "  Пустой слот (никто не попал): <code>/result ; ; арно, иракли</code>\n\n"
        "/cancel — отменить текущий раунд\n\n"
        "<b>🎯 Игроки</b>\n"
        "/bet — сделать ставку (300 очков при нескольких слотах, 100 при одном)\n"
        "  <code>/bet хилькевич 100, олимпийцы 150, ершов 50</code>\n"
        "  При одном слоте: <code>/bet хилькевич 100</code>\n\n"
        "/mybets — мои ставки в текущем раунде\n"
        "/myresult — мои итоги по всем раундам\n"
        "/stats — моя персональная статистика\n\n"
        "<b>📊 Просмотр</b>\n"
        "/scores — таблица очков с отрывом от лидера\n"
        "/status — статус текущего раунда\n"
        "/history — история раундов\n"
        "/history 4 — детали раунда #4"
    )
    await message.answer(help_text, parse_mode="HTML")


@dp.message(Command("newbet"))
async def cmd_newbet(message: Message, command: CommandObject):
    if not is_admin(message.from_user.id):
        await message.answer("❌ Только ведущий может открывать раунды.")
        return

    data = load_data()

    ep = get_current_episode(data)
    if ep and not ep["closed"]:
        await message.answer("❌ Есть незакрытый раунд! Сначала /result или /cancel.")
        return

    text = command.args or ""
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
        n = len(data["episodes"]) + 1
        seriya = (n - 1) // 3 + 1
        ispytanie = (n - 1) % 3 + 1
        ep_name = f"{seriya} серия, испытание {ispytanie}"
        slots_text = text

    slots = [s.strip() for s in slots_text.split(",") if s.strip()]
    if not slots:
        await message.answer("❌ Не указаны слоты для ставок!")
        return

    bet_total = 100 if len(slots) == 1 else 300

    episode = {
        "id": len(data["episodes"]) + 1,
        "name": ep_name,
        "slots": slots,
        "bet_total": bet_total,
        "bets": {p: [] for p in PLAYERS},
        "bets_locked": False,
        "results": [],
        "closed": False
    }

    data["episodes"].append(episode)
    save_data(data)

    slots_display = ", ".join(slots)

    if len(slots) == 1 and " или " in slots[0]:
        parts = [p.strip() for p in slots[0].split(" или ", maxsplit=1)]
        fmt = f"Варианты:\n  /bet {parts[0]} {bet_total}\n  /bet {parts[1]} {bet_total}"
    elif len(slots) == 1:
        fmt = f"Формат: /bet имя {bet_total}"
    else:
        fmt = f"Формат: /bet пара1 сумма1, пара2 сумма2, ...\nВсего нужно поставить ровно {bet_total} очков."

    await message.answer(
        f"✅ {ep_name} открыт!\n\n"
        f"Ставки на: {slots_display}\n\n"
        f"{fmt}"
    )


@dp.message(Command("bet"))
async def cmd_bet(message: Message, command: CommandObject):
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

    bets_text = command.args or ""
    if not bets_text:
        await message.answer("Формат: /bet пара1 сумма1, пара2 сумма2, ...")
        return

    # Принимаем запятую, | и перенос строки как разделитель
    normalized = re.sub(r'[|\n]+', ',', bets_text)
    bet_entries = [b.strip() for b in normalized.split(",") if b.strip()]
    slots = ep["slots"]

    bet_total = ep.get("bet_total", 300)

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

    if total_amount != bet_total:
        diff = bet_total - total_amount
        hint = f"не хватает {diff}" if diff > 0 else f"лишних {-diff}"
        await message.answer(
            f"❌ Сумма должна быть ровно {bet_total}! У тебя {total_amount} ({hint} очков)."
        )
        return

    used_pairs = [b["pair"].lower() for b in new_bets]
    if len(used_pairs) != len(set(used_pairs)):
        await message.answer("❌ Нельзя ставить на одну пару в нескольких слотах!")
        return

    ep["bets"][player] = new_bets
    save_data(data)

    try:
        await message.delete()
    except Exception:
        pass

    await message.answer(f"✅ {player} сделал(а) ставку!")


@dp.message(Command("stopbet"))
async def cmd_stopbet(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("❌ Только ведущий может закрывать приём ставок.")
        return

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

    not_bet = [p for p in PLAYERS if not ep["bets"].get(p)]

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
async def cmd_result(message: Message, command: CommandObject):
    if not is_admin(message.from_user.id):
        await message.answer("❌ Только ведущий может вводить результаты.")
        return

    data = load_data()
    ep = get_current_episode(data)

    if not ep:
        await message.answer("❌ Нет активного раунда!")
        return

    if ep["closed"]:
        await message.answer("❌ Раунд уже закрыт!")
        return

    if not ep.get("bets_locked"):
        ep["bets_locked"] = True
        save_data(data)

    result_text = command.args or ""
    if not result_text:
        await message.answer(
            "Обычный формат: /result 1й, 2й, 3й, 4й, 5й\n"
            "Групповой (испытания): /result победитель; прошли1, прошли2; не прошли1, не прошли2\n"
            "Пустой слот (никто): /result ; ; победители  ← пустые ; для слотов без победителей"
        )
        return

    if ";" in result_text:
        groups = [g.strip() for g in result_text.split(";")]
        results = [[m.strip() for m in g.split(",") if m.strip()] for g in groups]
    else:
        results = [r.strip() for r in result_text.split(",")]

    round_scores = {p: 0 for p in PLAYERS}
    win_details = {p: [] for p in PLAYERS}

    for player in PLAYERS:
        score, wins = score_bets(ep["bets"].get(player, []), results, ep["slots"])
        round_scores[player] = score
        win_details[player] = wins
        data["scores"][player] = data["scores"].get(player, 0) + score

    ep["results"] = results
    ep["closed"] = True
    save_data(data)

    results_display = format_results(results, ep.get("slots"))

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

        ep_total, wins = score_bets(player_bets, ep["results"], ep.get("slots", []))
        won_slots = {w.split("(")[1].split(")")[0].strip() for w in wins}
        for bet in player_bets:
            if bet["slot"] in won_slots:
                lines.append(f"  ✅ {bet['slot']}: {bet['pair']} +{bet['amount']}")
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

    bets = ep["bets"].get(player, [])
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
        f"  {p}: {'✅' if ep['bets'].get(p) else '⏳'}"
        for p in PLAYERS
    ])

    msg = f"📊 {ep['name']} [{status}]\n\nСлоты: {slots_display}\n\nСтавки:\n{bets_text}"

    if ep["results"]:
        msg += f"\n\nРезультаты:\n{format_results(ep['results'], ep.get('slots'))}"

    await message.answer(msg)


@dp.message(Command("scores"))
async def cmd_scores(message: Message):
    data = load_data()

    scores = sorted([(p, data["scores"].get(p, 0)) for p in PLAYERS], key=lambda x: x[1], reverse=True)
    leader = scores[0][1]

    lines = []
    for i, (p, s) in enumerate(scores):
        gap = f"  (-{leader - s})" if i > 0 else ""
        lines.append(f"  {i+1}. {p}: {s}{gap}")

    await message.answer("🏆 Общий счёт:\n" + "\n".join(lines))


@dp.message(Command("cancel"))
async def cmd_cancel(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("❌ Только ведущий может отменять раунды.")
        return

    data = load_data()
    ep = get_current_episode(data)

    if not ep:
        await message.answer("❌ Нет активного раунда!")
        return

    if ep["closed"]:
        await message.answer("❌ Раунд уже закрыт!")
        return

    data["episodes"].remove(ep)
    save_data(data)

    await message.answer("✅ Раунд отменён и удалён.")


@dp.message(Command("history"))
async def cmd_history(message: Message, command: CommandObject):
    data = load_data()

    if not data["episodes"]:
        await message.answer("❌ История пуста!")
        return

    # /history 4 — детали конкретного раунда
    if command.args:
        try:
            ep_id = int(command.args.strip())
        except ValueError:
            await message.answer("Формат: /history или /history 4")
            return

        ep = next((e for e in data["episodes"] if e["id"] == ep_id), None)
        if not ep:
            await message.answer(f"❌ Раунд #{ep_id} не найден!")
            return

        lines = [f"📜 {ep['name']} (#{ep['id']})\nСлоты: {', '.join(ep.get('slots', []))}"]

        if ep.get("results"):
            lines.append(f"\nРезультаты:\n{format_results(ep['results'], ep.get('slots'))}")

        lines.append("\nСтавки:")
        for p in PLAYERS:
            player_bets = ep["bets"].get(p, [])
            if not player_bets:
                lines.append(f"  {p}: —")
                continue
            if ep["closed"] and ep.get("results"):
                ep_score, wins = score_bets(player_bets, ep["results"], ep.get("slots", []))
                won_slots = {w.split("(")[1].split(")")[0].strip() for w in wins}
                bet_strs = []
                for b in player_bets:
                    mark = "✅" if b["slot"] in won_slots else "❌"
                    bet_strs.append(f"{mark} {b['slot']}: {b['pair']} ({b['amount']})")
                lines.append(f"  {p} [+{ep_score}]:\n    " + "\n    ".join(bet_strs))
            else:
                bet_strs = [f"{b['slot']}: {b['pair']} ({b['amount']})" for b in player_bets]
                lines.append(f"  {p}:\n    " + "\n    ".join(bet_strs))

        await message.answer("\n".join(lines))
        return

    # /history — список всех раундов
    history_lines = []
    for ep in data["episodes"]:
        if ep["closed"]:
            status = "✅"
        else:
            status = "🔄"
        history_lines.append(f"{status} #{ep['id']} {ep['name']}")

    await message.answer("📜 История раундов:\n" + "\n".join(history_lines))


@dp.message(Command("stats"))
async def cmd_stats(message: Message):
    data = load_data()

    player = find_player(message.from_user.id)
    if not player:
        await message.answer("❌ Ты не в списке игроков!")
        return

    closed = [ep for ep in data["episodes"] if ep["closed"] and ep.get("results")]
    if not closed:
        await message.answer("❌ Нет завершённых раундов!")
        return

    rounds_played = 0
    total_bets = 0
    won_bets = 0
    best_score = 0
    best_round = None

    for ep in closed:
        player_bets = ep["bets"].get(player, [])
        if not player_bets:
            continue
        rounds_played += 1
        total_bets += len(player_bets)
        ep_score, wins = score_bets(player_bets, ep["results"], ep.get("slots", []))
        won_bets += len(wins)
        if ep_score > best_score:
            best_score = ep_score
            best_round = ep["name"]

    if rounds_played == 0:
        await message.answer(f"{player}: ни одной ставки в завершённых раундах.")
        return

    total_score = data["scores"].get(player, 0)
    win_rate = won_bets / total_bets * 100 if total_bets else 0
    avg_score = total_score / rounds_played

    lines = [
        f"📊 Статистика {player}:",
        f"  Раундов сыграно: {rounds_played} из {len(closed)}",
        f"  Угадано ставок: {won_bets} / {total_bets} ({win_rate:.0f}%)",
        f"  Среднее за раунд: {avg_score:.0f} очков",
        f"  Лучший раунд: {best_round} (+{best_score})",
        f"  Всего очков: {total_score}",
    ]
    await message.answer("\n".join(lines))


async def main():
    print("🤖 Бот запущен...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
