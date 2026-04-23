from __future__ import annotations

from pathlib import Path

from PySide6 import QtCore, QtGui

from tools.board_tools.image import apply_image_tool_stack, normalize_tool_stack

try:
    import cv2  # type: ignore
except Exception:  # pragma: no cover - optional video backend
    cv2 = None  # type: ignore

try:  # Optional OpenEXR header access for channels/metadata.
    import OpenEXR  # type: ignore
    import Imath  # type: ignore
except Exception:  # pragma: no cover - optional exr backend
    OpenEXR = None  # type: ignore
    Imath = None  # type: ignore


def _downscale_rgb_for_preview(rgb: object, max_dim: int):
    import numpy as np  # type: ignore

    arr = np.asarray(rgb)
    if arr.ndim != 3 or arr.shape[2] < 3:
        return arr
    h = int(arr.shape[0])
    w = int(arr.shape[1])
    target = int(max_dim)
    if target <= 0 or (w <= target and h <= target):
        return arr
    scale = float(target) / float(max(w, h))
    new_w = max(1, int(round(w * scale)))
    new_h = max(1, int(round(h * scale)))
    if cv2 is not None:
        try:
            return cv2.resize(arr, (new_w, new_h), interpolation=cv2.INTER_AREA)
        except Exception:
            pass
    ys = np.linspace(0, h - 1, new_h).astype(np.int32)
    xs = np.linspace(0, w - 1, new_w).astype(np.int32)
    return arr[ys][:, xs]


class VideoToSequenceWorker(QtCore.QObject):
    progress = QtCore.Signal(int, int)
    finished = QtCore.Signal(bool, object, object)

    def __init__(self, video_path: Path, out_dir: Path) -> None:
        super().__init__()
        self._video_path = video_path
        self._out_dir = out_dir
        self._cancel = False

    @QtCore.Slot()
    def run(self) -> None:
        if cv2 is None:
            self.finished.emit(False, None, "OpenCV not available for video conversion.")
            return
        try:
            cap = cv2.VideoCapture(str(self._video_path))
            if not cap.isOpened():
                cap.release()
                self.finished.emit(False, None, "Failed to open video.")
                return
            total = int(cap.get(getattr(cv2, "CAP_PROP_FRAME_COUNT", 7)) or 0)
            idx = 0
            stem = self._video_path.stem
            while True:
                if self._cancel:
                    cap.release()
                    self.finished.emit(False, None, "Conversion cancelled.")
                    return
                ok, frame = cap.read()
                if not ok or frame is None:
                    break
                frame_name = f"{stem}_{idx:04d}.png"
                frame_path = self._out_dir / frame_name
                cv2.imwrite(str(frame_path), frame)
                idx += 1
                self.progress.emit(idx, total)
            cap.release()
            if idx <= 0:
                self.finished.emit(False, None, "No frames extracted.")
                return
            self.finished.emit(True, self._out_dir, None)
        except Exception as exc:
            self.finished.emit(False, None, str(exc))

    def cancel(self) -> None:
        self._cancel = True


class ExrInfoWorker(QtCore.QObject):
    finished = QtCore.Signal(bool, object, object, object)

    def __init__(self, path: Path) -> None:
        super().__init__()
        self._path = path

    @QtCore.Slot()
    def run(self) -> None:
        try:
            if OpenEXR is not None:
                exr = OpenEXR.InputFile(str(self._path))
                header = exr.header()
                channels = sorted(list(header.get("channels", {}).keys()))
                dw = header.get("dataWindow")
                size = None
                if dw is not None:
                    w = int(dw.max.x - dw.min.x + 1)
                    h = int(dw.max.y - dw.min.y + 1)
                    size = QtCore.QSize(w, h)
                note = "Channels from OpenEXR header."
                self.finished.emit(True, channels, size, note)
                return
            if cv2 is None:
                self.finished.emit(False, [], None, "OpenEXR/OpenCV not available.")
                return
            img = cv2.imread(str(self._path), cv2.IMREAD_UNCHANGED)
            if img is None:
                self.finished.emit(False, [], None, "Failed to read EXR.")
                return
            channels = []
            if img.ndim == 2:
                channels = ["Y"]
            elif img.shape[2] == 1:
                channels = ["Y"]
            elif img.shape[2] == 3:
                channels = ["B", "G", "R"]
            elif img.shape[2] == 4:
                channels = ["B", "G", "R", "A"]
            else:
                channels = [f"C{i}" for i in range(int(img.shape[2]))]
            size = QtCore.QSize(int(img.shape[1]), int(img.shape[0]))
            note = "Channels inferred via OpenCV (order may be BGR)."
            self.finished.emit(True, channels, size, note)
        except Exception as exc:
            self.finished.emit(False, [], None, str(exc))


