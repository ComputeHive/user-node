"""
https://github.com/z3ntu/QtWaitingSpinner

The MIT License (MIT)

Copyright (c) 2012-2014 Alexander Turkin
Copyright (c) 2014 William Hallatt
Copyright (c) 2015 Jacob Dawid
Copyright (c) 2016 Luca Weiss

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""
import math
from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtWidgets import *


class QtWaitingSpinner(QWidget):
    def __init__(self, parent, centerOnParent=True, disableParentWhenSpinning=False, modality=Qt.NonModal):
        super().__init__(parent)

        self._centerOnParent = centerOnParent
        self._disableParentWhenSpinning = disableParentWhenSpinning

        # Appearance
        self._color = QColor(255, 104, 0, 255)
        self._roundness = 50
        self._minimumTrailOpacity = 0
        self._trailFadePercentage = 100
        self._revolutionsPerSecond = 1.25
        self._numberOfLines = 20
        self._lineLength = 10
        self._lineWidth = 2
        self._innerRadius = 10

        # State
        self._currentCounter = 0
        self._isSpinning = False

        # Timer
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.rotate)

        self.updateSize()
        self.updateTimer()
        self.hide()

        self.setWindowModality(modality)
        self.setAttribute(Qt.WA_TranslucentBackground)

    # ---------------- Paint ----------------
    def paintEvent(self, event):
        self.updatePosition()

        painter = QPainter(self)
        painter.fillRect(self.rect(), Qt.transparent)
        painter.setRenderHint(QPainter.Antialiasing, True)

        if self._currentCounter >= self._numberOfLines:
            self._currentCounter = 0

        painter.setPen(Qt.NoPen)

        for i in range(self._numberOfLines):
            painter.save()

            painter.translate(
                self._innerRadius + self._lineLength,
                self._innerRadius + self._lineLength
            )

            rotateAngle = 360 * i / self._numberOfLines
            painter.rotate(rotateAngle)

            painter.translate(self._innerRadius, 0)

            distance = self.lineCountDistanceFromPrimary(
                i, self._currentCounter, self._numberOfLines
            )

            color = self.currentLineColor(
                distance,
                self._numberOfLines,
                self._trailFadePercentage,
                self._minimumTrailOpacity,
                self._color
            )

            painter.setBrush(color)
            painter.drawRoundedRect(
                QRect(0, -self._lineWidth // 2, self._lineLength, self._lineWidth),
                self._roundness,
                self._roundness
            )

            painter.restore()

    # ---------------- Control ----------------
    def start(self):
        self.updatePosition()
        self._isSpinning = True
        self.show()

        if self.parentWidget() and self._disableParentWhenSpinning:
            self.parentWidget().setEnabled(False)

        if not self._timer.isActive():
            self._timer.start()
            self._currentCounter = 0

    def stop(self):
        self._isSpinning = False
        self.hide()

        if self.parentWidget() and self._disableParentWhenSpinning:
            self.parentWidget().setEnabled(True)

        if self._timer.isActive():
            self._timer.stop()
            self._currentCounter = 0

    # ---------------- Settings ----------------
    def setNumberOfLines(self, lines):
        self._numberOfLines = lines
        self._currentCounter = 0
        self.updateTimer()

    def setLineLength(self, length):
        self._lineLength = length
        self.updateSize()

    def setLineWidth(self, width):
        self._lineWidth = width
        self.updateSize()

    def setInnerRadius(self, radius):
        self._innerRadius = radius
        self.updateSize()

    def setRevolutionsPerSecond(self, rps):
        self._revolutionsPerSecond = rps
        self.updateTimer()

    def setRoundness(self, roundness):
        self._roundness = max(0.0, min(100.0, roundness))

    def setColor(self, color=Qt.black):
        self._color = QColor(color)

    def setTrailFadePercentage(self, trail):
        self._trailFadePercentage = trail

    def setMinimumTrailOpacity(self, minOpacity):
        self._minimumTrailOpacity = minOpacity

    # ---------------- Timer FIX ----------------
    def updateTimer(self):
        denominator = self._numberOfLines * self._revolutionsPerSecond

        if denominator <= 0:
            interval = 1000
        else:
            interval = 1000 / denominator

        # 🔥 CRITICAL FIX: must be int, NOT float
        self._timer.setInterval(max(1, int(interval)))

    # ---------------- Animation ----------------
    def rotate(self):
        self._currentCounter = (self._currentCounter + 1) % self._numberOfLines
        self.update()

    # ---------------- Layout ----------------
    def updateSize(self):
        size = (self._innerRadius + self._lineLength) * 2
        self.setFixedSize(int(size), int(size))

    def updatePosition(self):
        if self.parentWidget() and self._centerOnParent:
            self.move(
                int(self.parentWidget().width() / 2 - self.width() / 2),
                int(self.parentWidget().height() / 2 - self.height() / 2)
            )

    # ---------------- Helpers ----------------
    def lineCountDistanceFromPrimary(self, current, primary, total):
        distance = primary - current
        if distance < 0:
            distance += total
        return distance

    def currentLineColor(self, distance, total, fade, minOpacity, baseColor):
        color = QColor(baseColor)

        if distance == 0:
            return color

        minAlpha = minOpacity / 100.0
        threshold = int(math.ceil((total - 1) * fade / 100.0))

        if distance > threshold:
            color.setAlphaF(minAlpha)
        else:
            alphaDiff = color.alphaF() - minAlpha
            gradient = alphaDiff / float(threshold + 1)
            alpha = color.alphaF() - gradient * distance
            color.setAlphaF(max(0.0, min(1.0, alpha)))

        return color