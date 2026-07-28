import math
import os
import sys
import tkinter as tk
import webbrowser
import xml.etree.ElementTree as ET
from tkinter import filedialog, messagebox, ttk

try:
    import customtkinter as ctk
except ImportError:
    sys.stderr.write(
        "customtkinter is required. Install with: pip install customtkinter\n"
    )
    raise

import numpy as np

try:
    import svgpathtools
except ImportError:
    sys.stderr.write(
        "svgpathtools is required. Install with: pip install svgpathtools\n"
    )
    raise

import matplotlib
matplotlib.use("TkAgg")
import matplotlib.patches
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg


HALF_BOX = 1.45 
EPS = 1e-4 #Dedupe


def _iter_subpaths(path):
    try:
        subs = path.subpaths()
    except AttributeError:
        return [path]
    if not isinstance(subs, (list, tuple)):
        try:
            subs = list(subs)
        except TypeError:
            return [path]
    if not subs:
        return [path]
    return list(subs)


def parse_paths_from_svg(svg_path):
    
    #Parse SVG file and return a list of svgpathtools.Path objects.
    
    try:
        tree = ET.parse(svg_path)
    except ET.ParseError as exc:
        raise ValueError(f"SVG file is not valid XML: {exc}")
    except OSError as exc:
        raise ValueError(f"Could not read SVG file: {exc}")

    root = tree.getroot()
    ns_prefix = ""
    if root.tag.startswith("{"):
        ns_uri = root.tag[1 :].split("}", 1)[0]
        ns_prefix = "{" + ns_uri + "}"

    parsed = []
    for path_elem in root.iter(f"{ns_prefix}path"):
        d = path_elem.get("d")
        if not d or not d.strip():
            continue
        try:
            p = svgpathtools.parse_path(d)
        except Exception as exc:
            print(
                f"Warning: skipping malformed <path> 'd' attribute: {exc}",
                file=sys.stderr,
            )
            continue
        if p is None:
            continue
        parsed.append(p)

    return parsed


def longest_closed_subpath(paths):
    #Find longest closed subpath from list of svgpathtools paths.

    candidates = []
    for path in paths:
        for sub in _iter_subpaths(path):
            try:
                closed = sub.isclosed()
            except Exception:
                closed = False
            if not closed:
                continue
            try:
                length = sub.length()
            except Exception:
                length = 0.0
            if length <= 0:
                continue
            candidates.append((length, sub))
    if not candidates:
        raise ValueError(
            "No closed paths found in the SVG. The tool needs a closed "
            "polygon (since the table has no overlapping edges or voids)."
        )
    candidates.sort(key=lambda item: -item[0])
    return candidates[0][1]


def sample_subpath(subpath, max_segment_length):
    #Sample every segment into points so adjacent samples are at most `max_segment_length` apart in the SVG's defined coordinates.

    pts = []
    for seg in subpath:
        try:
            seg_len = seg.length()
        except Exception:
            seg_len = 0.0
        if seg_len == 0:
            continue
        n = max(1, int(math.ceil(seg_len / max_segment_length)))
        for i in range(n):
            t = i / float(n)
            p = seg.point(t)
            pts.append((float(p.real), float(p.imag)))
        p = seg.point(1.0)
        pts.append((float(p.real), float(p.imag)))
    return pts


def normalize_to_box(points, half_size=HALF_BOX):
    #scale to fit within table
    if not points:
        return []
    pts = np.array(points, dtype=float)
    if pts.shape[0] == 0:
        return []
    # try to get the right point order (not sure exactly how y'all do this, so I'm just guessing. Can just be fixed in the online generator if it complains)
    pts[:, 1] = -pts[:, 1]
    min_x, min_y = pts.min(axis=0)
    max_x, max_y = pts.max(axis=0)
    width = max_x - min_x
    height = max_y - min_y
    if width <= 0 or height <= 0:
        return [(float(x), float(-y)) for x, y in points]
    #adjust scale to try and preserve aspect ratio
    scale = (2.0 * half_size) / max(width, height)
    cx = (min_x + max_x) / 2.0
    cy = (min_y + max_y) / 2.0
    pts[:, 0] = (pts[:, 0] - cx) * scale
    pts[:, 1] = (pts[:, 1] - cy) * scale
    return [(float(x), float(y)) for x, y in pts]


