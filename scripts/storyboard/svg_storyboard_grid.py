"""Layer 2 → 免生圖 SVG 構圖九宮格（stage-4 構圖來源之一，與 Qwen 九宮格、手繪並列）。

做法：2.5D 針孔相機（焦距／36mm 片幅、依景別反推物距、OTS 貼前景肩後）＋3D 骨架人偶（站／跪／走、IK 手、
可見性五官）＋程式搭景（房間、門窗、桌燈書碗等），SVG 以 resvg 轉 PNG。完全不呼叫生圖 API。

通用性：程式內不含任何專案的角色、場景或站位。外觀走 cast JSON、場景與站位走 staging JSON、
動作／道具／場景關鍵字走 svg_rig_actions.json；都沒有時依 Layer 2 文字與 continuity_anchors 自動搭景。
詳見 references/storyboard/svg-rig-grid.md。
"""
import json, math, re, sys, os
try:
    import numpy as np, resvg_py
except ImportError as _e:  # 選用依賴：只有這支構圖工具需要
    sys.stderr.write(f"缺少選用依賴（{_e.name}）：pip install numpy resvg-py Pillow\n"); sys.exit(2)

W, H = 768, 432
SENSOR_W = 36.0
INK = "#2b2b2b"

def nrm(v): v = np.asarray(v, float); n = np.linalg.norm(v); return v / n if n else v
def rot_y(v, a):  # 繞 y 軸，正值把 +z 轉向 +x
    c, s = math.cos(a), math.sin(a); x, y, z = v; return np.array([x * c + z * s, y, -x * s + z * c])
def rot_axis(v, axis, a):
    k = nrm(axis); v = np.asarray(v, float)
    return v * math.cos(a) + np.cross(k, v) * math.sin(a) + k * np.dot(k, v) * (1 - math.cos(a))

# ---------------------------------------------------------------- 相機
class Cam:
    def __init__(s, pos, yaw=0.0, pitch=0.0, f=50):
        s.pos = np.array(pos, float); s.yaw, s.pitch = yaw, pitch; s.f = f; s.du = s.dv = 0.0; s.update()
    @property
    def fx(s): return s.f / SENSOR_W * W
    def update(s):
        cy, sy, cp, sp = math.cos(s.yaw), math.sin(s.yaw), math.cos(s.pitch), math.sin(s.pitch)
        s.fw = np.array([sy * cp, sp, cy * cp]); s.rt = np.array([cy, 0, -sy]); s.up = np.cross(s.fw, s.rt)
    def look_at(s, t):
        d = np.asarray(t, float) - s.pos; s.yaw = math.atan2(d[0], d[2]); s.pitch = math.atan2(d[1], math.hypot(d[0], d[2])); s.update()
    def cc(s, P):
        d = np.asarray(P, float) - s.pos; return np.array([d @ s.rt, d @ s.up, d @ s.fw])
    def pc(s, c):  # camera coords -> screen
        z = max(c[2], 1e-4); return (W / 2 + s.fx * c[0] / z + s.du, H / 2 - s.fx * c[1] / z + s.dv)
    def proj(s, P): return s.pc(s.cc(P))
    def depth(s, P): return s.cc(P)[2]

FONT_CANDIDATES = [
    os.environ.get("SVG_GRID_FONT", ""), os.environ.get("RIG_FONT", ""),
    "C:/Windows/Fonts/msjhbd.ttc", "C:/Windows/Fonts/msjh.ttc", "C:/Windows/Fonts/msyhbd.ttc", "C:/Windows/Fonts/msyh.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc", "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/noto-cjk/NotoSansCJK-Bold.ttc", "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
    "/System/Library/Fonts/PingFang.ttc", "/Library/Fonts/Arial Unicode.ttf",
]
FONT_PATH = next((f for f in FONT_CANDIDATES if f and os.path.isfile(f)), None)
FONT_FAMILY = "Microsoft JhengHei, Microsoft YaHei, Noto Sans CJK TC, Noto Sans TC, PingFang TC, sans-serif"
NEAR = 0.06
def clip_poly(cam, pts):
    cs = [cam.cc(p) for p in pts]; out = []
    for i in range(len(cs)):
        a, b = cs[i], cs[(i + 1) % len(cs)]; ia, ib = a[2] >= NEAR, b[2] >= NEAR
        if ia: out.append(a)
        if ia != ib:
            t = (NEAR - a[2]) / (b[2] - a[2]); out.append(a + (b - a) * t)
    return out
def pstr(xy): return " ".join(f"{x:.1f},{y:.1f}" for x, y in xy)
def poly_svg(cam, pts, fill, stroke=INK, sw=1.4, extra=""):
    cs = clip_poly(cam, pts)
    if len(cs) < 3: return "", 1e9
    xy = [cam.pc(c) for c in cs]
    return f'<polygon points="{pstr(xy)}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}" stroke-linejoin="round" {extra}/>', float(np.mean([c[2] for c in cs]))
def line_svg(cam, a, b, stroke=INK, sw=1.0, extra=""):
    ca, cb = cam.cc(a), cam.cc(b)
    if ca[2] < NEAR and cb[2] < NEAR: return ""
    if ca[2] < NEAR: ca = ca + (cb - ca) * (NEAR - ca[2]) / (cb[2] - ca[2])
    if cb[2] < NEAR: cb = cb + (ca - cb) * (NEAR - cb[2]) / (ca[2] - cb[2])
    (x1, y1), (x2, y2) = cam.pc(ca), cam.pc(cb)
    return f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{stroke}" stroke-width="{sw}" stroke-linecap="round" {extra}/>'
def hull(pts):
    pts = sorted(set((round(x, 2), round(y, 2)) for x, y in pts))
    if len(pts) < 3: return pts
    def cr(o, a, b): return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lo, up = [], []
    for p in pts:
        while len(lo) >= 2 and cr(lo[-2], lo[-1], p) <= 0: lo.pop()
        lo.append(p)
    for p in reversed(pts):
        while len(up) >= 2 and cr(up[-2], up[-1], p) <= 0: up.pop()
        up.append(p)
    return lo[:-1] + up[:-1]
def capsule_svg(cam, A, B, ra, rb, fill, sw=1.6):
    """投影後的錐形膠囊：兩端圓的外公切線包絡。"""
    ca, cb = cam.cc(A), cam.cc(B)
    if ca[2] < NEAR or cb[2] < NEAR: return "", 1e9
    (x1, y1), (x2, y2) = cam.pc(ca), cam.pc(cb); r1, r2 = ra * cam.fx / ca[2], rb * cam.fx / cb[2]
    dx, dy = x2 - x1, y2 - y1; d = math.hypot(dx, dy); z = (ca[2] + cb[2]) / 2
    if d < abs(r1 - r2) + 0.5:
        x, y, r = (x1, y1, r1) if r1 > r2 else (x2, y2, r2)
        return f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}" fill="{fill}" stroke="{INK}" stroke-width="{sw}"/>', z
    ux, uy = dx / d, dy / d; s = (r1 - r2) / d; c = math.sqrt(max(0, 1 - s * s))
    nx1, ny1 = s * ux - c * uy, s * uy + c * ux; nx2, ny2 = s * ux + c * uy, s * uy - c * ux
    p = (f'M{x1+r1*nx1:.1f},{y1+r1*ny1:.1f} L{x2+r2*nx1:.1f},{y2+r2*ny1:.1f} '
         f'A{r2:.1f},{r2:.1f} 0 {1 if r2 > 0 else 0} 0 {x2+r2*nx2:.1f},{y2+r2*ny2:.1f} '
         f'L{x1+r1*nx2:.1f},{y1+r1*ny2:.1f} A{r1:.1f},{r1:.1f} 0 1 0 {x1+r1*nx1:.1f},{y1+r1*ny1:.1f} Z')
    # 弧的大小弧旗標：用兩個半圓近似即可
    p = (f'M{x1+r1*nx1:.1f},{y1+r1*ny1:.1f} L{x2+r2*nx1:.1f},{y2+r2*ny1:.1f} '
         f'A{r2:.1f},{r2:.1f} 0 0 0 {x2+r2*nx2:.1f},{y2+r2*ny2:.1f} '
         f'L{x1+r1*nx2:.1f},{y1+r1*ny2:.1f} A{r1:.1f},{r1:.1f} 0 0 0 {x1+r1*nx1:.1f},{y1+r1*ny1:.1f} Z')
    return f'<path d="{p}" fill="{fill}" stroke="{INK}" stroke-width="{sw}" stroke-linejoin="round"/>', z
def ring(center, axis_u, axis_v, ru, rv, n=18):
    return [center + axis_u * ru * math.cos(t) + axis_v * rv * math.sin(t) for t in np.linspace(0, 2 * math.pi, n, endpoint=False)]
def hull_svg(cam, pts3, fill, sw=1.6, extra=""):
    cs = [cam.cc(p) for p in pts3]; cs = [c for c in cs if c[2] > NEAR]
    if len(cs) < 3: return "", 1e9
    h = hull([cam.pc(c) for c in cs])
    return f'<polygon points="{pstr(h)}" fill="{fill}" stroke="{INK}" stroke-width="{sw}" stroke-linejoin="round" {extra}/>', float(np.mean([c[2] for c in cs]))

# ---------------------------------------------------------------- 角色
DEFAULT_LOOK = dict(name=None, tag="#444", robe="#b8b2a6", robe_dk="#8a857b", trousers="#aaa49a", skin="#f1ebe2", hair="#333",
                    bun="low", strip="#999", pin="#9a7b55", strands=False, robe_len="ankle", sash="#555", scale=1.0,
                    brow_w=1.0, under_eye=None, marks=[])
CHARS = {}
def load_cast(path):
    if path and os.path.exists(path): CHARS.update(json.load(open(path))["characters"])
def infer_names(layer2_paths, shots):
    """未在 cast 登記名字的角色：先找 layer2 上層的 assets.md 對照表（| `C-id` | 名字 |），
    再退回從單人鏡的 blocking_desc 開頭抓 2–4 字中文名（取最常出現者）。不寫死任何專案。"""
    need = {c for s in shots for c in s.get("character_ids", []) if not CHARS.get(c, {}).get("name")}
    if not need: return
    found = {}
    for fp in layer2_paths:
        d = os.path.dirname(os.path.abspath(fp))
        for _ in range(3):
            for mdp in _glob.glob(os.path.join(d, "assets*.md")):
                for m in re.finditer(r"`([A-Za-z][\w-]*)`\s*\|\s*([\u4e00-\u9fff·．A-Za-z]{1,12})\s*\|", open(mdp, encoding="utf-8").read()):
                    found.setdefault(m.group(1), m.group(2))
            d = os.path.dirname(d)
    from collections import Counter
    cnt = {}
    for s in shots:
        ids = s.get("character_ids", [])
        if len(ids) != 1 or ids[0] in found: continue
        txt = (s.get("spatial_blocking") or {}).get("blocking_desc", "")
        m = re.match(r"([\u4e00-\u9fff]{2,4}?)(?=胸|近景|中景|全景|特寫|大特寫|半身|腰|坐|站|跪|的|在|背|側|正|，|、|手|低|抬|轉|看|把|將)", txt)
        if m and not re.search(r"角度|鏡|景|近|遠|俯|仰|畫|前|後|左|右|拉|推|特|空|全|半|低|高|側|背", m.group(1)):
            cnt.setdefault(ids[0], Counter())[m.group(1)] += 1
    def specific(c, nm):  # 名字要主要出現在該角色入鏡的鏡頭
        tx = lambda s: json.dumps(s, ensure_ascii=False)
        w = sum(nm in tx(s) for s in shots if c in s.get("character_ids", [])); o = sum(nm in tx(s) for s in shots if c not in s.get("character_ids", []))
        return w >= 1 and w >= o * .5
    for c in need:
        cand = [n for n, _ in cnt.get(c, Counter()).most_common() if specific(c, n)]
        nm = found.get(c) or (cand[0] if cand else None)
        if nm: CHARS.setdefault(c, {})["name"] = nm
