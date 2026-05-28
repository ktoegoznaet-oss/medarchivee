"""Database access layer for the Telegram bot.

Контракт: бот хранит **свою копию** SQLAlchemy-моделей (только то, что
ему реально нужно: TelegramBinding, TelegramBindingCode, минимальный
User для отображения @username/имени). Источник истины по схеме —
backend; миграции бегут только из backend-контейнера. См. подсказку
этапа 6 о возможном рефакторинге в shared_models на этапе 10.
"""
