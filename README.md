# Oracle_ the DOTA2 Analyst Tool

A comprehensive match analysis and management tool designed for professional DOTA2 team coaches.

## Features

*   **Match Data Capture**: 
    *   Batch fetch matches by Team or League via OpenDota API.
    *   Single match fetch by Match ID.
    *   Manual entry for Scrims (Training matches) with full BP (Ban/Pick) support.
*   **Tactical Analysis**:
    *   **Team Overview**: Win rates (Radiant/Dire), Most Picked/Banned heroes.
    *   **Player Pool**: Automatic detection of main players per position (1-5) and their hero win rates.
    *   **BP Chain**: Visualized Ban/Pick timeline for recent matches, filtering by opponent.
*   **Management**:
    *   **Player Management**: Alias linking (multiple accounts -> one player), position tracking.
    *   **Patch Management**: Auto-sync with official Dota 2 patches.
    *   **Hero Management**: Support for custom hero slang/names.

## Installation

1.  **Clone the repository**:
    ```bash
    git clone <repository-url>
    cd dota2_analyst_tool
    ```

2.  **Install dependencies**:
    ```bash
    pip install -r requirements.txt
    ```

3.  **Configuration**:
    *   Create a secrets file for Streamlit:
        ```bash
        mkdir .streamlit
        cp secrets.toml.example .streamlit/secrets.toml
        ```
    *   Edit `.streamlit/secrets.toml` if you have an OpenDota API Key (optional but recommended for higher rate limits).

4.  **Initialize Database**:
    *   The SQLite database (`dota2_analyst.db`) will be automatically created on the first run.

## Usage

1.  **Run the application**:
    ```bash
    streamlit run main.py
    ```

2.  **First-time Setup**:
    *   Go to **系统设置 (Settings)** to sync initial Team and League data.
    *   Go to **版本管理 (Patches)** -> click **"🔄 从官方 API 同步版本"** to populate patch data.

3.  **Scripts**:
    *   Update Patch Data via CLI:
        ```bash
        python scripts/update_patches.py
        ```

## Structure

*   `main.py`: Entry point.
*   `views/`: UI components (Streamlit pages).
*   `services/`: Business logic (API client, Data processing, Managers).
*   `models.py`: Database schema (SQLAlchemy).
*   `data/`: JSON storage for Heroes and Patches.

## License

[MIT](LICENSE)

