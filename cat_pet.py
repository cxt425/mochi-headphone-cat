#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
小猫桌宠 · Headphone Cat
========================
一只戴着大耳机的极简线条小猫。纯 Qt 绘制，不需要图片素材。

运行：python cat_pet.py
依赖：PySide6
"""

from __future__ import annotations

import json
import math
import random
import sys
from pathlib import Path

from PySide6.QtCore import QElapsedTimer, QPoint, QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import (
    QColor,
    QFont,
    QGuiApplication,
    QIcon,
    QImage,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import QApplication, QMenu, QWidget


# ---------------------------------------------------------------------------
# 画布与配色
# ---------------------------------------------------------------------------

BASE_W, BASE_H = 300, 360
SCALE = 0.48
W, H = round(BASE_W * SCALE), round(BASE_H * SCALE)
CX = BASE_W / 2
GROUND = 338.0

if getattr(sys, "frozen", False):
    # 打包成 exe 后，设置文件放在 exe 旁边，方便保存位置
    SETTINGS_PATH = Path(sys.executable).resolve().with_name("cat_settings.json")
else:
    SETTINGS_PATH = Path(__file__).resolve().with_name("cat_settings.json")

INK = QColor("#111111")
PAPER = QColor("#FFFDF8")


def pen(color: QColor | str, width: float) -> QPen:
    p = QPen(QColor(color), width)
    p.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return p


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def ease_out_cubic(x: float) -> float:
    return 1 - (1 - x) ** 3


# ---------------------------------------------------------------------------
# 小猫窗口
# ---------------------------------------------------------------------------


class CatPet(QWidget):
    def __init__(self) -> None:
        super().__init__()

        self.setWindowTitle("小猫桌宠")
        self.setFixedSize(W, H)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setCursor(Qt.CursorShape.OpenHandCursor)

        self.settings_data = self._read_settings()
        self.wander_enabled = bool(self.settings_data.get("wander", True))

        self.clock = QElapsedTimer()
        self.clock.start()
        self.t = 0.0
        self.mode = "idle"
        self.sleeping = False
        self.sleep_blend = 0.0
        self.walk_blend = 0.0
        self.direction = 1
        self.walk_speed = 62.0
        self.target = QPoint(self.x(), self.y())
        self.next_idle = 5.0
        self.pet_start = -10.0
        self.eat_start = -10.0
        self._dragging = False
        self._maybe_drag = False
        self._press_global = QPoint()
        self._press_window = QPoint()
        self._drag_sway = 0.0
        self._menu_open = False

        self._restore_position()
        self.target = self.pos()
        self._build_menu()

        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.timeout.connect(self._tick)
        self.timer.start(33)

    # ------------------------------------------------------------------
    # 菜单和设置
    # ------------------------------------------------------------------

    def _build_menu(self) -> None:
        self.menu = QMenu(self)
        self.menu.setWindowTitle("小猫桌宠")
        self.menu.setStyleSheet(
            """
            QMenu {
                background: #FFFDF8;
                border: 2px solid #111111;
                border-radius: 12px;
                padding: 6px;
                color: #111111;
                font-family: "Microsoft YaHei UI", "Microsoft YaHei";
                font-size: 12px;
            }
            QMenu::item {
                padding: 7px 28px 7px 22px;
                border-radius: 6px;
                min-width: 110px;
            }
            QMenu::item:selected { background: #EEE9DF; }
            QMenu::separator {
                height: 1px;
                background: #DDD5C8;
                margin: 5px 10px;
            }
            """
        )

        self.act_pet = self.menu.addAction("摸摸头")
        self.act_pet.triggered.connect(lambda: self.pet_cat())
        self.act_feed = self.menu.addAction("喂小鱼干")
        self.act_feed.triggered.connect(self.feed_cat)
        self.menu.addSeparator()

        self.act_wander = self.menu.addAction("自己散步")
        self.act_wander.setCheckable(True)
        self.act_wander.triggered.connect(self._on_wander_action)

        self.act_sleep = self.menu.addAction("睡一会儿")
        self.act_sleep.setCheckable(True)
        self.act_sleep.triggered.connect(self._on_sleep_action)

        self.menu.addSeparator()
        self.act_home = self.menu.addAction("回到右下角")
        self.act_home.triggered.connect(self.go_home)
        self.act_quit = self.menu.addAction("告别小猫")
        self.act_quit.triggered.connect(self._quit)
        self.menu.aboutToShow.connect(self._on_menu_open)
        self.menu.aboutToHide.connect(self._on_menu_hide)
        self._sync_menu()

    def _on_menu_open(self) -> None:
        self._menu_open = True
        self.mode = "idle"
        self.target = self.pos()

    def _on_menu_hide(self) -> None:
        self._menu_open = False
        self.next_idle = self.t + random.uniform(5.0, 9.0)

    def _sync_menu(self) -> None:
        self.act_wander.setChecked(self.wander_enabled)
        self.act_sleep.setChecked(self.sleeping)
        self.act_sleep.setText("叫醒它" if self.sleeping else "睡一会儿")

    @staticmethod
    def _read_settings() -> dict:
        try:
            data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8-sig"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def _restore_position(self) -> None:
        screen = QGuiApplication.primaryScreen()
        rect = screen.availableGeometry() if screen else None
        saved = self.settings_data.get("position")
        if (
            isinstance(saved, (list, tuple))
            and len(saved) == 2
            and all(isinstance(v, (int, float)) for v in saved)
        ):
            point = QPoint(int(saved[0]), int(saved[1]))
            if self._point_on_screen(point):
                self.move(point)
                return
        if rect is not None:
            self.move(rect.right() - W - 42, rect.bottom() - H - 38)

    @staticmethod
    def _point_on_screen(point: QPoint) -> bool:
        center = QPoint(point.x() + W // 2, point.y() + H // 2)
        return any(s.availableGeometry().contains(center) for s in QGuiApplication.screens())

    def _current_screen(self):
        screen = QGuiApplication.screenAt(self.frameGeometry().center())
        return screen or QGuiApplication.primaryScreen()

    def closeEvent(self, event) -> None:
        self._save_settings()
        super().closeEvent(event)

    def _save_settings(self) -> None:
        data = {"position": [self.x(), self.y()], "wander": self.wander_enabled}
        try:
            SETTINGS_PATH.write_text(
                json.dumps(data, ensure_ascii=False, separators=(", ", ": ")),
                encoding="utf-8",
            )
        except OSError:
            pass

    def _quit(self) -> None:
        self._save_settings()
        QApplication.instance().quit()

    # ------------------------------------------------------------------
    # 交互
    # ------------------------------------------------------------------

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_global = event.globalPosition().toPoint()
            self._press_window = self.pos()
            self._maybe_drag = True
            self._dragging = False
            self.raise_()
        elif event.button() == Qt.MouseButton.RightButton:
            event.accept()
            return
        event.accept()

    def contextMenuEvent(self, event) -> None:
        self._sync_menu()
        self.menu.popup(event.globalPos())
        event.accept()

    def mouseMoveEvent(self, event) -> None:
        if not self._maybe_drag:
            return
        delta = event.globalPosition().toPoint() - self._press_global
        if not self._dragging and delta.manhattanLength() >= 5:
            self._dragging = True
            self.mode = "idle"
            self._drag_sway = 0.0
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        if self._dragging:
            self.move(self._press_window + delta)
            self.target = self.pos()
            self._drag_sway = clamp(delta.x() * 0.18, -7.0, 7.0)
        event.accept()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        if self._dragging:
            self._dragging = False
            self._drag_sway = 0.0
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            self._clamp_window()
            self._save_settings()
            self.mode = "idle"
            self.next_idle = self.t + random.uniform(1.4, 3.0)
            if self.sleeping:
                self.set_sleeping(False)
        else:
            self.pet_cat()
        self._maybe_drag = False
        event.accept()

    def _clamp_window(self) -> None:
        screen = self._current_screen()
        if screen is None:
            return
        rect = screen.availableGeometry()
        x = int(clamp(self.x(), rect.left(), rect.right() - W))
        y = int(clamp(self.y(), rect.top(), rect.bottom() - H))
        self.move(x, y)
        self.target = self.pos()

    def go_home(self) -> None:
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return
        rect = screen.availableGeometry()
        self.set_sleeping(False)
        self.mode = "walk"
        self.target = QPoint(rect.right() - W - 42, rect.bottom() - H - 38)
        self.walk_speed = 90.0

    def pet_cat(self) -> None:
        if self.sleeping:
            self.set_sleeping(False)
            self.pet_start = self.t
            return
        self.pet_start = self.t
        self.mode = "idle"
        self.target = self.pos()
        self.next_idle = self.t + random.uniform(4, 7)
        self.update()

    def feed_cat(self) -> None:
        if self.sleeping:
            self.set_sleeping(False)
        self.eat_start = self.t
        self.mode = "idle"
        self.target = self.pos()
        self.next_idle = self.t + 4.5
        self.update()

    def set_sleeping(self, sleeping: bool) -> None:
        if sleeping == self.sleeping:
            return
        self.sleeping = sleeping
        self.mode = "idle"
        self.target = self.pos()
        if not sleeping:
            self.pet_start = self.t
        self.next_idle = self.t + random.uniform(3, 6)
        self._sync_menu()
        self.update()

    def _on_sleep_action(self, checked: bool) -> None:
        self.set_sleeping(checked)

    def _on_wander_action(self, checked: bool) -> None:
        self.wander_enabled = checked
        if not checked:
            self.mode = "idle"
            self.target = self.pos()
        else:
            self.next_idle = self.t + 1.0
        self._save_settings()
        self._sync_menu()

    # ------------------------------------------------------------------
    # 主循环
    # ------------------------------------------------------------------

    def _tick(self) -> None:
        now = self.clock.elapsed() / 1000.0
        dt = clamp(now - self.t, 0.0, 0.08)
        self.t = now
        self._update(dt)
        self.update()

    def _update(self, dt: float) -> None:
        t = self.t
        target_sleep = 1.0 if self.sleeping else 0.0
        self.sleep_blend += (target_sleep - self.sleep_blend) * clamp(dt * 6.0, 0, 1)
        target_walk = 1.0 if (self.mode == "walk" and not self._dragging and not self.sleeping) else 0.0
        self.walk_blend += (target_walk - self.walk_blend) * clamp(dt * 7.0, 0, 1)

        if self.mode == "walk" and not self._dragging and not self.sleeping:
            current = QPointF(self.pos())
            goal = QPointF(self.target)
            delta = goal - current
            distance = math.hypot(delta.x(), delta.y())
            if distance < 2.5:
                self.move(self.target)
                self.mode = "idle"
                self.next_idle = t + random.uniform(9.0, 20.0)
            else:
                step = min(distance, self.walk_speed * dt)
                np = current + delta * (step / distance)
                self.move(round(np.x()), round(np.y()))
                if abs(delta.x()) > 0.5:
                    self.direction = 1 if delta.x() > 0 else -1

        busy = (
            self._dragging
            or self.sleeping
            or self._is_eating
            or self._is_being_petted
            or self._menu_open
        )
        if self.mode == "idle" and not busy and self.wander_enabled and t >= self.next_idle:
            self._start_walk()

    @property
    def _is_eating(self) -> bool:
        return 0.0 <= self.t - self.eat_start < 3.4

    @property
    def _is_being_petted(self) -> bool:
        return 0.0 <= self.t - self.pet_start < 1.7

    def _start_walk(self) -> None:
        screen = self._current_screen()
        if screen is None:
            return
        rect = screen.availableGeometry()
        x_min = rect.left() + 14
        x_max = max(x_min + 20, rect.right() - W - 14)
        y_min = rect.top() + int(rect.height() * 0.30)
        y_max = max(y_min + 20, rect.bottom() - H - 14)

        best = None
        best_dist = -1.0
        for _ in range(10):
            candidate = QPoint(
                random.randint(x_min, x_max),
                random.randint(y_min, y_max),
            )
            d = math.hypot(candidate.x() - self.x(), candidate.y() - self.y())
            if d > best_dist:
                best, best_dist = candidate, d
            if d > 130:
                break
        if best is None:
            return
        self.target = best
        self.walk_speed = random.uniform(50.0, 78.0)
        self.direction = 1 if best.x() >= self.x() else -1
        self.mode = "walk"

    # ------------------------------------------------------------------
    # 绘制
    # ------------------------------------------------------------------

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHints(
            QPainter.RenderHint.Antialiasing
            | QPainter.RenderHint.SmoothPixmapTransform
        )
        painter.scale(W / BASE_W, H / BASE_H)
        self._paint_scene(painter)
        painter.end()

    def _paint_scene(self, p: QPainter) -> None:
        t = self.t
        sleeping = self.sleep_blend
        petting = self._is_being_petted

        if petting:
            # 摸头时身体保持很慢的左右晃动，眼睛变成椭圆
            pet_age = t - self.pet_start
            sway_phase = clamp(pet_age / 1.4, 0.0, 1.0)
            body_sway = math.sin(math.pi * sway_phase)
            bob = -abs(body_sway) * 1.0
            lean = body_sway * 3.0
            sway_x = body_sway * 3.2
        else:
            sway_x = 0.0
            bob = math.sin(t * 2.1) * 1.2
            if self.walk_blend > 0.02:
                bob += -abs(math.sin(t * 8.4)) * 2.6 * self.walk_blend
            if self._dragging:
                bob += math.sin(t * 6.2) * 1.8
            bob += sleeping * 6.0
            lean = self.walk_blend * self.direction * 1.7 + math.sin(t * 0.9) * 0.3
            lean += self._drag_sway * 0.55
            eat_age = t - self.eat_start
            if 1.0 <= eat_age < 3.1:
                chew_phase = (eat_age - 1.0) * 10.0
                bob -= abs(math.sin(chew_phase)) * 2.4
                lean += math.sin(chew_phase) * 0.5

        p.save()
        p.translate(CX + sway_x, GROUND + bob)
        p.rotate(lean)
        p.scale(1.0 + sleeping * 0.012, 1.0 - sleeping * 0.022)
        p.translate(-CX, -GROUND)
        self._draw_cat(p, t, sleeping)
        p.restore()

        self._draw_fish(p, t)
        self._draw_zzz(p, t, sleeping)

    def _draw_cat(self, p: QPainter, t: float, sleeping: float) -> None:
        face_x = CX + 6.0

        # 耳机头梁先画，猫身会盖住中间部分，只露出头顶的一道弧
        band = QPainterPath()
        band.moveTo(CX - 96, 160)
        band.cubicTo(CX - 90, 88, CX - 48, 44, CX + 4, 44)
        band.cubicTo(CX + 52, 44, CX + 92, 80, CX + 102, 160)
        p.setPen(pen(PAPER, 9.8))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(band)
        p.setPen(pen(INK, 7.2))
        p.drawPath(band)

        # 稍微侧过去的正面：左肩略宽，右肩略收
        body = QPainterPath()
        body.moveTo(CX - 62, 336)
        body.cubicTo(CX - 100, 304, CX - 100, 246, CX - 82, 205)
        body.cubicTo(CX - 76, 184, CX - 80, 160, CX - 72, 147)
        body.cubicTo(CX - 62, 132, CX - 52, 92, CX - 43, 70)
        body.cubicTo(CX - 36, 58, CX - 23, 78, CX - 12, 98)
        body.cubicTo(CX - 5, 109, CX + 8, 109, CX + 15, 98)
        body.cubicTo(CX + 26, 78, CX + 38, 58, CX + 47, 64)
        body.cubicTo(CX + 57, 76, CX + 67, 118, CX + 77, 142)
        body.cubicTo(CX + 87, 158, CX + 87, 183, CX + 95, 201)
        body.cubicTo(CX + 102, 242, CX + 100, 300, CX + 64, 336)
        body.cubicTo(CX + 34, 346, CX - 34, 346, CX - 62, 336)
        body.closeSubpath()
        p.setPen(pen(INK, 4.2))
        p.setBrush(PAPER)
        p.drawPath(body)

        # 右侧这条线就是尾巴，向上翘起并在耳机上方反向卷一下
        if self._is_being_petted:
            pet_age = t - self.pet_start
            sway_phase = clamp(pet_age / 1.4, 0.0, 1.0)
            tail_sway = math.sin(math.pi * sway_phase) * 8.0
        else:
            tail_sway = math.sin(t * 2.4) * 2.4
        tail_sway += self._drag_sway * 0.6

        tail = QPainterPath()
        tail.moveTo(CX + 86, 310)
        tail.cubicTo(
            CX + 120 + tail_sway * 0.3,
            300,
            CX + 136 + tail_sway,
            280,
            CX + 138 + tail_sway,
            258,
        )
        tail.cubicTo(
            CX + 139 + tail_sway * 0.6,
            240,
            CX + 128,
            232,
            CX + 120,
            244,
        )
        tail.cubicTo(
            CX + 112,
            256,
            CX + 124,
            262,
            CX + 132,
            250,
        )
        p.setPen(pen(PAPER, 6.8))
        p.drawPath(tail)
        p.setPen(pen(INK, 4.0))
        p.drawPath(tail)

        # 两只黑色大耳罩：近侧（右）略大、略高，远侧（左）略小
        for rect, radius in (
            (QRectF(CX - 116, 142, 36, 76), 18.0),
            (QRectF(CX + 80, 136, 42, 84), 21.0),
        ):
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(PAPER)
            p.drawRoundedRect(rect.adjusted(-1.8, -1.8, 1.8, 1.8), radius + 2, radius + 2)
            p.setBrush(INK)
            p.drawRoundedRect(rect, radius, radius)

        # 平时是两道闭眼斜线，摸头时变成长椭圆形眼睛
        if self._is_being_petted:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(INK)
            p.drawEllipse(QRectF(face_x - 36, 157, 12, 23))
            p.drawEllipse(QRectF(face_x + 24, 157, 12, 23))
        else:
            left_eye = QPainterPath()
            left_eye.moveTo(face_x - 52, 161)
            left_eye.quadTo(face_x - 35, 167, face_x - 18, 172)
            right_eye = QPainterPath()
            right_eye.moveTo(face_x + 10, 172)
            right_eye.quadTo(face_x + 27, 167, face_x + 44, 161)
            p.setPen(pen(INK, 5.8))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(left_eye)
            p.drawPath(right_eye)

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(INK)
        eat_age = t - self.eat_start
        if 1.0 <= eat_age < 3.1:
            # 小鱼干到嘴边后，嘴巴一开一合地咀嚼
            open_amount = 0.5 + 0.5 * math.sin((eat_age - 1.0) * 18.0)
            mouth_h = 3.0 + 9.0 * open_amount
            p.drawEllipse(QRectF(face_x - 4, 201 - mouth_h / 2, 12, mouth_h))
        else:
            p.drawEllipse(QPointF(face_x + 2, 201), 4.8, 4.8)

    def _draw_zzz(self, p: QPainter, t: float, sleeping: float) -> None:
        if sleeping < 0.30:
            return

        letters = ("z", "Z", "z")
        sizes = (18, 22, 26)
        for i, (letter, size) in enumerate(zip(letters, sizes)):
            font = QFont("Microsoft YaHei UI", size)
            font.setBold(True)
            phase = (t * 0.38 + i / 3.0) % 1.0
            alpha = int(235 * sleeping * (1.0 - phase) * min(1.0, phase * 7.0))
            if alpha <= 0:
                continue
            x = CX + 82 + phase * 12
            y = 100 - phase * 48
            path = QPainterPath()
            path.addText(QPointF(x, y), font, letter)

            halo = QColor(PAPER)
            halo.setAlpha(min(235, alpha))
            p.setPen(pen(halo, 3.2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(path)

            ink = QColor(INK)
            ink.setAlpha(alpha)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(ink)
            p.drawPath(path)

    def _draw_fish(self, p: QPainter, t: float) -> None:
        age = t - self.eat_start
        if not (0.0 <= age < 1.05):
            return
        k = ease_out_cubic(age / 1.05)
        x = CX + 86 - 82 * k
        y = 202 - 8 * math.sin(k * math.pi)
        scale = 0.9 - 0.08 * k
        wiggle = math.sin(age * 24) * 7 * (1 - k)

        p.save()
        p.translate(x, y)
        p.rotate(-14 + wiggle)
        p.scale(scale, scale)

        fish = QPainterPath()
        fish.moveTo(-11, 0)
        fish.cubicTo(-4, -8, 12, -8, 17, 0)
        fish.cubicTo(12, 8, -4, 8, -11, 0)
        fish.closeSubpath()
        tail = QPainterPath()
        tail.moveTo(-10, 0)
        tail.lineTo(-20, -8)
        tail.lineTo(-17, 0)
        tail.lineTo(-20, 8)
        tail.closeSubpath()

        p.setPen(pen(INK, 2.2))
        p.setBrush(PAPER)
        p.drawPath(tail)
        p.drawPath(fish)
        p.setPen(pen(INK, 1.5))
        p.drawArc(QRectF(1, -7, 9, 14), -70 * 16, 140 * 16)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(INK)
        p.drawEllipse(QPointF(10, -2.2), 1.8, 1.8)
        p.restore()


# ---------------------------------------------------------------------------
# 程序入口
# ---------------------------------------------------------------------------


def make_app_icon() -> QIcon:
    image = QImage(64, 64, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    p = QPainter(image)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    # 猫头
    head = QPainterPath()
    head.moveTo(9, 43)
    head.cubicTo(5, 28, 12, 18, 23, 15)
    head.cubicTo(28, 7, 34, 9, 38, 16)
    head.cubicTo(46, 14, 55, 22, 55, 34)
    head.cubicTo(55, 48, 45, 56, 32, 56)
    head.cubicTo(20, 56, 11, 52, 9, 43)
    head.closeSubpath()
    p.setPen(pen(INK, 2.4))
    p.setBrush(PAPER)
    p.drawPath(head)

    # 耳机
    band = QPainterPath()
    band.moveTo(12, 31)
    band.cubicTo(12, 17, 21, 7, 32, 7)
    band.cubicTo(43, 7, 52, 17, 52, 31)
    p.setPen(pen(INK, 3.0))
    p.drawPath(band)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(INK)
    p.drawRoundedRect(QRectF(6, 24, 12, 23), 6, 6)
    p.drawRoundedRect(QRectF(46, 24, 12, 23), 6, 6)

    # 脸
    p.setPen(pen(INK, 2.2))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawLine(QPointF(22, 34), QPointF(29, 36))
    p.drawLine(QPointF(35, 36), QPointF(42, 34))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(INK)
    p.drawEllipse(QPointF(32, 42), 1.8, 1.8)
    p.end()
    return QIcon(QPixmap.fromImage(image))


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("小猫桌宠")
    app.setOrganizationName("MochiCat")
    app.setQuitOnLastWindowClosed(True)
    app.setWindowIcon(make_app_icon())
    pet = CatPet()
    pet.show()
    pet.raise_()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
