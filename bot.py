import json
import os
import re
from typing import Any, Awaitable, Callable
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, BaseMiddleware
from aiogram.types import BotCommand, Message
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
    """Return total points and structured winning bets."""
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
                wins.append(bet)
    else:
        for bet in player_bets:
            slot_idx = slots.index(bet["slot"]) if bet["slot"] in slots else None
            positions = slot_positions(bet["slot"], slot_idx)
            for pos in positions:
                if 1 <= pos <= len(results):
                    if fuzzy_match(bet["pair"], results[pos - 1]):
                        total += bet["amount"]
                        wins.append(bet)
                        break
    return total, wins


def format_win(bet):
    return f"{bet['pair']} — {bet['slot']}, +{bet['amount']}"


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


BET_LABELS = {"round": "Раунд", "elim": "Вылет", "final": "Финал"}


def active_bets(data):
    """Inspect existing state without creating empty betting blocks."""
    active = []
    ep = get_current_episode(data)
    if ep and not ep["closed"]:
        active.append(("round", ep))
    for kind in ("elim", "final"):
        block = data.get(kind)
        if block and block.get("bets") and not block.get("resolved"):
            active.append((kind, block))
    return active


def format_scores(data):
    scores = sorted(data["scores"].items(), key=lambda item: item[1], reverse=True)
    if not scores:
        return "🏆 Очков пока нет."
    leader = scores[0][1]
    return "🏆 Общий счёт:\n" + "\n".join(
        f"  {i}. {player}: {score}" + (f"  (-{leader - score})" if i > 1 else "")
        for i, (player, score) in enumerate(scores, 1)
    )


async def answer_long(message, text):
    """Keep growing season histories within Telegram's message limit."""
    while len(text) > 3500:
        cut = text.rfind("\n", 0, 3500)
        if cut <= 0:
            cut = 3500
        await message.answer(text[:cut])
        text = text[cut:].lstrip("\n")
    if text:
        await message.answer(text)


FINAL_BET_AMOUNT = 500


def get_final(data):
    """Возвращает блок финальной ставки, создавая его при первом обращении."""
    final = data.get("final")
    if final is None:
        final = {
            "amount": FINAL_BET_AMOUNT,
            "bets": {},
            "locked": False,
            "winner": None,
            "resolved": False,
        }
        data["final"] = final
    return final


ELIM_BET_AMOUNT = 300


def get_elim(data):
    """Create the current elimination block lazily; settlements live in history."""
    elim = data.get("elim")
    if elim is None:
        elim = {
            "amount": ELIM_BET_AMOUNT,
            "bets": {},
            "locked": False,
        }
        data["elim"] = elim
    return elim


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
    await message.answer(
        "🎲 <b>Ставка на любовь</b>\n\n"
        "Играем по очереди: открываем ставку → ставим → закрываем приём → вводим результат. "
        "Пока ставка не рассчитана или не отменена, новую открыть нельзя.\n\n"
        "<b>🎬 Обычный раунд</b>\n"
        "Открыть: <code>/newbet 1 место, 2–3 место, 4–5 место</code>\n"
        "Поставить: <code>/bet хилькевич 100, олимпийцы 150, ершов 50</code>\n"
        "Порядок ставок совпадает с порядком мест. Несколько мест — ровно 300 очков, "
        "не больше 200 на одно. Один участник не должен повторяться.\n"
        "Одно место: <code>/newbet Испытание: победитель</code>\n"
        "Ставка: <code>/bet хилькевич 100</code> — ровно 100 очков.\n\n"
        "<b>🚪 Вылет и 🏁 финал</b>\n"
        "<code>/elim башаров</code> — кто вылетит, 300 очков за верный прогноз.\n"
        "<code>/final хилькевич</code> — кто победит в сезоне, 500 очков.\n"
        "Первая ставка открывает приём, остальные ставят той же командой. "
        "Без имени /elim и /final показывают только твой выбор. "
        "Менять его можно до закрытия приёма.\n\n"
        "<b>🔒 Закрытие и результат — для любой ставки</b>\n"
        "/stopbet — закрыть приём. Если кто-то не поставил, бот предупредит; "
        "повтор команды всё равно закроет приём.\n"
        "/result — ввести результат и начислить очки:\n"
        "• Раунд: <code>/result хилькевич, олимпийцы, башаров, ершов, стогниенко</code>\n"
        "• Группы по местам: <code>/result победитель; прошли1, прошли2; выбыли</code>\n"
        "• Пустая группа: <code>/result ; ; победители</code>\n"
        "• Вылет: <code>/result башаров, арно</code>\n"
        "• Финал: <code>/result хилькевич</code>\n"
        "Тип бот определит сам. /result без текста только покажет подсказку.\n"
        "/cancel — отменить текущую ставку; прошлые очки сохранятся.\n"
        "Вести игру может любой из нас.\n\n"
        "<b>📊 Мои ставки и общий счёт</b>\n"
        "/me — моя текущая или последняя ставка, очки и статистика\n"
        "/mehistory — мои итоги по раундам, вылетам и финалу\n"
        "/scores — таблица очков\n"
        "/status — текущая ставка и кто уже поставил\n"
        "/history — история раундов и вылетов\n"
        "<code>/history 4</code> — детали раунда №4\n"
        "<code>/history e1</code> — детали вылета №1\n\n"
        "Чужие прогнозы скрыты до закрытия приёма. "
        "Ответы на личные команды в группе видны всем.",
        parse_mode="HTML",
    )