class ExrChannelPreviewWorker(QtCore.QObject):
    finished = QtCore.Signal(bool, str, object, object)

    def __init__(
        self,
        path: Path,
        channel: str,
        gamma: float,
        srgb: bool,
        max_dim: int = 0,
        tool_stack: object = None,
    ) -> None:
        super().__init__()
        self._path = path
        self._channel = channel
        self._gamma = max(0.1, float(gamma))
        self._srgb = bool(srgb)
        self._max_dim = int(max_dim)
        self._tool_stack = normalize_tool_stack(tool_stack)

    @QtCore.Slot()
    def run(self) -> None:
        if OpenEXR is None or Imath is None:
            self.finished.emit(False, self._channel, None, "OpenEXR not available.")
            return
        try:
            import numpy as np  # type: ignore
        except Exception:
            self.finished.emit(False, self._channel, None, "NumPy not available.")
            return
        try:
            exr = OpenEXR.InputFile(str(self._path))
            header = exr.header()
            dw = header.get("dataWindow")
            if dw is None:
                self.finished.emit(False, self._channel, None, "Missing dataWindow.")
                return
            w = int(dw.max.x - dw.min.x + 1)
            h = int(dw.max.y - dw.min.y + 1)
            pt = Imath.PixelType(Imath.PixelType.FLOAT)
            channel = self._channel
            prefix = ""
            if channel.endswith(".RGB") or channel.endswith(".RGBA"):
                prefix = channel.rsplit(".", 1)[0]
                channel = channel.rsplit(".", 1)[1]
            if channel in ("RGB", "RGBA"):

                def read_chan(name: str) -> np.ndarray:
                    try:
                        raw_c = exr.channel(name, pt)
                        arr_c = np.frombuffer(raw_c, dtype=np.float32)
                        return arr_c.reshape((h, w))
                    except Exception:
                        return np.zeros((h, w), dtype=np.float32)

                def name_for(suffix: str) -> str:
                    return f"{prefix}.{suffix}" if prefix else suffix

                r = read_chan(name_for("R"))
                g = read_chan(name_for("G"))
                b = read_chan(name_for("B"))
                img = np.stack([r, g, b], axis=-1)
            else:
                raw = exr.channel(self._channel, pt)
                arr = np.frombuffer(raw, dtype=np.float32)
                if arr.size != w * h:
                    self.finished.emit(False, self._channel, None, "Channel size mismatch.")
                    return
                img = arr.reshape((h, w))
            valid = np.isfinite(img)
            if not valid.any():
                self.finished.emit(False, self._channel, None, "Channel has no finite values.")
                return
            min_v = float(np.min(img[valid]))
            max_v = float(np.max(img[valid]))
            if max_v - min_v < 1e-8:
                norm = np.zeros_like(img, dtype=np.float32)
            else:
                norm = (img - min_v) / (max_v - min_v)
            norm = np.clip(norm, 0.0, 1.0)
            if self._srgb:
                norm = np.power(norm, 1.0 / self._gamma, where=norm > 0)
            if norm.ndim == 2:
                img8 = (norm * 255.0).astype(np.uint8)
                rgb = np.stack([img8, img8, img8], axis=-1)
            else:
                rgb = (norm * 255.0).astype(np.uint8)
            rgb = apply_image_tool_stack(rgb, self._tool_stack)
            rgb = _downscale_rgb_for_preview(rgb, self._max_dim)
            payload = (int(rgb.shape[1]), int(rgb.shape[0]), rgb.tobytes())
            self.finished.emit(True, self._channel, payload, None)
        except Exception as exc:
            self.finished.emit(False, self._channel, None, str(exc))