def look(cid):
    """登記過的角色用 cast；沒登記的給可辨識的預設人偶（顏色由 id 雜湊決定）。"""
    c = dict(DEFAULT_LOOK); c.update(CHARS.get(cid, {}))
    if cid not in CHARS:
        import hashlib; h = int(hashlib.md5(cid.encode()).hexdigest()[:6], 16)
        hue = [(0x9a, 0x8c, 0x7a), (0x7f, 0x8f, 0x9a), (0x8f, 0x7f, 0x9a), (0x7f, 0x9a, 0x86), (0x9a, 0x86, 0x7f)][h % 5]
        c["robe"] = "#%02x%02x%02x" % hue; c["robe_dk"] = "#%02x%02x%02x" % tuple(int(v * .75) for v in hue); c["trousers"] = c["robe"]
    c["name"] = c["name"] or re.sub(r"^C-", "", cid)
    return c
POSES = {
    "kneel": dict(head=(0, .87, .03), neck=(0, .74, 0), chest=(0, .62, 0), waist=(0, .49, -.01), pelvis=(0, .35, -.06),
                  lsh=(-.17, .69, 0), rsh=(.17, .69, 0), lel=(-.21, .47, .07), rel=(.21, .47, .07),
                  lwr=(-.13, .34, .30), rwr=(.13, .34, .30), lhip=(-.10, .32, -.06), rhip=(.10, .32, -.06),
                  lkn=(-.12, .07, .36), rkn=(.12, .07, .36), lan=(-.09, .05, -.14), ran=(.09, .05, -.14)),
    "stand": dict(head=(0, 1.58, .01), neck=(0, 1.45, 0), chest=(0, 1.32, 0), waist=(0, 1.08, 0), pelvis=(0, .95, 0),
                  lsh=(-.18, 1.40, 0), rsh=(.18, 1.40, 0), lel=(-.23, 1.12, -.02), rel=(.23, 1.12, -.02),
                  lwr=(-.22, .86, .04), rwr=(.22, .86, .04), lhip=(-.10, .93, 0), rhip=(.10, .93, 0),
                  lkn=(-.11, .50, .02), rkn=(.11, .50, .02), lan=(-.12, .07, -.02), ran=(.12, .07, -.02)),
}
POSES["walk_down"] = dict(POSES["stand"], lkn=(-.11, .52, -.06), lan=(-.12, .07, -.16), rkn=(.11, .38, .2), ran=(.12, -.09, .3),
                         lwr=(-.22, .88, .12), rwr=(.22, .88, -.08), lel=(-.23, 1.12, .04), rel=(.23, 1.12, -.06))
POSES["walk_up"] = dict(POSES["stand"], rkn=(.11, .68, .22), ran=(.12, .23, .28), lkn=(-.11, .45, -.1), lan=(-.12, .07, -.22),
                       head=(0, 1.56, .08), neck=(0, 1.43, .05), chest=(0, 1.3, .03))
UPPER = ["head", "neck", "chest", "lsh", "rsh", "lel", "rel", "lwr", "rwr"]

class Actor:
    def __init__(s, cid, pos, facing_deg, pose="kneel"):
        s.cid, s.c = cid, look(cid); s.pos = np.array(pos, float); s.th = math.radians(facing_deg)
        s.kind = pose; sc = s.c["scale"]
        s.L = {k: np.array(v, float) * sc for k, v in POSES[pose].items()}
        s.head_pitch = 0.0; s.head_yaw = 0.0; s.soft = False; s.hands = {}
    # 世界方向
    @property
    def F(s): return np.array([math.sin(s.th), 0, math.cos(s.th)])
    @property
    def R(s): return np.array([math.cos(s.th), 0, -math.sin(s.th)])
    def w(s, lp): lp = np.asarray(lp, float); return s.pos + s.R * lp[0] + np.array([0, lp[1], 0]) + s.F * lp[2]
    def loc(s, wp): d = np.asarray(wp, float) - s.pos; return np.array([d @ s.R, d[1], d @ s.F])
    def J(s, k): return s.w(s.L[k])
    def lean(s, deg):
        piv = s.L["pelvis"].copy(); a = math.radians(deg)
        for k in UPPER:
            v = s.L[k] - piv; s.L[k] = piv + rot_axis(v, (1, 0, 0), a)
    def reach(s, side, target_w, hover_hand=True):
        """雙骨 IK：肩→肘→腕，肘往外下方彎。"""
        S = s.L[side + "sh"]; T = s.loc(target_w); sc = s.c["scale"]
        hand_len = .09 * sc; l1, l2 = .29 * sc, .26 * sc
        d = T - S; dist = np.linalg.norm(d)
        # 腕位置 = 目標往肩方向退半個手掌
        Wt = T - nrm(d) * hand_len * .6; d = Wt - S; dist = np.linalg.norm(d)
        if dist > l1 + l2 - 1e-3: Wt = S + nrm(d) * (l1 + l2 - 1e-3); d = Wt - S; dist = l1 + l2 - 1e-3
        a = math.acos(np.clip((l1 * l1 + dist * dist - l2 * l2) / (2 * l1 * dist), -1, 1))
        pole = nrm(np.array([(-1 if side == "l" else 1) * .6, -1, 0]))
        axis = nrm(np.cross(d, pole)); E = S + rot_axis(nrm(d) * l1, axis, -a)
        if E[1] > S[1]: E = S + rot_axis(nrm(d) * l1, axis, a)
        s.L[side + "el"], s.L[side + "wr"] = E, Wt
        s.hands[side] = dict(dir=nrm(T - Wt), curl=.35 if hover_hand else .9)

def draw_hand(cam, a, side, prims, blur):
    c = a.c; sc = c["scale"]; Wr = a.J(side + "wr")
    info = a.hands.get(side)
    if info: d = nrm(a.w(a.L[side + "wr"] + info["dir"]) - a.pos - (a.w(a.L[side + "wr"]) - a.pos)); curl = info["curl"]
    else:
        d = nrm(Wr - a.J(side + "el")); curl = .9
    side_v = nrm(np.cross(d, [0, 1, 0])) if abs(d[1]) < .95 else a.R
    if np.dot(side_v, a.R) < 0: side_v = -side_v
    palm_n = nrm(np.cross(side_v, d))
    if palm_n[1] > 0: palm_n = -palm_n  # 掌心朝下
    pw, pl = .085 * sc, .09 * sc
    palm_c = Wr + d * pl * .55
    corners = [Wr + side_v * pw * .42, Wr - side_v * pw * .42, Wr + d * pl - side_v * pw * .5, Wr + d * pl + side_v * pw * .5]
    pts = corners + [p + palm_n * .012 for p in corners] + [p - palm_n * .012 for p in corners]
    prims.append(hull_svg(cam, pts, c["skin"], 1.4, blur))
    for i, off in enumerate((-.36, -.12, .12, .36)):
        base = Wr + d * pl + side_v * pw * off; ln = (.05, .056, .053, .042)[i] * sc
        seg1 = rot_axis(d, side_v, curl * .5 * (1 if np.dot(palm_n, [0, -1, 0]) > 0 else -1))
        p1 = base + seg1 * ln * .55; seg2 = rot_axis(seg1, side_v, curl * .6); p2 = p1 + seg2 * ln * .5
        prims.append(capsule_svg(cam, base, p1, .0095 * sc, .0085 * sc, c["skin"], 1.2)); prims.append(capsule_svg(cam, p1, p2, .0085 * sc, .0075 * sc, c["skin"], 1.2))
    tb = Wr + d * pl * .25 + side_v * pw * (-.5 if side == "r" else .5) * (1 if np.dot(side_v, a.R) > 0 else -1)
    tt = tb + nrm(d + palm_n * .4 - side_v * .2) * .045 * sc
    prims.append(capsule_svg(cam, tb, tt, .011 * sc, .009 * sc, c["skin"], 1.2))
    # cast 的 marks：手指上的小記號（筆繭、傷痕等）
    for mk in a.c.get("marks", []):
        if mk.get("side", "r") != side: continue
        mx, my = cam.proj(Wr + d * (pl + .02) - side_v * pw * .12 + palm_n * .01)
        if cam.fx / max(cam.depth(Wr), .1) > 900:
            prims.append((f'<circle cx="{mx:.1f}" cy="{my:.1f}" r="3.5" fill="none" stroke="{mk.get("color", "#7a1f1f")}" stroke-width="1.6"/>', cam.depth(Wr) - .01))