@dp.message(Command("newbet"))
async def cmd_newbet(message: Message, command: CommandObject):
    if not is_admin(message.from_user.id):
        await message.answer("❌ Только ведущий может открывать раунды.")
        return

    data = load_data()

    if active_bets(data):
        await message.answer("❌ Уже есть активная ставка. Сначала /result или /cancel.")
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
    data["last_bet_type"] = "round"
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

    # Accept commas, pipes and newlines between picks.
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
    active = active_bets(data)
    if len(active) != 1:
        await message.answer("❌ Нет единственной активной ставки. Проверь /status.")
        return
    kind, block = active[0]
    lock_key = "bets_locked" if kind == "round" else "locked"
    if block.get(lock_key):
        await message.answer("⚠️ Приём ставок уже закрыт. Введи /result.")
        return
    missing = [p for p in PLAYERS if not block["bets"].get(p)]
    if missing and not block.get("stop_warned"):
        block["stop_warned"] = True
        save_data(data)
        await message.answer(
            f"⚠️ {BET_LABELS[kind]}: не все поставили: {', '.join(missing)}.\n"
            "Введи /stopbet ещё раз, чтобы всё равно закрыть приём."
        )
        return
    block[lock_key] = True
    save_data(data)
    await message.answer(f"🔒 {BET_LABELS[kind]}: приём ставок закрыт!\nРезультат: /result ...")


def settle_round(data, ep, result_text):
    if ";" in result_text:
        results = [[m.strip() for m in group.split(",") if m.strip()]
                   for group in result_text.split(";")]
        if len(results) != len(ep["slots"]):
            raise ValueError(f"Нужно {len(ep['slots'])} групп, разделённых ;")
    else:
        results = [r.strip() for r in result_text.split(",")]
        if not all(results):
            raise ValueError("Пустые имена недопустимы. Для пустой группы используй ;")
    if not any(results):
        raise ValueError("Укажи хотя бы один результат.")
    round_scores = {}
    lines = []
    for player in PLAYERS:
        score, wins = score_bets(ep["bets"].get(player, []), results, ep["slots"])
        round_scores[player] = score
        details = "; ".join(format_win(w) for w in wins) or "—"
        lines.append(f"  {player}: +{score} ({details})")
    for player, score in round_scores.items():
        data["scores"][player] = data["scores"].get(player, 0) + score
    ep.update(results=results, closed=True, bets_locked=True, round_scores=round_scores)
    return (f"✅ Результаты {ep['name']}:\n{format_results(results, ep['slots'])}\n\n"
            "Очки за раунд:\n" + "\n".join(lines))


