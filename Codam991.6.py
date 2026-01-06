import curses
import time
import sys
import os
import random
from collections import deque
import uuid
import base64

# ================== CONFIG ==================

# --- Board Settings ---
WIDTH = 10
HEIGHT = 20

# --- Timing Settings ---
TICK = 0.60
READ_INTERVAL = 0.05
LEADERBOARD_REFRESH = 2.0
GARBAGE_DELAY = 0.5
LOCK_DELAY = 0.5
LOCK_DELAY_RESETS = 15
MESSAGE_DISPLAY_TIME = 3.0
COUNTDOWN_SECONDS = 3
COUNTDOWN_GO_DELAY = 0.5
SPIN_MESSAGE_DURATION = 1.5
LOOP_SLEEP = 0.01

# --- Speed Progression Settings ---
LINES_PER_SPEEDUP = 5
SPEEDUP_AMOUNT = 0.05
MIN_TICK = 0.01

# --- KO System Settings ---
BASE_KO_MULTIPLIER = 1.0
KO_MULTIPLIER_INCREMENT = 0.2
KO_CHECK_INTERVAL = 0.5
DEATH_FILE_CLEANUP = 30.0

# --- Multiplayer Settings ---
SHARED_DIR = "/sgoinfre/lusteur/tetris"
GARBAGE_BUFFER_PIECES = 3

# --- Remote Player Display Settings ---
STATE_PUBLISH_INTERVAL = 0.1
STATE_STALE_TIMEOUT = 2.0
STATE_CLEANUP_TIMEOUT = 5.0
SHOW_REMOTE_PLAYERS = True
REMOTE_BOARD_SPACING = 4

# --- Visual Settings ---
BLOCK_SIZE = 2
BLOCK_CHAR = "██"
EMPTY_CHAR = "  "
WALL_CHAR = "#"
BORDER_H_CHAR = "-"
BORDER_V_CHAR = "|"
CORNER_CHAR = "+"
GHOST_ENABLED = True
GHOST_DIM = True
TITLE_TEXT = "★ CODAM 99 ★"
WELCOME_TEXT = "Welcome to CODAM 99"

# --- Keybind Profiles ---
KEYBIND_PROFILES = {
    "default": {
        "left": ord('a'),
        "right": ord('d'),
        "rotate_cw": ord('w'),
        "rotate_ccw": None,
        "soft_drop": ord('s'),
        "hard_drop": ord(' '),
        "hold": ord('c'),
        "quit": ord('q'),
        "pause": None,
        "cycle_left": ord('['),
        "cycle_right": ord(']'),
    },
    "spectator": {
        "next_player": ord('d'),
        "prev_player": ord('a'),
        "toggle_auto": ord('t'),
        "zoom_in": ord('w'),
        "zoom_out": ord('s'),
        "quit": ord('q'),
    },
    "multiplayer": {
        "left": ord('a'),
        "right": ord('d'),
        "rotate_cw": ord('w'),
        "rotate_ccw": None,
        "soft_drop": ord('s'),
        "hard_drop": ord(' '),
        "hold": ord('c'),
        "quit": ord('q'),
        "pause": None,
        "target_next": ord('e'),
        "target_prev": ord('r'),
        "target_random": ord('t'),
        "target_attacker": ord('y'),
        "cycle_left": ord('['),
        "cycle_right": ord(']'),
    },
    "splitscreen_p1": {
        "left": ord('a'),
        "right": ord('d'),
        "rotate_cw": ord('w'),
        "rotate_ccw": ord('q'),
        "soft_drop": ord('s'),
        "hard_drop": ord(' '),
        "hold": ord('c'),
        "quit": ord('`'),
        "pause": ord('p'),
    },
    "splitscreen_p2": {
        "left": ord('j'),
        "right": ord('l'),
        "rotate_cw": ord('i'),
        "rotate_ccw": ord('u'),
        "soft_drop": ord('k'),
        "hard_drop": ord('\n'),
        "hold": ord('/'),
        "quit": ord('\\'),
        "pause": ord('p'),
    },
    "arrow_keys": {
        "left": curses.KEY_LEFT,
        "right": curses.KEY_RIGHT,
        "rotate_cw": curses.KEY_UP,
        "rotate_ccw": ord('w'),
        "soft_drop": curses.KEY_DOWN,
        "hard_drop": ord(' '),
        "hold": ord('c'),
        "quit": ord('q'),
        "pause": ord('p'),
        "cycle_left": ord('['),
        "cycle_right": ord(']'),
    },
    "vim": {
        "left": ord('h'),
        "right": ord('l'),
        "rotate_cw": ord('k'),
        "rotate_ccw": ord('j'),
        "soft_drop": ord('j'),
        "hard_drop": ord(' '),
        "hold": ord('f'),
        "quit": ord('q'),
        "pause": ord('p'),
        "cycle_left": ord('['),
        "cycle_right": ord(']'),
    },
}

ACTIVE_PROFILE = "arrow_keys"
SPLITSCREEN_P1_PROFILE = "splitscreen_p1"
SPLITSCREEN_P2_PROFILE = "splitscreen_p2"
SPECTATOR_PROFILE = "spectator"

# --- Color Configuration ---
USE_COLORS = True
COLOR_PAIRS = {
    1: (curses.COLOR_CYAN, -1),
    2: (curses.COLOR_YELLOW, -1),
    3: (curses.COLOR_MAGENTA, -1),
    4: (curses.COLOR_GREEN, -1),
    5: (curses.COLOR_RED, -1),
    6: (curses.COLOR_BLUE, -1),
    7: (curses.COLOR_YELLOW, -1),
    8: (curses.COLOR_WHITE, -1),
    9: (curses.COLOR_WHITE, -1),
    10: (curses.COLOR_RED, -1),
    11: (curses.COLOR_YELLOW, -1),
    12: (curses.COLOR_GREEN, -1),
}

# --- Custom Garbage Messages ---
GARBAGE_MESSAGES = [
    "{player} sent you {lines} lines!",
    "{player} attacks with {lines} garbage!",
    "{player} says: Take {lines} lines!",
    "Incoming {lines} lines from {player}!",
    "{player} is not playing nice: {lines} lines!",
]

# --- KO Messages ---
KO_MESSAGES = [
    "You KO'd {player}! ({kos} total)",
    "{player} eliminated! KO x{kos}",
    "KO! {player} is out! ({kos})",
]

# ============== END CONFIG ==================

# ============== GAME STATE ENCODING ==============
# 
# NEW FORMAT with color preservation (815 bits = 102 bytes → ~136 base64 chars):
# - Bits 0-799: Board cells (4 bits per cell, values 0-8 for colors)
# - Bits 800-802: Piece index (3 bits)
# - Bits 803-804: Rotation (2 bits)
# - Bits 805-809: X position + 4 (5 bits)
# - Bits 810-814: Y position + 4 (5 bits)
#
# Cell color values: 0=empty, 1-7=piece colors (I,O,T,S,Z,J,L), 8=garbage (gray)

