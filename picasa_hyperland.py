#!/usr/bin/env python3

import gi
import os
import sys
import cairo
import math
import subprocess
import json
import threading

gi.require_version("Gtk", "3.0")
gi.require_version("Pango", "1.0")
gi.require_version("PangoCairo", "1.0")
from gi.repository import Gtk, GdkPixbuf, Gdk, GLib, Pango, PangoCairo

def hyprctl(cmd: str, payload: str = "") -> dict | list | None:
    try:
        args = ["hyprctl", "-j"] + cmd.split()
        if payload:
            args.append(payload)
        result = subprocess.run(args, capture_output=True, text=True, timeout=2)
        if result.returncode == 0 and result.stdout.strip():
            return json.loads(result.stdout)
    except (FileNotFoundError, subprocess.TimeoutExpired, json.JSONDecodeError):
        pass
    return None


def hyprctl_dispatch(dispatch: str, args: str = ""):
    try:
        subprocess.Popen(
            ["hyprctl", "dispatch", dispatch, args],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
    except FileNotFoundError:
        pass


def is_hyprland() -> bool:
    return bool(os.environ.get("HYPRLAND_INSTANCE_SIGNATURE"))


def get_active_monitor_geometry():
    if is_hyprland():
        monitors = hyprctl("monitors")
        if monitors:
            for m in monitors:
                if m.get("focused"):
                    return (
                        m["x"], m["y"],
                        m["width"], m["height"],
                        m.get("scale", 1.0),
                    )
            m = monitors[0]
            return m["x"], m["y"], m["width"], m["height"], m.get("scale", 1.0)
    try:
        display = Gdk.Display.get_default()
        monitor = display.get_monitor(0)
        g = monitor.get_geometry()
        return g.x, g.y, g.width, g.height, monitor.get_scale_factor()
    except Exception:
        return 0, 0, 1920, 1080, 1.0


def float_and_center_self(win_title: str = "Picasa", width: int = 900, height: int = 650):
    if not is_hyprland():
        return
    GLib.timeout_add(120, lambda: (
        hyprctl_dispatch("focuswindow", f"title:{win_title}"),
        hyprctl_dispatch("togglefloating", f"title:{win_title}"),
        hyprctl_dispatch("resizewindowpixel", f"exact {width} {height},title:{win_title}"),
        hyprctl_dispatch("centerwindow", ""),
        False,         
    ) and False)

def wl_copy_text(text: str):
    try:
        subprocess.Popen(["wl-copy", text])
    except FileNotFoundError:
        cb = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        cb.set_text(text, -1)


def wl_copy_image(image_path: str):
    try:
        ext = os.path.splitext(image_path)[1].lower()
        mime = {".png": "image/png", ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg", ".bmp": "image/bmp"}.get(ext, "image/png")
        with open(image_path, "rb") as f:
            proc = subprocess.Popen(["wl-copy", "--type", mime], stdin=subprocess.PIPE)
            proc.communicate(input=f.read())
    except FileNotFoundError:
        try:
            pixbuf = GdkPixbuf.Pixbuf.new_from_file(image_path)
            cb = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
            cb.set_image(pixbuf)
        except Exception as e:
            print(f"Error copying image: {e}")

def set_wallpaper(image_path: str):
    return None

def trash_file(path: str) -> bool:
    try:
        subprocess.run(["gio", "trash", path], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    try:
        subprocess.run(["trash-put", path], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    return False

class PhotoViewer(Gtk.Window):
    TITLE = "Picasa"

    def __init__(self, image_path=None):
        super().__init__(title=self.TITLE)
        self.set_default_size(900, 650)
        self.set_position(Gtk.WindowPosition.CENTER)

        self.set_wmclass("picasa", "Picasa")
        GLib.set_prgname("picasa")
        GLib.set_application_name("Picasa")

        self.current_folder = None
        self.image_files = []
        self.current_index = 0
        self.thumbnail_size = 150
        self.single_opened = False

        self.fullscreen_window = None
        self.pixbuf = None
        self.scale_factor = 1.0
        self.offset = (0, 0)
        self.drag_start = None
        self.rotation_angle = 0
        self.current_image_path = ""

        self.animation = None
        self.current_iter = None
        self.animation_timeout = None

        self._draw_pending = False

        self._prefetch_cache: dict = {}
        self._loading_path = ""

        self._fade_alpha = 1.0
        self._fade_timeout = None

        self.setup_browser()

        if image_path:
            if os.path.isfile(image_path):
                folder_path = os.path.dirname(os.path.abspath(image_path))
                self.single_opened = True
                self.load_folder(folder_path)
                GLib.idle_add(self._open_single, image_path)
            elif os.path.isdir(image_path):
                self.load_folder(image_path)
            else:
                print(f"Error: invalid path: {image_path}")
                sys.exit(1)

        if not self.single_opened:
            float_and_center_self(self.TITLE, 900, 650)

    def _open_single(self, image_path):
        self.hide()   
        self.show_fullscreen(image_path)
        return False

    def setup_browser(self):
        self.grid = Gtk.Grid()
        self.add(self.grid)

        toolbar = Gtk.Toolbar()

        open_btn = Gtk.ToolButton(
            icon_widget=Gtk.Image.new_from_icon_name(
                "document-open", Gtk.IconSize.LARGE_TOOLBAR))
        open_btn.set_tooltip_text("Open folder (O)")
        open_btn.connect("clicked", self.select_folder)
        toolbar.insert(open_btn, 0)

        about_btn = Gtk.ToolButton(
            icon_widget=Gtk.Image.new_from_icon_name(
                "help-about", Gtk.IconSize.LARGE_TOOLBAR))
        about_btn.connect("clicked", self.show_about_dialog)
        toolbar.insert(about_btn, 1)

        self.grid.attach(toolbar, 0, 0, 1, 1)

        self.scrolled = Gtk.ScrolledWindow()
        self.flowbox = Gtk.FlowBox()
        self.flowbox.set_valign(Gtk.Align.START)
        self.flowbox.set_max_children_per_line(8)
        self.flowbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.flowbox.connect("child-activated", self.on_thumbnail_click)
        self.scrolled.set_size_request(900, 610)
        self.scrolled.add(self.flowbox)
        self.grid.attach(self.scrolled, 0, 1, 1, 1)

        self.connect("key-press-event", self.on_browser_key)

    def on_browser_key(self, widget, event):
        key = event.keyval
        if key == Gdk.KEY_o:
            self.select_folder()
        elif key == Gdk.KEY_q or key == Gdk.KEY_Escape:
            Gtk.main_quit()

    def show_about_dialog(self, widget=None):
        d = Gtk.AboutDialog()
        d.set_transient_for(self)
        d.set_program_name("Picasa for Linux")
        d.set_version("build 1.1.0 (Hyprland)")
        try:
            pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(
                "/usr/share/icons/hicolor/512x512/apps/Picasa.png", 128, 128)
            d.set_logo(pixbuf)
        except Exception:
            pass
        d.set_website("https://github.com/0xcds4r/PicasaLinux")
        d.set_website_label("Project GitHub")
        d.set_copyright("by 0xcds4r")
        d.run()
        d.destroy()

    def select_folder(self, widget=None):
        dialog = Gtk.FileChooserDialog(
            title="Select Folder", parent=self,
            action=Gtk.FileChooserAction.SELECT_FOLDER)
        dialog.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                           Gtk.STOCK_OPEN, Gtk.ResponseType.OK)
        if dialog.run() == Gtk.ResponseType.OK:
            self.load_folder(dialog.get_filename())
        dialog.destroy()

    def load_folder(self, folder_path):
        if not os.path.isdir(folder_path):
            print(f"Error: {folder_path} is not a directory.")
            return
        self.current_folder = folder_path
        supported = (".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp", ".heic")
        self.image_files = sorted(
            os.path.join(self.current_folder, f)
            for f in os.listdir(self.current_folder)
            if f.lower().endswith(supported)
        )
        self.update_thumbnails()

    def update_thumbnails(self):
        for child in self.flowbox.get_children():
            self.flowbox.remove(child)
        for path in self.image_files:
            thumb = self.create_thumbnail(path)
            if thumb:
                self.flowbox.add(thumb)
        self.flowbox.show_all()

    def create_thumbnail(self, path):
        try:
            pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(
                path, self.thumbnail_size, self.thumbnail_size, True)
            image = Gtk.Image.new_from_pixbuf(pixbuf)
            event_box = Gtk.EventBox()
            event_box.add(image)
            event_box.set_tooltip_text(os.path.basename(path))
            event_box.connect("button-press-event",
                              lambda w, e: self.show_fullscreen(path))
            return event_box
        except Exception as e:
            print(f"Error loading thumbnail {path}: {e}")
            return None

    def on_thumbnail_click(self, flowbox, child):
        self.current_index = child.get_index()
        self.show_fullscreen(self.image_files[self.current_index])

    def _make_display_pixbuf(self, pixbuf):
        _, _, mw, mh, scale = get_active_monitor_geometry()
        max_w = int(mw * scale * 2)
        max_h = int(mh * scale * 2)
        iw = pixbuf.get_width()
        ih = pixbuf.get_height()
        if iw <= max_w and ih <= max_h:
            return pixbuf
        ratio = min(max_w / iw, max_h / ih)
        new_w = max(1, int(iw * ratio))
        new_h = max(1, int(ih * ratio))
        return pixbuf.scale_simple(new_w, new_h, GdkPixbuf.InterpType.BILINEAR)

    def _load_image(self, path):
        self.reset_animation()
        self._loading_path = path

        if path in self._prefetch_cache:
            entry = self._prefetch_cache.pop(path)
            orig, disp = entry if isinstance(entry, tuple) else (entry, entry)
            self._apply_loaded(path, orig, disp, False)
            return True

        def _worker(target_path=path):
            try:
                anim = GdkPixbuf.PixbufAnimation.new_from_file(target_path)
                if anim.is_static_image():
                    orig = anim.get_static_image()
                    disp = self._make_display_pixbuf(orig)
                    GLib.idle_add(self._apply_loaded, target_path, orig, disp, False)
                else:
                    GLib.idle_add(self._apply_loaded, target_path, anim, anim, True)
            except Exception as e:
                print(f"Error loading {target_path}: {e}")

        threading.Thread(target=_worker, daemon=True).start()
        return True

    def _apply_loaded(self, path, orig, disp, is_anim):
        if self._loading_path != path:
            return False
        if is_anim:
            anim = orig
            self.animation = anim
            self.current_iter = anim.get_iter(None)
            self.pixbuf = self.current_iter.get_pixbuf()
            self.display_pixbuf = self.pixbuf
            self.start_animation()
        else:
            self.pixbuf = orig
            self.display_pixbuf = disp
            self.animation = None
        self.current_image_path = path
        self._fit_scale()
        self._cancel_fade()
        self._fade_alpha = 0.0
        self._start_fade_in()
        GLib.idle_add(self._prefetch_neighbours)
        self._draw_pending = False
        if self.drawing_area:
            self.drawing_area.queue_draw()
        return False

    def _prefetch_neighbours(self):
        for delta in (-1, 1):
            idx = self.current_index + delta
            if 0 <= idx < len(self.image_files):
                p = self.image_files[idx]
                if p not in self._prefetch_cache:
                    def _load(path=p):
                        try:
                            anim = GdkPixbuf.PixbufAnimation.new_from_file(path)
                            if not anim.is_static_image():
                                return
                            orig = anim.get_static_image()
                            disp = self._make_display_pixbuf(orig)
                            GLib.idle_add(lambda pa=path, o=orig, d=disp:
                                self._prefetch_cache.__setitem__(pa, (o, d)) or False)
                        except Exception:
                            pass
                    threading.Thread(target=_load, daemon=True).start()
        while len(self._prefetch_cache) > 4:
            del self._prefetch_cache[next(iter(self._prefetch_cache))]
        return False

    def _fit_scale(self):
        if not self.pixbuf:
            return
        mx, my, mw, mh, hidpi_scale = get_active_monitor_geometry()
        sw = mw / hidpi_scale
        sh = mh / hidpi_scale
        iw = self.pixbuf.get_width()
        ih = self.pixbuf.get_height()
        padding = min(sw, sh) * 0.05
        scale_w = (sw - 2 * padding) / iw if iw else 1.0
        scale_h = (sh - 2 * padding) / ih if ih else 1.0
        self.scale_factor = max(0.1, min(scale_w, scale_h, 1.0))

    def show_fullscreen(self, path):
        if self.fullscreen_window is not None:
            self.offset = (0, 0)
            self.rotation_angle = 0
            try:
                self.drawing_area.disconnect_by_func(self.show_context_menu)
            except Exception:
                pass
            self.drawing_area.connect("button-press-event",
                                      self.show_context_menu, path)
            self._load_image(path) 
            return

        win = Gtk.Window(type=Gtk.WindowType.TOPLEVEL)
        win.set_title(self.TITLE)
        self.fullscreen_window = win

        mx, my, mw, mh, hidpi_scale = get_active_monitor_geometry()
        win.set_default_size(mw, mh)
        win.set_decorated(False)
        win.set_app_paintable(True)
        win.set_modal(False)

        screen = win.get_screen()
        visual = screen.get_rgba_visual()
        if visual and screen.is_composited():
            win.set_visual(visual)

        win.connect("key-press-event", self.on_fullscreen_key_press)
        win.connect("delete-event", lambda *a: self.close_fullscreen())
        win.connect("button-press-event", self.on_button_press)
        win.connect("motion-notify-event", self.on_mouse_move)
        win.connect("button-release-event", self.on_button_release)
        win.add_events(
            Gdk.EventMask.BUTTON_PRESS_MASK
            | Gdk.EventMask.POINTER_MOTION_MASK
            | Gdk.EventMask.BUTTON_RELEASE_MASK
            | Gdk.EventMask.SMOOTH_SCROLL_MASK
        )

        self.offset = (0, 0)
        self.rotation_angle = 0
        self._fade_alpha = 0.0

        self._load_image(path)

        self.drawing_area = Gtk.DrawingArea()
        self.drawing_area.set_can_focus(True)
        self.drawing_area.connect("draw", self.on_draw)
        self.drawing_area.set_events(
            Gdk.EventMask.BUTTON_PRESS_MASK
            | Gdk.EventMask.BUTTON_RELEASE_MASK
            | Gdk.EventMask.POINTER_MOTION_MASK
            | Gdk.EventMask.SCROLL_MASK
            | Gdk.EventMask.SMOOTH_SCROLL_MASK
        )
        self.drawing_area.connect("scroll-event", self.on_scroll)
        self.drawing_area.connect("button-press-event",
                                  self.show_context_menu, path)
        win.add(self.drawing_area)
        win.show_all()

        def _grab():
            win.present()
            self.drawing_area.grab_focus()
            return False
        GLib.idle_add(_grab)

    def close_fullscreen(self):
        self.reset_animation()
        self._cancel_fade()
        if self.fullscreen_window:
            self.fullscreen_window.destroy()
            self.fullscreen_window = None
        if self.single_opened:
            Gtk.main_quit()

    def _start_fade_in(self):
        self._fade_alpha = 0.0
        self._fade_timeout = GLib.timeout_add(16, self._fade_step)

    def _fade_step(self):
        self._fade_alpha = min(1.0, self._fade_alpha + 0.07)
        if self.drawing_area:
            self.drawing_area.queue_draw()
        if self._fade_alpha >= 1.0:
            self._fade_timeout = None
            return False
        return True

    def _cancel_fade(self):
        if self._fade_timeout:
            GLib.source_remove(self._fade_timeout)
            self._fade_timeout = None

    def start_animation(self):
        self.reset_animation()
        self._schedule_next_frame()

    def _schedule_next_frame(self):
        delay = self.current_iter.get_delay_time()
        if delay < 0:
            delay = 100
        self.animation_timeout = GLib.timeout_add(delay, self._advance_frame)

    def _advance_frame(self):
        if not self.animation or not self.current_iter:
            return False
        self.current_iter.advance(None)
        self.pixbuf = self.current_iter.get_pixbuf()
        self.display_pixbuf = self._make_display_pixbuf(self.pixbuf)
        if self.drawing_area:
            self.drawing_area.queue_draw()
        self._schedule_next_frame()
        return False

    def reset_animation(self):
        if self.animation_timeout:
            GLib.source_remove(self.animation_timeout)
            self.animation_timeout = None
        self.animation = None
        self.current_iter = None

    def on_draw(self, widget, cr):
        if not self.pixbuf:
            return

        fade = self._fade_alpha
        dpb = getattr(self, "display_pixbuf", self.pixbuf)
        if dpb is not self.pixbuf:
            display_ratio = dpb.get_width() / self.pixbuf.get_width() if self.pixbuf.get_width() else 1.0
            if self.scale_factor > (1.0 / display_ratio) * 0.9:
                dpb = self.pixbuf

        cr.set_operator(cairo.OPERATOR_CLEAR)
        cr.paint()
        cr.set_operator(cairo.OPERATOR_OVER)
        cr.set_source_rgba(0.0, 0.0, 0.0, 0.75 * fade)
        cr.paint()

        alloc = widget.get_allocation()
        w, h = alloc.width, alloc.height
        dw = dpb.get_width()
        dh = dpb.get_height()
        iw = self.pixbuf.get_width()
        ih = self.pixbuf.get_height()

        display_ratio = dw / iw if iw else 1.0
        render_scale = self.scale_factor * display_ratio

        cr.save()
        cr.translate(w / 2 + self.offset[0], h / 2 + self.offset[1])
        cr.rotate(math.radians(self.rotation_angle))

        if self.rotation_angle % 180 == 90:
            cr.scale(render_scale * dh / dw, render_scale * dw / dh)
        else:
            cr.scale(render_scale, render_scale)

        cr.translate(-dw / 2, -dh / 2)
        Gdk.cairo_set_source_pixbuf(cr, dpb, 0, 0)
        cr.paint_with_alpha(fade)
        cr.restore()

        self.draw_info_overlay(cr, iw, ih, w, h, fade)

    def _pango_text(self, cr, text, font_desc_str, color_rgba, x, y,
                    bg_rgba=None, padding=5):
        layout = PangoCairo.create_layout(cr)
        layout.set_text(text, -1)
        layout.set_font_description(Pango.FontDescription(font_desc_str))
        pw, ph = layout.get_pixel_size()
        if bg_rgba:
            cr.set_source_rgba(*bg_rgba)
            cr.rectangle(x - padding, y - padding, pw + 2 * padding, ph + 2 * padding)
            cr.fill()
        cr.set_source_rgba(*color_rgba)
        cr.move_to(x, y)
        PangoCairo.show_layout(cr, layout)
        return pw, ph

    def draw_info_overlay(self, cr, img_w, img_h, sw, sh, alpha=1.0):
        margin = 6

        name = os.path.basename(self.current_image_path)
        idx = f"{self.current_index + 1}/{len(self.image_files)}"
        info = (f"{name}   {img_w}×{img_h}   [{idx}]   "
                f"Zoom {int(self.scale_factor * 100)}%   Rot {self.rotation_angle}°")
        self._pango_text(
            cr, info, "Monospace 10",
            color_rgba=(1, 1, 1, alpha),
            x=margin + 5, y=margin + 3,
            bg_rgba=(0, 0, 0, 0.55 * alpha),
            padding=5,
        )

        hint = ("← → navigate   ↑ ↓ rotate   scroll zoom   "
                "F fit   0 reset   D trash   C copy   W wallpaper   ESC close   RMB menu")
        if not hasattr(self, "_hint_size"):
            tmp_layout = Pango.Layout.new(
                Pango.Context.new()
            )
            tmp_layout.set_text(hint, -1)
            tmp_layout.set_font_description(Pango.FontDescription("Sans 8"))
        pw, ph = self._pango_text(
            cr, hint, "Sans 8",
            color_rgba=(0.85, 0.85, 0.85, 0.9 * alpha),
            x=0, y=-9999, 
            bg_rgba=None,
            padding=4,
        )
        hx = (sw - pw) / 2
        hy = sh - ph - margin - 4
        self._pango_text(
            cr, hint, "Sans 8",
            color_rgba=(0.85, 0.85, 0.85, 0.9 * alpha),
            x=hx, y=hy,
            bg_rgba=(0, 0, 0, 0.45 * alpha),
            padding=4,
        )

    def _request_draw(self):
        if not self._draw_pending and self.drawing_area:
            self._draw_pending = True
            GLib.idle_add(self._do_draw)

    def _do_draw(self):
        self._draw_pending = False
        if self.drawing_area and self.pixbuf:
            self.drawing_area.queue_draw()
        return False

    def on_button_press(self, widget, event):
        if event.button == 1:
            if event.type == Gdk.EventType._2BUTTON_PRESS:
                self.scale_factor = 1.0
                self.offset = (0, 0)
                self.rotation_angle = 0
                self._request_draw()
            else:
                self.drag_start = (event.x, event.y)

    def on_mouse_move(self, widget, event):
        if self.drag_start:
            dx = event.x - self.drag_start[0]
            dy = event.y - self.drag_start[1]
            self.offset = (self.offset[0] + dx, self.offset[1] + dy)
            self.drag_start = (event.x, event.y)
            self._request_draw()

    def on_button_release(self, widget, event):
        self.drag_start = None

    def on_scroll(self, widget, event):
        zoom_in = zoom_out = False
        if event.direction == Gdk.ScrollDirection.UP:
            zoom_in = True
        elif event.direction == Gdk.ScrollDirection.DOWN:
            zoom_out = True
        elif event.direction == Gdk.ScrollDirection.SMOOTH:
            _, dx, dy = event.get_scroll_deltas()
            if dy < 0:
                zoom_in = True
            elif dy > 0:
                zoom_out = True

        if zoom_in:
            self.scale_factor *= 1.10
        elif zoom_out:
            self.scale_factor /= 1.10

        self.scale_factor = max(0.05, min(self.scale_factor, 20.0))
        self._request_draw()

    def on_fullscreen_key_press(self, widget, event):
        key = event.keyval

        if key in (Gdk.KEY_Escape, Gdk.KEY_q):
            self.close_fullscreen()

        elif key in (Gdk.KEY_Left, Gdk.KEY_bracketleft, Gdk.KEY_p):
            self.current_index = max(0, self.current_index - 1)
            self.show_fullscreen(self.image_files[self.current_index])

        elif key in (Gdk.KEY_Right, Gdk.KEY_bracketright, Gdk.KEY_n):
            self.current_index = min(len(self.image_files) - 1,
                                     self.current_index + 1)
            self.show_fullscreen(self.image_files[self.current_index])

        elif key == Gdk.KEY_Up:
            self.rotation_angle = (self.rotation_angle + 90) % 360
            self._request_draw()

        elif key == Gdk.KEY_Down:
            self.rotation_angle = (self.rotation_angle - 90) % 360
            self._request_draw()

        elif key == Gdk.KEY_0:
            self.scale_factor = 1.0
            self.offset = (0, 0)
            self._request_draw()

        elif key == Gdk.KEY_f:
            self._fit_scale()
            self.offset = (0, 0)
            self._request_draw()

        elif key == Gdk.KEY_c:
            wl_copy_image(self.current_image_path)

        elif key == Gdk.KEY_w:
            set_wallpaper(self.current_image_path)

        elif key == Gdk.KEY_d:
            self._trash_current()

        elif key == Gdk.KEY_i:
            self._show_image_info()

        elif key == Gdk.KEY_Home:
            self.reset_animation()
            self.current_index = 0
            self.show_fullscreen(self.image_files[self.current_index])

        elif key == Gdk.KEY_End:
            self.reset_animation()
            self.current_index = len(self.image_files) - 1
            self.show_fullscreen(self.image_files[self.current_index])

    def _trash_current(self):
        if not self.image_files:
            return
        path = self.image_files[self.current_index]
        if trash_file(path):
            self.image_files.pop(self.current_index)
            self.update_thumbnails()
            if not self.image_files:
                self.close_fullscreen()
                return
            self.current_index = min(self.current_index, len(self.image_files) - 1)
            self.show_fullscreen(self.image_files[self.current_index])
        else:
            self._notify("Could not move to trash (install gio or trash-cli)")

    def _notify(self, msg: str):
        try:
            subprocess.Popen(["notify-send", "-a", "Picasa", "-t", "3000", msg],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except FileNotFoundError:
            print(f"[picasa] {msg}")

    def _show_image_info(self):
        if not self.pixbuf:
            return
        path = self.current_image_path
        try:
            stat = os.stat(path)
            size_kb = stat.st_size / 1024
            from datetime import datetime
            mtime = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M")
        except OSError:
            size_kb, mtime = 0, "unknown"

        info_lines = [
            f"File:      {os.path.basename(path)}",
            f"Path:      {path}",
            f"Size:      {size_kb:.1f} KB",
            f"Modified:  {mtime}",
            f"Dimensions:{self.pixbuf.get_width()} × {self.pixbuf.get_height()} px",
            f"Channels:  {self.pixbuf.get_n_channels()}",
        ]

        parent = self.fullscreen_window or self
        d = Gtk.MessageDialog(
            transient_for=parent,
            modal=True,
            message_type=Gtk.MessageType.INFO,
            buttons=Gtk.ButtonsType.CLOSE,
            text="Image Information",
        )
        d.format_secondary_text("\n".join(info_lines))
        d.run()
        d.destroy()

    def show_context_menu(self, widget, event, image_path):
        if event.button != 3:
            return

        menu = Gtk.Menu()

        items = [
            ("Copy image  [C]",            self.copy_image_to_clipboard),
            ("Copy path to image",          self.copy_path),
            ("Copy path to folder",         self.copy_folder_path),
            ("Set as wallpaper  [W]",       self._ctx_set_wallpaper),
            ("Image info  [I]",             self._ctx_info),
            ("Move to trash  [D]",          self._ctx_trash),
            ("Open in file manager",        self.open_folder),
        ]
        for label, cb in items:
            item = Gtk.MenuItem(label=label)
            item.connect("activate", cb, image_path)
            menu.append(item)

        menu.show_all()
        menu.popup_at_pointer(event)

    def copy_image_to_clipboard(self, widget, image_path):
        wl_copy_image(image_path)

    def copy_path(self, widget, image_path):
        wl_copy_text(image_path)

    def copy_folder_path(self, widget, image_path):
        wl_copy_text(os.path.dirname(image_path))

    def _ctx_set_wallpaper(self, widget, image_path):
        set_wallpaper(image_path)

    def _ctx_info(self, widget, image_path):
        self._show_image_info()

    def _ctx_trash(self, widget, image_path):
        self._trash_current()

    def open_folder(self, widget, image_path):
        managers = [
            ["thunar", image_path],
            ["dolphin", "--select", image_path],
            ["nautilus", "--select", image_path],
            ["nemo", "--select", image_path],
            ["pcmanfm", os.path.dirname(image_path)],
        ]
        for cmd in managers:
            if subprocess.call(["which", cmd[0]],
                               stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL) == 0:
                subprocess.Popen(cmd)
                return
        os.system(f'xdg-open "{os.path.dirname(image_path)}"')

if __name__ == "__main__":
    os.environ.setdefault("GDK_BACKEND", "wayland,x11")

    image_path = sys.argv[1] if len(sys.argv) > 1 else None
    win = PhotoViewer(image_path)
    win.connect("destroy", Gtk.main_quit)
    win.show_all()
    Gtk.main()