def draw_head(cam, a, prims, blur):
    c = a.c; sc = c["scale"]; Hc = a.J("head")
    hf = rot_y(a.F, a.head_yaw); hr = rot_y(a.R, a.head_yaw)
    hu = np.array([0, 1, 0.0]); hf, hu = rot_axis(hf, hr, a.head_pitch), rot_axis(hu, hr, a.head_pitch)
    rx, ry, rz = .074 * sc, .102 * sc, .092 * sc
    def P(u, v, w): return Hc + hr * u * rx + hu * v * ry + hf * w * rz
    def N(u, v, w): return nrm(hr * u / rx + hu * v / ry + hf * w / rz)
    view = lambda p: nrm(p - cam.pos)
    sph = [(math.cos(t) * math.sin(p), math.cos(p), math.sin(t) * math.sin(p)) for t in np.linspace(0, 2 * math.pi, 28) for p in np.linspace(0.05, math.pi - .05, 14)]
    # 下巴：臉前下方略收
    def jaw(u, v, w): return (u * (.82 if v < -.3 else 1), v * (1.08 if v < -.3 and w > 0 else 1), w)
    sph = [jaw(*q) for q in sph]
    z = cam.depth(Hc)
    # 髮髻（在頭後，先畫）
    bun = {"high": P(0, .55, -.62), "half": P(0, .3, -.86), "cloth": P(0, .32, -.86)}.get(c["bun"], P(0, -.25, -.95))
    br = {"high": .046, "half": .03, "cloth": .05}.get(c["bun"], .042) * sc
    bun_svg = capsule_svg(cam, bun, bun + hu * .001, br, br, c.get("bun_fill", c["hair"]), 1.6)
    head_out = hull_svg(cam, [P(*q) for q in sph], c["hair"], 1.8, blur)[0]
    vis = [q for q in sph if q[2] > (.12 if a.soft else -.15) and q[1] < .5 and np.dot(N(*q), view(P(*q))) < 0]
    face = hull_svg(cam, [P(*q) for q in vis], c["skin"], 0)[0] if len(vis) > 3 else ""
    face = face.replace(f'stroke="{INK}"', 'stroke="none"')
    feats = []
    r_px = ry * cam.fx / z
    def vis_pt(q): return np.dot(N(*q), view(P(*q))) < -.08
    def seg(q1, q2, sw, col=INK):
        if vis_pt(q1) and vis_pt(q2):
            (x1, y1), (x2, y2) = cam.proj(P(*q1)), cam.proj(P(*q2))
            feats.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{col}" stroke-width="{sw:.1f}" stroke-linecap="round"/>')
    if r_px > 14:
        sw = max(1.2, r_px / 26)
        look_down = a.head_pitch > .15
        for s_ in (-1, 1):  # 眼、眉、耳
            eu = s_ * .42
            if look_down: seg((eu - .2, .04, .9), (eu + .2, .02, .92), sw * 1.2)
            else:
                if r_px > 34:
                    pts = [(eu + k * .2, .06 + .05 * math.sin((k + 1) * math.pi / 2), .9 + .03 * (1 - abs(k))) for k in np.linspace(-1, 1, 7)]
                    for q1, q2 in zip(pts, pts[1:]): seg(q1, q2, sw * 1.4)
                    seg((eu - .2, .06, .9), (eu + .18, .02, .91), sw * .6, "#666")
                else: seg((eu - .2, .06, .9), (eu + .2, .06, .9), sw * 1.3)
                q = (eu, .06, .93)
                if vis_pt(q) and r_px > 30:
                    x, y = cam.proj(P(*q)); feats.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{sw*1.1:.1f}" fill="{INK}"/>')
            seg((eu - .24, .28, .86), (eu + .2, .3, .86), sw * c.get("brow_w", 1.0))
            ear = (s_ * 1.0, -.02, -.05)
            if np.dot(N(*ear), view(P(*ear))) < .25:
                x, y = cam.proj(P(*ear)); feats.append(f'<ellipse cx="{x:.1f}" cy="{y:.1f}" rx="{r_px*.13:.1f}" ry="{r_px*.22:.1f}" fill="{c["skin"]}" stroke="{INK}" stroke-width="{sw*.8:.1f}"/>')
        seg((0, .02, 1.0), (.04, -.26, 1.04), sw * .9, "#555")
        seg((-.16, -.5, .9), (0, -.47, .92), sw * .9, "#6b4a44"); seg((0, -.47, .92), (.16, -.5, .9), sw * .9, "#6b4a44")
        if r_px > 34: seg((-.1, -.6, .86), (.1, -.6, .86), sw * .5, "#9a7a72")
        if c.get("under_eye"):  # 眼下陰影
            for s_ in (-1, 1): seg((s_ * .42 - .15, -.06, .9), (s_ * .42 + .15, -.06, .9), sw * .6, c["under_eye"])
    # 髮際線：額頭上緣補一條弧（髮色覆蓋在臉區上方）
    hairline = [q for q in sph if q[1] > .5 and np.dot(N(*q), view(P(*q))) < 0]
    cap = hull_svg(cam, [P(*q) for q in hairline], c["hair"], 0)[0] if len(hairline) > 3 else ""
    cap = cap.replace(f'stroke="{INK}"', 'stroke="none"')
    acc = ""
    if c["bun"] == "half":  # 白玉髮扣
        acc += line_svg(cam, bun - hr * .028, bun + hr * .028, c["pin"], max(2.5, r_px / 8)) + line_svg(cam, bun - hr * .028, bun + hr * .028, INK, .6)
    elif c["bun"] == "cloth":  # 深藍頭巾結兩短角
        for s_ in (-1, 1):
            acc += line_svg(cam, bun - hf * .02, bun - hf * .05 - hu * .05 + hr * s_ * .025, c["bun_fill"], max(2.5, r_px / 10))
    elif c["bun"] == "high":  # 木簪
        p1, p2 = bun + hr * .07 + hu * .03, bun - hr * .06 - hu * .02
        acc += line_svg(cam, p1, p2, c["pin"], max(2, r_px / 14))
    else:  # 灰布條
        acc += line_svg(cam, bun - hr * .03 + hu * .012, bun + hr * .03 + hu * .012, c["strip"], max(2.5, r_px / 10))
        if c.get("strands"):
            for s_ in (-1, 1):
                q1, q2 = (s_ * .95, .25, .35), (s_ * 1.02, -.35, .4)
                if np.dot(N(*q1), view(P(*q1))) < .3:
                    (x1, y1), (x2, y2) = cam.proj(P(*q1)), cam.proj(P(*q2))
                    acc += f'<path d="M{x1:.1f},{y1:.1f} q{(x2-x1)*.2+3:.1f},{(y2-y1)*.5:.1f} {x2-x1:.1f},{y2-y1:.1f}" fill="none" stroke="{c["hair"]}" stroke-width="{max(1.2,r_px/30):.1f}"/>'
    if np.dot(nrm(bun - Hc), view(Hc)) > .25: acc = ""  # 髮扣／頭巾結在頭後被擋
    bun_front = np.dot(nrm(bun - Hc), view(Hc)) < 0  # 髻在頭前方（從後面看）時畫在上面
    g = (f'<g {blur}>' + ("" if bun_front else bun_svg[0]) + head_out + face + cap +
         f'<g>{"".join(feats)}</g>' + head_out.replace(f'fill="{c["hair"]}"', 'fill="none"') + ("" if not bun_front else bun_svg[0]) + acc + '</g>')
    prims.append((g, z - .02))

def draw_actor(cam, a, prims, labels):
    c = a.c; sc = c["scale"]; J = a.J
    blur = 'filter="url(#dof)" opacity="0.97"' if a.soft else ""
    local = []
    # 軀幹 loft
    up = nrm(J("neck") - J("waist")); fw = a.F
    rings = ring(J("neck") - up * .005, a.R, fw, .075 * sc, .06 * sc) + ring(J("lsh") * .5 + J("rsh") * .5 + up * .005, a.R, fw, .185 * sc, .1 * sc) + ring(J("chest"), a.R, fw, .165 * sc, .11 * sc) + ring(J("waist"), a.R, fw, .14 * sc, .095 * sc)
    torso = hull_svg(cam, rings, c["robe"], 1.7, blur)
    # 下擺
    if a.kind == "kneel":
        skirt = ring(J("waist") - up * .02, a.R, fw, .15 * sc, .1 * sc) + ring(J("pelvis") + np.array([0, -.2, 0]) * sc, a.R, fw, .2 * sc, .2 * sc)
        skirt += [J("lkn") + a.R * -.06 * sc + np.array([0, -.05, 0]), J("rkn") + a.R * .06 * sc + np.array([0, -.05, 0]),
                  J("lkn") + np.array([0, .07, 0]) * sc, J("rkn") + np.array([0, .07, 0]) * sc, J("lan") - a.F * .04, J("ran") - a.F * .04]
    else:
        hem = .48 if c["robe_len"] == "ankle" else .5 + .0
        skirt = ring(J("waist"), a.R, fw, .15 * sc, .1 * sc) + ring(a.w((0, .1 if c["robe_len"] == "ankle" else .52, 0)), a.R, fw, .22 * sc, .16 * sc)
        if c["robe_len"] == "knee":
            for s_ in "lr": local.append(capsule_svg(cam, J(s_ + "kn"), J(s_ + "an"), .055 * sc, .045 * sc, c["trousers"], 1.5))
    sk = hull_svg(cam, skirt, c["robe"], 1.7, blur)
    local.append((sk[0], sk[1] + .0))
    local.append(torso)
    # 交領＋腰帶（只在正面可見時）
    front = np.dot(fw, nrm(J("chest") - cam.pos)) < -.15
    if front:
        n0 = J("neck") + fw * .06 * sc
        L1 = line_svg(cam, n0 + a.R * .06 * sc, J("chest") + fw * .11 * sc + a.R * -.06 * sc, INK, 1.4)
        L2 = line_svg(cam, n0 - a.R * .06 * sc, J("chest") + fw * .105 * sc + a.R * .02 * sc, INK, 1.2)
        local.append((f'<g {blur}>{L1}{L2}</g>', torso[1] - .03))
    sash = hull_svg(cam, ring(J("waist") + up * .025, a.R, fw, .145 * sc, .1 * sc) + ring(J("waist") - up * .025, a.R, fw, .148 * sc, .102 * sc), c["sash"], 1.3, blur)
    local.append((sash[0], torso[1] - .02))
    # 脖子
    away = float(np.dot(a.F, cam.pos - a.pos)) < 0   # 背對鏡頭：後頸被頭髮蓋住
    nk = capsule_svg(cam, J("neck") - up * .03, J("head") - up * .07 * sc, .032 * sc, .031 * sc, c["hair"] if away else c["skin"], 1.5)
    local.append(((f'<g {blur}>{nk[0]}</g>' if blur else nk[0]), torso[1] + .01))
    # 手臂（窄袖）
    for s_ in "lr":
        sh = J(s_ + "sh") - up * .02
        ua = capsule_svg(cam, sh, J(s_ + "el"), .052 * sc, .046 * sc, c["robe"], 1.6); fa = capsule_svg(cam, J(s_ + "el"), J(s_ + "wr"), .046 * sc, .04 * sc, c["robe"], 1.6)
        cuff = capsule_svg(cam, J(s_ + "wr") - nrm(J(s_ + "wr") - J(s_ + "el")) * .03, J(s_ + "wr"), .042 * sc, .041 * sc, c["robe_dk"], 1.3)
        for p in (ua, fa, cuff):
            if p[0] and blur: p = (f'<g {blur}>{p[0]}</g>', p[1])
            local.append(p)
        hp = []; draw_hand(cam, a, s_, hp, blur)
        local += [(f'<g {blur}>{h[0]}</g>', h[1]) if blur else h for h in hp if h[0]]
    if c["bun"] == "half":
        Hc = a.J("head"); bk = -a.F
        pts = ring(Hc + bk * .05 * sc + np.array([0, -.02, 0]), a.R, bk, .07 * sc, .05 * sc) + ring(J("chest") * .5 + J("neck") * .5 + bk * .12 * sc, a.R, bk, .12 * sc, .03 * sc)
        hd = hull_svg(cam, pts, c["hair"], 1.5, blur); local.append((hd[0], max(hd[1], cam.depth(Hc) + .01)))
    if a.kind == "kneel" and c["bun"] == "cloth": a.lean(6)
    draw_head(cam, a, local, blur)
    prims.extend(local)
    # 名牌
    hx, hy = cam.proj(J("head") + np.array([0, .19, 0]) * sc); z = cam.depth(J("head"))
    if z > NEAR and -40 < hx < W + 40:
        labels.append((hx, hy, c["name"] + ("（前景虛焦）" if a.soft else ""), c["tag"]))

