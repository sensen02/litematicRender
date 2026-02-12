import math
import numpy as np
from PIL import Image, ImageDraw
from litemapy import Region, Schematic
from loader import parse_model, get_texture_image
from utils import isometric_projection

def is_transparent(block_id):
    """
    Checks if a block is transparent (should not cull faces of different transparent blocks).
    """
    transparent_keywords = [
        "glass", "ice", "water", "lava", "slime", "honey", "leaves", "beacon", "scaffolding", "spawner"
    ]
    for keyword in transparent_keywords:
        if keyword in block_id:
            return True
    return False

class LitematicRenderer:
    def __init__(self, litematic_path):
        self.schem = Schematic.load(litematic_path)
        self.reg = list(self.schem.regions.values())[0] # Assume single region for now
        self.block_sprites = {} # Cache for rendered block sprites
        
    def render_block_to_sprite(self, block_name, scale=32, visible_faces=None):
        """
        Renders a single block model to an isometric sprite.
        """
        if visible_faces is None:
            visible_faces = ['east', 'south', 'up']
            
        cache_key = (block_name, tuple(sorted(visible_faces)))
        if cache_key in self.block_sprites:
            return self.block_sprites[cache_key]
            
        model = parse_model(block_name)
        if not model:
            return None
            
        # Create a canvas for the sprite
        # Size depends on scale. Standard block is 16x16x16 units.
        # Isometric projection makes it wider/taller.
        w, h = scale * 4, scale * 4
        sprite = Image.new('RGBA', (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(sprite)
        
        elements = model.get('elements', [])
        if not elements:
            # Fallback for blocks without elements (like air or simple cubes if omitted)
            # But standard models usually have elements.
            # If no elements but parent is 'block/cube_all', we might need to handle built-in shapes.
            # For now, let's assume elements exist or we skip.
            pass
            
        # Sort elements? Usually not needed if we draw in order, but for transparency...
        
        # Center of drawing
        cx, cy = w // 2, h // 2
        
        # Iterate elements
        for element in elements:
            from_coord = np.array(element['from']) / 16.0
            to_coord = np.array(element['to']) / 16.0
            
            # Draw faces. For standard isometric (view from +x, +y, +z), we see Up, South, East?
            # Actually standard isometric is usually 45 deg Y rot, 30 deg X rot.
            # We see Top, and two sides (North/East or South/East etc depending on quadrant).
            # Let's assume we see Up, North, East (or similar).
            
            # Faces: up, down, north, south, east, west
            # defined in model.
            
            # We need to project faces.
            
            faces = element.get('faces', {})
            
            # Define render order for painter's algorithm (back to front)
            # If viewing from front-right-top:
            # We see: Up, South, East (assuming Z is South, X is East).
            # So draw: Down, North, West (hidden), then East, South, Up.
            
            render_order = ['east', 'south', 'up'] # Only draw visible faces for optimization?
            # Wait, if the block is not a full cube, we might see others.
            # But for a simple renderer, let's just draw visible ones.
            
            for face_name in render_order:
                if face_name not in faces:
                    continue
                
                if face_name not in visible_faces:
                    continue
                
                face_data = faces[face_name]
                texture_ref = face_data.get('texture', '')
                
                # Resolve texture variables recursively
                while texture_ref.startswith('#'):
                    resolved = model.get('textures', {}).get(texture_ref[1:])
                    if not resolved:
                        print(f"Warning: Could not resolve texture variable {texture_ref} in {block_name}")
                        break
                    texture_ref = resolved
                
                if texture_ref.startswith('#'):
                    # Failed to resolve fully
                    continue

                texture_img = get_texture_image(texture_ref)
                if not texture_img:
                    continue
                
                # Apply tint if needed
                if 'tintindex' in face_data:
                    # Simple hardcoded tint for now (Generic Green)
                    # Ideally this depends on biome and block type
                    tint_color = (145, 189, 89, 255) # Minecraft grass green
                    
                    # Apply tint
                    # Convert to RGBA
                    texture_img = texture_img.convert('RGBA')
                    
                    # Multiply color
                    data = np.array(texture_img)
                    r, g, b, a = data.T
                    
                    # Normalize tint
                    tr, tg, tb, ta = tint_color
                    
                    r = (r * tr // 255).astype(np.uint8)
                    g = (g * tg // 255).astype(np.uint8)
                    b = (b * tb // 255).astype(np.uint8)
                    
                    texture_img = Image.fromarray(np.dstack((r, g, b, a)))

                # Calculate corners of the face
                # This requires knowing which coords correspond to the face
                corners_3d = self.get_face_corners(from_coord, to_coord, face_name)
                
                # Project to 2D
                corners_2d = []
                for x, y, z in corners_3d:
                    ix, iy = isometric_projection(x, y, z, scale=scale)
                    corners_2d.append((cx + ix, cy - iy)) # Invert Y for image coords
                
                # Draw texture mapped to quad
                self.draw_textured_face(sprite, texture_img, corners_2d)
                
        self.block_sprites[cache_key] = sprite
        return sprite

    def draw_textured_face(self, canvas, texture, corners):
        """
        Warps the texture to the quad defined by corners and pastes it onto the canvas.
        corners: [(x0, y0), (x1, y1), (x2, y2), (x3, y3)] (TL, TR, BR, BL)
        """
        # Create a mask for the polygon
        w, h = canvas.size
        mask = Image.new('L', (w, h), 0)
        draw = ImageDraw.Draw(mask)
        draw.polygon(corners, fill=255)
        
        # Calculate affine transform to map texture to quad
        # We want to map texture (0,0)->TL, (w,0)->TR, (0,h)->BL
        # Destination points
        (x0, y0), (x1, y1), (x2, y2), (x3, y3) = corners
        
        tw, th = texture.size
        
        # Solve for affine coefficients
        # x = a*u + b*v + c
        # y = d*u + e*v + f
        # Wait, PIL transform takes inverse matrix: u = a*x + b*y + c...
        
        # We need to map destination (x,y) to source (u,v)
        # Using 3 points: TL(x0,y0)->(0,0), TR(x1,y1)->(tw,0), BL(x3,y3)->(0,th)
        
        dx1 = x1 - x0
        dy1 = y1 - y0
        dx2 = x3 - x0
        dy2 = y3 - y0
        
        det = dx1 * dy2 - dx2 * dy1
        
        if abs(det) < 1e-6:
            return # Degenerate
            
        a = (tw * dy2) / det
        b = (-tw * dx2) / det
        c = -a * x0 - b * y0
        
        d = (-th * dy1) / det
        e = (th * dx1) / det
        f = -d * x0 - e * y0
        
        data = (a, b, c, d, e, f)
        
        # Transform texture to canvas size
        try:
            transformed = texture.transform((w, h), Image.AFFINE, data, resample=Image.NEAREST)
            
            # Paste using mask
            canvas.paste(transformed, (0, 0), mask)
        except Exception as e:
            print(f"Error transforming texture: {e}")

    def get_face_corners(self, p1, p2, face):
        x1, y1, z1 = p1
        x2, y2, z2 = p2
        # p1 is min (from), p2 is max (to)
        
        # Define corners for each face (CCW or CW?)
        if face == 'up':
            return [(x1, y2, z1), (x2, y2, z1), (x2, y2, z2), (x1, y2, z2)]
        elif face == 'down':
            return [(x1, y1, z1), (x2, y1, z1), (x2, y1, z2), (x1, y1, z2)]
        elif face == 'north': # -Z
            return [(x2, y2, z1), (x1, y2, z1), (x1, y1, z1), (x2, y1, z1)]
        elif face == 'south': # +Z
            return [(x1, y2, z2), (x2, y2, z2), (x2, y1, z2), (x1, y1, z2)]
        elif face == 'east': # +X
            return [(x2, y2, z2), (x2, y2, z1), (x2, y1, z1), (x2, y1, z2)]
        elif face == 'west': # -X
            return [(x1, y2, z1), (x1, y2, z2), (x1, y1, z2), (x1, y1, z1)]
        return []

    def render(self, output_path):
        # Determine bounds
        min_x, max_x = self.reg.min_x(), self.reg.max_x()
        min_y, max_y = self.reg.min_y(), self.reg.max_y()
        min_z, max_z = self.reg.min_z(), self.reg.max_z()
        
        # Calculate canvas size (rough estimate)
        scale = 32
        # Isometric width approx: (dx + dz) * scale
        # Height: (dy + (dx+dz)/2) * scale
        
        # Create large canvas
        canvas_width = 2000
        canvas_height = 2000
        canvas = Image.new('RGBA', (canvas_width, canvas_height), (0, 0, 0, 0))
        
        # Center
        cx, cy = canvas_width // 2, canvas_height // 2
        
        # Iterate blocks
        # Order: Back to Front, Bottom to Top.
        # X, Z, Y
        # For isometric: 
        # Furthest is min_x, min_z (or max, depending on rotation).
        # We want to draw the blocks that are "behind" first.
        
        # Loop x, y, z
        for y in range(min_y, max_y + 1):
            for z in range(min_z, max_z + 1):
                for x in range(min_x, max_x + 1):
                    try:
                        block = self.reg.getblock(x, y, z)
                        if block.id == "minecraft:air":
                            continue
                        
                        visible_faces = ['east', 'south', 'up']
                        
                        # Face Culling
                        # Check East (+X)
                        if x + 1 <= max_x:
                            try:
                                neighbor = self.reg.getblock(x+1, y, z)
                                if neighbor.id != "minecraft:air":
                                    if is_transparent(block.id):
                                        if neighbor.id == block.id:
                                            visible_faces.remove('east')
                                    elif not is_transparent(neighbor.id):
                                        visible_faces.remove('east')
                            except: pass

                        # Check South (+Z)
                        if z + 1 <= max_z:
                            try:
                                neighbor = self.reg.getblock(x, y, z+1)
                                if neighbor.id != "minecraft:air":
                                    if is_transparent(block.id):
                                        if neighbor.id == block.id:
                                            visible_faces.remove('south')
                                    elif not is_transparent(neighbor.id):
                                        visible_faces.remove('south')
                            except: pass
                            
                        # Check Up (+Y)
                        if y + 1 <= max_y:
                            try:
                                neighbor = self.reg.getblock(x, y+1, z)
                                if neighbor.id != "minecraft:air":
                                    if is_transparent(block.id):
                                        if neighbor.id == block.id:
                                            visible_faces.remove('up')
                                    elif not is_transparent(neighbor.id):
                                        visible_faces.remove('up')
                            except: pass
                            
                        sprite = self.render_block_to_sprite(block.id, scale=scale, visible_faces=visible_faces)
                        if sprite:
                            # Calculate position
                            ix, iy = isometric_projection(x, y, z, scale=scale)
                            
                            # Center on canvas
                            px = int(cx + ix - sprite.width // 2)
                            py = int(cy - iy - sprite.height // 2) # Invert Y because y increases upwards in world but downwards in image
                            
                            # Paste (using alpha channel as mask)
                            canvas.paste(sprite, (px, py), sprite)
                    except Exception as e:
                        print(f"Error processing block at {x},{y},{z}: {e}")
                        import traceback
                        traceback.print_exc()
        
        # Crop to content
        bbox = canvas.getbbox()
        if bbox:
            canvas = canvas.crop(bbox)
            
        canvas.save(output_path)
        print(f"Render saved to {output_path}")

