# test_mario_standup_backrest_timercontrol.py
import sys
from PyQt5 import QtWidgets, QtGui, QtCore, QtMultimedia
from pynput import keyboard as pynput_keyboard
from pathlib import Path

# ---------- Mario sprite / physics ----------
class MarioSprite:
    def __init__(self, window, gif_path="mario_walking.gif", jump_path="mario_jump.png", target_size=(32, 32)):
        self.window = window
        self.x = 0
        self.ground_y = 0
        self.y = 0
        self.velocity_y = 0
        self.is_jumping = False
        self.target_w, self.target_h = target_size

        # Load walking GIF
        self.movie = QtGui.QMovie(gif_path)
        if self.movie.isValid():
            self.movie.setScaledSize(QtCore.QSize(*target_size))
            self.movie.start()
            self.sprite_w = self.movie.frameRect().width()
            self.sprite_h = self.movie.frameRect().height()
        else:
            fallback = QtGui.QPixmap(*target_size)
            fallback.fill(QtGui.QColor(200, 0, 0))
            self.movie = None
            self.sprite_w, self.sprite_h = target_size
            self.jump_pixmap = fallback

        # Load jump image
        jump_img = QtGui.QPixmap(jump_path)
        if jump_img.isNull():
            fallback = QtGui.QPixmap(*target_size)
            fallback.fill(QtGui.QColor(0, 200, 0))
            self.jump_pixmap = fallback
        else:
            self.jump_pixmap = jump_img.scaled(*target_size,
                                               QtCore.Qt.KeepAspectRatio,
                                               QtCore.Qt.SmoothTransformation)

        self.relayout()

    def relayout(self):
        w = max(1, self.window.width())
        h = max(1, self.window.height())
        self.x = int(w * 0.05)
        self.ground_y = h - self.sprite_h - 10
        if not self.is_jumping:
            self.y = self.ground_y

    def update(self):
        if self.is_jumping:
            self.velocity_y += 1
            self.y += self.velocity_y
            if self.y >= self.ground_y:
                self.y = self.ground_y
                self.is_jumping = False
                self.velocity_y = 0

    def jump(self):
        if not self.is_jumping:
            self.is_jumping = True
            self.velocity_y = -18
            if hasattr(self.window, "jump_sound"):
                self.window.jump_sound.play()

    def current_frame(self):
        if self.is_jumping:
            return self.jump_pixmap
        elif self.movie and self.movie.isValid():
            return self.movie.currentPixmap()
        else:
            return self.jump_pixmap

# ---------- Overlay window ----------
class OverlayWindow(QtWidgets.QWidget):
    def __init__(self, width=300, height=200, pos_x=50, pos_y=50):
        super().__init__()

        self.setWindowFlags(
            QtCore.Qt.Window |
            QtCore.Qt.WindowStaysOnTopHint
        )
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)

        self.resize(width, height)
        self.move(pos_x, pos_y)
        self.show()
        self.raise_()

        self.mario = MarioSprite(self, target_size=(32, 32))
        self.down_pressed = False
        self.down_was_pressed = False
        self.up_pressed = False

        # Reminder state
        self.show_standup_reminder = False
        self.show_backrest_reminder = False

        # Load jump sound
        self.jump_sound = QtMultimedia.QSoundEffect()
        jump_path = Path("jump_sound.wav")
        if jump_path.exists():
            self.jump_sound.setSource(QtCore.QUrl.fromLocalFile(str(jump_path)))
            self.jump_sound.setVolume(0.2)

        # Start keyboard listener
        self.listener = pynput_keyboard.Listener(
            on_press=self.on_press,
            on_release=self.on_release
        )
        self.listener.start()

        # Game loop timer (~60 FPS)
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.game_loop)
        self.timer.start(16)

        # Stand-up reminder timer (starts only when DOWN is pressed)
        self.reminder_timer = QtCore.QTimer()
        self.reminder_timer.timeout.connect(self.trigger_standup_reminder)

        self._last_size = (self.width(), self.height())

    # ---------- keyboard ----------
    def on_press(self, key):
        if key == pynput_keyboard.Key.down:
            if not self.down_pressed:
                # start or restart the timer when down arrow is pressed
                QtCore.QMetaObject.invokeMethod(
                    self, "_start_or_restart_standup_timer",
                    QtCore.Qt.QueuedConnection
                )
            self.down_pressed = True

        if key == pynput_keyboard.Key.up:
            self.up_pressed = True

    def on_release(self, key):
        if key == pynput_keyboard.Key.down:
            self.down_pressed = False
            self.show_standup_reminder = False
            # stop the timer when down arrow is released
            QtCore.QMetaObject.invokeMethod(
                self, "_stop_standup_timer",
                QtCore.Qt.QueuedConnection
            )

        if key == pynput_keyboard.Key.up:
            self.up_pressed = False

    # ---------- Timer control ----------
    @QtCore.pyqtSlot()
    def _start_or_restart_standup_timer(self):
        self.reminder_timer.stop()
        self.reminder_timer.start(30_000)
        self.show_standup_reminder = False
        self.update()

    @QtCore.pyqtSlot()
    def _stop_standup_timer(self):
        self.reminder_timer.stop()
        self.show_standup_reminder = False
        self.update()

    # ---------- game loop ----------
    def game_loop(self):
        if (self.width(), self.height()) != self._last_size:
            self._last_size = (self.width(), self.height())
            self.mario.relayout()

        if self.down_was_pressed and not self.down_pressed:
            self.mario.jump()

        self.down_was_pressed = self.down_pressed
        self.mario.update()

        self.show_backrest_reminder = self.down_pressed and not self.up_pressed
        self.update()

    # ---------- reminders ----------
    def trigger_standup_reminder(self):
        self.show_standup_reminder = True
        self.update()

    # ---------- drawing ----------
    def paintEvent(self, event):
        painter = QtGui.QPainter(self)

        # Draw Mario
        frame = self.mario.current_frame()
        painter.drawPixmap(self.mario.x, self.mario.y,
                           self.mario.sprite_w, self.mario.sprite_h,
                           frame)

        painter.setPen(QtGui.QColor(255, 0, 0))
        font = QtGui.QFont("Arial", 16, QtGui.QFont.Bold)
        painter.setFont(font)

        # Stand-up reminder
        if self.show_standup_reminder:
            text = "Please stand up!"
            w = painter.fontMetrics().horizontalAdvance(text)
            painter.drawText((self.width() - w) // 2, 30, text)

        # Backrest reminder
        if self.show_backrest_reminder:
            text = "Put your back to your backrest!"
            w = painter.fontMetrics().horizontalAdvance(text)
            painter.drawText((self.width() - w) // 2, 60, text)

        # Border
        pen = QtGui.QPen(QtGui.QColor(255, 255, 255))
        pen.setWidth(2)
        painter.setPen(pen)
        painter.drawRect(0, 0, self.width()-1, self.height()-1)

        painter.end()

    def closeEvent(self, event):
        try:
            self.listener.stop()
        except:
            pass
        event.accept()

# ---------- Run ----------
if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    window = OverlayWindow(width=300, height=200, pos_x=50, pos_y=50)
    sys.exit(app.exec_())
