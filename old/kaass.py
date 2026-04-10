import curses
import time
import sys
import os
import random
from collections import deque
import uuid
import base64
import getpass

# ================== CONFIG ==================

# --- Board Settings ---
WIDTH = 10
HEIGHT = 20

# --- Timing Settings ---
TICK = 0.60
READ_INTERVAL = 0.05
LEADERBOARD_REFRESH = 2.0
LOCK_DELAY = 0.5
LOCK_DELAY_RESETS = 15
MESSAGE_DISPLAY_TIME = 3.0
COUNTDOWN_SECONDS = 3
COUNTDOWN_GO_DELAY = 0.5
SPIN_MESSAGE_DURATION = 1.5
LOOP_SLEEP = 0.01

# --- Speed Progression Settings ---
LINES_PER_SPEEDUP = 5
SPEEDUP_AMOUNT = 0.02
MIN_TICK = 0.01

# --- KO System Settings ---
BASE_KO_MULTIPLIER = 1.0
KO_MULTIPLIER_INCREMENT = 0.2

# --- Multiplayer Settings ---
SHARED_DIR = "/sgoinfre/lusteur/tetris"
GARBAGE_BUFFER_PIECES = 3

# --- Remote Player Display Settings ---
STATE_PUBLISH_INTERVAL = 0.1
STATE_STALE_TIMEOUT = 2.0
STATE_CLEANUP_TIMEOUT = 5.0
DEAD_STATE_CLEANUP_TIMEOUT = 30.0
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
        "rotate_ccw": ord('e'),
        "soft_drop": ord('s'),
        "hard_drop": ord(' '),
        "hold": ord('c'),
        "quit": ord('q'),
        "pause": None,
        "cycle_target": ord('['),
        "cycle_target_back": ord(']'),
    },
    "arrow_keys": {
        "left": ord('h'),
        "right": ord('l'),
        "rotate_cw": ord('k'),
        "rotate_ccw": ord('w'),
        "soft_drop": ord('j'),
        "hard_drop": ord(' '),
        "hold": ord('c'),
        "quit": ord('q'),
        "pause": ord('p'),
        "cycle_target": ord('['),
        "cycle_target_back": ord(']'),
    },
}

ACTIVE_PROFILE = "arrow_keys"

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

PIECE_NAMES = ["I", "O", "T", "S", "Z", "J", "L"]


def encode_game_state(board, piece_name, rotation, piece_x, piece_y):
    bits = []
    for row in board:
        for cell in row:
            cell_val = min(15, max(0, cell))
            for i in range(3, -1, -1):
                bits.append((cell_val >> i) & 1)
    piece_idx = PIECE_NAMES.index(piece_name) if piece_name in PIECE_NAMES else 0
    for i in range(2, -1, -1):
        bits.append((piece_idx >> i) & 1)
    rot = rotation % 4
    bits.append((rot >> 1) & 1)
    bits.append(rot & 1)
    x_enc = max(0, min(31, piece_x + 4))
    for i in range(4, -1, -1):
        bits.append((x_enc >> i) & 1)
    y_enc = max(0, min(31, piece_y + 4))
    for i in range(4, -1, -1):
        bits.append((y_enc >> i) & 1)
    byte_array = bytearray()
    for i in range(0, len(bits), 8):
        byte_val = 0
        for j in range(8):
            if i + j < len(bits):
                byte_val |= (bits[i + j] << (7 - j))
        byte_array.append(byte_val)
    return base64.urlsafe_b64encode(bytes(byte_array)).decode('ascii').rstrip('=')


def decode_game_state(encoded):
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
    if len(bits) < 815:
        return None
    board = []
    bit_idx = 0
    for r in range(HEIGHT):
        row = []
        for c in range(WIDTH):
            cell_val = 0
            for i in range(4):
                cell_val = (cell_val << 1) | bits[bit_idx + i]
            bit_idx += 4
            row.append(cell_val)
        board.append(row)
    piece_idx = (bits[bit_idx] << 2) | (bits[bit_idx + 1] << 1) | bits[bit_idx + 2]
    bit_idx += 3
    piece_name = PIECE_NAMES[piece_idx] if piece_idx < len(PIECE_NAMES) else "I"
    rotation = (bits[bit_idx] << 1) | bits[bit_idx + 1]
    bit_idx += 2
    x_enc = 0
    for i in range(5):
        x_enc = (x_enc << 1) | bits[bit_idx + i]
    piece_x = x_enc - 4
    bit_idx += 5
    y_enc = 0
    for i in range(5):
        y_enc = (y_enc << 1) | bits[bit_idx + i]
    piece_y = y_enc - 4
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


def get_safe_player_id():
    username = getpass.getuser()
    safe_name = username.replace('_', '-')
    return safe_name


PLAYER = get_safe_player_id()
DISPLAY_NAME = getpass.getuser()

os.makedirs(SHARED_DIR, exist_ok=True)

# ============== UNIFIED STATE FILE SYSTEM ==============
# Format: state_{PLAYER}_{timestamp}_{isDead}_{target}_{garbageToTarget}_{encoded}.txt
#
# isDead: 0 = alive, 1 = dead
# target: current target player name (or "none")
# garbageToTarget: cumulative garbage sent to current target

