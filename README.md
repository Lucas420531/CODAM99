run program with:
python3 "version.py""your username"




           #ROADMAP#
ability to see who is currently online
ability to change font background etc
scorebased system
ko system with possible rewards, and a ko leaderboard
improved configs
proper way to launch the game and restart up on death
file names can be 255 character long the field in tetris is 200 characters, meaning it might be possible to share game states with other players through the same method, even better if this game state is encoded the easiest solution would be to just show the tetris grid in ones and zeroes but it would also be the slowest a funnier and more effective way is to split the playing field use the binary values of characters where each bit represents a block inside a game, for this i will need too find a range where preferably i can use 5 bits of a char to indicate half of a line  in the game because this would fit perfectly base32 seems to have exactly this 
Value  Binary   Char
-----  ------   ----
  0    00000     A
  1    00001     B
  2    00010     C
  3    00011     D
  4    00100     E
  5    00101     F
  6    00110     G
  7    00111     H
  8    01000     I
  9    01001     J
 10    01010     K
 11    01011     L
 12    01100     M
 13    01101     N
 14    01110     O
 15    01111     P
 16    10000     Q
 17    10001     R
 18    10010     S
 19    10011     T
 20    10100     U
 21    10101     V
 22    10110     W
 23    10111     X
 24    11000     Y
 25    11001     Z
 26    11010     2
 27    11011     3
 28    11100     4
 29    11101     5
 30    11110     6
 31    11111     7
