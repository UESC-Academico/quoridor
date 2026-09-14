# local_game.py
from ui.gui import QuoridorGUI

if __name__ == "__main__":
    app = QuoridorGUI(num_players=2)
    app.run()