import curses
import time
import sys
import os
import random
from collections import deque

# ---------------- CONFIG ----------------
WIDTH = 10
HEIGHT = 20
TICK = 0.25
SHARED_DIR = "/sgoinfre/lusteur/tetris"
READ_INTERVAL = 0.05  # Check for files more frequently (they're just directory listings now)
# ---------------------------------------

if len(sys.argv) < 2:
    print("Usage: python3 tetris.py <player_name>")
    sys.exit(1)

PLAYER = sys.argv[1]
PLAYER_DIR = f"{SHARED_DIR}/{PLAYER}"
os.makedirs(PLAYER_DIR, exist_ok=True)

last_read_time = 0
pending_garbage = 0  # Accumulated garbage lines

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
    "I": 1,
    "O": 2,
    "T": 3,
    "S": 4,
    "Z": 5,
    "J": 6,
    "L": 7
}

def rotate(shape):
    return list(zip(*shape[::-1]))

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

def clear_lines(board):
    new = [row for row in board if not all(row)]
    cleared = HEIGHT - len(new)
    while len(new) < HEIGHT:
        new.insert(0, [0]*WIDTH)
    return new, cleared

def add_garbage(board, n):
    """Add garbage lines with one random hole"""
    for _ in range(n):
        board.pop(0)
        hole_pos = random.randint(0, WIDTH - 1)
        garbage_line = [8 if i != hole_pos else 0 for i in range(WIDTH)]  # 8 = garbage color
        board.append(garbage_line)

def send_garbage(amount):
    """Send garbage to opponents by creating files"""
    try:
        for player_dir in os.listdir(SHARED_DIR):
            if player_dir == PLAYER:
                continue
            target_dir = f"{SHARED_DIR}/{player_dir}"
            if os.path.isdir(target_dir):
                # Create garbage files for opponent
                for i in range(amount):
                    garbage_file = f"{target_dir}/garbage_{time.time()}_{i}.txt"
                    try:
                        open(garbage_file, "w").close()
                    except:
                        pass
    except:
        pass

def check_garbage():
    """Check for garbage files and remove them"""
    garbage_count = 0
    try:
        files = os.listdir(PLAYER_DIR)
        for fname in files:
            if fname.startswith("garbage_"):
                garbage_count += 1
                try:
                    os.remove(f"{PLAYER_DIR}/{fname}")
                except:
                    pass
    except:
        pass
    return garbage_count

def signal_dead():
    """Signal that player is dead"""
    try:
        dead_file = f"{PLAYER_DIR}/DEAD"
        open(dead_file, "w").close()
    except:
        pass

def get_piece_name(shape):
    """Get the name of a tetromino from its shape"""
    for name, tetro_shape in TETROMINOES.items():
        if tetro_shape == shape:
            return name
    return "?"

def draw_preview(stdscr, shape, row_offset, col_offset, title):
    """Draw a preview box with a tetromino"""
    try:
        stdscr.addstr(row_offset, col_offset, title)
        stdscr.addstr(row_offset + 1, col_offset, "+----+")
        for i in range(4):
            stdscr.addstr(row_offset + 2 + i, col_offset, "|    |")
        stdscr.addstr(row_offset + 6, col_offset, "+----+")
        
        # Draw the piece centered in the preview
        if shape:
            y_offset = 2 + (4 - len(shape)) // 2
            x_offset = col_offset + 1 + (4 - len(shape[0]) * 2) // 2
            for r in range(len(shape)):
                for c in range(len(shape[0])):
                    if shape[r][c]:
                        stdscr.addstr(row_offset + y_offset + r, x_offset + c*2, "[]")
    except curses.error:
        pass

