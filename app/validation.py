from email_validator import EmailNotValidError, validate_email


EMAIL_MAX_LENGTH = 254
NAME_MAX_LENGTH = 100
PASSWORD_MIN_LENGTH = 12
COMMON_PASSWORDS = {
    "password", "password123", "qwerty", "qwerty123", "letmein",
    "welcome", "welcome123", "admin", "admin123", "changeme", "secret",
    "government", "hmrc",
}


def clean_text(value):
    return "" if value is None else value.strip()


def is_blank(value):
    return clean_text(value) == ""


def validate_email_address(value):
    email = clean_text(value)
    if not email:
        return None, "Enter an email address"
    if len(email) > EMAIL_MAX_LENGTH:
        return None, "Email address must be 254 characters or fewer"
    try:
        parsed = validate_email(email, check_deliverability=False)
    except EmailNotValidError:
        return None, "Enter an email address in the correct format, like name@example.com"
    normalised = parsed.normalized.lower()
    if len(normalised) > EMAIL_MAX_LENGTH:
        return None, "Email address must be 254 characters or fewer"
    return normalised, None


def validate_domain(value):
    domain = clean_text(value).lower()
    if not domain:
        return None, "Enter an email domain"
    if any(token in domain for token in ("@", "://", "/", "?", "#", "*", ":")):
        return None, "Enter an email domain in the correct format, like hmrc.gov.uk"
    try:
        parsed = validate_email(f"domain-check@{domain}", check_deliverability=False)
    except EmailNotValidError:
        return None, "Enter an email domain in the correct format, like hmrc.gov.uk"
    return parsed.domain.lower(), None


def validate_name(value, label):
    name = clean_text(value)
    if not name:
        return name, f"Enter your {label.lower()}"
    if len(name) > NAME_MAX_LENGTH:
        return name, f"{label} must be 100 characters or fewer"
    return name, None


def validate_password(password):
    if password == "" or password.isspace():
        return "Enter a password"
    compact = "".join(character for character in password.casefold() if character.isalnum())
    repeated_unit = any(
        len(compact) >= 12 and len(compact) % size == 0
        and compact == compact[:size] * (len(compact) // size)
        for size in (1, 2, 3)
    )
    sequences = {
        "0123456789", "1234567890", "123456789012", "9876543210",
        "abcdefghijklmnopqrstuvwxyz", "zyxwvutsrqponmlkjihgfedcba",
    }
    if compact in COMMON_PASSWORDS or repeated_unit or compact in sequences:
        return "Choose a password that is not commonly used"
    if len(password) < PASSWORD_MIN_LENGTH:
        return "Password must be at least 12 characters"
    return None


def email_domain(email):
    return email.rsplit("@", 1)[1].lower()
