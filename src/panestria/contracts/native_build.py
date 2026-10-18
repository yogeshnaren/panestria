"""Bash is bounded worker input, never a host command or an approval."""

MAX_BASH_BYTES = 16 * 1024


def bash_script(value: object) -> str:
    if type(value) is not str or not value.strip() or "\0" in value:
        raise ValueError("invalid_scoped_bash")
    try:
        if len(value.encode("utf-8")) > MAX_BASH_BYTES:
            raise ValueError
    except (UnicodeError, ValueError):
        raise ValueError("invalid_scoped_bash") from None
    return value
