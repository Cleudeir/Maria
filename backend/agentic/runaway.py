import re
from collections import Counter

# Minimum text length before we even check for runaway
_MIN_LENGTH = 200

# If unique tokens / total tokens is below this ratio, it's runaway
_MIN_UNIQUE_TOKEN_RATIO = 0.10

# If the single most common token accounts for more than this fraction of all
# tokens, it's runaway (normal text has diverse word frequencies)
_MAX_DOMINANT_TOKEN_RATIO = 0.30

# Minimum number of tokens before we check
_MIN_TOKENS_FOR_RATIO = 30

# If any N+ consecutive tokens are identical, it's runaway
_MAX_CONSECUTIVE_IDENTICAL = 6

# Threshold for character-level repetition: same char N+ times in a row
_MAX_CHAR_REPEAT = 30

# Maximum reasonable response length in characters
_MAX_RESPONSE_CHARS = 120_000


def _tokenize(text: str) -> list[str]:
    """Split text into tokens by whitespace, underscores, and common separators."""
    tokens = re.split(r"[\s_,;:.!?()\[\]{}<>=+'\"\\/`@#$%^&|~\n\r\t]+", text)
    return [t for t in tokens if t]


def _max_consecutive_identical(values: list[str]) -> int:
    """Return the longest run of identical consecutive values."""
    if not values:
        return 0
    best = 1
    run = 1
    for i in range(1, len(values)):
        if values[i] == values[i - 1]:
            run += 1
            if run > best:
                best = run
        else:
            run = 1
    return best


def is_runaway_response(text: str) -> bool:
    """Detect if a text contains runaway/generative repetition patterns.

    Uses multiple generic signals — character repetition, token repetition,
    token dominance, and consecutive token identity — with no hardcoded
    patterns or keywords.
    """
    if not text or len(text) < _MIN_LENGTH:
        return False

    # Strategy 1: Absolute size cap (most reliable indicator)
    if len(text) > _MAX_RESPONSE_CHARS:
        return True

    # Strategy 2: Character-level repetition (e.g. "aaaaaa...")
    # Only alpha characters — punctuation, digits, whitespace are normal in code
    for c in set(text.lower()):
        if not c.isalpha():
            continue
        if c * _MAX_CHAR_REPEAT in text:
            return True

    # Strategy 3: Token-level analysis
    tokens = _tokenize(text)
    if len(tokens) < _MIN_TOKENS_FOR_RATIO:
        return False

    # 3a: Unique token ratio — if most tokens are the same, it's repetitive
    unique = set(tokens)
    unique_ratio = len(unique) / len(tokens)
    if unique_ratio < _MIN_UNIQUE_TOKEN_RATIO:
        # 3b: Dominant token ratio — even if unique ratio is low,
        # single-token dominance confirms runaway vs repeated sentences
        counter = Counter(tokens)
        dominant_ratio = counter.most_common(1)[0][1] / len(tokens)
        if dominant_ratio > _MAX_DOMINANT_TOKEN_RATIO:
            return True

    # 3c: Consecutive identical tokens (e.g. "foo foo foo foo foo")
    return _max_consecutive_identical(tokens) >= _MAX_CONSECUTIVE_IDENTICAL


def has_text_loop(text: str, segment_length: int = 30, min_repeats: int = 3) -> bool:
    """Detect if a segment of segment_length characters repeats min_repeats times.

    Only counts non-overlapping segments to avoid false positives from
    normal text that happens to have overlapping 20-char windows.
    """
    if not text or len(text) < segment_length * min_repeats:
        return False
    seen: dict[str, int] = {}
    i = 0
    while i <= len(text) - segment_length:
        segment = text[i:i + segment_length]
        count = seen.get(segment, 0) + 1
        if count >= min_repeats:
            return True
        seen[segment] = count
        i += segment_length
    return False


def truncate_runaway(
    text: str,
    max_chars: int = _MAX_RESPONSE_CHARS,
    head_chars: int = 200,
    tail_chars: int = 200,
) -> str:
    """Truncate a runaway response to a manageable size, keeping head and tail."""
    if len(text) <= max_chars:
        return text
    head = text[:head_chars]
    tail = text[-tail_chars:] if tail_chars > 0 else ""
    truncated_str = f"{len(text)} chars -> {head_chars + tail_chars} chars"
    return f"{head}\n\n[... runaway generation truncated: {truncated_str}]\n\n{tail}"
