import tkinter as tk
import time
import threading

def highlight_click(x, y, duration=1.0):
    print(f"Drawing highlight at {x}, {y}")
    def show():
        try:
            root = tk.Tk()
            root.overrideredirect(True)
            root.attributes('-topmost', True)
            root.attributes('-transparentcolor', 'white')
            # Center the highlight
            size = 100
            root.geometry(f"{size}x{size}+{int(x-size/2)}+{int(y-size/2)}")
            
            canvas = tk.Canvas(root, width=size, height=size, bg='white', highlightthickness=0)
            canvas.pack()
            # Draw concentric red circles/crosshair
            canvas.create_oval(10, 10, size-10, size-10, outline='red', width=4)
            canvas.create_oval(30, 30, size-30, size-30, outline='red', width=2)
            canvas.create_line(size/2, 0, size/2, size, fill='red', width=2)
            canvas.create_line(0, size/2, size, size/2, fill='red', width=2)
            
            root.after(int(duration * 1000), root.destroy)
            root.mainloop()
        except Exception as e:
            print(f"Error in highlight: {e}")

    # Run in main thread for this test to be sure, or separate thread
    t = threading.Thread(target=show)
    t.start()
    t.join()

if __name__ == "__main__":
    import pyautogui
    x, y = pyautogui.position()
    print(f"Current mouse position: {x}, {y}")
    highlight_click(x, y)
