from ..discords.menu import menu_item
import logging
import pickle
import time
import os
from .equip_db import get_equip_info, get_weapon_state, get_armor_state
import random
__game_state__ = {}
SAVE_FILE = "game_save.pkl"
VERSION = "1.0.0"
RANDOM_WEIGHTS = [(51 - x)**2 for x in range(5, 51)]
def game_save_state():
    try:
        with open(SAVE_FILE, "wb") as f:
            pickle.dump({"version": VERSION, "game_state": __game_state__}, f)
        logging.info("状态已保存到本地文件")
    except Exception as e:
        logging.error(f"保存状态失败: {str(e)}")


def game_load_state():
    global __game_state__
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
                logging.warning("游戏存档版本不兼容，已重命名旧的序列化文件")
            else:
                __game_state__ = data.get("game_state", {})
                logging.info("已加载游戏存档")
        except Exception as e:
            logging.error(f"加载状态失败: {str(e)}")

def special_tag_to_text(tag: str) -> str:
    return  ""

def state_to_text(state: dict) -> str:
    
    addition_effects = []
    current_time = time.time()
    for effect_id, effect in state["additon"].items():
        effect_name = get_equip_info(effect_id)["name"]
        left_duration = max(0, int(effect["duration"] - (current_time - effect["start_time"])))
        addition_effects.append(f"{effect_name}: 效果剩余 {left_duration} 秒结束")
    
    addition_text = "\n".join(addition_effects) if addition_effects else "无"
    
    return f"""你的属性如下：
金币: {state["coin"]}
武器: {get_weapon_state(state["weapon"]).get("name","无") if get_weapon_state(state["weapon"]) else "无"}
护甲: {get_armor_state(state["armor"]).get("name","无") if get_armor_state(state["armor"]) else "无"}
经验: {state["exp"]}
攻击: {state['state']["atk"]}
防御: {state['state']["def"]}
生命: {state['state']["hp"]} / {state['state']["max_hp"]}
幸运: {state['state']["luck"]}
附加效果: 
{addition_text}
"""
@menu_item(
    matches=["!公会注册","!注册","!zc"],
    title="注册",
    description="成为一名冒险者！",
)
async def sign_up(ctx,**kwargs):
    user_id = ctx.author.id
    if(user_id not in __game_state__):
        __game_state__[user_id] = {}
        __game_state__[user_id]['coin'] = 0
        __game_state__[user_id]['npc_attitude'] = 0
        __game_state__[user_id]['weapon'] = "铁剑"
        __game_state__[user_id]['armor'] = "新人冒险家套装"
        __game_state__[user_id]['backpack'] = {}
        __game_state__[user_id]['exp'] = 0
        __game_state__[user_id]['state'] = {
            "atk":1,
            "def":1,
            "hp":36,
            "max_hp":36,
            "luck":0,
        }
        __game_state__[user_id]['additon'] = {}
        __game_state__[user_id]['special_memory'] = {}
        await ctx.reply(f"<@{user_id}>恭喜你成为了一名冒险家！输入 `!状态` 查看你的信息。")
    else:
        await ctx.reply(f"<@{user_id}>你已经注册过啦！输入 `!状态` 查看你的信息。或输入 `!注销` 来重置你的数据！")

def calculate_total_state(user_id,full_state = False):
    """计算玩家最终属性（基础属性 + 装备加成 + 持续效果）"""
    user_state = __game_state__[user_id]
    base_state = user_state['state'].copy()
    
    # 装备加成
    weapon = get_weapon_state(user_state['weapon'])
    armor = get_armor_state(user_state['armor'])
    
    for eq in [weapon, armor]:
        if eq and 'item_buff' in eq:
            for attr, val in eq['item_buff'].items():
                base_state[attr] += val
    
    # 持续效果加成
    current_time = time.time()
    expired = []
    
    for effect_id, effect in user_state['additon'].items():
        if current_time - effect['start_time'] <= effect['duration']:
            for attr, val in effect['buff'].items():
                base_state[attr] += val
        else:
            expired.append(effect_id)
    
    # 清理过期效果
    for effect_id in expired:
        del user_state['additon'][effect_id]
    if full_state:
        full = user_state.copy()
        full['state'] = base_state
        return full

    return base_state

@menu_item(
    matches=["!装备","!zb","!equip"],
    title="装备",
    description="使用 `!装备 <物品名>` 来装备一个武器或护甲",
    binding_func_args=["item_id"]
)
async def equip_item(ctx, item_id,**kwargs):
    """装备物品逻辑"""
    user_id = ctx.author.id
    user = __game_state__.get(user_id)
    if not user:
        return await ctx.reply("请先使用 !注册 创建角色")
    
    item_info = get_equip_info(item_id)
    if not item_info:
        return await  ctx.reply("不存在或无法装备的物品")

    slot_type = item_info.get('fit')
    current_item = user.get(slot_type, None)
    
    # 验证物品是否在背包
    if user['backpack'].get(item_id, 0) < 1:
        return await ctx.reply("背包中没有这个物品")
    
    # 执行装备操作
    if current_item:
        # 卸下当前装备
        user['backpack'][current_item] = user['backpack'].get(current_item, 0) + 1
    
    # 装备新物品
    user[slot_type] = item_id
    user['backpack'][item_id] -= 1
    if user['backpack'][item_id] == 0:
        del user['backpack'][item_id]
    
    await ctx.reply(f"成功装备 {item_info['name']}!")