def settle_special(data, kind, block, result_text):
    results = [name.strip() for name in result_text.split(",")]
    if not all(results) or ";" in result_text or (kind == "final" and len(results) != 1):
        raise ValueError("Для финала укажи одного победителя, для вылета — имена через запятую.")
    amount = block["amount"]
    round_scores = {}
    lines = []
    for player in PLAYERS:
        pick = block["bets"].get(player)
        score = amount if pick and any(fuzzy_match(pick, name) for name in results) else 0
        round_scores[player] = score
        mark = "✅" if score else "❌"
        lines.append(f"  {mark} {player}: {pick or 'не ставил'} +{score}")
    for player, score in round_scores.items():
        data["scores"][player] = data["scores"].get(player, 0) + score
    if kind == "final":
        block.update(locked=True, winner=results[0], resolved=True, round_scores=round_scores)
    else:
        history = data.setdefault("elim_history", [])
        history.append({"id": len(history) + 1, "amount": amount,
                        "bets": dict(block["bets"]), "results": results,
                        "round_scores": round_scores})
        data["elim"] = {"amount": amount, "bets": {}, "locked": False}
    return f"✅ {BET_LABELS[kind]}: {', '.join(results)}\n\n" + "\n".join(lines)


@dp.message(Command("result"))
async def cmd_result(message: Message, command: CommandObject):
    if not is_admin(message.from_user.id):
        await message.answer("❌ Только ведущий может вводить результаты.")
        return
    result_text = (command.args or "").strip()
    if not result_text:
        await message.answer("Формат: /result имя1, имя2, ...\nДля групп: /result победитель; прошедшие; выбывшие")
        return
    data = load_data()
    active = active_bets(data)
    if len(active) != 1:
        await message.answer("❌ Нет единственной активной ставки. Проверь /status.")
        return
    kind, block = active[0]
    try:
        text = (settle_round(data, block, result_text) if kind == "round"
                else settle_special(data, kind, block, result_text))
    except ValueError as error:
        await message.answer(f"❌ {error}")
        return
    save_data(data)
    await answer_long(message, text + "\n\n" + format_scores(data))


def personal_pick_lines(kind, block, player):
    if kind == "round":
        bets = block["bets"].get(player, [])
        return [f"  {b['slot']}: {b['pair']} ({b['amount']})" for b in bets] or ["  Ставки нет"]
    pick = block.get("bets", {}).get(player)
    return [f"  {pick} ({block['amount']})" if pick else "  Ставки нет"]


@dp.message(Command("mehistory"))
async def cmd_myresult(message: Message):
    data = load_data()
    player = find_player(message.from_user.id)
    if not player:
        await message.answer("❌ Ты не в списке игроков!")
        return
    lines = [f"📊 История {player}:"]
    for ep in data["episodes"]:
        if not ep["closed"] or not ep.get("results"):
            continue
        lines.append(f"\n▸ {ep['name']}")
        bets = ep["bets"].get(player, [])
        score, wins = score_bets(bets, ep["results"], ep.get("slots", []))
        won_slots = {w["slot"] for w in wins}
        for bet in bets:
            won = bet["slot"] in won_slots
            lines.append(f"  {'✅' if won else '❌'} {bet['slot']}: {bet['pair']} +{bet['amount'] if won else 0}")
        if not bets:
            lines.append("  Ставок не было")
        lines.append(f"  Итого: +{score}")
    for entry in data.get("elim_history", []):
        pick = entry["bets"].get(player)
        score = entry["round_scores"].get(player, 0)
        lines.append(f"\n▸ Вылет #{entry['id']}: {', '.join(entry['results'])}")
        lines.append(f"  {'✅' if score else '❌'} {pick or 'не ставил'} +{score}")
    final = data.get("final", {})
    if final.get("resolved"):
        pick = final["bets"].get(player)
        score = final.get("round_scores", {}).get(player)
        if score is None:
            score = final["amount"] if pick and fuzzy_match(pick, final["winner"]) else 0
        lines.append(f"\n▸ Финал: {final['winner']}\n  {pick or 'не ставил'} +{score}")
    if len(lines) == 1:
        lines.append("Завершённых ставок пока нет.")
    lines.append(f"\n🏆 Всего: {data['scores'].get(player, 0)}")
    await answer_long(message, "\n".join(lines))


