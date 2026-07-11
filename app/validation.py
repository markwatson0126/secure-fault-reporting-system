def clean_text(value):
    if value is None:
        return ""

    return value.strip()


def is_blank(value):
    return clean_text(value) == ""