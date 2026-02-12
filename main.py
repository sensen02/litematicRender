import os
import argparse
import glob
from renderer import LitematicRenderer

def process_file(input_path, output_path):
    print(f"Rendering {input_path} -> {output_path}...")
    try:
        renderer = LitematicRenderer(input_path)
        renderer.render(output_path)
        print("Done.")
    except Exception as e:
        print(f"Failed to render {input_path}: {e}")
        import traceback
        traceback.print_exc()

def main():
    parser = argparse.ArgumentParser(description="Render litematic files to isometric images.")
    parser.add_argument("input", nargs='?', default=".", help="Path to input .litematic file or directory containing them (default: current directory)")
    parser.add_argument("-o", "--output", help="Path to output .png file (only used for single file input)", default=None)
    
    args = parser.parse_args()
    
    input_path = args.input
    
    if os.path.isdir(input_path):
        # Batch mode
        search_path = os.path.join(input_path, "*.litematic")
        files = glob.glob(search_path)
        
        if not files:
            print(f"No .litematic files found in {input_path}")
            return
            
        # Create res directory
        res_dir = os.path.join(input_path, "res")
        if not os.path.exists(res_dir):
            os.makedirs(res_dir)
            print(f"Created output directory: {res_dir}")
            
        print(f"Found {len(files)} files to render.")
        
        for file_path in files:
            file_name = os.path.basename(file_path)
            output_name = os.path.splitext(file_name)[0] + ".png"
            output_path = os.path.join(res_dir, output_name)
            
            process_file(file_path, output_path)
            
    elif os.path.isfile(input_path):
        # Single file mode
        if not args.output:
            # Check if we want to enforce res folder for single file too?
            # User said "automatically scan... output to new res folder".
            # For single file, maybe just stick to old behavior or put in res?
            # Let's keep old behavior for explicit single file unless output is specified.
            output_path = os.path.splitext(input_path)[0] + ".png"
        else:
            output_path = args.output
            
        process_file(input_path, output_path)
    else:
        print(f"Error: Input {input_path} not found.")

if __name__ == "__main__":
    main()