class ImageAdjustPreviewWorker(QtCore.QObject):
    finished = QtCore.Signal(bool, object, object)

    def __init__(
        self,
        path: Path,
        max_dim: int = 0,
        tool_stack: object = None,
    ) -> None:
        super().__init__()
        self._path = path
        self._max_dim = int(max_dim)
        self._tool_stack = normalize_tool_stack(tool_stack)

    @QtCore.Slot()
    def run(self) -> None:
        try:
            import numpy as np  # type: ignore
        except Exception:
            self.finished.emit(False, None, "NumPy not available.")
            return
        img = None
        if cv2 is not None:
            try:
                img = cv2.imread(str(self._path), cv2.IMREAD_UNCHANGED)
            except Exception:
                img = None
        if img is None:
            qimg = QtGui.QImage(str(self._path))
            if qimg.isNull():
                self.finished.emit(False, None, "Failed to read image.")
                return
            qimg = qimg.convertToFormat(QtGui.QImage.Format.Format_RGB888)
            w = int(qimg.width())
            h = int(qimg.height())
            if w <= 0 or h <= 0:
                self.finished.emit(False, None, "Failed to read image.")
                return
            ptr = qimg.bits()
            arr = np.frombuffer(ptr, dtype=np.uint8)
            arr = arr.reshape((h, int(qimg.bytesPerLine())))
            img = arr[:, : w * 3].reshape((h, w, 3)).copy()
        if img is None:
            self.finished.emit(False, None, "Failed to read image.")
            return
        if img.ndim == 2:
            img = np.stack([img, img, img], axis=-1)
        if img.ndim == 3 and img.shape[2] == 1:
            img = np.repeat(img, 3, axis=2)
        if img.ndim == 3 and img.shape[2] >= 3:
            img = img[:, :, :3]
        if img.dtype != np.uint8:
            img_f = img.astype(np.float32)
            max_val = float(np.nanmax(img_f)) if img_f.size else 1.0
            if max_val <= 1.0:
                img_f = img_f * 255.0
            else:
                img_f = (img_f / max_val) * 255.0
            img = np.clip(img_f, 0, 255).astype(np.uint8)
        if cv2 is not None:
            try:
                rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            except Exception:
                rgb = img
        else:
            rgb = img
        rgb = apply_image_tool_stack(rgb, self._tool_stack)
        rgb = _downscale_rgb_for_preview(rgb, self._max_dim)
        payload = (int(rgb.shape[1]), int(rgb.shape[0]), rgb.tobytes())
        self.finished.emit(True, payload, None)


class VideoSegmentWorker(QtCore.QObject):
    status = QtCore.Signal(str)
    progress = QtCore.Signal(int, int)
    finished = QtCore.Signal(bool, object, object)

    def __init__(self, video_path: Path, out_dir: Path, start_frame: int, end_frame: int) -> None:
        super().__init__()
        self._video_path = video_path
        self._out_dir = out_dir
        self._start = max(0, int(start_frame))
        self._end = max(self._start, int(end_frame))
        self._cancel = False

    @QtCore.Slot()
    def run(self) -> None:
        if cv2 is None:
            self.finished.emit(False, None, "OpenCV not available.")
            return
        try:
            self.status.emit("Opening video...")
            cap = cv2.VideoCapture(str(self._video_path))
            if not cap.isOpened():
                cap.release()
                self.finished.emit(False, None, "Failed to open video.")
                return
            self.status.emit(f"Seeking to frame {self._start}...")
            cap.set(1, self._start)
            idx = 0
            total = max(1, self._end - self._start + 1)
            stem = self._video_path.stem
            self.status.emit(f"Exporting {total} frames...")
            while True:
                if self._cancel:
                    cap.release()
                    self.finished.emit(False, None, "Export cancelled.")
                    return
                pos = int(cap.get(1) or 0)
                if pos > self._end:
                    break
                ok, frame = cap.read()
                if not ok or frame is None:
                    break
                frame_name = f"{stem}_{self._start + idx:04d}.png"
                frame_path = self._out_dir / frame_name
                cv2.imwrite(str(frame_path), frame)
                idx += 1
                self.progress.emit(idx, total)
            cap.release()
            if idx <= 0:
                self.finished.emit(False, None, "No frames exported.")
                return
            self.finished.emit(True, self._out_dir, None)
        except Exception as exc:
            self.finished.emit(False, None, str(exc))

    def cancel(self) -> None:
        self._cancel = True


class UiBridge(QtCore.QObject):
    def __init__(self, controller: QtCore.QObject, parent: QtCore.QObject | None = None) -> None:
        super().__init__(parent)
        self._controller = controller

    @QtCore.Slot(bool, object, object, object)
    def on_exr_info_finished(self, success: bool, channels_obj: object, size_obj: object, note_obj: object) -> None:
        self._controller._handle_exr_info_finished(success, channels_obj, size_obj, note_obj)

    @QtCore.Slot(bool, str, object, object)
    def on_exr_preview_finished(self, success: bool, channel: str, payload: object, error: object) -> None:
        self._controller._handle_exr_preview_finished(success, channel, payload, error)