def dedupe_all(points, eps=EPS):
    #deduplicate vertices
    if not points:
        return []
    out = [points[0]]
    for p in points[1:]:
        is_dup = False
        for kept in out:
            if abs(p[0] - kept[0]) <= eps and abs(p[1] - kept[1]) <= eps:
                is_dup = True
                break
        if not is_dup:
            out.append(p)
    return out


def _signed_area(points):
    if len(points) < 3:
        return 0.0
    area = 0.0
    n = len(points)
    for i in range(n):
        x1, y1 = points[i]
        x2, y2 = points[(i + 1) % n]
        area += x1 * y2 - x2 * y1
    return area / 2.0


    #point order for compatibility with online generator
def order_counterclockwise_from_topleft(points):
    if len(points) <= 2:
        return points[:]

    result = list(points)
    
    if _signed_area(result) < 0:
        result.reverse()
  
    best_idx = 0
    bx, by = result[0]
    for i in range(1, len(result)):
        x, y = result[i]
        if y > by or (abs(y - by) <= EPS and x < bx):
            best_idx = i
            bx, by = x, y
    return result[best_idx:] + result[:best_idx]


def simplify_collinear(points, eps=EPS):
    #remove excess vertices if colinear
    if len(points) <= 3:
        return points[:]

    out = [points[0]]
    for i in range(1, len(points) - 1):
        prev = out[-1] 
        curr = points[i]
        nxt = points[i + 1]
        ax = curr[0] - prev[0]
        ay = curr[1] - prev[1]
        bx = nxt[0] - prev[0]
        by = nxt[1] - prev[1]
        cross = abs(ax * by - ay * bx)
        dot = ax * (nxt[0] - curr[0]) + ay * (nxt[1] - curr[1])

        if cross > eps or dot < 0:
            out.append(curr)

    out.append(points[-1])
    return out


def estimate_normalization_scale(subpath):
    #debug output, checking scaling values, not output in ui
    pts = []
    for seg in subpath:
        pts.append((float(seg.start.real), float(seg.start.imag)))
        pts.append((float(seg.end.real), float(seg.end.imag)))
    if not pts:
        return None
    arr = np.array(pts, dtype=float)
    arr[:, 1] = -arr[:, 1]  # flip
    w = arr[:, 0].max() - arr[:, 0].min()
    h = arr[:, 1].max() - arr[:, 1].min()
    max_dim = max(w, h)
    if max_dim <= 0:
        return None
    return (2.0 * HALF_BOX) / max_dim


def _otsu_threshold(gray):
    #convert raster image to grascale and 2 bit color. I have literally no idea how this works
    #I just copied some code online for this and it magically works I think
    hist, _ = np.histogram(gray.ravel(), bins=256, range=(0, 1))
    total = gray.size
    hist = hist.astype(np.float64)

    sum_total = np.dot(np.arange(256), hist)
    sum_b = 0.0
    w_b = 0.0
    var_max = 0.0
    threshold = 0

    for t in range(256):
        w_b += hist[t]
        if w_b == 0:
            continue
        w_f = total - w_b
        if w_f == 0:
            break

        sum_b += t * hist[t]
        mean_b = sum_b / w_b
        mean_f = (sum_total - sum_b) / w_f

        var_between = w_b * w_f * (mean_b - mean_f) ** 2

        if var_between > var_max:
            var_max = var_between
            threshold = t

    return threshold / 255.0


RASTER_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.bmp', '.tiff', '.tif'}


def _gaussian_blur(img, sigma=1.5):
    #apply blur to soften edges when converting raster images
    size = int(2 * sigma * 3 + 1)
    if size % 2 == 0:
        size += 1
    k = np.arange(size) - size // 2
    kernel = np.exp(-k**2 / (2 * sigma**2))
    kernel /= kernel.sum()
    pad = size // 2

    from numpy.lib.stride_tricks import sliding_window_view

    padded = np.pad(img, pad, mode='edge')
    windows_h = sliding_window_view(padded, size, axis=1)[pad:-pad]
    blurred = np.sum(
        windows_h * kernel[np.newaxis, np.newaxis, :], axis=2
    )

    padded_v = np.pad(blurred, pad, mode='edge')
    windows_v = sliding_window_view(padded_v, size, axis=0)
    return np.sum(
        windows_v * kernel[np.newaxis, np.newaxis, :], axis=2
    )


