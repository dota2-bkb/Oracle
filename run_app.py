import streamlit.web.cli as stcli
import os, sys
import shutil
import time
import webbrowser
import threading

def resolve_path(path):
    if getattr(sys, 'frozen', False):
        basedir = sys._MEIPASS
    else:
        basedir = os.path.dirname(__file__)
    return os.path.join(basedir, path)

def open_browser():
    """Wait for server to start and then open browser"""
    print("等待服务启动...")
    time.sleep(3) # Give Streamlit a moment to start
    url = "http://localhost:8501"
    print(f"正在尝试打开浏览器: {url}")
    try:
        webbrowser.open(url)
    except Exception as e:
        print(f"自动打开浏览器失败: {e}")
        print(f"请手动访问: {url}")

if __name__ == "__main__":
    print("正在初始化程序...")
    
    # Ensure CWD is set to the directory of the executable for persistence
    if getattr(sys, 'frozen', False):
        # sys.executable is the full path to the .exe
        # We want the directory containing the .exe
        exe_dir = os.path.dirname(sys.executable)
        os.chdir(exe_dir)
        print(f"工作目录已设置为: {exe_dir}")
        
        # Initialize 'data' folder (copy from bundle to local if not exists)
        bundle_data = resolve_path("data")
        local_data = os.path.join(exe_dir, "data")
        
        if not os.path.exists(local_data) and os.path.exists(bundle_data):
            try:
                shutil.copytree(bundle_data, local_data)
                print(f"Initialized data directory at {local_data}")
            except Exception as e:
                print(f"Error copying initial data: {e}")

        # Initialize 'assets' folder (copy from bundle to local if not exists)
        bundle_assets = resolve_path("assets")
        local_assets = os.path.join(exe_dir, "assets")
        
        if not os.path.exists(local_assets) and os.path.exists(bundle_assets):
             try:
                shutil.copytree(bundle_assets, local_assets)
                print(f"Initialized assets directory at {local_assets}")
             except Exception as e:
                print(f"Error copying initial assets: {e}")
        
        # Ensure .streamlit directory exists if needed for config?
        # Usually streamlit looks in user home or project root.
        # We can set config via args or environment vars.
    
    main_script = resolve_path("main.py")
    
    # Streamlit Arguments
    sys.argv = [
        "streamlit",
        "run",
        main_script,
        "--global.developmentMode=false",
        "--server.headless=true", # Set headless=true so we can control browser opening manually if needed, or false to let st do it.
        # Issue with st.run in frozen env: it might not auto-open correctly.
        # Let's try headless=true and use webbrowser module manually in a thread.
        "--server.port=8501",
    ]
    
    print("正在启动 Streamlit 服务...")
    print("提示: 如果程序卡住，请不要关闭此窗口。关闭此窗口将停止服务。")
    print("---------------------------------------------------------")
    
    # Start browser opener in background
    threading.Thread(target=open_browser, daemon=True).start()
    
    # Run Streamlit
    try:
        sys.exit(stcli.main())
    except Exception as e:
        print(f"程序运行出错: {e}")
        input("按回车键退出...")

