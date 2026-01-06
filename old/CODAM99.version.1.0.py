import curses
import time
import sys
import os
import random
from collections import deque
import uuid

# ---------------- CONFIG ----------------
WIDTH = 10
HEIGHT = 20
TICK = 0.40
SHARED_DIR = "/sgoinfre/lusteur/tetris"
READ_INTERVAL = 0.05
BLOCK_SIZE = 2  # Each block is [] which is 2 characters
LEADERBOARD_REFRESH = 2.0  # Refresh leaderboard every 2 seconds
GARBAGE_DELAY = 0.5  # Seconds to wait before deleting garbage files (allows multiplayer sync)
GARBAGE_BUFFER_PIECES = 3  # Number of piece placements before garbage is applied

# Lock delay settings (modern Tetris guideline)
LOCK_DELAY = 0.5  # Time before piece locks when touching ground
LOCK_DELAY_RESETS = 15  # Maximum number of lock delay resets per piece

# Custom garbage messages - customize these!
GARBAGE_MESSAGES = [
    "{player} sent you {lines} lines!",
    "{player} attacks with {lines} garbage!",
    "{player} says: Take {lines} lines!",
    "Incoming {lines} lines from {player}!",
    "{player} is not playing nice: {lines} lines!",
]
# ---------------------------------------

if len(sys.argv) < 2:
    print("Usage: python3 tetris.py <player_name>")
    sys.exit(1)

PLAYER = sys.argv[1]
os.makedirs(SHARED_DIR, exist_ok=True)

last_read_time = 0
last_clear_was_line = False  # Track if previous drop cleared a line

# ============= GARBAGE BUFFER SYSTEM =============
garbage_queue = []  # list of [lines, pieces_remaining, sender_name]

# Message queue for displaying garbage notifications
garbage_messages = []  # list of (message, expire_time)
MESSAGE_DISPLAY_TIME = 3.0  # How long to show garbage messages

# ============= SRS KICK DATA (Super Rotation System) =============
# Kick tables for JLSTZ pieces
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

# Kick tables for I piece
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

# Global for colors initialization
COLORS_INITIALIZED = False

def rotate_matrix(shape):
    """Rotate a matrix 90 degrees clockwise"""
    return [list(row) for row in zip(*shape[::-1])]

def rotate_piece(shape, times=1):
    """Rotate shape multiple times"""
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
    """Get the actual bounding box of the piece (ignoring empty rows/cols)"""
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

def check_spin(board, shape, x, y, piece_name, used_kick):
    """Check if the last rotation was a spin (works for all pieces)"""
    # For T-spins, use the 3-corner rule
    if piece_name == "T":
        corners_filled = 0
        center_x, center_y = x + 1, y + 1
        corner_positions = [(-1, -1), (1, -1), (-1, 1), (1, 1)]
        for dx, dy in corner_positions:
            check_x, check_y = center_x + dx, center_y + dy
            if check_x < 0 or check_x >= WIDTH or check_y < 0 or check_y >= HEIGHT:
                corners_filled += 1
            elif check_y >= 0 and board[check_y][check_x]:
                corners_filled += 1
        return corners_filled >= 3
    
    # For other pieces, check if they used a kick to fit (immobile test)
    if used_kick:
        # Verify piece is immobile (can't move in any direction)
        immobile = (collide(board, shape, x-1, y) and 
                   collide(board, shape, x+1, y) and 
                   collide(board, shape, x, y-1) and 
                   collide(board, shape, x, y+1))
        return immobile
    
    return False

def try_rotation(board, shape, x, y, piece_name, current_rotation, clockwise=True):
    """Try to rotate with SRS wall kicks. Returns (new_shape, new_x, new_y, new_rotation, used_kick) or None"""
    if piece_name == "O":
        return None  # O piece doesn't rotate
    
    new_rotation = (current_rotation + (1 if clockwise else 3)) % 4
    new_shape = rotate_matrix(shape)
    
    # Get appropriate kick table
    if piece_name == "I":
        kick_table = SRS_KICKS_I
    else:
        kick_table = SRS_KICKS_JLSTZ
    
    kick_key = (current_rotation, new_rotation)
    kicks = kick_table.get(kick_key, [(0, 0)])
    
    for i, (kick_x, kick_y) in enumerate(kicks):
        new_x = x + kick_x
        new_y = y - kick_y  # Y is inverted in our coordinate system
        if not collide(board, new_shape, new_x, new_y):
            return (new_shape, new_x, new_y, new_rotation, i > 0)  # i > 0 means used a kick
    
    return None

