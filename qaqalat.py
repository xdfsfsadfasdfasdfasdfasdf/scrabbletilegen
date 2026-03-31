import os
import collections
import math

# --------- PARSERS FOR NEW INPUTS ---------
def parse_valid_counts(s):
    s = s.strip()
    if not s:
        return None
    # Accept commas and/or spaces
    parts = s.replace(",", " ").split()
    vals = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        try:
            vals.append(int(part))
        except ValueError:
            pass
    return sorted(set(vals), reverse=True) if vals else None

def parse_maps(s):
    """
    Syntax: "a=â y=ý" meaning:
      â -> a
      ý -> y
    (right side is mapped to left side, one char each)
    """
    s = s.strip()
    if not s:
        return {}
    mapping = {}
    parts = s.split()
    for part in parts:
        if "=" not in part:
            continue
        left, right = part.split("=", 1)
        left = left.strip()
        right = right.strip()
        if len(left) == 1 and len(right) == 1:
            mapping[right] = left
    return mapping

def parse_graphs(s):
    """
    Syntax: "ch sh th" or "لا لآ لأ لإ"
    Returns: ["ch","sh","th"] / [...]
    """
    s = s.strip()
    if not s:
        return []
    return [g for g in s.split() if g]

# --------- GENERIC NORMALIZATION / FILTERING ---------
def normalize_char(ch, extra_maps):
    # Ignore whitespace and digits
    if ch.isspace() or ch.isdigit():
        return None

    # Keep any alphabetic character (any script)
    if not ch.isalpha():
        return None

    # Apply explicit maps only (no automatic diacritic stripping)
    if ch in extra_maps:
        ch = extra_maps[ch]

    return ch

def count_letters(path, extra_maps, graphs):
    counter = collections.Counter()
    total_chars = 0

    # Sort graphs by length desc so longer ones match first
    graphs = sorted(set(graphs), key=len, reverse=True)

    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            i = 0
            L = len(line)
            while i < L:
                matched = False

                # Try graphs first (case-sensitive; change if you want)
                if graphs:
                    for g in graphs:
                        gl = len(g)
                        if i + gl <= L and line[i:i+gl] == g:
                            counter[g] += 1
                            total_chars += 1
                            i += gl
                            matched = True
                            break

                if matched:
                    continue

                ch = line[i]
                i += 1
                norm = normalize_char(ch, extra_maps)
                if norm is None:
                    continue

                counter[norm] += 1
                total_chars += 1

    return counter, total_chars

# --------- ForcedReductions ---------
def parse_forced_reductions(s):
    """
    Input example:
      "10=1, 8=1, 5=1, 4=2, 3=2, 2=4-3, 1=12-4"
    Output:
      {score: (min_tiles, max_tiles)}
    Rules:
      - "10=1"  => score 10: min=1, max=1
      - "2=4-3" => score 2: min=3, max=4
    """
    s = s.strip()
    if not s:
        return {}

    result = {}
    parts = [p.strip() for p in s.split(",") if p.strip()]
    for part in parts:
        if "=" not in part:
            continue
        score_str, range_str = part.split("=", 1)
        score_str = score_str.strip()
        range_str = range_str.strip()
        if not score_str or not range_str:
            continue
        try:
            score = int(score_str)
        except ValueError:
            continue

        if "-" in range_str:
            max_str, min_str = range_str.split("-", 1)
            try:
                max_tiles = int(max_str.strip())
                min_tiles = int(min_str.strip())
            except ValueError:
                continue
        else:
            try:
                max_tiles = int(range_str)
            except ValueError:
                continue
            min_tiles = 1

        if min_tiles > max_tiles:
            min_tiles, max_tiles = max_tiles, min_tiles

        result[score] = (min_tiles, max_tiles)

    return result

