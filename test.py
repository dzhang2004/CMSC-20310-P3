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
        self.left_pressed = False

        # Reminder state
        self.standup_reminder = False
        self.backrest_reminder = False
        
        # Red flash state
        self.red_flash_active = False
        self.flash_opacity = 0.0
        self.flash_cycle_timer = QtCore.QTimer()
        self.flash_cycle_timer.timeout.connect(self.start_red_flash)

        # Load jump sound
        self.jump_sound = QtMultimedia.QSoundEffect()
        self.jump_sound.setSource(QtCore.QUrl.fromLocalFile(str(Path("jump_sound.wav"))))
        self.jump_sound.setVolume(0.2)
        
        # Load alarm sound
        self.alarm_sound = QtMultimedia.QSoundEffect()
        self.alarm_sound.setSource(QtCore.QUrl.fromLocalFile(str(Path("nuclear-alarm-siren-sound-effect-nuke.wav"))))
        self.alarm_sound.setVolume(0.5)
        self.alarm_sound.setLoopCount(QtMultimedia.QSoundEffect.Infinite)

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
        
        # Red flash animation timer
        self.flash_timer = QtCore.QTimer()
        self.flash_timer.timeout.connect(self.update_flash)
        self.flash_duration = 0
        self.flash_max_duration = 500  # milliseconds

        self._last_size = (self.width(), self.height())

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
            
        if key == pynput_keyboard.Key.left:
            self.left_pressed = True

    def on_release(self, key):
        if key == pynput_keyboard.Key.down:
            self.down_pressed = False
            self.standup_reminder = False
            # Stop the flashing when down is released
            QtCore.QMetaObject.invokeMethod(
                self, "stop_red_flash_cycle",
                QtCore.Qt.QueuedConnection
            )
            QtCore.QMetaObject.invokeMethod(
                self, "stop_standup_timer",
                QtCore.Qt.QueuedConnection
            )

        if key == pynput_keyboard.Key.up:
            self.up_pressed = False
            
        if key == pynput_keyboard.Key.left:
            self.left_pressed = False

    # ---------- Timer control ----------
    @QtCore.pyqtSlot()
    def start_or_restart_standup_timer(self):
        self.reminder_timer.stop()
        self.reminder_timer.start(5_000)
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
        
        # Check if left arrow is pressed to start repeating red flash
        if self.left_pressed:
            self.start_red_flash_cycle()
        
        self.update()
    
    # ---------- Red flash animation ----------
    def start_red_flash_cycle(self):
        """Start the repeating flash cycle"""
        self.start_red_flash()
        # Start timer to repeat the flash every 600ms (flash duration + small gap)
        if not self.flash_cycle_timer.isActive():
            self.flash_cycle_timer.start(600)
        # Start alarm sound
        if not self.alarm_sound.isPlaying():
            self.alarm_sound.play()
    
    @QtCore.pyqtSlot()
    def stop_red_flash_cycle(self):
        """Stop the repeating flash cycle"""
        self.flash_cycle_timer.stop()
        self.flash_timer.stop()
        self.red_flash_active = False
        self.flash_opacity = 0.0
        # Stop alarm sound
        if self.alarm_sound.isPlaying():
            self.alarm_sound.stop()
        self.update()
    
    def start_red_flash(self):
        """Start a single flash animation"""
        self.red_flash_active = True
        self.flash_opacity = 0.8
        self.flash_duration = 0
        if not self.flash_timer.isActive():
            self.flash_timer.start(16)  # ~60 FPS
    
    def update_flash(self):
        self.flash_duration += 16
        
        # Fade out effect
        progress = self.flash_duration / self.flash_max_duration
        self.flash_opacity = 0.8 * (1 - progress)
        
        if self.flash_duration >= self.flash_max_duration:
            self.flash_timer.stop()
            self.red_flash_active = False
            self.flash_opacity = 0.0
        
        self.update()

    # ---------- drawing ----------
    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        
        # Draw red flash overlay if active
        if self.red_flash_active:
            red_color = QtGui.QColor(255, 0, 0, int(self.flash_opacity * 255))
            painter.fillRect(self.rect(), red_color)

        # Draw Mario
        painter.drawPixmap(self.mario.x, self.mario.y,
                           self.mario.sprite_w, self.mario.sprite_h,
                           self.mario.current_frame())

        painter.setPen(QtGui.QColor(255, 0, 0))
        font = QtGui.QFont("Arial", 16, QtGui.QFont.Bold)
        painter.setFont(font)

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