# ---------------------------------------------------------------- 場景：預設室內（stages 檔的 room 可覆寫尺寸、門窗與牆地顏色）
ROOM = dict(x0=-3.4, x1=3.4, z0=-7.0, z1=9.0, h=4.2)
def room_prims(cam, R=None):
    R = R or ROOM; bg, prims = [], []
    x0, x1, z0, z1, h = R["x0"], R["x1"], R["z0"], R["z1"], R["h"]
    wall_fill, floor_fill = R.get("wall_fill", "#d9d5cc"), R.get("floor_fill", "#e4e1da")
    # 天花板、牆、地板大面
    faces = [([(x0, h, z0), (x1, h, z0), (x1, h, z1), (x0, h, z1)], "#c9c5bb"),
             ([(x0, 0, z1), (x1, 0, z1), (x1, h, z1), (x0, h, z1)], wall_fill),
             ([(x0, 0, z0), (x1, 0, z0), (x1, h, z0), (x0, h, z0)], wall_fill),
             ([(x0, 0, z0), (x0, 0, z1), (x0, h, z1), (x0, h, z0)], R.get("wall_side_fill", "#d2cec4")),
             ([(x1, 0, z0), (x1, 0, z1), (x1, h, z1), (x1, h, z0)], R.get("wall_side_fill", "#d2cec4")),
             ([(x0, 0, z0), (x1, 0, z0), (x1, 0, z1), (x0, 0, z1)], floor_fill)]
    for pts, fill in faces: bg.append(poly_svg(cam, [np.array(p, float) for p in pts], fill, INK, 1.6)[0])
    rng = np.random.default_rng(7)
    # 石板地縫（不規則）
    lines = []
    for zz in np.arange(z0, z1, .8):
        lines.append(line_svg(cam, (x0, 0, zz), (x1, 0, zz), "#9c978c", .9))
    for zz in np.arange(z0, z1, .8):
        off = rng.uniform(0, .9)
        for xx in np.arange(x0 + off, x1, 1.1):
            lines.append(line_svg(cam, (xx, 0, zz), (xx + rng.uniform(-.06, .06), 0, zz + .8), "#9c978c", .9))
    # 石牆塊縫
    for xw in (x0, x1):
        for yy in np.arange(.55, h, .55):
            lines.append(line_svg(cam, (xw, yy, z0), (xw, yy, z1), "#a29d92", .8))
            off = rng.uniform(0, 1)
            for zz in np.arange(z0 + off, z1, 1.2): lines.append(line_svg(cam, (xw, yy, zz), (xw, yy + .55, zz), "#a29d92", .8))
    for yy in np.arange(.55, h, .55):
        lines.append(line_svg(cam, (x0, yy, z1), (x1, yy, z1), "#a29d92", .8))
        for xx in np.arange(x0 + rng.uniform(0, 1), x1, 1.2): lines.append(line_svg(cam, (xx, yy, z1), (xx, yy + .55, z1), "#a29d92", .8))
    bg.append('<g>' + "".join(lines) + '</g>')
    # 天光（右後方斜射的光柱）
    shaft = R.get("light_shaft", [(1.2, h, 6.3), (2.4, h, 6.3), (1.6, 0, 3.6), (0.2, 0, 3.6)])
    bg.append(poly_svg(cam, [np.array(p) for p in shaft], "#ffffff", "none", 0, 'opacity="0.35"')[0])
    # 木門（左牆，已關）
    dz, dh = (R.get("door") or {}).get("z", [-3.2, -1.6]), (R.get("door") or {}).get("h", 2.7)
    door = [(x0 + .01, 0, dz[0]), (x0 + .01, 0, dz[1]), (x0 + .01, dh, dz[1]), (x0 + .01, dh, dz[0])]
    s, z = poly_svg(cam, [np.array(p) for p in door], "#8a7660", INK, 1.8); bg.append(s)
    bg.append(line_svg(cam, (x0 + .02, 0, -2.4), (x0 + .02, 2.7, -2.4), INK, 1.4))
    for zz in (-2.6, -2.2):
        q = cam.proj((x0 + .03, 1.25, zz))
        if cam.depth((x0 + .03, 1.25, zz)) > NEAR: bg.append(f'<circle cx="{q[0]:.1f}" cy="{q[1]:.1f}" r="{max(1.5, 60/cam.depth((x0, 1.25, zz))/10):.1f}" fill="none" stroke="{INK}" stroke-width="1.2"/>')
    # 授課案
    lc = R.get("lectern", dict(pos=[0, 0, 7.8], w=2.4, h=.55, d=.8))
    if lc: prims.append(box_prim(cam, tuple(lc["pos"]), lc["w"], lc["h"], lc["d"], "#a08c72"))
    cu = R.get("cushions", dict(x=[-1.7, 1.7], z_from=-5.5, z_to=7.0, step=1.25))
    if cu:
        for xx in cu["x"]:
            for zz in np.arange(cu["z_from"], cu["z_to"], cu["step"]):
                prims.append(cushion_prim(cam, (xx, 0, zz)))
    feats = R.get("features", [])
    if "shelves" in feats:  # 書架：後牆一整排＋左右各一排，留中間書架口
        for x0_, x1_ in ((x0 + .2, -.8), (.8, x1 - .2)):
            bg.append(shelf_svg(cam, x0_, x1_, z1 - .45, h * .78))
        for zz in np.arange(z0 + 1.5, z1 - 1.2, 1.6):
            for xs in (x0 + .35, x1 - .35): prims.append((shelf_side_svg(cam, xs, zz, h * .78), cam.depth((xs, 1, zz))))
    if "window" in feats:
        wq = [(-.6, 1.2, z1 - .01), (.6, 1.2, z1 - .01), (.6, 2.2, z1 - .01), (-.6, 2.2, z1 - .01)]
        bg.append(poly_svg(cam, [np.array(p) for p in wq], "#eae3cf", INK, 2)[0])
        for k in (-.2, .2): bg.append(line_svg(cam, (k, 1.2, z1 - .02), (k, 2.2, z1 - .02), "#6b5a45", 1.6))
        bg.append(line_svg(cam, (-.6, 1.7, z1 - .02), (.6, 1.7, z1 - .02), "#6b5a45", 1.6))
    if "bed" in feats:
        prims.append(box_prim(cam, (x1 - .55, 0, 1.0), 1.0, .45, 2.0, "#8a7356"))
    if "lamp" in feats and "lamp" not in R.get("_props", []):
        lp = np.array([x0 + .3, 2.2, z1 - 1.0]); q = cam.proj(lp)
        if cam.depth(lp) > NEAR:
            r = max(4, 300 / cam.depth(lp) / 10)
            bg.append(f'<circle cx="{q[0]:.1f}" cy="{q[1]:.1f}" r="{r*4:.1f}" fill="#fff4cc" opacity="0.45"/><rect x="{q[0]-r/2:.1f}" y="{q[1]-r:.1f}" width="{r:.1f}" height="{r*1.6:.1f}" fill="#e8b860" stroke="{INK}" stroke-width="1.2"/>')
    return bg, prims
def shelf_svg(cam, xa, xb, z, h):
    out = poly_svg(cam, [np.array(p) for p in [(xa, 0, z), (xb, 0, z), (xb, h, z), (xa, h, z)]], "#8b735a", INK, 1.6)[0]
    for yy in np.arange(.45, h, .5):
        out += line_svg(cam, (xa, yy, z - .01), (xb, yy, z - .01), "#4a3a2a", 1.4)
        rng = np.random.default_rng(int(yy * 100))
        xx = xa + .05
        while xx < xb - .1:
            w = rng.uniform(.04, .09); hh = rng.uniform(.25, .4)
            out += poly_svg(cam, [np.array(p) for p in [(xx, yy + .02, z - .02), (xx + w, yy + .02, z - .02), (xx + w, yy + .02 + hh, z - .02), (xx, yy + .02 + hh, z - .02)]],
                            rng.choice(["#c9b48f", "#a8946f", "#d8cdb3", "#7a8a8c"]), "#3a3a3a", .7)[0]
            xx += w + .01
    return out
def shelf_side_svg(cam, x, zc, h, d=1.1):
    out = poly_svg(cam, [np.array(p) for p in [(x, 0, zc - d / 2), (x, 0, zc + d / 2), (x, h, zc + d / 2), (x, h, zc - d / 2)]], "#7d6750", INK, 1.6)[0]
    sgn = 1 if x < 0 else -1; rng = np.random.default_rng(int(zc * 10) + 99)
    for yy in np.arange(.45, h, .5):
        out += line_svg(cam, (x, yy, zc - d / 2), (x, yy, zc + d / 2), "#3e3022", 1.2)
        zz = zc - d / 2 + .04
        while zz < zc + d / 2 - .08:
            w = rng.uniform(.05, .1); hh = rng.uniform(.25, .4); xx = x + sgn * .02
            out += poly_svg(cam, [np.array(p) for p in [(xx, yy + .02, zz), (xx, yy + .02, zz + w), (xx, yy + .02 + hh, zz + w), (xx, yy + .02 + hh, zz)]],
                            rng.choice(["#c9b48f", "#a8946f", "#d8cdb3", "#7a8a8c"]), "#3a3a3a", .7)[0]
            zz += w + .012
    return out
def steps_prims(cam, R):
    bg, prims = [], []; top, rise, run, n, hw = R["top"], R["rise"], R["run"], R["n"], R["half_w"]
    bg.append(f'<rect width="{W}" height="{H}" fill="#4a5462"/>')
    # 遠山
    rng = np.random.default_rng(3); ridge = [np.array([x, 0, 70.0]) for x in np.linspace(-90, 90, 2)]
    pts = [np.array([x, 6 + 10 * abs(math.sin(x * .07)) + rng.uniform(0, 5), 70.0]) for x in np.linspace(-90, 90, 24)]
    bg.append(poly_svg(cam, [np.array([-90, -5, 70.0])] + pts + [np.array([90, -5, 70.0])], "#606b78", "#3c444f", 1.2)[0])
    # 下方地坪（濕石板）
    L = n * run
    bg.append(poly_svg(cam, [np.array(p, float) for p in [(-14, 0, L), (14, 0, L), (14, 0, 40), (-14, 0, 40)]], "#767d86", INK, 1.4)[0])
    for zz in np.arange(L, 30, .9): bg.append(line_svg(cam, (-14, .001, zz), (14, .001, zz), "#4f565e", .8))
    for xx in np.arange(-14, 14, 1.1): bg.append(line_svg(cam, (xx, .001, L), (xx * 1.05, .001, 30), "#4f565e", .8))
    # 平台
    bg.append(poly_svg(cam, [np.array(p, float) for p in [(-6, top, -4), (6, top, -4), (6, top, 0), (-6, top, 0)]], "#8a9097", INK, 1.4)[0])
    # 階：每階一個盒（踢面＋踏面）
    for i in range(n):
        z0, y = i * run, top - (i + 1) * rise
        tread = [np.array(p, float) for p in [(-hw, y, z0), (hw, y, z0), (hw, y, z0 + run), (-hw, y, z0 + run)]]
        riser = [np.array(p, float) for p in [(-hw, y, z0), (hw, y, z0), (hw, y + rise, z0), (-hw, y + rise, z0)]]
        s1, d1 = poly_svg(cam, riser, "#666d75", INK, 1.3); s2, d2 = poly_svg(cam, tread, "#959ba1", INK, 1.3)
        side = [np.array(p, float) for p in [(hw, 0, z0), (hw, 0, z0 + run), (hw, y, z0 + run), (hw, y, z0)]]
        side2 = [np.array(p, float) for p in [(-hw, 0, z0), (-hw, 0, z0 + run), (-hw, y, z0 + run), (-hw, y, z0)]]
        prims.append((poly_svg(cam, side, "#5f666e", INK, 1.2)[0] + poly_svg(cam, side2, "#5f666e", INK, 1.2)[0], cam.depth(np.array([0, y, z0 + run / 2])) + 3))
        prims.append((s1 + s2 + line_svg(cam, (-hw * .7, y + .001, z0 + .05), (hw * .4, y + .001, z0 + .06), "#c9d3db", .9), cam.depth(np.array([0, y, z0 + run / 2])) + 2.5))
    # 石欄（+x 側）
    for i in range(0, n + 1, 3):
        z = i * run; y = top - i * rise if i else top
        prims.append(box_prim(cam, (hw + .15, y, z), .24, .85, .24, "#7f868d"))
    for i in range(0, n, 3):
        z1, z2 = i * run, min(n, i + 3) * run; y1, y2 = top - i * rise, top - min(n, i + 3) * rise
        prims.append((line_svg(cam, (hw + .15, y1 + .78, z1), (hw + .15, y2 + .78, z2), INK, 5) + line_svg(cam, (hw + .15, y1 + .78, z1), (hw + .15, y2 + .78, z2), "#8b9298", 3), cam.depth(np.array([hw + .15, y1, z1 + run])) ))
    # 岩塊（-x 側）
    prims.append((hull_svg(cam, [np.array(p, float) for p in [(-hw - .1, 0, -1), (-hw - 2.5, 0, -1), (-hw - .1, 0, L + 1), (-hw - 2.8, 0, L + .5), (-hw - .3, 2.6, -.5), (-hw - 1.8, 2.9, 1), (-hw - .4, 1.4, L)]], "#646a63", 1.6)[0], cam.depth(np.array([-hw - 1.2, 1, L / 2])) + 2))
    # 閣：牆、紅柱、格扇、簷
    zf = -2.6
    prims.append((poly_svg(cam, [np.array(p, float) for p in [(-6, top, zf), (6, top, zf), (6, top + 4.2, zf), (-6, top + 4.2, zf)]], "#6e4b3e", INK, 1.6)[0], 1e4))
    s = ""
    for x in np.arange(-5, 5.1, 2.0):
        s += poly_svg(cam, [np.array(p, float) for p in [(x - .14, top, zf + .3), (x + .14, top, zf + .3), (x + .14, top + 4.2, zf + .3), (x - .14, top + 4.2, zf + .3)]], "#8c3a2c", INK, 1.4)[0]
        for xx in np.arange(x + .35, x + 1.8, .25): s += line_svg(cam, (xx, top + .3, zf + .01), (xx, top + 3.4, zf + .01), "#c99a5a", 1.0)
    s += poly_svg(cam, [np.array(p, float) for p in [(-7, top + 4.2, zf + 1.6), (7, top + 4.2, zf + 1.6), (7, top + 4.9, zf - .4), (-7, top + 4.9, zf - .4)]], "#3a3c40", INK, 1.6)[0]
    prims.append((s, 9e3))
    # 護閣燈
    lp = np.array([.9, top + 3.3, -1.0]); x, y = cam.proj(lp); d_ = cam.depth(lp)
    if d_ > NEAR:
        r = .25 * cam.fx / d_
        prims.append((f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r*2.6:.1f}" fill="#f4d68c" opacity="0.25"/>' + line_svg(cam, lp + [0, .25, 0], lp + [0, .9, 0], INK, 1.5) +
                      box_prim(cam, (lp[0], lp[1] - .22, lp[2]), .3, .44, .3, "#f0c66c")[0], d_))
    # 松樹（+x 外側）
    base = np.array([hw + 1.6, 0, 2.0]); s = capsule_svg(cam, base, base + [-.3, 4.5, -.6], .16, .1, "#4b3d33", 1.6)[0]
    for k, (dx, dy, dz, rr) in enumerate([(-.8, 4.2, -.8, .9), (-1.8, 4.6, -1.2, .8), (.2, 3.6, -.3, .7), (-1.2, 3.5, .1, .7)]):
        c = base + [dx, dy, dz]; s += hull_svg(cam, ring(c, np.array([1., 0, 0]), np.array([0, .45, 0]), rr * 1.4, rr, 14), "#3f5348", 1.4)[0]
    prims.append((s, cam.depth(base + [0, 3, 0])))
    # 落水
    for k in range(6):
        p = np.array([hw + .4 - k * .35, top + 1.6 - k * .27, 1.0 + k * .45])
        prims.append((line_svg(cam, p, p + [0, -.12, 0], "#cfe6f0", 1.6), cam.depth(p)))
    return bg, prims