def _smooth_contour(vertices, sigma=1.5):
    if len(vertices) < 6:
        return vertices

    size = int(2 * sigma * 3 + 1)
    if size % 2 == 0:
        size += 1
    k = np.arange(size) - size // 2
    weights = np.exp(-k**2 / (2 * sigma**2))
    weights /= weights.sum()
    pad = size // 2

    n = len(vertices)
    padded = np.vstack([vertices[-pad:], vertices, vertices[:pad]])

    from numpy.lib.stride_tricks import sliding_window_view
    windows = sliding_window_view(padded, size, axis=0)  # (n, 2, size)
    return np.sum(
        windows * weights[np.newaxis, np.newaxis, :], axis=2
    )


def _morphological_close(binary, kernel_size=5):
    """Close small gaps in a binary image via dilation then erosion.
    Uses a square flat structuring element."""
    from numpy.lib.stride_tricks import sliding_window_view
    pad = kernel_size // 2

    # Dilation — True if ANY pixel in the window is True
    padded = np.pad(binary, pad, mode='constant', constant_values=False)
    windows = sliding_window_view(padded, (kernel_size, kernel_size)).reshape(
        binary.shape[0], binary.shape[1], -1
    )
    dilated = np.any(windows, axis=2)

    # Erosion — True only if ALL pixels in the window are True
    padded = np.pad(dilated, pad, mode='constant', constant_values=True)
    windows = sliding_window_view(padded, (kernel_size, kernel_size)).reshape(
        binary.shape[0], binary.shape[1], -1
    )
    eroded = np.all(windows, axis=2)

    return eroded



def _largest_foreground_mask(binary):
    from collections import deque
    h, w = binary.shape
    visited = np.zeros_like(binary)
    best_mask = np.zeros_like(binary)
    best_size = 0

    for y in range(h):
        for x in range(w):
            if not binary[y, x] or visited[y, x]:
                continue
            # BFS flood fill this component
            comp = []
            q = deque([(x, y)])
            visited[y, x] = True
            while q:
                cx, cy = q.popleft()
                comp.append((cx, cy))
                # 8-connected neighbours
                for nx in (cx - 1, cx, cx + 1):
                    for ny in (cy - 1, cy, cy + 1):
                        if (nx != cx or ny != cy) and 0 <= nx < w and 0 <= ny < h:
                            if binary[ny, nx] and not visited[ny, nx]:
                                visited[ny, nx] = True
                                q.append((nx, ny))
            if len(comp) > best_size:
                best_size = len(comp)
                best_mask.fill(False)
                for px, py in comp:
                    best_mask[py, px] = True
    return best_mask


def _trace_outer_boundary(binary):
    h, w = binary.shape
    start = None
    for y in range(h):
        for x in range(w):
            if binary[y, x]:
                start = (x, y)
                break
        if start is not None:
            break
    if start is None:
        return []

    dx = [1, 1, 0, -1, -1, -1, 0, 1]
    dy = [0, 1, 1, 1, 0, -1, -1, -1]

    backtrack = 4  

    boundary = []
    cx, cy = start

    while True:
        boundary.append((cx, cy))

        found = False
        for i in range(8):
            d = (backtrack + 1 + i) % 8
            nx, ny = cx + dx[d], cy + dy[d]
            if 0 <= nx < w and 0 <= ny < h and binary[ny, nx]:
                cx, cy = nx, ny
                backtrack = (d + 4) % 8 
                found = True
                break

        if not found:
            break

        if (cx, cy) == start:
            break

    return boundary


