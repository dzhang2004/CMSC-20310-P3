import sys
from pathlib import Path
from PyQt5 import QtWidgets, QtGui, QtCore, QtMultimedia
from pynput import keyboard as pynput_keyboard


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
        self.left_pressed = False   # track whether LEFT is currently held

        # Reminder state
        self.standup_reminder = False
        self.backrest_reminder = False

        # Flashing state
        self.flashing = False
        self.flash_on = False

        base_dir = Path(__file__).resolve().parent

        # Load jump sound
        self.jump_sound = QtMultimedia.QSoundEffect()
        self.jump_sound.setSource(
            QtCore.QUrl.fromLocalFile(str(base_dir / "jump_sound.wav"))
        )
        self.jump_sound.setVolume(0.2)

        # Nuclear sound – plays after LEFT has been held for > 5s
        self.nuclear_sound = QtMultimedia.QSoundEffect()
        self.nuclear_sound.setSource(
            QtCore.QUrl.fromLocalFile(
                str(base_dir / "nuclear-alarm-siren-sound-effect-nuke.wav")
            )
        )
        self.nuclear_sound.setVolume(1.0)  # loud for testing

        # Timer for "LEFT held" duration (single-shot: fires once after 5s)
        self.left_hold_timer = QtCore.QTimer()
        self.left_hold_timer.setSingleShot(True)
        self.left_hold_timer.timeout.connect(self.on_left_hold_timeout)

        # Timer to drive the flashing background
        self.flash_timer = QtCore.QTimer()
        self.flash_timer.timeout.connect(self.update_flash)

        # Keyboard listener (global, via pynput)
        
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
            on_release=self.on_release,
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
    # ---------- keyboard (pynput callbacks) ----------
    def on_press(self, key):
        # Sit timer (DOWN)
        if key == pynput_keyboard.Key.down and not self.down_pressed:
            QtCore.QMetaObject.invokeMethod(
                self,
                "start_or_restart_standup_timer",
                QtCore.Qt.QueuedConnection,
            )
            self.down_pressed = True

        # Backrest (UP)
        if key == pynput_keyboard.Key.up:
            self.up_pressed = True
            # STOP FLASHING WHEN BACK TOUCHES CHAIR
            self.flash_timer.stop()
            self.flash_on = False

        # LEFT pressed – start 5s hold timer the *first* time it goes down
        if key == pynput_keyboard.Key.left and not self.left_pressed:
            self.left_pressed = True
            QtCore.QMetaObject.invokeMethod(
                self,
                "start_left_hold_timer",
                QtCore.Qt.QueuedConnection,
            )

        # DEBUG: instant nuclear sound + flash with RIGHT arrow
        if key == pynput_keyboard.Key.right:
            QtCore.QMetaObject.invokeMethod(
                self,
                "debug_play_nuke",
                QtCore.Qt.QueuedConnection,
            )

    def on_release(self, key):
        # Stand-up timer control (DOWN released)
        if key == pynput_keyboard.Key.down:
            self.down_pressed = False
            self.standup_reminder = False
            QtCore.QMetaObject.invokeMethod(
                self,
                "stop_standup_timer",
                QtCore.Qt.QueuedConnection,
            )

        # Backrest (UP released)
        if key == pynput_keyboard.Key.up:
            self.up_pressed = False

        # LEFT released – cancel hold timer AND stop sound + flashing
        if key == pynput_keyboard.Key.left:
            self.left_pressed = False
            QtCore.QMetaObject.invokeMethod(
                self,
                "stop_left_hold_timer",
                QtCore.Qt.QueuedConnection,
            )
            QtCore.QMetaObject.invokeMethod(
                self,
                "stop_nuke_sequence",
                QtCore.Qt.QueuedConnection,
            )

    # ---------- Sit / stand timer control ----------
    @QtCore.pyqtSlot()
    def start_or_restart_standup_timer(self):
        self.reminder_timer.stop()
        self.reminder_timer.start(10_000)  # 10 seconds
        self.standup_reminder = False
        self.update()

    @QtCore.pyqtSlot()
    def stop_standup_timer(self):
        self.reminder_timer.stop()
        self.standup_reminder = False
        self.update()

    # ---------- nuclear "LEFT held" logic ----------
    @QtCore.pyqtSlot()
    def start_left_hold_timer(self):
        """
        Called once when LEFT arrow is first pressed.
        Start a 5s single-shot timer. The user does NOT need to release.
        """
        self.left_hold_timer.stop()
        self.left_hold_timer.start(5_000)  # 5 seconds

    @QtCore.pyqtSlot()
    def stop_left_hold_timer(self):
        self.left_hold_timer.stop()

    @QtCore.pyqtSlot()
    def on_left_hold_timeout(self):
        """
        When the 5s timer fires, only start the nuke sequence
        if LEFT is still being held.
        """
        if self.left_pressed:
            QtCore.QMetaObject.invokeMethod(
                self,
                "start_nuke_sequence",
                QtCore.Qt.QueuedConnection,
            )

    @QtCore.pyqtSlot()
    def start_nuke_sequence(self):
        """
        Start nuclear sound and begin flashing background.
        """
        self.nuclear_sound.stop()
        self.nuclear_sound.play()
        self.start_flashing()

    @QtCore.pyqtSlot()
    def stop_nuke_sequence(self):
        """
        Stop nuclear sound and stop flashing.
        Called when LEFT is released.
        """
        self.nuclear_sound.stop()
        self.stop_flashing()

    # ---------- flashing logic ----------
    @QtCore.pyqtSlot()
    def start_flashing(self):
        if not self.flashing:
            self.flashing = True
            self.flash_on = False
            self.flash_timer.start(150)  # flash every 150 ms

    @QtCore.pyqtSlot()
    def stop_flashing(self):
        self.flashing = False
        self.flash_timer.stop()
        self.flash_on = False
        self.update()

    @QtCore.pyqtSlot()
    def update_flash(self):
        """
        Toggle green flash state and repaint.
        """
        if self.flashing:
            self.flash_on = not self.flash_on
            self.update()

    @QtCore.pyqtSlot()
    def debug_play_nuke(self):
        """
        Debug shortcut to test sound + flash instantly with RIGHT arrow.
        """
        print("DEBUG: playing nuclear sound + flash")
        self.start_nuke_sequence()

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

        # Flashing green background
        if self.flashing and self.flash_on:
            painter.fillRect(self.rect(), QtGui.QColor(0, 255, 0))

        # Draw Mario
        painter.drawPixmap(
            self.mario.x,
            self.mario.y,
            self.mario.sprite_w,
            self.mario.sprite_h,
            self.mario.current_frame(),
        )

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
        self.left_hold_timer.stop()
        self.flash_timer.stop()
        self.reminder_timer.stop()
        event.accept()


# ---------- Run ----------
if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    window = OverlayWindow(width=300, height=200, pos_x=50, pos_y=50)
    sys.exit(app.exec_())