# Track garbage we've received from each player (cumulative per-sender)
_received_garbage_from = {}

# Track the initial garbage count when we first saw each player (to avoid receiving old garbage)
_player_initial_garbage = {}

# Track players we've already counted as KOs from us
_players_we_kod = set()

# Track garbage ownership in our board (list of sender names per garbage row, bottom-up)
_garbage_row_owners = []  # List of sender names for garbage rows

# Cache for remote player states
_remote_state_cache = {}
_remote_state_timestamps = {}

# Messages
garbage_messages = []
ko_messages = []

# Our session start time (to ignore garbage from before we joined)
_session_start_time = time.time()


def publish_game_state(board, piece_name, rotation, piece_x, piece_y, is_dead=False, 
                       target_player="none", garbage_to_target=0, attackers_garbage=None):
    """
    Publish encoded game state to shared filesystem.
    attackers_garbage: dict of {attacker_name: cumulative_garbage_received}
    """
    try:
        # Clean old state files for this player
        for fname in os.listdir(SHARED_DIR):
            if fname.startswith(f"state_{PLAYER}_") and fname.endswith(".txt"):
                try:
                    os.remove(f"{SHARED_DIR}/{fname}")
                except:
                    pass

        encoded = encode_game_state(board, piece_name, rotation, piece_x, piece_y)
        timestamp = time.time()
        dead_flag = 1 if is_dead else 0
        
        # Encode attackers_garbage as comma-separated "name:amount" pairs
        attackers_str = ""
        if attackers_garbage:
            pairs = [f"{k}:{v}" for k, v in attackers_garbage.items()]
            attackers_str = ",".join(pairs)
        if not attackers_str:
            attackers_str = "x"  # placeholder for empty
        
        # Sanitize target name for filename
        safe_target = target_player.replace('_', '-') if target_player else "none"
        
        # Format: state_{PLAYER}_{timestamp}_{isDead}_{target}_{garbageToTarget}_{attackers}_{encoded}.txt
        filename = f"state_{PLAYER}_{timestamp}_{dead_flag}_{safe_target}_{garbage_to_target}_{attackers_str}_{encoded}.txt"
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


def get_remote_player_states():
    """
    Read all other players' game states from shared filesystem.
    Returns dict: player_name -> decoded_state
    """
    global _remote_state_cache, _remote_state_timestamps
    current_time = time.time()
    fresh_states = {}

    try:
        files = os.listdir(SHARED_DIR)
        for fname in files:
            if fname.startswith("state_") and fname.endswith(".txt"):
                try:
                    # Parse: state_{player}_{timestamp}_{isDead}_{target}_{garbageToTarget}_{attackers}_{encoded}.txt
                    base = fname[:-4]
                    parts = base.split("_", 6)
                    
                    if len(parts) >= 7:
                        player_name = parts[1]
                        timestamp = float(parts[2])
                        is_dead = (parts[3] == "1")
                        target = parts[4] if parts[4] != "none" else None
                        garbage_to_target = int(parts[5])
                        
                        # Parse attackers string
                        attackers_str = parts[6].split("_")[0]  # Get part before encoded
                        attackers_garbage = {}
                        if attackers_str and attackers_str != "x":
                            for pair in attackers_str.split(","):
                                if ":" in pair:
                                    name, amt = pair.split(":", 1)
                                    try:
                                        attackers_garbage[name] = int(amt)
                                    except:
                                        pass
                        
                        # Get encoded part (everything after attackers)
                        rest_parts = parts[6].split("_", 1)
                        encoded = rest_parts[1] if len(rest_parts) > 1 else ""

                        if player_name == PLAYER:
                            continue

                        timeout = DEAD_STATE_CLEANUP_TIMEOUT if is_dead else STATE_STALE_TIMEOUT
                        cleanup_timeout = DEAD_STATE_CLEANUP_TIMEOUT if is_dead else STATE_CLEANUP_TIMEOUT

                        if current_time - timestamp > timeout:
                            if current_time - timestamp > cleanup_timeout:
                                try:
                                    os.remove(f"{SHARED_DIR}/{fname}")
                                except:
                                    pass
                            continue

                        state = decode_game_state(encoded)
                        if state:
                            state['player_name'] = player_name
                            state['timestamp'] = timestamp
                            state['is_dead'] = is_dead
                            state['target'] = target
                            state['garbage_to_target'] = garbage_to_target
                            state['attackers_garbage'] = attackers_garbage
                            
                            if player_name not in fresh_states or timestamp > fresh_states[player_name]['timestamp']:
                                fresh_states[player_name] = state
                except:
                    pass
    except:
        pass

    for player, state in fresh_states.items():
        cached_ts = _remote_state_timestamps.get(player, 0)
        if state['timestamp'] >= cached_ts:
            _remote_state_cache[player] = state
            _remote_state_timestamps[player] = state['timestamp']

    stale_players = []
    for player in list(_remote_state_cache.keys()):
        cached_ts = _remote_state_timestamps.get(player, 0)
        cached_state = _remote_state_cache.get(player, {})
        is_dead = cached_state.get('is_dead', False)
        timeout = DEAD_STATE_CLEANUP_TIMEOUT if is_dead else STATE_STALE_TIMEOUT
        
        if current_time - cached_ts > timeout:
            stale_players.append(player)

    for player in stale_players:
        del _remote_state_cache[player]
        if player in _remote_state_timestamps:
            del _remote_state_timestamps[player]

    return _remote_state_cache.copy()