PIECE_NAMES = ["I", "O", "T", "S", "Z", "J", "L"]

def encode_game_state(board, piece_name, rotation, piece_x, piece_y):
    """
    Encode full renderable game state as Base64url string.
    Preserves cell colors (4 bits per cell).
    """
    bits = []
    
    # Board: 4 bits per cell (0=empty, 1-7=piece colors, 8=garbage)
    for row in board:
        for cell in row:
            cell_val = min(15, max(0, cell))  # Clamp to 4 bits
            for i in range(3, -1, -1):
                bits.append((cell_val >> i) & 1)
    
    # Piece index (3 bits)
    piece_idx = PIECE_NAMES.index(piece_name) if piece_name in PIECE_NAMES else 0
    for i in range(2, -1, -1):
        bits.append((piece_idx >> i) & 1)
    
    # Rotation (2 bits)
    rot = rotation % 4
    bits.append((rot >> 1) & 1)
    bits.append(rot & 1)
    
    # X position + 4 (5 bits)
    x_enc = max(0, min(31, piece_x + 4))
    for i in range(4, -1, -1):
        bits.append((x_enc >> i) & 1)
    
    # Y position + 4 (5 bits)
    y_enc = max(0, min(31, piece_y + 4))
    for i in range(4, -1, -1):
        bits.append((y_enc >> i) & 1)
    
    # Pack bits into bytes
    byte_array = bytearray()
    for i in range(0, len(bits), 8):
        byte_val = 0
        for j in range(8):
            if i + j < len(bits):
                byte_val |= (bits[i + j] << (7 - j))
        byte_array.append(byte_val)
    
    return base64.urlsafe_b64encode(bytes(byte_array)).decode('ascii').rstrip('=')


def decode_game_state(encoded):
    """
    Decode Base64url string back to renderable game state.
    Preserves cell colors.
    """
    padding = (4 - len(encoded) % 4) % 4
    padded = encoded + '=' * padding
    
    try:
        byte_array = base64.urlsafe_b64decode(padded)
    except Exception:
        return None
    
    bits = []
    for byte_val in byte_array:
        for j in range(8):
            bits.append((byte_val >> (7 - j)) & 1)
    
    # Need at least 815 bits for new format
    if len(bits) < 815:
        return None
    
    # Decode board (4 bits per cell, preserving colors)
    board = []
    bit_idx = 0
    for r in range(HEIGHT):
        row = []
        for c in range(WIDTH):
            cell_val = 0
            for i in range(4):
                cell_val = (cell_val << 1) | bits[bit_idx + i]
            bit_idx += 4
            row.append(cell_val)  # Preserves actual color value
        board.append(row)
    
    # Decode piece index (3 bits)
    piece_idx = (bits[bit_idx] << 2) | (bits[bit_idx + 1] << 1) | bits[bit_idx + 2]
    bit_idx += 3
    piece_name = PIECE_NAMES[piece_idx] if piece_idx < len(PIECE_NAMES) else "I"
    
    # Decode rotation (2 bits)
    rotation = (bits[bit_idx] << 1) | bits[bit_idx + 1]
    bit_idx += 2
    
    # Decode X position (5 bits)
    x_enc = 0
    for i in range(5):
        x_enc = (x_enc << 1) | bits[bit_idx + i]
    piece_x = x_enc - 4
    bit_idx += 5
    
    # Decode Y position (5 bits)
    y_enc = 0
    for i in range(5):
        y_enc = (y_enc << 1) | bits[bit_idx + i]
    piece_y = y_enc - 4
    
    # Reconstruct shape and color
    shape = [row[:] for row in TETROMINOES[piece_name]]
    shape = rotate_piece(shape, rotation)
    color = COLORS.get(piece_name, 7)
    
    return {
        'board': board,
        'piece_name': piece_name,
        'rotation': rotation,
        'piece_x': piece_x,
        'piece_y': piece_y,
        'shape': shape,
        'color': color
    }


def publish_game_state(board, piece_name, rotation, piece_x, piece_y):
    """Publish encoded game state to shared filesystem."""
    try:
        for fname in os.listdir(SHARED_DIR):
            if fname.startswith(f"state_{PLAYER}_") and fname.endswith(".txt"):
                try:
                    os.remove(f"{SHARED_DIR}/{fname}")
                except:
                    pass
        
        encoded = encode_game_state(board, piece_name, rotation, piece_x, piece_y)
        timestamp = time.time()
        filename = f"state_{PLAYER}_{timestamp}_{encoded}.txt"
        open(f"{SHARED_DIR}/{filename}", "w").close()
    except:
        pass


def cleanup_state_file():
    """Remove our state file on exit."""
    try:
        for fname in os.listdir(SHARED_DIR):
            if fname.startswith(f"state_{PLAYER}_") and fname.endswith(".txt"):
                try:
                    os.remove(f"{SHARED_DIR}/{fname}")
                except:
                    pass
    except:
        pass


# Global cache for remote player states - prevents flicker from momentary read failures
_remote_state_cache = {}
_remote_state_timestamps = {}

def get_remote_player_states():
    """
    Read all other players' game states from shared filesystem.
    Returns dict: player_name -> decoded_state
    Uses caching to prevent flicker from momentary file read failures.
    """
    global _remote_state_cache, _remote_state_timestamps
    current_time = time.time()
    fresh_states = {}
    
    try:
        files = os.listdir(SHARED_DIR)
        for fname in files:
            if fname.startswith("state_") and fname.endswith(".txt"):
                try:
                    parts = fname[:-4].split("_", 3)
                    if len(parts) >= 4:
                        player_name = parts[1]
                        timestamp = float(parts[2])
                        encoded = parts[3]
                        
                        if player_name == PLAYER:
                            continue
                        
                        # Skip stale states
                        if current_time - timestamp > STATE_STALE_TIMEOUT:
                            if current_time - timestamp > STATE_CLEANUP_TIMEOUT:
                                try:
                                    os.remove(f"{SHARED_DIR}/{fname}")
                                except:
                                    pass
                            continue
                        
                        state = decode_game_state(encoded)
                        if state:
                            state['player_name'] = player_name
                            state['timestamp'] = timestamp
                            # Keep most recent state per player
                            if player_name not in fresh_states or timestamp > fresh_states[player_name]['timestamp']:
                                fresh_states[player_name] = state
                except:
                    pass
    except:
        pass
    
    # Update cache with fresh states (only update if we got valid new data)
    for player, state in fresh_states.items():
        cached_ts = _remote_state_timestamps.get(player, 0)
        if state['timestamp'] >= cached_ts:
            _remote_state_cache[player] = state
            _remote_state_timestamps[player] = state['timestamp']
    
    # Remove players from cache that are now stale
    stale_players = []
    for player in list(_remote_state_cache.keys()):
        cached_ts = _remote_state_timestamps.get(player, 0)
        if current_time - cached_ts > STATE_STALE_TIMEOUT:
            stale_players.append(player)
    
    for player in stale_players:
        del _remote_state_cache[player]
        if player in _remote_state_timestamps:
            del _remote_state_timestamps[player]
    
    return _remote_state_cache.copy()

