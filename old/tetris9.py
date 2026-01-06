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
TICK = 1
SHARED_DIR = "/sgoinfre/lusteur/tetris"
READ_INTERVAL = 0.05
BLOCK_SIZE = 2  # Each block is [] which is 2 characters
LEADERBOARD_REFRESH = 2.0  # Refresh leaderboard every 2 seconds
# ---------------------------------------

if len(sys.argv) < 2:
    print("Usage: python3 tetris.py <player_name>")
    sys.exit(1)

PLAYER = sys.argv[1]
os.makedirs(SHARED_DIR, exist_ok=True)

last_read_time = 0
pending_garbage = 0
last_clear_was_line = False  # Track if previous drop cleared a line

TETROMINOES = {
    "I": [[1,1,1,1]],
    "O": [[1,1],[1,1]],
    "T": [[0,1,0],[1,1,1]],
    "S": [[0,1,1],[1,1,0]],
    "Z": [[1,1,0],[0,1,1]],
    "J": [[1,0,0],[1,1,1]],
    "L": [[0,0,1],[1,1,1]]
}

COLORS = {
    "I": 1, "O": 2, "T": 3, "S": 4, "Z": 5, "J": 6, "L": 7, "garbage": 8
}

# Global for colors initialization
COLORS_INITIALIZED = False

def rotate(shape):
    return [list(row) for row in zip(*shape[::-1])]

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

def check_tspin(board, shape, x, y, piece_name):
    """Check if the last rotation was a T-spin"""
    if piece_name != "T":
        return False
    
    # Check corners around the T piece center
    corners_filled = 0
    center_x, center_y = x + 1, y + 1  # T piece center
    
    # Check all 4 corners
    corner_positions = [(-1, -1), (1, -1), (-1, 1), (1, 1)]
    for dx, dy in corner_positions:
        check_x, check_y = center_x + dx, center_y + dy
        if check_x < 0 or check_x >= WIDTH or check_y < 0 or check_y >= HEIGHT:
            corners_filled += 1
        elif board[check_y][check_x]:
            corners_filled += 1
    
    return corners_filled >= 3

def clear_lines(board):
    new = [row for row in board if not all(row)]
    cleared = HEIGHT - len(new)
    while len(new) < HEIGHT:
        new.insert(0, [0]*WIDTH)
    return new, cleared

def calculate_garbage(lines_cleared, is_tspin, last_was_line):
    """Calculate garbage lines to send based on Tetris rules"""
    if lines_cleared == 0:
        return 0
    
    if is_tspin:
        # T-Spin scoring
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

def send_garbage(amount):
    """Send garbage to all opponents by creating files with line count in name"""
    if amount <= 0:
        return
    
    try:
        # Create a unique file with the amount and sender in the name
        unique_id = str(uuid.uuid4())[:8]
        filename = f"garbage_{PLAYER}_{amount}_lines_{unique_id}.txt"
        filepath = f"{SHARED_DIR}/{filename}"
        open(filepath, "w").close()
    except:
        pass

def check_garbage():
    """Check for garbage files, sum them up, and remove them"""
    garbage_count = 0
    try:
        files = os.listdir(SHARED_DIR)
        for fname in files:
            if fname.startswith("garbage_") and fname.endswith(".txt"):
                # Extract the sender and number of lines from the filename
                # Format: garbage_{PLAYER}_{amount}_lines_{unique_id}.txt
                try:
                    parts = fname.split("_")
                    sender = parts[1]
                    
                    # Skip garbage sent by ourselves
                    if sender == PLAYER:
                        continue
                    
                    lines = int(parts[2])
                    garbage_count += lines
                    
                    # Remove the file
                    os.remove(f"{SHARED_DIR}/{fname}")
                except:
                    # If we can't parse it, try to remove it anyway
                    try:
                        os.remove(f"{SHARED_DIR}/{fname}")
                    except:
                        pass
    except:
        pass
    return garbage_count

def signal_dead(lines_cleared):
    """Signal that player is dead by creating score file"""
    try:
        unique_id = str(uuid.uuid4())[:8]
        score_file = f"{SHARED_DIR}/score_{PLAYER}_{lines_cleared}_lines_{unique_id}.txt"
        open(score_file, "w").close()
    except:
        pass