def process_incoming_garbage(remote_states, my_name):
    """
    Check remote states for new garbage targeted at us.
    Uses cumulative garbage tracking to ensure we receive each garbage send exactly once.
    Only receives garbage from players who are targeting us.
    Returns list of (amount, sender) tuples for new garbage.
    """
    global _received_garbage_from, _player_initial_garbage
    garbage_list = []
    
    for player, state in remote_states.items():
        if state.get('is_dead', False):
            continue
        
        # Only receive garbage if this player is targeting us
        if state.get('target') != my_name:
            continue
        
        cumulative = state.get('garbage_to_target', 0)
        
        # If this is the first time seeing this player, initialize to their current cumulative
        # This prevents receiving old garbage when joining late
        if player not in _player_initial_garbage:
            _player_initial_garbage[player] = cumulative
            _received_garbage_from[player] = cumulative
            continue
        
        last_received = _received_garbage_from.get(player, 0)
        
        if cumulative > last_received:
            new_garbage = cumulative - last_received
            garbage_list.append((new_garbage, player))
            _received_garbage_from[player] = cumulative
    
    return garbage_list


def check_for_kos(remote_states, my_garbage_in_players):
    """
    Check if any player died with our garbage in their board.
    my_garbage_in_players: dict of player_name -> amount of our garbage they've received
    Returns list of newly KO'd player names.
    """
    global _players_we_kod, ko_messages
    new_kos = []
    
    for player, state in remote_states.items():
        if not state.get('is_dead', False):
            continue
        if player in _players_we_kod:
            continue
        
        # Check if this player has received garbage from us (check their attackers_garbage)
        attackers = state.get('attackers_garbage', {})
        if PLAYER in attackers and attackers[PLAYER] > 0:
            # They had our garbage when they died - we get the KO!
            _players_we_kod.add(player)
            new_kos.append(player)
    
    return new_kos


def count_players_targeting_me(remote_states, my_name):
    """Count how many alive players are targeting us."""
    count = 0
    for player, state in remote_states.items():
        if state.get('is_dead', False):
            continue
        if state.get('target') == my_name:
            count += 1
    return count


def cleanup_old_files():
    """Clean up old files from previous versions."""
    current_time = time.time()
    try:
        for fname in os.listdir(SHARED_DIR):
            try:
                if fname.startswith("garbage_") and fname.endswith(".txt"):
                    fpath = f"{SHARED_DIR}/{fname}"
                    if current_time - os.path.getmtime(fpath) > 60:
                        os.remove(fpath)
                if fname.startswith("death_") and fname.endswith(".txt"):
                    fpath = f"{SHARED_DIR}/{fname}"
                    if current_time - os.path.getmtime(fpath) > 60:
                        os.remove(fpath)
                if fname.startswith(".received_"):
                    fpath = f"{SHARED_DIR}/{fname}"
                    if current_time - os.path.getmtime(fpath) > 60:
                        os.remove(fpath)
            except:
                pass
    except:
        pass


class TargetingSystem:
    """Manages target selection for Tetris 99-style targeting."""
    
    def __init__(self):
        self.target_idx = 0
        self.player_list = []
        self.current_target = None
    
    def update(self, remote_states):
        """Update player list with alive players only."""
        alive_players = [k for k, v in remote_states.items() if not v.get('is_dead', False)]
        self.player_list = sorted(alive_players)
        
        if not self.player_list:
            self.current_target = None
            self.target_idx = 0
        else:
            # Keep current target if still valid
            if self.current_target in self.player_list:
                self.target_idx = self.player_list.index(self.current_target)
            else:
                self.target_idx = min(self.target_idx, len(self.player_list) - 1)
                self.current_target = self.player_list[self.target_idx]
    
    def cycle_target(self, direction=1):
        """Cycle to next/previous target."""
        if not self.player_list:
            return
        self.target_idx = (self.target_idx + direction) % len(self.player_list)
        self.current_target = self.player_list[self.target_idx]
    
    def get_target(self):
        """Get current target name."""
        return self.current_target
    
    def get_display_player(self):
        """Get the player to display on the left (same as target)."""
        return self.current_target


class RemotePlayerView:
    """Manages which remote players to display."""
    
    def __init__(self):
        self.right_idx = 0
        self.player_list = []
    
    def update(self, states, target_player=None):
        """Update player list, excluding the target (shown on left)."""
        alive_players = [k for k, v in states.items() 
                        if not v.get('is_dead', False) and k != target_player]
        self.player_list = sorted(alive_players)
        
        if self.player_list:
            self.right_idx = self.right_idx % len(self.player_list)
        else:
            self.right_idx = 0
    
    def cycle_right(self, direction=1):
        """Cycle the right display player."""
        if self.player_list:
            self.right_idx = (self.right_idx + direction) % len(self.player_list)
    
    def get_right_player(self):
        """Get player to show on right side."""
        if self.player_list and self.right_idx < len(self.player_list):
            return self.player_list[self.right_idx]
        return None


