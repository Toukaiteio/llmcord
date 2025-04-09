import asyncio
from base64 import b64encode
from datetime import datetime as dt
from dataclasses import dataclass, field
from typing import Literal, Optional, List, Dict, AsyncGenerator
import httpx
from openai import AsyncOpenAI
import logging
import discord
from ..discords.menu import menu_item
VISION_MODEL_TAGS = ("gpt-4", "claude-3", "gemini", "gemma", "llama", "pixtral", "mistral-small", "vision", "vl")
streaming_indicator_list = "❤🧡💛💚💙💜🤎🖤🤍💕💓💗💖💘💝💟💌"

@dataclass
class AIConfig:
    provider: str
    model: str
    base_url: str
    api_key: str
    system_prompt: str
    max_text: int
    max_images: int
    max_messages: int
    extra_api_parameters: dict

@dataclass
class MessageNode:
    text: Optional[str] = None
    images: List[dict] = field(default_factory=list)
    role: Literal["user", "assistant"] = "assistant"
    user_id: Optional[str] = None
    parent_msg_id: Optional[int] = None

class AIGenerator:
    def __init__(self, config: AIConfig):
        self.config = config
        self.httpx_client = httpx.AsyncClient()
        self.openai_client = AsyncOpenAI(
            base_url=config.base_url,
            api_key=config.api_key
        )

    @staticmethod
    def get_streaming_indicator() -> str:
        return f"{streaming_indicator_list[int(dt.now().timestamp() * 2) % len(streaming_indicator_list)]} "

    async def process_attachments(self, attachments: List[dict]) -> tuple:
        """处理附件，返回（文本内容列表，图片内容列表）"""
        texts = []
        images = []
        
        for att in attachments:
            if att['content_type'].startswith('text'):
                resp = await self.httpx_client.get(att['url'])
                texts.append(resp.text)
            elif att['content_type'].startswith('image'):
                resp = await self.httpx_client.get(att['url'])
                b64 = b64encode(resp.content).decode('utf-8')
                images.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:{att['content_type']};base64,{b64}"}
                })
        
        return texts, images

    async def build_message_chain(
        self, 
        initial_message: dict,
        get_parent_message: callable
    ) -> List[dict]:
        """构建消息链"""
        messages = []
        current_msg = initial_message
        accept_images = any(x in self.config.model.lower() for x in VISION_MODEL_TAGS)
        accept_usernames = 'openai' in self.config.provider.lower()  # 示例逻辑
        
        while current_msg and len(messages) < self.config.max_messages:
            # 处理附件
            texts, images = await self.process_attachments(current_msg.get('attachments', []))
            
            # 构建消息内容
            content = []
            if text_content := current_msg.get('content', ''):
                content.append({"type": "text", "text": text_content[:self.config.max_text]})
            
            if accept_images:
                content.extend(images[:self.config.max_images])
            
            # 构建消息字典
            message = {
                "role": current_msg.get('role', 'user'),
                "content": content
            }
            
            if accept_usernames and (user_id := current_msg.get('user_id')):
                message["name"] = str(user_id)
            
            messages.append(message)
            
            # 获取上一条消息
            if parent_id := current_msg.get('parent_msg_id'):
                current_msg = await get_parent_message(parent_id)
            else:
                current_msg = None
        
        # 添加系统提示
        if self.config.system_prompt:
            system_content = [self.config.system_prompt]
            if accept_usernames:
                system_content.append(f"用户ID: <@{initial_message['user_id']}>")
            
            messages.append({
                "role": "system",
                "content": "\n".join(system_content)
            })
        
        return messages[::-1]  # 反转顺序为历史优先

    async def generate_response(
        self, 
        messages: List[dict]
    ) -> AsyncGenerator[str, None]:
        """流式生成AI响应"""
        async for chunk in await self.openai_client.chat.completions.create(
            model=self.config.model,
            messages=messages,
            stream=True,
            **self.config.extra_api_parameters
        ):
            if content := chunk.choices[0].delta.content:
                yield content

    async def generate_full_response(
        self,
        initial_message: dict,
        get_parent_message: callable
    ) -> str:
        """完整生成响应（非流式）"""
        messages = await self.build_message_chain(initial_message, get_parent_message)
        response = await self.openai_client.chat.completions.create(
            model=self.config.model,
            messages=messages,
            **self.config.extra_api_parameters
        )
        return response.choices[0].message.content

    async def close(self):
        """清理资源"""
        await self.httpx_client.aclose()
        await self.openai_client.close()

msg_nodes = {}
MAX_MESSAGE_NODES = 100

def get_msg_nodes():
    """获取消息节点"""
    return msg_nodes

def set_msg_nodes(nodes):
    """设置消息节点"""
    global msg_nodes
    msg_nodes.update(nodes)


