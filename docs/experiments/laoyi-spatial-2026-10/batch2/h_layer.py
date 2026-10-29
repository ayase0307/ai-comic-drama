"""H／I 組「提示詞層」：scene-consistency R1–R3＋camera-view 正反打規則＋牆面分配清單（wall-map.md）。
每鏡重寫（R1：禁「同上」），每鏡最多四句：
  1 Wall map：菜檯／廚房門洞／玻璃門／南牆／桌凳 逐一配到西北東南牆，並寫「本鏡在畫面哪裡」（R1＋R2 本機位畫面左右）
    武戲另含打鬥後場景狀態（兩張側倒桌位置、碎盤、隔間牆破洞）——第一批揭盲後 2026-10-28 00:00 老大指示加入
  2 本鏡專屬的一句否定（不新增門窗），寫成本鏡看得到的那面牆（每鏡不同，避開 E33 跨段套句；每鏡 ≤1 句，避開 E35）
  3 Directions：機位世界朝向＋人物世界朝向／自身左右＋主光世界位置在本機位的畫面方向（R2、R3）
  4 第 2 鏡起：camera-view 配對句（同一時刻、同一側、只收緊不新增機位、不鏡像不換位）
文戲：前置到五小節 camera；武戲：插在每個 [Shot N] 的 `Camera:` 前。不刪改原稿任何字。
字元預算：hosted API 硬上限 7000 字元（audit_refs_and_segments.HARD_CHAR_LIMIT）→ 每鏡約 400–550 字元。"""

WM = ("Wall map: the counter is only on the west wall{w}; the one open, glassless kitchen doorway is only in the north "
      "partition, west of centre{d}; the glass door and all glass are only in the east wall{e}; plain south wall; seven "
      "pale-stone tables with steel stools{t}.")
# 武戲：打鬥後狀態（EP05 blocking.md §1：破洞 x4.0–4.8＝門洞東側；側倒桌＝店中央一張、門邊一張；碎盤）
POST = "{t}, two on their sides (mid-room and by the door), broken plates on the tiles, a ragged hole in the partition east of the doorway"

