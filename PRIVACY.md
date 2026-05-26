[🇷🇺 Русский](#русский) | [🇬🇧 English](#english)

---

<a name="русский"></a>
# Политика конфиденциальности

Дата вступления в силу: 27 мая 2026 г.

Эта политика описывает, какие данные обрабатывает Telegram-бот «Ставка на любовь» и как они используются. Бот предназначен для игры в одном групповом чате и работает только для чата, указанного владельцем бота в настройках.

## Какие данные обрабатываются

Бот может обрабатывать следующие данные:

- Telegram ID игроков, указанные владельцем бота в переменной `PLAYERS`.
- Отображаемые имена игроков, указанные владельцем бота в переменной `PLAYERS`.
- Telegram ID разрешённого группового чата, указанный в переменной `CHAT_ID`.
- Ставки игроков: выбранные имена участников, суммы ставок и связанные раунды.
- Результаты раундов, история раундов и общий счёт игроков.
- Текст команд, отправленных боту в разрешённом чате, только в объёме, необходимом для выполнения команд.

Бот не запрашивает и не хранит номера телефонов, адреса электронной почты, геолокацию, фотографии, платёжные данные или пароли пользователей.

## Как используются данные

Данные используются только для работы игры:

- открытия и закрытия раундов;
- приёма и проверки ставок;
- подсчёта очков;
- показа текущего статуса, истории раундов и таблицы счёта;
- ограничения работы бота одним разрешённым чатом.

Данные не используются для рекламы, профилирования, аналитики или продажи третьим лицам.

## Где хранятся данные

Игровые данные сохраняются в локальном файле `data.json` на сервере или компьютере, где запущен бот. Конфигурационные данные, включая токен бота, список игроков и разрешённый чат, хранятся в локальном `.env` файле владельца бота.

Репозиторий не содержит внешней базы данных, встроенной аналитики или интеграций с рекламными сервисами.

## Передача данных третьим лицам

Бот работает через Telegram Bot API, поэтому сообщения и команды также обрабатываются Telegram в соответствии с политиками Telegram.

Кроме Telegram, бот не передаёт игровые данные третьим лицам, если владелец конкретного экземпляра бота не настроил дополнительную инфраструктуру самостоятельно.

## Срок хранения

Данные хранятся, пока владелец бота сохраняет файл `data.json` и использует бота. Владелец бота может удалить историю игры, удалив или изменив `data.json`.

Команда `/cancel` очищает ставки только текущего незавершённого раунда. Она не удаляет уже завершённую историю и общий счёт.

## Удаление и исправление данных

Если вы хотите удалить или исправить связанные с вами игровые данные, обратитесь к владельцу бота или администратору группового чата. Поскольку данные хранятся локально у владельца конкретного экземпляра бота, удаление выполняется владельцем этого экземпляра.

## Доступ к данным

Игровые данные могут быть видны:

- владельцу бота, у которого есть доступ к файлам `.env` и `data.json`;
- участникам разрешённого группового чата через команды бота, например `/scores`, `/status`, `/history`, `/mybets` и `/myresult`.

Бот не реализует отдельные роли администратора внутри кода. Доступ к запуску, настройке и файлам бота контролируется владельцем сервера или компьютера, где запущен бот.

## Безопасность

Владелец бота должен хранить `.env` файл и `BOT_TOKEN` в секрете, ограничивать доступ к серверу или компьютеру с ботом и не публиковать `data.json`, если он содержит реальные данные игроков.

Бот игнорирует сообщения из чатов, которые не совпадают с настроенным `CHAT_ID`.

## Изменения политики

Эта политика может обновляться при изменении функциональности бота или способа обработки данных. Актуальная версия хранится в этом файле.

## Контакты

По вопросам конфиденциальности обратитесь к владельцу конкретного экземпляра бота или администратору группового чата, где используется бот.

---

<a name="english"></a>
# Privacy Policy

Effective date: May 27, 2026

This policy explains what data the "Bet on Love" Telegram bot processes and how that data is used. The bot is designed for a single group chat and only works in the chat configured by the bot owner.

## Data Processed

The bot may process the following data:

- Telegram IDs of players configured by the bot owner in the `PLAYERS` variable.
- Display names of players configured by the bot owner in the `PLAYERS` variable.
- Telegram ID of the allowed group chat configured in the `CHAT_ID` variable.
- Player bets: selected participant names, bet amounts, and related rounds.
- Round results, round history, and player scores.
- Command text sent to the bot in the allowed chat, only as needed to execute commands.

The bot does not request or store phone numbers, email addresses, location data, photos, payment data, or user passwords.

## How Data Is Used

Data is used only to run the game:

- opening and closing rounds;
- accepting and validating bets;
- calculating scores;
- showing current status, round history, and the leaderboard;
- restricting the bot to one allowed chat.

Data is not used for advertising, profiling, analytics, or sale to third parties.

## Data Storage

Game data is stored in the local `data.json` file on the server or computer where the bot is running. Configuration data, including the bot token, player list, and allowed chat, is stored in the bot owner's local `.env` file.

This repository does not include an external database, built-in analytics, or advertising integrations.

## Third Parties

The bot operates through the Telegram Bot API, so messages and commands are also processed by Telegram according to Telegram's own policies.

Apart from Telegram, the bot does not share game data with third parties unless the owner of a specific bot instance adds extra infrastructure independently.

## Retention

Data is kept while the bot owner keeps the `data.json` file and continues using the bot. The bot owner can delete game history by deleting or editing `data.json`.

The `/cancel` command clears bets only for the current unfinished round. It does not delete completed history or the overall leaderboard.

## Deletion and Correction

If you want to delete or correct game data related to you, contact the bot owner or the group chat administrator. Because data is stored locally by the owner of each bot instance, deletion must be handled by that owner.

## Access to Data

Game data may be visible to:

- the bot owner, who has access to the `.env` and `data.json` files;
- members of the allowed group chat through bot commands such as `/scores`, `/status`, `/history`, `/mybets`, and `/myresult`.

The bot does not implement separate admin roles in code. Access to running, configuring, and editing the bot files is controlled by the owner of the server or computer where the bot is running.

## Security

The bot owner should keep the `.env` file and `BOT_TOKEN` secret, restrict access to the server or computer running the bot, and avoid publishing `data.json` if it contains real player data.

The bot ignores messages from chats that do not match the configured `CHAT_ID`.

## Changes

This policy may be updated when the bot functionality or data handling changes. The current version is kept in this file.

## Contact

For privacy questions, contact the owner of the specific bot instance or the administrator of the group chat where the bot is used.