def box_prim(cam, c, w, h, d, fill):
    x, y, z = c; P = lambda dx, dy, dz: np.array([x + dx, y + dy, z + dz])
    v = [P(sx * w / 2, sy, sz * d / 2) for sx in (-1, 1) for sy in (0, h) for sz in (-1, 1)]
    return hull_svg(cam, v, fill, 1.6)[0] + line_svg(cam, P(-w / 2, h, -d / 2), P(w / 2, h, -d / 2), INK, 1.2), cam.depth(c)
def cushion_prim(cam, c, r=.38, h=.12):
    c = np.array(c, float); top = ring(c + [0, h, 0], np.array([1., 0, 0]), np.array([0, 0, 1.]), r, r, 24)
    bot = ring(c, np.array([1., 0, 0]), np.array([0, 0, 1.]), r * 1.02, r * 1.02, 24)
    s1 = hull_svg(cam, top + bot, "#cdbf9f", 1.4)[0]
    s2 = poly_svg(cam, top, "#d8cbab", INK, 1.2)[0]
    rings = "".join(poly_svg(cam, ring(c + [0, h + .002, 0], np.array([1., 0, 0]), np.array([0, 0, 1.]), r * k, r * k, 20), "none", "#9b8e72", .8)[0] for k in (.35, .62, .85))
    return s1 + s2 + rings, cam.depth(c)
def cloth_book_prims(cam, c, blur=False):
    c = np.array(c, float); P = lambda dx, dz, dy=0: c + np.array([dx, dy, dz])
    ex = 'filter="url(#dof)"' if blur else ""
    out = []
    s, z = poly_svg(cam, [P(-.36, -.3, .003), P(.36, -.3, .003), P(.38, .3, .003), P(-.34, .31, .003)], "#bdb8ae", INK, 1.4, ex); out.append((s, z + .3))
    w, d, t = .34, .24, .012
    s, _ = poly_svg(cam, [P(-w / 2, -d / 2, t), P(w / 2, -d / 2, t), P(w / 2, d / 2, t), P(-w / 2, d / 2, t)], "#faf7ef", INK, 1.6, ex); out.append((s, z + .2))
    lines = line_svg(cam, P(0, -d / 2, t + .001), P(0, d / 2, t + .001), INK, 1.2, ex)
    for k in range(9):
        zz = -d / 2 + .025 + k * .023
        lines += line_svg(cam, P(.015, zz, t + .001), P(w / 2 - .02, zz, t + .001), "#3a3a3a", 1.0, ex + ' stroke-dasharray="5 3"')
    out.append((lines, z + .19))
    return out