# ============= LEADERBOARD FUNCTIONS =============

def get_leaderboard():
    """Get leaderboard from score files in shared directory"""
    scores = []
    try:
        files = os.listdir(SHARED_DIR)
        for fname in files:
            if fname.startswith("score_") and fname.endswith(".txt"):
                try:
                    # Format: score_{PLAYER}_{lines}_lines_{unique_id}.txt
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
    
    # Sort by lines descending
    scores.sort(key=lambda x: x["lines"], reverse=True)
    
    # Return top 10
    return scores[:10]

# ============= GHOST PIECE FUNCTIONS =============

def get_ghost_y(board, shape, x, y):
    """Calculate the Y position where the piece would land"""
    ghost_y = y
    while not collide(board, shape, x, ghost_y + 1):
        ghost_y += 1
    return ghost_y

def draw_preview(stdscr, shape, piece_name, row_offset, col_offset, title):
    """Draw a preview box with a tetromino"""
    try:
        # Draw title
        stdscr.addstr(row_offset, col_offset, title)
        
        # Draw box
        box_width = 4 * BLOCK_SIZE + 2
        stdscr.addstr(row_offset + 1, col_offset, "+" + "-" * box_width + "+")
        for i in range(4):
            stdscr.addstr(row_offset + 2 + i, col_offset, "|" + " " * box_width + "|")
        stdscr.addstr(row_offset + 6, col_offset, "+" + "-" * box_width + "+")
        
        # Draw the piece centered in the preview
        if shape and piece_name:
            color = COLORS.get(piece_name, 7)
            y_offset = 2 + (4 - len(shape)) // 2
            x_offset = col_offset + 1 + (box_width - len(shape[0]) * BLOCK_SIZE) // 2
            for r in range(len(shape)):
                for c in range(len(shape[0])):
                    if shape[r][c]:
                        stdscr.addstr(row_offset + y_offset + r, x_offset + c * BLOCK_SIZE, "[]", curses.color_pair(color))
    except curses.error:
        pass

def draw_countdown(stdscr, count):
    """Draw countdown in center of screen"""
    max_y, max_x = stdscr.getmaxyx()
    stdscr.clear()
    
    msg = str(count) if count > 0 else "GO!"
    y = max_y // 2
    x = (max_x - len(msg)) // 2
    
    try:
        stdscr.addstr(y, x, msg, curses.A_BOLD)
        stdscr.refresh()
    except curses.error:
        pass