# --------- TILE DISTRIBUTION ---------
def frequencies_to_tiles(letter_counts, total_tiles, blanks, norm_power=1.0):
    items = [(ch, cnt) for ch, cnt in letter_counts.items() if cnt > 0]
    if not items:
        return {}

    weights = []
    for ch, cnt in items:
        w = cnt ** norm_power
        weights.append((ch, w))

    total_letter_tiles = total_tiles - blanks
    total_weight = sum(w for _, w in weights)
    if total_weight <= 0:
        return {}

    raw_tiles = {}
    for ch, w in weights:
        raw = (w / total_weight) * total_letter_tiles
        raw_tiles[ch] = raw

    tile_counts = {ch: max(1, int(round(raw))) for ch, raw in raw_tiles.items()}
    diff = sum(tile_counts.values()) - total_letter_tiles

    # Fix rounding errors
    sorted_letters = [ch for ch, _ in sorted(weights, key=lambda x: x[1], reverse=True)]
    idx = 0
    direction = -1 if diff > 0 else 1
    diff = abs(diff)

    while diff > 0 and sorted_letters:
        ch = sorted_letters[idx % len(sorted_letters)]
        new_val = tile_counts[ch] + direction
        if new_val >= 1:
            tile_counts[ch] = new_val
            diff -= 1
        idx += 1

    return tile_counts

# --------- SCORE ASSIGNMENT ---------
def frequencies_to_scores(letter_counts, score_values):
    items = [(ch, cnt) for ch, cnt in letter_counts.items() if cnt > 0]
    if not items:
        return {}

    items.sort(key=lambda x: x[1], reverse=True)
    n_letters = len(items)
    n_scores = len(score_values)

    if n_scores == 1:
        return {ch: score_values[0] for ch, _ in items}

    scores_map = {}
    for idx, (ch, _) in enumerate(items):
        bucket = int(idx / n_letters * n_scores)
        if bucket >= n_scores:
            bucket = n_scores - 1
        scores_map[ch] = score_values[bucket]

    return scores_map

# --------- ForcedReductions APPLICATION ---------
def apply_forced_reductions(tile_counts, score_map, forced_ranges, total_tiles, blanks):
    if not forced_ranges:
        return tile_counts

    clamped = tile_counts.copy()
    for ch, cnt in tile_counts.items():
        score = score_map.get(ch)
        if score is None:
            continue
        if score in forced_ranges:
            min_t, max_t = forced_ranges[score]
            new_cnt = max(min_t, min(max_t, cnt))
            clamped[ch] = new_cnt

    total_letter_tiles = total_tiles - blanks
    current_sum = sum(clamped.values())
    diff = current_sum - total_letter_tiles

    direction = -1 if diff > 0 else 1
    diff = abs(diff)
    if diff == 0:
        return clamped

    letters = list(clamped.keys())

    def sort_key(ch):
        return (score_map.get(ch, 0), -tile_counts.get(ch, 0))

    letters.sort(key=sort_key)

    idx = 0
    while diff > 0 and letters:
        ch = letters[idx % len(letters)]
        score = score_map.get(ch)
        cnt = clamped[ch]

        if score in forced_ranges:
            min_t, max_t = forced_ranges[score]
        else:
            min_t, max_t = 1, max(1, cnt * 2)

        new_cnt = cnt + direction
        if new_cnt < min_t or new_cnt > max_t:
            idx += 1
            if idx > len(letters) * 5:
                break
            continue

        clamped[ch] = new_cnt
        diff -= 1
        idx += 1

    return clamped

# --------- VALID COUNTS SNAPPING ---------
def snap_to_valid_counts(tile_counts, valid_counts, total_tiles, blanks):
    if not valid_counts:
        return tile_counts

    snapped = {}
    for ch, cnt in tile_counts.items():
        best_v = valid_counts[0]
        best_d = abs(cnt - best_v)
        for v in valid_counts[1:]:
            d = abs(cnt - v)
            if d < best_d:
                best_d = d
                best_v = v
        snapped[ch] = max(1, best_v)

    total_letter_tiles = total_tiles - blanks
    current_sum = sum(snapped.values())
    diff = current_sum - total_letter_tiles
    if diff == 0:
        return snapped

    direction = -1 if diff > 0 else 1
    diff = abs(diff)

    valid_sorted = sorted(valid_counts)
    def next_up(v):
        for x in valid_sorted:
            if x > v:
                return x
        return v

    def next_down(v):
        for x in reversed(valid_sorted):
            if x < v:
                return x
        return v

    letters = list(snapped.keys())
    idx = 0
    guard = 0
    while diff > 0 and guard < len(letters) * 20:
        ch = letters[idx % len(letters)]
        cur = snapped[ch]
        if direction < 0:
            new_v = next_down(cur)
        else:
            new_v = next_up(cur)

        if new_v != cur and new_v >= 1:
            change = abs(new_v - cur)
            snapped[ch] = new_v
            diff -= change
            if diff < 0:
                diff = 0
        idx += 1
        guard += 1

    return snapped

