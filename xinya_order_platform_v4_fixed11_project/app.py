
# app.py
# ================================================================
# 这是一个 Streamlit 应用示例。
# 功能：在侧边栏切换 “Commander” / “Admin” 页面，
#       检查产品 ID 是否重复并修复，检查邮件配置状态。
# ================================================================

# 导入 Streamlit 库，用于搭建网页应用。
# st 是常用别名，所有页面控件、布局函数都通过 st 调用。
import streamlit as st

# 从项目配置模块导入一个检查函数：email_config_ok
# 作用：检查邮件发送配置是否正确（例如 EMAIL_USER / EMAIL_PASS 是否已设置）。
from xinya_app.config import email_config_ok

# 导入一个工具函数：fix_duplicate_product_ids_file
# 作用：扫描存放商品信息的数据文件，检查并修复重复的 product_id。
# 返回值通常是 (changed, cnt)
#   - changed: 布尔值，是否真的修复过
#   - cnt:     被修改 / 修复的数量
from xinya_app.ids import fix_duplicate_product_ids_file

# 导入前端渲染函数：客户下单页面
from xinya_app.ui_client import render_client_page

# 导入前端渲染函数：后台管理页面
from xinya_app.ui_admin import render_admin_page


# 设置页面的基本属性。
# 必须是脚本的第一条 Streamlit 命令，否则会报错：
# "set_page_config() can only be called once, and must be the first Streamlit command".
st.set_page_config(page_title="Xinya | Commandes", layout="wide")


# 在侧边栏创建一个单选按钮（radio），用户可以切换不同页面。
# 参数：
#   - "Pages d'accueil"：标题文字
#   - ["Commander", "Admin"]：两个选项
#   - index=0：默认选中第一个 ("Commander")
tab = st.sidebar.radio("Pages d'accueil", ["Commander", "Admin"], index=0)


# 调用函数检查并修复重复的产品 ID。
# 返回 changed (是否有修复) 和 cnt (修复了多少个)。
changed, cnt = fix_duplicate_product_ids_file()

# 如果确实做了修改，就在侧边栏提示一个警告信息。
if changed:
    st.sidebar.warning(f"⚠️ IDs produits dupliqués corrigés automatiquement：{cnt} modifiés.")


# 检查邮件配置是否已完成。
# email_config_ok() 如果返回 False，说明还没配置邮箱信息。
if not email_config_ok():
    st.sidebar.warning(
        "⚠️ Envoi d'e-mails non configuré. "
        "Copiez `.env.example` → `.env`, remplissez EMAIL_USER et EMAIL_PASS."
    )
else:
    st.sidebar.success("📧 E-mails configurés.")


# 根据侧边栏的 tab 值来决定渲染哪一个页面。
if tab == "Commander":
    # 渲染客户端下单页面。
    render_client_page()
else:
    # 渲染后台管理页面。
    render_admin_page()
