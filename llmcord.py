# main.py
import asyncio
from datetime import datetime as dt
import logging
import discord
import yaml
from utils.llmm.handler import get_msg_nodes,set_msg_nodes
from utils.discords.menu import *
from utils.minigame.utils import game_load_state,game_save_state
import os
import pickle
import signal
# 保持原始配置读取和初始化逻辑
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
intents = discord.Intents.default()
intents.message_content = True
discord_client = discord.Client(intents=intents)
init_menu()

__bot__config_cache__ = None
def get_config(filename="config.yaml"):
    global __bot__config_cache__
    if __bot__config_cache__: return __bot__config_cache__
    with open(filename, "r", encoding="utf-8") as file:
        __bot__config_cache__ = yaml.safe_load(file)
        return __bot__config_cache__


# 消息节点缓存（保持原始设计）
VERSION = "1.0.0"



@discord_client.event
async def on_message(new_msg: discord.Message):
    # 保持原始过滤逻辑
    is_dm = new_msg.channel.type == discord.ChannelType.private

    if (
        not is_dm and discord_client.user not in new_msg.mentions
    ) or new_msg.author.bot:
        return

    # 保持原始权限检查逻辑
    cfg = get_config()

    role_ids = set(role.id for role in getattr(new_msg.author, "roles", ()))
    channel_ids = set(
        filter(
            None,
            (
                new_msg.channel.id,
                getattr(new_msg.channel, "parent_id", None),
                getattr(new_msg.channel, "category_id", None),
            ),
        )
    )
    allow_dms = cfg["allow_dms"]
    permissions = cfg["permissions"]

    (
        (allowed_user_ids, blocked_user_ids),
        (allowed_role_ids, blocked_role_ids),
        (allowed_channel_ids, blocked_channel_ids),
    ) = (
        (perm["allowed_ids"], perm["blocked_ids"])
        for perm in (
            permissions["users"],
            permissions["roles"],
            permissions["channels"],
        )
    )

    allow_all_users = (
        not allowed_user_ids if is_dm else not allowed_user_ids and not allowed_role_ids
    )
    is_good_user = (
        allow_all_users
        or new_msg.author.id in allowed_user_ids
        or any(id in allowed_role_ids for id in role_ids)
    )
    is_bad_user = (
        not is_good_user
        or new_msg.author.id in blocked_user_ids
        or any(id in blocked_role_ids for id in role_ids)
    )

    allow_all_channels = not allowed_channel_ids
    is_good_channel = (
        allow_dms
        if is_dm
        else allow_all_channels or any(id in allowed_channel_ids for id in channel_ids)
    )
    is_bad_channel = not is_good_channel or any(
        id in blocked_channel_ids for id in channel_ids
    )

    if is_bad_user or is_bad_channel:
        return

    # Command Distributor
    # 如果时回复消息则该条件不成立（因为开头不再是at）
    line = new_msg.content.removeprefix(discord_client.user.mention).strip()

    
    if " " in line:
        cmd, params = line.split(" ",1)
    else:
        cmd, params = [line, ""]
    target_menu = get_matched_menus(cmd)
    if isinstance(target_menu, list):
        if len(target_menu) == 0:
            return
        for target in target_menu:
            params = params.strip().split(" ")
            valued_params = {
                "discord_client":discord_client,
                "cfg":cfg
            }
            for i in target["binding_func_args"]:
                if len(params) == 0: raise ValueError("参数不足")
                valued_params[i] = params.pop(0)
            await execute_menu(target, new_msg, **valued_params)
    else:
        if target_menu:
            params = params.strip().split(" ")
            valued_params = {
                "discord_client":discord_client,
                "cfg":cfg
            }
            for i in target_menu.binding_func_args:
                if len(params) == 0: raise ValueError("参数不足")
                valued_params[i] = params.pop(0)
            await execute_menu(target_menu, new_msg, **valued_params)





async def main():
    cfg = get_config()
    if cfg["client_id"]:
        logging.info(
            f'\nBOT INVITE URL:https://discord.com/api/oauth2/authorize?client_id={cfg["client_id"]}&permissions=412317273088&scope=bot'
        )
    discord_client.activity = discord.CustomActivity(
        name=(
            cfg["status_message"][:128]
            if cfg["status_message"]
            else "github.com/jakobdylanc/llmcord"
        )
    )
    await discord_client.start(cfg["bot_token"])


if __name__ == "__main__":
    SAVE_FILE = "msg_nodes.pkl"

    def save_state():
        try:
            game_save_state()
            msg_nodes = get_msg_nodes()
            # 检查对话链长度并修剪
            max_messages = get_config()["max_messages"]
            for key, messages in list(msg_nodes.items()):
                if len(messages) > max_messages:
                    msg_nodes[key] = messages[-max_messages:]

            # 删除超过24小时未更新的对话链
            now = dt.now()
            for key, messages in list(msg_nodes.items()):
                last_timestamp = dt.fromisoformat(messages[-1]["timestamp"])
                if (now - last_timestamp).total_seconds() > 86400:
                    del msg_nodes[key]
            with open(SAVE_FILE, "wb") as f:
                pickle.dump({"version": VERSION, "msg_nodes": msg_nodes}, f)
            logging.info("状态已保存到本地文件")
        except Exception as e:
            logging.error(f"保存状态失败: {str(e)}")

    def load_state():
        game_load_state()
        if os.path.exists(SAVE_FILE):
            try:
                with open(SAVE_FILE, "rb") as f:
                    data = pickle.load(f)
                saved_version = data.get("version", "")
                if saved_version.split(".")[:2] != VERSION.split(".")[:2]:
                    # 版本不兼容，重命名文件
                    backup_file = f"{SAVE_FILE}.backup"
                    if os.path.exists(backup_file):
                        os.remove(backup_file)
                    os.rename(SAVE_FILE, backup_file)
                    logging.warning("版本不兼容，已重命名旧的序列化文件")
                else:
                    set_msg_nodes(data.get("msg_nodes", {}))
                    logging.info("已加载之前保存的状态")
            except Exception as e:
                logging.error(f"加载状态失败: {str(e)}")

    def handle_exit(*args):
        save_state()
        logging.info("程序退出")
        exit(0)

    # 注册信号处理器
    signal.signal(signal.SIGINT, handle_exit)
    signal.signal(signal.SIGTERM, handle_exit)

    # 启动前加载状态
    load_state()
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        save_state()
        logging.info("程序退出")