# --------- MAIN ---------
def main():
    # Colors
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RESET = "\033[0m"

    print(CYAN + "Scrabble-style Tile Generator" + RESET)
    print()

    path_str = input("» Path? ")
    path_str = path_str.strip().strip('"')
    if not path_str:
        print("No path provided.")
        return
    if not os.path.exists(path_str):
        print(f"Path not found: {path_str}")
        return

    try:
        total_tiles = int(input("» How many tiles? "))
    except ValueError:
        print("Invalid number for tiles.")
        return

    try:
        blanks = int(input("» Blanks? "))
    except ValueError:
        print("Invalid number for blanks.")
        return

    scores_str = input("» Scores (comma-separated, e.g. 1,2,3,4,5,8,10)? ")
    try:
        score_values = [int(x.strip()) for x in scores_str.split(",") if x.strip()]
        score_values = sorted(set(score_values))
    except ValueError:
        print("Invalid scores.")
        return

    fr_str = input("» ForcedReductions? (e.g. 10=1, 8=1, 5=1, 4=2, 3=2, 2=4-3, 1=12-4) ")
    forced_ranges = parse_forced_reductions(fr_str)

    norm_str = input("» Norm? (0.8–0.9 recommended, leave blank for 1.0) ")
    if norm_str.strip():
        try:
            norm_power = float(norm_str.strip())
        except ValueError:
            print("Invalid norm, using 1.0.")
            norm_power = 1.0
    else:
        norm_power = 1.0

    vc_str = input("» ValidCounts? (e.g. 12,9,8,6,4,3,2,1 or 12 9 8 6 4 3 2 1; leave blank for none) ")
    valid_counts = parse_valid_counts(vc_str)

    maps_str = input("» Maps? (e.g. a=â y=ý; right side maps to left; leave blank for none) ")
    extra_maps = parse_maps(maps_str)

    graphs_str = input("» Graphs? (space-separated like: ch sh th or لا لآ لأ لإ; leave blank for none) ")
    graphs = parse_graphs(graphs_str)

    if blanks < 0 or blanks > total_tiles:
        print("Blanks must be between 0 and total tiles.")
        return
    if not score_values:
        print("You must provide at least one score value.")
        return

    print("\n" + YELLOW + "Reading and analyzing wordlist…" + RESET)
    letter_counts, total_chars = count_letters(path_str, extra_maps, graphs)
    if not letter_counts:
        print("No letters found in the wordlist.")
        return

    tile_counts = frequencies_to_tiles(letter_counts, total_tiles, blanks, norm_power)
    score_map = frequencies_to_scores(letter_counts, score_values)

    if forced_ranges:
        tile_counts = apply_forced_reductions(tile_counts, score_map, forced_ranges, total_tiles, blanks)

    if valid_counts:
        tile_counts = snap_to_valid_counts(tile_counts, valid_counts, total_tiles, blanks)

    print("\n" + GREEN + "» Generated tile counts:" + RESET)
    tiles_by_count = collections.defaultdict(list)
    for ch, cnt in tile_counts.items():
        tiles_by_count[cnt].append(ch)
    for cnt in sorted(tiles_by_count.keys(), reverse=True):
        letters = " ".join(sorted(tiles_by_count[cnt], key=lambda c: c))
        print(f"{letters}: {cnt}")
    print(f"blanks: {blanks}")

    print("\n" + GREEN + "» Generated scores:" + RESET)
    scores_by_value = collections.defaultdict(list)
    for ch, sc in score_map.items():
        scores_by_value[sc].append(ch)
    for sc in sorted(scores_by_value.keys()):
        letters = " ".join(sorted(scores_by_value[sc], key=lambda c: c))
        print(f"{letters}: {sc}")

if __name__ == "__main__":
    main()