# ---------------------------------------------------------------- 場面站位（讀 stages/*.json）
import glob as _glob
STAGE_DIR = ["stages"]
def step_y(R, z):
    if z < 0: return R["top"]
    i = int(z // R["run"]); return 0.0 if i >= R["n"] else R["top"] - (i + 1) * R["rise"]
def load_stage(shot_id):
    parts = shot_id.split("-"); keys = [shot_id, "-".join(parts[:3]), "-".join(parts[:2])]
    for k in keys:
        for fp in sorted(_glob.glob(os.path.join(STAGE_DIR[0], "*.json"))):
            cfg = json.load(open(fp))
            if "stagings" not in cfg: continue
            if k in cfg["stagings"]: sg = cfg["stagings"][k]; break
        else: continue
        break
    else:
        asset = SCENE.get("-".join(parts[:2]), {}).get("asset")
        for fp in sorted(_glob.glob(os.path.join(STAGE_DIR[0], "*.json"))):
            cfg = json.load(open(fp))
            if asset and cfg.get("scene_id") == asset and "room" in cfg: return auto_stage(shot_id, base=cfg)
        return auto_stage(shot_id)
    A = {}; R = cfg["room"]
    for a in sg["actors"]:
        pos = a.get("pos")
        if pos is None:
            z = (a["step"] + .5) * R["run"]; pos = [a.get("x", 0), step_y(R, z), z]
        A[a["id"]] = Actor(a["id"], pos, a["facing"], a.get("pose", "kneel"))
    props = {p["type"]: dict(p, pos=np.array(p["pos"], float)) for p in sg["props"]}
    return dict(room=cfg["room"], actors=A, props=props, axis_side=np.array(sg["axis_side"], float), persistent=sg.get("persistent", []))

SCENE = {}   # scene_id -> dict(cids=[...], text=全場文字, seg=第一段 metadata)
def _kw(group, text):
    return [k for k, rx in RULES.get(group, {}).items() if re.search(rx, text)]
def actor_pose(cid, text, default):
    nm = look(cid)["name"] or cid
    for m in re.finditer(re.escape(nm), text):
        seg = text[m.end():m.end() + 10]
        for k in ("kneel", "sit", "stand"):
            rx = RULES.get("poses", {}).get(k)
            if rx and re.search(rx, seg): return "kneel" if k in ("kneel", "sit") else "stand"
    return default
def auto_stage(shot_id, base=None):
    """沒有 stages 設定時，從 layer2 全場文字自動搭場景與站位（新專案零設定可跑）。"""
    sc = "-".join(shot_id.split("-")[:2]); info = SCENE.get(sc, dict(cids=[], text="", axis=""))
    if "_auto" in info: cfg = info["_auto"]
    else:
        text = info["text"]; feats = _kw("room_features", text); props = _kw("props", text)
        pose = next(iter(_kw("poses", info["axis"] + info["text"])), "stand")
        pose = "kneel" if pose in ("kneel", "sit") else "stand"
        cids = [c for c in info["cids"] if not c.startswith("C-func")]; extras_ = [c for c in info["cids"] if c.startswith("C-func")]
        # 依連戲軸線描述決定誰在畫左／畫右
        def scr_pos(cid):
            nm = look(cid)["name"]; ax = info["axis"]; i = ax.find(nm)
            if i < 0: return 0
            m = re.match(r"[（(]?\s*(?:在|居)?(畫左|畫右|左|右)", ax[i + len(nm):])   # 名字後緊接的（畫左）
            if m: return -1 if "左" in m.group(1) else 1
            m = re.search(r"(畫左|畫右|[案桌]左|[案桌]右)的?$", ax[max(0, i - 6):i])     # 名字前的「案左的」
            if m: return -1 if "左" in m.group(1) else 1
            return 0
        cids.sort(key=scr_pos)
        gap = .55 if pose == "kneel" else .7
        if base:
            R = base["room"]; anc = base.get("auto_anchor", {})
        else:
            R = dict(x0=-3.2, x1=3.2, z0=-5.0, z1=4.0, h=3.6, features=feats, lectern=None, cushions=None); anc = {}
            if "door" not in feats: R["door"] = None
        O = np.array(anc.get("pos", [0, 0, 0]), float); info["axis_side"] = anc.get("axis_side", [0, 0, -1])
        actors = []
        if len(cids) == 1: actors.append(dict(id=cids[0], pos=[0, 0, 0], facing=180, pose=actor_pose(cids[0], text, pose)))
        elif cids:
            p0, p1 = actor_pose(cids[0], text, pose), actor_pose(cids[1], text, pose)
            g0 = .55 if p0 == "kneel" else .5; g1 = .55 if p1 == "kneel" else .5
            if "table" not in props and p0 == p1 == "stand": g0 = g1 = .45
            actors.append(dict(id=cids[0], pos=[-g0, 0, 0], facing=90, pose=p0))
            actors.append(dict(id=cids[1], pos=[g1, 0, 0], facing=-90, pose=p1))
            for k, c in enumerate(cids[2:]): actors.append(dict(id=c, pos=[(-1) ** k * 1.4, 0, 1.2 + k * .5], facing=180 if k % 2 else 180, pose="stand"))
        n_extra = 2 if re.search(r"兩名|兩道|兩個|二人|兩人", text) else (3 if re.search(r"三名|三道|數名|幾名", text) else 1)
        for k, c in enumerate(extras_):
            for j in range(n_extra): actors.append(dict(id=c, pos=[-.35 + j * .7 - k * 1.6, 0, 2.4 + .15 * j], facing=180, pose="stand", dup=j))
        pr = []
        stand_any = any(actor_pose(c, text, pose) == "stand" for c in cids)
        top = (.75 if stand_any else .32) if "table" in props else 0   # 有人站著就用一般桌高
        if "table" in props: pr.append(dict(type="table", pos=[0, 0, 0], h=top, w=1.0 if top < .5 else 1.1, d=.6 if top < .5 else .7))
        if "book" in props: pr.append(dict(type="book", pos=[0.03, top, 0]))
        if "bowl" in props: pr.append(dict(type="bowl", pos=[0.15, top, .28]))
        if "lamp" in props and top: pr.append(dict(type="lamp", pos=[-.3, top, .22]))
        if base and R.get("type") == "steps": pr = [q for q in pr if q["type"] not in ("table",)]
        if not any(q["type"] == "table" for q in pr):   # 沒有桌面：書／紙拿在手上
            for q in pr:
                if q["type"] == "book" and re.search(r"掌上|手中|手上|捧著|托著", text): q["attach"] = "lwr"
        # 自動站位以「相機在 -z 側」寫成（畫左＝-x）；相機側不同時整組繞 y 轉，畫左／畫右才不會反
        s_ax = np.array(info["axis_side"], float); rot = math.atan2(-s_ax[0], -s_ax[2])
        def place(q):
            q = rot_y(np.array(q, float), rot) + O
            if R.get("type") == "steps": q[1] += step_y(R, q[2])
            return q.tolist()
        for a in actors: a["pos"] = place(a["pos"]); a["facing"] = a["facing"] + math.degrees(rot)
        for q in pr: q["pos"] = place(q["pos"])
        cfg = info["_auto"] = dict(room=R, actors=actors, props=pr, axis_side=info["axis_side"], anchor=O.tolist())
    A = {}
    for a in cfg["actors"]:
        key = a["id"] + ("#%d" % a["dup"] if a.get("dup") else ""); A[key] = Actor(a["id"], a["pos"], a["facing"], a["pose"])
    props = {p["type"]: dict(p, pos=np.array(p["pos"], float)) for p in cfg["props"]}
    return dict(room=cfg["room"], actors=A, props=props, axis_side=np.array(cfg["axis_side"], float), persistent=[], auto=True, anchor=np.array(cfg["anchor"]))

# ---------------------------------------------------------------- layer2 → 相機
def num_m(s, d):
    m = re.search(r"([\d.]+)\s*m(?!m)", s or ""); return float(m.group(1)) if m else d
def frac_u(t):
    if re.search(r"畫左三分之一|居畫左|在畫左", t): return 1 / 3
    if re.search(r"畫右三分之一|居畫右|在畫右", t): return 2 / 3
    return None
COVER = {"ECU": .2, "CU": .36, "MCU": .58, "MS": .95, "OTS_CU": .42, "OTS_MS": .8, "MLS": 1.5, "LS": 2.8, "ELS": 7.0}  # 畫面垂直涵蓋（公尺）
def size_dist(cam, size, fallback):
    """依景別標籤反推物距：成片是照景別取景，不是照 layer2 寫的物距。"""
    cv = COVER.get(size); return cv * cam.fx / H if cv else fallback
COVER_TOP = {"ECU": .42, "CU": .7, "MCU": 1.0, "MS": 1.6}  # 俯拍桌面／物件
COVER_HAND = {"ECU": .3, "CU": .45}
EYE_V = {"ECU": .45, "CU": .42, "MCU": .36, "MS": .32, "OTS_MS": .34, "MLS": .28, "LS": .25, "ELS": .3}

RULES = {}
def load_rules(path):
    RULES.update(json.load(open(path)))
def _target(spec, st, a):
    if "prop" in spec:
        p = st["props"].get(spec["prop"])
        if p is not None and p.get("attach"): p["pos"] = a.J(p["attach"]) + a.F * .05 + np.array([0, .03, 0])
        return None if p is None else p["pos"] + np.array(spec.get("off", [0, 0, 0]), float)
    t = a.J(spec["self"]) + a.F * spec.get("F", 0) + a.R * spec.get("R", 0) + np.array([0, spec.get("Y", 0), 0])
    srf = spec.get("to_surface")
    if srf and srf in st["props"]: t[1] = st["props"][srf]["pos"][1] + st["props"][srf].get("h", .32) + .01
    return t
def apply_actions(st, subj, txt):
    """依 rules/actions.json 把描述裡的動作關鍵字轉成姿勢操作；回傳附加道具。"""
    A, P = st["actors"], st["props"]; extra = []
    for ps in st["persistent"]:
        a = A[ps["actor"]]
        if ps["action"] == "hover": a.lean(ps.get("lean", 15)); a.reach("r", P[ps["prop"]]["pos"] + np.array([.03, .035, 0]))
    if subj is None: return extra
    for r in RULES.get("actions", []):
        if not re.search(r["match"], txt) or (r.get("not") and re.search(r["not"], txt)): continue
        if r.get("need") and r["need"] not in P: continue
        if r.get("pose_from") and subj.kind != r["pose_from"]: continue
        for op in r["ops"]:
            if "lean" in op: subj.lean(op["lean"])
            elif "reach" in op:
                t = _target(op["reach"]["target"], st, subj)
                if t is not None: subj.reach(op["reach"].get("hand", "r"), t, hover_hand=op["reach"].get("hover", True))
            elif "pose" in op:
                subj.L = {k: np.array(v, float) * subj.c["scale"] for k, v in POSES[op["pose"]].items()}; subj.kind = op["pose"]
            elif "head_pitch" in op: subj.head_pitch = op["head_pitch"]
            elif "head_yaw" in op: subj.head_yaw = op["head_yaw"]
            elif "extra" in op:
                e = op["extra"]
                if e["type"] == "waterline":
                    h = subj.J("head"); extra.append(("waterline", h - subj.F * .9 + subj.R * .09 + np.array([0, .02, 0]), h + subj.F * .7 + subj.R * .1))
                else:
                    t = _target(e["target"], st, subj)
                    if t is not None: extra.append((e["type"], subj, t))
    return extra

WARN = []
def check_direction(shot, cam, A):
    """layer2 寫的「面向／朝／看向 畫左右」與「居畫左右」對照實際投影，不符就記警告（不硬改，避免越軸）。"""
    sb = shot.get("spatial_blocking") or {}; txt = sb.get("blocking_desc", "") + (shot.get("camera_optics") or {}).get("axis_side", "")
    for cid in shot.get("character_ids", [])[:1]:
        a = A.get(cid)
        if a is None or cam.depth(a.J("head")) < .1: continue
        nm = look(cid)["name"] or cid; h = a.J("head"); x0 = cam.proj(h)[0]; dx = cam.proj(h + a.F * .3)[0] - x0
        m = re.search(r"(面向|朝|看向|看)畫(左|右)", txt)
        if m and abs(dx) > 8 and ((m.group(2) == "右") != (dx > 0)):
            WARN.append(f"{shot['shot_id']} {nm}：文字寫{m.group(0)}，構圖卻朝畫{'右' if dx > 0 else '左'}")
        m = re.search(r"(居|在)?畫(左|右)(三分之一)?[、，]", txt)
        if m and "前景" not in txt[max(0, m.start() - 8):m.end()] and not shot["camera_optics"].get("shot_size", "").startswith("OTS"):
            pass
def setup_shot(shot):
    st = load_stage(shot["shot_id"]); A = st["actors"]; P = st["props"]
    co, sb = shot["camera_optics"], shot["spatial_blocking"]
    txt = sb.get("blocking_desc", "") + "；" + co.get("axis_side", ""); pd = co.get("physical_distance", "")
    f = int(re.search(r"(\d+)mm", co.get("focal_length", "50mm")).group(1)); dist = num_m(pd, 3.0)
    size = co.get("shot_size", "MS"); cids = [c for c in shot["character_ids"] if c in A]
    subj = A[cids[0]] if cids else None
    if subj is not None and re.search(r"剪影|逆光", txt):
        for a in A.values():
            if a.cid == subj.cid: a.c = dict(a.c, robe="#34363d", robe_dk="#26282e", trousers="#34363d", skin="#3a3c42", hair="#202126", sash="#202126", pin="#202126", strip="#202126", name=a.c["name"] + "（剪影）")
    side_dir = st["axis_side"]; extras = apply_actions(st, subj, txt)
    for p_ in P.values():
        if p_.get("attach") and subj is not None: p_["pos"] = subj.J(p_["attach"]) + subj.F * .05 + np.array([0, .03, 0])
    book = P.get("book", {}).get("pos"); bowl = P.get("bowl", {}).get("pos")
    cam = Cam((0, 1, 0), f=f); dist_label = dist; dist = size_dist(cam, size, dist)
    if "正上方" in pd + txt:
        focus = bowl if ("碗" in pd and bowl is not None) else (book + np.array([.03, .035, 0]))
        dist = COVER_TOP.get(size, .6) * cam.fx / H if size in COVER_TOP else dist_label
        cam.pos = focus + np.array([0, dist, 0]); cam.yaw, cam.pitch = 0, -math.pi / 2 + 1e-4; cam.update()
        t = cam.proj(focus); cam.du, cam.dv = W / 2 - t[0], H / 2 - t[1]
        if "碗" in pd: extras.append(("reflection", txt))
        return cam, st, extras
    if subj is None:   # 無人空鏡／純物件：從相機側看場景基準點
        anc = st.get("anchor", np.zeros(3)); low = re.search(r"貼地|低角度", pd + txt)
        tgt = anc + np.array([0, .15 if low else .9, 0])
        R_ = st["room"]
        if re.search(r"門", txt) and R_.get("door") is not False and R_.get("type") != "steps" and "x0" in R_:
            dz = (R_.get("door") or {}).get("z", [-3.2, -1.6]); tgt = np.array([R_["x0"] + .02, .1 if low else 1.2, sum(dz) / 2])
            cam.pos = tgt + np.array([1, 0, 0]) * max(dist, .8) + np.array([0, .05 if low else 0, 0])
        else:
            cam.pos = tgt + side_dir * max(dist, 3.0) + np.array([0, .05 if low else .4, 0])
        cam.look_at(tgt)
        return cam, st, extras
    if "貼地" in pd + txt:
        tgt = book + np.array([0, .02, 0]); cam.pos = tgt + side_dir * dist + np.array([0, .06, 0]); cam.look_at(tgt)
        x, y = cam.proj(tgt); cam.du, cam.dv = .42 * W - x, .7 * H - y
        if "漾" in txt: extras.append(("ripple", None))
        return cam, st, extras
    faces_out = re.search(r"臉都在畫框外|臉不入畫|不見臉", txt)
    if faces_out and book is not None:  # 案面高度、只見手與道具
        dist = .55 * cam.fx / H
        tgt = book + np.array([0, .08, 0]); cam.pos = tgt + side_dir * dist + np.array([0, .12, 0]); cam.look_at(tgt)
        x, y = cam.proj(tgt); cam.du, cam.dv = .5 * W - x, .62 * H - y
        return cam, st, extras
    hand_only = re.search(r"只拍.{0,12}(手|指|腕|袖|掌|書口|簿|冊|頁|紙)|只見.{0,10}手|袖口特寫|(紙|頁|冊|簿)特寫|手特寫|(手|拇指|指尖|書口|裝訂).{0,6}特寫|特寫.{0,8}(手|拇指)", txt) and size in ("ECU", "CU")
    if hand_only and subj is not None:
        tgt = subj.w(subj.L["rwr"])
        if book is not None and re.search(r"簿頁|書口|頁緣", txt): tgt = tgt * .5 + (book + np.array([.1, .02, 0])) * .5
        if book is not None and re.search(r"裝訂", txt): tgt = book + np.array([0, .015, 0])
        dist = COVER_HAND.get(size, .3) * cam.fx / H
        pitch = math.radians(-45 if "45°" in pd else (-30 if "略俯" in pd + txt else (-42 if "側俯" in pd + txt else -20)))
        cam.pos = tgt + (side_dir * math.cos(-pitch) + np.array([0, 1, 0]) * math.sin(-pitch)) * dist
        cam.look_at(tgt)
        u = .36 if "畫左" in txt else (.6 if "畫右" in txt else .5); v = .38 if "上方" in txt else .5
        if size == "ECU": u, v = .56, .4
        x, y = cam.proj(tgt); cam.du, cam.dv = u * W - x, v * H - y
        if size == "ECU" and not re.search(r"裝訂|書口|頁緣|簿頁", txt): extras.append(("book_blur", None))
        return cam, st, extras
    if size.startswith("OTS"):
        cand = [A[k] for k in shot["character_ids"] if k in A and A[k] is not subj] or [a for a in A.values() if a is not subj]
        fg = cand[0]; fg.soft = True
        # 取靠相機側（axis_side）的那個肩，保證不跨 180 度線；文字的左右肩只用來決定前景落在畫面哪側
        shp = max((fg.J("rsh"), fg.J("lsh")), key=lambda p: float(np.dot(p - fg.J("neck"), side_dir))); out_v = nrm(shp - fg.J("neck")) * np.array([1, 0, 1])
        sh = shp + nrm(out_v) * .1; sh[1] = min(fg.J("head")[1], subj.J("head")[1]) - .03   # 前景耳高、略低於兩人眼高：平視
        tgt = subj.J("head"); d_ = nrm(sh - tgt)
        # 成片的過肩：相機緊貼前景肩後方（前景佔畫面 ~1/3 以上），再用焦距把主體縮放到景別涵蓋
        dist = np.linalg.norm(sh - tgt) + .42
        cam.f = float(np.clip(H * dist / COVER.get(size, .5) / W * SENSOR_W, 24, 135))
        if "畫左三分之一" in txt: u = 2 / 3          # 「X 在畫左三分之一」講的是前景 → 主體在右
        elif "畫右三分之一" in txt: u = 1 / 3
        else: u = 2 / 3 if re.search(r"(對焦|主體).{0,4}在畫右|在畫右.{0,3}對焦", txt) else 1 / 3
        u_fg = .8 if u < .5 else .2          # 前景肩落在另一側、靠畫框邊（允許部分出框）
        lat = nrm(np.cross(d_, [0, 1, 0]))
        def place(s_):
            cam.pos = tgt + d_ * dist + lat * s_; cam.look_at(tgt); cam.yaw += math.atan((.5 - u) * W / cam.fx); cam.update()
            return cam.proj(fg.J("head"))[0] / W
        def cost(s_):
            fx_ = place(s_); hx = cam.proj(fg.J("head"))[0] / W
            hr = .12 * cam.fx / max(.05, cam.depth(fg.J("head"))) / W   # 前景頭投影半徑（畫面比例）
            face_r = .1 * cam.fx / max(.05, cam.depth(tgt)) / W
            occl = max(0, hr * .75 + face_r * .6 - abs(hx - u)) * 10          # 前景頭不得蓋住主體臉
            behind = 5 if cam.depth(shp) < .15 else 0
            return abs(fx_ - u_fg) + occl + behind
        best = min(np.linspace(-1.6, 1.6, 81), key=cost)
        if os.environ.get("RIG_DEBUG"):
            for s_ in np.linspace(-1.6, 1.6, 17): print("ots", round(s_, 2), round(place(s_), 2), round(cost(s_), 2), round(cam.proj(fg.J("head"))[0] / W, 2), round(cam.depth(shp), 2))
        place(best)
        x, y = cam.proj(tgt); cam.dv = EYE_V.get(size, .36) * H - y
        st["visible"] = {subj.cid, fg.cid}
        return cam, st, extras
    ang = 90 if "正側" in txt else (55 if re.search(r"3/4|三分之四", txt) else (80 if "側臉" in txt else (10 if re.search(r"正面", txt) else 45)))
    if "背後" in pd: ang = 180
    elif re.search(r"側後|背影|背對鏡頭", pd + txt): ang = 145
    D = nrm(subj.F * math.cos(math.radians(ang)) + side_dir * math.sin(math.radians(ang)))
    hk = "略高" if re.search(r"略高|略俯", pd) else ("略低" if re.search(r"略低|低角度", pd) else "平視")
    h_off = {"平視": 0, "略低": -.16, "略高": .25 if "略俯" in pd else .2}[hk]
    head = subj.J("head")
    if size in ("MS", "MLS", "LS"): head = head * .55 + subj.J("waist") * .45
    if "背後" in pd: h_off = 1.1
    cam.pos = head + D * dist + np.array([0, h_off, 0])
    R_ = st["room"]
    if R_.get("type") == "steps" and cam.pos[2] < R_["n"] * R_["run"]:  # 機位在階上時留在石欄內
        cam.pos[0] = float(np.clip(cam.pos[0], -R_["half_w"] + .25, R_["half_w"] - .25))
        cam.pos[1] = max(cam.pos[1], step_y(R_, cam.pos[2]) + .5)
    cam.look_at(head); cam.pitch = -math.radians(17) if "背後" in pd else {"略高": math.radians(-9 if "略俯" in pd else -6), "略低": math.radians(4), "平視": 0}[hk]; cam.update()
    u = frac_u(txt)
    if u is None:
        s = np.dot(subj.F, cam.rt); u = .42 if s > .2 else (.58 if s < -.2 else .5)
    cam.yaw += math.atan((.5 - u) * W / cam.fx); cam.update()
    v = EYE_V.get(size, .36)
    if re.search(r"臉在畫上半", txt): v = .3
    if size == "ECU" and re.search(r"眼部|眉到眼|眼睛特寫|雙眼特寫", txt):
        v = .5; head = head + subj.F * .07 + np.array([0, .015, 0]); cam.pos = head + nrm(cam.pos - head) * (.09 * cam.fx / H) + np.array([0, .0, 0]); cam.look_at(head); cam.update()
    x, y = cam.proj(head); cam.dv = v * H - y
    return cam, st, extras

def bowl_prims(cam, c, ripple=False):
    c = np.array(c, float); X, Z = np.array([1., 0, 0]), np.array([0, 0, 1.])
    top = ring(c + [0, .065, 0], X, Z, .085, .085, 28); bot = ring(c, X, Z, .05, .05, 20)
    s = hull_svg(cam, top + bot, "#b9b2a3", 1.5)[0] + poly_svg(cam, top, "#d9dde0", INK, 1.5)[0]
    s += poly_svg(cam, ring(c + [0, .055, 0], X, Z, .072, .072, 28), "#c7d0d4", "#8a969b", .8)[0]
    if ripple:
        for k in (.25, .45, .65): s += poly_svg(cam, ring(c + [0, .056, 0], X, Z, .072 * k, .072 * k, 24), "none", "#6f7d83", .9)[0]
    return s, cam.depth(c)
def brush_prims(cam, tip):
    top = tip + np.array([.1, .17, .09]); s = capsule_svg(cam, tip + np.array([0, .03, 0]), top, .006, .007, "#6d5a45", 1.2)[0]
    s += capsule_svg(cam, tip, tip + np.array([0, .035, 0]), .002, .007, "#222", 1.0)[0]
    return s, 0.0
def reflection_svg(cam, c, label):
    """碗／水面倒影：只畫一圈虛線水面，標上 layer2 文字裡描述的倒影內容（不寫死任何畫面）。"""
    x, y = cam.proj(np.array(c) + [0, .056, 0]); r = .072 * cam.fx / cam.depth(c)
    label = (label or "倒影")[:16]
    return (f'<g opacity="0.75"><ellipse cx="{x:.1f}" cy="{y:.1f}" rx="{r*.62:.1f}" ry="{r*.22:.1f}" fill="#fff" fill-opacity=".35" stroke="#999" stroke-dasharray="4 3"/>'
            f'<text x="{x:.1f}" y="{y-r*.45:.1f}" font-size="16" text-anchor="middle" fill="#8a6a2c" font-family="{FONT_FAMILY}" font-weight="700">{label}</text></g>')

def reflection_label(shot):
    t = (shot.get("spatial_blocking") or {}).get("blocking_desc", "") + "；" + "；".join((shot.get("action_and_performance") or {}).get("action_stages", []) or [])
    m = re.search(r"(?:倒映|映出|映著|倒影(?:裡|中|是)?)[：:]?([^，。；、（）()]{2,14})", t)
    return ("倒影：" + m.group(1)) if m else "倒影"

def panel(shot, uid):
    cam, st, extras = setup_shot(shot); A, P = st["actors"], st["props"]
    check_direction(shot, cam, A)
    bg, prims = (steps_prims(cam, st["room"]) if st["room"].get("type") == "steps" else room_prims(cam, st["room"]))
    kinds = [e[0] for e in extras]
    if "table" in P:
        t = P["table"]; s_, z_ = box_prim(cam, tuple(t["pos"]), t.get("w", 1.0), t.get("h", .32), t.get("d", .6), "#6f5a44"); prims.append((s_, z_ + .6))
    if "lamp" in P:
        c_ = P["lamp"]["pos"]; body_ = [c_ + np.array([dx, dy, dz]) for dx in (-.04, .04) for dy in (0, .07) for dz in (-.04, .04)]
        s_, z_ = hull_svg(cam, body_, "#7a6248", 1.3); fl = cam.proj(c_ + np.array([0, .11, 0])); r_ = max(3, cam.fx * .02 / max(.2, cam.depth(c_)))
        prims.append((s_ + f'<ellipse cx="{fl[0]:.1f}" cy="{fl[1]:.1f}" rx="{r_*.6:.1f}" ry="{r_:.1f}" fill="#f2b84b" stroke="{INK}" stroke-width="1"/>', z_))
    if "book" in P: prims += cloth_book_prims(cam, P["book"]["pos"], blur="book_blur" in kinds)
    if "bowl" in P: prims.append(bowl_prims(cam, P["bowl"]["pos"], ripple="ripple" in kinds))
    for e in extras:
        if e[0] == "brush": prims.append(brush_prims(cam, e[2]))
        if e[0] == "talisman":
            t = e[2]; a_ = e[1]; q = [t + a_.R * .04 + np.array([0, .06, 0]), t - a_.R * .04 + np.array([0, .06, 0]), t - a_.R * .04 - np.array([0, .06, 0]), t + a_.R * .04 - np.array([0, .06, 0])]
            s, z = poly_svg(cam, q, "#e3e1da", INK, 1.4); prims.append((s, 0.0))
            for k in range(3): prims.append((line_svg(cam, t + a_.R * (.12 + k * .08) + np.array([0, .03 - k * .03, 0]), t + a_.R * (.3 + k * .1) + np.array([0, .03 - k * .03, 0]), "#555", 1.4), 0.0))
        if e[0] == "waterline":
            prims.append((line_svg(cam, e[1], e[2], "#bfe3ef", 5) + line_svg(cam, e[1], e[2], "#3d7d95", 1.6), 0.0))
    labels = []
    vis = st.get("visible") or set(shot["character_ids"]) | {ps["actor"] for ps in st["persistent"] if ps.get("always_visible")}
    for a in A.values():
        if a.cid in vis: draw_actor(cam, a, prims, labels)
    shadows = ""
    for a in A.values():
        if a.cid not in vis: continue
        s, _ = poly_svg(cam, ring(a.pos + np.array([0, .004, 0]), a.R, a.F, .3, .42, 20), "#000", "none", 0, 'opacity="0.12"'); shadows += s
    prims.sort(key=lambda p: -p[1])
    runs, cur, curb = [], [], None
    for p_ in prims:
        if not p_[0]: continue
        b = 'url(#dof)' in p_[0]
        if curb is not None and b != curb: runs.append((curb, cur)); cur = []
        cur.append(p_[0]); curb = b
    if cur: runs.append((curb, cur))
    body = '<g filter="url(#pencil)">' + "".join(bg) + shadows + '</g>' + "".join(
        ("<g>" if b else '<g filter="url(#pencil)">') + "".join(x) + "</g>" for b, x in runs)
    if "reflection" in kinds and "bowl" in P: body += reflection_svg(cam, P["bowl"]["pos"], reflection_label(shot))
    labels = [(min(max(x, 90), W - 130), y, t, col) for x, y, t, col in labels]
    labels.sort(key=lambda l: l[0])
    for i in range(1, len(labels)):   # 標籤互相不重疊
        px, py, pt, _ = labels[i - 1]; x, y, t, col = labels[i]
        if abs(y - py) < 20 and x - px < (len(pt) + len(t)) * 8.5: labels[i] = (x, py + 22, t, col)
    lab = "".join(f'<text x="{x:.1f}" y="{max(22, min(H-8, y)):.1f}" font-size="17" text-anchor="middle" fill="{col}" font-family="{FONT_FAMILY}" font-weight="700" stroke="#fff" stroke-width="4" paint-order="stroke">{t}</text>' for x, y, t, col in labels)
    co = shot["camera_optics"]; mov = co.get("movement", ""); arrows = ""
    if "dolly in" in mov or "push" in mov:
        arrows = '<g stroke="#111" stroke-width="4" marker-end="url(#ah)">' + "".join(
            f'<line x1="{x}" y1="{y}" x2="{x+(W/2-x)*.12:.0f}" y2="{y+(H/2-y)*.12:.0f}"/>' for x, y in ((16, 16), (W - 16, 16), (16, H - 16), (W - 16, H - 16))) + \
            f'</g><text x="{W-20}" y="{H-30}" font-size="16" text-anchor="end" font-family="{FONT_FAMILY}" font-weight="700" fill="#111" stroke="#fff" stroke-width="4" paint-order="stroke">慢推</text>'
    return (f'<svg width="{W}" height="{H}" overflow="hidden">{body}'
            f'<rect width="{W}" height="{H}" filter="url(#paper)" opacity="0.18"/>{lab}{arrows}</svg>')

DEFS = ('<defs><marker id="ah" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="4" markerHeight="4" orient="auto"><path d="M0,0 L10,5 L0,10 z" fill="#111"/></marker>'
        '<filter id="dof" x="-20%" y="-20%" width="140%" height="140%"><feGaussianBlur stdDeviation="5"/></filter>'
        '<filter id="pencil" x="0" y="0" width="100%" height="100%"><feTurbulence type="fractalNoise" baseFrequency="0.035" numOctaves="2" seed="4" result="n"/>'
        '<feDisplacementMap in="SourceGraphic" in2="n" scale="2.6" xChannelSelector="R" yChannelSelector="G"/></filter>'
        '<filter id="paper" x="0" y="0" width="100%" height="100%"><feTurbulence type="fractalNoise" baseFrequency="0.9" numOctaves="3" seed="2"/>'
        '<feColorMatrix type="matrix" values="0 0 0 0 0.3  0 0 0 0 0.28  0 0 0 0 0.25  0 0 0 0.9 0"/></filter></defs>')

def render_panel(shot, path):
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}">{DEFS}<rect width="100%" height="100%" fill="#f2efe8"/>{panel(shot, 0)}</svg>'
    open(path, "wb").write(bytes(resvg_py.svg_to_bytes(svg_string=svg, font_files=[FONT_PATH] if FONT_PATH else None)))

