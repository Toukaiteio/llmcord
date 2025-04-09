from functools import wraps

# 使用字典存储非通配符的匹配项，通配符单独存储
__menu_registry__ = {}
__menu_wildcard__ = []

def get_menu_map():
    """获取全部菜单映射"""
    return __menu_registry__, __menu_wildcard__

def add_menu(menu):
    """添加菜单项，支持多个匹配符"""
    # 确保菜单项有匹配规则且为列表形式
    assert 'matches' in menu and isinstance(menu['matches'], list), "菜单必须包含 matches 列表"
    
    for match in menu['matches']:
        if match == "*":
            __menu_wildcard__.append(menu)
        else:
            # 为每个匹配符注册菜单项
            __menu_registry__.setdefault(match, []).append(menu)

def get_matched_menus(match_str):
    """获取匹配的菜单项，无匹配时返回通配符菜单"""
    return __menu_registry__.get(match_str, __menu_wildcard__)

def menu_item(matches, title, description, binding_func_args=None, binding_func_kwargs=None):
    """装饰器，用于注册菜单项"""
    def decorator(func):
        add_menu({
            "matches": matches,
            "title": title,
            "description": description,
            "binding_func": func,
            "binding_func_args": binding_func_args or [],
            "binding_func_kwargs": binding_func_kwargs or {},
        })
        @wraps(func)
        async def wrapper(*args, **kwargs):
            return await func(*args, **kwargs)
        return wrapper
    return decorator
    

def init_menu():
    """初始化菜单示例"""
    @menu_item(
        matches=["*"],
        title="帮助",
        description="显示帮助信息",
    )
    async def show_help_simply(ctx,**kwargs):
        await ctx.reply(dump_help_list())

    @menu_item(
        matches=["!详细帮助", "!xz"],
        title="详细帮助",
        description="显示高级帮助",
    )
    async def show_help(ctx,**kwargs):
        await ctx.reply(dump_help_list(False))



def dump_help_list(simplified=True):
    """生成菜单帮助列表，排除通配符菜单项"""
    # 去重并收集所有非通配符菜单项
    seen = set()
    unique_menus = []
    for menu_set in __menu_registry__.values():
        for menu in menu_set:
            # 通过对象内存地址去重
            if id(menu) not in seen:
                seen.add(id(menu))
                unique_menus.append(menu)
    
    # 按标题排序
    sorted_menus = sorted(unique_menus, key=lambda m: m["title"])
    
    # 生成帮助文本行
    lines = []
    for menu in sorted_menus:
        # 过滤通配符，保留有效匹配符
        valid_matches = [f"`{m}`" for m in menu["matches"] if m != "*"]
        if not valid_matches:
            continue  # 理论上不会触发，防御性编程
        
        # 构造命令提示字符串
        cmd_str = "、".join(valid_matches)
        
        # 根据模式生成行内容
        if simplified:
            line = f"{menu['title']} - [使用命令:{cmd_str}]"
        else:
            desc = menu.get("description", "")
            line = f"{menu['title']} - {desc} [使用命令:{cmd_str}]"
        
        lines.append(line)
    
    # 组合最终输出
    return "菜单列表:\n" + "\n".join(lines) if lines else "暂无可用菜单"

async def execute_menu(menu, ctx, **kwargs):
    """执行菜单项绑定的功能函数
    
    Args:
        menu: 菜单项字典，需包含 binding_func 等字段
        ctx: 上下文对象，通常包含会话信息
        **kwargs: 动态关键字参数，会覆盖菜单项预设参数
    
    Returns:
        绑定函数的执行结果，若出错返回 None
    """
    # 参数校验
    if not isinstance(menu, dict):
        raise TypeError("菜单项必须为字典类型")
    
    binding_func = menu.get("binding_func")
    if not callable(binding_func):
        raise ValueError("菜单项缺少有效的 binding_func")
    
    # 合并参数：菜单预设参数 + 动态传入参数（后者优先级高）
    preset_kwargs = menu.get("binding_func_kwargs", {})
    merged_kwargs = {**preset_kwargs, **kwargs}  # 合并字典
    
    try:
        # 执行函数：ctx 作为首个参数，预设位置参数随后，合并的关键字参数最后
        return await binding_func(ctx, **merged_kwargs)
    except Exception as e:
        # 异常处理（含友好错误提示）
        error_detail = f"执行菜单 [{menu.get('title', '无标题')}] 时出错: {str(e)}"
        if hasattr(ctx, "reply"):
            await ctx.reply(f"❌ 操作失败: {error_detail}")
        else:
            print(f"[ERROR] {error_detail}")  # 无上下文时的降级处理
        
        return None