def _raster_to_contour_points(image_path):
    from matplotlib import pyplot as plt

    img = plt.imread(image_path)

    if img.ndim == 3 and img.shape[2] == 4:
        rgb = img[:, :, :3]
        alpha = img[:, :, 3:4]
        img_rgb = rgb * alpha + (1.0 - alpha)
    elif img.ndim == 3:
        img_rgb = img[:, :, :3]
    else:
        img_rgb = np.stack([img] * 3, axis=2)

    gray = np.mean(img_rgb, axis=2)

    blurred = _gaussian_blur(gray, sigma=3.0)

    threshold = _otsu_threshold(blurred)
    binary = blurred < threshold

    h, w = gray.shape
    border_pixels = np.concatenate([
        gray[0, :],
        gray[-1, :],
        gray[1:-1, 0],
        gray[1:-1, -1],
    ])
    if np.mean(border_pixels) < threshold:
        binary = ~binary

    binary = _morphological_close(binary, kernel_size=5)

    raw = _trace_outer_boundary(binary)
    if len(raw) < 6:
        raise ValueError(
            "The detected shape is too small to trace.  "
            "Use a larger or higher-contrast image."
        )
    #try to find the largest shape if multiple are detected
    binary = _largest_foreground_mask(binary)

    raw = _trace_outer_boundary(binary)
    if len(raw) < 6:
        raise ValueError(
            "The detected shape is too small to trace.  "
            "Use a larger or higher-contrast image."
        )

    smoothed = _smooth_contour(raw, sigma=1.5)

    return [(float(p[0]), float(p[1])) for p in smoothed]


def convert_image_to_polygon(image_path, target_vertices):

    ext = os.path.splitext(image_path)[1].lower()

    if ext in RASTER_EXTENSIONS:
        raw_points = _raster_to_contour_points(image_path)
        normalized = normalize_to_box(raw_points, half_size=HALF_BOX)
        resampled = _uniform_resample(normalized, target_vertices)
        cleaned = dedupe_all(resampled, eps=EPS)
        simplified = simplify_collinear(cleaned)
        ordered = order_counterclockwise_from_topleft(simplified)

        metadata = {
            "raw_vertices": len(raw_points),
            "final_vertices": len(ordered),
            "target_vertices": target_vertices,
        }
        return ordered, metadata

    elif ext == '.svg':
        paths = parse_paths_from_svg(image_path)
        if not paths:
            raise ValueError(
                "No <path> elements with a parseable 'd' attribute were "
                "found in the SVG. The file may be corrupted."
            )
        main = longest_closed_subpath(paths)
    else:
        raise ValueError(f"Unsupported file type: {ext}")

    # SVG path processing
    try:
        arc_length_svg = main.length()
    except Exception:
        arc_length_svg = 0.0
    if arc_length_svg <= 0:
        raise ValueError("Path has zero arc length.")
    if not isinstance(target_vertices, (int, float)) or target_vertices <= 0:
        raise ValueError(
            f"target_vertices must be a positive number, got {target_vertices!r}"
        )

    scale = estimate_normalization_scale(main)
    if not scale or scale <= 0:
        raise ValueError("Path has zero or degenerate bounding box.")

    step_svg = arc_length_svg / target_vertices

    raw_points = sample_subpath(main, step_svg)
    normalized = normalize_to_box(raw_points, half_size=HALF_BOX)
    resampled = _uniform_resample(normalized, target_vertices)
    cleaned = dedupe_all(resampled, eps=EPS)
    simplified = simplify_collinear(cleaned)
    ordered = order_counterclockwise_from_topleft(simplified)

    metadata = {
        "raw_vertices": len(raw_points),
        "final_vertices": len(ordered),
        "scale": scale,
        "step_svg": step_svg,
        "target_vertices": target_vertices,
        "arc_length_svg": arc_length_svg,
    }
    return ordered, metadata


def _uniform_resample(points, n):
    if len(points) < 3 or n >= len(points):
        return points[:]

    pts = np.array(points, dtype=float)
    diffs = np.diff(pts, axis=0)
    seg_lengths = np.sqrt(np.sum(diffs ** 2, axis=1))
    cum_lengths = np.concatenate([[0.0], np.cumsum(seg_lengths)])
    total_length = cum_lengths[-1]

    sample_lengths = np.linspace(0, total_length, n, endpoint=False)

    result = []
    idx = 0
    for sl in sample_lengths:
        while idx < len(cum_lengths) - 1 and cum_lengths[idx + 1] < sl:
            idx += 1
        seg_start = cum_lengths[idx]
        seg_end = cum_lengths[idx + 1]
        t = (sl - seg_start) / (seg_end - seg_start) if seg_end > seg_start else 0.0
        x = pts[idx, 0] + t * (pts[idx + 1, 0] - pts[idx, 0])
        y = pts[idx, 1] + t * (pts[idx + 1, 1] - pts[idx, 1])
        result.append((float(x), float(y)))

    return result


