from enum import StrEnum

LOGGER_COMMAND = "AuthChecker"


class SwitchEnum(StrEnum):
    ENABLE = "醒来"
    DISABLE = "休息吧"


WARNING_THRESHOLD = 0.5