@menu_item(
    matches=["!对话", "!聊天", "!chat", "!talk", "!lt", "!c", "!t", "!"],
    title="聊天",
    description="与AI聊天",
)
async def handler(ctx,discord_client,cfg,**kwargs):
    # 初始化配置
    new_msg = ctx
    provider, model = cfg["model"].split("/", 1)
    ai_config = AIConfig(
        provider=provider,
        model=model,
        base_url=cfg["providers"][provider]["base_url"],
        api_key=cfg["providers"][provider].get("api_key", "sk-no-key-required"),
        system_prompt=cfg["system_prompt"],
        max_text=cfg["max_text"],
        max_images=cfg["max_images"],
        max_messages=cfg["max_messages"],
        extra_api_parameters=cfg["extra_api_parameters"],
    )
    ai_generator = AIGenerator(ai_config)

    # 定义父消息获取器
    async def get_parent_message(message_id: int) -> Optional[dict]:
        try:
            parent_msg = await new_msg.channel.fetch_message(message_id)
            return {
                "content": parent_msg.content,
                "attachments": [
                    {"url": att.url, "content_type": att.content_type}
                    for att in parent_msg.attachments
                ],
                "role": (
                    "assistant" if parent_msg.author == discord_client.user else "user"
                ),
                "user_id": parent_msg.author.id,
                "parent_msg_id": (
                    parent_msg.reference.message_id if parent_msg.reference else None
                ),
            }
        except Exception as e:
            logging.error(f"获取父消息失败: {str(e)}")
            return None

    # 检查新消息发送者是否与父消息的发送者一致
    if new_msg.reference and new_msg.reference.message_id:
        parent_msg = await get_parent_message((await get_parent_message(new_msg.reference.message_id))["parent_msg_id"])
        if parent_msg and parent_msg["user_id"] != new_msg.author.id:
            await new_msg.reply(f'🔒<@{new_msg.author.id}>该对话不属于你,而属于<@{parent_msg["user_id"]}>')
            return

    # 构建初始消息
    initial_message = {
        "content": new_msg.content.removeprefix(discord_client.user.mention).strip(),
        "attachments": [
            {"url": att.url, "content_type": att.content_type}
            for att in new_msg.attachments
        ],
        "role": "user",
        "user_id": new_msg.author.id,
        "parent_msg_id": new_msg.reference.message_id if new_msg.reference else None,
        "timestamp": new_msg.created_at.isoformat(),
    }

    # 生成响应
    response_msgs = []
    # 修改后的响应处理部分
    try:
        # 构建消息链
        messages = await ai_generator.build_message_chain(initial_message, get_parent_message)
        
        # 保持原始响应分片逻辑
        use_plain_responses = cfg["use_plain_responses"]
        max_length = 2000 if use_plain_responses else 4096
        streaming_indicator = AIGenerator.get_streaming_indicator()
        
        # 流式生成响应
        buffer = ""
        last_send_time = dt.now()
        reply_to = new_msg
        
        async for chunk in ai_generator.generate_response(messages):
            buffer += chunk
            
            # 处理纯文本模式
            if use_plain_responses:
                if len(buffer) >= max_length:
                    await reply_to.reply(buffer[:max_length], suppress_embeds=True)
                    buffer = buffer[max_length:]
                    reply_to = response_msgs[-1] if response_msgs else new_msg
            # 处理Embed模式
            else:
                current_time = dt.now()
                time_diff = (current_time - last_send_time).total_seconds()
                
                # 满足以下任一条件时发送更新：
                # 1. 缓冲区达到最大长度
                # 2. 超过1秒未更新
                # 3. 收到完整句子（以句号结尾）
                if len(buffer) >= max_length or time_diff > 1 or chunk.endswith('。'):
                    # 创建或更新Embed
                    if not response_msgs:
                        embed = discord.Embed(
                            description=f"{buffer}{streaming_indicator}",
                            color=discord.Color.orange()
                        )
                        sent_msg = await reply_to.reply(embed=embed)
                        response_msgs.append(sent_msg)
                    else:
                        embed = response_msgs[-1].embeds[0]
                        embed.description = f"{buffer}{streaming_indicator}"
                        await response_msgs[-1].edit(embed=embed)
                    
                    last_send_time = current_time

        # 发送最终结果
        if buffer:
            if use_plain_responses:
                while buffer:
                    chunk = buffer[:2000]
                    await reply_to.reply(chunk, suppress_embeds=True)
                    buffer = buffer[2000:]
            else:
                embed = discord.Embed(
                    description=buffer,
                    color=discord.Color.green()
                )
                if response_msgs:
                    await response_msgs[-1].edit(embed=embed)
                else:
                    await new_msg.reply(embed=embed)

    except Exception as e:
        logging.error(f"生成失败: {str(e)}")
        error_embed = discord.Embed(
            title="⚠️ 生成错误",
            description="处理请求时发生错误，请稍后再试",
            color=discord.Color.red()
        )
        await new_msg.reply(embed=error_embed)
    # 保持原始缓存清理逻辑
    if len(msg_nodes) > MAX_MESSAGE_NODES:
        for msg_id in list(msg_nodes.keys())[: len(msg_nodes) - MAX_MESSAGE_NODES]:
            del msg_nodes[msg_id]