def draw(stdscr, board, shape, x, y, garbage_pending, next_shape, held_shape, can_hold, color):
    """Draw the game state with double buffering to reduce flicker"""
    max_y, max_x = stdscr.getmaxyx()
    
    # Check if terminal is large enough
    min_height = HEIGHT + 6
    min_width = WIDTH * 2 + 20  # Extra space for preview boxes
    
    if max_y < min_height or max_x < min_width:
        stdscr.clear()
        stdscr.addstr(0, 0, f"Terminal too small! Need at least {min_width}x{min_height}")
        stdscr.addstr(1, 0, f"Current size: {max_x}x{max_y}")
        stdscr.addstr(2, 0, "Please resize your terminal window")
        stdscr.refresh()
        return
    
    # Don't clear the screen - just overwrite
    # stdscr.clear() - removed to reduce flicker
    
    try:
        # Initialize colors if not done
        if not hasattr(draw, 'colors_initialized'):
            curses.start_color()
            curses.init_pair(1, curses.COLOR_CYAN, curses.COLOR_BLACK)    # I
            curses.init_pair(2, curses.COLOR_YELLOW, curses.COLOR_BLACK)  # O
            curses.init_pair(3, curses.COLOR_MAGENTA, curses.COLOR_BLACK) # T
            curses.init_pair(4, curses.COLOR_GREEN, curses.COLOR_BLACK)   # S
            curses.init_pair(5, curses.COLOR_RED, curses.COLOR_BLACK)     # Z
            curses.init_pair(6, curses.COLOR_BLUE, curses.COLOR_BLACK)    # J
            curses.init_pair(7, curses.COLOR_WHITE, curses.COLOR_BLACK)   # L
            curses.init_pair(8, curses.COLOR_WHITE, curses.COLOR_BLACK)   # Garbage
            draw.colors_initialized = True
        
        # Draw top border
        stdscr.addstr(0, 0, "#" * (WIDTH * 2 + 2))
        
        # Draw board with side walls
        for r in range(HEIGHT):
            stdscr.addstr(r + 1, 0, "#")
            for c in range(WIDTH):
                if board[r][c]:
                    cell_color = board[r][c]
                    stdscr.addstr(r + 1, c*2 + 1, "[]", curses.color_pair(cell_color))
                else:
                    stdscr.addstr(r + 1, c*2 + 1, "  ")
            stdscr.addstr(r + 1, WIDTH * 2 + 1, "#")
        
        # Draw current piece
        for r in range(len(shape)):
            for c in range(len(shape[0])):
                if shape[r][c] and y+r >= 0 and y+r < HEIGHT:
                    stdscr.addstr(y+r + 1, (x+c)*2 + 1, "[]", curses.color_pair(color))
        
        # Draw bottom border
        stdscr.addstr(HEIGHT + 1, 0, "#" * (WIDTH * 2 + 2))
        
        # Draw preview boxes
        preview_col = WIDTH * 2 + 4
        draw_preview(stdscr, held_shape, 0, preview_col, "HOLD (C)")
        draw_preview(stdscr, next_shape, 8, preview_col, "NEXT")
        
        # Draw info
        stdscr.addstr(HEIGHT + 2, 0, f"Player: {PLAYER}               ")
        if garbage_pending > 0:
            stdscr.addstr(HEIGHT + 3, 0, f"Garbage incoming: {garbage_pending}    ")
        else:
            stdscr.addstr(HEIGHT + 3, 0, " " * 30)  # Clear the line
        
        if not can_hold:
            stdscr.addstr(HEIGHT + 4, 0, "A/D=Move W=Rotate S=Soft SPACE=Hard C=Hold(used) Q=Quit")
        else:
            stdscr.addstr(HEIGHT + 4, 0, "A/D=Move W=Rotate S=Soft SPACE=Hard C=Hold Q=Quit       ")
        
    except curses.error:
        # If we still get an error, just continue
        pass
    
    stdscr.refresh()

