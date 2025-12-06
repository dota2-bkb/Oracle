import streamlit as st
from PIL import Image, ImageDraw, ImageFont
import requests
from io import BytesIO
import os

# ---------------------------------------------------------
# CONFIGURATION: Coordinates & Sizes
# ---------------------------------------------------------

# Icon Sizes
PICK_SIZE = (183, 105)  # Width, Height
BAN_SIZE = (112, 70)

# X Coordinates (Fixed by Side)
RAD_BAN_X = 120
RAD_PICK_X = 55
DIRE_BAN_X = 416
DIRE_PICK_X = 416

# Y Coordinates & Orders (Based on Sequence)
# Standard DOTA 2 Captain's Mode (7.35+) Order Correction derived from user input:
# FP (First Pick Team) Sequence:
#   Bans: 1, 3, 7, 10, 11, 19, 22
#   Picks: 9, 13, 16, 17, 24
# SP (Second Pick Team) Sequence:
#   Bans: 2, 4, 5, 6, 12, 20, 21
#   Picks: 8, 14, 15, 18, 23

# Y Values provided by User (Mapped to Corrected Orders)
FP_BANS_Y = {
    1: 66.8,
    3: 176,    # User wrote 2, corrected to 3 based on flow
    7: 287,
    10: 498,
    11: 575,
    19: 1007.5,
    22: 1083.3
}

FP_PICKS_Y = {
    9: 377,
    13: 658.5,
    16: 772.1,
    17: 888,
    24: 1166.3
}

SP_BANS_Y = {
    2: 66.8,
    4: 141.5,  # User wrote 3, corrected to 4
    5: 219.2,
    6: 293.2,
    12: 572,
    20: 1007.5,
    21: 1083.3
}

SP_PICKS_Y = {
    8: 377,
    14: 658.5,
    15: 772.1,
    18: 888,
    23: 1166.3
}

def build_coord_map(is_radiant_first):
    """
    Builds the full 1-24 coordinate map (x, y, w, h)
    """
    coords = {}
    
    # Helper to add points
    def add_points(orders_y, x_pos, size, is_pick):
        for order, y in orders_y.items():
            coords[order] = (int(x_pos), int(y), size[0], size[1])

    if is_radiant_first:
        # Radiant is First Pick (FP)
        add_points(FP_BANS_Y, RAD_BAN_X, BAN_SIZE, False)
        # Note: SP_PICKS_Y contains order 8 (1st pick), so it belongs to FP team
        add_points(SP_PICKS_Y, RAD_PICK_X, PICK_SIZE, True)
        
        # Dire is Second Pick (SP)
        add_points(SP_BANS_Y, DIRE_BAN_X, BAN_SIZE, False)
        # Note: FP_PICKS_Y contains order 9 (2nd pick), so it belongs to SP team
        add_points(FP_PICKS_Y, DIRE_PICK_X, PICK_SIZE, True)
    else:
        # Dire is First Pick (FP)
        add_points(FP_BANS_Y, DIRE_BAN_X, BAN_SIZE, False)
        add_points(SP_PICKS_Y, DIRE_PICK_X, PICK_SIZE, True)
        
        # Radiant is Second Pick (SP)
        add_points(SP_BANS_Y, RAD_BAN_X, BAN_SIZE, False)
        add_points(FP_PICKS_Y, RAD_PICK_X, PICK_SIZE, True)
        
    return coords

# ---------------------------------------------------------

def get_hero_image(hero_data, size=None, is_ban=False):
    """
    Download and cache hero image.
    """
    if not hero_data: return None
    
    hid = hero_data.get('id')
    # Use img_url (Large) usually.
    url = hero_data.get('img_url') 
    if not url: return None
    
    local_path = f"assets/heroes/{hid}.png"
    
    if not os.path.exists("assets/heroes"):
        os.makedirs("assets/heroes", exist_ok=True)
        
    img = None
    if os.path.exists(local_path):
        try:
            img = Image.open(local_path)
            img.load()
        except:
            pass
            
    if not img:
        # Download
        try:
            if not url.startswith("http"):
                url = f"https://api.opendota.com{url}"
                
            resp = requests.get(url, timeout=5)
            if resp.status_code == 200:
                img = Image.open(BytesIO(resp.content))
                img.save(local_path)
        except Exception as e:
            print(f"Failed to download image for hero {hid}: {e}")
            return None

    if img:
        if size: 
            img = img.resize(size)
        
        # FIX: Ensure RGBA mode before any further processing to avoid bad transparency mask error
        if img.mode != 'RGBA':
            img = img.convert('RGBA')

        if is_ban:
            # Grayscale for bans
            # Convert to L (grayscale) then back to RGBA to keep alpha but lose color
            # Extract alpha
            alpha = img.split()[3]
            img = img.convert('L').convert('RGB')
            # Put alpha back
            img.putalpha(alpha)
            
        return img
        
    return None