def clear_lines(board):
    new = [row for row in board if not all(row)]
    cleared = HEIGHT - len(new)
    while len(new) < HEIGHT:
        new.insert(0, [0]*WIDTH)
    return new, cleared

def calculate_garbage(lines_cleared, is_spin, piece_name, last_was_line):
    """Calculate garbage lines to send based on Tetris rules"""
    if lines_cleared == 0:
        return 0
    
    if is_spin:
        # All spins get bonus garbage
        if lines_cleared == 1:
            return 2
        elif lines_cleared == 2:
            return 4
        elif lines_cleared == 3:
            return 6
    else:
        # Normal line clears
        if lines_cleared == 1:
            return 1 if last_was_line else 0
        elif lines_cleared == 2:
            return 1
        elif lines_cleared == 3:
            return 2
        elif lines_cleared == 4:  # Tetris
            return 4
    
    return 0

def add_garbage(board, n):
    """Add garbage lines with one random hole"""
    for _ in range(n):
        board.pop(0)
        hole_pos = random.randint(0, WIDTH - 1)
        garbage_line = [8 if i != hole_pos else 0 for i in range(WIDTH)]
        board.append(garbage_line)

def queue_garbage(amount, sender="Unknown"):
    """Add garbage to the queue with initial buffer counter"""
    global garbage_queue, garbage_messages
    if amount <= 0:
        return
    garbage_queue.append([amount, GARBAGE_BUFFER_PIECES, sender])
    
    # Add a message to display
    msg_template = random.choice(GARBAGE_MESSAGES)
    msg = msg_template.format(player=sender, lines=amount)
    expire_time = time.time() + MESSAGE_DISPLAY_TIME
    garbage_messages.append((msg, expire_time))

def process_garbage_queue_on_placement():
    """Called after each piece placement - decrements buffer counters"""
    global garbage_queue
    for entry in garbage_queue:
        entry[1] -= 1

def apply_ready_garbage(board):
    """Apply garbage entries that have reached 0 buffer, remove them from queue"""
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
    """Reduce queued garbage when player clears lines, also extends buffer"""
    global garbage_queue
    if lines_cleared <= 0 or not garbage_queue:
        return
    
    remaining_reduction = lines_cleared
    
    while remaining_reduction > 0 and garbage_queue:
        if garbage_queue[0][0] <= remaining_reduction:
            remaining_reduction -= garbage_queue[0][0]
            garbage_queue.pop(0)
        else:
            garbage_queue[0][0] -= remaining_reduction
            remaining_reduction = 0
    
    for entry in garbage_queue:
        entry[1] += lines_cleared

def get_garbage_display_info():
    """Get garbage queue info for visual display"""
    return [(entry[0], entry[1]) for entry in garbage_queue]

def get_active_messages():
    """Get currently active garbage messages"""
    global garbage_messages
    current_time = time.time()
    garbage_messages = [(msg, exp) for msg, exp in garbage_messages if exp > current_time]
    return [msg for msg, exp in garbage_messages]

def send_garbage(amount):
    """Send garbage to all opponents by creating files with line count in name"""
    if amount <= 0:
        return
    
    try:
        unique_id = str(uuid.uuid4())[:8]
        timestamp = time.time()
        filename = f"garbage_{PLAYER}_{amount}_{timestamp}_{unique_id}.txt"
        filepath = f"{SHARED_DIR}/{filename}"
        open(filepath, "w").close()
    except:
        pass

