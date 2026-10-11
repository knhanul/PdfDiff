from pathlib import Path

INVALID_CHARS = set('\\/:*?"<>|')
RESERVED_NAMES = {"CON", "PRN", "AUX", "NUL"} | {f"COM{i}" for i in range(1, 10)} | {f"LPT{i}" for i in range(1, 10)}


def build_new_name(original_name, find, replace, prefix, suffix, number=None, digits=3, number_at_end=False):
    """확장자는 유지하고 이름만 바꾼다."""
    path = Path(original_name)
    stem = path.stem
    if find:
        stem = stem.replace(find, replace)
    stem = f"{prefix}{stem}{suffix}"
    if number is not None:
        token = str(number).zfill(max(1, digits))
        stem = f"{stem}_{token}" if number_at_end else f"{token}_{stem}"
    stem = clean_stem(stem)
    if not stem:
        stem = "이름없음"
    if stem.upper() in RESERVED_NAMES:
        stem += "_"
    return stem + path.suffix


def direct_name(original_name, typed):
    """사용자가 입력한 이름으로 바꾼다. 확장자를 생략하면 원래 확장자를 유지한다."""
    original = Path(original_name)
    typed = (typed or "").strip().replace("\\", "").replace("/", "")
    if not typed:
        return original.name
    typed_path = Path(typed)
    if typed_path.suffix:
        suffix = "." + "".join(ch for ch in typed_path.suffix[1:] if ch not in INVALID_CHARS and ord(ch) >= 32)
        stem = clean_stem(typed_path.stem)
    else:
        suffix = original.suffix
        stem = clean_stem(typed)
    if not stem:
        stem = "이름없음"
    if stem.upper() in RESERVED_NAMES:
        stem += "_"
    return stem + suffix


def clean_stem(stem):
    cleaned = "".join(ch for ch in stem if ch not in INVALID_CHARS and ord(ch) >= 32)
    return cleaned.strip().rstrip(".")


def unique_name(directory, name, reserved_names, source=None, freeing_paths=()):
    """같은 폴더에 이미 있거나 이번 작업에서 쓰는 이름은 번호를 붙여 피한다."""
    directory = Path(directory)
    source_resolved = Path(source).resolve() if source else None
    freeing = set(freeing_paths)
    candidate = name
    number = 2
    while True:
        dest = directory / candidate
        resolved = dest.resolve() if dest.exists() else None
        same_file = resolved is not None and resolved == source_resolved
        freed = resolved is not None and resolved in freeing
        occupied = dest.exists() and not same_file and not freed
        if candidate.lower() not in reserved_names and not occupied:
            break
        candidate = f"{Path(name).stem}_{number}{Path(name).suffix}"
        number += 1
    reserved_names.add(candidate.lower())
    return candidate
