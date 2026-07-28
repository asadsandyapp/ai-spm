"""PII regex rules for web UI mitmproxy (parity with gateway patterns.py).

Patterns for labeled / contextual entities use keyword forms where free-form
matching would be too aggressive.
"""
from __future__ import annotations

import re

MASK_FORMATS: dict[str, str] = {
    "CNIC": "*************",
    "US_SSN": "***-**-****",
    "CREDIT_CARD": "****-****-****-1234",
    "EMAIL_ADDRESS": "***@***.com",
    "PHONE_NUMBER": "***-***-****",
    "DATE_OF_BIRTH": "**/**/****",
    "IP_ADDRESS": "***.***.***.***",
    "IBAN": "****IBAN****",
    "PASSPORT_NUMBER": "********",
    "DRIVER_LICENSE": "********",
    "PERSON_NAME": "[NAME]",
    "STREET_ADDRESS": "[ADDRESS]",
    "TAX_ID": "**-*******",
    "HEALTH_INSURANCE_ID": "********",
    "VEHICLE_PLATE": "********",
    "ONLINE_USERNAME": "[USERNAME]",
    "BIOMETRIC_ID": "[BIOMETRIC]",
    "PLACE_OF_BIRTH": "[PLACE]",
    "MOTHERS_MAIDEN_NAME": "[REDACTED]",
    "GENDER": "[REDACTED]",
    "MARITAL_STATUS": "[REDACTED]",
    "ETHNICITY": "[REDACTED]",
    "SEXUAL_ORIENTATION": "[REDACTED]",
    "RELIGIOUS_POLITICAL": "[REDACTED]",
    "MEDICAL_INFO": "[HEALTH]",
    "EMPLOYMENT": "[EMPLOYMENT]",
    "EDUCATION": "[EDUCATION]",
    "MAC_ADDRESS": "**:**:**:**:**:**",
    "GEOLOCATION": "[GEO]",
    "DEVICE_COOKIE_ID": "[DEVICE_ID]",
    "SOCIAL_HANDLE": "[HANDLE]",
    "PHOTO_VIDEO_ID": "[MEDIA]",
    "LOGIN_CREDENTIALS": "[CREDENTIAL]",
    "PURCHASE_HISTORY": "[PURCHASE]",
    "MEMBERSHIP_ID": "********",
    "BADGE_ID": "********",
    "FACIAL_RECOGNITION_DATA": "[BIOMETRIC]",
}