def check_garbage():
    """Check for garbage files, returns list of (amount, sender) tuples"""
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
                        try:
                            file_timestamp = float(parts[3])
                            if current_time - file_timestamp > GARBAGE_DELAY:
                                os.remove(f"{SHARED_DIR}/{fname}")
                        except:
                            pass
                        continue
                    
                    lines = int(parts[2])
                    file_timestamp = float(parts[3])
                    file_age = current_time - file_timestamp
                    
                    marker_file = f"{SHARED_DIR}/.received_{PLAYER}_{fname}"
                    
                    if not os.path.exists(marker_file):
                        garbage_list.append((lines, sender))
                        try:
                            open(marker_file, "w").close()
                        except:
                            pass
                    
                    if file_age > GARBAGE_DELAY:
                        try:
                            os.remove(f"{SHARED_DIR}/{fname}")
                            if os.path.exists(marker_file):
                                os.remove(marker_file)
                        except:
                            pass
                except:
                    pass
    except:
        pass
    
    # Clean up old marker files
    try:
        files = os.listdir(SHARED_DIR)
        for fname in files:
            if fname.startswith(f".received_{PLAYER}_garbage_"):
                original_fname = fname[len(f".received_{PLAYER}_"):]
                if original_fname not in files:
                    try:
                        os.remove(f"{SHARED_DIR}/{fname}")
                    except:
                        pass
    except:
        pass
    
    return garbage_list

def signal_dead(lines_cleared):
    """Signal that player is dead by creating score file"""
    try:
        unique_id = str(uuid.uuid4())[:8]
        score_file = f"{SHARED_DIR}/score_{PLAYER}_{lines_cleared}_lines_{unique_id}.txt"
        open(score_file, "w").close()
    except:
        pass

def get_leaderboard():
    """Get leaderboard from score files in shared directory"""
    scores = []
    try:
        files = os.listdir(SHARED_DIR)
        for fname in files:
            if fname.startswith("score_") and fname.endswith(".txt"):
                try:
                    parts = fname.split("_")
                    if len(parts) >= 4:
                        player_name = parts[1]
                        lines_cleared = int(parts[2])
                        scores.append({
                            "name": player_name,
                            "lines": lines_cleared
                        })
                except:
                    pass
    except:
        pass
    
    scores.sort(key=lambda x: x["lines"], reverse=True)
    return scores[:10]

def get_ghost_y(board, shape, x, y):
    """Calculate the Y position where the piece would land"""
    ghost_y = y
    while not collide(board, shape, x, ghost_y + 1):
        ghost_y += 1
    return ghost_y

def draw_preview(stdscr, shape, piece_name, row_offset, col_offset, title):
    """Draw a preview box with a tetromino"""
    try:
        stdscr.addstr(row_offset, col_offset, title)
        
        box_width = 4 * BLOCK_SIZE + 2
        stdscr.addstr(row_offset + 1, col_offset, "+" + "-" * box_width + "+")
        for i in range(4):
            stdscr.addstr(row_offset + 2 + i, col_offset, "|" + " " * box_width + "|")
        stdscr.addstr(row_offset + 6, col_offset, "+" + "-" * box_width + "+")
        
        if shape and piece_name:
            color = COLORS.get(piece_name, 7)
            min_r, max_r, min_c, max_c = get_piece_bounds(shape)
            piece_h = max_r - min_r + 1
            piece_w = max_c - min_c + 1
            y_offset = 2 + (4 - piece_h) // 2 - min_r
            x_offset = col_offset + 1 + (box_width - piece_w * BLOCK_SIZE) // 2 - min_c * BLOCK_SIZE
            for r in range(len(shape)):
                for c in range(len(shape[0])):
                    if shape[r][c]:
                        stdscr.addstr(row_offset + y_offset + r, x_offset + c * BLOCK_SIZE, "[]", curses.color_pair(color))
    except curses.error:
        pass

def draw_countdown(stdscr, count):
    """Draw countdown in center of screen with welcome message"""
    max_y, max_x = stdscr.getmaxyx()
    stdscr.clear()
    
    # Draw "Welcome to Codam 99" above the countdown
    welcome_msg = "Welcome to CODAM 99"
    welcome_y = max_y // 2 - 2
    welcome_x = (max_x - len(welcome_msg)) // 2
    
    countdown_msg = str(count) if count > 0 else "GO!"
    countdown_y = max_y // 2
    countdown_x = (max_x - len(countdown_msg)) // 2
    
    try:
        stdscr.addstr(welcome_y, welcome_x, welcome_msg, curses.A_BOLD | curses.color_pair(1))
        stdscr.addstr(countdown_y, countdown_x, countdown_msg, curses.A_BOLD)
        stdscr.refresh()
    except curses.error:
        pass