# ============================================================================== CLI 與 stage-4 回寫
TOOL_VERSION = "svg-rig/1.0"
LOCKED_STATUSES = {"locked", "approved", "manual"}


def _sha256(path):
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""): h.update(chunk)
    return h.hexdigest()


def register_scene(d):
    """把一個 Layer 2 段落的角色、連戲錨點與走位文字併入所屬場景，供自動搭景使用。"""
    sc = d.get("scene_id") or "-".join(d["shots"][0]["shot_id"].split("-")[:2])
    inf = SCENE.setdefault(sc, dict(cids=[], text="", axis=""))
    inf["asset"] = (d.get("asset_refs") or {}).get("scene_id") or inf.get("asset")
    ca = (d.get("style_lock") or {}).get("continuity_anchors") or {}
    inf["axis"] += ca.get("axis", "") + "；" + ca.get("blocking", "")
    for s in d["shots"]:
        for c in s.get("character_ids", []):
            if c not in inf["cids"]: inf["cids"].append(c)
        inf["text"] += (s.get("spatial_blocking") or {}).get("blocking_desc", "") + "；"
    inf["text"] += ca.get("blocking", "")


def draw_grid(shots, panel_paths, save_path, title=None):
    from PIL import Image, ImageDraw, ImageFont
    try: font = ImageFont.truetype(FONT_PATH, 19) if FONT_PATH else ImageFont.load_default()
    except OSError: font = ImageFont.load_default()
    G, CAP, TOP = 20, 50, (46 if title else 0)
    TW = 3 * (W + G) + G; TH = TOP + ((len(shots) + 2) // 3) * (H + CAP) + G
    grid = Image.new("RGB", (TW, TH), "#ebe7dd"); d = ImageDraw.Draw(grid)
    if title: d.text((G, 14), title, font=font, fill="#111")
    for i, (s, pp) in enumerate(zip(shots, panel_paths)):
        x, y = G + (i % 3) * (W + G), TOP + G + (i // 3) * (H + CAP); co = s.get("camera_optics") or {}
        grid.paste(Image.open(pp).convert("RGB"), (x, y)); d.rectangle([x, y, x + W - 1, y + H - 1], outline="#111", width=3)
        d.text((x, y + H + 10), f'{i + 1:02d}  {s["shot_id"]}  ·  {co.get("shot_size", "")} {co.get("focal_length", "")}  ·  {s.get("duration", "")}s', font=font, fill="#111")
    os.makedirs(os.path.dirname(os.path.abspath(save_path)), exist_ok=True)
    grid.save(save_path)
    return save_path


def _rel(path, root):
    return os.path.relpath(os.path.abspath(path), os.path.abspath(root)).replace(os.sep, "/")


def run_project(root, layer2_files, staging=None, cast=None, rules=None, force=False, write_back=True, dry_run=False, log=print):
    """渲染指定 Layer 2 段落：每鏡 panels/panel-NN-<shot>.png、每段 images/grid-<segment>.png，
    並把 sketch_file／sketch_sha256／sketch_generation.grid_file 回寫 Layer 2，讓 stage-4 門禁與審核頁直接採用。"""
    root = os.path.abspath(root)
    STAGE_DIR[0] = staging if staging and os.path.isdir(staging) else os.path.join(root, ".svg-grid-none")
    load_rules(rules or os.path.join(os.path.dirname(os.path.abspath(__file__)), "svg_rig_actions.json"))
    if cast is None and staging and os.path.isdir(staging):
        cast = next(iter(sorted(_glob.glob(os.path.join(staging, "cast*.json")))), None)
    load_cast(cast)
    # 同一場景的全部段落都先登記（自動搭景要看整場文字），只渲染指定的檔案
    layer2_dir = {os.path.dirname(os.path.abspath(f)) for f in layer2_files}
    all_files = sorted({os.path.abspath(f) for d_ in layer2_dir for f in _glob.glob(os.path.join(d_, "layer2-*.json"))} | {os.path.abspath(f) for f in layer2_files})
    docs = {f: json.load(open(f, encoding="utf-8-sig")) for f in all_files}
    targets = {os.path.abspath(f) for f in layer2_files}
    target_scenes = {(docs[f].get("scene_id") or "-".join(docs[f]["shots"][0]["shot_id"].split("-")[:2])) for f in targets}
    for f, d in docs.items():
        if (d.get("scene_id") or "-".join(d["shots"][0]["shot_id"].split("-")[:2])) in target_scenes: register_scene(d)
    infer_names(list(docs), [s for d in docs.values() for s in d.get("shots", [])])
    summary = dict(rendered=0, skipped=0, segments=0, warnings=WARN)
    for f in sorted(targets):
        d = docs[f]; shots = d.get("shots", [])
        seg = d.get("segment_id") or os.path.basename(f)[len("layer2-"):-len(".json")]
        panel_paths, changed = [], False
        for idx, s in enumerate(shots, start=1):
            pp = os.path.join(root, "panels", f"panel-{idx:02d}-{s['shot_id']}.png")
            locked = (s.get("sketch_status") in LOCKED_STATUSES) or (s.get("sketch_generation") or {}).get("locked")
            existing = s.get("sketch_file") and os.path.isfile(os.path.join(root, s["sketch_file"]))
            if locked and existing and not force:
                panel_paths.append(os.path.join(root, s["sketch_file"])); summary["skipped"] += 1
                log(f"  鎖定，略過 {s['shot_id']}"); continue
            if dry_run:
                log(f"  [dry-run] {s['shot_id']} → {_rel(pp, root)}"); continue
            os.makedirs(os.path.dirname(pp), exist_ok=True)
            render_panel(s, pp); panel_paths.append(pp); summary["rendered"] += 1
            log(f"  {s['shot_id']} → {_rel(pp, root)}")
            if write_back:
                s["sketch_file"] = _rel(pp, root); s["sketch_sha256"] = _sha256(pp); s["sketch_status"] = "generated"
                s["sketch_generation"] = dict(backend="svg-rig", tool="scripts/storyboard/svg_storyboard_grid.py", version=TOOL_VERSION,
                                              grid_file=f"images/grid-{seg}.png", api_calls=0)
                changed = True
        if dry_run or not panel_paths: continue
        gp = draw_grid(shots[:len(panel_paths)], panel_paths, os.path.join(root, "images", f"grid-{seg}.png"), title=f"{seg}  ·  SVG 構圖（免生圖）")
        summary["segments"] += 1
        if write_back and changed:
            d["grid_preview_file"] = _rel(gp, root)
            d["storyboard_panels"] = [dict(index=i, shot_id=s.get("shot_id"), panel_file=s.get("sketch_file"), sha256=s.get("sketch_sha256")) for i, s in enumerate(shots, start=1)]
            with open(f, "w", encoding="utf-8") as fh: json.dump(d, fh, ensure_ascii=False, indent=2); fh.write("\n")
    return summary


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(
        description="Layer 2 → 免生圖 SVG 構圖（2.5D 相機＋3D 人偶）。每鏡 panels/panel-NN-<shot>.png、每段 images/grid-<segment>.png，並回寫 Layer 2 供 stage-4 審核。")
    ap.add_argument("--root", default=".", help="漫劇專案根目錄（含 layer2/）")
    ap.add_argument("--layer2", nargs="*", default=None, help="指定 Layer 2 檔（可多個）；省略則用 --layer2-dir")
    ap.add_argument("--layer2-dir", default=None, help="Layer 2 目錄（預設 <root>/layer2）")
    ap.add_argument("--episode", default=None, help="只處理某集，例如 EP04")
    ap.add_argument("--segment", nargs="*", default=None, help="只處理某些段或場，例如 EP04-S04 或 EP04-S04-a")
    ap.add_argument("--staging", default=None, help="場景／站位／外觀設定資料夾（預設 <root>/staging，可不存在）")
    ap.add_argument("--cast", default=None, help="角色外觀 JSON（預設 staging 內 cast*.json；未登記角色用預設人偶）")
    ap.add_argument("--rules", default=None, help="動作／道具／場景關鍵字表（預設 svg_rig_actions.json）")
    ap.add_argument("--force", action="store_true", help="連 sketch_status 為 locked/approved/manual 的鏡頭也重畫")
    ap.add_argument("--no-write-back", action="store_true", help="只輸出圖片，不改 Layer 2")
    ap.add_argument("--dry-run", action="store_true", help="只列出會產生的檔案")
    args = ap.parse_args(argv)
    root = os.path.abspath(args.root)
    if args.layer2: files = args.layer2
    else:
        ld = args.layer2_dir or os.path.join(root, "layer2")
        files = sorted(_glob.glob(os.path.join(ld, "layer2-*.json")))
    if args.episode: files = [f for f in files if os.path.basename(f).startswith(f"layer2-{args.episode}-")]
    if args.segment: files = [f for f in files if any(os.path.basename(f)[len("layer2-"):].startswith(sg) for sg in args.segment)]
    if not files: ap.error("找不到任何 Layer 2 檔")
    staging = args.staging or os.path.join(root, "staging")
    s = run_project(root, files, staging=staging, cast=args.cast, rules=args.rules, force=args.force,
                    write_back=not args.no_write_back, dry_run=args.dry_run)
    for w in WARN: print("⚠ 方向", w)
    print(f"完成：渲染 {s['rendered']} 鏡、略過鎖定 {s['skipped']} 鏡、九宮格 {s['segments']} 段；API 呼叫 0 次")
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"): sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
