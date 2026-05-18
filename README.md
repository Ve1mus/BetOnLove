[🇷🇺 Русский](#русский) | [🇬🇧 English](#english)

---

<a name="русский"></a>
# Ставка на любовь — Telegram-бот

Бот для группового чата на 4 игроков. Друзья делают ставки на участников реалити-шоу.

## Быстрый старт

**1. Установи зависимости:**
```bash
pip install -r requirements.txt
```

**2. Создай `.env` на основе `.env copy`:**
```
BOT_TOKEN=токен_от_BotFather
PLAYERS=111111111:Игрок1,222222222:Игрок2,333333333:Игрок3,444444444:Игрок4
CHAT_ID=        # узнать через /chatid прямо в чате
```

Telegram ID каждого игрока — через [@userinfobot](https://t.me/userinfobot).

**3. Запусти:**
```bash
python bot.py
```

**4. Узнай CHAT_ID:** добавь бота в групповой чат → напиши `/chatid` → скопируй число в `.env` → перезапусти бота.

## Флоу раунда

### Обычный раунд

```
Ведущий:  /newbet Серия 6: 1 место, 2–3 место, 4–5 место
Бот:      ✅ Серия 6 открыт! Ставки на: 1 место, 2–3 место, 4–5 место

Игрок1:   /bet хилькевич 100, олимпийцы 150, ершов 50
Бот:      ✅ Игрок1, ставка принята!
            1 место: хилькевич (100)
            2–3 место: олимпийцы (150)
            4–5 место: ершов (50)

Ведущий:  /stopbet
Бот:      🔒 Ставки закрыты! ⚠️ Не сделали ставки: [тег Игрока2]

Ведущий:  /result хилькевич, олимпийцы, башаров, ершов, стогниенко
Бот:      ✅ Результаты Серия 6:
            1. хилькевич  2. олимпийцы  3. башаров  4. ершов  5. стогниенко

            Очки за раунд:
              Игрок1: +100  (хилькевич (1 место) +100)
              ...

            🏆 Общий счёт: ...
```

### Испытание на вылет (1 слот)

```
Ведущий:  /newbet Испытание: выживший
Игрок1:   /bet хилькевич 300
Ведущий:  /result хилькевич, стогниенко
```

При одном слоте лимит 200 снимается — можно ставить все 300 на одного.

## Команды

### 🎬 Ведущий

| Команда | Описание |
|---------|----------|
| `/newbet слоты` | Открыть новый раунд |
| `/stopbet` | Закрыть приём ставок (тегает не поставивших) |
| `/result порядок` | Ввести результаты и начислить очки |
| `/cancel` | Отменить текущий раунд |

### 🎯 Игроки

| Команда | Описание |
|---------|----------|
| `/bet ставки` | Сделать ставку (ровно 300 очков) |
| `/mybets` | Мои ставки в текущем раунде |
| `/myresult` | Мои итоги по всем раундам |

### 📊 Просмотр

| Команда | Описание |
|---------|----------|
| `/scores` | Общая таблица очков |
| `/status` | Статус текущего раунда |
| `/history` | История раундов |
| `/help` | Список команд |

## Правила ставок

- Сумма ставок = **ровно 300 очков**
- Не более **200 очков** на одну ставку (при испытании — 1 слот — до 300)
- Нельзя ставить на одну пару в нескольких слотах
- Количество ставок = количеству слотов из `/newbet`

Формат `/bet` — порядок совпадает с порядком слотов. Разделитель — запятая, `|` или перенос строки:
```
/bet хилькевич 100, олимпийцы 150, ершов 50
```

## Защита чата

Бот отвечает **только в одном чате** — том, чей `CHAT_ID` указан в `.env`. Если кто-то чужой добавит бота — он молча игнорирует все команды.

## Настройка меню команд (BotFather)

Чтобы команды появлялись в меню `/` в нижней строке чата:

1. [@BotFather](https://t.me/BotFather) → `/setcommands` → выбери бота
2. Вставь:

```
newbet - Открыть новый раунд
bet - Сделать ставку
stopbet - Закрыть приём ставок
result - Ввести результаты
mybets - Мои ставки
myresult - Мои итоги по раундам
scores - Таблица очков
status - Статус раунда
cancel - Отменить раунд
history - История раундов
help - Список команд
```

---

<a name="english"></a>
# Bet on Love — Telegram Bot

A group chat bot for 4 players. Friends bet on participants of a reality show.

## Quick Start

**1. Install dependencies:**
```bash
pip install -r requirements.txt
```

**2. Create `.env` from `.env copy`:**
```
BOT_TOKEN=your_token_from_BotFather
PLAYERS=111111111:Alice,222222222:Bob,333333333:Carol,444444444:Dave
CHAT_ID=        # find it by running /chatid in your group chat
```

Get each player's Telegram ID via [@userinfobot](https://t.me/userinfobot).

**3. Run:**
```bash
python bot.py
```

**4. Get CHAT_ID:** add the bot to your group → send `/chatid` → copy the number into `.env` → restart the bot.

## Round Flow

### Regular round

```
Host:    /newbet Series 6: 1st place, 2nd–3rd place, 4th–5th place
Bot:     ✅ Series 6 open! Bets on: 1st place, 2nd–3rd place, 4th–5th place

Alice:   /bet participant1 100, participant2 150, participant3 50
Bot:     ✅ Alice, bet accepted!
           1st place: participant1 (100)
           2nd–3rd place: participant2 (150)
           4th–5th place: participant3 (50)

Host:    /stopbet
Bot:     🔒 Bets closed! ⚠️ Missing bets: [Bob tagged]

Host:    /result participant1, participant2, participant4, participant3, participant5
Bot:     ✅ Results Series 6:
           1. participant1  2. participant2  3. participant4  4. participant3  5. participant5

           Points this round:
             Alice: +100  (participant1 (1st place) +100)
             ...

           🏆 Leaderboard: ...
```

### Elimination challenge (1 slot)

```
Host:    /newbet Challenge: survivor
Alice:   /bet participant1 300
Host:    /result participant1, participant2
```

With a single slot the 200-point cap is lifted — all 300 can go on one pick.

## Commands

### 🎬 Host

| Command | Description |
|---------|-------------|
| `/newbet slots` | Open a new round |
| `/stopbet` | Lock bets (tags players who haven't bet) |
| `/result order` | Enter results and award points |
| `/cancel` | Cancel the current round |

### 🎯 Players

| Command | Description |
|---------|-------------|
| `/bet bets` | Place a bet (exactly 300 points) |
| `/mybets` | My bets in the current round |
| `/myresult` | My history across all rounds |

### 📊 Info

| Command | Description |
|---------|-------------|
| `/scores` | Overall leaderboard |
| `/status` | Current round status |
| `/history` | Round history |
| `/help` | Command list |

## Betting Rules

- Total bet = **exactly 300 points**
- Max **200 points** per single bet (exception: elimination round with 1 slot allows up to 300)
- Can't bet on the same participant in multiple slots
- Number of bets must equal the number of slots in `/newbet`

`/bet` order matches slot order. Separator can be comma, `|`, or newline:
```
/bet participant1 100, participant2 150, participant3 50
```

## Chat Restriction

The bot only responds in **one specific chat** — the one whose `CHAT_ID` is set in `.env`. Anyone else adding the bot to a different group or messaging it in private will be silently ignored.

## Setting Up the Command Menu (BotFather)

To show commands in the `/` menu at the bottom of the chat:

1. [@BotFather](https://t.me/BotFather) → `/setcommands` → select your bot
2. Paste:

```
newbet - Open a new round
bet - Place a bet
stopbet - Lock bets
result - Enter results
mybets - My bets
myresult - My round history
scores - Leaderboard
status - Round status
cancel - Cancel round
history - Round history
help - Command list
```