def draw_garbage_indicator(stdscr, garbage_info, offset_x, offset_y):
    """Draw garbage queue indicator on the left side of the board"""
    if not garbage_info:
        return
    
    indicator_col = offset_x - 4
    if indicator_col < 0:
        indicator_col = 0
    
    current_row = offset_y + HEIGHT
    
    for lines, pieces_remaining in reversed(garbage_info):
        if pieces_remaining <= 1:
            color_pair = 10  # Red
        elif pieces_remaining == 2:
            color_pair = 11  # Yellow
        else:
            color_pair = 12  # Green
        
        for _ in range(lines):
            if current_row > offset_y:
                try:
                    stdscr.addstr(current_row, indicator_col, "[]", curses.color_pair(color_pair) | curses.A_BOLD)
                except curses.error:
                    pass
                current_row -= 1

def draw(stdscr, board, shape, piece_name, x, y, garbage_info, next_shape, next_piece_name, 
         held_shape, held_piece_name, can_hold, color, spin_message, total_lines, leaderboard, messages):
    """Draw the game state centered on screen"""
    max_y, max_x = stdscr.getmaxyx()
    
    field_width = WIDTH * BLOCK_SIZE + 2
    field_height = HEIGHT + 2
    preview_width = 20
    leaderboard_width = 25
    garbage_indicator_width = 5
    total_width = garbage_indicator_width + field_width + preview_width + leaderboard_width + 4
    
    offset_x = max((max_x - total_width) // 2 + garbage_indicator_width, garbage_indicator_width)
    offset_y = max((max_y - field_height - 7) // 2, 2)  # Extra space for title
    
    ghost_y = get_ghost_y(board, shape, x, y)
    
    try:
        stdscr.erase()
        
        # Draw "CODAM 99" title above the playing field
        title = "★ CODAM 99 ★"
        title_x = offset_x + (field_width - len(title)) // 2
        stdscr.addstr(offset_y - 2, title_x, title, curses.A_BOLD | curses.color_pair(1))
        
        # Draw top border
        top_border = "#" * field_width
        stdscr.addstr(offset_y, offset_x, top_border)
        
        # Draw board with side walls
        for r in range(HEIGHT):
            stdscr.addstr(offset_y + r + 1, offset_x, "#")
            for c in range(WIDTH):
                cell_drawn = False
                
                for pr in range(len(shape)):
                    for pc in range(len(shape[0])):
                        if shape[pr][pc]:
                            if r == y + pr and c == x + pc:
                                stdscr.addstr(offset_y + r + 1, offset_x + c * BLOCK_SIZE + 1, "[]", curses.color_pair(color))
                                cell_drawn = True
                                break
                    if cell_drawn:
                        break
                
                if not cell_drawn and ghost_y != y:
                    for pr in range(len(shape)):
                        for pc in range(len(shape[0])):
                            if shape[pr][pc]:
                                if r == ghost_y + pr and c == x + pc:
                                    stdscr.addstr(offset_y + r + 1, offset_x + c * BLOCK_SIZE + 1, "[]", curses.color_pair(9) | curses.A_DIM)
                                    cell_drawn = True
                                    break
                        if cell_drawn:
                            break
                
                if not cell_drawn:
                    if board[r][c]:
                        cell_color = board[r][c]
                        stdscr.addstr(offset_y + r + 1, offset_x + c * BLOCK_SIZE + 1, "[]", curses.color_pair(cell_color))
                    else:
                        stdscr.addstr(offset_y + r + 1, offset_x + c * BLOCK_SIZE + 1, "  ")
                
            stdscr.addstr(offset_y + r + 1, offset_x + field_width - 1, "#")
        
        stdscr.addstr(offset_y + HEIGHT + 1, offset_x, top_border)
        
        draw_garbage_indicator(stdscr, garbage_info, offset_x, offset_y)
        
        # Draw preview boxes
        preview_col = offset_x + field_width + 2
        draw_preview(stdscr, held_shape, held_piece_name, offset_y, preview_col, "HOLD (C)")
        draw_preview(stdscr, next_shape, next_piece_name, offset_y + 8, preview_col, "NEXT")
        
        # Draw leaderboard
        leaderboard_col = preview_col + preview_width + 2
        stdscr.addstr(offset_y, leaderboard_col, "=== TOP 10 ===")
        stdscr.addstr(offset_y + 1, leaderboard_col, f"{'#':<3}{'Name':<10}{'Lines'}")
        
        for i, entry in enumerate(leaderboard[:10]):
            row_y = offset_y + 2 + i
            rank_text = f"{i+1:<3}{entry['name'][:9]:<10}{entry['lines']}"
            if entry['name'] == PLAYER:
                stdscr.addstr(row_y, leaderboard_col, rank_text, curses.A_BOLD | curses.color_pair(4))
            else:
                stdscr.addstr(row_y, leaderboard_col, rank_text)
        
        # Draw info below the game
        info_y = offset_y + HEIGHT + 3
        total_queued = sum(entry[0] for entry in garbage_info)
        stdscr.addstr(info_y, offset_x, f"Player: {PLAYER}    Lines: {total_lines}         ")
        
        if total_queued > 0:
            min_buffer = min(entry[1] for entry in garbage_info) if garbage_info else 0
            stdscr.addstr(info_y + 1, offset_x, f"Garbage queued: {total_queued} (in {min_buffer} pieces)    ")
        else:
            stdscr.addstr(info_y + 1, offset_x, " " * 40)
        
        # Draw spin message
        if spin_message:
            stdscr.addstr(info_y + 2, offset_x, f"{spin_message}!                    ", curses.A_BOLD | curses.color_pair(3))
        else:
            stdscr.addstr(info_y + 2, offset_x, " " * 30)
        
        controls = "A/D=Move W=Rotate S=Soft SPACE=Hard "
        controls += "C=Hold(used) " if not can_hold else "C=Hold "
        controls += "Q=Quit"
        stdscr.addstr(info_y + 3, offset_x, controls)
        
        # Draw garbage messages on the left side of the screen
        msg_y = offset_y
        for i, msg in enumerate(messages[:5]):  # Show up to 5 messages
            if msg_y + i < max_y - 1:
                try:
                    # Truncate message if too long
                    display_msg = msg[:offset_x - 6] if len(msg) > offset_x - 6 else msg
                    stdscr.addstr(msg_y + i, 1, display_msg, curses.color_pair(5))
                except curses.error:
                    pass
        
    except curses.error:
        pass
    
    stdscr.refresh()

def main(stdscr):
    global garbage_queue, last_read_time, last_clear_was_line, COLORS_INITIALIZED
    
    curses.curs_set(0)
    stdscr.nodelay(True)
    
    if not COLORS_INITIALIZED:
        curses.start_color()
        curses.use_default_colors()
        curses.init_pair(1, curses.COLOR_CYAN, -1)
        curses.init_pair(2, curses.COLOR_YELLOW, -1)
        curses.init_pair(3, curses.COLOR_MAGENTA, -1)
        curses.init_pair(4, curses.COLOR_GREEN, -1)
        curses.init_pair(5, curses.COLOR_RED, -1)
        curses.init_pair(6, curses.COLOR_BLUE, -1)
        curses.init_pair(7, curses.COLOR_YELLOW, -1)
        curses.init_pair(8, curses.COLOR_WHITE, -1)
        curses.init_pair(9, curses.COLOR_WHITE, -1)
        curses.init_pair(10, curses.COLOR_RED, -1)
        curses.init_pair(11, curses.COLOR_YELLOW, -1)
        curses.init_pair(12, curses.COLOR_GREEN, -1)
        COLORS_INITIALIZED = True
    
    # 3-second countdown
    for i in range(3, 0, -1):
        draw_countdown(stdscr, i)
        time.sleep(1)
    draw_countdown(stdscr, 0)
    time.sleep(0.5)
    
    board = new_board()
    total_lines = 0
    
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
    
    # Center the piece properly
    x = WIDTH // 2 - len(shape[0]) // 2
    y = 0
    
    # Adjust starting Y so piece starts at top
    while not any(shape[0]):
        shape = shape[1:] + [shape[0]]
        y -= 1
    y = -1
    
    last_tick = time.time()
    soft_drop_active = False
    last_leaderboard_refresh = 0
    leaderboard = []
    
    # Lock delay variables
    lock_delay_start = None
    lock_delay_resets = 0
    last_used_kick = False
    is_hard_drop = False
    
    def spawn_new_piece():
        nonlocal current_piece_name, current_rotation, shape, next_piece_name, next_shape
        nonlocal x, y, can_hold, current_color, lock_delay_start, lock_delay_resets, last_used_kick
        
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
        last_used_kick = False
        
        if collide(board, shape, x, y + 1):
            return False
        return True
    
    while True:
        current_time = time.time()
        
        # Clear spin message after 1.5 seconds
        if spin_message and current_time - spin_message_time > 1.5:
            spin_message = ""
        
        # Handle input
        key = stdscr.getch()
        soft_drop_active = False
        is_hard_drop = False
        moved_or_rotated = False
        
        if key == ord('q'):
            signal_dead(total_lines)
            break
        if key == ord('a') and not collide(board, shape, x-1, y):
            x -= 1
            moved_or_rotated = True
        if key == ord('d') and not collide(board, shape, x+1, y):
            x += 1
            moved_or_rotated = True
        if key == ord('w'):
            result = try_rotation(board, shape, x, y, current_piece_name, current_rotation, clockwise=True)
            if result:
                shape, x, y, current_rotation, last_used_kick = result
                moved_or_rotated = True
        if key == ord('s'):
            soft_drop_active = True
        if key == ord(' '):
            # Hard drop - instant lock, no lock delay
            while not collide(board, shape, x, y+1):
                y += 1
            is_hard_drop = True
        if key == ord('c') and can_hold:
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
            last_used_kick = False
        
        # Reset lock delay on movement/rotation (up to max resets)
        if moved_or_rotated and lock_delay_start is not None and lock_delay_resets < LOCK_DELAY_RESETS:
            lock_delay_start = current_time
            lock_delay_resets += 1
        
        # Game tick
        tick_speed = TICK / 10 if soft_drop_active else TICK
        
        should_lock = False
        
        if current_time - last_tick >= tick_speed:
            last_tick = current_time
            
            if not collide(board, shape, x, y+1):
                y += 1
                # Reset lock delay when piece moves down naturally
                if lock_delay_start is not None:
                    lock_delay_start = None
            else:
                # Piece is on ground - start or check lock delay
                if lock_delay_start is None:
                    lock_delay_start = current_time
                elif current_time - lock_delay_start >= LOCK_DELAY:
                    should_lock = True
        
        # Hard drop bypasses lock delay
        if is_hard_drop and collide(board, shape, x, y+1):
            should_lock = True
        
        if should_lock:
            # Check for spin before locking
            is_spin = check_spin(board, shape, x, y, current_piece_name, last_used_kick)
            
            lock(board, shape, x, y, current_color)
            board, cleared = clear_lines(board)
            total_lines += cleared
            
            # Set spin message
            if is_spin and cleared > 0:
                spin_names = {1: "SINGLE", 2: "DOUBLE", 3: "TRIPLE"}
                spin_message = f"{current_piece_name}-SPIN {spin_names.get(cleared, '')}"
                spin_message_time = current_time
            elif is_spin:
                spin_message = f"{current_piece_name}-SPIN"
                spin_message_time = current_time
            
            garbage_to_send = calculate_garbage(cleared, is_spin, current_piece_name, last_clear_was_line)
            if garbage_to_send > 0:
                send_garbage(garbage_to_send)
            
            if cleared > 0:
                reduce_garbage_queue(cleared)
            
            last_clear_was_line = (cleared > 0)
            
            process_garbage_queue_on_placement()
            apply_ready_garbage(board)
            
            if not spawn_new_piece():
                signal_dead(total_lines)
                break
        
        # Check for incoming garbage
        if current_time - last_read_time >= READ_INTERVAL:
            last_read_time = current_time
            garbage_list = check_garbage()
            for amount, sender in garbage_list:
                queue_garbage(amount, sender)
        
        # Refresh leaderboard periodically
        if current_time - last_leaderboard_refresh >= LEADERBOARD_REFRESH:
            last_leaderboard_refresh = current_time
            leaderboard = get_leaderboard()
        
        # Render
        garbage_display = get_garbage_display_info()
        messages = get_active_messages()
        draw(stdscr, board, shape, current_piece_name, x, y, garbage_display, 
             next_shape, next_piece_name, held_shape, held_piece_name, 
             can_hold, current_color, spin_message, total_lines, leaderboard, messages)
        
        time.sleep(0.01)

curses.wrapper(main)