def draw(stdscr, board, shape, piece_name, x, y, garbage_pending, next_shape, next_piece_name, 
         held_shape, held_piece_name, can_hold, color, last_rotation_was_tspin, total_lines, leaderboard):
    """Draw the game state centered on screen"""
    max_y, max_x = stdscr.getmaxyx()
    
    # Calculate game field dimensions
    field_width = WIDTH * BLOCK_SIZE + 2  # +2 for borders
    field_height = HEIGHT + 2  # +2 for top and bottom borders
    preview_width = 20
    leaderboard_width = 25
    total_width = field_width + preview_width + leaderboard_width + 4
    
    # Calculate offset to center the game
    offset_x = max((max_x - total_width) // 2, 0)
    offset_y = max((max_y - field_height - 5) // 2, 0)
    
    # Calculate ghost position
    ghost_y = get_ghost_y(board, shape, x, y)
    
    try:
        # Don't clear screen, use erase to reduce flicker
        stdscr.erase()
        
        # Draw top border
        top_border = "#" * field_width
        stdscr.addstr(offset_y, offset_x, top_border)
        
        # Draw board with side walls
        for r in range(HEIGHT):
            stdscr.addstr(offset_y + r + 1, offset_x, "#")
            for c in range(WIDTH):
                cell_drawn = False
                
                # Check if current piece is here
                for pr in range(len(shape)):
                    for pc in range(len(shape[0])):
                        if shape[pr][pc]:
                            if r == y + pr and c == x + pc:
                                stdscr.addstr(offset_y + r + 1, offset_x + c * BLOCK_SIZE + 1, "[]", curses.color_pair(color))
                                cell_drawn = True
                                break
                    if cell_drawn:
                        break
                
                # Check if ghost piece is here (only if not current piece)
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
                
                # Draw board cell
                if not cell_drawn:
                    if board[r][c]:
                        cell_color = board[r][c]
                        stdscr.addstr(offset_y + r + 1, offset_x + c * BLOCK_SIZE + 1, "[]", curses.color_pair(cell_color))
                    else:
                        stdscr.addstr(offset_y + r + 1, offset_x + c * BLOCK_SIZE + 1, "  ")
                
            stdscr.addstr(offset_y + r + 1, offset_x + field_width - 1, "#")
        
        # Draw bottom border
        stdscr.addstr(offset_y + HEIGHT + 1, offset_x, top_border)
        
        # Draw preview boxes
        preview_col = offset_x + field_width + 2
        draw_preview(stdscr, held_shape, held_piece_name, offset_y, preview_col, "HOLD (C)")
        draw_preview(stdscr, next_shape, next_piece_name, offset_y + 8, preview_col, "NEXT")
        
        # Draw leaderboard on the right
        leaderboard_col = preview_col + preview_width + 2
        stdscr.addstr(offset_y, leaderboard_col, "=== TOP 10 ===")
        stdscr.addstr(offset_y + 1, leaderboard_col, f"{'#':<3}{'Name':<10}{'Lines'}")
        
        for i, entry in enumerate(leaderboard[:10]):
            row_y = offset_y + 2 + i
            rank_text = f"{i+1:<3}{entry['name'][:9]:<10}{entry['lines']}"
            # Highlight current player
            if entry['name'] == PLAYER:
                stdscr.addstr(row_y, leaderboard_col, rank_text, curses.A_BOLD | curses.color_pair(4))
            else:
                stdscr.addstr(row_y, leaderboard_col, rank_text)
        
        # Draw info below the game
        info_y = offset_y + HEIGHT + 3
        stdscr.addstr(info_y, offset_x, f"Player: {PLAYER}    Lines: {total_lines}         ")
        
        if garbage_pending > 0:
            stdscr.addstr(info_y + 1, offset_x, f"Garbage incoming: {garbage_pending}    ")
        else:
            stdscr.addstr(info_y + 1, offset_x, " " * 30)
        
        if last_rotation_was_tspin:
            stdscr.addstr(info_y + 2, offset_x, "T-SPIN!                    ", curses.A_BOLD | curses.color_pair(3))
        else:
            stdscr.addstr(info_y + 2, offset_x, " " * 30)
        
        controls = "A/D=Move W=Rotate S=Soft SPACE=Hard "
        controls += "C=Hold(used) " if not can_hold else "C=Hold "
        controls += "Q=Quit"
        stdscr.addstr(info_y + 3, offset_x, controls)
        
    except curses.error:
        pass
    
    stdscr.refresh()

def main(stdscr):
    global pending_garbage, last_read_time, last_clear_was_line, COLORS_INITIALIZED
    
    curses.curs_set(0)
    stdscr.nodelay(True)
    
    # Initialize colors once at start
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
        COLORS_INITIALIZED = True
    
    # 3-second countdown
    for i in range(3, 0, -1):
        draw_countdown(stdscr, i)
        time.sleep(1)
    draw_countdown(stdscr, 0)
    time.sleep(0.5)
    
    board = new_board()
    total_lines = 0
    
    # Generate piece bag with names
    def refill_bag():
        piece_names = list(TETROMINOES.keys())
        random.shuffle(piece_names)
        return piece_names
    
    piece_bag = refill_bag()
    
    # Get first piece with its name
    current_piece_name = piece_bag.pop(0)
    shape = [row[:] for row in TETROMINOES[current_piece_name]]
    
    # Get next piece
    if not piece_bag:
        piece_bag = refill_bag()
    next_piece_name = piece_bag[0]
    next_shape = [row[:] for row in TETROMINOES[next_piece_name]]
    
    held_shape = None
    held_piece_name = None
    can_hold = True
    last_rotation_was_tspin = False
    
    current_color = COLORS[current_piece_name]
    
    x = WIDTH//2 - len(shape[0])//2
    y = -1
    
    last_tick = time.time()
    soft_drop_active = False
    last_rotation_time = 0
    last_leaderboard_refresh = 0
    leaderboard = []
    
    while True:
        current_time = time.time()
        
        # Handle input
        key = stdscr.getch()
        soft_drop_active = False
        
        if key == ord('q'):
            signal_dead(total_lines)
            break
        if key == ord('a') and not collide(board, shape, x-1, y):
            x -= 1
        if key == ord('d') and not collide(board, shape, x+1, y):
            x += 1
        if key == ord('w'):
            r = rotate(shape)
            # Try wall kicks
            kicks = [0, -1, 1, -2, 2]
            for kick in kicks:
                if not collide(board, r, x + kick, y):
                    shape = r
                    x += kick
                    last_rotation_time = current_time
                    break
        if key == ord('s'):
            soft_drop_active = True
        if key == ord(' '):
            while not collide(board, shape, x, y+1):
                y += 1
        if key == ord('c') and can_hold:
            if held_shape is None:
                held_shape = [row[:] for row in TETROMINOES[current_piece_name]]
                held_piece_name = current_piece_name
                
                # Get next piece
                if not piece_bag:
                    piece_bag = refill_bag()
                current_piece_name = piece_bag.pop(0)
                shape = [row[:] for row in TETROMINOES[current_piece_name]]
                
                if not piece_bag:
                    piece_bag = refill_bag()
                next_piece_name = piece_bag[0]
                next_shape = [row[:] for row in TETROMINOES[next_piece_name]]
            else:
                # Swap current and held
                shape, held_shape = [row[:] for row in TETROMINOES[held_piece_name]], [row[:] for row in TETROMINOES[current_piece_name]]
                current_piece_name, held_piece_name = held_piece_name, current_piece_name
            
            current_color = COLORS[current_piece_name]
            x = WIDTH//2 - len(shape[0])//2
            y = -1
            can_hold = False
            last_rotation_was_tspin = False
        
        # Game tick
        tick_speed = TICK / 10 if soft_drop_active else TICK
        
        if current_time - last_tick >= tick_speed:
            last_tick = current_time
            
            if not collide(board, shape, x, y+1):
                y += 1
            else:
                # Check if last rotation was recent (T-spin detection)
                is_tspin = (current_time - last_rotation_time < 0.5) and check_tspin(board, shape, x, y, current_piece_name)
                last_rotation_was_tspin = is_tspin
                
                lock(board, shape, x, y, current_color)
                board, cleared = clear_lines(board)
                total_lines += cleared
                
                # Calculate and send garbage
                garbage_to_send = calculate_garbage(cleared, is_tspin, last_clear_was_line)
                if garbage_to_send > 0:
                    send_garbage(garbage_to_send)
                
                # Update last clear status
                last_clear_was_line = (cleared > 0)
                
                # Get next piece
                if not piece_bag:
                    piece_bag = refill_bag()
                
                current_piece_name = piece_bag.pop(0)
                shape = [row[:] for row in TETROMINOES[current_piece_name]]
                
                if not piece_bag:
                    piece_bag = refill_bag()
                next_piece_name = piece_bag[0]
                next_shape = [row[:] for row in TETROMINOES[next_piece_name]]
                
                current_color = COLORS[current_piece_name]
                x = WIDTH//2 - len(shape[0])//2
                y = -1
                can_hold = True
                
                if collide(board, shape, x, y+1):
                    signal_dead(total_lines)
                    break
        
        # Check for incoming garbage
        if current_time - last_read_time >= READ_INTERVAL:
            last_read_time = current_time
            garbage_count = check_garbage()
            if garbage_count > 0:
                pending_garbage += garbage_count
        
        # Apply pending garbage
        if pending_garbage > 0:
            add_garbage(board, 1)
            pending_garbage -= 1
        
        # Refresh leaderboard periodically
        if current_time - last_leaderboard_refresh >= LEADERBOARD_REFRESH:
            last_leaderboard_refresh = current_time
            leaderboard = get_leaderboard()
        
        # Render
        draw(stdscr, board, shape, current_piece_name, x, y, pending_garbage, 
             next_shape, next_piece_name, held_shape, held_piece_name, 
             can_hold, current_color, last_rotation_was_tspin, total_lines, leaderboard)
        
        time.sleep(0.01)

curses.wrapper(main)