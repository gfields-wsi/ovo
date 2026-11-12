from PIL import Image, ImageDraw, ImageFont
import textwrap

W, H = 1800, 2700
BG = (242, 242, 240)
img = Image.new("RGB", (W, H), BG)
d = ImageDraw.Draw(img)

def font(size, bold=False):
    # DejaVu is available on most Linux VMs
    paths = ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]
    try:
        return ImageFont.truetype(paths[0], size)
    except Exception:
        return ImageFont.load_default()

def rounded_box(x, y, w, h, fill, outline=None, radius=28):
    d.rounded_rectangle([x, y, x+w, y+h], radius=radius, fill=fill, outline=outline, width=2 if outline else 1)

def wrap_text(text, fnt, max_w):
    words = text.split()
    lines, cur = [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if d.textlength(t, font=fnt) <= max_w:
            cur = t
        else:
            lines.append(cur); cur = w
    if cur: lines.append(cur)
    return lines

def draw_text_centered(cx, y, text, fnt, color=(30,30,30), max_w=240, line_h=30):
    lines = wrap_text(text, fnt, max_w)
    for i, line in enumerate(lines):
        tw = d.textlength(line, font=fnt)
        d.text((cx - tw/2, y + i*line_h), line, font=fnt, fill=color)
    return len(lines)

# Title
d.text((100, 70), "OvO Payment Bridge", font=font(52, True), fill=(20,20,20))
d.text((100, 140), "Agent-to-Agent Checkout, Programmatic Only, No Browser Step", font=font(32), fill=(60,60,60))

cols = ["User", "Muse Agent", "Merchant", "OvO Bridge", "Stripe"]
col_x = [200, 550, 900, 1250, 1600]  # centers
# vertical lines
for cx in col_x:
    d.line([(cx, 300), (cx, 2150)], fill=(200,200,198), width=3)
# headers: black pills
for cx, label in zip(col_x, cols):
    f = font(28, True)
    tw = d.textlength(label, font=f) + 48
    x = cx - tw/2
    rounded_box(x, 240, tw, 58, (0,0,0), radius=29)
    d.text((cx - d.textlength(label, font=f)/2, 255), label, font=f, fill=(255,255,255))

steps = [
    (0, "User asks Muse agent to buy a product"),
    (1, "Agent creates a cart, from the purchase request"),
    (2, "Merchant calculates total, tax, shipping, and locks quote"),
    (1, "Agent creates a Link spend request, amount = merchant total"),
    (3, "Bridge checks network id, agent authorization, merchant approval"),
    (0, "User approves in the Link app, within 30 minutes"),
    (3, "Link issues SPT, single use, merchant scoped, amount limited"),
    (1, "Agent sends SPT, programmatic only, no card data, no browser"),
    (2, "Merchant creates PaymentIntent with SPT, own Stripe account"),
    (4, "Stripe charges, through merchant account"),
    (2, "Merchant creates paid Woo order, only after Stripe confirms"),
]

y = 360
prev_cx, prev_y = None, None
box_w, box_h = 280, 150
for i, (ci, text) in enumerate(steps):
    cx = col_x[ci]
    x = cx - box_w/2
    # arrow from previous box to this box
    if prev_cx is not None:
        # vertical down from prev, then horizontal to new center, then down into box
        mid_y = y - 18
        d.line([(prev_cx, prev_y), (prev_cx, mid_y)], fill=(130,130,130), width=3)
        d.line([(prev_cx, mid_y), (cx, mid_y)], fill=(130,130,130), width=3)
        d.line([(cx, mid_y), (cx, y)], fill=(130,130,130), width=3)
        # arrowhead
        d.polygon([(cx-9, y-12), (cx+9, y-12), (cx, y)], fill=(130,130,130))
    rounded_box(x, y, box_w, box_h, (255,255,255), outline=(210,210,208), radius=24)
    # step number
    d.text((x+18, y+12), f"{i+1}", font=font(24, True), fill=(120,120,120))
    f = font(23)
    lines = wrap_text(text, f, 240)
    total_h = len(lines)*28
    start_y = y + 28 + (box_h - 28 - total_h)//2
    for j, line in enumerate(lines):
        tw = d.textlength(line, font=f)
        d.text((cx - tw/2, start_y + j*28), line, font=f, fill=(30,30,30))
    prev_cx, prev_y = cx, y + box_h
    y += box_h + 36

# Bottom green checks, like ACP
check_y = y + 20
for cx in col_x:
    # white box with green check
    rounded_box(cx-42, check_y, 84, 84, (255,255,255), outline=(210,210,208), radius=20)
    # green circle
    d.ellipse([cx-22, check_y+22, cx+22, check_y+66], fill=(30,200,80))
    f = font(30, True)
    d.text((cx - d.textlength("✓", font=f)/2, check_y+28), "✓", font=f, fill=(255,255,255))
    # arrow back to user check? draw line from each to previous, like ACP
for i in range(len(col_x)-1, 0, -1):
    d.line([(col_x[i]-42, check_y+42), (col_x[i-1]+42, check_y+42)], fill=(160,160,160), width=3)
    d.polygon([(col_x[i-1]+42, check_y+42), (col_x[i-1]+58, check_y+34), (col_x[i-1]+58, check_y+50)], fill=(160,160,160))

# Footer note
fy = check_y + 130
note = "Failure fails closed: declined, stock gone, quote void, or reused token creates no paid order.  Card data is never collected, stored, or sent by OvO."
f = font(26)
lines = wrap_text(note, f, 1600)
for j, line in enumerate(lines):
    tw = d.textlength(line, font=f)
    d.text(((W-tw)/2, fy + j*34), line, font=f, fill=(80,80,80))

out = "/home/hatch/workspace/ovo-hackathon/ovo-payment-bridge/ovo-payment-bridge-flow.png"
img.save(out)
print(out)