def main(stdscr):
    global pending_garbage, last_read_time
    
    curses.curs_set(0)
    stdscr.nodelay(True)
    
    # Check terminal size before starting
    max_y, max_x = stdscr.getmaxyx()
    min_height = HEIGHT + 6
    min_width = WIDTH * 2 + 20
    
    if max_y < min_height or max_x < min_width:
        stdscr.clear()
        stdscr.addstr(0, 0, f"Terminal too small! Need at least {min_width}x{min_height}")
        stdscr.addstr(1, 0, f"Current size: {max_x}x{max_y}")
        stdscr.addstr(2, 0, "Please resize your terminal and restart")
        stdscr.addstr(3, 0, "Press any key to exit...")
        stdscr.nodelay(False)
        stdscr.getch()
        return
    
    board = new_board()
    
    # Generate piece bag
    piece_names = list(TETROMINOES.keys())
    random.shuffle(piece_names)
    piece_bag = [TETROMINOES[name] for name in piece_names]
    
    shape = piece_bag.pop(0)
    next_shape = piece_bag[0] if piece_bag else random.choice(list(TETROMINOES.values()))
    held_shape = None
    can_hold = True
    
    # Get current piece color
    current_color = COLORS[get_piece_name(shape)]
    
    x = WIDTH//2 - len(shape[0])//2
    y = -1
    
    last_tick = time.time()
    soft_drop_active = False
    
    while True:
        current_time = time.time()
        
        # Handle input (non-blocking)
        key = stdscr.getch()
        soft_drop_active = False
        
        if key == ord('q'):
            signal_dead()
            break
        if key == ord('a') and not collide(board, shape, x-1, y):
            x -= 1
        if key == ord('d') and not collide(board, shape, x+1, y):
            x += 1
        if key == ord('w'):
            r = rotate(shape)
            if not collide(board, r, x, y):
                shape = r
        if key == ord('s'):
            # Soft drop - move down faster
            soft_drop_active = True
        if key == ord(' '):
            # Hard drop - instantly drop to bottom
            while not collide(board, shape, x, y+1):
                y += 1
        if key == ord('c') and can_hold:
            # Hold piece
            if held_shape is None:
                held_shape = shape
                # Get next piece from bag
                if not piece_bag:
                    piece_names = list(TETROMINOES.keys())
                    random.shuffle(piece_names)
                    piece_bag = [TETROMINOES[name] for name in piece_names]
                shape = piece_bag.pop(0)
                next_shape = piece_bag[0] if piece_bag else random.choice(list(TETROMINOES.values()))
            else:
                # Swap with held piece
                shape, held_shape = held_shape, shape
            
            current_color = COLORS[get_piece_name(shape)]
            x = WIDTH//2 - len(shape[0])//2
            y = -1
            can_hold = False
        
        # Game tick (faster when soft dropping)
        tick_speed = TICK / 10 if soft_drop_active else TICK
        
        if current_time - last_tick >= tick_speed:
            last_tick = current_time
            
            if not collide(board, shape, x, y+1):
                y += 1
            else:
                lock(board, shape, x, y, current_color)
                board, cleared = clear_lines(board)
                if cleared:
                    # Send garbage to opponents (n-1 lines)
                    garbage_to_send = max(0, cleared - 1)
                    if garbage_to_send > 0:
                        send_garbage(garbage_to_send)
                
                # Get next piece from bag
                if not piece_bag:
                    piece_names = list(TETROMINOES.keys())
                    random.shuffle(piece_names)
                    piece_bag = [TETROMINOES[name] for name in piece_names]
                
                shape = piece_bag.pop(0)
                next_shape = piece_bag[0] if piece_bag else random.choice(list(TETROMINOES.values()))
                current_color = COLORS[get_piece_name(shape)]
                x = WIDTH//2 - len(shape[0])//2
                y = -1
                can_hold = True  # Can hold again after placing
                
                if collide(board, shape, x, y+1):
                    signal_dead()
                    break
        
        # Check for incoming garbage (throttled)
        if current_time - last_read_time >= READ_INTERVAL:
            last_read_time = current_time
            garbage_count = check_garbage()
            if garbage_count > 0:
                pending_garbage += garbage_count
        
        # Apply pending garbage (one line per tick to avoid huge lag spike)
        if pending_garbage > 0:
            add_garbage(board, 1)
            pending_garbage -= 1
        
        # Render
        draw(stdscr, board, shape, x, y, pending_garbage, next_shape, held_shape, can_hold, current_color)
        
        # Small sleep to prevent CPU spinning
        time.sleep(0.01)

curses.wrapper(main)