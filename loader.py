import os
import json
import requests
from PIL import Image
from io import BytesIO

ASSETS_BASE_URL = "https://raw.githubusercontent.com/InventivetalentDev/minecraft-assets/1.19.4/assets/minecraft"
# Use a consistent cache directory relative to this file
CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache")

# Manual mapping for blocks that don't have a direct model file
# or use a different name for their model (e.g. state-dependent blocks)
BLOCK_MODEL_MAP = {
    "redstone_wire": "block/redstone_dust_dot",
    "wall_torch": "block/wall_torch", # Just in case
    "fire": "block/fire_floor0",
    "soul_fire": "block/soul_fire_floor0",
    "water": "block/water_still", # Doesn't really have a model, but for consistency
    "lava": "block/lava_still",
    "grass": "block/grass", # Sometimes it's just 'grass', sometimes 'short_grass' in newer versions
    "tall_grass": "block/tall_grass_bottom", # Or top?
}

def ensure_cache_dir():
    if not os.path.exists(CACHE_DIR):
        os.makedirs(CACHE_DIR)

def get_model_file(block_name):
    """
    Fetches the block model JSON from the assets server.
    """
    ensure_cache_dir()
    
    name = block_name.replace("minecraft:", "")
    
    if name.startswith("item/"):
        model_type = "item"
        clean_name = name[5:]
    elif name.startswith("block/"):
        model_type = "block"
        clean_name = name[6:]
    else:
        model_type = "block"
        clean_name = name
    
    # Check cache first (flat cache for now, or structured?)
    # Let's use structure matching the type
    cache_path = os.path.join(CACHE_DIR, model_type, f"{clean_name}.json")
    if os.path.exists(cache_path):
        with open(cache_path, 'r') as f:
            return json.load(f)

    url = f"{ASSETS_BASE_URL}/models/{model_type}/{clean_name}.json"
    print(f"Fetching model: {url}")
    
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        
        # Save to cache
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        with open(cache_path, 'w') as f:
            json.dump(data, f)
            
        return data
    except Exception as e:
        # Don't print error here, let caller handle or retry
        # print(f"Error loading model for {block_name}: {e}")
        return None

def get_texture_image(texture_name):
    """
    Fetches the texture image from the assets server.
    """
    ensure_cache_dir()
    clean_name = texture_name.replace("minecraft:", "")
    
    # Check cache
    # Replace / with _ for flat cache or keep structure?
    # Let's keep structure but sanitize for Windows
    safe_name = clean_name.replace("/", os.sep)
    cache_path = os.path.join(CACHE_DIR, f"{safe_name}.png")
    
    if os.path.exists(cache_path):
        return Image.open(cache_path)

    # If the name doesn't have block/ or item/, and it's not a clear path, 
    # we might need to guess or it's implicitly block/ ?
    # Most references in models are explicit "block/name".
    
    url = f"{ASSETS_BASE_URL}/textures/{clean_name}.png"
    print(f"Fetching texture: {url}")
    
    try:
        response = requests.get(url)
        response.raise_for_status()
        image = Image.open(BytesIO(response.content))
        
        # Save to cache
        # Ensure subdirectory exists if needed
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        image.save(cache_path)
        
        return image
    except Exception as e:
        print(f"Error loading texture {texture_name}: {e}")
        return None

def deep_assign(target, source):
    """
    Recursively merges source into target.
    """
    for key, val in source.items():
        if isinstance(val, dict):
            target.setdefault(key, {})
            deep_assign(target[key], val)
        else:
            target[key] = val
    return target

def parse_model(block_name):
    """
    Parses a model and its parents.
    """
    # Check manual map first
    clean_name = block_name.replace("minecraft:", "")
    if clean_name in BLOCK_MODEL_MAP:
        # print(f"Mapping {block_name} -> {BLOCK_MODEL_MAP[clean_name]}")
        model_data = get_model_file(BLOCK_MODEL_MAP[clean_name])
    else:
        model_data = get_model_file(block_name)
    
    if not model_data:
        # Fallback: if we tried block/name and failed, try item/name
        # Only do this if we were trying a "raw" block name or explicit block/ name
        if not block_name.startswith("item/"):
             clean_name = block_name.replace("minecraft:", "").replace("block/", "")
             # print(f"Fallback: Trying item model for {block_name} -> item/{clean_name}")
             model_data = get_model_file(f"item/{clean_name}")
    
    if not model_data:
        # Check for built-in fallbacks for fluids and signs
        if block_name in ["minecraft:water", "minecraft:lava"]:
             return {
                 "elements": [{
                     "from": [0, 0, 0],
                     "to": [16, 16, 16],
                     "faces": {
                         "up": {"texture": "#all"},
                         "north": {"texture": "#all"},
                         "east": {"texture": "#all"},
                         "south": {"texture": "#all"},
                         "west": {"texture": "#all"},
                         "down": {"texture": "#all"}
                     }
                 }],
                 "textures": {
                     "all": "block/water_still" if block_name == "minecraft:water" else "block/lava_still"
                 }
             }
        
        # Fallback for signs (wall and standing)
        if "_sign" in block_name:
            wood_type = block_name.replace("minecraft:", "").replace("_wall_sign", "").replace("_sign", "")
            # Simple sign board model
            return {
                "elements": [{
                    "from": [0, 4, 0], 
                    "to": [16, 12, 2], 
                    "faces": {
                        "up": {"texture": "#all"},
                        "north": {"texture": "#all"},
                        "east": {"texture": "#all"},
                        "south": {"texture": "#all"},
                        "west": {"texture": "#all"},
                        "down": {"texture": "#all"}
                    }
                }],
                "textures": {
                    "all": f"block/{wood_type}_planks"
                }
            }

        # If still failed, log it
        print(f"Error: Could not load model for {block_name} (tried block and item)")
        return {}

    if 'parent' in model_data:
        parent_model = parse_model(model_data['parent'])
        model_data = deep_assign(parent_model, model_data)
        
    return model_data
