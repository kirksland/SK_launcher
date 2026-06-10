from __future__ import annotations

from typing import Dict


DEFAULT_USER_PROFILE: Dict[str, str] = {
    "display_name": "",
    "email": "",
    "role": "",
    "studio": "",
    "bio": "",
}


def normalize_user_profile(raw: object) -> Dict[str, str]:
    profile = dict(DEFAULT_USER_PROFILE)
    if not isinstance(raw, dict):
        return profile

    for key in profile:
        value = raw.get(key)
        if isinstance(value, str):
            profile[key] = value.strip()
    return profile


def profile_initials(profile: object) -> str:
    normalized = normalize_user_profile(profile)
    name = normalized["display_name"]
    if not name:
        return "SF"

    words = [word for word in name.replace("-", " ").split() if word]
    if not words:
        return "SF"
    if len(words) == 1:
        return words[0][:2].upper()
    return f"{words[0][0]}{words[-1][0]}".upper()