# ============== REMOTE PLAYER VIEW MANAGER ==============

class RemotePlayerView:
    """Manages which remote players are displayed on left/right."""
    
    def __init__(self):
        self.left_idx = 0
        self.right_idx = 1
        self.player_list = []
    
    def update(self, states):
        self.player_list = sorted(states.keys())
        n = len(self.player_list)
        if n == 0:
            self.left_idx = 0
            self.right_idx = 1
        else:
            self.left_idx = self.left_idx % n
            self.right_idx = self.right_idx % n if n > 1 else self.left_idx
            if n > 1 and self.left_idx == self.right_idx:
                self.right_idx = (self.left_idx + 1) % n
    
    def cycle_left(self, direction=1):
        n = len(self.player_list)
        if n > 0:
            self.left_idx = (self.left_idx + direction) % n
            if n > 1 and self.left_idx == self.right_idx:
                self.left_idx = (self.left_idx + direction) % n
    
    def cycle_right(self, direction=1):
        n = len(self.player_list)
        if n > 0:
            self.right_idx = (self.right_idx + direction) % n
            if n > 1 and self.right_idx == self.left_idx:
                self.right_idx = (self.right_idx + direction) % n
    
    def get_left_player(self):
        if self.player_list and self.left_idx < len(self.player_list):
            return self.player_list[self.left_idx]
        return None
    
    def get_right_player(self):
        if self.player_list and self.right_idx < len(self.player_list):
            return self.player_list[self.right_idx]
        return None

remote_view = RemotePlayerView()

# ============== KEYBIND HELPERS ==============

def get_keybinds(profile_name=None):
    if profile_name is None:
        profile_name = ACTIVE_PROFILE
    profile = KEYBIND_PROFILES.get(profile_name)
    if profile is None:
        profile = KEYBIND_PROFILES.get("default", {})
    return profile.copy()

def get_splitscreen_keybinds():
    return (get_keybinds(SPLITSCREEN_P1_PROFILE), 
            get_keybinds(SPLITSCREEN_P2_PROFILE))

def key_name(keycode):
    if keycode is None:
        return "---"
    special_keys = {
        ord(' '): "SPACE",
        ord('\n'): "ENTER",
        ord('\t'): "TAB",
        27: "ESC",
        ord('`'): "`",
        ord('\\'): "\\",
        ord('['): "[",
        ord(']'): "]",
    }
    if keycode in special_keys:
        return special_keys[keycode]
    curses_keys = {
        curses.KEY_LEFT: "←",
        curses.KEY_RIGHT: "→",
        curses.KEY_UP: "↑",
        curses.KEY_DOWN: "↓",
    }
    if keycode in curses_keys:
        return curses_keys[keycode]
    if 32 <= keycode <= 126:
        return chr(keycode).upper()
    return f"[{keycode}]"

def format_controls(keybinds, can_hold=True, show_cycle=False):
    left = key_name(keybinds.get("left"))
    right = key_name(keybinds.get("right"))
    rotate = key_name(keybinds.get("rotate_cw"))
    soft = key_name(keybinds.get("soft_drop"))
    hard = key_name(keybinds.get("hard_drop"))
    hold = key_name(keybinds.get("hold"))
    quit_key = key_name(keybinds.get("quit"))
    controls = f"{left}/{right}=Move {rotate}=Rotate {soft}=Soft {hard}=Hard "
    if keybinds.get("hold") is not None:
        controls += f"{hold}=Hold(used) " if not can_hold else f"{hold}=Hold "
    controls += f"{quit_key}=Quit"
    if show_cycle:
        cl = key_name(keybinds.get("cycle_left"))
        cr = key_name(keybinds.get("cycle_right"))
        controls += f" {cl}/{cr}=Cycle"
    return controls

def validate_keybinds(profile_name):
    warnings = []
    keybinds = get_keybinds(profile_name)
    seen = {}
    for action, keycode in keybinds.items():
        if keycode is None:
            continue
        if keycode in seen:
            warnings.append(f"Key conflict: {action}")
        else:
            seen[keycode] = action
    return warnings

def check_splitscreen_conflicts():
    p1_keys = get_keybinds(SPLITSCREEN_P1_PROFILE)
    p2_keys = get_keybinds(SPLITSCREEN_P2_PROFILE)
    conflicts = []
    p1_codes = {v for v in p1_keys.values() if v is not None}
    p2_codes = {v for v in p2_keys.values() if v is not None}
    shared = p1_codes & p2_codes
    allowed_shared = {p1_keys.get("quit"), p1_keys.get("pause"), p2_keys.get("quit"), p2_keys.get("pause")}
    for keycode in shared:
        if keycode not in allowed_shared:
            conflicts.append(key_name(keycode))
    return conflicts

# ============== SPEED SYSTEM ==============

def get_current_tick(total_lines_cleared):
    speedups = total_lines_cleared // LINES_PER_SPEEDUP
    new_tick = TICK - (speedups * SPEEDUP_AMOUNT)
    return max(new_tick, MIN_TICK)