@dp.message(Command("me"))
async def cmd_mybets(message: Message):
    data = load_data()
    player = find_player(message.from_user.id)
    if not player:
        await message.answer("❌ Ты не в списке игроков!")
        return
    lines = [f"🎯 {player} — {data['scores'].get(player, 0)} очков"]
    active = active_bets(data)
    if active:
        for kind, block in active:
            lines.append(f"\n{BET_LABELS[kind]} — моя ставка:")
            lines.extend(personal_pick_lines(kind, block, player))
    else:
        lines.append("\nАктивной ставки нет.")
        kind = data.get("last_bet_type", "round")
        block = (get_current_episode(data) if kind == "round" else
                 data.get("final") if kind == "final" else
                 (data.get("elim_history") or [None])[-1])
        if block:
            lines.append(f"Последняя ставка ({BET_LABELS[kind]}):")
            lines.extend(personal_pick_lines(kind, block, player))
    played = [(ep, ep["bets"].get(player, [])) for ep in data["episodes"]
              if ep["closed"] and ep.get("results") and ep["bets"].get(player)]
    if played:
        scores = [score_bets(bets, ep["results"], ep["slots"]) for ep, bets in played]
        wins = sum(len(w) for _, w in scores)
        count = sum(len(bets) for _, bets in played)
        average = sum(score for score, _ in scores) / len(played)
        best_index = max(range(len(scores)), key=lambda i: scores[i][0])
        lines.extend([f"\nРаундов: {len(played)}; угадано: {wins}/{count}",
                      f"Среднее за обычный раунд: {average:.0f}",
                      f"Лучший: {played[best_index][0]['name']} (+{scores[best_index][0]})"])
    lines.append("\nПодробная история: /mehistory")
    await answer_long(message, "\n".join(lines))


@dp.message(Command("status"))
async def cmd_status(message: Message):
    active = active_bets(load_data())
    if not active:
        await message.answer("Активной ставки нет. Новый раунд: /newbet; вылет: /elim; финал: /final.")
        return
    lines = []
    for kind, block in active:
        locked = block.get("bets_locked" if kind == "round" else "locked", False)
        title = block["name"] if kind == "round" else BET_LABELS[kind]
        lines.append(f"{'🔒' if locked else '🟢'} {title}")
        for player in PLAYERS:
            has_bet = bool(block["bets"].get(player))
            lines.append(f"  {player}: {'✅' if has_bet else '⏳'}")
            if locked and has_bet:
                lines.extend(personal_pick_lines(kind, block, player))
    if len(active) > 1:
        lines.append("⚠️ Найдены старые параллельные ставки; автоматический расчёт отключён.")
    await answer_long(message, "\n".join(lines))


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
        await message.answer("❌ Только ведущий может отменять ставки.")
        return
    data = load_data()
    active = active_bets(data)
    if len(active) != 1:
        await message.answer("❌ Нет единственной активной ставки. Проверь /status.")
        return
    kind, block = active[0]
    if kind == "round":
        data["episodes"].remove(block)
    else:
        data.pop(kind)
    save_data(data)
    await message.answer(f"✅ {BET_LABELS[kind]}: ставка отменена. Начисленные ранее очки и история сохранены.")