# Order matters for overlapping digit patterns (CNIC before SSN-like, etc.).
REGEX_PATTERNS: dict[str, re.Pattern[str]] = {
    "CNIC": re.compile(r"\b\d{5}-\d{7}-\d\b"),
    "US_SSN": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "CREDIT_CARD": re.compile(r"\b(?:\d{4}[\s-]?){3}\d{4}\b"),
    "EMAIL_ADDRESS": re.compile(
        r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
    ),
    "PHONE_NUMBER": re.compile(
        r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"
    ),
    "DATE_OF_BIRTH": re.compile(
        r"\b(?:(?:0?[1-9]|1[0-2])[/-](?:0?[1-9]|[12]\d|3[01])[/-](?:19|20)\d{2}"
        r"|(?:19|20)\d{2}[/-](?:0?[1-9]|1[0-2])[/-](?:0?[1-9]|[12]\d|3[01]))\b"
    ),
    "IP_ADDRESS": re.compile(
        r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b"
    ),
    "IBAN": re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{10,30}\b"),
    "PASSPORT_NUMBER": re.compile(r"\b[A-Z]{1,2}\d{6,9}\b"),
    "DRIVER_LICENSE": re.compile(r"\b[A-Z]\d{7,12}\b"),
    "TAX_ID": re.compile(r"\b\d{2}-\d{7}\b"),
    "MAC_ADDRESS": re.compile(
        r"\b(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}\b"
    ),
    "GEOLOCATION": re.compile(
        r"\b-?(?:[1-8]?\d(?:\.\d+)?|90(?:\.0+)?)\s*,\s*-?(?:1[0-7]\d(?:\.\d+)?|"
        r"[1-9]?\d(?:\.\d+)?|180(?:\.0+)?)\b"
    ),
    # Name tokens stay case-sensitive so "I am going" is not treated as a name.
    "PERSON_NAME": re.compile(
        r"(?i)\b(?:my\s+name\s+is|i\s+am|i'm|full\s*name|legal\s*name|name)"
        r"\s*[:=]?\s*(?-i:([A-Z][a-z]+(?:[\s\-'][A-Z][a-z]+){0,3}))\b"
    ),
    "STREET_ADDRESS": re.compile(
        r"(?i)\b\d{1,5}\s+[A-Za-z0-9.'\-]+\s+"
        r"(?:Street|St\.?|Avenue|Ave\.?|Road|Rd\.?|Boulevard|Blvd\.?|Lane|Ln\.?|"
        r"Drive|Dr\.?|Court|Ct\.?|Way|Place|Pl\.?|Terrace|Ter\.?|Circle|Cir\.?|"
        r"Highway|Hwy\.?|Parkway|Pkwy\.?)\b"
        r"(?:\s*,?\s*[A-Za-z .'-]+){0,3}"
        r"(?:\s+\d{5}(?:-\d{4})?)?"
    ),
    "HEALTH_INSURANCE_ID": re.compile(
        r"(?i)\b(?:member\s*(?:id|number|#)|policy\s*(?:id|number|#)|"
        r"health\s*(?:plan|insurance)\s*(?:id|number|#)|medicaid\s*(?:id|#))"
        r"(?:\s*[:=]\s*|\s+is\s+)\s*[A-Z0-9\-]{5,20}\b"
    ),
    "VEHICLE_PLATE": re.compile(
        r"(?i)\b(?:license\s*plate|number\s*plate|reg(?:istration)?\s*(?:no|number|#)|plate)"
        r"(?:\s*[:=]\s*|\s+is\s+)\s*[A-Z0-9\-]{5,10}\b"
    ),
    "ONLINE_USERNAME": re.compile(
        r"(?i)\b(?:user\s*name|username|login\s*name|handle)"
        r"(?:\s*[:=]\s*|\s+is\s+)\s*[A-Za-z0-9._\-]{3,32}\b"
    ),
    "BIOMETRIC_ID": re.compile(
        r"(?i)\b(?:fingerprint|retina\s*scan|iris\s*scan|voice\s*print|voiceprint|"
        r"biometric\s*(?:id|template|data)|palm\s*print)"
        r"(?:\s*[:=]\s*[A-Za-z0-9+/=_\-]{6,})?"
    ),
    "PLACE_OF_BIRTH": re.compile(
        r"(?i)\b(?:place\s+of\s+birth|birth\s*place)"
        r"(?:\s*[:=]\s*|\s+is\s+)\s*[A-Za-z][A-Za-z .,'\-]{1,60}"
        r"|\bborn\s+in\s+[A-Za-z][A-Za-z .,'\-]{1,60}"
        r"|\bborn\s+on\s+\S+\s+in\s+[A-Za-z][A-Za-z .,'\-]{1,40}"
    ),
    "MOTHERS_MAIDEN_NAME": re.compile(
        r"(?i)\b(?:mother'?s?\s+maiden\s+name|maiden\s+name)"
        r"(?:\s*[:=]\s*|\s+is\s+)\s*[A-Za-z][A-Za-z\-']{1,40}"
    ),
    "GENDER": re.compile(
        r"(?i)\b(?:gender|sex)(?:\s*[:=]\s*|\s+is\s+)"
        r"(?:male|female|non[-\s]?binary|other|man|woman|m|f|nb)\b"
        r"|\b(?:i\s+am|i'm)\s+(?:male|female|non[-\s]?binary)\b"
    ),
    "MARITAL_STATUS": re.compile(
        r"(?i)\b(?:marital\s*status)(?:\s*[:=]\s*|\s+is\s+)"
        r"(?:single|married|divorced|widowed|separated|domestic\s+partner)\b"
        r"|\b(?:i\s+am|i'm)\s+(?:single|married|divorced|widowed)\b"
    ),
    "ETHNICITY": re.compile(
        r"(?i)\b(?:ethnicity|race|racial\s*identity)"
        r"(?:\s*[:=]\s*|\s+is\s+)\s*[A-Za-z][A-Za-z /\-]{1,40}"
    ),
    "SEXUAL_ORIENTATION": re.compile(
        r"(?i)\b(?:sexual\s*orientation|orientation)(?:\s*[:=]\s*|\s+is\s+)"
        r"(?:straight|heterosexual|homosexual|gay|lesbian|bisexual|bi|asexual|"
        r"pansexual|queer|other)\b"
    ),
    "RELIGIOUS_POLITICAL": re.compile(
        r"(?i)\b(?:religion|religious\s*affiliation|political\s*(?:party|affiliation)|"
        r"party\s*affiliation)(?:\s*[:=]\s*|\s+is\s+)\s*[A-Za-z][A-Za-z .'\-]{1,40}"
    ),
    "MEDICAL_INFO": re.compile(
        r"(?i)\b(?:diagnosis|diagnosed\s+with|prescription|prescribed|medical\s*record|"
        r"patient\s*id|mrn|condition)(?:\s*[:=]\s*|\s+is\s+|\s+)?"
        r"[A-Za-z0-9][A-Za-z0-9 .,\-/]{2,80}"
    ),
    "EMPLOYMENT": re.compile(
        r"(?i)\b(?:employer|company|works?\s+at|job\s*title|employed\s+(?:at|by))"
        r"(?:\s*[:=]\s*|\s+is\s+|\s+)\s*[A-Za-z0-9][A-Za-z0-9 .,&'\-]{1,60}"
    ),
    "EDUCATION": re.compile(
        r"(?i)\b(?:student\s*(?:id|number|#)|school\s*id|university\s*id|gpa|"
        r"transcript\s*(?:id|#)|enrollment\s*(?:id|#))"
        r"(?:\s*[:=]\s*|\s+is\s+)\s*[A-Za-z0-9.\-]{2,20}\b"
    ),
    "DEVICE_COOKIE_ID": re.compile(
        r"(?i)\b(?:device\s*id|cookie\s*id|client\s*id|session\s*id|advertising\s*id|"
        r"idfa|aaid|android\s*id)(?:\s*[:=]\s*|\s+is\s+)\s*[A-Za-z0-9_\-]{8,64}\b"
    ),
    "SOCIAL_HANDLE": re.compile(
        r"(?i)\b(?:twitter|x|instagram|tiktok|facebook|linkedin|github|snapchat|"
        r"social\s*(?:handle|user|username)|@handle)"
        r"(?:\s*[:=]\s*|\s+is\s*|\s+as\s+)\s*@?[A-Za-z0-9._]{2,30}\b"
        r"|(?<![A-Za-z0-9._])@[A-Za-z0-9_]{3,30}\b"
    ),
    "PHOTO_VIDEO_ID": re.compile(
        r"(?i)\b(?:photo\s*id|image\s*id|video\s*id|media\s*id|face\s*id)"
        r"(?:\s*[:=]\s*|\s+is\s+)\s*[A-Za-z0-9_\-]{6,64}\b"
    ),
    "LOGIN_CREDENTIALS": re.compile(
        r"(?i)\b(?:password|passwd|pwd|passcode|pin|otp|one[-\s]?time\s*password|"
        r"security\s*(?:answer|question)|secret\s*answer)"
        r"(?:\s*[:=]\s*|\s+is\s+)\s*\S{3,64}"
    ),
    "PURCHASE_HISTORY": re.compile(
        r"(?i)\b(?:order\s*(?:id|number|#)|purchase\s*(?:id|number|#)|"
        r"invoice\s*(?:id|number|#)|transaction\s*(?:id|#))"
        r"(?:\s*[:=]\s*|\s+is\s+)\s*[A-Z0-9\-]{5,24}\b"
    ),
    "MEMBERSHIP_ID": re.compile(
        r"(?i)\b(?:membership\s*(?:id|number|#)|loyalty\s*(?:id|number|#)|"
        r"member\s*(?:number|#)|account\s*(?:number|#))"
        r"(?:\s*[:=]\s*|\s+is\s+)\s*[A-Z0-9\-]{5,24}\b"
    ),
    "BADGE_ID": re.compile(
        r"(?i)\b(?:badge\s*(?:id|number|#)|employee\s*(?:id|number|#)|"
        r"staff\s*(?:id|number|#)|access\s*(?:card|id)\s*(?:number|#)?)"
        r"(?:\s*[:=]\s*|\s+is\s+)\s*[A-Z0-9\-]{3,20}\b"
    ),
    "FACIAL_RECOGNITION_DATA": re.compile(
        r"(?i)\b(?:facial\s*recognition|face\s*template|face\s*embedding|"
        r"face\s*vector|faceprint)"
        r"(?:\s*[:=]\s*[A-Za-z0-9+/=_\-]{8,})?"
    ),
}