def get_speed_level(total_lines_cleared):
    return (total_lines_cleared // LINES_PER_SPEEDUP) + 1

# ============== KO SYSTEM ==============

def get_ko_multiplier(ko_count):
    return BASE_KO_MULTIPLIER + (ko_count * KO_MULTIPLIER_INCREMENT)

def apply_ko_multiplier(base_garbage, ko_count):
    if base_garbage <= 0:
        return 0
    multiplier = get_ko_multiplier(ko_count)
    return max(1, int(base_garbage * multiplier))

# ============================================

if len(sys.argv) < 2:
    print("Usage: python3 tetris.py <player_name>")
    sys.exit(1)

PLAYER = sys.argv[1]
os.makedirs(SHARED_DIR, exist_ok=True)

last_read_time = 0
last_clear_was_line = False

garbage_queue = []
garbage_messages = []
known_deaths = set()
ko_messages = []

# ============= SRS KICK DATA =============
SRS_KICKS_JLSTZ = {
    (0, 1): [(0, 0), (-1, 0), (-1, -1), (0, 2), (-1, 2)],
    (1, 0): [(0, 0), (1, 0), (1, 1), (0, -2), (1, -2)],
    (1, 2): [(0, 0), (1, 0), (1, 1), (0, -2), (1, -2)],
    (2, 1): [(0, 0), (-1, 0), (-1, -1), (0, 2), (-1, 2)],
    (2, 3): [(0, 0), (1, 0), (1, -1), (0, 2), (1, 2)],
    (3, 2): [(0, 0), (-1, 0), (-1, 1), (0, -2), (-1, -2)],
    (3, 0): [(0, 0), (-1, 0), (-1, 1), (0, -2), (-1, -2)],
    (0, 3): [(0, 0), (1, 0), (1, -1), (0, 2), (1, 2)],
}

SRS_KICKS_I = {
    (0, 1): [(0, 0), (-2, 0), (1, 0), (-2, 1), (1, -2)],
    (1, 0): [(0, 0), (2, 0), (-1, 0), (2, -1), (-1, 2)],
    (1, 2): [(0, 0), (-1, 0), (2, 0), (-1, -2), (2, 1)],
    (2, 1): [(0, 0), (1, 0), (-2, 0), (1, 2), (-2, -1)],
    (2, 3): [(0, 0), (2, 0), (-1, 0), (2, -1), (-1, 2)],
    (3, 2): [(0, 0), (-2, 0), (1, 0), (-2, 1), (1, -2)],
    (3, 0): [(0, 0), (1, 0), (-2, 0), (1, 2), (-2, -1)],
    (0, 3): [(0, 0), (-1, 0), (2, 0), (-1, -2), (2, 1)],
}

TETROMINOES = {
    "I": [[0,0,0,0], [1,1,1,1], [0,0,0,0], [0,0,0,0]],
    "O": [[1,1],[1,1]],
    "T": [[0,1,0],[1,1,1],[0,0,0]],
    "S": [[0,1,1],[1,1,0],[0,0,0]],
    "Z": [[1,1,0],[0,1,1],[0,0,0]],
    "J": [[1,0,0],[1,1,1],[0,0,0]],
    "L": [[0,0,1],[1,1,1],[0,0,0]]
}

COLORS = {
    "I": 1, "O": 2, "T": 3, "S": 4, "Z": 5, "J": 6, "L": 7, "garbage": 8
}

COLORS_INITIALIZED = False

def rotate_matrix(shape):
    return [list(row) for row in zip(*shape[::-1])]

def rotate_piece(shape, times=1):
    result = [row[:] for row in shape]
    for _ in range(times % 4):
        result = rotate_matrix(result)
    return result

def new_board():
    return [[0]*WIDTH for _ in range(HEIGHT)]

def collide(board, shape, x, y):
    for r in range(len(shape)):
        for c in range(len(shape[0])):
            if shape[r][c]:
                nx, ny = x+c, y+r
                if nx < 0 or nx >= WIDTH or ny >= HEIGHT:
                    return True
                if ny >= 0 and board[ny][nx]:
                    return True
    return False

def lock(board, shape, x, y, color):
    for r in range(len(shape)):
        for c in range(len(shape[0])):
            if shape[r][c] and y+r >= 0:
                board[y+r][x+c] = color

def get_piece_bounds(shape):
    min_r, max_r = len(shape), 0
    min_c, max_c = len(shape[0]), 0
    for r in range(len(shape)):
        for c in range(len(shape[0])):
            if shape[r][c]:
                min_r = min(min_r, r)
                max_r = max(max_r, r)
                min_c = min(min_c, c)
                max_c = max(max_c, c)
    return min_r, max_r, min_c, max_c

def check_tspin(board, x, y):
    center_x, center_y = x + 1, y + 1
    corners_filled = 0
    for dx, dy in [(-1, -1), (1, -1), (-1, 1), (1, 1)]:
        check_x, check_y = center_x + dx, center_y + dy
        if check_x < 0 or check_x >= WIDTH or check_y >= HEIGHT:
            corners_filled += 1
        elif check_y < 0:
            continue
        elif board[check_y][check_x]:
            corners_filled += 1
    return corners_filled >= 3

def try_rotation(board, shape, x, y, piece_name, current_rotation, clockwise=True):
    if piece_name == "O":
        return None
    new_rotation = (current_rotation + (1 if clockwise else 3)) % 4
    new_shape = rotate_matrix(shape) if clockwise else rotate_matrix(rotate_matrix(rotate_matrix(shape)))
    kick_table = SRS_KICKS_I if piece_name == "I" else SRS_KICKS_JLSTZ
    kick_key = (current_rotation, new_rotation)
    kicks = kick_table.get(kick_key, [(0, 0)])
    for i, (kick_x, kick_y) in enumerate(kicks):
        new_x = x + kick_x
        new_y = y - kick_y
        if not collide(board, new_shape, new_x, new_y):
            return (new_shape, new_x, new_y, new_rotation, i > 0)
    return None

def clear_lines(board):
    new = [row for row in board if not all(row)]
    cleared = HEIGHT - len(new)
    while len(new) < HEIGHT:
        new.insert(0, [0]*WIDTH)
    return new, cleared

def calculate_garbage(lines_cleared, is_tspin, last_was_line):
    if lines_cleared == 0:
        return 0
    if is_tspin:
        return {1: 2, 2: 4, 3: 6}.get(lines_cleared, 0)
    else:
        if lines_cleared == 1:
            return 1 if last_was_line else 0
        elif lines_cleared == 2:
            return 1
        elif lines_cleared == 3:
            return 2
        elif lines_cleared == 4:
            return 4
    return 0

def add_garbage(board, n):
    for _ in range(n):
        board.pop(0)
        hole_pos = random.randint(0, WIDTH - 1)
        garbage_line = [8 if i != hole_pos else 0 for i in range(WIDTH)]
        board.append(garbage_line)

def queue_garbage(amount, sender="Unknown"):
    global garbage_queue, garbage_messages
    if amount <= 0:
        return
    garbage_queue.append([amount, GARBAGE_BUFFER_PIECES, sender])
    msg_template = random.choice(GARBAGE_MESSAGES)
    msg = msg_template.format(player=sender, lines=amount)
    garbage_messages.append((msg, time.time() + MESSAGE_DISPLAY_TIME))

def process_garbage_queue_on_placement():
    global garbage_queue
    for entry in garbage_queue:
        entry[1] -= 1

def apply_ready_garbage(board):
    global garbage_queue
    total_to_apply = 0
    new_queue = []
    for entry in garbage_queue:
        if entry[1] <= 0:
            total_to_apply += entry[0]
        else:
            new_queue.append(entry)
    garbage_queue = new_queue
    if total_to_apply > 0:
        add_garbage(board, total_to_apply)
    return total_to_apply

def reduce_garbage_queue(lines_cleared):
    global garbage_queue
    if lines_cleared <= 0 or not garbage_queue:
        return
    remaining = lines_cleared
    while remaining > 0 and garbage_queue:
        if garbage_queue[0][0] <= remaining:
            remaining -= garbage_queue[0][0]
            garbage_queue.pop(0)
        else:
            garbage_queue[0][0] -= remaining
            remaining = 0
    for entry in garbage_queue:
        entry[1] += lines_cleared

def get_garbage_display_info():
    return [(entry[0], entry[1]) for entry in garbage_queue]

def get_active_messages():
    global garbage_messages
    current_time = time.time()
    garbage_messages = [(m, e) for m, e in garbage_messages if e > current_time]
    return [m for m, e in garbage_messages]

def get_ko_messages():
    global ko_messages
    current_time = time.time()
    ko_messages = [(m, e) for m, e in ko_messages if e > current_time]
    return [m for m, e in ko_messages]

def send_garbage(amount):
    if amount <= 0:
        return
    try:
        unique_id = str(uuid.uuid4())[:8]
        timestamp = time.time()
        filename = f"garbage_{PLAYER}_{amount}_{timestamp}_{unique_id}.txt"
        open(f"{SHARED_DIR}/{filename}", "w").close()
    except:
        pass

def check_garbage():
    garbage_list = []
    current_time = time.time()
    try:
        files = os.listdir(SHARED_DIR)
        for fname in files:
            if fname.startswith("garbage_") and fname.endswith(".txt"):
                try:
                    parts = fname.split("_")
                    sender = parts[1]
                    if sender == PLAYER:
                        file_ts = float(parts[3])
                        if current_time - file_ts > GARBAGE_DELAY:
                            os.remove(f"{SHARED_DIR}/{fname}")
                        continue
                    lines = int(parts[2])
                    file_ts = float(parts[3])
                    marker = f"{SHARED_DIR}/.received_{PLAYER}_{fname}"
                    if not os.path.exists(marker):
                        garbage_list.append((lines, sender))
                        open(marker, "w").close()
                    if current_time - file_ts > GARBAGE_DELAY:
                        try:
                            os.remove(f"{SHARED_DIR}/{fname}")
                            if os.path.exists(marker):
                                os.remove(marker)
                        except:
                            pass
                except:
                    pass
    except:
        pass
    return garbage_list

def signal_death():
    try:
        unique_id = str(uuid.uuid4())[:8]
        timestamp = time.time()
        open(f"{SHARED_DIR}/death_{PLAYER}_{timestamp}_{unique_id}.txt", "w").close()
    except:
        pass

def check_deaths(current_ko_count):
    global known_deaths, ko_messages
    new_kos = 0
    current_time = time.time()
    try:
        for fname in os.listdir(SHARED_DIR):
            if fname.startswith("death_") and fname.endswith(".txt"):
                try:
                    parts = fname.split("_")
                    if len(parts) < 4:
                        continue
                    dead_player = parts[1]
                    file_ts = float(parts[2])
                    if dead_player == PLAYER:
                        if current_time - file_ts > DEATH_FILE_CLEANUP:
                            os.remove(f"{SHARED_DIR}/{fname}")
                        continue
                    if fname not in known_deaths:
                        known_deaths.add(fname)
                        new_kos += 1
                        msg = random.choice(KO_MESSAGES).format(player=dead_player, kos=current_ko_count + new_kos)
                        ko_messages.append((msg, time.time() + MESSAGE_DISPLAY_TIME))
                    if current_time - file_ts > DEATH_FILE_CLEANUP:
                        os.remove(f"{SHARED_DIR}/{fname}")
                        known_deaths.discard(fname)
                except:
                    pass
    except:
        pass
    return new_kos

def save_highscore(lines_sent, ko_count):
    try:
        existing_best = 0
        existing_files = []
        for fname in os.listdir(SHARED_DIR):
            if fname.startswith(f"highscore_{PLAYER}_") and fname.endswith(".txt"):
                existing_files.append(fname)
                parts = fname.split("_")
                existing_best = max(existing_best, int(parts[2]))
        if lines_sent > existing_best:
            for f in existing_files:
                os.remove(f"{SHARED_DIR}/{f}")
            unique_id = str(uuid.uuid4())[:8]
            open(f"{SHARED_DIR}/highscore_{PLAYER}_{lines_sent}_{ko_count}_{unique_id}.txt", "w").close()
    except:
        pass

def get_leaderboard():
    scores = {}
    try:
        for fname in os.listdir(SHARED_DIR):
            if fname.startswith("highscore_") and fname.endswith(".txt"):
                parts = fname.split("_")
                if len(parts) >= 5:
                    player = parts[1]
                    lines = int(parts[2])
                    kos = int(parts[3])
                    if player not in scores or lines > scores[player]["lines"]:
                        scores[player] = {"name": player, "lines": lines, "kos": kos}
    except:
        pass
    return sorted(scores.values(), key=lambda x: x["lines"], reverse=True)[:10]

def get_ghost_y(board, shape, x, y):
    ghost_y = y
    while not collide(board, shape, x, ghost_y + 1):
        ghost_y += 1
    return ghost_y

def get_color_attr(color_pair_num):
    if USE_COLORS:
        return curses.color_pair(color_pair_num)
    return 0

# ============== UNIFIED BOARD DRAWING ==============

def draw_board(stdscr, board, shape, x, y, color, offset_x, offset_y, show_ghost=True, player_name=None):
    """
    SINGLE rendering path for any game board - used by both local and remote players.
    Draws: walls, locked cells (with preserved colors), active piece, ghost piece, and optional player name.
    """
    field_width = WIDTH * BLOCK_SIZE + 2
    
    try:
        if player_name:
            name_display = player_name[:WIDTH*2] if len(player_name) > WIDTH*2 else player_name
            name_x = offset_x + (field_width - len(name_display)) // 2
            stdscr.addstr(offset_y - 1, name_x, name_display, curses.A_BOLD)
        
        top_border = WALL_CHAR * field_width
        stdscr.addstr(offset_y, offset_x, top_border)
        
        ghost_y = get_ghost_y(board, shape, x, y) if (show_ghost and GHOST_ENABLED) else y
        
        for r in range(HEIGHT):
            stdscr.addstr(offset_y + r + 1, offset_x, WALL_CHAR)
            
            for c in range(WIDTH):
                cell_x = offset_x + c * BLOCK_SIZE + 1
                cell_y = offset_y + r + 1
                cell_drawn = False
                
                # Draw active piece
                for pr in range(len(shape)):
                    for pc in range(len(shape[0])):
                        if shape[pr][pc] and r == y + pr and c == x + pc:
                            stdscr.addstr(cell_y, cell_x, BLOCK_CHAR, get_color_attr(color))
                            cell_drawn = True
                            break
                    if cell_drawn:
                        break
                
                # Draw ghost piece
                if not cell_drawn and show_ghost and GHOST_ENABLED and ghost_y != y:
                    for pr in range(len(shape)):
                        for pc in range(len(shape[0])):
                            if shape[pr][pc] and r == ghost_y + pr and c == x + pc:
                                ghost_attr = get_color_attr(9)
                                if GHOST_DIM:
                                    ghost_attr |= curses.A_DIM
                                stdscr.addstr(cell_y, cell_x, BLOCK_CHAR, ghost_attr)
                                cell_drawn = True
                                break
                        if cell_drawn:
                            break
                
                # Draw locked cells with their original colors
                if not cell_drawn:
                    cell_color = board[r][c]
                    if cell_color:
                        # Use the stored color value directly (1-7 for pieces, 8 for garbage)
                        stdscr.addstr(cell_y, cell_x, BLOCK_CHAR, get_color_attr(cell_color))
                    else:
                        stdscr.addstr(cell_y, cell_x, EMPTY_CHAR)
            
            stdscr.addstr(offset_y + r + 1, offset_x + field_width - 1, WALL_CHAR)
        
        stdscr.addstr(offset_y + HEIGHT + 1, offset_x, top_border)
        
    except curses.error:
        pass


def draw_preview(stdscr, shape, piece_name, row_offset, col_offset, title):
    try:
        stdscr.addstr(row_offset, col_offset, title)
        box_width = 4 * BLOCK_SIZE + 2
        stdscr.addstr(row_offset + 1, col_offset, CORNER_CHAR + BORDER_H_CHAR * box_width + CORNER_CHAR)
        for i in range(4):
            stdscr.addstr(row_offset + 2 + i, col_offset, BORDER_V_CHAR + " " * box_width + BORDER_V_CHAR)
        stdscr.addstr(row_offset + 6, col_offset, CORNER_CHAR + BORDER_H_CHAR * box_width + CORNER_CHAR)
        if shape and piece_name:
            color = COLORS.get(piece_name, 7)
            min_r, max_r, min_c, max_c = get_piece_bounds(shape)
            piece_h = max_r - min_r + 1
            piece_w = max_c - min_c + 1
            y_off = 2 + (4 - piece_h) // 2 - min_r
            x_off = col_offset + 1 + (box_width - piece_w * BLOCK_SIZE) // 2 - min_c * BLOCK_SIZE
            for r in range(len(shape)):
                for c in range(len(shape[0])):
                    if shape[r][c]:
                        stdscr.addstr(row_offset + y_off + r, x_off + c * BLOCK_SIZE, BLOCK_CHAR, get_color_attr(color))
    except curses.error:
        pass

def draw_countdown(stdscr, count):
    max_y, max_x = stdscr.getmaxyx()
    stdscr.clear()
    welcome_y = max_y // 2 - 2
    welcome_x = (max_x - len(WELCOME_TEXT)) // 2
    countdown_msg = str(count) if count > 0 else "GO!"
    countdown_y = max_y // 2
    countdown_x = (max_x - len(countdown_msg)) // 2
    try:
        stdscr.addstr(welcome_y, welcome_x, WELCOME_TEXT, curses.A_BOLD | get_color_attr(1))
        stdscr.addstr(countdown_y, countdown_x, countdown_msg, curses.A_BOLD)
        stdscr.refresh()
    except curses.error:
        pass

def draw_garbage_indicator(stdscr, garbage_info, offset_x, offset_y):
    if not garbage_info:
        return
    indicator_col = offset_x - 4
    if indicator_col < 0:
        indicator_col = 0
    current_row = offset_y + HEIGHT
    for lines, pieces_remaining in reversed(garbage_info):
        color_pair = 10 if pieces_remaining <= 1 else (11 if pieces_remaining == 2 else 12)
        for _ in range(lines):
            if current_row > offset_y:
                try:
                    stdscr.addstr(current_row, indicator_col, BLOCK_CHAR, get_color_attr(color_pair) | curses.A_BOLD)
                except curses.error:
                    pass
                current_row -= 1

def draw(stdscr, board, shape, piece_name, x, y, garbage_info, next_shape, next_piece_name, 
         held_shape, held_piece_name, can_hold, color, spin_message, total_lines, 
         total_lines_sent, ko_count, speed_level, leaderboard, messages, keybinds,
         remote_states=None, left_player=None, right_player=None):
    """Draw the complete game state with optional remote players on left/right."""
    max_y, max_x = stdscr.getmaxyx()
    
    field_width = WIDTH * BLOCK_SIZE + 2
    field_height = HEIGHT + 2
    preview_width = 20
    leaderboard_width = 28
    garbage_indicator_width = 5
    
    has_left = SHOW_REMOTE_PLAYERS and remote_states and left_player and left_player in remote_states
    has_right = SHOW_REMOTE_PLAYERS and remote_states and right_player and right_player in remote_states
    
    left_width = (field_width + REMOTE_BOARD_SPACING) if has_left else 0
    right_width = (field_width + REMOTE_BOARD_SPACING) if has_right else 0
    
    center_x = max_x // 2
    local_field_x = center_x - field_width // 2
    offset_x = max(local_field_x, garbage_indicator_width + left_width)
    offset_y = max((max_y - field_height - 7) // 2, 3)
    
    try:
        stdscr.erase()
        
        # Draw left remote player
        if has_left:
            rs = remote_states[left_player]
            left_x = offset_x - field_width - REMOTE_BOARD_SPACING
            if left_x >= 0:
                draw_board(stdscr, rs['board'], rs['shape'], rs['piece_x'], rs['piece_y'], 
                          rs['color'], left_x, offset_y, show_ghost=True, player_name=left_player)
        
        # Draw local player title
        title_x = offset_x + (field_width - len(TITLE_TEXT)) // 2
        stdscr.addstr(offset_y - 2, title_x, TITLE_TEXT, curses.A_BOLD | get_color_attr(1))
        
        # Draw local player board using the SAME draw_board function
        draw_board(stdscr, board, shape, x, y, color, offset_x, offset_y, show_ghost=True)
        
        draw_garbage_indicator(stdscr, garbage_info, offset_x, offset_y)
        
        preview_col = offset_x + field_width + 2
        hold_title = f"HOLD ({key_name(keybinds.get('hold'))})"
        draw_preview(stdscr, held_shape, held_piece_name, offset_y, preview_col, hold_title)
        draw_preview(stdscr, next_shape, next_piece_name, offset_y + 8, preview_col, "NEXT")
        
        stats_y = offset_y + 16
        ko_mult = get_ko_multiplier(ko_count)
        stdscr.addstr(stats_y, preview_col, f"Lines Sent: {total_lines_sent}")
        stdscr.addstr(stats_y + 1, preview_col, f"KOs: {ko_count} (x{ko_mult:.1f})")
        stdscr.addstr(stats_y + 2, preview_col, f"Speed: Lv.{speed_level}")
        if remote_states:
            stdscr.addstr(stats_y + 3, preview_col, f"Players: {len(remote_states) + 1}")
        
        leaderboard_col = preview_col + preview_width + 2
        stdscr.addstr(offset_y, leaderboard_col, "=== TOP 10 ===")
        stdscr.addstr(offset_y + 1, leaderboard_col, f"{'#':<3}{'Name':<9}{'Sent':<6}{'KO'}")
        
        for i, entry in enumerate(leaderboard[:10]):
            row_y = offset_y + 2 + i
            rank_text = f"{i+1:<3}{entry['name'][:8]:<9}{entry['lines']:<6}{entry['kos']}"
            if entry['name'] == PLAYER:
                stdscr.addstr(row_y, leaderboard_col, rank_text, curses.A_BOLD | get_color_attr(4))
            else:
                stdscr.addstr(row_y, leaderboard_col, rank_text)
        
        # Draw right remote player
        if has_right:
            rs = remote_states[right_player]
            right_x = leaderboard_col + leaderboard_width + REMOTE_BOARD_SPACING
            if right_x + field_width < max_x:
                draw_board(stdscr, rs['board'], rs['shape'], rs['piece_x'], rs['piece_y'],
                          rs['color'], right_x, offset_y, show_ghost=True, player_name=right_player)
        
        info_y = offset_y + HEIGHT + 3
        total_queued = sum(e[0] for e in garbage_info)
        stdscr.addstr(info_y, offset_x, f"Player: {PLAYER}  Lines: {total_lines}  Sent: {total_lines_sent}  KOs: {ko_count}  ")
        
        if total_queued > 0:
            min_buffer = min(e[1] for e in garbage_info) if garbage_info else 0
            stdscr.addstr(info_y + 1, offset_x, f"Garbage queued: {total_queued} (in {min_buffer} pieces)    ")
        else:
            stdscr.addstr(info_y + 1, offset_x, " " * 45)
        
        if spin_message:
            stdscr.addstr(info_y + 2, offset_x, f"{spin_message}!                    ", curses.A_BOLD | get_color_attr(3))
        else:
            stdscr.addstr(info_y + 2, offset_x, " " * 30)
        
        show_cycle = remote_states and len(remote_states) > 2
        controls = format_controls(keybinds, can_hold, show_cycle)
        stdscr.addstr(info_y + 3, offset_x, controls)
        
        msg_y = offset_y
        all_msgs = messages + get_ko_messages()
        for i, msg in enumerate(all_msgs[:5]):
            if msg_y + i < max_y - 1:
                try:
                    max_len = (offset_x - left_width - 6) if has_left else (offset_x - 6)
                    if max_len > 0:
                        display_msg = msg[:max_len] if len(msg) > max_len else msg
                        msg_color = 4 if "KO" in msg else 5
                        stdscr.addstr(msg_y + i, 1, display_msg, get_color_attr(msg_color))
                except curses.error:
                    pass
        
    except curses.error:
        pass
    
    stdscr.refresh()


def main(stdscr):
    global garbage_queue, last_read_time, last_clear_was_line, COLORS_INITIALIZED, remote_view
    
    curses.curs_set(0)
    stdscr.nodelay(True)
    
    if not COLORS_INITIALIZED:
        curses.start_color()
        curses.use_default_colors()
        if USE_COLORS:
            for pair_num, (fg, bg) in COLOR_PAIRS.items():
                try:
                    curses.init_pair(pair_num, fg, bg)
                except curses.error:
                    pass
        COLORS_INITIALIZED = True
    
    keybinds = get_keybinds()
    validate_keybinds(ACTIVE_PROFILE)
    
    for i in range(COUNTDOWN_SECONDS, 0, -1):
        draw_countdown(stdscr, i)
        time.sleep(1)
    draw_countdown(stdscr, 0)
    time.sleep(COUNTDOWN_GO_DELAY)
    
    board = new_board()
    total_lines = 0
    total_lines_sent = 0
    ko_count = 0
    last_ko_check = time.time()
    last_state_publish = time.time()
    remote_states = {}
    
    def refill_bag():
        piece_names = list(TETROMINOES.keys())
        random.shuffle(piece_names)
        return piece_names
    
    piece_bag = refill_bag()
    
    current_piece_name = piece_bag.pop(0)
    current_rotation = 0
    shape = [row[:] for row in TETROMINOES[current_piece_name]]
    
    if not piece_bag:
        piece_bag = refill_bag()
    next_piece_name = piece_bag[0]
    next_shape = [row[:] for row in TETROMINOES[next_piece_name]]
    
    held_shape = None
    held_piece_name = None
    can_hold = True
    spin_message = ""
    spin_message_time = 0
    
    current_color = COLORS[current_piece_name]
    
    x = WIDTH // 2 - len(shape[0]) // 2
    y = 0
    
    while not any(shape[0]):
        shape = shape[1:] + [shape[0]]
        y -= 1
    y = -1
    
    last_tick = time.time()
    soft_drop_active = False
    last_leaderboard_refresh = 0
    leaderboard = []
    
    lock_delay_start = None
    lock_delay_resets = 0
    last_rotation_was_spin = False
    is_hard_drop = False
    
    def spawn_new_piece():
        nonlocal current_piece_name, current_rotation, shape, next_piece_name, next_shape
        nonlocal x, y, can_hold, current_color, lock_delay_start, lock_delay_resets, last_rotation_was_spin
        
        if not piece_bag:
            piece_bag.extend(refill_bag())
        
        current_piece_name = piece_bag.pop(0)
        current_rotation = 0
        shape = [row[:] for row in TETROMINOES[current_piece_name]]
        
        if not piece_bag:
            piece_bag.extend(refill_bag())
        next_piece_name = piece_bag[0]
        next_shape = [row[:] for row in TETROMINOES[next_piece_name]]
        
        current_color = COLORS[current_piece_name]
        x = WIDTH // 2 - len(shape[0]) // 2
        y = -1
        can_hold = True
        lock_delay_start = None
        lock_delay_resets = 0
        last_rotation_was_spin = False
        
        if collide(board, shape, x, y + 1):
            return False
        return True
    
    try:
        while True:
            current_time = time.time()
            
            current_tick = get_current_tick(total_lines)
            speed_level = get_speed_level(total_lines)
            
            if spin_message and current_time - spin_message_time > SPIN_MESSAGE_DURATION:
                spin_message = ""
            
            if current_time - last_ko_check >= KO_CHECK_INTERVAL:
                last_ko_check = current_time
                new_kos = check_deaths(ko_count)
                ko_count += new_kos
            
            if current_time - last_state_publish >= STATE_PUBLISH_INTERVAL:
                last_state_publish = current_time
                publish_game_state(board, current_piece_name, current_rotation, x, y)
            
            key = stdscr.getch()
            soft_drop_active = False
            is_hard_drop = False
            moved_or_rotated = False
            
            if key == keybinds.get("quit"):
                signal_death()
                save_highscore(total_lines_sent, ko_count)
                cleanup_state_file()
                break
            if key == keybinds.get("left") and not collide(board, shape, x-1, y):
                x -= 1
                moved_or_rotated = True
            if key == keybinds.get("right") and not collide(board, shape, x+1, y):
                x += 1
                moved_or_rotated = True
            if key == keybinds.get("rotate_cw"):
                result = try_rotation(board, shape, x, y, current_piece_name, current_rotation, clockwise=True)
                if result:
                    shape, x, y, current_rotation, _ = result
                    moved_or_rotated = True
                    if current_piece_name == "T":
                        last_rotation_was_spin = check_tspin(board, x, y)
                    else:
                        last_rotation_was_spin = False
            if key == keybinds.get("rotate_ccw"):
                result = try_rotation(board, shape, x, y, current_piece_name, current_rotation, clockwise=False)
                if result:
                    shape, x, y, current_rotation, _ = result
                    moved_or_rotated = True
                    if current_piece_name == "T":
                        last_rotation_was_spin = check_tspin(board, x, y)
                    else:
                        last_rotation_was_spin = False
            if key == keybinds.get("soft_drop"):
                soft_drop_active = True
            if key == keybinds.get("hard_drop"):
                while not collide(board, shape, x, y+1):
                    y += 1
                is_hard_drop = True
            if key == keybinds.get("hold") and can_hold:
                if held_shape is None:
                    held_shape = [row[:] for row in TETROMINOES[current_piece_name]]
                    held_piece_name = current_piece_name
                    if not piece_bag:
                        piece_bag.extend(refill_bag())
                    current_piece_name = piece_bag.pop(0)
                    current_rotation = 0
                    shape = [row[:] for row in TETROMINOES[current_piece_name]]
                    if not piece_bag:
                        piece_bag.extend(refill_bag())
                    next_piece_name = piece_bag[0]
                    next_shape = [row[:] for row in TETROMINOES[next_piece_name]]
                else:
                    shape = [row[:] for row in TETROMINOES[held_piece_name]]
                    held_shape = [row[:] for row in TETROMINOES[current_piece_name]]
                    current_piece_name, held_piece_name = held_piece_name, current_piece_name
                    current_rotation = 0
                current_color = COLORS[current_piece_name]
                x = WIDTH // 2 - len(shape[0]) // 2
                y = -1
                can_hold = False
                lock_delay_start = None
                lock_delay_resets = 0
                last_rotation_was_spin = False
            
            if key == keybinds.get("cycle_left"):
                remote_view.cycle_left()
            if key == keybinds.get("cycle_right"):
                remote_view.cycle_right()
            
            if moved_or_rotated and lock_delay_start is not None and lock_delay_resets < LOCK_DELAY_RESETS:
                lock_delay_start = current_time
                lock_delay_resets += 1
            
            tick_speed = current_tick / 50 if soft_drop_active else current_tick
            
            should_lock = False
            
            if current_time - last_tick >= tick_speed:
                last_tick = current_time
                if not collide(board, shape, x, y+1):
                    y += 1
                    if lock_delay_start is not None:
                        lock_delay_start = None
                else:
                    if lock_delay_start is None:
                        lock_delay_start = current_time
                    elif current_time - lock_delay_start >= LOCK_DELAY:
                        should_lock = True
            
            if is_hard_drop and collide(board, shape, x, y+1):
                should_lock = True
            
            if should_lock:
                is_tspin = False
                if current_piece_name == "T":
                    is_tspin = check_tspin(board, x, y) and last_rotation_was_spin
                
                lock(board, shape, x, y, current_color)
                board, cleared = clear_lines(board)
                total_lines += cleared
                
                base_garbage = calculate_garbage(cleared, is_tspin, last_clear_was_line)
                garbage_to_send = apply_ko_multiplier(base_garbage, ko_count) if base_garbage > 0 else 0
                
                if is_tspin and cleared > 0:
                    spin_names = {1: "SINGLE", 2: "DOUBLE", 3: "TRIPLE"}
                    spin_message = f"T-SPIN {spin_names.get(cleared, '')} (+{garbage_to_send})"
                    spin_message_time = current_time
                elif is_tspin:
                    spin_message = "T-SPIN"
                    spin_message_time = current_time
                elif cleared == 4:
                    spin_message = f"TETRIS! (+{garbage_to_send})"
                    spin_message_time = current_time
                elif cleared > 0 and garbage_to_send > 0:
                    spin_message = f"+{garbage_to_send} lines"
                    spin_message_time = current_time
                
                if garbage_to_send > 0:
                    send_garbage(garbage_to_send)
                    total_lines_sent += garbage_to_send
                
                if cleared > 0:
                    reduce_garbage_queue(cleared)
                
                last_clear_was_line = (cleared > 0)
                
                process_garbage_queue_on_placement()
                apply_ready_garbage(board)
                
                publish_game_state(board, current_piece_name, current_rotation, x, y)
                
                if not spawn_new_piece():
                    signal_death()
                    save_highscore(total_lines_sent, ko_count)
                    cleanup_state_file()
                    break
            
            if current_time - last_read_time >= READ_INTERVAL:
                last_read_time = current_time
                garbage_list = check_garbage()
                for amount, sender in garbage_list:
                    queue_garbage(amount, sender)
                
                if SHOW_REMOTE_PLAYERS:
                    remote_states = get_remote_player_states()
                    remote_view.update(remote_states)
            
            if current_time - last_leaderboard_refresh >= LEADERBOARD_REFRESH:
                last_leaderboard_refresh = current_time
                leaderboard = get_leaderboard()
            
            garbage_display = get_garbage_display_info()
            messages = get_active_messages()
            
            left_player = remote_view.get_left_player()
            right_player = remote_view.get_right_player()
            
            draw(stdscr, board, shape, current_piece_name, x, y, garbage_display, 
                 next_shape, next_piece_name, held_shape, held_piece_name, 
                 can_hold, current_color, spin_message, total_lines, 
                 total_lines_sent, ko_count, speed_level, leaderboard, messages, keybinds,
                 remote_states, left_player, right_player)
            
            time.sleep(LOOP_SLEEP)
    
    finally:
        cleanup_state_file()

curses.wrapper(main)
