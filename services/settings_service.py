"""Runtime settings helpers backed by the database, with config.py fallbacks."""

import logging
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import config

logger = logging.getLogger(__name__)


def get_setting(key: str, default: str = "") -> str:
    """Read a persisted runtime setting, falling back safely during startup/tests."""
    try:
        from models.database import _get_db
        value = _get_db().get_setting(key, "")
    except Exception as e:
        logger.debug("Unable to read setting %s from database: %s", key, e)
        return default
    return value if value != "" else default


def get_int_setting(key: str, default: int, *, min_value: int | None = None, max_value: int | None = None) -> int:
    raw = get_setting(key, "")
    if raw == "":
        return default
    try:
        value = int(raw)
    except ValueError:
        logger.warning("%s 設定格式錯誤，改用預設值 %s", key, default)
        return default
    if min_value is not None and value < min_value:
        logger.warning("%s 設定小於允許範圍，改用預設值 %s", key, default)
        return default
    if max_value is not None and value > max_value:
        logger.warning("%s 設定大於允許範圍，改用預設值 %s", key, default)
        return default
    return value


def get_int_list_setting(key: str, default: list[int], *, min_value: int = 0, max_value: int = 23) -> list[int]:
    raw = get_setting(key, "")
    if raw == "":
        return default
    try:
        values = [int(x.strip()) for x in raw.split(",") if x.strip()]
    except ValueError:
        logger.warning("%s 設定格式錯誤，改用預設值", key)
        return default
    if not values or any(v < min_value or v > max_value for v in values):
        logger.warning("%s 設定超出允許範圍，改用預設值", key)
        return default
    return values


def get_timezone_name() -> str:
    value = get_setting("timezone", config.TIMEZONE)
    try:
        ZoneInfo(value)
    except ZoneInfoNotFoundError:
        logger.warning("timezone 設定無效，改用預設值 %s", config.TIMEZONE)
        return config.TIMEZONE
    return value


def get_gpt_model() -> str:
    return get_setting("gpt_model", config.GPT_MODEL)


def get_google_drive_folder_id() -> str:
    return get_setting("google_drive_folder_id", config.GOOGLE_DRIVE_FOLDER_ID)


def get_gcal_calendar_id() -> str:
    return get_setting("gcal_calendar_id", config.GCAL_CALENDAR_ID)