def generate_bp_image(pick_bans, radiant_name, dire_name, hero_manager, first_pick_radiant=True):
    """
    Generate the BP image using the template.
    """
    # Select Template
    template_path = "assets/bp_template_RF.png" if first_pick_radiant else "assets/bp_template_DF.png"
    
    if not os.path.exists(template_path):
        return None 

    try:
        template_img = Image.open(template_path).convert("RGBA")
        w, h = template_img.size 
        
        # Create base canvas
        base_img = Image.new("RGBA", (w, h), (20, 23, 26, 255)) # Dark background
        
        # Build Coords for this specific match
        current_coords = build_coord_map(first_pick_radiant)
        
        # Draw Heroes (Underneath Template holes)
        for pb in pick_bans:
            order = pb.order + 1 # 1-based
            
            if order in current_coords:
                x, y, width, height = current_coords[order]
                
                # Get Hero Image
                hero = hero_manager.get_hero(pb.hero_id)
                is_ban = not pb.is_pick
                
                h_img = get_hero_image(hero, size=(width, height), is_ban=is_ban)
                
                if h_img:
                    # FIX: Paste with mask only if image has alpha.
                    # h_img is guaranteed RGBA by get_hero_image fix.
                    base_img.paste(h_img, (x, y), h_img)

        # Paste Template ON TOP
        base_img.paste(template_img, (0, 0), template_img)
        
        # Draw Names (On Top of Template)
        draw_top = ImageDraw.Draw(base_img)
        try:
            font_size = 30
            try:
                # Try common Chinese fonts
                font_path = "arial.ttf"
                if os.path.exists("msyh.ttc"): font_path = "msyh.ttc"
                elif os.path.exists("simhei.ttf"): font_path = "simhei.ttf"
                
                font = ImageFont.truetype(font_path, font_size)
            except:
                font = ImageFont.load_default()
                
            # Approximate text positions (User didn't specify, keeping previous guess)
            # Assuming centered on top L/R
            draw_top.text((100, 20), radiant_name, fill=(0, 255, 0, 255), font=font)
            draw_top.text((450, 20), dire_name, fill=(255, 0, 0, 255), font=font)
        except:
            pass

        return base_img
        
    except Exception as e:
        print(f"Image Gen Error: {e}")
        return None

def render_bp_visual(pick_bans, radiant_name, dire_name, hero_manager, first_pick_radiant=True, layout="default"):
    """
    Main entry point for UI.
    layout: "default" (top-down) or "side-by-side" (image left, html right)
    """
    img = generate_bp_image(pick_bans, radiant_name, dire_name, hero_manager, first_pick_radiant)
    
    if layout == "side-by-side":
        # Requested: Image scaled to 66% and side-by-side with HTML
        # Originally image width 400. 66% is 264.
        # But user said "shrink to 66%", maybe of original? 
        # Original template is 665px wide. 66% of 665 is ~440px.
        # Previous fixed width was 400. 
        # Let's assume user wants it smaller than before or smaller relative to container?
        # "缩小到原来的66%" -> if original display was 400px, now 266px?
        # Or relative to the 665px template? 0.66 * 665 = 438px.
        # Let's try 300px width for image to be compact.
        
        c1, c2 = st.columns([1, 2]) # Image takes 1/3, HTML takes 2/3
        with c1:
            if img:
                st.image(img, width=250) 
            else:
                st.write("Image N/A")
                
        with c2:
            render_html_strip(pick_bans, radiant_name, dire_name, hero_manager)
            
    else:
        # Default top-down behavior
        if img:
            st.image(img, width=400) 
        
        render_html_strip(pick_bans, radiant_name, dire_name, hero_manager)

def render_html_strip(pick_bans, radiant_name, dire_name, hero_manager):
    """
    Legacy HTML/Streamlit Component rendering
    """
    rad_picks = []
    rad_bans = []
    dire_picks = []
    dire_bans = []
    
    sorted_pbs = sorted(pick_bans, key=lambda x: x.order)
    
    for pb in sorted_pbs:
        item = {
            'hero': hero_manager.get_hero(pb.hero_id),
            'order': pb.order + 1,
            'is_pick': pb.is_pick
        }
        if pb.team_side == 0: # Radiant
            if pb.is_pick: rad_picks.append(item)
            else: rad_bans.append(item)
        else: # Dire
            if pb.is_pick: dire_picks.append(item)
            else: dire_bans.append(item)

    def render_row(label, items, is_ban=False):
        st.caption(label)
        cols = st.columns(12)
        for i, item in enumerate(items):
            if i < 12:
                with cols[i]:
                    h = item['hero']
                    url = h.get('img_url') or h.get('icon_url')
                    st.image(url, width="stretch")
                    st.markdown(f"<div style='text-align:center; font-size:10px;'>#{item['order']}</div>", unsafe_allow_html=True)
    
    render_row(f"🟢 {radiant_name} Picks", rad_picks)
    render_row(f"🚫 {radiant_name} Bans", rad_bans, is_ban=True)
    st.write("")
    render_row(f"🔴 {dire_name} Picks", dire_picks)
    render_row(f"🚫 {dire_name} Bans", dire_bans, is_ban=True)
