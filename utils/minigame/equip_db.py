__weapon_db__ = {
    "铁剑":{
        "name":"铁剑",
        "item_buff":{
            "atk":3,
            "def":1,
            "luck":1,
        },
        "fit":"weapon"
    }

}

__armor_db__ = {
    "新人冒险家套装":{
        "name":"新人冒险家套装",
        "item_buff":{
            "atk":0,
            "def":3,
            "luck":1,
        },
        "fit":"armor"
    }
}

__item_db__ = {
    "生命药水":{
        "name":"生命药水",
        "item_buff_instant":{
            "hp":15
        },
        "fit":"cost"
    },
    "力量药水":{
        "name":"力量药水",
        "item_buff_duration":{
            "atk":15
        },
        "duration":300,
        "fit":"cost"
    }
}

def get_equip_info(item_id):
    """通用获取物品信息"""
    if item_id in __weapon_db__:
        return {'type': 'weapon', **__weapon_db__[item_id]}
    if item_id in __armor_db__:
        return {'type': 'armor', **__armor_db__[item_id]}
    return None

def get_weapon_state(db_index):
    return __weapon_db__.get(db_index)

def get_armor_state(db_index):
    return __armor_db__.get(db_index)

def get_item_state(db_index):
    return __item_db__.get(db_index)