SHOTS = {
 ("EP90-S01-a", 1): dict(w=", off to frame left", d=", far back", e=", the frame-right third here", t="",
    neg="No glass appears in the far partition.",
    own="The camera is south, facing north-east; Shen Luonian walks west toward frame left, the warm streetlight from the east glass behind him.",
    pair=None),
 ("EP90-S01-a", 2): dict(w=", frame left here", d=", soft behind the cook", e=", off-screen right", t="",
    neg="No window opens behind the counter.",
    own="The camera faces north-west; the cook faces east into the room, so the door and its warm glow are toward frame right.",
    pair="Same moment as the door shutting, same south side, the room unmirrored."),
 ("EP90-S01-b", 1): dict(w=", its north end at the left edge", d=", at the right third here", e=", off-screen right",
    t=", the corner table being the only one between the counter's north end and the doorway",
    neg="No door fills the doorway.",
    own="The camera is south, facing north; Shen Luonian ends facing south-west with his back to the partition, the doorway on his own left, frame right; warm light comes only from the east, off frame right.",
    pair=None),
 ("EP90-S01-b", 2): dict(w=", frame left here", d=", back right", e=", off-screen right", t=", the corner table off-screen back right, west of the doorway",
    neg="No window appears behind the soup pot.",
    own="The camera faces north-west; the cook faces east, so his glance at the corner table goes toward frame right.",
    pair="It follows the instant Shen Luonian sits in Shot 1, from the same south side, the cook keeping his place."),
 ("EP90-S01-c", 1): dict(w=", its north end at the left edge", d=", at the frame-right edge here", e=", far off-screen right and unseen", t="",
    neg="No glass or street appears in that doorway.",
    own="The camera is south, facing north; Shen Luonian faces south-west, the partition behind him; the cook stands on the table's west side, Shen Luonian's own right and frame left; warm light comes only from the east, off frame right.",
    pair=None),
 ("EP90-S01-c", 2): dict(w=", off-screen left", d=", just off the right edge", e=", off-screen right", t=", the bowl on the corner table",
    neg="No door or glass sits behind his head.",
    own="Only the soft light-wood partition is behind him; the cook, on his own right, stays at frame left.",
    pair="This close-up is the matching view of the same moment, tightened along Shot 1's direction from the same south side, not a new camera position."),
 ("EP90-S01-d", 1): dict(w=", far off-screen left", d=", far off left", e=", along frame right with the dusk street", t=", the north-east one by the glass at centre",
    neg="No door appears in the white wall behind them.",
    own="The camera is south, facing north-east; the little boy sits on the east stool facing west, frame left, the glass behind him; the mother sits on the north stool; warm light comes only through that east glass.",
    pair=None),
 ("EP90-S01-d", 2): dict(w=", far off-screen left", d=", off-screen left", e=", the blurred glass behind him at frame right", t="",
    neg="No other window appears beyond him.",
    own="He still faces west, so his glance across the room goes toward frame left; the orange glow rims him from frame right.",
    pair="Tightened along Shot 1's direction as his mother's line ends, same south side."),
 # ---- 武戲（EP05 S02-b～d 原稿不動，只加句）
 ("EP91-S02-b", 1): dict(w=", off left", d=", back left", e=", beyond Shen Luonian at frame right", t="",
    neg="No door appears in the back wall.",
    own="The camera is south, facing north; the rat faces east, frame right; Shen Luonian faces west, his back to the east door.",
    pair=None),
 ("EP91-S02-b", 2): dict(w=", off-screen left", d=", soft behind", e=", off-screen right", t="",
    neg="No window appears behind the rat's head.",
    own="The rat's head comes from the west, frame left, toward Shen Luonian on the east side.",
    pair="Same leap, same south side."),
 ("EP91-S02-b", 3): dict(w=", off-screen left", d=", soft behind him", e=", warm behind him toward frame right", t="",
    neg="No glass appears on his left.",
    own="He still faces west, so the sliding rat is toward frame left.",
    pair="It tightens on him from the same south side."),
 ("EP91-S02-c", 1): dict(w=", its stainless front beyond the rat toward frame left", d=", across the back beyond the tail", e=", off-screen right",
    t=", several standing beyond the rat at floor level",
    neg="No plain studio backdrop replaces the room behind the rat.",
    own="The camera is low on the south side, facing north; the rat faces east toward frame right.",
    pair=None),
 ("EP91-S02-c", 2): dict(w=", off-screen left", d=", in the background", e=", behind him toward frame right", t="",
    neg="No door appears on his left.",
    own="Shen Luonian faces west toward the rat, frame left, and backs east toward frame right; his own right side is the far side.",
    pair="It picks up as the rat lowers its head in Shot 1, same south side."),
 ("EP91-S02-c", 3): dict(w=", off-screen left", d=", off-screen behind", e=", just beyond the table at frame right", t="",
    neg="No other table blocks his heel.",
    own="His right heel moves east, from frame left toward frame right, into the overturned table by the door.",
    pair="It tightens to his heel along Shot 2's direction, same backward step."),
 ("EP91-S02-d", 1): dict(w=", off left", d=", back left", e=", behind Shen Luonian at frame right", t="",
    neg="No door appears in the partition beside the hole.",
    own="The camera is south, facing north; the rat leaps east toward the door side, frame right, while Shen Luonian lunges north-west, deeper into the room toward frame left and away from the glass door.",
    pair=None),
 ("EP91-S02-d", 2): dict(w=", off-screen left", d=", soft behind", e=", off-screen right", t="",
    neg="No window appears behind the contact point.",
    own="The claw comes from the west, frame left; the rebound drives Shen Luonian deeper into the room, away from the door.",
    pair="Same instant of contact, same south side."),
 ("EP91-S02-d", 3): dict(w=", off-screen left", d=", back left where he is flung", e=", off-screen right", t="",
    neg="No glass appears in the back of the room.",
    own="The tail comes from the west, frame left; Shen Luonian is flung north-west toward the partition on frame left, away from the glass door.",
    pair="It follows the rebound from Shot 2, same south side."),
}


def camera_prefix(seg_id, n, combat=False):
    s = SHOTS[(seg_id, n)]
    t = POST.format(t=s["t"]) if combat else s["t"]
    parts = [WM.format(w=s["w"], d=s["d"], e=s["e"], t=t), s["neg"], s["own"]]
    if s["pair"]:
        parts.append(s["pair"])
    return " ".join(parts)