@dp.message(Command("history"))
async def cmd_history(message: Message, command: CommandObject):
    data = load_data()

    if not data["episodes"] and not data.get("elim_history"):
        await message.answer("❌ История пуста!")
        return

    # Elimination entries have a separate stable ID, such as e1.
    if command.args and command.args.strip().lower().startswith("e"):
        try:
            entry_id = int(command.args.strip()[1:])
        except ValueError:
            await message.answer("Формат: /history e1")
            return
        entry = next((e for e in data.get("elim_history", []) if e["id"] == entry_id), None)
        if not entry:
            await message.answer("❌ Вылет не найден.")
            return
        lines = [f"📜 Вылет #e{entry_id}: {', '.join(entry['results'])}"]
        for player in PLAYERS:
            pick = entry["bets"].get(player, "не ставил")
            score = entry["round_scores"].get(player, 0)
            lines.append(f"  {'✅' if score else '❌'} {player}: {pick} +{score}")
        await answer_long(message, "\n".join(lines))
        return
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

        reveal = ep["closed"] or ep.get("bets_locked", False)
        lines.append("\nСтавки:" if reveal else "\nСтавки скрыты до закрытия приёма:")
        for p in PLAYERS:
            if not reveal:
                lines.append(f"  {p}: {'✅' if ep['bets'].get(p) else '⏳'}")
                continue
            player_bets = ep["bets"].get(p, [])
            if not player_bets:
                lines.append(f"  {p}: —")
                continue
            if ep["closed"] and ep.get("results"):
                ep_score, wins = score_bets(player_bets, ep["results"], ep.get("slots", []))
                won_slots = {w["slot"] for w in wins}
                bet_strs = []
                for b in player_bets:
                    mark = "✅" if b["slot"] in won_slots else "❌"
                    bet_strs.append(f"{mark} {b['slot']}: {b['pair']} ({b['amount']})")
                lines.append(f"  {p} [+{ep_score}]:\n    " + "\n    ".join(bet_strs))
            else:
                bet_strs = [f"{b['slot']}: {b['pair']} ({b['amount']})" for b in player_bets]
                lines.append(f"  {p}:\n    " + "\n    ".join(bet_strs))

        await answer_long(message, "\n".join(lines))
        return

    # /history — список всех раундов
    history_lines = []
    for ep in data["episodes"]:
        if ep["closed"]:
            status = "✅"
        else:
            status = "🔄"
        history_lines.append(f"{status} #{ep['id']} {ep['name']}")

    for entry in data.get("elim_history", []):
        history_lines.append(f"✅ #e{entry['id']} Вылет: {', '.join(entry['results'])}")
    await answer_long(message, "📜 История ставок:\n" + "\n".join(history_lines))


async def place_special_bet(message, command, kind):
    data = load_data()
    player = find_player(message.from_user.id)
    if not player:
        await message.answer("❌ Ты не в списке игроков!")
        return
    pick = (command.args or "").strip()
    if not pick:
        block = data.get(kind)
        if kind == "elim" and not (block and block.get("bets")):
            block = (data.get("elim_history") or [None])[-1]
        lines = [f"{BET_LABELS[kind]} — моя ставка:"]
        lines.extend(personal_pick_lines(kind, block, player) if block else ["  Ставки нет"])
        lines.append(f"Поставить: /{kind} имя")
        await message.answer("\n".join(lines))
        return
    active = active_bets(data)
    if any(other != kind for other, _ in active):
        await message.answer("❌ Уже есть другая активная ставка. Сначала /result или /cancel.")
        return
    block = get_final(data) if kind == "final" else get_elim(data)
    if block.get("resolved") or block.get("locked"):
        await message.answer("🔒 Приём ставок закрыт.")
        return
    block["bets"][player] = pick
    data["last_bet_type"] = kind
    save_data(data)
    try:
        await message.delete()
    except Exception:
        pass
    await message.answer(f"✅ {player}: ставка принята ({BET_LABELS[kind]}, {block['amount']} очков).")


@dp.message(Command("final"))
async def cmd_final(message: Message, command: CommandObject):
    await place_special_bet(message, command, "final")


@dp.message(Command("elim"))
async def cmd_elim(message: Message, command: CommandObject):
    await place_special_bet(message, command, "elim")


BOT_COMMANDS = [
    BotCommand(command="me", description="Моя ставка, очки и статистика"),
    BotCommand(command="mehistory", description="Мои результаты за сезон"),
    BotCommand(command="scores", description="Общая таблица очков"),
    BotCommand(command="status", description="Что играем и кто уже поставил"),
    BotCommand(command="bet", description="Поставить в текущем раунде"),
    BotCommand(command="elim", description="Поставить на вылет — 300 очков"),
    BotCommand(command="final", description="Поставить на победителя — 500 очков"),
    BotCommand(command="newbet", description="Начать новый раунд"),
    BotCommand(command="stopbet", description="Закрыть приём ставок"),
    BotCommand(command="result", description="Ввести результат и начислить очки"),
    BotCommand(command="cancel", description="Отменить текущую ставку"),
    BotCommand(command="history", description="История раундов и вылетов"),
    BotCommand(command="help", description="Как играть и пользоваться ботом"),
]


async def main():
    await bot.set_my_commands(BOT_COMMANDS)
    print("🤖 Бот запущен...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