# Stable apply order: structured IDs first, then labeled context patterns.
ENTITY_APPLY_ORDER: list[str] = [
    "CNIC",
    "US_SSN",
    "TAX_ID",
    "CREDIT_CARD",
    "IBAN",
    "EMAIL_ADDRESS",
    "PHONE_NUMBER",
    "DATE_OF_BIRTH",
    "IP_ADDRESS",
    "MAC_ADDRESS",
    "GEOLOCATION",
    "PASSPORT_NUMBER",
    "DRIVER_LICENSE",
    "LOGIN_CREDENTIALS",
    "HEALTH_INSURANCE_ID",
    "MEMBERSHIP_ID",
    "BADGE_ID",
    "PURCHASE_HISTORY",
    "DEVICE_COOKIE_ID",
    "PHOTO_VIDEO_ID",
    "VEHICLE_PLATE",
    "EDUCATION",
    "ONLINE_USERNAME",
    "SOCIAL_HANDLE",
    "MOTHERS_MAIDEN_NAME",
    "PLACE_OF_BIRTH",
    "PERSON_NAME",
    "STREET_ADDRESS",
    "EMPLOYMENT",
    "MEDICAL_INFO",
    "GENDER",
    "MARITAL_STATUS",
    "ETHNICITY",
    "SEXUAL_ORIENTATION",
    "RELIGIOUS_POLITICAL",
    "BIOMETRIC_ID",
    "FACIAL_RECOGNITION_DATA",
]

ENTITY_AUDIT_LABEL = {
    "US_SSN": "SSN",
}


def iter_patterns_for(entities: list[str] | None = None):
    """Yield (entity_id, pattern, mask) in apply order, optionally filtered."""
    wanted = set(entities) if entities is not None else set(REGEX_PATTERNS)
    for eid in ENTITY_APPLY_ORDER:
        if eid not in wanted:
            continue
        pattern = REGEX_PATTERNS.get(eid)
        if not pattern:
            continue
        yield eid, pattern, MASK_FORMATS.get(eid, f"[{eid}]")