def format_polygon_output(polygon, decimals=4):
    return "\n".join(f"{p[0]:.{decimals}f},{p[1]:.{decimals}f}" for p in polygon)


# ---------------------------------------------------------------------------
# Tkinter UI
# ---------------------------------------------------------------------------

class SvgToSpooker:
    def __init__(self, root):
        self.root = root
        self.root.title("Image to Spooker Table Converter")
        self.root.geometry("1200x720")
        self.root.minsize(800, 520)

        self.filepath = None
        self.polygon = []
        self.metadata = {}
        self.status_var = tk.StringVar(
            value="Ready. Use the file picker to load an image."
        )

        self._build_ui()

    #ui stuff

    def _setup_dark_style(self):
        style = ttk.Style()
        style.theme_use("clam")
        # Base colors
        bg = "#0d1117"
        accent = "#010409"
        fg = "#e6edf3"
        sel = "#580aff"
        entry_bg = "#010409"
        disabled_fg = "#484f58"
        border = "#30363d"

        style.configure(".", background=bg, foreground=fg, fieldbackground=accent,
                        selectbackground=sel, selectforeground=fg)
        style.configure("TFrame", background=bg)
        style.configure("TLabel", background=bg, foreground=fg)
        style.configure("TLabelframe", background=bg, foreground=fg, bordercolor=border)
        style.configure("TLabelframe.Label", background=bg, foreground=fg)
        style.configure("TButton", background=accent, foreground=fg, bordercolor=border,
                        focuscolor="none", lightcolor=accent, darkcolor=accent)
        style.map("TButton",
                   background=[("active", "#1c2128"), ("disabled", accent)],
                   foreground=[("disabled", disabled_fg)])
        style.configure("TEntry", fieldbackground=entry_bg, foreground=fg,
                        bordercolor=border)
        style.map("TEntry", fieldbackground=[("focus", "#161b22")])
        style.configure("TPanedwindow", background=bg, bordercolor=border)
        style.configure("Vertical.TScrollbar", background=accent, bordercolor=border,
                        arrowcolor=fg, troughcolor=bg)
        style.map("Vertical.TScrollbar",
                   background=[("active", "#1c2128")])
        style.configure("Horizontal.TScale", background=bg, troughcolor=border,
                        lightcolor=border, darkcolor=border, bordercolor=border)

    def _build_ui(self):
        self._setup_dark_style()

        outer = ttk.Frame(self.root, padding=8)
        outer.pack(fill=tk.BOTH, expand=True)

        controls = ttk.LabelFrame(outer, text="Inputs", padding=8)
        controls.pack(fill=tk.X)

        #file picker
        ttk.Button(controls, text="Select image\u2026",
                   command=self._pick_file).grid(row=0, column=0, padx=(0, 8))
        self.file_label = ttk.Label(controls, text="(no file selected)")
        self.file_label.grid(row=0, column=1, columnspan=3, sticky="w")

        #resolution + buttons
        ttk.Label(controls, text="Resolution:").grid(row=1, column=0, sticky="e",
                                                     pady=(8, 0))
        self.resolution_var = tk.StringVar(value="24")
        self.resolution_int = tk.IntVar(value=24)
        res_entry = ttk.Entry(controls, textvariable=self.resolution_var,
                              width=8)
        res_entry.grid(row=1, column=1, sticky="w", pady=(8, 0), padx=(0, 4))
        res_slider = ttk.Scale(controls, from_=8, to=48, orient=tk.HORIZONTAL,
                               variable=self.resolution_int,
                               command=self._resolution_slider_moved)
        res_slider.grid(row=1, column=2, sticky="ew", pady=(8, 0), padx=(0, 8))
        self.resolution_var.trace_add("write", self._resolution_entry_typed)

        btn_style = dict(
            corner_radius=8,
            fg_color="#010409",
            hover_color="#1c2128",
            text_color="#e6edf3",
            border_width=1,
            border_color="#30363d",
        )
        self.open_gen_btn = ctk.CTkButton(
            controls, text="Open Online Generator",
            command=self._open_generator, **btn_style,
        )
        self.open_gen_btn.grid(row=0, column=4, rowspan=2, padx=(4, 4),
                                sticky="ns")
        self.convert_btn = ctk.CTkButton(
            controls, text="Convert",
            command=self._convert, state="disabled", **btn_style,
        )
        self.convert_btn.grid(row=0, column=5, rowspan=2, padx=(4, 4),
                              sticky="ns")
        self.copy_btn = ctk.CTkButton(
            controls, text="Copy to Clipboard",
            command=self._copy_output, state="disabled", **btn_style,
        )
        self.copy_btn.grid(row=0, column=6, rowspan=2, padx=(4, 0),
                            sticky="ns")

        controls.columnconfigure(2, weight=1)
        controls.columnconfigure(4, weight=1)

        content = ttk.Frame(outer)
        content.pack(fill=tk.BOTH, expand=True, pady=(8, 0))
        content.columnconfigure(0, weight=1)   
        content.columnconfigure(1, weight=0)   

        bg = "#0d1117"
        fg = "#e6edf3"
        border = "#30363d"


        plot_pane = ttk.Frame(content)
        plot_pane.grid(row=0, column=0, sticky="nsew")
        plot_pane.rowconfigure(0, weight=1)
        plot_pane.columnconfigure(0, weight=1)

        self.fig = Figure(figsize=(10, 5), dpi=100, facecolor=bg)
        self.ax_orig = self.fig.add_subplot(121, facecolor=bg)
        self.ax_plot = self.fig.add_subplot(122, facecolor=bg)
        self.fig.subplots_adjust(wspace=0.05, left=0.01, right=0.99,
                                 top=0.92, bottom=0.05)
        for ax in (self.ax_orig, self.ax_plot):
            ax.set_facecolor(bg)
            ax.tick_params(colors=fg, which="both")
            for spine in ax.spines.values():
                spine.set_color(border)


        self.ax_orig.axis("off")
        self.ax_orig.set_title("Original Image", color=fg, fontsize=11)

        self.ax_plot.set_aspect("equal")
        self.ax_plot.set_xlim(-1.6, 1.6)
        self.ax_plot.set_ylim(-1.6, 1.6)
        self.ax_plot.grid(True, alpha=0.3, color=border)
        self.ax_plot.axhline(0, color=border, linewidth=0.5)
        self.ax_plot.axvline(0, color=border, linewidth=0.5)
        self.ax_plot.set_title("Table Preview", color=fg, fontsize=11)
        self.ax_plot.add_patch(
            matplotlib.patches.Rectangle(
                (-1.5, -1.5), 3.0, 3.0,
                fill=False, edgecolor=border,
                linestyle="--", linewidth=1.0,
            )
        )

        self.canvas = FigureCanvasTkAgg(self.fig, master=plot_pane)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        self._draw_axes_only()

        text_pane = tk.Frame(content, width=200, bg="#0d1117",
                             highlightthickness=0)
        text_pane.grid(row=0, column=1, sticky="ns")
        text_pane.grid_propagate(False)
        content.columnconfigure(1, weight=0)
        ttk.Label(text_pane,
                  text="Output vertices:").pack(anchor="w")
        self.output_text = tk.Text(
            text_pane, wrap=tk.NONE, font=("Consolas", 9),
            width=22, height=10,
            undo=False, bg="#010409", fg=fg, insertbackground=fg,
            selectbackground="#580aff", selectforeground=fg,
        )
        self.output_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        ysb = ttk.Scrollbar(text_pane, orient="vertical",
                            style="Vertical.TScrollbar",
                            command=self.output_text.yview)
        ysb.pack(side=tk.RIGHT, fill=tk.Y)
        self.output_text.configure(yscrollcommand=ysb.set)

        #status bar
        self.status_bar = ttk.Label(self.root, textvariable=self.status_var,
                                    relief="sunken", anchor="w", padding=(6, 2))
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)

    #event handlers

    def _pick_file(self):
        path = filedialog.askopenfilename(
            title="Choose an image",
            filetypes=[
                ("Image files", "*.svg *.png *.jpg *.jpeg *.bmp *.tiff *.tif"),
                ("SVG files", "*.svg"),
                ("PNG files", "*.png"),
                ("JPEG files", "*.jpg *.jpeg"),
                ("BMP files", "*.bmp"),
                ("TIFF files", "*.tiff *.tif"),
                ("All files", "*.*"),
            ],
        )
        if not path:
            return
        self.filepath = path
        self.file_label.config(text=os.path.basename(path))
        self.convert_btn.configure(state="normal")
        self._refresh_original_image()
        self.status_var.set(
            f"Loaded {os.path.basename(path)} "
            f"({os.path.getsize(path):,} bytes). Click Convert."
        )

    def _resolution_slider_moved(self, value):
        if getattr(self, '_updating', False):
            return
        self._updating = True
        self.resolution_var.set(str(int(float(value))))
        self._updating = False

    def _resolution_entry_typed(self, *_):
        if getattr(self, '_updating', False):
            return
        self._updating = True
        raw = self.resolution_var.get().strip()
        try:
            val = int(raw)
            if val <= 0:
                raise ValueError
            self.resolution_int.set(val)
        except ValueError:
            pass
        self._updating = False

    def _parse_resolution(self):
        raw = self.resolution_var.get().strip()
        try:
            value = int(raw)
        except ValueError:
            raise ValueError(
                f"Resolution must be a positive integer (target vertex "
                f"count), got {raw!r}."
            )
        if value <= 0:
            raise ValueError("Resolution must be a positive integer.")
        return value

    def _convert(self):
        if not self.filepath:
            messagebox.showinfo("No file", "Select an image first.")
            return
        try:
            resolution = self._parse_resolution()
        except ValueError as exc:
            messagebox.showerror("Bad resolution", str(exc))
            return
        try:
            polygon, metadata = convert_image_to_polygon(
                self.filepath, resolution
            )
        except Exception as exc:
            messagebox.showerror("Conversion failed", str(exc))
            self.status_var.set(f"Failed: {exc}")
            return
        self.polygon = polygon
        self.metadata = metadata
        self._refresh_plot()
        self._refresh_output()
        self.copy_btn.configure(state="normal")
        self.status_var.set(
            f"Generated {metadata['final_vertices']} vertices "
            f"(target {resolution}, sampled {metadata['raw_vertices']} "
            f"before dedupe"
            + (f"; arc_len={metadata['arc_length_svg']:.1f}, "
               f"step={metadata['step_svg']:.4f}"
               if 'arc_length_svg' in metadata else "")
            + ")."
        )

    def _open_generator(self):
        #Open official table generator in browser
        webbrowser.open("https://spooker-table-generator.tiiny.site/")
        self.status_var.set(
            "Opened Spooker Table Generator in your browser."
        )

    def _copy_output(self):
        if not self.polygon:
            messagebox.showinfo("Nothing to copy", "Run Convert first.")
            return
        text = format_polygon_output(self.polygon)
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.status_var.set(
            f"Copied {len(self.polygon)} vertices to clipboard."
        )

    #plotting and output renderer

    def _draw_axes_only(self):
        fg = "#e6edf3"
        border = "#30363d"
        self.ax_orig.clear()
        self.ax_orig.set_facecolor("#0d1117")
        self.ax_orig.axis("off")
        self.ax_orig.set_title("Original Image", color=fg, fontsize=11)

        self.ax_plot.clear()
        self.ax_plot.set_facecolor("#0d1117")
        self.ax_plot.set_aspect("equal")
        self.ax_plot.set_xlim(-1.6, 1.6)
        self.ax_plot.set_ylim(-1.6, 1.6)
        self.ax_plot.grid(True, alpha=0.3, color=border)
        self.ax_plot.axhline(0, color=border, linewidth=0.5)
        self.ax_plot.axvline(0, color=border, linewidth=0.5)
        self.ax_plot.tick_params(colors=fg, which="both")
        self.ax_plot.set_title("Table Preview", color=fg, fontsize=11)
        for spine in self.ax_plot.spines.values():
            spine.set_color(border)
        self.ax_plot.add_patch(
            matplotlib.patches.Rectangle(
                (-1.5, -1.5), 3.0, 3.0,
                fill=False, edgecolor=border,
                linestyle="--", linewidth=1.0,
            )
        )
        self.canvas.draw_idle()

    def _refresh_original_image(self):
        self.ax_orig.clear()
        self.ax_orig.set_facecolor("#0d1117")
        self.ax_orig.axis("off")
        self.ax_orig.set_title("Original Image", color="#e6edf3", fontsize=11)
        if not self.filepath:
            self.canvas.draw_idle()
            return
        ext = os.path.splitext(self.filepath)[1].lower()
        if ext in RASTER_EXTENSIONS:
            from matplotlib import pyplot as plt
            img = plt.imread(self.filepath)
            self.ax_orig.imshow(img, aspect="equal")
        else:
            border = "#30363d"
            self.ax_orig.text(
                0.5, 0.5, "Unable to render SVG images\nwithin this container.",
                ha="center", va="center", color="#e6edf3", fontsize=10,
                transform=self.ax_orig.transAxes,
            )
            self.ax_orig.add_patch(
                matplotlib.patches.Rectangle(
                    (0.05, 0.05), 0.9, 0.9,
                    fill=False, edgecolor=border, linewidth=1.0,
                    linestyle="--", transform=self.ax_orig.transAxes,
                )
            )
        self.canvas.draw_idle()

    def _refresh_plot(self):
        bg = "#0d1117"
        fg = "#e6edf3"
        border = "#30363d"
        poly_color = "#580aff"
        self.ax_plot.clear()
        self.ax_plot.set_facecolor(bg)
        self.ax_plot.set_aspect("equal")
        self.ax_plot.set_xlim(-1.6, 1.6)
        self.ax_plot.set_ylim(-1.6, 1.6)
        self.ax_plot.grid(True, alpha=0.3, color=border)
        self.ax_plot.axhline(0, color=border, linewidth=0.5)
        self.ax_plot.axvline(0, color=border, linewidth=0.5)
        self.ax_plot.tick_params(colors=fg, which="both")
        self.ax_plot.set_title("Table Preview", color=fg, fontsize=11)
        for spine in self.ax_plot.spines.values():
            spine.set_color(border)
        self.ax_plot.add_patch(
            matplotlib.patches.Rectangle(
                (-1.5, -1.5), 3.0, 3.0,
                fill=False, edgecolor=border,
                linestyle="--", linewidth=1.0,
            )
        )
        if self.polygon:
            xs = [p[0] for p in self.polygon] + [self.polygon[0][0]]
            ys = [p[1] for p in self.polygon] + [self.polygon[0][1]]
            self.ax_plot.fill(xs, ys, color=poly_color, alpha=0.25)
            self.ax_plot.plot(xs, ys, "-", color=poly_color, linewidth=2.0)
            x0, y0 = self.polygon[0]
            self.ax_plot.plot(x0, y0, "o", color=poly_color, markersize=7,
                              markeredgecolor="#ffffff", markeredgewidth=1.0)
            for i, (x, y) in enumerate(self.polygon):
                if i == 0:
                    continue
                self.ax_plot.plot(x, y, ".", color=poly_color, markersize=3)
        self.canvas.draw_idle()

    def _refresh_output(self):
        if not self.output_text:
            return
        self.output_text.delete("1.0", tk.END)
        if self.polygon:
            self.output_text.insert(tk.END, format_polygon_output(self.polygon))
        self.output_text.mark_set(tk.INSERT, "1.0")

def main():
    import traceback
    try:
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")
        root = ctk.CTk()
        SvgToSpooker(root)
        root.mainloop()
    except Exception:
        traceback.print_exc()
        sys.stderr.write("\nPress Enter to exit...")
        input()
        raise


if __name__ == "__main__":
    main()
