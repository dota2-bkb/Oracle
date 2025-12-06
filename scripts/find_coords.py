import matplotlib.pyplot as plt
import matplotlib.image as mpimg
import os

def show_image_with_coords(image_path):
    if not os.path.exists(image_path):
        print(f"Error: File not found at {image_path}")
        # Try to find any png in assets to help user
        if os.path.exists("assets"):
            print("Files in assets/:")
            for f in os.listdir("assets"):
                print(f" - {f}")
        return

    img = mpimg.imread(image_path)
    
    fig, ax = plt.subplots(figsize=(10, 18)) # Portrait aspect ratio
    ax.imshow(img)
    
    ax.set_title(f"Coordinate Finder: {os.path.basename(image_path)}\nHover mouse to see x, y coordinates at bottom right")
    
    # Enable grid for easier alignment estimation
    ax.grid(True, which='both', color='r', linestyle='-', linewidth=0.5, alpha=0.3)
    ax.minorticks_on()
    
    plt.show()

if __name__ == "__main__":
    # Check for templates
    rf_path = "assets/bp_template_RF.png"
    df_path = "assets/bp_template_DF.png"
    
    print("Starting Coordinate Finder...")
    
    if os.path.exists(rf_path):
        print(f"Opening {rf_path}...")
        show_image_with_coords(rf_path)
    elif os.path.exists(df_path):
        print(f"Opening {df_path}...")
        show_image_with_coords(df_path)
    else:
        print("No template files found in assets/.")
        print("Please ensure 'bp_template_RF.png' and 'bp_template_DF.png' are in 'assets/' folder.")

