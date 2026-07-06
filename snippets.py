"""Snippet expansion: 'snippet <name>' or '/<name>' in dictated text becomes
the stored expansion. One pass — expansions are never re-scanned."""
import re
import time

NAME_RE = re.compile(r"^[A-Za-z0-9-]{1,30}$")
MAX_SNIPPETS = 100
MAX_EXPANSION = 2000
MAX_CLIPBOARD_CHARS = 10000


def _default_clipboard():
    import pyperclip
    return pyperclip.paste()


def resolve_variables(text, clipboard_getter=None):
    out = text.replace("{date}", time.strftime("%x"))
    out = out.replace("{time}", time.strftime("%H:%M"))
    if "{clipboard}" in out:
        try:
            clip = (clipboard_getter or _default_clipboard)() or ""
        except Exception:
            clip = ""
        clip = str(clip)[:MAX_CLIPBOARD_CHARS]
        out = out.replace("{clipboard}", clip)
    return out


def uses_clipboard(text):
    return isinstance(text, str) and "{clipboard}" in text


def expand(text, snippets, keyword="snippet", clipboard_getter=None):
    if not snippets or not isinstance(snippets, dict):
        return text
    table = {k.lower(): v for k, v in snippets.items()
             if isinstance(k, str) and isinstance(v, str)}

    def sub(match):
        name = match.group(1).lower()
        if name in table:
            return resolve_variables(table[name], clipboard_getter)
        return match.group(0)

    # both trigger forms in ONE sub: re.sub never rescans replacement text,
    # so expansions containing "/name" or "keyword name" stay literal
    pattern = (r"(?<!\S)(?:" + re.escape(keyword)
               + r"\s+|/)([A-Za-z0-9-]{1,30})\b")
    return re.sub(pattern, sub, text, flags=re.IGNORECASE)


def validate(name, expansion, existing):
    if not NAME_RE.match(name or ""):
        return "names are 1-30 letters, digits or dashes"
    if not expansion or len(expansion) > MAX_EXPANSION:
        return f"expansions are 1-{MAX_EXPANSION} characters"
    lower_existing = {k.lower() for k in existing}
    if len(existing) >= MAX_SNIPPETS and (name or "").lower() not in lower_existing:
        return f"limited to {MAX_SNIPPETS} snippets"
    return None


def _collision_name(name, lower):
    if name.lower() not in lower:
        return name
    for i in range(2, 100):
        candidate = f"{name}-{i}"
        if candidate.lower() not in lower:
            return candidate
    return None


def validate_pack(incoming, existing):
    accepted = {}
    summary = {"added": 0, "renamed": 0, "skipped": 0, "clipboard": []}
    if not isinstance(incoming, dict):
        summary["skipped"] = 1
        return accepted, summary
    lower = {k.lower() for k in existing if isinstance(k, str)}
    for name, text in incoming.items():
        if not isinstance(name, str) or not isinstance(text, str):
            summary["skipped"] += 1
            continue
        target = _collision_name(name, lower)
        if target is None:
            summary["skipped"] += 1
            continue
        if target != name:
            summary["renamed"] += 1
        err = validate(target, text, {**existing, **accepted})
        if err:
            summary["skipped"] += 1
            continue
        accepted[target] = text
        lower.add(target.lower())
        summary["added"] += 1
        if uses_clipboard(text):
            summary["clipboard"].append(target)
    return accepted, summary
