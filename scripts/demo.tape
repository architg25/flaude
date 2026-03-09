# Flaude Demo Recording
# Usage: vhs scripts/demo.tape

Output docs/img/demo.gif

Require flaude

Set Shell "zsh"
Set FontSize 16
Set Width 1800
Set Height 900
Set Padding 12
Set Framerate 30
Set Theme "Catppuccin Mocha"
Set TypingSpeed 0
Set PlaybackSpeed 1

# Set up environment and start demo sessions
Hide
Type "export TERM=xterm-256color"
Enter
Type "export COLORTERM=truecolor"
Enter
Type "python scripts/demo.py > /dev/null 2>&1 &"
Enter
Sleep 3s
Type "flaude"
Enter
Sleep 5s
Show
Sleep 1s

# Navigate through sessions — show detail panel updating
Down
Sleep 1.5s
Down
Sleep 1.5s
Down
Sleep 1.5s
Down
Sleep 1.5s

# Back to top
Up
Sleep 0.5s
Up
Sleep 0.5s
Up
Sleep 0.5s
Up
Sleep 1.5s

# Show loop manager
Type "L"
Sleep 3s
Escape
Sleep 1s

# Show help dialog
Type "?"
Sleep 3s
Escape
Sleep 1.5s

# Quit flaude
Type "q"
Sleep 1s

# Clean up demo sessions
Hide
Type "kill %1 2>/dev/null; python scripts/demo.py --clean > /dev/null 2>&1"
Enter
Sleep 1s
