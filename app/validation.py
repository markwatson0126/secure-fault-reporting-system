import re


USERNAME_MIN_LENGTH = 3
USERNAME_MAX_LENGTH = 30
NAME_MAX_LENGTH = 50
PASSWORD_MIN_LENGTH = 12
USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9._-]+$")


def clean_text(value):
    if value is None:
        return ""

    return value.strip()


def is_blank(value):
    return clean_text(value) == ""


def is_valid_username(value):
    return USERNAME_PATTERN.fullmatch(value) is not None
