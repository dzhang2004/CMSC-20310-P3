# test_mario_standup_backrest_timercontrol_clean.py
import sys
from PyQt5 import QtWidgets, QtGui, QtCore, QtMultimedia
from pynput import keyboard as pynput_keyboard
from pathlib import Path

# ---------- Mario sprite / physics ----------
class Mario:
    def __init__(self, window, target_size=(32, 32)):
        self.window = window
        self.x = 0
        self.ground_y = 0
        self.y = 0
        self.velocity_y = 0
        self.jumping = False
        self.target_w, self.target_h = target_size

        # Load walking GIF
        self.movie = QtGui.QMovie("mario_walking.gif")
        self.movie.setScaledSize(QtCore.QSize(*target_size))
        self.movie.start()
        self.sprite_w = self.movie.frameRect().width()
        self.sprite_h = self.movie.frameRect().height()

        # Load jump image
        self.jump_pixmap = QtGui.QPixmap("mario_jump.png").scaled(*target_size)

        self.relayout()

    def relayout(self):
        w, h = self.window.width(), self.window.height()
        self.x = int(w * 0.05)
        self.ground_y = h - self.sprite_h - 10
        if not self.jumping:
            self.y = self.ground_y

    def update(self):
        if self.jumping:
            self.velocity_y += 1
            self.y += self.velocity_y
            if self.y >= self.ground_y:
                self.y = self.ground_y
                self.jumping = False
                self.velocity_y = 0

    def jump(self):
        if not self.jumping:
            self.jumping = True
            self.velocity_y = -18
            self.window.jump_sound.play()

    def current_frame(self):
        return self.jump_pixmap if self.jumping else self.movie.currentPixmap()

# ---------- Overlay window ----------
class OverlayWindow(QtWidgets.QWidget):
    def __init__(self, width=300, height=200, pos_x=50, pos_y=50):
        super().__init__()
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)

        self.resize(width, height)
        self.move(pos_x, pos_y)
        self.show()
        self.raise_()

        self.mario = Mario(self, target_size=(32, 32))
        self.down_pressed = False
        self.down_was_pressed = False
        self.up_pressed = False

        # Reminder state
        self.standup_reminder = False
        self.backrest_reminder = False

        # Load jump sound
        self.jump_sound = QtMultimedia.QSoundEffect()
        self.jump_sound.setSource(QtCore.QUrl.fromLocalFile(str(Path("jump_sound.wav"))))
        self.jump_sound.setVolume(0.2)
        
        # Alert sound for long sitting
        self.alert_sound = QtMultimedia.QSoundEffect()
        alert_path = Path("alert_sound.wav")
        if alert_path.exists():
            self.alert_sound.setSource(QtCore.QUrl.fromLocalFile(str(alert_path)))
            self.alert_sound.setVolume(0.7)

        # Flash state
        self.flash_on = False
        self.flash_timer = QtCore.QTimer()
        self.flash_timer.timeout.connect(self.toggle_flash)

        # Keyboard listener
        self.listener = pynput_keyboard.Listener(
            on_press=self.on_press,
            on_release=self.on_release
        )
        self.listener.start()

        # Game loop timer (~60 FPS)
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.game_loop)
        self.timer.start(16)

        # Stand-up reminder timer
        self.reminder_timer = QtCore.QTimer()
        self.reminder_timer.timeout.connect(self.trigger_standup_reminder)

        self._last_size = (self.width(), self.height())

    def toggle_flash(self):
        self.flash_on = not self.flash_on
        self.update()

    # ---------- keyboard ----------
    def on_press(self, key):
        if key == pynput_keyboard.Key.down and not self.down_pressed:
            QtCore.QMetaObject.invokeMethod(
                self, "start_or_restart_standup_timer",
                QtCore.Qt.QueuedConnection
            )
            self.down_pressed = True

        if key == pynput_keyboard.Key.up:
            self.up_pressed = True
            # STOP FLASHING WHEN BACK TOUCHES CHAIR
            self.flash_timer.stop()
            self.flash_on = False

    def on_release(self, key):
        if key == pynput_keyboard.Key.down:
            self.down_pressed = False
            self.standup_reminder = False
            QtCore.QMetaObject.invokeMethod(
                self, "stop_standup_timer",
                QtCore.Qt.QueuedConnection
            )

        if key == pynput_keyboard.Key.up:
            self.up_pressed = False

    # ---------- Timer control ----------
    @QtCore.pyqtSlot()
    def start_or_restart_standup_timer(self):
        self.reminder_timer.stop()
        self.reminder_timer.start(10_000)
        self.standup_reminder = False
        self.update()

    @QtCore.pyqtSlot()
    def stop_standup_timer(self):
        self.reminder_timer.stop()
        self.standup_reminder = False
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

        self.backrest_reminder = self.down_pressed and not self.up_pressed
        self.update()

    # ---------- reminders ----------
    def trigger_standup_reminder(self):
        self.standup_reminder = True
        self.alert_sound.play()    
        self.flash_timer.start(120)
        self.update()


    # ---------- drawing ----------
    def paintEvent(self, event):
        painter = QtGui.QPainter(self)

        # Draw Mario
        painter.drawPixmap(self.mario.x, self.mario.y,
                           self.mario.sprite_w, self.mario.sprite_h,
                           self.mario.current_frame())

        painter.setPen(QtGui.QColor(255, 0, 0))
        font = QtGui.QFont("Arial", 16, QtGui.QFont.Bold)
        painter.setFont(font)
        
        if self.flash_on:
            painter.fillRect(self.rect(), QtGui.QColor(255, 0, 0, 180))

        # Stand-up reminder
        if self.standup_reminder:
            text = "Please stand up!"
            w = painter.fontMetrics().horizontalAdvance(text)
            painter.drawText((self.width() - w) // 2, 30, text)

        # Backrest reminder
        if self.backrest_reminder:
            text = "Put your back to your backrest!"
            w = painter.fontMetrics().horizontalAdvance(text)
            painter.drawText((self.width() - w) // 2, 60, text)

        # Border
        pen = QtGui.QPen(QtGui.QColor(255, 255, 255))
        pen.setWidth(2)
        painter.setPen(pen)
        painter.drawRect(0, 0, self.width() - 1, self.height() - 1)

        painter.end()

    def closeEvent(self, event):
        self.listener.stop()
        event.accept()

# ---------- Run ----------
if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    window = OverlayWindow(width=300, height=200, pos_x=50, pos_y=50)
    sys.exit(app.exec_())