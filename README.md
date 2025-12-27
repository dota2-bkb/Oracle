# Oracle: DOTA2 战队数据分析平台 (Oracle - The DOTA2 Analyst Tool)

这是一个专为 DOTA2 职业战队教练和分析师设计的比赛分析与管理工具。

---

## 📖 零基础安装与使用指南

如果你刚刚安装了 Git 和 Python，请按照以下步骤一步步操作。

### 第一步：准备工作

确保你的电脑上已经安装了以下软件：
1.  **Git**: [点击下载 Git](https://git-scm.com/downloads) (安装时一直点下一步即可)
2.  **Python**: [点击下载 Python](https://www.python.org/downloads/) (建议版本 3.10 或以上，**安装时务必勾选 "Add Python to PATH"**)

### 第二步：下载代码 (Clone)

1.  在你的电脑上，找到你想要存放项目的文件夹（例如 D盘）。
2.  在文件夹空白处右键，选择 **"Open Git Bash here"** (或者在地址栏输入 `cmd` 回车)。
3.  在出现的黑色窗口中，输入以下命令并回车：

```bash
git clone https://github.com/dota2-bkb/Oracle.git
```

4.  下载完成后，进入项目文件夹：

```bash
cd Oracle
```

### 第三步：安装依赖环境

为了不影响你电脑上的其他软件，我们需要创建一个独立的"虚拟环境"。

1.  **创建虚拟环境** (输入命令并回车):
    ```bash
    python -m venv venv
    ```

2.  **激活虚拟环境**:
    *   **Windows**:
        ```bash
        .\venv\Scripts\activate
        ```
    *   **Mac/Linux**:
        ```bash
        source venv/bin/activate
        ```
    *   *成功后，你会看到命令行前面多了一个 `(venv)` 的标志。*

3.  **安装项目所需的库**:
    ```bash
    pip install -r requirements.txt
    ```

### 第四步：配置设置

项目需要一个配置文件来运行。

1.  **创建配置文件夹**:
    ```bash
    mkdir .streamlit
    ```
    *(如果提示文件夹已存在，可以忽略)*

2.  **复制配置文件**:
    *   Windows: `copy secrets.toml.example .streamlit\secrets.toml`
    *   Mac/Linux: `cp secrets.toml.example .streamlit/secrets.toml`

### 第五步：启动软件

一切准备就绪，输入以下命令启动：

```bash
streamlit run main.py
```

如果不自动跳转，请复制终端中显示的地址 (通常是 `http://localhost:8501`) 到浏览器打开。

---

## 🔄 如何更新代码 (Git Pull)

当开发者更新了功能，你需要同步更新本地代码：

1.  打开项目文件夹的终端 (CMD 或 Git Bash)。
2.  输入：
    ```bash
    git pull
    ```
3.  如果提示有依赖更新，再次运行：
    ```bash
    pip install -r requirements.txt
    ```

---

## 🛠️ 功能简介

*   **比赛数据抓取**: 支持 OpenDota API 批量抓取和单场 ID 抓取。
*   **训练赛录入**: 手动录入训练赛 BP 数据。
*   **战术分析**:
    *   **队伍概览**: 胜率、常用英雄、被 Ban 英雄分析。
    *   **英雄池**: 自动分析 1-5 号位选手的绝活英雄。
    *   **BP 链路**: 可视化查看近期比赛的 BP 思路。
*   **版本管理**: 自动同步 DOTA2 官方版本更新。

## 许可证

[MIT License](LICENSE)