targeting = TargetingSystem()
remote_view = RemotePlayerView()


def get_keybinds(profile_name=None):
    if profile_name is None:
        profile_name = ACTIVE_PROFILE
    return KEYBIND_PROFILES.get(profile_name, KEYBIND_PROFILES.get("default", {})).copy()


def key_name(keycode):
    if keycode is None:
        return "---"
    special_keys = {
        ord(' '): "SPACE", ord('\n'): "ENTER", ord('\t'): "TAB", 27: "ESC",
        ord('`'): "`", ord('\\'): "\\", ord('['): "[", ord(']'): "]",
    }
    if keycode in special_keys:
        return special_keys[keycode]
    curses_keys = {
        curses.KEY_LEFT: "←", curses.KEY_RIGHT: "→",
        curses.KEY_UP: "↑", curses.KEY_DOWN: "↓",
    }
    if keycode in curses_keys:
        return curses_keys[keycode]
    if 32 <= keycode <= 126:
        return chr(keycode).upper()
    return f"[{keycode}]"


def format_controls(keybinds, can_hold=True):
    left = key_name(keybinds.get("left"))
    right = key_name(keybinds.get("right"))
    rotate_cw = key_name(keybinds.get("rotate_cw"))
    soft = key_name(keybinds.get("soft_drop"))
    hard = key_name(keybinds.get("hard_drop"))
    hold = key_name(keybinds.get("hold"))
    quit_key = key_name(keybinds.get("quit"))
    cycle = key_name(keybinds.get("cycle_target"))
    
    controls = f"{left}/{right}=Move {rotate_cw}=Rot {soft}=Soft {hard}=Hard "
    controls += f"{hold}=Hold" if can_hold else f"{hold}=Hold(used)"
    controls += f" {cycle}=Target {quit_key}=Quit"
    return controls


def get_current_tick(total_lines_cleared):
    speedups = total_lines_cleared // LINES_PER_SPEEDUP
    new_tick = TICK - (speedups * SPEEDUP_AMOUNT)
    return max(new_tick, MIN_TICK)