@menu_item(
    matches=["!卸下","!xx","!dequip"],
    title="卸下装备",
    description="使用 `!卸下 <武器|护甲>` 来卸下一个武器或护甲",
    binding_func_args=["slot_type"]
)
async def unequip_item(ctx, slot_type,**kwargs):
    """卸下装备逻辑"""
    _slot_type = "armor" if slot_type == "护甲" else "weapon"
    user_id = ctx.author.id
    user = __game_state__.get(user_id)
    if not user:
        return await ctx.reply("请先使用 !注册 创建角色")
    
    item_id = user.get(_slot_type)
    if not item_id:
        return await ctx.reply(f"当前没有装备{slot_type}")
    
    # 放回背包
    user['backpack'][item_id] = user['backpack'].get(item_id, 0) + 1
    user[_slot_type] = None
    await ctx.reply(f"已卸下 {get_equip_info(item_id)['name']}")

def use_item(ctx, item_id):
    """使用物品逻辑"""
    user_id = ctx.author.id
    user = __game_state__.get(user_id)
    if not user:
        return ctx.reply("请先使用 !注册 创建角色")
    
    item_info = get_equip_info(item_id)
    if not item_info or item_info['fit'] != 'cost':
        return ctx.reply("不可使用的物品")
    
    if user['backpack'].get(item_id, 0) < 1:
        return ctx.reply("背包中没有这个物品")
    
    # 处理即时效果
    if 'item_buff_instant' in item_info:
        for attr, val in item_info['item_buff_instant'].items():
            if attr == 'hp':
                user['state']['hp'] = min(user['state']['max_hp'], user['state']['hp'] + val)
            else:
                user['state'][attr] += val
    
    # 处理持续效果
    if 'item_buff_duration' in item_info:
        user['additon'][item_id] = {
            'start_time': time.time(),
            'duration': item_info['duration'],
            'buff': item_info['item_buff_duration']
        }
    
    # 消耗物品
    user['backpack'][item_id] -= 1
    if user['backpack'][item_id] == 0:
        del user['backpack'][item_id]
    
    ctx.reply(f"成功使用 {item_info['name']}!")

@menu_item(
    matches=["!背包","!bb","!check"],
    title="背包",
    description="查看你的背包",
)
async def show_backpack(ctx,**kwargs):
    """显示背包内容"""
    user_id = ctx.author.id
    user = __game_state__.get(user_id)
    if not user:
        return await ctx.reply("请先使用 `!注册` 创建角色")
    
    backpack = user['backpack']
    if not backpack:
        return await ctx.reply("背包空空如也")
    
    items = []
    for item_id, count in backpack.items():
        item_info = get_equip_info(item_id)
        name = item_info['name'] if item_info else f"未知物品({item_id})"
        items.append(f"{name} ×{count}")
    
    await ctx.reply("背包内容：\n" + "\n".join(items))

@menu_item(
    matches=["!状态","!zt"],
    title="状态",
    description="查看你当前的状态！",
)
async def check_status(ctx, **kwargs):
    user_id = ctx.author.id
    user = __game_state__.get(user_id)
    if not user:
        await ctx.reply("请先使用 `!注册` 创建角色")
        return
    await ctx.reply(state_to_text(calculate_total_state(user_id,True)))
@menu_item(
    matches=["!公会签到","!签到","!qd"],
    title="签到",
    description="每日在公会签到领取奖励！",
)
async def sign_in(ctx,**kwargs):
    user_id = ctx.author.id
    if user_id in __game_state__:
        sp_m = __game_state__[user_id].get("special_memory")
        if not sp_m:
            __game_state__[user_id]["special_memory"] = {}
        sign = __game_state__[user_id]["special_memory"].get("signed")
        if not sign:
            __game_state__[user_id]["special_memory"]["signed"] = {
                "times":0,
                "last_sign_time":0
            }
        last_sign_time = __game_state__[user_id]["special_memory"]["signed"]["last_sign_time"]
        current_time = time.time()
        if current_time - last_sign_time >= 8 * 3600:
            __game_state__[user_id]["special_memory"]["signed"]["times"] += 1
            __game_state__[user_id]["special_memory"]["signed"]["last_sign_time"] = current_time
            reward = random.choices(range(5, 51), weights=RANDOM_WEIGHTS, k=1)[0]  # 非均等概率，值越小概率越大
            __game_state__[user_id]["coin"] += reward  # 奖励金币
            await ctx.reply(f"<@{user_id}> 签到成功！你获得了 {reward} 金币。(最高可获得 50 金币！)")
        else:
            remaining_time = 8 * 3600 - (current_time - last_sign_time)
            hours, remainder = divmod(remaining_time, 3600)
            minutes, _ = divmod(remainder, 60)
            await ctx.reply(f"<@{user_id}> 距离下次签到还有 {int(hours)} 小时 {int(minutes)} 分钟。")