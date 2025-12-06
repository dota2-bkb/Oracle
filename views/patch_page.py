import streamlit as st
from services.patch_manager import PatchManager

def show():
    st.title("版本管理 / Patch Manager")
    
    pm = PatchManager()
    
    st.write("在此处管理 Dota 2 版本号及其对应的起始时间。")
    
    # Auto Update Section
    col_auto, col_manual = st.columns([1, 2])
    
    with col_auto:
        st.subheader("自动更新")
        if st.button("🔄 从官方 API 同步版本", type="primary"):
            with st.spinner("正在连接 OpenDota API..."):
                try:
                    count = pm.update_from_api()
                    if count > 0:
                        st.success(f"成功同步！更新了 {count} 个版本信息。")
                        st.rerun()
                    else:
                        st.info("版本库已是最新。")
                except Exception as e:
                    st.error(f"更新失败: {e}")

    # Manual Update Section
    with col_manual:
        st.subheader("手动添加/修改")
        with st.form("add_patch"):
            c1, c2 = st.columns(2)
            new_name = c1.text_input("版本号 (如 7.37d)")
            new_date = c2.date_input("起始日期")
            
            if st.form_submit_button("保存"):
                if new_name:
                    pm.save_patch(new_name, str(new_date))
                    st.success(f"已保存版本 {new_name}")
                    st.rerun()
                else:
                    st.error("请输入版本号")
    
    st.divider()

    # List Existing
    st.subheader("已有版本列表")
    patches = pm.patches
    
    # Convert to list for dataframe
    data = []
    for name, info in patches.items():
        data.append({"Patch": name, "Start Date": info['start_date']})
        
    # Sort desc by date
    data.sort(key=lambda x: x['Start Date'], reverse=True)
    
    st.dataframe(data, use_container_width=True)