def get_speed_level(total_lines_cleared):
    return (total_lines_cleared // LINES_PER_SPEEDUP) + 1


def get_ko_multiplier(ko_count):
    return BASE_KO_MULTIPLIER + (ko_count * KO_MULTIPLIER_INCREMENT)


def apply_ko_multiplier(base_garbage, ko_count):
    if base_garbage <= 0:
        return 0
    multiplier = get_ko_multiplier(ko_count)
    return max(1, int(base_garbage * multiplier))


last_read_time = 0
last_clear_was_line = False
garbage_queue = []

# Track garbage we've received from each player (for KO attribution)
_garbage_received_from = {}  # sender -> total amount received

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
    (0, 1): [(0, 0), (-2, 0), (1, 0), (-2, -1), (1, 2)],
    (1, 0): [(0, 0), (2, 0), (-1, 0), (2, 1), (-1, -2)],
    (1, 2): [(0, 0), (-1, 0), (2, 0), (-1, 2), (2, -1)],
    (2, 1): [(0, 0), (1, 0), (-2, 0), (1, -2), (-2, 1)],
    (2, 3): [(0, 0), (2, 0), (-1, 0), (2, 1), (-1, -2)],
    (3, 2): [(0, 0), (-2, 0), (1, 0), (-2, -1), (1, 2)],
    (3, 0): [(0, 0), (1, 0), (-2, 0), (1, -2), (-2, 1)],
    (0, 3): [(0, 0), (-1, 0), (2, 0), (-1, 2), (2, -1)],
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


def rotate_matrix_ccw(shape):
    return [list(row) for row in zip(*shape)][::-1]


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


def get_front_corners_for_t(rotation):
    front_corners = {
        0: [(-1, -1), (1, -1)],
        1: [(1, -1), (1, 1)],
        2: [(-1, 1), (1, 1)],
        3: [(-1, -1), (-1, 1)],
    }
    return front_corners.get(rotation % 4, [(-1, -1), (1, -1)])


def check_tspin(board, x, y, rotation):
    center_x, center_y = x + 1, y + 1
    corner_positions = [(-1, -1), (1, -1), (-1, 1), (1, 1)]
    corners_filled = 0
    corner_status = {}
    
    for dx, dy in corner_positions:
        check_x, check_y = center_x + dx, center_y + dy
        is_filled = False
        if check_x < 0 or check_x >= WIDTH or check_y >= HEIGHT:
            is_filled = True
        elif check_y >= 0 and board[check_y][check_x]:
            is_filled = True
        corner_status[(dx, dy)] = is_filled
        if is_filled:
            corners_filled += 1
    
    if corners_filled < 3:
        return False, False
    
    front_corners = get_front_corners_for_t(rotation)
    front_filled = sum(1 for fc in front_corners if corner_status.get(fc, False))
    
    is_tspin = True
    is_mini = (front_filled < 2)
    
    return is_tspin, is_mini


def check_spin(board, shape, x, y, piece_name, rotation, kick_idx, rotation_direction):
    if piece_name == "O":
        return None, False
    
    if piece_name == "T":
        is_tspin, is_mini = check_tspin(board, x, y, rotation)
        if is_tspin:
            if kick_idx == 4:
                is_mini = False
            return "T-SPIN", is_mini
        return None, False
    
    if kick_idx == 0:
        return None, False
    
    spin_names = {"S": "S-SPIN", "Z": "Z-SPIN", "I": "I-SPIN", "J": "J-SPIN", "L": "L-SPIN"}
    return spin_names.get(piece_name), True


def try_rotation(board, shape, x, y, piece_name, current_rotation, clockwise=True):
    if piece_name == "O":
        return None
    
    new_rotation = (current_rotation + (1 if clockwise else 3)) % 4
    new_shape = rotate_matrix(shape) if clockwise else rotate_matrix_ccw(shape)
    
    kick_table = SRS_KICKS_I if piece_name == "I" else SRS_KICKS_JLSTZ
    kick_key = (current_rotation, new_rotation)
    kicks = kick_table.get(kick_key, [(0, 0)])
    
    for i, (kick_x, kick_y) in enumerate(kicks):
        new_x = x + kick_x
        new_y = y + kick_y
        if not collide(board, new_shape, new_x, new_y):
            return (new_shape, new_x, new_y, new_rotation, i)
    
    return None


def clear_lines(board):
    new = [row for row in board if not all(row)]
    cleared = HEIGHT - len(new)
    while len(new) < HEIGHT:
        new.insert(0, [0]*WIDTH)
    return new, cleared


def check_perfect_clear(board):
    for row in board:
        for cell in row:
            if cell:
                return False
    return True


def calculate_garbage(lines_cleared, spin_type, is_mini, back_to_back, is_perfect_clear=False):
    if lines_cleared == 0:
        return 0
    
    if is_perfect_clear:
        return 10
    
    base_garbage = 0
    
    if spin_type == "T-SPIN":
        if is_mini:
            base_garbage = {1: 0, 2: 1, 3: 2}.get(lines_cleared, 0)
        else:
            base_garbage = {1: 2, 2: 4, 3: 6}.get(lines_cleared, 0)
    elif spin_type:
        if is_mini:
            base_garbage = {1: 0, 2: 1, 3: 2, 4: 4}.get(lines_cleared, 0)
        else:
            base_garbage = {1: 2, 2: 4, 3: 6, 4: 8}.get(lines_cleared, 0)
    else:
        base_garbage = {1: 0, 2: 1, 3: 2, 4: 4}.get(lines_cleared, 0)
    
    if back_to_back and base_garbage > 0:
        base_garbage += 1
    
    return base_garbage


def add_garbage(board, n, sender="Unknown"):
    """Add garbage lines with one random hole, tracking sender for KO attribution."""
    global _garbage_received_from
    
    for _ in range(n):
        board.pop(0)
        hole_pos = random.randint(0, WIDTH - 1)
        garbage_line = [8 if i != hole_pos else 0 for i in range(WIDTH)]
        board.append(garbage_line)
    
    # Track how much garbage we've received from this sender
    _garbage_received_from[sender] = _garbage_received_from.get(sender, 0) + n


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
    senders = []
    new_queue = []
    
    for entry in garbage_queue:
        if entry[1] <= 0:
            total_to_apply += entry[0]
            senders.append(entry[2])
        else:
            new_queue.append(entry)
    
    garbage_queue = new_queue
    
    if total_to_apply > 0:
        # Apply garbage and track sender
        for sender in senders:
            add_garbage(board, total_to_apply // len(senders), sender)
    
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


def save_highscore(lines_sent, ko_count):
    try:
        existing_best = 0
        existing_files = []
        for fname in os.listdir(SHARED_DIR):
            if fname.startswith(f"highscore_{PLAYER}_") and fname.endswith(".txt"):
                existing_files.append(fname)
                try:
                    parts = fname[:-4].split("_")
                    if len(parts) >= 4:
                        existing_best = max(existing_best, int(parts[2]))
                except:
                    pass
        if lines_sent > existing_best:
            for f in existing_files:
                try:
                    os.remove(f"{SHARED_DIR}/{f}")
                except:
                    pass
            unique_id = str(uuid.uuid4())[:8]
            new_file = f"{SHARED_DIR}/highscore_{PLAYER}_{lines_sent}_{ko_count}_{unique_id}.txt"
            open(new_file, "w").close()
    except:
        pass


def get_leaderboard():
    scores = {}
    try:
        for fname in os.listdir(SHARED_DIR):
            if fname.startswith("highscore_") and fname.endswith(".txt"):
                try:
                    parts = fname[:-4].split("_")
                    if len(parts) >= 5:
                        player = parts[1]
                        lines = int(parts[2])
                        kos = int(parts[3])
                        if player not in scores or lines > scores[player]["lines"]:
                            scores[player] = {"name": player, "lines": lines, "kos": kos}
                except:
                    pass
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


def draw_board(stdscr, board, shape, x, y, color, offset_x, offset_y, show_ghost=True, 
               player_name=None, is_dead=False, is_target=False, is_targeting_me=False):
    field_width = WIDTH * BLOCK_SIZE + 2
    try:
        if player_name:
            name_display = player_name[:WIDTH*2] if len(player_name) > WIDTH*2 else player_name
            if is_dead:
                name_display = f"☠ {name_display} ☠"
            name_x = offset_x + (field_width - len(name_display)) // 2
            attr = curses.A_BOLD
            if is_dead:
                attr |= curses.A_DIM
            stdscr.addstr(offset_y - 1, name_x, name_display, attr)
            
            # Show targeting indicator
            if is_target and not is_dead:
                target_text = "◆ TARGET ◆"
                target_x = offset_x + (field_width - len(target_text)) // 2
                stdscr.addstr(offset_y - 2, target_x, target_text, curses.A_BOLD | get_color_attr(5))
        
        top_border = WALL_CHAR * field_width
        stdscr.addstr(offset_y, offset_x, top_border)
        ghost_y = get_ghost_y(board, shape, x, y) if (show_ghost and GHOST_ENABLED and not is_dead) else y
        
        for r in range(HEIGHT):
            stdscr.addstr(offset_y + r + 1, offset_x, WALL_CHAR)
            for c in range(WIDTH):
                cell_x = offset_x + c * BLOCK_SIZE + 1
                cell_y = offset_y + r + 1
                cell_drawn = False
                
                if not is_dead:
                    for pr in range(len(shape)):
                        for pc in range(len(shape[0])):
                            if shape[pr][pc] and r == y + pr and c == x + pc:
                                stdscr.addstr(cell_y, cell_x, BLOCK_CHAR, get_color_attr(color))
                                cell_drawn = True
                                break
                        if cell_drawn:
                            break
                    
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
                
                if not cell_drawn:
                    cell_color = board[r][c]
                    if cell_color:
                        attr = get_color_attr(cell_color)
                        if is_dead:
                            attr |= curses.A_DIM
                        stdscr.addstr(cell_y, cell_x, BLOCK_CHAR, attr)
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


def get_alive_player_count(remote_states):
    return sum(1 for s in remote_states.values() if not s.get('is_dead', False))


def draw(stdscr, board, shape, piece_name, x, y, garbage_info, next_shape, next_piece_name,
         held_shape, held_piece_name, can_hold, color, spin_message, total_lines,
         total_lines_sent, ko_count, speed_level, leaderboard, messages, keybinds,
         remote_states=None, target_player=None, right_player=None, targeting_me_count=0):
    max_y, max_x = stdscr.getmaxyx()
    field_width = WIDTH * BLOCK_SIZE + 2
    field_height = HEIGHT + 2
    preview_width = 20
    leaderboard_width = 28
    garbage_indicator_width = 5
    
    has_left = SHOW_REMOTE_PLAYERS and remote_states and target_player and target_player in remote_states
    has_right = SHOW_REMOTE_PLAYERS and remote_states and right_player and right_player in remote_states
    
    left_width = (field_width + REMOTE_BOARD_SPACING) if has_left else 0
    center_x = max_x // 2
    local_field_x = center_x - field_width // 2
    offset_x = max(local_field_x, garbage_indicator_width + left_width)
    offset_y = max((max_y - field_height - 7) // 2, 4)
    
    try:
        stdscr.erase()
        
        # Draw target player on left (with TARGET indicator)
        if has_left:
            rs = remote_states[target_player]
            left_x = offset_x - field_width - REMOTE_BOARD_SPACING
            if left_x >= 0:
                draw_board(stdscr, rs['board'], rs['shape'], rs['piece_x'], rs['piece_y'],
                          rs['color'], left_x, offset_y, show_ghost=True, 
                          player_name=target_player, is_dead=rs.get('is_dead', False),
                          is_target=True)
        
        # Draw title
        title_x = offset_x + (field_width - len(TITLE_TEXT)) // 2
        stdscr.addstr(offset_y - 2, title_x, TITLE_TEXT, curses.A_BOLD | get_color_attr(1))
        
        # Draw local board
        draw_board(stdscr, board, shape, x, y, color, offset_x, offset_y, show_ghost=True)
        draw_garbage_indicator(stdscr, garbage_info, offset_x, offset_y)
        
        # Draw preview boxes
        preview_col = offset_x + field_width + 2
        hold_title = f"HOLD ({key_name(keybinds.get('hold'))})"
        draw_preview(stdscr, held_shape, held_piece_name, offset_y, preview_col, hold_title)
        draw_preview(stdscr, next_shape, next_piece_name, offset_y + 8, preview_col, "NEXT")
        
        # Stats
        stats_y = offset_y + 16
        ko_mult = get_ko_multiplier(ko_count)
        stdscr.addstr(stats_y, preview_col, f"Lines Sent: {total_lines_sent}")
        stdscr.addstr(stats_y + 1, preview_col, f"KOs: {ko_count} (x{ko_mult:.1f})")
        stdscr.addstr(stats_y + 2, preview_col, f"Speed: Lv.{speed_level}")
        
        if remote_states:
            alive_count = get_alive_player_count(remote_states)
            total_count = len(remote_states)
            stdscr.addstr(stats_y + 3, preview_col, f"Alive: {alive_count + 1}/{total_count + 1}")
        
        # Targeting me indicator
        if targeting_me_count > 0:
            targeting_text = f"⚠ {targeting_me_count} TARGETING YOU ⚠"
            stdscr.addstr(stats_y + 4, preview_col, targeting_text, curses.A_BOLD | get_color_attr(5))
        
        # Leaderboard
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
        
        # Draw right player
        if has_right:
            rs = remote_states[right_player]
            right_x = leaderboard_col + leaderboard_width + REMOTE_BOARD_SPACING
            if right_x + field_width < max_x:
                draw_board(stdscr, rs['board'], rs['shape'], rs['piece_x'], rs['piece_y'],
                          rs['color'], right_x, offset_y, show_ghost=True,
                          player_name=right_player, is_dead=rs.get('is_dead', False))
        
        # Info bar
        info_y = offset_y + HEIGHT + 3
        total_queued = sum(e[0] for e in garbage_info)
        
        target_display = target_player if target_player else "None"
        stdscr.addstr(info_y, offset_x, f"Player: {DISPLAY_NAME}  Target: {target_display}  Lines: {total_lines}")
        
        if total_queued > 0:
            min_buffer = min(e[1] for e in garbage_info) if garbage_info else 0
            stdscr.addstr(info_y + 1, offset_x, f"Garbage queued: {total_queued} (in {min_buffer} pieces)    ")
        else:
            stdscr.addstr(info_y + 1, offset_x, " " * 45)
        
        if spin_message:
            stdscr.addstr(info_y + 2, offset_x, f"{spin_message}!                    ", curses.A_BOLD | get_color_attr(3))
        else:
            stdscr.addstr(info_y + 2, offset_x, " " * 30)
        
        controls = format_controls(keybinds, can_hold)
        stdscr.addstr(info_y + 3, offset_x, controls)
        
        # Messages
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
    global garbage_queue, last_read_time, last_clear_was_line, COLORS_INITIALIZED
    global targeting, remote_view, _garbage_received_from, ko_messages

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
    cleanup_old_files()

    for i in range(COUNTDOWN_SECONDS, 0, -1):
        draw_countdown(stdscr, i)
        time.sleep(1)
    draw_countdown(stdscr, 0)
    time.sleep(COUNTDOWN_GO_DELAY)

    board = new_board()
    total_lines = 0
    total_lines_sent = 0
    garbage_sent_to_target = 0  # Cumulative garbage sent to current target
    ko_count = 0
    last_state_publish = time.time()
    remote_states = {}
    back_to_back = False
    is_dead = False

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
    last_rotation_kick = 0
    last_rotation_direction = None
    last_action_was_rotation = False
    is_hard_drop = False

    def spawn_new_piece():
        nonlocal current_piece_name, current_rotation, shape, next_piece_name, next_shape
        nonlocal x, y, can_hold, current_color, lock_delay_start, lock_delay_resets
        nonlocal last_rotation_kick, last_rotation_direction, last_action_was_rotation

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
        last_rotation_kick = 0
        last_rotation_direction = None
        last_action_was_rotation = False

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

            # Get current target
            current_target = targeting.get_target()

            # Publish state regularly
            if current_time - last_state_publish >= STATE_PUBLISH_INTERVAL:
                last_state_publish = current_time
                publish_game_state(
                    board, current_piece_name, current_rotation, x, y,
                    is_dead, current_target or "none", garbage_sent_to_target,
                    _garbage_received_from
                )

            key = stdscr.getch()
            soft_drop_active = False
            is_hard_drop = False
            moved_or_rotated = False

            if key == keybinds.get("quit"):
                is_dead = True
                publish_game_state(
                    board, current_piece_name, current_rotation, x, y,
                    is_dead, current_target or "none", garbage_sent_to_target,
                    _garbage_received_from
                )
                save_highscore(total_lines_sent, ko_count)
                cleanup_state_file()
                break
            
            if key == keybinds.get("left") and not collide(board, shape, x-1, y):
                x -= 1
                moved_or_rotated = True
                last_action_was_rotation = False
            
            if key == keybinds.get("right") and not collide(board, shape, x+1, y):
                x += 1
                moved_or_rotated = True
                last_action_was_rotation = False
            
            if key == keybinds.get("rotate_cw"):
                result = try_rotation(board, shape, x, y, current_piece_name, current_rotation, clockwise=True)
                if result:
                    shape, x, y, current_rotation, kick_idx = result
                    moved_or_rotated = True
                    last_rotation_kick = kick_idx
                    last_rotation_direction = 'cw'
                    last_action_was_rotation = True
            
            if key == keybinds.get("rotate_ccw"):
                result = try_rotation(board, shape, x, y, current_piece_name, current_rotation, clockwise=False)
                if result:
                    shape, x, y, current_rotation, kick_idx = result
                    moved_or_rotated = True
                    last_rotation_kick = kick_idx
                    last_rotation_direction = 'ccw'
                    last_action_was_rotation = True
            
            if key == keybinds.get("soft_drop"):
                soft_drop_active = True
                last_action_was_rotation = False
            
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
                last_rotation_kick = 0
                last_rotation_direction = None
                last_action_was_rotation = False

            # Target cycling with [ and ]
            if key == keybinds.get("cycle_target"):
                targeting.cycle_target(1)
                # Reset garbage counter when switching targets
                garbage_sent_to_target = 0
            
            if key == keybinds.get("cycle_target_back"):
                targeting.cycle_target(-1)
                garbage_sent_to_target = 0

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
                spin_type = None
                is_mini = False
                
                if last_action_was_rotation:
                    spin_type, is_mini = check_spin(
                        board, shape, x, y, current_piece_name, current_rotation,
                        last_rotation_kick, last_rotation_direction
                    )

                lock(board, shape, x, y, current_color)
                board, cleared = clear_lines(board)
                total_lines += cleared

                is_perfect = check_perfect_clear(board) if cleared > 0 else False
                is_difficult = (cleared == 4) or (spin_type is not None and cleared > 0)

                base_garbage = calculate_garbage(cleared, spin_type, is_mini, back_to_back and is_difficult, is_perfect)
                garbage_to_send = apply_ko_multiplier(base_garbage, ko_count) if base_garbage > 0 else 0

                if cleared > 0:
                    back_to_back = is_difficult if is_difficult else False

                if is_perfect:
                    spin_message = f"PERFECT CLEAR! (+{garbage_to_send})"
                    spin_message_time = current_time
                elif spin_type and cleared > 0:
                    spin_names = {1: "SINGLE", 2: "DOUBLE", 3: "TRIPLE", 4: "QUAD"}
                    mini_prefix = "MINI " if is_mini else ""
                    b2b_prefix = "B2B " if back_to_back else ""
                    spin_message = f"{b2b_prefix}{mini_prefix}{spin_type} {spin_names.get(cleared, '')} (+{garbage_to_send})"
                    spin_message_time = current_time
                elif spin_type:
                    spin_message = spin_type
                    spin_message_time = current_time
                elif cleared == 4:
                    b2b_text = "B2B " if back_to_back else ""
                    spin_message = f"{b2b_text}TETRIS! (+{garbage_to_send})"
                    spin_message_time = current_time
                elif cleared > 0 and garbage_to_send > 0:
                    spin_message = f"+{garbage_to_send} lines"
                    spin_message_time = current_time

                if garbage_to_send > 0:
                    garbage_sent_to_target += garbage_to_send
                    total_lines_sent += garbage_to_send
                    publish_game_state(
                        board, current_piece_name, current_rotation, x, y,
                        is_dead, current_target or "none", garbage_sent_to_target,
                        _garbage_received_from
                    )

                if cleared > 0:
                    reduce_garbage_queue(cleared)

                last_clear_was_line = (cleared > 0)

                process_garbage_queue_on_placement()
                apply_ready_garbage(board)

                if not spawn_new_piece():
                    is_dead = True
                    publish_game_state(
                        board, current_piece_name, current_rotation, x, y,
                        is_dead, current_target or "none", garbage_sent_to_target,
                        _garbage_received_from
                    )
                    save_highscore(total_lines_sent, ko_count)
                    cleanup_state_file()
                    break

            # Read remote states and process garbage/deaths
            if current_time - last_read_time >= READ_INTERVAL:
                last_read_time = current_time
                
                if SHOW_REMOTE_PLAYERS:
                    remote_states = get_remote_player_states()
                    targeting.update(remote_states)
                    
                    current_target = targeting.get_target()
                    remote_view.update(remote_states, current_target)
                    
                    # Process incoming garbage (only from players targeting us)
                    garbage_list = process_incoming_garbage(remote_states, PLAYER)
                    for amount, sender in garbage_list:
                        queue_garbage(amount, sender)
                    
                    # Check for KOs (players who died with our garbage)
                    new_ko_players = check_for_kos(remote_states, _garbage_received_from)
                    for player in new_ko_players:
                        ko_count += 1
                        msg = random.choice(KO_MESSAGES).format(player=player, kos=ko_count)
                        ko_messages.append((msg, time.time() + MESSAGE_DISPLAY_TIME))

            if current_time - last_leaderboard_refresh >= LEADERBOARD_REFRESH:
                last_leaderboard_refresh = current_time
                leaderboard = get_leaderboard()

            garbage_display = get_garbage_display_info()
            messages = get_active_messages()

            current_target = targeting.get_target()
            right_player = remote_view.get_right_player()
            targeting_me = count_players_targeting_me(remote_states, PLAYER) if remote_states else 0

            draw(stdscr, board, shape, current_piece_name, x, y, garbage_display,
                 next_shape, next_piece_name, held_shape, held_piece_name,
                 can_hold, current_color, spin_message, total_lines,
                 total_lines_sent, ko_count, speed_level, leaderboard, messages, keybinds,
                 remote_states, current_target, right_player, targeting_me)

            time.sleep(LOOP_SLEEP)

    finally:
        cleanup_state_file()

curses.wrapper(main)
